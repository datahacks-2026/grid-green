#!/usr/bin/env bash
# check_secrets_health.sh — verify secrets are not tracked and scan staged/tracked files.
# Run from repo root:  bash scripts/check_secrets_health.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0

echo "==> Checking backend/.env is gitignored and not tracked"
if git ls-files --error-unmatch backend/.env >/dev/null 2>&1; then
  echo "FAIL: backend/.env is tracked by git — run: git rm --cached backend/.env" >&2
  FAIL=1
elif git check-ignore -q backend/.env 2>/dev/null || [ ! -f backend/.env ]; then
  echo "    OK (.env ignored or not present locally)"
else
  echo "FAIL: backend/.env exists but is not gitignored" >&2
  FAIL=1
fi

echo "==> Scanning all tracked files with secret_scan.py"
TRACKED="$(git ls-files)"
if [ -n "$TRACKED" ]; then
  # shellcheck disable=SC2086
  if ! python3 scripts/secret_scan.py $TRACKED; then
    FAIL=1
  fi
else
  echo "    (no tracked files)"
fi

echo "==> Rotation checklist (manual — rotate in each provider if ever committed or shared)"
cat <<'EOF'
    GEMINI_API_KEY  → https://aistudio.google.com/app/apikey
    EIA_API_KEY     → https://www.eia.gov/opendata/register.php
    SNOWFLAKE_*     → Snowflake console → Users → reset password
    WANDB_API_KEY   → https://wandb.ai/authorize
    AWS keys        → IAM → Security credentials → deactivate old, create new
    DATABRICKS_TOKEN → Workspace → User Settings → Developer → Access tokens
EOF

if [ "$FAIL" -ne 0 ]; then
  echo
  echo "Secrets health check FAILED." >&2
  exit 1
fi

echo
echo "Secrets health check passed."
