"""REST API Server - Tobi Agent"""
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

import os
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from core.database import (
    init_database, get_dashboard, get_all_projects, get_all_lessons,
    create_task, approve_project, reject_project, record_revenue,
)

app = FastAPI(title="Tobi API", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", "tobi-api-key-change-this")


def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    project_id: int
    task_type: str = "human"
    priority: int = 5


class RevenueAdd(BaseModel):
    project_id: Optional[int] = None
    amount: float
    source: str
    note: str = ""


@app.on_event("startup")
async def startup():
    init_database()


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "Tobi", "version": "1.0.0"}


@app.get("/status", dependencies=[Depends(verify_api_key)])
async def status():
    return get_dashboard()


@app.get("/projects", dependencies=[Depends(verify_api_key)])
async def list_projects():
    return get_all_projects()


@app.get("/lessons", dependencies=[Depends(verify_api_key)])
async def list_lessons():
    return get_all_lessons()


@app.post("/task", dependencies=[Depends(verify_api_key)])
async def create_task_endpoint(task: TaskCreate):
    task_id = create_task(
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        priority=task.priority,
    )
    return {"task_id": task_id, "status": "created"}


@app.post("/research", dependencies=[Depends(verify_api_key)])
async def trigger_research():
    import asyncio
    asyncio.create_task(_run_research_bg())
    return {"status": "started", "message": "Research cycle started in background"}


async def _run_research_bg():
    from core.research_engine import run_research_cycle
    run_research_cycle()


@app.post("/revenue", dependencies=[Depends(verify_api_key)])
async def add_revenue(rev: RevenueAdd):
    if rev.project_id is None:
        raise HTTPException(status_code=400, detail="project_id required")
    record_revenue(
        project_id=rev.project_id,
        amount=rev.amount,
        source=rev.source,
        description=rev.note,
    )
    return {"status": "recorded", "amount": rev.amount}


@app.post("/approve/{project_id}", dependencies=[Depends(verify_api_key)])
async def approve(project_id: int):
    approve_project(project_id)
    return {"status": "approved", "project_id": project_id}


@app.post("/reject/{project_id}", dependencies=[Depends(verify_api_key)])
async def reject(project_id: int):
    reject_project(project_id, "Rejected via API")
    return {"status": "rejected", "project_id": project_id}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
