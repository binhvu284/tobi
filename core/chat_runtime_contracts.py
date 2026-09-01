"""Typed contracts shared by the Mission Control chat runtime.

The contracts deliberately use stdlib dataclasses so the runtime does not add a
validation dependency to the existing FastAPI/Pydantic application.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional


ModeId = Literal["chat", "agent"]
TrustLevel = Literal["trusted", "owner", "untrusted"]


@dataclass(frozen=True)
class TurnRequest:
    session_id: int
    message: str
    mode: ModeId = "chat"
    model: Optional[str] = None
    client_turn_id: Optional[str] = None
    resume_run_id: Optional[int] = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    workflow_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteDecision:
    route: str
    intent: str
    confidence: float
    allowed_tools: tuple[str, ...] = ()
    requires_clarification: bool = False
    reason: str = ""
    max_tool_steps: int = 0
    step_tokens: int = 700
    final_tokens: int = 1600


@dataclass(frozen=True)
class ContextItem:
    source: str
    label: str
    content: str
    trust: TrustLevel
    relevance: float
    token_cost: int
    version: str = "1"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextManifest:
    mode: ModeId
    token_budget: int
    items: list[ContextItem] = field(default_factory=list)
    total_tokens: int = 0

    def add(self, item: ContextItem) -> bool:
        if item.token_cost <= 0 or self.total_tokens + item.token_cost > self.token_budget:
            return False
        self.items.append(item)
        self.total_tokens += item.token_cost
        return True

    def source_content(self, source: str) -> str:
        return "\n\n".join(item.content for item in self.items if item.source == source)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk: str
    allowed_modes: tuple[ModeId, ...]
    args_schema: dict[str, Any]
    result_schema: dict[str, Any]
    timeout_s: int
    retry_policy: str
    idempotent: bool
    required_integrations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    idempotency_key: Optional[str] = None


@dataclass
class ToolResult:
    ok: bool
    tool: str
    data: Any = None
    error: Optional["TurnError"] = None
    receipt_key: Optional[str] = None
    replayed: bool = False


@dataclass(frozen=True)
class TurnError:
    code: str
    stage: str
    message: str
    retryable: bool = False
    safe_detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryOptions:
    actions: tuple[str, ...] = ("resume", "retry_step", "skip_step", "revise", "cancel")
    run_id: Optional[int] = None
    failed_step_id: Optional[int] = None


@dataclass
class TurnOutcome:
    status: str
    reply: str = ""
    tools_used: list[str] = field(default_factory=list)
    error: Optional[TurnError] = None
    recovery: Optional[RecoveryOptions] = None
