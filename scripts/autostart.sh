#!/bin/bash
echo "🚀 Tobi autostart..."
cd /workspaces/tobi
mkdir -p ~/.local/bin && ln -sf /workspaces/tobi/tobi ~/.local/bin/tobi
source venv/bin/activate 2>/dev/null || python3 -m venv venv && source venv/bin/activate
pip install -q -r requirements.txt
tmux kill-session -t tobi 2>/dev/null || true
tmux new-session -d -s tobi 'cd /workspaces/tobi && source venv/bin/activate && python3 main.py start >> logs/tobi.log 2>&1'
echo "✅ Tobi started in tmux session 'tobi'"
tmux ls

# Mission Control (port 8080) must be PUBLIC so the Telegram link opens on a
# phone / outside this Codespace. Codespaces forwards ports as private by
# default (404s for anyone not signed in) AND resets them to private on every
# restart, so we must re-flip 8080 each boot. On a cold restart the container
# does pip/venv work first, so the dashboard can take MINUTES to bind — poll up
# to 5 min, then retry the flip until `gh ports` actually reports public (the
# first call can race the port-forward registration after a restart). All
# output goes to logs/autostart.log — no silent failures. Background, never
# blocks boot. Needs gh + CODESPACE_NAME (both present in Codespaces).
if [ -n "$CODESPACE_NAME" ]; then
  (
    mkdir -p /workspaces/tobi/logs
    log=/workspaces/tobi/logs/autostart.log
    echo "[$(date -Is)] autostart: waiting for dashboard on :8080 (up to 5 min)..." >> "$log"
    up=0
    for _ in $(seq 1 150); do
      if curl -sf -o /dev/null http://localhost:8080/api/status; then up=1; break; fi
      sleep 2
    done
    if [ "$up" != 1 ]; then
      echo "[$(date -Is)] autostart: dashboard never answered on :8080 after 5 min — giving up" >> "$log"
      exit 0
    fi
    echo "[$(date -Is)] autostart: dashboard is up, flipping 8080 to public..." >> "$log"
    # ~2 min of retries: a restart-in-place tears down the existing 8080 forward
    # and Codespaces re-registers it up to a minute later; until it reappears in
    # `gh ports` there is no port for `visibility` to act on. A fresh boot
    # succeeds on the first attempt and breaks out immediately.
    ok=0
    for attempt in $(seq 1 40); do
      gh codespace ports visibility 8080:public -c "$CODESPACE_NAME" >> "$log" 2>&1
      if gh codespace ports -c "$CODESPACE_NAME" 2>/dev/null | grep -qE '8080[[:space:]]+public'; then
        echo "[$(date -Is)] autostart: Mission Control (8080) is PUBLIC (attempt $attempt)" >> "$log"
        ok=1; break
      fi
      echo "[$(date -Is)] autostart: 8080 not public yet (attempt $attempt/40, forward may be registering), retrying in 3s..." >> "$log"
      sleep 3
    done
    [ "$ok" = 1 ] || echo "[$(date -Is)] autostart: gave up — 8080 still not public after 40 attempts (MC link will 404 externally)" >> "$log"
  ) &
fi
