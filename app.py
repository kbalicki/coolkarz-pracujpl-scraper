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
ENV_PATH = Path(__file__).parent / ".env"
OFFERS_PATH = Path(__file__).parent / "offers.json"
URLS_PATH = Path(__file__).parent / "urls.txt"
SCRAPER_PATH = Path(__file__).parent / "scraper.py"
VENV_PYTHON = Path(__file__).parent / "venv" / "bin" / "python3"

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
    return render_template("index.html", data=data)


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
    return render_template("settings.html", include=include, exclude=exclude, urls=urls, status=scrape_status)


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
    app.run(host="0.0.0.0", port=5000)
