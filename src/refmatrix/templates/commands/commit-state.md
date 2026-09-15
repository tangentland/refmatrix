---
description: Commit-state — checkpoint mid-session (proper commits + promote STM), keep going
---

Checkpoint progress WITHOUT winding down — the lighter variant of `/save-state`.
Commit the real work cleanly and snapshot the working memory, then continue.

**If `$ARGUMENTS` contains `--undo`:** reverse the last commit-state checkpoint
instead of making one.
- `git reset --soft HEAD~1` — drops the last commit but KEEPS all its changes
  staged, so I can amend or redo. NEVER `--hard` (that loses work).
- First sanity-check it's safe: if `HEAD` is already pushed
  (`git branch -r --contains HEAD`), STOP and warn — don't rewrite published
  history; the user pushes manually.
- Report which commit was undone (sha + subject, now back in the working tree),
  and note if it had deployed code (deploy is now ahead of dev until redone).
- The STM promote is idempotent (overwrites the same memory id), so there's
  nothing to undo there.
Then stop — don't re-commit. Otherwise, make a checkpoint:

1. **Commit the work properly.** Review the diff, stage only intentional
   changes (tool noise — `.tldr/`, `__pycache__/`, `egg-info/` — stays
   unstaged), and make conventional commit(s), split by logical concern. Use
   `$ARGUMENTS` as a hint for the headline if given. Deploy (ff `~/refmatrix` to the sha + `rmx daemon restart --relaunch`; verify `rmx version -v` →
   `rmx` venv) only if code that other instances run changed.
2. **Promote the STM snapshot** so this checkpoint's state is durable:
   ```
   rmx focus summarize --promote
   ```
3. **Confirm briefly** — the commit sha(s) + subjects, and that STM was
   promoted — then KEEP GOING. This is a checkpoint, not a handoff: skip the
   full save-state ritual (no checkpoint doc, no memory pass, no wait-for-
   direction). Run it as often as makes sense to keep a clean commit trail.
