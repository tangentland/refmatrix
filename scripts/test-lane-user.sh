#!/usr/bin/env bash
# Task 23.0 R7: the tier-1 lane -- the full suite at one commit, as the separate macOS user
# `rmxtest`.
#
# Why (d9w/d9x, 2026-10-14): the in-process sandbox (R1-R4) cannot remove what a run shares with
# the developer's account -- the same `~`, Keychain, launchd domain and file permissions. Run as
# another user, a test that escapes the sandbox meets a permission error instead of the live
# store. Tier 1 gates every merge to master.
#
# Usage:
#   scripts/test-lane-user.sh <sha>       run the lane at <sha> (a commit of this repo)
#   scripts/test-lane-user.sh --setup     print the one-time operator setup; runs nothing
#   (internal) --lane check PATH... / --lane run <stage> <sha>   -- the half that runs AS rmxtest
#
# Setup is operator work (needs admin). This script PRINTS the commands and refuses to run them.
# Known limit: `sudo -u` creates no gui/<uid> launchd domain; tests that bootstrap into gui/
# fail here, are LISTED (by id, with their error) in
# workflow/review-output/lane-user-gui-only-<sha>.txt, and run in tier 2 -- never skipped.
set -euo pipefail

LANE_USER="${RMX_LANE_USER:-rmxtest}"
INSTALLED="/usr/local/libexec/rmx/test-lane-user.sh"
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

usage() {
  echo "usage: $(basename "$0") <sha>   (a commit sha of this repo is required)" >&2
  echo "       $(basename "$0") --setup  (print the one-time operator setup)" >&2
}

print_setup() {
  local repo="$1"
  cat <<EOF
# One-time setup for the tier-1 lane (task 23.0 R7). Run these YOURSELF, as an admin;
# this script never runs them. Record the date in docs/INTEGRATION.md.
sudo sysadminctl -addUser $LANE_USER -fullName "refmatrix test lane" -password -
sudo mkdir -p /usr/local/libexec/rmx
sudo install -o root -g wheel -m 0755 "$repo/scripts/test-lane-user.sh" $INSTALLED
echo "$(id -un) ALL=($LANE_USER) NOPASSWD: $INSTALLED" | sudo tee /etc/sudoers.d/rmx-test-lane
sudo chmod 0440 /etc/sudoers.d/rmx-test-lane && sudo visudo -cf /etc/sudoers.d/rmx-test-lane
# the lane venv, built from pyproject.toml, as $LANE_USER:
sudo -u $LANE_USER -H bash -lc 'python3.14 -m venv ~/.venv-lane && ~/.venv-lane/bin/pip install -e "<a lane clone>[dev]"'
# a READ-ONLY copy of the model cache, loaded offline (HF_HUB_OFFLINE=1):
sudo rsync -a "\$HOME/.cache/huggingface/" ~$LANE_USER/.cache/huggingface/
sudo chown -R root:staff ~$LANE_USER/.cache/huggingface && sudo chmod -R a+rX,go-w ~$LANE_USER/.cache/huggingface
# re-install $INSTALLED after every change to scripts/test-lane-user.sh (the lane refuses a stale copy)
EOF
}

# ---- the half that runs AS the lane user (via sudo, from the installed root-owned copy) ----

lane_check() {
  # Every path given must be UNREADABLE by this user.
  local bad=0
  for p in "$@"; do
    if [ -r "$p" ]; then
      echo "lane precondition FAILED: $p is readable by $(id -un)" >&2
      bad=1
    fi
  done
  return $bad
}

lane_run() {
  local stage="$1" sha="$2" tag="$3"
  local lane="$HOME/lane/$sha"
  if [ -e "$lane" ]; then
    echo "lane: $lane already exists; remove it or pick another sha" >&2
    return 2
  fi
  mkdir -p "$HOME/lane"
  git clone --no-hardlinks -q "$stage/repo.git" "$lane"
  git -C "$lane" checkout -q --detach "$sha"
  mkdir -p "$lane/workflow/review-output"
  cd "$lane"
  HF_HUB_OFFLINE=1 RMX_SANDBOX_TAG="$tag" PYTHONPATH="$lane/src" \
    "$HOME/.venv-lane/bin/python" -m pytest -q -p no:cacheprovider 2>&1 \
    | tee "$lane/workflow/review-output/pytest-lane-user-$sha.log"
  return "${PIPESTATUS[0]}"
}

if [ "${1:-}" = "--lane" ]; then
  shift
  case "${1:-}" in
    check) shift; lane_check "$@"; exit $? ;;
    run) shift; lane_run "${1:?stage}" "${2:?sha}" "${3:?tag}"; exit $? ;;
    *) echo "lane: unknown internal mode ${1:-}" >&2; exit 2 ;;
  esac
fi

# ---- the developer's half --------------------------------------------------------------------

REPO="$(cd "$(dirname "$SELF")/.." && pwd)"
if [ "${1:-}" = "--setup" ]; then
  print_setup "$REPO"
  exit 0
