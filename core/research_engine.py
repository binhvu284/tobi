"""
RESEARCH ENGINE - MMO Agent System
=====================================
Tự động research niches, score tiềm năng, generate business plans

Flow (chạy weekly):
  1. Search web cho trending niches (Tavily API)
  2. Score từng niche theo công thức
  3. Chọn top 3 niches
  4. Generate business plan chi tiết cho mỗi niche
  5. Lưu vào DB → Notify Telegram để bạn approve

Env vars:
  TAVILY_API_KEY=xxx    (free 1000 searches/month tại tavily.com)
  PRIMARY_MODEL=claude  (model để generate business plans)
"""

import os
import json
import time
from datetime import datetime
from typing import Optional

from core.model_router import llm_complete
from core.database import (
    create_project, save_report, get_all_projects, get_all_lessons,
    get_latest_strategy,
)


# ─────────────────────────────────────────
# Web Search (Tavily)
# ─────────────────────────────────────────

def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Search web via Tavily API. Returns list of {title, url, content}."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("⚠️  TAVILY_API_KEY không có. Dùng mock data.")
        return _mock_search_results(query)

    try:
        import requests
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": True,
            },
            timeout=30,
        )
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        print(f"⚠️  Tavily error: {e}")
        return _mock_search_results(query)


def _mock_search_results(query: str) -> list[dict]:
    """Mock data khi không có Tavily key (để test)."""
    return [
        {
            "title": f"Mock result 1 for: {query}",
            "url": "https://example.com/1",
            "content": f"This is a sample result about {query}. High demand, low competition.",
        },
        {
            "title": f"Mock result 2 for: {query}",
            "url": "https://example.com/2",
            "content": f"Another perspective on {query}. Growing market, $500M TAM.",
        },
    ]


# ─────────────────────────────────────────
# Niche Discovery
# ─────────────────────────────────────────

RESEARCH_QUERIES = [
    "trending digital products to sell 2025",
    "profitable micro niche affiliate marketing 2025",
    "best selling notion templates gumroad 2025",
    "AI tools for sale profitable niche",
    "underserved market digital products creators",
    "high margin online business ideas solo founder",
    "best selling prompt packs AI tools marketplace",
    "niche newsletter monetization ideas 2025",
]


def discover_raw_niches() -> list[dict]:
    """
    Search web để tìm niche ideas thô.
    Returns list của raw niche mentions.
    """
    print("🔍 Searching for niche opportunities...")
    all_results = []

    for query in RESEARCH_QUERIES[:4]:  # Giới hạn để tiết kiệm API quota
        results = tavily_search(query, max_results=3)
        all_results.extend(results)
        time.sleep(0.5)

    print(f"✅ Found {len(all_results)} raw results")
    return all_results


# ─────────────────────────────────────────
# Niche Scoring & Analysis
# ─────────────────────────────────────────

SCORING_PROMPT = """
Bạn là một chuyên gia kinh doanh online với 10 năm kinh nghiệm về MMO, digital products, và affiliate marketing.

Dựa trên các kết quả research sau đây, hãy identify và score TOP 5 niches tiềm năng nhất.

## Research Data:
{research_data}

## Existing Projects (để tránh trùng lặp):
{existing_projects}

## Lessons Learned:
{lessons}

## Current Strategy:
{strategy}

## Yêu cầu scoring:
Score mỗi niche từ 1-10 cho các tiêu chí sau:
1. **demand_score** (1-10): Nhu cầu thị trường cao không?
2. **competition_score** (1-10): Competition thấp = điểm cao
3. **agent_doable_score** (1-10): AI agent có thể tự làm 80-90% không?
4. **monetization_speed** (1-10): Có thể tạo revenue trong 30-60 ngày không?
5. **budget_fit_score** (1-10): Phù hợp budget $10-30/tháng không?

## Final Score Formula:
final_score = (demand*0.25) + (competition*0.25) + (agent_doable*0.30) + (monetization_speed*0.15) + (budget_fit*0.05)

## Output format (JSON only, no markdown):
{
  "niches": [
    {
      "name": "tên niche",
      "type": "digital_product | affiliate | saas | newsletter",
      "description": "mô tả ngắn gọn",
      "target_audience": "đối tượng mục tiêu",
      "monetization_method": "cách kiếm tiền",
      "demand_score": 8,
      "competition_score": 7,
      "agent_doable_score": 9,
      "monetization_speed": 8,
      "budget_fit_score": 10,
      "final_score": 8.2,
      "why_good": "lý do tiềm năng",
      "main_risk": "rủi ro chính",
      "agent_can_do": ["task 1", "task 2", "task 3"],
      "human_must_do": ["task cần human 1", "task cần human 2"]
    }
  ]
}
"""


