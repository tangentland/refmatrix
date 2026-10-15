---
gmd: "0.1"
id: bsd-decision-log-review-a192ba2
title: "Decision-log review: d5a re-opens a removal path outside plan-22, d5c contradicts ADR-0004's asserted floor, 22.3 cannot run in Wave 1 as decided, and four decisions grow unowned scope"
severity: BULLSHIT
plan: plan-review-2026-10-14
task: close-out
round: 1
tags: [bsd, audit, decision-review, wave-0, wave-1, plan-16, plan-17, plan-19, plan-21, plan-22, plan-23]
---

# ch-bsd review of the Wave 0 decision log {#root}

**Commit reviewed:** `a192ba2` (d1a..d7a), plus `83bc43d` (d5e, added at the coordinator's request
mid-run) and `290e040` (d2a and d3b confirmed). HEAD was `290e040` at write time.
**Written:** 2026-10-14T12:06:28-0700.
**Scope:** `workflow/plan-review-2026-10-14.md` against the six spec reviews it answers. Also read:
the plan-17/19/21/22/23 and 16.6 task specs; ADR-0004 `#rule-floor`, `#rule-no-delete`,
`#rule-asserted-floor` and `#rule-no-undercount`; both explorations; and the four named memories.
Code read for facts only: `Store.transaction`, `replica_merge.py`, `invocation_source`,
`tests/test_verb_parity.py`, and the daemon's slot-offset code.
**Method:** read-only throughout. No rmx call was made against a live store, no suite was run, and
nothing outside this file was edited. The frozen STM ring
`workflow/review-output/stm-export-db80475a-20261014.jsonl` was parsed with Python.

rel: specifies -> [[plan-review-2026-10-14]]
rel: related-to -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: related-to -> [[bsd-plan17-spec-review-3104a81]]
rel: related-to -> [[bsd-plan19-spec-review-3104a81]]
rel: related-to -> [[bsd-plan21-spec-review-3104a81]]
rel: related-to -> [[bsd-plan22-spec-review-3104a81]]
rel: related-to -> [[bsd-plan23-spec-review-3104a81]]
rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]
rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-asserted-floor]]

## Coverage of the six reports {#coverage}

Every BULLSHIT and SKETCHY id in the six reports was checked mechanically against the decision
table and the fix paragraphs (93 ids in all).

| report | BULLSHIT | SKETCHY | not cited | cited, but the remedy is incomplete or inverted |
|---|---|---|---|---|
| plan-23 | b-1..b-3 | s-1..s-7 | **s-3** | — |
| plan-17 | b-1..b-6 | s-1..s-8 | — | **b-4** (no ratio cap; nothing reads the orphan list) |
| plan-19 | b-1..b-7 | s-1..s-10 | — | **s-4** (only the key is taken, not the route for global hits or the drop-and-replay AC); **s-7** (the fix is inverted: "not deleted" became "reaps") |
| plan-21 | b-1..b-3 | s-1..s-13 | — | — |
| plan-22 | b-1..b-8 | s-1..s-7 | — | **b-8** (the "apply refuses a root not named explicitly" clause is not carried) |
| plan-16 r5 | b-r5-1, b-r5-2 | s-r5-1..s-r5-6 | — | — |

