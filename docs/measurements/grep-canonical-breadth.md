---
gmd: "0.1"
id: refmatrix/grep-canonical-breadth
title: "bug-070: narrowing the canonical grep predicate — four arms, one that costs nothing"
tags: [measurement, grep, learning, index, precision, bug-070]
metadata:
  node_type: measurement
  created: 2026-10-06
  verdict: "ship the trailing-segment anchor; reachability identical, `error:` 26 concepts -> 5"
---

# bug-070: how wide should the canonical grep match be? {#root}

rel: derives-from -> [[refmatrix/grep-learning-replay]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]
rel: related-to -> [[project_grep_learning_measured]]

## The question {#question}

bug-067 made `Store.grep_evidence` also consult `canonical_name`, which is what
lets a LEARNED `query/roaring bitmap` be found by the query that created it. It
did that with a SUBSTRING predicate, and on a short punctuated pattern that
substring joins a whole family: `canonicalize_name('error:')` is `error`, and
`canonical_name ILIKE '%error%'` matches every `error`-ish concept. bug-070 is
that breadth — "a caller who asked for a narrower thing now gets the family" —
and the row refused to retune it in the session that measured it, because the
same predicate also bought reach and the decision needed BOTH numbers. {#q-body}

## What was measured, and what was deliberately not {#method}

Two instruments, both on the production read path. `Store.grep_evidence` is THE
index-backed grep read — bug-067 collapsed three divergent copies into it, and
the daemon op plus both CLI branches call it. {#method-lead}

- **Breadth / reach** — `eval/production/grep_evidence_breadth.py`, 16 patterns
  (bug-070's four outliers, eight multi-word spellings the same predicate
  reaches, four single-token controls) against ONE store built from `src` +
  `docs` through the production ingest. All four arms read the SAME store: a
  rebuilt corpus would make them differ in more than the predicate. {#m-breadth}
- **Reach on the real workload** — `eval/production/grep_learning_replay.py
  --reachability --repeated-only`, this project's own 132 repeated grep
  patterns, teach → drain → grep again per pattern. {#m-reach}

**Precision against a literal `rg` control was tried and discarded.** The first
version of the breadth script scored it and reported 0.000 for every multi-word
pattern — BY CONSTRUCTION, because the bridge's whole job is to answer a
space-spelled query from underscore-spelled evidence, so the evidence lines do
not contain the literal. That number would have indicted the mechanism it was
built to protect. Precision stays measured where it means something: the replay
harness scores LEARNED `query/*` rows, whose evidence came from a floor result
and does contain the literal. {#m-not}

## Four arms {#arms}

| arm | predicate | patterns answered | index rows | concept draws | `error:` concepts |
|-----|-----------|------------------:|-----------:|--------------:|------------------:|
| **A** (HEAD) | `canonical_name ILIKE '%canon%'` | 16/16 | 584 | 128 | **26** |
| **B** | `canonical_name = canon` | **6/16** | 423 | 68 | 0 (no answer) |
| **C** | `name = canon OR name ILIKE '%/canon'` | 15/16 | 507 | 77 | 1 |
| **D** | `canonical_name = canon OR canonical_name LIKE '%\_canon'` | 16/16 | 518 | 86 | **5** |

Per-pattern rows are in `eval/production/results/grep_learning/bug070-breadth-*.json`.
{#arms-table}

**B fails because concept canonical names are NAMESPACE-PREFIXED.** The concept
is `keyword/roaring_bitmap`, whose `canonical_name` is `keyword_roaring_bitmap`
— so `= 'roaring_bitmap'` matches nothing and ten of sixteen patterns lost their
index answer outright. The reach bug-067 bought would have gone with it. This is
the hypothesis the measurement killed; it was the obvious one, and arguing it
from the predicate's shape would have shipped it. {#arm-b}

**C fails on one pattern, and the one matters.** Anchoring on `c.name`'s
post-slash tail loses `replica bundle`, whose concept is
`keyword/_replica_bundle` — a leading underscore the name carries and the
canonical form folds away. {#arm-c}

## The gain side is unchanged {#reach}

Arm D against arm A over the 132-pattern reachability workload, same corpus,
same drain, one bit different:

| metric | A (substring) | D (trailing segment) |
|--------|--------------:|---------------------:|
| patterns | 132 | 132 |
| first-call `answered_by=index` | 42 | **42** |
| taught something | 46 | **46** |
| second-call `answered_by=index` | 78 | **78** |
| scored for precision | 38 | **38** |
| precision median | 1.000 | **1.000** |
| precision < 0.6 | `timeout` 0.50 | `timeout` 0.50 |
| index rows over scored patterns | 301 | **301** |

Identical on every metric. The narrowing costs nothing the instrument can see.
Raw: `bug070-reach-A-substring.json`, `bug070-reach-D-tail-segment.json`. {#reach-table}

## Verdict {#verdict}

Ship arm D. `error:` draws 5 concepts instead of 26, every spelling bridge
survives, and the reachability numbers do not move. {#verdict-body}

## What this does NOT fix, stated so the row is not read wider {#limits}

`ERROR` and `timeout` are unchanged — 74 rows / 26 concepts and 26 / 6 in BOTH
arms. Their breadth comes from the OTHER predicate, `c.name ILIKE '%pattern%'`,
which is the pre-bug-067 contract and is what gives the loop its reach on
unpunctuated tokens. bug-070's row already recorded that this breadth is older
than bug-067's fix (`ERROR` returned 62 rows with the canonical predicate and 62
without). Narrowing it is a separate decision with its own trade, and the
registry's other candidate — capping how many DISTINCT concepts one lookup may
draw from — applies to that predicate, not this one. Pinned by
`test_the_name_predicate_breadth_is_deliberately_unchanged`. {#limits-body}

## Reproduce {#repro}

```bash
# build the breadth store once (~55 s), then read it per arm
eval/production/grep_evidence_breadth.py --build --root /tmp/b070
eval/production/grep_evidence_breadth.py --root /tmp/b070 --out A.json
# reachability on the real workload (~3 min per arm)
eval/production/grep_learning_replay.py --reachability --repeated-only --out reach.json
```

Commit the predicate before mutating it: the mutation loop reverts with
`git checkout --`, which restores HEAD and silently discards an uncommitted
arm — it did exactly that here, and two mutations reported a pass they never
ran. {#repro-note}

rel: reinforces -> [[feedback_commit_before_mutation_revert]]
