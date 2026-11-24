#!/usr/bin/env bash
# scripts/ptest.sh — the test runner's entry point: run tiers sharded, compare runs, gate a merge.
# A thin wrapper (task-29.4 #r2, 29.4a, 2026-11-23): the logic is scripts/ptest.py, in Python so
# it can be tested (the dev shell is bash 3.2). Its docstring lists the modes and exit codes:
#
#   scripts/ptest.sh --tier unit|daemon|devtree|timing|all [--shards N] [--name RUN]
#   scripts/ptest.sh --files tests/test_x.py … [--shards N] [--name RUN]
#   scripts/ptest.sh --compare [--outcomes] RUN_A RUN_B [--expect 'node:phase:from->to' …]
#   scripts/ptest.sh --merge-gate
#
# The interpreter is $RMX_PYTEST_PY, else this checkout's .venv-eval/bin/python; the same one
# runs the shards. Replaces the 24-line round-robin sharder that printed "ALL GREEN".
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PY="${RMX_PYTEST_PY:-$HERE/../.venv-eval/bin/python}"
if [ ! -x "$PY" ]; then
  echo "ptest.sh: no interpreter at $PY (set RMX_PYTEST_PY)" >&2
  exit 2
fi
exec "$PY" "$HERE/ptest.py" "$@"
