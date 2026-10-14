---
gmd: "0.1"
id: plan-review-2026-10-14
title: "Wave 0 spec-review decisions, 2026-10-14"
tags: [plan-review, decisions, wave-0, spec-review]
metadata:
  node_type: review
  created: 2026-10-14
---

# Wave 0 spec-review decisions, 2026-10-14 {#root}

The user, 2026-10-14: "lets review each bsd report and its questions. if it makes sense to cluster
by topic, feel free." The six ch-bsd spec reviews of Wave 0 (plans 16 r5, 17, 19, 21, 22, 23) are
walked topic by topic; every decision is written here the moment it is taken, and the spec
revisions are driven from this file.

rel: amends -> [[plan-review-2026-10-07]]
rel: derives-from -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: derives-from -> [[bsd-plan17-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan19-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan21-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan22-spec-review-3104a81]]
rel: derives-from -> [[bsd-plan23-spec-review-3104a81]]
rel: related-to -> [[exploration-session-phased-context]]

## Topics {#topics}

1. Test isolation (all reports).
2. Write harness and concurrency (plan-23; 17 s-1/s-7; 22 s-1/s-2; Option A).
3. Lance nightly maintenance (plan-17).
4. Recall-event schema (plan-21, shared with 19).
5. Memory budget, recall, phased context and the topic cache (plan-19).
6. Audited removal and repair, with plan-16's 16.6 (plan-22, plan-16 r5).
7. Grep shim (plan-16 r5, remaining items).

## Topic 1: test isolation {#t1}

Findings: 17 #b-5, 19 #b-7, 21 #s-7, 22 #b-8 (bug-101), 23 #s-7; bug-088's recorder cannot see
spawned subprocesses.

| id | decision | by |
|---|---|---|
| d1a | A shared test sandbox is the FIRST build of Wave 1, ahead of the rest of plan-23. | user, 2026-10-14 |
| d1b | It is a new task **23.0** at the front of plan-23 (not a separate plan). | user, 2026-10-14 |
| d1c | The 1,655 pytest entities in the live global store and the 235 fixture rows in the live `query.log` (bug-101) are removed by plan-22 task **22.3**'s audited apply, not by a one-off forget. | user, 2026-10-14 |

