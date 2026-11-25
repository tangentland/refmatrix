#!/bin/bash
# Claude Code status line, two lines: (1) the one user-level script, ~/.claude/statusline.sh
# (project, model + Claude Code version, context, tokens, weekly tokens); (2) refmatrix's
# isolated-user line (scripts/lane-status.sh: which rmxtestN lane run and isolated agent is live;
# the user, 2026-11-25: "we can add another line").
input=$(cat)
printf '%s' "$input" | "$HOME/.claude/statusline.sh"
"${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}/scripts/lane-status.sh"
