---
gmd: "0.1"
id: bsd-plan13-cross-partition-sweep-0cb8b1a
title: "plan-13 pre-build audit — the arbiter cannot see the mechanism, and the motivating number is two versions stale"
severity: BULLSHIT
plan: plan-13-cross-partition-sweep
task: "(pre-task — status drafting, no task specs yet)"
tags: [bsd, plan-13, retrieval, fusion, partitions, memaware]
---

# ch-bsd findings — plan-13 cross-partition fusion sweep (plan audit, not a commit range) {#root}

**Target:** `workflow/plans/plan-13-cross-partition-sweep.md` (`metadata.status: drafting`)
**Tree:** `0cb8b1a` on `bug-053-inflight-registry`
**Date:** 2026-09-20
**Author of target:** Todd Holley / Opus 5 (1M) / orchestrator
**Production code for plan-13:** none — `rmx grep -E "def sweep|rmx_sweep"` over `verbs.py`/`cli.py`
returns no matches, and `workflow/plans/plan-13-cross-partition-sweep-tasks/` does not exist. The
`plans-pre-written` gate is clean. {#preamble}

The question is shifted one stage earlier than usual: not "does this code run" but "can this plan's
claims be checked, do its primitives exist as cited, and can its acceptance criteria tell success
from the status quo". Three of those answer no. {#preamble-question}

rel: contradicts -> [[claude#plans-pre-written]]
rel: derives-from -> [[project_memaware_benchmark]]

## Findings {#findings}

### BULLSHIT: the pre-registered arbiter has ONE partition, so the mechanism under test cannot fire {#b-1}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:131` (`#acceptance`), against
`eval/memaware/paths.py:44` and `eval/memaware/ingest.py:77-88`

**What:** The primary criterion is "MemAware Layer A, same 90 questions, same harness", and the plan
is accepted or rejected on it.

**Why it's bullshit:** The MemAware store is a single partition holding a single kind.
`eval/memaware/paths.py:44` pins `PARTITION = "memaware"`, and the whole corpus enters through one
command (`eval/memaware/ingest.py:83`):

```
rmx ingest-gmd --as-memory --memory-mtype memaware/session $CORPUS
```

All 1307 documents land as `kind=memory` in partition `memaware`. There is no code partition (no
`refmatrix.ingest` pass ever runs on that store), no doc partition (`--as-memory` makes them memory
rows), and no `sessions-memaware` partition. Of the four legs in `#legs`, three are empty by
construction and the fourth — `hybrid_memory_recall` — IS the existing `recall` condition. The sweep
on this harness is `rmx memory recall` with fusion against nothing.

That makes the criterion undiscriminating in both directions. **FAIL is guaranteed and
uninformative**: hit@20 lands at the recall row (0.378, or 0.422 with rerank per
`eval/memaware/REPORT.md:22`), below the 0.444 FAIL line, and the plan would record "the union does
not change the reachable set on this corpus" as a negative when the union never ran — the plan's own
`#risks` line "Fusion hides a broken leg" applied to the entire experiment. **PASS is unreachable by
the claimed mechanism**: any gain would have to come from re-composing one partition's candidates,
i.e. reordering — the exact thing `#why-this` says this plan is not.

**Evidence:**
```
eval/memaware/paths.py:44   PARTITION = "memaware"
eval/memaware/ingest.py:83  run([args.rmx, "ingest-gmd", "--as-memory",
                                 "--memory-mtype", "memaware/session", str(CORPUS)], ...)
eval/memaware/ingest.py:86  run([args.rmx, "embed", "--kinds", "memory"], ...)
```
`store.py:257-272` — `entities.kind CHECK (kind IN ('doc','code','concept','memory'))`; nothing on
that store is `code` or `doc`.

**Fix:** Either (a) name a primary arbiter that HAS ≥2 populated partitions — refmatrix's own store
plus its `sessions-refmatrix` partition, with a known-item question set — and pre-register on that,
or (b) extend the MemAware build to plant a second partition and say exactly what goes in it. Until
one of those is written down, the plan has no arbiter and cannot reach `approved`.

**Pattern match:** YES — [[impression_bsd_existence_check_tests]] (a gate that cannot observe the
thing it gates) and the `#risks` entry the plan wrote about its own legs.

rel: contradicts -> [[claude#quality-gates]]

### BULLSHIT: the motivating number is two minor versions stale and understates the surface by 89% {#b-2}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:35-49` (`#context-numbers`)

**What:** The plan's table gives `rmx scan-prompt` hit@20 **0.200**, MRR@20 **0.043**, labels the
whole table "at 0.36.0", and concludes in bold: "The weakest surface is the one that ships on every
prompt."

**Why it's bullshit:** Those are the PRE-FIX figures, and the source document says so under a
heading that names the fix. `eval/memaware/REPORT.md:128-133`:

```
## scan-prompt (0.37.0) — before and after
| hit@20 overall | 0.200 | **0.378** |
| MRR@20 overall | 0.043 | **0.149** |
```

The live rows are `REPORT.md:21` (hit@20 **0.378**) and `REPORT.md:34` (MRR@20 **0.149**), re-measured
unchanged at 0.42.0 (`REPORT.md:202-205`). `docs/PERFORMANCE.md:287-288` carries both as separate
rows — "`rmx scan-prompt` at 0.36.0 | 0.200 | 0.043 | starting point" and "`rmx scan-prompt` now | —
| **0.241** | content fusion + bodies + rerank ≈ BM25 parity". The plan quotes the row explicitly
labelled "starting point" as the current state.

Two consequences. First, the headline gap is fiction: 0.200-vs-0.444 is a 2.2x deficit; the live
comparison is 0.378 vs 0.444 on hit@20 and **0.241 vs 0.242 on MRR — parity**. Second, scan-prompt
is not "the weakest surface": at 0.378 it ties `rmx memory recall` and `--fuse` exactly.

The attribution is also wrong in the other direction. Four of the five rows (bm25 0.444/0.242,
context 0.433/0.153, recall 0.378/0.180, bm25-per-day 0.156) match REPORT.md's 0.37.0 table
verbatim; only the scan-prompt row is 0.36.0. The table is labelled "at 0.36.0" and is mostly
0.37.0, with the one genuinely-0.36.0 row being the one the plan is built on.

**Fix:** Requote from `eval/memaware/REPORT.md:21,34` and `docs/PERFORMANCE.md:284-290`, restate the
gap as MRR parity plus a 0.066 hit@20 deficit, and rebuild the motivation on the deficit that is
actually there. If the motivation does not survive the correct numbers, that is the result.

**Pattern match:** YES — [[feedback_read_identifiers_at_write_time]] and my own
[[bsd-impressions#imp-i-did-it-too]]: a number carried from a prior message instead of re-read from
the file at write time.

rel: contradicts -> [[feedback_read_identifiers_at_write_time]]

### BULLSHIT: the PASS bar is already cleared today, by one surface, with no union {#b-3}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:133-134`

**What:** "**PASS** — sweep hit@20 ≥ 0.50 (beats the best single surface, 0.444, by ≥ 0.05 absolute)
AND MRR@20 ≥ 0.242 (no worse than upstream bm25)."

**Why it's bullshit:** `docs/PERFORMANCE.md:286` records `rmx context` (+lead signal) at hit@20
**0.511**, MRR@20 **0.248** — "+35% hit@20 from lead alone". Both PASS conditions are met **today**,
by a shipped single-partition surface, on the same 90 questions. A sweep scoring exactly 0.50 would
be recorded PASS while regressing 0.011 hit@20 against what `rmx context` already returns.

The reference the criterion names — "the best single surface, 0.444" — is bm25-per-session, an
UPSTREAM baseline, not an rmx surface, and it is no longer the best of anything. The plan's own table
also omits the `recall +rerank (0.42.0)` row at 0.422 (`REPORT.md:22`), which matters for a second
reason: `REPORT.md:202-203` states that `scan-prompt` and `context` do NOT run the reranker but
`memory_recall` does. A 4-leg sweep whose memory leg is `hybrid_memory_recall` inherits the rerank
stage, so a measured gain is attributable to rerank rather than to the union — and the plan has no
arm that separates them.

**Fix:** Set the bar against 0.511 / 0.248 and re-derive the margin; add a `--no-rerank` arm so a
PASS can be attributed to the union rather than to the cross-encoder.

**Pattern match:** YES — [[impression_bsd_cost_measured_idle]] (a threshold set against a number
taken from the wrong condition).

rel: contradicts -> [[project_helix_phase2_decision_criterion]]

### BULLSHIT: "the leg that does not exist yet" shipped, with turn-level content, in its own partition {#b-4}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:97-105` (`#session-gap`), and `:91`, `:178`

**What:** The plan states "Session transcripts are currently STM (a per-session ring, promoted as a
`session/digest` memory) — a digest is not the turn-level content MemAware questions ask about", and
task 13.4 is "the session leg — turn-level session rows".

**Why it's bullshit:** Every piece of that leg is in the tree.

- `src/refmatrix/session_ingest.py` (295 lines) parses Claude Code session JSONL into GMD cards
  carrying **per-turn user prompts** (`MAX_PROMPT_LEN = 600`, line 24) and **per-turn assistant
  decisions** (`MAX_DECISION_LEN = 1200`), rendered as `## User prompts {#prompts}` and
  `## Assistant decisions {#decisions}` sections by `build_card`. That is turn-level content, not a
  digest.
- `src/refmatrix/cli.py:11901-11908` — the `session` command group's own docstring: "Ingests session
  JSONLs from `~/.claude/projects/` into a dedicated **sessions-`<project>` partition**."
- `src/refmatrix/cli.py:12034-12046` routes the cards through `ingest_gmd` with
  `as_memory=True, memory_mtype="session", partition=_sessions_partition_default()`.
- Retrieval surfaces already exist: `rmx session recall|show|list|stats`
  (`cli.py:12192, 12348, 12394, 12459`), with `_session_call` auto-pinning the sessions partition
  (`cli.py:12386`).
- It is wired into the maintenance path (`cli.py:6869`, `step("3/5 sessions", …)`) and scheduled
  (`src/refmatrix/session_launchctl.py`).

The cross-partition reach the plan proposes to build also partly exists. `store.py:2185`
`find_memory_any_partition` — "Resolve a memory by NAME across ALL partitions … Used by `rmx context`
to pull a mention neighbor's parent-doc body when that body lives in a different partition than the
anchor (e.g. session cards live in `sessions-<project>` while the co-mention concept resolves in the
project's memory/code partition)". And `pagerank.py:255-262` had to filter session-card concepts
**globally** precisely because "a code partition's `mentions` fragment can carry cross-partition
edges to session-card concepts that live in the `sessions-<project>` partition".

What actually stands between `rmx context` and a session answer on the live store is a default-false
boolean: `context.py:346` `if not include_sessions and _is_session_card(ent.name): continue`, where
`_is_session_card` is `name.startswith("session-")` (`context.py:1213`), with the comment at
`context.py:343-345` — "by default keep them out of the durable concept graph so specs / code / ADRs
aren't drowned out. `rmx session recall <term>` is their home."

To be precise about scope: that filter does **not** confound the MemAware numbers — MemAware docs are
named `answer_*`, so `_is_session_card` never matches them. The claim this finding makes is about the
product, which is what 13.4 proposes to build.

**Fix:** Rewrite `#session-gap` to say what is true (the substrate, the partition, the CLI and the
default-off filter all ship), retarget 13.4 from "land session rows" to "measure the shipped
`sessions-<project>` partition, and decide whether `include_sessions` should default true for which
surfaces", and add the cheap experiment that plan should have opened with — run the Layer A harness
against a store that has both partitions.

**Pattern match:** YES — [[bsd-impressions#imp-two-paths]]: a second way to do X, proposed as if the
first did not exist.

rel: contradicts -> [[claude#no-workarounds]]

### BULLSHIT: "Rank, never score" is a measured negative on the corpus of the plan's own secondary criterion {#b-5}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:78-82` (`#principle-rank`) and `:141-143`

**What:** "**Rank, never score.** … RRF consumes ORDER, which is why it is already the project's
fusion primitive. A plan that normalised scores across partitions would be inventing a calibration
nobody measured." The secondary criterion then defends CSN MRR@10 0.961.

**Why it's bullshit:** Score summation across sources is not an uninvented calibration — it is the
shipped stack, and it is what produces the 0.961 the secondary criterion defends.
`eval/production/csn_code.py:158` ranks with `s.content_rank(terms, kinds=["code"], limit=…)`, the
BM25-summed path. `project_rrf_landed` records the head-to-head explicitly:

> **Where RRF was SUPERSEDED**: NL→code retrieval on csn_python. The current best stack
> (`bm25_docstring30_cov30_cm20`) BM25-sums per-linkage scores instead of fusing ranks. RRF over
> per-token TF lists was the baseline (0.28 MRR@10). BM25 summation hits 0.97.

`docs/PERFORMANCE.md#negatives` carries the same verdict at the surface level: "RRF dense⊕symbolic
recall fusion as default | dense 0.848 vs fused 0.794 MRR@10 | fusion wins Recall@10 (+0.143) and
nDCG (+0.095) — right for set-oriented surfaces, wrong for top-1; `--fuse` stays opt-in."

And on the plan's PRIMARY corpus, the same fusion is already measured as a null.
`eval/memaware/REPORT.md:64-67`: "**`--fuse` is a no-op at this scale.** Identical scores; the two
ranking files differ on 1 question of 90. Consistent with the prior finding that RRF fusion's win is
a scale effect." `REPORT.md:207-209` confirms it held after 0.42.0.

So the plan's core primitive has been measured twice and rejected as a default once, on both of the
plan's own corpora, and the plan cites `project_retrieval_negatives_2026_09` only as
`rel: related-to` (line 25) without engaging with any of it. Under `docs/PERFORMANCE.md#negatives`
("Measured negatives — do not re-derive these") this is a re-derivation.

**Fix:** State why this application of RRF escapes the recorded negative — the honest argument
available is that cross-partition scores genuinely are incomparable while intra-partition ones are
not, which is a narrower claim than `#principle-rank` makes — and pre-register the score-summed arm
as a second condition rather than ruling it out in prose. If the sweep's code leg is RRF-fused, say
what protects the 0.961.

**Pattern match:** YES — this repo closes ideas as negatives and then re-proposes them under a new
name; that is exactly what the negatives table exists to prevent.

rel: contradicts -> [[project_retrieval_negatives_2026_09]]

### SKETCHY: the dedupe rationale is not true of `fuse_rrf`, and the real double-count is elsewhere {#s-1}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:107-113` (`#dedupe`)

**What:** "RRF sums `1/(k + rank)` across lists, so three copies of one answer outrank a single copy
of a better one — the fusion would reward duplication and call it consensus."

**Why it's sketchy:** `query.py:45-49` sums per **entity id**:

```python
for lst in ranked_lists:
    for rank, eid in enumerate(lst):
        scores[eid] = scores.get(eid, 0.0) + 1.0 / (k + rank)
```

`entities.id` is a store-global `INTEGER PRIMARY KEY AUTOINCREMENT` with
`UNIQUE(partition_id, kind, name)` (`store.py:256-272`), so a decision written in a session, saved as
a memory and quoted in an ADR is three DIFFERENT ids in three partitions. RRF never sums them; each
gets `1/(k+rank)` in its own list and they tie rather than outrank. The harm is real but it is top-k
**crowding** — three of twenty slots spent on one answer — not rank inflation. The proposed fix
(collapse to canonical identity before fusion, keep the best-ranked instance) is right for crowding;
the stated mechanism is not the one in the code.

There IS a genuine double-count the plan creates and does not notice: `#legs` splits ONE partition
into a "code" leg and a "docs" leg ("same pass; separated from code only for per-leg caps"). Two legs
drawing from the same candidate pool CAN return the same id, and there RRF does sum — inflating an
entity purely because of an arbitrary leg split.

Precedent the plan should cite: `verbs.merge_scope` (`verbs.py:375-399`) already dedupes a two-source
union by `name` with a round-robin that guarantees the smaller source representation. That is 13.2's
shipped ancestor.

**Fix:** Restate `#dedupe` as slot-crowding, name the code/docs same-partition double-count as the
case where summation actually bites, and cite `merge_scope`.

rel: contradicts -> [[claude#development-guidelines]]

### SKETCHY: the per-leg diagnostic is not computable from the harness, and the "early kill" is gated behind the build {#s-2}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:145-147` (`#acceptance-diag`) and
`:160-162` (`#risks`)

**What:** "**Diagnostic (must be reported either way):** per-leg contribution — for each question,
which leg produced the winning candidate." The risk section adds: "Measure the per-leg contribution
first (13.5 diagnostic) — it is cheap and it can kill the plan early."

**Why it's sketchy:** The harness discards leg identity before scoring.
`eval/memaware/retrieval_eval.py:75-111` — `_ids()` walks any envelope and keeps "the first
id-looking string per record", returning a flat `list[str]`; every entry in `METHODS` (line 145) is
typed to that contract and `score()` (line 194) consumes `dict[str, list[str]]`. A `leg` field on the
sweep's JSON output would be walked past and dropped. The diagnostic requires a new method contract
(e.g. `list[tuple[str, str]]`) or a sidecar leg map, plus changes in `score()` — and no task in
`#tasks` names harness work.

The ordering is also circular. The diagnostic is 13.5, which sits after 13.1-13.3 in the task table
and requires the verb to exist; 13.4 is gated on 13.5; and the risk section wants the diagnostic
FIRST because it can kill the plan cheaply. As written the cheap early kill costs three tasks.

**Fix:** Add the harness change explicitly to 13.5's scope, and split out a 13.0 that runs the
kill-shot measurement with what ships today — the Layer A harness against a store carrying both a
project partition and its `sessions-<project>` partition, plus `rmx session recall` as a condition.
That is the measurement that can end the plan in an afternoon.

rel: contradicts -> [[feedback_green_tests_are_not_a_working_command]]

### SKETCHY: the "no regression" secondary measures a path the sweep cannot reach {#s-3}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:141-143`

**What:** "**Secondary (no regression):** CSN python/JS/TS through `eval/production/csn_code.py` —
MRR@10 within noise of the recorded 0.961."

**Why it's sketchy:** `eval/production/csn_code.py:158` ranks in-process:

```python
hits = s.content_rank(terms, kinds=["code"], limit=a.top_k)
```

One `Store`, one partition, one kind, no CLI, no verb, no daemon. A new `sweep` verb changes nothing
that harness measures, so the secondary passes unconditionally — it is a constant, not a gate. The
CSN corpus store is also code-only, so even if the sweep were wired in, it would again be a one-leg
sweep (same shape as [[#b-1]]).

Two smaller things in the same sentence: the harness defaults to `--dataset eval/datasets/csn_python`
and labels its output `csn_python` regardless of the dataset passed (line 173), and the cited
production run cost "ingest 1913 s, retrieval 390 s" for ONE language
(`docs/PERFORMANCE.md:235-238`) — "python/JS/TS" is roughly two hours of compute the plan does not
budget.

**Fix:** State how a sweep enters that harness, or replace the secondary with a criterion that can
fail — e.g. defend `content_rank`'s own numbers by asserting the sweep does not modify it, which is a
test, not an eval.

**Pattern match:** YES — [[feedback_measure_the_path_users_run]], inverted: here the harness measures
the production path and the CHANGE is off it.

rel: contradicts -> [[feedback_measure_the_path_users_run]]

### SKETCHY: "Nothing unions them" is false, and the closest prior specification is uncited {#s-4}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:30-33` (`#context-lead`), `:71-76`
(`#principle`)

**What:** "Every retrieval surface rmx ships queries exactly ONE partition. … Nothing unions them."
The primitive list names `hybrid_recall`, `hybrid_memory_recall`, `fuse_rrf`, `memory_partition`,
`default_partition_name`.

**Why it's sketchy:** Every named primitive exists with the cited signature and semantics — that part
checks out (`recall.py:64`, `recall.py:120`, `query.py:33`, `verbs.py:224`, `store.py:223`), and
`hybrid_memory_recall`'s docstring confirms the plan's reading that "the CALLER must already have
`store` bound to the target memory partition". But the survey around them is wrong in both
directions.

A union already ships: `verbs.memory_recall(scope="both")` (`verbs.py:634`) fans out to
`global_recall_rows` (`verbs.py:342`, the hub-owned global store through ITS daemon) and merges with
`merge_scope` (`verbs.py:375`). That crosses a STORE boundary, which matters for the plan's fusion
choice: entity ids are unique within a root but **collide across roots**, so `fuse_rrf` over ids is
safe across partitions of one store and silently wrong across the project/global boundary. The plan
never states that constraint.

The closest prior specification is uncited. `docs/adr/0001-intuition-lance-integration.md:114-115`:
"Memory partition defaults to `intuition`. Cross-partition fusion uses the existing `partition_fuse`
infrastructure", and `:160` lists "Cross-partition fuse defaults on for `rmx memory recall`" as a
Phase B deliverable. `partition_fuse` appears nowhere in `src/` (`rmx grep -rn partition_fuse src/`
→ no matches) and the ADR is still `Status: Proposed` (2026-05-27). `project_partitions_canon` tracks
the same thread and already names the infrastructure gap plan-13 needs: "needs a query engine that
can open additional Stores keyed by partition_id."

Plan-13 has no `rel:` edge to any ADR.

**Fix:** Correct `#context-lead` to "no surface unions the project's own partitions" (which is true),
add `rel: supersedes -> [[0001-intuition-lance-integration#phased-build]]` or an explicit note that
the ADR's cross-partition clause was never built, and state the id-collision rule for cross-store
fusion.

rel: contradicts -> [[claude#graph-markdown]]

### MEH: the cliquedb ceiling numbers are retracted at their source {#m-1}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:58`

**What:** "The cliquedb known-item baseline puts the ceiling at recall, not ranking: hit@1 0.447
against hit@20 0.537."

**Why:** Quoted faithfully from `eval/memaware/REPORT.md:556`, but `docs/PERFORMANCE.md:296-298`
retracts the number: "known-item hit@1 on a healthy store is **0.808** post-re-derive (the earlier
0.447 'ceiling' was pool contamination from the main-path incident)". `project_cliquedb_baseline_post_rederive`
records the same. The 46%-never-retrieved arithmetic the plan leans on is the contaminated run's.

PERFORMANCE.md still endorses the CONCLUSION at the same anchor ("The remaining ceiling is recall,
not ranking"), so the plan's argument survives — its evidence does not, and a reader checking the
pair would find hit@1 0.808 quoted beside hit@20 0.537, which cannot be one run.

**Fix:** Cite `docs/PERFORMANCE.md#memaware-ceiling` and drop the two retracted figures.

rel: contradicts -> [[feedback_read_identifiers_at_write_time]]

### MEH: the primitive list omits the one that constrains the design {#m-2}

**File:** `workflow/plans/plan-13-cross-partition-sweep.md:71-76`, `:149-155` (`#cost`)

**What:** The plan lists the recall/fusion/partition-resolution primitives but not the mechanism by
which one Store actually addresses a second partition.

**Why:** `Store.with_partition(name)` (`store.py:1590`) is that mechanism, and its docstring carries
the constraint the plan needs: "Not safe under concurrent ops on the same Store — wrap with
`d._store_lock` at the daemon op layer." Consequences the plan does not name:

1. The lock-free read path cannot serve a second partition. `search.cached_replica(root)`
   (`search.py:38-55`) is cached per ROOT and opens `Store(root, partition=discovery.store_name(root),
   read_only=True)` — one partition, fixed. Every leg outside the default partition is a daemon op.
2. Four daemon ops against one daemon serialize on `_store_lock`, so the sweep's wall clock is the
   SUM of its legs, not the max — the shape already filed as bsd-plan2-r5 #b-1 and
   [[bsd-impressions#imp-fleet-sum-timeouts]].
3. `daemon.call` defaults to `retries=2`, tripling a per-leg timeout
   ([[feedback_daemon_call_retries_multiply_timeouts]]).

`#cost` does the right thing in principle — one deadline, a missed leg DROPPED and COUNTED — but does
not say `retries=0` or acknowledge the serialization, and this family has been filed twice before.
If 13.1's spec ships without both, escalate to SKETCHY.

**Fix:** Name `with_partition`, the replica's single-partition pinning, and `retries=0` under one
shared deadline, in 13.1.

rel: contradicts -> [[feedback_daemon_call_retries_multiply_timeouts]]

### MEH: plan-13 is not in `workflow/plan-of-plans.md` {#m-3}

**What:** `CLAUDE.md#planning-task-docs` makes `plan-of-plans.md` the head of the source-of-truth
chain, and `CLAUDE.md#session-start` step 2 says to read it for what to implement next. The table
(`workflow/plan-of-plans.md:30-31`) jumps 10 → 12; neither plan-11 nor plan-13 has a row.

**Fix:** Add rows for 11 and 13 with their `metadata.status`.

rel: contradicts -> [[claude#planning-task-docs]]

## What checks out {#clean}

Recorded so the findings are not read as "everything is wrong": {#clean-lead}

- All five named primitives exist with the cited signatures and the cited semantics —
  `recall.hybrid_recall` (`recall.py:64`), `recall.hybrid_memory_recall` (`recall.py:120`, whose
  docstring independently confirms the plan's caller-binds-the-partition reading),
  `query.fuse_rrf(ranked_lists, k=60)` (`query.py:33`), `verbs.memory_partition` (`verbs.py:224`),
  `store.default_partition_name` (`store.py:223`), `context.build_context` (`context.py:127`),
  `eval/memaware/retrieval_eval.py`, `eval/production/csn_code.py`.
- Four of the five MemAware rows are quoted verbatim from `eval/memaware/REPORT.md` (bm25 0.444/0.242,
  context 0.433/0.153, recall 0.378/0.180, bm25-per-day 0.156).
- CSN 0.961 traces correctly to `docs/PERFORMANCE.md:228` and its committed artifact.
- No production code exists for plan-13 — `plans-pre-written` is satisfied.
- `#cost`'s drop-and-count discipline and `#risks`'s "a zero is an error line, not an empty list" are
  both correct applications of [[feedback_no_silent_failures]].
- The `#why-this` test — does an idea change the candidate SET or reorder the found one — is the right
  question, and a cross-partition union does change the set. The claim is worth measuring; what this
  audit says is that nothing currently in the plan would measure it.

## Verdict {#verdict}

**DIRTY — 12 findings (5 BULLSHIT, 4 SKETCHY, 3 MEH).**

Plan-13 must not reach `approved`. Two of the five BULLSHIT findings are structural: the
pre-registered arbiter cannot observe the mechanism ([[#b-1]]), and the plan's marquee gap — the
session leg — already ships behind a default-false boolean ([[#b-4]]). Two more are the numbers the
plan is argued from ([[#b-2]], [[#b-3]]), and the fifth is the project's own recorded negative
standing against the plan's central principle ([[#b-5]]).

The cheapest path back is a measurement the plan does not contain and which needs no new code: run
Layer A against a store that actually has two populated partitions — refmatrix's own store plus
`sessions-refmatrix` — with `rmx context --include-sessions` and `rmx session recall` as conditions.
If the union pays, that run says so before a verb exists. If it does not, the plan closes for one
report, which is the outcome `#acceptance` already says is acceptable.

rel: contradicts -> [[claude#quality-gates]]
rel: amends -> [[plan-13-cross-partition-sweep#acceptance]]
