#!/bin/bash
# scripts/lane-status.sh — one line naming what each local isolated user (rmxtest1..3) is doing:
#   lanes 1:<run> 2:- 3:<run> | agents 2:<label>
# A lane is busy while `lockf` holds ~/lane/slot.lock (scripts/lane-local.sh); its run name is
# the `runs/<log-name>.XXXX` work dir. An agent is a live `tmux -S ~/agents/tmux.sock` session
# `agent-<label>` (scripts/agent-isolated.sh). Read from `ps` only (no sudo, ~60 ms), so the
# status line can call it on every refresh (user ask, 2026-11-25). Mac mini lanes are not shown:
# an ssh per refresh is too slow for a status line.
ps -axo user=,command= | awk '
$1 ~ /^rmxtest[0-9]$/ {
  n = substr($1, 8, 1)
  if ($0 ~ /lockf -t 0 .*slot\.lock/ && match($0, /runs\/[A-Za-z0-9._-]+\./))
    lane[n] = substr($0, RSTART + 5, RLENGTH - 6)
  if ($0 ~ /tmux -S .*new-session/ && match($0, /-s agent-[A-Za-z0-9._-]+/))
    ag[n] = substr($0, RSTART + 9, RLENGTH - 9)
}
END {
  for (i = 1; i <= 3; i++) printf "%s%d:%s", (i > 1 ? " " : "lanes "), i, (i in lane ? lane[i] : "-")
  printf " | agents"; any = 0
  for (i = 1; i <= 3; i++) if (i in ag) { printf " %d:%s", i, ag[i]; any = 1 }
  if (!any) printf " -"
  print ""
}'
