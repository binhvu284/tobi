"""
PROJECT EXECUTOR - MMO Agent System
=====================================
Engine xử lý việc thực thi tasks của agent:
  • Load active projects từ DB
  • Execute task tiếp theo theo priority
  • Cập nhật progress + notify Telegram
  • Tự nhận diện task nào cần human → flag và alert

Chạy: python project_executor.py
Hoặc gọi execute_all_projects() từ main orchestrator
"""

import os
import json
import time
from datetime import datetime
from typing import Optional

from core.model_router import llm_complete, get_llm
from core.database import (
    get_active_projects, get_next_agent_task, get_human_todos,
    complete_task, update_project_progress, get_project_progress,
    create_task, add_lesson, save_report, record_revenue,
)


# ─────────────────────────────────────────
# Task Executors
# ─────────────────────────────────────────

def execute_research_task(task: dict, project: dict) -> str:
    """Thực hiện research tasks - tìm kiếm, tổng hợp thông tin."""
    prompt = f"""
Bạn là một researcher chuyên nghiệp. Thực hiện task sau cho project "{project['name']}".

## Task: {task['title']}
## Description: {task.get('description', '')}

## Project Context:
Niche: {project.get('niche', '')}
Type: {project.get('type', '')}
Business Plan Summary: {json.dumps(project.get('business_plan', {}).get('executive_summary', ''), ensure_ascii=False)}

## Yêu cầu:
- Cung cấp kết quả research chi tiết và thực tế
- Bao gồm: insights, data points, recommendations
- Format: Markdown
- Độ dài: 500-1000 words
- Chỉ thông tin có thể verify được

Thực hiện ngay:
"""
    return llm_complete(prompt, task_type="research", max_tokens=2000)


def execute_writing_task(task: dict, project: dict) -> str:
    """Thực hiện writing tasks - content, copy, product descriptions."""
    business_plan = project.get('business_plan', {})
    target_audience = business_plan.get('target_audience', 'general audience')
    unique_value = business_plan.get('unique_value', '')

    prompt = f"""
Bạn là một content writer chuyên nghiệp. Viết nội dung cho task sau.

## Task: {task['title']}
## Description: {task.get('description', '')}

## Project Info:
- Project: {project['name']}
- Niche: {project.get('niche', '')}
- Target Audience: {target_audience}
- Unique Value: {unique_value}

## Yêu cầu:
- Viết chất lượng cao, engaging
- Phù hợp với target audience
- SEO-friendly nếu là web content
- Actionable và valuable cho reader

Viết nội dung ngay:
"""
    return llm_complete(prompt, task_type="writing", max_tokens=3000)


def execute_planning_task(task: dict, project: dict) -> str:
    """Thực hiện planning tasks - strategy, roadmap, breakdown."""
    prompt = f"""
Bạn là một project manager có kinh nghiệm. Lên kế hoạch cho task sau.

## Task: {task['title']}
## Description: {task.get('description', '')}
## Project: {project['name']}

## Business Plan:
{json.dumps(project.get('business_plan', {}), ensure_ascii=False, indent=2)[:1000]}

## Yêu cầu output:
- Kế hoạch chi tiết, có thể thực thi ngay
- Breakdown thành các bước nhỏ
- Timeline thực tế
- Resource cần thiết

Output:
"""
    return llm_complete(prompt, task_type="planning", max_tokens=2000)


def execute_coding_task(task: dict, project: dict) -> str:
    """Thực hiện coding tasks - scripts, automation code."""
    prompt = f"""
Bạn là một developer chuyên nghiệp. Viết code cho task sau.

## Task: {task['title']}
## Description: {task.get('description', '')}
## Project: {project['name']}

## Yêu cầu:
- Code sạch, có comments
- Production-ready
- Include error handling
- Include usage example

Viết code ngay:
"""
    return llm_complete(prompt, task_type="coding", max_tokens=3000)


