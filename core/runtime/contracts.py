"""Validated Mission Control V2 runtime contracts for queue #21 T01.

These dependency-free dataclasses define domain boundaries without activating a
new runtime. Existing Chat Runtime V2 values remain unchanged; the explicit
``from_chat_spec`` adapter is the migration bridge for its current tool shape.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from core.chat_runtime_contracts import ToolSpec as ChatToolSpec


class Surface(str, Enum):
    CHAT = "chat"
    AGENT = "agent"
    MCP = "mcp"
    TELEGRAM = "telegram"
    CLI = "cli"
    SCHEDULER = "scheduler"
    OFFICE = "office"
    PROJECTS = "projects"
    DEVELOPER = "developer"


class Capability(str, Enum):
    READ_FILES = "read_files"
    WRITE_FILES = "write_files"
    RUN_TERMINAL = "run_terminal"
    READ_PROJECTS = "read_projects"
    WRITE_PROJECTS = "write_projects"
    READ_BRAIN = "read_brain"
    WRITE_BRAIN = "write_brain"
    USE_CONNECTORS = "use_connectors"
    USE_BROWSER = "use_browser"
    RUN_CODING = "run_coding"
    RUN_SCHEDULED = "run_scheduled"
    RUN_PROACTIVE = "run_proactive"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SideEffectClass(str, Enum):
    NONE = "none"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    EXTERNAL = "external"


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class ApprovalMode(str, Enum):
    ASK = "ask"
    SESSION = "session"
    ALWAYS = "always"


class ApprovalStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CredentialStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    AVAILABLE = "available"
    MISSING = "missing"
    LOCKED = "locked"
    PURPOSE_MISMATCH = "purpose_mismatch"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ToolAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class TrustClass(str, Enum):
    OWNER_DIRECT = "owner_direct"
    SYSTEM_VERIFIED = "system_verified"
    CONNECTOR_VERIFIED = "connector_verified"
    DERIVED = "derived"
    UNTRUSTED_CONTENT = "untrusted_content"


class Certainty(str, Enum):
    KNOWN = "known"
    INFERRED = "inferred"
    CONTRADICTED = "contradicted"
    STALE = "stale"


class IsolationLevel(str, Enum):
    IN_PROCESS = "in_process"
    SUBPROCESS = "subprocess"
    WORKSPACE = "workspace"
    CONTAINER = "container"
    REMOTE = "remote"


class BudgetStatus(str, Enum):
    AVAILABLE = "available"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"


class LoopType(str, Enum):
    TURN = "turn"
    GOAL = "goal"
    TIME = "time"
    PROACTIVE = "proactive"


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    POLICY = "policy"
    APPROVAL = "approval"
    AUTHENTICATION = "authentication"
    AVAILABILITY = "availability"
    TIMEOUT = "timeout"
    BUDGET = "budget"
    CONFLICT = "conflict"
    EXECUTION = "execution"
    INTERNAL = "internal"


class ErrorStage(str, Enum):
    ACCEPT = "accept"
    ROUTE = "route"
    PLAN = "plan"
    POLICY = "policy"
    APPROVE = "approve"
    EXECUTE = "execute"
    EVALUATE = "evaluate"
    RESPOND = "respond"
    RECOVER = "recover"


class RecoveryAction(str, Enum):
    RESUME = "resume"
    RETRY_STEP = "retry_step"
    SKIP_STEP = "skip_step"
    REVISE = "revise"
    PROVIDE_INPUT = "provide_input"
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


class EvalStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELED = "canceled"


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SystemEntityType(str, Enum):
    SUBSYSTEM = "subsystem"
    COMPONENT = "component"
    CAPABILITY = "capability"
    TOOL = "tool"
    LOOP = "loop"
    RUN = "run"
    EVAL = "eval"
    POLICY = "policy"
    INTEGRATION = "integration"
    LIMITATION = "limitation"
    RISK = "risk"
    DECISION = "decision"
    QUEUE_ITEM = "queue_item"


def _require_text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_text(value: Any, name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be None or a non-empty string")


@dataclass(frozen=True)
class CredentialRequirement:
    purpose: str
    secret_name: str
    integration_id: Optional[str] = None
    contract_version: str = "1"

    def __post_init__(self) -> None:
        _require_text(self.purpose, "purpose")
        _require_text(self.secret_name, "secret_name")
        _require_optional_text(self.integration_id, "integration_id")
        _require_text(self.contract_version, "contract_version")


@dataclass(frozen=True)
class LegacyPolicyFacts:
    source: str
    source_mode: str
    approval_mode: ApprovalMode
    execution_allowed: bool
    denial_reason: Optional[str] = None
    contract_version: str = "1"

    def __post_init__(self) -> None:
        if self.source not in {"chat_review", "terminal"}:
            raise ValueError("source must be chat_review or terminal")
        _require_text(self.source_mode, "source_mode")
        _require_enum(self.approval_mode, ApprovalMode, "approval_mode")
        if not isinstance(self.execution_allowed, bool):
            raise ValueError("execution_allowed must be a bool")
        _require_optional_text(self.denial_reason, "denial_reason")
        _require_text(self.contract_version, "contract_version")
        if self.execution_allowed and self.denial_reason is not None:
            raise ValueError("allowed legacy facts cannot include a denial reason")
        if not self.execution_allowed and self.denial_reason is None:
            raise ValueError("denied legacy facts require a denial reason")


def _require_enum(value: Any, enum_type: type[Enum], name: str) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{name} must be a {enum_type.__name__}")


def _require_tuple(value: Any, name: str, item_type: Optional[type] = None) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    if item_type is not None and any(not isinstance(item, item_type) for item in value):
        raise ValueError(f"every {name} item must be a {item_type.__name__}")


def _require_mapping(value: Any, name: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")


def _require_probability(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")


def _require_non_negative(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_positive_int(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def contract_to_dict(value: Any) -> Any:
    """Convert a contract tree to JSON-ready primitives."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return contract_to_dict(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): contract_to_dict(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [contract_to_dict(item) for item in value]
    return value


