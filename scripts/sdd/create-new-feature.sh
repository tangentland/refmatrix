#!/usr/bin/env bash
# Create a new SDD feature: workflow/specs/NNN-<slug>/spec.md (+ optional branch).
# Usage: create-new-feature.sh [--json] [--short-name <slug>] [--no-branch] <feature description>
set -euo pipefail
SCRIPT_DIR="$(CDPATH="" cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

JSON=false; SHORT=""; MAKE_BRANCH=true; ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --json) JSON=true ;;
        --no-branch) MAKE_BRANCH=false ;;
        --short-name) SHORT="$2"; shift ;;
        -h|--help) echo "Usage: $0 [--json] [--short-name <slug>] [--no-branch] <description>"; exit 0 ;;
        *) ARGS+=("$1") ;;
    esac
    shift
done
DESC="${ARGS[*]:-}"
[ -n "$DESC" ] || { echo "Error: feature description required" >&2; exit 1; }

slugify() {
    # lowercase, drop stop words, keep first 3-4 meaningful words, hyphenate
    local stop="^(a|an|the|to|for|of|in|on|at|by|with|from|is|are|be|add|get|set|new|and|or)$"
    local out=() n=0
    for w in $(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' ' '); do
        [ -z "$w" ] && continue
        echo "$w" | grep -qiE "$stop" && continue
        [ ${#w} -lt 2 ] && continue
        out+=("$w"); n=$((n+1)); [ $n -ge 4 ] && break
    done
    local IFS=-; echo "${out[*]}"
}

SLUG="$(slugify "${SHORT:-$DESC}")"
[ -n "$SLUG" ] || SLUG="feature"
NUM=$(printf "%03d" "$(( $(highest_feature_num) + 1 ))")
NAME="${NUM}-${SLUG}"
ROOT="$(get_repo_root)"
FEATURE_DIR="$ROOT/workflow/specs/$NAME"
SPEC="$FEATURE_DIR/spec.md"

mkdir -p "$FEATURE_DIR"
if [ ! -f "$SPEC" ]; then
    TPL="$(resolve_template spec "$ROOT" || true)"
    if [ -n "$TPL" ]; then cp "$TPL" "$SPEC"; else echo "# Feature Specification: $SLUG" > "$SPEC"; fi
fi

if $MAKE_BRANCH && git rev-parse --git-dir >/dev/null 2>&1; then
    git show-ref --verify --quiet "refs/heads/$NAME" || git checkout -b "$NAME" >/dev/null 2>&1 || true
fi

if $JSON; then
    emit_json BRANCH_NAME="$NAME" FEATURE_DIR="$FEATURE_DIR" SPEC_FILE="$SPEC" FEATURE_NUM="$NUM"
else
    echo "BRANCH_NAME: $NAME"; echo "FEATURE_DIR: $FEATURE_DIR"; echo "SPEC_FILE: $SPEC"
fi
