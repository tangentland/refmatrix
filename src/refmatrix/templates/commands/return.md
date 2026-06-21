---
description: Return from a soft branch detour — rewind focus to the bookmark
---

Snap back from a detour. `$ARGUMENTS` selects which one (a label substring, or
the index from `rmx focus detours`); empty = the most recent.

Run:

```
rmx focus return "$ARGUMENTS"
```

This re-warms the focus to the pre-detour state. The tangent stays in the full
log (recallable, still its own topic). Report what was restored and the focus
symbols it re-warmed, then re-orient on that before resuming the original work.

To see open detours first: `rmx focus detours`.
