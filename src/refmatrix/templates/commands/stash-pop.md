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
3. If git reports a conflict, STOP and surface it — do not force or discard.

Report what was resumed (desc + focus) and confirm the code is back, so I can
pick the work up where I left it.
