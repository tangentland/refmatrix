#!/usr/bin/env bash
# Verify SDD prerequisites for the active feature and emit available artifact paths.
# Usage: check-prerequisites.sh [--json] [--paths-only] [--require-tasks] [--include-tasks]
set -euo pipefail
SCRIPT_DIR="$(CDPATH="" cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

JSON=false; PATHS_ONLY=false; REQUIRE_TASKS=false; INCLUDE_TASKS=false
for a in "$@"; do case "$a" in
    --json) JSON=true ;; --paths-only) PATHS_ONLY=true ;;
    --require-tasks) REQUIRE_TASKS=true ;; --include-tasks) INCLUDE_TASKS=true ;;
esac; done

ROOT="$(get_repo_root)"
FEATURE_DIR="$(current_feature_dir)" || { echo "Error: no active feature (run /ch-specify)" >&2; exit 1; }
SPEC="$FEATURE_DIR/spec.md"; PLAN="$FEATURE_DIR/plan.md"; TASKS="$FEATURE_DIR/tasks.md"

if ! $PATHS_ONLY; then
    [ -f "$SPEC" ] || { echo "Error: spec.md missing" >&2; exit 1; }
    [ -f "$PLAN" ] || { echo "Error: plan.md missing (run /ch-plan)" >&2; exit 1; }
    if $REQUIRE_TASKS && [ ! -f "$TASKS" ]; then echo "Error: tasks.md missing (run /ch-tasks)" >&2; exit 1; fi
fi

kv=(FEATURE_DIR="$FEATURE_DIR" SPEC_FILE="$SPEC" PLAN_FILE="$PLAN"
    CONSTITUTION="$ROOT/workflow/constitution.md")
$INCLUDE_TASKS && kv+=(TASKS_FILE="$TASKS")

if $JSON; then emit_json "${kv[@]}"; else printf '%s\n' "${kv[@]}"; fi
