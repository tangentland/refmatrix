#!/usr/bin/env bash
# Parallel test runner — shards tests/ across N workers (no pytest-xdist needed)
# and aggregates pass/fail. Usage: scripts/ptest.sh [N] [extra pytest args...]
set -u
N="${1:-4}"; shift || true
PY="${RMX_PYTEST_PY:-.venv-eval/bin/python}"
TMP="$(mktemp -d)"
files=$(ls tests/test_*.py)
fail=0; pids=()
for i in $(seq 0 $((N - 1))); do
  shard=$(echo "$files" | awk "NR % $N == $i" | tr '\n' ' ')
  [ -z "$shard" ] && continue
  ( $PY -m pytest $shard -q -p no:cacheprovider "$@" > "$TMP/res$i" 2>&1
    echo "rc=$?" >> "$TMP/res$i" ) &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
for i in $(seq 0 $((N - 1))); do
  [ -f "$TMP/res$i" ] || continue
  echo "── shard $i ──"; grep -E "passed|failed|error|FAILED" "$TMP/res$i" | tail -4
  grep -q "rc=0" "$TMP/res$i" || fail=1
done
rm -rf "$TMP"
[ $fail -eq 0 ] && echo "ALL GREEN" || { echo "FAILURES"; exit 1; }
