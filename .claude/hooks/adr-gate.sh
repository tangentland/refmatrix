#!/usr/bin/env bash
# PostToolUse (Edit|Write) — ADR-FIRST gate. Warns (does not block) when new class definitions in
# source files match an existing ADR that should be consulted first. Project-neutral: reads
# SRC_DIR / ADR_DIR / ADR_GATE_FILE_RE from .claude/hooks/hooks.env (see hooks.env.example).
set -euo pipefail
DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; . "$DIR/_common.sh"

INPUT="$(cat)"
FILE_PATH="$(printf '%s' "$INPUT" | hook_json_field tool_input.file_path)"
[ -z "$FILE_PATH" ] && exit 0
printf '%s' "$FILE_PATH" | grep -qE "$ADR_GATE_FILE_RE" || exit 0
# Only gate files under the configured source root.
case "$FILE_PATH" in *"/$SRC_DIR/"*|"$SRC_DIR/"*) ;; *) exit 0 ;; esac

NEW="$(printf '%s' "$INPUT" | hook_json_field tool_input.content)"
[ -z "$NEW" ] && NEW="$(printf '%s' "$INPUT" | hook_json_field tool_input.new_string)"
[ -z "$NEW" ] && exit 0

ADR_PATH="$HOOK_ROOT/$ADR_DIR"
[ -d "$ADR_PATH" ] || exit 0
CLASSES="$(printf '%s' "$NEW" | grep -oE 'class [A-Z][A-Za-z0-9_]*' | sed 's/class //' | sort -u)"
[ -z "$CLASSES" ] && exit 0

WARN=""
for C in $CLASSES; do
    case "$C" in Test*|Mock*|Fake*|_*) continue ;; esac
    M="$(grep -rli "${C}" "$ADR_PATH"/*.md 2>/dev/null | head -3 || true)"
    [ -n "$M" ] && WARN="${WARN}  class '${C}' → $(echo "$M" | xargs -I{} basename {} .md | tr '\n' ',' | sed 's/,$//')\n"
done
if [ -n "$WARN" ]; then
    echo "ADR-FIRST GATE — new classes match existing ADRs:" >&2
    printf "$WARN" >&2
    echo "Consult the ADR before proceeding. If already read, continue." >&2
fi
exit 0
