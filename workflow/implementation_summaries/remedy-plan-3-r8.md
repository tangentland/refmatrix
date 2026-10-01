---
gmd: "0.1"
id: impl-remedy-plan-3-r8
title: "Plan-3 round 8: legs that can fire, a bound on the leg that costs"
tags: [implementation, plan-3, remedy]
metadata:
  node_type: implementation-summary
  date: 2026-10-01
---

# Plan-3 round 8 {#root}

rel: evidence-for -> [[bsd-plan3-verbs-parity-r7-e0b7df6]]
rel: amends -> [[impl-remedy-plan-3-verbs-parity]]

Remedies ch-bsd plan-3 r7 (DIRTY, 2B/2S/2M). Every finding was against round 7's
own work, which I had reported as closed hours earlier in the same session.

## The shape all four shared {#shape}

Round 7 fixed four things and three of them **could not work**, because each fix
was written against a failure mode that does not occur:

- an `except Exception` around a callee that never raises,
- a bound on the leg that was not the one spending the time,
- a renderer for "the last consumer", which was not last.

Mutation checking caught none of it. Round 7's mutations *did* kill a test
apiece — because its tests patched `_replica_bundle` into raising, so the
mutation and the test agreed with each other about a path the product never
takes. **Equal verdicts on a faked collaborator are not a reproduction.**

The gate that does catch it costs seconds and is now the first step here: run the
new suite against UNFIXED code. **A RED test that passes at HEAD is not a RED
test** (ch-bsd plan-3 r7's phrasing).

## Fixes {#fixes}

| r7 finding | Fix |
|---|---|
| #b-1 both `skipped` legs unreachable | `_replica_bundle(..., on_error: list \| None)` appends its reason and still returns `{}` for every existing caller. Both legs read the list |
| #b-2 promote still 180.2 s | the GLOBAL write carries `timeout=_left(30.0), retries=0`. Round 7 bounded the project READ and left the write at `global_call`'s 60 s × 3 |
| #s-3 "last consumer" false; fix pasted | one `cli._echo_skipped`, two call sites; `app.js` renders `skipped` — the omnibox was a third consumer turning a busy store into "no hits" |
| #m-5 probe spent twice | `max(0.5, _budget - elapsed)`, like its three siblings |
| #s-4 registry | both plan-3 remedy test files registered, the r6 row naming the `_replica_bundle` patch as the thing #b-1 is |

### The third caller, found by sweeping rather than by report {#third-caller}

r7 named two `_replica_bundle` callers. There were **three**:
`_locate_one_project` (`search.py:374`) had no reasons channel at all, and two
silent swallows. So a store with a missing replica produced `{}`,
`federated_locate` merged nothing, and `rmx locate` printed "no matches" with no
skipped line — the r3 #b-2 symptom, fixed at the fan-out level and still live one
frame down. Both legs now report, and `federated_locate` merges per-project
reasons into `skipped`.

This is the quoted-line-sibling lesson applied before the audit rather than
after: the auditor's round-9 plan named "whether `on_error` is read by every
caller" as its first check.

### A sibling deliberately left alone {#sibling}

`verbs.memory_add` (`--global`) has the same unbounded `global_call` and **stays
that way**, with a comment saying why: a user-initiated plain write has no budget
over it, so waiting beats dropping the write. promote is different because it
promised 10 s. Silently leaving it would read as the same oversight; silently
changing it would alter a documented choice on an auditor's aside.

## Gates {#gates}

RED `workflow/review-output/pytest-plan3-r8-red.log` — 4 failed / 2 passed. **The
two passes were my own vacuous tests** and both are recorded because the failure
is instructive:

- #b-2's used a BLANKET `monkeypatch.setattr("refmatrix.daemon.call")`, and
  `hub.global_call` routes through the same function, so the fake answered the
  global write: 0.00 s, global ops `['ping']`, every assertion passing for free.
  It would have passed against `timeout=10000, retries=99`. I had already
  diagnosed this exact hole in my own probe, fixed the probe, measured 180.2 s —
  and never propagated the fix into the test file.
- #m-5's called `_snapshot()`, i.e. replica PRESENT — the one state where the
  defect is invisible, because the probe is then answered from the replica. The
  finding named `[ping/replica=False]`.

Corrected, both fail at HEAD; #m-5 at **15.01 s** against a 13 s bar, matching
the auditor's 15.0 s — the state was corrected, not the tolerance.

GREEN `pytest-plan3-r8-green2.log` — 7 passed in 23.7 s.

Mutations `pytest-plan3-r8-mutations.log`, 7 of 7 kill their target: R1
(`_replica_bundle` swallows again → 3 fail, including the signature test), R2/R3
(each leg stops reading the callee), R4 (global write unbounded → fails in
**90.6 s**, the hang returning), R5 (whole budget → 15.4 s), R6 (`canon_find`
stops rendering), R7 (locate stops collecting).

Committed BEFORE mutating. Earlier in this session a `git checkout -- src/` to
revert a mutation destroyed an uncommitted implementation and it had to be
replayed in full; see [[feedback_commit_before_mutation_revert]].

## Status {#status}

plan-3 stays `in-progress`. A round-9 re-review is the auditor's call; after this
session's evidence about self-assessment I am not flipping a plan status on my
own say-so, and the rule BSD enforced against plan-1 says the gate decides.
