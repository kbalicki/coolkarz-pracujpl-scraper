#!/usr/bin/env python3
"""Watchdog scrapera pracuj.pl.

Uruchamiany z crona co godzinę. Pilnuje dwóch rzeczy:

1. Panel webowy odpowiada - jeśli nie, restartuje usługę systemd.
2. Dane są świeże - jeśli nie, próbuje sam naprawić sytuację uruchamiając
   scraper (który m.in. doinstalowuje brakującą przeglądarkę Playwrighta).

Jeśli po próbie naprawy problem zostaje, wysyła maila alarmowego.
Gdy problem sam ustąpi, wysyła maila "wróciło do normy". Alarmy mają cooldown,
żeby nie zasypać skrzynki przy dłuższej awarii.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

sys.path.insert(0, str(BASE_DIR))
from alerts import send_alert  # noqa: E402

OFFERS_PATH = BASE_DIR / "offers.json"
STATUS_PATH = BASE_DIR / "last_run.json"
STATE_PATH = BASE_DIR / "watchdog_state.json"
SCRAPER_PATH = BASE_DIR / "scraper.py"
VENV_PYTHON = BASE_DIR / "venv" / "bin" / "python3"

APP_PORT = os.getenv("APP_PORT", "8112")
HEALTH_URL = os.getenv("WATCHDOG_HEALTH_URL", f"http://127.0.0.1:{APP_PORT}/health")
SERVICE_NAME = os.getenv("WATCHDOG_SERVICE", "pracuj-scraper")
STALE_AFTER_HOURS = int(os.getenv("STALE_AFTER_HOURS", "30"))
ALERT_COOLDOWN_HOURS = int(os.getenv("ALERT_COOLDOWN_HOURS", "12"))
REPAIR_COOLDOWN_HOURS = int(os.getenv("REPAIR_COOLDOWN_HOURS", "6"))


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def read_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default if default is not None else {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def cooldown_passed(iso_value, hours):
    stamp = parse_iso(iso_value)
    return stamp is None or datetime.now() - stamp > timedelta(hours=hours)


def systemctl(*args):
    """systemctl --user z crona wymaga wskazania XDG_RUNTIME_DIR."""
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True, text=True, timeout=60, env=env,
    )


def panel_responds():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=15) as resp:
            return True, resp.status
    except urllib.error.HTTPError as e:
        # 503 = panel żyje, ale zgłasza nieaktualne dane - to osobny problem
        return True, e.code
    except Exception as e:
        log(f"Panel nie odpowiada: {type(e).__name__}: {e}")
        return False, None


def check_panel():
    """Zwraca opis problemu albo None. Po drodze próbuje zrestartować usługę."""
    alive, _ = panel_responds()
    if alive:
        return None

    log(f"Restartuję usługę {SERVICE_NAME}")
    result = systemctl("restart", SERVICE_NAME)
    if result.returncode != 0:
        log(f"systemctl restart zwrócił {result.returncode}: {result.stderr.strip()}")

    for _ in range(6):
        time.sleep(5)
        alive, _ = panel_responds()
        if alive:
            log("Panel wstał po restarcie")
            return None

    return f"Panel webowy nie odpowiada pod {HEALTH_URL} mimo restartu usługi {SERVICE_NAME}."


def check_data():
    """Zwraca opis problemu z danymi albo None."""
    offers = read_json(OFFERS_PATH)
    last_run = read_json(STATUS_PATH)

    date = parse_iso(offers.get("date"))
    if date is None:
        return "Brak pliku offers.json albo nieczytelna data ostatniej aktualizacji."

    age_hours = (datetime.now() - date).total_seconds() / 3600
    if age_hours > STALE_AFTER_HOURS:
        return (f"Dane mają {age_hours:.1f} godz. (limit {STALE_AFTER_HOURS} godz.). "
                f"Ostatnia udana aktualizacja: {date:%Y-%m-%d %H:%M:%S}.")

    if last_run.get("ok") is False:
        return f"Ostatnie uruchomienie scrapera zakończyło się błędem: {last_run.get('error')}"

    return None


def run_scraper():
    """Próba samonaprawy - scraper sam doinstaluje brakującą przeglądarkę."""
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    log("Uruchamiam scraper (próba naprawy)")
    try:
        result = subprocess.run(
            [python, str(SCRAPER_PATH)],
            capture_output=True, text=True, timeout=1800, cwd=str(BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        log("Scraper przekroczył limit czasu")
        return False, "Scraper przekroczył limit czasu (30 min)."

    output = (result.stdout + result.stderr)
    log(f"Scraper zakończony kodem {result.returncode}")
    if result.returncode == 0:
        return True, ""
    return False, output[-3000:]


def trim_logs(max_bytes=5 * 1024 * 1024, keep_lines=2000):
    """Logi rosną bez końca (cron dopisuje) - przycinamy je same z siebie."""
    for name in ("cron.log", "watchdog.log", "app.log"):
        path = BASE_DIR / name
        try:
            if path.exists() and path.stat().st_size > max_bytes:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-keep_lines:]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                log(f"Przycięto {name} do ostatnich {keep_lines} linii")
        except OSError as e:
            log(f"Nie udało się przyciąć {name}: {e}")


def main():
    trim_logs()
    state = read_json(STATE_PATH, {})
    problems = []
    repaired = False
    scraper_output = ""

    panel_problem = check_panel()
    if panel_problem:
        problems.append(panel_problem)

    data_problem = check_data()
    if data_problem:
        log(f"Problem z danymi: {data_problem}")
        if cooldown_passed(state.get("last_repair"), REPAIR_COOLDOWN_HOURS):
            state["last_repair"] = datetime.now().isoformat()
            save_state(state)
            ok, scraper_output = run_scraper()
            still_broken = check_data()
            if ok and not still_broken:
                log("Naprawione automatycznie")
                repaired = True
                data_problem = None
            else:
                data_problem = still_broken or data_problem
        else:
            log(f"Naprawa pominięta - ostatnia próba mniej niż {REPAIR_COOLDOWN_HOURS} godz. temu")

    if data_problem:
        problems.append(data_problem)

    if problems:
        body = "Scraper pracuj.pl zgłasza problem:\n\n" + "\n\n".join(f"- {p}" for p in problems)
        if scraper_output:
            body += f"\n\nOstatnie linie logu scrapera:\n{scraper_output}"
        body += ("\n\nPanel: https://pracuj.k4.pl/\n"
                 f"Log crona: {BASE_DIR}/cron.log\n"
                 f"Log watchdoga: {BASE_DIR}/watchdog.log")

        if cooldown_passed(state.get("last_alert"), ALERT_COOLDOWN_HOURS):
            if send_alert("[ALARM] Scraper pracuj.pl nie działa", body):
                state["last_alert"] = datetime.now().isoformat()
        else:
            log(f"Alarm pominięty - cooldown {ALERT_COOLDOWN_HOURS} godz.")
        state["alerted"] = True
        state["problem"] = problems[0]
        save_state(state)
        return 1

    if state.get("alerted"):
        send_alert(
            "[OK] Scraper pracuj.pl znowu działa",
            "Problem zgłoszony wcześniej ustąpił - dane są aktualne, panel odpowiada.\n\n"
            f"Poprzedni problem: {state.get('problem', 'nieznany')}",
        )
    elif repaired:
        send_alert(
            "[NAPRAWIONE] Scraper pracuj.pl - awaria usunięta automatycznie",
            "Watchdog wykrył nieaktualne dane i naprawił to sam, uruchamiając scraper.\n"
            "Serwis działa, ale warto sprawdzić przyczynę w cron.log.",
        )

    state["alerted"] = False
    state.pop("problem", None)
    state["last_ok"] = datetime.now().isoformat()
    save_state(state)
    log("Wszystko OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