The MEH findings are covered by the blanket phrase "MEH items", which names no ids. Nothing stops
a spec reviser from dropping them all. Plan-22 #m-7 (ADR-0004 says removal goes "only" through
plan-22, while plan-22 claims only a scoped "one path") is load-bearing for [[#b-1]] and should
not sit inside that blanket. {#coverage-body}

## Findings {#findings}

### BULLSHIT b-1: d5a and the #t5 fix let compile "reap" protected subject rows, a second removal path that ADR-0004 forbids {#b-1}

**Where:** d5a ("compile reaps stale subjects"); #t5-fixes ("stale-subject reaping (#s-7)").
**What:** plan-19 #s-7's fix read: "Stale compiled subject nodes with 0 leaves are excluded from
recall (**not deleted; removal goes through plan-22**)". The report's question 1 also asked whether
they should "stay protected but recall-invisible". The decision log turned that into reaping, done
by `memory compile` on a nightly schedule (19.4). This conflicts with:
- ADR-0004 `#rule-no-delete`: "Removal goes only through the ONE explicit, audited path,
  plan-22 … That includes merges".
- Memory `feedback_decay_never_loses_knowledge`: "Allow removal only through an explicit audited
  dry-run → apply path."

The rows are protected, and d5a itself says "they stay protected". So the decision both protects
the rows and deletes them.
**Fix:** reword d5a and #t5-fixes as follows. Stale subjects (0 leaves) are excluded from recall
and from the `MEMORY.md` render. Compile marks them `stale`. Any actual removal is a plan-22 class
(dry-run → manifest → apply). Add an AC: after a re-compile, the stale subject row still exists and
is recall-invisible.
**Pattern match:** YES (plan-22 #m-7: "one removal path" keeps acquiring exceptions).

### BULLSHIT b-2: d5c redefines "asserted" against ADR-0004 #rule-asserted-floor without amending it, and depends on a protection source that does not exist {#b-2}

**Where:** d5c.
**What:**
- ADR-0004 `#rule-asserted-floor` reads: "Feedback memories, user-asserted or `protected` rows, and
  `rel:`-anchored GMD nodes keep a higher floor". The decay memory repeats it. d5c drops
  `rel:`-anchored nodes to a tie-break and excludes learner auto-protects. This narrowing is
  reasonable (plan-19 #s-5: 91% of memories carry a `rel:`), but it is an ADR change, and neither the
  ADR nor the memory records an amendment. A spec reviser following the ADR re-introduces the 91%
  degeneracy.
- "Explicitly user-protected" cannot be computed today. Plan-22 #s-4: the learner's
  `upsert_entity(protected=True)` and a user's `rmx protect` write identical events with no source.
  The #t6 fix "learner auto-protect distinguished" creates that source going forward only. Every
  existing protection is unclassified, and no decision says how to backfill them.
- 19.3 now depends on plan-22's protection-source field, and that cross-plan edge is not recorded.

**Fix:**
- Amend ADR-0004 `#rule-asserted-floor` in the decision log's spec-revision pass.
- Write an amending memory (`rel: amends -> [[feedback_decay_never_loses_knowledge]]`).
- Name the owner of the protection-source column (22.2, per #s-4) and add a 19.3 → 22.2 dependency.
- Have the user decide how pre-existing protections count: a backfill rule, or "unknown = asserted",
  which is the safe direction for a floor.

### BULLSHIT b-3: 22.3 cannot run in Wave 1 as decided (d1c + d6d): its prerequisites 22.1 and 22.2 are not in the Wave 1 list, 22.1 depends on 16.6 R1, and 16.6 depends on 16.1 (Wave 2) {#b-3}

**Where:** d1c, d6d, and the Wave 1 shape in the review brief (23.0 ∥ A-measure → 23.2 → 23.1 →
23.3; 16.6-sidecar; 22.3; 17.1/17.2; 19.1/19.2; 21.1).
**What:**
- `task-22.3` reads "Depends on: 22.1, 22.2". `task-22.1` reads "Depends on: 16.6 R1/R5
  (provenance, backfill)". `task-22.2` reads "Depends on: 22.1; plan-23".
- d6d moves 16.6 R1 (the learn-time provenance write) into 16.1, which is Wave 2. A Wave 1 22.1 is
  therefore possible only if 22.1 is SPLIT into its provenance-free classes. d6d implies that split
  ("the classes that need no provenance") but no task records it.
- `task-16.6` reads "Depends on: 16.1". The Wave 1 sidecar slice must drop that header, or Wave 1
  depends on Wave 2: an inversion, which is the closest thing to a cycle in this graph.
- 22.2 carries everything 22.3's apply needs, and all of it lands in Wave 1:
  - the removal primitive (22 #s-6);
  - row-level `facts.log` events (22 #b-3);
  - rename merge-on-collision (22 #s-3);
  - the bind + recorder ACs.
- 22.3 R3 still says "repairs rewrite to absolute paths". d6b replaced that with a cross-store
  move, which has no owner ([[#b-4]]).
- d1c also routes the 235 fixture rows in the LIVE `~/.refmatrix/query.log` through 22.3's audited
  apply. 22.x removes CATALOG rows. Rewriting a JSONL log that hooks, CLI and MCP append to
  lock-free is a different primitive, races those appenders, and is in no 22.x spec.

**Fix:**
- Wave 1 order: 23.0 → 23.2 → 23.1 → 16.6-slice (R4/R5 + sidecar; header no longer depends on
  16.1) → 22.1a (provenance-free classes) → 22.2 → move-op owner ([[#b-4]]) → 22.3.
- Record the 22.1a/22.1b split and rewrite 22.3 R3.
- For `query.log`, have the user choose: mark-and-filter (readers drop `invocation=internal`/fixture
  rows; nothing rewritten), or an offline rewrite with a backup. The first fits "never lose" and
  needs no lock.

### BULLSHIT b-4: d6b requires a cross-store write path that no task owns, rests on an undefined "registered project root", and silently changes the 10-07 outcome for at least 114 rows {#b-4}

**Where:** d6b ("Needs a cross-store write path").
**What:**
- **No owner.** No task spec owns the move. Because of `feedback_store_calls_via_daemon`, it must be:
  - a read from the global daemon;
  - a write op on the TARGET project's daemon (which must be up; the "registered, supervised,
    running" set is undefined per 17 #s-6);
  - an audited forget in global after the target commits.

  That is two daemons and two transactions. A crash between them duplicates the rows or loses them,
  and neither d2a's offset nor 22's manifest spans two stores. The target store can also collide
  (`UNIQUE(partition, kind, name)`; 22 #s-3's merge rule).
- **Undefined root set.** Plan-17 #s-6 found that `registry.json` names only 3 of the 8 stores.
- **A silent flip.** The 10-07 probe (memory `project_global_relative_rows_repair`) shows the 8
  registered roots verify only 362 of the 476 rows. So at least 114 rows, and more if "registered"
  means the 3 in `registry.json`, change from "recovered" (the 10-07 decision) to "audited forget"
  (d6b). The user was not shown that number.
- **Vectors.** A moved entity's global vector becomes an orphan under d3a. Unless the move
  re-embeds or carries the vector, the target store has none ([[#s-7]]).

**Fix:**
- Name an owner: a new 22.3a "cross-store move op", with copy → verify on the target →
  manifest-recorded forget in global, an idempotent re-run, and vectors carried or re-embedded.
- Define the root set (the registered daemon list, the same definition 17 #s-6 gets).
- Re-run the probe and put the count of rows in each bucket (move / forget) in front of the user
  before 22.3's dry run.
**Pattern match:** YES (a decision that says "needs X" without naming who builds X is an
unanchored deferral; rule 9a).

### BULLSHIT b-5: plan-17 #b-4 is only half answered: d3a promises a reap "can be undone", but nothing reads the orphan list and the ratio cap was dropped {#b-5}

**Where:** d3a and #t3-fixes. The report's fix had five parts. The log takes:
- the whole-catalog definition;
- vectors stored in the list.

It omits:
- the ratio cap ("orphans > max(50, 5%) → `ok:false`, no reap, alert");
- a restore op that reads `orphans-*.jsonl`;
- the "computed against another partition" mutation.

**Why it matters:** the whole-catalog rule removes the binding error. It does not remove the
empty- or partial-catalog error: a catalog opened mid-rebuild, or an `entities` read that fails
open, makes every vector an orphan. The fingerprint arithmetic still balances (the circular proof),
and the nightly reap then wipes the dense layer with `ok:true`. "Can be undone" with no reader is
the 16.6 "safety net with no reader" again.
**Fix:**
- Carry the ratio cap and its mutation into 17.1.
- Name the restore op (or extend 17.1 with an AC that reaps then restores and compares
  fingerprints).
- State the orphan list's retention (forever, under the decay rule).

### BULLSHIT b-6: three decisions defer to triggers that are not scheduled or measure the wrong thing (rule 9a) {#b-6}

1. **d4d, last range.** "> 1 s after that → NO-GO, defer, revisit after Option A's measurement
   (d2e)."
   - d2e runs in Wave 1, in parallel with 23.0, so it will be DONE before 21.3 starts. "After" then
     points at the past.
   - Measurement #4 times write-thread concurrency (conflict rate, throughput, ART errors). It says
     nothing about a read-side hook's wall time.

   The anchor is both expired and irrelevant.
2. **d2b.** "A revisit is recorded for when Option A lands." Option A has no plan, no task and no
   wave (plan-of-plans has no row for it). So the revisit is unscheduled.
3. **d5a.** "Expanding a subject into its members is deferred." There is no task and no target.

**Fix:** turn each into either "not planned (closed)" or a concrete trigger with an owner:
- d4d: "NO-GO; re-open only if 21.4's harness shows the nudge's target symbols are missed at ≥ X%".
- d2b: "re-opened by the d2e result through the decision rule in [[#s-2]]".
- d5a: "not planned; `--subject` is the expansion".

## SKETCHY {#sketchy}

### SKETCHY s-1: d2a (now confirmed) is exactly-once only for effects inside the one DuckDB transaction; three edges are unstated {#s-1}

The confirmation at `290e040` settles the assumption. The mechanism still has gaps:
- **Fragments.** `Store.transaction()` (`store.py:4233`) flushes dirty bitmap fragments AFTER
  `COMMIT`. A flush failure only prints to stderr ("Don't roll the transaction back"). For the learn
  queue, the offset and the relational rows commit while the bits can be lost, with no replay. That
  is a silent-failure shape on a memory path.
- **`replica_merge`.** It keeps the A-side row on conflict for tables without `updated_at`
  (`replica_merge.py` docstring). Writer rotation is dropped, so slot B is stale. A merge could
  regress a `queue_offsets` row AND the 19.2 `memory_usage` counters. Only the 16.6 sidecar got a
  `replica_merge` fix (16 #s-r5-4).
- **Retention of the source file.** d4a makes `recall-events.jsonl` the replay source for the
  counters (19 #s-4's drop-and-replay). The log must therefore never be truncated past the oldest
  offset any rebuild could restore. No decision says the file is retained.

**Fix:**
- 23.1 states that the exactly-once boundary covers relational effects only, and that fragments are
  rebuilt from `entity_links` (or flushed inside).
- `replica_merge` gets a rule for `queue_offsets`/`memory_usage`: take the max offset and the
  counters from that slot, or refuse.
- `recall-events.jsonl` is append-only with no rotation, or rotation is segment-aware with
  `(segment, offset)`.

### SKETCHY s-2: d2e has no owner task, no pre-registered decision rule, and no gate, so "data before plan-23's code lands" changes nothing {#s-2}

- The measurement needs a per-op-cursor writer prototype (Option A's interface), and no task builds
  it.
- No go/no-go threshold is written. d4d has one; d2e does not.
- 23.2/23.1 are not gated on it.
- Its stated consumer (d2b's revisit) triggers on "Option A lands", not on the measurement.

`feedback_causal_story_before_evidence` and the helix pre-registration pattern both say: write the
rule first.
**Fix:**
- Make it a task (for example 23.M) with a sandboxed `cliquet` copy off the watched tree.
- Pre-register ranges, for example: conflict rate ≤ X and 0 ART errors → schedule Option A as a plan
  in Wave 2; otherwise close Option A.
- State whether 23.1 waits for it. The recommendation is no, because the `bind` seam absorbs either
  outcome.

### SKETCHY s-3: plan-23 #s-3 is unaddressed, and d4a makes it worse: a second drain on the `_runner` tick, in a mode `BoundedQueue` does not have {#s-3}

- **Uncited.** No line cites #s-3. Its items are open:
  - a tick queue registry with ONE shared budget;
  - `bounded_steps` vs `drain(queue)`;
  - plan-21 as a consumer edge.
- **d4a's file is not a queue.** `recall-events.jsonl` is append-only, lock-free and SHARED with
  plan-21's measurement. Plan-23's queue rotates the file to `*.draining` and unlinks it
  (`read_rotated`), and it coalesces and drops on overflow. Folding d4a's file therefore needs a
  third primitive: a non-consuming tail reader by `(file, offset)`. That reader must stop at the
  last complete newline, because lock-free appenders can leave a torn tail. No task owns it.
- **Tick budget.** The fold adds a second consumer to the tick's 5 s budget, which is the N×budget
  problem #s-3 named.
- **d2c.** 23.3 (the bug-093 yield inside `_sync_paths`) is a bounded-steps consumer, not a queue
  consumer. The decision does not say which API it uses.

**Fix:** answer #s-3 explicitly in 23.1:
- `drain(queue)`, `tail(log, offset)` and `bounded_steps(items)` over one bind/recorder core;
- a tick registry with one budget;
- 23.3 on `bounded_steps`.

### SKETCHY s-4: plan-19 #s-4's global-hit route is still undefined, and with d2a/d4a it is a cross-store write {#s-4}

The #t5 fix takes only "name-keyed global hits". A project session's recall that hits a GLOBAL
memory is recorded in that project's `recall-events.jsonl`. There are two ways to count it:
- **The counter lives in the global store.** Then the project daemon's fold writes into another
  store's catalog. d2a's "same transaction" is impossible across two DuckDB files, and this is a
  second unowned cross-store write path (compare [[#b-4]]).
- **The counter stays in the project store.** Then one global memory's lifetime record is split
  across N stores, and the floor (`base * log1p(hits + 2*used)`) must sum them at read time.

Either way it is a user-visible decision about how global memories rank.
**Fix:** the user picks one. The recommendation is per-store counters keyed by
`(scope=global, name)`, summed at read time, because that needs no cross-store write. Also restore
19 #s-4's "drop the table, replay, identical rows" AC.

### SKETCHY s-5: d6e's "apply is CLI-only" cannot pass the verb-parity test, and it is not a guard {#s-5}

`tests/test_verb_parity.py::test_tools_and_verbs_are_the_same_set` asserts
`set(mcp.TOOLS) == set(verbs.VERBS)`. There is an `MCP_ONLY` class and no `CLI_ONLY` class. The
project constraint is "every capability an agent can call is a verb first". So the apply is either:
- a verb, which makes it an MCP tool; or
- a non-verb CLI command, which breaks the constraint.

Also, an agent can run the CLI apply through Bash, so "CLI-only" adds friction but excludes no
agent. The real guard is the dry-run + manifest + explicit-root refusal (22 #b-8, not carried).
**Fix:** decide on one of these:
- a `CLI_ONLY` verb class with a reason, plus a parity-test change;
- or an apply verb exposed on both surfaces that refuses without a manifest id from a prior dry
  run.

Carry 22 #b-8's explicit-root refusal in either case.

### SKETCHY s-6: d3e's "a hub-side timeout = still running" breaks "serially" unless retries are off and the op is single-flight {#s-6}

`daemon.call` defaults to `retries=2` (memory `feedback_daemon_call_retries_multiply_timeouts`).
That causes two problems:
- **A duplicate run on one store.** A hub timeout on store 1 re-sends `vectors_maintain` to a daemon
  that is still compacting. The result is two concurrent compactions on one dataset.
- **Overlapping runs across stores.** Store 2's run starts while store 1 is "still running", so the
  stores are no longer serial.

**Fix:**
- 17.2 calls with `retries=0`.
- The op is single-flight per store: a second call returns `already_running`.
- The tick does not start the next store until the previous one reports done, or until a stated
  overlap rule allows it.

### SKETCHY s-7: three restore artifacts for one entity: d3a's orphan list, 22's manifest, and d6b's move {#s-7}

There are three ways an entity can lose its vector:
- A 22.3 audited forget, followed the same night by 17.1's whole-catalog orphan reap of its vector.
- A d6b move, which leaves the global vector orphaned.
- A d1c removal, by the same route as the forget.

Each splits "restore" across two plans' artifacts. Restoring a 22 manifest brings back rows (if it
reuses ids) but not vectors, unless it reads 17's orphan list or re-embeds. Neither spec says
which. ADR-0004 `#rule-no-delete` also needs a sentence on why 17's automatic reap of DERIVED
vectors is not a second removal path (the plan-22 #m-7 wording).
**Fix:**
- 22.2's restore AC includes vectors (from the orphan list, or by re-embedding).
- The ADR scopes `#rule-no-delete` to knowledge rows, and names derived-vector reaping as restorable
  maintenance.

### SKETCHY s-8: d4c commits real user queries to a public repository: a privacy decision taken implicitly {#s-8}

d4c draws the 21.4 question set "from real NL queries in `query.log`" and commits its hash "into the
spec". The set itself has to live somewhere the tuner can read it. `github.com/tangentland/refmatrix`
is public. If the global `~/.refmatrix/query.log` is the source, it holds queries from every cwd,
including work trees (`~/github/atollogy/...`). The draw must also exclude bug-101's 235 fixture
rows, which until [[#b-3]] lands are still in that log.
**Fix:** the user decides the source log (project only?), whether the set is committed or kept
off-repo with only its hash committed, and adds a fixture/`internal` filter to the draw.

### SKETCHY s-9: d4d's 300 ms–1 s branch creates a precomputed indexed-symbol set with no owner and two writers {#s-9}

The branch creates a new artifact, "written at SessionStart / on derive". That means two writers:
- a hook process;
- the daemon.

This is the same class as plan-19 #s-8 (a concurrent, non-atomic writer of `MEMORY.md`). The
artifact appears in no 21.3 requirement and has no staleness rule (what happens between derives?).
**Fix:** 21.3 gets a conditional R with the following:
- ONE writer: the daemon, on derive. SessionStart only triggers that writer.
- An atomic replace.
- A version stamp the hook checks.
- An AC that runs only if R0's measurement lands in that range.

### SKETCHY s-10: d5e (task 19.0): its RED/GREEN fixture is gitignored, its acceptance is judged rather than mechanical, and item 2 assumes a discriminator nobody has probed {#s-10}

Checked against the frozen ring (502 rows, keys `ts session kind terse refs task detail
abandoned`). This review's own calls are part of the evidence, as the coordinator noted.
- **The fixture is not durable.** `workflow/review-output/` is gitignored (`.gitignore:35`), and the
  fallback "regenerate with `rmx focus export --json`" produces a DIFFERENT ring (the ring keeps
  moving). A RED/GREEN that depends on an uncommitted 295 KB live export cannot be re-run by the
  reviewer or the next session. Committing it has its own cost: it holds user prompts and tool
  details, and the repo is public. That is a privacy choice the user should make ([[#s-8]]).
- **The acceptance is judged.** "Topic labels name this session's real threads (Wave 0, spec
  reviews, …)" is scored by whoever implements it (the 21 #s-12 shape). The mechanical half, "none
  of the junk refs as a label or member", is good. The judged half needs a frozen expected-label
  list, written before GREEN.
- **Item 2's discriminator is unverified.** The ring rows carry NO agent field. The subagent event
  at 11:06:41 (`sed -n 2418,2490p …`) has the parent's `session` and nothing else that would mark it
  as a subagent's. "Record subagent events under the agent's own id" requires the PostToolUse
  envelope to carry an agent id. Nobody has probed whether it does. The causal line in bug-103
  ("nothing separates them by agent") asserts a mechanism, not a measurement
  (`feedback_causal_story_before_evidence`).
- **bug-100 has no owner.** Its resolver (`latest_session`) is still unowned, and the topic cache
  is session-scoped. 19.0 is its natural owner.

**Fix:**
- R0: probe one subagent's PostToolUse envelope and record the fields.
- Commit a REDACTED, minimal ring fixture under `tests/fixtures/` (only the junk-bearing events and a
  synthetic thread set).
- Freeze the expected labels.
- Take bug-100 into 19.0, or name its owner.

## MEH {#meh}

### MEH m-1: d5e item 4: edit-distance-2 folding on short tokens is a behaviour change with no threshold measured {#m-1}

At distance 2, every token of four characters or fewer has many neighbours. `ann`, `lru`, `bm25`,
`pql`, `cwd` and new identifiers with "no corpus match" yet would fold into words. Fold only at
length ≥ 5, measure how often a fold fires on the frozen ring before GREEN, and keep folding a label
choice only (the member keeps its raw form).

### MEH m-2: d4f: `CLAUDECODE` is inherited by every child of Claude Code {#m-2}

That includes hooks, the MCP server and `!` bash-mode commands. Today an explicit
`RMX_INVOCATION_SOURCE` wins (`telemetry.invocation_source`), which keeps hooks and MCP correct.
Two cases still change:
- `!`-typed human commands become `agent`;
- greps rewritten by the shim become `agent`, though the agent never chose rmx.

Spec the precedence (explicit > `CLAUDECODE` > tty > unknown). Make sure 21's adoption reading uses
`channel`, not `invocation`, to separate rewritten greps from chosen ones.

### MEH m-3: 16.6 R4's `stale_seen` still rides the coalescing, overflow-dropping queue {#m-3}

d4a moved 19.2 off it. 16.6 is crash-safe under d2a but lossy on overflow, and the decisions treat
it as an exact counter (plan-23 #b-2 lists it). It undercounts in the safe direction (it delays
removal), but the spec should say so, or give it the same no-drop overflow.

### MEH m-4: d3c counts the reader retry with no surface {#m-4}

This is the fourth "count with no surface" in the ledger (`#imp-count-in-a-dict`). Name where the
count lands: a `query.log` field or a daemon health key.

### MEH m-5: d2a and d3b were confirmed by the same quoted answer {#m-5}

Both are confirmed by the identical text "1 - yes agree" (`290e040`). Record which question that
answer replied to, or confirm that it answered both.

### MEH m-6: the blanket "MEH items" in every #tN-fixes paragraph enumerates nothing {#m-6}

List the MEH ids carried, so a reviser cannot drop them silently. Plan-22 #m-7 belongs with
[[#b-1]].

## Per-decision verdicts {#per-decision}

| id | verdict | why |
|---|---|---|
| d1a | sound | closes 17 #b-5, 19 #b-7, 21 #s-7, 22 #b-8 (sandbox half), 23 #s-7 |
| d1b | sound | — |
| d1c | needs-amend | 22.3's prerequisites; the `query.log` rows are not a catalog removal ([[#b-3]]) |
| d2a | needs-amend | confirmed; fragments, `replica_merge` and source retention unstated ([[#s-1]]) |
| d2b | needs-amend | the revisit "when Option A lands" is unanchored ([[#b-6]]) |
| d2c | sound | state the `bounded_steps` API ([[#s-3]]) |
| d2d | sound | — |
| d2e | needs-amend | no owner, no decision rule, no gate ([[#s-2]]) |
| d3a | needs-amend | no ratio cap, no restore reader, cross-plan restore ([[#b-5]], [[#s-7]]) |
| d3b | sound | confirmed at `290e040`; specify tag lifecycle across failed runs |
| d3c | sound | retry count needs a surface ([[#m-4]]) |
| d3d | sound | closes 17 #s-3 |
| d3e | needs-amend | retries and single-flight ([[#s-6]]) |
| d4a | needs-amend | tail-reader mode, tick registry, global route ([[#s-3]], [[#s-4]]) |
| d4b | sound | closes 21 #s-9 |
| d4c | needs-amend | source-log and public-repo privacy; fixture filter ([[#s-8]]) |
| d4d | needs-amend | last range unanchored; symbol set unowned ([[#b-6]], [[#s-9]]) |
| d4e | sound | closes 21 #m-7 |
| d4f | sound | precedence note ([[#m-2]]) |
| d5a | unsound | "reaps" protected rows outside plan-22; expansion deferral unanchored ([[#b-1]], [[#b-6]]) |
| d5b | sound | now also depends on 19.0 (d5e) |
| d5c | unsound as recorded | contradicts ADR `#rule-asserted-floor` without amendment; source not computable ([[#b-2]]) |
| d5d | sound | closes 19 #s-1 |
| d5e | needs-amend | fixture, acceptance, discriminator, typo fold ([[#s-10]], [[#m-1]]) |
| d6a | sound | closes 22 #b-4 for the 48 |
| d6b | needs-amend | unowned cross-store path; root set; ≥ 114-row flip ([[#b-4]]) |
| d6c | sound | matches the decay rule |
| d6d | needs-amend | 22.1 split, 16.6 header, Wave 1 list ([[#b-3]]) |
| d6e | needs-amend | parity test, explicit-root refusal ([[#s-5]]) |
| d7a | sound | closes dn-1 with the corrected reason |

Totals: 15 sound, 13 needs-amend, 2 unsound (d5a, d5c). {#per-decision-body}

## Answers to the seven questions {#answers}

1. **Closure.** One id is uncited (plan-23 #s-3). Four are partial or inverted (17 #b-4, 19 #s-4,
   19 #s-7, 22 #b-8). The MEH findings are unenumerated.
2. **Consistency.**
   - d2a vs d4a vs 19.2: consistent only with a tail-reader mode and source retention
     ([[#s-1]], [[#s-3]]).
   - d6b vs the memory-only guard: consistent. d6b vs store-via-daemon: it needs a two-daemon
     protocol nobody owns ([[#b-4]]).
   - d1c vs d6d: 22.3's chain is not in Wave 1 ([[#b-3]]).
   - d3b/d3c vs d3a: consistent. Different artifacts protect different readers.
   - d5b vs d4a/d4d: consistent.
   - d2e vs d2b: d2e's data has no consumer that d2b schedules ([[#s-2]]).
3. **ADR and memory rules.** d5a contradicts `#rule-no-delete` ([[#b-1]]); d5c contradicts
   `#rule-asserted-floor` ([[#b-2]]); 17's reap needs scoping against `#rule-no-delete`
   ([[#s-7]]). Store-via-daemon is at risk in d6b and in the global-hit fold ([[#b-4]],
   [[#s-4]]).
4. **Hidden decisions in the fix paragraphs.**
   - "Stale-subject reaping" ([[#b-1]]).
   - "Learner auto-protect distinguished": how existing protections are backfilled ([[#b-2]]).
   - "Name-keyed global hits": which store counts them ([[#s-4]]).
   - "Rename merge-on-collision": which counters and protection win in a merge.
   - The overflow route and log-row removal for `query.log` ([[#b-3]]).
5. **The two flagged assumptions** are confirmed at `290e040` (one quoted answer for both,
   [[#m-5]]). d2a's mechanism still needs [[#s-1]]. d3b is sound.
6. **Waves.** There is no true cycle. There is one inversion (16.6 depends on 16.1, Wave 2) and a
   missing chain (22.1a → 22.2 → move op → 22.3). The corrected order is in [[#b-3]]. d2e is
   parallel and gates nothing.
7. **Scope with no owner.**
   - the cross-store move ([[#b-4]]);
   - the global-hit fold ([[#s-4]]);
   - the tail-reader drain and tick registry ([[#s-3]]);
   - the precomputed symbol set ([[#s-9]]);
   - the Option A prototype for d2e ([[#s-2]]);
   - the orphan-list restore op ([[#b-5]]);
   - the `CLI_ONLY` verb class ([[#s-5]]);
   - the protection-source backfill ([[#b-2]]).

   The row-level `facts.log` events have a home (22.2) and are fine. {#answers-body}

## Verdict {#verdict}

**DIRTY.** 22 findings: 6 BULLSHIT (b-1..b-6), 10 SKETCHY (s-1..s-10), 6 MEH (m-1..m-6). The user
must revisit:
- d5a and d5c (unsound);
- d6b (the ≥ 114-row flip and the root set);
- d4c and d5e (public-repo privacy);
- the `query.log` removal mechanism (d1c);
- the global-hit counter home (19 #s-4).

The rest are spec amendments the orchestrator can carry. {#verdict-body}

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| a192ba2 (+83bc43d d5e, 290e040 confirmations; decision-log review of plan-review-2026-10-14; written 2026-10-14T12:06:28-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 22 (6B/10S/6M) | [[bsd-decision-log-review-a192ba2]]: 15 sound / 13 needs-amend / 2 unsound (d5a, d5c). BULLSHIT: d5a "compile reaps stale subjects" = removal outside plan-22 (inverts 19 #s-7's "not deleted"); d5c narrows ADR #rule-asserted-floor with no amend and needs a protection source that does not exist; 22.3 not runnable in Wave 1 (22.1→16.6 R1, 22.2, 16.6→16.1 inversion; query.log rows are not catalog); d6b cross-store move unowned, "registered root" undefined, ≥114 rows flip recover→forget; 17 #b-4 ratio cap + orphan-list reader dropped; three unanchored deferrals (d4d >1 s, d2b, d5a). Uncited: 23 #s-3. SKETCHY: d2a fragments/replica_merge/retention; d2e no owner/rule; tail-reader drain; global-hit route; d6e vs parity test; d3e retries; restore across 17/22; d4c public-repo queries; d4d symbol-set writers; d5e gitignored fixture, judged AC, unprobed subagent discriminator. |
```

last_run.log line:

```
2026-10-14T12:06:28-0700 commit=a192ba2 verdict=DIRTY findings=22 (6B/10S/6M) report=2026-10-14-1206-decision-log-review-reaps-asserted-and-unowned-paths-a192ba2.md
```

IMPRESSIONS.md bullets:

- 2026-10-14 (decision-log review): A DECISION LOG REWRITES FIXES AS IT SUMMARIZES THEM. 19 #s-7
  said "excluded, not deleted; removal via plan-22", and the log recorded "reaping". When a log
  paraphrases an auditor's fix, diff the verb, not only the id. {#imp-paraphrase-flips-the-verb}
- 2026-10-14 (decision-log review): "NEEDS X" IN A DECISION IS AN UNOWNED TASK. d6b ("needs a
  cross-store write path"), d2e (no task), d4d's symbol set and d3a's "can be undone" each name a
  mechanism with no task spec. Treat "needs/requires/can be undone" in a decision row as a rule-9a
  probe. {#imp-needs-x-is-unowned}
- 2026-10-14 (decision-log review): A DEFERRAL ANCHORED TO A MEASUREMENT MUST NAME ONE THAT
  MEASURES THE THING AND IS STILL IN THE FUTURE. d4d deferred a hook-latency decision to a
  write-concurrency probe scheduled two waves earlier. {#imp-anchor-must-measure-the-thing}
