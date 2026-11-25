#!/usr/bin/env bash
# run.sh P<n> [--save]  — rebuild probe P<n>'s project in a fresh dir under $WORKROOT, run its
# session(s), print the observation. --save copies the evidence to P<n>/evidence/<version>-<mode>.jsonl.
# `run.sh cost` runs the prefilter baseline. Headless probes only; P1b and P2 are interactive
# (lead): `run.sh P1b` / `run.sh P2` build the project and print the steps. Canary on upgrade.
set -u
HERE=$(cd "$(dirname "$0")" && pwd); . "$HERE/common/lib.sh"
which=${1:?usage: run.sh P1|P1b|P2|...|P11|cost [--save]}; save=${2:-}
if [ "$which" = cost ]; then exec "${RMX_DEV_PYTHON:-$HOME/.venv-lane/bin/python}" "$HERE/cost/baseline.py"; fi
dir="$HERE/$which"; [ -f "$dir/probe.sh" ] || { echo "no probe $which" >&2; exit 2; }
case $which in P1b|P2) MODE="interactive (lead): build + steps only";; esac
echo "== $which  claude $CC_VERSION  mode: ${MODE:-headless (claude -p)}"
. "$dir/probe.sh"; run_probe
echo "-- hook evidence (key paths, lengths and hashes only):"; summ
if [ "$save" = --save ]; then mkdir -p "$dir/evidence"; cp "$PROBE_EV" "$dir/evidence/$CC_VERSION-${EVMODE:-headless}.jsonl"; echo "saved"; fi
echo "project: $P"
