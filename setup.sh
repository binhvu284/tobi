#!/bin/bash
# ================================================
# MMO AGENT SYSTEM - ONE-COMMAND SETUP
# ================================================
# Chạy trên VPS (Ubuntu 20.04+):
#   bash setup.sh
# ================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'
YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓ $1${NC}"; }
err()  { echo -e "${RED}✗ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
info() { echo -e "${BLUE}ℹ $1${NC}"; }

echo -e "${BLUE}"
echo "╔══════════════════════════════════════╗"
echo "║     MMO AGENT SYSTEM - SETUP         ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── STEP 1: System update ─────────────────────
echo -e "\n${BLUE}STEP 1: Update system${NC}"
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv git curl -qq
ok "System updated"

# ── STEP 2: Project directory ─────────────────
echo -e "\n${BLUE}STEP 2: Setup project${NC}"
mkdir -p ~/mmo-agent
cd ~/mmo-agent
mkdir -p core hermes_skills config logs ~/.mmo_agent
ok "Directories created"

# ── STEP 3: Python venv ───────────────────────
echo -e "\n${BLUE}STEP 3: Python environment${NC}"
python3 -m venv venv
source venv/bin/activate
ok "Virtual env created"

# ── STEP 4: Install dependencies ──────────────
echo -e "\n${BLUE}STEP 4: Install Python packages${NC}"
pip install -q --upgrade pip
pip install -q \
  anthropic \
  openai \
  google-generativeai \
  python-telegram-bot \
  tavily-python \
  requests \
  schedule \
  python-dotenv \
  aiohttp
ok "Python packages installed"

# ── STEP 5: Env file ─────────────────────────
echo -e "\n${BLUE}STEP 5: Configure environment${NC}"

if [ ! -f ".env" ]; then
  echo ""
  echo -e "${YELLOW}Nhập API Keys (bắt buộc):${NC}"

  read -sp "Claude API Key (sk-ant-...): " ANTHROPIC_KEY; echo
  read -p  "Telegram Bot Token: "          TG_TOKEN
  read -p  "Telegram Chat ID: "            TG_CHAT
  read -p  "Tavily API Key (Enter để skip): " TAVILY_KEY; echo

  cat > .env << EOF
# ── LLM Configuration ─────────────────────
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}

# PRIMARY_MODEL options:
#   claude (default) | claude-sonnet | claude-haiku
#   gpt | gemini | ollama | auto
PRIMARY_MODEL=claude

# Optional: Other models
OPENAI_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8080/api/integrations/google/oauth/callback

# ── Telegram ─────────────────────────────
TELEGRAM_BOT_TOKEN=${TG_TOKEN}
TELEGRAM_CHAT_ID=${TG_CHAT}
TELEGRAM_ALLOWED_USERS=${TG_CHAT}

# ── Search API ───────────────────────────
TAVILY_API_KEY=${TAVILY_KEY}

# ── System ───────────────────────────────
DB_PATH=~/.mmo_agent/agent.db
LOG_LEVEL=INFO
EOF
  ok ".env created"
else
  warn ".env already exists, skipping"
fi

# ── STEP 6: Hermes Agent ──────────────────────
echo -e "\n${BLUE}STEP 6: Install Hermes Agent${NC}"
if ! command -v hermes &> /dev/null; then
  info "Installing Hermes..."
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash > /dev/null 2>&1
  source ~/.bashrc 2>/dev/null || true
  ok "Hermes installed"
else
  ok "Hermes already installed"
fi

# ── STEP 7: Copy Hermes skills ────────────────
echo -e "\n${BLUE}STEP 7: Setup Hermes skills${NC}"
mkdir -p ~/.hermes/skills/mmo-agent
cp hermes_skills/*.md ~/.hermes/skills/mmo-agent/ 2>/dev/null && ok "Skills copied" || warn "Skills not found (copy manually)"

# ── STEP 8: Init database ─────────────────────
echo -e "\n${BLUE}STEP 8: Initialize database${NC}"
source .env
python3 -c "
import sys, os
sys.path.insert(0, '.')
from core.database import init_database
init_database()
print('Database ready')
" && ok "Database initialized"

# ── STEP 9: Systemd service ───────────────────
echo -e "\n${BLUE}STEP 9: Setup auto-start service${NC}"
CURRENT_DIR=$(pwd)
PYTHON_PATH="$CURRENT_DIR/venv/bin/python3"

sudo tee /etc/systemd/system/mmo-agent.service > /dev/null << EOF
[Unit]
Description=MMO Agent System
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$CURRENT_DIR
EnvironmentFile=$CURRENT_DIR/.env
ExecStart=$PYTHON_PATH main.py start
Restart=always
RestartSec=30
StandardOutput=append:$CURRENT_DIR/logs/system.log
StandardError=append:$CURRENT_DIR/logs/error.log
MemoryLimit=1G
CPUQuota=70%

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mmo-agent
ok "Systemd service configured"

# ── STEP 10: Test ─────────────────────────────
echo -e "\n${BLUE}STEP 10: Test connections${NC}"
source venv/bin/activate
source .env
python3 main.py test 2>/dev/null || warn "Some tests failed - check .env"

# ── DONE ─────────────────────────────────────
echo -e "\n${GREEN}"
echo "╔══════════════════════════════════════╗"
echo "║         SETUP COMPLETE! 🚀           ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

cat << 'EOF'
NEXT STEPS:

1. Start system:
   sudo systemctl start mmo-agent
   sudo systemctl status mmo-agent

2. Watch logs (real-time):
   tail -f ~/mmo-agent/logs/system.log

3. Test Telegram bot:
   Send /start to your bot

4. Manual research (first run):
   cd ~/mmo-agent && source venv/bin/activate
   python main.py research

5. Check status anytime:
   python main.py status

Estimated monthly cost: $5-10 (VPS + Claude API)
EOF
