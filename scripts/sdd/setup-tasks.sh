#!/usr/bin/env bash
# Prepare tasks.md for the active feature. Emits its path (seeded from the tasks template).
# Usage: setup-tasks.sh [--json]
set -euo pipefail
SCRIPT_DIR="$(CDPATH="" cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
JSON=false; [ "${1:-}" = "--json" ] && JSON=true

ROOT="$(get_repo_root)"
FEATURE_DIR="$(current_feature_dir)" || { echo "Error: no active feature" >&2; exit 1; }
PLAN="$FEATURE_DIR/plan.md"
TASKS="$FEATURE_DIR/tasks.md"
[ -f "$PLAN" ] || { echo "Error: plan.md missing (run /ch-plan first)" >&2; exit 1; }

if [ ! -f "$TASKS" ]; then
    TPL="$(resolve_template tasks "$ROOT" || true)"
    [ -n "$TPL" ] && cp "$TPL" "$TASKS" || touch "$TASKS"
fi

if $JSON; then
    emit_json FEATURE_DIR="$FEATURE_DIR" PLAN_FILE="$PLAN" TASKS_FILE="$TASKS"
else
    echo "FEATURE_DIR: $FEATURE_DIR"; echo "TASKS_FILE: $TASKS"
fi
