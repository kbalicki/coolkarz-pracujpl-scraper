#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/app.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        kill "$PID"
        echo "[*] Stopped PID=$PID"
    else
        echo "[!] Process $PID not running"
    fi
    rm -f "$PID_FILE"
else
    echo "[!] No PID file"
fi
