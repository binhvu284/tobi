# TOBI Agent Guide

Read [`docs/README.md`](docs/README.md) first. For implementation work, also read [`docs/02_CURRENT_STATE.md`](docs/02_CURRENT_STATE.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and the relevant feature plan or domain section.

## Reporting To The Owner

One owner reads every report, and he is steering the whole system from them. A report he cannot finish is a report that did not happen. These rules are not style preferences; a report that breaks them costs him the thread of what is actually going on.

- **Lead with the answer.** First line is the result. Everything after it earns its place by changing a decision.
- **Stay short.** A routine reply is under ten lines. A large delivery is under forty, with headings so it can be skimmed and re-found later. If it genuinely needs more, the detail goes in a file and the reply links to it.
- **Explain every technical term the first time it appears**, in the same sentence, by what it *does* — not by what it is called. Write "a lease (so two workers can never grab the same job)", not "a lease". Never leave a term for him to look up.
- **Three unfamiliar terms in one paragraph means the paragraph is wrong.** Rewrite it in ordinary words before sending.
- **Prefer a table to a list, and a list to a paragraph.** Never nest more than two levels deep.
- **End findings with what they mean for him** — what he can now do, or what is now blocked.
- **Step by step means step by step.** When he asks how to set up, test, run, or check something, write it for someone doing it for the first time: the exact command, the exact button, the exact place to look, and what a correct result looks like. Never write "configure X" or "see the docs" and leave him to research it.
- **Say the uncomfortable part plainly and once.** "This failed." "I was wrong." "This is not done." One sentence, no cushioning, then carry on.
- **Never pad.** Length is not evidence of effort, and it is the main way he loses the picture.

## The Standard: It Must Work For A Non-Technical Person

TOBI is judged as a product, not as a developer tool. The owner set this standard on 2026-08-01 after a Chat failure whose only available fix was "configure a fallback model on the Models page":

> *"If I use it as a normal person, I would expect it should do whatever I said. If it requires my config, it shall teach me how to do it. Setting up a fallback in MC is only suitable if I was a developer who knows the system well."*

- **A feature that needs hidden configuration to work is broken, not configurable.** Ship a working default. Configuration may refine behavior; it must never be the difference between working and failing.
- **Never propose a fix whose steps are "open this settings page and set this field"** unless a non-technical person would already know that field exists and what to put in it. If they would not, fix the code instead.
- **A silent empty setting is a defect.** If a recovery path, fallback, or safety net depends on a value that ships empty, it does not exist. Either give it a working default or make its absence visible at the moment it matters.
- **Error messages must be true and actionable.** "Try a stronger model from the picker" implied TOBI had already tried and failed; it never tried, because the list it reads was empty. An error that misdescribes the cause sends the owner to fix the wrong thing.
- **When the model or a service returns something imperfect but usable, use it.** Dropping a valid result because it arrived in an unexpected shape is TOBI's bug, not the provider's.
- **This applies to every fix, in every subsystem, from now on.** When a change would leave the owner needing to know how TOBI works internally, it is not finished.

## Current Work

[`.claude/CURRENT_WORK.md`](.claude/CURRENT_WORK.md) holds the one package being built right now: its purpose, its non-goals, and its gate. Read it before writing code, and re-read the purpose line whenever a fix has run long — if what you are fixing does not serve that line, stop and log it as a separate item instead of absorbing it.

`scripts/gate.py` enforces the gate declared in that file on every stop. A failing gate refuses the stop. Never weaken, skip, or delete a check to get past it; that is the failure mode the gate exists to catch.

## Product Direction

TOBI's mission is a personal Jarvis: persistent owner understanding, safe real-world action, and reliable presence. The MMO/business loop is one implemented capability, not the product identity.

## Source of Truth

1. Code, schemas, and tests define current behavior.
2. Current documents in `docs/` explain that behavior.
3. `docs/feature-idea-queue/QUEUE.md` records delivery status.
4. Feature plans preserve original intent and may contain pre-implementation assumptions.
5. `docs/archive/` is historical only.

## Repository Map

- `main.py`: process entry point, scheduler, Telegram lifecycle, API launch.
- `core/`: Chat runtime/modes, Conductor, Agent runs, Awakening, Brain/Graph, model routing, terminal, projects/resources, integrations, MCP/A2A, storage/usage, Explore, and business engines.
- `api/dashboard.py`: Mission Control API plus static React host. It is a large monolith; inspect the relevant route group before editing.
- `api/server.py`: smaller API-key-protected legacy/external API.
- `dashboard/src/`: Mission Control application, global workspace tabs, pages, components, contexts, themes, and API client.
- `SOUL.md` and `hermes_skills/`: runtime inputs. Treat changes as behavior changes, not docs cleanup.

## Graphify

Generated Graphify data lives in `graphify-out/`. Use it to locate related symbols and flows, then verify the cited code. The local index can lag recent commits, so do not rely on stored node counts or treat the graph as current system truth. Refresh it after code changes when the Graphify tool is available.

## Working Rules

- Keep feature plans intact unless the task explicitly asks to revise a plan.
- Update current docs and the queue row when delivered behavior changes.
- Never expose `.env`, vault, OAuth, token, or key values.
- Do not claim an integration is connected from code presence alone; use current status evidence.
- For Awakening External Read, configured credentials are not proof: connector readiness plus a fresh successful integration test is required, and Google also requires completed OAuth.
- Treat Chat route allowlists as focus hints for safe reads, not permission boundaries. Mode denial, action risk, approval, terminal policy, and server-side validation remain the security boundaries.
- Preserve user/runtime data under `.tobi/`, `.hermes/`, the configured database directory, and project resources.
- Treat port-8080 Mission Control as a trusted single-owner surface unless authentication is added.
- Do not run `main.py start` casually: it starts Telegram and scheduled work. Use the narrower commands in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for local verification.
- UI buttons that trigger async work (network calls, renders, exports) MUST show an inline loading state — a spinner and/or a disabled state — for the duration, so the UI never appears frozen and the action can't be double-fired. Re-enable on both success and failure. Use the shared primitives in [`dashboard/src/components/async-ui.tsx`](dashboard/src/components/async-ui.tsx) rather than hand-rolling pending state; they own the re-enable-on-failure guarantee. Pick by blast radius: `ActionButton` when only the control is affected, `BusyOverlay` when one section's data is being replaced, `ActivityBar` for a page-wide refetch, `SectionSkeleton` only where no content exists yet. Never swap loaded content for a skeleton on refresh — it costs the reader their place; dim it instead. `tests/test_ui_loading_states.py` fails if any control in the app ships without one.
- **Backend changes must not drop the loading affordance.** Every regression of this rule so far arrived alongside a backend fix, when a control was rewritten for a new API shape and its pending state was not carried over. After changing an endpoint or a handler signature, re-run `tests/test_ui_loading_states.py`.
- Token efficiency: prefer token-saving methods — graphify-first analysis, targeted file-range reads, and search tools over full-file dumps (`core/performance_doctor.py` is the reference pattern: it reads the graph as a map and opens source only to count lines, never feeding raw code to an LLM). When you use one, name the method and give a rough estimate of the tokens or % saved versus the naive approach.
