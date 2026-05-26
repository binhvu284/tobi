"""Web Dashboard - Tobi Agent"""
from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from datetime import datetime

from core.database import init_database, get_dashboard, get_all_projects, get_all_lessons, get_pending_human_tasks_all

app = FastAPI(title="Tobi Dashboard")

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tobi Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; font-size: 14px; }}
  .header {{ background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }}
  .header h1 {{ color: #58a6ff; font-size: 20px; font-weight: 700; letter-spacing: 2px; }}
  .header .meta {{ color: #8b949e; font-size: 12px; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; text-align: center; }}
  .card .label {{ color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
  .card .value {{ font-size: 32px; font-weight: 700; color: #58a6ff; }}
  .card .value.green {{ color: #3fb950; }}
  .card .value.yellow {{ color: #d29922; }}
  .section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
  .section h2 {{ color: #f0f6fc; font-size: 14px; font-weight: 600; margin-bottom: 16px; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; color: #8b949e; font-size: 11px; text-transform: uppercase; padding: 8px 12px; border-bottom: 1px solid #30363d; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #21262d; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
  .badge-active {{ background: #1f6feb33; color: #58a6ff; }}
  .badge-pending {{ background: #d2992233; color: #d29922; }}
  .badge-completed {{ background: #3fb95033; color: #3fb950; }}
  .badge-failed {{ background: #f8514933; color: #f85149; }}
  .progress-bar {{ background: #21262d; border-radius: 4px; height: 6px; width: 100px; }}
  .progress-fill {{ background: #58a6ff; height: 6px; border-radius: 4px; }}
  .lesson-item {{ padding: 10px 0; border-bottom: 1px solid #21262d; }}
  .lesson-item:last-child {{ border-bottom: none; }}
  .lesson-title {{ color: #f0f6fc; font-weight: 600; margin-bottom: 4px; }}
  .lesson-content {{ color: #8b949e; font-size: 12px; line-height: 1.5; }}
  .todo-item {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #21262d; }}
  .todo-item:last-child {{ border-bottom: none; }}
  .todo-text {{ flex: 1; }}
  .todo-project {{ color: #8b949e; font-size: 11px; }}
  .btn-done {{ background: #238636; color: #fff; border: none; padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }}
  .btn-done:hover {{ background: #2ea043; }}
  .empty {{ color: #8b949e; text-align: center; padding: 20px; font-style: italic; }}
  @media (max-width: 600px) {{ .cards {{ grid-template-columns: 1fr; }} }}
</style>
<script>
  setTimeout(() => location.reload(), 60000);
  async function markDone(taskId) {{
    if (!confirm('Mark task #' + taskId + ' as done?')) return;
    const r = await fetch('/done/' + taskId, {{method: 'POST'}});
    if (r.ok) location.reload();
  }}
</script>
</head>
<body>
<div class="header">
  <h1>⚡ TOBI</h1>
  <div class="meta">Updated: {updated} · Auto-refresh: 60s</div>
</div>
<div class="container">
  <div class="cards">
    <div class="card">
      <div class="label">Active Projects</div>
      <div class="value">{active_count}</div>
    </div>
    <div class="card">
      <div class="label">Revenue This Month</div>
      <div class="value green">${revenue_month:.0f}</div>
    </div>
    <div class="card">
      <div class="label">Pending Todos</div>
      <div class="value yellow">{todos_count}</div>
    </div>
  </div>

  <div class="section">
    <h2>📁 Projects</h2>
    {projects_table}
  </div>

  <div class="section">
    <h2>📚 Recent Lessons</h2>
    {lessons_html}
  </div>

  <div class="section">
    <h2>📋 Human Todos</h2>
    {todos_html}
  </div>
</div>
</body>
</html>"""

STATUS_BADGE = {
    "active":    '<span class="badge badge-active">active</span>',
    "pending":   '<span class="badge badge-pending">pending</span>',
    "approved":  '<span class="badge badge-pending">approved</span>',
    "completed": '<span class="badge badge-completed">completed</span>',
    "failed":    '<span class="badge badge-failed">failed</span>',
    "paused":    '<span class="badge badge-failed">paused</span>',
}

TYPE_EMOJI = {"success": "✅", "failure": "❌", "insight": "💡", "warning": "⚠️"}


def build_projects_table(projects):
    if not projects:
        return '<p class="empty">No projects yet</p>'
    rows = ""
    for p in projects:
        badge = STATUS_BADGE.get(p["status"], f'<span class="badge">{p["status"]}</span>')
        pct = p.get("progress_pct", 0)
        rev = p.get("revenue_total", 0) or 0
        rows += f"""<tr>
          <td><strong>{p['name']}</strong></td>
          <td>{p['type']}</td>
          <td>
            <div class="progress-bar"><div class="progress-fill" style="width:{pct}%"></div></div>
            <small style="color:#8b949e">{pct}%</small>
          </td>
          <td style="color:#3fb950">${rev:.2f}</td>
          <td>{badge}</td>
        </tr>"""
    return f"""<table>
      <thead><tr><th>Name</th><th>Type</th><th>Progress</th><th>Revenue</th><th>Status</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def build_lessons_html(lessons):
    if not lessons:
        return '<p class="empty">No lessons recorded yet</p>'
    html = ""
    for l in lessons[:5]:
        emoji = TYPE_EMOJI.get(l["lesson_type"], "📌")
        title = l.get("title") or l["lesson_type"].upper()
        content = l["content"][:200]
        html += f"""<div class="lesson-item">
          <div class="lesson-title">{emoji} {title}</div>
          <div class="lesson-content">{content}</div>
        </div>"""
    return html


def build_todos_html(todos):
    if not todos:
        return '<p class="empty">✅ No pending todos</p>'
    html = ""
    for t in todos:
        html += f"""<div class="todo-item">
          <div class="todo-text">
            <div>{t['title']}</div>
            <div class="todo-project">📁 {t.get('project_name', '')}</div>
          </div>
          <button class="btn-done" onclick="markDone({t['id']})">Done</button>
        </div>"""
    return html


@app.on_event("startup")
async def startup():
    init_database()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    dash = get_dashboard()
    projects = get_all_projects()
    lessons = get_all_lessons()
    todos = get_pending_human_tasks_all()

    rev = dash.get("revenue", {})
    active_count = len(dash.get("active_projects", []))

    html = DASHBOARD_HTML.format(
        updated=datetime.now().strftime("%d/%m/%Y %H:%M"),
        active_count=active_count,
        revenue_month=rev.get("this_month", 0),
        todos_count=dash.get("human_todos_count", 0),
        projects_table=build_projects_table(projects),
        lessons_html=build_lessons_html(lessons),
        todos_html=build_todos_html(todos),
    )
    return HTMLResponse(content=html)


@app.post("/done/{task_id}")
async def mark_done(task_id: int):
    from core.database import complete_task
    complete_task(task_id, output="Completed via dashboard")
    return {"status": "done", "task_id": task_id}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
