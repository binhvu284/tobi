#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# TOBI VPS one-time setup — run this ONCE on your VPS.
#
# Creates a bare git repo with a push-to-deploy hook, clones your code into
# the working directory, installs Python deps, builds the frontend, and starts
# the server.
#
# Usage (on the VPS):
#   git clone <your-repo-url> ~/tobi && cd ~/tobi && bash setup-vps.sh
#
# After setup, from your LOCAL machine:
#   git remote add deploy user@your-vps-ip:~/repos/tobi.git
#   git push deploy main          # ← this auto-deploys every time
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$HOME/repos/tobi.git"
BRANCH="${DEPLOY_BRANCH:-main}"

echo "═══════════════════════════════════════════════════════════"
echo "  TOBI VPS Setup"
echo "═══════════════════════════════════════════════════════════"
echo "  Working dir: $INSTALL_DIR"
echo "  Bare repo:   $REPO_DIR"
echo "  Branch:      $BRANCH"
echo ""

# ── 1. Python venv ──────────────────────────────────────────
if [ ! -d "$INSTALL_DIR/venv" ]; then
    echo "── Creating Python virtual environment ──"
    python3 -m venv "$INSTALL_DIR/venv"
fi
echo "── Installing Python dependencies ──"
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || \
    "$INSTALL_DIR/venv/bin/pip" install -q fastapi uvicorn requests pydantic 2>/dev/null || true

# ── 2. Frontend build ───────────────────────────────────────
if command -v npm &>/dev/null; then
    echo "── Building frontend ──"
    cd "$INSTALL_DIR/dashboard"
    npm install --silent 2>/dev/null || true
    npm run build 2>/dev/null || echo "  ⚠ Frontend build skipped (will retry on first deploy)"
    cd "$INSTALL_DIR"
else
    echo "  ⚠ npm not found — frontend won't build until Node.js is installed"
    echo "    Install with: curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
fi

# ── 3. Bare git repo + hook ─────────────────────────────────
echo "── Setting up bare git repo + deploy hook ──"
mkdir -p "$(dirname "$REPO_DIR")"
if [ ! -d "$REPO_DIR" ]; then
    git init --bare "$REPO_DIR"
fi

# Write the post-receive hook
cat > "$REPO_DIR/hooks/post-receive" << HOOK
#!/usr/bin/env bash
set -euo pipefail
TARGET="$INSTALL_DIR"
BRANCH="$BRANCH"
GIT_DIR="\$(pwd)"

while read -r oldrev newrev ref; do
    branch=\$(echo "\$ref" | sed 's|refs/heads/||')
    if [ "\$branch" != "\$BRANCH" ]; then
        echo "  ↳ Pushed \$branch — skipping (only \$BRANCH auto-deploys)"
        continue
    fi
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  TOBI auto-deploy: \$BRANCH (\$(echo \$newrev | cut -c1-7))"
    echo "═══════════════════════════════════════════════════════════"
    echo "── Checking out code ──"
    git --work-tree="\$TARGET" --git-dir="\$GIT_DIR" checkout -f "\$BRANCH"
    git --work-tree="\$TARGET" --git-dir="\$GIT_DIR" clean -fd -e data -e logs -e venv -e .env
    echo "── Running deploy.sh ──"
    cd "\$TARGET"
    bash deploy.sh
    echo ""
    echo "✓ Deploy complete: \$newrev"
done
HOOK
chmod +x "$REPO_DIR/hooks/post-receive"

# ── 4. Logs directory ───────────────────────────────────────
mkdir -p "$INSTALL_DIR/logs"

# ── 5. Start the server (if not already running) ────────────
if pgrep -f "python.*main.py start" >/dev/null 2>&1; then
    echo "── TOBI is already running — skipping start ──"
else
    echo "── Starting TOBI ──"
    cd "$INSTALL_DIR"
    nohup venv/bin/python main.py start > logs/tobi.log 2>&1 &
    sleep 3
    if pgrep -f "python.*main.py start" >/dev/null 2>&1; then
        echo "  ✓ TOBI started (PID: $(pgrep -f 'python.*main.py start' | head -1))"
    else
        echo "  ⚠ TOBI didn't start — check logs/tobi.log"
    fi
fi

# Install the external coding runner as a separately supervised service when
# systemd and non-interactive sudo are available. The API remains in local
# runner mode until TOBI_CODING_RUNNER_MODE=service is set in .env.
if command -v systemctl >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    echo "── Installing supervised coding runner ──"
    bash "$INSTALL_DIR/scripts/install_coding_runner_service.sh" "$INSTALL_DIR" || \
        echo "  ⚠ Coding runner service install failed; rerun the installer manually."
else
    echo "  ⚠ systemd or passwordless sudo unavailable; install the coding runner manually:"
    echo "    bash $INSTALL_DIR/scripts/install_coding_runner_service.sh $INSTALL_DIR"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Setup complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  From your LOCAL machine, add the deploy remote:"
echo ""
echo "    git remote add deploy $USER@$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'VPS-IP'):$REPO_DIR"
echo ""
echo "  Then push to deploy:"
echo ""
echo "    git push deploy main"
echo ""
echo "  Every push will auto-build + restart. No SSH needed."
echo ""
