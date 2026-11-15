#!/bin/bash
# scripts/agent-isolated.sh — start one small-fix agent as an isolated local macOS user (L174, L175).
#
#   scripts/agent-isolated.sh <slot 1-3> <base-ref> <branch> <brief-file> [<label>]
#
# The agent is an INTERACTIVE Claude Code running in a detached tmux session
# (`agent-<label>`; tmux (MacPorts /opt/local/bin/tmux) with its socket at ~/agents/tmux.sock in the agent's own home;
# the system screen 4.00 fails silently under `sudo -u` (its socket lands in the caller's TMPDIR).) as rmxtest<slot>: its own HOME, no write access to tholley's live stores, the
# dev tree or other clones (the OS enforces what was policy), `rmx`/`tldr` on PATH, the global
# CLAUDE.md/GMD.md/MEMORY-RULES.md, no tholley hooks (`--setting-sources user`). It works in a
# fresh clone ~/agents/<label>/refmatrix at <base-ref> on <branch>, and must commit there and write
# ~/agents/<label>/REPORT.md when done. Interactive (not `claude -p`) so the lead can feed
# addendums mid-run with scripts/agent-say.sh, which types into the agent's prompt
# (`tmux send-keys`; Claude Code queues input typed while it works). Read its screen with
# scripts/agent-peek.sh. The hub-bus channel push did not reach 2.1.325 (bug-275), hence tmux.
# Long text always goes through a file plus a short typed pointer.
set -u
SLOT=${1:?slot 1-3}; BASE=${2:?base ref}; BRANCH=${3:?branch}; BRIEF=${4:?brief file}
LABEL=${5:-$BRANCH}; LABEL=$(printf '%s' "$LABEL" | tr '/ ' '--')
U=rmxtest$SLOT; DEV=/Users/tholley/claude_tools/refmatrix; S="agent-$LABEL"
T=(sudo -n -H -u "$U" /opt/local/bin/tmux -S "/Users/$U/agents/tmux.sock")
case "$SLOT" in 1|2|3) ;; *) echo "agent-isolated: slot must be 1-3" >&2; exit 2;; esac
[ -r "$BRIEF" ] || { echo "agent-isolated: brief $BRIEF unreadable" >&2; exit 2; }
SHA=$(git -C "$DEV" rev-parse --verify "$BASE^{commit}") || { echo "agent-isolated: bad base $BASE" >&2; exit 2; }
sudo -n test -s "/Users/$U/.claude-env" || { echo "agent-isolated: $U has no ~/.claude-env token" >&2; exit 2; }
sudo -n -H -u "$U" mkdir -p "/Users/$U/agents"
if "${T[@]}" ls 2>/dev/null | grep -q '^agent-'; then
  echo "agent-isolated: $U already runs an agent ($("${T[@]}" ls 2>/dev/null | cut -d: -f1 | head -1)); one per slot" >&2; exit 75
fi
D="/Users/$U/agents/$LABEL"
sudo -n -H -u "$U" bash -lc "rm -rf '$D' && mkdir -p '$D' && cd '$D' && git clone -q '$DEV' refmatrix \
  && cd refmatrix && git checkout -q -b '$BRANCH' $SHA && ln -sfn ~/.venv-lane .venv-eval" || exit 2
sudo -n cp "$BRIEF" "$D/brief.txt" && sudo -n chown "$U:staff" "$D/brief.txt"
"${T[@]}" new-session -d -s "$S" -x 160 -y 50 "bash -lc \"cd '$D/refmatrix' && exec /Users/tholley/.local/bin/claude \
  --setting-sources user --permission-mode acceptEdits --allowedTools 'Bash Read Edit Write Grep Glob'\"" \
  || { echo "agent-isolated: tmux session failed to start" >&2; exit 2; }
peek() { "${T[@]}" capture-pane -p -t "$S" 2>/dev/null; }
# Get past the start-up prompts (folder trust, tips) until the input box is ready, up to ~60 s.
for i in $(seq 1 30); do
  sleep 2; SCR=$(peek)
  # The folder-trust prompt defaults to "No, exit": choose "Yes, I trust this folder" explicitly.
  if printf '%s' "$SCR" | LC_ALL=C grep -q 'Yes, I trust this folder'; then
    "${T[@]}" send-keys -t "$S" Down; sleep 0.5; "${T[@]}" send-keys -t "$S" Enter; continue
  fi
  if printf '%s' "$SCR" | LC_ALL=C grep -q 'Enter to confirm'; then
    "${T[@]}" send-keys -t "$S" Enter; continue
  fi
  printf '%s' "$SCR" | LC_ALL=C grep -qE 'Try "|shift\+tab|for shortcuts' && break
done
"${T[@]}" send-keys -t "$S" -l "Read the file $D/brief.txt and do what it says. When you are done, write $D/REPORT.md with your report."
sleep 1; "${T[@]}" send-keys -t "$S" Enter
echo "agent-isolated: started $S as $U in $D/refmatrix ($BRANCH @ ${SHA:0:8}); peek: scripts/agent-peek.sh $SLOT $LABEL; say: scripts/agent-say.sh $SLOT $LABEL <text|file>; done when $D/REPORT.md exists"
