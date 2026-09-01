"""Tool-call parsing, affirm/negate detection and proposal/confirmation replies.

Extracted from core/conductor.py (Phase 4b). Pure text/JSON handling plus the reply
builders the orchestration loop uses; the action audit helpers come from
core.conductor_registry. Verbatim move.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional  # noqa: F401 - used in signatures

from core.conductor_registry import _action_summary, _log_action

logger = logging.getLogger("tobi.conductor")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _balanced_objects(text: str) -> list[str]:
    """Extract every top-level {...} substring with brace-balanced bodies (string-aware), so a
    tool-call object survives nested braces (e.g. "args": {}) and a chatty prose preamble."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0; j = i; instr = False; esc = False
        while j < n:
            c = text[j]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = not instr
            elif not instr:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(text[i:j + 1]); break
            j += 1
        i = j + 1
    return out


def _parse_tool_call(text: str) -> Optional[dict]:
    """Return {'tool','args'} if the model asked for a tool, else None (= final answer).
    Tolerates a prose preamble and nested braces by scanning balanced {...} objects."""
    if not text:
        return None
    candidates: list[str] = [text.strip()]
    m = _FENCE_RE.search(text)
    if m:
        candidates.insert(0, m.group(1).strip())
    candidates += _balanced_objects(text)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
            return {"tool": obj["tool"], "args": obj.get("args") or {}}
    return None


def _parse_tool_calls(text: str) -> list[dict]:
    """EVERY tool-call object in a model reply, in order — handles a model that emits several
    calls at once (two JSON objects, or a JSON array) so e.g. 'create 2 projects' all run.
    Dedupes identical calls."""
    if not text:
        return []
    out: list[dict] = []
    seen: set[str] = set()

    def add(o: Any) -> None:
        if isinstance(o, dict) and isinstance(o.get("tool"), str):
            call = {"tool": o["tool"], "args": o.get("args") or {}}
            key = json.dumps(call, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key); out.append(call)

    candidates: list[str] = [m.group(1).strip() for m in _FENCE_RE.finditer(text)]
    candidates += _balanced_objects(text)
    candidates.append(text.strip())
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, list):
            for o in obj:
                add(o)
        else:
            add(obj)
    return out


