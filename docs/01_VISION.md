# TOBI Vision

## Mission

TOBI is being built as a personal Jarvis: an assistant that understands its owner over time, safely performs real work across a computer and connected services, and remains available as a continuous presence rather than a disposable chat session.

The current system is a foundation for that goal, not the finished product.

## Three Product Pillars

### 1. Understand the owner

TOBI should retain durable facts, decisions, preferences, routines, project context, and feedback. It should retrieve only relevant context, distinguish known facts from inference, let the owner review or delete memory, and avoid repeatedly asking for information already provided.

Current foundations include the Brain memory store, conversation history, project resources, lessons, semantic retrieval, and the static persona in `SOUL.md`. The remaining challenge is a deeper and more reliable preference/habit model with proactive recall.

### 2. Perform real work safely

TOBI should be able to use Mission Control, files, the terminal, the browser, applications, and connected services. Capability must be paired with visible execution, audit history, reversible defaults, permission-aware behavior, and confirmation before destructive or sensitive work.

Current foundations include Conductor tools, the full-machine terminal engine, project/task operations, integrations, MCP, research, and workflow engines. Browser and desktop control, broader automation, and stronger policy enforcement remain future work.

### 3. Remain available and proactive

TOBI should run reliably, preserve state across sessions, surface important events, and be reachable through appropriate channels. Proactivity should eventually come from meaningful events and learned context, not only fixed schedules.

Current foundations include Mission Control, Telegram, the CLI, scheduled jobs, health reporting, storage/usage visibility, and Hermes synchronization. Voice, event-driven observation, personal-PC service hardening, and context-aware interruption are not complete.

## System Roles

TOBI is currently a composed system:

- The Python application is the main orchestrator and execution layer.
- Mission Control is the owner-facing cockpit for chat, memory, projects, tools, settings, and governance.
- The Conductor translates conversation into grounded reads and audited actions.
- SQLite and project resource storage hold most application state.
- Hermes is an integrated runtime for persona, skills, memory, and model-routing sync, but the integration is one-way in several places and Hermes is not the only source of truth.
- The MMO/business portfolio loop is a substantial capability and proving ground, not TOBI's identity.

## Product Principles

1. Show real capability, not optimistic badges.
2. Ground state claims in live data or label them as unknown.
3. Keep the owner in control of destructive, external, or sensitive actions.
4. Make actions observable, cancellable where practical, and auditable.
5. Reuse one memory, tool, permission, and model-routing architecture across surfaces.
6. Preserve user data and backward compatibility when replacing modes or modules.
7. Prefer local/private ownership of state and secrets.
8. Treat web pages, project files, and external tool output as untrusted input.
9. Keep Mission Control understandable to the owner and precise enough for an AI coding agent.

## Definition of Done

TOBI reaches the vision when the owner can state an outcome in ordinary language and TOBI can:

- recover the relevant owner and project context without re-explanation;
- explain what it can and cannot do;
- choose a safe execution path;
- request approval only when the risk warrants it;
- perform the work across the required tools;
- report progress and evidence;
- preserve the result and lessons for the next session;
- proactively surface genuinely important changes through the right channel.
