#!/usr/bin/env bash
# Prepare a disposable developer workspace. Do not start TOBI services here.
set -euo pipefail

export PIP_DISABLE_PIP_VERSION_CHECK=1
export NPM_CONFIG_AUDIT=false
export NPM_CONFIG_FUND=false

python -m pip install --user --upgrade pip
python -m pip install --user -r requirements.txt

if [[ -f dashboard/package-lock.json ]]; then
  (
    cd dashboard
    npm ci
  )
else
  (
    cd dashboard
    npm install
  )
fi

echo "TOBI developer environment is ready. Services remain stopped until you run a focused command."
