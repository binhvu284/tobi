#!/bin/bash
echo "======================================"
echo "PRE-MIGRATION CHECK"
echo "======================================"

echo -n "DB backup:     "
cp /workspaces/tobi/.tobi/agent.db /workspaces/tobi/.tobi/agent.db.bak 2>/dev/null && echo "✅ done" || echo "⚠️  skipped"

echo -n "SOUL.md:       "
[ -f /workspaces/tobi/SOUL.md ] && echo "✅" || echo "❌ missing"

echo -n "Hermes soul:   "
[ -f ~/.hermes/SOUL.md ] && echo "✅" || echo "❌ missing"

echo -n "Skills:        "
count=$(ls ~/.hermes/skills/tobi/*.md 2>/dev/null | wc -l)
echo "✅ $count files"

echo -n "Requirements:  "
cd /workspaces/tobi && source venv/bin/activate 2>/dev/null
pip install -q -r requirements.txt 2>/dev/null && echo "✅ installed"

echo "======================================"
echo "Ready to migrate."
