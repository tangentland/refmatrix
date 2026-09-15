#!/usr/bin/env bash
# Lint a Claude memory tree with the canonical project scope.
#
# Memories live at:
#   ~/.claude/projects/<encoded-path>/memory/
#
# Many memory `[[ref]]` links resolve into the matching project tree's
# docs/ dir (or CLAUDE.md). Linting the memory dir alone surfaces those
# as false dangling-doc errors. This wrapper:
#   1) lints the memory dir as the target,
#   2) auto-resolves the matching project root from the encoded path,
#   3) passes that root's CLAUDE.md + docs/ as --scope so cross-tree
#      refs resolve cleanly.
#
# Usage:
#   tools/gmd/lint-memory.sh <memory_dir>
#   tools/gmd/lint-memory.sh ~/.claude/projects/<encoded-project-dir>/memory
#
# If the project root can't be decoded (e.g. memory tree isn't under
# the canonical ~/.claude/projects/ path) the scope is omitted and the
# lint runs against the memory dir alone.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <memory_dir>" >&2
  exit 2
fi

MEMORY_DIR="$1"; shift
# Resolve the linter next to this script (bundled under tools/gmd/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINTER="$SCRIPT_DIR/lint.py"

if [[ ! -d "$MEMORY_DIR" ]]; then
  echo "lint-memory: not a directory: $MEMORY_DIR" >&2
  exit 2
fi

# Decode the project path from the encoded project-dir name.
# `~/.claude/projects/-Users-me-code-myproject/memory`
# -> project root = `/Users/me/code/myproject`
PROJ_DIR=""
PARENT="$(dirname "$MEMORY_DIR")"
PARENT_BASE="$(basename "$PARENT")"
if [[ "$PARENT_BASE" == -* ]]; then
  # Strip leading "-" then replace "-" with "/" to recover the path.
  CANDIDATE="/${PARENT_BASE#-}"
  CANDIDATE="${CANDIDATE//-//}"
  if [[ -d "$CANDIDATE" ]]; then
    PROJ_DIR="$CANDIDATE"
  fi
fi

ARGS=("$MEMORY_DIR")
if [[ -n "$PROJ_DIR" ]]; then
  if [[ -f "$PROJ_DIR/CLAUDE.md" ]]; then
    ARGS+=("--scope" "$PROJ_DIR/CLAUDE.md")
  fi
  if [[ -d "$PROJ_DIR/docs" ]]; then
    ARGS+=("--scope" "$PROJ_DIR/docs")
  fi
fi

exec python3 "$LINTER" "${ARGS[@]}" "$@"
