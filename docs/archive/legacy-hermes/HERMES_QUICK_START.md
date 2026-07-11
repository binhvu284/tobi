# 🚀 HERMES SETUP - QUICK START (30 PHÚT)

> **For Thomas:** Setup một AI agent 24/7 chạy trên VPS, chat qua Telegram, dùng Claude Opus

---

## ⏱️ BƯỚC-BY-BƯỚC (30 phút total)

### PREP (5 phút)

**1. Chuẩn bị thông tin cần:**

```
□ VPS IP: ________________
□ VPS Username: ________________
□ Claude API Key: sk-ant-...________________
□ Telegram Bot Token: 123456:ABC...________________
□ Your Telegram User ID: ________________
  (Get from @userinfobot)
```

**2. SSH vào VPS:**
```bash
ssh root@YOUR_VPS_IP
# Or: ssh username@YOUR_VPS_IP
```

---

### SETUP (20 phút)

**Cách 1: AUTO SETUP (Recommended - 5 phút)**

```bash
# Download & run auto setup script
curl -o ~/setup_hermes.sh https://raw.githubusercontent.com/yourusername/hermes-setup/main/setup_hermes.sh

bash ~/setup_hermes.sh

# Follow prompts:
# 1. Paste Claude API Key
# 2. Paste Telegram Bot Token
# 3. Enter Your Telegram User ID
# 4. Wait for installation (~3 min)
# 5. Done! ✓
```

**Cách 2: MANUAL SETUP (15 phút) - nếu cần customization**

```bash
# 1. Update system (2 min)
sudo apt update && sudo apt upgrade -y

# 2. Install Hermes (3 min)
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc

# 3. Set Claude API Key (1 min)
hermes config set ANTHROPIC_API_KEY "sk-ant-xxxxx"

# 4. Select Claude Opus (1 min)
hermes model
# Choose: Anthropic → claude-3-5-opus-20241022

# 5. Enable Memory & Skills (2 min)
nano ~/.hermes/config/hermes.yaml
# Find these lines and make sure they're true:
# persistent_memory: true
# skill_generation: true
# auto_skill_save: true
# Save: Ctrl+X → Y → Enter

# 6. Setup Telegram Gateway (3 min)
hermes gateway setup
# Select: telegram
# Paste Bot Token
# Enter Your User ID
# Select: Yes for restricted access

# 7. Create systemd service (2 min)
sudo tee /etc/systemd/system/hermes.service > /dev/null << 'EOF'
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
MemoryLimit=2G
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hermes
sudo systemctl start hermes

# 8. Verify running (1 min)
sudo systemctl status hermes
# Should show: "active (running)"
```

---

### TEST (5 phút)

**1. Check service running:**
```bash
sudo systemctl status hermes
```

**2. Open Telegram → Find your bot:**
```
Search: @hermes_ai_yourname_bot
```

**3. Send test message:**
```
Message: "Hi Hermes, who are you?"
```

**4. Check logs (real-time):**
```bash
sudo journalctl -u hermes -f
```

**Expected flow:**
```
You: "Hi Hermes, who are you?"
        ↓ (5-10 seconds)
Bot: "I'm Hermes, your AI assistant. I'm running on your VPS..."
```

If bot replies → ✅ **SUCCESS!**

---

## ✅ VERIFICATION CHECKLIST

```
☐ Service running: sudo systemctl status hermes
☐ Telegram bot replies in 5-10 seconds
☐ Config set correctly: hermes config show
☐ Memory working: hermes memory
☐ Skills folder exists: ls ~/.hermes/skills/
☐ Can SSH without issues
```

---

## 🎮 FIRST TASKS TO TRY

Once bot is working, try these:

```
"What's my Telegram ID?"
→ Bot should know your user ID

"Remember: My startup is OneApp"
→ Bot stores in memory

"Help me brainstorm 5 product ideas"
→ Bot uses Claude Opus for quality responses

"What did I tell you about OneApp?"
→ Bot retrieves from memory

"Research latest AI trends"
→ Bot does web search
```

---

## 📊 COST CHECK

Run this to estimate monthly cost:
```bash
# Assuming 20-30 interactions per day:
# - Input: ~35,000 tokens/month
# - Output: ~21,000 tokens/month
# - Cost: ~$1.37/month (Opus only)

# Plus VPS: $4/month
# Total: ~$5.37/month

# Check actual usage:
# → console.anthropic.com → Usage & billing
```

---

## 🆘 QUICK TROUBLESHOOTING

