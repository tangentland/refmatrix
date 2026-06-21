---
description: Save state — handoff the session (commit, promote STM, memory, report)
---

"Save state" is a handoff directive: make the work ready for context-clear,
exit, or pickup by another instance. Not just a summary. **Save state =
promote** — the working memory graduates to durable memory.

Do all of this:

1. **Commit** outstanding intentional work (multiple commits if it spans
   concerns). Tool noise (`.tldr/`, `__pycache__/`, `egg-info/`) stays
   unstaged.
2. **Save-state + promote** in one:
   ```
   rmx save-state --commit -m "<one-line headline of this session>"
   ```
   This writes the GMD handoff, promotes the condensed STM digest to durable
   memory (so the next instance recalls it), and commits.
3. **Enduring memory** — write/append any feedback rules, project-state facts,
   or gotchas to the memory dir + update `MEMORY.md`.
4. **Deploy if code landed** — promote dev → the live `rmx` venv and restart
   any affected daemon.
5. **Report** the resume point: branch + HEAD, what shipped, open loose ends,
   the concrete next action, and whether the push is still pending (the user
   pushes).

$ARGUMENTS
