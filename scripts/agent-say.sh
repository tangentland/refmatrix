#!/bin/bash
# scripts/agent-say.sh — send an addendum to a running isolated agent (L175).
#
#   scripts/agent-say.sh <slot 1-3> <label> <text | @file>
#
# Writes the addendum to ~/agents/<label>/addendum-<n>.txt in rmxtest<slot>'s home and types a short
# pointer into the agent's prompt (tmux send-keys; Claude Code queues it if the agent is busy). Long
# text never goes through the keystrokes, only the pointer does.
set -u
SLOT=${1:?slot}; LABEL=${2:?label}; MSG=${3:?text or @file}
U=rmxtest$SLOT; S="agent-$LABEL"; D="/Users/$U/agents/$LABEL"
T=(sudo -n -H -u "$U" /opt/local/bin/tmux -S "/Users/$U/agents/tmux.sock")
"${T[@]}" has-session -t "$S" 2>/dev/null || { echo "agent-say: no session $S for $U" >&2; exit 3; }
N=$(( $(sudo -n ls "$D" 2>/dev/null | grep -c '^addendum-') + 1 )); F="$D/addendum-$N.txt"
if [ "${MSG#@}" != "$MSG" ]; then sudo -n cp "${MSG#@}" "$F"; else printf '%s\n' "$MSG" | sudo -n tee "$F" >/dev/null; fi
sudo -n chown "$U:staff" "$F"
"${T[@]}" send-keys -t "$S" C-u
"${T[@]}" send-keys -t "$S" -l "ADDENDUM $N from the lead: read $F and apply it to your current task."
sleep 1; "${T[@]}" send-keys -t "$S" Enter
echo "agent-say: addendum $N sent to $S ($F)"
