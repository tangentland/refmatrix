#!/bin/bash
# scripts/lane-local.sh — INTERIM isolated test lane on THIS workstation, three slots (local users
# rmxtest1..3, standard accounts, no sudo). Lead-built 2026-11-15 (the user: "we can add three
# rmxtest users locally too").
#
#   scripts/lane-local.sh <repo-dir> <ref> <log-name> <pytest args / test files...>
#
# The first FREE slot (its ~/lane/slot.lock, `lockf -t 0`) fetches <ref> from <repo-dir> (the dev
# tree or a littlebig clone; read access only), checks it out into a fresh worktree, and runs pytest
# as that user: own HOME, own ~/.refmatrix, own launchd domain, own TMPDIR, and NO write access to
# the live stores or their sockets (they belong to tholley, mode 755 / socket 600). Packages: the
# slot's thin ~/.venv-lane over .venv-eval's site-packages (same versions as the local verify runs).
# HF_HUB_OFFLINE=1, PYTHONPATH=<worktree>/src. The log is copied to
# <repo-dir>/workflow/review-output/<log-name>.log. Exit code = pytest's.
# All slots busy → waits (15 s polls) up to LOCAL_LANE_WAIT_S (default 3600), then exit 4.
set -u
REPO=$(cd "${1:?repo dir}" && pwd); REF=${2:?ref}; NAME=${3:?log name}; shift 3
# a log name is one path component: "/" would make mktemp and `git worktree add` fail (bug-273)
NAME=$(printf '%s' "$NAME" | tr '/ ' '--')
[ $# -gt 0 ] || { echo "local-lane: no test files given" >&2; exit 2; }
SHA=$(git -C "$REPO" rev-parse --verify "$REF^{commit}") || { echo "local-lane: bad ref $REF" >&2; exit 2; }
ARGS=$(printf '%q ' "$@")
WAIT=${LOCAL_LANE_WAIT_S:-3600}; waited=0
while :; do
  for n in 1 2 3; do
    U=rmxtest$n
    sudo -n -H -u "$U" bash -c "
      set -u
      mkdir -p ~/lane/runs ~/lane/logs
      exec /usr/bin/lockf -t 0 ~/lane/slot.lock bash -c '
        set -u
        WT=\$(mktemp -d ~/lane/runs/$NAME.XXXX)
        git -C ~/lane/refmatrix fetch -q \"$REPO\" $SHA 2>/dev/null || git -C ~/lane/refmatrix fetch -q \"$REPO\" \"+refs/heads/*:refs/remotes/src/*\"
        git -C ~/lane/refmatrix worktree add -q --detach \"\$WT\" $SHA || { echo \"local-lane: checkout of $SHA failed\"; exit 2; }
        ln -sfn ~/.venv-lane \"\$WT/.venv-eval\"
        cd \"\$WT\"
        LOG=~/lane/logs/$NAME.log
        { echo \"# local-lane slot=\$(whoami) sha=$SHA start=\$(date +%F\ %T) load=\$(sysctl -n vm.loadavg)\"
          HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=\"\$WT/src\" ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider $ARGS
          echo \"exit \$?\"; } > \"\$LOG\" 2>&1
        RC=\$(tail -1 \"\$LOG\" | awk \"{print \\\$2}\")
        cd ~ && git -C ~/lane/refmatrix worktree remove --force \"\$WT\"
        exit \${RC:-1}
      '
    "
    RC=$?
    if [ "$RC" -ne 75 ]; then
      mkdir -p "$REPO/workflow/review-output"
      sudo -n cat "/Users/$U/lane/logs/$NAME.log" > "$REPO/workflow/review-output/$NAME.log" 2>/dev/null \
        || echo "local-lane: could not copy the log back from $U" >&2
      head -1 "$REPO/workflow/review-output/$NAME.log" 2>/dev/null; tail -2 "$REPO/workflow/review-output/$NAME.log" 2>/dev/null
      exit "$RC"
    fi
  done
  [ "$waited" -ge "$WAIT" ] && { echo "local-lane: all 3 slots busy for ${WAIT}s — DID NOT RUN" >&2; exit 4; }
  sleep 15; waited=$((waited+15))
done
