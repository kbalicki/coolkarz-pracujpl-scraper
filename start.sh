#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/app.pid"
LOG_FILE="$SCRIPT_DIR/app.log"

if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
    echo "[!] App already running, PID=$(cat "$PID_FILE")"
    exit 0
fi

echo "[*] Starting pracuj.pl scraper web app on port 8112..."
nohup "$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/app.py" > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo "[*] Started, PID=$!, log: $LOG_FILE"
