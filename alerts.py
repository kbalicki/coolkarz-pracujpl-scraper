#!/usr/bin/env python3
"""Wysyłka maili alarmowych o awarii scrapera.

Celowo niezależna od SEND_EMAIL - na produkcji maile z ofertami są wyłączone,
ale alarmy mają chodzić zawsze.
"""

import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime


def alerts_enabled():
    return os.getenv("SEND_ALERTS", "1") != "0"


def _smtp_config():
    return {
        "server": os.getenv("ALERT_SMTP_SERVER") or os.getenv("SMTP_SERVER"),
        "port": int(os.getenv("ALERT_SMTP_PORT") or os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("ALERT_SMTP_USERNAME") or os.getenv("SMTP_USERNAME"),
        "password": os.getenv("ALERT_SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD"),
        "sender": os.getenv("ALERT_EMAIL_FROM") or os.getenv("EMAIL_FROM"),
        "recipient": os.getenv("ALERT_EMAIL_TO", "monitor@web-systems.pl"),
    }


def send_alert(subject, body):
    """Wysyła maila alarmowego. Zwraca True/False, nigdy nie rzuca wyjątkiem -
    nieudany alarm nie może wywalić procesu, który go zgłasza."""
    if not alerts_enabled():
        print("[alert] Alarmy wyłączone (SEND_ALERTS=0)")
        return False

    cfg = _smtp_config()
    missing = [k for k in ("server", "username", "password", "sender", "recipient") if not cfg[k]]
    if missing:
        print(f"[alert] Brak konfiguracji SMTP dla alarmów: {', '.join(missing)}")
        return False

    host = os.getenv("ALERT_HOSTNAME") or os.uname().nodename
    full_body = (
        f"{body}\n\n"
        f"---\n"
        f"Host: {host}\n"
        f"Katalog: {os.path.dirname(os.path.abspath(__file__))}\n"
        f"Czas: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
    )

    msg = MIMEText(full_body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["recipient"]

    try:
        with smtplib.SMTP(cfg["server"], cfg["port"], timeout=30) as server:
            server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["sender"], [cfg["recipient"]], msg.as_string())
    except Exception as e:
        print(f"[alert] Nie udało się wysłać alarmu: {type(e).__name__}: {e}")
        return False

    print(f"[alert] Wysłano alarm do {cfg['recipient']}: {subject}")
    return True
