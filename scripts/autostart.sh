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
