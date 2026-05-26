#!/bin/bash
echo "========================================"
echo "TOBI + HERMES INTEGRATION TEST"
echo "========================================"

# Test 1: Hermes installed
echo -n "T1 Hermes binary:    "
command -v hermes >/dev/null 2>&1 && echo "✅ $(hermes --version 2>/dev/null | head -1)" || echo "❌ not found"

# Test 2: Hermes identity (SOUL.md)
echo -n "T2 Hermes memory:    "
grep -qi "tobi\|thomas" ~/.hermes/SOUL.md 2>/dev/null && echo "✅ Tobi identity found" || echo "❌ no Tobi identity in SOUL.md"

# Test 3: Skill files
echo -n "T3 Skill CEO:        "
[ -f ~/.hermes/skills/tobi/skill_ceo_agent.md ] && echo "✅" || echo "❌"
echo -n "T3 Skill Research:   "
[ -f ~/.hermes/skills/tobi/skill_research_pm_learning.md ] && echo "✅" || echo "❌"

# Test 4: Hermes one-shot response (uses -z flag with free model)
echo -n "T4 Hermes response:  "
RESPONSE=$(hermes -z "In one sentence, who are you and what is your main mission?" -m "nvidia/nemotron-3-super-120b-a12b:free" --provider openrouter 2>/dev/null)
if echo "$RESPONSE" | grep -qi "tobi\|thomas\|business\|agent"; then
    echo "✅ Context-aware"
    echo "   → $RESPONSE" | head -c 120
else
    echo "⚠️  Response: $(echo "$RESPONSE" | head -c 80)"
fi

# Test 5: Tobi bot running in tmux
echo -n "T5 Tobi bot (tmux):  "
tmux ls 2>/dev/null | grep -q "tobi" && echo "✅ running" || echo "❌ not running"

# Test 6: Bot log check
echo -n "T6 Bot log:          "
if [ -f /workspaces/tobi/logs/tobi.log ]; then
    LAST=$(tail -3 /workspaces/tobi/logs/tobi.log 2>/dev/null)
    echo "✅ exists"
    echo "   Last lines: $LAST" | head -c 150
else
    echo "⚠️  no log yet"
fi

# Test 7: Python integration (hermes memory status)
echo -n "T7 Python-Hermes:    "
cd /workspaces/tobi && source venv/bin/activate && python3 -c "
import subprocess
result = subprocess.run(['hermes', 'memory', 'status'], capture_output=True, text=True)
if result.returncode == 0:
    print('✅ callable from Python')
else:
    print('⚠️  ' + result.stderr[:50])
" 2>/dev/null

echo "========================================"
