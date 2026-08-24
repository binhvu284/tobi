"""Additive SQLite schema for Mission Control Runtime V2."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone


RUNTIME_SCHEMA_VERSIONS = (
    "mc-runtime-v2-001",
    "mc-runtime-v2-002",
    "mc-runtime-v2-003",
    "mc-runtime-v2-004",
    "mc-runtime-v2-005",
    "mc-runtime-v2-006",
    "mc-runtime-v2-007",
    "mc-runtime-v2-008",
    "mc-runtime-v2-009",
    "mc-runtime-v2-010",
    "mc-runtime-v2-011",
    "mc-runtime-v2-012",
    "mc-runtime-v2-013",
)
RUNTIME_SCHEMA_VERSION = RUNTIME_SCHEMA_VERSIONS[-1]
_SCHEMA_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_RUNTIME_TABLES = {
    "mc_run_events",
    "mc_change_events",
    "mc_runtime_projections",
    "mc_system_entities",
    "mc_system_edges",
    "mc_runs",
    "mc_run_steps",
    "mc_run_checkpoints",
    "mc_run_commands",
    "mc_loop_recipes",
    "mc_loop_runs",
    "mc_loop_iterations",
    "mc_idempotency",
    "mc_action_receipts",
    "mc_policy_decisions",
    "mc_run_approvals",
    "mc_terminal_jobs",
    "mc_eval_cases",
    "mc_eval_runs",
    "mc_eval_findings",
    "mc_runtime_preferences",
    "mc_rollout_comparisons",
}

_STEP_LEASE_COLUMNS = {
    "lease_owner": "TEXT",
    "lease_token_hash": "TEXT",
    "lease_expires_at": "TEXT",
    "lease_epoch": "INTEGER NOT NULL DEFAULT 0 CHECK (lease_epoch >= 0)",
}

_STEP_CONTROL_COLUMNS = {
    "last_error_json": "TEXT",
    "last_error_hash": "TEXT",
    "next_attempt_at": "TEXT",
}

_RUN_CONTROL_COLUMNS = {
    "cancel_requested_at": "TEXT",
    "cancel_requested_by": "TEXT",
}

_TERMINAL_JOB_CANCEL_COLUMNS = {
    "cancel_idempotency_key": "TEXT",
    "cancel_requested_at": "TEXT",
    "cancel_requested_by": "TEXT",
    "cancel_acknowledged_at": "TEXT",
}

_TERMINAL_JOB_CANCEL_OBJECTS = {
    "idx_mc_terminal_jobs_cancel_request",
    "mc_terminal_jobs_cancel_request_guard",
    "mc_terminal_jobs_cancel_ack_guard",
}

_LOOP_CONTROL_COLUMNS = {
    "loop_version": "INTEGER NOT NULL DEFAULT 0 CHECK (loop_version >= 0)",
    "model_calls": "INTEGER NOT NULL DEFAULT 0 CHECK (model_calls >= 0)",
    "tool_calls": "INTEGER NOT NULL DEFAULT 0 CHECK (tool_calls >= 0)",
    "prompt_tokens": "INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0)",
    "completion_tokens": "INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0)",
    "runtime_ms": "INTEGER NOT NULL DEFAULT 0 CHECK (runtime_ms >= 0)",
    "cost_microusd": "INTEGER NOT NULL DEFAULT 0 CHECK (cost_microusd >= 0)",
    "download_bytes": "INTEGER NOT NULL DEFAULT 0 CHECK (download_bytes >= 0)",
    "storage_bytes": "INTEGER NOT NULL DEFAULT 0 CHECK (storage_bytes >= 0)",
    "started_at": "TEXT",
    "stopped_at": "TEXT",
}


_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS mc_run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        run_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        event_type TEXT NOT NULL,
        stage TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        trace_id TEXT,
        parent_span_id TEXT,
        contract_version TEXT NOT NULL DEFAULT '1',
        created_at TEXT NOT NULL,
        UNIQUE (run_id, sequence)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_events_stream ON mc_run_events(run_id, sequence)",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_events_trace ON mc_run_events(trace_id)",
    """CREATE TABLE IF NOT EXISTS mc_change_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        sequence INTEGER NOT NULL UNIQUE CHECK (sequence > 0),
        change_type TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        contract_version TEXT NOT NULL DEFAULT '1',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_change_events_subject ON mc_change_events(subject_type, subject_id, sequence)",
    """CREATE TABLE IF NOT EXISTS mc_runtime_projections (
        projection_type TEXT NOT NULL,
        projection_key TEXT NOT NULL,
        projection_version TEXT NOT NULL,
        last_sequence INTEGER NOT NULL DEFAULT 0,
        state_json TEXT NOT NULL,
        state_hash TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (projection_type, projection_key)
    )""",
    """CREATE TABLE IF NOT EXISTS mc_system_entities (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        canonical_key TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        version TEXT NOT NULL,
        owner_domain TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        source_sequence INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS mc_system_edges (
        edge_id TEXT PRIMARY KEY,
        from_entity_id TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        to_entity_id TEXT NOT NULL,
        version TEXT NOT NULL,
        evidence_refs_json TEXT NOT NULL,
        confidence REAL NOT NULL,
        valid_from TEXT,
        valid_to TEXT,
        source_sequence INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS mc_eval_cases (
        eval_case_id TEXT NOT NULL,
        version TEXT NOT NULL,
        category TEXT NOT NULL,
        objective TEXT NOT NULL,
        expected_behavior TEXT NOT NULL,
        required_evidence_json TEXT NOT NULL,
        scorer TEXT NOT NULL,
        threshold REAL NOT NULL CHECK (threshold >= 0 AND threshold <= 1),
        release_gate INTEGER NOT NULL CHECK (release_gate IN (0, 1)),
        autonomy_gate INTEGER NOT NULL CHECK (autonomy_gate IN (0, 1)),
        fixture_hash TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (eval_case_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS mc_eval_runs (
        eval_run_id TEXT PRIMARY KEY,
        eval_case_id TEXT NOT NULL,
        eval_case_version TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'pending', 'running', 'passed', 'failed', 'blocked', 'canceled'
        )),
        threshold REAL NOT NULL CHECK (threshold >= 0 AND threshold <= 1),
        score REAL CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
        run_id TEXT,
        trace_id TEXT,
        evidence_refs_json TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (eval_case_id, eval_case_version)
            REFERENCES mc_eval_cases(eval_case_id, version),
        FOREIGN KEY (run_id) REFERENCES mc_runs(run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_eval_runs_case ON mc_eval_runs(eval_case_id, eval_case_version, created_at)",
    """CREATE TABLE IF NOT EXISTS mc_eval_findings (
        finding_id TEXT PRIMARY KEY,
        eval_run_id TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
        summary TEXT NOT NULL,
        remediation_owner TEXT NOT NULL,
        status TEXT NOT NULL,
        defect_ref TEXT,
        evidence_refs_json TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (eval_run_id) REFERENCES mc_eval_runs(eval_run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_eval_findings_run ON mc_eval_findings(eval_run_id, severity, created_at)",
    """CREATE TABLE IF NOT EXISTS mc_runtime_preferences (
        preference_key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        value_hash TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_by TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS mc_rollout_comparisons (
        comparison_id TEXT PRIMARY KEY,
        stage TEXT NOT NULL CHECK (stage IN ('direct_chat','read_chat','actions','agent')),
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        legacy_route TEXT NOT NULL,
        runtime_route TEXT NOT NULL,
        legacy_manifest_hash TEXT NOT NULL,
        runtime_manifest_hash TEXT NOT NULL,
        legacy_policy TEXT NOT NULL,
        runtime_policy TEXT NOT NULL,
        legacy_outcome TEXT NOT NULL,
        runtime_outcome TEXT NOT NULL,
        legacy_latency_ms INTEGER NOT NULL CHECK (legacy_latency_ms >= 0),
        runtime_latency_ms INTEGER NOT NULL CHECK (runtime_latency_ms >= 0),
        passed INTEGER NOT NULL CHECK (passed IN (0,1)),
        reasons_json TEXT NOT NULL,
        evidence_refs_json TEXT NOT NULL,
        input_hash TEXT NOT NULL,
        actor TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (stage, sequence)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_rollout_stage_sequence ON mc_rollout_comparisons(stage,sequence DESC)",
    """CREATE TRIGGER IF NOT EXISTS mc_rollout_comparisons_update_guard
        BEFORE UPDATE ON mc_rollout_comparisons BEGIN
            SELECT RAISE(ABORT, 'rollout comparison history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_rollout_comparisons_delete_guard
        BEFORE DELETE ON mc_rollout_comparisons BEGIN
            SELECT RAISE(ABORT, 'rollout comparison history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_eval_cases_update_guard
        BEFORE UPDATE ON mc_eval_cases BEGIN
            SELECT RAISE(ABORT, 'mc_eval_cases versions are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_eval_cases_delete_guard
        BEFORE DELETE ON mc_eval_cases BEGIN
            SELECT RAISE(ABORT, 'mc_eval_cases history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_eval_runs_update_guard
        BEFORE UPDATE ON mc_eval_runs BEGIN
            SELECT RAISE(ABORT, 'mc_eval_runs history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_eval_runs_delete_guard
        BEFORE DELETE ON mc_eval_runs BEGIN
            SELECT RAISE(ABORT, 'mc_eval_runs history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_eval_findings_update_guard
        BEFORE UPDATE ON mc_eval_findings BEGIN
            SELECT RAISE(ABORT, 'mc_eval_findings history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_eval_findings_delete_guard
        BEFORE DELETE ON mc_eval_findings BEGIN
            SELECT RAISE(ABORT, 'mc_eval_findings history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_events_update_immutable
        BEFORE UPDATE ON mc_run_events BEGIN
            SELECT RAISE(ABORT, 'mc_run_events is append-only');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_events_delete_immutable
        BEFORE DELETE ON mc_run_events BEGIN
            SELECT RAISE(ABORT, 'mc_run_events is append-only');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_change_events_update_immutable
        BEFORE UPDATE ON mc_change_events BEGIN
            SELECT RAISE(ABORT, 'mc_change_events is append-only');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_change_events_delete_immutable
        BEFORE DELETE ON mc_change_events BEGIN
            SELECT RAISE(ABORT, 'mc_change_events is append-only');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_runs (
        run_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL,
        request_json TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        surface TEXT NOT NULL,
        mode TEXT NOT NULL,
        objective TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'accepted', 'routing', 'clarifying', 'planned', 'waiting_approval',
            'running', 'waiting_external', 'recovering', 'waiting_owner',
            'succeeded', 'failed', 'cancelled'
        )),
        version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
        plan_id TEXT,
        plan_version TEXT,
        plan_hash TEXT,
        budget_profile TEXT NOT NULL,
        budget_json TEXT NOT NULL DEFAULT '{}',
        contract_version TEXT NOT NULL DEFAULT '1',
        legacy_run_id TEXT,
        legacy_action_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        cancel_requested_at TEXT,
        cancel_requested_by TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_runs_status_time ON mc_runs(status, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_mc_runs_session ON mc_runs(session_id, created_at)",
    """CREATE TABLE IF NOT EXISTS mc_run_steps (
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        plan_version TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (position >= 0),
        kind TEXT NOT NULL,
        tool_name TEXT,
        arguments_json TEXT NOT NULL DEFAULT '{}',
        depends_on_json TEXT NOT NULL DEFAULT '[]',
        risk TEXT NOT NULL,
        timeout_s INTEGER NOT NULL DEFAULT 0 CHECK (timeout_s >= 0),
        retry_policy TEXT NOT NULL,
        idempotency_key TEXT,
        required_capabilities_json TEXT NOT NULL DEFAULT '[]',
        output_contract_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        lease_owner TEXT,
        lease_token_hash TEXT,
        lease_expires_at TEXT,
        lease_epoch INTEGER NOT NULL DEFAULT 0 CHECK (lease_epoch >= 0),
        last_error_json TEXT,
        last_error_hash TEXT,
        next_attempt_at TEXT,
        PRIMARY KEY (run_id, step_id),
        UNIQUE (run_id, position),
        FOREIGN KEY (run_id) REFERENCES mc_runs(run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_steps_runnable ON mc_run_steps(status, run_id, position)",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_steps_idempotency ON mc_run_steps(idempotency_key)",
    """CREATE TABLE IF NOT EXISTS mc_idempotency (
        idempotency_key TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        call_id TEXT NOT NULL,
        tool_ref TEXT NOT NULL,
        target TEXT NOT NULL,
        request_json TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'in_progress', 'completed', 'reconciliation_required', 'retry_allowed'
        )),
        execution_count INTEGER NOT NULL DEFAULT 1 CHECK (execution_count > 0),
        lease_epoch INTEGER NOT NULL CHECK (lease_epoch > 0),
        worker_id TEXT NOT NULL,
        receipt_id TEXT,
        result_json TEXT NOT NULL DEFAULT '{}',
        result_hash TEXT,
        reconciliation_outcome TEXT CHECK (
            reconciliation_outcome IS NULL OR
            reconciliation_outcome IN ('direct', 'applied', 'not_applied', 'unknown', 'cancelled')
        ),
        reconciliation_json TEXT NOT NULL DEFAULT '{}',
        reconciliation_hash TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        UNIQUE (run_id, step_id),
        FOREIGN KEY (run_id, step_id) REFERENCES mc_run_steps(run_id, step_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_idempotency_status ON mc_idempotency(status, updated_at)",
    """CREATE TRIGGER IF NOT EXISTS mc_idempotency_identity_guard
        BEFORE UPDATE OF idempotency_key, run_id, step_id, call_id, tool_ref,
                         target, request_json, request_hash, created_at
        ON mc_idempotency BEGIN
            SELECT RAISE(ABORT, 'mc_idempotency identity is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_idempotency_lifecycle_guard
        BEFORE UPDATE OF status ON mc_idempotency
        WHEN NOT (
            (OLD.status='in_progress' AND NEW.status IN (
                'completed', 'reconciliation_required', 'retry_allowed'
            )) OR
            (OLD.status='reconciliation_required' AND NEW.status IN (
                'completed', 'reconciliation_required', 'retry_allowed'
            )) OR
            (OLD.status='retry_allowed' AND NEW.status='in_progress')
        )
        BEGIN
            SELECT RAISE(ABORT, 'illegal mc_idempotency lifecycle transition');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_idempotency_delete_guard
        BEFORE DELETE ON mc_idempotency BEGIN
            SELECT RAISE(ABORT, 'mc_idempotency history cannot be deleted');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_action_receipts (
        receipt_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        tool_ref TEXT NOT NULL,
        target TEXT NOT NULL,
        effect_summary TEXT NOT NULL,
        before_ref TEXT,
        after_ref TEXT,
        external_ref TEXT,
        approval_ref TEXT,
        result_json TEXT NOT NULL,
        result_hash TEXT NOT NULL,
        reconciliation_outcome TEXT NOT NULL CHECK (
            reconciliation_outcome IN ('direct', 'applied')
        ),
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        actor TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (idempotency_key) REFERENCES mc_idempotency(idempotency_key),
        FOREIGN KEY (run_id, step_id) REFERENCES mc_run_steps(run_id, step_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_action_receipts_run ON mc_action_receipts(run_id, step_id, created_at)",
    """CREATE TRIGGER IF NOT EXISTS mc_action_receipts_update_guard
        BEFORE UPDATE ON mc_action_receipts BEGIN
            SELECT RAISE(ABORT, 'mc_action_receipts is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_action_receipts_delete_guard
        BEFORE DELETE ON mc_action_receipts BEGIN
            SELECT RAISE(ABORT, 'mc_action_receipts is immutable');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_policy_decisions (
        decision_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        step_id TEXT,
        tool_ref TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        effect TEXT NOT NULL CHECK (effect IN ('allow', 'require_approval', 'deny')),
        input_json TEXT NOT NULL,
        input_hash TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        decision_hash TEXT NOT NULL,
        actor TEXT NOT NULL,
        contract_version TEXT NOT NULL DEFAULT '1',
        created_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES mc_runs(run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_policy_decisions_run ON mc_policy_decisions(run_id, created_at, decision_id)",
    """CREATE TRIGGER IF NOT EXISTS mc_policy_decisions_update_guard
        BEFORE UPDATE ON mc_policy_decisions BEGIN
            SELECT RAISE(ABORT, 'mc_policy_decisions is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_policy_decisions_delete_guard
        BEFORE DELETE ON mc_policy_decisions BEGIN
            SELECT RAISE(ABORT, 'mc_policy_decisions is immutable');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_run_approvals (
        approval_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        policy_decision_id TEXT NOT NULL UNIQUE,
        owner_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        tool_ref TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK (
            status IN ('pending', 'approved', 'rejected', 'expired')
        ),
        request_json TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        response_json TEXT,
        response_hash TEXT,
        requested_by TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        decided_by TEXT,
        decided_at TEXT,
        contract_version TEXT NOT NULL DEFAULT '1',
        CHECK (
            (status = 'pending' AND response_json IS NULL AND response_hash IS NULL
             AND decided_by IS NULL AND decided_at IS NULL)
            OR
            (status IN ('approved', 'rejected', 'expired')
             AND response_json IS NOT NULL AND response_hash IS NOT NULL
             AND decided_by IS NOT NULL AND decided_at IS NOT NULL)
        ),
        FOREIGN KEY (run_id, step_id) REFERENCES mc_run_steps(run_id, step_id),
        FOREIGN KEY (policy_decision_id) REFERENCES mc_policy_decisions(decision_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_approvals_run ON mc_run_approvals(run_id, requested_at, approval_id)",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_approvals_pending ON mc_run_approvals(status, expires_at)",
    """CREATE TRIGGER IF NOT EXISTS mc_run_approvals_identity_guard
        BEFORE UPDATE OF approval_id, run_id, step_id, policy_decision_id,
                         owner_id, session_id, tool_ref, request_json, request_hash,
                         requested_by, requested_at, expires_at, contract_version
        ON mc_run_approvals BEGIN
            SELECT RAISE(ABORT, 'mc_run_approvals identity is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_approvals_lifecycle_guard
        BEFORE UPDATE OF status, response_json, response_hash, decided_by, decided_at
        ON mc_run_approvals
        WHEN OLD.status != 'pending'
          OR NEW.status NOT IN ('approved', 'rejected', 'expired')
          OR NEW.response_json IS NULL
          OR NEW.response_hash IS NULL
          OR NEW.decided_by IS NULL
          OR NEW.decided_at IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'mc_run_approvals can only resolve once');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_approvals_delete_guard
        BEFORE DELETE ON mc_run_approvals BEGIN
            SELECT RAISE(ABORT, 'mc_run_approvals history is immutable');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_terminal_jobs (
        job_id TEXT PRIMARY KEY,
        start_idempotency_key TEXT NOT NULL UNIQUE,
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        call_id TEXT NOT NULL,
        tool_ref TEXT NOT NULL,
        target TEXT NOT NULL,
        operation TEXT NOT NULL CHECK (operation = 'wait'),
        command_sha256 TEXT NOT NULL CHECK (length(command_sha256) = 64),
        working_directory_sha256 TEXT NOT NULL CHECK (
            length(working_directory_sha256) = 64
        ),
        duration_s INTEGER NOT NULL CHECK (duration_s BETWEEN 1 AND 300),
        status TEXT NOT NULL CHECK (status IN (
            'intent', 'launching', 'running', 'succeeded', 'failed', 'not_started'
        )),
        launch_count INTEGER NOT NULL DEFAULT 0 CHECK (launch_count >= 0),
        worker_identity_sha256 TEXT CHECK (
            worker_identity_sha256 IS NULL OR length(worker_identity_sha256) = 64
        ),
        output TEXT NOT NULL DEFAULT '' CHECK (length(output) <= 6000),
        output_sha256 TEXT NOT NULL CHECK (length(output_sha256) = 64),
        output_truncated INTEGER NOT NULL DEFAULT 0 CHECK (output_truncated IN (0, 1)),
        exit_code INTEGER,
        error_code TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        launch_started_at TEXT,
        worker_started_at TEXT,
        heartbeat_at TEXT,
        completed_at TEXT,
        cancel_idempotency_key TEXT,
        cancel_requested_at TEXT,
        cancel_requested_by TEXT,
        cancel_acknowledged_at TEXT,
        version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
        FOREIGN KEY (start_idempotency_key) REFERENCES mc_idempotency(idempotency_key),
        FOREIGN KEY (run_id, step_id) REFERENCES mc_run_steps(run_id, step_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_terminal_jobs_run ON mc_terminal_jobs(run_id, created_at, job_id)",
    "CREATE INDEX IF NOT EXISTS idx_mc_terminal_jobs_status ON mc_terminal_jobs(status, heartbeat_at, updated_at)",
    """CREATE TRIGGER IF NOT EXISTS mc_terminal_jobs_identity_guard
        BEFORE UPDATE OF job_id, start_idempotency_key, run_id, step_id, call_id,
                         tool_ref, target, operation, command_sha256,
                         working_directory_sha256, duration_s, created_at
        ON mc_terminal_jobs BEGIN
            SELECT RAISE(ABORT, 'mc_terminal_jobs identity is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_terminal_jobs_lifecycle_guard
        BEFORE UPDATE OF status ON mc_terminal_jobs
        WHEN OLD.status != NEW.status AND NOT (
            (OLD.status='intent' AND NEW.status IN ('launching', 'not_started')) OR
            (OLD.status='not_started' AND NEW.status='launching') OR
            (OLD.status='launching' AND NEW.status IN ('running', 'not_started')) OR
            (OLD.status='running' AND NEW.status IN ('succeeded', 'failed'))
        )
        BEGIN
            SELECT RAISE(ABORT, 'illegal mc_terminal_jobs lifecycle transition');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_terminal_jobs_terminal_guard
        BEFORE UPDATE ON mc_terminal_jobs
        WHEN OLD.status IN ('succeeded', 'failed') AND (
            NEW.status IS NOT OLD.status OR
            NEW.launch_count IS NOT OLD.launch_count OR
            NEW.worker_identity_sha256 IS NOT OLD.worker_identity_sha256 OR
            NEW.output IS NOT OLD.output OR
            NEW.output_sha256 IS NOT OLD.output_sha256 OR
            NEW.output_truncated IS NOT OLD.output_truncated OR
            NEW.exit_code IS NOT OLD.exit_code OR
            NEW.error_code IS NOT OLD.error_code OR
            NEW.updated_at IS NOT OLD.updated_at OR
            NEW.launch_started_at IS NOT OLD.launch_started_at OR
            NEW.worker_started_at IS NOT OLD.worker_started_at OR
            NEW.heartbeat_at IS NOT OLD.heartbeat_at OR
            NEW.completed_at IS NOT OLD.completed_at OR
            NEW.version IS NOT OLD.version
        )
        BEGIN
            SELECT RAISE(ABORT, 'completed mc_terminal_jobs rows are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_terminal_jobs_delete_guard
        BEFORE DELETE ON mc_terminal_jobs BEGIN
            SELECT RAISE(ABORT, 'mc_terminal_jobs history cannot be deleted');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_run_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        lease_epoch INTEGER NOT NULL CHECK (lease_epoch > 0),
        worker_id TEXT NOT NULL,
        state_json TEXT NOT NULL,
        state_hash TEXT NOT NULL,
        contract_version TEXT NOT NULL DEFAULT '1',
        created_at TEXT NOT NULL,
        UNIQUE (run_id, sequence),
        FOREIGN KEY (run_id, step_id) REFERENCES mc_run_steps(run_id, step_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_checkpoints_step ON mc_run_checkpoints(run_id, step_id, sequence)",
    """CREATE TRIGGER IF NOT EXISTS mc_run_checkpoints_update_guard
        BEFORE UPDATE ON mc_run_checkpoints BEGIN
            SELECT RAISE(ABORT, 'mc_run_checkpoints is append-only');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_checkpoints_delete_guard
        BEFORE DELETE ON mc_run_checkpoints BEGIN
            SELECT RAISE(ABORT, 'mc_run_checkpoints is append-only');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_run_commands (
        command_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        action TEXT NOT NULL CHECK (action IN (
            'resume', 'retry_step', 'skip_step', 'revise', 'provide_input',
            'approve', 'reject', 'cancel'
        )),
        payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        expected_run_version INTEGER NOT NULL CHECK (expected_run_version > 0),
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'consumed')),
        actor TEXT NOT NULL,
        consumed_by TEXT,
        contract_version TEXT NOT NULL DEFAULT '1',
        created_at TEXT NOT NULL,
        consumed_at TEXT,
        FOREIGN KEY (run_id) REFERENCES mc_runs(run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_run_commands_pending ON mc_run_commands(run_id, status, created_at, command_id)",
    """CREATE TRIGGER IF NOT EXISTS mc_run_commands_identity_guard
        BEFORE UPDATE OF command_id, run_id, action, payload_json, payload_hash,
                         expected_run_version, actor, contract_version, created_at
        ON mc_run_commands BEGIN
            SELECT RAISE(ABORT, 'mc_run_commands identity is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_commands_lifecycle_guard
        BEFORE UPDATE OF status, consumed_by, consumed_at
        ON mc_run_commands
        WHEN OLD.status != 'pending'
          OR NEW.status != 'consumed'
          OR NEW.consumed_by IS NULL
          OR NEW.consumed_at IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'mc_run_commands can only be consumed once');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_run_commands_delete_guard
        BEFORE DELETE ON mc_run_commands BEGIN
            SELECT RAISE(ABORT, 'mc_run_commands history is immutable');
        END""",
    """CREATE TABLE IF NOT EXISTS mc_loop_recipes (
        recipe_id TEXT NOT NULL,
        version TEXT NOT NULL,
        name TEXT NOT NULL,
        loop_type TEXT NOT NULL,
        contract_json TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (recipe_id, version)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_loop_recipes_type ON mc_loop_recipes(loop_type, recipe_id, version)",
    """CREATE TABLE IF NOT EXISTS mc_loop_runs (
        run_id TEXT PRIMARY KEY,
        recipe_id TEXT NOT NULL,
        recipe_version TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        policy_decision_id TEXT NOT NULL,
        loop_type TEXT NOT NULL,
        policy_json TEXT NOT NULL,
        policy_hash TEXT NOT NULL,
        owner_override_json TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
        iteration INTEGER NOT NULL DEFAULT 0 CHECK (iteration >= 0),
        loop_version INTEGER NOT NULL DEFAULT 0 CHECK (loop_version >= 0),
        model_calls INTEGER NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
        tool_calls INTEGER NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
        prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
        completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
        runtime_ms INTEGER NOT NULL DEFAULT 0 CHECK (runtime_ms >= 0),
        cost_microusd INTEGER NOT NULL DEFAULT 0 CHECK (cost_microusd >= 0),
        download_bytes INTEGER NOT NULL DEFAULT 0 CHECK (download_bytes >= 0),
        storage_bytes INTEGER NOT NULL DEFAULT 0 CHECK (storage_bytes >= 0),
        status TEXT NOT NULL DEFAULT 'accepted',
        stop_reason TEXT,
        started_at TEXT,
        stopped_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES mc_runs(run_id),
        FOREIGN KEY (recipe_id, recipe_version) REFERENCES mc_loop_recipes(recipe_id, version)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_loop_runs_status ON mc_loop_runs(status, updated_at)",
    """CREATE TABLE IF NOT EXISTS mc_loop_iterations (
        iteration_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        iteration INTEGER NOT NULL CHECK (iteration > 0),
        started_run_version INTEGER NOT NULL CHECK (started_run_version > 0),
        finished_run_version INTEGER,
        actor TEXT NOT NULL,
        finished_by TEXT,
        start_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'stopped')),
        usage_json TEXT NOT NULL DEFAULT '{}',
        usage_hash TEXT,
        result_json TEXT NOT NULL DEFAULT '{}',
        result_hash TEXT,
        contract_version TEXT NOT NULL DEFAULT '1',
        started_at TEXT NOT NULL,
        completed_at TEXT,
        UNIQUE (run_id, iteration),
        FOREIGN KEY (run_id) REFERENCES mc_loop_runs(run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mc_loop_iterations_run ON mc_loop_iterations(run_id, iteration)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mc_loop_iterations_active ON mc_loop_iterations(run_id) WHERE status='running'",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_iterations_identity_guard
        BEFORE UPDATE OF iteration_id, run_id, iteration, started_run_version,
                         actor, start_hash, contract_version, started_at
        ON mc_loop_iterations BEGIN
            SELECT RAISE(ABORT, 'mc_loop_iterations identity is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_iterations_lifecycle_guard
        BEFORE UPDATE OF status, finished_run_version, finished_by, usage_json,
                         usage_hash, result_json, result_hash, completed_at
        ON mc_loop_iterations
        WHEN OLD.status != 'running'
          OR NEW.status NOT IN ('completed', 'stopped')
          OR NEW.finished_run_version IS NULL
          OR NEW.finished_by IS NULL
          OR NEW.usage_hash IS NULL
          OR NEW.result_hash IS NULL
          OR NEW.completed_at IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'mc_loop_iterations can only finish once');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_iterations_delete_guard
        BEFORE DELETE ON mc_loop_iterations BEGIN
            SELECT RAISE(ABORT, 'mc_loop_iterations history is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_recipes_update_guard
        BEFORE UPDATE ON mc_loop_recipes BEGIN
            SELECT RAISE(ABORT, 'mc_loop_recipes versions are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_recipes_delete_guard
        BEFORE DELETE ON mc_loop_recipes BEGIN
            SELECT RAISE(ABORT, 'mc_loop_recipes versions are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_runs_policy_guard
        BEFORE UPDATE OF recipe_id, recipe_version, policy_id, policy_version,
                         policy_decision_id, loop_type, policy_json, policy_hash,
                         owner_override_json, enabled
        ON mc_loop_runs BEGIN
            SELECT RAISE(ABORT, 'effective loop policy snapshots are immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_loop_runs_delete_guard
        BEFORE DELETE ON mc_loop_runs BEGIN
            SELECT RAISE(ABORT, 'effective loop policy snapshots are immutable');
        END""",
)

_TERMINAL_JOB_CANCEL_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_mc_terminal_jobs_cancel_request "
    "ON mc_terminal_jobs(cancel_requested_at, cancel_acknowledged_at, status)",
    """CREATE TRIGGER IF NOT EXISTS mc_terminal_jobs_cancel_request_guard
        BEFORE UPDATE OF cancel_idempotency_key, cancel_requested_at, cancel_requested_by
        ON mc_terminal_jobs
        WHEN NOT (
            OLD.cancel_idempotency_key IS NULL AND
            OLD.cancel_requested_at IS NULL AND
            OLD.cancel_requested_by IS NULL AND
            NEW.cancel_idempotency_key IS NOT NULL AND
            length(trim(NEW.cancel_idempotency_key)) > 0 AND
            NEW.cancel_requested_at IS NOT NULL AND
            length(trim(NEW.cancel_requested_at)) > 0 AND
            NEW.cancel_requested_by IS NOT NULL AND
            length(trim(NEW.cancel_requested_by)) > 0 AND
            OLD.status IN ('launching', 'running') AND
            EXISTS (
                SELECT 1
                FROM mc_idempotency AS i
                JOIN mc_runs AS r ON r.run_id=i.run_id
                WHERE i.idempotency_key=NEW.cancel_idempotency_key
                  AND i.tool_ref='tobi.terminal.cancel_job@1'
                  AND i.target='terminal:job:' || OLD.job_id || ':cancel'
                  AND i.status='in_progress'
                  AND r.owner_id=NEW.cancel_requested_by
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'mc_terminal_jobs cancellation request is immutable');
        END""",
    """CREATE TRIGGER IF NOT EXISTS mc_terminal_jobs_cancel_ack_guard
        BEFORE UPDATE OF cancel_acknowledged_at ON mc_terminal_jobs
        WHEN NOT (
            OLD.cancel_acknowledged_at IS NULL AND
            NEW.cancel_acknowledged_at IS NOT NULL AND
            length(trim(NEW.cancel_acknowledged_at)) > 0 AND
            OLD.cancel_idempotency_key IS NOT NULL AND
            OLD.cancel_requested_at IS NOT NULL AND
            OLD.cancel_requested_by IS NOT NULL AND
            OLD.status='running' AND
            NEW.status='failed' AND
            NEW.error_code='managed_job_cancelled'
        )
        BEGIN
            SELECT RAISE(ABORT, 'mc_terminal_jobs cancellation acknowledgement is invalid');
        END""",
)


def _schema_is_ready(conn: sqlite3.Connection) -> bool:
    ledger = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if ledger is None:
        return False
    versions = {
        row[0]
        for row in conn.execute(
            "SELECT version FROM schema_migrations WHERE version LIKE 'mc-runtime-v2-%'"
        ).fetchall()
    }
    if not set(RUNTIME_SCHEMA_VERSIONS).issubset(versions):
        return False
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'mc_*'"
        ).fetchall()
    }
    if not _RUNTIME_TABLES.issubset(tables):
        return False
    step_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(mc_run_steps)").fetchall()
    }
    run_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(mc_runs)").fetchall()
    }
    loop_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(mc_loop_runs)").fetchall()
    }
    terminal_job_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(mc_terminal_jobs)").fetchall()
    }
    terminal_job_objects = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE name IN (?,?,?)",
            tuple(sorted(_TERMINAL_JOB_CANCEL_OBJECTS)),
        ).fetchall()
    }
    return (
        set(_STEP_LEASE_COLUMNS).issubset(step_columns)
        and set(_STEP_CONTROL_COLUMNS).issubset(step_columns)
        and set(_RUN_CONTROL_COLUMNS).issubset(run_columns)
        and set(_LOOP_CONTROL_COLUMNS).issubset(loop_columns)
        and set(_TERMINAL_JOB_CANCEL_COLUMNS).issubset(terminal_job_columns)
        and _TERMINAL_JOB_CANCEL_OBJECTS.issubset(terminal_job_objects)
    )


def _apply_runtime_schema(conn: sqlite3.Connection) -> None:
    conn.execute("SAVEPOINT mc_runtime_schema")
    try:
        for statement in _STATEMENTS:
            conn.execute(statement)
        step_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(mc_run_steps)").fetchall()
        }
        for name, declaration in {
            **_STEP_LEASE_COLUMNS,
            **_STEP_CONTROL_COLUMNS,
        }.items():
            if name not in step_columns:
                conn.execute(
                    f"ALTER TABLE mc_run_steps ADD COLUMN {name} {declaration}"
                )
        run_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(mc_runs)").fetchall()
        }
        for name, declaration in _RUN_CONTROL_COLUMNS.items():
            if name not in run_columns:
                conn.execute(f"ALTER TABLE mc_runs ADD COLUMN {name} {declaration}")
        loop_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(mc_loop_runs)").fetchall()
        }
        for name, declaration in _LOOP_CONTROL_COLUMNS.items():
            if name not in loop_columns:
                conn.execute(
                    f"ALTER TABLE mc_loop_runs ADD COLUMN {name} {declaration}"
                )
        terminal_job_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(mc_terminal_jobs)").fetchall()
        }
        for name, declaration in _TERMINAL_JOB_CANCEL_COLUMNS.items():
            if name not in terminal_job_columns:
                conn.execute(
                    f"ALTER TABLE mc_terminal_jobs ADD COLUMN {name} {declaration}"
                )
        for statement in _TERMINAL_JOB_CANCEL_STATEMENTS:
            conn.execute(statement)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mc_run_steps_lease "
            "ON mc_run_steps(status, lease_expires_at, run_id, position)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mc_run_steps_retry_due "
            "ON mc_run_steps(status, next_attempt_at, run_id, position)"
        )
        # `schema_migrations` is shared with Chat's runtime, which creates it without a default
        # for `applied_at`. Leaving that column out therefore breaks NOT NULL on any database
        # where Chat got there first -- and `OR IGNORE` swallows that violation silently, so
        # the ledger stayed empty, `_schema_is_ready` answered False forever, and this whole
        # schema was re-applied on every runtime call. Supply every column we depend on.
        applied_at = _now()
        conn.executemany(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            [(version, applied_at) for version in RUNTIME_SCHEMA_VERSIONS],
        )
        conn.execute("RELEASE SAVEPOINT mc_runtime_schema")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT mc_runtime_schema")
        conn.execute("RELEASE SAVEPOINT mc_runtime_schema")
        raise


def _ensure_runtime_schema(conn: sqlite3.Connection) -> None:
    """Create Runtime V2 tables without modifying any legacy runtime table."""
    if _schema_is_ready(conn):
        return
    with _SCHEMA_LOCK:
        if not _schema_is_ready(conn):
            _apply_runtime_schema(conn)
