---
description: Commit-state — checkpoint mid-session (proper commits + promote STM), keep going
---

Checkpoint progress WITHOUT winding down — the lighter variant of `/save-state`.
Commit the real work cleanly and snapshot the working memory, then continue.

1. **Commit the work properly.** Review the diff, stage only intentional
   changes (tool noise — `.tldr/`, `__pycache__/`, `egg-info/` — stays
   unstaged), and make conventional commit(s), split by logical concern. Use
   `$ARGUMENTS` as a hint for the headline if given. Deploy (promote dev →
   `rmx` venv) only if code that other instances run changed.
2. **Promote the STM snapshot** so this checkpoint's state is durable:
   ```
   rmx focus summarize --promote
   ```
3. **Confirm briefly** — the commit sha(s) + subjects, and that STM was
   promoted — then KEEP GOING. This is a checkpoint, not a handoff: skip the
   full save-state ritual (no checkpoint doc, no memory pass, no wait-for-
   direction). Run it as often as makes sense to keep a clean commit trail.
