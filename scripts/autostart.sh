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
# default, which 404s for anyone not signed in to this Codespace. Wait for the
# dashboard to bind, then flip 8080 to public. Runs in background; needs gh +
# CODESPACE_NAME (both present in Codespaces).
if [ -n "$CODESPACE_NAME" ]; then
  (
    for _ in $(seq 1 30); do
      if curl -sf -o /dev/null http://localhost:8080/api/status; then
        gh codespace ports visibility 8080:public -c "$CODESPACE_NAME" >/dev/null 2>&1 \
          && echo "🌐 Mission Control (8080) set to public"
        break
      fi
      sleep 2
    done
  ) &
fi
