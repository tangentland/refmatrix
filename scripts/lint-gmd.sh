#!/usr/bin/env bash
# Lint the project's GMD graph with the correct scope.
#
# refmatrix scope: CLAUDE.md (root agent-rules doc), docs/, workflow/, eval/, the project profile,
# and —
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
# `eval/` is a CORPUS ROOT (.claude/PROJECT_PROFILE.md#corpus) and carries GMD docs with `rel:`
# edges, but was outside this list — so `eval/production/longmemeval/REPORT.md` was ingested into
# the graph and linted by nothing. A stray code fence there deleted its `#next` node and no gate
# could see it (ch-bsd r4 #b-2-r4). A corpus root that is ingested is a corpus root that is linted.
SCOPE=(CLAUDE.md docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md)
[[ -d "$MEMDIR" ]] && SCOPE+=("$MEMDIR")
exec python3 "$LINTER" "${SCOPE[@]}" "$@"
