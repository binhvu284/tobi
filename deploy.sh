#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# TOBI deploy script — rebuild frontend + restart backend.
#
# Called automatically by the post-receive git hook on push.
# Can also be run manually:  bash deploy.sh
#
# Safe re-deploy: a failed build keeps the old server running.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

LOG_FILE="logs/tobi.log"
PID_FILE="logs/tobi.pid"
PYTHON="venv/bin/python"
[ -f "$PYTHON" ] || PYTHON="venv/Scripts/python.exe"

# ── 1. Install Python deps (in case requirements.txt changed) ──
if [ -f "venv/bin/pip" ]; then
    echo "── Checking Python dependencies ──"
    venv/bin/pip install -q -r requirements.txt 2>/dev/null || true
fi

# ── 2. Build frontend ──
if [ -d "dashboard/node_modules" ]; then
    echo "── Building frontend ──"
    cd dashboard
    npm run build || { echo "  ✗ Frontend build FAILED — keeping old build"; cd ..; exit 1; }
    cd ..
else
    echo "── Installing frontend deps + building ──"
    cd dashboard
    npm install --silent || true
    npm run build || { echo "  ✗ Frontend build FAILED — keeping old build"; cd ..; exit 1; }
    cd ..
fi

echo "✓ Frontend built"

# ── 3. Restart backend ──
echo "── Restarting backend ──"
mkdir -p logs

# Kill old process
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi
# Fallback: kill by pattern if no PID file
pkill -f "python.*main.py start" 2>/dev/null || true
sleep 1

# Start fresh
nohup "$PYTHON" main.py start > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

sleep 3
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "✓ Backend started (PID: $NEW_PID)"
else
    echo "  ✗ Backend failed to start — check $LOG_FILE"
    exit 1
fi

# Restart the separately supervised coding runner when it is installed.
if command -v systemctl >/dev/null 2>&1 && \
   systemctl list-unit-files tobi-coding-runner.service >/dev/null 2>&1; then
    echo "── Restarting supervised coding runner ──"
    if sudo -n systemctl restart tobi-coding-runner.service; then
        sudo -n systemctl is-active --quiet tobi-coding-runner.service || {
            echo "  ✗ Coding runner failed to start"
            exit 1
        }
        echo "✓ Coding runner restarted"
    else
        echo "  ⚠ Could not restart tobi-coding-runner.service without sudo."
    fi
elif grep -q '^TOBI_CODING_RUNNER_MODE=service' .env 2>/dev/null; then
    echo "  ⚠ Service runner mode is enabled but tobi-coding-runner.service is not installed."
fi

echo ""
echo "════════════════════════════════════════════════"
echo "  ✓ Deploy complete"
echo "  PID: $NEW_PID"
echo "  Log: $LOG_FILE"
echo "════════════════════════════════════════════════"
