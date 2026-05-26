# 🚀 HERMES AI AGENT - SETUP COMPLETE (VPS + TELEGRAM + CLAUDE OPUS)

**Mục tiêu:** Setup Hermes chạy 24/7 trên VPS, tương tác qua Telegram, dùng Claude Opus, tối ưu chi phí

---

## 📋 PHẦN 1: CHUẨN BỊ

### 1.1 Yêu Cầu Trước Setup
- ✅ VPS Linux (Ubuntu 20.04+) - giá từ $3-5/tháng (Contabo, DigitalOcean, Linode)
- ✅ Claude API Key (có rồi)
- ✅ Telegram Bot Token (sẽ tạo ở bước 2)
- ✅ SSH access vào VPS

### 1.2 Giá Chi Phí Ước Tính
```
VPS: $3-5/tháng (tuỳ provider)
Claude Opus API: $0.50-2/tháng (tuỳ tần suất sử dụng)
Telegram Bot: FREE
─────────────────
TOTAL: $3.50-7/tháng
```

> **Tiết kiệm mẹo:** Nếu dùng local model (Ollama) thay Opus, chi phí là 0, nhưng tốc độ sẽ chậm hơn.

---

## 🔧 PHẦN 2: SETUP VPS

### 2.1 Kết nối SSH vào VPS
```bash
ssh root@YOUR_VPS_IP
# Hoặc: ssh user@YOUR_VPS_IP (nếu có username khác)
```

### 2.2 Update Hệ Thống
```bash
sudo apt update
sudo apt upgrade -y
```

### 2.3 Cài đặt Dependencies (Optional - Hermes sẽ tự cài)
```bash
sudo apt install -y curl wget git build-essential
```

---

## 📱 PHẦN 3: TẠO TELEGRAM BOT

### 3.1 Tạo Bot Token
1. Mở Telegram app
2. Tìm bot `@BotFather`
3. Gửi: `/newbot`
4. Đặt tên: `HermesAI` (tên bất kỳ)
5. Đặt username: `hermes_ai_yourname_bot` (phải unique)
6. **Copy Bot Token** - sẽ dùng sau (ví dụ: `123456:ABCxyz...`)

### 3.2 Lấy Telegram User ID
1. Tìm bot `@userinfobot`
2. Gửi `/start`
3. **Copy User ID** - cần để restrict quyền truy cập

> **Bảo mật:** Restrict bot chỉ cho user ID của bạn

---

## 🤖 PHẦN 4: INSTALL HERMES

### 4.1 SSH vào VPS và Cài Đặt (2 phút)
```bash
# Chạy installer
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Reload shell
source ~/.bashrc
# Hoặc: source ~/.zshrc (tuỳ shell)
```

### 4.2 Kiểm Tra Installation
```bash
hermes doctor
# Kết quả nên show: "Hermes Agent installed successfully"
```

---

## ⚙️ PHẦN 5: SETUP CLAUDE OPUS

### 5.1 Cấu Hình API Key
```bash
hermes config set ANTHROPIC_API_KEY "sk-ant-xxxxx..." 
# Paste API key của bạn
```

### 5.2 Chọn Model
```bash
hermes model
# Chọn: "Anthropic" 
# Model: "claude-3-5-opus-20241022"
```

Verify:
```bash
hermes config show
# Nên thấy:
# model_provider: anthropic
# model: claude-3-5-opus-20241022
```

---

## 💾 PHẦN 6: ENABLE PERSISTENT MEMORY & SKILLS

### 6.1 Chỉnh Sửa Config File
```bash
nano ~/.hermes/config/hermes.yaml
```

Tìm và chỉnh các dòng sau (Ctrl+W để search):

```yaml
# Memory Settings
persistent_memory: true      # ← Đảm bảo là true
memory_type: "sqlite"        # ← Dùng SQLite

# Skills Settings
skill_generation: true       # ← Tự tạo skills
auto_skill_save: true       # ← Tự lưu skills

# Context & Performance
max_context_tokens: 100000  # ← Tối ưu cho Opus
enable_compression: true    # ← Giảm token usage
```

**Lưu file:** Ctrl+X → Y → Enter

### 6.2 Tạo Folder cho Skills & Memory
```bash
mkdir -p ~/.hermes/skills
mkdir -p ~/.hermes/memory
mkdir -p ~/.hermes/logs

# Xem cấu trúc
ls -la ~/.hermes/
```

---

## 🌐 PHẦN 7: SETUP TELEGRAM GATEWAY

### 7.1 Cấu Hình Telegram
```bash
hermes gateway setup
```