def execute_generic_task(task: dict, project: dict) -> str:
    """Generic task executor cho tasks không phân loại được."""
    prompt = f"""
Bạn là một AI agent chuyên nghiệp đang thực hiện một task trong project kinh doanh.

## Project: {project['name']} ({project.get('niche', '')})
## Task: {task['title']}
## Description: {task.get('description', '')}

## Business Context:
{json.dumps(project.get('business_plan', {}).get('executive_summary', ''), ensure_ascii=False)}

## Yêu cầu:
Thực hiện task này một cách chuyên nghiệp. Cung cấp output cụ thể, có thể dùng ngay.
Nếu cần thông tin thêm, note rõ những gì còn thiếu.

Output:
"""
    return llm_complete(prompt, task_type="writing", max_tokens=2000)


# ─────────────────────────────────────────
# Task Router
# ─────────────────────────────────────────

def classify_task_type(task_title: str, task_desc: str) -> str:
    """Quick classify task type để route đến executor phù hợp."""
    title_lower = (task_title + " " + task_desc).lower()

    if any(kw in title_lower for kw in ["research", "analyze", "find", "search", "discover", "investigate"]):
        return "research"
    elif any(kw in title_lower for kw in ["write", "create content", "draft", "copy", "article", "blog", "description"]):
        return "writing"
    elif any(kw in title_lower for kw in ["plan", "strategy", "roadmap", "breakdown", "schedule"]):
        return "planning"
    elif any(kw in title_lower for kw in ["code", "script", "automate", "build", "develop", "implement"]):
        return "coding"
    else:
        return "generic"


def execute_task(task: dict, project: dict) -> Optional[str]:
    """Router: phân loại và execute task phù hợp."""
    task_category = classify_task_type(
        task.get("title", ""),
        task.get("description", ""),
    )

    print(f"   ⚡ Executing [{task_category}]: {task['title']}")

    try:
        executors = {
            "research": execute_research_task,
            "writing":  execute_writing_task,
            "planning": execute_planning_task,
            "coding":   execute_coding_task,
            "generic":  execute_generic_task,
        }
        executor = executors.get(task_category, execute_generic_task)
        output = executor(task, project)
        return output

    except Exception as e:
        print(f"   ❌ Task execution error: {e}")
        return f"Error: {str(e)}"


# ─────────────────────────────────────────
# Progress Calculator
# ─────────────────────────────────────────

def recalculate_progress(project_id: int) -> int:
    """Tính lại % progress và cập nhật DB."""
    stats = get_project_progress(project_id)
    pct = stats["progress_pct"]
    update_project_progress(project_id, pct)
    return pct


# ─────────────────────────────────────────
# Project Executor
# ─────────────────────────────────────────

def execute_project_cycle(project: dict, max_tasks: int = 3) -> dict:
    """
    Execute một cycle của một project:
    - Lấy và thực hiện tối đa max_tasks agent tasks
    - Cập nhật progress
    - Return summary

    Returns dict với results để gửi report
    """
    project_id = project["id"]
    project_name = project["name"]

    print(f"\n🚀 Executing project #{project_id}: {project_name}")

    executed = []
    skipped = []

    for _ in range(max_tasks):
        task = get_next_agent_task(project_id)
        if not task:
            print(f"   ℹ️  No more agent tasks pending")
            break

        print(f"   📋 Task #{task['id']}: {task['title']}")

        output = execute_task(task, project)

        if output:
            complete_task(task["id"], output=output)
            executed.append({
                "id": task["id"],
                "title": task["title"],
                "output_preview": output[:200] + "..." if len(output) > 200 else output,
            })
            print(f"   ✅ Done")
        else:
            skipped.append(task["title"])
            print(f"   ⚠️  Skipped (no output)")

        time.sleep(0.5)  # Rate limiting

    # Recalculate progress
    progress = recalculate_progress(project_id)

    # Get pending human tasks
    human_todos = get_human_todos(project_id)

    # Generate completion notes
    if progress == 100:
        notes = "Project completed! All tasks done."
        add_lesson(
            content=f"Project '{project_name}' completed successfully.",
            title=f"Completed: {project_name}",
            lesson_type="success",
            project_id=project_id,
            impact_score=7,
        )
    else:
        notes = f"Progress: {progress}%. {len(human_todos)} human tasks pending."

    update_project_progress(project_id, progress, notes)

    return {
        "project_id": project_id,
        "project_name": project_name,
        "tasks_executed": len(executed),
        "tasks_skipped": len(skipped),
        "progress_pct": progress,
        "human_todos_count": len(human_todos),
        "executed_details": executed,
        "human_todos": human_todos,
    }


