#!/usr/bin/env bash
# Lint the project's GMD graph with the correct scope.
#
# refmatrix scope: CLAUDE.md (root agent-rules doc), docs/, workflow/, the project profile, and —
# when present on this machine — the curated memory dir for this checkout, because the
# workflow/bullshit ledger and docs cite memory ids ([[feedback_no_silent_failures]] …) that only
# resolve with the memory files in the scanned set. Missing memory dir = those refs surface as
# dangling-doc, which is the honest answer on a machine without the memories.
# Exit non-zero on errors; warnings are informational.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LINTER="$ROOT/tools/gmd/lint.py"

if [[ ! -f "$LINTER" ]]; then
  echo "gmd lint not found at $LINTER" >&2
  echo "The bundled tools/gmd/lint.py is missing — restore it from the template." >&2
  exit 2
fi

cd "$ROOT"
SLUG="$(printf '%s' "$ROOT" | tr '/_' '--')"
MEMDIR="$HOME/.claude/projects/$SLUG/memory"
SCOPE=(CLAUDE.md docs/ workflow/ .claude/PROJECT_PROFILE.md)
[[ -d "$MEMDIR" ]] && SCOPE+=("$MEMDIR")
exec python3 "$LINTER" "${SCOPE[@]}" "$@"
