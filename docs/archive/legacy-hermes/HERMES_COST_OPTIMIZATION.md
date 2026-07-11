# 💰 HERMES - COST OPTIMIZATION & USAGE TIPS

## 📊 Chi Phí Breakdown

### Current Setup (Opus only)
```
VPS: $3-5/tháng (DigitalOcean, Contabo, Linode)
Claude Opus: $0.30-3/tháng (tuỳ usage)
Telegram: FREE
Total: $3.30-8/tháng
```

### Cost Breakdown by Usage Level

| Usage | Daily Chats | Est. Monthly | Total Cost |
|-------|-------------|--------------|-----------|
| Light | 10-20 | ~100-200 | $3.50-5 |
| Medium | 50-100 | ~1500-3000 | $5-10 |
| Heavy | 200+ | ~6000+ | $10-20 |

> **Note:** Opus costs: Input $3/1M tokens, Output $15/1M tokens

---

## 🎯 STRATEGY 1: Hybrid Model Setup (Recommended)

Thay vì chỉ dùng Opus cho tất cả, dùng **multi-model strategy**:

### Cách hoạt động:
```
Simple questions (Q&A) → Haiku (cheap, fast)
Normal tasks → Sonnet (balanced)
Complex reasoning → Opus (powerful)
Web research → Sonnet (good for web)
```

### Setup Code:

Tạo skill để route requests:
```bash
nano ~/.hermes/skills/routing/model_router.md
```

```markdown
# Smart Model Router

## Purpose
Route requests đến model phù hợp để tối ưu cost.

## Rules
1. If task is simple Q&A → use haiku
2. If task is web/search → use sonnet
3. If task is complex logic → use opus
4. If task is writing → use sonnet

## Implementation
This skill works with Hermes' model selection.
Set as default routing before executing tasks.

## Examples
- "What's 2+2?" → Haiku
- "Research AI trends" → Sonnet
- "Design system architecture" → Opus
```

### Estimate Savings:
```
Monthly cost reduction: 50-70% 
From: $10/month → $3-5/month
```

---

## 🎯 STRATEGY 2: Batch Processing

Thay vì gửi requests từng cái một, batch chúng lại:

### Example - Daily Summary Batch:
```bash
# Thay vì 10 separate requests:
# ❌ "Tell me about startup A"
# ❌ "Tell me about startup B"
# ❌ "Tell me about startup C"

# ✅ Gửi 1 request batch:
hermes cron add --schedule "0 8 * * *" \
  --prompt "
Provide daily summaries for:
1. Startup A - latest news
2. Startup B - funding round updates
3. Startup C - product launches

Format as table. Be concise.
"
```

### Savings:
```
Single 3x batched = ~40% fewer API calls
(token overhead for formatting < individual request overhead)
```

---

## 🎯 STRATEGY 3: Local Model for Offline Tasks

Setup **Ollama** để chạy local model cho tasks không cần internet:

### Cài Ollama:
```bash
# On VPS
curl https://ollama.ai/install.sh | sh

# Pull a good small model
ollama pull qwen2.5-coder:7b

# Run it
OLLAMA_CONTEXT_LENGTH=32768 ollama serve &
```

### Use Local Model:
```bash
# Configure Hermes to use Ollama for certain tasks
hermes config set secondary_model_endpoint "http://localhost:11434/v1"
hermes config set secondary_model_name "qwen2.5-coder:7b"
```

### When to Use Local:
```
✅ Markdown editing
✅ Code formatting
✅ Simple text processing
✅ Offline brainstorming
✅ Memory search & retrieval

❌ Web search
❌ Complex reasoning
❌ Code generation (high stakes)
❌ Creative writing
```

### Savings:
```
With local model for 30% of tasks:
$10/month → $7/month (-30%)
```

---

## 🎯 STRATEGY 4: Memory Compression

Hermes stores everything. Optimize memory usage:

### Enable Compression:
```bash
nano ~/.hermes/config/hermes.yaml
```

Add/enable:
```yaml
# Memory optimization
enable_compression: true
max_memory_size: 500MB
context_compression_ratio: 0.7

# Session management
max_sessions_kept: 50
archive_older_than: 30  # days

# Token optimization
enable_prompt_caching: true  # Use Claude's native caching
```

### Cleanup Command:
```bash
# Run monthly
hermes memory optimize

# Archive old sessions (keeps but don't load in context)
hermes memory archive --older-than 60

# Delete very old data
hermes memory purge --older-than 180
```

### Savings:
```
Better context compression = 20-30% fewer tokens
$10/month → $7-8/month
```

---

## 🎯 STRATEGY 5: Scheduled Batched Reports

Instead of interactive chats, schedule batch reports:

