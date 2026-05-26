# 🚀 MMO AGENT SYSTEM — WEEK-BY-WEEK ROADMAP

> **Mục tiêu**: Trong 3 tuần, có hệ thống agent hoạt động 24/7, tự nghiên cứu cơ hội, propose dự án, và thực thi sau khi bạn approve.

---

## 📋 TỔNG QUAN HỆ THỐNG

```
Bạn (Investor)  ←──────── Telegram ──────────→  Agent System
                           Approve/Reject             │
                           Daily reports              │
                           Human todo alerts          │
                                                      │
              ┌───────────────────────────────────────┤
              │                                       │
         Research Engine              Project Executor
         (Weekly)                     (Every 6 hours)
         • Niche discovery            • Execute agent tasks
         • Score niches               • Update progress
         • Generate plans             • Alert human tasks
              │                            │
              └──────── Database ──────────┘
                     (SQLite local)
                           │
                     CEO Loop (Monthly)
                     • Review all projects
                     • Extract lessons
                     • Update strategy
```

**Chi phí ước tính**: $5-10/tháng (VPS $4-5 + Claude API $1-5)

---

## 📅 WEEK 1: FOUNDATION (Ngày 1-7)

### Ngày 1-2: VPS + Python Setup

**Mục tiêu**: Môi trường chạy được, test pass

```bash
# SSH vào VPS
ssh root@YOUR_VPS_IP

# Clone/upload project
git clone [your-repo] ~/mmo-agent
cd ~/mmo-agent

# Chạy setup (one-command)
bash setup.sh
```

**Checklist sau setup:**
```
☐ Python venv active
☐ .env file có ANTHROPIC_API_KEY
☐ Database initialized (agent.db)
☐ python main.py test → tất cả PASS
```

---

### Ngày 3-4: Telegram Bot

**Mục tiêu**: Bot reply được, approval flow hoạt động

**Step 1**: Tạo bot qua @BotFather → lấy token
**Step 2**: Lấy chat ID qua @userinfobot
**Step 3**: Update .env:
```bash
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
TELEGRAM_ALLOWED_USERS=xxx
```

**Step 4**: Test bot:
```bash
python main.py test
# Gửi /start cho bot → nên reply
# Gửi /status → nên show dashboard
```

**Expected output trên Telegram:**
```
🤖 MMO Agent System — Đang hoạt động!

/status — Xem tổng quan
/projects — Danh sách projects
/todos — Việc cần làm
...
```

---

### Ngày 5-7: First Research Run

**Mục tiêu**: Agent đề xuất project đầu tiên

```bash
cd ~/mmo-agent
source venv/bin/activate

# Manual research run
python main.py research
```

**Expected**: Trong 5-10 phút, nhận Telegram message với business plan + buttons Approve/Reject/Edit

**Nếu thành công:**
- Bạn nhận được business plan proposal
- Click ✅ APPROVE
- Agent bắt đầu tạo tasks

**Nếu thất bại:**
- Check `logs/system.log`
- Verify API keys trong .env
- Check internet connectivity trên VPS

---

### Cuối Week 1: Checklist

```
☐ System installed và running
☐ Telegram bot hoạt động
☐ Đã nhận ít nhất 1 business plan proposal
☐ Đã approve (hoặc reject) 1 project
☐ /todos command shows tasks
☐ Service auto-starts: sudo systemctl start mmo-agent
```

---

## 📅 WEEK 2: FIRST PROJECT (Ngày 8-14)

### Ngày 8-9: Approve & Setup

**Bạn làm (human tasks từ bot):**

Sau khi approve project, bot sẽ gửi HUMAN TODO list. Thường bao gồm:

```
📋 VIỆC BẠN CẦN LÀM

1. Tạo tài khoản Gumroad
   → gumroad.com/signup
   → Connect Stripe/PayPal (cần ID verify)
   → Reply /done 1

2. Setup domain (nếu cần)
   → Namecheap ~$10/year
   → Reply /done 2
```

**Agent làm song song (tự động):**
- Research target audience
- Analyze competitors  
- Draft product outline
- Prepare content structure

---

### Ngày 10-14: Watch First Project Run

