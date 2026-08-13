"""Pure T10 adapter from accepted worker metadata to MC-owned capabilities."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional

from core.runtime.contracts import (
    ErrorCategory,
    ErrorStage,
    RecoveryAction,
    RuntimeErrorInfo,
)


AUTHORITY = "mission_control"
CONTRACT_VERSION = "1"
CODING_SOURCE_VERSION = "2"
HERMES_SOURCE_VERSION = "1"
_CODING_ADAPTERS = frozenset({"native", "codex", "opencode", "hermes"})
_CODING_CAPABILITIES = (
    "bounded_coding",
    "checkpoint_resume",
    "evidence_report",
    "goal_handoff",
    "queue_item_execution",
    "typed_events",
)
_READY_STATUSES = frozenset({"ready"})


def _text(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{name} must be a non-empty string")
    return result


@dataclass(frozen=True)
class WorkerCapabilityRecord:
    worker_id: str
    display_name: str
    adapter: str
    available: bool
    status: str
    reason: str
    capabilities: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()
    canonical_writes: tuple[str, ...] = ()
    authority: str = AUTHORITY
    source_version: str = CODING_SOURCE_VERSION
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in ("worker_id", "display_name", "adapter", "status", "reason",
                     "authority", "source_version", "contract_version"):
            _text(getattr(self, name), name)
        if self.authority != AUTHORITY:
            raise ValueError("worker capability authority must remain Mission Control")
        if not isinstance(self.available, bool):
            raise ValueError("available must be a bool")
        if any(not str(item).strip() for item in self.capabilities):
            raise ValueError("capabilities must contain non-empty strings")
        if self.canonical_writes:
            raise ValueError("workers cannot own canonical writes")


@dataclass(frozen=True)
class WorkerCapabilitySnapshot:
    version: str
    observed_at: str
    workers: tuple[WorkerCapabilityRecord, ...]
    authority: str = AUTHORITY
    coding_source_version: str = CODING_SOURCE_VERSION
    hermes_source_version: str = HERMES_SOURCE_VERSION
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in ("version", "observed_at", "authority", "coding_source_version",
                     "hermes_source_version", "contract_version"):
            _text(getattr(self, name), name)
        if self.authority != AUTHORITY:
            raise ValueError("snapshot authority must remain Mission Control")
        if any(not isinstance(worker, WorkerCapabilityRecord) for worker in self.workers):
            raise ValueError("workers must contain WorkerCapabilityRecord values")


@dataclass(frozen=True)
class WorkerAssignment:
    run_id: str
    worker_id: str
    status: str
    worker: Optional[WorkerCapabilityRecord] = None
    fallback_worker_ids: tuple[str, ...] = ()
    error: Optional[RuntimeErrorInfo] = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _text(self.run_id, "run_id")
        _text(self.worker_id, "worker_id")
        if self.status not in {"ready", "blocked"}:
            raise ValueError("status must be ready or blocked")
        if self.status == "ready" and (self.worker is None or self.error is not None):
            raise ValueError("ready assignments require a worker and no error")
        if self.status == "blocked" and self.error is None:
            raise ValueError("blocked assignments require an error")


def _safe_status(row: Mapping[str, Any]) -> tuple[bool, str, str]:
    enabled = bool(row.get("enabled", True))
    status = str(row.get("health_status") or "unknown").strip().lower()
    if not enabled or status == "disabled":
        return False, "disabled", "Worker is disabled by Mission Control policy."
    if status == "needs_auth":
        return False, status, "Worker setup is incomplete."
    if status in _READY_STATUSES:
        return True, "ready", "Worker is available."
    if status in {"unavailable", "offline", "degraded"}:
        return False, status, "Worker is currently unavailable."
    return False, "unknown", "Worker availability has not been verified."


def _skill_evidence(skills: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    refs: set[str] = set()
    for skill in skills:
        path = str(skill.get("file_path") or "").strip()
        version = skill.get("version")
        if path and version is not None:
            refs.add(f"{path}@{version}")
    return tuple(sorted(refs))


def build_snapshot(
    worker_profiles: Iterable[Mapping[str, Any]],
    hermes_skills: Iterable[Mapping[str, Any]],
    *,
    observed_at: str,
    coding_source_version: str = CODING_SOURCE_VERSION,
    hermes_source_version: str = HERMES_SOURCE_VERSION,
) -> WorkerCapabilitySnapshot:
    """Build a deterministic snapshot without probing, executing, or persisting."""
    if coding_source_version != CODING_SOURCE_VERSION:
        raise ValueError("unsupported coding worker source version")
    if hermes_source_version != HERMES_SOURCE_VERSION:
        raise ValueError("unsupported Hermes source version")
    observed_at = _text(observed_at, "observed_at")
    rows = sorted((dict(row) for row in worker_profiles), key=lambda row: str(row.get("slug") or ""))
    skill_refs = _skill_evidence(hermes_skills)
    seen: set[str] = set()
    workers: list[WorkerCapabilityRecord] = []
    for row in rows:
        worker_id = _text(row.get("slug"), "worker_id")
        if worker_id in seen:
            raise ValueError(f"duplicate worker authority: {worker_id}")
        seen.add(worker_id)
        adapter = _text(row.get("adapter"), "adapter").lower()
        available, status, reason = _safe_status(row)
        enabled = bool(row.get("enabled", True))
        capabilities = (
            _CODING_CAPABILITIES
            if enabled and adapter in _CODING_ADAPTERS
            else ()
        )
        evidence_refs = skill_refs if adapter == "hermes" else (
            f"coding-worker-profile:{worker_id}@{coding_source_version}",
        )
        workers.append(WorkerCapabilityRecord(
            worker_id=worker_id,
            display_name=str(row.get("name") or worker_id).strip() or worker_id,
            adapter=adapter,
            available=available,
            status=status,
            reason=reason,
            capabilities=tuple(sorted(capabilities)),
            evidence_refs=evidence_refs,
            source_version=(hermes_source_version if adapter == "hermes" else coding_source_version),
        ))
    canonical = {
        "authority": AUTHORITY,
        "coding_source_version": coding_source_version,
        "hermes_source_version": hermes_source_version,
        "workers": [asdict(worker) for worker in workers],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    version = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return WorkerCapabilitySnapshot(
        version=version,
        observed_at=observed_at,
        workers=tuple(workers),
        coding_source_version=coding_source_version,
        hermes_source_version=hermes_source_version,
    )


def select_worker(
    snapshot: WorkerCapabilitySnapshot,
    worker_id: str,
    *,
    run_id: str,
) -> WorkerAssignment:
    """Select metadata only; execution remains with a later T10 adapter."""
    worker_id = _text(worker_id, "worker_id")
    run_id = _text(run_id, "run_id")
    worker = next((item for item in snapshot.workers if item.worker_id == worker_id), None)
    if worker is not None and worker.available:
        return WorkerAssignment(run_id=run_id, worker_id=worker_id, status="ready", worker=worker)
    fallback = tuple(item.worker_id for item in snapshot.workers if item.available)
    status = worker.status if worker is not None else "unknown"
    error = RuntimeErrorInfo(
        code="worker_unavailable",
        category=ErrorCategory.AVAILABILITY,
        stage=ErrorStage.PLAN,
        message="Requested worker capability is unavailable.",
        owner_message="This worker is unavailable. Retry its check, finish setup, or choose an available worker.",
        retryable=True,
        recovery_actions=(
            RecoveryAction.RETRY_STEP,
            RecoveryAction.PROVIDE_INPUT,
            RecoveryAction.REVISE,
        ),
        safe_detail=f"worker={worker_id};status={status}",
    )
    return WorkerAssignment(
        run_id=run_id,
        worker_id=worker_id,
        status="blocked",
        worker=worker,
        fallback_worker_ids=fallback,
        error=error,
    )
