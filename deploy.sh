#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# TOBI deploy script — pull latest code, rebuild frontend, restart backend.
# Usage on VPS:  bash deploy.sh
#
# For systemd setups, this script is the ExecStartPre / post-receive hook.
# It only restarts if the build succeeds — a failed build keeps the old server
# running so you don't lose the dashboard mid-deploy.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

echo "── Pulling latest code ──"
git pull

echo "── Building frontend ──"
cd dashboard
npm install --silent
npm run build
cd ..

echo "── Restarting backend ──"
if command -v systemctl &>/dev/null && systemctl list-units --full | grep -q "tobi"; then
  # systemd manages TOBI — just restart the service
  sudo systemctl restart tobi
  echo "✓ Restarted via systemd (sudo systemctl restart tobi)"
else
  # No systemd — kill old process and start fresh
  pkill -f "python.*main.py start" && echo "  killed old process" || echo "  no old process found"
  nohup venv/bin/python main.py start > logs/tobi.log 2>&1 &
  echo "✓ Started in background (logs/tobi.log)"
fi

echo "── Deploy complete ──"
