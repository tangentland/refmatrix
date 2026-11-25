---
gmd: "0.1"
id: agent-brief-build-b1
title: "Brief: build-b1 — B1's F4/F7 residue (small path)"
tags: [agent-brief, small-fix, b1, ch-bsd]
metadata:
  node_type: brief
  created: 2026-11-25
---

# build-b1 {#root}

rel: implements -> [[task-b1-f4-f7]]

You are one isolated small-fix agent (ORCHESTRATION `#task-small`). Build
`workflow/plans/task-b1-f4-f7.md` exactly: read it first, then
`docs/external_reviews/ch-bsd-assessment-2026-11-23.md` `#f4` and `#f7`, `workflow/bullshit/OPEN.md`
and `CLOSED.md`, `workflow/bullshit/IMPRESSIONS.md`, CLAUDE.md `#test-discipline`. Write the tests and
the change; show each test failing first by its E line; run the verify set (your tests + every
importer + the repo guards) on a committed sha; commit. {#role}

**The lead does, not you:** writing the new `impression_bsd_ledger_*` memory and running the bridge
(F7's fold into memory). Prepare the exact text of the bullets to fold in a file
`workflow/review-output/b1-f7-fold.txt` and leave the memory write to the lead. Read-only against
every live store; never `find /`; never export `REFMATRIX_ROOT`. No POP or registry edits.
Report (REPORT.md): sha, what changed, RED E lines, verify counts, self-audit answers. {#rules}
