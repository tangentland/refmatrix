#!/bin/bash
# Claude Code status line: delegates to the one user-level script, ~/.claude/statusline.sh
# (project, model + Claude Code version, context, tokens, weekly tokens). Kept as a wrapper so
# .claude/settings.json's "statusLine" still resolves and every project shows the same line.
exec "$HOME/.claude/statusline.sh"