**Cần làm của bạn**: Gần như không có, chỉ monitor

**Cách monitor:**
```bash
# Check status bất kỳ lúc nào
python main.py status

# Xem log real-time
tail -f ~/mmo-agent/logs/system.log

# Qua Telegram
/projects  → xem progress
/todos     → việc cần làm
```

**Daily Telegram reports** (8 AM tự động):
```
📅 DAILY REPORT — 15/01/2025

💰 Revenue this month: $0 (đang build)
💰 All-time: $0

🚀 Active Projects: 1
   📁 AI Prompt Pack for Designers
      Progress: 35% | Revenue: $0
      Status: Writing prompt content

🔔 2 việc đang chờ bạn → /todos
```

**Expected progress by end of Week 2:**
- Project progress: 40-60%
- Core content: created
- Human setup tasks: done
- Ready for pre-launch preparation

---

### Cuối Week 2: Checklist

```
☐ 1 project active và running
☐ Human setup tasks completed (account, domain)
☐ Agent đã produce content/product draft
☐ Daily reports coming in at 8 AM
☐ Progress >40%
```

---

## 📅 WEEK 3: LAUNCH & SECOND PROJECT (Ngày 15-21)

### Ngày 15-17: First Project Launch Prep

**Agent chuẩn bị:**
- Product listings
- Marketing copy
- SEO descriptions
- Pricing strategy

**Bạn review và approve:**
```
Bot: "Product description draft ready. Review tại /todos"

→ Bạn đọc draft
→ Reply: "OK" hoặc request changes
→ Bot: "Publishing to Gumroad..."
```

---

### Ngày 18-19: Research Cycle 2

**Tự động** (hoặc manual):
```bash
python main.py research
```

Agent sẽ:
1. Incorporate lessons từ project 1
2. Search niches với refined criteria
3. Propose 2 opportunities mới

**Bạn nhận và review**:
- Business Plan Proposal #2
- Click Approve/Reject

---

### Ngày 20-21: System Optimization

**Check costs:**
- Log vào console.anthropic.com
- Xem usage thực tế vs estimate
- Adjust `PRIMARY_MODEL` nếu cần tiết kiệm:
  ```bash
  # Trong .env
  PRIMARY_MODEL=auto  # Smart routing, tiết kiệm 40-50%
  ```

**Performance tuning:**
```bash
# Nếu muốn chạy nhanh hơn
# Trong main.py, điều chỉnh:
schedule.every(4).hours.do(...)  # 4h thay vì 6h

# Nếu muốn tiết kiệm API
tasks_per_project=2  # Giảm từ 3
```

---

### Cuối Week 3: Checklist

```
☐ Project 1: >80% progress
☐ Project 1: Listing live trên platform
☐ Project 2: Approved và running
☐ System costs within $10-30 budget
☐ CEO review scheduled (1st of next month)
☐ 24/7 service stable
```

---

## 📅 MONTH 2: SCALE & OPTIMIZE

### Đầu tháng: First CEO Review

Ngày 1 tự động, hoặc:
```bash
python main.py ceo
```

**Nhận CEO report qua Telegram:**
```
📊 MONTHLY CEO REVIEW

🟡 Portfolio Health: YELLOW

💰 Revenue this month: $0
   → Project 1 live nhưng chưa có sale
   → Recommend: Marketing push

PROJECT VERDICTS:
✅ AI Prompt Pack → CONTINUE
   Tốt về execution, cần traffic generation

🔬 Next Research Focus:
• Lower competition digital products
• Templates with built-in audience
• Tools for existing communities
```

### Điều chỉnh dựa trên CEO review:

**Nếu revenue = $0 sau tháng 1:**
- Project pivot: thay đổi pricing/positioning
- Add marketing tasks: agent viết SEO content
- Research new niche với traction hơn

**Nếu có revenue:**
- Scale: tăng budget, add more products
- Replicate: apply same approach sang niche tương tự
- Optimize: A/B test pricing, descriptions

---

## 📅 MONTH 3-6: GROWTH PATH

