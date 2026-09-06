# Subscription Usage Tracking

**Item:** #38 · `NEW-CORE-1D-014`
**Status:** Draft — proposed, not started
**One line:** See how much of your Claude Code and Codex subscriptions you have burned, inside Mission Control, without opening either tool.

---

## 1. The problem

You pay for Claude (Pro/Max) and ChatGPT (Plus/Pro). Both meter you on a rolling
window — a **5-hour window** (a short-term cap that refills a few hours after you
start using it) and a **weekly window** (a longer cap on top of it). Today the only
way to see either number is to open the tool itself and type `/usage` (Claude Code)
or `/status` (Codex). That means you find out you are near a cap *after* you have
started work, not before.

MC already has a Storage & Usage page, but it only counts **TOBI's own API calls**
(item #10). It knows nothing about what you spend from the subscriptions, which is
where most of your real capacity goes.

**What "done" looks like:** you open MC, glance at one card, and know whether you can
start a big coding session right now or should wait for a reset.

---

## 2. What the research found

I confirmed the data shapes on this machine rather than trusting blog posts.

| Provider | What we can read | Where it comes from | How reliable |
|---|---|---|---|
| **Claude Code** — token history | Per-message model, input/output/cache tokens, timestamp, session, project folder | Local files `~/.claude/projects/**/*.jsonl` — **verified live in this session**, exact field names confirmed | High. Local files, no network, no key. |
| **Claude Code** — the % of your cap used | `five_hour.utilization`, `seven_day.utilization`, per-model weekly splits, `resets_at` timestamps, extra-usage balance | `GET https://api.anthropic.com/api/oauth/usage`, using the login token Claude Code already stored on this machine | Medium. This is the same source `/usage` reads, but it is **undocumented** — Anthropic can change it without notice. |
| **Codex** — tokens *and* the % of your cap used | `token_count` events carrying `total_token_usage` plus `rate_limits` with `used_percent`, `window_minutes`, `resets_in_seconds` | Local files `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | High for tokens. Medium for limits — the numbers are only as fresh as your **last Codex session**, because they are a snapshot Codex wrote, not a live reading. |

Two consequences worth stating plainly:

1. **Codex needs no network call at all.** OpenAI already writes the limit percentages
   into the local session file. We just read the newest one.
2. **Claude needs one network call** to get the live percentage. Without it we can still
   show tokens and estimated value, but not "you are at 62% of your weekly cap".

### Buy versus build

Tools already exist — `ccusage` (Claude only, CLI), `vibeusage` (13 providers, terminal
UI), SessionWatcher (macOS menu bar). They are good, and I checked them before proposing
we build.

**Recommendation: build it into MC.** Your stated goal is *"so I don't have to open those
apps"* — swapping two apps for a third app does not solve that. The reading logic is small
(roughly 200-250 lines) now that the file shapes are confirmed, and putting the data in
MC's own database means TOBI can later use it in decisions, which no external tool can do.

---

## 3. Proposed design

### Where it lives in MC

A new **Subscriptions** tab on the existing **Storage & Usage** page, plus a small
two-bar card on the Dashboard so you see it without navigating.

Reusing the Storage & Usage page rather than making a new page is deliberate: it already
owns the charts, the date-range control, and the price table. Building a fresh page would
duplicate all three.

### The pieces

| Piece | File | What it does |
|---|---|---|
| Readers | `core/subscription_usage.py` | One reader per provider. Each returns the same shape, so the UI does not care which tool the numbers came from. |
| Store | new tables in the existing `agent.db` | `sub_usage_daily` (tokens per day/provider/model), `sub_usage_windows` (the latest cap percentages), `sub_usage_ingest` (how far we read each file, so re-scanning is cheap). |
| Scheduled job | `core/scheduled_jobs.py` | Re-scan local files every 5 minutes; refresh the Claude live percentage no more often than every 3 minutes. |
| API | `api/routers/subscriptions.py` | `GET /api/subscriptions/usage`, `POST /api/subscriptions/refresh`. |
| UI | `dashboard/src/pages/Storage.tsx` + a new component | The tab, the meters, the 30-day chart. |

### What the screen shows

```
CLAUDE CODE                                  Claude Max
  5-hour window   ███████░░░░░░░░  43%   resets 16:20
  Weekly          ██████████░░░░░  67%   resets Fri 09:00
  Today  412k tokens · 38 sessions · ~$14.20 at API rates

CODEX                                        ChatGPT Pro
  5-hour window   ████░░░░░░░░░░░  22%   resets 15:05
  Weekly          ██████░░░░░░░░░  41%   resets Sun 22:10
  Today  180k tokens · 11 sessions        as of 14:32 (last Codex session)

  [30-day chart: tokens per day, one colour per tool]
```

---

## 4. Rules this feature must follow

These come from `CLAUDE.md` and are not optional.

- **The dollar figure is labelled as notional, never as money spent.** On a subscription
  you do not pay per token. The number means *"this much usage would have cost this much
  at pay-as-you-go API rates"* — useful for deciding whether the subscription is worth it,
  and a lie if presented as a bill. The label says so on screen.
- **Read-only on credentials, always.** TOBI reads the stored login token to make the one
  Claude call and never writes it, logs it, caches it, or returns it through any API
  response. If it has expired, MC says *"Claude limits need a refresh — run any Claude Code
  command and they will update"*, not a raw error.
- **Stale is shown as stale.** Codex numbers carry the timestamp of the session they came
  from. If you have not run Codex in two days, the card says "as of 2 days ago" rather than
  implying it is live.
- **Every part degrades on its own.** If the undocumented Claude endpoint disappears, the
  token history and the Codex meters keep working, and the Claude meter says why it is
  blank. No single failure empties the page.
- **It works with zero configuration.** No API key to paste, no settings page to find. If
  the tool is installed on this machine, MC finds it.
- **Loading states are mandatory.** The refresh button uses `ActionButton`; replacing the
  meters uses `BusyOverlay`. `tests/test_ui_loading_states.py` enforces this.

---

## 5. Milestones

Assumes MC and both CLIs run on the same machine, which you confirmed.

| # | What ships | You can check it by | Size |
|---|---|---|---|
| **M1** | Both readers + the database tables + a `python scripts/check_subscription_usage.py` command that prints what it found. No UI yet. | Running that one command and seeing your real numbers in the terminal. | ~4 hours |
| **M2** | The API and the Subscriptions tab: both meters, today's totals, the 30-day chart. | Opening MC → Storage & Usage → Subscriptions and comparing against `/usage` in Claude Code. They should match. | ~4 hours |
| **M3** | Background refresh, the Dashboard card, and an in-app warning when a window passes a threshold you set (default 80%). | Working until a meter crosses 80% and seeing the warning appear in MC. | ~3 hours |

**Total: 1.5 focus days.** M1 alone already answers your original question; M2 and M3 are
what make it something you glance at rather than run.

---

## 6. Non-goals

- No Gemini, Cursor, or Copilot in v1. You do not pay for them today, and Cursor/Copilot
  need browser session tokens that break every few weeks.
- No changes to the existing #10 usage tracking of TOBI's own API calls. This sits beside
  it, in its own tables.
- No Telegram or push alerts. In-app only, consistent with the #10 decision.
- No writing to any provider file. Read-only, always.
- No uploader agent for a VPS. If MC later moves off this machine, that becomes its own item.
- No autonomous behaviour change — TOBI does not yet *decide* anything based on these
  numbers. That is a natural follow-up, not part of this.

---

## 7. The main risk, stated once

The Claude live-percentage endpoint is undocumented. It can change or close at any time,
and if it does, that one meter goes blank. Everything else in this feature reads local
files that the tools write for their own use, and those are stable.

I judge that acceptable because the meter is the enhancement, not the foundation — but you
should know the feature has one soft spot rather than discovering it later.

---

## Sources

- [ccusage / Claude Code JSONL usage parsing](https://ccclub.dev/claude-code-usage)
- [Anthropic OAuth usage endpoint — fields, headers, polling limits](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor/issues/202)
- [codex-ratelimit — reading rate limits from Codex session files](https://github.com/xiangz19/codex-ratelimit)
- [Codex usage, limits and logs](https://ccclub.dev/codex-usage)
- [vibeusage — multi-provider terminal usage tracker](https://github.com/joshuadavidthomas/vibeusage)
- [Anthropic Usage and Cost Admin API (API accounts, not subscriptions)](https://platform.claude.com/docs/en/manage-claude/usage-cost-api)
