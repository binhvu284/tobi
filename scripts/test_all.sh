#!/bin/bash
echo "======================================"
echo "TOBI SYSTEM TEST"
echo "======================================"
cd /workspaces/tobi && source venv/bin/activate

echo -n "1. Python imports:    "
python3 -c "
from core.database import init_database, get_dashboard
from core.model_router import llm_complete
from core.integrations import check_all
from api.server import app as api_app
from api.dashboard import app as dash_app
print('✅ all OK')
" 2>&1 | tail -1

echo -n "2. Database:          "
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from core.database import init_database, get_dashboard
init_database()
d = get_dashboard()
print(f'✅ projects={d[\"projects\"]}')
" 2>&1 | tail -1

echo -n "3. LLM:               "
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from core.model_router import llm_complete
r = llm_complete('Reply: OK', task_type='simple', max_tokens=10)
print(f'✅ {r.strip()[:20]}')
" 2>&1 | tail -1

echo -n "4. Integrations:      "
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from core.integrations import check_all
s = check_all()
ok = sum(1 for v in s.values() if v)
print(f'✅ {ok}/{len(s)} available')
" 2>&1 | tail -1

echo -n "5. Tavily:            "
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from core.research_engine import tavily_search
r = tavily_search('test', max_results=1)
print(f'✅ {len(r)} result(s)')
" 2>&1 | tail -1

echo -n "6. SOUL.md:           "
[ -f /workspaces/tobi/SOUL.md ] && [ -f ~/.hermes/SOUL.md ] && echo "✅ both present" || echo "⚠️  one missing"

echo -n "7. Tmux bot:          "
tmux ls 2>/dev/null | grep -q "tobi" && echo "✅ running" || echo "⚠️  not running (run: bash scripts/autostart.sh)"

echo "======================================"