@dataclass(frozen=True)
class RunRequest:
    request_id: str
    surface: Surface
    owner_id: str
    session_id: str
    mode: str
    message: str
    attachments: tuple[dict[str, Any], ...] = ()
    capability_toggles: tuple[Capability, ...] = ()
    selected_project: Optional[str] = None
    client_timestamp: Optional[str] = None
    budget_profile: str = "default"
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in ("request_id", "owner_id", "session_id", "mode", "budget_profile", "contract_version"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.message, str):
            raise ValueError("message must be a string")
        _require_enum(self.surface, Surface, "surface")
        _require_tuple(self.attachments, "attachments", dict)
        _require_tuple(self.capability_toggles, "capability_toggles", Capability)
        _require_optional_text(self.selected_project, "selected_project")
        _require_optional_text(self.client_timestamp, "client_timestamp")


@dataclass(frozen=True)
class RouteDecision:
    route_class: str
    intent: str
    confidence: float
    candidate_capabilities: tuple[Capability, ...] = ()
    clarification: Optional[str] = None
    context_requirements: tuple[str, ...] = ()
    planner_required: bool = False
    reasons: tuple[str, ...] = ()
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in ("route_class", "intent", "contract_version"):
            _require_text(getattr(self, name), name)
        _require_probability(self.confidence, "confidence")
        _require_tuple(self.candidate_capabilities, "candidate_capabilities", Capability)
        _require_tuple(self.context_requirements, "context_requirements", str)
        _require_tuple(self.reasons, "reasons", str)
        _require_optional_text(self.clarification, "clarification")
        if not isinstance(self.planner_required, bool):
            raise ValueError("planner_required must be a bool")


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    kind: str
    risk: RiskLevel
    tool_name: Optional[str] = None
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    timeout_s: int = 0
    retry_policy: str = "none"
    idempotency_key: Optional[str] = None
    required_capabilities: tuple[Capability, ...] = ()
    output_contract: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("step_id", "kind", "retry_policy"):
            _require_text(getattr(self, name), name)
        _require_enum(self.risk, RiskLevel, "risk")
        _require_optional_text(self.tool_name, "tool_name")
        _require_optional_text(self.idempotency_key, "idempotency_key")
        _require_mapping(self.arguments, "arguments")
        _require_mapping(self.output_contract, "output_contract")
        _require_tuple(self.depends_on, "depends_on", str)
        _require_tuple(self.required_capabilities, "required_capabilities", Capability)
        _require_non_negative(self.timeout_s, "timeout_s")


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    run_id: str
    version: str
    objective: str
    assumptions: tuple[str, ...] = ()
    steps: tuple[PlanStep, ...] = ()
    expected_artifacts: tuple[str, ...] = ()
    approval_points: tuple[str, ...] = ()
    completion_predicate: str = "explicit owner stop"
    budget: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("plan_id", "run_id", "version", "objective", "completion_predicate"):
            _require_text(getattr(self, name), name)
        _require_tuple(self.assumptions, "assumptions", str)
        _require_tuple(self.steps, "steps", PlanStep)
        _require_tuple(self.expected_artifacts, "expected_artifacts", str)
        _require_tuple(self.approval_points, "approval_points", str)
        _require_mapping(self.budget, "budget")


