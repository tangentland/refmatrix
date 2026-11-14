#!/usr/bin/env bash
# Lint the project's GMD graph with the correct scope.
#
# refmatrix scope: CLAUDE.md (root agent-rules doc), docs/, workflow/, eval/, the project profile,
# and —
# when present on this machine — the curated memory dir for this checkout, because the
# workflow/bullshit ledger and docs cite memory ids ([[feedback_no_silent_failures]] …) that only
# resolve with the memory files in the scanned set. Missing memory dir = those refs surface as
# dangling-doc, which is the honest answer on a machine without the memories.
#
# Then, over the SAME scope, scripts/check-gmd-parity.py: lint's registered anchor set must equal
# the store ingester's node-id set for every GMD doc (bug-179, 2026-11-09). Lint passed 0 errors
# on a ledger whose 188 packed ids the store never registered; lint alone cannot see a
# disagreement with the ingester, so the gate that runs on a docs commit checks it directly. The
# parity script imports refmatrix, so it runs under the dev interpreter `.venv-eval/bin/python`.
# Both steps always run (one failure never hides the other); exit is non-zero if either fails.
# Exit non-zero on errors; warnings are informational.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LINTER="$ROOT/tools/gmd/lint.py"
PARITY="$ROOT/scripts/check-gmd-parity.py"
DEVPY="$ROOT/.venv-eval/bin/python"

if [[ ! -f "$LINTER" ]]; then
  echo "gmd lint not found at $LINTER" >&2
  echo "The bundled tools/gmd/lint.py is missing — restore it from the template." >&2
  exit 2
fi
if [[ ! -f "$PARITY" ]]; then
  echo "gmd parity check not found at $PARITY" >&2
  exit 2
fi
if [[ ! -x "$DEVPY" ]]; then
  echo "dev interpreter not found at $DEVPY" >&2
  echo "The anchor-parity step needs the .venv-eval dev venv (it imports refmatrix); create" >&2
  echo ".venv-eval/ — this gate does not skip the step without it." >&2
  exit 2
fi

cd "$ROOT"
SLUG="$(printf '%s' "$ROOT" | tr '/_' '--')"
MEMDIR="$HOME/.claude/projects/$SLUG/memory"
# bug-155 cause 2 (Q18, 2026-11-14): a littlebig clone (/Volumes/littlebig/refmatrix-<worker>) has
# a slug of its own and no memory dir, so every [[feedback_…]] / [[impression_…]] link dangled and
# the gate failed in every clone while the dev tree passed. A clone's `origin` is the canonical
# checkout's local path; when this checkout's slug has no memory dir, use that checkout's. Said on
# stderr either way, never silent.
if [[ ! -d "$MEMDIR" ]]; then
  ORIGIN_URL="$(git -C "$ROOT" config --get remote.origin.url 2>&1)" || ORIGIN_URL=""
  if [[ "$ORIGIN_URL" == /* && -d "$ORIGIN_URL/.git" ]]; then
    ORIGIN_ROOT="$(cd "$ORIGIN_URL" && pwd)"
    ORIGIN_SLUG="$(printf '%s' "$ORIGIN_ROOT" | tr '/_' '--')"
    ORIGIN_MEMDIR="$HOME/.claude/projects/$ORIGIN_SLUG/memory"
    if [[ -d "$ORIGIN_MEMDIR" ]]; then
      echo "lint-gmd: no memory dir for $ROOT; using its origin's ($ORIGIN_ROOT): $ORIGIN_MEMDIR" >&2
      MEMDIR="$ORIGIN_MEMDIR"
    else
      echo "lint-gmd: no memory dir for $ROOT or its origin $ORIGIN_ROOT; memory-id refs will dangle" >&2
    fi
  else
    echo "lint-gmd: no memory dir for $ROOT and no local-path origin; memory-id refs will dangle" >&2
  fi
fi
# `eval/` is a CORPUS ROOT (.claude/PROJECT_PROFILE.md#corpus) and carries GMD docs with `rel:`
# edges, but was outside this list — so `eval/production/longmemeval/REPORT.md` was ingested into
# the graph and linted by nothing. A stray code fence there deleted its `#next` node and no gate
# could see it (ch-bsd r4 #b-2-r4). A corpus root that is ingested is a corpus root that is linted.
SCOPE=(CLAUDE.md docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md)
PARITY_ARGS=(CLAUDE.md docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md)
if [[ -d "$MEMDIR" ]]; then
  SCOPE+=("$MEMDIR")
  PARITY_ARGS+=(--memory-dir "$MEMDIR")
fi

# Extra arguments ("$@") are lint flags and go to lint only.
lint_status=0
python3 "$LINTER" "${SCOPE[@]}" "$@" || lint_status=$?
parity_status=0
"$DEVPY" "$PARITY" "${PARITY_ARGS[@]}" || parity_status=$?

if (( lint_status != 0 || parity_status != 0 )); then
  echo "lint-gmd: lint exit $lint_status, anchor parity exit $parity_status" >&2
  exit $(( lint_status > parity_status ? lint_status : parity_status ))
fi
