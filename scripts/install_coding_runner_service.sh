#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
SERVICE_NAME="tobi-coding-runner.service"
TEMPLATE="$ROOT/scripts/systemd/$SERVICE_NAME.template"
TARGET="/etc/systemd/system/$SERVICE_NAME"
RUN_USER="${SUDO_USER:-$USER}"
RUN_GROUP="$(id -gn "$RUN_USER")"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"

if [ ! -x "$ROOT/venv/bin/python" ]; then
    echo "Missing $ROOT/venv/bin/python. Create the VPS virtual environment first." >&2
    exit 1
fi
if [ ! -f "$TEMPLATE" ]; then
    echo "Missing systemd template: $TEMPLATE" >&2
    exit 1
fi

sed \
    -e "s|__ROOT__|$ROOT|g" \
    -e "s|__USER__|$RUN_USER|g" \
    -e "s|__GROUP__|$RUN_GROUP|g" \
    -e "s|__HOME__|$RUN_HOME|g" \
    "$TEMPLATE" | sudo tee "$TARGET" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME"

echo
echo "Set TOBI_CODING_RUNNER_MODE=service in $ROOT/.env, then restart TOBI."