Khi prompt hiện:
```
Select gateway type: [telegram/discord/slack/etc]
→ Chọn: telegram

Enter Telegram bot token:
→ Paste Bot Token từ @BotFather

Enable restricted access? (y/n)
→ Chọn: y

Enter allowed Telegram user IDs (comma-separated):
→ Paste User ID của bạn (vd: 123456789)
```

### 7.2 Verify Telegram Setup
```bash
hermes config show | grep -i telegram
# Nên show bot token (masked)
```

---

## 🚀 PHẦN 8: SETUP AUTO-START (24/7 MODE)

### 8.1 Cách 1: Systemd Service (Recommended - Chạy như daemon)

Tạo service file:
```bash
sudo nano /etc/systemd/system/hermes.service
```

Paste nội dung dưới:
```ini
[Unit]
Description=Hermes AI Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/root/.local/bin/hermes --daemon --gateway telegram
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Resource limits
MemoryLimit=2G
CPUQuota=80%

[Install]
WantedBy=multi-user.target
```

**Lưu file:** Ctrl+X → Y → Enter

Kích hoạt service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes
sudo systemctl start hermes

# Verify
sudo systemctl status hermes
# Nên show: "active (running)"
```

Kiểm tra logs:
```bash
sudo journalctl -u hermes -f
# -f = follow (real-time logs)
```

---

### 8.2 Cách 2: Tmux Session (Alternative - dễ debug)

Nếu muốn chạy trong tmux session:
```bash
# Cài tmux
sudo apt install -y tmux

# Tạo session
tmux new-session -d -s hermes -c /root

# Chạy Hermes trong session
tmux send-keys -t hermes "hermes --daemon --gateway telegram" Enter

# Attach to session (kiểm tra logs)
tmux attach -t hermes

# Detach (Ctrl+B rồi D)
```

---

## ✅ PHẦN 9: TEST & VERIFY

### 9.1 Test Hermes locally
```bash
# Thoát tmux nếu dùng (Ctrl+B rồi D)
# Hoặc SSH vào terminal khác

hermes
# Nên mở interactive CLI
# Gõ: "Hello Hermes"
# Nên thấy response từ Claude Opus
```

### 9.2 Test Telegram Bot
1. Mở Telegram
2. Tìm bot của bạn: `@hermes_ai_yourname_bot`
3. Gửi: `Hi`
4. Bot nên reply trong vòng 5-10 giây
5. Kiểm tra logs: `sudo journalctl -u hermes -f`

### 9.3 Troubleshoot nếu không hoạt động

**Bot không reply:**
```bash
# 1. Check service status
sudo systemctl status hermes

# 2. Check logs
sudo journalctl -u hermes -n 50

# 3. Restart service
sudo systemctl restart hermes

# 4. Test API key
hermes config show | grep -i anthropic
```

**Token hết/sai:**
```bash
hermes config set ANTHROPIC_API_KEY "sk-ant-xxxxx..."
sudo systemctl restart hermes
```

---

## 📚 PHẦN 10: BUILD SKILLS & MEMORY SYSTEM

### 10.1 Tạo Skill Đầu Tiên (Research Skill)
```bash
mkdir -p ~/.hermes/skills/research

# Tạo file skill
nano ~/.hermes/skills/research/web_research.md
```

Paste:
```markdown
# Web Research Skill

## Purpose
Tìm kiếm thông tin từ web, scrape dữ liệu, phân tích từ multiple sources.

## Tools Used
- web_search: Tìm kiếm Google
- browser_use: Truy cập trang web
- extract_data: Lấy dữ liệu structured

## Workflow
1. User yêu cầu research topic
2. Search trên web
3. Visit top 3-5 results
4. Extract & summarize findings
5. Return structured report

## Examples
- "Research latest AI trends 2024"
- "Compare 3 VPS providers"
- "Find tech jobs in Vietnam"

## Notes
- Luôn verify sources
- Tránh outdated info
- Cite references properly
```

**Lưu:** Ctrl+X → Y → Enter

### 10.2 Tạo Skill cho Task Management
```bash
nano ~/.hermes/skills/tasks/task_manager.md
```

Paste:
```markdown
# Task Manager Skill

## Purpose
Quản lý daily tasks, reminders, và todo lists.

## Tools
- file_write: Lưu tasks vào file
- cron_jobs: Schedule reminders
- memory_update: Lưu vào persistent memory

## Workflow
1. Parse task từ user message
2. Add to ~/tasks.txt
3. Set reminder nếu có deadline
4. Update memory tự động

## Command Patterns
- "Remind me to [task] at [time]"
- "Add task: [description]"
- "Show my tasks"
- "Mark done: [task_id]"

## Storage
Tasks lưu ở: ~/.hermes/tasks/daily.txt
```

### 10.3 Enable Skills
```bash
# Hermes tự detect skills từ ~/.hermes/skills/
# Verify:
hermes skills list