def analyze_and_score_niches(raw_results: list[dict]) -> list[dict]:
    """Dùng LLM để analyze và score niches từ raw research."""
    print("🧠 Analyzing niches with AI...")

    # Prepare context
    research_text = "\n\n".join([
        f"Title: {r.get('title', '')}\n{r.get('content', '')[:500]}"
        for r in raw_results[:10]
    ])

    existing = get_all_projects()
    existing_names = [p["name"] for p in existing] if existing else ["None"]

    lessons = get_all_lessons()
    lessons_text = "\n".join([
        f"- [{l['lesson_type']}] {l.get('title', '')}: {l['content'][:200]}"
        for l in lessons[:10]
    ]) if lessons else "Chưa có bài học nào."

    strategy = get_latest_strategy() or "Chưa có strategy. Ưu tiên digital products và tools."

    prompt = SCORING_PROMPT.format(
        research_data=research_text,
        existing_projects=", ".join(existing_names),
        lessons=lessons_text,
        strategy=strategy,
    )

    raw_output = llm_complete(prompt, task_type="research", max_tokens=3000)

    # Parse JSON
    try:
        # Clean up potential markdown wrapping
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        data = json.loads(cleaned)
        niches = data.get("niches", [])
        # Sort by final_score desc
        niches.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        print(f"✅ Scored {len(niches)} niches")
        return niches[:5]
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}. Raw: {raw_output[:300]}")
        return []


# ─────────────────────────────────────────
# Business Plan Generator
# ─────────────────────────────────────────

BUSINESS_PLAN_PROMPT = """
Bạn là một CEO kinh nghiệm, chuyên xây dựng các online business. Hãy tạo một business plan chi tiết và thực tế.

## Niche Information:
{niche_info}

## Budget: $10-30/tháng
## Executor: AI Agent (Claude/GPT) - tự động 90%
## Investor review: Bắt buộc approve trước khi bắt đầu

## Yêu cầu Business Plan:
Tạo plan THỰC TẾ, không lý thuyết. Focus vào:
1. Các bước cụ thể agent CÓ THỂ tự làm được
2. Chỉ list việc thật sự cần human (account setup, payment verify)
3. Revenue projections thực tế (conservative + optimistic)
4. 90-day execution roadmap chi tiết theo tuần

## Output format (JSON only):
{
  "project_name": "tên project ngắn gọn, dễ nhớ",
  "executive_summary": "2-3 câu mô tả project và cơ hội",
  "niche": "tên niche",
  "type": "digital_product | affiliate | saas | newsletter",
  "revenue_model": "cách kiếm tiền cụ thể",
  "target_audience": "đối tượng cụ thể",
  "unique_value": "tại sao khách hàng mua",
  
  "revenue_projections": {
    "month_1": "$X-Y (conservative)",
    "month_3": "$X-Y",
    "month_6": "$X-Y",
    "month_12": "$X-Y",
    "assumptions": "các giả định"
  },
  
  "monthly_budget": 15.0,
  "budget_breakdown": {
    "VPS hosting": 5,
    "Domain": 1.5,
    "Claude API": 5,
    "Tools/APIs": 3.5
  },
  
  "agent_workload_pct": 90,
  
  "agent_tasks": [
    "Task cụ thể agent làm được 1",
    "Task cụ thể agent làm được 2"
  ],
  
  "human_tasks": [
    "Tạo tài khoản [Platform X]",
    "Verify payment method",
    "Approve final product trước khi publish"
  ],
  
  "week_by_week_plan": {
    "week_1": ["Subtask 1", "Subtask 2"],
    "week_2": ["Subtask 3", "Subtask 4"],
    "week_3": ["Subtask 5", "Subtask 6"],
    "week_4": ["Subtask 7", "Subtask 8"],
    "week_5_8": ["Growth tasks"],
    "week_9_12": ["Scale tasks"]
  },
  
  "risks": [
    "Rủi ro 1 và cách mitigate",
    "Rủi ro 2 và cách mitigate"
  ],
  
  "success_metrics": {
    "week_4": "KPI cụ thể",
    "month_3": "KPI cụ thể",
    "month_6": "KPI cụ thể"
  },
  
  "platforms_needed": ["Gumroad", "GitHub", "Netlify"],
  "tools_needed": ["Tavily API", "Claude API"],
  
  "why_agent_can_do_this": "Giải thích tại sao 90% công việc agent làm được",
  "first_action": "Hành động đầu tiên ngay sau khi approved"
}
"""


