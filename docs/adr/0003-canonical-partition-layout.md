---
gmd: "0.1"
id: adr-0003-canonical-partition-layout
title: "ADR-0003: Canonical partition layout — two per project store, one for global, benchmarks mirror production"
tags: [adr, partitions, fleet, sessions, benchmarks]
---

# ADR-0003: Canonical partition layout {#root}

**Status:** Proposed · **Date:** 2026-09-20 · **Implementation:** `rmx partition audit` (read-only) first

rel: derives-from -> [[partition-layout-survey]]
rel: depends-on -> [[feedback_operational_content_not_in_graph]]
rel: related-to -> [[project_partitions_canon]]
rel: related-to -> [[project_shared_memory_daemon_plan]]
rel: related-to -> [[plan-13-cross-partition-sweep]]
rel: part-of -> [[adr-0000-adr-overview]]

## Context {#context}

A survey of all eight supervised stores plus the benchmark store on 0.72.4 found **four different
layouts, six zero-row orphan partition registrations, and ~143MB of Lance vectors for partitions
that no longer exist** ([[partition-layout-survey]]). One orphan is `test_session_list_shows_ingest0`
— a test fixture name registered in this project's live catalog. Session partitions exist on four
of eight stores and only one of those four is embedded. `orderly` has never been embedded at all,
so every dense retrieval there returns nothing while symbolic surfaces keep working. {#context-lead}

The cost is not tidiness. A cross-partition feature cannot be specified against "the" layout,
because there is none: [[plan-13-cross-partition-sweep]] was written twice against two different
stores' shapes and was wrong both times about what the fleet holds. Nothing in the product reports
drift, so it is invisible until someone surveys by hand.

## Decision {#decision}

### A partition is three things at once, and they must agree {#three-things}

A partition is simultaneously a **BM25 statistics base** (its own `N`, `avgdl`, document
frequencies), a **vector dataset** (`vectors/<name>`), and a **wikilink/`rel:` resolution scope**.
Every layout question is decided by making those three agree. Two consequences follow, and both are
settled by evidence rather than preference. {#three-things-lead}

**Things that cite each other MUST co-reside.** The `memory-<project>` split was tried and reversed
post-0.5.0 *because* it made cross-partition wikilinks unresolvable, so memory→memory `rel:` edges
silently dropped (`cli.py:9736`). Code, docs and memory cite each other constantly. They share one
partition. {#co-reside}

**Things that would distort the statistics MUST NOT.** Session cards are a different genre with
different length and vocabulary distributions, and there are a lot of them: {#isolate}

| store | session concepts | project concepts | inflation if merged |
|---|---:|---:|---:|
| refmatrix | 16,775 | 68,586 | +24% |
| viascope | 57,188 | 76,891 | **+74%** |

Merging viascope's sessions would move idf for every term in that corpus by three quarters of its
mass. Session cards also emit no `rel:` edges (`session_ingest.build_card` writes none), so they
lose nothing by sitting outside the resolution scope. Both tests point the same way: sessions get
their own partition.

**Note what the partition is NOT doing.** Session cards are kept out of the durable concept graph by
NAME, through four independent gates — `context._is_session_card`, `consolidate._OPERATIONAL_RE`,
`pagerank._OPERATIONAL_RE`, `scan._is_operational_anchor`. Graph exclusion and statistical isolation
are different mechanisms that today are easy to conflate. The partition buys the second only.
{#not-exclusion}

### The canonical shape {#shape}

```
<project>/.refmatrix
  <project>            ACTIVE — code + docs + memory
  sessions-<project>   session cards only (kind=memory, `session-<hex>` names)

~/.refmatrix
  global               memory only

<benchmark>/.refmatrix
  <bench>              ACTIVE — the corpus under test
  sessions-<bench>     when the corpus is chat/session material
```

**Exactly two partitions per project store, exactly one for global.** Anything else is drift until
this ADR is amended. {#shape-lead}

### Benchmarks mirror production topology {#benchmarks}

A benchmark whose corpus is chat encodes it the way production does: `session-<hex>` names in
`sessions-<bench>`. The MemAware harness today loads 1307 chat documents as `kind=memory` into the
store's DEFAULT partition under `answer_*` names, where none of the four exclusion gates match — so
every MemAware number rmx has published describes a topology no project runs, and the favourable
one. Today's encoding is retained ONLY as an explicitly labelled control arm
([[task-13.0-two-partition-kill-shot#reencode]]), never as the default. This is the project's own
"the benchmark path IS the production path" rule applied to corpus shape rather than to code path.
{#benchmarks-lead}

### The invariants that keep it {#invariants}

Drift produced every anomaly in the survey, and none of it came from a decision:

1. **A partition is registered only with its first rows, in the same transaction.** A registration
   with zero rows is not a partition; it is a leak. This alone prevents
   `test_session_list_shows_ingest0`, which exists because a test registered a partition and wrote
   nothing.
2. **Only `init` (project) and `session ingest` (sessions) create partitions.** No other path
   registers one.
3. **`vectors/<name>` with no matching partition is an orphan** and is reported.
4. **The shape is checked where an operator already looks** — fleet health — so a drifted store says
   so rather than waiting for a survey.

## What this ADR deliberately does NOT decide {#deferred}

**Whether session partitions are embedded.** viascope's session vectors cost 233MB and nobody has
measured whether that dense half pays. [[task-13.0-two-partition-kill-shot]] measures exactly that.
Embedding the other seven stores first would spend ~1.6GB on an unmeasured bet.
Decide after 13.0. {#deferred-embed}

**Whether memory moves to a user-level shared daemon.** [[project_shared_memory_daemon_plan]]
(decided 2026-06-11, never started) would move memory out of the project partition into a
`project_id`-tagged user store. Today's counts argue for patience: **~1,060 memory rows live in
project stores against 200 in global**, memory co-cites code and docs heavily, and the move
re-creates the two-stat-base fusion problem [[plan-13-cross-partition-sweep]] exists to measure. If
that plan's gate returns STOP, the shared-memory fork inherits the same negative. Decide after 13.0.
{#deferred-shared}

## Consequences {#consequences}

- **Remediation is a repair, not a redesign**: six orphan registrations dropped, three orphan vector
  directories removed (~143MB), three stores gain `sessions-<project>`, `orderly` gets its first
  embed. Every one of those is announced and backed up before it touches a live catalog
  ([[claude#permissions]]).
- **`rmx partition audit` ships read-only first**, which is also the P0 that
  [[project_shared_memory_daemon_plan]] already named. `--repair` is a separate step.
- **[[plan-13-cross-partition-sweep]]'s session leg becomes specifiable**, because "does this store
  have a session partition, and is it embedded" gets one answer per store instead of four across the
  fleet.
- **One open question this ADR surfaces and does not answer**: `rmx stats` on the global store
  reports 120 docs and 14 code rows while a `kind:doc` query there returns zero. Either stats
  aggregates across partitions or the memory-only guard (0.65.0) has been violated. The audit
  answers it; guessing does not. {#open-global}