# Nên show:
# - research/web_research
# - tasks/task_manager
```

### 10.4 Setup Memory Files

Tạo USER Profile:
```bash
nano ~/.hermes/memory/USER.md
```

Paste:
```markdown
# User Profile

## Name
Thomas (Solo Founder)

## Role
PM + Full-stack developer for OneApp

## Preferences
- Timezone: Vietnam (UTC+7)
- Language: Vietnamese + English
- Work style: Async, detail-oriented
- Goals: Build sustainable SaaS, 24/7 automation

## Important Projects
- OneApp v3 (React + Supabase)
- Skill development for Hermes
- OneProject, OneMess ecosystem

## Contact
- Email: [your-email]
- Telegram: @yourusername
- Working hours: 9 AM - 6 PM Vietnam time

## Preferences for Agent
- Be concise, use bullet points
- Suggest optimizations
- Warn about costs/risks
- Prefer Vietnamese for clarity
```

Tạo MEMORY file:
```bash
nano ~/.hermes/memory/MEMORY.md
```

Paste:
```markdown
# Hermes Memory Log

## Skills & Knowledge
- Web scraping (Firecrawl, Tavily)
- API integration (Anthropic, custom)
- VPS management & Linux

## Learned Patterns
- User prefers step-by-step guides
- Productivity peak: Morning sessions
- Needs cost-aware recommendations

## Important Notes
- API key: ✓ Configured
- Telegram bot: ✓ Active
- Memory: ✓ Persistent SQLite
- Skills: ✓ Auto-generated

## Decisions Made
- Using Claude Opus (reliability > cost)
- VPS deployment (24/7 uptime)
- Telegram (convenience)
```

---

## ⏱️ PHẦN 11: SETUP CRON JOBS (AUTOMATION)

### 11.1 Daily Digest Example
```bash
hermes cron add \
  --schedule "0 9 * * *" \
  --prompt "Give me a summary of my tasks for today and any important reminders"
```

Verify:
```bash
hermes cron list
```

### 11.2 Weekly Research Task
```bash
hermes cron add \
  --schedule "0 8 * * 1" \
  --prompt "Research latest trends in AI, SaaS startups, and market opportunities. Create a report."
```

### 11.3 Memory Cleanup (Monthly)
```bash
hermes cron add \
  --schedule "0 2 1 * *" \
  --prompt "Analyze my memory and old sessions. Delete irrelevant old sessions older than 90 days. Keep important ones."
```

---

## 🔒 PHẦN 12: SECURITY & OPTIMIZATION

### 12.1 Enable Tirith (Security Module)
```bash
nano ~/.hermes/config/tirith.yaml
```

Default rules (nên safe):
```yaml
# Block dangerous commands
block_patterns:
  - "curl.*\\|.*sh"
  - "rm -rf /"
  - ":(){ :|: &};"
  
# Allow safe web operations
allow_patterns:
  - "curl.*-o.*pdf"
  - "wget.*-O"
```

### 12.2 Restrict File Permissions
```bash
# Chỉ cho Hermes access config
chmod 600 ~/.hermes/config/hermes.yaml
chmod 600 ~/.hermes/config/tirith.yaml

# Folder permissions
chmod 700 ~/.hermes/
```

### 12.3 Monitor API Usage
```bash
# View monthly usage (nếu dùng web dashboard)
# hoặc check bill từ Anthropic console

# Estimate: 
# - 50 chats/day = ~$1-2/bulan
# - 100 chats/day = ~$2-4/bulan
# - 500 chats/day = ~$10-15/bulan
```

---

## 📊 PHẦN 13: MONITOR & MAINTAIN

### 13.1 Daily Health Check
```bash
# SSH vào VPS
ssh root@YOUR_VPS_IP

# Check service status
sudo systemctl status hermes

# Check recent logs (last 20 lines)
sudo journalctl -u hermes -n 20

# Check memory/CPU usage
ps aux | grep hermes
```

### 13.2 Weekly Maintenance
```bash
# Cleanup old sessions
hermes memory optimize

# View memory size
du -sh ~/.hermes/memory/

# Backup memory (important!)
tar -czf ~/hermes_backup_$(date +%Y%m%d).tar.gz ~/.hermes/memory/ ~/.hermes/skills/
```

### 13.3 Backup Strategy
```bash
# Backup vào local machine (monthly)
scp -r root@YOUR_VPS_IP:~/.hermes ~/hermes_backup_`date +%Y%m%d`

# Or setup automatic backup
# (sẽ chi tiết sau)
```

---

## 🚨 PHẦN 14: TROUBLESHOOTING

### Problem 1: Bot không reply trên Telegram
```bash
# Step 1: Check bot token
hermes config show | grep telegram

