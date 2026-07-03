#!/bin/bash
# TOBI cloud bootstrap — installs Python + dashboard dependencies at the start of a
# Claude Code web/cloud session (claude.ai/code or the mobile app), so an agent
# launched from your phone can build and unit-test TOBI out of the box.
#
# Local (PC) sessions are skipped: your machine already has its own venv +
# node_modules, and CLAUDE_CODE_REMOTE is only "true" in Anthropic's cloud VM.
# Wired via .claude/settings.json → SessionStart. Runs every session/resume, so
# both steps short-circuit when the deps are already present (fast on resume).
set -u

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0   # cloud sessions only

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT" || exit 0

# ── Python deps (skip if already importable) ────────────────────────────────
if python3 -c "import fastapi" >/dev/null 2>&1; then
  echo "[tobi] python deps present — skipping pip"
else
  echo "[tobi] installing python deps from requirements.txt…"
  python3 -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
  python3 -m pip install --quiet -r requirements.txt \
    || echo "[tobi] pip install hit an issue (continuing — the session still starts)"
fi

# ── Dashboard deps (skip if node_modules already installed) ──────────────────
if [ -d dashboard ]; then
  if [ -d dashboard/node_modules ]; then
    echo "[tobi] dashboard node_modules present — skipping npm"
  else
    echo "[tobi] installing dashboard deps (npm)…"
    if [ -f dashboard/package-lock.json ]; then
      ( cd dashboard && npm ci --no-audit --no-fund ) \
        || ( cd dashboard && npm install --no-audit --no-fund ) \
        || echo "[tobi] npm install hit an issue (continuing)"
    else
      ( cd dashboard && npm install --no-audit --no-fund ) \
        || echo "[tobi] npm install hit an issue (continuing)"
    fi
  fi
fi

echo "[tobi] cloud bootstrap done."
exit 0