def generate_business_plan(niche: dict) -> dict:
    """Generate full business plan cho một niche."""
    print(f"📋 Generating business plan for: {niche.get('name', 'unknown')}")

    niche_info = json.dumps(niche, ensure_ascii=False, indent=2)
    prompt = BUSINESS_PLAN_PROMPT.format(niche_info=niche_info)

    raw_output = llm_complete(prompt, task_type="planning", max_tokens=4000)

    try:
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        plan = json.loads(cleaned)
        print(f"✅ Plan generated: {plan.get('project_name', 'unnamed')}")
        return plan
    except json.JSONDecodeError as e:
        print(f"⚠️  Plan parse error: {e}")
        # Fallback: return basic plan
        return {
            "project_name": niche.get("name", "Project"),
            "executive_summary": niche.get("description", ""),
            "niche": niche.get("name", ""),
            "type": niche.get("type", "digital_product"),
            "revenue_model": niche.get("monetization_method", ""),
            "monthly_budget": 15.0,
            "agent_workload_pct": 90,
            "revenue_projections": {
                "month_1": "$0-50",
                "month_3": "$50-200",
                "month_6": "$100-500",
            },
            "human_tasks": ["Setup payment account", "Approve product before publish"],
            "agent_tasks": ["Research market", "Create content", "Setup listing"],
            "risks": ["Low initial traction"],
            "raw_output": raw_output[:500],
        }


# ─────────────────────────────────────────
# Full Research Cycle
# ─────────────────────────────────────────

def run_research_cycle() -> list[int]:
    """
    Chạy full research cycle:
    1. Discover niches
    2. Score và analyze
    3. Generate business plans
    4. Lưu vào DB

    Returns list của project_ids vừa tạo (status=pending)
    """
    print(f"\n{'='*50}")
    print(f"🔬 RESEARCH CYCLE START — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # Step 1: Discover
    raw_results = discover_raw_niches()
    if not raw_results:
        print("❌ No results found")
        return []

    # Step 2: Score
    scored_niches = analyze_and_score_niches(raw_results)
    if not scored_niches:
        print("❌ Scoring failed")
        return []

    print(f"\n📊 TOP NICHES:")
    for i, n in enumerate(scored_niches[:3], 1):
        print(f"  {i}. {n['name']} (score: {n.get('final_score', 0):.1f})")

    # Step 3: Generate plans for top 2
    project_ids = []
    for niche in scored_niches[:2]:
        time.sleep(1)  # Rate limit
        plan = generate_business_plan(niche)
        if not plan:
            continue

        pid = create_project(
            name=plan.get("project_name", niche["name"]),
            type_=plan.get("type", "digital_product"),
            niche=niche.get("name", ""),
            business_plan=plan,
            monthly_budget=plan.get("monthly_budget", 15),
        )
        project_ids.append(pid)
        print(f"✅ Created project #{pid}: {plan.get('project_name')}")

    # Step 4: Save research report
    report_content = f"""
# Research Cycle — {datetime.now().strftime('%Y-%m-%d')}

## Top Niches Found:
{json.dumps(scored_niches[:3], ensure_ascii=False, indent=2)}

## Projects Created:
{', '.join(f'#{pid}' for pid in project_ids)}
"""
    save_report(report_content, "niche_research")

    print(f"\n✅ Research cycle complete. {len(project_ids)} proposals ready for review.")
    return project_ids


# ─────────────────────────────────────────
# Main (để test)
# ─────────────────────────────────────────

if __name__ == "__main__":
    from core.database import init_database
    init_database()
    project_ids = run_research_cycle()
    print(f"\n🎯 Created project proposals: {project_ids}")
    print("Gửi Telegram notifications để bạn approve...")
