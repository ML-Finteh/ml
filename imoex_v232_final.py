"""
================================================================================
IMOEX ДИНАМИЧЕСКАЯ СТРАТЕГИЯ V2.3.2 — БАРОМЕТР С АГРЕГАЦИЕЙ
(ИСПРАВЛЕННАЯ СПЕЦИФИКАЦИЯ КОНТРАКТОВ MOEX + ЗАГРУЗКА OHLCV)
================================================================================
Изменения (взяты из V2.3.3):
- Исправлена генерация кодов контрактов для MOEX (буквенные коды месяцев и года)
- Обновлён список контрактов (только реальные: PLZLM, NOTKM, SBRF, GAZR и т.д.)
- Добавлена задержка и retry в load_imoex_data
- Исправлен метод _fetch_futures_candles (использует правильные MOEX-коды)
- Все остальные части (торговая логика, фазы, агрегация, email) сохранены без изменений

Email: olegmirk@yandex.ru -> rinatsafin1@ya.ru
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests
import warnings
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import smtplib
import ssl
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import io
warnings.filterwarnings('ignore')


# =============================================================================
# КОНФИГУРАЦИЯ КОНТРАКТОВ (ИСПРАВЛЕННАЯ)
# =============================================================================
ASSET_CONTRACTS = {
    'ALRS':   [('ALRS', 1)],
    'PLZL':   [('PLZLM', 10)],      # только мини
    'VTBR':   [('VTBR', 100)],
    'MGNT':   [('MGNT', 1)],
    'NVTK':   [('NOTKM', 10)],      # только мини
    'ROSN':   [('ROSN', 10)],
    'GMKN':   [('GMKN', 1)],
    'YDEX':   [('YDEX', 1)],
    'GAZR':   [('GAZR', 100), ('GAZPF', 100)],
    'LKOH':   [('LKOH', 1)],
    'SBRF':   [('SBRF', 100), ('SBERF', 100)],
    'MIX':    [('MIX', 1)],
    'MXI':    [('MXI', 1)],
    'IMOEXF': [('IMOEXF', 10)],
}

CONTRACT_MULTIPLIERS = {}
CONTRACT_TO_ASSET = {}
for asset, contract_list in ASSET_CONTRACTS.items():
    for code, mult in contract_list:
        CONTRACT_TO_ASSET[code] = asset
        CONTRACT_MULTIPLIERS[code] = mult

ALL_CONTRACT_CODES = [code for sublist in ASSET_CONTRACTS.values() for code, _ in sublist]


# =============================================================================
# ГЕНЕРАЦИЯ КОДОВ КОНТРАКТОВ MOEX (ИСПРАВЛЕННАЯ)
# =============================================================================
CONTRACT_INFO = {
    'ALRS':   {'prefix': 'AL', 'type': 'quarterly'},
    'PLZLM':  {'prefix': 'PX', 'type': 'quarterly'},
    'VTBR':   {'prefix': 'VB', 'type': 'quarterly'},
    'MGNT':   {'prefix': 'MN', 'type': 'quarterly'},
    'NOTKM':  {'prefix': 'NV', 'type': 'quarterly'},
    'ROSN':   {'prefix': 'RN', 'type': 'quarterly'},
    'GMKN':   {'prefix': 'GK', 'type': 'quarterly'},
    'YDEX':   {'prefix': 'YD', 'type': 'quarterly'},
    'GAZR':   {'prefix': 'GZ', 'type': 'quarterly'},
    'GAZPF':  {'prefix': 'GAZPF', 'type': 'eternal'},
    'LKOH':   {'prefix': 'LK', 'type': 'quarterly'},
    'SBRF':   {'prefix': 'SR', 'type': 'quarterly'},
    'SBERF':  {'prefix': 'SBERF', 'type': 'eternal'},
    'MIX':    {'prefix': 'MX', 'type': 'quarterly'},
    'MXI':    {'prefix': 'MM', 'type': 'quarterly'},
    'IMOEXF': {'prefix': 'IMOEXF', 'type': 'eternal'},
}

MONTH_CODES = {
    1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
    7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'
}

def get_third_thursday(y, m):
    d = date(y, m, 1)
    while d.weekday() != 3:
        d += timedelta(days=1)
    d += timedelta(days=14)
    return d

def get_contract_code(asset, dt):
    """
    Возвращает код фьючерсного контракта для MOEX (например, SRH6 для SBRF-3.26)
    """
    if pd.isnull(dt) or not asset:
        return ''
    info = CONTRACT_INFO.get(asset)
    if info is None:
        return asset
    if info['type'] == 'eternal':
        return info['prefix']
    prefix = info['prefix']
    # Приводим dt к date для корректного сравнения
    if hasattr(dt, 'date'):
        dt = dt.date()
    y = dt.year
    m = dt.month
    d = dt.day
    q_months = [3, 6, 9, 12]
    exp_month = None
    for qm in q_months:
        third_thu = get_third_thursday(y, qm)
        if dt <= third_thu:
            exp_month = qm
            break
    if exp_month is None:
        exp_month = 3
        y += 1
    month_code = MONTH_CODES.get(exp_month, 'Z')
    year_code = str(y)[-1]
    return prefix + month_code + year_code


# =============================================================================
# EMAIL NOTIFIER (без изменений)
# =============================================================================
class SignalNotifier:
    def __init__(self):
        self.smtp_host = "smtp.yandex.ru"
        self.smtp_port = 465
        self.smtp_user = "olegmirk@yandex.ru"
        self.smtp_password = "vsxyapxitouwiohq"
        self.email_from = "olegmirk@yandex.ru"
        self.email_to = "rinatsafin1@ya.ru"
        self.enabled = all([self.smtp_user, self.smtp_password, self.email_to])
        if not self.enabled:
            print("[WARN] Email notifications disabled")

    def _send(self, subject, body_html, body_text, attachments=None):
        if not self.enabled:
            return False
        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = self.email_from
            msg["To"] = self.email_to

            body_part = MIMEMultipart("alternative")
            body_part.attach(MIMEText(body_text, "plain", "utf-8"))
            body_part.attach(MIMEText(body_html, "html", "utf-8"))
            msg.attach(body_part)

            if attachments:
                for filename, data_bytes in attachments:
                    part = MIMEApplication(data_bytes, Name=filename)
                    part['Content-Disposition'] = 'attachment; filename="' + filename + '"'
                    msg.attach(part)

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, self.email_to, msg.as_string())
            print("[OK] Email sent: " + subject)
            return True
        except Exception as e:
            print("[ERR] Email failed: " + str(e))
            return False

    def _get_phase_names(self):
        return {
            0: 'Нейтральная',
            1: 'Накопление (Accumulation)',
            2: 'Распределение (Distribution)',
            3: 'Ослабление тренда',
            4: 'Аккумуляция (Mark-down)'
        }

    def _get_phase_arg(self, phase):
        if phase == 4:
            return ("Крупные игроки накапливают активы по низким ценам. "
                    "Рынок падает, но формируется база для будущего роста.")
        elif phase == 3:
            return ("Тренд ослабел, цена ниже EMA50, но ещё выше MA126. "
                    "Профессионалы начинают фиксировать прибыль.")
        elif phase == 2:
            return ("Активы распределяются от профессионалов к толпе. "
                    "Цена растёт, но риск увеличивается.")
        elif phase == 1:
            return ("Рынок начинает восстанавливаться. "
                    "Цена выше EMA15/EMA50, но ещё ниже MA126.")
        else:
            return "Рынок в неопределённом состоянии."

    def send_status_report(self, date, cagr, max_dd, sharpe, current_signal,
                           last_price, ema_fast, ema_slow, adx, regime, days_out,
                           last_trade_date, days_gap, entry_mode,
                           trades_count, win_rate, time_in_market, wyckoff_phase=0,
                           avg_phase_durations=None, current_phase_duration=0,
                           barometer_data=None, barometer_df=None, final_capital=None,
                           target_assets=None,
                           ohlcv_futures_df=None,
                           raw_oi_df=None, raw_ohlcv_df=None):
        # (полная копия из предыдущей версии, без изменений)
        phase_names = self._get_phase_names()
        phase_name = phase_names.get(wyckoff_phase, 'Неизвестно')
        phase_arg = self._get_phase_arg(wyckoff_phase)
        status = "🟢 В ПОЗИЦИИ" if current_signal == 1 else "🔴 ВНЕ РЫНКА"

        subject = "📊 IMOEX REPORT | " + date.strftime('%Y-%m-%d') + " | " + status + " | Фаза: " + phase_name

        avg_duration_text = f"Средняя длительность непрерывной фазы «{phase_name}»: {avg_phase_durations.get(wyckoff_phase, 0):.0f} дн." if avg_phase_durations else ""
        current_duration_text = f"Текущая непрерывная фаза длится уже: {current_phase_duration} дн." if current_phase_duration else ""
        clarification = ("Средняя длительность рассчитана для непрерывных отрезков одной фазы. "
                         "Полный цикл (например, медвежий рынок) обычно состоит из чередования "
                         "фаз Ослабления тренда и Аккумуляции и длится дольше.")

        body_text = f"""ОТЧЁТ ПО СТРАТЕГИИ IMOEX V2.3.2
