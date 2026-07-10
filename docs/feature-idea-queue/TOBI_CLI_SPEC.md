# TOBI CLI — Feature Spec & Requirements

> **Status:** ✅ **Built (v1, P0–P3)** this session — all four phases shipped against the 30 locked
> decisions (D1–D30). Verified: `tests/test_terminal_engine.py` 67/67 + Storage #10 regression 32/32,
> `tsc` + `vite build` clean, all 7 `/api/terminal/*` routes register. See the QUEUE row for the
> full build note. **Delivered files:** `core/terminal_engine.py` (new), Conductor terminal tools +
> two-axis gate in `core/conductor.py`, `run_bash` repointed in `core/telegram_bot.py` + upgraded REPL,
> 7 endpoints + SSE `terminal` events in `api/dashboard.py`, `dashboard/src/components/chat/TerminalMode.tsx`
> (new) wired into `pages/Chat.tsx`, `tobi hermes` mode in `main.py`, Evolution flags in `_detect_abilities`.
> **Open owner inputs (defaults shipped, tune in §13):** exact denylist patterns · terminal-loop spend cap ·
> install-timeout values · admin-elevation confirm policy. `terminal_sessions` reserved; remote owner-token deferred.
>
> **Owner:** Thomas (sole principal). **Head agent:** TOBI. **Date:** 2026-06-27 (spec) · built 2026-07-10.
>
> **Persona for the build:** SaaS system-development expert.
>
> **Related specs/code:** routes through [CONDUCTOR_SPEC.md](CONDUCTOR_SPEC.md) (#7) tool-loop +
> `tobi_actions` audit; secrets via [GENESIS_SPEC.md](GENESIS_SPEC.md) (#4) vault; acquired tools can
> become tools via [MCP_SPEC.md](MCP_SPEC.md) (#5); LLM calls log to [STORAGE_USAGE_SPEC.md](STORAGE_USAGE_SPEC.md)
> (#10) `llm_usage`; terminal UI is a mode of [PREMIUM_CHAT_SPEC.md](PREMIUM_CHAT_SPEC.md) (#8).
> **Upgrades existing code:** `core/telegram_bot.py` `_execute_tool`/`run_bash`/`_run_coding_agent`,
> `main.py terminal` REPL, `core/hermes_sync.py`. **Advances the Evolution roadmap** (`api/dashboard.py`
> `_TIER_DEFINITIONS`): delivers Awakening-tier `tiered_permissions` + `full_filesystem`, seeds
> Agent-tier `shell_full_access`.

---

## 1. Vision

Give TOBI a **real terminal** — and give Thomas a way to **talk to TOBI through one**. Today the
shell is a toy: `core/telegram_bot.py` `_execute_tool` exposes `read_file`/`write_file`/`run_bash`/
`list_files` locked to `PROJECT_DIR` behind a 5-item denylist (`_BLOCKED_CMDS`), 30s timeout,
`shell=True`. TOBI CLI turns that into a proper, safe, full-machine execution engine that TOBI uses
to **do real things**: download packages, install tools, configure and connect them, run commands —
on request via **chat or Telegram**, and as multi-step Conductor chains.

Two faces, built phased `[D1]`:
1. **TOBI-as-terminal-user** — TOBI executes terminal tasks itself (install / configure / connect /
   run), surfaced as Conductor tools.
2. **The `tobi` command** — a thin CLI Thomas types in any terminal to reach TOBI/MC, plus the
   upgraded interactive REPL.

This is the **first base for the Agent tier** in TOBI's evolution. It will be hardened further once
the Awakening tier is otherwise complete; in fact it *delivers* the two Awakening control abilities
it depends on `[D30]`.

---

## 2. Architecture & TOBI integration

- **One engine, extracted `[D5]`:** evolve the existing `_execute_tool`/`run_bash` into
  **`core/terminal_engine.py`** — risk tiers, modes, streaming, configurable timeout, background
  jobs, audit. The four existing tools (`read_file`/`write_file`/`run_bash`/`list_files`) keep
  working; the coding agent (`_run_coding_agent`) repoints onto it.
- **Routed through the Conductor (#7) `[D3]`:** terminal capability is exposed as **new Conductor
  tools** (`run_command`, `install_package`, `configure_tool`, `connect_tool`, `list_jobs`,
  `kill_job`, …) so it inherits risk tiers, Confirm/Cancel cards, the `tobi_actions` audit, the
  butler EN/VN voice, and **both surfaces (MC + Telegram)** for free.
- **Hermes is the 24/7 runtime, kept `[D4]`:** the interactive *TOBI* terminal is the upgraded
  `main.py terminal` REPL; `core/hermes_sync.py` keeps pushing routing config **one-way** to
  `~/.hermes`. We "take advantage of the Hermes CLI" rather than reimplement a runtime.
- **The `tobi` command = thin Hermes wrapper + MC logging `[D2][D20]`:** `tobi <x>` passes through
  to the real `hermes` binary and logs the invocation to MC (no new TOBI-specific verbs in v1 — the
  rich interaction lives in the REPL + Chat terminal-mode + Telegram). Keeps surface area small and
  leans on Hermes's existing CLI.
- **Model + budget `[D28]`:** the agentic loop reuses `core/model_router.py` (#8) — **Haiku** for
  simple command planning + risk classification, **Opus** for complex multi-step tasks. Every call
  logs to `llm_usage` (#10) with a `terminal` source tag, under a **small monthly cap + alert**.
- **Cross-platform from day one `[D26]`:** detect OS → branch shell (PowerShell/cmd on Windows, bash
  on POSIX), paths, and package managers. Thomas is on **local Windows** now; the Hermes runtime
  historically ran on a Linux VPS, so both must work.

---

## 3. The execution engine (`core/terminal_engine.py`)

- **Network on, flagged `[D9]`:** network access is **enabled** (pip/npm/winget installs need it),
  but any network-touching command is auto-rated **medium-risk** (act+report) and logged. Network is
  the main exfil vector, so it is never silent.
- **Output: stream to MC, summarize to Telegram `[D10]`:** MC streams live stdout/stderr over **SSE**
  (xterm-style); Telegram gets a concise `✓ done (exit 0)` + a short output tail (it can't render a
  live console).
- **Background jobs `[D11]`:** long-running commands (dev servers, big installs, watchers) detach
  into a **`terminal_jobs`** registry — start → get an id → stream / inspect / kill later
  (`list_jobs`/`kill_job`, MC job list). Short commands still run inline. A mini process manager.
- **Timeout per-risk + configurable `[D12]`:** ~30s for quick commands, longer (~300s) for installs,
  **unbounded for background jobs**; overridable per command.

---

## 4. Permission model — two axes (Codex-style) `[D6]`

The crux of the feature. Two **independent** axes, mapped onto `SOUL.md`'s low/med/high tiers,
replacing the blunt `_BLOCKED_CMDS` denylist. This *is* the Awakening `tiered_permissions` item.

### Axis 1 — SCOPE (where it may run/write) `[D7]`
- **Default = full machine** (no `PROJECT_DIR` lock) — risky operations confirm. This deliberately
  seeds the Agent-tier `shell_full_access` early. Because the default is wide, the **safety floor**
  (§7) does the heavy lifting.
- Network on/off is part of scope `[D9]`.

### Axis 2 — APPROVAL MODE (when it must ask) `[D17]`
Selectable, switchable anytime (`/mode` in chat/REPL, `tobi --mode`), like Claude Code / Codex.
**Four modes, default = Ask:**

| Mode | low-risk | medium-risk | high-risk | notes |
|------|----------|-------------|-----------|-------|
| **Plan** | — | — | — | read + propose only; **executes nothing** (Claude Code `plan` / opencode Plan) |
| **Ask** ⟵ default | auto | confirm | confirm | the safe default |
| **Accept** | auto | auto | confirm | only high-risk pauses (Claude Code `acceptEdits`) |
| **Auto** | auto | auto | auto | runs everything — **hard denylist still blocks** (Codex `auto`/full-access) |

### Risk classification — hybrid `[D8]`
- **Static rules** for known-safe (`ls`, `cat`, `pip list`, `git status`) → low, and known-dangerous
  (`rm -rf`, disk format, fork bombs) → high/denylist. No LLM call.
- **LLM judge** (Haiku) rates only **ambiguous** commands. Best balance of speed / cost / safety.

Scope × mode × risk compose: e.g. *Accept mode + a network install* → medium → **auto-runs** (logged);
*Ask mode + same* → **confirms**; *Plan mode* → **proposes, never runs**.

---

## 5. Surfaces

- **MC: terminal mode inside the Chat page `[D19]`** (no new route). The Chat page (#8) gains a
  **terminal mode/panel**: live SSE console, **mode switcher**, inline approval cards, command
  history, background-job list, and the capability registry. Reuses Premium Chat's streaming + `+`
  menu machinery.
- **Telegram, capped at Ask `[D18]`:** low-risk auto-runs; medium/high require a typed/button
  confirm there. Telegram **cannot** escalate to Accept/Auto (no live console when away from the PC).
  Mirrors the Conductor (#7) surface asymmetry.
- **REPL `[D4]`:** `main.py terminal` upgraded into the interactive TOBI terminal (modes, streaming,
  jobs, `/mode`, `/status`).
- **`tobi` command `[D2][D20]`:** thin Hermes passthrough + MC logging. Headless use is available
  via Hermes; the agentic verbs live in the REPL/Chat/Telegram surfaces.
- **Auth `[D21]`:** localhost → **trust 127.0.0.1** (no prompt); remote → a **single-owner token**
  issued from the Genesis vault (revocable). Single-owner system (D66).

---

## 6. Acquire — install / configure / connect (the headline use case)

- **Package managers in scope `[D13]`:** **pip/pipx**, **npm/pnpm/npx**, **winget**, **Chocolatey/Scoop**.
- **Configure / connect `[D14]`:** *configure* = TOBI writes/edits the tool's config files; *connect*
  = store the tool's credentials in the **Genesis vault (#4)** then run the tool's setup/login. **No
  plaintext secrets.**
- **Capability registry `[D15]`:** a DB-backed **`installed_tools`** table (name, version, how-to-use,
  status) surfaced in MC and **mirrored to `~/.hermes/skills`**. TOBI remembers what it can do; its
  toolset grows over time — true Agent-tier behavior.
- **Auto-wire acquired tools `[D16]`:** after install/configure, TOBI **offers** to wire the new CLI
  as a **Conductor tool / MCP tool (#5)** so future calls skip raw shell and the capability compounds.
- **Self-modification `[D27]`:** TOBI may edit its **own repo / pip-install into its own venv**, but
  those actions are **forced to high-risk** (propose + wait) in Plan/Ask/Accept; only Auto would run
  them unattended. Enables safe self-improvement without self-corruption.

---

## 7. Safety floor `[D25]` (all three — the price of full-machine default)

1. **Absolute hard denylist** — `rm -rf /`, disk wipes/format, fork bombs, etc. **Even Auto mode
   cannot bypass it.** (Supersedes the old `_BLOCKED_CMDS`.)
2. **Global kill-switch** — a master *"disable shell"* toggle in MC/Settings that freezes all
   execution instantly.
3. **Secret redaction** — mask API keys / tokens / `.env` values in stored output + audit (consistent
   with D37 vault + D63 audit-retention).

Plus: **full audit `[D22]`** of every command → the existing **`tobi_actions`** table (#7): command,
mode, risk, scope, cwd, exit code, output-tail, trigger surface (MC/TG/CLI), timestamps — visible in
`/actions` + the Chat activity panel. **Approvals `[D24]`** reuse the Conductor pending-action card
(Confirm/Cancel in MC; typed `yes`/`có` or a Telegram button resolves it).

---

## 8. State & schema changes

- **`terminal_sessions` `[D23]`** (new) — cross-surface, resumable: `cwd`, `env`, active `mode`,
  command `history`. Start a session in Telegram, continue it in MC (mirrors `chat_store` sessions).
- **`terminal_jobs` `[D11]`** (new) — background-job registry: command, pid/handle, status, started/
  ended, output ring-buffer, exit code.
- **`installed_tools` `[D15]`** (new) — capability registry: name, version, install channel,
  how-to-use, wired-as-tool flag, status.
- **`tobi_actions` `[D22]`** (extend, from #7) — add terminal-specific columns if needed (`mode`,
  `scope`, `cwd`, `exit_code`, `output_tail`).
- **`llm_usage` `[D28]`** — terminal-loop calls tagged `source='terminal'` (#10 instrumentation).

---

## 9. Phasing `[D29]`

- **P0 — Engine.** Extract `core/terminal_engine.py`; two-axis scope × approval **modes** + hybrid
  risk classifier; **safety floor** (denylist + kill-switch + redaction); per-risk timeout;
  background-job registry; full `tobi_actions` audit. Cross-platform shell/path detection.
- **P1 — Surfaces.** Terminal **mode inside Chat** (live SSE + mode switcher + approval cards + job
  list); **Telegram** (capped at Ask); Conductor tools (`run_command`, `list_jobs`, `kill_job`);
  `terminal_sessions` persistence.
- **P2 — Acquire.** `install_package` / `configure_tool` / `connect_tool` across the 4 package
  managers; **vault-backed** connect; **capability registry** (`installed_tools`, mirror to Hermes
  skills); **auto-wire** acquired tools into the Conductor/MCP catalog.
- **P3 — CLI.** The `tobi` Hermes-wrapper command + MC logging; **remote owner-token** auth; upgraded
  REPL polish; self-modify path hardened.

---

## 10. Evolution / Awakening `[D30]`

TOBI CLI **is** the implementation of the Awakening-tier control abilities and seeds the Agent tier:

- Awakening `tiered_permissions` → **delivered** by §4 (two-axis model replaces `_BLOCKED_CMDS`).
- Awakening `full_filesystem` → **delivered** by §4 Axis-1 (full-machine scope, risk-gated).
- Agent `shell_full_access` → **seeded** (full-machine shell with risk-gating + timeout).

Mark those Evolution abilities (`api/dashboard.py` `_TIER_DEFINITIONS`) active when this ships. Build
now — no waiting on the rest of Awakening.

---

## 11. Reference CLIs studied (the user asked for "the best solutions")

Design drew on the 2026 state of the leading agent CLIs:

- **OpenAI Codex CLI** — the **two-axis safety model**: *sandbox mode* (workspace-write /
  danger-full-access, OS-enforced, network off by default) × *approval policy* (untrusted /
  on-request). Directly mapped onto our **scope × mode** axes `[D6][D7][D17]`.
  ([sandboxing](https://developers.openai.com/codex/concepts/sandboxing) ·
  [approvals & security](https://developers.openai.com/codex/agent-approvals-security))
- **Claude Code** — **selectable permission modes** (`plan` / `acceptEdits` / `dontAsk` /
  `bypassPermissions`), **scoped allow-rules** (`Bash(git diff *)`), a **layered evaluation order**
  (hooks → allow/deny → mode → callback), and **headless `-p`**. Shaped our **4-mode set** `[D17]`,
  the rules-first risk classifier `[D8]`, and the audit/approval flow.
  ([headless](https://code.claude.com/docs/en/headless) ·
  [permissions](https://platform.claude.com/docs/en/agent-sdk/permissions))
- **opencode** — **client/server** architecture (one always-on brain, many thin clients — drive from
  laptop/phone) + **Plan mode**. Validated routing everything through the always-on MC/Conductor and
  keeping `tobi` a thin client `[D2][D3][D19]`.
  ([opencode docs](https://opencode.ai/docs/cli/) ·
  [deep dive](https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/))

---

## 12. Decision log (D1–D30)

| # | Decision |
|---|----------|
| **D1** | Build **both faces, phased**: TOBI-as-terminal-user + the owner `tobi` command. |
| **D2** | The `tobi` command **wraps the Hermes CLI** + adds MC logging (no standalone agent loop). |
| **D3** | **Route terminal actions through the Conductor (#7)** — new Conductor tools, reusing tiers/confirm/audit/voice/both-surfaces. |
| **D4** | **Upgrade the `main.py terminal` REPL**; keep **Hermes as the 24/7 runtime**; keep `hermes_sync.py` one-way. |
| **D5** | **Upgrade `run_bash` in place** → extract to `core/terminal_engine.py`; keep read/write/run/list working. |
| **D6** | **Two-axis safety** (Codex-style): sandbox **scope** × approval **policy**, mapped to SOUL.md tiers. |
| **D7** | Default **scope = full machine**; risky operations confirm (seeds Agent-tier `shell_full_access`). |
| **D8** | **Hybrid risk classifier**: static rules for known-safe/known-dangerous; LLM (Haiku) judges ambiguous. |
| **D9** | **Network ON**, but network-touching commands auto-rated **medium** + logged. |
| **D10** | Output: **stream live to MC (SSE)**, **summarize to Telegram** (result + tail). |
| **D11** | **Background job registry** (`terminal_jobs`): detach long commands, inspect/stream/kill later; short inline. |
| **D12** | **Per-risk + configurable timeout** (quick ~30s, install ~300s, background unbounded). |
| **D13** | Package managers in scope: **pip/pipx, npm/pnpm/npx, winget, Chocolatey/Scoop**. |
| **D14** | Configure = write config files; **connect = vault-store creds (#4) + run tool's login/setup**. No plaintext secrets. |
| **D15** | **Capability registry** (`installed_tools`), surfaced in MC + **mirrored to Hermes skills**; grows over time. |
| **D16** | **Auto-offer to wire** acquired CLIs as **Conductor/MCP tools (#5)** so future calls skip raw shell. |
| **D17** | **Four selectable modes** — **Plan / Ask (default) / Accept / Auto** — switch via `/mode` or `tobi --mode`. |
| **D18** | **Telegram capped at Ask** (low auto, med/high confirm); no Accept/Auto from phone. |
| **D19** | Terminal UI = **mode inside the Chat page (#8)**, not a new route. |
| **D20** | `tobi` = **pure Hermes passthrough + MC logging** (no new TOBI verbs in v1). |
| **D21** | Auth: **localhost-trust** (127.0.0.1, no prompt) + **single-owner vault token** for remote (revocable). |
| **D22** | **Full audit** of every command → `tobi_actions` (#7): cmd, mode, risk, scope, cwd, exit, output-tail, surface, ts. |
| **D23** | **`terminal_sessions`** DB persistence — cross-surface, resumable (cwd/env/mode/history). |
| **D24** | Approvals **reuse the Conductor pending-action card** (Confirm/Cancel; typed `yes`/`có`; TG button). |
| **D25** | **Safety floor = hard denylist (Auto can't bypass) + global kill-switch + secret redaction** (all three). |
| **D26** | **Cross-platform from day one** (detect OS → branch shell/paths/package-managers). |
| **D27** | **Self-modify allowed but forced high-risk + confirm** (own repo/venv); only Auto runs it unattended. |
| **D28** | Model: **model_router tiered** (Haiku simple/classify, Opus complex), log to `llm_usage` (#10), **small monthly cap + alert**. |
| **D29** | Phasing: **P0 engine → P1 Chat-mode + Telegram + Conductor tools → P2 acquire/registry/wire → P3 owner CLI + remote**. |
| **D30** | **Delivers** Awakening `tiered_permissions` + `full_filesystem`; **seeds** Agent `shell_full_access`; **build now**. |

---

## 13. Open inputs (not blockers — set before/at build)

- **Hard denylist contents** — confirm the absolute never-run patterns (Windows + POSIX) for the
  safety floor `[D25]`.
- **Monthly spend cap value** + alert threshold for the terminal LLM loop `[D28]`.
- **Default timeout values** for quick / install tiers `[D12]`.
- **Remote owner-token** — issue from the vault only if/when remote CLI use is wanted `[D21]`.
- **Hermes CLI presence** — `tobi` passthrough `[D2]` degrades gracefully if `hermes` isn't on PATH
  (consistent with `hermes_sync.py`'s existing graceful behavior).
- **Per-package-manager elevation** — confirm whether winget/choco installs that need admin should be
  high-risk/confirm even in Accept mode `[D13]`.
