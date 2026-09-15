#!/usr/bin/env bash
# Common helpers for the SDD (spec-driven development) command scripts.
# Feature artifacts live under workflow/specs/NNN-<slug>/ ; templates under workflow/templates/.
set -euo pipefail

get_repo_root() {
    git rev-parse --show-toplevel 2>/dev/null || pwd
}

# Resolve a template by base name, e.g. resolve_template "spec" -> workflow/templates/spec-template.md
resolve_template() {
    local name="$1" root="${2:-$(get_repo_root)}"
    local path="$root/workflow/templates/${name}-template.md"
    [ -f "$path" ] && echo "$path" || return 1
}

specs_dir() { echo "$(get_repo_root)/workflow/specs"; }

# Highest sequential NNN prefix in workflow/specs/ (0 if none).
highest_feature_num() {
    local dir; dir="$(specs_dir)"; local highest=0
    [ -d "$dir" ] || { echo 0; return; }
    for d in "$dir"/*; do
        [ -d "$d" ] || continue
        local base; base="$(basename "$d")"
        if echo "$base" | grep -Eq '^[0-9]{3,}-'; then
            local n; n=$((10#$(echo "$base" | grep -Eo '^[0-9]+')))
            [ "$n" -gt "$highest" ] && highest=$n
        fi
    done
    echo "$highest"
}

# Locate the active feature dir: $SPECIFY_FEATURE env override, else current git branch
# matching NNN-*, else the highest-numbered specs/ dir.
current_feature_dir() {
    local root; root="$(get_repo_root)"; local dir="$root/workflow/specs"
    if [ -n "${SPECIFY_FEATURE:-}" ] && [ -d "$dir/$SPECIFY_FEATURE" ]; then
        echo "$dir/$SPECIFY_FEATURE"; return 0
    fi
    local branch; branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [ -n "$branch" ] && [ -d "$dir/$branch" ]; then
        echo "$dir/$branch"; return 0
    fi
    # Fallback: highest-numbered dir
    local best=""
    if [ -d "$dir" ]; then
        for d in "$dir"/*; do [ -d "$d" ] && best="$d"; done
    fi
    [ -n "$best" ] && { echo "$best"; return 0; }
    return 1
}

# Emit a flat JSON object from key=value args (no nested values).
emit_json() {
    local first=1; printf '{'
    for kv in "$@"; do
        local k="${kv%%=*}" v="${kv#*=}"
        [ $first -eq 1 ] || printf ','; first=0
        printf '"%s":"%s"' "$k" "$(printf '%s' "$v" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    done
    printf '}\n'
}
