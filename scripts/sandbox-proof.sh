#!/usr/bin/env bash
# Task 23.0 AC-4: prove a whole-suite run left no row in a LIVE log, judged by CONTENT.
#
# Why content (ns23-2, 2026-10-14): the live logs grow from normal activity during a 13-minute
# run (the re-review saw the repo's query.log and facts.log written at 12:42 and 12:43 while it
# only read), so size and mtime cannot be the check. This wrapper draws a fresh
# RMX_SANDBOX_TAG (every sandbox path then carries `rmx-<tag>-`), records each live log's
# (inode, size), runs the suite, and fails if any DELTA line carries the tag, `/pytest-of-`, or
# the d9g fixture shape; the touches log must gain no line outside the sandbox's own deliberate
# refusal probes. The check itself lives once in tests/sandbox_site/rmx_sandbox.py.
#
# Usage: scripts/sandbox-proof.sh [--live-logs DIR] [-- PYTEST-ARGS...]
#   --live-logs DIR  read DIR/global/{query,facts}.log and DIR/repo/{query,facts}.log instead of
#                    ~/.refmatrix/ and <repo>/.refmatrix/ (AC-4's detector check, no live write)
#   -- ARGS          replace the full-suite selection (default: -q -p no:cacheprovider)
#   RMX_PYTEST_PY    the interpreter (default <repo>/.venv-eval/bin/python, as scripts/ptest.sh)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${RMX_PYTEST_PY:-$REPO/.venv-eval/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"   # a clone has no .venv-eval of its own
HELPER="$REPO/tests/sandbox_site/rmx_sandbox.py"
OUT="$REPO/workflow/review-output"
LIVE=""
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --live-logs) LIVE="${2:?--live-logs needs a directory}"; shift 2 ;;
    --) shift; ARGS=("$@"); break ;;
    *) echo "sandbox-proof: unknown argument: $1 (usage: [--live-logs DIR] [-- PYTEST-ARGS])" >&2
       exit 2 ;;
  esac
done
[ ${#ARGS[@]} -eq 0 ] && ARGS=(-q -p no:cacheprovider)

if [ -n "$LIVE" ]; then
  LOGS=("$LIVE/global/query.log" "$LIVE/global/facts.log"
        "$LIVE/repo/query.log" "$LIVE/repo/facts.log")
else
  LOGS=("$HOME/.refmatrix/query.log" "$HOME/.refmatrix/facts.log"
        "$REPO/.refmatrix/query.log" "$REPO/.refmatrix/facts.log")
fi

mkdir -p "$OUT"
TAG="$("$PY" -c 'import secrets; print(secrets.token_hex(3))')"
SNAP="$(mktemp "${TMPDIR:-/tmp}/rmx-proof-snap.XXXXXX")"
TOUCHES="$OUT/live-socket-touches.log"
TOUCHES_SIZE=0
[ -f "$TOUCHES" ] && TOUCHES_SIZE="$(wc -c < "$TOUCHES" | tr -d ' ')"
"$PY" "$HELPER" snapshot "$SNAP" "${LOGS[@]}"

echo "sandbox-proof: tag=$TAG, ${#LOGS[@]} live logs, suite: ${ARGS[*]}"
set +e
RMX_SANDBOX_TAG="$TAG" PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PY" -m pytest "${ARGS[@]}" 2>&1 | tee "$OUT/pytest-sandbox.log"
SUITE_RC=${PIPESTATUS[0]}
"$PY" "$HELPER" check "$SNAP" "$TAG" "$TOUCHES" "$TOUCHES_SIZE"
CHECK_RC=$?
set -e
rm -f "$SNAP"

echo "sandbox-proof: suite exit=$SUITE_RC, content check exit=$CHECK_RC"
if [ "$CHECK_RC" -ne 0 ]; then
  echo "sandbox-proof: FAIL -- the run left sandbox rows in a live log (see LEAK lines above)"
  exit 1
fi
if [ "$SUITE_RC" -ne 0 ]; then
  echo "sandbox-proof: the content check is clean but the suite itself failed (exit $SUITE_RC)"
  exit "$SUITE_RC"
fi
echo "sandbox-proof: PASS"
