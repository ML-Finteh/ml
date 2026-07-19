"""
================================================================================
IMOEX ДИНАМИЧЕСКАЯ СТРАТЕГИЯ V2.3.2 — ИНФОРМАЦИОННЫЕ ФАЗЫ ВАЙКОФФА
(ИСПРАВЛЕННАЯ ВЕРСИЯ — смысловые фазы по Вайкоффу)
================================================================================
Изменения V2.3.2 (исправлено):
- Фазы переименованы в соответствии со смыслом по Вайкоффу:
  * Фаза 1 → Накопление (Accumulation) — рынок восстанавливается
  * Фаза 2 → Распределение (Distribution) — активы переходят к толпе
  * Фаза 3 → Ослабление тренда — тренд ослаб, профи фиксируют прибыль
  * Фаза 4 → Аккумуляция (Mark-down) — крупные игроки накапливают по низким
- Добавлена аргументация смысла каждой фазы
- Добавлена статистика средней длительности непрерывных серий фаз
- Добавлено пояснение: средняя длительность — для отрезков одной фазы,
  полный цикл состоит из чередования фаз и длится дольше
- Исправлен баг с выводом EMA15 (был result['ema_fast'] вместо last_ema_fast)
- Фазы НЕ влияют на торговую логику — только на аналитику
- Базовая логика V2.3.1 сохранена полностью

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
warnings.filterwarnings('ignore')

# =============================================================================
# EMAIL NOTIFIER (отправка только при ручном запуске)
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

    def _send(self, subject, body_html, body_text):
        if not self.enabled:
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email_from
            msg["To"] = self.email_to
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, self.email_to, msg.as_string())
            print(f"[OK] Email sent: {subject}")
            return True
        except Exception as e:
            print(f"[ERR] Email failed: {e}")
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

    def send_buy(self, date, price, regime, risk, last_trade_date, entry_mode, wyckoff_phase):
        phase_names = self._get_phase_names()
        phase_name = phase_names.get(wyckoff_phase, 'Неизвестно')
        subject = f"🟢 BUY IMOEX | {date.strftime('%Y-%m-%d')} | Фаза: {phase_name}"
        mode_text = "лимитная заявка на EMA" if entry_mode == 'limit_ema' else "рыночная заявка"
        body_text = f"СИГНАЛ ПОКУПКИ - IMOEX\nДата сигнала: {date.strftime('%Y-%m-%d')}\nДата данных: {last_trade_date}\nЦена: {price:,.2f} ₽\nРежим: {regime}\nРиск: {risk:.0%}\nТип входа: {mode_text}\nФаза Вайкоффа: {phase_name}"
        body_html = f"""<html><body style="font-family:Arial">
        <h2 style="color:#2e7d32">🟢 BUY IMOEX</h2>
        <table style="border-collapse:collapse;width:400px">
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Дата сигнала</b></td><td style="padding:8px;border:1px solid #ddd">{date.strftime('%Y-%m-%d')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#e8f5e9"><b>Дата данных</b></td><td style="padding:8px;border:1px solid #ddd;background:#e8f5e9;font-weight:bold">{last_trade_date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Цена</b></td><td style="padding:8px;border:1px solid #ddd">{price:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Режим тренда</b></td><td style="padding:8px;border:1px solid #ddd">{regime} ({'слабый' if regime==0 else 'средний' if regime==1 else 'сильный'})</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Риск на сделку</b></td><td style="padding:8px;border:1px solid #ddd">{risk:.0%}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#e8f5e9"><b>Тип входа</b></td><td style="padding:8px;border:1px solid #ddd;background:#e8f5e9;font-weight:bold">{mode_text}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Фаза Вайкоффа</b></td><td style="padding:8px;border:1px solid #ddd;background:#fff3e0;font-weight:bold">{phase_name}</td></tr>
        </table></body></html>"""
        return self._send(subject, body_html, body_text)

    def send_sell(self, date, price, capital, pnl, last_trade_date, wyckoff_phase):
        phase_names = self._get_phase_names()
        phase_name = phase_names.get(wyckoff_phase, 'Неизвестно')
        subject = f"🔴 SELL IMOEX | {date.strftime('%Y-%m-%d')} | Фаза: {phase_name}"
        pnl_text = f"\nP&L: {pnl:+.2f}%" if pnl else ""
        body_text = f"СИГНАЛ ПРОДАЖИ - IMOEX\nДата сигнала: {date.strftime('%Y-%m-%d')}\nДата данных: {last_trade_date}\nЦена: {price:,.2f} ₽\nКапитал: {capital:,.0f} ₽{pnl_text}\nФаза Вайкоффа: {phase_name}"
        pnl_color = "#2e7d32" if pnl and pnl > 0 else "#c62828"
        pnl_html = f'<tr><td style="padding:8px;border:1px solid #ddd"><b>P&L</b></td><td style="padding:8px;border:1px solid #ddd;color:{pnl_color}">{pnl:+.2f}%</td></tr>' if pnl else ""
        body_html = f"""<html><body style="font-family:Arial">
        <h2 style="color:#c62828">🔴 SELL IMOEX</h2>
        <table style="border-collapse:collapse;width:400px">
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Дата сигнала</b></td><td style="padding:8px;border:1px solid #ddd">{date.strftime('%Y-%m-%d')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Дата данных</b></td><td style="padding:8px;border:1px solid #ddd;background:#ffebee;font-weight:bold">{last_trade_date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Цена</b></td><td style="padding:8px;border:1px solid #ddd">{price:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Капитал</b></td><td style="padding:8px;border:1px solid #ddd">{capital:,.0f} ₽</td></tr>
        {pnl_html}
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Фаза Вайкоффа</b></td><td style="padding:8px;border:1px solid #ddd;background:#fff3e0;font-weight:bold">{phase_name}</td></tr>
        </table></body></html>"""
        return self._send(subject, body_html, body_text)

    def send_emergency_sell(self, date, price, capital, pnl, last_trade_date, wyckoff_phase):
        phase_names = self._get_phase_names()
        phase_name = phase_names.get(wyckoff_phase, 'Неизвестно')
        subject = f"🚨 EMERGENCY SELL IMOEX | {date.strftime('%Y-%m-%d')} | Фаза: {phase_name}"
        pnl_text = f"\nP&L: {pnl:+.2f}%" if pnl else ""
        body_text = f"АВАРИЙНЫЙ ВЫХОД - IMOEX\nДата сигнала: {date.strftime('%Y-%m-%d')}\nДата данных: {last_trade_date}\nЦена: {price:,.2f} ₽\nКапитал: {capital:,.0f} ₽{pnl_text}\nПричина: стоп -1.5 ATR\nФаза Вайкоффа: {phase_name}"
        pnl_color = "#2e7d32" if pnl and pnl > 0 else "#c62828"
        pnl_html = f'<tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>P&L</b></td><td style="padding:8px;border:1px solid #ddd;color:{pnl_color}">{pnl:+.2f}%</td></tr>' if pnl else ""
        body_html = f"""<html><body style="font-family:Arial">
        <h2 style="color:#c62828">🚨 EMERGENCY SELL IMOEX</h2>
        <p style="color:#c62828">Сработал аварийный стоп -1.5 ATR. Позиция закрыта для освобождения капитала.</p>
        <table style="border-collapse:collapse;width:400px">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Дата сигнала</b></td><td style="padding:8px;border:1px solid #ddd">{date.strftime('%Y-%m-%d')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Дата данных</b></td><td style="padding:8px;border:1px solid #ddd;background:#ffebee;font-weight:bold">{last_trade_date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Цена</b></td><td style="padding:8px;border:1px solid #ddd">{price:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Капитал</b></td><td style="padding:8px;border:1px solid #ddd">{capital:,.0f} ₽</td></tr>
        {pnl_html}
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Причина</b></td><td style="padding:8px;border:1px solid #ddd">Цена пробила стоп -1.5 ATR от входа</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Фаза Вайкоффа</b></td><td style="padding:8px;border:1px solid #ddd;background:#fff3e0;font-weight:bold">{phase_name}</td></tr>
        </table></body></html>"""
        return self._send(subject, body_html, body_text)

    def send_hold_cash(self, date, price, ema_fast, ema_slow, adx, regime, days_out, last_trade_date, days_gap=0, entry_mode='limit_ema', wyckoff_phase=0):
        phase_names = self._get_phase_names()
        phase_name = phase_names.get(wyckoff_phase, 'Неизвестно')
        subject = f"🔴 HOLD CASH | {date.strftime('%Y-%m-%d')} | Вне рынка {days_out} дн. | Фаза: {phase_name}"
        warning_html = f'<tr><td colspan="2" style="padding:8px;border:1px solid #ddd;background:#fff3e0;color:#e65100;font-weight:bold">⚠️ Данные устарели на {days_gap} дней. Показаны цены за {last_trade_date}.</td></tr>' if days_gap > 0 else ''
        warning_text = f'\n⚠️ ВНИМАНИЕ: Данные устарели на {days_gap} дней. Показаны цены за {last_trade_date}.' if days_gap > 0 else ''
        mode_text = "лимитная заявка на EMA" if entry_mode == 'limit_ema' else "рыночная заявка"
        body_text = f"СТАТУС: ВНЕ РЫНКА - IMOEX\nДата сигнала: {date.strftime('%Y-%m-%d')}\nДата данных: {last_trade_date}{warning_text}\nЦена: {price:,.2f} ₽\nEMA20: {ema_fast:,.2f} ₽\nEMA50: {ema_slow:,.2f} ₽\nADX: {adx:.1f}\nДней вне рынка: {days_out}\nТип входа: {mode_text}\nФаза Вайкоффа: {phase_name}"
        body_html = f"""<html><body style="font-family:Arial">
        <h2 style="color:#666">🔴 HOLD CASH - IMOEX</h2>
        <p style="color:#666">Позиция закрыта. Сигнала на вход нет.</p>
        <table style="border-collapse:collapse;width:400px">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Дата сигнала</b></td><td style="padding:8px;border:1px solid #ddd">{date.strftime('%Y-%m-%d')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#e3f2fd"><b>Дата данных</b></td><td style="padding:8px;border:1px solid #ddd;background:#e3f2fd;font-weight:bold">{last_trade_date}</td></tr>
        {warning_html}
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Цена IMOEX</b></td><td style="padding:8px;border:1px solid #ddd">{price:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>EMA15</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{ema_fast:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>EMA50</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{ema_slow:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>ADX</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{adx:.1f} ({'слабый' if adx < 20 else 'средний' if adx < 30 else 'сильный'} тренд)</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Дней вне рынка</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{days_out}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Тип входа</b></td><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">{mode_text}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Фаза Вайкоффа</b></td><td style="padding:8px;border:1px solid #ddd;background:#fff3e0;font-weight:bold">{phase_name}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>До входа</b></td><td style="padding:8px;border:1px solid #ddd">Цена &gt; EMA15 ({ema_fast:,.0f}) и EMA50 ({ema_slow:,.0f})</td></tr>
        </table></body></html>"""
        return self._send(subject, body_html, body_text)

    def send_wait(self, date, price, ema_fast, ema_slow, adx, regime, days_out, last_trade_date, days_gap=0, entry_mode='limit_ema', wyckoff_phase=0):
        phase_names = self._get_phase_names()
        phase_name = phase_names.get(wyckoff_phase, 'Неизвестно')
        subject = f"🟡 WAIT IMOEX | {date.strftime('%Y-%m-%d')} | Приближение к входу | Фаза: {phase_name}"
        warning_html = f'<tr><td colspan="2" style="padding:8px;border:1px solid #ddd;background:#fff3e0;color:#e65100;font-weight:bold">⚠️ Данные устарели на {days_gap} дней. Показаны цены за {last_trade_date}.</td></tr>' if days_gap > 0 else ''
        warning_text = f'\n⚠️ ВНИМАНИЕ: Данные устарели на {days_gap} дней. Показаны цены за {last_trade_date}.' if days_gap > 0 else ''
        mode_text = "лимитная заявка на EMA" if entry_mode == 'limit_ema' else "рыночная заявка"
        body_text = f"СТАТУС: ОЖИДАНИЕ - IMOEX\nДата сигнала: {date.strftime('%Y-%m-%d')}\nДата данных: {last_trade_date}{warning_text}\nЦена: {price:,.2f} ₽\nEMA15: {ema_fast:,.2f} ₽\nEMA50: {ema_slow:,.2f} ₽\nADX: {adx:.1f}\nДней вне рынка: {days_out}\nТип входа: {mode_text}\nФаза Вайкоффа: {phase_name}"
        body_html = f"""<html><body style="font-family:Arial">
        <h2 style="color:#f9a825">🟡 WAIT - IMOEX</h2>
        <p style="color:#f9a825">Позиция закрыта. Цена приближается к уровню входа.</p>
        <table style="border-collapse:collapse;width:400px">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fffde7"><b>Дата сигнала</b></td><td style="padding:8px;border:1px solid #ddd">{date.strftime('%Y-%m-%d')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#e3f2fd"><b>Дата данных</b></td><td style="padding:8px;border:1px solid #ddd;background:#e3f2fd;font-weight:bold">{last_trade_date}</td></tr>
        {warning_html}
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fffde7"><b>Цена IMOEX</b></td><td style="padding:8px;border:1px solid #ddd">{price:,.2f} ₽</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fffde7"><b>EMA15</b></td><td style="padding:8px;border:1px solid #ddd;background:#fffde7">{ema_fast:,.2f} ₽ ({((price/ema_fast-1)*100):+.1f}%)</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fffde7"><b>EMA50</b></td><td style="padding:8px;border:1px solid #ddd;background:#fffde7">{ema_slow:,.2f} ₽ ({((price/ema_slow-1)*100):+.1f}%)</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fffde7"><b>ADX</b></td><td style="padding:8px;border:1px solid #ddd;background:#fffde7">{adx:.1f}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fffde7"><b>Дней вне рынка</b></td><td style="padding:8px;border:1px solid #ddd;background:#fffde7">{days_out}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fffde7"><b>Тип входа</b></td><td style="padding:8px;border:1px solid #ddd;background:#fffde7">{mode_text}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#fff3e0"><b>Фаза Вайкоффа</b></td><td style="padding:8px;border:1px solid #ddd;background:#fff3e0;font-weight:bold">{phase_name}</td></tr>
        </table></body></html>"""
        return self._send(subject, body_html, body_text)

    def send_alert(self, date, last_date, days_gap):
        subject = f"⚠️ ALERT IMOEX | Данные устарели на {days_gap} дн."
        body_text = f"ВНИМАНИЕ: Данные IMOEX устарели!\nПоследняя дата: {last_date}\nСегодня: {date.strftime('%Y-%m-%d')}\nРазрыв: {days_gap} дней"
        body_html = f"""<html><body style="font-family:Arial">
        <h2 style="color:#c62828">⚠️ ALERT - Данные устарели</h2>
        <table style="border-collapse:collapse;width:400px">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Сегодня</b></td><td style="padding:8px;border:1px solid #ddd">{date.strftime('%Y-%m-%d')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Последние данные</b></td><td style="padding:8px;border:1px solid #ddd">{last_date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#ffebee"><b>Разрыв</b></td><td style="padding:8px;border:1px solid #ddd">{days_gap} дней</td></tr>
        </table></body></html>"""
        return self._send(subject, body_html, body_text)

    def send_status_report(self, date, cagr, max_dd, sharpe, current_signal, 
                           last_price, ema_fast, ema_slow, adx, regime, days_out,
                           last_trade_date, days_gap, entry_mode, final_capital,
                           trades_count, win_rate, time_in_market, wyckoff_phase=0,
                           avg_phase_durations=None, current_phase_duration=0,
                           barometer_data=None):
        """Отправка полного отчёта при ручном запуске модели"""
        phase_names = self._get_phase_names()
        phase_name = phase_names.get(wyckoff_phase, 'Неизвестно')
        phase_arg = self._get_phase_arg(wyckoff_phase)
        status = "🟢 В ПОЗИЦИИ" if current_signal == 1 else "🔴 ВНЕ РЫНКА"
        subject = f"📊 IMOEX REPORT | {date.strftime('%Y-%m-%d')} | {status} | Фаза: {phase_name}"

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
Финальный капитал: {final_capital:,.0f} ₽

📊 ТЕКУЩИЙ СИГНАЛ
Статус: {status}
Цена: {last_price:,.2f} ₽
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
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Финальный капитал</b></td><td style="padding:8px;border:1px solid #ddd;font-weight:bold">{final_capital:,.0f} ₽</td></tr>
        </table>

        <h3 style="color:#1565c0">📊 Текущий сигнал</h3>
        <table style="border-collapse:collapse;width:500px">
        <tr><td style="padding:8px;border:1px solid #ddd;background:{'#e8f5e9' if current_signal==1 else '#ffebee'}"><b>Статус</b></td>
        <td style="padding:8px;border:1px solid #ddd;background:{'#e8f5e9' if current_signal==1 else '#ffebee'};font-weight:bold;font-size:16px">{status}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Цена IMOEX</b></td><td style="padding:8px;border:1px solid #ddd">{last_price:,.2f} ₽</td></tr>
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
        '<tr><td colspan="2" style="padding:8px;border:1px solid #ddd;font-family:monospace">' +
        'BEAR [' + "░" * int((barometer_data.get('composite', 0) + 100) * 30 / 200) + "█" + "░" * (30 - int((barometer_data.get('composite', 0) + 100) * 30 / 200)) + 
        '] BULL (Score: ' + f"{barometer_data.get('composite', 0):+.1f}" + ')</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd"><b>Smart Money Control</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd">' + f"{barometer_data.get('index_smart_control', 0):.1f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>Retail Control</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">' + f"{barometer_data.get('index_retail_control', 0):.1f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd"><b>ΔSmart (5 дней)</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd">' + f"{barometer_data.get('smart_delta_5d', 0):+.2f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5"><b>MXI Сигнал</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:#f5f5f5">' + str(barometer_data.get('mxi_signal', 'N/A')) + '</td></tr>' +
        (('<tr><td style="padding:8px;border:1px solid #ddd;background:#e3f2fd"><b>MXI Розница</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd;background:#e3f2fd">' + f"{barometer_data.get('mxi', {}).get('retail_pct', 0):.1f}" + '%</td></tr>' +
        '<tr><td style="padding:8px;border:1px solid #ddd"><b>MXI Чистая поз. розницы</b></td>' +
        '<td style="padding:8px;border:1px solid #ddd">' + f"{barometer_data.get('mxi', {}).get('net_fiz', 0):+,.0f}" + '</td></tr>') if barometer_data and barometer_data.get('mxi') else '') +
        '<tr><td colspan="2" style="padding:8px;border:1px solid #ddd;color:#666;font-size:12px">' +
        'Барометр основан на открытых позициях физ/юр лиц по фьючерсам компонентов IMOEX.<br>' +
        '<b>Не влияет на торговые решения</b> — только для подтверждения контекста.' +
        '</td></tr></table>' if barometer_data else ''}

        </body></html>"""
        return self._send(subject, body_html, body_text)



# =============================================================================
# MOEX BAROMETER LAYER — Автозагрузка с API, без CSV
# =============================================================================
class MOEXBarometerLayer:
    """
    Взвешенный барометр по 12 фьючерсам компонентов IMOEX + MXI.
    Загружает данные напрямую с MOEX JSON API за 14 торговых дней.
    Параллельная загрузка через ThreadPoolExecutor.
    НЕ требует CSV-файла. НЕ влияет на торговые решения.
    """
    IMOEX_WEIGHTS = {
        'SBRF': 0.16, 'LKOH': 0.14, 'GAZR': 0.10, 'YDEX': 0.07,
        'GMKN': 0.06, 'ROSN': 0.05, 'NVTK': 0.05, 'MGNT': 0.04,
        'PLZL': 0.03, 'VTBR': 0.03, 'ALRS': 0.02,
    }
    MXI_TICKER = 'MXI'
    TARGET_ASSETS = list(IMOEX_WEIGHTS.keys()) + [MXI_TICKER]
    REQUEST_TIMEOUT = 6
    FRESH_DAYS = 14
    MAX_WORKERS = 8

    # ASSETCODE для JSON API (NOTKM=NVTK, PLZLM=PLZL)
    JSON_CODES = {
        'SBRF': 'SBRF', 'LKOH': 'LKOH', 'GAZR': 'GAZR', 'YDEX': 'YDEX',
        'GMKN': 'GMKN', 'ROSN': 'ROSN', 'NVTK': 'NOTKM', 'MGNT': 'MGNT',
        'PLZL': 'PLZLM', 'VTBR': 'VTBR', 'ALRS': 'ALRS', 'MXI': 'MXI',
    }

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

    def __init__(self):
        self.df = None
        self._load_data()

    @staticmethod
    def _is_trading_day(d):
        if d.weekday() >= 5:
            return False
        if d in MOEXBarometerLayer.RUSSIAN_HOLIDAYS:
            return False
        return True

    def _fetch_json_api(self, asset_code, date_str):
        api_code = self.JSON_CODES.get(asset_code, asset_code)
        url = f"https://web.moex.com/moex-web-iss-api/api/v1/open-position/F/{api_code}"
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
                        "date": date_str, "asset": asset_code, "type": "futures",
                        "total_oi": total_oi, "fiz_oi": fiz_oi, "yur_oi": yur_oi,
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
        """Загружает все активы за один день параллельно."""
        records = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {executor.submit(self._fetch_json_api, asset, date_str): asset
                       for asset in self.TARGET_ASSETS}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    records.append(result)
        return records

    def _load_data(self):
        print("  [BARO] Загрузка данных с MOEX API (14 дней, параллельно)...")
        today = date.today()
        trading_days = []
        d = today
        while len(trading_days) < self.FRESH_DAYS:
            if self._is_trading_day(d):
                trading_days.insert(0, d)
            d -= timedelta(days=1)

        print(f"  [BARO] Период: {trading_days[0]} → {trading_days[-1]}")
        all_records = []

        for i, trade_date in enumerate(trading_days):
            date_str = trade_date.strftime("%Y-%m-%d")
            records = self._load_day(date_str)
            all_records.extend(records)
            print(f"    [{i+1:>2}/{len(trading_days)}] {date_str}: {len(records)}/{len(self.TARGET_ASSETS)} активов")

        if all_records:
            self.df = pd.DataFrame(all_records)
            self.df['date'] = pd.to_datetime(self.df['date'])
            for col in ['total_oi', 'fiz_oi', 'yur_oi', 'long_fiz', 'short_fiz', 'long_jur', 'short_jur']:
                if col in self.df.columns:
                    self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
            print(f"  [BARO] Готово: {len(self.df)} записей, {self.df['date'].nunique()} дат")
        else:
            self.df = pd.DataFrame()
            print("  [BARO] Нет данных")

    def get_current_metrics(self):
        if self.df is None or self.df.empty:
            return None
        df = self.df[self.df['type'] == 'futures'].copy()
        df = df[df['asset'].isin(self.TARGET_ASSETS)]
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(['asset', 'date'])
        if df.empty:
            return None

        latest_date = df['date'].max()
        latest = df[df['date'] == latest_date].set_index('asset')

        weighted_smart = 0.0
        weighted_retail = 0.0
        covered_weight = 0.0
        details = []

        for asset, weight in self.IMOEX_WEIGHTS.items():
            if asset not in latest.index:
                details.append({'asset': asset, 'weight': weight, 'smart_pct': None, 'retail_pct': None, 'status': '❌'})
                continue
            row = latest.loc[asset]
            smart_pct = row['yur_share']
            retail_pct = row['fiz_share']
            weighted_smart += smart_pct * weight
            weighted_retail += retail_pct * weight
            covered_weight += weight
            details.append({'asset': asset, 'weight': weight, 'smart_pct': smart_pct, 'retail_pct': retail_pct,
                            'smart_contrib': smart_pct * weight, 'total_oi': row['total_oi'], 'status': '✅'})

        index_smart = weighted_smart / covered_weight if covered_weight > 0 else 0
        index_retail = weighted_retail / covered_weight if covered_weight > 0 else 0

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
        if len(unique_dates) >= 6:
            five_days_ago = unique_dates[-6]
            past = df[df['date'] == five_days_ago].set_index('asset')
            if not past.empty:
                w_delta = 0.0
                for asset, weight in self.IMOEX_WEIGHTS.items():
                    if asset in latest.index and asset in past.index:
                        w_delta += (latest.loc[asset, 'yur_share'] - past.loc[asset, 'yur_share']) * weight
                norm_smart_delta = w_delta / covered_weight if covered_weight > 0 else 0

        control_score = (index_smart - 50) * 2
        delta_score = norm_smart_delta * 10
        composite = np.clip(control_score * 0.50 + delta_score * 0.30 + mxi_penalty * 0.20, -100, 100)

        if composite > 40: bar_signal = "🟢 STRONG BUY"
        elif composite > 15: bar_signal = "🟢 BUY"
        elif composite > -15: bar_signal = "⚪ NEUTRAL"
        elif composite > -40: bar_signal = "🔴 SELL"
        else: bar_signal = "🔴 STRONG SELL"

        return {
            'date': latest_date, 'index_smart_control': index_smart, 'index_retail_control': index_retail,
            'covered_weight': covered_weight, 'smart_delta_5d': norm_smart_delta,
            'mxi': mxi_data, 'mxi_signal': mxi_signal, 'composite': composite,
            'signal': bar_signal, 'details': details, 'data_fresh': True,
        }

    def get_freshness_status(self, today=None):
        if self.df is None or self.df.empty:
            return "❌ Нет данных барометра"
        latest = self.df['date'].max()
        if today is None:
            today = pd.Timestamp.now()
        gap = (today - latest).days
        if gap <= 1:
            return f"✅ Данные актуальны ({latest.date()})"
        return f"⚠️ Данные устарели на {gap} дн."

# =============================================================================
# ЗАГРУЗКА ДАННЫХ
# =============================================================================
def load_imoex_data(from_date="2003-01-01", to_date=None):
    if to_date is None:
        to_date = datetime.today().strftime("%Y-%m-%d")
    all_data = []
    base_url = "https://iss.moex.com/iss/history/engines/stock/markets/index/securities/IMOEX.json"
    start = 0
    print(f"[INFO] Загрузка данных: {from_date} - {to_date}")
    while True:
        url = f"{base_url}?from={from_date}&till={to_date}&start={start}"
        try:
            r = requests.get(url, timeout=30)
            data = r.json()
            rows = data['history']['data']
            if not rows:
                break
            all_data.extend(rows)
            start += 100
        except Exception as e:
            print(f"[ERR] Ошибка загрузки: {e}")
            break
    columns = ["BOARDID", "SECID", "TRADEDATE", "SHORTNAME", "NAME", "CLOSE", 
               "OPEN", "HIGH", "LOW", "VALUE", "DURATION", "YIELD", "DECIMALS", 
               "CAPITALIZATION", "CURRENCYID", "DIVISOR", "TRADINGSESSION", 
               "VOLUME", "TRADE_SESSION_DATE", "RECALC_DATE"]
    df = pd.DataFrame(all_data, columns=columns)
    df['TRADEDATE'] = pd.to_datetime(df['TRADEDATE'])
    for col in ['CLOSE', 'OPEN', 'HIGH', 'LOW']:
        df[col.lower()] = pd.to_numeric(df[col], errors='coerce')
    df = df.drop_duplicates(subset=['TRADEDATE']).sort_values('TRADEDATE')
    df = df.set_index('TRADEDATE')
    last_date = df.index.max()
    today = datetime.today()
    days_gap = (today - last_date).days
    print(f"[OK] Данные: {df.index.min().date()} - {last_date.date()}, {len(df)} записей")
    return df, last_date, days_gap


# =============================================================================
# РЕАЛЬНЫЕ КЛЮЧЕВЫЕ СТАВКИ ЦБ РФ
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
    """Возвращает название фазы Вайкоффа (исправленное)"""
    names = {
        0: 'Нейтральная',
        1: 'Накопление (Accumulation)',
        2: 'Распределение (Distribution)',
        3: 'Ослабление тренда',
        4: 'Аккумуляция (Mark-down)'
    }
    return names.get(phase, 'Неизвестно')


def get_wyckoff_phase_arg(phase):
    """Возвращает аргументацию смысла фазы Вайкоффа"""
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
# СТРАТЕГИЯ V2.3.2 (базовая V2.3.1 + информационные фазы Вайкоффа)
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

    # V2.3.2: ФАЗЫ ВАЙКОФФА — ТОЛЬКО ДЛЯ ИНФОРМАЦИИ, НЕ ДЛЯ ТОРГОВЛИ
    df['WyckoffPhase'] = 0
    df.loc[(df['close'] > df['EMA_fast']) & (df['close'] > df['EMA_slow']) & (df['close'] < df['MA_long']), 'WyckoffPhase'] = 1
    df.loc[(df['close'] > df['EMA_fast']) & (df['close'] > df['EMA_slow']) & (df['close'] > df['MA_long']), 'WyckoffPhase'] = 2
    df.loc[(df['close'] < df['EMA_slow']) & (df['close'] > df['MA_long']), 'WyckoffPhase'] = 3
    df.loc[(df['close'] < df['EMA_slow']) & (df['close'] < df['MA_long']), 'WyckoffPhase'] = 4

    # Расчёт средней длительности непрерывных фаз и текущей длительности
    phase_series = df['WyckoffPhase']
    current_phase = phase_series.iloc[-1]
    current_duration = 0
    for i in range(len(phase_series) - 1, -1, -1):
        if phase_series.iloc[i] == current_phase:
            current_duration += 1
        else:
            break

    # Средняя длительность непрерывных отрезков каждой фазы
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

    # Базовая торговая логика V2.3.1 (без изменений)
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

    # Цена исполнения ВХОДА
    if entry_mode == 'open':
        df['ExecPrice'] = df['open'].shift(-1)
    elif entry_mode == 'close':
        df['ExecPrice'] = df['close']
    elif entry_mode == 'limit_ema':
        next_open = df['open'].shift(-1)
        ema_fast_val = df['EMA_fast']
        df['ExecPrice'] = np.where(next_open <= ema_fast_val, next_open, ema_fast_val)
    df.loc[df.index[-1], 'ExecPrice'] = df['close'].iloc[-1]

    # Цена исполнения ВЫХОДА (всегда на открытии следующего дня)
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

        # АВАРИЙНЫЙ СТОП
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

    # Статистика по фазам (для отчёта)
    phase_stats = df['WyckoffPhase'].value_counts().sort_index().to_dict()

    # Текущий статус для email
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

    # --- БАРОМЕТР: информационный слой (не влияет на торговлю) ---
    barometer_data = None
    if barometer_layer is not None:
        try:
            barometer_data = barometer_layer.get_current_metrics()
            print(f"\n[INFO] Барометр: {barometer_layer.get_freshness_status()}")
        except Exception as e:
            print(f"[WARN] Ошибка барометра: {e}")

    # Email только при ручном запуске
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
            final_capital=final,
            trades_count=len(trades),
            win_rate=win_rate,
            time_in_market=time_in_market,
            wyckoff_phase=last_phase,
            avg_phase_durations=avg_durations,
            current_phase_duration=current_duration,
            barometer_data=barometer_data
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
# ГЛАВНЫЙ БЛОК — РУЧНОЙ ЗАПУСК
# =============================================================================
if __name__ == "__main__":
    print("=" * 75)
    print("  IMOEX V2.3.2 — МОДЕЛЬ С ИНФОРМАЦИОННЫМИ ФАЗАМИ ВАЙКОФФА")
    print(f"  Запуск: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75)
    print()

    notifier = SignalNotifier()

    # Инициализация барометра (автозагрузка с MOEX API)
    barometer = MOEXBarometerLayer()

    df, last_date_data, days_gap = load_imoex_data()

    if days_gap > 1:
        print(f"[WARN] Данные устарели на {days_gap} дней!")

    # V2.3.2 Рекомендуемые параметры
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
    print("  РЕЗУЛЬТАТЫ БЭКТЕСТА V2.3.2 (с информационными фазами)")
    print("=" * 75)
    print(f"  Период:            {result['equity'].index[0].date()} - {result['equity'].index[-1].date()}")
    print(f"  Начальный капитал: 1,000,000 ₽")
    print(f"  Финальный капитал: {result['final']:>15,.0f} ₽")
    print(f"  Прибыль:           {(result['final']/1e6 - 1)*100:>14.1f}%")
    print(f"  CAGR:              {result['cagr']:>15.2f}%")
    print(f"  Max Drawdown:      {result['max_dd']:>14.2f}%")
    print(f"  Sharpe:            {result['sharpe']:>15.2f}")
    print(f"  Sortino:           {result['sortino']:>15.2f}")
    print(f"  Calmar:            {result['calmar']:>15.2f}")
    print(f"  Сделок:            {result['trades']:>15d}")
    print(f"  Аварийных выходов: {result['emergency_count']:>15d}")
    print(f"  Win Rate:          {result['win_rate']:>14.1f}%")
    print(f"  Profit Factor:     {result['profit_factor']:>15.2f}")
    print(f"  Expectancy:        {result['expectancy']:>14.2f}%")
    print(f"  Avg Win:           {result['avg_win']:>14.2f}%")
    print(f"  Avg Loss:          {result['avg_loss']:>14.2f}%")
    print(f"  Время в рынке:     {result['time_in_market']:>13.1f}%")
    print(f"  Тип входа:         {result['entry_mode']:>15s}")
    print(f"  Дивиденды:         {'+3% годовых в кэше':>15s}")
    print("=" * 75)

    print()
    print("=" * 75)
    print("  🔄 ФАЗА ВАЙКОФФА (ИНФОРМАЦИОННО)")
    print("=" * 75)
    print("  Фаза определяется по положению цены относительно EMA15, EMA50 и MA126.")
    print("  НЕ влияет на торговые решения — только для аналитики.")
    print()
    print(f"  Текущая фаза: {current_phase_name}")
    print(f"  Аргументация: {current_phase_arg}")
    print(f"  Средняя длительность непрерывной фазы «{current_phase_name}»: {result['avg_phase_durations'][result['last_phase']]:.0f} дн.")
    print(f"  Текущая непрерывная фаза длится уже: {result['current_phase_duration']} дн.")
    print()
    print("  Примечание: средняя длительность — для непрерывных отрезков одной фазы.")
    print("  Полный цикл (например, медвежий рынок) обычно состоит из чередования")
    print("  фаз Ослабления тренда и Аккумуляции и длится дольше.")
    print("=" * 75)

    print()
    print("=" * 75)
    print("  ТЕКУЩИЙ СИГНАЛ")
    print("=" * 75)
    status = "🟢 ОТКРЫТА" if result['last_signal'] == 1 else "🔴 ЗАКРЫТА"
    print(f"  Позиция: {status}")
    print(f"  Дата сигнала: {result['last_date'].strftime('%Y-%m-%d')}")
    print(f"  Дата данных:  {result['last_trade_date']} (разрыв: {result['days_gap']} дн.)")
    print(f"  Цена:     {result['last_price']:,.2f} ₽")
    print(f"  EMA15:    {result['last_ema_fast']:,.2f} ₽")
    print(f"  EMA50:    {result['last_ema_slow']:,.2f} ₽")
    print(f"  ADX:      {result['last_adx']:.1f}")
    print(f"  Режим:    {result['last_regime']} ({'слабый' if result['last_regime']==0 else 'средний' if result['last_regime']==1 else 'сильный'})")
    print(f"  Фаза:     {current_phase_name}")
    print(f"  Тип входа: {result['entry_mode']}")
    if result['last_signal'] == 0:
        print(f"  Дней вне рынка: {result['days_out']}")
        if result['last_price'] > result['last_ema_fast'] and result['last_price'] > result['last_ema_slow'] and result['last_regime'] > 0:
            print(f"  ⚡ СИГНАЛ: WAIT (приближение к входу)")
        else:
            print(f"  ⏸️  СИГНАЛ: HOLD CASH (нет сигнала)")
    print("=" * 75)

    # --- БАРОМЕТР (консоль) ---
    if result.get('barometer'):
        b = result['barometer']
        print()
        print("=" * 75)
        print("  📊 SMART MONEY BAROMETER (информационный слой)")
        print("=" * 75)
        print(f"  Дата данных:      {b['date'].date()}")
        print(f"  Сигнал:           {b['signal']}")
        print(f"  Composite Score:  {b['composite']:+.1f} / 100")
        print(f"  Smart Control:    {b['index_smart_control']:.1f}%")
        print(f"  Retail Control:   {b['index_retail_control']:.1f}%")
        print(f"  ΔSmart (5д):      {b['smart_delta_5d']:+.2f}%")
        print(f"  MXI:              {b['mxi_signal']}")
        if b.get('mxi'):
            print(f"  MXI Розница:      {b['mxi']['retail_pct']:.1f}% "
                  f"(чистая поз. {b['mxi']['net_fiz']:+,.0f})")
        print(f"  Покрытие индекса: {b['covered_weight']*100:.0f}%")
        print("  ─" + "─" * 73)
        print("  ⚠️  Барометр НЕ влияет на торговые решения — только для контекста.")
        print("=" * 75)
    else:
        print("\n  [INFO] Барометр недоступен")

    print(f"\n[OK] Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("[INFO] Email-отчёт отправлен (если настроен)")
