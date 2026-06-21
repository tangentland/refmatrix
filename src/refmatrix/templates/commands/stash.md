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

If `$ARGUMENTS` is empty, first run `rmx focus context` and use a concise
one-line description of what I'm working on, and use it for BOTH commands so
they stay paired.

Then report what was stashed (code + focus) and the new depth (`git stash list`
/ `rmx task list`). Don't start the new task — just stash and report.
