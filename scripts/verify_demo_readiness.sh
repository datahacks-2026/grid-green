#!/usr/bin/env bash
# Pre-flight checks aligned with DataHacks submission readiness:
# backend tests + frontend production build + ESLint.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Backend pytest (from $ROOT/backend)"
cd "$ROOT/backend"
if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
fi
python -m pytest -q

echo "==> Frontend npm install (if needed)"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi

echo "==> Frontend production build"
npm run build

echo "==> Frontend lint"
npm run lint

echo "OK — demo readiness checks passed."
