#!/usr/bin/env bash
# Prepare planning artifacts for the active feature. Emits paths for plan.md + design docs.
# Usage: setup-plan.sh [--json]
set -euo pipefail
SCRIPT_DIR="$(CDPATH="" cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
JSON=false; [ "${1:-}" = "--json" ] && JSON=true

ROOT="$(get_repo_root)"
FEATURE_DIR="$(current_feature_dir)" || { echo "Error: no active feature (run /ch-specify first)" >&2; exit 1; }
SPEC="$FEATURE_DIR/spec.md"
PLAN="$FEATURE_DIR/plan.md"
[ -f "$SPEC" ] || { echo "Error: spec.md missing in $FEATURE_DIR" >&2; exit 1; }

if [ ! -f "$PLAN" ]; then
    TPL="$(resolve_template plan "$ROOT" || true)"
    [ -n "$TPL" ] && cp "$TPL" "$PLAN" || touch "$PLAN"
fi
CONSTITUTION="$ROOT/workflow/constitution.md"

if $JSON; then
    emit_json FEATURE_DIR="$FEATURE_DIR" SPEC_FILE="$SPEC" PLAN_FILE="$PLAN" \
        RESEARCH="$FEATURE_DIR/research.md" DATA_MODEL="$FEATURE_DIR/data-model.md" \
        CONTRACTS_DIR="$FEATURE_DIR/contracts" CONSTITUTION="$CONSTITUTION"
else
    echo "FEATURE_DIR: $FEATURE_DIR"; echo "SPEC_FILE: $SPEC"; echo "PLAN_FILE: $PLAN"
    echo "CONSTITUTION: $CONSTITUTION"
fi