@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    sequence: int
    event_type: str
    stage: str
    timestamp: str
    actor: str
    redacted_payload: dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in ("event_id", "run_id", "event_type", "stage", "timestamp", "actor", "contract_version"):
            _require_text(getattr(self, name), name)
        _require_positive_int(self.sequence, "sequence")
        _require_mapping(self.redacted_payload, "redacted_payload")
        _require_optional_text(self.trace_id, "trace_id")
        _require_optional_text(self.parent_span_id, "parent_span_id")


@dataclass(frozen=True)
class RuntimeToolSpec:
    name: str
    namespace: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effect_class: SideEffectClass
    risk: RiskLevel
    allowed_modes: tuple[str, ...]
    allowed_surfaces: tuple[Surface, ...]
    required_permissions: tuple[str, ...] = ()
    required_integrations: tuple[str, ...] = ()
    credential_purpose: Optional[str] = None
    timeout_s: int = 30
    retry_policy: str = "none"
    idempotency_policy: str = "none"
    isolation: str = "in_process"
    cost_hint: Optional[float] = None
    audit_policy: str = "standard"
    availability_probe: Optional[str] = None
    adapter: str = "local"

    def __post_init__(self) -> None:
        for name in (
            "name", "namespace", "version", "description", "retry_policy",
            "idempotency_policy", "isolation", "audit_policy", "adapter",
        ):
            _require_text(getattr(self, name), name)
        _require_mapping(self.input_schema, "input_schema")
        _require_mapping(self.output_schema, "output_schema")
        _require_enum(self.side_effect_class, SideEffectClass, "side_effect_class")
        _require_enum(self.risk, RiskLevel, "risk")
        _require_tuple(self.allowed_modes, "allowed_modes", str)
        _require_tuple(self.allowed_surfaces, "allowed_surfaces", Surface)
        _require_tuple(self.required_permissions, "required_permissions", str)
        _require_tuple(self.required_integrations, "required_integrations", str)
        _require_optional_text(self.credential_purpose, "credential_purpose")
        _require_optional_text(self.availability_probe, "availability_probe")
        _require_positive_int(self.timeout_s, "timeout_s")
        if self.cost_hint is not None:
            _require_non_negative(self.cost_hint, "cost_hint")

    @property
    def ref(self) -> str:
        return f"{self.namespace}.{self.name}@{self.version}"

    @classmethod
    def from_chat_spec(
        cls,
        spec: ChatToolSpec,
        *,
        namespace: str,
        version: str,
        side_effect_class: SideEffectClass = SideEffectClass.NONE,
        allowed_surfaces: tuple[Surface, ...] = (Surface.CHAT, Surface.AGENT),
        adapter: str = "chat_runtime_v2",
    ) -> "RuntimeToolSpec":
        if not isinstance(spec, ChatToolSpec):
            raise ValueError("spec must be a Chat Runtime V2 ToolSpec")
        if spec.risk == "read":
            risk = RiskLevel.NONE
        else:
            try:
                risk = RiskLevel(spec.risk)
            except ValueError as exc:
                raise ValueError(f"unsupported Chat tool risk: {spec.risk}") from exc
        return cls(
            name=spec.name,
            namespace=namespace,
            version=version,
            description=spec.description,
            input_schema=dict(spec.args_schema),
            output_schema=dict(spec.result_schema),
            side_effect_class=side_effect_class,
            risk=risk,
            allowed_modes=tuple(spec.allowed_modes),
            allowed_surfaces=allowed_surfaces,
            required_integrations=tuple(spec.required_integrations),
            timeout_s=spec.timeout_s,
            retry_policy=spec.retry_policy,
            idempotency_policy="required" if spec.idempotent else "none",
            adapter=adapter,
        )


