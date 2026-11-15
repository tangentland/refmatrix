---
gmd: "0.1"
id: plan-review-fable-2026-11-14-store
title: "Plan review (Fable), 2026-11-14: store, daemon and measurement tracks after 0.83.0"
tags: [plan-review, store, daemon, measurement, plan-16, plan-17, plan-18, plan-22, plan-23, plan-28, plan-29]
metadata:
  node_type: review
  status: archived
  created: 2026-11-14
  updated: 2026-11-14
---

# Plan review (Fable): store, daemon and measurement tracks after 0.83.0 {#root}

> **ARCHIVED 2026-11-15** (the user: "archive any other doc that acts as an alternate source of truth").
> Not a source of truth: order, scope, status and the live L / D / Q ledgers are in [[plan-of-plans]];
> finished items are in [[pop-finished]]. This file is kept unchanged otherwise, as history and evidence;
> its ids and anchors still resolve.


**Verdict: no task in T4, T5, T6 or the measurement lane is ready to start its RED as written.**
Fourteen findings block a RED or a GREEN, and every spec needs one freshness revision. Three causes
account for nearly all of it:

1. **The three spec branches forked at `1cf3b9f`, before bug-212, bug-216/227 and bug-230 merged.**
   0.83.0 added a catalog-opener census, a `pending_refs` table, four replay ops
   (`pending_ref`, `pending_ref_delete`, `pending_refs_clear`, `rel_evidence_clear`), `denotes`
   links and an id-remapping replica merge. Plan-22, 18.2, 18.3, 22.5 and 22.6 mention none of
   them (zero hits for `pending_ref`, `denotes`, `rel_evidence_clear`, `bug-212`, `bug-227`).
2. **Plan-29 is in no merge order.** Every T4-T6 `#merge-order` predates L104, about 43 new
   wall-clock assertions would fail 29.4's census, and at least seven specs pin AST checks to
   `store.py`, `cli.compact` or a non-recursive `src/refmatrix/*.py` glob that 29.5 breaks.
3. **bug-241 landed after the specs froze.** bug-216 AC-6 fails live, its RED is held by the
   user, and bug-185's golden, the `denotes` fold evaluation and plan-22's recounts all read the
   state it leaves wrong.

