---
gmd: "0.1"
id: refmatrix/partition-layout-survey
title: "Fleet partition layout survey — four shapes, six orphans, and 143MB of vectors for partitions that do not exist"
tags: [architecture, partitions, fleet, survey, sessions]
metadata:
  node_type: survey
  created: 2026-09-20
  version_surveyed: "0.72.4"
---

# Fleet partition layout survey {#root}

Read-only survey of every store the hub supervises plus the benchmark stores, taken 2026-09-20 on
0.72.4 through `rmx partition list` / `rmx -p <name> stats` / the on-disk `vectors/` directories.
No store was modified. {#root-lead}

rel: derives-from -> [[project_partitions_canon]]
rel: related-to -> [[project_shared_memory_daemon_plan]]
rel: amends -> [[plan-13-cross-partition-sweep]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

## The canonical shape, as the code defines it {#canonical}

Post-0.5.0 the project partition holds code, docs AND memory in one partition; the split into
`memory-<project>` was REVERSED because it made cross-partition wikilinks unresolvable and
memory→memory `rel:` edges silently dropped (`cli.py:9736`). Sessions are separate by design and
excluded from the concept graph ([[feedback_operational_content_not_in_graph]]). So a project store
should carry exactly two partitions: {#canonical-lead}

```
<project>            active — code + docs + memory
sessions-<project>   turn-level session cards, excluded from the durable graph
```

and the global store exactly one (`global`), memory-only since 0.65.0.

## What is actually there {#actual}

| store | partitions | canonical? | vectors present |
|---|---|---|---|
| refmatrix | `refmatrix`*, `sessions-refmatrix`, **`memory-viascope`** (0 rows), **`test_session_list_shows_ingest0`** (0 rows) | 2 orphans | `refmatrix`, **`memory-refmatrix`** (14M, no such partition), `memory-viascope` (0B) |
| global (`~/.refmatrix`) | `global`*, **`tholley`** (0 rows) | 1 orphan | `global` |
| viascope | `viascope`*, `sessions-viascope`, **`local`** (0 rows) | 1 orphan | `viascope`, `sessions-viascope` (233M), **`memory-viascope`** (108M, no such partition) |
| cliquet | `cliquet`*, `sessions-cliquet` | **yes** | `cliquet` only — sessions NOT embedded |
| cliquedb | `cliquedb`*, `sessions-cliquedb`, **`global`** (0 rows) | 1 orphan | `cliquedb`, **`memory-cliquedb`** (21M, no such partition) |
| orderly | `orderly`* | **no sessions partition** | **none at all — never embedded** |
| atldb | `atldb`*, **`global`** (0 rows) | no sessions, 1 orphan | `atldb` |
| thiquet | `thiquet`* | no sessions partition | `thiquet` |
| memaware (benchmark) | `memaware`* | n/a — see [[#benchmarks]] | `memaware` |

`*` = active partition. Bold = anomaly.

## Four findings {#findings}

### 1. Six orphan partition registrations, one of them from a test {#orphans}

`test_session_list_shows_ingest0` is a TEST FIXTURE NAME registered in this project's live catalog.
`memory-viascope` is registered inside **refmatrix's** store — another project's memory partition
name. `global` is registered inside cliquedb's and atldb's stores; `local` inside viascope's;
`tholley` inside the global store. All six hold **zero rows**. They are catalog rows a reader must
scroll past, and `rmx partition list` is how an operator answers "what is in this store". {#orphans-lead}

### 2. ~143MB of vectors for partitions that no longer exist {#orphan-vectors}

`refmatrix/vectors/memory-refmatrix` (14M), `viascope/vectors/memory-viascope` (108M) and
`cliquedb/vectors/memory-cliquedb` (21M) are Lance datasets for the `memory-<project>` split that
was reversed post-0.5.0. Nothing in the catalog points at them. They are not merely dead weight:
a reader of `vectors/` would conclude those partitions exist. {#orphan-vectors-lead}

### 3. Session coverage is 4 of 8, and dense coverage is 1 of 4 {#sessions}

`sessions-<project>` exists on refmatrix, viascope, cliquet and cliquedb; **orderly, atldb and
thiquet have none.** Of the four that have one, only **viascope's is embedded** (233M of vectors).
{#sessions-lead}

**This corrects a claim made in plan-13 earlier today.** That plan states the session partition has
no vectors "and none is coming", generalising from refmatrix's store — where it is true — to the
fleet, where it is false. viascope's session partition carries 233MB of dense vectors. The accurate
statement is: **dense availability of the session leg varies per store, and a sweep that assumes
either answer is wrong on some fleet member.** How viascope acquired them (an explicit
`-p sessions-viascope embed`, or an older embed pass) is not established by this survey.

Session partition CONTENT also differs in shape: refmatrix's holds 66 memory rows; viascope's holds
155 memory rows **plus 40 docs**. A `doc` row in a sessions partition is a third shape.

### 4. orderly has never been embedded {#orderly}

27 code + 79 doc + 4721 concept + 1 memory row, and **no `vectors/` directory at all**. Every dense
retrieval against orderly returns nothing, silently — symbolic surfaces work, so nothing reads
broken. {#orderly-lead}

## Benchmarks are a fifth shape {#benchmarks}

`memaware` is a single partition holding 1307 chat documents as `kind=memory` in the store's DEFAULT
partition. Production puts chat in `sessions-<project>` where four gates exclude it from `context`
(`_is_session_card`, `consolidate._OPERATIONAL_RE`, `pagerank._OPERATIONAL_RE`,
`scan._is_operational_anchor`). So the benchmark measures a topology no project runs, and the
favourable one — see [[task-13.0-two-partition-kill-shot#reencode]], which measures that gap.
{#benchmarks-lead}

## What this costs {#cost}

- **A cross-partition feature cannot be specified against "the" layout**, because there isn't one.
  plan-13 was written twice against two different stores' shapes and was wrong both times about
  what the fleet holds.
- **An operator cannot read a store's shape and trust it** — six of the partition rows are noise
  and three vector directories describe partitions that do not exist.
- **Retrieval quality varies per store for reasons no surface reports**: orderly has no dense half
  at all; three stores have no session history; one has session vectors nobody else has.

## Proposal {#proposal}

`project_shared_memory_daemon_plan` already names the first step as **P0: `rmx partition audit`
(READ-ONLY)**. This survey is that audit run by hand, and it argues for shipping it: {#proposal-lead}

1. **`rmx partition audit`** — per store: partitions with row counts, orphan registrations (0 rows,
   no vectors, not the active or sessions partition), vector directories with no matching partition,
   and a canonical-shape verdict. Read-only, no repair.
2. **`rmx partition audit --repair`** — separately, later, and never on a live catalog without a
   backup ([[claude#permissions]]): drop orphan registrations, remove orphan vector directories.
3. **A canonical-shape test in the fleet health surface**, so a store that drifts says so rather
   than waiting for a survey.
4. **Decide the session question once**: either every project store carries `sessions-<project>`
   and it is embedded, or none does and `rmx session recall` is symbolic by design. Today it is
   four different answers, and plan-13's session leg cannot be specified until it is one.

## Remediation, 2026-09-20 (0.72.6) {#remediation}

Run with `rmx partition audit --fleet` + `rmx partition drop`, after both shipped. Every step was
backed up first. {#remediation-lead}

| action | result |
|---|---|
| global store code/doc rows dumped | 134 rows (14 code, 120 doc) — **all `$HOME`-crawl leftovers**, every source file still on disk; backed up to `~/.refmatrix-backups/2026-09-20/global-code-doc-rows.json`. Global is now `memory 200 + concept 62776` |
| orphan registrations dropped | 6 of 6 — `tholley`, `local`, `global`×2, `test_session_list_shows_ingest0`, `memory-viascope` |
| orphan vector directories removed | 4 dirs, **143MB** reclaimed; moved to a backup, dense recall verified on viascope and orderly, then deleted |
| `orderly` embedded | `embedded=4828` — its dense half had never existed |
| fleet shape | **5 of 8 canonical** (global, refmatrix, cliquedb, cliquet, viascope) |

**The drop guard earned itself on the first run.** `memory-viascope` was REFUSED because
`vectors/memory-viascope` still existed on disk — dropping the registration would have manufactured
the orphan-vectors finding the audit reports. Moving the vectors first, then dropping, is the
correct order and the tool enforced it rather than trusting the operator to remember.

**21 of the dumped doc rows are other projects' memory-dir `.md` files ingested as `doc` instead of
`memory`.** The disk files are untouched; they should return through the memory bridge as
`kind=memory`. {#remediation-memory-rows}

## The ADR is wrong about one thing, found by remediating {#missing-sessions-severity}

`thiquet`, `atldb` and `orderly` still read `drift` for `missing-sessions`, and **it cannot be
fixed**: their `~/.claude/projects/` transcript directories exist and hold **zero JSONL files**.
Those projects have no Claude Code history, so there is nothing to ingest. {#missing-sessions-lead}

A store that reads drift forever for a condition it cannot remedy trains the signal away — which is
the exact argument [[adr-0003-canonical-partition-layout#deferred-embed]] uses to make
`sessions-unembedded` an `info`. **Proposed amendment:** `missing-sessions` is `drift` when session
transcripts EXIST for the project and `info` when they do not. The `gather` side already reads the
filesystem and can supply `sessions_available`; the pure `audit()` keeps taking facts.

Not applied unilaterally: it changes what "canonical" means, which is the ADR's whole job.