# Step 2: Check logs
sudo journalctl -u hermes -f

# Step 3: Test API
hermes test --provider anthropic

# Step 4: Restart
sudo systemctl restart hermes
```

### Problem 2: High CPU/Memory Usage
```bash
# Check what's running
ps aux | grep hermes

# Reduce context size
hermes config set max_context_tokens 50000

# Restart
sudo systemctl restart hermes
```

### Problem 3: API errors / Token exhaustion
```bash
# Check balance
# Log in console.anthropic.com → Usage

# Verify key
hermes config set ANTHROPIC_API_KEY "sk-ant-..."

# Set spending limit (nếu provider hỗ trợ)
```

### Problem 4: Telegram gateway stopped
```bash
# Rebuild gateway
hermes gateway setup

# Or restart
sudo systemctl restart hermes
```

---

## 📈 PHẦN 15: OPTIMIZATION TIPS

### 15.1 Tối Ưu Chi Phí
```yaml
# Use Claude Sonnet for non-critical tasks
# Reserve Opus cho: reasoning, complex tasks

# Example config (không có built-in, nhưng có thể tạo skill)
Critical tasks: opus-4-20250514
Normal chat: sonnet-4-20250514
Simple Q&A: haiku-3-5-sonnet
```

### 15.2 Tối Ưu Latency
```bash
# Use VPS gần nhất với location bạn
# Có thể test ping:
ping vps.provider.com

# Setup local caching (tuỳ chọn)
# Hermes sẽ auto-cache frequently accessed skills
```

### 15.3 Tối Ưu Memory
```bash
# Enable compression
hermes config set enable_compression true

# Limit session history
hermes config set max_sessions 50

# Archive old sessions
hermes memory optimize --archive-older-than 30
```

---

## ✨ PHẦN 16: ADVANCED FEATURES (Optional)

### 16.1 MCP Integration (Connect with other AI agents)
```bash
# Expose Hermes as MCP server
hermes expose-mcp --port 3000

# Sau đó Claude Code / agents khác có thể gọi Hermes
```

### 16.2 Voice Mode (Chat bằng giọng nói)
```bash
# Enable voice (nếu support)
hermes config set voice_enabled true
hermes config set tts_provider elevenlabs

# Sau đó có thể gọi Telegram voice messages
```

### 16.3 Vision & Image Processing
```bash
# Enable vision
hermes config set vision_enabled true

# Now bot có thể: 
# - Analyze images
# - Extract text từ screenshots
# - Generate images (via FAL.ai nếu cấu hình)
```

---

## 🎯 QUICK REFERENCE - COMMANDS THƯỜNG DÙNG

```bash
# Management
hermes                    # Interactive CLI
hermes start             # Start daemon
hermes stop              # Stop daemon
hermes status            # Check status
hermes doctor            # Diagnose issues

# Configuration
hermes config show       # View current config
hermes config set KEY VALUE

# Skills & Memory
hermes skills list       # List all skills
hermes memory           # View memory
hermes memory search "keyword"
hermes memory optimize  # Cleanup old data

# Gateway
hermes gateway setup    # Setup messaging
hermes gateway status   # Check gateway status

# Cron Jobs
hermes cron add --schedule "0 9 * * *" --prompt "..."
hermes cron list        # List scheduled tasks
hermes cron remove ID   # Remove task

# Systemd (if using service)
sudo systemctl start hermes
sudo systemctl stop hermes
sudo systemctl restart hermes
sudo systemctl status hermes
sudo journalctl -u hermes -f
```

---

## 🎓 PHẦN 17: NEXT STEPS

Sau khi setup hoàn tất:

1. **Đợi 5 phút** - Hermes sẽ tự-generate các skills đầu tiên từ interactions
2. **Send requests** qua Telegram - Hermes sẽ học từ mỗi task
3. **Build custom skills** - Thêm skills cho domain riêng của bạn
4. **Setup cron jobs** - Automation daily/weekly tasks
5. **Monitor & optimize** - Watch logs, adjust config theo usage

---

## 📞 SUPPORT & RESOURCES

| Resource | Link |
|----------|------|
| **Official Docs** | https://hermes-agent.nousresearch.com |
| **GitHub Issues** | https://github.com/NousResearch/hermes-agent/issues |
| **Community Discord** | Nous Research Discord |

---

## 🏁 SUMMARY

```
✅ Hermes installed & running on VPS
✅ Claude Opus configured
✅ Telegram gateway active
✅ Persistent memory enabled
✅ Skills system ready
✅ Cron automation setup
✅ 24/7 uptime
✅ Est. cost: $3-7/month

Bạn giờ có một AI agent personal, học từng ngày, 
hoạt động 24/7, chỉ với chi phí tối thiểu! 🚀
```
