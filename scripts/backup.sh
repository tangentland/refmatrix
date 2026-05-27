#!/usr/bin/env bash
# refmatrix catalog backup.
#
# Uses the 0.3.8+ rotation layout: the daemon maintains catalog.A.duckdb
# and catalog.B.duckdb plus a `.refmatrix/active` marker naming the
# current writer slot. The non-writer slot is a frozen consistent
# snapshot that's safe to copy without contending on the daemon's lock.
#
# This script:
#   1. Refreshes the replica (forces the inactive slot to catch up to
#      writer state, then swaps the marker). After this, the new
#      inactive slot is current as of "now".
#   2. Reads the active marker; backs up the *inactive* slot file.
#   3. Also copies facts.log (the replayable log) and the active marker
#      so a restore can reconstruct the rotation state.
#
# Falls back to legacy catalog.duckdb when the rotation hasn't been
# bootstrapped (pre-0.3.8 stores).
#
# Usage:
#   scripts/backup.sh [dest-dir]
#
# Default dest-dir: ~/refmatrix-backups/<repo-basename>/<timestamp>/
#
# Exit codes:
#   0 on success
#   1 on bad invocation
#   2 if .refmatrix/ not found
#   3 on copy failure

set -euo pipefail

# ---- locate .refmatrix root -------------------------------------------

resolve_refmatrix_root() {
    local cur
    cur="$(pwd -P)"
    while [[ "$cur" != "/" ]]; do
        if [[ -d "$cur/.refmatrix" ]]; then
            echo "$cur/.refmatrix"
            return 0
        fi
        cur="$(dirname "$cur")"
    done
    return 1
}

if ! ROOT="$(resolve_refmatrix_root)"; then
    echo "error: no .refmatrix/ found in cwd ancestry" >&2
    exit 2
fi

REPO_DIR="$(dirname "$ROOT")"
REPO_NAME="$(basename "$REPO_DIR")"

# ---- destination -----------------------------------------------------

DEST_BASE="${1:-$HOME/refmatrix-backups/$REPO_NAME}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$DEST_BASE/$TS"
mkdir -p "$DEST"

# ---- best-effort refresh so the inactive slot is current -------------

# Only meaningful when the daemon is up; rmx replica refresh is a no-op
# if the daemon isn't running.
if rmx daemon status >/dev/null 2>&1; then
    rmx replica refresh >/dev/null 2>&1 || true
fi

# ---- pick the source file --------------------------------------------

ACTIVE_MARKER="$ROOT/active"
LEGACY="$ROOT/catalog.duckdb"

if [[ -f "$ACTIVE_MARKER" ]]; then
    ACTIVE="$(cat "$ACTIVE_MARKER" 2>/dev/null || echo A)"
    if [[ "$ACTIVE" != "A" && "$ACTIVE" != "B" ]]; then
        ACTIVE="A"
    fi
    case "$ACTIVE" in
        A) INACTIVE="B" ;;
        B) INACTIVE="A" ;;
    esac
    SRC="$ROOT/catalog.${INACTIVE}.duckdb"
    LAYOUT="rotation (active=$ACTIVE, backing up frozen=$INACTIVE)"
elif [[ -f "$LEGACY" ]]; then
    SRC="$LEGACY"
    LAYOUT="legacy single-file"
else
    echo "error: no catalog file found in $ROOT" >&2
    exit 3
fi

if [[ ! -f "$SRC" ]]; then
    echo "error: expected catalog file missing: $SRC" >&2
    exit 3
fi

# ---- copy -----------------------------------------------------------

echo "refmatrix backup"
echo "  layout: $LAYOUT"
echo "  source: $SRC"
echo "  dest:   $DEST"

cp -p "$SRC" "$DEST/$(basename "$SRC")"

# Bring along facts.log so a restore can rebuild via rmx rebuild --from-log
# even if the catalog file is corrupted. Also bring the active marker so
# rotation state is preserved.
if [[ -f "$ROOT/facts.log" ]]; then
    cp -p "$ROOT/facts.log" "$DEST/facts.log"
fi
if [[ -f "$ACTIVE_MARKER" ]]; then
    cp -p "$ACTIVE_MARKER" "$DEST/active"
fi

# Summarize.
SIZE_HUMAN="$(du -h "$DEST" | tail -1 | awk '{print $1}')"
echo "  size:   $SIZE_HUMAN"
echo "  done."
