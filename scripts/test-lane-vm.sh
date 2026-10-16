#!/usr/bin/env bash
# Task 23.0 R8: the tier-2 lane -- the full suite at one commit inside a throwaway macOS VM
# (Tart, Apple's Virtualization framework).
#
# Why (d9x, 2026-10-14): tier 1 (a separate user) still shares the kernel, /tmp, the port
# namespace and has no gui/<uid> launchd domain. A VM shares nothing writable with the host; it
# runs before every deploy, on a tier-1/tier-0 disagreement, and runs the gui/-only tests tier 1
# lists. Host (d9aa): the M1 Mac mini once it runs (`--host <ssh-target>`), the workstation
# until then.
#
# Usage: scripts/test-lane-vm.sh <sha> [--host <ssh-target>]
# Setup is operator work: install Tart (a new dependency -- proposed and approved, never
# installed by an agent) and build the golden image `rmx-golden` (auto-login test user, Python
# 3.14, ~/.venv-lane, the offline model cache, SSH). Pulling the base image is the one explicit
# network step; nothing at run time reaches the network.
# Licence limit: at most two macOS VMs per Mac at once -- this script refuses a third BEFORE it
# clones one.
set -euo pipefail

GOLDEN="${RMX_LANE_GOLDEN:-rmx-golden}"
VM_USER="${RMX_LANE_VM_USER:-admin}"
MAX_MACOS_VMS=2
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/workflow/review-output"
PY="${RMX_PYTEST_PY:-$REPO/.venv-eval/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"   # a clone has no .venv-eval of its own

usage() { echo "usage: $(basename "$0") <sha> [--host <ssh-target>]  (a commit sha is required)" >&2; }

SHA_ARG=""
HOST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:?--host needs an ssh target}"; shift 2 ;;
    -*) usage; exit 2 ;;
    *) [ -z "$SHA_ARG" ] || { usage; exit 2; }; SHA_ARG="$1"; shift ;;
  esac
done
[ -n "$SHA_ARG" ] || { usage; exit 2; }
SHA="$(git -C "$REPO" rev-parse --verify --quiet "$SHA_ARG^{commit}")" || {
  echo "test-lane-vm: '$SHA_ARG' is not a commit sha of $REPO" >&2
  exit 2
}
VM="rmx-run-${SHA:0:12}"

# Every tart / VM command goes through these, so --host changes nothing else.
on_host() { if [ -n "$HOST" ]; then ssh "$HOST" "$@"; else "$@"; fi; }
T() { on_host tart "$@"; }
vm_ssh() {
  local ip="$1"; shift
  if [ -n "$HOST" ]; then ssh -J "$HOST" "$VM_USER@$ip" "$@"; else ssh "$VM_USER@$ip" "$@"; fi
}
vm_scp_from() {
  local ip="$1" src="$2" dst="$3"
  if [ -n "$HOST" ]; then scp -J "$HOST" "$VM_USER@$ip:$src" "$dst"; else scp "$VM_USER@$ip:$src" "$dst"; fi
}

if ! on_host sh -c 'command -v tart' >/dev/null; then
  echo "test-lane-vm: tart is not installed${HOST:+ on $HOST}. It is a new dependency: propose" >&2
  echo "  it for approval, then the operator installs it and builds '$GOLDEN' (see this header)." >&2
  exit 3
fi

# The licence limit, checked BEFORE any clone.
RUNNING="$(T list --format json | "$PY" -c '
import json, sys
vms = json.load(sys.stdin)
print(sum(1 for v in vms if str(v.get("State", "")).lower() == "running"
          and str(v.get("OS", "darwin")).lower() == "darwin"))')"
if [ "$RUNNING" -ge "$MAX_MACOS_VMS" ]; then
  echo "test-lane-vm: REFUSING: $RUNNING macOS VMs already running; Apple's licence allows two" \
       "at once and this lane would start a third. Stop one (tart stop <name>) and retry." >&2
  exit 4
fi

mkdir -p "$OUT"
LOG="$OUT/pytest-lane-vm-$SHA.log"
RUNS="$OUT/lane-vm-runs.jsonl"
HELPER="$REPO/tests/sandbox_site/rmx_sandbox.py"

