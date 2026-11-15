#!/bin/bash
# scripts/agent-isolated.sh — run one small-fix agent as an isolated local macOS user (L174).
#
#   scripts/agent-isolated.sh <slot 1-3> <base-ref> <branch> <brief-file> [<label>]
#
# The agent is a headless Claude Code (`claude -p`) running as rmxtest<slot>: its own HOME, no
# write access to tholley's live stores, the dev tree or other clones (the OS enforces what was
# policy), `rmx`/`tldr` on PATH (read-only lookups through scripts/rmx-master), the global
# CLAUDE.md/GMD.md/MEMORY-RULES.md, and no tholley hooks (`--setting-sources user`). It works in a
# FRESH clone ~/agents/<label>/refmatrix of the dev tree at <base-ref>, on <branch>, and must commit
# there; the lead fetches that branch, reads the diff and merges (ORCHESTRATION #task-small).
# Output: ~/agents/<label>/result.json (num_turns, cost, result text) and stderr.log; a summary is
# printed here. One agent per slot at a time (lockf on the slot's ~/agents/slot.lock).
set -u
SLOT=${1:?slot 1-3}; BASE=${2:?base ref}; BRANCH=${3:?branch}; BRIEF=${4:?brief file}
LABEL=${5:-$BRANCH}; LABEL=$(printf '%s' "$LABEL" | tr '/ ' '--')
U=rmxtest$SLOT; DEV=/Users/tholley/claude_tools/refmatrix
case "$SLOT" in 1|2|3) ;; *) echo "agent-isolated: slot must be 1-3" >&2; exit 2;; esac
[ -r "$BRIEF" ] || { echo "agent-isolated: brief $BRIEF unreadable" >&2; exit 2; }
SHA=$(git -C "$DEV" rev-parse --verify "$BASE^{commit}") || { echo "agent-isolated: bad base $BASE" >&2; exit 2; }
sudo -n test -s "/Users/$U/.claude-env" || { echo "agent-isolated: $U has no ~/.claude-env token" >&2; exit 2; }
D="/Users/$U/agents/$LABEL"
sudo -n -H -u "$U" bash -c "mkdir -p ~/agents && rm -rf '$D' && mkdir -p '$D'" || exit 2
sudo -n cp "$BRIEF" "$D/brief.txt" && sudo -n chown "$U:staff" "$D/brief.txt"
START=$(date +%s)
sudo -n -H -u "$U" bash -lc "
  set -u
  exec /usr/bin/lockf -t 0 ~/agents/slot.lock bash -c '
    cd \"$D\" && git clone -q \"$DEV\" refmatrix && cd refmatrix \
      && git checkout -q -b \"$BRANCH\" $SHA && ln -sfn ~/.venv-lane .venv-eval || exit 2
    /Users/tholley/.local/bin/claude -p \"\$(cat \"$D/brief.txt\")\" --setting-sources user \
      --allowedTools \"Bash Read Edit Write Grep Glob\" --output-format json \
      > \"$D/result.json\" 2> \"$D/stderr.log\"
  '
"
RC=$?
[ "$RC" -eq 75 ] && { echo "agent-isolated: slot $SLOT busy" >&2; exit 75; }
echo "agent-isolated: slot=$U rc=$RC wall=$(( $(date +%s) - START ))s clone=$D/refmatrix branch=$BRANCH"
sudo -n python3 - "$D/result.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"agent-isolated: no readable result.json ({e})"); sys.exit(0)
print(f"turns={d.get('num_turns')} cost_usd={d.get('total_cost_usd')} is_error={d.get('is_error')}")
print((d.get('result') or '')[-3000:])
PY
exit "$RC"
