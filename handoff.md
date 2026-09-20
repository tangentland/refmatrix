---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-09-17/20 (session dd1cb4f9). Prior handoff archived at
`workflow/past_handoffs/003-plan-12-close-bug-041-043_2026-09-16.md`.

rel: depends-on -> [[plan-of-plans]]

## Where the work sits {#state}

**`master` at `1109b4a`, tree clean.** Version **0.72.3** — **NOT DEPLOYED**. `~/refmatrix` and all
8 fleet stores still serve 0.72.2. The push is the user's, as always. {#state-lead}

Two merges this session:

| sha | what |
|---|---|
| `8efef73` | plan-6 task 6.1 — stale deferrals, and **bug-044** (silent degradation on the memory embed path) |
| `1109b4a` | the ch-bsd remedy round — **bug-045..049** + the `#s-3` sibling gate |

Plus **bug-050**, found during this save-state and fixed (committed separately — see
[[#bug-050]]).

## What was asked, and what it turned into {#arc}

The session opened cold ("where are we") and ran a, b, c in order:

1. **(a) Audit the unaudited range.** `@ch-bsd` over `34aeddf..00d0ded` — the bug-041/042/043 work
   that shipped as 0.72.2 with no adversarial pass. Verdict **DIRTY, 14 findings (5B/4S/5M)**.
   All five BULLSHIT and the `#s-3` sibling are fixed; **4 SKETCHY and 5 MEH are NOT** ([[#open]]).
2. **(b) plan-6.** Smaller than it looked: 6.4 and 6.5 were already done and only needed closing
   out; 6.1 was real and exposed bug-044.
3. **(c) benchmarks — NOT STARTED.** The user chose MemAware, CSN python/JS/TS, and the
   8-experiment retrieval set, then redirected to chase the grep wall first.

## The grep wall (bug-049) — found in telemetry, not by a test {#grep-wall}

The suite was green throughout. `.refmatrix/query.log` said otherwise: 104 of 1,165
`grep-replica` calls pinned at **30,178-30,222 ms**, rising to **17% of calls on 09-16**, ~52 min
of pure waiting lifetime. Reproduced live at **30.425 s** with `user 0m0.259s`.

Cause: four `learn_from_grep` sites each passed a timeout and inherited `daemon.call`'s
`retries=2` → 3× budget (worst case **180.45 s** at one unwrapped `timeout=60.0` site). Fixed in
two halves — a bounded shared broker, and a coalescing `learn_queue.py` the daemon's flush tick
drains. **The drain yields the writer per entry** (the user caught a batch-wide hold in review),
with a 5 s tick budget, shutdown stop, and requeue-never-drop. Full story:
[[project_grep_learn_wall_and_queue]]. {#grep-wall-body}

## bug-050, found by this very save-state {#bug-050}

Regenerating `MEMORY.md` during the handoff, `check()` read OUT OF SYNC immediately after a
successful `write()`. Rendering the index from its own output folded **2 more entries each time**
(56 → 58) with no memory added: `parse_hooks` only sees entries the index still lists, so a folded
entry lost its curated hook, fell back to longer derived prose, and pushed two more out. Every
save-state would have degraded the index further. Fixed with a `.memory_hooks.json` sidecar;
`render(render(x)) == render(x)` is now a test. Live index converged **145 lines / 23,104 chars,
`check()` True**. {#bug-050-body}

## What is NOT done {#open}

- **DEPLOY.** 0.72.3 is committed and unpushed. I asked and did not get an answer, so I did not
  deploy — b-3 and s-3 change daemon and hub behaviour, and this repo's own rule is that a
  shutdown-path change is only observable on the SECOND restart after a deploy. Two things argue
  for deploying soon: the 30 s grep wall is live in production right now, and bug-045 means every
  session still loads a truncated `MEMORY.md` from the deploy path.
- **4 SKETCHY + 5 MEH from the audit.** Ranked: **s-1** is the serious one — the flush budget went
  5→15 s, putting the degraded stop at 59 s worst case against launchd's `ExitTimeOut = 45`, the
  SIGKILL that corrupts the ART index. Then **s-2** (`_inflight_ops` keyed by op NAME) and **m-5**
  (the suite cannot run against a detached checkout of its own commit — ch-bsd saw 42 failures).
- **(c) the benchmark re-run.** Note the ordering constraint: the grep-wall fix changes
  retrieval-path latency, so runs before and after the deploy are not comparable. Deploy first,
  then measure the deployed path.
- **A telemetry defect, unfixed:** `grep-replica` shows 278 "errors" of which 256 are
  `SystemExit: 1` (grep's normal NO-MATCH) and 22 are `BrokenPipeError`. Real failures ≈ 6. Same
  distortion in `cli.log`. Anything reading `error`/`exit_code` from those logs reads noise as
  failure. Recorded in [[project_grep_learn_wall_and_queue]].
- **plan-6 is not flipped to `completed`,** and plans 2/3/4/7/8/9/10 still read `in-progress`
  although every task under them is complete or cancelled. That is bookkeeping I deliberately did
  not do unilaterally: the plan-of-plans rule gates `completed` on a CLEAN `@ch-bsd` over each
  plan's range, and plans 7-10's last round was DIRTY before plan-12 absorbed its findings.

## Quality gates {#gates}

| gate | state |
|---|---|
| Full suite | **2112 passed, 0 failed** at `1109b4a`, `src/` hash identical before and after the run |
| bug-050 run | in flight at handoff — `workflow/review-output/pytest-bug050-full.log` |
| GMD lint | 0 errors, 14 warnings (the standing baseline) |
| `rmx install-hooks --check` | in sync |
| `@ch-bsd` | DIRTY at `00d0ded`; the 5 BULLSHIT + s-3 remedied here, NOT re-audited |

**Every full-suite log this session was hash-verified** against the tree it describes, because two
were contaminated: one by a mutation I was running concurrently, and one by my own new
Python-floor guard writing 62 `cpython-310` pycs into `src/__pycache__`. See
[[feedback_never_explain_away_a_failing_guard]] — I attributed the second to the first and was
wrong; the clean re-run proved it.

## Next session {#next}

1. Read `workflow/bullshit/2026-09-16-1700-bug-041-042-043-post-deploy-00d0ded.md` — the 9
   unaddressed findings, `#s-1` first.
2. Decide the deploy. If deploying: `git -C ~/refmatrix pull --ff-only origin master` →
   `rmx daemon restart --relaunch` → **restart a second time** to observe the shutdown-path change
   → `rmx hub relaunch-fleet` → verify all 8 stores on 0.72.3.
3. Confirm on the live fleet that the `hot` gate now alerts once rather than every tick, and that
   `rmx grep` no longer walls at 30 s (it does today, on the deploy build).
4. Then (c): MemAware, CSN python/JS/TS, the 8-experiment set — against the DEPLOYED path.