The designs survive. Nothing 0.83.0 shipped invalidates a plan's approach; the work is revision,
not re-planning. {#verdict}

rel: derives-from -> [[plan-review-2026-11-13]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[bug_registry]]
rel: evidence-for -> [[task-bug185-bulk-gmd-ingest]]
rel: evidence-for -> [[plan-23-bounded-write-harness]]
rel: evidence-for -> [[plan-16-invisible-grep-shim]]
rel: evidence-for -> [[plan-17-nightly-store-maintenance]]
rel: evidence-for -> [[plan-18-duckdb-store-maintenance]]
rel: evidence-for -> [[plan-22-audited-removal-and-repair]]
rel: related-to -> [[open-questions]]

## Method and limits {#method}

- **Read:** the latest text of 49 spec files, about 28,000 lines: `spec-wave-t4` (`b409d98`),
  `spec-wave-t56` (`fa1af7d`) and `spec-wave-t3c` (`01c1f63`) where a branch changed the file,
  master otherwise. Eight forks each read one slice in full and checked its code claims against
  master `src/refmatrix` and `tests/`.
- **Verified by the reviewer directly:** the evidence behind every BLOCKER (spec quote and master
  code line), the registry rows cited, the duckdb versions and the ADR-0004 hunk overlap.
  SHOULD-FIX and NOTE evidence is as the forks read it.
- **Nothing was run.** No test, no probe, no store open, no `rmx` write verb. Every behavioural
  claim is from reading source. Mutation-survival arguments (for example
  [[#s226-rel-fixtures-predate-rel-evidence-clear]]) are derived, not demonstrated.
- **Master moved during the review**, from `f3709d2` to `cfb9de5` (bug-241 row; Q22 withdrawn).
  Line numbers below are master at `cfb9de5`.
- **Spec paths:** `workflow/plans/<plan>-tasks/<task>.md` unless stated; `t4`, `t56`, `t3c` name
  the branch that holds the text cited. {#method-list}

## Cross-cutting findings {#cross-cutting}

### BLOCKER: bug-241 gates bug-185's golden, the fold evaluation and plan-22's recounts {#bug185-red-waits-on-bug241}

- **Evidence:** `workflow/bug_registry.md` row bug-241: after the 0.83.0 deploy and the forced
  reingest, both rule docs are stored only as plain relpath-named `doc` rows; `claude: 234` and
  `project-profile: 38` targets unresolved; cause "NOT MEASURED". `open-questions.md` Q22: the
  bug-241 RED dispatch "stays held until the user says otherwise".
- **What it blocks:**
  - bug-185 `#ac-2` (t4) records its golden "at HEAD … regenerated, never adapted" and treats
    "bug-216 merged" as sufficient. A golden taken now can pin a bug-216 defect on the path
    bug-185 rewrites.
  - The `denotes` fold evaluation (G30, t3c) needs "its live recount (AC-6) recorded". AC-6 fails.
  - 22.1a AC-8d and 22.6 R10 recount on "the post-re-ingest store"; that store is the wrong one.
- **Symptom match, cause not measured:** `ingest.py:1407-1421` wraps `ingest_gmd_paths` in
  `except Exception:`, then registers each GMD path as a plain `doc` named by relpath, inside
  `except Exception: pass`. That is the row shape bug-241 reports. No causal link is shown.
- **Fix:** bug-241 is root-caused before bug-185's RED commit. bug-185's header gate and `#ac-2`
  ancestry check gain "bug-241 fixed and merged when its fix touches `ingest_gmd.py`,
  `ingest_path`'s GMD dispatch or `sync._sync_one`". G30's Depends-on gains "R4's forced reingest
  re-run after bug-241, recount recorded". See [[#d1]].

### SHOULD-FIX: plan-29 is absent from every T4-T6 build order {#plan29-absent-from-build-orders}

- **Evidence:** bug-185 `#merge-order`, plan-23 `#merge-order` (plan-23 `:41` still says "Wave 1's
  FIRST build"), 23.1 `#merge-order`, the 23.2, 23.3 and 23.5 headers, plan-17, plan-18 and
  plan-22 `#dependencies` all predate L104.
- **Fix:** each gains "plan-29 (29.4, 29.5) →", and one re-stamp on the post-29.5 tree. L104
  re-points line numbers only; the re-stamp must also cover qualified names and AST globs
  ([[#ast-pins-break-under-29-5]]).

### SHOULD-FIX list, cross-cutting {#cross-cutting-should-fix}

- **Queue text contradicts later rulings.** `plan-review-2026-11-13.md#queue` item 7 still says
  "(user-gated: the start) … runs ≥ 14 days in the background" and L45 still says "randomises
  live sessions ≥ 14 days". L78 delegated the start and L83 removed the live leg and the time box.
  Item 9 still carries "D-Q1's live purge, if Q8 makes it one"; D-Q1 is final with no purge, and
  plan-22 has no such step. L28's premise is wrong for plan-18: 18.2 R9 declares
  `requires_arming=False`, so `catalog_maintain` runs for real from its first tick.
  {#queue-text-stale}
- **User gates the queue does not mark** (L45 takes gates from the specs): bug-185 R9's index
  build on every fleet catalog at daemon start (item 5); 23.4's re-pin (item 8,
  [[#t23-4-replay-op-mapping-predates-0830]]); 22.6's first live vacuum (834,201-row manifest
  inside one `_store_lock` hold), bug-218 R4's per-store `--apply`, D-Q1 R6's fleet re-derives
  and 22.5's live bucket-1 move (item 9); `rmx learn on --global`, the `RMXGREP_MODE` delete and
  the fleet `install-hooks --apply --force` that reaps the enforce entry (item 10; L77 covered
  0.83.0 only); 18.2 R10's hand runs on live stores (item 11). {#queue-gates-unmarked}
- **The D-Q1 task (G22) has no queue slot** and no plan-of-plans row on master.
  {#dq1-no-queue-slot}
- **ADR-0004 will conflict at the second merge.** T56 and T3c both insert a decision-log bullet
  at the same place (`@@ -343,6` in both diffs). The contents are complementary. Keep T3c's
  bullet contiguous with its three `rel:` lines, or those edges attach to T56's node.
  {#adr0004-two-branch-conflict}
- **ARCH-DRIFT, ADR-0004 `#a14-removal-scope`:** it allows derived cleanup outside plan-22 "only
  with a manifest written before the change". The 0.83.0 removers (`clear_rel_evidence`, the
  pending-ref deletes, the merge's vector-owner deletes) are logged and replayable but write no
  manifest. The ADR should gain a class "re-derived in the same operation, logged, replayable:
  no manifest"; the code is right. I own the ADR layer and will draft the line when asked.
  {#adr0004-a14-manifest-rule}
- **Tree walks for fleet discovery:** bug-218 `#r0b` and D-Q1 `#r6` find stores by
  `grep -l` over `~/github`, `~/claude_tools` and `~/enduris`. L77 requires the known candidate
  list. 17.3 `#r1-hand-run` and 18.2 R10 name a stale eight-store roster (thiquet's daemon is
  gone, atlftpd is new). All four read the roster from `discovery._roots_from_launchd()` at
  start. {#fleet-list-stale}
- **Body status drift:** bug-218 and D-Q1 have frontmatter `approved` and a body "Status:
  Drafting"; plan-28, 28.1 and 28.5 say "pending a confirm-lite" beside their approval rows;
  18.3's Q-A and Q-E still read "Recommended". {#body-status-drift}

## T4 findings: bug-185, plan-23, 16.6, plan-17, plan-18 {#t4}

### BLOCKER: 23.1 R11 rebuilds the promote path bug-212 removed {#t231-promote-digest-predates-bug212}

- **Spec:** 23.1 `#r11` items 4-5 (t4 `:1224`, `:1246`): `_promote_digest` passes `local=` "its
  EXISTING in-process closure (the `Store(root)` + `with_partition` + `add_memory` …)", and a
  held writer "today turns it into a `promote skipped: … busy` line".
- **Master:** `handoff.py:512-521` routes through `verbs.local_write(…, create=True)`. A
  hand-rolled `Store(` in `handoff` fails the opener census (`tests/test_bug212_r4_red.py`
  `:252-268`, `:628-645`). `_write_or_local` (`verbs.py:601-611`) has no `create=`, so routing
  through it breaks `test_the_save_state_promote_creates_a_missing_catalog`
  (`tests/test_bug212_r5_red.py:459`). A held writer today is `SaveStateIncompleteError`, CLI
  exit 1, MCP isError.
- **Fix:** `_write_or_local` gains `create: bool = False`; `_promote_digest` passes
  `create=True`; no `Store(` in `handoff.py`. A `{"queued", "name", "note"}` promote is a success
  and stays out of `save_state`'s `failed` list. AC-21 step 2 asserts `rmx save-state` exits 0
  under the held writer (RED on master: exit 1).

### BLOCKER: 16.6 retired its merge requirement on a premise that is now false {#s166-r1c-retirement-premise-false}

- **Spec:** 16.6 `#r1c` and AC-2 (t4 `:376`, `:672`): retired because "`replica_merge` is broken
  on every real store (bug-113, open)".
- **Master:** bug-113 is fixed (0.79.0). bug-227 made `merge_slots` an id-remapping merge over an
  explicit table list (`replica_merge.py:63-77`, `:105-110`), and L81/L99 set the rule that a new
  id-keyed table follows both merges (`Store._merge_pending_refs`, `store.py:1961`). 16.6's
  `learned_evidence` sidecar would come out of `rmx replica merge` empty, uncounted, and
  `merge_partition` would remap ids past it.
- **Fix:** reinstate a reduced R1c. The sidecar joins `OPTIONAL_TABLES`, both remaps (chained per
  L99) and `merge_partition`, with an AC through `_op_replica_merge`. Add bug-124's cheap half
  here or in 29.3: a census that every `init_catalog` table is handled by `merge_slots` or on a
  named skip list. 23.1 R8 adds three more tables and has the same gap
  ([[#t4-should-fix]]).

### BLOCKER: 17.4's restore step cannot run {#s174-restore-step2-cannot-run}

- **Spec:** 17.4 `#r6-restore` step 2 (t4 `:185-190`): copy the log to
  `<mkdtemp>/.refmatrix/facts.log`, then `rmx rebuild --from-log` with
  `REFMATRIX_ROOT=<mkdtemp>`. AC-3 has the same shape.
- **Master:** `REFMATRIX_ROOT` is the store root itself (`cli.py:130-132`), so the log is looked
  for at `<mkdtemp>/facts.log`; and `_store_rw` raises "no refmatrix at … Run `rmx init` first"
  when the catalog is missing (`cli.py:272-275`), before `rebuild` reads anything.
- **Fix:** the root is `<mkdtemp>/.refmatrix`, and `rebuild --from-log` creates the catalog
  through a checked `create=True` opener. The same step 5 promote copies a catalog onto a live
  slot from `scripts/`, outside the census (`SRC.rglob`); it calls
  `store.refuse_tracked_catalog_open(root, dst, names=(dst.name,))` first, as
  `migrate-to-duckdb` does (L98, L102).

### BLOCKER: 18.3 R10 deletes the code two bug-212 census tests require to exist {#p18-compact-retire-breaks-bug212-census}

- **Spec:** 18.3 `#r10-compact` (t4 `:781-782`) deletes `rmx compact`'s "in-process
  `duckdb.connect`", its daemon stop and its restart. 18.3 `#files-to-modify` names no bug-212
  test.
- **Master:** `cli:compact` is a `CHECKED_OPENER` and a "sees" anchor
  (`tests/test_bug212_r4_red.py:255`, `:486-487`); the stale-entry test (`:645`) fails when a
  listed site stops opening; `tests/test_bug212_r5_red.py:84` and `:110` assert compact refuses a
  tracked catalog, before it stops the daemon; `docs/INTEGRATION.md` states the claim.
- **Policy change hidden in it:** at 0.83.0 `rmx compact` refuses on a git-tracked catalog.
  After R10, `rmx compact --confirm` swaps that committed file through the daemon. See [[#d2]].
- **Fix:** R10 and AC-13 name the census edits (drop `cli:compact`; re-anchor the raw and move
  "sees" guards on a surviving site), replace the two r5 tests, and correct INTEGRATION.md.

### BLOCKER: 18.3 R8 adds catalog sites the opener census will reject {#p18-new-catalog-sites-unlisted-in-opener-census}

- **Spec:** 18.3 R8 adds `CatalogHold.swap` (`os.replace(new, slot)`), a
  `python -m refmatrix.catalog_maint` child opener and `Daemon._rebind_init_slot`, and moves the
  `shutil.copy2` out of `_bootstrap_rotation_if_needed`.
- **Master:** the census scans `SRC.rglob("*.py")` for `Store(`, raw opens, moves and copies onto
  a catalog name (`test_bug212_r4_red.py:406-437`); `_bootstrap_rotation_if_needed` is on
  `UNCHECKED_ALLOWED` (`:267`) and its copy is a "sees" anchor (`:624`).
- **Fix:** R8 and AC-14 state the `UNCHECKED_ALLOWED` delta with a reason per site, and the
  census file joins `#files-to-modify`.

### BLOCKER: 18.2's pre-registered CHECKPOINT census is wrong on its own base {#p18-checkpoint-census-stale}

- **Spec:** 18.2 R11 (t4 `:449-453`): "exactly 10 constants in these 9 functions", permanent
  exemption `replica_merge.merge_slots`.
- **Master:** 10 constants, but two sit in functions on no list: `_merge_into`
  (`replica_merge.py:696`; `merge_slots` holds none) and `Daemon._repair_missing_slot_locked`
  (`daemon.py:1470`). Both exist at the branch's own merge-base `1cf3b9f`. AC-17 is red on
  18.2's correct code.
- **Also missed:** 18.3 R8's "no `_copy_out_of_process(` outside the helper" ignores
  `_repair_missing_slot_locked` (`daemon.py:1478`, called from the merge op at `:6034`), and
  `_op_rebuild_index` closes the writer, unlinks `db_path` and re-inits under `_store_lock` with
  no CHECKPOINT literal for the AST rule to see.
- **Fix:** re-run the census at master; name `_merge_into` permanent; stage or exempt the other
  two by name with a reason.

### SHOULD-FIX list, T4 {#t4-should-fix}

- **bug-185, silent fallback.** bug-185 makes writes set-based and atomic
  (`backend.py:720`), so one bad row fails the batch, and `ingest.py:1407-1421` then strands every
  GMD doc of the tree as a plain doc with no count. The hash-stamp failure prints only
  `if verbose` (`ingest_gmd.py:1955-1960`). Add a requirement and AC: a failed bulk write is
  counted in `IngestStats` and exits non-zero. {#bug185-silent-fallback-in-ingest-path}
- **bug-185, post-merge wording.** L3 is folded (`#r2` steps 2-3, `#r8`, `#ac-2`) and master
  matches what the spec assumed. Stale: header `:44` (now satisfied at `7aed8df`);
  `#open-replay-216` ("on its branch until it merges"); `#rev-round-2-facts` says the clears do
  not call `_log_event`, and master logs all of them (`store.py:6132`, `:6188`, `:6210`);
  `#ac-5`'s keep-green list names none of the 22 `tests/test_bug216_*.py` files; `#r9` changes
  `clear_rel_evidence`'s return type without stating the signature. {#bug185-post-merge-wording}
- **L3's order edge is missing.** L3 and L62 M4 say bug-216 gains an order edge to bug-185.
  Master's bug-216 spec does not mention bug-185. {#l3-order-edge-missing}
- **23.1 R8 is stale against the rewritten merge.** "Explicit 10-table list" is 11 with
  `pending_refs`; the spec invents a mechanism master already has (`OPTIONAL_TABLES` plus
  `_has_table`); "no textual overlap is expected" is false after bug-216/227's +237 lines; the
  required `writer_side=` keyword touches 19 direct test call sites, not 13.
  {#t231-r8-merge-text-stale}
- **23.1 should split three ways.** It is 2,102 lines, R1-R11, 21 ACs, nine source files; the
  0.83.0 fixes took 3-7 ch-bsd rounds at a fraction of that. Cut: **23.1a** R1.1-R1.5, R2-R10
  (harness, queue, tail; closes bug-099, bug-106); **23.1b** R1.6 and AC-20 (`_FairLock` owner;
  all that 23.5 R4 and plan-18 need); **23.1c** R11 and AC-21 (`hook_writes`; closes bug-177).
  {#t231-split-three-ways}
- **23.1 and `task-compaction-as-handoff` collide.** 23.1 `#facts` round 12 rests on "No
  generated hook reaches `_promote_digest`". True today (`hooks.py:178`), false once L90's task
  makes PreCompact run save-state with promote. Each spec gains an edge to the other and says
  whether a hook-run save-state may take the in-process branch.
  {#t231-save-state-becomes-hook-path}
- **23.5 AC-5 cannot see a dropped pending ref.** It compares the rebuilt log "BY NAME (entities,
  links, evidence and memory content)". `dump_catalog_to_log` now emits `pending_ref` events
  (`store.py:8665-8683`). Add `pending_refs` and `denotes` links to the equality, with the
  mutation "dump-to-path omits `pending_ref`". {#t235-ac5-omits-pending-refs}
- **23.5 R5 does not say what a non-JSON tail line does.** bug-119 is that shape and has no
  owner. The line is copied verbatim and counted, with an AC. {#t235-r5-unparseable-tail-line}
- **23.3 predates 26.2.** `#r5` lists six report keys, master returns eight (`sync.py:442-446`);
  the per-path `MemoryOwnershipError` catch and `raise_if_refused` appear in no requirement.
  `#r4` ("nothing is stamped done while a later step still owes it work") conflicts with
  bug-185 `#r2` step 9, which stamps a GMD doc's hash before its later semantics step.
  {#task233-stale-vs-26-2}
- **23.0 is `completed` with two ACs open.** Its implementation summary says tiers 1 and 2 "were
  not run … AC-7/AC-8 stay open"; no deferral row. `#r3` forbids "any `open` (write OR read)",
  and bug-230 added a read-only allow for `.refmatrix/.refmatrix_ignore`
  (`tests/sandbox_site/rmx_sandbox.py:270-274`). 29.4's spec amends 23.0 and adopts or defers
  the tier ACs. {#task230-completed-with-open-acs}
- **17.1 R9's filter must not reach the shared executor.** The spec filters
  `_drop_lance_for_purge_batch` to ids with `vectors_updated_at IS NOT NULL`. On master that is a
  wrapper over `_delete_vector_groups` (`store.py:4192`), which the replica merge calls after
  setting the stamp to NULL (`replica_merge.py:461`). A filter in the executor skips every merge
  delete: bug-227's wrong-owner-vector class. State where the filter lives and add the mutation.
  {#s171-r9-filter-must-not-reach-shared-executor}
- **17.1 R10 restores "under the SAME id".** 0.83.0 established that an id is not an identity
  (L99, L101: vacated ids get new holders). A same-id restore from an older orphan list writes a
  dead entity's vector onto a live one. Orphan-list lines carry a catalog generation, or restore
  is refused across a merge or rebuild without an `id_map`. {#s171-same-id-restore-after-id-moves}
- **17.1 leaves two orphan rules and a stale reader list.** `gc_vectors` and `embed --gc` stay,
  and 0.83.0's loud-failure text sends users to `rmx embed --gc` (`store.py:4131`). `#r4-readers`
  names `_replica_memory_recall` at `cli.py:10971`; 25.1 moved it to `recall.py:930`, and three
  more out-of-daemon Lance reads exist. {#s171-two-orphan-rules}
- **17.2 would be the hub's second scheduler.** `#why` says the hub's only periodic loop is
  `_queue_alert_loop`. The hub also starts `scheduler.Scheduler` (`hub.py:437`, `:981`) with its
  own `rmx schedule` CLI, a bare `except Exception: pass` and child output to DEVNULL. It is idle
  (no `~/.refmatrix/schedule.json`). Recommended, settled as the user would ("two ways to do X:
  collapse to one"): 17.2 retires `scheduler.py` and `rmx schedule`, after checking no fleet
  store holds a `schedule.json`. {#s172-second-hub-scheduler}
- **16.6 smaller items.** AC-12's string scan fails on `tests/test_bug216_replay_fidelity.py`
  (its docstring names `apply_log_delta`); `#r5` backfills dead-ended rows through `row_event`,
  which raises on a None end. {#s166-smaller}
- **18.x smaller items.** bug-123's row says 18.3 R8 fixes the swallowed CHECKPOINT error; R8
  says "Behaviour is unchanged" and has no AC (`store.py:4381-4384`). 18.3 R8 still says "one
  signature must win before 23.1 is built"; 23.1 settled it (d9cd). 18.2 R10 seeds baselines
  from 2026-10-15 measurements that predate the forced reingest. {#p18-smaller}
- **Dev venv is below the package floor.** `pyproject.toml` requires `duckdb>=1.5.3`;
  `.venv-eval` has 1.5.2 and the deploy venv 1.5.3. 18.3's facts I4/I10/I11/I13 are 1.5.3
  probes and its mutation kills depend on them. An environment gap; see [[#d5]].
  {#p18-duckdb-version-gap}

### NOTE list, T4 {#t4-notes}

- Already in master, so not work: `backend.bulk_write`, `bulk_upsert_entity`,
  `_bulk_add_concepts`, `bulk_link(update_weight)`, `OPS["denotes_link"]`. Not in master:
  `bounded_steps`, `tests/lockhold.py`, every `gmd_*` entry point, `bulk_add_pending_refs`.
  {#t4-what-exists}
- 23.1 R1.6 item 3 lists three purge entry points as Lance writers; bug-227 added
  `Store.drop_vector_rows` inside `_op_replica_merge`'s hold (`daemon.py:6066-6068`).
  `purge_entity` now deletes `pending_refs` too, so AC-20's "three catalog tables unchanged" is
  four. {#t231-r16-new-lance-writer}
- `_op_denotes_link` is a new whole-store holder on the bg pool (`daemon.py:4804-4824`); 23.5
  R8's census will find it. It defaults its partition outside the lock, one of 20
  `args.get("partition") or d._st()._partition_name` sites: a 29.3 helper candidate.
  {#t235-new-holder-denotes-link}
- 18.3 is not an offline reclaim since d9bf: it is an in-daemon rewrite-and-swap under one
  `_store_lock` hold. The file name is kept for link stability. `COPY FROM DATABASE` copies the
  writer's schema, so `pending_refs` is carried. 18.1 is done and merged (`530660e`).
  {#p18-not-offline}
- Verified unchanged: the dispatcher sets `expires` only for cli reads (`daemon.py:3356-3359`);
  `_call(retries=0)` probes once, so 23.5's timed ACs are not tripled; 16.6 `#rev-round-15`'s
  fold rules match master's rebuild; L21/L40 order is consistent across plan-17. {#t4-verified}

## T5 findings: plan-16 {#t5}

### BLOCKER: 16.1 AC-5d would remove a clause bug-216 shipped {#p16-watch-corpus-identity-regresses-l94}

- **Spec:** 16.1 `#r3-predicate` and AC-5d (t56 `:338`, `:511`): the predicate is the suffix gate
  and `not ingest.should_ignore(…)`, "nothing else", and
  "`watch.is_relevant is corpus.is_relevant`".
- **Master:** `watch.py:29-48` has a third clause before `should_ignore`:
  `if is_builtin_include_path(p, root): return True` (remedy M1-r2, L94). It lets a deleted or
  de-GMD'd rule doc reach `_sync_one` for purge.
- **Consequence:** identity either deletes that clause, or puts it in the learner's predicate,
  which then teaches a `CLAUDE.md` the ignore file excludes.
- **Fix:** `corpus.is_relevant` is the suffix gate plus `should_ignore`.
  `watch.is_relevant` is `is_builtin_include_path(p, root) or corpus.is_relevant(p, root)`. AC-5d
  asserts the call and "no other rule", not `is`. Fold `context._grep_backstop`
  (`context.py:966-978`), an existing hand-composed copy, onto it.

### BLOCKER: two approved specs give the learn queue incompatible keys {#p16-learn-queue-key-drops-provenance}

- **Spec:** 16.1 `#r10` (t56) puts per-record rules (`tool`, `bin`, `match_argv`, `locale`) and a
  per-hit `line_hash` in the queue record; AC-15 needs two readings for one pattern under two
  locales. 23.1 `#r9` (t4 `:982`) pins `key_fn=pattern+partition, merge_fn=UNION by (file, line)`.
- **Master:** `learn_queue.enqueue(root, pattern, hits)` (`learn_queue.py:55`) and `read_rotated`
  (`:92`) coalesce by pattern alone. 16.1 `#files-to-modify` omits `learn_queue.py`.
- **Fix:** 16.1 names the record schema and the key `(pattern, partition, rules_sha)` and lists
  `learn_queue.py`; 23.1 R9's `key_fn` is amended in the same revision.

### SHOULD-FIX list, T5 {#t5-should-fix}

- **The learn sink has no predicate.** `daemon._learn_grep_hits` (`daemon.py:4543-4585`) upserts
  any path as a protected entity. Between 16.1 and 16.5 the legacy `rmx grep` broker still feeds
  it unfiltered. Apply `corpus.is_relevant` at the sink, counted. {#p16-sink-has-no-predicate}
- **16.5's path-less leg meets the bug-212 refusal.** With no replica and no daemon, master runs
  `_store()` then `_store_rw` (`cli.py:6705-6707`) and prints `Error:` with exit 1, which is
  grep's "no match". 16.5 `#r3` needs a row "index unavailable (refused or absent)": the floor
  runs with one stderr note, never exit 1. {#p16-tracked-catalog-index-leg}
- **16.5 R6 names the wrong tuple.** `_outcome_of` tests `CALL_OUTCOMES` (`telemetry.py:87`,
  `:191-195`), added by 21.1, not `OUTCOMES`. {#p16-telemetry-wrong-tuple}
- **Verb parity is unaddressed.** 16.1 R7 says `grep-learn` goes on `verbs.INTERNAL_CLI` "once
  task 3.4 lands"; it landed (`verbs.py:3531`). `("grep",)` sits in `LEGACY_UNPAIRED` as
  "invoked by a generated hook"; after 16.3 no hook calls it. The map is shrink-only, so 16.3 or
  16.5 needs a decision row. {#p16-verb-parity-unaddressed}
- **16.3 carries dead conditionals.** "bug-118 is unmerged", "If 16.3 lands first…" and AC-10's
  "tree without bug-118" clause; bug-118 shipped in 0.79.0 (`hooks.py:509`).
  {#p16-bug118-conditionals-stale}
- **16.3 AC-5 re-scans the installed Claude Code binary** each run (33 s, 235 MB), fails on every
  auto-update and cannot resolve `~/.local/bin/claude` under the sandbox's redirected `HOME`.
  Move it to a deploy-time gate or a named 29.4 tier. {#p16-binary-extraction-test}
- **16.4:** arm A is "a `git worktree`"; the standing rule is a littlebig clone. `#r4-reopen`'s
  2026-12-31 date will fire with n near 0 now that plan-29 and items 2-9 come first; anchor it to
  the flip plus N days, starting at the later of the flip and 16.4's merge.
  {#p16-16-4-worktree-and-date}
- **Closure bookkeeping:** 25.4/25.5 are `superseded` in t56, but G24's plan-25 table amendment
  is not in the diff, and registry rows bug-167 and bug-174 still read "planned: task-25.4/25.5".
  {#p16-closure-bookkeeping}

### NOTE list, T5 {#t5-notes}

- No conflict with D-Q7, L2, L5, L42 or the two grep memories. `corpus.py` and `grep_learn.py`
  do not exist in master; 16.1 creates both. The learner, shims and hook open no store.
  {#p16-contradictions-clean}

## T6 findings: plan-22, bug-218, D-Q1 {#t6}

### BLOCKER: 22.2's restore cannot rebuild what a purge removes {#p22-restore-omits-pending-refs}

- **Spec:** 22.2 `#r4` (t56 `:250`): the before-state is enough to rebuild "every removed row by
  itself"; it lists entity row, vector, `memory_content`, `tracked_files`, evidence, links.
- **Master:** `purge_entity` deletes the source's `pending_refs` rows (`store.py:6860`).
  `_bulk_purge_ids`, the engine's purge per R2, deletes five tables and not `pending_refs`
  (`store.py:7236-7290`), leaving rows with a dead `source_id`.
- **Effect:** purge then restore of a doc silently loses its unresolved `rel:` lines.
- **Fix:** the intent record holds the pending rows; restore re-adds them through
  `add_pending_ref` with the source mapped by `id_map`; `_bulk_purge_ids` deletes them as
  `purge_entity` does; AC-4 compares pending rows by name.

### BLOCKER: 22.2's replay requirement describes a replay that no longer exists {#p22-replay-premise-false}

- **Spec:** 22.2 `#r3` and plan-22 d-32: "The replay knows only entity-level `tombstone` and
  append-only `evidence` today"; "never a pass per op family"; re-read at `23ad703`.
- **Master:** `rebuild_index_from_log` dispatches four more ops (`store.py:9010-9028`), and a
  `tombstone` drops the key's pending rows (`:9007-9009`). `rel_evidence_clear` is a filter over
  collected evidence events and is not count-neutral.
- **Fix:** R3 names the four ops and places `rel_evidence_clear` in the one timestamp-ordered
  pass; `FOLD_RULES` declares all four, or the "dispatch set equals the fold tables" test is RED
  on arrival; `restated_copy`, AC-3d and AC-4e are re-derived with clear events in the log.

### BLOCKER: 22.6's `rel:` fixtures and mutations predate `clear_rel_evidence` {#s226-rel-fixtures-predate-rel-evidence-clear}

- **Spec:** 22.6 AC-6b, AC-6e, AC-9b/9c, AC-10 (t56 `:627`): a re-ingest "re-creates the same
  name and appends the identical row".
- **Master:** `rel:` rows store the source at the concept end (`ingest_gmd.py:1881-1882`);
  re-ingest calls `clear_rel_evidence` per changed doc (`:1707`), logged and replayed as a drop
  of every earlier `rel:` copy for the file. The mutation "orphan-drop checks the materialized
  catalog … the copy holds 2" can then no longer fail. 22.2 states the direction reversed too
  (`#r2`, AC-3c/3d/4d), although 22.1a (t56 round 9) has it right.
- **Fix:** a freshness revision before RED, as L3 did for bug-185. Rebuild the fixtures on
  non-`rel:` rows or state ends and files explicitly, and re-trace every pre-registered mutation.

### BLOCKER: D-Q1 AC-5 orders a row that is never in the pack {#dq1-recall-leg-and-fifth-gate}

- **Spec:** D-Q1 `#r2` recall-pack row and `#ac-5` (t56 `:310-314`): the pack lists
  `project_session_0328` before `savestate_s1`.
- **Master:** hook-mode recall drops `session/*` by default through `verbs.recall_patterns`,
  "THE recall exclusion globs" (`verbs.py:1105-1115`). `savestate_s1` is never in the pack, so
  the assertion is vacuous. `recall_patterns` is a fifth operational gate that R0's inventory and
  AC-3's literal list do not cover.
- **Fix:** name the invocation and use a row that survives the filter; route the glob through
  `memory_layout` or record it as a named facet.

### SHOULD-FIX list, T6 {#t6-should-fix}

- **Removal inventories miss the 0.83.0 removers.** Plan-22 `#scope` and 22.6 `#r9` claim to
  classify every removal site. Unlisted: `clear_rel_evidence` (`store.py:6110`);
  `clear_pending_refs_for_file`, `delete_pending_ref` and `purge_entity`'s pending delete;
  `_merge_pending_refs`' `pending_refs_dropped` (`store.py:1994-1998`); the replica merge's
  name-loser drops and vector-owner deletes; `_sync_one` purging a rule doc that lost its
  frontmatter. {#s226-removal-inventory-missing-083-paths}
- **22.6 has no census that fails on a new removal site.** That is how the paths above went
  unseen. R9 becomes the allowlist of a resource-keyed census (`DELETE FROM` the five tables,
  `purge_entity(`, `_bulk_purge_ids(`, Lance `.delete(`), reusing bug-212's scanner
  (`tests/test_bug212_r4_red.py:329-404`). 29.3 extracts the scanner; 22.6 supplies the family.
  {#s226-no-removal-census}
- **22.6's facts are three releases old.** Round 17 says "re-read at `1cf3b9f`", but the last
  full re-read is `23ad703`. `purge_path` already keeps memory-owned anchors and can raise
  `MemoryOwnershipError` (`store.py:6984-7000`, 26.2); R4's `keep_learned=True` is a second keep
  rule on it and must compose. {#s226-facts-three-releases-old}
- **22.6 R10 needs a recount before it is built.** bug-219's 25,760 edge-less rows predate
  `clear_rel_evidence` and the forced reingest. Recount after bug-241, with a pre-registered band
  for whether step 3b (new op, replay branch, fold rule, ten mutations) is built at all.
  {#s226-r10-needs-recount}
- **22.2's Lance finalize has the wrong unit.** "Finalized once per kind after the loop";
  `_bulk_purge_ids` drops Lance inside every batch and has no deferral parameter. The 0.83.0 unit
  is the (partition, kind) table: one `drop_vector_rows` call, whose non-empty `errors` is
  recorded and exits non-zero. {#p22-lance-finalize-unit}
- **22.1a reads neither `pending_refs` nor `denotes`.** No class counts pending rows with a dead
  source; `orphan-alias`, "learned-only" and `empty-learned` do not say how a `denotes` link
  counts. Reference readings predate 0.83.0; label them so.
  {#p22-1a-pending-and-denotes-unread}
- **22.1a's candidate walk** covers `$HOME/github`, `$HOME/claude_tools`, `$HOME/enduris`
  (973,157 files) inside a daemon op with no duration bound. The user ruled out those walks for
  fleet discovery on 2026-11-14. See [[#d3]]. {#p22-candidate-walk-vs-no-walk-rule}
- **22.2's manifests hold memory bodies and vectors** under `.refmatrix/removal/`. Fleet repos
  that track store files may not ignore that path, and `rmx save-state --commit` runs
  `git add -A`. Refuse or warn when git does not ignore it. {#p22-manifests-in-tracked-store-dirs}
- **22.3:** AC-1's "N ≤ 90" is a 2026-10-14 measurement, not a cap. AC-4's restore check runs on
  a pre-apply clone and is vacuous; make it apply-then-restore. R2 does not say how a live store
  is cloned with its daemon running. {#p22-3-bound-and-vacuous-restore}
- **D-Q1 and the `denotes` fold.** L69 M2 drops the hand-bumped cache constant; bug-216 R9 has
  since added exactly one, `_ADJ_SHAPE = "denotes-fold-2"` (`pagerank.py:156`). Say it is
  removed. `build_adjacency` drops any edge touching an operational id (`:286-288`), so a typed
  edge into a concept that `denotes` a `workflow/` doc disappears; the spec is silent. Add a
  row, an AC and a mutation. {#dq1-denotes-fold-vs-exclusion}
- **D-Q1's W and N stores have no ignore spec.** They are `git archive` unpacks, and
  `.refmatrix/.refmatrix_ignore` is untracked, so W ingests templates production never does.
  Commit the spec W uses as a frozen input. 28.2's clone stores have the same gap.
  {#dq1-wn-ignore-spec-unspecified}
- **bug-203 belongs to 22.6.** `rmx sync -i` sends `purge_path` to the read-only replica; 22.6
  R4 rewrites that command and AC-5c drives it. {#s226-bug203-unowned}

### NOTE list, T6 {#t6-notes}

- bug-218 is still present as specced (`reinforcement.py:129-133`, `:170-175`). Its R1 and R4
  change which rows the `denotes` fold credits; G30 should run on a fixed sha first. Its
  bug-185 references must follow bug-185's revision. {#bug218-still-present}
- L2, L6 and L22 are folded in t56. 22.1 after 22.2 is by design (Wave 2). 22.2 R6 re-classifies
  `moved` and `stale-line` with no classifier until 22.1; AC-1 needs a stated fixture classifier.
  {#p22-order-consistent}
- ADR-0003's repoint is consistent with master, which leaves D-Q1 AC-11 satisfied at HEAD and
  not RED-able; move it to the T56 merge checklist. {#adr0003-repoint-consistent}
- bug-227's "live stores … not audited" has no owner. 22.1a AC-8b's `would_resurrect_unclaimed`
  is the only instrument that would show a past collision; print it for every fleet store.
  {#bug227-live-audit-unowned}

## Measurement findings: plan-28, the fold evaluation, 23.4 {#measurement}

### BLOCKER: paired runs would write to the live global store {#p28-paired-runs-write-live-global-events}

- **Spec:** plan-28 `#acceptance` (t3c `:245`): "No experiment agent writes to a live store".
  28.2 `#r4` (`:149`): "no live store is opened".
- **Master:** `telemetry.emit_recall_events` sends every `scope == "global"` event to the global
  root's `recall-events.jsonl` (`telemetry.py:1400-1404`), and the generated recall hooks run
  `--scope both` (`hooks.py:397`, `:453`, `:483`). A-cell runs and B's SessionStart would append
  rows to `~/.refmatrix`. The writer's routing is verified; each hook call end to end is not.
- **Second effect:** 28.3 `#r7` reads `used` events from the clone store's telemetry, so
  global-item events are missing from two outcomes.
- **Fix:** while a paired run is active, global-scope events go to the clone root's file, carried
  as an argument and counted. 28.1 gains an AC that the live global file gains no row whose
  `root` is under the clone; 28.5 AC-4 extends to `recall-events.jsonl` of every live store.
  28.2 `#r0` (a) also writes a probe memory to the real global store; use an existing row.

### SHOULD-FIX list, measurement {#measurement-should-fix}

- **23.4's op mapping predates 0.83.0.** `#r3` maps each event to a write shape; cliquet's log
  now holds `rel_evidence_clear` and `pending_refs_clear` events, and the spec has no rule for an
  unmapped op. An op table changes procedure text, which by 23.4's own AC-1 needs a new user
  decision and a new pin (d9ba `6fa243d` goes stale). 23.4 has not run. See [[#d4]].
  {#t23-4-replay-op-mapping-predates-0830}
- **Clone-store fidelity.** 28.2 `#r2` builds the store "by the deployed `rmx` ingest under the
  clone" with no ignore spec and no wait for vectors; hook recall is `hub_only`, so an early run
  gets a symbolic-only pack (an inference). Copy the source's ignore spec, sha recorded, and
  wait for zero un-embedded rows. {#p28-clone-store-fidelity}
- **The deploy-pause rule is a stale file list.** 28.5 `#r3` pauses for deploys touching five
  named files. Missing: `cli.py` (hosts `scan_prompt_cmd`, `_memory_recall_impl`, `focus_hook`),
  `recall.py`, `verbs.py`, `pagerank.py`; 29.5 then moves `cli.py`. State the rule by import
  closure; no deploy lands while a run is in flight; `deploy_straddled` runs are excluded and
  counted; n is pooled, with sha as a sensitivity split.
  {#p28-deploy-pause-list-is-a-stale-file-list}
- **A killed runner leaves a clone daemon behind** (bug-229's shape). Add a pre-run sweep from
  the runner's own ledger, sharing 29.4's helper. {#p28-orphan-clone-daemon-sweep}
- **The fold evaluation's precondition** must name the forced reingest's completion and recount
  ([[#bug185-red-waits-on-bug241]]). Its e2 pins "bug-216's deploy sha" for code but clones the
  live catalog at run time; after a schema-changing deploy the old code opens a newer catalog.
  Pin "the deployed sha at copy time". {#denotes-eval-precondition-names-the-reingest}
- **Residual live-leg text:** plan-28 `#tasks` row 28.1 ("`session_arm` fields"), `#p-12`
  ("a user-gated commit that sets the active record's `end`"), 28.1 `#r5`'s `push_on` signature,
  the exploration's `#open`. {#p28-residual-text}

### NOTE list, measurement {#measurement-notes}

- `arms.py` and `RMX_HANDHOLD_*` do not exist in master; they are 10.2's and unbuilt, as plan-28
  says. 28.1 AC-9 keeps the hook block byte-identical, so it needs no install window.
  {#p28-hook-surfaces-match-master}
- Bands, δ and minimum n are fixed before data, each tied to an action. {#p28-bands-preregistered}
- `task-compaction-as-handoff` and D-Q1 both change what a paired run's treatment reads. Land
  them before 28.4's calibration freeze, or after the series ends. {#p28-land-before-freeze}
- Lane items with no spec found: the m1 r2-lite confirm (G32), which blocks 28.4. Specs that
  exist but are unmerged: bug-182 per-leg timing (25.1b, `spec-wave-t3a`), the 10.5 probe and
  L17's Table A (`spec-wave-t3b`), L34's scoring (25.2, `spec-wave-t3a`, not read).
  {#lane-spec-status}

## Plan-29 interactions {#plan-29}

### Line-number citations per spec {#citations}

Counted by one rule: explicit `cli.py:N`, `store.py:N`, `daemon.py:N`. "Bare" is `:N`
continuations after a named file (fork counts). All are dead on master already: `cli.py` moved
about 1,200 lines and `store.py` gained 774 since `1cf3b9f`. Specs not listed cite none.

| Spec | cli | store | daemon | Bare | Where the cites sit |
|---|---|---|---|---|---|
| 23.1 | 2 | 33 | 28 | 72 | mostly sha-stamped `#facts`; requirements cite symbols |
| 22.6 | 9 | 18 | 8 | 26 | 27 in `#requirements` need symbol cites |
| 23.5 | 0 | 7 | 4 | 94 | live requirements; all dead |
| 18.3 | 5 | 4 | 8 | 25 | requirements |
| 16.6 | 1 | 8 | 6 | 5 | requirements |
| 23.3 | 5 | 3 | 9 | 34 | requirements |
| 17.1 | 5 | 7 | 3 | 4 | requirements |
| 18.2 | 0 | 1 | 10 | 15 | requirements and census |
| 17.4 | 1 | 5 | 4 | 2 | requirements |
| 16.5 | 8 | 1 | 0 | 0 | the grep block |
| 22.1a | 2 | 4 | 2 | 0 | requirements |
| 18.1 | 2 | 1 | 4 | 9 | done |
| 17.3 | 1 | 0 | 5 | 4 | procedure |
| 22.2 | 1 | 4 | 1 | 0 | requirements |
| bug-218 | 0 | 5 | 0 | 1 | requirements |
| plan-17 | 4 | 1 | 2 | 0 | overview |
| 16.1 | 2 | 0 | 2 | 0 | requirements |
| bug-185 | 0 | 1 | 2 | 1 | requirements |
| 22.1, 22.4, 23.4, D-Q1, 17.2 | ≤ 2 each | ≤ 2 each | ≤ 1 each | — | — |
| plan-28, 28.1-28.5, fold evaluation, 16.2-16.4, 22.3, 22.5, 23.0, 23.2 | 0 | 0 | 0 | — | — |

### SHOULD-FIX: AST pins break under 29.5, and L104 does not cover them {#ast-pins-break-under-29-5}

- 18.2 R11/R13/AC-17 and 18.3 AC-14 walk "EVERY `src/refmatrix/*.py`" (non-recursive) with
  exemptions by qualified name (`cli.compact`, `store.Store.rebuild_entities_indexes`).
- 22.1a AC-8c, 22.2's `ingest_ok` and `restored_from` pins, 22.6 AC-6f, 16.6 AC-9c/9d/AC-12 and
  bug-218 AC-2/AC-4b key on the file `store.py` or `cli.py`.
- After 29.5 those are packages. A non-recursive glob stops seeing them and passes vacuously.
- **Fix:** every pin says "every module under `src/refmatrix`, recursive" (as bug-212's `rglob`)
  and locates by symbol. L104's re-point gains "qualified names and AST scopes".

### SHOULD-FIX: 29.5's concern list has no home for evidence, links and replay {#plan29-split-missing-replay-module}

- Plan-29 `#t5` splits `store.py` into "fragments/bitmaps, vectors, catalog and slots, memory".
- `rebuild_index_from_log`, `dump_catalog_to_log`, the evidence and link primitives and
  `pending_refs` fit none of them, and bug-185, 16.6, 17.4, 22.2, 22.6 and 23.5 R5 all land
  there.
- **Fix:** 29.5's spec names an evidence/links module and a replay (facts.log) module. New CLI
  surface arriving later should have its group reserved: `vectors`, `catalog`, `learn`, the grep
  block (so 16.5's rewrite stays in one file), `removal`.

### SHOULD-FIX: 29.4's wall-clock census meets about 43 new assertions {#wall-clock-acs-vs-29-4}

| Spec | Wall-clock clauses |
|---|---|
| 23.5 | 14 (AC-1, 1b, 2, 4, 5, 6, 7, 9) |
| 18.3 | 7 ACs (50 ms; `hold_s < 1.5`; `phase_a_s < 1.0`; `rewrite_s` ±25 %) |
| 16.1-16.5 | 7 (incl. 16.2 AC-9's p50 ≤ 15 ms / p95 ≤ 40 ms gate) |
| 23.1 | 4 (AC-16b, AC-19, AC-21 steps 2 and 3) |
| 18.2 | 4 ACs |
| 17.1, 17.4 | 4 |
| 23.2 | 3 (deadlines: fail-not-hang) |

- 23.1 AC-21 step 2 (spawn-to-exit under 5.0 s with a dial of up to 4.0 s) and 18.3 AC-7 (±25 %,
  where 18.3's own I9 measured loaded at twice idle) are bug-228/231 by construction.
- 23.1 AC-21 step 1 holds a lock 70 s, and steps 4 and 5a repeat it: minutes of sleep against
  29.4's 20-minute target.
- **Fix, in 29.4's spec before any of these REDs:** two classes. Where the bound is the feature
  (a deadline, R2's `RMX_CLI_WRITER_WAIT_S`), the test is allow-listed by name with env-shrunk
  bounds. Everything else is recast as an ordering outcome ("answers while the test thread still
  holds the lock"; "the hook exits before the competitor releases").

### SHOULD-FIX: one daemon reaper, keyed on the spawn {#one-reaper-keyed-on-spawn}

- Plan-29 `#t4` does not say what the reaper keys on; bug-229's row proposes "socket path under
  the sandbox root". bug-229's daemon lived under `mkdtemp(prefix="r1-", dir="/tmp")`. 96 test
  lines call `mkdtemp(… dir="/tmp")`; a root-keyed reaper misses them.
- 23.2 `#r4`'s `recorded_daemon`, 18.3's SIGKILLed subprocess daemons, 17.2's ops blocked "on an
  event the test never sets", 16.1's detached learners, D-Q1's and 22.5's throwaway daemons and
  28.2's clone daemons each need the same teardown.
- **Fix:** the reaper keys on the spawn (`spawn_daemon_subprocess`, `Daemon` construction), 23.2's
  fixture registers with it, and teardown asserts stop and pid exit. Plan-29 never mentions
  plan-23; 29.4's spec should cite 23.0 and 23.2.

### SHOULD-FIX: 29.3 should extract one census scanner and adopt the helpers these specs already define {#plan29-converge-candidates}

- **One scanner.** bug-212's (`tests/test_bug212_r4_red.py:329-404`: alias handling, synthetic
  self-test, "allowlist names no dead site"). Families waiting for it: removal sites (22.6),
  CHECKPOINT and catalog holds (18.2, 18.3), out-of-daemon Lance reads (17.1), merge table
  coverage (bug-124; 16.6, 23.1), the corpus predicate (16.1 AC-5d), `_cli_read` (23.5 R7), the
  one writer installer (23.1). Without it these become six hand-rolled AST walkers.
- **Helpers:** the partition default at 20 daemon sites; `run_git` for `_op_sync_since`, which
  runs `changed_since` inside `_store_lock` (`daemon.py:4035-4039`), and for 16.4.
- **Except census hits created or touched here:** `ingest.py:1407-1421`, `Scheduler._loop`,
  `store.py:4381-4384` (bug-123), `Store.close()` and `Store.transaction` (23.1 R1.6, R7).
- **29.2:** the `_DaemonWriter`/`Store` Protocol must include what these specs add
  (`batch_transaction`, `add_evidence_if_absent`, `add_memory(updated_at=)`, bug-185's bulk
  methods).

### Merge with, rebase onto, or independent {#plan29-verdicts}

| Task | Verdict |
|---|---|
| 23.0 tier ACs 7-8, bug-230 amendment | **merge into 29.4** |
| 23.2 | rebase onto 29.4 (shares the reaper; allow-list its deadlines) |
| bug-185, 23.1, 23.3, 16.6, 17.1, 17.4, 22.1a, 22.2, 22.6, bug-218, D-Q1, 16.1, 16.5, 28.1 | rebase onto 29.5; none may be in flight during its window |
| 23.5, 18.2, 18.3 | rebase onto 29.4; mostly `daemon.py` and new modules, low 29.5 exposure |
| 22.6's removal census, 16.1's predicate, 23.5's `_cli_read` | built as 29.3 families, not duplicated |
| 23.4, fold evaluation (G30), 28.2-28.4, 16.2-16.4, 22.5 | independent of 29.5; 23.4 and G30 build no `src/` and can run alongside plan-29 |

## Registry {#registry}

**Open rows in these tracks with no owning task:**

| Row | What | Proposed owner |
|---|---|---|
| bug-241 | bug-216 AC-6 fails live; RED held by the user | first; see [[#d1]] |
| bug-240 | `rmx ingest <file>` ingests nothing, exit 0 | with bug-241 (same store, same day) or 29.1 |
| bug-203 | `sync -i` sends `purge_path` to the replica | 22.6 R4 |
| bug-207 | in-process `rmx sync` never closes its store | 23.3 `#r3` (rewrites those callers) |
| bug-210 item 3 | watcher re-queue of refused paths | 23.3 (touches its flush site) |
| bug-226 | daemon-down reingest probe attach conflict | 23.5, as a second AC beside the bug-136 rider |
| bug-119 | non-JSON `facts.log` line dropped uncounted | 16.6 (rewrites the function) and 23.5 R5 |
| bug-124 | replica merge drops derived tables | 16.6 R1c, as the merge-table census |
| bug-123 | swallowed CHECKPOINT error | owned on paper only; 18.3 R8 or 29.3 |
| bug-232 | one refusal text, three callers | 17.4's promote guard needs it; its compact leg is deleted by 18.3 R10 |
| bug-194 | truncated daemon reply under load | 23.5 `_raise_for_answer` |
| bug-161 | hub wedge | before 17.2 adds a hub thread doing 600 s daemon calls |
| bug-097 | embed timeout | before 17.4 step 7's re-embed at scale |
| bug-089, bug-096, bug-153, bug-188, bug-201 | search-dense `KeyError`; reingest partial; refine partition; env knob; sync suffix | 29.1 triage |
| bug-100, bug-165, bug-166 | measurement lane; fix column empty | 29.1 triage (165/166 only if L43 fires) |

**Rows whose text is wrong:** bug-219's Fix column ("purge evidence with the entity … on every
purge path") contradicts L6 and 22.6 R5; bug-167 and bug-174 still name 25.4/25.5; bug-121 names
22.2 as its fix while the queue backlog lists it outside the goal; bug-088 and bug-101 do not
mention 23.0's shipped refuse stage. **No row exists** for `_bulk_purge_ids` leaving
`pending_refs` behind ([[#p22-restore-omits-pending-refs]]). **bug-228:** 23.5 R1 moves
`_op_memory_recall` off the store lock, the path its test exercises; re-measure after 23.5 before
closing it on a reworded assertion. {#registry-notes}

## Readiness {#readiness}

"Rev" = needs the revision named in the findings. RED-first holds for every task unless stated:
the ACs are falsifiable and mutation-backed.

| Task | State | Blocked on | User gates |
|---|---|---|---|
| bug-185 | rev (5 items) | bug-241; plan-29 | AC-4 below 5× STOP; R9 STOP; R9 index build (unmarked) |
| 23.0 | built; AC-7/8 open | — (fold into 29.4) | tier setup (admin user; Tart) |
| 23.2 | ready after 29.4 | 29.4 | none |
| 23.1 | rev (1 BLOCKER; split) | 23.2; plan-29; bug-185 | none in spec; deploy adds 3 tables per slot: announce |
| 23.3 | rev | 23.1, 23.2, bug-185 | R9 STOP band |
| 23.5 R1-R8 | rev | 23.1b | R8's live-snapshot copy is a lead step |
| 23.5 R9 | — | 26.7 → 26.6 R3 residual (L1) | — |
| 23.4 | rev (op table) | new pin | **the re-pin** ([[#d4]]) |
| 16.6 slice | rev (1 BLOCKER) | 23.1, 23.2, bug-185, 23.4 | none |
| 17.1 | rev (untouched since 2026-10-15) | 23.1, 23.2, 23.4's verdict | none |
| 17.2 | rev (small) | 17.1; 26.6 R3 residual | arming follows the gated hand run |
| 17.4 | rev (1 BLOCKER) | 16.6, 17.2 | R6 restore is store surgery, announced |
| 17.3 | rev (roster) | 17.1, 17.2, 17.4 deployed | orphan release; `tmutil`; backup deletion |
| 18.1 | done | re-take before 18.2 R10 | re-take announced |
| 18.2 | rev (1 BLOCKER) | 17.2, 23.2, 23.5, 23.1b | R10 hand runs (unmarked) |
| 18.3 | rev (2 BLOCKERs) | 18.2, 23.1b, 23.5, 17.2 | per store before `--confirm` and the arm; RSS over 2 GiB; backup deletion; [[#d2]] |
| 16.1 | rev (2 BLOCKERs) | 16.6 slice; 29.4, 29.5 | none |
| 16.2 | minor rev | 16.1 | `RMXGREP_MODE` delete; install window |
| 16.3 | rev | 16.1 | fleet install window; the learn flip |
| 16.5 | rev | 16.1, 16.2, 29.5 | cliquedb bus message |
| 16.4 | minor rev | the flip; 16.5 | 14-day hand-back; reopen question |
| 25.4, 25.5 | closed in t56 | plan-25 table, registry repoint | — |
| 22.1a | rev | 16.6 slice; bug-241 recount | [[#d3]] |
| 22.2 | rev (2 BLOCKERs) | 22.1a, 16.6, 23.1, 23.2, 17.1 | none (sandbox only) |
| 22.6 | rev (1 BLOCKER) | 22.2, 22.1a, 16.6 | first live vacuum (unmarked) |
| 22.5 | light rev | 22.1a, 22.2, 23.1 | no-owner ruling (d9b); live move |
| 22.3 | light rev; AC-4 not falsifiable | 22.5, 22.2, 22.1a | backup and count confirmation |
| 22.1 | text ready | 16.1, 22.2, 16.6 | none |
| 22.4 | deferred (L22) | plan-20 | — |
| bug-218 | R0 ready after plan-29; R1-R7 rev | bug-185 | R4 per-store `--apply` |
| D-Q1 (G22) | rev (1 BLOCKER) | a queue slot | R6 per-store re-derive |
| 28.1 | rev (1 BLOCKER) | 10.2; 29.5 | none |
| 28.2, 28.3, 28.5 | rev | 28.1 | pause, stop, archive deletion, spot check, G18 |
| 28.4 | blocked | 28.1-28.3; G32; 21.5 phase M | — |
| Fold evaluation (G30) | rev | bug-241 and the recount | cliquedb copy; archive announcement |

## Recommended order {#recommended-order}

1. **Now, beside 29.1 (docs only):** feed this review into plan-29's task specs: the wall-clock
   allow-list rule, the spawn-keyed reaper, the two missing store modules, the census scanner.
   *Those four choices decide whether 43 assertions and seven AST pins are written once or twice.*
2. **bug-241 diagnosis, as soon as the user releases it.** *Three tracks read the state it
   leaves wrong, and the suspect code is not in the modules 29.5 moves.*
3. **23.4 (after its re-pin) and the fold evaluation (after bug-241), alongside plan-29.** *They
   build no `src/`; 23.4's verdict is what reopens 17.1, and the fold's baseline should be taken
   before bug-218 and D-Q1 move it.*
4. **After 29.5: one freshness revision pass over every T4-T6 spec, then a ch-bsd confirm-lite
   per branch.** *One re-stamp on the final modules instead of one now and one later.*
5. **T4 core:** bug-185 → 23.2 → 23.1b → 23.1a → 23.1c → 23.3 ∥ 23.5. *23.1b first because 23.5
   R4, 18.2 and 18.3 need only the lock owner; 23.1c last because it needs the queue and closes
   bug-177.*
6. **D-Q1 (G22), then `task-compaction-as-handoff`, before 28.4 freezes.** *Both change what a
   paired run's treatment reads; D-Q1 is blocked by nothing in plan-22.*
7. **Plan-28:** 28.1 (after 10.2) → 28.2 → 28.3 → 28.4 → the series. *No deploy lands during a
   run, so the series fits between releases, not across them.*
8. **T4 maintenance:** 16.6 slice (with the reduced R1c) → 17.1 → 17.2 → 17.4 → 17.3. *L2 and
   L40's order holds; 16.6's merge census must exist before more id-keyed tables arrive.*
9. **T6:** bug-218 R1-R7; 22.1a → 22.2 → 22.5 ∥ 22.6 → 22.3. *22.6's removal census lands with
   22.6, on the 29.3 scanner.*
10. **T5:** 16.1 → 16.2 ∥ 16.3 → 16.5 → 16.4; then 22.1. *Unchanged; 16.1's queue key is settled
    with 23.1a in step 5.*
11. **T4 tail:** 18.1 re-take → 18.2 → 18.3. *Last because it depends on 17.2, 23.5 and 23.1b,
    and its census edits are the largest.*

{#recommended-order-list}

## Decisions for the user {#decisions-for-the-user}

**Decided (The user, 2026-11-14: "go with your recommendations on all of them".):** store D1 released (bug-241 RED ran; 0.83.1 in progress). store D2 (a) refuse real reclaim on a git-tracked catalog by rule (`refused:catalog_tracked`), rehearsal allowed. store D3 (b) walk only registered store roots; the rest `unverifiable (not-walked)`, kept — this changes the 2026-10-07 global-store recover/forget decision. store D4 approve 23.4's op table ("mapped shape, or skipped and counted in both reference and measured runs"); confirmed ranges stand. store D5 upgrade `.venv-eval` duckdb to 1.5.3 after the in-flight 0.83.1 runs, before plan-29's baselines. {#decided}

Settled as the user would, not asked: 23.1's three-way split; reinstating 16.6 R1c; retiring the
idle `rmx schedule` in 17.2; no fleet tree walks in bug-218, D-Q1, 17.3 and 18.2.
{#decisions-settled}

- **plan-review-fable-store D1: release the bug-241 RED, and when.** It is held by your stop. It gates
  bug-185's golden, the fold evaluation and plan-22's recounts. Recommended: release it now, to
  run beside plan-29's 29.1 and 29.4, since its suspect code is in `ingest.py`, which 29.5 does
  not move. The alternative, after plan-29, delays step 3 and 5 of the order above by the length
  of plan-29. {#d1}
- **plan-review-fable-store D2: does a real catalog reclaim run on a store whose catalog git tracks?**
  Today `rmx compact` refuses there. 18.3 R10 routes compact through the daemon, which is the
  accepted writer, so it would swap the committed file. (a) Refuse real runs by rule
  (`refused:catalog_tracked`), rehearsal allowed: keeps 0.83.0's behaviour. (b) Allow it; the
  per-store announcement names the tracked catalog. Recommended: (a). The catch: cliquet `main`,
  atldb and prep_prolific can never reclaim until bug-214's untracking reaches every branch. {#d2}
- **plan-review-fable-store D3: 22.1a's candidate walk.** (a) Keep the three-tree walk (973,157 files),
  lead-run and announced. (b) Walk only registered store roots and classify the rest
  `unverifiable (not-walked)`, kept. Recommended: (b), which matches your 2026-11-14 rule. The
  catch: it changes your 2026-10-07 decision for the global store (recover 476, forget 611),
  because rows the walk would have verified or condemned are now kept unverified. {#d3}
- **plan-review-fable-store D4: 23.4's new pin.** Its procedure needs an op table for the four replay
  ops 0.83.0 added, and 23.4's own AC-1 says a procedure change needs your decision and a new
  pin. Recommended: approve the table "mapped shape, or skipped and counted in both reference and
  measured runs"; the ranges you confirmed stand. {#d4}
- **plan-review-fable-store D5: raise the dev venv to duckdb 1.5.3.** `.venv-eval` has 1.5.2, below
  `pyproject.toml`'s floor and below the deploy venv. It is an environment gap, and 18.3's
  mutation kills depend on 1.5.3 behaviour. Recommended: upgrade before plan-29's equal-by-E-line
  baselines are taken, so they are not re-taken after. {#d5}
