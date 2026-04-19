#!/usr/bin/env bash
# Run FastAPI from repo root (avoids "No module named 'app'" when cwd is not backend/).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT:-8000}"
