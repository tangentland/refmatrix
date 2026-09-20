---
gmd: "0.1"
id: impl-bug-053-054-audit-s2-m5
title: "bug-053 / bug-054: the in-flight registry names the right call, and the suite runs from any checkout"
tags: [implementation-summary, ch-bsd, daemon, tests, reproducibility]
metadata:
  node_type: implementation-summary
  status: complete
  audit: bsd-bug-041-042-043-00d0ded
  findings: [s-2, m-5]
  created: 2026-09-20
---

# bug-053 / bug-054: the audit's last two ranked findings {#root}

rel: derives-from -> [[bsd-bug-041-042-043-00d0ded]]
rel: amends -> [[impl-bug-051-stop-deadline]]
rel: reinforces -> [[feedback_check_the_sibling_condition]]

## bug-053 (#s-2): the registry lost the call it exists to name {#s2}

bug-041 replaced a hypothesis in the shutdown log — *"leaked worker likely holds it"* — with an
in-flight registry, "the evidence". The registry was keyed by op NAME, so two concurrent calls of
one op shared an entry: the second arrival overwrote the first's timestamp, and whichever finished
FIRST popped the key while the other still held the writer. The audit reproduced the result on the
exact scenario the fix exists for: {#s2-lead}

```
A still holds _store_lock; registry: {}
SHUTDOWN LOG: final flush skipped: ... in flight: nothing tracked — the holder
  is not an op, check the watcher or a background tick
```

A guess had become a confident misdirection. With `disp=20`, duplicate concurrent op names are the
NORMAL case: the hub tick's `ping` and `daemon_status`, the watcher's and the queue's
`ingest_path`.

Now `{token: (op, started_at)}` — one entry per CALL, each popping its own token. The skipped-flush
line renders oldest-first, so two live `ingest_path`s show two ages instead of collapsing into one.

**The old test could not have caught this.** It drove the hand-off through a `_Pool` stub that ran
the op inline — the ch-bsd #b-5 MUST GRADUATE row — so it asserted the registry against a
dispatcher that never used the executor. It is deleted; `tests/test_inflight_registry.py` drives
the real `_handle` on real `ThreadPoolExecutor`s and real socketpairs, which is where the defect
lives. Mutation: popping by name again kills
`test_the_call_that_finishes_first_does_not_clear_the_one_still_running`. {#s2-tests}

## bug-054 (#m-5): a commit's suite result was not reproducible from its sha {#m5}

`.claude/settings.json` is committed, and its hook commands carry ABSOLUTE paths of the tree they
were rendered for. `test_installed_hooks_match_generated` compared that committed file against a
render for the CURRENT root, so a second checkout of the same commit failed on a pure path rebase:
{#m5-lead}

```
- ... rmx primer --out '/Users/tholley/claude_tools/refmatrix/.refmatrix/PRIMER.md'
+ ... rmx primer --out '/private/tmp/rmxwt/.refmatrix/PRIMER.md'
```

Nothing is wrong with either tree. The cost is the one the auditor paid: once the working tree
moves on, a commit's suite result can no longer be reproduced from its sha, which is why this
ledger has filed "full-suite log ≠ committed tree" three times.

`hooks.installed_root()` reads which checkout the installed hooks belong to. The identity test
skips when that is not this tree, and `check()` now LEADS its diff with

```
! these hooks were generated for another checkout (<path>); this tree is <path>
  — the entries below differ by path prefix, not by content
```

so `rmx install-hooks --check` in a relocated tree stops sending a reader to hunt a hand-edit that
does not exist.

**Measured, not asserted.** The audit's six files went **42 failing → 83 passed, 1 skipped** in a
detached worktree at this sha, and the full suite was then run from that worktree
(`workflow/review-output/pytest-bug054-worktree-full.log`). The one skip is the identity check,
with its reason. {#m5-evidence}

## Gates {#gates}

| gate | bug-053 | bug-054 |
|---|---|---|
| RED | `pytest-bug053-red.log` — 4 failed | `pytest-bug054-red.log` — 5 failed |
| GREEN | `pytest-bug053-green.log` — 32 passed with the shutdown set | `pytest-bug054-green.log` — 12 passed |
| Mutation | `pytest-bug053-mutation.log` — pop-by-name kills 1 | the worktree run is the mutation-equivalent: the fix's absence IS the 42 failures |
| Full suite | `pytest-bug053-054-full.log` (in-tree) + `pytest-bug054-worktree-full.log` (detached worktree) | same |

## What remains of that audit {#open}

Five MEH findings (`m-1`..`m-4`) and `s-4` (partly addressed by bug-045's `STILL OVER` line). No
BULLSHIT or SKETCHY finding from `bsd-bug-041-042-043-00d0ded` is now open. {#open-lead}
