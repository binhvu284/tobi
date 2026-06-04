# Hermes Verify-First Spike Runbook (`[H19]`)

> **Purpose:** Before any Phase 1.5 / Phase 2 feature code that depends on Hermes, empirically
> confirm what the **installed** Hermes daemon on the VPS actually supports. The H-series
> (`docs/MISSION_CONTROL_SPEC.md` §9) is the *plan*; this spike *validates or corrects* it.
>
> **Rule (`[H19]`):** if a step here contradicts an H-decision, **the spike wins** — update §9 to
> match reality before building.
>
> **Who runs it:** Thomas, on the VPS (Claude Code in this Codespace cannot SSH to the VPS).
> **What to do:** run each block, paste the real output into the **Results** table at the bottom,
> and send it back. No feature code is written during the spike — it is read-only probing plus a
> couple of throwaway test skills that you delete at the end.
>
> **Why it matters:** `HERMES_QUICK_START.md` is partly aspirational (placeholder install URLs, a
> model id that was never real). So whether the installed Hermes supports skill generation,
> the skills-dir contract, the memory API, the gateway API, and tool/delegation is genuinely
> unknown until measured.

---

## 0. Prep — open a tracked session

```bash
ssh <user>@<VPS_IP>          # the box running the hermes systemd service
tmux new -s spike            # so the session survives a disconnect
hermes --version || hermes version
sudo systemctl status hermes --no-pager | head -20
```

**Capture:** the Hermes version string and whether the service is `active (running)`.

---

## 1. Config flags — does this build even claim the features?

```bash
sed -n '1,200p' ~/.hermes/config/hermes.yaml
hermes config show 2>/dev/null | sed -n '1,80p'
```

**Confirm the three flags exist and are `true`:** `persistent_memory`, `skill_generation`,
`auto_skill_save`. If any flag is **absent** (not just false), that feature may not exist in this
build — note it.

---

## 2. Skills directory — the storage contract (H12/H13)

```bash
ls -la ~/.hermes/skills/
find ~/.hermes/skills -maxdepth 2 -type f | head -40
# Inspect one real skill file to learn the on-disk format (frontmatter? plain md?):
F=$(find ~/.hermes/skills -name '*.md' | head -1); echo "== $F =="; sed -n '1,60p' "$F"
```

**Capture:**
- Exact path skills live under (`~/.hermes/skills/` vs `~/.hermes/skills/<namespace>/`).
- File format: plain markdown vs YAML-frontmatter + body. (This decides how MC writes the `.md`.)
- **Locking:** is there a lock/index file (`.lock`, `index.json`, a sqlite)? Does Hermes hold the
  dir open? Test whether an external write is picked up:

```bash
# Throwaway skill written by an EXTERNAL process (simulating MC writing the .md):
cat > ~/.hermes/skills/_spike_probe.md <<'EOF'
# Spike Probe Skill
When asked "spike probe", reply exactly: SPIKE-OK-7421.
EOF
# Does Hermes notice without a restart?  Wait ~10s then ask via CLI:
sleep 10
hermes -z "spike probe"
```

**Decision point (H12/H13):** if Hermes picks up an externally-written `.md` live → MC can own the
file and Hermes is the canonical body store as planned. If it needs a restart or a `hermes skill
reload`, **record that command** — MC must call it after writing.

---

## 3. Skill generation — can Hermes author a skill itself? (H8)

```bash
# Ask Hermes to CREATE a skill (prose/L1). Watch the skills dir for a new file.
hermes -z "Create a new skill called 'spike_greeter' that, when I say 'greet spike', replies with a one-line friendly hello. Save it."
ls -la ~/.hermes/skills/        # did a new file appear, and where?
NEW=$(find ~/.hermes/skills -name '*greet*' -o -name '*spike_greeter*' | head -1); echo "$NEW"; sed -n '1,60p' "$NEW" 2>/dev/null
hermes -z "greet spike"         # does the freshly-authored skill actually fire?
```

**Capture:**
- Did Hermes write a file unprompted-by-path (true auto-generation), or only describe one?
- Is the generated body **prose-only**, or did it embed shell/commands? (H8 expects prose-only
  for auto-gen; if it writes commands, the H8 safety seam needs the MC scrubber in front.)
- Did `auto_skill_save` persist it without an explicit "save"?

---

## 4. Memory API — is Hermes memory usable as the canonical store? (H10)

