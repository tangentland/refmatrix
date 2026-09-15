#!/usr/bin/env bash
# Shared hook helpers. Sources .claude/hooks/hooks.env if present (else defaults).
# All enforcement hooks are optional + fail-open: any internal error exits 0 (never blocks work
# spuriously) EXCEPT the deliberate policy blocks (exit 2) in the individual hooks.

hook_repo_root() { git rev-parse --show-toplevel 2>/dev/null || pwd; }

# Load config with defaults.
HOOK_ROOT="$(hook_repo_root)"
SRC_DIR="src"
ADR_DIR="docs/architecture/adr"
CORPUS_PATHS="src docs workflow tests"
CORPUS_EXTS=".py .ts .tsx .js .jsx .md .sh .json .yaml .yml .toml .txt .html .css"
ADR_GATE_FILE_RE='\.(py|ts|tsx)$'
[ -f "$HOOK_ROOT/.claude/hooks/hooks.env" ] && . "$HOOK_ROOT/.claude/hooks/hooks.env"

# Read a field from the hook stdin JSON (tool_input.<key>), via python3. Echoes empty on miss.
hook_json_field() { python3 -c "import json,sys
d=json.load(sys.stdin)
cur=d
for k in sys.argv[1].split('.'):
    cur=(cur or {}).get(k) if isinstance(cur,dict) else None
print(cur if isinstance(cur,str) else '')" "$1" 2>/dev/null || true; }