fi
if [ $# -ne 1 ] || [ -z "${1:-}" ] || [ "${1#-}" != "$1" ]; then
  usage
  exit 2
fi
SHA="$(git -C "$REPO" rev-parse --verify --quiet "$1^{commit}")" || {
  echo "test-lane-user: '$1' is not a commit sha of $REPO" >&2
  exit 2
}

if ! id "$LANE_USER" >/dev/null 2>&1; then
  echo "test-lane-user: the lane user '$LANE_USER' does not exist. Operator setup:" >&2
  print_setup "$REPO" >&2
  exit 3
fi
if [ ! -x "$INSTALLED" ] || ! cmp -s "$INSTALLED" "$SELF"; then
  echo "test-lane-user: $INSTALLED is missing or differs from $SELF; re-install it:" >&2
  echo "  sudo install -o root -g wheel -m 0755 '$SELF' $INSTALLED" >&2
  exit 3
fi
as_lane() { sudo -n -u "$LANE_USER" -H "$INSTALLED" --lane "$@"; }

# Preconditions (R7): nothing live is readable by the lane user, and it holds no hub port.
DENIED=("$HOME/.refmatrix" "$HOME/Library/LaunchAgents" "$REPO/.refmatrix")
for plist in "$HOME"/Library/LaunchAgents/com.refmatrix.daemon.*.plist; do
  [ -e "$plist" ] || continue
  root="$(/usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:REFMATRIX_ROOT' "$plist")"
  DENIED+=("$root")
done
echo "test-lane-user: checking ${#DENIED[@]} live paths are unreadable by $LANE_USER"
as_lane check "${DENIED[@]}" || {
  echo "test-lane-user: REFUSING to run -- a live path is readable by $LANE_USER" >&2
  exit 4
}
if lsof -nP -a -u "$LANE_USER" -iTCP:7777 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "test-lane-user: REFUSING to run -- a $LANE_USER process holds TCP 7777" >&2
  exit 4
fi

# The lane reads a bare clone staged under /tmp, never this tree.
STAGE="$(mktemp -d /tmp/rmx-lane-stage.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
git clone --bare --no-hardlinks -q "$REPO" "$STAGE/repo.git"
chmod -R a+rX "$STAGE"

OUT="$REPO/workflow/review-output"
mkdir -p "$OUT"
LOG="$OUT/pytest-lane-user-$SHA.log"
# AC-7(c): the developer's four live logs, judged by content after the run (the same check
# scripts/sandbox-proof.sh runs; the logic lives once in rmx_sandbox.py).
PY="${RMX_PYTEST_PY:-$REPO/.venv-eval/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"   # a clone has no .venv-eval of its own
HELPER="$REPO/tests/sandbox_site/rmx_sandbox.py"
TAG="$("$PY" -c 'import secrets; print(secrets.token_hex(3))')"
SNAP="$STAGE/live-logs.json"
TOUCHES="$OUT/live-socket-touches.log"
TOUCHES_SIZE=0
[ -f "$TOUCHES" ] && TOUCHES_SIZE="$(wc -c < "$TOUCHES" | tr -d ' ')"
"$PY" "$HELPER" snapshot "$SNAP" "$HOME/.refmatrix/query.log" "$HOME/.refmatrix/facts.log" \
  "$REPO/.refmatrix/query.log" "$REPO/.refmatrix/facts.log"
echo "test-lane-user: running the suite at $SHA as $LANE_USER (tag $TAG) -> $LOG"
set +e
as_lane run "$STAGE" "$SHA" "$TAG" > "$LOG" 2>&1
RC=$?
"$PY" "$HELPER" check "$SNAP" "$TAG" "$TOUCHES" "$TOUCHES_SIZE"
LEAK_RC=$?
set -e

# AC-7(b): the final tally is the evidence a shrunk collection would hide; compare it with the
# developer run at the same sha. grep exit 1 = no such line, which is itself reported.
set +e
TALLY="$(grep -E "[0-9]+ (passed|failed)" "$LOG" | tail -1)"
GUI="$OUT/lane-user-gui-only-$SHA.txt"
grep -E "^(FAILED|ERROR) " "$LOG" | grep -E "gui/[0-9]+|Bootstrap failed|Domain does not support" \
  > "$GUI"
GREP_RC=$?
set -e
[ "$GREP_RC" -le 1 ] || { echo "test-lane-user: grep over $LOG failed ($GREP_RC)" >&2; exit 5; }
echo "test-lane-user: tally: ${TALLY:-<no pytest tally line in the log>}"
echo "test-lane-user: $(wc -l < "$GUI" | tr -d ' ') gui/-only test(s) listed in $GUI (run them in tier 2)"
echo "test-lane-user: suite exit $RC; live-log content check exit $LEAK_RC; log $LOG"
[ "$LEAK_RC" -eq 0 ] || exit 6
exit "$RC"
