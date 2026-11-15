#!/bin/bash
# scripts/lane-mini.sh — INTERIM macOS test lane on the Mac mini, until T0.9 (d) ships
# scripts/test-lane-host.sh. Lead-built 2026-11-15 ("setup the macmini to run test now"; the
# user approved three isolated test users).
#
#   scripts/lane-mini.sh <repo-dir> <ref> <log-name> <pytest args / test files...>
#
# Slots: rmxtest1..2 on the mini (rmxtest3 is the canary, L172), standard users (no sudo), each with its own home, launchd
# domain, clone (~/lane/refmatrix) and thin venv (~/.venv-lane over the shared pinned venv in
# /Users/Shared/rmx-lane/venv). <ref> is pushed once (as the setup account rmxtest) to the shared
# mirror /Users/Shared/rmx-lane/refmatrix.git as refs/lane/<log-name>; the first FREE slot (its
# ~/lane/slot.lock, taken with `lockf -t 0`) checks it out into a fresh worktree, runs pytest with
# HF_HUB_OFFLINE=1 and PYTHONPATH=<worktree>/src, then removes the worktree. The log comes back to
# <repo-dir>/workflow/review-output/<log-name>.log. Exit code = pytest's.
# Fails loud: unreachable mini → exit 3 "DID NOT RUN"; all slots busy → waits, polling every 15 s,
# up to MINI_LANE_WAIT_S (default 3600) then exit 4. Never falls back to a local run.
set -u
REPO=${1:?repo dir}; REF=${2:?ref}; NAME=${3:?log name}; shift 3
# a log name is one path component: "/" would make mktemp and `git worktree add` fail (bug-273)
NAME=$(printf '%s' "$NAME" | tr '/ ' '--')
[ $# -gt 0 ] || { echo "mini-lane: no test files given" >&2; exit 2; }
SSH=(ssh -o BatchMode=yes -o ForwardX11=no -o ConnectTimeout=10)
SHA=$(git -C "$REPO" rev-parse --verify "$REF^{commit}") || { echo "mini-lane: bad ref $REF" >&2; exit 2; }
"${SSH[@]}" rmxtest@mini true 2>/dev/null || { echo "mini-lane: mini unreachable — DID NOT RUN" >&2; exit 3; }
GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ForwardX11=no" \
  git -C "$REPO" push -q -f rmxtest@mini:/Users/Shared/rmx-lane/refmatrix.git "$SHA:refs/lane/$NAME" 2>&1 \
  | grep -v 'X11\|cargo' >&2
ARGS=$(printf '%q ' "$@")
WAIT=${MINI_LANE_WAIT_S:-3600}; waited=0
while :; do
  for n in 1 2; do   # rmxtest3 is the latest-versions canary (L172), never a verify slot
    U=rmxtest$n
    "${SSH[@]}" "$U@mini" "bash -s" <<EOF 2>&1 | grep -v 'X11 forwarding\|cargo/env'
set -u
mkdir -p ~/lane/runs ~/lane/logs
/usr/bin/lockf -t 0 ~/lane/slot.lock bash -c '
  set -u
  WT=\$(mktemp -d ~/lane/runs/$NAME.XXXX)
  git -C ~/lane/refmatrix fetch -q /Users/Shared/rmx-lane/refmatrix.git "refs/lane/$NAME" \
    && git -C ~/lane/refmatrix worktree add -q --detach "\$WT" $SHA || { echo "mini-lane: checkout failed"; exit 2; }
  ln -sfn ~/.venv-lane "\$WT/.venv-eval"
  cd "\$WT"
  LOG=~/lane/logs/$NAME.log
  { echo "# mini-lane slot=\$(whoami) sha=$SHA host=\$(hostname) macOS \$(sw_vers -productVersion) py=\$(~/.venv-lane/bin/python -V 2>&1) start=\$(date "+%F %T") load=\$(sysctl -n vm.loadavg)"
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH="\$WT/src" ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider $ARGS
    echo "exit \$?"; } > "\$LOG" 2>&1
  RC=\$(tail -1 "\$LOG" | awk "{print \\\$2}")
  cd ~ && git -C ~/lane/refmatrix worktree remove --force "\$WT"
  exit \${RC:-1}
'
EOF
    RC=${PIPESTATUS[0]}
    if [ "$RC" -ne 75 ]; then   # 75 = EX_TEMPFAIL from lockf -t 0: slot busy
      mkdir -p "$REPO/workflow/review-output"
      scp -q -o ForwardX11=no "$U@mini:lane/logs/$NAME.log" "$REPO/workflow/review-output/$NAME.log" 2>/dev/null \
        || echo "mini-lane: could not copy the log back from $U" >&2
      head -1 "$REPO/workflow/review-output/$NAME.log" 2>/dev/null; tail -2 "$REPO/workflow/review-output/$NAME.log" 2>/dev/null
      exit "$RC"
    fi
  done
  [ "$waited" -ge "$WAIT" ] && { echo "mini-lane: both locked slots busy for ${WAIT}s — DID NOT RUN" >&2; exit 4; }
  sleep 15; waited=$((waited+15))
done
