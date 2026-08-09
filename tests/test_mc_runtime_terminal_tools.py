"""T07 Run 3A/3B1: dormant bounded foreground terminal execution."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any


TMP = Path(tempfile.mkdtemp(prefix="tobi_t07_terminal_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ApprovalMode,
    ApprovalStatus,
    BudgetStatus,
    Certainty,
    ExecutionPlan,
    IsolationLevel,
    LoopPolicy,
    LoopRecipe,
    LoopType,
    PlanStep,
    PolicyInput,
    RiskLevel,
    RunRequest,
    SideEffectClass,
    Surface,
    TrustClass,
    contract_to_dict,
)
from core.runtime.actions import ActionConflictError  # noqa: E402
from core.runtime.event_store import list_run_events  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.runtime.terminal_tools import (  # noqa: E402
    RUN_COMMAND_ACTION_REF,
    RUN_COMMAND_REF,
    TERMINAL_STATUS_REF,
    build_terminal_tool_runtime,
)
from core.runtime.tool_catalog import ToolCallPreparationError  # noqa: E402
from core.runtime.tool_execution import ToolExecutionError  # noqa: E402


PASS = 0


def ok(name: str, condition: bool, detail: object = "") -> None:
    global PASS
    if not condition:
        print(f"FAIL {name}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"PASS {name}")


def raises(error_type: type[Exception], callback) -> Exception | None:
    try:
        callback()
    except error_type as exc:
        return exc
    return None


def query_count(table: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])
    finally:
        conn.close()


def query_one(sql: str, parameters: tuple = ()) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(sql, parameters).fetchone()
    finally:
        conn.close()


def command_target(command: str) -> str:
    digest = hashlib.sha256(command.encode("utf-8")).hexdigest()
    return f"terminal:inspect:sha256:{digest}"


def action_target(command: str, directory: Path = ROOT) -> str:
    command_digest = hashlib.sha256(command.encode("utf-8")).hexdigest()
    directory_digest = hashlib.sha256(
        str(directory.resolve()).encode("utf-8")
    ).hexdigest()
    return (
        f"terminal:action:cwd-sha256:{directory_digest}:"
        f"command-sha256:{command_digest}"
    )


def prepare_run(
    repository: RuntimeRepository,
    *,
    run_id: str,
    tool_ref: str,
    arguments: dict[str, Any],
    surface: Surface,
    mode: str,
    idempotency_key: str | None = None,
) -> tuple[str, dict]:
    step_id = f"step-{run_id}"
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="Terminal tool fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Use the local terminal through a bounded contract",
        stop_condition="typed terminal result persisted",
        max_attempts=1,
        max_runtime_s=60,
        max_cost_usd=1.0,
        allowed_tools=(tool_ref,),
    )
    repository.save_loop_recipe(recipe)
    repository.create_run(
        RunRequest(
            request_id=f"request-{run_id}",
            surface=surface,
            owner_id="owner",
            session_id="session-t07-run3a",
            mode=mode,
            message="Use the local terminal safely",
        ),
        loop_policy=LoopPolicy.from_recipe(
            policy_id=f"loop-policy-{run_id}",
            version="1",
            recipe=recipe,
            policy_decision_id=f"bootstrap-{run_id}",
            enabled=True,
        ),
        run_id=run_id,
    )
    repository.transition_run(
        run_id,
        RunStatus.ROUTING,
        expected_version=1,
        actor="runtime-test",
    )
    repository.save_plan(
        ExecutionPlan(
            plan_id=f"plan-{run_id}",
            run_id=run_id,
            version="1",
            objective="Use the local terminal through a bounded contract",
            steps=(
                PlanStep(
                    step_id=step_id,
                    kind="tool",
                    risk=(
                        RiskLevel.HIGH
                        if tool_ref == RUN_COMMAND_ACTION_REF
                        else RiskLevel.LOW
                        if tool_ref == RUN_COMMAND_REF
                        else RiskLevel.NONE
                    ),
                    tool_name=tool_ref,
                    arguments=arguments,
                    retry_policy="none",
                    idempotency_key=idempotency_key,
                ),
            ),
        ),
        expected_version=2,
        actor="runtime-test",
    )
    repository.transition_run(
        run_id,
        RunStatus.RUNNING,
        expected_version=3,
        actor="runtime-test",
    )
    lease = repository.claim_step(run_id, worker_id=f"worker-{run_id}")
    assert lease is not None
    return step_id, lease


def execute(
    runtime,
    repository: RuntimeRepository,
    *,
    run_id: str,
    tool_ref: str,
    arguments: dict[str, Any],
    surface: Surface,
    mode: str,
    target: str,
    permissions: tuple[str, ...],
    isolations: tuple[IsolationLevel, ...],
    idempotency_key: str | None = None,
    approval_mode: ApprovalMode = ApprovalMode.ALWAYS,
    approval_status: ApprovalStatus = ApprovalStatus.NONE,
    approval_id: str | None = None,
):
    step_id, lease = prepare_run(
        repository,
        run_id=run_id,
        tool_ref=tool_ref,
        arguments=arguments,
        surface=surface,
        mode=mode,
        idempotency_key=idempotency_key,
    )
    call = runtime.catalog.prepare_call(
        call_id=f"call-{run_id}",
        run_id=run_id,
        step_id=step_id,
        tool_ref=tool_ref,
        arguments=arguments,
        surface=surface,
        mode=mode,
        candidate_tool_refs=(tool_ref,),
        idempotency_key=idempotency_key,
        approval_id=approval_id,
    )
    facts = PolicyInput(
        decision_id=f"policy-{run_id}",
        run_id=run_id,
        step_id=step_id,
        owner_id="owner",
        session_id="session-t07-run3a",
        surface=surface,
        mode=mode,
        tool=runtime.catalog.get_spec(tool_ref),
        target=target,
        granted_permissions=permissions,
        trust_class=TrustClass.OWNER_DIRECT,
        certainty=Certainty.KNOWN,
        instruction_authority=True,
        available_isolations=isolations,
        budget_status=BudgetStatus.AVAILABLE,
        approval_mode=approval_mode,
        approval_status=approval_status,
        approval_id=approval_id,
    )
    result = runtime.execute(
        call,
        facts,
        worker_id=lease["worker_id"],
        lease_token=lease["lease_token"],
        lease_epoch=lease["lease_epoch"],
    )
    return result


def prepare_action(
    runtime,
    repository: RuntimeRepository,
    *,
    run_id: str,
    command: str,
    timeout: int = 60,
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    approval_id: str | None = None,
    directory: Path = ROOT,
):
    arguments = {"command": command, "timeout": timeout}
    step_id, lease = prepare_run(
        repository,
        run_id=run_id,
        tool_ref=RUN_COMMAND_ACTION_REF,
        arguments=arguments,
        surface=Surface.AGENT,
        mode="agent",
        idempotency_key=f"effect-{run_id}",
    )
    call = runtime.catalog.prepare_call(
        call_id=f"call-{run_id}",
        run_id=run_id,
        step_id=step_id,
        tool_ref=RUN_COMMAND_ACTION_REF,
        arguments=arguments,
        surface=Surface.AGENT,
        mode="agent",
        candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
        idempotency_key=f"effect-{run_id}",
        approval_id=approval_id,
    )
    facts = PolicyInput(
        decision_id=f"policy-{run_id}",
        run_id=run_id,
        step_id=step_id,
        owner_id="owner",
        session_id="session-t07-run3b1",
        surface=Surface.AGENT,
        mode="agent",
        tool=runtime.catalog.get_spec(RUN_COMMAND_ACTION_REF),
        target=action_target(command, directory),
        granted_permissions=("terminal.execute",),
        trust_class=TrustClass.OWNER_DIRECT,
        certainty=Certainty.KNOWN,
        instruction_authority=True,
        available_isolations=(IsolationLevel.SUBPROCESS,),
        budget_status=BudgetStatus.AVAILABLE,
        approval_mode=ApprovalMode.ASK,
        approval_status=approval_status,
        approval_id=approval_id,
    )
    return call, facts, lease


def execute_prepared(runtime, call, facts, lease):
    return runtime.execute(
        call,
        facts,
        worker_id=lease["worker_id"],
        lease_token=lease["lease_token"],
        lease_epoch=lease["lease_epoch"],
    )


SECRET = "terminal-secret-123456789"


class FakeTerminalEngine:
    def __init__(self) -> None:
        self.mode = "ask"
        self.enabled = True
        self.status_calls = 0
        self.gate_calls: list[dict[str, Any]] = []
        self.run_calls: list[dict[str, Any]] = []
        self.gate_results: list[dict[str, Any]] = []
        self.raise_on_run = False
        self.next_result: dict[str, Any] = {
            "ok": True,
            "exit_code": 0,
            "output": f"git version 2.0 {SECRET}",
            "truncated": False,
            "duration_ms": 12,
        }

    def status(self) -> dict[str, Any]:
        self.status_calls += 1
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "os": "Windows",
            "shell": "PowerShell",
            "cwd": "C:/private-owner-path",
            "package_managers": ["pip", "npm"],
            "tools_registered": 2,
            "modes": ["plan", "ask", "accept", "auto"],
        }

    def effective_mode(self, surface: str = "mc") -> str:
        return self.mode

    def gate(
        self, command: str, surface: str = "mc", use_llm: bool = False
    ) -> dict[str, Any]:
        self.gate_calls.append(
            {"command": command, "surface": surface, "use_llm": use_llm}
        )
        if self.gate_results:
            return self.gate_results.pop(0)
        read_only = command in {
            "Get-Location",
            "date",
            "git --version",
            "hostname",
            "node --version",
            "node -v",
            "pwd",
            "py --version",
            "py -V",
            "python --version",
            "python -V",
            "python3 --version",
            "python3 -V",
            "whoami",
        }
        risk = "low" if read_only else "medium"
        if not self.enabled:
            return {
                "decision": "refuse",
                "risk": "blocked",
                "reason": "terminal disabled",
                "mode": self.mode,
            }
        if self.mode == "plan":
            return {
                "decision": "plan",
                "risk": risk,
                "reason": "plan mode",
                "mode": self.mode,
            }
        if self.mode not in {"ask", "accept", "auto"}:
            return {
                "decision": "refuse",
                "risk": "blocked",
                "reason": "unknown mode",
                "mode": self.mode,
            }
        decision = "confirm" if self.mode == "ask" and risk != "low" else "run"
        return {
            "decision": decision,
            "risk": risk,
            "reason": "known-safe inspection command" if read_only else "local mutation",
            "mode": self.mode,
        }

    def run(self, command: str, **kwargs: Any) -> dict[str, Any]:
        self.run_calls.append({"command": command, **kwargs})
        if self.raise_on_run:
            raise RuntimeError("simulated terminal interruption")
        return dict(self.next_result)

    def redact(self, text: str) -> str:
        return str(text).replace(SECRET, "[REDACTED]")


init_database()
repository = RuntimeRepository()
fake = FakeTerminalEngine()
runtime = build_terminal_tool_runtime(engine=fake, working_directory=ROOT)

refs = tuple(entry.tool_ref for entry in runtime.catalog.manifest.entries)
run_spec = runtime.catalog.get_spec(RUN_COMMAND_REF)
action_spec = runtime.catalog.get_spec(RUN_COMMAND_ACTION_REF)
status_spec = runtime.catalog.get_spec(TERMINAL_STATUS_REF)
metadata_json = json.dumps(
    {
        "manifest": contract_to_dict(runtime.catalog.manifest),
        "specs": contract_to_dict((run_spec, action_spec, status_spec)),
    },
    sort_keys=True,
)
ok(
    "terminal catalog keeps two accepted reads and adds one separate bounded action",
    len(refs) == 3
    and set(refs) == {RUN_COMMAND_REF, RUN_COMMAND_ACTION_REF, TERMINAL_STATUS_REF}
    and run_spec.allowed_surfaces == (Surface.AGENT,)
    and run_spec.allowed_modes == ("agent",)
    and run_spec.required_permissions == ("terminal.execute",)
    and run_spec.side_effect_class is SideEffectClass.NONE
    and run_spec.risk is RiskLevel.LOW
    and run_spec.isolation == "subprocess"
    and run_spec.timeout_s == 30
    and run_spec.idempotency_policy == "none"
    and action_spec.allowed_surfaces == (Surface.AGENT,)
    and action_spec.allowed_modes == ("agent",)
    and action_spec.required_permissions == ("terminal.execute",)
    and action_spec.side_effect_class is SideEffectClass.IRREVERSIBLE
    and action_spec.risk is RiskLevel.HIGH
    and action_spec.isolation == "subprocess"
    and action_spec.timeout_s == 300
    and action_spec.retry_policy == "none"
    and action_spec.idempotency_policy == "required"
    and status_spec.allowed_surfaces == (Surface.CHAT, Surface.AGENT)
    and status_spec.allowed_modes == ("chat", "agent")
    and status_spec.required_permissions == ("terminal.read",)
    and status_spec.side_effect_class is SideEffectClass.NONE
    and status_spec.isolation == "in_process"
    and set(run_spec.input_schema["properties"]) == {"command", "timeout"}
    and set(action_spec.input_schema["properties"]) == {"command", "timeout"}
    and str(ROOT).lower() not in metadata_json.lower()
    and "callable" not in metadata_json.lower()
    and "function" not in metadata_json.lower(),
    metadata_json,
)

blocked_commands = (
    "",
    "git status",
    "git status; whoami",
    "git status | whoami",
    "git status > result.txt",
    "$(whoami)",
    "`whoami`",
    "git status\nwhoami",
    "env",
    "printenv",
    "curl https://example.com",
    "pip install rich",
    "npm --version",
    "pnpm --version",
    "rm -rf build",
    "python -c print(1)",
    "unknown-command",
)
invalid_calls = [
    raises(
        ToolCallPreparationError,
        lambda command=command: runtime.catalog.prepare_call(
            call_id=f"invalid-{hashlib.sha256(command.encode()).hexdigest()[:8]}",
            run_id="invalid-run",
            step_id="invalid-step",
            tool_ref=RUN_COMMAND_REF,
            arguments={"command": command},
            surface=Surface.AGENT,
            mode="agent",
            candidate_tool_refs=(RUN_COMMAND_REF,),
        ),
    )
    for command in blocked_commands
]
invalid_calls.extend(
    (
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-cwd",
                run_id="invalid-run",
                step_id="invalid-step",
                tool_ref=RUN_COMMAND_REF,
                arguments={"command": "git --version", "cwd": "C:/"},
                surface=Surface.AGENT,
                mode="agent",
                candidate_tool_refs=(RUN_COMMAND_REF,),
            ),
        ),
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-background",
                run_id="invalid-run",
                step_id="invalid-step",
                tool_ref=RUN_COMMAND_REF,
                arguments={"command": "git --version", "background": True},
                surface=Surface.AGENT,
                mode="agent",
                candidate_tool_refs=(RUN_COMMAND_REF,),
            ),
        ),
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-timeout",
                run_id="invalid-run",
                step_id="invalid-step",
                tool_ref=RUN_COMMAND_REF,
                arguments={"command": "git --version", "timeout": 31},
                surface=Surface.AGENT,
                mode="agent",
                candidate_tool_refs=(RUN_COMMAND_REF,),
            ),
        ),
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-surface",
                run_id="invalid-run",
                step_id="invalid-step",
                tool_ref=RUN_COMMAND_REF,
                arguments={"command": "git --version"},
                surface=Surface.CHAT,
                mode="agent",
                candidate_tool_refs=(RUN_COMMAND_REF,),
            ),
        ),
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-mode",
                run_id="invalid-run",
                step_id="invalid-step",
                tool_ref=RUN_COMMAND_REF,
                arguments={"command": "git --version"},
                surface=Surface.AGENT,
                mode="chat",
                candidate_tool_refs=(RUN_COMMAND_REF,),
            ),
        ),
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-allowlist",
                run_id="invalid-run",
                step_id="invalid-step",
                tool_ref=RUN_COMMAND_REF,
                arguments={"command": "git --version"},
                surface=Surface.AGENT,
                mode="agent",
                candidate_tool_refs=(TERMINAL_STATUS_REF,),
            ),
        ),
    )
)
ok(
    "unsafe malformed caller-directed and non-allowlisted calls fail before terminal access",
    all(error is not None for error in invalid_calls)
    and not fake.gate_calls
    and not fake.run_calls,
    invalid_calls,
)

status_result = execute(
    runtime,
    repository,
    run_id="terminal-status",
    tool_ref=TERMINAL_STATUS_REF,
    arguments={},
    surface=Surface.CHAT,
    mode="chat",
    target="terminal:status",
    permissions=("terminal.read",),
    isolations=(IsolationLevel.IN_PROCESS,),
)
ok(
    "terminal status is schema validated without exposing the engine working directory",
    status_result.status == "succeeded"
    and status_result.typed_output
    == {
        "enabled": True,
        "mode": "ask",
        "os": "Windows",
        "shell": "PowerShell",
        "package_managers": ["pip", "npm"],
        "tools_registered": 2,
        "modes": ["plan", "ask", "accept", "auto"],
    }
    and status_result.receipt_id is None
    and fake.status_calls == 1
    and not fake.gate_calls,
    status_result,
)

safe_command = "git --version"
safe_hash = hashlib.sha256(safe_command.encode("utf-8")).hexdigest()
safe_result = execute(
    runtime,
    repository,
    run_id="terminal-safe-command",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": safe_command, "timeout": 5},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target(safe_command),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
)
ok(
    "allowlisted command passes central policy and both terminal gates with bounded redaction",
    safe_result.status == "succeeded"
    and safe_result.typed_output
    == {
        "state": "completed",
        "ok": True,
        "exit_code": 0,
        "output": "git version 2.0 [REDACTED]",
        "truncated": False,
        "duration_ms": 12,
        "command_sha256": safe_hash,
    }
    and safe_result.evidence_refs == (f"terminal:command:sha256:{safe_hash}",)
    and safe_result.receipt_id is None
    and len(fake.gate_calls) == 2
    and fake.gate_calls[-1]["use_llm"] is False
    and fake.run_calls
    and fake.run_calls[-1]
    == {
        "command": safe_command,
        "cwd": str(ROOT.resolve()),
        "timeout": 5,
        "background": False,
        "risk": "low",
        "mode": "ask",
        "surface": "mc",
    },
    safe_result,
)

run_count = len(fake.run_calls)
denied_permission = execute(
    runtime,
    repository,
    run_id="terminal-permission-denied",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "whoami"},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("whoami"),
    permissions=(),
    isolations=(IsolationLevel.SUBPROCESS,),
)
denied_isolation = execute(
    runtime,
    repository,
    run_id="terminal-isolation-denied",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "hostname"},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("hostname"),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.IN_PROCESS,),
)
ok(
    "missing permission or subprocess isolation blocks before command execution",
    denied_permission.status == "blocked"
    and denied_isolation.status == "blocked"
    and denied_permission.error is not None
    and denied_permission.error.code == "tool.policy_denied"
    and denied_isolation.error is not None
    and denied_isolation.error.code == "tool.policy_denied"
    and len(fake.run_calls) == run_count,
    (denied_permission, denied_isolation),
)

policy_denials = []
for run_id, mode, enabled, command in (
    ("terminal-plan-denied", "plan", True, "pwd"),
    ("terminal-unknown-denied", "mystery", True, "date"),
    ("terminal-disabled-denied", "ask", False, "git --version"),
):
    fake.mode = mode
    fake.enabled = enabled
    policy_denials.append(
        execute(
            runtime,
            repository,
            run_id=run_id,
            tool_ref=RUN_COMMAND_REF,
            arguments={"command": command},
            surface=Surface.AGENT,
            mode="agent",
            target=command_target(command),
            permissions=("terminal.execute",),
            isolations=(IsolationLevel.SUBPROCESS,),
        )
    )
fake.mode = "ask"
fake.enabled = True
ok(
    "plan unknown mode and kill-switch refusal tighten policy and invoke no command",
    all(result.status == "blocked" for result in policy_denials)
    and all(result.error is not None for result in policy_denials)
    and all(result.error.code == "tool.policy_denied" for result in policy_denials if result.error)
    and len(fake.run_calls) == run_count,
    policy_denials,
)

fake.gate_results = [
    {"decision": "run", "risk": "medium", "reason": "changed", "mode": "ask"}
]
risk_denied = execute(
    runtime,
    repository,
    run_id="terminal-risk-denied",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "date"},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("date"),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
)
ok(
    "terminal risk classification can tighten but never widen the command contract",
    risk_denied.status == "blocked"
    and risk_denied.error is not None
    and risk_denied.error.code == "tool.policy_denied"
    and len(fake.run_calls) == run_count,
    risk_denied,
)

fake.gate_results = [
    {"decision": "run", "risk": "low", "reason": "safe", "mode": "ask"},
    {"decision": "refuse", "risk": "blocked", "reason": "changed", "mode": "ask"},
]
recheck_result = execute(
    runtime,
    repository,
    run_id="terminal-recheck-denied",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "hostname"},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("hostname"),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
)
ok(
    "terminal gate is rechecked immediately before execution and late refusal runs nothing",
    recheck_result.status == "failed"
    and recheck_result.error is not None
    and recheck_result.error.code == "tool.read_failed"
    and len(fake.run_calls) == run_count,
    recheck_result,
)

fake.next_result = {
    "ok": False,
    "exit_code": 7,
    "output": "command returned seven",
    "truncated": False,
    "duration_ms": 8,
}
nonzero_result = execute(
    runtime,
    repository,
    run_id="terminal-nonzero",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "python --version"},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("python --version"),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
)
fake.next_result = {
    "ok": False,
    "exit_code": None,
    "timed_out": True,
    "error": "command timed out after 3s",
    "risk": "low",
}
timeout_result = execute(
    runtime,
    repository,
    run_id="terminal-timeout",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "git --version", "timeout": 3},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("git --version"),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
)
ok(
    "non-zero exit and timeout remain typed truthful command outcomes",
    nonzero_result.status == "succeeded"
    and nonzero_result.typed_output["state"] == "completed"
    and nonzero_result.typed_output["ok"] is False
    and nonzero_result.typed_output["exit_code"] == 7
    and timeout_result.status == "succeeded"
    and timeout_result.typed_output["state"] == "timed_out"
    and timeout_result.typed_output["ok"] is False
    and timeout_result.typed_output["exit_code"] is None
    and timeout_result.typed_output["output"] == "Command timed out before returning a result.",
    (nonzero_result, timeout_result),
)

fake.next_result = {
    "ok": True,
    "exit_code": 0,
    "output": "x" * 6_125,
    "truncated": False,
    "duration_ms": 4,
}
bounded_result = execute(
    runtime,
    repository,
    run_id="terminal-output-bounded",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "node --version"},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("node --version"),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
)
ok(
    "terminal output is capped after redaction before persistence",
    bounded_result.status == "succeeded"
    and bounded_result.typed_output["truncated"] is True
    and len(bounded_result.typed_output["output"]) == 6_000,
    bounded_result,
)

safe_events = list_run_events("terminal-safe-command")
safe_event_json = json.dumps(contract_to_dict(safe_events), sort_keys=True)
policy_row = query_one(
    "SELECT input_json FROM mc_policy_decisions WHERE decision_id='policy-terminal-safe-command'"
)
persisted_json = (policy_row["input_json"] if policy_row else "") + safe_event_json
ok(
    "terminal history uses a hashed target and stores only bounded redacted output",
    safe_command not in persisted_json
    and SECRET not in persisted_json
    and "[REDACTED]" in persisted_json
    and command_target(safe_command) in persisted_json
    and len(safe_result.typed_output["output"]) <= 6000,
    persisted_json,
)

ok(
    "Run 3A terminal reads create no action reservation or receipt",
    query_count("mc_idempotency") == 0 and query_count("mc_action_receipts") == 0,
)

real_runtime = build_terminal_tool_runtime(working_directory=ROOT)
real_result = execute(
    real_runtime,
    repository,
    run_id="terminal-real-command",
    tool_ref=RUN_COMMAND_REF,
    arguments={"command": "git --version", "timeout": 10},
    surface=Surface.AGENT,
    mode="agent",
    target=command_target("git --version"),
    permissions=("terminal.execute",),
    isolations=(IsolationLevel.SUBPROCESS,),
)
ok(
    "real terminal engine executes one allowlisted foreground inspection command",
    real_result.status == "succeeded"
    and real_result.typed_output["state"] == "completed"
    and real_result.typed_output["ok"] is True
    and real_result.typed_output["exit_code"] == 0
    and "git version" in real_result.typed_output["output"].lower()
    and real_result.receipt_id is None,
    real_result,
)

action_schema_gate_count = len(fake.gate_calls)
action_schema_invalid = (
    "",
    "mkdir first; whoami",
    "mkdir first | whoami",
    "mkdir first > output.txt",
    "$(whoami)",
    "`whoami`",
    "mkdir first\nwhoami",
    'mkdir "space name"',
    "mkdir ../escape",
    "mkdir nested/path",
    "mkdir C:\\outside",
    "git --version",
    "curl example.com",
    "pip install rich",
    "rm build",
    "powershell -Command whoami",
    "setx TOKEN value",
    "git push origin main",
)
action_schema_errors = [
    raises(
        ToolCallPreparationError,
        lambda command=command: runtime.catalog.prepare_call(
            call_id=f"invalid-action-{hashlib.sha256(command.encode()).hexdigest()[:8]}",
            run_id="invalid-action-run",
            step_id="invalid-action-step",
            tool_ref=RUN_COMMAND_ACTION_REF,
            arguments={"command": command},
            surface=Surface.AGENT,
            mode="agent",
            candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
            idempotency_key="effect-invalid-action",
            approval_id="approval-invalid-action",
        ),
    )
    for command in action_schema_invalid
]
action_schema_errors.extend(
    (
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-action-cwd",
                run_id="invalid-action-run",
                step_id="invalid-action-step",
                tool_ref=RUN_COMMAND_ACTION_REF,
                arguments={"command": "mkdir first", "cwd": "C:/"},
                surface=Surface.AGENT,
                mode="agent",
                candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
                idempotency_key="effect-invalid-action-cwd",
                approval_id="approval-invalid-action-cwd",
            ),
        ),
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-action-background",
                run_id="invalid-action-run",
                step_id="invalid-action-step",
                tool_ref=RUN_COMMAND_ACTION_REF,
                arguments={"command": "mkdir first", "background": True},
                surface=Surface.AGENT,
                mode="agent",
                candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
                idempotency_key="effect-invalid-action-background",
                approval_id="approval-invalid-action-background",
            ),
        ),
        raises(
            ToolCallPreparationError,
            lambda: runtime.catalog.prepare_call(
                call_id="invalid-action-timeout",
                run_id="invalid-action-run",
                step_id="invalid-action-step",
                tool_ref=RUN_COMMAND_ACTION_REF,
                arguments={"command": "mkdir first", "timeout": 301},
                surface=Surface.AGENT,
                mode="agent",
                candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
                idempotency_key="effect-invalid-action-timeout",
                approval_id="approval-invalid-action-timeout",
            ),
        ),
    )
)
ok(
    "mutable schema allows only one safe-name mkdir command before runtime access",
    all(error is not None for error in action_schema_errors)
    and len(fake.gate_calls) == action_schema_gate_count,
    action_schema_errors,
)

missing_idempotency_gate_count = len(fake.gate_calls)
missing_idempotency = raises(
    ToolExecutionError,
    lambda: execute(
        runtime,
        repository,
        run_id="terminal-action-missing-idempotency",
        tool_ref=RUN_COMMAND_ACTION_REF,
        arguments={"command": "mkdir missing-idempotency"},
        surface=Surface.AGENT,
        mode="agent",
        target=action_target("mkdir missing-idempotency"),
        permissions=("terminal.execute",),
        isolations=(IsolationLevel.SUBPROCESS,),
        approval_mode=ApprovalMode.ASK,
        approval_status=ApprovalStatus.APPROVED,
        approval_id="approval-terminal-action-missing-idempotency",
    ),
)
ok(
    "mutable command cannot reach policy or terminal access without idempotency",
    missing_idempotency is not None
    and len(fake.gate_calls) == missing_idempotency_gate_count
    and query_one(
        "SELECT 1 FROM mc_idempotency "
        "WHERE idempotency_key='effect-terminal-action-missing-idempotency'"
    )
    is None,
    missing_idempotency,
)

action_run_count = len(fake.run_calls)
denied_call, denied_facts, denied_lease = prepare_action(
    runtime,
    repository,
    run_id="terminal-action-approval",
    command="mkdir approval-denied",
    approval_status=ApprovalStatus.NONE,
)
denied_action = execute_prepared(runtime, denied_call, denied_facts, denied_lease)
ok(
    "mutable command requires matching approval before reservation or invocation",
    denied_action.status == "blocked"
    and denied_action.error is not None
    and denied_action.error.code == "tool.approval_required"
    and len(fake.run_calls) == action_run_count
    and query_one(
        "SELECT 1 FROM mc_idempotency WHERE idempotency_key='effect-terminal-action-approval'"
    )
    is None,
    denied_action,
)

fake.next_result = {
    "ok": True,
    "exit_code": 0,
    "output": f"directory created {SECRET}",
    "truncated": False,
    "duration_ms": 21,
}
action_command = "mkdir canonical-marker"
action_hash = hashlib.sha256(action_command.encode("utf-8")).hexdigest()
action_call, action_facts, action_lease = prepare_action(
    runtime,
    repository,
    run_id="terminal-action-success",
    command=action_command,
    approval_id="approval-terminal-action-success",
)
action_result = execute_prepared(runtime, action_call, action_facts, action_lease)
action_row = query_one(
    "SELECT * FROM mc_idempotency WHERE idempotency_key='effect-terminal-action-success'"
)
action_receipt = query_one(
    "SELECT * FROM mc_action_receipts WHERE idempotency_key='effect-terminal-action-success'"
)
action_request = json.loads(action_row["request_json"]) if action_row else {}
ok(
    "approved mutable foreground command records one redacted immutable receipt",
    action_result.status == "succeeded"
    and action_result.typed_output["state"] == "completed"
    and action_result.typed_output["ok"] is True
    and action_result.typed_output["command_sha256"] == action_hash
    and action_result.typed_output["output"] == "directory created [REDACTED]"
    and action_result.receipt_id is not None
    and action_row is not None
    and action_row["status"] == "completed"
    and action_row["execution_count"] == 1
    and action_request["validated_arguments"]["command"] == "[REDACTED]"
    and action_request["validated_arguments"]["command_sha256"] == action_hash
    and action_request["validated_arguments"]["command_chars"] == len(action_command)
    and action_receipt is not None
    and action_receipt["approval_ref"] == "approval-terminal-action-success"
    and action_receipt["target"] == action_target(action_command)
    and fake.run_calls[-1]
    == {
        "command": action_command,
        "cwd": str(ROOT.resolve()),
        "timeout": 60,
        "background": False,
        "risk": "medium",
        "mode": "ask",
        "surface": "mc",
    },
    action_result,
)

action_outcomes = []
for run_id, command, raw_result in (
    (
        "terminal-action-nonzero",
        "mkdir nonzero-case",
        {
            "ok": False,
            "exit_code": 9,
            "output": "mkdir returned nine",
            "truncated": False,
            "duration_ms": 9,
        },
    ),
    (
        "terminal-action-timeout",
        "mkdir timeout-case",
        {
            "ok": False,
            "exit_code": None,
            "timed_out": True,
            "error": "command timed out",
        },
    ),
    (
        "terminal-action-failed-start",
        "mkdir failed-start-case",
        {"ok": False, "error": "shell unavailable"},
    ),
):
    fake.next_result = raw_result
    outcome_call, outcome_facts, outcome_lease = prepare_action(
        runtime,
        repository,
        run_id=run_id,
        command=command,
        approval_id=f"approval-{run_id}",
    )
    action_outcomes.append(
        execute_prepared(runtime, outcome_call, outcome_facts, outcome_lease)
    )
ok(
    "non-zero timeout and failed-start action attempts remain truthful and receipted",
    [result.typed_output["state"] for result in action_outcomes]
    == ["completed", "timed_out", "failed_to_start"]
    and [result.typed_output["exit_code"] for result in action_outcomes]
    == [9, None, None]
    and all(result.status == "succeeded" for result in action_outcomes)
    and all(result.typed_output["ok"] is False for result in action_outcomes)
    and all(result.receipt_id is not None for result in action_outcomes),
    action_outcomes,
)

replay_run_count = len(fake.run_calls)
replayed_action = runtime.execute(
    action_call,
    action_facts,
    worker_id="terminal-action-replay-worker",
    lease_token="unused-terminal-action-replay",
    lease_epoch=99,
)
changed_command = "mkdir changed-marker"
changed_call = runtime.catalog.prepare_call(
    call_id=action_call.call_id,
    run_id=action_call.run_id,
    step_id=action_call.step_id,
    tool_ref=RUN_COMMAND_ACTION_REF,
    arguments={"command": changed_command, "timeout": 60},
    surface=Surface.AGENT,
    mode="agent",
    candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
    idempotency_key=action_call.idempotency_key,
    approval_id=action_call.approval_id,
)
changed_action = raises(
    ActionConflictError,
    lambda: runtime.execute(
        changed_call,
        replace(
            action_facts,
            decision_id="policy-terminal-action-changed",
            target=action_target(changed_command),
        ),
        worker_id="terminal-action-changed-worker",
        lease_token="unused-terminal-action-changed",
        lease_epoch=100,
    ),
)
changed_timeout_call = runtime.catalog.prepare_call(
    call_id=action_call.call_id,
    run_id=action_call.run_id,
    step_id=action_call.step_id,
    tool_ref=RUN_COMMAND_ACTION_REF,
    arguments={"command": action_command, "timeout": 61},
    surface=Surface.AGENT,
    mode="agent",
    candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
    idempotency_key=action_call.idempotency_key,
    approval_id=action_call.approval_id,
)
changed_timeout = raises(
    ActionConflictError,
    lambda: runtime.execute(
        changed_timeout_call,
        replace(action_facts, decision_id="policy-terminal-action-timeout-changed"),
        worker_id="terminal-action-timeout-worker",
        lease_token="unused-terminal-action-timeout",
        lease_epoch=101,
    ),
)
changed_approval_call = runtime.catalog.prepare_call(
    call_id=action_call.call_id,
    run_id=action_call.run_id,
    step_id=action_call.step_id,
    tool_ref=RUN_COMMAND_ACTION_REF,
    arguments={"command": action_command, "timeout": 60},
    surface=Surface.AGENT,
    mode="agent",
    candidate_tool_refs=(RUN_COMMAND_ACTION_REF,),
    idempotency_key=action_call.idempotency_key,
    approval_id="approval-terminal-action-changed",
)
changed_approval = raises(
    ActionConflictError,
    lambda: runtime.execute(
        changed_approval_call,
        replace(
            action_facts,
            decision_id="policy-terminal-action-approval-changed",
            approval_id="approval-terminal-action-changed",
        ),
        worker_id="terminal-action-approval-worker",
        lease_token="unused-terminal-action-approval",
        lease_epoch=102,
    ),
)
different_directory_runtime = build_terminal_tool_runtime(
    engine=fake, working_directory=TMP
)
changed_directory = raises(
    ActionConflictError,
    lambda: different_directory_runtime.execute(
        action_call,
        replace(
            action_facts,
            decision_id="policy-terminal-action-directory-changed",
            tool=different_directory_runtime.catalog.get_spec(RUN_COMMAND_ACTION_REF),
            target=action_target(action_command, TMP),
        ),
        worker_id="terminal-action-directory-worker",
        lease_token="unused-terminal-action-directory",
        lease_epoch=103,
    ),
)
ok(
    "completed replay invokes no command and changed action identity conflicts",
    replayed_action == action_result
    and changed_action is not None
    and changed_timeout is not None
    and changed_approval is not None
    and changed_directory is not None
    and len(fake.run_calls) == replay_run_count
    and query_one(
        "SELECT execution_count FROM mc_idempotency "
        "WHERE idempotency_key='effect-terminal-action-success'"
    )["execution_count"]
    == 1,
)

late_call, late_facts, late_lease = prepare_action(
    runtime,
    repository,
    run_id="terminal-action-late-refusal",
    command="mkdir late-refusal",
    approval_id="approval-terminal-action-late-refusal",
)
fake.gate_results = [
    {"decision": "confirm", "risk": "medium", "reason": "approve", "mode": "ask"},
    {"decision": "refuse", "risk": "blocked", "reason": "changed", "mode": "ask"},
]
late_run_count = len(fake.run_calls)
late_result = execute_prepared(runtime, late_call, late_facts, late_lease)
ok(
    "second terminal gate can refuse without invoking the reserved action",
    late_result.status == "failed"
    and late_result.error is not None
    and late_result.error.code == "tool.action_not_applied"
    and late_result.error.retryable is True
    and len(fake.run_calls) == late_run_count
    and query_one(
        "SELECT status FROM mc_idempotency "
        "WHERE idempotency_key='effect-terminal-action-late-refusal'"
    )["status"]
    == "retry_allowed",
    late_result,
)

unknown_call, unknown_facts, unknown_lease = prepare_action(
    runtime,
    repository,
    run_id="terminal-action-unknown",
    command="mkdir unknown-outcome",
    approval_id="approval-terminal-action-unknown",
)
fake.raise_on_run = True
unknown_run_count = len(fake.run_calls)
unknown_initial = execute_prepared(runtime, unknown_call, unknown_facts, unknown_lease)
fake.raise_on_run = False
unknown_reconciliation = runtime.executor.reconcile_action(unknown_call, actor="owner")
unknown_retry = runtime.execute(
    unknown_call,
    unknown_facts,
    worker_id="terminal-action-unknown-retry",
    lease_token="unused-terminal-action-unknown-retry",
    lease_epoch=101,
)
ok(
    "interrupted mutable command remains unknown and cannot execute again",
    unknown_initial.status == "blocked"
    and unknown_initial.error is not None
    and unknown_initial.error.code == "tool.action_reconciliation_required"
    and unknown_reconciliation.status == "blocked"
    and unknown_reconciliation.error is not None
    and unknown_reconciliation.error.code == "tool.action_reconciliation_required"
    and unknown_retry.status == "blocked"
    and len(fake.run_calls) == unknown_run_count + 1
    and query_one(
        "SELECT status FROM mc_idempotency "
        "WHERE idempotency_key='effect-terminal-action-unknown'"
    )["status"]
    == "reconciliation_required",
    unknown_reconciliation,
)

action_events = list_run_events("terminal-action-success")
action_policy = query_one(
    "SELECT input_json FROM mc_policy_decisions "
    "WHERE decision_id='policy-terminal-action-success'"
)
persisted_action_json = json.dumps(
    {
        "action": dict(action_row) if action_row else {},
        "receipt": dict(action_receipt) if action_receipt else {},
        "events": contract_to_dict(action_events),
        "policy": action_policy["input_json"] if action_policy else "",
    },
    sort_keys=True,
)
ok(
    "mutable terminal persistence contains hashes and redacted output but no raw command",
    action_command not in persisted_action_json
    and SECRET not in persisted_action_json
    and action_hash in persisted_action_json
    and "[REDACTED]" in persisted_action_json,
    persisted_action_json,
)

with tempfile.TemporaryDirectory(prefix="tobi_t07_action_", dir=TMP) as real_dir_text:
    real_dir = Path(real_dir_text)
    real_action_runtime = build_terminal_tool_runtime(working_directory=real_dir)
    real_action_call, real_action_facts, real_action_lease = prepare_action(
        real_action_runtime,
        repository,
        run_id="terminal-action-real",
        command="mkdir created-by-t07",
        approval_id="approval-terminal-action-real",
        directory=real_dir,
    )
    real_action_result = execute_prepared(
        real_action_runtime,
        real_action_call,
        real_action_facts,
        real_action_lease,
    )
    real_directory_created = (real_dir / "created-by-t07").is_dir()
ok(
    "real approved foreground mutation runs once in the fixed temporary directory",
    real_action_result.status == "succeeded"
    and real_action_result.typed_output["state"] == "completed"
    and real_action_result.typed_output["ok"] is True
    and real_action_result.typed_output["exit_code"] == 0
    and real_action_result.receipt_id is not None
    and real_directory_created,
    real_action_result,
)

terminal_runtime_path = (ROOT / "core" / "runtime" / "terminal_tools.py").resolve()
live_imports: list[str] = []
for source_root in (ROOT / "core", ROOT / "api"):
    for source_path in source_root.rglob("*.py"):
        if source_path.resolve() == terminal_runtime_path:
            continue
        source = source_path.read_text(encoding="utf-8", errors="ignore")
        if "core.runtime.terminal_tools" in source or "runtime.terminal_tools import" in source:
            live_imports.append(source_path.relative_to(ROOT).as_posix())
ok(
    "no live caller imports the dormant terminal runtime",
    live_imports == [],
    live_imports,
)

print(f"\n{PASS}/{PASS} T07 RUN 3A/3B1 TERMINAL TOOL CHECKS PASS")
