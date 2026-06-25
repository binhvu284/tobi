"""
CEO LOOP - MMO Agent System
==============================
Vòng lặp tư duy CEO: review projects, rút kinh nghiệm, cập nhật strategy.
Chạy monthly (hoặc khi triggered thủ công).

Vai trò:
  • Đánh giá hiệu quả từng project (ROI, tốc độ tăng trưởng)
  • Identify patterns từ successes & failures
  • Cập nhật strategy cho các project tiếp theo
  • Recommend: continue / scale / pause / shutdown
  • Gửi executive summary cho investor (bạn)
"""

import os
import json
from datetime import datetime
from typing import Optional

from core.model_router import llm_complete
from core.database import (
    get_all_projects, get_revenue_summary, get_all_lessons,
    get_latest_strategy, save_strategy, add_lesson, save_report,
    get_dashboard, get_connection,
)


# ─────────────────────────────────────────
# Data Collectors
# ─────────────────────────────────────────

def collect_project_performance() -> list[dict]:
    """Thu thập performance data của tất cả projects."""
    conn = get_connection()

    rows = conn.execute("""
        SELECT
            p.id, p.name, p.type, p.niche, p.status,
            p.progress_pct, p.revenue_total, p.monthly_budget,
            p.created_at, p.approved_at,
            COUNT(DISTINCT t.id) as total_tasks,
            SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as done_tasks,
            SUM(CASE WHEN t.task_type='human' AND t.status='pending' THEN 1 ELSE 0 END) as pending_human
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        WHERE p.status NOT IN ('pending')
        GROUP BY p.id
        ORDER BY p.revenue_total DESC
    """).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def calculate_roi(project: dict) -> dict:
    """Tính ROI và các metrics hiệu quả."""
    revenue = project.get("revenue_total") or 0
    budget = project.get("monthly_budget") or 1
    progress = project.get("progress_pct") or 0

    # Estimate months running
    created_at = project.get("created_at", "")
    months_running = 1
    if created_at:
        try:
            from datetime import datetime
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            delta = datetime.now() - created.replace(tzinfo=None)
            months_running = max(1, delta.days // 30)
        except Exception:
            months_running = 1

    total_cost = budget * months_running
    roi_pct = ((revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0
    monthly_revenue = revenue / months_running if months_running > 0 else 0

    return {
        "revenue": revenue,
        "total_cost": round(total_cost, 2),
        "roi_pct": round(roi_pct, 1),
        "months_running": months_running,
        "monthly_revenue_avg": round(monthly_revenue, 2),
        "progress_pct": progress,
    }


# ─────────────────────────────────────────
# CEO Analysis Prompt
# ─────────────────────────────────────────

CEO_ANALYSIS_PROMPT = """
Bạn là một CEO có kinh nghiệm, chuyên xây dựng và scale các digital businesses.
Hãy review toàn bộ portfolio và đưa ra đánh giá chiến lược.

## PORTFOLIO OVERVIEW:
{portfolio_data}

## REVENUE SUMMARY:
{revenue_summary}

## LESSONS LEARNED SO FAR:
{lessons}

## CURRENT STRATEGY:
{current_strategy}

## YÊU CẦU PHÂN TÍCH:

1. **Performance Review**: Đánh giá từng project - đang tốt hay không?
2. **Pattern Recognition**: Nhận ra patterns trong những gì work/không work
3. **Strategic Recommendations**: Mỗi project nên: Continue | Scale | Pivot | Shutdown?
4. **New Strategy**: Cập nhật strategy dựa trên learnings
5. **Next Research Focus**: Chỉ ra 3-5 loại niches nên research tiếp theo

## OUTPUT FORMAT (JSON only):
{
  "executive_summary": "Tổng quan tình hình business trong 1-2 đoạn",
  
  "project_reviews": [
    {
      "project_id": 1,
      "project_name": "...",
      "verdict": "scale | continue | pivot | shutdown",
      "reasoning": "Lý do cụ thể",
      "recommended_actions": ["action 1", "action 2"]
    }
  ],
  
  "key_learnings": [
    {
      "type": "success | failure | insight",
      "title": "Tiêu đề ngắn",
      "content": "Nội dung bài học",
      "impact_score": 8
    }
  ],
  
  "updated_strategy": "Viết strategy mới đầy đủ (500-800 words). Bao gồm: focus areas, project types ưu tiên, types nên tránh, budget allocation, timeline expectations.",
  
  "next_research_focus": [
    "Niche category 1 - lý do",
    "Niche category 2 - lý do",
    "Niche category 3 - lý do"
  ],
  
  "kpi_summary": {
    "total_revenue": 0,
    "monthly_revenue": 0,
    "best_performing_type": "",
    "worst_performing_type": "",
    "portfolio_health": "green | yellow | red"
  },
  
  "investor_message": "Tin nhắn ngắn cho investor - bạn đang làm như thế nào, next steps là gì"
}
"""


# ─────────────────────────────────────────
# CEO Review
# ─────────────────────────────────────────

def run_ceo_review() -> dict:
    """
    Chạy full CEO review cycle.
    Returns analysis dict + saves to DB.
    """
    print(f"\n{'='*50}")
    print(f"🎯 CEO REVIEW — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # Collect data
    projects = collect_project_performance()
    revenue = get_revenue_summary()
    lessons = get_all_lessons()
    current_strategy = get_latest_strategy() or "Chưa có strategy được thiết lập."

    if not projects:
        print("ℹ️  No projects to review yet.")
        return {"status": "no_projects"}

    # Prepare portfolio data
    portfolio = []
    for p in projects:
        roi = calculate_roi(p)
        portfolio.append({**p, **roi})

    # Generate CEO analysis
    print("🧠 Running CEO analysis with AI...")

    prompt = CEO_ANALYSIS_PROMPT.format(
        portfolio_data=json.dumps(portfolio, ensure_ascii=False, indent=2),
        revenue_summary=json.dumps(revenue, ensure_ascii=False, indent=2),
        lessons=json.dumps([
            {"type": l["lesson_type"], "title": l.get("title", ""), "content": l["content"][:300]}
            for l in lessons[:15]
        ], ensure_ascii=False, indent=2),
        current_strategy=current_strategy[:1500],
    )

    # Memory-first (Brain v2): weigh portfolio decisions against the owner's strategic
    # priorities, values, and risk appetite.
    try:
        from core import brain
        _owner = brain.owner_context("strategic priorities, values, risk appetite, long-term goals")
    except Exception:
        _owner = ""
    raw_output = llm_complete(prompt, task_type="ceo_review", system=_owner or None, max_tokens=4000)

    # Parse response
    try:
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        analysis = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"⚠️  CEO analysis parse error. Using raw output.")
        analysis = {
            "executive_summary": raw_output[:500],
            "investor_message": "CEO review complete. Check full report for details.",
            "raw": raw_output,
        }

    # Save updated strategy
    if analysis.get("updated_strategy"):
        save_strategy(
            content=analysis["updated_strategy"],
            model_used=os.getenv("PRIMARY_MODEL", "claude"),
        )
        print("✅ Strategy updated")

    # Save new lessons
    for lesson in analysis.get("key_learnings", []):
        add_lesson(
            content=lesson.get("content", ""),
            title=lesson.get("title", ""),
            lesson_type=lesson.get("type", "insight"),
            impact_score=lesson.get("impact_score", 5),
        )
    print(f"✅ {len(analysis.get('key_learnings', []))} new lessons saved")

    # Save CEO report
    report_content = format_ceo_report(analysis, portfolio, revenue)
    save_report(report_content, "monthly")
    print("✅ CEO report saved")

    return analysis


# ─────────────────────────────────────────
# Report Formatters
# ─────────────────────────────────────────

def format_ceo_report(analysis: dict, portfolio: list, revenue: dict) -> str:
    """Full text CEO report cho archiving."""
    kpi = analysis.get("kpi_summary", {})
    reviews = analysis.get("project_reviews", [])

    lines = [
        f"# 📊 CEO MONTHLY REPORT — {datetime.now().strftime('%B %Y')}",
        "",
        "## Executive Summary",
        analysis.get("executive_summary", "N/A"),
        "",
        "## KPI Dashboard",
        f"- Total Revenue: ${revenue.get('total_all_time', 0):.2f}",
        f"- This Month: ${revenue.get('this_month', 0):.2f}",
        f"- Portfolio Health: {kpi.get('portfolio_health', 'N/A')}",
        f"- Best Type: {kpi.get('best_performing_type', 'N/A')}",
        "",
        "## Project Reviews",
    ]

    VERDICT_EMOJI = {
        "scale": "🚀", "continue": "✅",
        "pivot": "🔄", "shutdown": "🛑",
    }
    for r in reviews:
        emoji = VERDICT_EMOJI.get(r.get("verdict", ""), "❓")
        lines.extend([
            f"\n### {emoji} #{r.get('project_id')} {r.get('project_name')}",
            f"**Verdict:** {r.get('verdict', 'N/A').upper()}",
            f"**Reasoning:** {r.get('reasoning', 'N/A')}",
            f"**Actions:** {', '.join(r.get('recommended_actions', []))}",
        ])

    lines.extend([
        "",
        "## Updated Strategy",
        analysis.get("updated_strategy", "No strategy update"),
        "",
        "## Next Research Focus",
        *[f"- {focus}" for focus in analysis.get("next_research_focus", [])],
        "",
        f"_Generated: {datetime.now().isoformat()}_",
    ])

    return "\n".join(lines)


def format_ceo_telegram_summary(analysis: dict) -> str:
    """Short Telegram-friendly summary của CEO review."""
    kpi = analysis.get("kpi_summary", {})
    reviews = analysis.get("project_reviews", [])

    HEALTH_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    VERDICT_EMOJI = {"scale": "🚀", "continue": "✅", "pivot": "🔄", "shutdown": "🛑"}

    health = kpi.get("portfolio_health", "yellow")
    emoji = HEALTH_EMOJI.get(health, "🟡")

    project_lines = ""
    for r in reviews:
        v_emoji = VERDICT_EMOJI.get(r.get("verdict", ""), "❓")
        project_lines += f"\n{v_emoji} *{r.get('project_name', 'Unknown')}* → {r.get('verdict', '?').upper()}"
        project_lines += f"\n   _{r.get('reasoning', '')[:100]}_"

    next_focus = analysis.get("next_research_focus", [])
    focus_lines = "\n".join(f"   • {f[:80]}" for f in next_focus[:3])

    return (
        f"📊 *MONTHLY CEO REVIEW*\n"
        f"{'─' * 32}\n\n"
        f"{emoji} *Portfolio Health:* {health.upper()}\n\n"
        f"💰 *Revenue this month:* ${kpi.get('monthly_revenue', 0):.2f}\n"
        f"💰 *All-time:* ${kpi.get('total_revenue', 0):.2f}\n\n"
        f"🎯 *Project Verdicts:*{project_lines}\n\n"
        f"🔬 *Next Research Focus:*\n{focus_lines}\n\n"
        f"💬 *From your CEO agent:*\n_{analysis.get('investor_message', 'Review complete.')}_"
    )


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────

if __name__ == "__main__":
    from core.database import init_database
    init_database()
    analysis = run_ceo_review()
    print("\n📋 CEO Review complete:")
    print(json.dumps(
        {k: v for k, v in analysis.items() if k not in ("updated_strategy", "raw")},
        ensure_ascii=False, indent=2
    ))
