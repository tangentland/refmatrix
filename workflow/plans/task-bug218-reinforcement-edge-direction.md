---
gmd: "0.1"
id: task-bug218-reinforcement-edge-direction
title: "Task bug-218: one storage orientation for reinforces / contradicts edges — R0 confirms or refutes the reversed read, then both writers and the reader agree (with bug-223)"
tags: [task, bug-218, bug-223, reinforcement, linkages, direction, memory, t6]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
---

# Task bug-218: reinforcement reads its edges in one orientation {#root}

> Status: Drafting (2026-11-13, spec wave G20; revision 1 the same day folds the lead's rulings:
> O-1 = A, O-2 = (a), bug-223 hosted as [[#r7]], [[#rev-1]]; revision 2 answers ch-bsd
> `bsd-spec-t56-r1-fecda59` S1-S4, M1-M3 with the lead's rulings, [[#rev-2]]).
> Track: T6 (graph integrity), queue item 9, first ([[plan-review-2026-11-13#queue]]; L8 puts
> bug-218 on T6).
> Depends on: bug-216 merged and live. Its R6 changes which entity a bare `rel:` target binds
> (doc / memory first), its R7 `denotes` links are what [[#r2b]] reads, and its R8 recount is the
> census tool this task reuses. bug-185 merged (its R10 replace is what [[#r1]]'s evidence row
> protects a `memory_link` edge against; queue item 5, ahead of this task's item 9).
> The bug row is `suspected`: [[#r0]] confirms or refutes it before any fix is written.

rel: derives-from -> [[bug_registry]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r6]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r8]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r7-denotes]]
rel: depends-on -> [[task-bug185-bulk-gmd-ingest]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]
rel: related-to -> [[task-bug216-rule-docs-in-graph#out-of-scope]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: depends-on -> [[feedback_red_test_must_fail_at_head]]

## Why {#why}

The bug-218 row (found 2026-11-13 while diagnosing bug-216) says `reinforcement.py` reads
`reinforces` / `contradicts` edges reversed against "the only writer (the GMD ingester)". Re-read
at `1cf3b9f`, the defect is real in shape but the row's premise is wrong: there are TWO writers,
and they store the same statement in opposite orientations. {#why-lead}

`Store.link(linkage, concept_id, entity_id, …)` (`store.py:4810`) writes
`entity_links(entity_id, linkage_id, concept_id)`. {#why-writers}

| writer | call | statement "memory m reinforces target c" stored as |
|---|---|---|
| GMD ingester, a `rel: reinforces -> [[c]]` line in m | `ingest_gmd.py:1766` `store.link(verb, src_eid, target_eid)`, evidence at `:1769` `add_evidence(verb, src_eid, target_eid, …)` | `concept_id = m`, `entity_id = c` (bug-216's "storage direction", the same for every `rel:` verb) |
| `rmx memory link m reinforces c` (CLI local path) | `cli.py` `memory_link`: `s.link(linkage, cid, m["id"], weight=…)` | `concept_id = c`, `entity_id = m` |
| daemon op `memory_link` (the CLI's daemon route; MCP `rmx_memory` action `link` through `verbs._MEMORY_OPS`) | `daemon.py` `_op_memory_link`: `d._st().link(linkage, cid, m["id"], weight=…)` | `concept_id = c`, `entity_id = m` |

The reader, `reinforcement.reinforcement_scores` and `reinforcement_components`, selects
`WHERE el.concept_id IN (<targets>)` and decays on `entities.created_at` of `el.entity_id`. That
is the `memory_link` orientation. For a GMD-written row the signal lands on the reinforcing
memory's id and decays by the target's age, which is the row's description. {#why-reader}

**One GMD statement writes two rows (the root-mirror).** Every memory file carries
`# Title {#root}` (MEMORY-RULES). A `rel:` line under it links from the `m#root` node, a
`kind='concept'` entity (`ingest_gmd.py:1766`), and the ingester then mirrors the same edge onto the
doc-level entity, here the memory m (`ingest_gmd.py:1784-1797`, evidence detail
`rel: … (root-mirror)`). So a root-level `rel: reinforces -> [[c]]` in m stores `(m#root → c)` with
a concept source AND `(m → c)` with a memory source. {#why-root-mirror}

Every fixture agrees with the `memory_link` orientation, so no test can see the GMD rows:
`tests/test_reinforcement.py:33,102,121,167` and both benches, `eval/reinforcement_bench.py:143,149`
and `eval/reinforcement_csn_bench.py:117,135`, seed with a raw `s.link(linkage, cid, mid)`. The
benchmarks measure an orientation the GMD path never writes ([[feedback_measure_the_path_users_run]]).
{#why-fixtures}

Live exposure is small today: `RMX_REINFORCE_ALPHA` defaults to 0.0, `apply_to_concept_scores`
has no caller, and the `RMX_BOOST_REINFORCE` term boost in `Store.content_rank` (`store.py:5610`)
is unset. What does read the signal today is `rmx memory score` (CLI and `_op_memory_score`), and
the two direction-sensitive graph readers of the same rows: `pagerank.py` (which keeps
`contradicts` connectivity) and `brief.contradicted` (which de-duplicates pairs, so it does not
depend on orientation). {#why-exposure}

## Decision O-1: the canonical orientation (lead, 2026-11-13: A) {#o-1}

**Decided: A.** The GMD orientation is canonical; `memory_link` changes; the reader swaps its
joins. The options as they were put, for the record:

1. **(A, recommended) The GMD orientation is canonical** (`concept_id` = source, `entity_id` =
   target, as for every `rel:` verb). `memory_link` (CLI local path and daemon op) changes to
   `link(linkage, m_id, cid)`; the reader keys the signal on `entity_id` and decays on the
   `concept_id` side's `created_at`. Why: it is the graph-wide convention that bug-216's R6-R8,
   `denotes`, `check-rel-landing.py`, PageRank and every other `rel:` reader already assume; the
   rows to re-orient are only `memory_link`-written ones, which [[#r0b]] expects to be few.
2. **(B) The `memory_link` orientation is canonical for these two verbs.** The GMD ingester
   special-cases `reinforces` / `contradicts` and writes them reversed; every existing GMD row of
   these verbs is re-oriented. Cost: a per-verb exception that every `rel:` reader (bug-216's
   recount and `denotes`, PageRank, `brief`) must learn, and the larger repair.
3. **(C) The reader infers the source by kind** (the `kind='memory'` side is the source).
   Rejected: a memory reinforcing another memory, the common GMD case, has no answer.

B and C are not built. {#o-1-impact}

## Requirements {#requirements}

1. **R0 Confirm or refute, at HEAD, before any fix.** {#r0}
   - **R0a RED on the real writers.** In task 23.0's sandbox (a throwaway store under a short
     `mkdtemp()` root), two statements of "m reinforces c": one ingested from a GMD memory file
     carrying `rel: reinforces -> [[c]]` (through `ingest_gmd_paths`, the bridge's path), one
     written by the `memory_link` daemon op. Read `reinforcement_scores` and
     `reinforcement_components` for c and for m. At HEAD the expected result is: the
     `memory_link` statement scores on c, the GMD statement scores 0 on c and non-zero on m. If
     the GMD statement scores on c at HEAD, the bug is REFUTED: the test is kept as a guard, the
     row is closed `not a bug` with the run log, and R1-R5 are not built. The RED run is logged
     ([[feedback_red_test_must_fail_at_head]]). {#r0a}
   - **R0b Census, read-only.** On copies of each store's `catalog.read.duckdb` AND its
     `facts.log` (the ONE census procedure, [[task-16.6-learned-row-validation#r7]]: copy into a
     short `/tmp` dir, `duckdb.connect(read_only=True)`, the log read as a file; no `Store()`, no
     daemon, no socket; r2 M5), count `reinforces` and `contradicts` rows in `entity_links` by
     writer class:
     - **GMD direct**: a `linkage_evidence` row at the same `(entity_id, linkage_id, concept_id)`
       whose `detail` starts `rel:` and does not end `(root-mirror)`;
     - **GMD root-mirror**: the same with `(root-mirror)`; and its twin, the direct row from
       `<doc>#root` to the same target, is counted as `root_twin` (one statement, two rows), never
       as a drop;
     - **`memory_link` after R1**: an evidence row whose `detail` starts `memory link:` ([[#r1]]);
     - **no evidence**: the rest, which holds every pre-R1 `memory_link` row, split by end-kind
       shape (entity side `memory` with concept side `concept` is R4's candidate shape).
     For each class, also count the kind of each end (memory / doc / concept / other), rows with
     a dead end, and rows whose source is not `kind='memory'` and is not a `root_twin`, which is
     R3's real drop. **Stores:** the global store `~/.refmatrix/` (the bridge lands memories there,
     ADR-0005) and every fleet repo found by the installed hook marker (`grep -l "refmatrix:
     refresh" <repo>/.git/hooks/post-commit` over `~/github`, `~/claude_tools` and `~/enduris`,
     skipping `_frameworks_and_libraries`; [[project_fleet_hooks_found_by_marker_not_hub]], the
     bug-209 rule) that holds a `.refmatrix/` catalog. The list is printed in the measurement file.
     Results go to `workflow/measurements/bug218-direction-census-<date>.md`, counts only, one
     row per store, with the copy's timestamp. {#r0b}
2. **R1 One orientation, both writers, one `memory_link` body (O-1 = A).** "m reinforces /
   contradicts c" is stored as `concept_id = m` (the source), `entity_id = c` (the target), the
   orientation the GMD ingester writes for every `rel:` verb. The ingester is unchanged.
   - **One body (M1).** `Store.memory_link(src, linkage, concept, weight=None) -> dict` is the ONE
     store-level body. It resolves the memory, `add_concept(concept)` as today, writes
     `link(linkage, m_id, cid, weight=weight)` and the evidence row below, calls bug-216's
     ingest-time `denotes` helper for the concept's name (`Store.link_denotes(names=[concept])`
     on the bug-216 branch, the call GMD ingest makes "on ingest of X"; idempotent), and returns
     `{src_id, concept_id}`. A hand link made AFTER its same-named doc or memory exists therefore
     gets its `denotes` at once, not at the next re-ingest or derive (r2 S2). The CLI's local path and `_op_memory_link` (which the MCP
     `rmx_memory` `link` action reaches) both call it, and neither keeps a body of its own.
     Fixtures and benches call it too ([[#r5]]).
   - **An evidence row tags the writer (S3).** It writes `add_evidence(linkage, m_id, cid,
     detail="memory link: <linkage> -> <concept>")` (no file, no line), logged as an `evidence`
     event like every evidence write. After R1 a `memory_link` edge and a GMD line of the same
     statement share one `entity_links` key, and bug-185 R10 unlinks a key a dropped `rel:` line
     no longer states "UNLESS a `linkage_evidence` row still supports it"
     (bug-185 R10, [[task-bug185-bulk-gmd-ingest]] as revised on `spec-wave-t4` at `db701e8`; cited
     without its anchor until that branch merges). This row is that
     support, so a user's `memory link` is never unlinked with a GMD line. It also gives R0b a
     positive writer class and plan-22's stale-edge census a discriminator. bug-185's R9 clear
     removes only the file's `rel:` evidence, so it never removes this row.
   - The orientation is written once, as a docstring paragraph in `reinforcement.py` that the
     writer and the reader cite. {#r1}
3. **R2 The reader reads that orientation.** `reinforcement_scores(store, ids)` returns the
   signal of each TARGET id: the sum over its `reinforces` / `contradicts` rows with
   `el.entity_id IN (<ids>)`, decayed on the SOURCE's `entities.created_at` (the
   `el.concept_id` side, joined `e.id = el.concept_id`), clamped to ±cap.
   `reinforcement_components(store, id)` lists the SOURCE entities (id, name, kind, age, decay,
   contribution). Both SQL joins swap. {#r2}
   - **R2b Targets resolve the bug-216 R6 way, plus `denotes` (S2).** {#r2b} After R1-R2 a GMD
     row lands on whatever bug-216 R6 bound: for a bare `[[x]]`, the doc, then the memory, then
     the concept; for an anchored `[[x#a]]`, the concept. A `memory_link` row always targets the
     concept `add_concept(x)`. Today's readers ask only for concept ids (`resolve_concept_ids`,
     `WHERE kind='concept'`, `store.py:3305-3333`; the boost passes query-term concept ids), so
     every GMD row on a doc or memory target would be unreachable. One function,
     `reinforcement.resolve_targets(store, name_or_ids) -> set[int]`, gives the target set:
     - for a NAME (`rmx memory score <name>`, CLI local path and `_op_memory_score`): a bare name
       resolves doc, memory, then concept (the concept only when no doc or memory has the name;
       the concept leg is today's `resolve_concept_ids(name, strict=False)`, so canonical
       variants still match: `FooBar` finds `foo_bar`, r2 M4);
       an anchored `x#a` resolves the concept; and to that entity it adds every concept that
       `denotes` it ([[task-bug216-rule-docs-in-graph#r7-denotes]]; stored like `rel:`, concept
       side = the concept, entity side = the doc or memory), which is where a same-named
       `memory_link` concept lands;
     - for concept IDS (the `RMX_BOOST_REINFORCE` term boost): each concept plus every entity it
       `denotes`; the boost's per-concept signal is the sum over that set.
     `memory score`'s signal is the sum over the set; `--explain` lists the components per
     target. No other resolver is written for this reader.
4. **R3 Only memories reinforce, and each statement counts once.** A row contributes only when
   its source is `kind='memory'`. That is the module docstring's definition ("Memories accumulate
   confidence on a concept") and the bug row's proposed fix, and it does two jobs, both stated so
   a later change cannot drop one silently:
   - **What it drops:** a doc that cites a target with `rel: reinforces` (task specs do), and any
     other non-memory source; R0b counts these as R3's drop.
   - **What it de-duplicates:** the root-mirror ([[#why-root-mirror]]). A root-level statement in
     m writes `(m#root → c)` (concept source) and `(m → c)` (memory source); only the memory row
     counts, so the statement counts once. Letting `kind='concept'` sources count would double
     every root-level statement. {#r3}
5. **R4 Existing pre-R1 `memory_link` rows are re-oriented by a daemon op (O-2 = (a); S4).** Built
   only if R0b finds candidates; with 0 on every store, R4 builds nothing and the summary says
   so. {#r4}
   - **The op.** `daemon._op_repair_reinforce_orientation(d, args)`, registered in `OPS`, shaped
     like `_op_repair_fragments` (the bug-105 repair): `dry_run` defaults to True, it runs under
     `d._store_lock`, writes its manifest under `<store>/backups/`, logs its counts through
     `d._log`, and requests a snapshot after a real change. The CLI entry is a flag on the
     existing command, `rmx repair-index --reinforce-orientation [--apply]`, which calls the op
     through the store's own daemon and refuses when no daemon answers; it never opens `Store()`
     ([[feedback_store_calls_via_daemon]]). Each store is repaired through its own daemon.
   - **Flag matrix (r2 M6).** `--reinforce-orientation` is exclusive with `--entities` and
     `--fragments` (usage error, exit 2). With it, a dry run is the default and `--apply` writes.
     `--dry-run` with `--reinforce-orientation` is accepted only alone (a no-op restatement of
     the default), and `--dry-run --apply` is a usage error. `--apply` without
     `--reinforce-orientation` is a usage error. The other modes keep their behaviour.
   - **Candidates.** A `reinforces` / `contradicts` row in the pre-R1 shape (entity side
     `kind='memory'`, concept side `kind='concept'`) with no `rel:` or `memory link:` evidence row
     at its key AND no `rel:` `evidence` append for its key in `facts.log` (a GMD row whose
     evidence was lost has the same end kinds when its source is an `x#root` concept and its target
     a memory). A row that matches the shape but has such an append is listed as `ambiguous`,
     never re-oriented. **Cross-check (r2 M5):** a concept side whose name contains `#` (a GMD
     node, never an `add_concept` name) is reported beside the verdict. A candidate with `#` in
     its concept name is listed as `ambiguous` too, so a GMD row whose append is missing (logging
     off, a compacted log) is never re-oriented. The hint never promotes a row to a candidate.
   - **Backup, a prior step.** Before any write, an `--apply` run materializes a fresh read
     snapshot (`d._snapshot_catalog(force=True)`), copies it and `facts.log` into
     `<store>/backups/bug218-reorient-<stamp>/`, prints both paths, and writes nothing if either
     copy fails.
   - **Manifest, then rows.** The manifest of every row it will change (both ends by name and
     kind, weight) is written before any change. Per row it then logs an `unlink` of the old
     orientation and a `link` of the new one through `edge_records.edge_fields` (with `c_kind`),
     writes the R1 `memory link:` evidence row, and prints the row. A rebuild from `facts.log`
     reproduces the result. The manifest-first, dry-run-by-default pattern is bug-195's
     ([[task-bug195-cut-hook-repair#r1]]); nothing else of that task's shape applies.
   - A re-orientation removes no knowledge (the same statement is written back), so it is not
     plan-22's knowledge removal; it is recorded as a derived repair in ADR-0004's decision log
     ([[refmatrix/adr-0004-unified-location-space-index#d-2026-11-13-t56]]).
   - **USER-GATED live step.** Each live store's `--apply` is announced first and runs only on the
     user's go; the dry run may run unattended.
6. **R5 Fixtures and benches seed through the writers.** `tests/test_reinforcement.py`, both
   `eval/reinforcement_*bench.py` scripts and the new tests create reinforcement edges only
   through the production writers (`Store.memory_link` from [[#r1]], or a GMD ingest),
   never a raw `Store.link` with a hand-chosen orientation, so a future orientation change cannot
   hide behind fixtures. {#r5}
7. **R6 Stated where a reader looks.** The `reinforcement.py` module docstring and `rmx memory
   link --help` state the stored orientation; the bug-218 row's "only writer" premise is corrected
   when the row is updated. {#r6}
8. **R7 The `RMX_BOOST_REINFORCE` read fails loudly (bug-223).** In `Store.content_rank`, the
   block that reads `reinforcement_scores` for the term boost is wrapped in `except Exception:
   pass` (`store.py:5624-5625` at `1cf3b9f`): with the boost switched on, any failure of the read
   this task rewrites drops the boost silently and the caller sees an unboosted ranking as if it
   were boosted. The `except … pass` is removed; a failure propagates, re-raised with context
   (`RMX_BOOST_REINFORCE: reinforcement signal read failed: <error>`). Raising, not
   count-and-continue, because the boost is an opt-in tuning channel: a run that silently ran
   without it reports a tuning result that never applied it, and with the variable unset the
   block never runs, so nothing else can reach the raise. The three sibling silent guards in the
   same method (the term-boost loop's two `except Exception: continue` and `_document_priors`'
   `except Exception: pass`, `store.py:5631-5658`) are read in the same pass and listed in the
   summary, each as "stated reason" or "silent failure"; a silent one is logged as its own bug
   row, not fixed here. {#r7}

## Acceptance criteria {#acceptance}

1. **AC-1 (R0a) RED at HEAD.** The R0a test fails at HEAD on the GMD statement (signal on c is 0;
   on m it is non-zero) and passes after R1-R2. Its run log is cited in the summary. If it passes
   at HEAD, see R0a's refute branch. {#ac-1}
2. **AC-2 (R1) Writer parity.** c is a concept-only name (no doc or memory is called c, so
   bug-216 R6 binds the concept). m is a canonical memory file (`# Title {#root}`) with one
   root-level `rel: reinforces -> [[c]]`. The GMD ingest writes exactly two `entity_links` rows,
   `(concept_id = m#root, entity_id = c)` and `(concept_id = m, entity_id = c)`, with `rel:` and
   `rel: … (root-mirror)` evidence. The `memory_link` daemon op and the CLI's local path each write
   exactly one row, `(concept_id = m, entity_id = c)`, with one `memory link:` evidence row; on a
   store holding both, the `(m, c)` key is ONE row. Mutations, each FAILS it: revert
   `Store.memory_link`'s orientation; give the CLI or the op a private body (a check asserts both
   call `Store.memory_link` and neither calls `.link(`). {#ac-2}
3. **AC-3 (R2) Signal and decay.** c is created now; m (created 30 days ago) reinforces c with
   weight 1.0; m2 (created now) contradicts c with weight 0.4; halflife 30 days, cap 5. `reinforcement_scores`
   gives c = 0.5 − 0.4 = 0.1 (±1e-6) and m = m2 = 0.0. Mutations, each FAILS it: key the signal
   on the source (c reads 0); decay on the target's `created_at` (c reads 0.6); drop the sign
   from the linkage name (c reads 0.9). **GMD-seeded variant:** a canonical memory file m3
   (created now) with a root-level `rel: reinforces -> [[c3]]` gives c3 = 1.0. Mutation "count
   `kind='concept'` sources" FAILS it (c3 reads 2.0: the `m3#root` twin counts too). {#ac-3}
4. **AC-4 (R2) Components name the sources.** `rmx memory score c --explain` (and the daemon op's
   `components`) lists m and m2, ordered by |contribution|, and never c. Mutation: select the
   target's name for the component row: FAILS. {#ac-4}
4b. **AC-4b (R2b) Doc and memory targets reach the readers.** Memory m5 is ingested FIRST. Then a
   memory m4 (canonical file, created now) is ingested with a root-level
   `rel: reinforces -> [[m5]]` (bug-216 R6 binds the memory m5), and `Store.memory_link` writes
   `m6 reinforces m5` (m6 created now), which targets the concept `m5`; no derive is run, so the
   concept's `denotes` to memory m5 comes from `memory_link` itself ([[#r1]]). `rmx memory score
   m5` (CLI local and the daemon op) reads 2.0 and `--explain` lists m4 and m6. **Variant
   spelling (r2 M4):** a concept `foo_bar` reinforced by m7 through `memory_link`, with no doc or
   memory named `foo_bar`: `rmx memory score FooBar` reads 1.0. With `RMX_BOOST_REINFORCE=1`, a query
   whose term is `m5` boosts the postings of concept `m5` by the signal of {concept `m5`, memory
   m5}. Mutations, each FAILS it: "resolve with `resolve_concept_ids` only" (score reads 1.0, m4
   missing); "skip `denotes`" (the boost sees 1.0, from the concept's own row only);
   "`memory_link` maintains no `denotes`" (score reads 1.0, m6 missing); "an exact-name concept
   lookup" (`FooBar` reads 0.0); "a second resolver in `cli.py`" (a check asserts both score
   paths and the boost call `reinforcement.resolve_targets`). {#ac-4b}
5. **AC-5 (R3) Memory-only.** A doc d created now (`# Title {#root}`, a root-level
   `rel: reinforces -> [[c]]`) beside AC-3's rows leaves c at 0.1. Mutation: drop the kind filter:
   FAILS (c reads 2.1: the `d#root` concept row and the `d` doc mirror row both count). {#ac-5}
6. **AC-6 (R5) No raw seeding.** A check over `tests/test_reinforcement*.py`, `tests/test_bug218*.py`
   and `eval/reinforcement_*bench.py` finds no `.link(` call whose first argument is
   `"reinforces"`, `"contradicts"` or a variable bound to them. Mutation: restore
   `tests/test_reinforcement.py`'s raw helper: FAILS. {#ac-6}
7. **AC-7 (R5) The bench still measures the same thing (M2).** `.venv-eval/bin/python
   eval/reinforcement_bench.py --alpha 0.3` (the bench is deterministic: it takes no RNG seed) is
   run before and after the change and prints identical metrics, and
   `tests/test_reinforcement_bench.py` passes after it: the change re-orients storage and reading
   together and moves no score. A difference is a defect in R1/R2, not a new baseline. Logs in
   `workflow/review-output/`. Mutation: seed through `Store.memory_link` but leave R2 unswapped:
   the metrics differ. `eval/reinforcement_csn_bench.py` needs `eval/datasets/csn_python`, which is
   not committed; R5 converts its seeding and AC-6 checks it, but it is not run here. {#ac-7}
8. **AC-8 (R0b) Census committed.** The measurement file lists the stores found by R0b's rule
   (the marker search's output included) and has one row per store with a catalog, each with the
   writer-class split (`root_twin` apart), the end-kind split, the dead-end count, R3's real drop
   count, R4's candidate and `ambiguous` counts, and the copy's timestamp. {#ac-8}
9. **AC-9 (R4, only if R0b found candidates).** On a sandbox daemon whose store holds a pre-R1
   row, a canonical GMD row, and an `ambiguous` row (pre-R1 end kinds, a `rel:` `evidence` append
   in `facts.log`): `rmx repair-index --reinforce-orientation` (dry run) prints the candidate and
   the ambiguous row and changes nothing; `--apply` first writes the backup directory (snapshot +
   `facts.log`) and the manifest, then re-orients only the candidate (with its `memory link:`
   evidence row), and a rebuild from a copy of `facts.log` reproduces the applied rows. With the
   daemon stopped, the CLI refuses and writes nothing. Mutations, each FAILS it: apply without the
   `unlink` event (the rebuild holds both orientations); re-orient the ambiguous row; apply when
   the backup copy fails (the injection must leave the catalog unchanged). On the live stores,
   the post-apply R0b census reads 0 candidates. **Flags (r2 M6):** `--reinforce-orientation
   --fragments`, `--reinforce-orientation --dry-run --apply` and `--fragments --apply` each exit 2
   with a usage error and change nothing. Mutation: let `--apply` combine with `--fragments`:
   FAILS. {#ac-9}
10. **AC-10 (R7, bug-223) The boost read fails loudly.** In the sandbox, with
    `RMX_BOOST_REINFORCE=1` and `refmatrix.reinforcement.reinforcement_scores` replaced by a
    stub that raises (a dependency of the method under test, not the method; the stub is
    registered in `workflow/test_mock_registry.md`), a `content_rank` call raises an error whose text starts
    `RMX_BOOST_REINFORCE: reinforcement signal read failed`. With the variable unset, the same
    store's call returns normally (the block never runs). Mutation: restore `except Exception:
    pass`: FAILS (the call returns a ranking). {#ac-10}
11. **AC-11 (R1, S3) A `memory link` survives a dropped GMD line.** c is concept-only. m's file
    has a root-level `rel: reinforces -> [[c]]`, and `Store.memory_link(m, "reinforces", c)` writes
    the same `(m, c)` key. The line is removed from m's file and m is re-ingested through the
    bridge (the path bug-185 R10 runs on). The `(m, c)` row is still present, with its
    `memory link:` evidence row; the `(m#root, c)` row is gone. Mutation: `Store.memory_link`
    writes no evidence row: FAILS (bug-185 R10 unlinks the key). {#ac-11}

## Decision O-2: the route for R4's repair (lead, 2026-11-13: a) {#o-2}

**Decided: (a)**, a USER-GATED live step ([[#r4]]); revision 2 makes it a daemon op (S4). The
options as they were put:

1. **(a, recommended) A one-shot repair, outside plan-22** (as put: "in the bug-195 shape"; since
   revision 2 only bug-195's manifest-first, dry-run-by-default pattern is kept, and the repair
   is a daemon op, [[#r4]]), with the manifest and events of R4. A
   re-orientation removes no knowledge (the same statement is written back), so it is not
   plan-22's knowledge removal under [[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]].
2. **(b) Through plan-22's engine** as a repair class, after 22.2 lands. Cost: bug-218 waits for
   22.2, which queue item 9 places after it.

## Q8 note {#q8-b}

Under Q8 b (save-states and `workflow/` excluded at ingest), the GMD rows whose source is a
`workflow/` doc disappear on re-ingest. R3 already gives them no weight, so no requirement changes;
R0b's counts would differ.

## Revision 1 (2026-11-13, lead rulings) {#rev-1}

| ruling | answered in |
|---|---|
| O-1 = A (GMD orientation canonical; `memory_link` changes; the reader swaps its joins) | [[#o-1]], [[#r1]], [[#r2]], [[#files]] (`ingest_gmd.py` unchanged) |
| O-2 = (a) (one-shot repair, manifest, `unlink` + `link` events, dry-run default; a daemon op since revision 2), a USER-GATED live step | [[#o-2]], [[#r4]], [[#ac-9]] |
| bug-223 (the `except Exception: pass` around the `RMX_BOOST_REINFORCE` read) is owned here | [[#r7]], [[#ac-10]], [[#files]]; removed from [[#out-of-scope]] |

## Revision 2 (2026-11-13, ch-bsd r1 + lead rulings) {#rev-2}

Answers `bsd-spec-t56-r1-fecda59` (scratchpad report, the lead persists it) S1-S4 and M1-M3 under
the lead's rulings of the same day.

| finding / ruling | answered in |
|---|---|
| S1 the root-mirror (two rows per GMD statement) | [[#why-root-mirror]]; [[#r0b]] `root_twin` class and R3's real drop; [[#r3]] states both jobs; [[#ac-2]] row counts; [[#ac-3]] GMD variant + mutation; [[#ac-5]] value 2.1 |
| S2 resolve targets the bug-216 R6 way plus `denotes` | [[#r2b]] `reinforcement.resolve_targets`; [[#ac-4b]] + three mutations; AC-2 pins c's kind |
| S3 `memory_link` writes an evidence row tagged `memory link:` | [[#r1]]; [[#r0b]] writer class; [[#ac-11]] + mutation; cross-checked against bug-185 R10 on `spec-wave-t4` at `db701e8` |
| S4 R4 is a daemon op with a backup prior step | [[#r4]] `_op_repair_reinforce_orientation`, `rmx repair-index --reinforce-orientation`, the backup, candidates vs `ambiguous`; [[#ac-9]]; [[#files]] |
| M1 one `memory_link` body | [[#r1]] `Store.memory_link`; [[#r5]]; AC-2's private-body check |
| M2 AC-7 runnable unattended | [[#ac-7]]: `reinforcement_bench.py --alpha 0.3` + its test; the CSN bench is not run |
| M3 the store list | [[#r0b]] global store + the hook-marker search; [[#ac-8]] |
| M8 (ADR-0004 decision-log line for R4) | [[refmatrix/adr-0004-unified-location-space-index#d-2026-11-13-t56]] |

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: related-to -> [[project_fleet_hooks_found_by_marker_not_hub]]

## Revision 3 (2026-11-13, ch-bsd r2 + lead rulings) {#rev-3}

| finding / ruling | answered in |
|---|---|
| r2 S2 (a hand link made after its target exists got no `denotes`) | [[#r1]] `Store.memory_link` calls bug-216's ingest-time `denotes` helper; [[#ac-4b]] ingests m5 first, no derive step, m6 created now; mutation "`memory_link` maintains no `denotes`" |
| r2 M3 (AC-11 relies on bug-185 R10 keeping its evidence-support clause) | noted; the lead pins it on the writer side (spec-t4: R10 keeps the clause with its own AC) |
| r2 M4 (canonical-variant match on the concept leg) | [[#r2b]] `resolve_concept_ids(name, strict=False)`; AC-4b variant row + mutation |
| r2 M5 (R4's ambiguous count needs `facts.log`) | [[#r0b]] copies `facts.log`; [[#r4]] the `#`-in-name hint as a cross-check only, demoting to `ambiguous`, never promoting |
| r2 M6 (the flag matrix) | [[#r4]] flag matrix; [[#ac-9]] flag rows + mutation |
| lead: bug-185 AC-15's fixture | [[#files]] row; [[#done]] |
| lead (spec-t4 `b13c611`): remove bug-185's `UNOWNED_REL_PRODUCERS` entry for `memory_link` and re-run AC-14/AC-15 | [[#files]] `ingest_gmd.py` row; [[#done]] |

rel: derives-from -> [[plan-review-2026-11-13#lead]]

## Out of scope {#out-of-scope}

- Turning the channel on (`RMX_REINFORCE_ALPHA`, `RMX_BOOST_REINFORCE`): a ranking change, gated
  by ADR-0004's per-type evaluation, not by this fix.
- bug-219 (stale evidence rows): plan-22's census, [[task-22.1a-provenance-free-classes#rev-round-9]].

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/reinforcement.py` | R1 orientation stated once; R2 reader joins swapped; R2b `resolve_targets`; R3 kind filter; docstring (R6) |
| `src/refmatrix/store.py` | R1 `Store.memory_link` (one body: link + `memory link:` evidence); R2b the boost calls `resolve_targets`; R7 (bug-223) the swallow removed, re-raise with context |
| `src/refmatrix/cli.py` | `memory link` local path calls `Store.memory_link`; `memory score` local path calls `resolve_targets`; `repair-index --reinforce-orientation [--apply]` (R4); R6 help text |
| `src/refmatrix/daemon.py` | `_op_memory_link` calls `Store.memory_link`; `_op_memory_score` calls `resolve_targets`; `_op_repair_reinforce_orientation` in `OPS` (R4, only if R0b finds candidates) |
| `tests/test_bug218_reinforcement_direction.py` (new) | AC-1..AC-6, AC-4b, AC-9 sandbox half, AC-10, AC-11 |
| `tests/test_reinforcement.py` | fixtures seed through the writers (R5) |
| `workflow/test_mock_registry.md` | AC-10's raising `reinforcement_scores` stub |
| `eval/reinforcement_bench.py`, `eval/reinforcement_csn_bench.py` | seed through the writers (R5); AC-7 runs |
| `scripts/census_on_copy.py` (16.6's) or a scratch census script | R0b (read-only, copies only) |
| `workflow/measurements/bug218-direction-census-<date>.md` (new) | AC-8 |
| `src/refmatrix/ingest_gmd.py` (`UNOWNED_REL_PRODUCERS`, bug-185's, spec-wave-t4) | REMOVE the entry `("*", "concept", "memory", "bug-218")`. bug-185 pinned it to `memory_link`'s pre-R1 shape (concept side = the concept, entity side = the memory) with this task as owner. After R1, `memory_link` writes the GMD orientation and its own `memory link:` evidence row, so it is no longer an unowned producer |
| `tests/` (bug-185's AC-15 test, spec-wave-t4 at `4133f35`) | bug-185 merges first and writes a `memory_link`-shaped edge through `Store.link` + `Store.add_evidence`; this task switches that fixture to the real `Store.memory_link` ([[#r1]]) and re-runs bug-185 AC-15 |
| `workflow/bug_registry.md` | bug-218 row: premise corrected (two writers), status, fix sha; bug-223 row: fix sha; any sibling silent guard R7 finds, as its own row |

## Definition of done {#done}

- RED run (AC-1) and GREEN run recorded under `workflow/review-output/`, mutation check noted.
- Implementation summary at `workflow/implementation_summaries/task-bug218-reinforcement-edge-direction.md`.
- bug-185's AC-15 fixture uses `Store.memory_link`. bug-185's `UNOWNED_REL_PRODUCERS` entry for
  `memory_link` is removed, and bug-185 AC-14 (every `rel:`-verb producer writes evidence, with
  the unowned skip) and AC-15 are re-run green after both changes (logs cited).
- Committed on branch `task-bug218-reinforcement-edge-direction`; merged `--no-ff` to `master`;
  the bug-218 row updated with the sha.
