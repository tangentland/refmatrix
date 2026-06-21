---
description: Stash current work — git working tree + focus state — to switch tasks
---

Stash my current work so I can chase a tangent and restore it later — BOTH the
in-progress code AND the focus context, paired by a matching label.

1. Stash uncommitted code (including untracked) under a matching message:
   ```
   git stash push -u -m "rmx-stash: $ARGUMENTS"
   ```
   If the working tree is clean, skip this and note "no code to stash".
2. Stash the focus state (snapshots the current focus subgraph):
   ```
   rmx task push "$ARGUMENTS"
   ```

If `$ARGUMENTS` contains `--branch <name>` (or `-b <name>`), strip it from the
description, and AFTER stashing switch git direction to that branch:
```
git switch <name>      # or: git switch -c <name>   (if it doesn't exist yet)
```
The STM/focus is per-SESSION, not per-branch, so it stays intact across the
swap and keeps recording — that's the point: swap direction, STM intact.

If `$ARGUMENTS` (after removing any `--branch`) is empty, first run
`rmx focus context` and use a concise one-line description of what I'm working
on, and use it for BOTH the git stash message and `rmx task push` so they stay
paired.

Then report what was stashed (code + focus), the branch now checked out, and
the new depth (`git stash list` / `rmx task list`). Don't start the new task —
just stash, swap if asked, and report.
