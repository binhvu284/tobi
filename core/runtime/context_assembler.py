"""Compatibility context assembly for the legacy Conductor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from core.chat_runtime_contracts import ContextManifest
from core.runtime.intent_router import needs_episodic_recall

ProfileLoader = Callable[[], str]
TierLoader = Callable[[], str]
ManifestRenderer = Callable[[ContextManifest], str]
PromptBuilder = Callable[..., str]
HistoryLoader = Callable[..., list[dict[str, Any]]]
RecallDetector = Callable[[str], bool]

_EPISODIC_RECALL_PROMPT = (
    "\n\n\u26a0 EPISODIC RECALL: The owner is asking about past conversations. "
    "Use the recall_conversations tool to retrieve relevant messages BEFORE responding. "
    "Extract the time reference (e.g., 'yesterday', 'last week') and topic from their "
    "message and pass them as the 'when' and 'query' args. "
    "If the owner asks broadly ('what did we discuss yesterday?'), summarize the returned "
    "messages. If they ask specifically ('when did we discuss X?'), report exact messages "
    "with timestamps and which session they came from."
)


@dataclass(frozen=True)
class ContextSources:
    """Content already selected by the existing manifest or legacy owners."""

    profile: str
    tier_context: str
    manifest_text: str


@dataclass(frozen=True)
class PreparedPrompt:
    """The attachment-expanded owner message and exact system prompt."""

    message: str
    system: str


def resolve_context_sources(
    context_manifest: Optional[ContextManifest],
    *,
    profile_loader: ProfileLoader,
    tier_loader: TierLoader,
    manifest_renderer: Optional[ManifestRenderer] = None,
) -> ContextSources:
    """Preserve Conductor's manifest and legacy source-selection branches."""

    if context_manifest is not None:
        profile = context_manifest.source_content("owner_memory")
        tier_context = context_manifest.source_content("evolution")
        try:
            if manifest_renderer is None:
                from core.context_manager import prompt_context

                manifest_renderer = prompt_context
            manifest_text = manifest_renderer(context_manifest)
        except Exception:
            manifest_text = ""
    else:
        try:
            profile = profile_loader()
        except Exception:
            profile = ""
        tier_context = tier_loader()
        manifest_text = ""
    return ContextSources(profile=profile, tier_context=tier_context, manifest_text=manifest_text)


def prepare_prompt_context(
    message: str,
    attachments_text: Optional[str],
    sources: ContextSources,
    *,
    tools_enabled: bool,
    surface: str,
    directives: Optional[str],
    extra_tools: Optional[list[str]],
    denied_tools: Optional[set[str]],
    allowed_tools: Optional[set[str]],
    prompt_builder: PromptBuilder,
    recall_detector: RecallDetector = needs_episodic_recall,
) -> PreparedPrompt:
    """Build the exact prompt inputs without changing their current owners."""

    expanded_message = message
    if attachments_text:
        expanded_message = f"{message}\n\n[Attached content the owner shared]\n{attachments_text}"
    system = prompt_builder(
        sources.profile,
        tools_enabled,
        surface,
        directives,
        extra_tools,
        user_message=expanded_message,
        denied_tools=denied_tools,
        allowed_tools=allowed_tools,
        tier_context=sources.tier_context,
        context_text=sources.manifest_text,
    )
    if tools_enabled and recall_detector(expanded_message):
        system += _EPISODIC_RECALL_PROMPT
    return PreparedPrompt(message=expanded_message, system=system)


def prepare_model_messages(
    message: str,
    history: Optional[list[dict]],
    chat_id: int,
    *,
    history_loader: HistoryLoader,
) -> list[dict]:
    """Copy explicit history or load the legacy six-turn fallback, then append the turn."""

    prior = history if history is not None else history_loader(chat_id, limit=6)
    return list(prior) + [{"role": "user", "content": message}]