@dataclass(frozen=True)
class ToolAvailability:
    tool_ref: str
    status: ToolAvailabilityStatus
    reason_codes: tuple[str, ...] = ()
    contract_version: str = "1"

    def __post_init__(self) -> None:
        _require_text(self.tool_ref, "tool_ref")
        _require_enum(self.status, ToolAvailabilityStatus, "status")
        _require_tuple(self.reason_codes, "reason_codes", str)
        _require_text(self.contract_version, "contract_version")


@dataclass(frozen=True)
class ToolCatalogEntry:
    source_key: str
    spec: RuntimeToolSpec
    availability: ToolAvailability
    contract_version: str = "1"

    def __post_init__(self) -> None:
        _require_text(self.source_key, "source_key")
        if not isinstance(self.spec, RuntimeToolSpec):
            raise ValueError("spec must be a RuntimeToolSpec")
        if not isinstance(self.availability, ToolAvailability):
            raise ValueError("availability must be a ToolAvailability")
        if self.availability.tool_ref != self.spec.ref:
            raise ValueError("availability tool_ref must match spec ref")
        _require_text(self.contract_version, "contract_version")


@dataclass(frozen=True)
class ToolDiscoveryQuery:
    surface: Surface
    mode: str
    candidate_tool_refs: tuple[str, ...] = ()
    limit: int = 20
    contract_version: str = "1"

    def __post_init__(self) -> None:
        _require_enum(self.surface, Surface, "surface")
        _require_text(self.mode, "mode")
        _require_tuple(self.candidate_tool_refs, "candidate_tool_refs", str)
        _require_positive_int(self.limit, "limit")
        if self.limit > 100:
            raise ValueError("limit must not exceed 100")
        _require_text(self.contract_version, "contract_version")


@dataclass(frozen=True)
class ToolDiscoveryResult:
    tools: tuple[RuntimeToolSpec, ...]
    truncated: bool = False
    contract_version: str = "1"

    def __post_init__(self) -> None:
        _require_tuple(self.tools, "tools", RuntimeToolSpec)
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a bool")
        _require_text(self.contract_version, "contract_version")


