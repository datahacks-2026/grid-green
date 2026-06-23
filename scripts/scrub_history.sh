#!/usr/bin/env bash
# scrub_history.sh — remove leaked Gemini API key from all git history.
#
# CRITICAL READ BEFORE RUNNING:
#   1. The leaked key is ALREADY on GitHub (origin = green-watts, grid-green = grid-green).
#      You MUST rotate the key in Google AI Studio FIRST. Treat it as compromised forever.
#      https://aistudio.google.com/app/apikey
#   2. Also rotate every other secret currently in backend/.env:
#        EIA, Snowflake password, W&B, AWS access key, Databricks token.
#   3. This script rewrites history. Anyone with the repo cloned will need to re-clone.
#   4. After it runs, you must force-push to BOTH remotes.
#
# Run from repo root:  bash scripts/scrub_history.sh

set -euo pipefail

if [ ! -d ".git" ]; then
  echo "ERROR: must be run from the repo root" >&2
  exit 1
fi

# Pass the compromised key at runtime — never commit it to this script.
# Example:  LEAKED_KEY='AIza...' bash scripts/scrub_history.sh
LEAKED_KEY="${LEAKED_KEY:-}"
if [ -z "$LEAKED_KEY" ]; then
  echo "ERROR: set LEAKED_KEY to the compromised secret before running." >&2
  echo "       Example: LEAKED_KEY='AIza...' bash scripts/scrub_history.sh" >&2
  exit 1
fi

echo "==> Sanity check: searching git history for the leaked key"
# NOTE: avoid `grep -q` here — it exits early, SIGPIPEs git log, and combined
# with `set -o pipefail` the whole pipeline reports failure (false negative).
HITS=$(git log --all -p 2>/dev/null | grep -cF "$LEAKED_KEY" || true)
if [ "${HITS:-0}" -eq 0 ]; then
  echo "    Not found in history. Nothing to scrub. Exiting."
  exit 0
fi
echo "    Found ${HITS} occurrence(s). Will rewrite history to redact."

echo "==> Stashing any unstaged changes (will pop after rewrite)"
STASHED=0
if ! git diff-index --quiet HEAD -- || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git stash push --include-untracked -m "scrub_history.sh auto-stash" >/dev/null && STASHED=1
fi

echo "==> Backing up current refs to refs/original-backup/"
for ref in $(git for-each-ref --format='%(refname)' refs/heads refs/remotes); do
  git update-ref "refs/original-backup/${ref#refs/}" "$ref" 2>/dev/null || true
done

echo "==> Rewriting all history (this may take a minute)"
# Replace the leaked key with a placeholder in every file across all commits.
git filter-branch --force --tree-filter "
  if command -v gsed >/dev/null 2>&1; then
    SED=gsed
    SED_INPLACE=(\"\$SED\" -i)
  elif sed --version >/dev/null 2>&1; then
    SED=sed
    SED_INPLACE=(\"\$SED\" -i)
  else
    SED=sed
    SED_INPLACE=(\"\$SED\" -i '')
  fi
  find . -type f \\
       -not -path './.git/*' \\
       -not -path './.venv/*' \\
       -not -path './venv/*' \\
       -not -path './node_modules/*' \\
       -not -path './frontend/node_modules/*' \\
       -not -path './*.pdf' \\
       -size -1M \\
       -exec \"\${SED_INPLACE[@]}\" 's/${LEAKED_KEY}/REDACTED_GEMINI_KEY_ROTATED/g' {} + 2>/dev/null || true
" --tag-name-filter cat -- --all

echo "==> Verifying (main branch only; backup refs cleaned next)"
HITS_AFTER=$(git log main -p 2>/dev/null | grep -cF "$LEAKED_KEY" || true)
if [ "${HITS_AFTER:-0}" -ne 0 ]; then
  echo "ERROR: key still present in history (${HITS_AFTER} occurrences). Investigate manually." >&2
  exit 1
fi
echo "    Clean."

if [ "$STASHED" = "1" ]; then
  echo "==> Restoring stashed changes"
  git stash pop >/dev/null || echo "    (manual: run 'git stash pop' to restore)"
fi

echo "==> Removing backup refs created by filter-branch"
git for-each-ref --format='delete %(refname)' refs/original 2>/dev/null | git update-ref --stdin || true
rm -rf .git/refs/original-backup 2>/dev/null || true
git stash clear 2>/dev/null || true

echo "==> Expiring reflog and garbage collecting"
git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin || true
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo
echo "==> NEXT STEPS — do these now:"
echo "    1. Verify your working tree still looks right:   git log --oneline -10"
echo "    2. Force-push to BOTH remotes:"
echo "         git push origin     --force --all"
echo "         git push origin     --force --tags"
echo "         git push grid-green --force --all"
echo "         git push grid-green --force --tags"
echo "    3. On GitHub, contact support to purge cached views of old commit SHAs"
echo "       (the rewritten commits are gone, but old SHAs may still be reachable"
echo "       via direct URL until GH GCs them):"
echo "       https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository"
echo "    4. Tell any teammate who cloned this repo to re-clone (their local history"
echo "       still has the key)."
echo
echo "==> Done."
