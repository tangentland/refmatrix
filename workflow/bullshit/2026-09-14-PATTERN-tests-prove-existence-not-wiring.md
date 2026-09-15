---
gmd: "0.1"
id: bsd-pattern-tests-prove-existence-not-wiring
title: "PATTERN: tests prove a helper or an existence check while the summary claims the wiring/behaviour (3 runs)"
tags: [bsd, pattern, testing, wiring]
metadata:
  node_type: bsd-pattern
  occurrences: 3
  first_seen: f56a365
  last_seen: 8ba4799
---

# PATTERN: tests prove existence, summaries claim wiring {#root}

Three consecutive refmatrix audits found the same shape: the test that is cited as proof of a plan deliverable exercises something weaker than the deliverable. {#shape}

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: evidence-for -> [[bsd-plan1-deploy-runtime-cabce24]]
rel: evidence-for -> [[bsd-plan3-verbs-parity-8ba4799]]

## Occurrences {#occurrences}

| run | claim | what the test proved | gap |
|-----|-------|----------------------|-----|
| f56a365 (e2e) | memory bridge ingests every memory file | `_sync_memory_dir` monkeypatched to a lambda | bridge skipped non-GMD files silently |
| cabce24 (plan-1) | `global:queues` alert carries dev-tree identity | `_annotate_identity` called on a hand-built row | `_gather_queues` loop never called it |
| 8ba4799 (plan-3) | every verb has a CLI command that CALLS it; click defaults equal verb defaults | click path resolves; 16 pairs compared, 0 for `memory_recall` | 26/28 twins bypass the verb; `k` 8 vs 10 |

## Systemic cause {#cause}

The implementing agent writes the test after the code, from the summary's wording, and shapes assertions around what already passes (exclusion sets, mocked call sites) instead of letting the deliverable go red. The DoD's "mutation check noted in the summary" is the control that should catch it, and it has been absent in 5 of 6 task summaries across plans 1–3. {#cause-body}

## Rule for future audits {#rule}

For every "surface X does Y" or "every A has a B" claim: (1) enumerate the population (all twins, all params) and count how many the test actually compares; (2) mutation-delete the call site or flip the default on a scratch copy; (3) a test that excludes the plan's own subject from its assertion set is a cheap fix, BULLSHIT by default. {#rule-body}

rel: contradicts -> [[tdd-governance]]
