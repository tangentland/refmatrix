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
# parity script imports refmatrix, so it runs under the dev interpreter: `$RMX_DEV_PYTHON` when
# set, else `.venv-eval/bin/python`. A littlebig clone has no `.venv-eval` of its own and runs the
# dev tree's interpreter (bug-253, T0.2 stage 2, 2026-11-15; ruling L142 (3)): its caller names
# that interpreter, as tests/devbin.py names the dev `rmx` from `sys.executable`. Named or not, a
# missing interpreter stops the gate with exit 2 and names the path (never a narrower gate).
# Both steps always run (one failure never hides the other); exit is non-zero if either fails.
# Exit non-zero on errors; warnings are informational.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LINTER="$ROOT/tools/gmd/lint.py"
PARITY="$ROOT/scripts/check-gmd-parity.py"
DEVPY="${RMX_DEV_PYTHON:-$ROOT/.venv-eval/bin/python}"
RESOLVER="$ROOT/scripts/gmd_memdir.py"

if [[ ! -f "$LINTER" ]]; then
  echo "gmd lint not found at $LINTER" >&2
  echo "The bundled tools/gmd/lint.py is missing — restore it from the template." >&2
  exit 2
fi
if [[ ! -f "$PARITY" ]]; then
  echo "gmd parity check not found at $PARITY" >&2
  exit 2
fi
if [[ ! -f "$RESOLVER" ]]; then
  echo "gmd memory-dir resolver not found at $RESOLVER" >&2
  exit 2
fi
if [[ -n "${RMX_DEV_PYTHON:-}" && ! -x "$DEVPY" ]]; then
  echo "dev interpreter not found at RMX_DEV_PYTHON=$DEVPY" >&2
  echo "The anchor-parity step imports refmatrix; name an existing dev interpreter (the dev" >&2
  echo "tree's .venv-eval/bin/python) — this gate does not skip the step without it." >&2
  exit 2
fi
if [[ ! -x "$DEVPY" ]]; then
  echo "dev interpreter not found at $DEVPY" >&2
  echo "The anchor-parity step needs the .venv-eval dev venv (it imports refmatrix); create" >&2
  echo ".venv-eval/, or name the dev tree's interpreter in RMX_DEV_PYTHON (a clone, bug-253)" >&2
  echo "— this gate does not skip the step without it." >&2
  exit 2
fi

cd "$ROOT"
# The memory dir is chosen by ONE resolver, scripts/gmd_memdir.py (bug-155's residual + bug-254,
# T0.1' R1.4, 2026-11-15). The bash fallback that lived here (44d1a34) tested only that the
# own-slug dir existed and followed the origin one hop, so an EMPTY own-slug memory/ (Claude Code
# makes one for any session in the checkout) or a clone of a clone dangled every memory-id ref.
# The resolver needs a populated dir (>= 1 *.md), walks local origins hop by hop (bound 5, cycle
# guard), and prints one stderr line naming the chain whenever the own dir is not the one used.
# It runs under python3, as the linter does, never under $DEVPY: the resolver needs no refmatrix,
# and a no-venv clone (bug-253) that names its dev interpreter in RMX_DEV_PYTHON reaches this line
# and gets its memory dir. This script keeps no slug or origin logic of its own (AC-1.7).
# A resolver failure stops the gate with exit 2 (a missing precondition), never a narrower scope.
resolver_status=0
MEMDIR="$(python3 "$RESOLVER" "$ROOT" "$HOME")" || resolver_status=$?
if (( resolver_status != 0 )); then
  echo "lint-gmd: memory-dir resolver $RESOLVER failed (exit $resolver_status); the gate did not run" >&2
  exit 2
fi
# `eval/` is a CORPUS ROOT (.claude/PROJECT_PROFILE.md#corpus) and carries GMD docs with `rel:`
# edges, but was outside this list — so `eval/production/longmemeval/REPORT.md` was ingested into
# the graph and linted by nothing. A stray code fence there deleted its `#next` node and no gate
# could see it (ch-bsd r4 #b-2-r4). A corpus root that is ingested is a corpus root that is linted.
SCOPE=(CLAUDE.md docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md)
PARITY_ARGS=(CLAUDE.md docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md)
if [[ -n "$MEMDIR" ]]; then
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
