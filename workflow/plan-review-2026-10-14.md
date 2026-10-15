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

## Close-out {#close-out}

The user, 2026-10-14: "have bsd review our decisions when we're done". When the last topic is
decided, a `@ch-bsd` review of THIS decision log runs before any spec is revised: are the decisions
consistent with each other, with the findings they answer, with ADR-0004 and the memory rules
(decay never loses knowledge, store calls via daemon), and does any "taken without a decision" fix
hide a real decision? Its findings are answered here first; the spec revisions follow.

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
| d2a | Exactly-once drain: the drain offset is committed in the SAME DuckDB transaction as the batch (option 1), not an event-id dedupe table. Answered "2a - opt"; read as option 1 and CONFIRMED by the user ("1 - yes agree"). | user, 2026-10-14 |
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
| d3b | The pre-compaction version is tagged and kept until the next successful run; cleanup never removes the tagged version. First implied by d3c ("3b mostly covers this"), then CONFIRMED by the user ("1 - yes agree"). | user, 2026-10-14 |
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
| d5e | STM cluster quality is fixed BEFORE the phased-context work: new task **19.0 (STM cluster hygiene)**, a hard prerequisite of 19.6, scheduled no later than Wave 2. Scope in #t5-stm-hygiene. | user, 2026-10-14 ("lets add fixes to the STM before the phased context work") |

