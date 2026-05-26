# Research Agent Skill
# Skill for Hermes Agent - MMO Agent System

## Purpose
Tự động research niches, analyze market opportunities, và generate actionable business plans.
Chạy weekly. Output: proposals gửi investor để approve.

## When to Activate
- Every Sunday 8 PM (scheduled)
- Khi investor yêu cầu: "research niches", "find opportunities"
- Khi CEO review chỉ ra cần pivot sang niche mới

## Research Process

### Step 1: Gather Raw Data
```bash
python core/research_engine.py
```
Tự động search:
- Trending digital products (Gumroad bestsellers, ProductHunt launches)
- Underserved markets (Reddit pain points, community discussions)
- AI-native opportunities (tools AI can build autonomously)
- Low competition, high demand niches

### Step 2: Scoring Criteria
Khi evaluate niche, score 1-10 theo:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| demand_score | 25% | Có đủ người muốn mua không? |
| competition_score | 25% | Đối thủ ít = điểm cao |
| agent_doable | 30% | AI agent tự làm >80% được không? |
| monetization_speed | 15% | Revenue trong <60 ngày? |
| budget_fit | 10% | Phù hợp budget $10-30/month? |

**Ideal niche**: final_score ≥ 7.5

### Step 3: Business Plan Template
Mỗi business plan phải có:
- Executive summary (2-3 câu)
- Revenue model rõ ràng
- Conservative revenue projections
- Week-by-week 90-day plan
- **Tasks agent làm** vs **Tasks cần human**
- Budget breakdown
- Top 3 risks + mitigation

### Step 4: Notification
Sau khi generate plan:
```python
# Gửi Telegram với inline buttons
await send_project_proposal(app, project_id, business_plan)
```

## Project Types Priority (Learned from Strategy)

### ✅ Ưu tiên cao (agent-doable 85-95%)
1. **Prompt Packs** - Research + write + package prompts → Gumroad
2. **Digital Templates** - Notion, Figma, Canva templates
3. **Mini Guides/Ebooks** - Specific problem solving guides
4. **Curated Resource Packs** - Toolkits, checklists, SOP collections
5. **Simple Utility Scripts** - Python/JS tools for specific workflows

### ⚠️ Secondary (agent-doable 70-80%)
6. **Affiliate Niche Sites** - SEO takes 3-6 months, delayed revenue
7. **Newsletter Curation** - Good long-term, slow to monetize
8. **API Wrapper Tools** - Requires coding + deployment

### ❌ Tránh (không phù hợp)
- Social media dependent products (needs viral content)
- Physical goods (fulfillment needs human)
- Service-based (needs ongoing human involvement)
- Platform-specific (risk of ban/policy changes)

## Research Sources (use with Tavily API)
```
"best selling digital products gumroad 2025"
"trending notion templates creators 2025"
"AI prompt packs high demand"
"profitable micro niche affiliate 2025"
"underserved market digital products"
"solo founder online business ideas"
```

## Quality Check Before Proposing
Trước khi gửi proposal, verify:
- [ ] Revenue model cụ thể (không chỉ "sell products")
- [ ] Week 1 tasks có thể bắt đầu ngay
- [ ] Human tasks tối thiểu (chỉ những gì thực sự cần)
- [ ] Risk assessment thực tế (không optimistic quá)
- [ ] Budget estimate đã bao gồm hidden costs

---
---

# Project Manager Skill
# Skill for Hermes Agent - MMO Agent System

## Purpose
Manage project execution: track progress, coordinate tasks, report to investor.

## When to Activate
- Sau khi project được approved
- Mỗi 6 giờ (execution cycle)
- Khi investor hỏi "/status" hoặc "/projects"

## Execution Cycle (Every 6 Hours)

### Run:
```bash
python core/project_executor.py
```

### Per-Project Process:
1. Load active projects từ DB
2. Get next agent task (highest priority, lowest week_num)
3. Execute task với appropriate LLM
4. Save output → complete_task()
5. Recalculate progress %
6. Check for human todos → alert if new ones
7. Generate progress notes

### Task Classification
Dựa trên task title/description, route đến executor phù hợp:

| Keywords | Executor | Model Used |
|----------|----------|-----------|
| research, analyze, find | Research | claude-opus |
| write, create content, draft | Writing | claude-sonnet |
| plan, strategy, roadmap | Planning | claude-opus |
| code, script, build | Coding | claude-sonnet |
| (other) | Generic | claude-sonnet |

## Progress Tracking

### Progress = (done_tasks / total_tasks) * 100

### Status Updates
Sau mỗi execution cycle, cập nhật project notes:
```
Progress: X%
Tasks done this session: N
Remaining agent tasks: N
Pending human tasks: N
Next task: [title]
```