@dataclass(frozen=True)
class PolicyInput:
    decision_id: str
    run_id: str
    owner_id: str
    session_id: str
    surface: Surface
    mode: str
    tool: RuntimeToolSpec
    target: str
    step_id: Optional[str] = None
    granted_permissions: tuple[str, ...] = ()
    available_integrations: tuple[str, ...] = ()
    credential_status: CredentialStatus = CredentialStatus.NOT_REQUIRED
    trust_class: TrustClass = TrustClass.OWNER_DIRECT
    certainty: Certainty = Certainty.KNOWN
    instruction_authority: bool = False
    available_isolations: tuple[IsolationLevel, ...] = (IsolationLevel.IN_PROCESS,)
    budget_status: BudgetStatus = BudgetStatus.AVAILABLE
    approval_mode: ApprovalMode = ApprovalMode.ASK
    approval_status: ApprovalStatus = ApprovalStatus.NONE
    approval_id: Optional[str] = None
    compatibility_denials: tuple[str, ...] = ()
    active_kill_switches: tuple[str, ...] = ()
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "run_id",
            "owner_id",
            "session_id",
            "mode",
            "target",
            "contract_version",
        ):
            _require_text(getattr(self, name), name)
        _require_optional_text(self.step_id, "step_id")
        if not isinstance(self.tool, RuntimeToolSpec):
            raise ValueError("tool must be a RuntimeToolSpec")
        _require_enum(self.surface, Surface, "surface")
        _require_tuple(self.granted_permissions, "granted_permissions", str)
        _require_tuple(self.available_integrations, "available_integrations", str)
        _require_enum(self.credential_status, CredentialStatus, "credential_status")
        _require_enum(self.trust_class, TrustClass, "trust_class")
        _require_enum(self.certainty, Certainty, "certainty")
        if not isinstance(self.instruction_authority, bool):
            raise ValueError("instruction_authority must be a bool")
        _require_tuple(self.available_isolations, "available_isolations", IsolationLevel)
        _require_enum(self.budget_status, BudgetStatus, "budget_status")
        _require_enum(self.approval_mode, ApprovalMode, "approval_mode")
        _require_enum(self.approval_status, ApprovalStatus, "approval_status")
        _require_optional_text(self.approval_id, "approval_id")
        _require_tuple(self.compatibility_denials, "compatibility_denials", str)
        _require_tuple(self.active_kill_switches, "active_kill_switches", str)
        if self.approval_status is ApprovalStatus.NONE and self.approval_id is not None:
            raise ValueError("approval_id requires an approval status")
        if self.approval_status is not ApprovalStatus.NONE and self.approval_id is None:
            raise ValueError("approval status requires approval_id")


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    run_id: str
    tool_ref: str
    policy_id: str
    policy_version: str
    effect: PolicyEffect
    reason_codes: tuple[str, ...]
    owner_message: str
    required_approval: bool
    isolation: str
    step_id: Optional[str] = None
    approval_id: Optional[str] = None
    credential_purpose: Optional[str] = None
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "run_id",
            "tool_ref",
            "policy_id",
            "policy_version",
            "owner_message",
            "isolation",
            "contract_version",
        ):
            _require_text(getattr(self, name), name)
        _require_optional_text(self.step_id, "step_id")
        _require_enum(self.effect, PolicyEffect, "effect")
        _require_tuple(self.reason_codes, "reason_codes", str)
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty")
        if not isinstance(self.required_approval, bool):
            raise ValueError("required_approval must be a bool")
        _require_optional_text(self.approval_id, "approval_id")
        _require_optional_text(self.credential_purpose, "credential_purpose")
        if self.effect is PolicyEffect.REQUIRE_APPROVAL and not self.required_approval:
            raise ValueError("require_approval effect must set required_approval")


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    run_id: str
    step_id: str
    policy_decision_id: str
    owner_id: str
    session_id: str
    tool_ref: str
    expires_at: str
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in (
            "approval_id",
            "run_id",
            "step_id",
            "policy_decision_id",
            "owner_id",
            "session_id",
            "tool_ref",
            "expires_at",
            "contract_version",
        ):
            _require_text(getattr(self, name), name)


@dataclass(frozen=True)
class OwnerApprovalDecision:
    approval_id: str
    owner_id: str
    session_id: str
    status: ApprovalStatus
    authentication_method: str
    authentication_evidence_hash: str
    authenticated_at: str
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in (
            "approval_id",
            "owner_id",
            "session_id",
            "authentication_method",
            "authentication_evidence_hash",
            "authenticated_at",
            "contract_version",
        ):
            _require_text(getattr(self, name), name)
        _require_enum(self.status, ApprovalStatus, "status")
        if self.status not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError("owner approval status must be approved or rejected")
        evidence_hash = self.authentication_evidence_hash
        if len(evidence_hash) != 64 or any(
            character not in "0123456789abcdef" for character in evidence_hash
        ):
            raise ValueError("authentication_evidence_hash must be lowercase SHA-256")