# ─────────────────────────────────────────
# Full Execution Cycle
# ─────────────────────────────────────────

def execute_all_projects(tasks_per_project: int = 3) -> list[dict]:
    """
    Run execution cycle cho tất cả active projects.
    Được gọi bởi main orchestrator (mỗi 6 giờ).
    Returns list of execution results.
    """
    print(f"\n{'='*50}")
    print(f"⚙️  EXECUTION CYCLE — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    active = get_active_projects()
    if not active:
        print("ℹ️  No active projects to execute")
        return []

    print(f"📋 {len(active)} active project(s)")

    results = []
    for project in active:
        try:
            result = execute_project_cycle(project, max_tasks=tasks_per_project)
            results.append(result)
        except Exception as e:
            print(f"❌ Error executing project #{project['id']}: {e}")
            results.append({
                "project_id": project["id"],
                "project_name": project["name"],
                "error": str(e),
            })

    # Save execution report
    report = _format_execution_report(results)
    save_report(report, "daily")

    print(f"\n✅ Execution cycle complete: {len(results)} projects processed")
    return results


def _format_execution_report(results: list[dict]) -> str:
    """Format execution results thành report text."""
    lines = [
        f"# Execution Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"## ❌ #{r['project_id']} {r['project_name']}")
            lines.append(f"Error: {r['error']}")
        else:
            lines.append(f"## ✅ #{r['project_id']} {r['project_name']}")
            lines.append(f"- Tasks executed: {r.get('tasks_executed', 0)}")
            lines.append(f"- Progress: {r.get('progress_pct', 0)}%")
            lines.append(f"- Human todos: {r.get('human_todos_count', 0)}")
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────
# Helper: Auto-generate tasks from business plan
# ─────────────────────────────────────────

def generate_tasks_from_plan(project_id: int, business_plan: dict) -> int:
    """
    Parse business plan và tạo tasks trong DB.
    Gọi sau khi project được approve.
    Returns số tasks được tạo.
    """
    count = 0
    week_plan = business_plan.get("week_by_week_plan", {})

    # Agent tasks từ plan
    for week_key, tasks in week_plan.items():
        week_num = 1
        try:
            week_num = int(week_key.replace("week_", "").split("_")[0])
        except Exception:
            week_num = 5  # Default for "week_5_8" etc.

        for task_title in (tasks or []):
            create_task(
                project_id=project_id,
                title=task_title,
                description=f"From business plan, {week_key}",
                task_type="agent",
                priority=week_num,
                week_num=week_num,
            )
            count += 1

    # Human tasks
    for i, human_task in enumerate(business_plan.get("human_tasks", [])):
        create_task(
            project_id=project_id,
            title=human_task,
            description="Việc cần bạn thực hiện thủ công",
            task_type="human",
            priority=1,
            week_num=1,
        )
        count += 1

    print(f"✅ Created {count} tasks for project #{project_id}")
    return count


# ─────────────────────────────────────────
# Main (để test)
# ─────────────────────────────────────────

if __name__ == "__main__":
    from core.database import init_database
    init_database()
    results = execute_all_projects(tasks_per_project=2)
    print(f"\n📊 Results: {json.dumps(results, indent=2, ensure_ascii=False)}")
