#!/usr/bin/env python3

import json
import os
import subprocess
import threading
from pathlib import Path
from functools import wraps
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET", "zmien-na-losowy-ciag-w-produkcji")

APP_USER = os.getenv("APP_USER", "coolkarz")
APP_PASS = os.getenv("APP_PASS", "Praca1")
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
OFFERS_PATH = BASE_DIR / "offers.json"
URLS_PATH = BASE_DIR / "urls.txt"
SCRAPER_PATH = BASE_DIR / "scraper.py"
STATUS_PATH = BASE_DIR / "last_run.json"
VENV_PYTHON = BASE_DIR / "venv" / "bin" / "python3"

# Po ilu godzinach bez świeżych danych panel pokazuje ostrzeżenie.
# Cron chodzi raz na dobę o 5:00, więc 30 h daje zapas na jedno nieudane uruchomienie.
STALE_AFTER_HOURS = int(os.getenv("STALE_AFTER_HOURS", "30"))

scrape_status = {"running": False, "log": "", "last_run": None}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def load_offers():
    if not OFFERS_PATH.exists():
        return {"date": None, "count": 0, "offers": []}
    return json.loads(OFFERS_PATH.read_text(encoding="utf-8"))


def load_last_run():
    if not STATUS_PATH.exists():
        return {}
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def build_health(data):
    """Wiek danych i wynik ostatniego uruchomienia scrapera."""
    last_run = load_last_run()
    age_hours = None
    if data.get("date"):
        try:
            age_hours = round((datetime.now() - datetime.fromisoformat(data["date"])).total_seconds() / 3600, 1)
        except ValueError:
            age_hours = None

    stale = age_hours is None or age_hours > STALE_AFTER_HOURS
    return {
        "ok": not stale and last_run.get("ok", True),
        "stale": stale,
        "age_hours": age_hours,
        "stale_after_hours": STALE_AFTER_HOURS,
        "last_update": data.get("date"),
        "count": data.get("count", 0),
        "last_run_ok": last_run.get("ok"),
        "last_run_finished": last_run.get("finished"),
        "last_run_error": last_run.get("error"),
    }


def read_env_filters():
    include = ""
    exclude = ""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("COUNTRIES_INCLUDE="):
                include = line.split("=", 1)[1]
            elif line.startswith("COUNTRIES_EXCLUDE="):
                exclude = line.split("=", 1)[1]
    return include, exclude


def write_env_filters(include, exclude):
    if not ENV_PATH.exists():
        return
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("COUNTRIES_INCLUDE="):
            new_lines.append(f"COUNTRIES_INCLUDE={include}")
        elif stripped.startswith("COUNTRIES_EXCLUDE="):
            new_lines.append(f"COUNTRIES_EXCLUDE={exclude}")
        else:
            new_lines.append(line)
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def read_urls():
    if URLS_PATH.exists():
        return URLS_PATH.read_text(encoding="utf-8")
    return ""


def write_urls(text):
    URLS_PATH.write_text(text.strip() + "\n", encoding="utf-8")


def run_scraper_bg():
    scrape_status["running"] = True
    scrape_status["log"] = ""
    try:
        python = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"
        result = subprocess.run(
            [python, str(SCRAPER_PATH)],
            capture_output=True, text=True, timeout=600,
            cwd=str(SCRAPER_PATH.parent),
        )
        scrape_status["log"] = result.stdout + result.stderr
        if result.returncode != 0:
            scrape_status["log"] += f"\n[scraper zakończony kodem {result.returncode}]"
    except subprocess.TimeoutExpired:
        scrape_status["log"] = "BŁĄD: Scraper przekroczył limit czasu (10 min)"
    except Exception as e:
        scrape_status["log"] = f"BŁĄD: {e}"
    finally:
        scrape_status["running"] = False
        scrape_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@app.route("/")
def index():
    data = load_offers()
    return render_template("index.html", data=data, health=build_health(data))


@app.route("/health")
def health():
    """Status dla monitoringu: HTTP 200 gdy dane świeże, 503 gdy nie."""
    info = build_health(load_offers())
    return jsonify(info), (200 if info["ok"] else 503)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["user"] == APP_USER and request.form["pass"] == APP_PASS:
            session["logged_in"] = True
            return redirect(url_for("settings"))
        flash("Nieprawidłowy login lub hasło")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("index"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        include = request.form.get("include", "").strip()
        exclude = request.form.get("exclude", "").strip()
        urls_text = request.form.get("urls", "").strip()
        write_env_filters(include, exclude)
        write_urls(urls_text)
        flash("Ustawienia zapisane")
        return redirect(url_for("settings"))
    include, exclude = read_env_filters()
    urls = read_urls()
    return render_template("settings.html", include=include, exclude=exclude, urls=urls,
                           status=scrape_status, health=build_health(load_offers()))


@app.route("/scrape", methods=["POST"])
@login_required
def scrape_now():
    if scrape_status["running"]:
        flash("Scraper już działa, poczekaj na zakończenie")
    else:
        thread = threading.Thread(target=run_scraper_bg, daemon=True)
        thread.start()
        flash("Scraper uruchomiony w tle — odśwież stronę za ~2 minuty")
    return redirect(url_for("settings"))


@app.route("/scrape-status")
@login_required
def scrape_status_api():
    return jsonify(scrape_status)


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
