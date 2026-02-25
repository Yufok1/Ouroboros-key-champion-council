#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "[run] Virtualenv not found. Running setup first..."
  "$ROOT/scripts/setup.sh"
fi

echo "[run] Starting self_deploy backend..."
exec "$ROOT/.venv/bin/python" backend/server.py
