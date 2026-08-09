"""T07 Run 3A: dormant read-only foreground terminal execution."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any


TMP = Path(tempfile.mkdtemp(prefix="tobi_t07_terminal_"))
os.environ["DB_PATH"] = str(TMP / "agent.db")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.database import get_connection, init_database  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    ApprovalMode,
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
from core.runtime.event_store import list_run_events  # noqa: E402
from core.runtime.repository import RuntimeRepository  # noqa: E402
from core.runtime.state import RunStatus  # noqa: E402
from core.runtime.terminal_tools import (  # noqa: E402
    RUN_COMMAND_REF,
    TERMINAL_STATUS_REF,
    build_terminal_tool_runtime,
)
from core.runtime.tool_catalog import ToolCallPreparationError  # noqa: E402


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


def prepare_run(
    repository: RuntimeRepository,
    *,
    run_id: str,
    tool_ref: str,
    arguments: dict[str, Any],
    surface: Surface,
    mode: str,
) -> tuple[str, dict]:
    step_id = f"step-{run_id}"
    recipe = LoopRecipe(
        recipe_id=f"recipe-{run_id}",
        version="1",
        name="Terminal tool fixture",
        loop_type=LoopType.TURN,
        trigger="owner request",
        objective="Inspect terminal state without mutation",
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
            message="Inspect the local terminal safely",
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
            objective="Inspect terminal state without mutation",
            steps=(
                PlanStep(
                    step_id=step_id,
                    kind="tool",
                    risk=RiskLevel.LOW if tool_ref == RUN_COMMAND_REF else RiskLevel.NONE,
                    tool_name=tool_ref,
                    arguments=arguments,
                    retry_policy="none",
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
):
    step_id, lease = prepare_run(
        repository,
        run_id=run_id,
        tool_ref=tool_ref,
        arguments=arguments,
        surface=surface,
        mode=mode,
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
        approval_mode=ApprovalMode.ALWAYS,
    )
    result = runtime.execute(
        call,
        facts,
        worker_id=lease["worker_id"],
        lease_token=lease["lease_token"],
        lease_epoch=lease["lease_epoch"],
    )
    return result


SECRET = "terminal-secret-123456789"


class FakeTerminalEngine:
    def __init__(self) -> None:
        self.mode = "ask"
        self.enabled = True
        self.status_calls = 0
        self.gate_calls: list[dict[str, Any]] = []
        self.run_calls: list[dict[str, Any]] = []
        self.gate_results: list[dict[str, Any]] = []
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
                "risk": "low",
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
        return {
            "decision": "run",
            "risk": "low",
            "reason": "known-safe inspection command",
            "mode": self.mode,
        }

    def run(self, command: str, **kwargs: Any) -> dict[str, Any]:
        self.run_calls.append({"command": command, **kwargs})
        return dict(self.next_result)

    def redact(self, text: str) -> str:
        return str(text).replace(SECRET, "[REDACTED]")


init_database()
repository = RuntimeRepository()
fake = FakeTerminalEngine()
runtime = build_terminal_tool_runtime(engine=fake, working_directory=ROOT)

refs = tuple(entry.tool_ref for entry in runtime.catalog.manifest.entries)
run_spec = runtime.catalog.get_spec(RUN_COMMAND_REF)
status_spec = runtime.catalog.get_spec(TERMINAL_STATUS_REF)
metadata_json = json.dumps(
    {
        "manifest": contract_to_dict(runtime.catalog.manifest),
        "specs": contract_to_dict((run_spec, status_spec)),
    },
    sort_keys=True,
)
ok(
    "terminal catalog is exactly two bounded dormant contracts",
    refs == (RUN_COMMAND_REF, TERMINAL_STATUS_REF)
    and run_spec.allowed_surfaces == (Surface.AGENT,)
    and run_spec.allowed_modes == ("agent",)
    and run_spec.required_permissions == ("terminal.execute",)
    and run_spec.side_effect_class is SideEffectClass.NONE
    and run_spec.risk is RiskLevel.LOW
    and run_spec.isolation == "subprocess"
    and run_spec.timeout_s == 30
    and run_spec.idempotency_policy == "none"
    and status_spec.allowed_surfaces == (Surface.CHAT, Surface.AGENT)
    and status_spec.allowed_modes == ("chat", "agent")
    and status_spec.required_permissions == ("terminal.read",)
    and status_spec.side_effect_class is SideEffectClass.NONE
    and status_spec.isolation == "in_process"
    and set(run_spec.input_schema["properties"]) == {"command", "timeout"}
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

print(f"\n{PASS}/{PASS} T07 RUN 3A TERMINAL TOOL CHECKS PASS")