```
Tháng 3: 2-3 projects active simultaneously
         Revenue target: $50-200/tháng

Tháng 4: Identify best-performing project type
         Double down on what works
         Revenue target: $100-300/tháng

Tháng 5: System fully autonomous
         Bạn chỉ cần approve/reject + setup accounts
         Revenue target: $200-500/tháng

Tháng 6: Review và consider scaling
         More budget → Better models → Higher quality
         Revenue target: $300-800/tháng
```

---

## 🛠️ COMMON ISSUES & FIXES

### Issue: "Bot không reply"
```bash
sudo systemctl restart mmo-agent
sudo journalctl -u mmo-agent -n 20
```

### Issue: "API cost quá cao"
```bash
# Trong .env:
PRIMARY_MODEL=auto   # Dùng routing thông minh
# Hoặc:
PRIMARY_MODEL=claude-sonnet  # Rẻ hơn Opus 3-4x
```

### Issue: "Project stuck, không có progress"
```bash
python main.py execute  # Force chạy execution cycle
/todos                  # Check nếu đang chờ human task
```

### Issue: "Research không tìm được niche hay"
```bash
# Cung cấp Tavily API key trong .env:
TAVILY_API_KEY=tvly-xxx
# Free 1000 searches/month tại tavily.com
```

### Issue: "VPS service stopped"
```bash
sudo systemctl status mmo-agent
sudo systemctl start mmo-agent
sudo systemctl enable mmo-agent  # Auto-start on reboot
```

---

## 💡 TIPS & BEST PRACTICES

### 1. Luôn review business plan kỹ trước khi approve
- Đọc kỹ "human tasks" - bạn có thể làm không?
- Check revenue projections có realistic không
- Verify budget breakdown đủ không

### 2. Đừng approve quá nhiều project cùng lúc
- Max 2-3 active projects
- Agent cần focus để làm tốt

### 3. Setup accounts sớm ngay sau khi approve
- Gumroad, Stripe, domain → Agent bị block nếu thiếu
- Giải quyết /todos trong 48h

### 4. Trust the process trong tháng đầu
- Tháng 1: Build + launch (revenue = $0, bình thường)
- Tháng 2: Traction + iteration
- Tháng 3+: Revenue growth

### 5. Monitor costs weekly
- console.anthropic.com → Usage
- Target: <$5/tháng Claude API
- Dùng PRIMARY_MODEL=auto nếu >$8/tháng

---

## 🎯 SUCCESS METRICS

| Timeline | Milestone |
|----------|-----------|
| Week 1 | System running, bot working |
| Week 2 | First project active, >40% progress |
| Week 3 | First product live on platform |
| Month 2 | First sale/revenue |
| Month 3 | $50+/month revenue |
| Month 6 | $200+/month revenue |
| Month 12 | $500+/month revenue (target) |

---

## 📁 FILE STRUCTURE

```
~/mmo-agent/
├── main.py                 ← Entry point (chạy cái này)
├── setup.sh                ← One-command setup
├── requirements.txt
├── .env                    ← API keys (private!)
│
├── core/
│   ├── model_router.py     ← Multi-model abstraction
│   ├── database.py         ← SQLite manager
│   ├── telegram_bot.py     ← Approval bot
│   ├── research_engine.py  ← Niche research
│   ├── project_executor.py ← Task execution
│   └── ceo_loop.py         ← CEO review
│
├── hermes_skills/
│   ├── skill_ceo_agent.md
│   └── skill_research_pm_learning.md
│
└── logs/
    ├── system.log
    └── error.log

~/.mmo_agent/
└── agent.db               ← SQLite database (backup này!)
```

---

## 🔑 KEY COMMANDS QUICK REFERENCE

```bash
# Start system
sudo systemctl start mmo-agent

# Check status
python main.py status

# Force research now
python main.py research

# Force execution now
python main.py execute

# Run CEO review
python main.py ceo

# Test all connections
python main.py test

# Watch logs
tail -f ~/mmo-agent/logs/system.log

# Backup database
cp ~/.mmo_agent/agent.db ~/backup_$(date +%Y%m%d).db
```

---

*Estimated setup time: 2-3 hours (Week 1)*
*Time to first revenue: 4-8 weeks*
*Monthly involvement required: ~2-3 hours (approve plans + setup accounts)*
