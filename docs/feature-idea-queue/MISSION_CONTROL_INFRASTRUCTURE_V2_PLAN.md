# Mission Control Infrastructure V2 Plan

## Queue Contract

| Field | Decision |
|---|---|
| Queue item | `#21` |
| Status | Queued design only |
| Delivery order | Start only after queue items `#18` and `#20` are accepted and merged |
| Primary outcome | Make Mission Control the authoritative, reliable control plane for TOBI |
| First usable release | Reliable Chat/Agent runtime with durable runs, typed tools, policy, and traceability |
| Migration style | Incremental strangler migration behind per-domain flags |
| Deployment posture | Local-first on the owner's Windows/D-drive environment; managed services remain optional |
| Worker model | Small sequential packages; one implementation worker at a time |
| Compatibility | Preserve existing conversations, actions, runs, tools, pages, Telegram, CLI, Office, and schedulers through adapters |
| Planning boundary | This document and the queue row are the only deliverables now; do not implement from this planning task |

This plan consolidates TOBI around Mission Control (MC). MC becomes the owner of run state, policy, approvals, tools, context, audit, observability, and shared UI projections. Hermes remains useful as a managed execution engine, but it must not become a second control plane.

Before implementation, reconcile this plan against the delivered state of:

- [TOBI Coding Agent / Controlled Self-Development System](TOBI_CODING_AGENT_SELF_DEVELOPMENT_PLAN.md) (`#18`)
- [Brain Context & Architecture V2](BRAIN_CONTEXT_ARCHITECTURE_V2_PLAN.md) (`#20`)
- [Current TOBI architecture](../ARCHITECTURE.md)
- [Current Mission Control guide](../MISSION_CONTROL.md)

Do not implement `#18`, `#20`, and `#21` in parallel. They share Chat/Agent orchestration, durable execution, tool policy, Brain context, Hermes, database migrations, observability, and frontend state.

## 1. Outcome And Non-Goals

### 1.1 Required outcome

MC must be able to:

1. accept an owner request from Chat, Agent, a page action, CLI, Telegram, Office, or a scheduler;
2. classify the request with deterministic rules before model planning;
3. assemble only relevant owner, project, system, and conversation context;
4. select tools from a filtered, typed registry;
5. enforce permissions, approvals, budgets, and trust boundaries centrally;
6. execute short or long workflows with persisted checkpoints and idempotency;
7. stream one ordered run history to every relevant MC page;
8. recover the same run after failure, restart, disconnect, or owner intervention;
9. produce grounded answers and action receipts from actual evidence;
10. learn from verified outcomes and explicit owner feedback without silently changing safety policy.

### 1.2 V1 non-goals

- multi-tenant SaaS hosting;
- replacing SQLite before measured contention requires it;
- forcing every internal call through a network MCP server;
- adopting Temporal, Trigger.dev, or Inngest before the local durable runtime is proven insufficient;
- unrestricted autonomous computer control;
- arbitrary multi-agent swarms;
- removing legacy Chat, Conductor, `agent_runs`, or `tobi_actions` during the first release;
- rebuilding the frontend design system;
- changing Supabase or Vercel.

## 2. Graphify-Guided Current-State Audit

Graphify is a navigation index only. The available graph was built at commit `c39c34a`, while this plan was verified against source commit `8f07c32`; workers must refresh or re-check the graph after `#18` and `#20` merge.

```mermaid
flowchart LR
  Owner["Owner"] --> MC["Mission Control web app"]
  MC --> API["FastAPI dashboard API"]
  API --> Chat["Chat Runtime v2 and legacy route"]
  Chat --> Conductor["Conductor"]
  Conductor --> Models["Model router"]
  Conductor --> Tools["Read, action, terminal, connector tools"]
  Chat --> Context["Context manager"]
  Context --> Brain["Brain and Graph"]
  Tools --> Data["SQLite and project resources"]
  Tools --> MCP["MCP and A2A"]
  Models --> Hermes["Hermes routing sync"]
  Brain --> Hermes
  API --> Pages["MC domain pages"]
  Telegram["Telegram"] --> Conductor
  CLI["CLI and schedulers"] --> Tools
```

| Node | Current truth | V2 gap |
|---|---|---|
| FastAPI boundary | `api/dashboard.py` owns a very large set of routes, SSE, static hosting, and orchestration glue | High collision risk; HTTP concerns and domain services are not consistently separated |
| Conductor | `core/conductor.py` owns classification, prompts, tool catalog behavior, execution, permissions, confirmations, action logging, and surface-specific behavior | God-module blast radius; policy and tool behavior are difficult to evolve independently |
| Chat Runtime v2 | Typed turn/tool/error contracts, context manifests, telemetry, bounded workers, runtime flags, and recovery routes exist | It coexists with legacy orchestration; contracts are incomplete as a platform-wide runtime |
| Agent runs | `agent_runs` and steps persist Chat Agent history and same-run recovery | Not yet the universal durable workflow state for page actions, coding workflows, Office, CLI, or schedulers |
| Actions | `tobi_actions` stores proposals and outcomes | Action history and run history are related but separate; no canonical append-only event stream |
| Tool registry | Typed `ToolSpec` validation exists for the Chat runtime | Tool metadata, MCP tools, Conductor functions, terminal capabilities, and page commands still have multiple ownership paths |
| Context | A `ContextManifest` and token budgets exist | Owner intelligence is not consistently applied to routing, planning, tool choice, and final response across all surfaces |
| Brain and Graph | Brain stores durable memories; Graph exposes relationships and retrieval | Graph is more visible than causal; certainty, provenance, relevance, and feedback need typed decision influence |
| Hermes | Startup, persona/skills, memory, and model routing have several one-way sync paths | No single synchronization contract; split-brain behavior is possible |
| MCP/A2A | Inbound/outbound tools, scopes, approvals, audits, and discovery exist | MCP is not yet the canonical tool description shared by local tools, pages, and the runtime |
| MC pages | Rich domain pages exist and each has useful local state | Cross-page actions, run progress, recovery, and audit are not projected from one shared live state |
| Observability | Usage, actions, runtime events, performance doctor, and page-specific status exist | No unified trace joins request, context, route, model, tool, approval, artifact, cost, and owner feedback |
| Evals | Strong feature-specific test suites exist | No required behavioral gate for tool choice, context quality, workflow recovery, or hallucination resistance |
| Security | Vault, mode denial, terminal gates, MCP scopes, SSRF guards, and prompt boundaries exist | Policy is distributed; excessive agency, cross-surface permissions, budgets, and untrusted evidence need one authority |