@dataclass(frozen=True)
class RuntimeToolCall:
    call_id: str
    run_id: str
    step_id: str
    tool_ref: str
    validated_arguments: dict[str, Any]
    idempotency_key: Optional[str] = None
    approval_id: Optional[str] = None
    deadline: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("call_id", "run_id", "step_id", "tool_ref"):
            _require_text(getattr(self, name), name)
        _require_mapping(self.validated_arguments, "validated_arguments")
        _require_optional_text(self.idempotency_key, "idempotency_key")
        _require_optional_text(self.approval_id, "approval_id")
        _require_optional_text(self.deadline, "deadline")


@dataclass(frozen=True)
class RuntimeErrorInfo:
    code: str
    category: ErrorCategory
    stage: ErrorStage
    message: str
    owner_message: str
    retryable: bool = False
    recovery_actions: tuple[RecoveryAction, ...] = ()
    safe_detail: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("code", "message", "owner_message"):
            _require_text(getattr(self, name), name)
        _require_enum(self.category, ErrorCategory, "category")
        _require_enum(self.stage, ErrorStage, "stage")
        _require_tuple(self.recovery_actions, "recovery_actions", RecoveryAction)
        _require_optional_text(self.safe_detail, "safe_detail")
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a bool")


@dataclass(frozen=True)
class RuntimeToolResult:
    status: str
    typed_output: Any = None
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    receipt_id: Optional[str] = None
    retryable: bool = False
    error: Optional[RuntimeErrorInfo] = None
    timing: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "failed", "blocked", "canceled"}:
            raise ValueError("status must be succeeded, failed, blocked, or canceled")
        _require_tuple(self.evidence_refs, "evidence_refs", str)
        _require_tuple(self.artifact_refs, "artifact_refs", str)
        _require_optional_text(self.receipt_id, "receipt_id")
        _require_mapping(self.timing, "timing")
        _require_mapping(self.cost, "cost")
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a bool")
        if self.error is not None and not isinstance(self.error, RuntimeErrorInfo):
            raise ValueError("error must be RuntimeErrorInfo or None")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed results require error details")


@dataclass(frozen=True)
class RunUsageDelta:
    model_calls: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    runtime_ms: int = 0
    cost_microusd: int = 0
    download_bytes: int = 0
    storage_bytes: int = 0

    def __post_init__(self) -> None:
        for name in (
            "model_calls",
            "tool_calls",
            "prompt_tokens",
            "completion_tokens",
            "runtime_ms",
            "cost_microusd",
            "download_bytes",
            "storage_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class LoopIterationResult:
    stop_condition_met: bool
    summary: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stop_condition_met, bool):
            raise ValueError("stop_condition_met must be a bool")
        _require_text(self.summary, "summary")
        _require_tuple(self.evidence_refs, "evidence_refs", str)


@dataclass(frozen=True)
class ActionReceipt:
    receipt_id: str
    run_id: str
    step_id: str
    tool_ref: str
    target: str
    effect_summary: str
    timestamp: str
    before_ref: Optional[str] = None
    after_ref: Optional[str] = None
    external_ref: Optional[str] = None
    approval_ref: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("receipt_id", "run_id", "step_id", "tool_ref", "target", "effect_summary", "timestamp"):
            _require_text(getattr(self, name), name)
        for name in ("before_ref", "after_ref", "external_ref", "approval_ref"):
            _require_optional_text(getattr(self, name), name)


