---
description: List stashed work — focus task stack + paired git stashes
---

Show everything I've stashed so I can pick one to resume (possibly out of
order):

```
rmx task list
git stash list
```

`rmx task list` is the focus stash stack (1-based, top = most recent). The git
stashes carry a matching `rmx-stash: <desc>` message. Pair them by description
and present a short numbered list so I can choose which to `/stash-pop`.
