#!/usr/bin/env bash
# PreToolUse (Bash) — block test-runner invocations whose output is not captured to a file.
# Rule (CLAUDE.md): all test runs tee/redirect to a log (e.g. /test-output/ or /tmp/...); never
# inline. Piping to tail/head/wc for a summary is allowed. Project-neutral.
set -euo pipefail
DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; . "$DIR/_common.sh"

CMD="$(cat | hook_json_field tool_input.command)"
[ -z "$CMD" ] && exit 0

# Is this actually invoking a test runner (not merely mentioning one)?
echo "$CMD" | grep -qE '\bpytest\b|\bvitest\b|playwright test|\bnpm (run )?test\b|go test\b|cargo test\b' || exit 0
# Exclude commands that merely reference a runner in a non-executing context.
echo "$CMD" | grep -qE '^\s*(echo|printf|cat|grep|git|kill|pkill|pgrep|wc|ls|find)\b' && exit 0

# Allow when output is captured or summarized.
case "$CMD" in
  *"| tee "*|*"| tee "*|*"> "*|*">"*|*"2>&1 |"*|*"| tail"*|*"| head"*|*"| wc"*) exit 0 ;;
esac

{
  echo "BLOCKED: capture test output to a file (do not run tests inline)."
  echo "  tee:      <test-cmd> 2>&1 | tee /test-output/test-\$(date +%s).log"
  echo "  redirect: <test-cmd> > /tmp/test-\$(date +%s).log 2>&1"
  echo "  summary:  <test-cmd> 2>&1 | tail -40"
} >&2
exit 2