Scope of 23.0 (proposal accepted with d1a): `$HOME`, global root, registry path and LaunchAgents
dir redirected to a tmp dir BEFORE `refmatrix` is imported; store roots injected so discovery
cannot find live stores; spawned `rmx` children refuse any socket outside the tmp dir (bug-088's
refuse stage); a conftest guard fails any test that touches `~/.refmatrix` or a registered live
store. {#t1-scope}

## Topic 2: write harness and concurrency {#t2}

Findings: 23 #b-1..b-3, #s-1..s-7, #m-1..m-3; 17 #s-1, #s-7; 22 #s-1, #s-2.

| id | decision | by |
|---|---|---|
| d2a | Exactly-once drain: the drain offset is committed in the SAME DuckDB transaction as the batch (option 1), not an event-id dedupe table. Answered "2a - opt"; read as option 1, the recommendation — to be confirmed. | user, 2026-10-14 |
| d2b | Plan-23 stays first in Wave 1 (after 23.0), with the `bind(batch)` seam; Option A is not folded in. Plan-17 takes no per-dataset Lance lock now; it goes through `bind`, and a revisit is recorded for when Option A lands. | user, 2026-10-14 |
| d2c | bug-093's between-file yield becomes task **23.3** (after 23.1): a transaction boundary inside `_sync_paths`, the same `bind` seam and write-count tests. | user, 2026-10-14 |
| d2e | Option A's measurement #4 (one writer thread vs N per-op cursor writer threads on a cliquet copy: conflict rate, throughput, ART errors under load; [[exploration-storage-concurrency-redesign#measure]]) runs in Wave 1 IN PARALLEL with 23.0, so the Option A revisit (d2b) has data before plan-23's code lands. | user, 2026-10-14 |
| d2d | bug-099 (learn queue unlinks `*.draining` before apply) stays logged; fixed by 23.1. | user, 2026-10-14 |

Spec fixes taken without a decision (proposed, not objected to): per-batch `bind` inside the hold
with a two-partition competitor AC (#b-1); a write-count recorder and a finalize step (#b-3); one
event per hold by default with drain budget, shutdown stop, error policy and requeue (#s-1); a
required `merge_fn` (#s-2); 17.1 and 22's apply use `bind` + the recorder but not the lossy queue
(17 #s-1, 22 #s-1/#s-2); real `_FairLock` in tests, every-batch-released AC, recorder required,
23.2 before 23.1 (#s-4, #s-5); overflow reaches `rmx learn status` through a daemon op (#s-6);
the MEH items. {#t2-fixes}

## Topic 3: Lance nightly maintenance (plan-17) {#t3}

Findings: 17 #b-1..b-6, #s-1..s-8, MEH.

| id | decision | by |
|---|---|---|
| d3a | An orphan vector is one whose entity id is absent from the WHOLE catalog (every partition), not `gc_vectors`' bound-partition-and-kind rule. The orphan list stores the vectors themselves, so a reap can be undone. | user, 2026-10-14 |
| d3b | The pre-compaction version is tagged and kept until the next successful run; cleanup never removes the tagged version. Not answered directly; accepted as the premise of d3c ("3b mostly covers this") — to be confirmed. | user (implied), 2026-10-14 |
| d3c | Out-of-daemon readers (`_replica_memory_recall`, `rmx recall`, `memory compile`) are protected by d3b; a reader that hits a missing file retries once on the current version and counts it. No N-newest retention floor. | user, 2026-10-14 |
| d3d | With no `maintain` stamp, the tick runs a dry run only and reports; the real op starts only after 17.3 writes the stamp by hand (after its dry run and backup). | user, 2026-10-14 |
| d3e | Maintenance is its own step on 17.2's tick (plan-review C6), not on the queue-alert thread; stores run serially with a per-store budget, and a hub-side timeout is reported as "still running", not "failed". | user, 2026-10-14 |

Spec fixes taken without a decision: drop the phantom handle refresh (#b-1); a parameterized
`older_than` with a production-24h AC (#b-2); fingerprint before cleanup, gate before any delete,
restore AC (#b-3); injected roots + 23.0 (#b-5); the never-embedded skip filter becomes a 17.1
requirement (#b-6); `bind` + recorder, no queue (#s-1, #s-7 per d2b); 17.3 latency on refmatrix,
cliquedb, thiquet (#s-4); `partition=None` = every partition (#s-5); stores from the registered
daemon list (#s-6); no in-process fallback, skip counted (#s-8); MEH items. {#t3-fixes}

## Topic 4: recall-event schema (plan-21, shared with plan-19) {#t4}

Findings: 21 #b-1..b-3, #s-1..s-13, MEH; C7.

| id | decision | by |
|---|---|---|
| d4a | Events go to a NEW append-only `recall-events.jsonl`, written lock-free like `query.log`. 19.2's counters fold it into DuckDB through plan-23's drain (d2a offset-in-transaction); 21.1's emission does not depend on plan-23. | user, 2026-10-14 |
| d4b | The C9 ranking-eval gold set is extended to code AND docs now; sessions stay out and plan-13's sessions question is marked dormant with a pointer; AC-3 gets a minimum win and n. | user, 2026-10-14 |
| d4c | The 21.4 question set is drawn from real NL queries in `query.log` by an agent that never reads the ranking code, approved by the user, and its hash committed into the spec before tuning; the tuner cannot change it. | user, 2026-10-14 |
| d4d | The 21.3 nudge's latency budget (old d-3) is decided by MEASUREMENT when 21.3 starts, and the nudge is NOT dropped in advance. R0 times the hook wall time (p50/p95) on the real identifier set, once quiet and once under load, and applies go/no-go ranges written into the spec before the run (see #t4-nudge-ranges). The hook never builds a full context bundle in any range. | user, 2026-10-14 (revised: "I'd rather state multiple go-no-go ranges") |
| d4e | No habit memory (old d-4): `feedback_rmx_first_retrieval` exists and a voluntary rule is the channel that goes unused; the nudge is the mechanism. | user, 2026-10-14 |
| d4f | An `agent` invocation source is added, keyed on `CLAUDECODE`; eval harnesses set `internal` explicitly. | user, 2026-10-14 |

Spec fixes taken without a decision: `session` (envelope → `CLAUDE_CODE_SESSION_ID` →
`RMX_SESSION`, never `latest_session`), `turn`, `query_id` (#b-1); `name` + `entity_id`, `channel`
surface enum separate from `invocation` (#b-2); named emitters per surface and an AC through a real
hook command (#b-3); `emitted` vs `seen` with `offset_bytes`/`bytes` (#s-1); phased fields `arm`
(fixed / phased / phased+cache), `policy`, raw phase inputs, restored cluster id (#s-2, topic
cache); fixed-window AC-4 excluding replay rows (#s-3); R3 retargeted to `grep-stdin` (#s-4); CLI
daemon route of `context` logged (#s-5); no test writes the measured log (#s-7); replica-route
reranker (#s-8); generator-not-runtime ACs, "tested by" defined or dropped, frozen replay names
(#s-10..#s-12); MEH items. {#t4-fixes}

Go/no-go ranges for the 21.3 nudge (d4d), on hook wall-time p95, the worse of quiet and loaded:

| p95 | verdict |
|---|---|
| ≤ 100 ms | GO: fire inline on every eligible call |
| 100–300 ms | GO, gated: at most once per symbol per session; report the per-prompt cost |
| 300 ms–1 s | NOT YET: build a precomputed indexed-symbol set (written at SessionStart / on derive), so the hook check is a set lookup; re-measure, then apply this table again |
| > 1 s after that | NO-GO in the hook: defer, revisit after Option A's measurement (d2e) |
{#t4-nudge-ranges}

## Topic 5: memory budget, recall, phased context (plan-19) {#t5}

Findings: 19 #b-1..b-7, #s-1..s-10, MEH; the phased-context exploration and topic cache.

| id | decision | by |
|---|---|---|
| d5a | `mtype=subject` rows are excluded from recall by default (opt-in flag); they stay protected and reachable through `--subject`; compile reaps stale subjects. Expanding a subject into its members is deferred. | user, 2026-10-14 |
| d5b | New task **19.6** (Wave 3) owns phasing AND the topic cache for the whole per-prompt budget (recall + scan-prompt). Depends on 19.1, d5a, 19.5's probe and fixed baseline, and 21.1's fields; plan-21 only measures. Turn count is logged, never a phase signal. | user, 2026-10-14 |
| d5c | "Asserted" = `type: feedback` or explicitly user-protected (a learner auto-protect does not count), ~16-20% of memories; inbound `rel:` edges are a tie-break only. Measured 2026-10-14 over 326 memory files: has-any-rel 298 (91%), inbound-rel target 222 (68%), inbound ≥ 3 92 (28%), feedback 52 (16%). | user, 2026-10-14 |
| d5d | 19.5's probe decides PreCompact: if its stdout does not reach the agent, PreCompact stops doing recall and keeps only save-state/promote. Until then PreCompact hits are not counted as delivered. | user, 2026-10-14 |

Spec fixes taken without a decision: no `${RMX_HOOK_BUDGET_CHARS}` interpolation, AC runs with it
unset (#b-2); operational reachability — run each fold command, page through, find every member
(#b-3); nonzero floor with `base`/`asserted_floor` defined, AC on a zero-hit memory (#b-4); sum
`merge_fn` + d2a (#b-5); "use" counted only at explicit agent calls, never recall's internal
`memory_get` (#b-6); 23.0 (#b-7); per-hook vs per-event cap probe (#s-2); arithmetic fixed
(#s-3); name-keyed global hits (#s-4); 19.3/19.4 cycle broken (#s-6); stable `unlabeled-N` names
and stale-subject reaping (#s-7); atomic single-writer index files (#s-8); decay-free `check()`
(#s-9); MEH items. {#t5-fixes}
