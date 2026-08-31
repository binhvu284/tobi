"""Evidence-backed source of truth for Tier II Agent progress."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from core.release_manager import current_developer_version
from core.schema.agent_tier import _ensure_agent_tier_schema


class AgentTierEvidenceError(ValueError):
    """Raised when evidence could make Agent progress untrustworthy."""


FAMILY_IDS = (
    "project_execution",
    "local_diagnosis",
    "coding_maintenance",
    "browser_work",
    "github_monitoring_action",
)

_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "id": "grounded_task_intake",
        "name": "Grounded task intake",
        "short_name": "Task intake",
        "description": "Goal, scope, constraints, target, and missing fields are resolved or explicitly clarified.",
        "required_evidence": ("typed_request", "resolution_record", "clarification_record"),
        "required_families": FAMILY_IDS,
        "freshness": "current_release",
        "next_action": "Provide the one missing field shown by Mission Control.",
        "pillar": "understand",
        "risk": "low",
        "setup_actions": (),
    },
    {
        "id": "bounded_workflow_planning",
        "name": "Bounded workflow planning",
        "short_name": "Safe workflow plan",
        "description": "A versioned workflow records allowed tools, stop condition, budget, and approval boundary.",
        "required_evidence": ("workflow_selection", "tool_allowlist", "stop_condition", "policy_decision"),
        "required_families": FAMILY_IDS,
        "freshness": "current_release",
        "next_action": "Review the selected workflow and approve only the declared external effect.",
        "pillar": "understand",
        "risk": "medium",
        "setup_actions": (),
    },
    {
        "id": "local_work_execution",
        "name": "Local work execution",
        "short_name": "Local execution",
        "description": "Project, local diagnosis, and Coding maintenance complete through canonical Runtime.",
        "required_evidence": ("runtime_run", "typed_tool_result", "local_action_receipt", "coding_check"),
        "required_families": ("project_execution", "local_diagnosis", "coding_maintenance"),
        "freshness": "current_release",
        "next_action": "Run one bounded local workflow from normal Chat or Agent mode.",
        "pillar": "control",
        "risk": "medium",
        "setup_actions": ({"label": "Open Runs", "route": "/runs"},),
    },
    {
        "id": "browser_external_action",
        "name": "Browser and external action",
        "short_name": "External action",
        "description": "A bounded browser flow and an approved GitHub write have current successful evidence.",
        "required_evidence": ("browser_artifact", "navigation_allowlist", "external_approval", "external_receipt"),
        "required_families": ("browser_work", "github_monitoring_action"),
        "freshness": "24_hours",
        "next_action": "Approve the bounded browser or GitHub target shown in Mission Control.",
        "pillar": "control",
        "risk": "high",
        "setup_actions": ({"label": "Open Integrations", "route": "/integrations"},),
    },
    {
        "id": "durable_recovery",
        "name": "Durable recovery",
        "short_name": "Recovery",
        "description": "Restart, retry, resume, revise, and cancel preserve history without repeating completed effects.",
        "required_evidence": ("checkpoint", "recovery_event", "idempotency_key", "effect_receipt"),
        "required_families": FAMILY_IDS,
        "freshness": "current_release",
        "next_action": "Use the displayed resume, retry, revise, or cancel action on the same run.",
        "pillar": "control",
        "risk": "medium",
        "setup_actions": ({"label": "Open Runs", "route": "/runs"},),
    },
    {
        "id": "verified_delivery",
        "name": "Verified delivery",
        "short_name": "Verified result",
        "description": "Every success claim links to its required receipt, artifact, check, or external evidence.",
        "required_evidence": ("grounded_outcome", "receipt_or_artifact", "verification_check", "trace_link"),
        "required_families": FAMILY_IDS,
        "freshness": "current_release",
        "next_action": "Open the evidence link beside the final result.",
        "pillar": "presence",
        "risk": "low",
        "setup_actions": ({"label": "Open Runs", "route": "/runs"},),
    },
    {
        "id": "proactive_delivery",
        "name": "Proactive delivery",
        "short_name": "Proactive delivery",
        "description": "One fresh scheduled GitHub signal reaches Telegram exactly once and links to its source event.",
        "required_evidence": ("fresh_monitor_signal", "notification_receipt", "deduplication_record", "source_event_link"),
        "required_families": ("github_monitoring_action",),
        "freshness": "24_hours",
        "next_action": "Connect GitHub and Telegram when Mission Control reports setup needed.",
        "pillar": "presence",
        "risk": "medium",
        "setup_actions": ({"label": "Open Integrations", "route": "/integrations"},),
    },
)

ABILITY_IDS = tuple(row["id"] for row in _CONTRACTS)
_BY_ID = {row["id"]: row for row in _CONTRACTS}
_PILLAR_LABELS = {
    "understand": "Understand The Work",
    "control": "Execute And Recover",
    "presence": "Prove And Deliver",
}
_REF_PATTERN = re.compile(
    r"^(?:run|receipt|artifact|check|trace|event|notification|connector|policy|workflow|approval|source):"
    r"[A-Za-z0-9._:/#@-]{1,240}$"
)
_FORBIDDEN_REF_TERMS = ("raw_prompt", "raw_response", "authorization", "access_token", "secret")
_SETUP_ABILITIES = {"browser_external_action", "proactive_delivery"}


def contract(ability_id: str) -> dict[str, Any]:
    try:
        row = _BY_ID[ability_id]
    except KeyError as exc:
        raise AgentTierEvidenceError("unknown Agent ability") from exc
    return {
        **row,
        "required_evidence": list(row["required_evidence"]),
        "required_families": list(row["required_families"]),
        "setup_actions": [dict(action) for action in row["setup_actions"]],
    }


def _utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AgentTierEvidenceError("observed_at must be an ISO timestamp") from exc
    if value.tzinfo is None:
        raise AgentTierEvidenceError("observed_at must include a timezone")
    return value.astimezone(timezone.utc)


def _iso(value: datetime | str | None = None) -> str:
    return _utc(value).isoformat()


def _validate_evidence(
    *,
    ability_id: str,
    family_id: str,
    evidence_type: str,
    evidence_ref: str,
    source_release: str,
) -> dict[str, Any]:
    row = contract(ability_id)
    if family_id not in row["required_families"]:
        raise AgentTierEvidenceError("workflow family is not required by this ability")
    if evidence_type not in row["required_evidence"]:
        raise AgentTierEvidenceError("evidence type is not required by this ability")
    lowered = str(evidence_ref).lower()
    if (
        not isinstance(evidence_ref, str)
        or not _REF_PATTERN.fullmatch(evidence_ref)
        or any(term in lowered for term in _FORBIDDEN_REF_TERMS)
    ):
        raise AgentTierEvidenceError("evidence_ref must be a bounded opaque reference")
    if not isinstance(source_release, str) or not source_release.strip() or len(source_release) > 64:
        raise AgentTierEvidenceError("source_release must be a bounded identifier")
    return row


def record_evidence(
    conn: sqlite3.Connection,
    *,
    ability_id: str,
    family_id: str,
    evidence_type: str,
    evidence_ref: str,
    source_release: str,
    observed_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Persist one opaque proof idempotently; bodies and credentials are never accepted."""
    _validate_evidence(
        ability_id=ability_id,
        family_id=family_id,
        evidence_type=evidence_type,
        evidence_ref=evidence_ref,
        source_release=source_release,
    )
    _ensure_agent_tier_schema(conn)
    observed = _iso(observed_at)
    identity = "\x1f".join((ability_id, family_id, evidence_type, evidence_ref))
    evidence_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    recorded = _iso()
    conn.execute(
        """INSERT INTO agent_tier_evidence(
               evidence_id,ability_id,family_id,evidence_type,evidence_ref,
               source_release,observed_at,status,recorded_at
           ) VALUES (?,?,?,?,?,?,?,'valid',?)
           ON CONFLICT(evidence_id) DO UPDATE SET
               source_release=excluded.source_release,
               observed_at=excluded.observed_at,
               status='valid',
               recorded_at=excluded.recorded_at""",
        (
            evidence_id, ability_id, family_id, evidence_type, evidence_ref,
            source_release.strip(), observed, recorded,
        ),
    )
    conn.commit()
    stored = conn.execute(
        "SELECT * FROM agent_tier_evidence WHERE evidence_id=?", (evidence_id,)
    ).fetchone()
    return dict(stored)