def strip_tool_calls(text: str) -> str:
    """Return `text` with every tool-call JSON object removed, leaving the prose around it.

    A model may answer with both at once. `codex:gpt-5.6-sol`, asked to "list all project,
    update their progress", replied:

        {"tool":"list_projects","args":{}}I need each project's current status or completed
        milestones to update progress accurately.

    That is not malformed. It starts the lookup and asks the one question the request left
    open -- what to update the progress to. Treating the whole reply as unusable threw away a
    valid call *and* a fair question, and told the owner his model was struggling.

    Only objects that genuinely parse as `{"tool": ...}` are removed, so a fenced JSON answer
    the owner actually asked for survives untouched.
    """
    if not text:
        return ""
    out = text
    for candidate in _balanced_objects(text):
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
            out = out.replace(candidate, " ", 1)
    # Collapse the gap the removal leaves behind without disturbing paragraph breaks.
    out = re.sub(r"[ \t]{2,}", " ", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _safe_complete(client, msgs: list, system: str, max_tokens: int = 700) -> str:
    try:
        out = client.complete(list(msgs), system=system, max_tokens=max_tokens)
        return (out or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("conductor LLM call failed: %s", e)
        return ""


def _history(chat_id: int, limit: int = 6) -> list[dict]:
    try:
        from core.database import load_conversation_history
        rows = load_conversation_history(chat_id, limit=limit)
        return [{"role": r["role"], "content": r["content"]} for r in rows
                if r.get("role") in ("user", "assistant") and r.get("content")]
    except Exception:
        return []


def _default_chat_id() -> int:
    from core import brain
    return brain.DASHBOARD_CHAT_ID


# Affirm/negate sets cover EN + VN so a typed "yes"/"có" confirms a pending action.
_AFFIRM = {"yes", "y", "yeah", "yep", "yup", "confirm", "confirmed", "do it", "go ahead", "proceed",
           "ok", "okay", "sure", "please do", "yes please", "go", "approve",
           "có", "co", "đồng ý", "dong y", "ừ", "u", "được", "duoc", "làm đi", "lam di",
           "tiến hành", "tien hanh"}
_NEGATE = {"no", "n", "nope", "cancel", "stop", "reject", "don't", "dont", "never mind", "nevermind",
           "không", "khong", "hủy", "huy", "đừng", "dung", "thôi", "thoi"}


def _norm(msg: str) -> str:
    return re.sub(r"[!.\s]+$", "", (msg or "").strip().lower())


def _is_affirm(msg: str) -> bool:
    return _norm(msg) in _AFFIRM


def _is_negate(msg: str) -> bool:
    return _norm(msg) in _NEGATE


def _propose_reply(summary: str, risk: str) -> str:
    return (f"I'd like to {summary}, sir — that's a {risk}-risk action, so I'll wait for your nod. "
            "Shall I proceed? (Reply “yes” to confirm, or use the button.)")


def _propose_actions(highs: list[tuple], chat_id: int, surface: str, used: list, intent: str) -> dict:
    """Propose one or many actions for confirmation. Multiple → a single batch card the owner
    accepts/refuses together (so 'delete 3 projects' asks once). Items may carry their own risk
    (a terminal command confirmed under Ask is medium, not high)."""
    items: list[dict] = []
    out_used = list(used)
    for entry in highs:
        tool, args = entry[0], entry[1]
        risk = entry[2] if len(entry) > 2 else "high"
        summary = _action_summary(tool, args)
        logged_args = args
        if tool in {"office_create_artifact", "office_update_artifact"}:
            try:
                from core import office_artifacts
                logged_args = office_artifacts.stage_action_payload(tool, args)
            except Exception:
                pass
        aid = _log_action(chat_id, surface, tool, logged_args, risk, "proposed", summary)
        items.append({"id": aid, "tool": tool, "summary": summary, "risk": risk})
        out_used.append(tool)
    if len(items) == 1:
        it = items[0]
        return {"reply": _propose_reply(it["summary"], it["risk"]), "tools_used": out_used,
                "intent": intent, "pending_action": it, "streamed": False}
    lines = "\n".join(f"  • {i['summary']}" for i in items)
    reply = (f"Those are {len(items)} high-risk actions, sir — I'll wait for your go-ahead:\n{lines}\n"
             "Reply “yes” to confirm them all, or use the buttons.")
    return {"reply": reply, "tools_used": out_used, "intent": intent,
            "pending_action": {"id": items[0]["id"], "tool": "batch", "risk": "high",
                               "summary": f"{len(items)} high-risk actions", "items": items},
            "streamed": False}


def _confirm_reply_batch(pendings: list[dict], results: Optional[list], decision: str) -> str:
    if len(pendings) == 1:
        return _confirm_reply(pendings[0], (results[0] if results else {"status": "rejected"}))
    if decision != "approve":
        return f"Very good, sir — I've cancelled all {len(pendings)} of those."
    done = sum(1 for r in (results or []) if r.get("status") == "executed")
    if done == len(pendings):
        return f"Done, sir — all {done} actions are complete."
    return f"Completed {done} of {len(pendings)}, sir — the rest didn't go through."


def _confirm_reply(pending: dict, res: dict) -> str:
    status = res.get("status")
    summary = pending.get("summary")
    if status == "executed":
        return f"Done, sir — {summary}."
    if status == "rejected":
        return f"Very good, sir — I've cancelled that ({summary})."
    err = res.get("result", {}).get("error") if isinstance(res.get("result"), dict) else None
    return f"I'm afraid that didn't go through, sir{(' — ' + err) if err else ''}."


_TOOL_PHASE = {
    "get_evolution": "Checking your evolution…", "explain_architecture": "Reviewing the architecture…",
    "office_status": "Looking in on the office…", "list_projects": "Reading your projects…",
    "list_project_resources": "Opening the project's resources…", "read_resource": "Reading the resource…",
    "list_tasks": "Reading your tasks…", "check_health": "Running a health check…",
    "recall": "Searching your memory…", "read_notion": "Reading Notion…",
    "read_github": "Reading GitHub…", "list_github_repos": "Listing repos…", "read_drive": "Checking Drive…", "recall_conversations": "Searching past conversations…", "web_search": "Searching the web…",
    "outline_plan": "Planning the approach…",
    "remember": "Saving that to memory…", "create_project": "Creating the project…",
    "create_task": "Adding the task…", "complete_task": "Completing the task…",
    "assign_task": "Assigning the task…", "update_project_progress": "Updating progress…",
    "delete_task": "Removing the task…", "run_mission": "Preparing the mission…",
    "run_command": "Running the command…", "install_package": "Installing…",
    "configure_tool": "Writing the config…", "connect_tool": "Connecting…",
    "kill_job": "Stopping the job…", "set_terminal_mode": "Switching mode…",
    "terminal_status": "Checking the terminal…", "list_jobs": "Checking jobs…",
    "job_output": "Reading job output…", "list_installed_tools": "Reviewing your toolset…",
    "analyze_performance": "Running a system-health diagnosis…",
    "read_news": "Reading your News page…",
    "awakening_status": "Checking my Awakening status…", "summarize_repo": "Summarizing the repo…",
    "update_task": "Updating the task…", "save_note": "Saving the note…",
    "create_task_from_conversation": "Capturing tasks from our chat…",
}


def _phase_for(tool: str) -> str:
    return _TOOL_PHASE.get(tool, f"Using {tool.replace('_', ' ')}…")