### 2.1 Existing assets to preserve

- `core/chat_runtime.py` and `core/chat_runtime_contracts.py` as the seed for the shared runtime contracts;
- `core/tool_registry.py` as a migration source, not a second permanent registry;
- `core/context_manager.py` as the first manifest builder;
- `core/agent_runs.py` and `tobi_actions` as compatibility data sources;
- current mode enforcement, terminal safety, vault, network guard, MCP security, artifact storage, and SSE behavior;
- all saved conversations and message metadata;
- existing page APIs until domain adapters are proven;
- rollback flags already used by Chat and feature pages.

## 3. Research Decisions

Use the following primary/official references as design inputs, not automatic dependency choices:

| Topic | Reference | Decision for TOBI |
|---|---|---|
| Durable execution | [Temporal](https://docs.temporal.io/), [Trigger.dev](https://trigger.dev/docs), [Inngest](https://www.inngest.com/docs) | Build a small local durable state machine first. Re-evaluate managed execution only for multi-host, high-volume, or operationally demanding workloads. |
| Tool interoperability | [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture), [MCP authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) | Make one canonical tool contract MCP-compatible while allowing direct in-process local invocation. |
| Agent runtimes | [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Google ADK](https://google.github.io/adk-docs/), [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), [AutoGen Core](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/index.html) | Borrow checkpoints, typed handoffs, sessions, guardrails, and traces. Avoid framework lock-in and unrestricted agent teams. |
| Agent memory | [Letta memory](https://docs.letta.com/guides/agents/memory), [Mem0 memory types](https://docs.mem0.ai/core-concepts/memory-types), [LlamaIndex memory](https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/memory/) | Use relevance-gated typed memory with provenance and certainty; do not inject the full profile every turn. |
| Browser/computer action | [Playwright](https://playwright.dev/docs/intro), [E2B](https://e2b.dev/docs), [Browser Use](https://docs.browser-use.com/) | Use deterministic Playwright workflows first. Keep E2B optional for isolated risky jobs and Browser Use optional for adaptive sites. |
| Observability/evals | [OpenTelemetry](https://opentelemetry.io/docs/concepts/), [Phoenix](https://arize.com/docs/phoenix), [Braintrust](https://www.braintrust.dev/docs), [LangSmith](https://docs.langchain.com/langsmith/home) | Emit OpenTelemetry-compatible local traces first. Keep vendor exporters optional; use MC as the owner-facing trace UI. |
| LLM security | [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/) | Treat prompt injection, sensitive disclosure, excessive agency, supply-chain tools, and unbounded consumption as release gates. |

### 3.1 Durable-runtime decision gate

Stay on the local runtime while all are true:

- one owner and one primary MC deployment;
- SQLite remains healthy under concurrency tests;
- workflows can recover after process restart;
- local scheduling and workers meet latency targets;
- no cross-region or always-on worker requirement exists.

Open a separate architecture decision record before adopting a managed service. The ADR must compare operational burden, Windows/local support, D-drive data placement, offline behavior, lock-in, cost, secrets, migration complexity, and rollback.

## 4. Locked Product Decisions

The 60-question intake is summarized below. Workers must not reopen these choices unless current code makes one impossible.

| Area | Locked decision |
|---|---|
| Authority | MC is the authoritative control plane |
| Migration | Incremental strangler migration |
| Success priority | Action reliability first |
| Scope | All MC pages eventually; reliable Chat/Agent core first |
| Conductor | Thin compatibility facade after migration |
| Backend structure | Shared core services plus staged page adapters |
| Queue order | Implement after `#18` and `#20` |
| Other surfaces | Telegram, CLI, Office, and schedulers use compatibility adapters initially |
| Deployment | Local-first hybrid |
| Ownership | Single-owner, future-ready data and API contracts |
| Runtime | Local durable runtime first |
| Delivery semantics | At-least-once execution with idempotency |
| Approvals | Risk-based approvals |
| Recovery | Runs resumable indefinitely; safe steps auto-resume after restart |
| Retry | Bounded retry, then same-run recovery card |
| Tool contract | MCP-style canonical contract; direct local invocation allowed |
| First tool domains | Files, terminal, and projects |
| Discovery | Filtered registry, not an all-tools prompt |
| Policy | One central policy engine |
| Results | Typed result plus durable action receipt |
| Routing | Deterministic rules, then structured planner |
| Missing capability | Offer setup or a safe alternative |
| Owner intelligence | Influences routing through final response |
| Certainty | `known`, `inferred`, `contradicted`, or `stale` |
| Learning | Explicit feedback plus verified outcomes |
| Corrections | Supersede immediately while retaining history |
| Context visibility | Context chips plus expandable manifest |
| Memory use | Relevance-gated |
| Hermes | Managed engine component |
| Sync authority | MC-authoritative selective sync; MC wins conflicts |
| Multi-agent | Orchestrator with bounded workers |
| Handoffs | Typed task and artifact handoffs |
| Isolation | Local isolation first; E2B optional |
| Browser | Deterministic Playwright first |
| External commitments | Require approval before execution |
| Browser evidence | Trace plus key screenshots |
| Telemetry | OpenTelemetry-compatible events plus MC local UI |
| Trace UX | Concise by default, expandable details |
| Retention | Full trace 90 days, then redacted summary |
| Evals | Required regression gates |
| Dataset | Golden cases plus real production failures |
| Reliability target | At least 95% supported-workflow completion or structured recovery |
| Trust | Label by source class; trust never grants instruction authority |
| Credentials | Vault-brokered, purpose-bound access |
| Budgets | Per-run hard limits |
| Run UI | Global Runs center plus contextual page views |
| Frontend state | Shared live projections across pages |
| Failure UX | Actionable recovery cards |
| Schema | Additive shared runtime tables |
| History | Append-only events plus projections |
| Rollback | Per-domain feature flags |
| Services | Targeted managed services allowed only after an ADR |
| Delivery packages | Small sequential worker packages |
| Docs | Update after each accepted phase |
| Build order | Runtime, then tools, then owner intelligence |
| Activation | Shadow mode, then staged defaults |

## 5. Target Architecture

```mermaid
flowchart TB
  subgraph Surfaces["Owner and system surfaces"]
    Chat["Chat and Agent"]
    Pages["MC domain pages"]
    RunsUI["Runs center"]
    CLI["CLI"]
    Telegram["Telegram"]
    Office["Office"]
    Scheduler["Schedulers"]
  end

  subgraph Gateway["Mission Control control plane"]
    Turn["Turn and command gateway"]
    Router["Hybrid intent router"]
    Context["Context and owner-intelligence assembler"]
    Planner["Typed planner and clarification gate"]
    Policy["Policy, approval, budget, and trust engine"]
    Runtime["Durable workflow runtime"]
    Tools["Canonical tool registry and router"]
    Events["Append-only events and projections"]
    Trace["Trace, metrics, evals, and feedback"]
  end

  subgraph Engines["Managed engines and adapters"]
    Local["Local Python tools"]
    MCP["MCP clients and server"]
    Terminal["Terminal and files"]
    Browser["Playwright browser worker"]
    Hermes["Hermes managed worker"]
    Model["Model providers"]
    Brain["Brain and Graph"]
    Connectors["External connectors"]
  end

  Surfaces --> Turn
  Turn --> Router
  Router --> Context
  Router --> Planner
  Context --> Planner
  Planner --> Policy
  Policy --> Runtime
  Runtime --> Tools
  Tools --> Engines
  Runtime --> Events
  Context --> Events
  Policy --> Events
  Engines --> Events
  Events --> Trace
  Events --> Surfaces
```

### 5.1 Domain ownership

| Domain | Sole responsibility | Must not own |
|---|---|---|
| Turn gateway | Request validation, identity/surface, idempotency, SSE/reconnect | Tool logic, prompts, persistence SQL |
| Intent router | Deterministic classification, confidence, candidate capabilities | Tool execution or owner memory retrieval |
| Context service | Context manifests, relevance, certainty, provenance, token budgets | Permission decisions or action execution |
| Planner | Typed plans, dependencies, clarification needs, expected artifacts | Direct side effects |
| Policy engine | Mode/surface capability, risk, approval, credential, budget, isolation decisions | UI rendering or model prose |
| Workflow runtime | State transitions, leases, checkpoints, retries, cancellation, resume | Tool implementations or provider-specific parsing |
| Tool registry/router | Canonical schemas, discovery, validation, invocation adapter selection | Owner-facing response composition |
| Event store | Append-only durable facts with sequence numbers | Business decisions |
| Projection service | Current run/page views derived from events | Mutable source-of-truth history |
| Trace/eval service | Timings, cost, redaction, datasets, scores, feedback | Execution authority |
| Response composer | Grounded owner-facing result from evidence and receipts | New actions or hidden tool calls |
| Surface adapters | Translate Chat/page/CLI/Telegram requests and render events | Duplicated policy or orchestration |

### 5.2 Conductor end state

Keep in `Conductor`:

- stable `answer(...)` compatibility entry point;
- surface normalization for old callers;
- shared butler persona reference until the response composer owns it;
- translation from legacy callbacks/events to the new gateway;
- one feature flag selecting legacy or V2 behavior.

Move out:

| Current concern | Target owner |
|---|---|
| intent classification | `intent_router` |
| prompt/tool catalog construction | `planner` plus filtered `tool_registry` |
| tool argument parsing/repair | typed model adapter plus `tool_router` |
| mode and risk permissions | `policy_engine` |
| approval creation/resolution | `approval_service` |
| action execution | `workflow_runtime` plus `tool_router` |
| action logging | `event_store` plus compatibility projector |
| Brain/profile assembly | `context_service` |
| provider fallback | `model_adapter` |
| final grounding/persona | `response_composer` |
| Telegram-specific limitations | Telegram surface policy |

The migration must delegate one concern at a time. Do not rewrite `conductor.py` in one worker task.

## 6. Core Contracts

Use validated dataclasses or Pydantic models consistently. No unvalidated dictionary may cross a domain boundary.

### 6.1 Run and plan contracts

```text
RunRequest
  request_id, surface, owner_id, session_id, mode, message, attachments,
  capability_toggles, selected_project, client_timestamp, budget_profile

RouteDecision
  route_class, intent, confidence, candidate_capabilities, clarification,
  context_requirements, planner_required, reasons

ExecutionPlan
  plan_id, run_id, objective, assumptions, steps[], expected_artifacts,
  approval_points, completion_predicate, budget

PlanStep
  step_id, kind, tool_name, arguments, depends_on[], risk, timeout,
  retry_policy, idempotency_key, required_capabilities, output_contract

RunEvent
  event_id, run_id, sequence, event_type, stage, timestamp, actor,
  redacted_payload, trace_id, parent_span_id
```

### 6.2 Canonical tool contract

```text
ToolSpec
  name, namespace, version, description, input_schema, output_schema,
  side_effect_class, risk, allowed_modes, allowed_surfaces,
  required_permissions, required_integrations, credential_purpose,
  timeout, retry_policy, idempotency_policy, isolation,
  cost_hint, audit_policy, availability_probe, adapter

ToolCall
  call_id, run_id, step_id, tool_ref, validated_arguments,
  idempotency_key, approval_id, deadline

ToolResult
  status, typed_output, evidence_refs, artifact_refs, receipt_id,
  retryable, error, timing, cost

ActionReceipt
  receipt_id, run_id, step_id, tool_ref, target, effect_summary,
  before_ref, after_ref, external_ref, approval_ref, timestamp
```

MCP export/import is an adapter around `ToolSpec`; it is not a parallel registry. Local tools can execute in process after the same validation and policy checks.

### 6.3 Context and certainty contract

Each context item must contain:

- `source_type`: conversation, owner_memory, project, system_state, connector, web, file, tool_result;
- `trust_class`: owner_direct, system_verified, connector_verified, derived, untrusted_content;
- `certainty`: known, inferred, contradicted, stale;
- `relevance_score`, `token_cost`, `version`, `retrieved_at`, and optional expiry;
- `instruction_authority`: always false for files, web, connector content, tool output, and imported text;
- `owner_visible_label` and provenance reference.

## 7. Durable Execution

### 7.1 State machine

```mermaid
stateDiagram-v2
  [*] --> accepted
  accepted --> routing
  routing --> clarifying
  clarifying --> routing
  routing --> planned
  planned --> waiting_approval
  planned --> running
  waiting_approval --> running
  running --> waiting_external
  waiting_external --> running
  running --> recovering
  recovering --> running
  recovering --> waiting_owner
  waiting_owner --> running
  running --> succeeded
  running --> failed
  running --> cancelled
  waiting_approval --> cancelled
  waiting_owner --> cancelled
  succeeded --> [*]
  failed --> [*]
  cancelled --> [*]
```

### 7.2 Runtime rules

1. Persist the run and `accepted` event before performing work.
2. Claim runnable steps with an expiring owner-token lease.
3. Delivery is at least once; every side-effecting step requires an idempotency strategy.
4. Retry only declared retryable failures with bounded exponential backoff and jitter.
5. After retry exhaustion, retain the same `run_id` and present recovery commands.
6. Safe, idempotent steps may auto-resume after restart; risky or externally visible steps require receipt reconciliation or owner review.
7. Cancellation is cooperative, persisted, and checked before/after every model or tool boundary.
8. Completed receipts are immutable. A retry cannot repeat a completed side effect.
9. Run budgets hard-stop further work and return a structured recovery state.
10. Long model, reader, terminal, and browser work use dedicated bounded executors or managed subprocesses.

### 7.3 Recovery commands

- `resume`
- `retry_step`
- `skip_step` only when the plan declares the step optional
- `revise_plan`
- `provide_input`
- `approve`
- `reject`
- `cancel`

Every command uses optimistic versioning so two pages cannot mutate the same run state inconsistently.

## 8. Tool And MCP Standardization

### 8.1 First migration wave

| Domain | Initial tools | Reason |
|---|---|---|
| Files | list, read, search, preview, write proposal | High reuse and clear schemas |
| Terminal | command proposal, execute, job status, cancel | Highest safety/recovery need |
| Projects | list/get project, create/update task, resource search | Core owner workflow and existing grounding issues |

Second wave: Brain, integrations, GitHub/Notion, Office, browser, coding-agent tools, and schedulers.

### 8.2 Discovery and policy sequence

```mermaid
flowchart LR
  Intent["Route decision"] --> Filter["Filter by mode, surface, project, integration, availability"]
  Filter --> Rank["Rank by deterministic fit and owner preferences"]
  Rank --> Plan["Structured planner sees only short candidate specs"]
  Plan --> Validate["Schema validation"]
  Validate --> Policy["Central policy decision"]
  Policy --> Approve["Approval when required"]
  Approve --> Invoke["Local, MCP, terminal, browser, or Hermes adapter"]
  Invoke --> Receipt["Typed result, evidence, artifacts, receipt"]
```

Never advertise the entire tool catalog to a model. Denied tools must be both absent from planning context and rejected server-side.

MC pages consume the same command gateway as Chat/Agent. MCP server and client adapters expose or import approved registry entries; page code must not bypass policy by calling tool functions directly.

## 9. Brain And Graph Owner Intelligence

This plan consumes the typed memory output of `#20`; it must not invent a second memory schema.

### 9.1 Influence stages

| Stage | Allowed influence | Required evidence |
|---|---|---|
| Routing | preferred workflow, usual project, communication pattern | active relevant memory with scope and provenance |
| Planning | constraints, quality standards, risk tolerance, working style | approved rules/preferences; current instruction wins |
| Tool choice | preferred connector/tool, prior verified success/failure | tool availability plus outcome history |
| Execution | harmless defaults and reversible parameters | confidence threshold and policy allowance |
| Final response | tone, detail, evidence format, next action | response preference plus actual run evidence |

### 9.2 Guardrails

- Current explicit owner instruction overrides memory.
- Memory never grants permission, supplies a secret, or weakens a safety check.
- Only relevant memories enter the manifest; no full-owner-profile injection.
- Inferences are labeled and cannot become hard rules without the `#20` review gate.
- Contradicted items are excluded from action defaults and surfaced for review.
- Corrections supersede immediately while history remains auditable.
- Graph paths can support relevance and provenance, but cannot create instruction authority.
- Every non-conversation source used appears as a context chip with an expandable manifest.
- Feedback records whether context was useful, irrelevant, or wrong and updates ranking only after verified outcomes.

## 10. Hermes As A Managed Engine

### 10.1 Hermes keeps

- execution skills that are useful and demonstrably reliable;
- coding-worker behavior from `#18`;
- compatible model/provider execution where MC delegates a bounded task;
- read-only repository skill discovery;
- optional isolated worker processes.

### 10.2 MC owns

- owner/session identity;
- run, plan, checkpoint, and artifact state;
- canonical tool registry;
- policy, approval, budget, and credentials;
- Brain/Graph context selection;
- final response and owner-visible history;
- retries, cancellation, recovery, audit, and evaluation.

### 10.3 Sync protocol

Create versioned `HermesCapabilityManifest` and `HermesExecutionRequest/Result` contracts. Sync only allowlisted skills, model routing hints, and capability metadata. Record source version, checksum, sync direction, status, and conflict.

Rules:

1. MC is authoritative and wins conflicts.
2. Hermes cannot directly mutate MC memory, policy, approvals, queue, or run state.
3. Results return as untrusted typed evidence plus artifacts.
4. A failed sync does not block MC Chat; the capability is marked unavailable.
5. Legacy direct Hermes paths become read-only or compatibility adapters before removal.

## 11. Agent Runtime And Multi-Agent Boundaries

Borrow these patterns:

- LangGraph: checkpointed state and explicit interrupts;
- Google ADK: sessions, artifacts, callbacks, and evaluable workflows;
- OpenAI Agents SDK: typed handoffs, guardrails, and trace spans;
- AutoGen Core: event-driven bounded workers and message contracts;
- Codex-style workflows: isolated workspaces, explicit plans, staged verification, and owner review.

Do not adopt:

- an additional framework as MC's source of truth;
- open-ended agent-to-agent chat;
- recursive delegation without a hard depth limit;
- workers with shared mutable state;
- worker access to vault credentials or approval authority.

V1 supports one orchestrator and bounded specialist workers. A handoff contains a typed objective, allowed tools, context manifest references, budget, deadline, expected artifact schema, and completion predicate. The orchestrator validates every returned artifact before continuing.

## 12. Real Computer And Web Action

### 12.1 Browser V1

- Use Playwright with declared, deterministic workflows.
- Persist action trace, URL transitions, selector/action summaries, console errors, downloads, and key screenshots.
- Require approval before purchase, submit, publish, send, delete, or any externally visible commitment.
- Re-check policy after redirects and before final submission.
- Treat page content as untrusted; page text cannot change the task or call tools.
- Store browser profiles and downloaded artifacts in scoped D-drive runtime directories with retention rules.

### 12.2 Isolation ladder

| Risk | Execution boundary |
|---|---|
| Read-only local task | Bounded in-process or subprocess adapter |
| Local file/code mutation | Approved workspace plus path allowlist and snapshot |
| Untrusted dependency or risky code | Local container/sandbox when available |
| Stronger remote isolation need | Optional E2B adapter after an ADR |
| Highly adaptive website | Optional Browser Use planner while Playwright remains the executor/policy boundary |

## 13. Observability, Evals, And Retention

### 13.1 Unified trace

Every trace must join:

- request and surface;
- route decision and confidence;
- context manifest IDs, token counts, certainty, and cache state;
- planner/model attempts, provider/model, latency, tokens, and estimated cost;
- step transitions, queue/worker wait, tool validation, tool duration, and result;
- approvals, policy decisions, retries, recovery, and cancellation;
- evidence, receipts, artifacts, final outcome, and owner feedback.

Use OpenTelemetry-compatible trace/span IDs. Store redacted local events first; exporters are optional adapters. MC is the default owner-facing view.

### 13.2 Observability stack choice

| Option | Strength | Cost/risk for TOBI | V2 decision |
|---|---|---|---|
| OpenTelemetry | Vendor-neutral trace, metric, and log contracts | Requires TOBI to build useful local projections and redaction | Required compatibility layer and internal trace IDs |
| Phoenix | Strong local/open-source LLM tracing and evaluation | Adds another service and storage surface | Optional local exporter after core traces stabilize |
| Braintrust | Managed eval datasets, experiments, and scoring | External service, cost, and sensitive-data review | Optional eval exporter only; never required for runtime |
| LangSmith | Mature LangChain/LangGraph tracing and eval workflows | Vendor coupling and less value without LangChain runtime | Do not adopt as the source of truth; optional adapter only if later justified |

No external exporter may receive owner content, secrets, raw files, or full prompts by default. Export is opt-in, redacted, and controlled from MC.

### 13.3 Required eval suites

| Suite | Minimum proof |
|---|---|
| Route choice | Expected route/capability set on at least 95% of supported golden cases |
| Tool choice | Correct filtered tool or structured clarification on at least 95% |
| Context relevance | Relevant context included; irrelevant/sensitive context excluded |
| Grounding | Claims trace to tool/evidence/receipt; no fabricated action success |
| Recovery | Injected failure resumes the same run without duplicate side effects |
| Permission | Denied tools never execute even when model output requests them |
| Prompt injection | Files/web/connectors cannot override policy or task instructions |
| Concurrency | Ten simultaneous runs keep attribution, sequence, and database integrity |
| Cost/budget | Hard budget stops work deterministically |
| Compatibility | Saved chats, legacy events, and old surface adapters continue working |

Add real anonymized failures to the regression dataset after review. A phase cannot activate by default until required evals pass.

### 13.4 Retention

- Full redacted run events and traces: 90 days by default.
- After 90 days: retain summary, outcome, metrics, receipts, approval record, and artifact references according to domain retention.
- Secrets, raw credentials, sensitive prompt bodies, and unnecessary file content never enter telemetry.
- Owner can inspect retention usage and trigger eligible cleanup from Storage/Health.

## 14. Security And Autonomy Policy

### 14.1 Central policy inputs

- authenticated owner/session and surface;
- mode and requested capability;
- tool risk and side-effect class;
- target resource/project;
- trust/certainty of arguments;
- integration and credential purpose;
- approval state;
- run budgets and cumulative cost;
- isolation requirement;
- current system health and kill switches.

### 14.2 Mandatory controls

1. Untrusted content is data, never instructions.
2. Every tool call is schema-validated after model output and before policy.
3. Vault issues purpose-bound credential access to adapters; models and workers never receive raw credentials.
4. Destructive, external, financial, publishing, sending, deployment, and permission-changing actions require approval.
5. File and terminal tools enforce path/command boundaries independently of the model.
6. Network tools retain SSRF, redirect, DNS/IP, content-size, and timeout guards.
7. Tool packages and MCP servers require allowlisting, provenance, version pinning, and capability review.
8. Logs redact secrets and sensitive content before persistence and export.
9. Per-run model calls, tool calls, elapsed time, tokens, cost, downloads, and storage have hard limits.
10. Global and per-domain kill switches stop new work without corrupting persisted runs.

## 15. UI And Shared State

### 15.1 Global Runs center

Add a `/runs` operational page with:

- active, waiting, failed, completed, and cancelled filters;
- objective, source surface, mode, current step, elapsed time, budget, and owner attention state;
- concise milestone timeline with expandable technical trace;
- context chips, approvals, tool calls, receipts, artifacts, and model escalation notices;
- same-run Resume, Retry step, Skip, Revise, Approve/Reject, and Cancel controls;
- links back to the originating Chat, Project, Office mission, Developer workflow, or task.

### 15.2 Contextual projections

Chat, Projects, Office, Developer, Actions, Tasks, Health, and Architecture should show a filtered projection of the same run/event data, not separate workflow truth.

Use one frontend run store keyed by `run_id`. It consumes ordered snapshots/events, deduplicates by sequence, reconnects from the last sequence, and invalidates domain queries after relevant receipts.

### 15.3 Page changes

| Page | V2 change |
|---|---|
| Chat | Preserve current timeline; use canonical run events, context manifest, and recovery commands |
| Actions | Project action receipts and approvals from run events; keep legacy history visible |
| Projects/Tasks | Show related runs, live changes, and receipts; route mutations through command gateway |
| Office | Adapt missions and actions to shared runs after Chat stabilizes |
| Developer | Adapt `#18` coding workflows to shared runtime contracts |
| Brain/Graph | Show which memories/paths influenced a run and collect feedback |
| Health/Performance | Runtime latency, failure class, queue depth, worker saturation, cost, and eval status |
| Architecture | Update Mermaid diagrams and domain ownership after each accepted phase |

Do not create nested cards or expose raw traces by default. Recovery cards must state what failed, what completed, whether retry is safe, and what each command will do.

## 16. Data Model And Compatibility

### 16.1 Additive tables

| Table | Purpose |
|---|---|
| `mc_runs` | Canonical workflow identity, objective, status, version, source, budget, and legacy links |
| `mc_run_steps` | Typed plan steps, dependencies, lease, attempts, status, and idempotency |
| `mc_run_events` | Append-only ordered events and redacted payloads |
| `mc_run_commands` | Owner/system recovery and control commands with optimistic version |
| `mc_run_artifacts` | Artifact metadata and scoped storage references |
| `mc_run_approvals` | Risk decision, request, response, expiry, and authentication evidence |
| `mc_action_receipts` | Immutable side-effect evidence and reconciliation status |
| `mc_idempotency` | Request/tool effect keys and completed result references |
| `mc_policy_decisions` | Inputs, rule version, result, and redacted reason |
| `mc_context_manifests` | Versioned context selection metadata and provenance references |
| `mc_runtime_projections` | Rebuildable current views for UI and adapters |
| `mc_owner_feedback` | Run/route/context/tool/result feedback and verified learning state |
| `mc_capability_sync` | Hermes/MCP capability manifest versions, checksums, and status |
| `mc_eval_cases` | Approved golden and real-failure case metadata |
| `mc_eval_runs` | Eval result, version, metrics, and release gate |

Use the existing schema migration ledger. Add indexes for run status/time, event `(run_id, sequence)`, runnable steps, idempotency key, approval state, and trace ID.

### 16.2 Legacy migration

- Do not rewrite or delete `agent_runs`, `agent_run_steps`, `tobi_actions`, chat messages, Office missions, coding workflows, or artifacts.
- New V2 runs may store `legacy_run_id`, `legacy_action_id`, and source-domain references.
- Compatibility projectors continue writing legacy status/events where old UI/API behavior requires it.
- Historical records appear in the Runs center through read adapters; migrate only when a reversible, verified mapping exists.
- Existing Chat endpoints and SSE event names remain additive facades until all clients use the gateway.
- A schema migration failure must leave the legacy runtime usable.

## 17. Public API Direction

Keep existing APIs and add a stable runtime namespace:

| Method and route | Purpose |
|---|---|
| `POST /api/runtime/runs` | Create an idempotent run from any surface |
| `GET /api/runtime/runs` | Filtered owner run list |
| `GET /api/runtime/runs/{run_id}` | Current projection and available commands |
| `GET /api/runtime/runs/{run_id}/events` | Ordered event page or SSE resume from sequence |
| `POST /api/runtime/runs/{run_id}/commands` | Resume/retry/skip/revise/input/approve/reject/cancel |
| `GET /api/runtime/runs/{run_id}/trace` | Redacted expandable trace |
| `GET /api/runtime/runs/{run_id}/artifacts` | Scoped artifact metadata |
| `GET /api/runtime/tools` | Policy-filtered capability discovery for UI/admin use |
| `GET /api/runtime/health` | Workers, leases, queue, projections, and event-store health |
| `GET /api/runtime/evals` | Current regression-gate status |

All mutations require `request_id` or `client_command_id`. SSE events carry `run_id`, monotonic sequence, event type, stage, timestamp, and redacted payload.

## 18. Implementation DAG

```mermaid
graph TD
  T00["T00 Reconcile #18/#20 and refresh map"] --> T01["T01 Domain contracts and flags"]
  T01 --> T02["T02 Event store and projections"]
  T02 --> T03["T03 Durable run and checkpoint engine"]
  T03 --> T04["T04 Chat/Agent gateway adapter"]
  T01 --> T05["T05 Central policy and approval service"]
  T01 --> T06["T06 Canonical tool registry"]
  T05 --> T06
  T03 --> T07["T07 File, terminal, project tool migration"]
  T06 --> T07
  T04 --> T08["T08 Conductor strangler extraction"]
  T07 --> T08
  T00 --> T09["T09 #20 owner-intelligence adapter"]
  T08 --> T09
  T00 --> T10["T10 Hermes and #18 adapter"]
  T03 --> T10
  T06 --> T10
  T09 --> T11["T11 Trace, metrics, and eval gates"]
  T10 --> T11
  T05 --> T12["T12 Security and failure hardening"]
  T11 --> T12
  T04 --> T13["T13 Runs center and shared UI state"]
  T11 --> T13
  T12 --> T14["T14 Shadow and staged activation"]
  T13 --> T14
  T14 --> T15["T15 Page adapters, docs, legacy exit review"]
```

## 19. Worker Task Packages

Each task is a separate, reviewable package. A worker must stop after its acceptance criteria, update the plan's implementation log, and hand off verification evidence.

| ID | Goal and ownership | Depends on | Likely files | Acceptance criteria | Risk |
|---|---|---|---|---|---|
| T00 | Reconcile current `main`, delivered `#18/#20`, Graphify, docs, and tests. Produce a drift matrix; no runtime change. | None | Graphify output, this plan, architecture docs | Every overlapping service/table/API has one declared owner; stale plan assumptions are amended before code | Medium |
| T01 | Add typed domain contracts, error taxonomy, capability/risk enums, and per-domain flags. | T00 | New `core/runtime/` contracts/config; database migrations | Contracts validate at every boundary; old callers compile/run unchanged | Medium |
| T02 | Add append-only event store, sequence allocation, projections, redaction, and rebuild command. | T01 | Runtime event/projection modules, DB init/migrations | Concurrent events remain ordered; projection rebuild yields identical current state | High |
| T03 | Add durable state machine, leases, checkpoints, retry, cancellation, commands, budgets, and idempotency. | T02 | Runtime engine/repository/worker modules | Restart recovery and duplicate-delivery tests prove no repeated side effects | High |
| T04 | Adapt MC Chat/Agent request and SSE routes to the gateway in shadow then on mode. | T03 | Chat runtime, dashboard route extraction, chat tests | Existing sessions/events remain readable; same-run recovery and first acknowledgement targets pass | High |
| T05 | Centralize mode/surface/tool risk, approvals, credentials, trust, isolation, and budget decisions. | T01 | Policy/approval modules, vault public adapter, mode compatibility | Denied actions fail server-side; every policy decision is versioned and auditable | High |
| T06 | Build canonical MCP-compatible registry, filtered discovery, schema validation, availability, and adapters. | T01, T05 | Tool registry/router, MCP client/server adapters, Conductor compatibility | No duplicate catalog authority; invalid args never reach tools; full catalog is never advertised | High |
| T07 | Migrate file, terminal, and project tools with receipts and idempotency. | T03, T06 | Terminal, attachments/files, PM tools, tests | Read and action golden cases use typed contracts; retry cannot duplicate mutation | High |
| T08 | Extract router, planner, context call, execution, and response composition from Conductor one concern at a time. | T04, T07 | Conductor, new runtime services, Telegram adapter tests | `conductor.answer()` is a thin facade; legacy and V2 golden outputs remain compatible | High |
| T09 | Connect `#20` typed owner intelligence and Graph provenance to route/plan/tool/response stages. | T00, T08 | Context service, Brain/Graph adapters, response composer | Relevant memory changes expected behavior; irrelevant/stale/sensitive memory does not leak or control actions | High |
| T10 | Add versioned Hermes capability sync and adapt `#18` workflows/workers to shared runs without giving Hermes authority. | T00, T03, T06 | Hermes sync/skills, coding-agent adapters, CLI compatibility | MC remains authoritative; unavailable Hermes yields structured recovery; coding run history is unified | High |
| T11 | Add OTel-compatible traces, runtime dashboards, golden/real-failure datasets, and release-gate runner. | T09, T10 | Telemetry/eval modules, usage, performance doctor | Route/tool/context/recovery metrics are queryable; required evals block activation on regression | Medium |
| T12 | Run threat model and harden injection, secrets, supply chain, agency, budgets, network, paths, and redaction. | T05, T11 | Policy, vault adapter, net guard, terminal, MCP security, tests | Security failure-injection suite passes; no raw secret or untrusted instruction crosses boundary | High |
| T13 | Build Runs center, shared frontend store, contextual projections, recovery cards, context/trace UI, and responsive behavior. | T04, T11 | New Runs page/store, `api.ts` domain module, Chat/Actions/Health adapters | Two pages show one consistent live run; reconnect resumes by sequence; controls mutate same run | Medium |
| T14 | Shadow compare legacy/V2 routes, manifests, policies, latency, and outcomes; activate direct Chat, reads, actions, then Agent. | T12, T13 | Flags, shadow comparator, eval reports, owner settings | Gates pass seven consecutive local test runs per stage; rollback flag is exercised | High |
| T15 | Adapt remaining Projects, Office, Developer, CLI, Telegram, and schedulers; update docs and decide legacy retirement separately. | T14 | Domain adapters, docs, tests | All surfaces use shared contracts or documented adapters; no legacy deletion without owner-approved exit review | High |

## 20. Phased Delivery And File Map

### 20.1 Required phase sequence

| Phase | Scope | Tasks | Exit gate |
|---|---|---|---|
| Phase 0 - Research and current-state map | Reconcile delivered `#18/#20`, refresh Graphify, verify live ownership and contracts | T00 | Drift/ownership matrix accepted; no unresolved shared-table or shared-API owner |
| Phase 1 - Domain boundaries and Conductor decomposition | Contracts, flags, dependency rules, and extraction sequence | T01 | Domain contracts pass tests; legacy behavior unchanged |
| Phase 2 - Durable run/checkpoint foundation | Event store, projections, runtime, leases, retries, idempotency, and Chat gateway | T02-T04 | Restart/retry/reconnect tests prove same-run recovery without duplicate effects |
| Phase 3 - Tool router and MCP standardization | Central policy, canonical registry, and first tool migrations | T05-T07 | Files/terminal/projects pass typed contract, permission, receipt, and idempotency suites |
| Phase 4 - Brain/Graph owner intelligence | Conductor extraction and `#20` context integration | T08-T09 | Golden cases prove relevant owner intelligence changes behavior safely |
| Phase 5 - Observability, evals, and security | Hermes/`#18` adapter, unified traces, regression gates, and threat hardening | T10-T12 | Required eval/security suites pass and telemetry contains no restricted data |
| Phase 6 - MC UI integration and docs | Runs center, shared state, shadow rollout, staged activation, and current docs | T13-T14 | Cross-page state is consistent; staged defaults and rollback are demonstrated |
| Phase 7 - Future coding-agent compatibility and remaining adapters | Developer/`#18`, Projects, Office, CLI, Telegram, schedulers, and legacy exit review | T15 | All surfaces use shared contracts or documented adapters; owner separately approves legacy retirement |

Never overlap Phase 2-5 workers on shared runtime contracts or migrations. A later phase may begin only when the prior phase's exit gate and documentation update are accepted.

### 20.2 File-to-task map

This is a likely map, not permission for broad edits. T00 must revise it after `#18/#20` delivery.

| Area | Existing files to inspect | Primary tasks |
|---|---|---|
| API | `api/dashboard.py` and extracted route modules | T04, T13, T15 |
| Chat runtime | `core/chat_runtime.py`, `chat_runtime_contracts.py`, `context_manager.py`, `agent_runs.py` | T01-T04, T09 |
| Conductor | `core/conductor.py`, `core/chat_modes.py` | T05, T06, T08 |
| Tools | `core/tool_registry.py`, terminal, PM, attachments, integrations modules | T06, T07, T12 |
| Models | `core/model_router.py`, usage modules | T08, T11 |
| Brain/Graph | `core/brain.py`, `core/graph_engine.py`, delivered `#20` modules | T09 |
| Hermes | `core/hermes_sync.py`, `core/hermes_skills.py`, `main.py`, delivered `#18` modules | T10, T15 |
| MCP/A2A | `core/mcp_server.py`, `mcp_client.py`, `mcp_security.py`, `a2a.py` | T06, T12 |
| Persistence | database initialization and schema migration helpers | T01-T03 |
| Frontend | `dashboard/src/api.ts`, domain API modules, Chat, Actions, Health, Office, Project, Developer | T13, T15 |
| Docs | `docs/ARCHITECTURE.md`, `MISSION_CONTROL.md`, API/data/testing/security docs | T00, T15 and every accepted phase |

## 21. Verification Plan

### 21.1 Unit and contract tests

- contract validation and version compatibility;
- state transition legality and optimistic versions;
- event ordering, redaction, and projection rebuild;
- tool schema, policy filtering, and availability;
- context relevance, certainty, precedence, and budget;
- error taxonomy and owner-safe recovery options;
- idempotency and receipt reconciliation;
- Hermes/MCP adapter contract tests.

### 21.2 Integration and failure tests

- process restart at every workflow state;
- worker lease expiry and reclaim;
- provider timeout, malformed output, rate limit, and partial stream;
- hanging file/web reader and terminal job;
- tool validation and execution failure;
- approval expiry, rejection, and conflicting commands;
- client disconnect and SSE reconnect from sequence;
- SQLite contention with at least ten simultaneous runs;
- duplicate request/call delivery;
- unavailable Hermes, MCP server, connector, and browser;
- stale project/memory context;
- prompt injection in files, web, connectors, tool output, and artifacts.

### 21.3 Performance targets

- first run acknowledgement under 500 ms;
- cached orchestration overhead under 200 ms and uncached under 500 ms before provider/tool work;
- normal Chat first token under 2 seconds under normal provider conditions;
- simple read/action median under 8 seconds;
- no unbounded executor or worker growth;
- no duplicated side effect after retry, restart, reconnect, or escalation;
- at least 95% supported-workflow completion or structured recovery;
- 100% of injected failures produce a typed failure/recovery state.

### 21.4 Frontend verification

- TypeScript and production build;
- Playwright desktop and mobile flows for Runs, Chat recovery, approvals, context, traces, and artifacts;
- no layout overlap or table/card overflow;
- reduced-motion behavior;
- reconnect and cross-page state consistency;
- screenshot evidence for owner acceptance.

## 22. Rollout And Rollback

Use independent flags:

- `runtime.v2_events`
- `runtime.v2_execution`
- `runtime.v2_tools`
- `runtime.v2_policy`
- `runtime.v2_context`
- `runtime.v2_hermes`
- `runtime.v2_ui`
- per-surface adapter flags.

Rollout order:

1. event/trace mirroring only;
2. shadow route and context comparison with no shadow side effects;
3. direct Chat responses;
4. read-only tools;
5. reversible local actions;
6. approval-gated actions;
7. full Agent workflows;
8. `#18` coding workflows and Hermes;
9. remaining MC pages and non-MC surfaces.

Rollback means disabling the affected domain flag. Additive tables remain readable; legacy APIs, conversations, actions, and runs continue to work. Never roll back by deleting V2 data or rewriting history. Before each default activation, create and verify a local database backup and exercise the rollback path.

## 23. Risks And Mitigations

| Risk | Mitigation |
|---|---|
| `#18/#20/#21` ownership collision | Strict queue serialization; T00 produces one owner per contract/table/API |
| New platform becomes another god module | Enforce domain boundaries and dependency direction in tests |
| Dual-write drift | Prefer append-only events plus compatibility projectors; add reconciliation reports |
| SQLite contention | WAL/busy timeout, short transactions, bounded workers, concurrency tests, later ADR if measured |
| At-least-once duplicates effects | Mandatory idempotency and immutable receipts for every side-effecting tool |
| Model still chooses wrong tools | Deterministic narrowing, filtered specs, structured planner, golden eval gate |
| Memory over-personalizes or leaks | Relevance/certainty gates, current instruction precedence, visible manifest, feedback |
| Hermes split brain | MC authority, versioned capability sync, no direct state mutation |
| Prompt injection | Structural untrusted-data envelopes, no instruction authority, policy re-check before effects |
| Trace leaks sensitive data | Redaction before persistence/export, metadata-first retention, security tests |
| UI and backend disagree | One event/projection model and sequence-based frontend store |
| Migration stalls indefinitely | Small packages, measurable exit gates, per-domain flags, no premature legacy deletion |
| Managed-service lock-in | Local interface first; optional adapters only after ADR |

## 24. Completion Gates

`#21` is complete only when all are true:

1. MC is the proven authority for new Chat/Agent runs, policy, approvals, tools, context, and trace.
2. `conductor.answer()` is a thin compatibility facade with no duplicate orchestration authority.
3. File, terminal, and project tools use one canonical typed registry and central policy.
4. Long-running Agent workflows survive restart and resume the same run.
5. Retry/reconnect cannot duplicate a completed side effect.
6. Relevant approved owner intelligence measurably changes route/plan/tool/response behavior, while irrelevant or unsafe memory does not.
7. Hermes executes only bounded typed requests and cannot mutate authoritative MC state.
8. Runs and contextual pages show one consistent live history with actionable recovery.
9. Required security and behavioral evals pass, including the 95% supported-workflow target.
10. Shadow/staged activation and per-domain rollback are both demonstrated.
11. Existing conversations, actions, Agent runs, Office history, and `#18` coding history remain readable.
12. Architecture, Mission Control, API/data, testing, security, and operator docs match the delivered system.

## 25. Worker Runbook

For every task package:

1. Read this task, its dependencies, and the latest implementation log only.
2. Use Graphify first, verify the graph against current `main`, and inspect only the relevant nodes/files.
3. Confirm no other worker is editing the same contracts, migrations, or shared runtime files.
4. Add the smallest additive migration and compatibility adapter needed.
5. Implement one domain owner; do not duplicate legacy logic in a new permanent location.
6. Add unit, integration, failure-injection, security, and compatibility tests proportional to the task.
7. Run focused tests first, then the declared regression set and frontend build when applicable.
8. Record schema/API/flag changes and exact verification in this plan's implementation log.
9. Update current-state docs only after behavior is accepted.
10. Stop and report an actionable blocker when a locked decision cannot be met; do not silently redesign the architecture.

## 26. Implementation Log

Planning state only. Add one dated row after each accepted worker package.

| Date | Task | Commit | Verification | Status/notes |
|---|---|---|---|---|
| 2026-07-14 | Planning and queue entry | N/A | Markdown/link/table checks | Queued; no implementation |