@dataclass(frozen=True)
class LoopRecipe:
    recipe_id: str
    version: str
    name: str
    loop_type: LoopType
    trigger: str
    objective: str
    stop_condition: str
    max_attempts: int
    max_runtime_s: int
    max_cost_usd: float
    max_model_calls: int = 50
    max_tool_calls: int = 100
    max_total_tokens: int = 500_000
    max_download_bytes: int = 100_000_000
    max_storage_bytes: int = 500_000_000
    allowed_tools: tuple[str, ...] = ()
    approval_gates: tuple[str, ...] = ()
    required_evals: tuple[str, ...] = ()
    recovery_policy: str = "pause_with_options"
    evidence_required: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("recipe_id", "version", "name", "trigger", "objective", "stop_condition", "recovery_policy"):
            _require_text(getattr(self, name), name)
        _require_enum(self.loop_type, LoopType, "loop_type")
        _require_positive_int(self.max_attempts, "max_attempts")
        _require_positive_int(self.max_runtime_s, "max_runtime_s")
        _require_non_negative(self.max_cost_usd, "max_cost_usd")
        for name in (
            "max_model_calls",
            "max_tool_calls",
            "max_total_tokens",
            "max_download_bytes",
            "max_storage_bytes",
        ):
            _require_positive_int(getattr(self, name), name)
        _require_tuple(self.allowed_tools, "allowed_tools", str)
        _require_tuple(self.approval_gates, "approval_gates", str)
        _require_tuple(self.required_evals, "required_evals", str)
        _require_tuple(self.evidence_required, "evidence_required", str)


@dataclass(frozen=True)
class LoopPolicy:
    policy_id: str
    version: str
    recipe_id: str
    recipe_version: str
    policy_decision_id: str
    loop_type: LoopType
    trigger: str
    objective: str
    stop_condition: str
    max_attempts: int
    max_runtime_s: int
    max_cost_usd: float
    max_model_calls: int = 50
    max_tool_calls: int = 100
    max_total_tokens: int = 500_000
    max_download_bytes: int = 100_000_000
    max_storage_bytes: int = 500_000_000
    allowed_tools: tuple[str, ...] = ()
    approval_gates: tuple[str, ...] = ()
    required_evals: tuple[str, ...] = ()
    recovery_policy: str = "pause_with_options"
    evidence_required: tuple[str, ...] = ()
    owner_override: dict[str, Any] = field(default_factory=dict)
    enabled: bool = False

    def __post_init__(self) -> None:
        for name in (
            "policy_id", "version", "recipe_id", "recipe_version", "policy_decision_id",
            "trigger", "objective", "stop_condition", "recovery_policy",
        ):
            _require_text(getattr(self, name), name)
        _require_enum(self.loop_type, LoopType, "loop_type")
        _require_positive_int(self.max_attempts, "max_attempts")
        _require_positive_int(self.max_runtime_s, "max_runtime_s")
        _require_non_negative(self.max_cost_usd, "max_cost_usd")
        for name in (
            "max_model_calls",
            "max_tool_calls",
            "max_total_tokens",
            "max_download_bytes",
            "max_storage_bytes",
        ):
            _require_positive_int(getattr(self, name), name)
        _require_tuple(self.allowed_tools, "allowed_tools", str)
        _require_tuple(self.approval_gates, "approval_gates", str)
        _require_tuple(self.required_evals, "required_evals", str)
        _require_tuple(self.evidence_required, "evidence_required", str)
        _require_mapping(self.owner_override, "owner_override")
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")

    @classmethod
    def from_recipe(
        cls,
        policy_id: str,
        version: str,
        recipe: LoopRecipe,
        policy_decision_id: str,
        *,
        owner_override: Optional[dict[str, Any]] = None,
        enabled: bool = False,
    ) -> "LoopPolicy":
        if not isinstance(recipe, LoopRecipe):
            raise ValueError("recipe must be a LoopRecipe")
        return cls(
            policy_id=policy_id,
            version=version,
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.version,
            policy_decision_id=policy_decision_id,
            loop_type=recipe.loop_type,
            trigger=recipe.trigger,
            objective=recipe.objective,
            stop_condition=recipe.stop_condition,
            max_attempts=recipe.max_attempts,
            max_runtime_s=recipe.max_runtime_s,
            max_cost_usd=recipe.max_cost_usd,
            max_model_calls=recipe.max_model_calls,
            max_tool_calls=recipe.max_tool_calls,
            max_total_tokens=recipe.max_total_tokens,
            max_download_bytes=recipe.max_download_bytes,
            max_storage_bytes=recipe.max_storage_bytes,
            allowed_tools=recipe.allowed_tools,
            approval_gates=recipe.approval_gates,
            required_evals=recipe.required_evals,
            recovery_policy=recipe.recovery_policy,
            evidence_required=recipe.evidence_required,
            owner_override=owner_override or {},
            enabled=enabled,
        )