### Example Setup:
```bash
# Morning briefing (9 AM)
hermes cron add --schedule "0 9 * * *" \
  --prompt "
Daily briefing for Thomas:
- 5 top AI news stories
- 3 market opportunities
- Tasks due today
- Yesterday's summary

Format: Markdown, 2-3 lines each.
Be concise.
"

# Weekly deep dive (Friday 5 PM)
hermes cron add --schedule "0 17 * * 5" \
  --prompt "
Weekly deep research report:
1. AI market trends
2. Startup funding news
3. Tech skills to learn

Cite sources. ~500 words total.
"

# Cost analysis (1st of month)
hermes cron add --schedule "0 2 1 * *" \
  --prompt "
Analyze this month's API costs.
Suggest optimizations.
"
```

### Savings:
```
Replace 30 ad-hoc chats with 3 scheduled batches:
$5/month for batches instead of $15 for ad-hoc
```

---

## 📈 FORMULA: Estimate Your Costs

```python
# Input tokens (approx)
task_tokens = 500          # Average task context
daily_tasks = 20           # Tasks per day
daily_input = task_tokens * daily_tasks
monthly_input = daily_input * 30

# Output tokens (approx)
output_per_task = 300      # Average response
monthly_output = output_per_task * daily_tasks * 30

# Cost calculation
opus_input_cost = (monthly_input / 1000000) * 3     # $3/1M input
opus_output_cost = (monthly_output / 1000000) * 15  # $15/1M output
total_opus = opus_input_cost + opus_output_cost

print(f"Est. monthly cost: ${total_opus:.2f}")
```

### Examples:
```
20 tasks/day (light): ~$1-2/month
50 tasks/day (medium): ~$3-5/month
100 tasks/day (heavy): ~$6-10/month
200+ tasks/day (very heavy): $12+/month
```

---

## 🛠️ OPTIMIZATION CHECKLIST

```
☐ Enable persistent memory
☐ Setup hybrid model routing (Opus + Sonnet + Haiku)
☐ Enable context compression
☐ Batch similar tasks together
☐ Use Ollama for offline tasks
☐ Schedule daily/weekly batch reports
☐ Monitor memory size (du -sh ~/.hermes)
☐ Archive old sessions monthly
☐ Check API usage: console.anthropic.com
☐ Set spending alerts/limits
```

---

## 📊 REAL-WORLD EXAMPLE: Thomas's Startup

### Scenario:
Thomas uses Hermes for:
- Daily morning briefing (1 request)
- Web research (2 requests × 3/week)
- Code help (2 requests/day)
- Market analysis (1 request/week)
- Memory cleanup + searches (5 searches/day)

### Calculation:
```
Daily AI tasks: 2-3 requests
Daily searches: 5 (very cheap, local memory)
Monthly requests: ~70 tasks

Est. token usage:
- Input: 70 × 500 = 35,000 tokens
- Output: 70 × 300 = 21,000 tokens

With Opus only: $1.05 (input) + $0.32 (output) = ~$1.37/month
With hybrid (70% Sonnet, 30% Opus): ~$0.80/month

Plus VPS: $4/month
Total: $4.80/month
```

---

## 💡 BONUS: Free Alternatives for Non-Critical Tasks

If you need to cut costs further:

### Free/Cheap Options:
```
Web research → Use Tavily API (cheaper or free tier)
Code generation → Use Ollama locally
Writing/brainstorm → Use Haiku (cheapest Claude)
Memory search → All local (free)
Task management → Local file system (free)
```

### Setup Example - Use Haiku for Simple Tasks:
```bash
# Create skill that auto-uses Haiku for simple tasks
nano ~/.hermes/skills/optimization/use_haiku_for_simple.md
```

---

## 📱 MONITORING & ALERTS

### Weekly Cost Check:
```bash
# Create a cron job to check costs
hermes cron add --schedule "0 10 * * 1" \
  --prompt "Check my Anthropic API usage from console.anthropic.com. 
Are costs within expected range? 
Suggest optimizations if needed."
```

### Set Spending Limit:
```bash
# In Anthropic console, set:
# - Monthly budget limit: $10
# - Alerts: notify at 50%, 75%, 90%
```

---

## 🎯 RECOMMENDED FINAL CONFIG

For your use case (startup PM + web research + automation):

```yaml
# ~/.hermes/config/hermes.yaml (optimization section)

cost_optimization:
  enable_hybrid_models: true
  
  model_routing:
    simple_questions: "haiku"
    normal_tasks: "sonnet"
    complex_reasoning: "opus"
    web_research: "sonnet"
    
  token_optimization:
    enable_compression: true
    enable_caching: true
    max_context: 80000  # Instead of 100000
    
  memory_management:
    auto_cleanup: true
    archive_older_than_days: 30
    max_sessions: 50
    compression_ratio: 0.8

budget:
  monthly_limit: 10  # USD
  alert_thresholds: [50, 75, 90]  # percent
```

---

## 🚀 FINAL RESULT

With these optimizations:
```
Before: $10-15/month
After:  $4-6/month

Savings: 50-60%
Same capabilities ✓
24/7 uptime ✓
Local data ✓
```

Bạn sẽ có một AI agent tối ưu chi phí mà vẫn mạnh mẽ! 💪
