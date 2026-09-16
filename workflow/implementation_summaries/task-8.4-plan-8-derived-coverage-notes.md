---
gmd: "0.1"
id: task-8.4-summary
title: "Task 8.4 summary: the brief/unanswered gate FAILED and the detector was not built"
tags: [implementation-summary, plan-8, negative-result]
metadata:
  node_type: summary
  task: task-8.4-plan-8-derived-coverage-notes
  created: 2026-09-15
  verdict: FAIL
---

# brief/unanswered: pre-registered confound check {#root}

rel: evidence-for -> [[task-8.4-plan-8-derived-coverage-notes]]
rel: depends-on -> [[project_helix_log_confounded]]
rel: implements -> [[project_helix_phase2_decision_criterion]]

**Verdict: FAIL on C3. The detector does not ship.** This document is the
deliverable; a negative result recorded is worth more than a class that emits
plausible rows nobody can act on.

## Why a gate at all {#why}

`brief/unanswered` would group queries that returned nothing, by term, and
report them as places the corpus is asked and cannot answer.
[[project_helix_log_confounded]] is the precedent and the exact shape of the
danger: a log written by a path that suppresses its own signal, read afterwards
as if it measured demand. A near-empty helix log almost decided a phase.

So the criteria below were fixed BEFORE the numbers were read, per
[[project_helix_phase2_decision_criterion]].

## Criteria, as registered {#criteria}

| # | Criterion | Bar |
|---|---|---|
| C1 | The log is not suppressed by the condition it records | logging unconditional on cardinality; zero-result rows present across the whole span |
| C2 | The demand is real content, not control tokens | >= 50% of zero-result rows retain >= 1 content term after the shared stoplist + shape gate |
| C3 | Volume supports a threshold | >= 5 terms appear in >= 5 distinct zero-result queries, and the top term is not an artifact |

## What was measured {#measured}

`.refmatrix/query.log`, this project's own store, **2026-06-03 to 2026-09-15**
(3.5 months): 2,527 rows, 0 unparsed. 465 zero-cardinality rows.

### C1 — PASS {#c1}

`telemetry.log_query.__exit__` writes its record unconditionally; nothing
branches on `cardinality`. Zero-result rows are 18.4% of all rows and appear in
every month of the span (0.326 / 0.034 / 0.123 / 0.196). This log is **not**
the helix failure.

Two genuine blind spots exist and are named rather than waved off: `__exit__`
returns early when `store is None` (RPC-served paths have nowhere local to
append), and a write `OSError` is swallowed. Neither is result-dependent, so
neither biases the zero-rate — but both mean the log is a sample, not a census.

### C2 — passes the bar, and the bar is wrong {#c2}

263 of 465 zero rows (56.6%) retain a content term. That clears 50%.

It should not be credited. The rows the gate DROPPED include:

```
fix the slot rotation catalog sync
run replica refresh
diff A vs B both directions
verify recall from a fresh hook fire
```

Those are real queries. The shape-0 junk gate is calibrated for code tokens and
is discarding ordinary prose — the same mis-calibration
[[project_scan_prompt_junk_gate]] records against conversational register. So
C2's operationalization does not measure what it claimed to, and a pass here is
not evidence.

### C3 — FAIL {#c3}

| threshold | qualifying terms |
|---|---:|
| appears in >= 2 distinct zero-result queries | 28 |
| >= 3 | 9 |
| >= 5 | **1** |

One term at the registered threshold, against a bar of five. And the nine at
`>= 3` are not knowledge gaps:

```
set_flag_by_selector (5)   grep_backstop (4)   project_memory_compile_shipped#root (4)
.local.md (4)              snapshot-tier (3)   <task-notification> (3)
commit-state (3)           MUTATION (3)        make_daemon (3)
```

`project_memory_compile_shipped#root` is an anchor id. `.local.md` is a filename
fragment. `<task-notification>` is harness noise. `->` reached the top twelve.

## The real finding {#finding}

The confound is not self-suppression. It is that **`query.log` records what the
agent grepped for, not what the corpus was asked and failed to answer.** The
dominant zero-result sources are `grep-replica` (206) and `scan-prompt` (174) —
a literal-pattern search that legitimately misses, and an always-on hook firing
on every prompt including "yes" and "go". Neither is a question the memory was
asked.

Three and a half months of production telemetry yield one term at threshold.
That is not a tuning problem.

## What would change the verdict {#would-change}

Not a lower threshold — that is how a fitted result gets shipped. The detector
needs a signal that distinguishes *asked* from *typed*:

1. **A retrieval-intent marker.** `RMX_INVOCATION_SOURCE` already separates
   `hook` from `eval` from a direct call; `query.log` does not carry it. Adding
   it, then re-running this check on a fresh span, is the cheapest next step.
2. **Answer-usefulness, not cardinality.** A query returning 20 rows nobody
   used is a better miss than one returning zero. The helix layer already
   timestamps retrievals; joining on whether a hit was subsequently read is the
   signal `cardinality == 0` is standing in for.

Both are follow-ups, registered in `workflow/deferral_registry.md`. Neither is
in plan 8.

## Disposition {#disposition}

- `brief/unanswered` is **not implemented**. No partial detector, no flag-gated
  stub — the CLAUDE.md no-mocks rule forbids the facade and this document is the honest
  alternative.
- Plan 8 ships with four classes: `corroborated`, `singleton`, `contradicted`,
  `orphan-concept`.
- Task 8.4 closes as a completed measurement with a negative result.
