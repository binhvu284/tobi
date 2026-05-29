# Tobi — Documentation Index

> **Read this first if you are a new agent or contributor working on Tobi.**

## What is Tobi?

Tobi is being built to be a **personal Jarvis** — an AI that *understands its owner deeply*, can *operate his PC and do whatever a PC can do*, and is *available 24/7*, interacting the way Jarvis interacts with Tony Stark.

That is the **mission**. It is bigger than what the code does today.

## ⚠️ Don't mistake the current code for the goal

If you open this repository and only read the code, you will see an **autonomous MMO (make-money-online) business-portfolio agent**: it researches niches, proposes business plans, waits for the owner's approval over Telegram, executes project tasks on a schedule, and runs a monthly "CEO review."

**That business engine is one *capability*, not the identity.** It is a proof-of-concept that Tobi can run a self-directed loop end-to-end. The north star is the Jarvis vision in [`01_VISION.md`](01_VISION.md). Read it before assuming the MMO portfolio is "the point."

## The three docs

| Doc | Purpose |
|-----|---------|
| [`01_VISION.md`](01_VISION.md) | The Jarvis ambition — the north star and its 3 pillars. |
| [`02_CURRENT_STATE.md`](02_CURRENT_STATE.md) | Honest, real-vs-stub inventory of what actually exists today. |
| [`03_ROADMAP.md`](03_ROADMAP.md) | % progress toward the Jarvis end-state, organized by the 3 pillars, with evidence and next steps. |

## Source-of-truth files in the repo

- `SOUL.md` — Tobi's persona, operating modes, and decision rules (hand-written; synced into `~/.hermes/`).
- `main.py` — the orchestrator and entry point; defines all run modes and the scheduler.
- `core/` — the engines: model routing, task classification, research, execution, CEO loop, database, Telegram bot, integrations.
- `api/` + `dashboard/` — REST API (FastAPI) and the React dashboard.
- `HERMES_*.md` — setup/operation guides for the Hermes framework (the always-on runtime layer).

## Key decisions guiding this documentation

- **Identity = Jarvis-first.** All roadmap percentages are measured against the *Jarvis* end-state, not the MMO-agent end-state. (Measured against the latter, the code is far more mature — see the roadmap's "Business engine" sub-section.)
- **Runtime = personal PC, always-on.** The long-term target is Tobi running locally on the owner's machine for true desktop/file/app/shell control. Current `HERMES_*.md` guides assume a VPS — treat that as a *migration item*, not the goal.

## Open item to confirm

`SOUL.md` names the owner **"Thomas (binhvu284)"**, while the active git/user identity is **"Vũ Lê Bình / vubinh2843@gmail.com"**. Confirm the canonical owner name/persona before relying on either.

---

*These docs describe intent and current state. Code is the source of truth for behavior; when they disagree, trust the code and update the docs.*
