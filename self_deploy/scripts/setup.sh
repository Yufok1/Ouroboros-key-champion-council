#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FULL="${1:-}"

if [[ ! -d .venv ]]; then
  echo "[setup] Creating virtualenv..."
  python3 -m venv .venv
fi

PYTHON="$ROOT/.venv/bin/python"

echo "[setup] Upgrading pip..."
"$PYTHON" -m pip install --upgrade pip

if [[ "$FULL" == "--full" ]]; then
  echo "[setup] Installing full dependencies (server + capsule)..."
  "$PYTHON" -m pip install -r requirements.txt
else
  echo "[setup] Installing server dependencies..."
  "$PYTHON" -m pip install -r requirements-server.txt
fi

if [[ ! -f config/.env && -f config/.env.example ]]; then
  cp config/.env.example config/.env
  echo "[setup] Created config/.env from .env.example"
fi

echo "[setup] Done."