```bash
hermes memory add "spike lesson: prefer small diffs (impact 7)"
hermes memory search "small diffs"
ls -la ~/.hermes/memory/ ; sed -n '1,40p' ~/.hermes/memory/MEMORY.md 2>/dev/null
# Can an external reader parse it (MC needs to index it)?
file ~/.hermes/memory/* 2>/dev/null
```

**Capture:** does `add`/`search` work from the CLI? Is memory a readable markdown/JSON/sqlite that
MC can index (H10), or an opaque format? Record the on-disk path + format.

---

## 5. Gateway API — one bot, programmatic send? (H16)

```bash
hermes gateway --help 2>/dev/null | sed -n '1,40p'
hermes config show 2>/dev/null | grep -i -E 'telegram|gateway|allowed'
# Can we send a message THROUGH Hermes programmatically (so MC alerts ride this one bot)?
hermes gateway send --help 2>/dev/null || echo "no 'gateway send' subcommand"
```

**Capture:** is there a programmatic send path (so D21/D51 MC notifications go through the single
Hermes Telegram bot, H16), or only inbound chat? If no send API, note how MC alerts should reach
Telegram instead.

---

## 6. Tool / delegation — can a skill call tools or hand off? (H5/H18)

```bash
hermes -z "What tools or function-calling can you use? List them."
hermes --help 2>/dev/null | grep -i -E 'tool|deleg|agent|sub' || echo "no tool/deleg flags in help"
```

**Capture:** does Hermes expose tool-use / function-calling a skill can invoke (needed for H5
workflow-skills that call MC abilities)? Any built-in delegation (relevant to H18 — though
orchestration stays in MC regardless)?

---

## 7. Daemon footprint — confirm the H14 hardening target

```bash
systemctl cat hermes | grep -E 'User=|ExecStart=|MemoryLimit=|CPUQuota='
ps -o user= -p "$(pgrep -f 'hermes.*daemon' | head -1)"
# Can the daemon user read secrets it shouldn't?
sudo -u "$(ps -o user= -p "$(pgrep -f hermes | head -1)")" cat ~/.env 2>&1 | head -1 || true
```

**Capture:** confirm it currently runs `User=root` (the H14 de-root target) and whether the daemon
process can read `.env`/secrets today. This sizes the Phase-1.5 hardening work.

---

## 8. Cleanup (leave Hermes as you found it)

```bash
rm -f ~/.hermes/skills/_spike_probe.md
# delete the generated spike_greeter skill (path from step 3):
[ -n "$NEW" ] && rm -f "$NEW"
# optional: remove the spike memory line if your store supports deletion
sudo systemctl restart hermes        # only if a step required a reload
tmux kill-session -t spike
```

---

## Results — paste real output / answers here, then send back

| # | Probe | Expected (per H-series) | Actual result | Verdict |
|---|-------|-------------------------|---------------|---------|
| 0 | Version + service running | active (running) | | ☐ ok ☐ no |
| 1 | `skill_generation` / `persistent_memory` / `auto_skill_save` flags present + true | all true | | ☐ ok ☐ no |
| 2 | Skills dir path + file format | `~/.hermes/skills/…`, markdown | | ☐ ok ☐ no |
| 2 | External `.md` picked up live (no restart) | live pickup (H12/H13) | | ☐ live ☐ needs reload: `____` |
| 3 | Hermes auto-generates a skill file | yes, **prose-only** (H8) | | ☐ prose ☐ embeds code ☐ can't |
| 4 | `hermes memory add/search` + readable store | works, indexable (H10) | | ☐ ok ☐ no |
| 5 | Programmatic gateway send (one bot, H16) | send path exists | | ☐ ok ☐ inbound-only |
| 6 | Tool-use / function-calling available (H5) | yes | | ☐ ok ☐ no |
| 7 | Daemon runs `User=root`; can read `.env` | root today → de-root (H14) | | ☐ root ☐ other: `____` |

**Spike conclusion (fill in):**
- H-decisions **confirmed:** `____`
- H-decisions **contradicted → §9 must change:** `____`
- Surprises / blockers for Phase 1.5: `____`

> Once this table is filled and sent back, the Phase 1.5 plan (live Hermes self-evolution loop) is
> finalized against reality and §9 of `MISSION_CONTROL_SPEC.md` is reconciled. Only then does
> Phase 1.5 coding begin — and only with Thomas's explicit go-ahead.
