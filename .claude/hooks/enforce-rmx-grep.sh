#!/usr/bin/env bash
# PreToolUse (Bash) — redirect CORPUS-discovery grep -> rmx; allow everything else.
# Only acts when rmx is installed. Blocks grep/rg/egrep/fgrep that READS the indexed corpus
# (CORPUS_PATHS from hooks.env) or does pure pathless discovery. Allows: rmx, piped grep
# (filtering output), a specific non-corpus file, and scratch/absolute paths. Project-neutral.
set -euo pipefail
DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; . "$DIR/_common.sh"

# No-op if rmx isn't available — nothing to redirect to.
command -v rmx >/dev/null 2>&1 || exit 0

CMD="$(cat | hook_json_field tool_input.command)"
[ -z "$CMD" ] && exit 0

case "$CMD" in rmx\ *|rmx) exit 0 ;; esac                      # allow rmx
case "$CMD" in *\|*grep*|*\|*\ rg\ *|*\|*egrep*|*\|*fgrep*) exit 0 ;; esac  # allow piped grep
case "$CMD" in grep\ *|grep|rg\ *|egrep\ *|fgrep\ *) ;; *) exit 0 ;; esac    # only leading grep

DECISION="$(CORPUS_PATHS="$CORPUS_PATHS" CORPUS_EXTS="$CORPUS_EXTS" \
  python3 -c "
import sys, os, shlex
CORPUS = tuple(os.environ.get('CORPUS_PATHS','src docs workflow tests').split())
EXTS   = tuple(os.environ.get('CORPUS_EXTS','.py .ts .md').split())
cmd = sys.stdin.read().strip()
try: parts = shlex.split(cmd)
except ValueError: parts = cmd.split()
flags     = [t for t in parts[1:] if t.startswith('-')]
non_flags = [t for t in parts[1:] if not t.startswith('-')]
path_tokens = non_flags[1:]                       # first non-flag is the PATTERN
path_like = [t for t in path_tokens if ('/' in t or t.endswith(EXTS) or t in ('.','./','*'))]
def is_corpus(tok):
    t = tok.lstrip('./').rstrip('/')
    return any(t==d or t.startswith(d+'/') or ('/'+d+'/') in tok or tok.endswith('/'+d) for d in CORPUS)
recursive = any(f in ('-r','-R','--recursive') or (f.startswith('-') and not f.startswith('--') and 'r' in f[1:]) for f in flags) or any('--include' in f for f in flags)
barewide  = any(t in ('.','./','*') for t in path_like)
corpus    = any(is_corpus(t) for t in path_like)
no_path   = len(path_like) == 0
print('block' if (corpus or barewide or (recursive and no_path) or no_path) else 'allow')
" <<<"$CMD" 2>/dev/null || echo allow)"

if [ "$DECISION" = "block" ]; then
  {
    echo "Corpus grep redirected — use rmx for code/doc lookups:"
    echo "  rmx grep PATTERN        # index-backed content search"
    echo "  rmx context SYMBOL      # symbol bundle (defs/refs/neighbors)"
    echo "  rmx memory search TEXT  # workflow/ docs + memory"
    echo "(Piped grep, single non-corpus files, and scratch/tmp paths are still allowed.)"
  } >&2
  exit 2
fi
exit 0
