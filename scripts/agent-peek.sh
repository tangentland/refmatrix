#!/bin/bash
# scripts/agent-peek.sh — print the last lines of an isolated agent's pane, or stop it (L175).
#
#   scripts/agent-peek.sh <slot 1-3> <label> [lines (default 30) | stop]
set -u
SLOT=${1:?slot}; LABEL=${2:?label}; N=${3:-30}
U=rmxtest$SLOT; S="agent-$LABEL"; D="/Users/$U/agents/$LABEL"
T=(sudo -n -H -u "$U" /opt/local/bin/tmux -S "/Users/$U/agents/tmux.sock")
if [ "$N" = stop ]; then "${T[@]}" kill-session -t "$S" && echo "agent-peek: $S stopped"; exit; fi
if ! "${T[@]}" has-session -t "$S" 2>/dev/null; then
  echo "agent-peek: no session $S for $U (finished or stopped)"
  sudo -n test -f "$D/REPORT.md" && echo "REPORT.md present: $D/REPORT.md"; exit 0
fi
"${T[@]}" capture-pane -p -t "$S" -S -400 | grep -v '^ *$' | tail -n "$N"
sudo -n test -f "$D/REPORT.md" && echo "--- REPORT.md present: $D/REPORT.md"