def revoke_evidence(conn: sqlite3.Connection, evidence_id: str) -> bool:
    _ensure_agent_tier_schema(conn)
    changed = conn.execute(
        "UPDATE agent_tier_evidence SET status='revoked' WHERE evidence_id=? AND status='valid'",
        (evidence_id,),
    ).rowcount
    conn.commit()
    return changed == 1


def _is_current(row: sqlite3.Row, *, policy: str, release: str, now: datetime) -> bool:
    if row["status"] != "valid":
        return False
    observed = _utc(str(row["observed_at"]))
    if policy == "current_release":
        return str(row["source_release"]) == release
    return now - timedelta(hours=24) <= observed <= now + timedelta(minutes=5)


def _ability_result(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    current_release: str,
    now: datetime,
) -> dict[str, Any]:
    evidence_rows = conn.execute(
        """SELECT ability_id,family_id,evidence_type,evidence_ref,source_release,
                  observed_at,status
           FROM agent_tier_evidence WHERE ability_id=? ORDER BY observed_at,evidence_id""",
        (row["id"],),
    ).fetchall()
    current_rows = [
        evidence for evidence in evidence_rows
        if _is_current(evidence, policy=row["freshness"], release=current_release, now=now)
    ]
    present_types = {str(evidence["evidence_type"]) for evidence in current_rows}
    present_families = {str(evidence["family_id"]) for evidence in current_rows}
    missing_types = [value for value in row["required_evidence"] if value not in present_types]
    missing_families = [value for value in row["required_families"] if value not in present_families]
    missing = [f"Missing evidence: {value.replace('_', ' ')}" for value in missing_types]
    missing.extend(f"Missing workflow proof: {value.replace('_', ' ')}" for value in missing_families)

    if not missing:
        status = "active"
    elif current_rows or evidence_rows:
        status = "partial"
    elif row["id"] in _SETUP_ABILITIES:
        status = "setup_needed"
    else:
        status = "inactive"

    if current_rows:
        freshness_state = "current"
    elif evidence_rows:
        freshness_state = "stale"
    else:
        freshness_state = "missing"
    last_verified = max((str(evidence["observed_at"]) for evidence in evidence_rows), default=None)
    category = {
        "understand": "agent_understanding",
        "control": "agent_execution",
        "presence": "agent_delivery",
    }[row["pillar"]]
    return {
        "id": row["id"],
        "name": row["name"],
        "short_name": row["short_name"],
        "description": row["description"],
        "how_to_unlock": row["next_action"],
        "category": category,
        "category_label": _PILLAR_LABELS[row["pillar"]],
        "risk": row["risk"],
        "status": status,
        "evidence": [str(evidence["evidence_ref"]) for evidence in current_rows],
        "missing": missing,
        "freshness": {
            "policy": row["freshness"],
            "state": freshness_state,
            "last_verified_at": last_verified,
        },
        "next_action": row["next_action"],
        "setup_actions": [dict(action) for action in row["setup_actions"]],
    }


