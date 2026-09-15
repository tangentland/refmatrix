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
2. **Enduring memory FIRST** — write/append any feedback rules, project-state
   facts, or gotchas to the memory dir + update `MEMORY.md`. Before
   save-state, because save-state's memory bridge ingests the dir as it is
   at that moment.
3. **Save-state + promote + bridge** in one:
   ```
   rmx save-state --commit -m "<one-line headline of this session>"
   ```
   This writes the GMD handoff, promotes the condensed STM digest to durable
   memory, runs the memory bridge (`ingest-gmd --as-memory` over the memory
   dir, so the next instance's SessionStart recall sees everything), and
   commits. A red `memory bridge FAILED` line is a loose end — fix or report
   it, never skip it.
4. **Deploy if code landed** — fast-forward the deploy tree to the committed sha and
   relaunch: `git -C ~/refmatrix pull --ff-only origin master && rmx daemon restart --relaunch`.
   Verify with `rmx version -v` (no `[DEV TREE]`). NEVER `pip install -e <dev tree>` into the
   deploy venv — that makes `rmx`, every daemon and the hub run uncommitted code (2026-09-14).
5. **Report** the resume point: branch + HEAD, what shipped, open loose ends,
   the concrete next action, and whether the push is still pending (the user
   pushes).

$ARGUMENTS