## Daily Report Format (gửi Telegram)
```
📅 DAILY REPORT — DD/MM/YYYY

💰 Revenue this month: $X
💰 All-time: $X

🚀 Active Projects: N
[Per project]:
  📁 [Name] ([type])
     Progress: X% | Revenue: $X
     [status note]

🔔 X việc đang chờ bạn → /todos
```

## Human Task Management
Khi task có `task_type='human'`:
1. KHÔNG execute bằng agent
2. Alert Telegram ngay: `/todos`
3. Format rõ ràng: What → Why → How → Expected outcome
4. Đợi user confirm via `/done <task_id>`

### Good Human Task Format:
```
📋 VIỆC CẦN BẠN LÀM

Project: [Name]
Task: Create Gumroad account

Tại sao cần: Để publish và bán digital products
Cách làm:
  1. Vào gumroad.com/signup
  2. Verify email
  3. Connect Stripe/PayPal
  4. Reply /done 15 khi xong

Thời gian: ~10 phút
```

## Execution Limits (Để tránh overspend API)
- Max 3 tasks per project per execution cycle
- Max 2 API calls per task
- Daily limit: 20 task executions total
- Skip tasks nếu API errors >3 lần liên tiếp

## Project Health Indicators
Sau mỗi 2 tuần, check:
- Progress < 30% → Flag: Stuck, investigate
- No revenue after 6 weeks → Flag: Monetization issue
- >5 human tasks pending → Flag: Bottleneck, simplify

---
---

# Learning Engine Skill
# Skill for Hermes Agent - MMO Agent System

## Purpose
Continuously extract lessons, update memory, và improve agent performance over time.
"Sáng mai giỏi hơn hôm nay."

## When to Activate
- Sau khi complete task (micro-learning)
- Sau khi complete project (project-level learning)
- Monthly CEO review (strategic learning)
- Khi gặp unexpected error/result

## Lesson Capture Framework

### After Each Task
Khi task output có result unexpected (better/worse than expected):
```python
add_lesson(
    content="[What happened] → [Why it happened] → [What to do differently]",
    title="[Short memorable title]",
    lesson_type="insight",
    impact_score=5,
    project_id=project_id
)
```

### After Project Completion

**If Success (revenue > budget):**
```
Title: "SUCCESS: [Project type] in [Niche]"
Type: success
Content:
  - What specifically worked
  - Which tasks were most valuable
  - What would I do more of
  - Revenue model effectiveness
Impact: 7-9
```

**If Failure (shutdown without revenue):**
```
Title: "FAILURE: [Project type] - [Root cause]"
Type: failure
Content:
  - Actual root cause (not surface reason)
  - Early warning signs ignored
  - What to avoid next time
  - What could have pivoted to
Impact: 8-10 (failures are more valuable)
```

### Memory Files to Maintain

#### MEMORY.md (Hermes built-in)
Luôn cập nhật:
- Current portfolio status
- Active project IDs
- Revenue totals
- API key status
- Last research date

#### Strategy evolution (via database)
Lưu mỗi updated strategy với version number.
So sánh strategy v1 vs current để thấy học được gì.

## Pattern Recognition

### Good Patterns to Detect:
- "Prompt packs in [X] niche always sell faster than ebooks"
- "Week 2 tasks always take 2x longer than estimated"
- "Agent writing quality degrades after 3 hours runtime"

### Anti-Patterns to Flag:
- Promising niche, no revenue after 8 weeks → Not agent-doable
- Complex multi-step task → Break down more
- Budget exceeded by >30% → Plan was wrong

## Memory Search Before Acting
Trước khi bắt đầu task mới, luôn check:
```bash
hermes memory search "[niche name]"
hermes memory search "[project type]"
hermes memory search "[task type]"
```
Dùng past experiences để make better decisions.

## Strategy Self-Improvement Loop

Monthly reflection questions:
1. "Nếu tôi bắt đầu lại từ đầu, tôi sẽ làm gì khác?"
2. "Loại task nào agent làm tốt nhất? Tệ nhất?"
3. "Market đang thay đổi như thế nào?"
4. "Budget allocation có optimal không?"

Write answers vào CEO review → Update strategy.

## Knowledge Categories to Build
Theo thời gian, accumulate knowledge về:
- **Markets**: Niche demand patterns, seasonality
- **Platforms**: Gumroad, LemonSqueezy best practices
- **Content**: What converts, what doesn't
- **Technical**: Which tools work best for which tasks
- **Economics**: Real cost per task, revenue per project type

## Long-term Goal
Sau 6 tháng, agent nên:
- Có library >50 lessons
- Strategy được update ≥5 lần
- Biết chính xác niche nào agent làm tốt nhất
- Có template cho mỗi project type từ experience thực
