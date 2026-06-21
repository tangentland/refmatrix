---
description: Restore stashed work (focus + code), optionally out of order
---

Restore work I stashed — BOTH the focus context AND the code — optionally a
specific one. `$ARGUMENTS` selects which: a desc substring, or the index from
`/stash-list`. Empty = the most recent.

1. Restore the focus (this resolves which stash by selector):
   ```
   rmx task pop "$ARGUMENTS"
   ```
   Note the restored desc + focus symbols it reports.
2. Restore the paired code. Find the git stash whose message matches that desc:
   ```
   git stash list | grep "rmx-stash: <desc>"
   ```
   Then apply its `stash@{n}` and drop it:
   ```
   git stash pop "stash@{n}"
   ```
   With no `$ARGUMENTS`, the most recent rmx-stash is `stash@{0}`.
3. If `$ARGUMENTS` contains `--branch <name>` (or `-b <name>`), strip it from
   the selector and restore the code ONTO that branch instead of the current
   one — this is the clean way to resume on a different direction:
   ```
   git stash branch <name> "stash@{n}"   # creates <name> at the stash's base + applies + drops
   ```
   The focus restores the same way regardless of branch (STM is per-session).
4. If git reports a conflict, STOP and surface it — do not force or discard.

Report what was resumed (desc + focus), the branch now checked out, and confirm
the code is back, so I can pick the work up where I left it.