# A bare clone of the commit, staged on the host and shared READ-ONLY into the VM.
STAGE="$(mktemp -d /tmp/rmx-lane-vm.XXXXXX)"
git clone --bare --no-hardlinks -q "$REPO" "$STAGE/repo.git"
HOST_STAGE="$STAGE"
if [ -n "$HOST" ]; then
  HOST_STAGE="$(ssh "$HOST" mktemp -d /tmp/rmx-lane-vm.XXXXXX)"
  rsync -a "$STAGE/repo.git" "$HOST:$HOST_STAGE/"
fi

RUN_PID=""
cleanup() {
  set +e
  T stop "$VM" >/dev/null 2>&1
  [ -n "$RUN_PID" ] && wait "$RUN_PID" 2>/dev/null
  T delete "$VM"
  [ -n "$HOST" ] && ssh "$HOST" rm -rf "$HOST_STAGE"
  rm -rf "$STAGE"
}
trap cleanup EXIT

# AC-8(c): the host's live logs, judged by content after the run (rmx_sandbox.py's check).
TAG="$("$PY" -c 'import secrets; print(secrets.token_hex(3))')"
SNAP="$(mktemp /tmp/rmx-lane-vm-snap.XXXXXX)"
TOUCHES="$OUT/live-socket-touches.log"
TOUCHES_SIZE=0
[ -f "$TOUCHES" ] && TOUCHES_SIZE="$(wc -c < "$TOUCHES" | tr -d ' ')"
"$PY" "$HELPER" snapshot "$SNAP" "$HOME/.refmatrix/query.log" "$HOME/.refmatrix/facts.log" \
  "$REPO/.refmatrix/query.log" "$REPO/.refmatrix/facts.log"

T0="$(date +%s)"
T clone "$GOLDEN" "$VM"
T run --no-graphics --dir="lane:$HOST_STAGE:ro" "$VM" >/dev/null 2>&1 &
RUN_PID=$!
IP=""
for _ in $(seq 1 120); do
  IP="$(T ip "$VM" 2>/dev/null)" && [ -n "$IP" ] && vm_ssh "$IP" true 2>/dev/null && break
  IP=""
  sleep 2
done
[ -n "$IP" ] || { echo "test-lane-vm: $VM never answered ssh within 240 s" >&2; exit 5; }
T1="$(date +%s)"

set +e
vm_ssh "$IP" bash -lc "'
  set -e
  git clone --no-hardlinks -q \"/Volumes/My Shared Files/lane/repo.git\" ~/lane-$SHA
  cd ~/lane-$SHA && git checkout -q --detach $SHA && mkdir -p workflow/review-output
  HF_HUB_OFFLINE=1 RMX_SANDBOX_TAG=$TAG PYTHONPATH=\$HOME/lane-$SHA/src \
    ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider > ~/pytest-lane-vm-$SHA.log 2>&1
'"
RC=$?
vm_scp_from "$IP" "pytest-lane-vm-$SHA.log" "$LOG"
SCP_RC=$?
set -e
T2="$(date +%s)"
DISK="$(T list --format json | "$PY" -c '
import json, sys
print(next((v.get("Size") for v in json.load(sys.stdin) if v.get("Name") == sys.argv[1]), None))' "$VM")"

cleanup
trap - EXIT
if T list --format json | "$PY" -c '
import json, sys
sys.exit(0 if any(str(v.get("Name", "")).startswith("rmx-run-") for v in json.load(sys.stdin)) else 1)'; then
  echo "test-lane-vm: an rmx-run-* VM survived tart delete (AC-8(c))" >&2
  exit 6
fi
set +e
"$PY" "$HELPER" check "$SNAP" "$TAG" "$TOUCHES" "$TOUCHES_SIZE"
LEAK_RC=$?
set -e
rm -f "$SNAP"
printf '{"sha": "%s", "host": "%s", "boot_s": %s, "run_s": %s, "disk_gb": %s, "rc": %s}\n' \
  "$SHA" "${HOST:-local}" "$((T1 - T0))" "$((T2 - T1))" "${DISK:-null}" "$RC" >> "$RUNS"
echo "test-lane-vm: suite exit $RC (log copy exit $SCP_RC), live-log check exit $LEAK_RC; $LOG"
[ "$SCP_RC" -eq 0 ] || exit 7
[ "$LEAK_RC" -eq 0 ] || exit 6
exit "$RC"