def evaluate(
    conn: sqlite3.Connection,
    *,
    current_release: str | None = None,
    now: datetime | str | None = None,
) -> list[dict[str, Any]]:
    """Return seven conservative Agent abilities; no evidence means no active claim."""
    _ensure_agent_tier_schema(conn)
    release = current_release or current_developer_version(conn)
    current_time = _utc(now)
    return [
        _ability_result(conn, row, current_release=release, now=current_time)
        for row in _CONTRACTS
    ]


def unavailable_pillars(reason: str) -> dict[str, list[dict[str, Any]]]:
    pillars: dict[str, list[dict[str, Any]]] = {key: [] for key in _PILLAR_LABELS}
    for row in _CONTRACTS:
        result = {
            "id": row["id"], "name": row["name"], "short_name": row["short_name"],
            "description": row["description"], "how_to_unlock": row["next_action"],
            "category": "agent_registry", "category_label": _PILLAR_LABELS[row["pillar"]],
            "risk": row["risk"], "status": "inactive", "evidence": [],
            "missing": [reason],
            "freshness": {"policy": row["freshness"], "state": "missing", "last_verified_at": None},
            "next_action": row["next_action"],
            "setup_actions": [dict(action) for action in row["setup_actions"]],
        }
        pillars[row["pillar"]].append(result)
    return pillars


def tier2_pillars(
    conn: sqlite3.Connection,
    *,
    current_release: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    pillars: dict[str, list[dict[str, Any]]] = {key: [] for key in _PILLAR_LABELS}
    by_id = {row["id"]: row for row in evaluate(
        conn, current_release=current_release, now=now
    )}
    for contract_row in _CONTRACTS:
        pillars[contract_row["pillar"]].append(by_id[contract_row["id"]])
    return pillars


def pillar_labels() -> dict[str, str]:
    return dict(_PILLAR_LABELS)


def status_map(
    conn: sqlite3.Connection,
    *,
    current_release: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, str]:
    return {
        row["id"]: row["status"]
        for row in evaluate(conn, current_release=current_release, now=now)
    }


def summary(
    conn: sqlite3.Connection,
    *,
    current_release: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    abilities = evaluate(conn, current_release=current_release, now=now)
    active = sum(1 for row in abilities if row["status"] == "active")
    total = len(abilities)
    return {
        "tier": 2,
        "tier_name": "Agent",
        "active_count": active,
        "total": total,
        "progress_pct": round(active / total * 100) if total else 0,
        "complete": active == total and total > 0,
        "abilities": abilities,
    }
