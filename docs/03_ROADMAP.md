# TOBI Roadmap

This roadmap uses evidence and dependency order rather than a single Jarvis percentage. Awakening Tier 1 is now evidence-based; later Evolution tiers are not yet an authoritative whole-product score.

## Current Baseline

The platform already has persistent memory, backend-enforced Chat/Agent modes, grounded tools, persisted Agent runs and recovery, Deep Research, real project/task operations, a full-machine terminal, configurable model routing, Premium readers, Awakening evidence, integrations, MCP/A2A, Performance Doctor, a broad Mission Control UI, scheduled jobs, and Telegram access.

The next phase should turn those systems into one coherent and defensible assistant rather than adding disconnected surfaces.

## Recommended Sequence

```mermaid
flowchart LR
  A[Finish Theme v2 owner review] --> B[Office V3 owner visual acceptance]
  C[Accept #17 review follow-up] --> D[Stabilize Chat Runtime v2]
  D --> E[Controlled coding agent - queue 18]
  D --> F[Security and API hardening]
  C --> G[Design evidence contracts for later tiers]
```

### 1. Close active UI work

Finish the owner review for queue #13 before broad changes to Chat, Ability, Office, or shared theme components. Record final status in the queue.

### 2. Stabilize Chat Runtime v2

Queue #16 is delivered: Chat/Agent is a backend capability contract, Terminal is part of Agent, Deep Research is a capability, and project context is automatic. The next work is operational: complete staged runtime-v2 rollout, measure routing/context/tool reliability, retain checkpoint/recovery compatibility, and remove legacy orchestration only after acceptance targets hold.

Do not build a second execution system for queue #18; consume these runtime, tool, approval, trace, and recovery contracts.

### 3. Accept and protect Awakening (#17)

Tier 1 is delivered with nine evidence-backed abilities. Preserve the hardened gates: usable connector state, successful workflow receipts, reviewed sensitive memory, serialized failure-safe Brain sweeps, and shared persona evidence. Accept the follow-up before queue #18 starts, then reuse the same evidence-contract pattern for later tiers.

### 4. Accept Office V3 (#15)

Office V3 v1 is delivered as a flagged replacement that reuses mission APIs, SSE, Phaser, and Conductor confirmation. Complete owner visual acceptance across desktop/mobile/theme modes before removing the legacy fallback. Future Office work should link Project resources rather than adding an Office upload system.

## Platform Hardening Track

These tasks are not represented well by a visual feature queue but are required for reliable growth:

1. Add authentication or a trusted-network boundary to Mission Control; remove reliance on a public URL as the only gate.
2. Replace the default API key fallback in `api/server.py` with a required secure configuration.
3. Split `api/dashboard.py` into domain routers without changing endpoint behavior; continue the frontend API-domain extraction already started.
4. Document and migrate the legacy `projects` model toward Project v2 ownership.
5. Add browser and integration regression coverage for Chat -> runtime -> Conductor -> recovery/confirmation, project resources, vault/integrations, and Agent terminal behavior.
6. Add schema migration/version tracking instead of relying only on scattered `CREATE TABLE` and additive column checks.
7. Define one skills source of truth and extend the Awakening evidence service pattern to later tiers.

## Jarvis Pillars: Next Milestones

| Pillar | Strong foundation | Next milestone |
|---|---|---|
| Understand the owner | Brain, semantic retrieval, lessons, conversations, project resources | Preference/habit learning with review, confidence, provenance, and proactive recall |
| Perform real work | Chat/Agent policy, Conductor tools, persisted runs, Project v2, integrations, MCP, terminal | Controlled coding agent, reusable workflows, then browser automation and desktop control |
| Remain available | Mission Control, Telegram, CLI, scheduler, health/usage | Hardened personal-PC service, event-driven observation, voice, and context-aware alerts |

## Queue Coordination

| Pair | Parallel safety |
|---|---|
| Chat Runtime v2 + #18 coding agent | Sequential unless #18 only consumes stable runtime contracts; both touch tools, approvals, runs, terminal, and traces |
| #15 Office V3 + Chat runtime work | Possible with strict Office/frontend ownership and no shared mission/runtime API rewrite |
| Theme v2 owner review + shared Chat/Office UI | High collision risk in tokens, shell, and shared components; assign file ownership |
| Any feature + `api/dashboard.py` decomposition | Unsafe unless domain files and endpoint compatibility are locked first |

## Completion Rules

A roadmap item is complete only when:

- behavior is implemented, not represented only by a label or status badge;
- API and persistent-state contracts are documented;
- security and approval behavior is explicit;
- configuration-dependent states show `setup needed` rather than fake success;
- focused automated tests and a Mission Control smoke path pass;
- queue status and current docs are updated in the same delivery.
