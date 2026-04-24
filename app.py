#!/usr/bin/env python3

import json
import os
from pathlib import Path
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET", "zmien-na-losowy-ciag-w-produkcji")

APP_USER = os.getenv("APP_USER", "coolkarz")
APP_PASS = os.getenv("APP_PASS", "Praca1")
ENV_PATH = Path(__file__).parent / ".env"
OFFERS_PATH = Path(__file__).parent / "offers.json"


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
        write_env_filters(include, exclude)
        flash("Filtry zapisane")
        return redirect(url_for("settings"))
    include, exclude = read_env_filters()
    return render_template("settings.html", include=include, exclude=exclude)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
