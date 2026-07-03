# CLAUDE.md — Read this first

**Before working on Tobi, read [`docs/README.md`](docs/README.md), then [`docs/01_VISION.md`](docs/01_VISION.md).**

## The one thing not to get wrong

The mission is to make Tobi a **personal Jarvis**: an AI that understands its owner deeply, can control his PC and do anything a PC can do, and is available 24/7.

The code in this repo currently looks like an **autonomous MMO business-portfolio agent** (research → approve → execute → CEO review). **That is one capability, not the mission.** Don't assume the business loop is "the point" — it's a proof-of-concept of self-directed execution that serves the larger Jarvis goal.

## Map

- `docs/` — vision, honest current state, and %-progress roadmap (the long-term plan).
- `SOUL.md` — Tobi's persona, operating modes, and decision rules.
- `main.py` — orchestrator + scheduler; run modes (`start/bot/api/research/execute/ceo/status/test/terminal`).
- `core/` — engines (model router, classifier, research, executor, CEO loop, database, Telegram bot, integrations).
- `HERMES_*.md` — Hermes framework (always-on runtime) setup/operation guides.

## Codebase navigation (save tokens — query before you read)

A graphify knowledge graph of this repo lives at `graphify-out/graph.json` (2331 nodes / 4718 edges,
indexing every symbol + doc concept with file:line pointers). For "how does X work / where is Y /
what calls Z" questions, run `graphify query "<question>"` **before** Glob/Grep/Read — it returns the
relevant subgraph with `src=file loc=L###` pointers, then read only those cited lines.

- `graphify query "<q>"` — broad context (BFS) · add `--dfs` to trace one path · `--budget N` to cap size
- `graphify path "A" "B"` — shortest link between two concepts · `graphify explain "node"` — node summary
- After changing code, refresh the index: `graphify . --update` (re-extracts only changed files).
- Reading the graph routes you to the right file; **editing** a file still needs a full Read first.

## Guardrails

- Never commit or paste `.env` values — reference key *names* only.
- Code is the source of truth for behavior; if the docs disagree with the code, trust the code and update the docs.