@dataclass(frozen=True)
class EvalCase:
    eval_case_id: str
    version: str
    category: str
    objective: str
    input_fixture: dict[str, Any]
    expected_behavior: str
    required_evidence: tuple[str, ...]
    scorer: str
    threshold: float
    release_gate: bool = False
    autonomy_gate: bool = False

    def __post_init__(self) -> None:
        for name in ("eval_case_id", "version", "category", "objective", "expected_behavior", "scorer"):
            _require_text(getattr(self, name), name)
        _require_mapping(self.input_fixture, "input_fixture")
        _require_tuple(self.required_evidence, "required_evidence", str)
        _require_probability(self.threshold, "threshold")
        if not isinstance(self.release_gate, bool) or not isinstance(self.autonomy_gate, bool):
            raise ValueError("release_gate and autonomy_gate must be bools")


@dataclass(frozen=True)
class EvalRun:
    eval_run_id: str
    eval_case_id: str
    eval_case_version: str
    status: EvalStatus
    threshold: float
    score: Optional[float] = None
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    tool_call_refs: tuple[str, ...] = ()
    policy_decision_refs: tuple[str, ...] = ()
    context_manifest_ref: Optional[str] = None
    receipt_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    finding_refs: tuple[str, ...] = ()
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("eval_run_id", "eval_case_id", "eval_case_version"):
            _require_text(getattr(self, name), name)
        _require_enum(self.status, EvalStatus, "status")
        _require_probability(self.threshold, "threshold")
        if self.score is not None:
            _require_probability(self.score, "score")
        for name in ("run_id", "trace_id", "context_manifest_ref", "started_at", "completed_at"):
            _require_optional_text(getattr(self, name), name)
        for name in ("tool_call_refs", "policy_decision_refs", "receipt_refs", "artifact_refs", "finding_refs"):
            _require_tuple(getattr(self, name), name, str)


@dataclass(frozen=True)
class EvalFinding:
    finding_id: str
    eval_run_id: str
    category: str
    severity: FindingSeverity
    summary: str
    remediation_owner: str
    status: str
    defect_ref: Optional[str] = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("finding_id", "eval_run_id", "category", "summary", "remediation_owner", "status"):
            _require_text(getattr(self, name), name)
        _require_enum(self.severity, FindingSeverity, "severity")
        _require_optional_text(self.defect_ref, "defect_ref")
        _require_tuple(self.evidence_refs, "evidence_refs", str)


@dataclass(frozen=True)
class SystemEntity:
    entity_id: str
    entity_type: SystemEntityType
    canonical_key: str
    name: str
    status: str
    version: str
    owner_domain: str
    source_ref: str
    observed_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("entity_id", "canonical_key", "name", "status", "version", "owner_domain", "source_ref", "observed_at"):
            _require_text(getattr(self, name), name)
        _require_enum(self.entity_type, SystemEntityType, "entity_type")
        _require_mapping(self.metadata, "metadata")


@dataclass(frozen=True)
class SystemEdge:
    edge_id: str
    from_entity_id: str
    edge_type: str
    to_entity_id: str
    version: str = ""
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 1.0
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("edge_id", "from_entity_id", "edge_type", "to_entity_id", "version"):
            _require_text(getattr(self, name), name)
        _require_tuple(self.evidence_refs, "evidence_refs", str)
        _require_probability(self.confidence, "confidence")
        _require_optional_text(self.valid_from, "valid_from")
        _require_optional_text(self.valid_to, "valid_to")