**Bot not responding:**
```bash
# 1. Check service
sudo systemctl restart hermes

# 2. Check logs
sudo journalctl -u hermes -n 20

# 3. Verify API key
hermes config show | grep -i anthropic
# If empty: hermes config set ANTHROPIC_API_KEY "sk-ant-..."

# 4. Restart again
sudo systemctl restart hermes
```

**SSH disconnects:**
```bash
# Use tmux for persistent sessions
tmux new-session -d -s work
tmux send-keys -t work "sudo journalctl -u hermes -f" Enter

# Later, reconnect:
tmux attach -t work
```

**High memory usage:**
```bash
# Cleanup old data
hermes memory optimize
hermes memory archive --older-than 30

# Check size
du -sh ~/.hermes/
```

---

## 📚 NEXT STEPS (AFTER SETUP)

### Week 1: Learn Basics
- [ ] Chat with bot daily
- [ ] Try different types of requests
- [ ] Read bot's responses to memory usage
- [ ] Monitor costs (console.anthropic.com)

### Week 2: Add Skills
- [ ] Create skill for web research
- [ ] Create skill for task management
- [ ] Create skill for code help

### Week 3: Automation
- [ ] Setup daily morning briefing (cron)
- [ ] Setup weekly research digest
- [ ] Setup task reminders

### Week 4+: Optimize
- [ ] Review memory usage
- [ ] Archive old sessions
- [ ] Switch to hybrid models (Sonnet + Haiku)
- [ ] Monitor & reduce costs

---

## 🎯 KEY FILES

```
Main config:        ~/.hermes/config/hermes.yaml
User profile:       ~/.hermes/memory/USER.md
Memory log:         ~/.hermes/memory/MEMORY.md
Skills folder:      ~/.hermes/skills/
Logs:              sudo journalctl -u hermes
Backup:            ~/hermes_backup_YYYYMMDD
```

---

## 💾 BACKUP NOW (Important!)

```bash
# Create first backup
tar -czf ~/hermes_backup_initial.tar.gz ~/.hermes/

# Keep it safe
# You can restore if something breaks:
# tar -xzf ~/hermes_backup_initial.tar.gz
```

---

## 🔑 IMPORTANT SECURITY

**Keep these safe:**
```
✓ Claude API Key - Never share!
✓ Telegram Bot Token - Never share!
✓ Your User ID - Public okay, but restrict bot to only you
✓ VPS root password - Change on first login
✓ SSH keys - Keep backup copies
```

**Restrict Telegram bot (already done if using auto setup):**
```bash
# Verify only you can access bot:
hermes config show | grep TELEGRAM_ALLOWED_USERS
# Should show: your_user_id_only
```

---

## 📞 GETTING HELP

**If stuck, check:**
1. Full setup guide: `HERMES_SETUP_GUIDE_VPS_TELEGRAM.md`
2. Troubleshooting: `HERMES_TROUBLESHOOTING_GUIDE.md`
3. Cost optimization: `HERMES_COST_OPTIMIZATION.md`
4. Official docs: https://hermes-agent.nousresearch.com

---

## 🎓 WHAT YOU'LL HAVE AFTER 30 MIN

```
✅ AI Agent running 24/7 on VPS
✅ Chat via Telegram anywhere
✅ Powered by Claude Opus
✅ Persistent memory (learns over time)
✅ Auto-generates skills
✅ Can do web research
✅ Can automate tasks
✅ Cost: ~$5/month

🎉 A personal AI that never sleeps!
```

---

## 🚀 NEXT: EXPLORE FEATURES

After successful setup, explore:

```bash
# 1. Web research
"Research top 10 AI startups 2024"

# 2. Code help
"Help me debug this React component"

# 3. Writing
"Write a professional email to investors"

# 4. Brainstorming
"5 ideas for a SaaS product for Vietnamese market"

# 5. Task automation
"Remind me to check competitor prices every Monday at 9 AM"

# 6. Memory
"What did you remember about my startup OneApp?"
```

---

**Ready? Let's go! 🚀**

Next step: SSH into VPS and run the setup!

```bash
ssh root@YOUR_VPS_IP
bash ~/setup_hermes.sh  # Or manual steps above
```

**Expected time: 30 minutes to full working AI agent!**

---

## 📋 SETUP TRACKER

```
Timeline:
[ ] 0:00-0:05   - Prep (gather info)
[ ] 0:05-0:25   - Auto/Manual setup
[ ] 0:25-0:30   - Test & verify
[ ] After        - Monitor & optimize

Status: _______________
Start time: _________
Finish time: _________
Working? ☐ YES ☐ FIXING
```

