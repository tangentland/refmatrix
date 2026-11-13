---
gmd: "0.1"
id: task-dq1-operational-content-out-of-graph
title: "Task D-Q1: workflow/ stays in the project partition but out of co-mention and concept-weight derivation and ranked below code/docs; save-states and STM digests likewise out of the derivation; pre-registered DOESN'T-SKEW and USEFUL gates"
tags: [task, d-q1, q8, q9, operational-content, derive, pagerank, ranking, context, scan-prompt, measurement, t6, fleet]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
  revision: 2
---

# Task D-Q1: operational content stays in the store, out of the weights {#root}

> Status: Drafting (2026-11-13, spec wave G22). Revision 2 replaces revision 1 (`f19a28b`, the
> ingest-exclusion version) after Q9 ([[#history]]).
> Track: T6, queue item 9 ([[plan-review-2026-11-13#queue]]).
> Depends on: bug-216 merged and live (bare doc ids bind the doc, so a `workflow/` doc and its
> anchors are found by name; `denotes` ties a same-named concept to it).
> User gates: only the per-store live `pagerank` re-derive ([[#r6]]).

rel: implements -> [[plan-review-2026-11-13#d-q1]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: derives-from -> [[open-questions]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r6]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r7-denotes]]
rel: amends -> [[feedback_operational_content_not_in_graph]]
rel: depends-on -> [[feedback_converge_repeated_shapes]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[project_fleet_hooks_found_by_marker_not_hub]]

## The decision {#decision}

D-Q1, FINAL per Q8 = a as amended by Q9 (user, 2026-11-13; [[open-questions]] rows Q8 and Q9):
`workflow/` STAYS in the project partition, "as long as it is useful and doesn't skew whats
returned". It is excluded from co-mention / concept-weight derivation and ranked below code/docs
by default unless the query names a workflow doc or anchor; a frozen query set pins both
conditions. Save-states and digests stay in the store and in memory recall, excluded from
co-mention. There is no ingest exclusion and no purge. {#decision-text}

## Facts at `1cf3b9f` {#facts}

- **Partitions.** This store has `refmatrix` (code, docs, memory and `workflow/`) and
  `sessions-refmatrix` (session cards, ADR-0003 `#isolate`). `workflow/` is not ignored here;
  viascope's ignore file lists it. {#facts-partitions}
- **Four name gates exist, and none sees `workflow/`:** {#facts-gates}
  - `pagerank._OPERATIONAL_RE = ^(session|digest)[-_]`. `build_adjacency(exclude_operational=
    True)` (the `pagerank` derive pass) drops matching entities. `ppr.py`, `enrich.py` and
    `net.py` import it.
  - `consolidate._OPERATIONAL_RE` is a copy (`brief.py` re-exports it), beside
    `DEFAULT_EXCLUDE_MTYPES = ("session", "session/*", "digest", "digest/*", "subject")` for the
    memory compile.
  - `scan._is_operational_anchor` matches `savestate_`, `session-` and `focus_summary_` (and
    their `#anchor` sections) and keeps them out of scan-prompt's PPR expansion.
  - `context._is_session_card` (`session-` only) sorts session cards after docs in
    `_rank_entries`.

  So the `pagerank` pass keeps every save-state (`savestate_*`, mtype `session/recall-state`),
  STM digest (`focus_summary_*`, mtype `session/digest`) and `workflow/` doc in the centrality
  graph today, and the read-side statistics count them all.
- **Read-side concept weights** (cached per partition in `Store`, invalidated together at
  `store.py:5311`): `concept_df` (the co-mention base rate `assoc.py` reads),
  `_mentions_bm25_stats` (BM25 N and avgdl), `mentions_tf_tail`, `code_fraction`. {#facts-stats}
- **Memory recall reads `mentions`.** `recall.hybrid_memory_recall` fuses dense ANN with
  `content_rank` (BM25 over `mentions`, `kinds=["memory"]`), so a save-state's body terms are how
  recall finds it. The recall hook (`rmx memory recall --stdin-json … --scope both`) returns
  `kind=memory` rows only, so it never returns a `workflow/` doc. {#facts-recall}

## Requirements {#requirements}

1. **R0 Inventory, before the build.** {#r0} Every reader that aggregates `mentions` (or typed
   edges) into a CONCEPT weight (centrality, document frequency, BM25 statistics, co-occurrence,
   clustering) is listed in the summary as "filtered by R1" or "not a concept weight, unchanged",
   with the reason. The list closes only when an `rmx grep` for the four gates' names and for the
   callers of `build_adjacency`, `concept_df`, `_mentions_bm25_stats`, `mentions_tf_tail`,
   `code_fraction` and `co_occurrence` finds no unlisted site.
2. **R1 One operational gate, extended from the existing ones.** {#r1}
   - **Home.** `pagerank.py` keeps the gate (its regex is the one three modules already import)
     and grows it into:
     - `pagerank.is_operational_name(name) -> bool`: the union of today's name gates (the base
       name before `#` starts with `session-`, `session_`, `digest-`, `digest_`, `savestate_` or
       `focus_summary_`). Curated memories whose names merely contain "session"
       (`project_session_0328`) stay out of it;
     - `pagerank.operational_ids(con, *, project_root) -> frozenset[int]`: the entity ids the gate
       covers in a partition. That is every name the name gate matches, plus every entity whose
       `path`, relative to `project_root`, starts with `workflow/`, plus the `#anchor` concepts of
       those docs (`<doc-name>#…`), plus every concept that `denotes` one of them (bug-216 R7).
       Cached per (partition, snapshot) like `concept_df`.
   - `consolidate._OPERATIONAL_RE`, `scan._is_operational_anchor` and `context._is_session_card`
     become calls to these. No module keeps its own regex, prefix list or path test. The
     compile's `DEFAULT_EXCLUDE_MTYPES` stays (it filters by mtype, and `subject` is
     compile-specific). No parallel mechanism (a new partition, a new linkage, an ingest flag) is
     introduced.
3. **R2 The derivations the gate touches, named.** {#r2}
   - **`pagerank` pass** (stamped): `build_adjacency(exclude_operational=True)` drops every id in
     `operational_ids` (nodes and their edges), so `workflow/` docs, save-states, digests and their
     anchors carry no centrality and lend none. `_DERIVE_PASS_MODULES["pagerank"]` already holds
     `pagerank.py`; no change there.
   - **`memory-compile` and `memory-compile:pattern`** (stamped): the name gate comes from
     `pagerank`; save-states and digests were already excluded by mtype, so no row changes. Both
     pass entries gain `pagerank.py` so a gate change marks them behind code.
   - **`Store.concept_df`**, **`_mentions_bm25_stats`** (N, avgdl), **`mentions_tf_tail`** and
     **`code_fraction`**: computed over non-operational entities only. The operational entities
     keep their `mentions` rows and are still SCORED by `content_rank`, so BM25 finds them; they
     just do not move any other entity's weights.
   - **`QueryEngine.co_occurrence`** (the co-mention counts `graphread` serves): skips
     operational entities.
   - **Not touched:** the `gmd` and `ingest` passes (a `workflow/` doc's entity, anchors, `rel:`
     edges, body terms and vectors are written as today), embeddings, and memory recall's BM25
     scoring of a save-state.
4. **R3 Ranking: `workflow/` below code/docs unless the query names it.** {#r3}
   - **Default `rmx context`.** In `context._rank_entries` the existing "docs first" tier becomes
     "non-operational first": inside each co-mention linkage, an entry for an `operational_ids`
     member sorts after every other entry (hits before non-hits stays the first key). The
     ref-level hit lists (`content_rank` over `kinds=["code","doc","memory","concept"]`,
     `context.py:778/792`, and the grep floor's hits) are stably partitioned the same way: same
     order inside each part, operational hits last. Under a token budget they are cut first.
     Nothing is removed.
   - **scan-prompt** (the UserPromptSubmit push hook): its injected entries are partitioned the
     same way. Its PPR expansion already drops the gate's members unless they are seeds; that
     exemption is kept.
   - **The recall hook** returns `kind=memory` only ([[#facts-recall]]), so no `workflow/` doc
     reaches it. Save-states keep their place in memory recall (Q8 a).
   - **"Unless the query names a workflow doc or anchor."** A query names one when a ref or seed
     resolves, by bug-216 R6's rules, to a `workflow/` doc, one of its `#anchor` concepts, or a
     path under `workflow/`. The NAMED doc and its anchors are then ranked like any doc. Other
     operational hits stay last. This is the same seed exemption scan-prompt already applies.
5. **R4 Pre-registered acceptance, frozen before the build.** {#r4} The bands below are part of
   this spec; once it is approved they do not change after a run
   ([[feedback_go_no_go_ranges_not_predrop]]).
   - **Stores.** All throwaway: under a short `mkdtemp()` root, never the live store. `W` is a
     copy of this store built by a full ingest of one repo commit plus the memory bridge. `N` is
     the same build with `workflow/*` in the throwaway's ignore spec (`workflow/` absent). Each is
     measured on the pre-change build (BEFORE) and the post-change build (AFTER) through the
     production entry points (`rmx context`, `rmx scan-prompt`, `rmx neighbors`; the daemon of the
     throwaway store), never a bespoke path ([[feedback_measure_the_path_users_run]]).
   - **Drawing the sets (frozen first).** A committed script, `eval/dq1/draw_queries.py`, reads
     `N` only and never reads a ranking, and draws with seed `20261113`:
     - the CODE/DOC set: 40 `kind=code` entity names (≥ 4 characters, `src/` paths), plus 20 GMD
       doc ids under `docs/`, plus 20 three-word phrases (the rarest three body terms of 20
       sampled `docs/` sections);
     - the WORKFLOW set, read from `W`'s `workflow/` paths and recorded beside it: 20 doc ids
       (plans, task specs, ch-bsd reports), 20 `<id>#<anchor>` refs, 10 `rel:` edges from a
       non-`workflow/` doc into a `workflow/` doc, and 10 three-word rarest-term phrases from
       sampled `workflow/` sections.
     Both sets and the script are committed in the RED commit, before any `src/` change; that
     sha is cited in the summary.
   - **DOESN'T SKEW (gate).** For each CODE/DOC query, take `k = min(10, len(N's list))` and
     compute the Jaccard of the top-k entity names of `W`'s list and `N`'s list, for `rmx context`
     (the ref-level hit list) and for scan-prompt's injected entity set. A `workflow/` entity in
     `W`'s top-k counts as a mismatch. **PASS** on AFTER when the mean Jaccard is ≥ 0.90 and no
     query is below 0.60, on each surface. BEFORE is recorded, not gated.
   - **USEFUL (gate).** On `W`, AFTER:
     - by name: `rmx context <id>` resolves to the doc for 20/20;
     - by anchor: `rmx context <id>#<anchor>` resolves to the anchor for 20/20;
     - by `rel:`: `rmx neighbors <workflow-id>` lists the citing doc for 10/10;
     - by BM25: the target doc appears in the default `rmx context "<phrase>"` output for at
       least 8/10.
     BEFORE is recorded. **FAIL** on any count below its bar, or on any count lower AFTER than
     BEFORE.
   - **Report.** `workflow/measurements/dq1-skew-useful-<date>.md` (GMD): both sets' sizes and
     sha, every per-query Jaccard for both surfaces and both builds, the USEFUL counts, the
     verdicts, and the commit and store build of each run.
6. **R5 The amendment memory.** {#r5} A new memory,
   `feedback_operational_content_same_partition_out_of_weights`, GMD per MEMORY-RULES (type
   `feedback`, fresh id, `created` frozen), with `rel: amends ->
   [[feedback_operational_content_not_in_graph]]` (the rule stands; the mechanism for `workflow/`
   changes). Written once this spec is approved (the decision is final), linted, indexed in
   `MEMORY.md`, and verified by a `rmx memory recall` for a phrase unique to it. Text:
   [[#appendix-memory]].
7. **R6 Fleet rollout by hook marker.** {#r6}
   - **Stores:** every fleet repo found by the installed hook marker (`grep -l "refmatrix:
     refresh" <repo>/.git/hooks/post-commit` over `~/github`, `~/claude_tools` and `~/enduris`,
     skipping `_frameworks_and_libraries`; [[project_fleet_hooks_found_by_marker_not_hub]], the
     bug-209 rule) that holds a `.refmatrix/` catalog, plus the global store `~/.refmatrix/`. The
     list is printed first.
   - The gate and the ranking ship in code with the release. The read-side statistics follow on
     their own (they are caches, refreshed per partition snapshot). The one live step is a
     `pagerank` re-derive through each store's daemon, which is **user-gated per store**: the
     store is announced, run, and recorded with its derive stamp in
     `workflow/measurements/dq1-rollout-<date>.md`, or recorded `held`. No other step needs a gate.
   - A store whose ignore file already excludes `workflow` (viascope) keeps its line; this task
     changes no ignore file.

## Acceptance criteria {#acceptance}

1. **AC-1 (R1) One gate.** A check over `src/refmatrix/` finds no regex, prefix tuple or
   `workflow/` path test for operational content outside `pagerank.py`; `consolidate`, `brief`,
   `scan`, `context`, `ppr`, `enrich` and `net` call `pagerank.is_operational_name` /
   `operational_ids`. Mutation: leave `scan._is_operational_anchor` with its own prefixes: FAILS. {#ac-1}
2. **AC-2 (R1) Membership.** A sandbox store holds `workflow/plans/p.md` (GMD, id `p`, an anchor
   `#a`, a same-named concept `p` with `denotes`), `src/pkg/workflow/x.py`, a save-state
   `savestate_s1` (and `savestate_s1#root`), a digest `focus_summary_s1`, `docs/d.md`, and a
   curated memory `project_session_0328`. `operational_ids` holds `p`, `p#a`, the concept `p`,
   `savestate_s1`, `savestate_s1#root` and `focus_summary_s1`, and not `src/pkg/workflow/x.py`,
   `docs/d.md` or `project_session_0328`. Mutations, each FAILS it: match `workflow` as any path
   segment (`x.py` joins); `"session" in name` (`project_session_0328` joins); omit anchors
   (`p#a` missing). {#ac-2}
3. **AC-3 (R2) Out of the derivations.** On AC-2's store, with every entity mentioning concept
   `alpha`: `build_adjacency` has no node in `operational_ids`; `concept_df[alpha]` counts
   `docs/d.md`, `x.py` and `project_session_0328` only; `_mentions_bm25_stats` N excludes the
   operational ids; `co_occurrence("alpha")` lists no operational entity. `content_rank(["alpha"])`
   still scores `workflow/plans/p.md`, and `rmx memory recall` for a phrase unique to
   `savestate_s1` returns it. Mutations, each FAILS it: keep the old regex in `build_adjacency`
   (save-state and `p` are nodes); drop operational `mentions` at ingest instead (recall misses
   the save-state, `content_rank` misses `p`). {#ac-3}
4. **AC-4 (R2) Passes know their modules.** Both compile passes list `pagerank.py`; on a copy of
   the module tree (`_DERIVE_SRC_DIR`) an edit to the gate flips `pagerank` and both compile
   passes to `behind_code`. Mutation: omit `pagerank.py` from the compile passes: FAILS. {#ac-4}
5. **AC-5 (R3) Ranked below unless named.** On AC-2's store, `rmx context alpha`'s hit list and
   co-mention lists place `p.md` and `savestate_s1` after `docs/d.md` and `x.py`; at a budget
   that fits two entries, neither operational entry is printed. `rmx context p` ranks `p.md` and
   `p#a` first, while `savestate_s1` stays last. `rmx scan-prompt` on a prompt naming `alpha`
   injects `docs/d.md` before `p.md`; on a prompt naming `p`, `p.md` is injected. Mutations, each
   FAILS it: no partition (`p.md` ties by score); exempt every operational hit when any one is
   named (`savestate_s1` rises on `rmx context p`). {#ac-5}
6. **AC-6 (R4) The pre-registered gates.** The R4 report exists with both sets drawn and committed
   before the first `src/` change (the sha precedes the GREEN commits), and DOESN'T SKEW and
   USEFUL read PASS on AFTER. A FAIL is reported with its numbers and goes to the user; the bands
   are not edited. {#ac-6}
7. **AC-7 (R5) The memory exists and is found.** It lints with 0 errors, carries `rel: amends ->
   [[feedback_operational_content_not_in_graph]]`, has a `MEMORY.md` line, and `rmx memory recall`
   for a phrase unique to it returns it. {#ac-7}
8. **AC-8 (R6) The rollout record.** `workflow/measurements/dq1-rollout-<date>.md` lists the marker
   search's output and, per store, the `pagerank` re-derive stamp and the user's go (date) or
   `held`. {#ac-8}

## Open items {#open-items}

- **The "named" exemption covers only the named doc.** [[#r3]] lifts the demotion for the named
  workflow doc and its anchors only, as scan-prompt's seed exemption does. The alternative reading
  of "unless the query names a workflow doc" (lift it for every operational hit) would let a single
  named plan pull every other plan and save-state up. Recommendation: named-only (as written).
- **amends vs supersedes for the memory.** The parent rule says "Exclude at INGEST"; Q9 reverses
  that mechanism for `workflow/` and keeps the principle. MEMORY-RULES' tree reads a reversed
  mechanism as supersede; the lead asked for `amends`. Recommendation: `amends` (the principle,
  keeping operational content out of the weights, stands).
- **R4's bands.** The 0.90 mean / 0.60 floor and the 8/10 BM25 bar are the spec writer's proposal
  (the lead gave "e.g. top-10 Jaccard ≥ 0.9"). They freeze at approval.

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/pagerank.py` | R1 `is_operational_name`, `operational_ids`; R2 `build_adjacency` uses them |
| `src/refmatrix/consolidate.py`, `brief.py`, `scan.py`, `context.py`, `ppr.py`, `enrich.py`, `net.py` | R1 call the gate; R3 the ranking partition in `context._rank_entries`, the hit lists and scan-prompt |
| `src/refmatrix/store.py` | R2 `concept_df`, `_mentions_bm25_stats`, `mentions_tf_tail`, `code_fraction` over non-operational entities; both compile passes gain `pagerank.py` in `_DERIVE_PASS_MODULES` |
| `src/refmatrix/query.py` | R2 `co_occurrence` skips operational entities |
| `eval/dq1/draw_queries.py`, `eval/dq1/queries-*.txt` (new) | R4 frozen sets (RED commit) |
| `eval/dq1/measure.py` (new) | R4 the four runs through the production entry points |
| `tests/test_dq1_operational_weights.py` (new) | AC-1..AC-5 |
| `workflow/measurements/dq1-skew-useful-<date>.md`, `workflow/measurements/dq1-rollout-<date>.md` (new) | AC-6, AC-8 |
| the memory dir: the R5 file and its `MEMORY.md` line | R5, AC-7 |

## Definition of done {#done}

- RED run and GREEN run recorded under `workflow/review-output/`, mutation check noted; the R4
  sets committed before the first `src/` change.
- Implementation summary at `workflow/implementation_summaries/task-dq1-operational-content-out-of-graph.md`.
- Committed on branch `task-dq1-operational-content-out-of-graph`; merged `--no-ff` to `master`;
  every store's rollout row recorded (done or `held`).

## History {#history}

Revision 1 (`f19a28b`, 2026-11-13) followed Q8 = a literally: an anchored `workflow/*` ignore
line, a manifest-backed purge through 22.6 R3, and a lint-parity carve-out. Q9 (the user: "I'm
okay with it being in the same partition as long as it is useful and doesn't skew whats returned")
superseded it the same day: no ingest exclusion, no purge, no ignore line, no parity change. The
derive filter carried over and is now built from the existing name gates rather than a new
predicate module. {#history-rev-1}

## Appendix: the amendment memory's text {#appendix-memory}

Frontmatter: `id: feedback_operational_content_same_partition_out_of_weights`, `title:
"Operational content stays in the store, out of the weights: workflow/, save-states and digests"`,
`tags: [feedback, derive, ranking, operational-content]`, `type: feedback`. Body:

> `# Operational content: in the partition, out of the weights {#root}`
>
> `workflow/` stays in the project partition: ingested, findable by name, anchor, `rel:` and
> BM25. Save-states and STM digests stay in the store and in memory recall. All three are kept
> out of every co-mention and concept-weight derivation (pagerank, `concept_df`, BM25
> statistics, co-occurrence, the compile) by ONE gate, `pagerank.operational_ids`. Default
> `rmx context` and scan-prompt rank `workflow/` hits below code and docs unless the query names
> that workflow doc or anchor.
>
> `**Why:**` the user, Q9, 2026-11-13: "I'm okay with it being in the same partition as long as
> it is useful and doesn't skew whats returned". The parent rule's reasons stand (operational text
> co-mentions everything and goes stale), but its ingest exclusion also lost what the user wants
> kept: the plans and reports are useful by name. Two frozen query sets pin both conditions
> (DOESN'T SKEW, USEFUL).
>
> `**How to apply:**` a new kind of operational content joins the one gate, never a private
> regex or an ingest exclusion; check a ranking change against the frozen sets.
>
> `rel: amends -> [[feedback_operational_content_not_in_graph]]`