Spec fixes taken without a decision: no `${RMX_HOOK_BUDGET_CHARS}` interpolation, AC runs with it
unset (#b-2); operational reachability — run each fold command, page through, find every member
(#b-3); nonzero floor with `base`/`asserted_floor` defined, AC on a zero-hit memory (#b-4); sum
`merge_fn` + d2a (#b-5); "use" counted only at explicit agent calls, never recall's internal
`memory_get` (#b-6); 23.0 (#b-7); per-hook vs per-event cap probe (#s-2); arithmetic fixed
(#s-3); name-keyed global hits (#s-4); 19.3/19.4 cycle broken (#s-6); stable `unlabeled-N` names
and stale-subject reaping (#s-7); atomic single-writer index files (#s-8); decay-free `check()`
(#s-9); MEH items. {#t5-fixes}

Task 19.0 scope (d5e), from this session's frozen ring
(`workflow/review-output/stm-export-db80475a-20261014.jsonl`, 502 events: 416 tool, 27 input,
22 say, 21 git, 16 reason; gitignored evidence, regenerate with `rmx focus export --json`):
1. **Agent script bodies are not focus.** 68 tool events carried heredoc/inline scripts; their refs
   are truncated locals and stdlib calls (`r.get` 32, `re.searc` 21, `collections.Count` 18,
   `glob.glob` 16, `json.loads` 13, `s.repla` 10, `m.group` 10). Extract refs from a tool event's
   command line and paths, never from a heredoc or `-c` script body; drop dotted refs whose head is
   a stdlib module or a short local. Reuse `scan._PROMPT_STOPWORDS` per
   `feedback_reuse_shared_stoplist`, plus a separate documented code-noise set.
2. **Subagent tool events are not the parent's focus.** While the decision-log review ran in the
   background, its `sed`/`python3` calls landed in THIS session's ring (same session id), and the
   composite's lead topic became its `glob.glob`/`re.findi` members. Record subagent events under
   the agent's own id (or drop them from the parent's focus graph), keeping them in the ring for
   provenance.
3. **Hand-back envelopes are ambient.** `<agent-message` / subagent hand-back text joins
   `<channel`, `<task-notification`, `[SYSTEM NOTIFICATION` in `is_ambient_text`.
4. **Typos do not become topic labels.** A prompt token with no corpus match that sits within edit
   distance 2 of a known term folds to it ("aggre" → agree, "llok" → look); an unmatched,
   non-code-shaped token can be a member but never a cluster label.
Acceptance: replay the frozen ring through `rmx focus rebuild --dry-run` (or its successor) and
the topic labels name this session's real threads (Wave 0, spec reviews, decision walk, test
isolation, plan-16/19/21/22/23) with none of the junk refs above as a label or member; the same
replay at HEAD shows the junk (RED). {#t5-stm-hygiene}

## Topic 6: audited removal and repair (plan-22, plan-16's 16.6) {#t6}

Findings: 22 #b-1..b-8, #s-1..s-7, MEH; 16 r5 #b-r5-1, #s-r5-3..s-r5-5; plan-16 dn-2.

| id | decision | by |
|---|---|---|
| d6a | The 48 ambiguous global entities are KEPT, marked ambiguous (plan-22 principle 3, decay rule). This supersedes the 2026-10-07 "forget 611" for those 48 only. | user, 2026-10-14 |
| d6b | The 476 uniquely verified global rows: rows whose file is under a registered project root MOVE to that project's store; rows under trees no store owns get an AUDITED forget whose manifest keeps the rows (restorable; grep relearns on real use). Supersedes the 2026-10-07 rewrite-in-global (it would put code entities in the memory-only global store, 0.65.0 guard). Needs a cross-store write path. | user, 2026-10-14 |
| d6c | `query/*` rows with df ≤ 1 and a valid evidence row are NOT a cull class (no removal by counter threshold). | user, 2026-10-14 |
| d6d | 16.6 is split by dependency: the sidecar table, backfill and read-time marks go to Wave 1 after plan-23; the learn-time provenance write moves into 16.1 (Wave 2); 22.3 (bug-086 + bug-101 rows) and the classes that need no provenance run in Wave 1 without 16.6. Settles plan-16 dn-2 and plan-22 #b-7. | user, 2026-10-14 |
| d6e | The audit is an MCP verb (read-only); apply is CLI-only behind dry-run + manifest. | user, 2026-10-14 |

Spec fixes taken without a decision: 16.6 records a line hash; "moved" repairs per (concept, file)
set (#b-1); provenance carries tool + dialect + line hash, pre-provenance rows re-checked under
the most permissive reading, the verifier speaks grep's dialect (#b-2, 16 #b-r5-1); row-level
`facts.log` events (evidence delete / re-point / rename) that rebuild and restore replay, restore
checked by name incl. evidence + protection (#b-3); ablation gate on a copy of THIS store (#b-5);
empty-learned redefined so it can fail (#b-6); `bind` + two-partition AC, no lossy queue, re-check
before apply, rename merge-on-collision with an event, learner auto-protect distinguished, alias
repair from the alias's own text, a row-level removal primitive, 22.3 AC on bug-086's symptom
(#s-1..#s-7); read-time marks distinguish reader-rule drops from staleness, sidecar key survives
`replica_merge` (16 #s-r5-3, #s-r5-4); MEH items. {#t6-fixes}

## Topic 7: grep shim (plan-16 r5, remaining) {#t7}

Findings: 16 r5 #b-r5-2, #s-r5-1, #s-r5-2, #s-r5-6, MEH; dn-1.

| id | decision | by |
|---|---|---|
| d7a | dn-1, option (a): `-k`/`--linkage` on a path-less call never runs the grep floor; an index miss exits 1, and a call that would go straight to the floor exits 2 with a message that the option needs the index. Nothing is silently widened. The plan's stated reason is corrected: the blockers are a caller's own `--include` widening the translated globs, BSD glob case-sensitivity, and `--linkage` having no file-level translation — not a "wider kind". | user, 2026-10-14 |

Spec fixes taken without a decision: seed a row that survives bug-074 verification and pre-check
that the mutated route returns it (#b-r5-2); click parses nothing — `--help` handled by our parser
only as the first argument, `-ekey` read as `-e key` (#s-r5-1); 16.1's case-insensitive
`--include` pruning only on recursive calls, so `grep -i PAT dir` keeps exit 2 (#s-r5-2); a
`spawned_by` field on learner records (#s-r5-6); MEH items. {#t7-fixes}

## Close-out: the decision-log review, answered {#t8}

[[bsd-decision-log-review-a192ba2]] (DIRTY 6B/10S/6M; 15 sound, 13 needs-amend, 2 unsound). The
user, 2026-10-14: "I agree with your other recommendations". Where a row below changes an earlier
decision, the later row wins.

rel: derives-from -> [[bsd-decision-log-review-a192ba2]]

### Unsound decisions, replaced {#t8-replaced}

| id | replaces | decision |
|---|---|---|
| d8a | d5a "compile reaps stale subjects" | Compile MARKS stale subjects `stale`; they stay protected and are hidden from recall; removal only through plan-22's audited path (ADR-0004 #rule-no-delete; 19 #s-7 as written). Subject expansion stays deferred and is listed in 19.6's out-of-scope, not left unowned. |
| d8b | d5c "asserted = feedback or user-protected" | Two signals, decoupled. The FLOOR (protection against loss) keeps ADR-0004 #rule-asserted-floor's definition unchanged (feedback, protected, `rel:`-anchored). FOLD ORDER in `MEMORY.md` uses a separate tier: feedback (52) → memories linked from curated (feedback/project/reference) memories → the rest. Folding loses nothing (operational reachability, 19 #b-3), so a narrow tier is safe. Measured 2026-10-14 over 329 files: curated-inbound 178; feedback ∪ curated-inbound 192 (58%). No user-vs-learner protect distinction is needed, so 22 #s-4 no longer blocks 19.3. |

### Revisited {#t8-revisited}

| id | decision |
|---|---|
| d8c | d6b amended: "registered roots" = the registered daemon list (8 stores), not `registry.json` (3). The cross-store move is a new task **22.5** (copy → verify → forget across two daemons, through daemon ops, manifest-backed) ahead of 22.3. Rows under no store's root (≥ 114 of the 476: the 8 roots verify only 362) get an AUDITED forget whose manifest keeps them restorable; this knowingly changes them from "recovered" (2026-10-07) to "forgotten, restorable". |
| d8d | The 235 fixture rows in the live `query.log` are not catalog rows, so 22.3 cannot remove them (amends d1c). Mark-and-filter: every `query.log` / `recall-events.jsonl` reader skips rows whose cwd or root is a pytest temp dir (one shared predicate); the log stays append-only history. 23.0 prevents new ones. |
| d8e | A recall hit on a GLOBAL memory is counted in the global store, keyed by name; the event carries `scope` (19 #s-4). The drop-and-replay AC is restored. |
| d8f | Privacy (public repo): raw `query.log` question sources (d4c) and raw STM rings (d5e) stay local and gitignored. Only a content hash and a REDACTED fixture (prompts and paths scrubbed) are committed; 19.0 and 21.4 tests run on the redacted fixture. |
| d8g | Apply interface (amends d6e): one verb on both surfaces (parity test holds); apply requires a manifest id from a prior dry-run in the same store AND `--confirm <manifest-hash>`. The gate is the manifest, not the surface. |

### Added after the close-out {#t8-added}

| id | decision | by |
|---|---|---|
| d8h | 19.0 item 2 (subagent events out of the parent's focus) gets a fallback ladder: (1) the hook envelope's subagent id if present; else (2) match a PostToolUse event (tool name + input digest + timestamp window) against the session's `subagents/agent-<id>.jsonl` transcripts, labelled by `agent-<id>.meta.json` (`agentType`, `description`); else (3) keep the event in the ring as `origin: unattributed`, never a cluster label. Attributed events live under `agent:<id>`, out of the parent's focus graph and composite. The TUI status lines are not persisted and are not a source. Owns bug-103. | user, 2026-10-14 ("add the subagent differentiation to plan 19") |

### Amendments carried without a new decision {#t8-amendments}

- **d1c/d6d:** 22.1 splits; **22.1a** (classes needing no provenance) runs in Wave 1 and feeds
  22.2 → 22.5 → 22.3. 16.6's leftover dependency on 16.1 is removed (the Wave 1 slice is R4/R5 +
  sidecar). (Review #b-3.)
- **d2a:** exactly-once covers only what is inside the one DuckDB transaction. Add: bitmap
  fragments flushed after COMMIT get a failure that is surfaced and retried, not printed;
  `replica_merge` must not roll back the offset table or the 19.2 counters on conflict;
  `recall-events.jsonl` is the retained replay source (never rotated away before it is folded).
- **d2b/d2e:** the Option A measurement becomes task **23.4** (Wave 1, ∥ 23.0) with go/no-go ranges
  written before it runs. The d2b revisit trigger is 23.4's verdict, not "Option A lands".
- **d3a:** keep the orphan RATIO CAP (refuse a reap above it), and add a restore op that reads the
  orphan list back (17 #b-4).
- **d3e:** the hub calls maintenance with `retries=0` and single-flight per store, so a timed-out op
  is never re-sent onto a running compaction (`feedback_daemon_call_retries_multiply_timeouts`).
- **d4a:** a non-consuming tail reader for `recall-events.jsonl`, and plan-23's TICK REGISTRY
  (one registry, one shared budget; `bounded_steps` vs `drain(queue)`; plan-21 listed as a
  consumer). Closes 23 #s-3, which no decision had cited.
- **d4d:** the precomputed indexed-symbol set has ONE owner (the daemon, written on derive; the
  hook only reads). The "> 1 s" band no longer waits on d2e (a write-concurrency measurement); it
  means no-go in the hook, revisited only if 21.3 is re-planned.
- **d5e (19.0):** owns bug-100; verifies the hook envelope identifies subagents BEFORE item 2
  relies on it (else: separate by `agent_id` from the transcript path, or drop tool events whose
  `session_id` has a live subagent marker); objective acceptance — the redacted fixture's top-5
  topic labels contain none of the listed junk refs and each of a pre-listed set of thread terms;
  typo folding skips tokens of length ≤ 4 and identifier-shaped tokens (`ann`, `lru`).
- **22 #b-8:** apply refuses any root not named on its command line.
- **19 #s-7:** see d8a.
- **MEH:** the review's m-1..m-6, and plan-22 #m-7 (ADR-0004 "only" vs `forget`/`prune-noise`,
  answered by d8a's audited-path rule), are carried by id into the spec revisions. m-5: the
  "1 - yes agree" confirmation answered the question "Confirm d2a and d3b?" (2026-10-14).
{#t8-amendments-body}

### Wave 1 order after the close-out {#t8-wave1}

23.0 ∥ 23.4 (Option A measurement) → 23.2 → 23.1 (+ tick registry) → 23.3; after 23.1: 16.6
Wave-1 slice → 22.1a → 22.2 → 22.5 → 22.3; 17.1 → 17.2; 19.0, 19.1, 19.2; 21.1 needs only 23.0.

## Re-review round (32dde06), answered {#t9}

The three paired re-reviews ([[bsd-plan19-21-spec-rereview-32dde06]],
[[bsd-plan16-22-spec-rereview-32dde06]], [[bsd-plan23-17-spec-rereview-32dde06]]) all returned
NEEDS-REVISION. The user, 2026-10-14: "go with your recommendations". Later rows win.

rel: derives-from -> [[bsd-plan23-17-spec-rereview-32dde06]]
rel: derives-from -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: derives-from -> [[bsd-plan19-21-spec-rereview-32dde06]]

| id | decision | by |
|---|---|---|
| d9a | **bug-105 is hotfixed NOW, ahead of Wave 1** (as bug-093 was): the fragment cache is rebound/keyed with the partition, and every partition's fragments are rebuilt from `entity_links` (derived, loses nothing). Live-store repair is announced and backed up first. Plan-23's `bind` still owns the contract going forward. | user, 2026-10-14 |
| d9b | Supersedes d8c's "≥ 114 forgotten" (the probe was misread: all 362 verified rows matched under the global store's own root). Global learned rows that read correctly but sit under no project store are decided AFTER 22.5's dry run shows the real split; 22.5 R1 reports the counts and applies nothing for that bucket until the user rules. | user, 2026-10-14 |
| d9c | plan-17 bulk orphans above the ratio cap: a cap refusal skips the reap but still compacts; release requires `--confirm-orphans <sha of the dry-run orphan list>`. | user, 2026-10-14 |
| d9d | 23.4's go/no-go ranges are amended first (workload includes `bitmap_fragments` writes; a broken copy is a test failure, not NO-GO; expected counts and "worst of three" defined; no live-file stat), then presented for the user's confirmation before the run. | user, 2026-10-14 |
| d9e | 19.2 stores raw per-evidence counts; weights and floors apply at READ time. `base` 0.25, `asserted_floor` 1.0, weights 1/2 are accepted as tunable starting defaults. | user, 2026-10-14 |
| d9f | 19.6's tables A-C and N=8/K=8 are marked PROPOSED; the user confirms them before 19.6 starts (Wave 3, after 19.5's baseline exists). | user, 2026-10-14 |
| d9g | The 235 legacy fixture rows in the live `query.log` are excluded by exact shape (the `alpha|beta` fixture pattern with no `cwd`) and reported as their own count. | user, 2026-10-14 |
| d9h | 21.4's question set is drawn from this project's `query.log` only. | user, 2026-10-14 |
| d9i | One ADR-0004 amendment, drafted by the orchestrator for the user's approval: the floor formula (`base·(1+log1p(…))`, never zero) and removal-path scoping (`forget`, `prune-noise --drop`, `untrack`, `memory bulk-forget` either route through plan-22's audited path or carry a stated exception). | user, 2026-10-14 |
| d9j | plan-22 can close with 22.4 handed to the future helix plan. | user, 2026-10-14 |

Spec fixes for the next revision round, taken without a decision (from the re-reviews'
"specs can settle" lists): 19.0 matches subagent events by `tool_use_id` (not a time window) and
filters refs at `cli._tool_event_fields`; 21.1 events gain `partition`, `cwd`, `root`, one owner
for `delivered`, one unit (bytes); 19.2's channel enum follows 21.1; AC-6/AC-7 reconciled (legacy
rows counted in totals with a separate printed count); `used` evidence fully specified incl.
global destination; 22.1 calls 16.6's verifier, which returns the matching line set and closes
its three false-stale holes (`-m`, absolute-path `--exclude`, exit 2); 16.6 provenance gets a
`facts.log` event; 22.2/22.5 update provenance keys; 22.1a's candidate set matches the probe;
sandbox-safe catalog clones for the census ACs; 16.2 fixture scrubber; 23.1 learn evidence
insert-if-absent (bug-106); 23.3 stamps a file only after its semantic pass, and takes bug-093's
op-start log line; 23.0 AC-4 checks added row content, not size/mtime; 17.1 uses 23.1's real
names; 17.2 keeps its own registry (17.2 ≠ 23.1 tick registry); 17.2 `still_running` gets a
ceiling; arming per (store, step) for every registered step; 17.3 ACs on a synthetic 30k-version
clone; d8d's predicate owned by 21.1 in `telemetry.py`; the dead-letter file kept with a re-drive.
{#t9-fixes}

### Approvals after round 2 {#t9-approvals}

| id | decision | by |
|---|---|---|
| d9k | The ADR-0004 amendment ([[refmatrix/adr-0004-unified-location-space-index#amend-2026-10-14]]) is APPROVED and folded into `#rule-floor`, `#rule-no-delete` and `#rule-asserted-floor`. | user, 2026-10-14 ("1 - yes") |
| d9l | 23.4's amended go/no-go ranges are CONFIRMED as written in `task-23.4#ranges`. | user, 2026-10-14 ("2 - yes") |
| d9m | 23.4's PROCEDURE is corrected under the confirmed numbers (round-3 #ns23-r3-4): the integrity check compares by NAME, not sequence-assigned id; no 60 s cap (runs drain to completion, as the serial reference does); a failed transaction retries in place, in key order; the workload's size and window are pinned; AC-1 orders runs; a positive control proves a correct concurrent run passes. | user, 2026-10-14 ("a - yes") |
| d9o | The removal paths the approved ADR text omitted (bug-107) are classified: `purge_path` on a deleted/ignored file = derived cleanup WITH a manifest (learned rows go to the manifest, never silently away); sync's GMD legacy purge on a `.md` edit = a BUG, fixed to keep learned rows (16.6's verifier judges them); `vacuum`'s orphan-evidence delete = derived cleanup with a manifest AND a `facts.log` event; `fold_concept_dups` = a merge, a plan-22 entry point owned with merge writes by the helix plan; `unprotect` = not removal, but it writes a `facts.log` event with its source so user and learner actions stay distinguishable. Folded into ADR-0004 `#a14-removal-scope`. | user, 2026-10-14 ("3 - agree") |
| d9n | Option F (one SQLite file holding catalog and vectors via `sqlite-vec`) is added to the storage exploration as an UNMEASURED option, with a small benchmark task: the same queries on a copy of this store under both engines. | user, 2026-10-14 ("b - yes") |

### Approvals after round 3 {#t11-approvals}

| id | decision | by |
|---|---|---|
| d9p | Sync keeps learned rows on ANY edit of a file that still exists, not only a `.md` edit: the non-GMD path also calls `purge_path` before re-adding a changed file, and an edit is not a deletion. 22.6 R4 owns it; 16.6's verifier judges the kept rows. Extends d9o and bug-107. | user, 2026-10-14 ("1 - agree") |
| d9q | `rmx memory forget` (and `memory bulk-forget`) are removal entry points under ADR-0004's knowledge-removal rule: plan without `--confirm`, apply only with a matching hash, `--yes` refused (22.6 R1). | user, 2026-10-14 ("2 - agree") |
| d9r | A user-asserted memory, for the decay floor, is one whose `metadata.type` is `user` or `guardrail` (19.2 R7, AC-9). | user, 2026-10-14 ("3 - agree") |
| d9s | MCP session attribution is fixed NOW as a bug (bug-109), ahead of 19.0 R5 / 21.1 R9: the long-lived `rmx mcp` server resolves the session through a pid pointer for its parent Claude process, written by the input hook, and never through its own frozen `CLAUDE_CODE_SESSION_ID`. The specs' resolver signatures stay the target; the fix ships the subset. | user, 2026-10-14 ("4 fix it") |
| d9t | 22.6 joins the wave list in Wave 1, after 22.2 and alongside 22.5; plan-of-plans row 16 (and row 22) brought current. | user, 2026-10-14 ("yes") |
| d9u | Round-4 spec re-reviews of plans 16/17/19/21/22/23 start at the round-3 commit. | user, 2026-10-14 ("start them") |
| d9v | 19.6's pre-registered ranges are CONFIRMED as written: the phase thresholds (`w_min` 2, `j_warm` 0.15, `j_return` 0.20), Tables A-D, `N = 8`, `K = 8`, `C = 6`. Settles d9f; 19.6's status lines flip to CONFIRMED after its round-4 re-review lands. | user, 2026-10-14 ("tables confirmed as written") |
| d9w | `tests/conftest.py` refuses to run when `refmatrix` imports from a different tree than the tests (`.venv-eval`'s editable install silently tested the dev tree from a clone). Shipped on the bug-109 branch (54e13c6), reaches master with it. | user, 2026-10-14 ("yes add the guard") |
| d9x | Test isolation gets two outer tiers on top of 23.0's in-process sandbox: a separate macOS user `rmxtest` (full suite before any merge to `master`) and a Tart macOS VM (before every deploy, and on any disagreement), written into 23.0 as R7/R8 with AC-7/AC-8. A Linux container cannot exercise launchd or macOS socket limits, so it is not one of them. Operator setup (user, sudoers, Tart install) is proposed and run by the user. | user, 2026-10-14 ("both, write it into 23.0") |
| d9y | 23.4's PROCEDURE is corrected again under the confirmed numbers (round-4 #ns23-r4-3): threads are dealt in dependency order (an entity's create/delete precedes its links, across threads), the dead-bit check is DIFFERENTIAL against the copy's own pre-run census (a live copy already carries ~410 dead bits), and the workload window reads the LIVE log's `st_birthtime`, never the copy's. The ranges (d9l) are unchanged. | user, 2026-10-14 ("1 - agree") |
| d9z | `vectors_restore`'s `id_map` gets its caller (round-4 #ns17-r4-1, option a): 22.2's manifest keeps each removed entity's OLD id and its vector, so a restore re-inserts the vector under the new id with no model call; plan-22 names the parameter in 22.2 R4. | user, 2026-10-14 ("2 - a") |
| d9aa | The user's M1 Mac mini hosts 23.0's tier-2 macOS VM lane once it is running (real arm64 Apple hardware, off the workstation); until then the workstation hosts it. A hackintosh is rejected: x86 diverges from the arm64 production builds, Intel macOS ends at 26, and it breaks the macOS licence. | user, 2026-10-14 ("I have a m1 mac mini") |
| d9ab | A protection's origin is trusted ONLY from an explicit `source` on its event or a CLI/MCP command record; anything else (every protection that survived a `facts.log` compaction) is user-asserted and never auto-removed; its learned rows may still be removed. Two companions: the compactor (`dump_catalog_to_log`) must keep `source` and the learned-evidence events from now on, and a read-only count on a store copy of what each rule classifies is taken before the rule is built. Round-4 16/22 #b-2. | user, 2026-10-14 ("1- a") |
| d9ac | `merge_partition` is a MERGE entry point owned by the future helix plan, as d9o made `fold_concept_dups`; its dropped fragment bits already go to a manifest (bug-105). Round-4 16/22 #s-2. | user, 2026-10-14 ("2- a") |
| d9ad | 23.4 procedure pin = `d454bf9` (the d9y procedure text as written in `task-23.4-option-a-measurement` at that commit). 23.4 AC-1 runs with `--spec-pin d454bf9` and compares against this row. | orchestrator, recording d9y (user, 2026-10-14) |
| d9ae | bug-105 ships the REPAIR now and fences LIVE merge: the daemon's `partition_merge` op refuses (offline merge with the daemon down stays available); the merge redesign (r4 #b4-1 rebind window, #s4-1 late SRC writes) goes to the helix plan, which owns merge (d9ac). Before merge: pin the r2 survivor mutants M1/M11/M12/M14, implementation summary, registry row. | user, 2026-10-14 ("1- b") |
| d9af | bug-109: pin the r3 surviving mutants and fix the same-session stale-pointer shortcut, one more audit, then merge; after merge, merge `master` into `wave0-spec-reviews` so this project's `.venv-eval` MCP server gets the fix. | user, 2026-10-14 ("2- agree") |
| d9ag | 23.1 R1.6 (held-writer-lock check: `_FairLock` owner field, `Store.writer_lock`, `WriterLockNotHeld` in the store writers and rebind sites, WARN-mode census first) is ADOPTED as written; no longer PROPOSED. | user, 2026-10-14 ("3-a") |
| d9ah | Session pointers: bug-109 merges with its per-store `stm/by-pid/`; 19.0 / 21.1 move them to the user-level location later and read the old one for one release (21.1 D3). | user, 2026-10-14 ("4-q", confirmed "4-a") |
| d9ai | `rmx focus record` / `rmx focus clear` become writes under 19.0 R5: with no pointer and no `RMX_SESSION` they exit 2 instead of using the `default` ring. | user, 2026-10-14 ("5-agree") |
| d9aj | Older revision tables that say PROPOSED stay as history; only live status labels carry CONFIRMED (d9v). | user, 2026-10-14 ("6-agree") |
| d9ak | Protected entities no class plan may remove: (a) their learned rows are removed, the entities stay listed `kept: asserted-protection`, removable only through an explicit 22.6 `--confirm` plan; AND (b) a `cli.log` `rmx grep P` record counts as learner evidence for concept `query/P` (217 here, 90 global; none of the 1,655 pytest-tmp). | user, 2026-10-14 ("7 a and b") |
| d9al | 22.5 cross-store move: the global entity is purged after a fully verified move even when user-protected, because its protection and `protect_source` are copied to the target (a move is not a removal). | user, 2026-10-14 ("8-a") |
| d9am | Protection `source` vocabulary: `learner`, `user`, `system`, `removal`, set by the caller; `upsert` is dropped (`rmx add-entity` also uses that path). | user, 2026-10-14 ("9-agree") |
| d9an | Plan 22 gains a `dangling-link` class: an `entity_links` row whose entity or concept id exists in neither `entities` nor `concepts`. 22.1a audits it, 22.2 removes it through the manifest. It is the owner of the bug-111 deferral (cliquedb: 5,298 dead-entity + 8 dead-concept rows on 2026-10-14). | user, 2026-10-14 ("add the dangling type to p22") |

### Approvals after round 6 (0e77da3) {#t12-approvals}

| id | decision | by |
|---|---|---|
| d9ao | 23.1 R8 and AC-13 (merging two slots' `queue_offsets` through `replica_merge`) are RETIRED: writer rotation is dropped (`_refresh_replica_now` is a no-op), so nothing produces diverged slots any more, and the frozen inactive slots predate the queue tables. The frozen slots are a separate item: `rmx replica audit` (2026-10-15) found rows only in the inactive slot on atldb (502 ids), refmatrix (3,183 ids, 60 `memory_content`) and viascope (113,985 ids, 124 `memory_content`), by id; a by-name census decides recover (after bug-113) or discard. Round-6 23/17 #ns23-r6-3, option (b). | user, 2026-10-15 ("all four - i agree") |
| d9ap | 23.4's procedure handles dangling `entity_links` rows (an id resolving to no `entities` or `concepts` row, d9an): they are counted in the differential census (count plus the untouched id set), excluded from the by-name hash explicitly, and seeded into the AC-3 fixture; a resolver that raises is a mutation that must fail. The procedure pin moves to the revision commit (new pin row). Round-6 23/17 #ns23-r6-4. | user, 2026-10-15 ("all four - i agree") |
| d9aq | d9an's removal is replay-safe: for each dead endpoint whose `entity` event survives in `facts.log`, 22.2 logs a `tombstone` BY NAME, and the row an `unlink` by name; a dead endpoint the log cannot name logs nothing (stated). A rebuild after the removal yields 0 dangling rows and no resurrected endpoint (AC). The id-keyed `link_remove` event is withdrawn. Round-6 16/22 #b-1. | user, 2026-10-15 ("all four - i agree") |
| d9ar | `linkage_evidence` rows whose concept is dead (14,745 on cliquedb, 5,920 on refmatrix) become a `dangling-evidence` sub-class beside `dangling-link`: same audit (22.1a), same manifest removal (22.2). 22.6 R9's claim that `purge_entity` unlinks evidence is corrected. Round-6 16/22 #s-3. | user, 2026-10-15 ("all four - i agree") |
| d9as | 23.4 procedure pin = `6db632b` (the d9ap procedure text in `task-23.4-option-a-measurement` at that commit); supersedes the d9ad pin `d454bf9`. 23.4 AC-1 runs with `--spec-pin 6db632b`. | orchestrator, recording d9ap (user, 2026-10-15) |
| d9at | 23.0 (test sandbox) and 23.2 (lock-hold fixture) are APPROVED for implementation ahead of the rest of plan-23: no round-6 finding touches either spec. 23.0 starts now in a `/Volumes/littlebig` clone, TDD; the rest of Wave 1 waits for a clean round-7 re-review. (d9as is reserved for the 23.4 procedure pin at the round-6 revision commit.) | user, 2026-10-15 ("yes approved") |
| d9au | Plan 20's similarity check compares the concepts' linkage BITMAPS (which entities each concept is linked from, per linkage), not just their names: the name rule only generates candidate pairs, and "merge iff" is decided on bitmap overlap. Answers plan-20 r1 #b-1 (79% of name-matched pairs share no raw entity because code links `keyword/x` and docs link `x`; the revision defines the roll-up unit over the bitmaps) and #s-2 (the name signal cannot be scored on name-matched gold). | user, 2026-10-15 ("the similarity check should check the bitmaps not just the names") |
| d9av | Log replay applies `evidence` appends and row operations together in TIMESTAMP order: an `evidence_remove` (or `unlink`) at T deletes only copies appended at or before T, never a row re-learned after it. Applies to 22.2 R3 and 16.6 R1d (the one replay pass); dangling-evidence then logs `evidence_remove` by name too. Round-7 16/22 #b-1. | user, 2026-10-15 ("1 timestamp order, 2 yes, 3 a, 4 retire, 5 23") |
| d9aw | 22.3's live global apply may purge the learned-only global entities d9ak(b) makes removable (up to 90 on 2026-10-14); the plan prints that count before the apply and the user sees it first. Round-7 16/22 #s-3. | user, 2026-10-15 ("1 timestamp order, 2 yes, 3 a, 4 retire, 5 23") |
| d9ax | 19.6 R9 snapshot identity: a live cluster matches a frozen snapshot only with ≥ 2 shared members AND Jaccard ≥ `j_return` (0.20). `j_return` (d9v) now has a second use, acknowledged. Round-7 19/21 #s-1, option (a). | user, 2026-10-15 ("1 timestamp order, 2 yes, 3 a, 4 retire, 5 23") |
| d9ay | d9ao's retirement extends to 19.2 R6/AC-10 and 16.6 R1c (slot-merge paths): writer rotation is dropped and bug-113 breaks `replica_merge`; `plan-19`'s "CLOSED: 23.1 R8" line is corrected. Round-7 23/17 #ns-x-r7-1. | user, 2026-10-15 ("1 timestamp order, 2 yes, 3 a, 4 retire, 5 23") |
| d9az | Plan 23 owns the NON-harness `_store_lock` holders (`_op_stats` and the other 15 lock-taking cli reads, the facts.log compaction tick) and the heartbeat's coupling to the cli pool: bounded holds and read-path lock use are 23.x requirements. bug-115 (0.78.2) moved `ping` off the pool and beats on cli completions; the read stall under a long writer hold is 23's. Round-7 23/17 "ownership". | user, 2026-10-15 ("1 timestamp order, 2 yes, 3 a, 4 retire, 5 23") |
| d9bb | Plan 18: 18.1 (read-only catalog measurement on copies) runs NOW, ahead of Wave 4. Its result answers Q1 ("do we need it": lift C12 for an offline writer-slot rewrite) and Q3 (the 30 s / 120 s rewrite-time edges): both are decided on the measured bands, not before. d9ba stays reserved for the 23.4 pin at the round-7 revision commit. | user, 2026-10-15 ("p18: a-do we need it, b-yes, c-see a, d- we should have a reason to run. p20: lets review after the wave 2 stuff is clean") |
| d9bc | Plan 18 Q4: `catalog_maintain` runs only with a REASON: a measured band (reclaimable / WAL / growth) that calls for it, never unconditionally on the nightly tick. 18.2 states the trigger and logs the reason it ran or skipped. | user, 2026-10-15 ("p18: a-do we need it, b-yes, c-see a, d- we should have a reason to run. p20: lets review after the wave 2 stuff is clean") |
| d9bd | Plan 20's revision (r1 findings, d9au bitmaps, the four labelling/gold questions) waits until the Wave 2 work is clean; it is not revised in Wave 0. | user, 2026-10-15 ("p18: a-do we need it, b-yes, c-see a, d- we should have a reason to run. p20: lets review after the wave 2 stuff is clean") |
| d9ba | 23.4 procedure pin = `6fa243d` (round-7 text in `task-23.4-option-a-measurement`): supersedes d9as (`6db632b`). The procedure change is the census ORDER and a `dead-linkage` class (counted by raw `linkage_id`), from the corrected cliquedb counts (5,298 entity-dead, 1 concept-dead, 0 dead-linkage; plan-16/22 r7 #m-5); the ranges (d9l) are unchanged. 23.4 AC-1 runs with `--spec-pin 6fa243d`. | orchestrator, recording the round-7 revision; procedure change flagged to the user 2026-10-15 |
| d9be | **PROVISIONAL until its ch-bsd loop is clean.** 18.1 RAN 2026-10-15 on copies of all 8 registered snapshots (`workflow/review-output/plan18-catalog-measure-20261015.{md,jsonl,log}`; script `8a93ab1` in the `refmatrix-task-18.1` clone). Every gate passed. Table A: refmatrix A2 (789.0 -> 176.8 MiB, r 0.776), global A2 (241.8 -> 34.0, r 0.859), cliquedb A2 (230.5 -> 99.8, r 0.567), viascope A1 (291.5 -> 158.3, r 0.457); cliquet/orderly/atldb/thiquet A0 (under 64 MiB). Table C: every store C0, max rewrite 1.98 s. **Q1 answered: C12 is lifted for a writer-slot reclaim** (4 stores pay, 1.1 GiB reclaimable in writers and the same again in their snapshots; C12's premise, A/B reconciliation, went with d9ao). **Q3 moot:** the 30/120 s edges stay as pre-registered; nothing is near them. | orchestrator, on the user's pattern (user, 2026-10-15: "get us to ready to implement on wave 0-1. You've seen my pattern of approvals follow my lead") |
| d9bf | **PROVISIONAL until its ch-bsd loop is clean.** 18.3 is RESHAPED from an offline stop-the-daemon rewrite to an IN-DAEMON rewrite-and-swap under one `_store_lock` hold: rewrite to a sibling file in-process (a NEW path), gate, close the writer, `os.replace`, reopen through 23.1 R1.6's `_install_writer_store`, refresh the snapshot. 18.1 R3's recorded-not-built condition holds (every store's max rewrite <= 5 s; worst 1.98 s against 18.2's 10 s hold ceiling), and it removes the watchdog pause, launchd stop/kickstart and `daemon.lock` machinery the offline design needed. It DEPENDS on bug-112 (reopening a replaced path in-process returns the cached database) and on 23.1 R1.6. A store whose measured max rewrite exceeds 5 s keeps the offline route. `rmx compact` is retired onto it. The 18.3 spec is rewritten and re-reviewed before approval. | orchestrator, on the user's pattern (user, 2026-10-15: "get us to ready to implement on wave 0-1. You've seen my pattern of approvals follow my lead") |
| d9bg | **PROVISIONAL until its ch-bsd loop is clean.** 18.2's `RMX_CATALOG_BAND_MODE` default is `growth`: all 8 stores are B-disagree (f under-reads r by 0.10-0.63; on scattered deletes the index and partly-used blocks keep f low while a rewrite packs them). The growth baseline is each store's 18.1 `file_bytes`. d9bc's reason gate is that band. **Q4:** `requires_arming=False` stands; d9bc makes every run reason-gated, and a CHECKPOINT/reclaim decided by a measured band needs no extra hand arming. | orchestrator, on the user's pattern (user, 2026-10-15: "get us to ready to implement on wave 0-1. You've seen my pattern of approvals follow my lead") |
| d9bh | **PROVISIONAL until its ch-bsd loop is clean.** 18.1 spec amendments the tests forced: AC-1's `f >= 0.80` cannot hold on the real schema (200k entities, 90 % deleted: f 0.63, r 0.83), so AC-1 asserts `0 < f <= r`; AC-2's 100/40 MiB gives 60 MiB reclaimable, under Table A's own 64 MiB edge, so it uses 200/80 MiB (r 0.60 unchanged). The rewrite child opens the scratch copy read-write (a read-only connection attaches its target read-only). The 18.1 tests ran on injected tmp roots before 23.0 exists; they move under the sandbox when 23.0 lands. 18.1 is COMPLETED. | orchestrator, on the user's pattern (user, 2026-10-15: "get us to ready to implement on wave 0-1. You've seen my pattern of approvals follow my lead") |
| d9bi | Plan 19 (adaptive, context-variable STM) is the substrate the helix plan builds on, so it LEADS Wave 1 after 23.0: 19.0 (STM hygiene) and 21.1 -> 19.1 -> 19.2 move ahead of plans 16/17/22 in Wave 1, and 19.6 (phased context, topic cache) is pulled from Wave 3 to directly after its own dependencies. The helix plan (Wave 4 draft) consumes 19.x's outputs. | user, 2026-10-15 ("I want the context adaptive/variable stm handling in-place so we can build helix on top of that substrate") |
| d9bj | **PROVISIONAL until its ch-bsd loop is clean.** `learn.off` comes off only after 16.2 (passive shim) and 16.3 deploy TOGETHER; 16.3 RETIRES `enforce-rmx-grep.sh`'s redirect (d-1: grep is observed, not answered; the redirect is the hook load bug-115 removed). 16.4's measurement window opens only after `rmx learn on --global` and prints the switch decision in its header. Matches the user's 2026-10-15 rule "off until plan 16's passive shim exists". | orchestrator, on the user's pattern (user, 2026-10-15: "follow my lead"), from ch-bsd plan-16/22 r8 (`2026-10-15-0318-…-23ad703`) |
| d9bk | **PROVISIONAL until its ch-bsd loop is clean.** 22.6's `evidence_orphan_drop` decides "dead" by the LOG TIMELINE (entity create/tombstone timestamps), matching on `(linkage, c_kind, c, file, line, detail)`; `purge_entity` keeps deleting no evidence (round 6 stands). Rejected: purge removing its own evidence, which widens every purge manifest. | orchestrator, on the user's pattern (user, 2026-10-15: "follow my lead"), from ch-bsd plan-16/22 r8 (`2026-10-15-0318-…-23ad703`) |
| d9bl | **PROVISIONAL until its ch-bsd loop is clean.** Every row-level event plans 16/22 add (`evidence_remove`, `evidence_repoint`, `unlink`, `evidence_orphan_drop`, `learned_provenance`, `learned_provenance_move`) is spelled through `edge_records.edge_fields` with `c_kind`, and resolved by the SAME (kind, name) / `resolve_legacy_kind` path as the replay of that row (bug-117, 0.78.3). One edge-record format, one resolver: no per-event spelling (user, 2026-10-15: converge repeated shapes into one function). | orchestrator, on the user's pattern (user, 2026-10-15: "follow my lead"), from ch-bsd plan-16/22 r8 (`2026-10-15-0318-…-23ad703`) |
| d9bm | **PROVISIONAL until its ch-bsd loop is clean.** 19.6 topic identity AMENDS d9ax: two topics are the same only with >= 2 shared members, at least ONE of them not a hub, AND J >= `j_return`. A hub is a ref that is a member of >= ceil(N/2) = 4 of the topic cache's N = 8 newest snapshots (19.6's cache bound `N`; `K` is R6's keyframe interval) (no new constant; `derive_snapshots` stays pure). Measured by ch-bsd r8 on copies of the 60 live focus graphs: hub-only pairs were 63-73 % of d9ax's matches; the rule cuts 426 matches to 116. Two AC-7i legs + one mutation. Rejected (b): keep d9ax with a 25 % trip-wire. | orchestrator, on the user's pattern, from ch-bsd plan-19/21 r8 (`2026-10-15-0320-…-23ad703`) |
| d9bn | **PROVISIONAL until its ch-bsd loop is clean.** 23.5 read path, four rulings: (1) every cli-reachable read goes through ONE helper that always passes `writer_wait_s=_cli_writer_wait(d)` and answers "writer busy" on timeout; the 10 bare `_read_with_fallback` sites route through it and R7's AST check follows helpers to a fixpoint (user rule: converge repeated shapes); `snapshot` moves to the bg pool. (2) `stats(include_health)` runs `_store_health` OUTSIDE the read function, `memory_read_ok` from the read path, `db_file` from `d.store.db_path`. (3) An op stays on the shared mirror only if its measured p99 on a snapshot copy is < 50 ms; others get a private reader. (4) `partition_add`/`partition_rename` move to the bg pool, so writes are still never dropped and R2's deadline covers only `replica_audit`. `include_stale` reads the snapshot; bug-112 is cited as the freshness exception for private reads. | orchestrator, on the user's pattern, from ch-bsd plan-23/17 r8 (`2026-10-15-0320-…-cli-ops-reach-the-lock-through-helpers-23ad703`) |
| d9bo | **PROVISIONAL until its ch-bsd loop is clean.** 23.0 GREEN rulings on the RED writer's 7 ambiguities (`e9b1765`): (1) AC-4 interface as the tests assume: decoys at `<dir>/global/{query,facts}.log` + `<dir>/repo/{query,facts}.log`, args after `--` replace the suite selection, `RMX_PYTEST_PY` picks the interpreter, the leaking log's path is printed. (2) AC-6's mutation is applied to the INNER copy only. (3) SAFETY: no mutation run may reach a live path. The AC-2/AC-3 mutation gate runs with the OUTER `HOME` on a decoy home holding listening decoy `rmxd.sock`/`hub.sock` and decoy logs; "the children must then connect" is asserted against the decoys. (4) AC-3(b) points `REFMATRIX_ROOT` at a decoy `.refmatrix` the test builds with `Store.init()` (works in a clone and the tier-2 VM), never the repo's real root. (5) A swallowed violation still fails the test: every violation is appended to a per-test record AND raised; the conftest teardown fails any test whose record is non-empty. `SandboxViolation` must not subclass `OSError` (so `except OSError: pass` sites cannot eat it), and the teardown check makes the test fail even where a broader `except Exception` does. In a child, the audit hook writes the violation to the touches log and `os._exit(86)`. (6) R1/R9: the checkout guard resolves `refmatrix` via `importlib.util.find_spec` (no import), so the redirect stays the first import-capable step. (7) the touches-log test id comes from `PYTEST_CURRENT_TEST`; the per-test `REFMATRIX_ROOT` dir is created by the fixture; only plist roots are probed (the redirected registry path makes the real one unreadable by design). Also: with the real `~/.refmatrix/learn.off` present, a sandboxed test sees learning ON by default (the learn-off noise, user 2026-10-15) — one AC. | orchestrator, on the user's pattern (safety first; user 2026-10-15 "follow my lead") |
| d9bp | **PROVISIONAL until its ch-bsd loop is clean.** AMENDS d9bf (r1 B-1, B-2, S-1). (a) The in-daemon swap is gated on bug-112's FIX (in progress, branch `bugs-112-113-118`) with an AC that reproduces r1's swap write-loss (close one of two in-process connections, replace, reopen, write, checkpoint: the write must reach disk), AND 18.3 reads back a sentinel row after the reopen, refusing and rolling back if absent. (b) No offline route survives: a store whose LOADED max hold exceeds 5 s gets Table C's `refused:rewrite_too_slow` and goes to the helix plan. (c) "Feasible" is re-decided on a LOADED number: 18.3 measures the full hold (rewrite + gate + swap + reopen + snapshot refresh) in a tmp daemon with 6 concurrent readers, applies the 5 s gate to that max, aborts mid-rewrite with `con.interrupt()` past the budget, and states the rewrite's peak RSS (884 MiB on refmatrix) as a daemon-memory cost. Idle 1.94 s became 3.60-3.92 s under 6 readers. | orchestrator, on the user's pattern, from ch-bsd task-18.1 r1 (`2026-10-15-0331-task18-1-measurement-r1-8a93ab1`) |
| d9bq | **PROVISIONAL until its ch-bsd loop is clean.** AMENDS d9bg (r1 S-2, M-1). The growth baseline is each store's 18.1 `rewrite_bytes` (its live-data size), reset to the new `rewrite_bytes` after every reclaim; `catalog_reclaim_due` when `file_bytes >= 2 x baseline`, which is exactly r >= 0.50 (Table A's A2 edge) [corrected by d9bw(a): also needs the 64 MiB floor], so the 4 stores already due flag on the first nightly. 18.2 R5 uses this one definition. Corrected figures: f under-reads r by 0.115-0.657 on 7 stores and OVER-reads on thiquet (f 0.550 > r 0.272); no cause is claimed. | orchestrator, on the user's pattern, from ch-bsd task-18.1 r1 (`2026-10-15-0331-task18-1-measurement-r1-8a93ab1`) |
| d9br | **PROVISIONAL until its ch-bsd loop is clean.** 18.1 status is IN-PROGRESS (r1 M-5) until `task-18.1-catalog-measurement` merges to master and its ch-bsd loop is clean. The remedy (r1 S-3..S-5, M-2..M-4): gate on per-table count + full-column content hash + column types/defaults + constraint text + index SQL + views/macros/types, one AC-4 variant per part; AC-1 pins `free_blocks`/`total_blocks`/`f` against its own reading and gains margin; `rewrite_bytes` = median of the runs; R4 bytes tolerance 2 %; `rewrite_s_max` over every run; cleanup only per-store work dirs in a `finally`, any per-root exception an error row; each row records the duckdb version; stores named from the root path. The fleet run is re-taken after the remedy. | orchestrator, on the user's pattern, from ch-bsd task-18.1 r1 (`2026-10-15-0331-task18-1-measurement-r1-8a93ab1`) |
| d9bs | **PROVISIONAL until its ch-bsd loop is clean.** 22.2 keeps the reviser's `Store._row_op_c_kinds` (log a second, concept-keyed op where the legacy rule would rebuild a doc-held row onto a live same-name `concept`; bug-121) over the alternative "compact facts.log before every plan-22 apply", which would remove the legacy case but make every dangling endpoint nameless and add a mandatory heavy precondition to each apply. | orchestrator, on the user's pattern, from the plan-16/22 round-8 revision |
| d9bt | **PROVISIONAL until its ch-bsd loop is clean.** Plan-18 rewrite questions: (Q-A) the `catalog_reclaim` nightly step is `requires_arming=True` (it replaces the live writer file; the arm is the hand rollout's rehearsal + real-run pair), while `catalog_maintain` stays False (d9bg); (Q-C) the facts.log compaction moves onto the same `_catalog_hold` helper (a 23.1/23.5 amendment; same hold-and-swap shape — user rule: converge repeated shapes); (Q-D) the 5 s deadline interrupts Phase A (rewrite + gate) only, the whole hold is measured against 18.2's 10 s ceiling (Phases B/C ~0.3 s, not interruptible mid-swap); (Q-E) the rewrite's peak RSS (884 MiB on refmatrix) is accepted inside the daemon and stated per store; above 2 GiB the user decides (a child COPY would read the live slot from another process, which bug-110 forbids). | orchestrator, on the user's pattern, from the plan-18 rewrite |
| d9bu | **PROVISIONAL until its ch-bsd loop is clean.** The incremental replay path (`Store.apply_log_delta` -> `_apply_one_event` -> `_apply_event_body`) has no caller in `src/` and is RETIRED: 16.6 owns its deletion (with its tests) as a new requirement, and every spec clause that extends it (16.6 AC-9d check 3, `row_skips` on "both paths", 22.2 AC-3f's incremental clause, 22.6's catalog check) is dropped; the rebuild is the one replay path. This closes bug-120 (two resolvers fed different kind sets) by removing the second resolver. Rationale: dead code that specs keep extending is cost with no caller (ch-bsd r9 s-2); one path is the convergence rule. | orchestrator, on the user's pattern, from ch-bsd plan-16/22 r9 (`2026-10-15-0350-…-29e335a`) |
| d9bv | **PROVISIONAL until its ch-bsd loop is clean.** AMENDS d9br/18.3 AC-7: the rehearsal-match bytes tolerance is `max(2 %, 2 blocks = 512 KiB)`. The 18.1 r2 fleet re-run (`workflow/review-output/plan18-catalog-measure-20261015-r2.md`, script `34ac5cd`) measured the rewrite-size spread over 3 runs at up to 2.17 % (orderly; 1.5-1.7 % on cliquet/atldb/cliquedb), in whole 262,144-byte block steps that dominate small stores. Every band, gate and the fleet verdict of r1 were reproduced under the full nine-leg fingerprint gate. | orchestrator, on the user's pattern, from the 18.1 r2 remedy |
| d9bw | **PROVISIONAL until its ch-bsd loop is clean.** From ch-bsd plan-18 r1 (`2026-10-15-0351-…-b84fd8d`): (a) AMENDS d9bq — the nightly due band is `file_bytes >= 2 x baseline` AND `file_bytes - baseline >= 64 MiB` (Table A's floor; without it cliquet, A0 in 18.1, flagged), and an A0 rehearsal re-seeds the baseline so legitimate growth does not stick a permanent hot row; d9bq's "exactly r >= 0.50" is corrected. (b) A store refused `rewrite_too_slow` has an HONEST terminal state: it stays unreclaimed, carries a hot hub row and a bug-registry row, and the user decides — no pointer to a helix plan that does not exist yet (the helix plan, when drafted, may inherit it by name). (c) Q-C closed: 18.3 owns the port of 23.5's compaction hold onto `_catalog_hold`. (d) ONE immediate writer-lost exit is shared by 18.3 and the bug-113 fix (`_writer_lost`), not three mechanisms (S-3); the bug branch adopts it before merge. Q-D stands after the interrupt is made a real bound (flag + 50 ms re-interrupt + per-statement deadline check). | orchestrator, on the user's pattern |
| d9bx | **PROVISIONAL until its ch-bsd loop is clean.** 21.1 D9: ONE `stm.HOOK_PROMPT_KEYS` = scan's four keys (`prompt`, `text`, `user_prompt`, `message`); `_resolve_query` therefore also accepts the other three, and scan returns `""` (not raw JSON) for an object with none of them. Claude Code envelopes send `prompt`, so generated hooks are unaffected; one key set beats two (convergence rule). `CALL_OUTCOMES` keeps the four outcomes rows already carry (`ok`, `empty`, `consumer-closed`, `error`; bug-052) plus `skipped_budget`. 23.0 R4 gains `$RMX_SANDBOX_CONNECT_LOG`, `$RMX_SANDBOX_PRELOAD` and the named refusal exit 86 as interfaces 19.0 AC-6f / 21.3 AC-5 consume. | orchestrator, on the user's pattern, from the plan-19/21 round-9 revision |
| d9by | **PROVISIONAL until its ch-bsd loop is clean.** Plan-18 round 2: (a) THE writer-lost exit is immediate (`os._exit(2)` while holding `_store_lock`, no timer); the merge op's reply is lost and the log line + state file are the record — the bug-113 branch adopts `Daemon._writer_lost` + `Daemon._reopen_writer` before merge. (b) 18.3 R14 feasibility has TWO edges, per d9bt Q-D: loaded `phase_a_s <= 5 s` AND whole hold <= 10 s (refines d9bp(c), which put 5 s on the whole hold). | orchestrator, on the user's pattern, from the plan-18 round-2 revision |
| d9bz | **PROVISIONAL until its ch-bsd loop is clean.** AMENDS d9bk (plan-22 d-28): an orphan evidence copy is dropped only if its entity key has a TOMBSTONE after the copy and at or before the vacuum time T (the same test in the vacuum scan and in the rebuild). "Dead at T" alone revived the old copy after purge -> re-ingest -> vacuum (rebuild 2 copies vs live 1); measured by ch-bsd r10 s-2 (0 of 2,387 cliquedb / 0 of 55,242 refmatrix matched appends have a later tombstone today). Every drop keys on the orphan's OWN matched appends from the one scan, kinds via `resolve_c_kind` over logged kinds (r10 s-1; `names_from_log`/`_row_op_c_kinds` leave the vacuum path). | orchestrator, on the user's pattern, from ch-bsd plan-16/22 r10 (`2026-10-15-0408-…-451b505`) |
| d9ca | **PROVISIONAL until its ch-bsd loop is clean.** 19.6 topic cache: `TOPIC_CACHE_MAX = 64` (8 x N) records, derived not chosen, and PROVISIONAL until 19.6 R1's replay reports the per-session maximum record count; the replay's number replaces it by a decision row if it disagrees. One member-set hash: 19.4 R6's `unlabeled-<h>` slug is `stm.cluster_cid(members)`, the same function as 19.6's `<cid>`. | orchestrator, on the user's pattern, from the plan-19/21 round-10 revision |
| d9cb | **PROVISIONAL until its ch-bsd loop is clean.** Plan-22 round-10 residue: (a) `orphan_drop_skipped_live` is per logged drop op — a drop that matches copies but deletes none counts `skipped_live` once; one matching nothing counts `no_row`. (b) When the orphan's concept is LIVE, the vacuum scan additionally requires the append's `c` to match that concept (closes the 22.2 R4 restore re-attach case, where a restored entity's old append has a later tombstone); ch-bsd r11 probes it. (c) Accepted as narrow: a legacy append resolved over kinds logged up to the vacuum can miss if a same-name `concept` is logged later; compaction ends legacy appends; noted, re-measured if r11 finds any. (d) `_row_op_c_kinds` raises on an orphan row ("identical" defined only for a live, named entity end). | orchestrator, on the user's pattern, from the plan-16/22 round-10 revision |
| d9cc | **PROVISIONAL until its ch-bsd loop is clean.** SUPERSEDES d9cb(b) (the live-concept `c`-match closed 1 of 4 measured re-attach shapes, F1 only; ch-bsd plan-16/22 r11 S-1, fixtures F1-F4): (i) every `evidence_orphan_drop` carries the matched append's entity end `(e_kind, e)` and the rebuild matches on the full `row_key` plus `detail` (no "null entity end" wording in 16.6/22.6 `ROW_OPS`); (ii) a re-attach guard: no drop when `L > N` (L = identical copies the live entity holds, N = that key's appends with no later tombstone), counted `orphan_drop_reattached`; (iii) AC-6e with a variant and three mutations. Measured: all four shapes pass; 0 re-attach cases in today's data. Also: 22.2 `rename_entity` logs `unlink`/`link` per re-attached link and the `entity_rename` fold rule is "evidence moves; links and entities follow their own events" (r11 S-2). | orchestrator, on the user's pattern (measured evidence), from ch-bsd plan-16/22 r11 (`2026-10-15-0424-…-d8188ee`) |

## The wave list, all waves (2026-10-14) {#t10-waves}

The user, 2026-10-14: "fix the drift now". This list SUPERSEDES [[plan-review-2026-10-07#order]]
for every wave; it is derived from each revised task spec's own header and `Depends on:` line
(read 2026-10-14), not from the 10-07 list. Hard dependencies are in the specs; this is the
order of record.

rel: supersedes -> [[plan-review-2026-10-07#order]]

- **Wave 0 (done 2026-10-14; this log)** — spec reviews and revisions of plans 16/17/19/21/22/23,
  the ADR-0004 amendment (d9k), 23.4's ranges (d9l). Still waiting on the user's time: the 19.5
  R1 hook-limit probe, the 20.1 gold labelling, the 21.4 question-set approval.
- **Hotfix (now, ahead of Wave 1)** — bug-105 (d9a): fragment cache follows the partition binding,
  `rmx repair-index --fragments`, live repair after deploy. bug-109 (d9s): the MCP server resolves
  the CURRENT session through a per-Claude-process pointer. 23.1 waits for bug-105's merge; 19.0
  and 21.1 wait for bug-109's (they extend its code).
- **Wave 1**
  - 23.0 (test sandbox) ∥ 23.4 (Option A measurement; its verdict triggers the d2b revisit).
  - 23.2 → 23.1 (+ tick registry, `add_evidence_if_absent`) → 23.3 (sync between-file yield).
  - 21.1 (recall-event schema; needs 23.0 and bug-109 merged) → 19.1 (19.1 consumes 21.1's events).
  - 19.5 R1 (the probe) → 19.1 → 19.2; 19.0 (STM hygiene; needs 23.0 and bug-109 merged, no later
    than Wave 2).
  - After 23.1: 17.1 → 17.2 → 17.4; 16.6 Wave-1 slice → 22.1a → 22.2 → (22.5 ∥ 22.6) → 22.3 (d9t).
- **Wave 2**
  - 16.1 (learn-time provenance write) → 16.2 ∥ 16.3 → 16.5; 22.1 (classes that need 16.1's
    provenance).
  - 19.3 → 19.4 (a registered, arming-gated step on 17.2's registry); 19.0 if not done in Wave 1.
  - 17.3 (fleet rollout, after 17.1/17.2/17.4 deploy).
- **Wave 3**
  - 16.4 (measurement; closes plan-14).
  - 21.2 → 21.3 (its R0 band decides the nudge) ∥ 21.4 (NL ranking, code+docs gold set).
  - 19.6 (phased context, topic cache, tree render, versioned injection), after 19.0, 19.1, 19.5's
    baseline and 21.1; its PROPOSED tables confirmed by the user first (d9f).
- **Wave 4**
  - 20.2 → 20.3 (after the user's 20.1 labels).
  - plan-18 (catalog CHECKPOINT) as a 17.2 step, after its task specs are written.
  - Draft the ADR-0004 helix plan: inherits 22.4 (merge writes, d9j), 19.2's raw counts with
    read-time weights, 17.2's step registry, plan-20's merge rule, the approved amendment.
- **Wave 5** — build the helix: age tiers, manifests, the alias map and merge writes.
- **Dormant** — plan-13 (waits on a sessions gold set; d4b). **Closed into others** — plan-14
  (by 16.4).
{#t10-waves-body}

## Deliverable when the review converges {#final-doc}

The user, 2026-10-14: "at the end of all this review, I would like a separate consolidated
document created". When every Wave 0 re-review is clean (or its remaining items are explicitly
deferred), write ONE standalone document that does not require reading this log, the reports or
the revision tables: the final decisions (d1a..d9o and any later rows) in their latest form only,
the plan-by-plan contract that came out (tasks, waves, cross-plan interfaces), the approved ADR
changes, what is still open and who owns it, and the review history in one summary table.
{#final-doc-body}