================================
Дата запуска: {date.strftime('%Y-%m-%d %H:%M:%S')}
Дата данных: {last_trade_date}

📈 РЕЗУЛЬТАТЫ БЭКТЕСТА (2003-2026)
CAGR: {cagr:.2f}%
Max Drawdown: {max_dd:.2f}%
Sharpe: {sharpe:.2f}
Сделок: {trades_count}
Win Rate: {win_rate:.1f}%
Время в рынке: {time_in_market:.1f}%

📊 ТЕКУЩИЙ СИГНАЛ
Статус: {status}
Цена IMOEX (Close): {last_price:,.2f} ₽
EMA15: {ema_fast:,.2f} ₽
EMA50: {ema_slow:,.2f} ₽
ADX: {adx:.1f}
Режим: {regime} ({'слабый' if regime==0 else 'средний' if regime==1 else 'сильный'})
Дней вне рынка: {days_out}
Тип входа: {entry_mode}

🔄 ФАЗА ВАЙКОФФА (информационно)
Текущая фаза: {phase_name}
{phase_arg}
{avg_duration_text}
{current_duration_text}
{clarification}

Фаза определяется по положению цены относительно EMA15, EMA50 и MA126.
НЕ влияет на торговые решения — только для аналитики и понимания контекста рынка.
"""
        if days_gap > 0:
            body_text += f"\n⚠️ Данные устарели на {days_gap} дней!"

        # HTML
        ohlcv_html = ""

        barometer_conclusion = (
            'Институционалы доминируют — бычий настрой.' if barometer_data and barometer_data.get('composite', 0) > 15 else
            'Нейтральная картина — ожидайте подтверждения.' if barometer_data and barometer_data.get('composite', 0) > -15 else
            'Розница доминирует — медвежий настрой.'
        )
        barometer_disclaimer = (
            'Smart Money Barometer — инструмент анализа соотношения позиций юридических и физических лиц. '
            'Не является торговой рекомендацией.'
        )

        body_html = f"""<html><body style="font-family:Arial">
        <h2 style="color:#1565c0">📊 IMOEX V2.3.2 — Отчёт</h2>
        <p>Дата запуска: <b>{date.strftime('%Y-%m-%d %H:%M:%S')}</b> | Дата данных: <b>{last_trade_date}</b></p>

        <h3 style="color:#2e7d32">📈 Результаты бэктеста (2003-2026)</h3>
        <table style="border-collapse:collapse;width:500px">
        <tr><td style="padding:8px;border:1px solid #ddd"><b>CAGR</b></td><td style="padding:8px;border:1px solid #ddd;font-weight:bold;color:#2e7d32">{cagr:.2f}%</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Max Drawdown</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;font-weight:bold;color:#c62828">{max_dd:.2f}%</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Sharpe</b></td><td style="padding:8px;border:1px solid #ddd">{sharpe:.2f}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Сделок</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{trades_count}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Win Rate</b></td><td style="padding:8px;border:1px solid #ddd">{win_rate:.1f}%</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Время в рынке</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{time_in_market:.1f}%</td></tr>
        </table>

        {ohlcv_html}

        <h3 style="color:#1565c0">📊 Текущий сигнал</h3>
        <table style="border-collapse:collapse;width:500px">
        <tr><td style="padding:8px;border:1px solid #ddd;background:{'#e8f5e9' if current_signal==1 else '#ffebee'}"><b>Статус</b></td>
        <td style="padding:8px;border:1px solid #ddd;background:{'#e8f5e9' if current_signal==1 else '#ffebee'};font-weight:bold;font-size:16px">{status}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Цена IMOEX (Close)</b></td><td style="padding:8px;border:1px solid #ddd">{last_price:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>EMA15</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{ema_fast:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>EMA50</b></td><td style="padding:8px;border:1px solid #ddd">{ema_slow:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>ADX</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{adx:.1f}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Режим</b></td><td style="padding:8px;border:1px solid #ddd">{regime} ({'слабый' if regime==0 else 'средний' if regime==1 else 'сильный'})</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Дней вне рынка</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{days_out}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Тип входа</b></td><td style="padding:8px;border:1px solid #ddd">{entry_mode}</td></tr>
        </table>

        <h3 style="color:#e65100">🔄 Фаза Вайкоффа (информационно)</h3>
        <table style="border-collapse:collapse;width:500px">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Текущая фаза</b></td><td style="padding:8px;border:1px solid #ddd;background:#fff3e0;font-weight:bold;font-size:16px">{phase_name}</td></tr>
        <tr><td colspan="2" style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Аргументация:</b> {phase_arg}</td></tr>
        <tr><td colspan="2" style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Средняя длительность серии:</b> {avg_phase_durations.get(wyckoff_phase, 0):.0f} дн. | <b>Текущая серия:</b> {current_phase_duration} дн.</td></tr>
        <tr><td colspan="2" style="padding:8px;border:1px solid #ddd;color:#666;font-size:12px">
        {clarification}<br><br>
        Фаза определяется по положению цены относительно EMA15, EMA50 и MA126.<br>
        <b>НЕ влияет на торговые решения</b> — только для аналитики и понимания контекста рынка.
        </td></tr>
        </table>

        {'<p style="color:#c62828;font-weight:bold">⚠️ Данные устарели на ' + str(days_gap) + ' дней!</p>' if days_gap > 0 else ''}

        {'<h3 style="color:#1565c0">📊 Smart Money Barometer (информационно)</h3>' +
        '<table style="border-collapse:collapse;width:500px">' +
        '<tr><td style="padding:8px;border:1px solid #ddd;background:#e8f5e9"><b>Сигнал барометра</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:#e8f5e9;font-weight:bold">' + str(barometer_data.get('signal', 'N/A')) + '</td></tr>' +
        '<tr><td colspan="2" style="padding:8px;border:1px solid #ddd;background:#f5f5f5">' +
        '<b>Зона барометра:</b> ' + str(barometer_data.get('signal', '⚪ N/A')) + ' (Score: ' + f"{barometer_data.get('composite', 0):+.1f}" + ')<br>' +
        '<span style="color:#666;font-size:12px">' + (
            'Экстремальный бычий сигнал — профи доминируют, толпа в панике.' if barometer_data.get('composite', 0) > 40 else
            'Лёгкое бычье преимущество, но не уверенное.' if barometer_data.get('composite', 0) > 15 else
            'Нейтралитет — нет чёткого преимущества ни у одной стороны.' if barometer_data.get('composite', 0) > -15 else
            'Лёгкое медвежье преимущество, толпа переоценивает рост.' if barometer_data.get('composite', 0) > -40 else
            'Экстремальный медвежий сигнал — толпа в эйфории, профи накапливают.'
        ) + '</span></td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd"><b>Δ доли Юрлиц (10 дней)</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd">' + f"{barometer_data.get('smart_delta_10d', 0):+.2f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd"><b>Доля Юрлиц (всего)</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd">' + f"{barometer_data.get('index_smart_control', 0):.1f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_net_jur', 0) >= 0 else '#ffebee') + '"><b>Нетто-позиция Юрлиц</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_net_jur', 0) >= 0 else '#ffebee') + ';font-weight:bold;color:' + ('#2e7d32' if barometer_data.get('index_net_jur', 0) >= 0 else '#c62828') + '">' + f"{barometer_data.get('index_net_jur', 0):+.1f}" + '% (' + ('лонг' if barometer_data.get('index_net_jur', 0) >= 0 else 'шорт') + ')</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_jur_long_ratio', 50) >= 50 else '#ffebee') + '"><b>Доля лонгов среди Юрлиц</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_jur_long_ratio', 50) >= 50 else '#ffebee') + ';font-weight:bold;color:' + ('#2e7d32' if barometer_data.get('index_jur_long_ratio', 50) >= 50 else '#c62828') + '">' + f"{barometer_data.get('index_jur_long_ratio', 50):.1f}" + '%</td></tr>' +

        '<tr><td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_net_fiz', 0) >= 0 else '#ffebee') + '"><b>Нетто-позиция Физлиц</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_net_fiz', 0) >= 0 else '#ffebee') + ';font-weight:bold;color:' + ('#2e7d32' if barometer_data.get('index_net_fiz', 0) >= 0 else '#c62828') + '">' + f"{barometer_data.get('index_net_fiz', 0):+.1f}" + '% (' + ('лонг' if barometer_data.get('index_net_fiz', 0) >= 0 else 'шорт') + ')</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_fiz_long_ratio', 50) >= 50 else '#ffebee') + '"><b>Доля лонгов среди Физлиц</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:' + ('#e8f5e9' if barometer_data.get('index_fiz_long_ratio', 50) >= 50 else '#ffebee') + ';font-weight:bold;color:' + ('#2e7d32' if barometer_data.get('index_fiz_long_ratio', 50) >= 50 else '#c62828') + '">' + f"{barometer_data.get('index_fiz_long_ratio', 50):.1f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>MXI Сигнал</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">' + str(barometer_data.get('mxi_signal', 'N/A')) + '</td></tr>' +
        (('<tr><td style="padding:8px;border:1px solid #ddd;background:#e3f2fd"><b>MXI Розница</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:#e3f2fd">' + f"{barometer_data.get('mxi', {}).get('retail_pct', 0):.1f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd"><b>MXI Чистая поз. розницы</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd">' + f"{barometer_data.get('mxi', {}).get('net_fiz', 0):+,.0f}" + '</td></tr>') if barometer_data and barometer_data.get('mxi') else '') +
        '<tr><td colspan="2" style="padding:8px;border:1px solid #ddd;color:#333;font-size:12px;background:#fff8e1">' +
        '<b>📊 Вывод:</b> ' + barometer_conclusion + '<br><br>' +
        '<span style="color:#666">' + barometer_disclaimer + '</span>' +
        '</td></tr></table>' if barometer_data else ''}

        </body></html>"""

        # Формируем CSV: все контракты + сводка
        attachments = []
        if raw_oi_df is not None and raw_ohlcv_df is not None and not raw_oi_df.empty and not raw_ohlcv_df.empty:
            oi = raw_oi_df.copy()
            oi['date'] = pd.to_datetime(oi['date'])
            ohlcv = raw_ohlcv_df.copy()
            ohlcv['date'] = pd.to_datetime(ohlcv['date'])
            combined = oi.merge(ohlcv, on=['date', 'contract'], how='left')
            if 'asset_x' in combined.columns and 'asset_y' in combined.columns:
                combined['asset'] = combined['asset_x']
                combined = combined.drop(columns=['asset_x', 'asset_y'])
            elif 'asset' not in combined.columns:
                combined['asset'] = combined['contract'].map(CONTRACT_TO_ASSET)
            combined = combined.loc[:, ~combined.columns.duplicated()]
            combined = combined.sort_values(['asset', 'contract', 'date'])
            combined.insert(0, '№', range(1, len(combined) + 1))
            cols = ['№', 'date', 'asset', 'contract', 'total_oi', 'fiz_oi', 'yur_oi',
                    'fiz_share', 'yur_share', 'long_fiz', 'short_fiz', 'long_jur', 'short_jur',
                    'open', 'high', 'low', 'close', 'volume']
            cols_present = [c for c in cols if c in combined.columns]
            combined = combined[cols_present]

            # Сводка по тикерам
            summary_rows = []
            if barometer_df is not None and not barometer_df.empty:
                summary_rows.append({})
                summary_rows.append({'№': '', 'date': '=== ОТЧЁТ ПО ТИКЕРАМ (АГРЕГИРОВАННЫЙ) ===',
                                     'asset': '', 'contract': '',
                                     'total_oi': '', 'fiz_oi': '', 'yur_oi': '',
                                     'fiz_share': '', 'yur_share': 'Изменение доли юриков',
                                     'long_fiz': '', 'short_fiz': '', 'long_jur': '', 'short_jur': '',
                                     'open': '', 'high': '', 'low': '', 'close': '', 'volume': ''})
                custom_order = ['ALRS', 'PLZL', 'VTBR', 'MGNT', 'NVTK', 'ROSN',
                                'GMKN', 'YDEX', 'GAZR', 'LKOH', 'SBRF', 'MXI', 'MIX', 'IMOEXF']
                for asset in custom_order:
                    if asset not in barometer_df['asset'].values:
                        summary_rows.append({
                            '№': '', 'date': '', 'asset': asset, 'contract': asset,
                            'total_oi': '', 'fiz_oi': '', 'yur_oi': '',
                            'fiz_share': '', 'yur_share': 'Нет данных',
                            'long_fiz': '', 'short_fiz': '', 'long_jur': '', 'short_jur': '',
                            'open': '', 'high': '', 'low': '', 'close': '', 'volume': ''
                        })
                        continue
                    asset_df = barometer_df[barometer_df['asset'] == asset].sort_values('date')
                    count = len(asset_df)
                    valid = asset_df.dropna(subset=['yur_share'])
                    if len(valid) >= 2:
                        last_yur = valid['yur_share'].iloc[-1]
                        prev_yur = valid['yur_share'].iloc[-2]
                        delta = last_yur - prev_yur
                        delta_str = f"{delta:+.2f}%"
                    elif len(valid) == 1:
                        last_yur = valid['yur_share'].iloc[0]
                        delta_str = "N/A (1 запись)"
                    else:
                        last_yur = 0
                        delta_str = "N/A"
                    summary_rows.append({
                        '№': '', 'date': '', 'asset': asset, 'contract': asset,
                        'total_oi': '', 'fiz_oi': '', 'yur_oi': '',
                        'fiz_share': '', 'yur_share': f'{last_yur:.2f}% ({delta_str})' if count > 0 else 'Нет данных',
                        'long_fiz': '', 'short_fiz': '', 'long_jur': '', 'short_jur': '',
                        'open': '', 'high': '', 'low': '', 'close': '', 'volume': ''
                    })

            summary_df = pd.DataFrame(summary_rows)
            for col in combined.columns:
                if col not in summary_df.columns:
                    summary_df[col] = ''
            summary_df = summary_df[combined.columns]
            combined_final = pd.concat([combined, summary_df], ignore_index=True)

            csv_buffer = io.StringIO()
            combined_final.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
            csv_bytes = csv_buffer.getvalue().encode("utf-8-sig")
            attachments.append((f"imoex_data_{last_trade_date}.csv", csv_bytes))

        elif barometer_df is not None and not barometer_df.empty:
            combined = barometer_df.copy()
            if 'type' in combined.columns:
                combined = combined.drop(columns=['type'])
            combined['contract'] = combined['asset'] + '_AGG'
            cols = combined.columns.tolist()
            asset_idx = cols.index('asset')
            cols.insert(asset_idx + 1, cols.pop(cols.index('contract')))
            combined = combined[cols]
            combined.insert(0, '№', range(1, len(combined) + 1))
            csv_buffer = io.StringIO()
            combined.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
            csv_bytes = csv_buffer.getvalue().encode("utf-8-sig")
            attachments.append((f"imoex_data_{last_trade_date}.csv", csv_bytes))

        return self._send(subject, body_html, body_text, attachments=attachments)


# =============================================================================
# MOEX BAROMETER LAYER (ИСПРАВЛЕННАЯ ЗАГРУЗКА OHLCV)
# =============================================================================
class MOEXBarometerLayer:
    IMOEX_WEIGHTS = {
        'SBRF': 0.16, 'LKOH': 0.14, 'GAZR': 0.10, 'YDEX': 0.07,
        'GMKN': 0.06, 'ROSN': 0.05, 'NVTK': 0.05, 'MGNT': 0.04,
        'PLZL': 0.03, 'VTBR': 0.03, 'ALRS': 0.02,
    }
    MXI_TICKER = 'MXI'
    BASE_ASSETS = list(IMOEX_WEIGHTS.keys()) + [MXI_TICKER, 'MIX', 'IMOEXF']
    REQUEST_TIMEOUT = 6
    FRESH_DAYS = 14
    MAX_WORKERS = 8

    def __init__(self):
        self.df_raw = None
        self.df_aggregated = None
        self.ohlcv_df = None
        self._load_data()

    @staticmethod
    def _is_trading_day(d):
        if d.weekday() >= 5:
            return False
        if d in MOEXBarometerLayer.RUSSIAN_HOLIDAYS:
            return False
        return True

    RUSSIAN_HOLIDAYS = {
        date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4),
        date(2024, 1, 5), date(2024, 1, 8), date(2024, 2, 23), date(2024, 3, 8),
        date(2024, 4, 29), date(2024, 4, 30), date(2024, 5, 1), date(2024, 5, 9),
        date(2024, 5, 10), date(2024, 6, 12), date(2024, 11, 4), date(2024, 12, 31),
        date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6),
        date(2025, 1, 7), date(2025, 1, 8), date(2025, 2, 24), date(2025, 3, 10),
        date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 9), date(2025, 6, 12),
        date(2025, 6, 13), date(2025, 11, 3), date(2025, 11, 4), date(2025, 12, 31),
        date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6),
        date(2026, 1, 7), date(2026, 1, 8), date(2026, 2, 23), date(2026, 3, 9),
        date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 11), date(2026, 6, 12),
        date(2026, 11, 4), date(2026, 12, 31),
    }

    def _fetch_json_api(self, contract_code, date_str):
        url = "https://web.moex.com/moex-web-iss-api/api/v1/open-position/F/" + contract_code
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.moex.com/ru/derivatives/open-positions"
        }
        try:
            r = requests.get(url, params={"date": date_str, "lang": "ru"},
                             headers=headers, timeout=self.REQUEST_TIMEOUT)
            if r.status_code != 200:
                return None
            data = r.json()
            if len(data) < 2 or "openpositions" not in data[1]:
                return None
            for item in data[1]["openpositions"]:
                if item.get("title") == "Кол-во контрактов, шт.":
                    fiz_oi = float(item.get("long_fiz", 0)) + float(item.get("short_fiz", 0))
                    yur_oi = float(item.get("long_jur", 0)) + float(item.get("short_jur", 0))
                    total_oi = float(item.get("total", 0))
                    if total_oi == 0:
                        return None
                    return {
                        "date": date_str,
                        "contract": contract_code,
                        "asset": CONTRACT_TO_ASSET.get(contract_code, contract_code),
                        "total_oi": total_oi,
                        "fiz_oi": fiz_oi,
                        "yur_oi": yur_oi,
                        "fiz_share": round(fiz_oi / total_oi * 100, 2),
                        "yur_share": round(yur_oi / total_oi * 100, 2),
                        "long_fiz": float(item.get("long_fiz", 0)),
                        "short_fiz": float(item.get("short_fiz", 0)),
                        "long_jur": float(item.get("long_jur", 0)),
                        "short_jur": float(item.get("short_jur", 0)),
                    }
        except Exception:
            pass
        return None

    def _load_day(self, date_str):
        records = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {executor.submit(self._fetch_json_api, code, date_str): code
                       for code in ALL_CONTRACT_CODES}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    records.append(result)
        return records

    def _fetch_futures_candles(self, contract_code, from_date, to_date):
        # Определяем MOEX-код для запроса свечей
        # Для вечных контрактов используем их как есть
        if contract_code in ['GAZPF', 'SBERF', 'IMOEXF']:
            moex_code = contract_code
        else:
            # Для квартальных контрактов генерируем код на текущую дату
            today = date.today()
            moex_code = get_contract_code(contract_code, pd.Timestamp(today))
            # Для SBRF и GAZR используется prefix SR и GZ, но get_contract_code вернёт
            # правильный код, если в CONTRACT_INFO заданы правильные префиксы.
            # Проверим: для SBRF в CONTRACT_INFO указан prefix 'SR', для GAZR 'GZ'
            # Это корректно.

        url = "https://iss.moex.com/iss/engines/futures/markets/forts/securities/" + moex_code + "/candles.json"
        params = {"from": from_date, "till": to_date, "interval": 24}
        try:
            r = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)
            if r.status_code != 200:
                return pd.DataFrame()
            data = r.json()
            if "candles" not in data:
                return pd.DataFrame()
            cols = data["candles"]["columns"]
            rows = data["candles"]["data"]
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows, columns=cols)
            df['begin'] = pd.to_datetime(df['begin'])
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
            df['high'] = pd.to_numeric(df['high'], errors='coerce')
            df['low'] = pd.to_numeric(df['low'], errors='coerce')
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            df = df.rename(columns={'begin': 'date'})
            df['contract'] = contract_code
            return df[['date', 'contract', 'open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            print("[WARN] Не удалось загрузить свечи для " + contract_code + " (MOEX: " + moex_code + "): " + str(e))
            return pd.DataFrame()

    def load_ohlcv(self):
        if self.df_raw is None or self.df_raw.empty:
            return pd.DataFrame()
        start_date = self.df_raw['date'].min()
        end_date = self.df_raw['date'].max()
        all_candles = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {executor.submit(self._fetch_futures_candles, code,
                                       start_date.strftime("%Y-%m-%d"),
                                       end_date.strftime("%Y-%m-%d")): code
                       for code in ALL_CONTRACT_CODES}
            for future in as_completed(futures):
                df = future.result()
                if not df.empty:
                    all_candles.append(df)
        if all_candles:
            return pd.concat(all_candles, ignore_index=True)
        else:
            return pd.DataFrame()

    def _aggregate_oi(self):
        if self.df_raw is None or self.df_raw.empty or self.ohlcv_df is None or self.ohlcv_df.empty:
            return pd.DataFrame()

        merged = pd.merge(self.df_raw, self.ohlcv_df, on=['date', 'contract'], how='left')
        merged['multiplier'] = merged['contract'].map(CONTRACT_MULTIPLIERS).fillna(1)

        merged['total_rub'] = merged['total_oi'] * merged['close'] * merged['multiplier']
        merged['fiz_rub'] = merged['fiz_oi'] * merged['close'] * merged['multiplier']
        merged['yur_rub'] = merged['yur_oi'] * merged['close'] * merged['multiplier']
        merged['long_fiz_rub'] = merged['long_fiz'] * merged['close'] * merged['multiplier']
        merged['short_fiz_rub'] = merged['short_fiz'] * merged['close'] * merged['multiplier']
        merged['long_jur_rub'] = merged['long_jur'] * merged['close'] * merged['multiplier']
        merged['short_jur_rub'] = merged['short_jur'] * merged['close'] * merged['multiplier']

        grouped = merged.groupby(['date', 'asset'], as_index=False).agg({
            'total_rub': 'sum',
            'fiz_rub': 'sum',
            'yur_rub': 'sum',
            'long_fiz_rub': 'sum',
            'short_fiz_rub': 'sum',
            'long_jur_rub': 'sum',
            'short_jur_rub': 'sum',
        })

        grouped = grouped.rename(columns={
            'total_rub': 'total_oi',
            'fiz_rub': 'fiz_oi',
            'yur_rub': 'yur_oi',
            'long_fiz_rub': 'long_fiz',
            'short_fiz_rub': 'short_fiz',
            'long_jur_rub': 'long_jur',
            'short_jur_rub': 'short_jur',
        })

        grouped['fiz_share'] = np.where(grouped['total_oi'] > 0,
                                        grouped['fiz_oi'] / grouped['total_oi'] * 100, 0)
        grouped['yur_share'] = np.where(grouped['total_oi'] > 0,
                                        grouped['yur_oi'] / grouped['total_oi'] * 100, 0)

        grouped['type'] = 'futures_aggregated'
        return grouped

    def _load_data(self):
        print("  [BARO] Загрузка OI по всем контрактам (14 дней)...")
        today = date.today()
        trading_days = []
        d = today
        while len(trading_days) < self.FRESH_DAYS:
            if self._is_trading_day(d):
                trading_days.insert(0, d)
            d -= timedelta(days=1)

        print("  [BARO] Период OI: " + str(trading_days[0]) + " → " + str(trading_days[-1]))
        all_records = []

        for i, trade_date in enumerate(trading_days):
            date_str = trade_date.strftime("%Y-%m-%d")
            records = self._load_day(date_str)
            all_records.extend(records)
            print("    [" + str(i+1).rjust(2) + "/" + str(len(trading_days)) + "] " + date_str + ": " + str(len(records)) + "/" + str(len(ALL_CONTRACT_CODES)) + " контрактов")

        if all_records:
            self.df_raw = pd.DataFrame(all_records)
            self.df_raw['date'] = pd.to_datetime(self.df_raw['date'])
            for col in ['total_oi', 'fiz_oi', 'yur_oi', 'long_fiz', 'short_fiz', 'long_jur', 'short_jur']:
                if col in self.df_raw.columns:
                    self.df_raw[col] = pd.to_numeric(self.df_raw[col], errors='coerce')
            print("  [BARO] Сырых OI записей: " + str(len(self.df_raw)))
        else:
            self.df_raw = pd.DataFrame()
            print("  [BARO] OI: Нет данных")

        if not self.df_raw.empty:
            print("  [BARO] Загрузка OHLCV для всех контрактов...")
            self.ohlcv_df = self.load_ohlcv()
            if not self.ohlcv_df.empty:
                print("  [BARO] OHLCV записей: " + str(len(self.ohlcv_df)))
            else:
                print("  [BARO] OHLCV: Нет данных")
        else:
            self.ohlcv_df = pd.DataFrame()

        if not self.df_raw.empty and not self.ohlcv_df.empty:
            print("  [BARO] Агрегация OI по активам (рублёвый эквивалент с учётом лотности)...")
            self.df_aggregated = self._aggregate_oi()
            print("  [BARO] Агрегированных записей: " + str(len(self.df_aggregated)))
        else:
            self.df_aggregated = pd.DataFrame()

    def get_current_metrics(self):
        if self.df_aggregated is None or self.df_aggregated.empty:
            return None

        df = self.df_aggregated.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(['asset', 'date'])

        latest_date = df['date'].max()
        latest = df[df['date'] == latest_date].set_index('asset')

        weighted_smart = 0.0
        weighted_retail = 0.0
        weighted_net_jur = 0.0
        weighted_net_fiz = 0.0
        weighted_jur_long_ratio = 0.0
        weighted_fiz_long_ratio = 0.0
        covered_weight = 0.0
        details = []

        for asset, weight in self.IMOEX_WEIGHTS.items():
            if asset not in latest.index:
                details.append({'asset': asset, 'weight': weight, 'smart_pct': None, 'retail_pct': None,
                                'net_jur': None, 'net_fiz': None,
                                'jur_long_ratio': None, 'fiz_long_ratio': None, 'status': '❌'})
                continue
            row = latest.loc[asset]
            smart_pct = row['yur_share']
            retail_pct = row['fiz_share']
            total_oi = row['total_oi'] if row['total_oi'] > 0 else 1
            long_jur = row.get('long_jur', 0)
            short_jur = row.get('short_jur', 0)
            long_fiz = row.get('long_fiz', 0)
            short_fiz = row.get('short_fiz', 0)
            net_jur = (long_jur - short_jur) / total_oi * 100
            net_fiz = (long_fiz - short_fiz) / total_oi * 100
            jur_long_ratio = long_jur / (long_jur + short_jur) * 100 if (long_jur + short_jur) > 0 else 50
            fiz_long_ratio = long_fiz / (long_fiz + short_fiz) * 100 if (long_fiz + short_fiz) > 0 else 50
            weighted_smart += smart_pct * weight
            weighted_retail += retail_pct * weight
            weighted_net_jur += net_jur * weight
            weighted_net_fiz += net_fiz * weight
            weighted_jur_long_ratio += jur_long_ratio * weight
            weighted_fiz_long_ratio += fiz_long_ratio * weight
            covered_weight += weight
            details.append({'asset': asset, 'weight': weight, 'smart_pct': smart_pct, 'retail_pct': retail_pct,
                            'net_jur': net_jur, 'net_fiz': net_fiz,
                            'jur_long_ratio': jur_long_ratio, 'fiz_long_ratio': fiz_long_ratio,
                            'smart_contrib': smart_pct * weight, 'total_oi': row['total_oi'], 'status': '✅'})

        index_smart = weighted_smart / covered_weight if covered_weight > 0 else 0
        index_retail = weighted_retail / covered_weight if covered_weight > 0 else 0
        index_net_jur = weighted_net_jur / covered_weight if covered_weight > 0 else 0
        index_net_fiz = weighted_net_fiz / covered_weight if covered_weight > 0 else 0
        index_jur_long_ratio = weighted_jur_long_ratio / covered_weight if covered_weight > 0 else 50
        index_fiz_long_ratio = weighted_fiz_long_ratio / covered_weight if covered_weight > 0 else 50

        mxi_data = None
        mxi_penalty = 0
        mxi_signal = "⚪ нет данных"
        if self.MXI_TICKER in latest.index:
            mxi = latest.loc[self.MXI_TICKER]
            mxi_data = {
                'smart_pct': mxi['yur_share'], 'retail_pct': mxi['fiz_share'], 'total_oi': mxi['total_oi'],
                'net_fiz': (mxi.get('long_fiz', 0) or 0) - (mxi.get('short_fiz', 0) or 0),
                'net_jur': (mxi.get('long_jur', 0) or 0) - (mxi.get('short_jur', 0) or 0),
            }
            if mxi_data['retail_pct'] > 95:
                mxi_signal, mxi_penalty = "🔴 ЭЙФОРИЯ толпы", -30
            elif mxi_data['retail_pct'] > 85:
                mxi_signal, mxi_penalty = "⚠️  Розница доминирует", -15
            elif mxi_data['retail_pct'] > 70:
                mxi_signal, mxi_penalty = "🟡 Розница преобладает", -5
            elif mxi_data['smart_pct'] > 30:
                mxi_signal, mxi_penalty = "🟢 Институционалы активны", +20
            else:
                mxi_signal = "⚪ Стандартно"

        unique_dates = sorted(df['date'].unique())
        norm_smart_delta = 0
        if len(unique_dates) >= 11:
            ten_days_ago = unique_dates[-11]
            past = df[df['date'] == ten_days_ago].set_index('asset')
            if not past.empty:
                w_delta = 0.0
                for asset, weight in self.IMOEX_WEIGHTS.items():
                    if asset in latest.index and asset in past.index:
                        w_delta += (latest.loc[asset, 'yur_share'] - past.loc[asset, 'yur_share']) * weight
                norm_smart_delta = w_delta / covered_weight if covered_weight > 0 else 0

        control_score = (index_smart - 50) * 2
        delta_score = norm_smart_delta * 10
        composite = np.clip(control_score * 0.50 + delta_score * 0.30 + mxi_penalty * 0.20, -100, 100)

        if composite > 40:
            bar_signal = "🟢 STRONG BUY"
        elif composite > 15:
            bar_signal = "🟢 BUY"
        elif composite > -15:
            bar_signal = "⚪ NEUTRAL"
        elif composite > -40:
            bar_signal = "🔴 SELL"
        else:
            bar_signal = "🔴 STRONG SELL"

        return {
            'date': latest_date,
            'index_smart_control': index_smart,
            'index_retail_control': index_retail,
            'index_net_jur': index_net_jur,
            'index_net_fiz': index_net_fiz,
            'index_jur_long_ratio': index_jur_long_ratio,
            'index_fiz_long_ratio': index_fiz_long_ratio,
            'covered_weight': covered_weight,
            'smart_delta_10d': norm_smart_delta,
            'mxi': mxi_data,
            'mxi_signal': mxi_signal,
            'composite': composite,
            'signal': bar_signal,
            'details': details,
            'data_fresh': True,
        }

    def get_freshness_status(self, today=None):
        if self.df_aggregated is None or self.df_aggregated.empty:
            return "❌ Нет данных барометра"
        latest = self.df_aggregated['date'].max()
        if today is None:
            today = pd.Timestamp.now()
        gap = (today - latest).days
        if gap <= 1:
            return "✅ Данные актуальны (" + str(latest.date()) + ")"
        return "⚠️ Данные устарели на " + str(gap) + " дн."


# =============================================================================
# ЗАГРУЗКА ДАННЫХ IMOEX (С ЗАДЕРЖКОЙ И RETRY)
# =============================================================================
def load_imoex_data(from_date="2003-01-01", to_date=None):
    if to_date is None:
        to_date = datetime.today().strftime("%Y-%m-%d")
    all_data = []
    base_url = "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json"
    start = 0
    print("[INFO] Загрузка данных: " + from_date + " - " + to_date)

    max_retries = 3
    retry_count = 0
    empty_count = 0

    while True:
        url = base_url + "?from=" + from_date + "&till=" + to_date + "&start=" + str(start)
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                print("[WARN] HTTP " + str(r.status_code) + ", retry " + str(retry_count+1) + "/" + str(max_retries))
                retry_count += 1
                if retry_count >= max_retries:
                    break
                time.sleep(1)
                continue

            try:
                data = r.json()
            except Exception as e:
                print("[WARN] JSON decode error: " + str(e) + ", retry " + str(retry_count+1) + "/" + str(max_retries))
                retry_count += 1
                if retry_count >= max_retries:
                    break
                time.sleep(1)
                continue

            rows = data['history']['data']

            if not rows:
                empty_count += 1
                if empty_count >= 2:
                    break
                time.sleep(0.5)
                continue

            retry_count = 0
            empty_count = 0
            all_data.extend(rows)
            start += 100
            time.sleep(0.3)

        except Exception as e:
            print("[ERR] Ошибка загрузки: " + str(e))
            retry_count += 1
            if retry_count >= max_retries:
                break
            time.sleep(1)

    columns = ["BOARDID", "SECID", "TRADEDATE", "SHORTNAME", "NAME", "CLOSE",
               "OPEN", "HIGH", "LOW", "VALUE", "DURATION", "YIELD", "DECIMALS",
               "CAPITALIZATION", "CURRENCYID", "DIVISOR", "TRADINGSESSION",
               "VOLUME", "TRADE_SESSION_DATE", "RECALC_DATE"]
    df = pd.DataFrame(all_data, columns=columns)
    df['TRADEDATE'] = pd.to_datetime(df['TRADEDATE'])
    for col in ['CLOSE', 'OPEN', 'HIGH', 'LOW']:
        df[col.lower()] = pd.to_numeric(df[col], errors='coerce')
    df['volume'] = pd.to_numeric(df['VALUE'], errors='coerce')
    df = df.drop_duplicates(subset=['TRADEDATE']).sort_values('TRADEDATE')
    df = df.set_index('TRADEDATE')
    last_date = df.index.max()
    today = datetime.today()
    days_gap = (today - last_date).days
    print("[OK] Данные: " + str(df.index.min().date()) + " - " + str(last_date.date()) + ", " + str(len(df)) + " записей")
    return df, last_date, days_gap


# =============================================================================
# СТАВКИ ЦБ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================
CASH_RATES_BY_YEAR = {
    2003: 18.00, 2004: 14.00, 2005: 13.00, 2006: 11.25, 2007: 10.25,
    2008: 10.75, 2009: 10.00, 2010: 8.00, 2011: 8.08, 2012: 8.25,
    2013: 5.50, 2014: 9.08, 2015: 11.00, 2016: 10.50, 2017: 8.25,
    2018: 7.42, 2019: 7.00, 2020: 5.08, 2021: 6.42, 2022: 11.08,
    2023: 10.58, 2024: 17.50, 2025: 17.33, 2026: 15.08
}

def get_daily_cash_rate(df_index):
    rates = pd.Series(index=df_index, dtype=float)
    for year, rate in CASH_RATES_BY_YEAR.items():
        rates[rates.index.year == year] = rate / 100.0
    avg_rate = sum(CASH_RATES_BY_YEAR.values()) / len(CASH_RATES_BY_YEAR)
    return rates.fillna(avg_rate / 100.0)

def get_wyckoff_phase_name(phase):
    names = {
        0: 'Нейтральная',
        1: 'Накопление (Accumulation)',
        2: 'Распределение (Distribution)',
        3: 'Ослабление тренда',
        4: 'Аккумуляция (Mark-down)'
    }
    return names.get(phase, 'Неизвестно')

def get_wyckoff_phase_arg(phase):
    if phase == 4:
        return ("Крупные игроки накапливают активы по низким ценам. "
                "Рынок падает, но формируется база для будущего роста.")
    elif phase == 3:
        return ("Тренд ослабел, цена ниже EMA50, но ещё выше MA126. "
                "Профессионалы начинают фиксировать прибыль.")
    elif phase == 2:
        return ("Активы распределяются от профессионалов к толпе. "
                "Цена растёт, но риск увеличивается.")
    elif phase == 1:
        return ("Рынок начинает восстанавливаться. "
                "Цена выше EMA15/EMA50, но ещё ниже MA126.")
    else:
        return "Рынок в неопределённом состоянии."


# =============================================================================
# СТРАТЕГИЯ (без изменений)
# =============================================================================
def run_strategy(df, notifier=None, ema_fast=15, ema_slow=50, ma_long=126,
                 barometer_layer=None,
                 commission=0.0005, slippage=0.001,
                 initial_capital=1_000_000,
                 use_regime_filter=True,
                 partial_exit_atr_mult=4.0,
                 base_risk=0.05, max_risk=0.10,
                 emergency_stop_atr=1.5,
                 entry_mode='limit_ema',
                 adx_threshold_weak=20, adx_threshold_strong=40,
                 dividend_yield_annual=0.03):
    # Полный код стратегии — без изменений, он уже был в предыдущей версии.
    # В целях экономии места здесь приведена только обёртка, но в реальном файле он будет полным.
    # Ниже приведён полный код стратегии, он идентичен предыдущей версии.
    cash_rate = get_daily_cash_rate(df.index)
    df = df.copy()
    df['EMA_fast'] = df['close'].ewm(span=ema_fast, adjust=False).mean()
    df['EMA_slow'] = df['close'].ewm(span=ema_slow, adjust=False).mean()
    df['MA_long'] = df['close'].rolling(window=ma_long, min_periods=ma_long).mean()

    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.ewm(span=14, adjust=False).mean()

    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[plus_dm <= minus_dm] = 0
    minus_dm[minus_dm <= plus_dm] = 0
    atr_ema = tr.ewm(span=14, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=14, adjust=False).mean() / atr_ema
    minus_di = 100 * minus_dm.ewm(span=14, adjust=False).mean() / atr_ema
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    df['ADX'] = dx.ewm(span=14, adjust=False).mean()

    df['TrendRegime'] = 0
    df.loc[df['ADX'] > adx_threshold_weak, 'TrendRegime'] = 1
    df.loc[df['ADX'] > adx_threshold_strong, 'TrendRegime'] = 2

    df['WyckoffPhase'] = 0
    df.loc[(df['close'] > df['EMA_fast']) & (df['close'] > df['EMA_slow']) & (df['close'] < df['MA_long']), 'WyckoffPhase'] = 1
    df.loc[(df['close'] > df['EMA_fast']) & (df['close'] > df['EMA_slow']) & (df['close'] > df['MA_long']), 'WyckoffPhase'] = 2
    df.loc[(df['close'] < df['EMA_slow']) & (df['close'] > df['MA_long']), 'WyckoffPhase'] = 3
    df.loc[(df['close'] < df['EMA_slow']) & (df['close'] < df['MA_long']), 'WyckoffPhase'] = 4

    phase_series = df['WyckoffPhase']
    current_phase = phase_series.iloc[-1]
    current_duration = 0
    for i in range(len(phase_series) - 1, -1, -1):
        if phase_series.iloc[i] == current_phase:
            current_duration += 1
        else:
            break

    avg_durations = {}
    for ph in range(5):
        durations = []
        count = 0
        for i in range(len(phase_series)):
            if phase_series.iloc[i] == ph:
                count += 1
            else:
                if count > 0:
                    durations.append(count)
                count = 0
        if count > 0:
            durations.append(count)
        avg_durations[ph] = np.mean(durations) if durations else 0

    entry_cond = (df['close'] > df['EMA_fast']) & (df['close'] > df['EMA_slow'])
    exit_cond = df['close'] < df['EMA_slow']

    signal = np.zeros(len(df), dtype=int)
    in_position = False
    for i in range(len(df)):
        if not in_position:
            if entry_cond.iloc[i]:
                if use_regime_filter and df['TrendRegime'].iloc[i] == 0:
                    signal[i] = 0
                else:
                    signal[i] = 1
                    in_position = True
        else:
            if exit_cond.iloc[i]:
                signal[i] = 0
                in_position = False
            else:
                signal[i] = 1
    df['Signal'] = signal

    if entry_mode == 'open':
        df['ExecPrice'] = df['open'].shift(-1)
    elif entry_mode == 'close':
        df['ExecPrice'] = df['close']
    elif entry_mode == 'limit_ema':
        next_open = df['open'].shift(-1)
        ema_fast_val = df['EMA_fast']
        df['ExecPrice'] = np.where(next_open <= ema_fast_val, next_open, ema_fast_val)
    df.loc[df.index[-1], 'ExecPrice'] = df['close'].iloc[-1]

    df['ExitPrice'] = df['open'].shift(-1)
    df.loc[df.index[-1], 'ExitPrice'] = df['close'].iloc[-1]

    capital = initial_capital
    shares = 0
    cash_in_position = 0
    equity = []
    trade_log = []
    prev_signal = 0
    entry_price = 0
    entry_atr = 0
    partial_exited = False
    emergency_count = 0

    prices = df['close'].values
    signals = df['Signal'].values
    exec_prices = df['ExecPrice'].values
    exit_prices = df['ExitPrice'].values
    atr_vals = df['ATR'].values
    regimes = df['TrendRegime'].values
    wyckoff_phases = df['WyckoffPhase'].values
    dates = df.index
    lows = df['low'].values

    for i in range(1, len(df)):
        date = dates[i]
        price = exec_prices[i]
        exit_price_today = exit_prices[i]
        signal = signals[i]
        atr = atr_vals[i]
        regime = regimes[i]
        phase = wyckoff_phases[i]

        if emergency_stop_atr is not None and shares > 0 and entry_price > 0 and entry_atr > 0:
            stop_level = entry_price - entry_atr * emergency_stop_atr
            if lows[i] < stop_level:
                exit_price = stop_level * (1 - slippage)
                proceeds = shares * exit_price * (1 - commission)
                capital += proceeds + cash_in_position
                trade_pnl = ((exit_price / entry_price - 1) * 100) if entry_price > 0 else None
                trade_log.append((date, 'EMERGENCY_SELL', exit_price, shares, capital, trade_pnl, phase))
                shares = 0
                cash_in_position = 0
                entry_price = 0
                entry_atr = 0
                partial_exited = False
                emergency_count += 1
                signal = 0
                prev_signal = 0
                daily_equity = capital
                daily_rate = cash_rate.iloc[i] / 252
                daily_rate += dividend_yield_annual / 252
                capital *= (1 + daily_rate)
                equity.append(daily_equity)
                continue

        if signal == 1 and prev_signal == 0:
            entry_price = price * (1 + slippage)
            entry_atr = atr
            if regime == 2:
                risk = max_risk
            elif regime == 1:
                risk = base_risk + (max_risk - base_risk) * 0.5
            else:
                risk = base_risk
            risk_amount = capital * risk
            stop_distance = atr * 3
            position_size = risk_amount / stop_distance if stop_distance > 0 else capital * 0.5 / entry_price
            max_shares = capital * (1 - commission) / entry_price
            shares = min(position_size, max_shares)
            capital -= shares * entry_price
            capital = max(capital, 0)
            cash_in_position = 0
            partial_exited = False
            trade_log.append((date, 'BUY', entry_price, shares, regime, risk, phase))

        elif signal == 1 and prev_signal == 1 and not partial_exited and shares > 0:
            current_pnl_pct = (prices[i] / entry_price - 1) * 100
            if current_pnl_pct > 0 and (prices[i] - entry_price) > atr * partial_exit_atr_mult:
                partial_shares = shares * 0.5
                exit_price_partial = exit_price_today * (1 - slippage)
                proceeds = partial_shares * exit_price_partial * (1 - commission)
                cash_in_position += proceeds
                shares -= partial_shares
                partial_exited = True
                trade_log.append((date, 'PARTIAL', exit_price_partial, partial_shares, cash_in_position, current_pnl_pct, phase))

        elif signal == 0 and prev_signal == 1:
            exit_price = exit_price_today * (1 - slippage)
            proceeds = shares * exit_price * (1 - commission)
            capital += proceeds + cash_in_position
            trade_pnl = ((exit_price / entry_price - 1) * 100) if entry_price > 0 else None
            trade_log.append((date, 'SELL', exit_price, shares, capital, trade_pnl, phase))
            shares = 0
            cash_in_position = 0
            entry_price = 0
            entry_atr = 0
            partial_exited = False

        if shares > 0:
            daily_equity = capital + cash_in_position + shares * prices[i]
        else:
            daily_equity = capital
            daily_rate = cash_rate.iloc[i] / 252
            daily_rate += dividend_yield_annual / 252
            capital *= (1 + daily_rate)

        equity.append(daily_equity)
        prev_signal = signal

    equity_df = pd.DataFrame({'Equity': equity}, index=dates[1:])

    final = equity_df['Equity'].iloc[-1]
    years = (equity_df.index[-1] - equity_df.index[0]).days / 365.25
    cagr = (pow(final / initial_capital, 1 / years) - 1) * 100
    daily_rets = equity_df['Equity'].pct_change().dropna()
    sharpe = np.sqrt(252) * daily_rets.mean() / daily_rets.std() if daily_rets.std() != 0 else 0
    cummax = equity_df['Equity'].cummax()
    drawdown = (equity_df['Equity'] / cummax - 1) * 100
    max_dd = drawdown.min()
    time_in_market = df['Signal'].iloc[1:].sum() / len(df['Signal'].iloc[1:]) * 100

    trades = [t for t in trade_log if t[1] in ('SELL', 'EMERGENCY_SELL')]
    pnl_list = [t[5] for t in trades if len(t) > 5 and t[5] is not None]
    win_rate = sum(1 for p in pnl_list if p > 0) / len(pnl_list) * 100 if pnl_list else 0
    avg_win = np.mean([p for p in pnl_list if p > 0]) if any(p > 0 for p in pnl_list) else 0
    avg_loss = np.mean([p for p in pnl_list if p < 0]) if any(p < 0 for p in pnl_list) else 0
    profit_factor = abs(sum(p for p in pnl_list if p > 0) / sum(p for p in pnl_list if p < 0)) if sum(p for p in pnl_list if p < 0) != 0 else float('inf')
    expectancy = (win_rate/100 * avg_win + (1-win_rate/100) * avg_loss) if pnl_list else 0

    neg_rets = daily_rets[daily_rets < 0]
    sortino = np.sqrt(252) * daily_rets.mean() / neg_rets.std() if len(neg_rets) > 0 and neg_rets.std() != 0 else 0
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0
    ulcer = np.sqrt(np.mean(drawdown[drawdown < 0] ** 2)) if any(drawdown < 0) else 0

    phase_stats = df['WyckoffPhase'].value_counts().sort_index().to_dict()

    last_idx = len(df) - 1
    last_signal = df['Signal'].iloc[last_idx]
    last_date = df.index[last_idx]
    last_price = df['close'].iloc[last_idx]
    last_ema_fast = df['EMA_fast'].iloc[last_idx]
    last_ema_slow = df['EMA_slow'].iloc[last_idx]
    last_adx = df['ADX'].iloc[last_idx]
    last_regime = df['TrendRegime'].iloc[last_idx]
    last_phase = df['WyckoffPhase'].iloc[last_idx]

    days_out = 0
    signal_series = df['Signal']
    for i in range(len(signal_series) - 1, -1, -1):
        if signal_series.iloc[i] == 0:
            days_out += 1
        else:
            break

    last_trade_date = df.index[-1].strftime('%Y-%m-%d')
    today = datetime.today()
    days_gap = (today - df.index[-1]).days

    barometer_data = None
    barometer_df = None
    raw_oi_df = None
    raw_ohlcv_df = None
    if barometer_layer is not None:
        try:
            barometer_data = barometer_layer.get_current_metrics()
            barometer_df = barometer_layer.df_aggregated if hasattr(barometer_layer, 'df_aggregated') else None
            raw_oi_df = barometer_layer.df_raw if hasattr(barometer_layer, 'df_raw') else None
            raw_ohlcv_df = barometer_layer.ohlcv_df if hasattr(barometer_layer, 'ohlcv_df') else None
            print("\n[INFO] Барометр: " + barometer_layer.get_freshness_status())
        except Exception as e:
            print("[WARN] Ошибка барометра: " + str(e))

    if notifier and notifier.enabled:
        notifier.send_status_report(
            date=today,
            cagr=cagr,
            max_dd=max_dd,
            sharpe=sharpe,
            current_signal=last_signal,
            last_price=last_price,
            ema_fast=last_ema_fast,
            ema_slow=last_ema_slow,
            adx=last_adx,
            regime=last_regime,
            days_out=days_out,
            last_trade_date=last_trade_date,
            days_gap=days_gap,
            entry_mode=entry_mode,
            trades_count=len(trades),
            win_rate=win_rate,
            time_in_market=time_in_market,
            wyckoff_phase=last_phase,
            avg_phase_durations=avg_durations,
            current_phase_duration=current_duration,
            barometer_data=barometer_data,
            barometer_df=barometer_df,
            target_assets=barometer_layer.BASE_ASSETS if barometer_layer else None,
            ohlcv_futures_df=None,
            raw_oi_df=raw_oi_df,
            raw_ohlcv_df=raw_ohlcv_df
        )

    return {
        'equity': equity_df, 'trade_log': trade_log, 'cagr': cagr,
        'max_dd': max_dd, 'sharpe': sharpe, 'sortino': sortino,
        'calmar': calmar, 'trades': len(trades), 'time_in_market': time_in_market,
        'final': final, 'drawdown': drawdown, 'win_rate': win_rate,
        'profit_factor': profit_factor, 'expectancy': expectancy,
        'avg_win': avg_win, 'avg_loss': avg_loss, 'ulcer': ulcer,
        'last_signal': last_signal, 'last_date': last_date,
        'last_price': last_price, 'last_ema_fast': last_ema_fast,
        'last_ema_slow': last_ema_slow, 'last_adx': last_adx,
        'last_regime': last_regime, 'days_out': days_out,
        'emergency_count': emergency_count,
        'last_trade_date': last_trade_date, 'days_gap': days_gap,
        'entry_mode': entry_mode,
        'last_phase': last_phase,
        'barometer': barometer_data,
        'phase_stats': phase_stats,
        'avg_phase_durations': avg_durations,
        'current_phase_duration': current_duration,
        'df': df
    }


# =============================================================================
# ГЛАВНЫЙ БЛОК
# =============================================================================
if __name__ == "__main__":
    print("=" * 75)
    print("  IMOEX V2.3.2 — БАРОМЕТР С АГРЕГАЦИЕЙ (ИСПРАВЛЕННАЯ СПЕЦИФИКАЦИЯ)")
    print("  Запуск: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 75)
    print()

    notifier = SignalNotifier()
    barometer = MOEXBarometerLayer()

    df, last_date_data, days_gap = load_imoex_data()

    if days_gap > 1:
        print("[WARN] Данные устарели на " + str(days_gap) + " дней!")

    result = run_strategy(df, notifier=notifier,
                          barometer_layer=barometer,
                          ema_fast=15, ema_slow=50, ma_long=126,
                          base_risk=0.05, max_risk=0.10,
                          emergency_stop_atr=1.5,
                          partial_exit_atr_mult=4.0,
                          entry_mode='limit_ema',
                          adx_threshold_weak=20, adx_threshold_strong=40,
                          dividend_yield_annual=0.03)

    phase_names = {
        0: 'Нейтральная',
        1: 'Накопление (Accumulation)',
        2: 'Распределение (Distribution)',
        3: 'Ослабление тренда',
        4: 'Аккумуляция (Mark-down)'
    }
    current_phase_name = phase_names.get(result['last_phase'], 'Неизвестно')
    current_phase_arg = get_wyckoff_phase_arg(result['last_phase'])

    print()
    print("=" * 75)
    print("  РЕЗУЛЬТАТЫ БЭКТЕСТА V2.3.2")
    print("=" * 75)
    print("  Период:            " + str(result['equity'].index[0].date()) + " - " + str(result['equity'].index[-1].date()))
    print("  Начальный капитал: 1,000,000 ₽")
    print("  Прибыль:           " + str(round((result['final']/1e6 - 1)*100, 1)) + "%")
    print("  CAGR:              " + str(round(result['cagr'], 2)) + "%")
    print("  Max Drawdown:      " + str(round(result['max_dd'], 2)) + "%")
    print("  Sharpe:            " + str(round(result['sharpe'], 2)))
    print("  Sortino:           " + str(round(result['sortino'], 2)))
    print("  Calmar:            " + str(round(result['calmar'], 2)))
    print("  Сделок:            " + str(result['trades']))
    print("  Аварийных выходов: " + str(result['emergency_count']))
    print("  Win Rate:          " + str(round(result['win_rate'], 1)) + "%")
    print("  Profit Factor:     " + str(round(result['profit_factor'], 2)))
    print("  Expectancy:        " + str(round(result['expectancy'], 2)) + "%")
    print("  Avg Win:           " + str(round(result['avg_win'], 2)) + "%")
    print("  Avg Loss:          " + str(round(result['avg_loss'], 2)) + "%")
    print("  Время в рынке:     " + str(round(result['time_in_market'], 1)) + "%")
    print("  Тип входа:         " + result['entry_mode'])
    print("  Дивиденды:         +3% годовых в кэше")
    print("=" * 75)

    print()
    print("=" * 75)
    print("  🔄 ФАЗА ВАЙКОФФА (ИНФОРМАЦИОННО)")
    print("=" * 75)
    print("  Фаза определяется по положению цены относительно EMA15, EMA50 и MA126.")
    print("  НЕ влияет на торговые решения — только для аналитики.")
    print()
    print("  Текущая фаза: " + current_phase_name)
    print("  Аргументация: " + current_phase_arg)
    print("  Средняя длительность непрерывной фазы «" + current_phase_name + "»: " + str(round(result['avg_phase_durations'][result['last_phase']], 0)) + " дн.")
    print("  Текущая непрерывная фаза длится уже: " + str(result['current_phase_duration']) + " дн.")
    print()
    print("  Примечание: средняя длительность — для непрерывных отрезков одной фазы.")
    print("  Полный цикл обычно состоит из чередования фаз и длится дольше.")
    print("=" * 75)

    print()
    print("=" * 75)
    print("  ТЕКУЩИЙ СИГНАЛ")
    print("=" * 75)
    status = "🟢 ОТКРЫТА" if result['last_signal'] == 1 else "🔴 ЗАКРЫТА"
    print("  Позиция: " + status)
    print("  Дата сигнала: " + result['last_date'].strftime('%Y-%m-%d'))
    print("  Дата данных:  " + result['last_trade_date'] + " (разрыв: " + str(result['days_gap']) + " дн.)")
    print("  Цена (Close): " + str(round(result['last_price'], 2)) + " ₽")
    print("  EMA15:    " + str(round(result['last_ema_fast'], 2)) + " ₽")
    print("  EMA50:    " + str(round(result['last_ema_slow'], 2)) + " ₽")
    print("  ADX:      " + str(round(result['last_adx'], 1)))
    print("  Режим:    " + str(result['last_regime']) + " (" + ('слабый' if result['last_regime']==0 else 'средний' if result['last_regime']==1 else 'сильный') + ")")
    print("  Фаза:     " + current_phase_name)
    print("  Тип входа: " + result['entry_mode'])
    if result['last_signal'] == 0:
        print("  Дней вне рынка: " + str(result['days_out']))
        if result['last_price'] > result['last_ema_fast'] and result['last_price'] > result['last_ema_slow'] and result['last_regime'] > 0:
            print("  ⚡ СИГНАЛ: WAIT (приближение к входу)")
        else:
            print("  ⏸️  СИГНАЛ: HOLD CASH (нет сигнала)")
    print("=" * 75)

    if result.get('barometer'):
        b = result['barometer']
        print()
        print("=" * 75)
        print("  📊 SMART MONEY BAROMETER (информационный слой)")
        print("=" * 75)
        print("  Дата данных:      " + str(b['date'].date()))
        print("  Сигнал:           " + b['signal'])
        print("  Composite Score:  " + str(round(b['composite'], 1)) + " / 100")
        net_jur = b.get('index_net_jur', 0)
        net_fiz = b.get('index_net_fiz', 0)
        jur_lr = b.get('index_jur_long_ratio', 50)
        fiz_lr = b.get('index_fiz_long_ratio', 50)
        print("  Δ доли Юрлиц (10д): " + str(round(b['smart_delta_10d'], 2)) + "%")
        print("  Доля Юрлиц (всего): " + str(round(b['index_smart_control'], 1)) + "%")
        print("    └─ Нетто-позиция: " + str(round(net_jur, 1)) + "% (" + ('лонг' if net_jur >= 0 else 'шорт') + ")")
        print("    └─ Доля лонгов:   " + str(round(jur_lr, 1)) + "%")
        print("  Физлицы:")
        print("    └─ Нетто-позиция: " + str(round(net_fiz, 1)) + "% (" + ('лонг' if net_fiz >= 0 else 'шорт') + ")")
        print("    └─ Доля лонгов:   " + str(round(fiz_lr, 1)) + "%")
        print("  MXI:              " + b['mxi_signal'])
        if b.get('mxi'):
            print("  MXI Розница:      " + str(round(b['mxi']['retail_pct'], 1)) + "% (чистая поз. " + str(int(b['mxi']['net_fiz'])) + ")")
        print("  Покрытие индекса: " + str(round(b['covered_weight']*100, 0)) + "%")
        print("  ─" + "─" * 73)
        print("  ⚠️  Барометр НЕ влияет на торговые решения — только для контекста.")
        print("=" * 75)
    else:
        print("\n  [INFO] Барометр недоступен")

    print("\n[OK] Завершено: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("[INFO] Email-отчёт отправлен (если настроен)")