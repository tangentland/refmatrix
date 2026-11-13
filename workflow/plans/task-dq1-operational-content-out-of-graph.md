---
gmd: "0.1"
id: task-dq1-operational-content-out-of-graph
title: "Task D-Q1: operational content stays in the partition, out of the skew — one predicate keeps workflow/, save-states and digests out of co-mention and concept-weight derivation, and default ranking puts them below code/docs; pre-registered DOESN'T-SKEW and USEFUL gates"
tags: [task, d-q1, q8, q9, operational-content, derive, pagerank, ranking, context, scan-prompt, measurement, t6, fleet]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
  revision: 4
---

# Task D-Q1: operational content stays in the partition, out of the skew {#root}

> Status: Drafting (2026-11-13, spec wave G22). Revision 4: revision 3's Q9 direction with the
> lead's rulings on revision 2's open items ([[#rulings]]); revisions 1 (`f19a28b`, ingest
> exclusion) and 2 (`d9296bd`) are superseded ([[#history]]).
> Track: T6 ([[plan-review-2026-11-13#queue]]). [[#r1]]-[[#r3]] have no dependency on plan-22; the
> lead places them in the queue.
> Depends on: bug-216 merged and live (a bare doc id binds the doc, so a `workflow/` doc and its
> anchors are found by name; `denotes` ties a same-named concept to it).
> Nothing is excluded at ingest and nothing is deleted.

rel: implements -> [[plan-review-2026-11-13#d-q1]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: derives-from -> [[open-questions]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r6]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r7-denotes]]
rel: supersedes -> [[feedback_operational_content_not_in_graph]]
rel: depends-on -> [[feedback_converge_repeated_shapes]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[project_fleet_hooks_found_by_marker_not_hub]]

## The decision {#decision}

D-Q1, final per Q8 = a as amended by Q9 (user, 2026-11-13; [[open-questions]] rows Q8 and Q9).
The user on Q9: "I'm okay with it being in the same partition as long as it is useful and doesn't
skew whats returned". So:
- `workflow/` stays ingested in the project partition;
- it is excluded from co-mention / concept-weight derivation;
- it is ranked below code/docs by default unless the query names a workflow doc or anchor;
- save-states and STM digests stay in the store and in memory recall, also excluded from
  co-mention;
- two frozen query sets pin the user's two conditions.
{#decision-text}

## Facts at `1cf3b9f` {#facts}

- **Partitions.** This store has `refmatrix` (code, docs, memory and `workflow/`) and
  `sessions-refmatrix` (session cards, ADR-0003 `#isolate`). `workflow/` is not ignored here.
  {#facts-partitions}
- **Four operational gates exist, none sees `workflow/`, and they disagree:** {#facts-gates}
  - `pagerank._OPERATIONAL_RE = ^(session|digest)[-_]`, used by `build_adjacency(
    exclude_operational=True)` (the `pagerank` derive pass) and imported by `ppr.py`, `enrich.py`
    and `net.py`. It misses save-states (`savestate_*`, mtype `session/recall-state`) and STM
    digests (`focus_summary_*`, mtype `session/digest`), so the `pagerank` pass keeps both.
  - `consolidate._OPERATIONAL_RE` is a copy (`brief.py` re-exports it), beside
    `DEFAULT_EXCLUDE_MTYPES = ("session", "session/*", "digest", "digest/*", "subject")` for the
    memory compile.
  - `scan._is_operational_anchor`: `savestate_`, `session-`, `focus_summary_` and their
    `#anchor` sections, kept out of scan-prompt's PPR expansion unless they are seeds.
  - `context._is_session_card` (`session-` only) sorts session cards after docs in
    `_rank_entries`.
- **Memory recall reads `mentions`.** `recall.hybrid_memory_recall` fuses dense ANN with
  `content_rank` (BM25 over `mentions`). That is how a save-state is recalled and how a
  `workflow/` doc is found by a phrase, so `mentions`, BM25 and embeddings stay untouched.
  {#facts-recall}

## Requirements {#requirements}

1. **R0 Inventory, before the build.** {#r0} Every reader that aggregates `mentions` or typed
   edges into a CONCEPT weight is listed in the summary as "filtered by R1" or "not a concept
   weight, unchanged" (with the reason; BM25 and embeddings are in the second group by decision).
   The list closes only when an `rmx grep` for the four gates' names and the callers of
   `build_adjacency`, `concept_df` and `co_occurrence` finds no unlisted site.
2. **R1 One predicate, `memory_layout.is_operational`.** {#r1}
   - `memory_layout.is_operational(*, name, mtype=None, path=None, project_root=None,
     workflow_docs=frozenset()) -> bool` is True when:
     - `mtype` is `session`, `session/*`, `digest` or `digest/*`; or
     - the name's base (before `#`) starts with `session-`, `session_`, `digest-`, `digest_`,
       `savestate_` or `focus_summary_` (the union of today's name gates; a curated memory whose
       name merely contains "session", such as `project_session_0328`, stays out); or
     - `path`, relative to `project_root`, starts with `workflow/` (path-based, never a segment
       match, so `src/pkg/workflow/x.py` stays out); or
     - the name's base is in `workflow_docs` (the `#anchor` concepts of a `workflow/` doc), or the
       entity is a concept that `denotes` one (bug-216 R7).
   - `memory_layout.operational_ids(con, *, project_root) -> frozenset[int]` loads the
     `workflow_docs` names once and applies the predicate to a partition, for SQL-side callers.
     It is cached per (partition, snapshot) like `concept_df`.
   - **Convergence.** `pagerank._OPERATIONAL_RE`, `consolidate._OPERATIONAL_RE`,
     `scan._is_operational_anchor` and `context._is_session_card` are removed. `pagerank`, `ppr`,
     `enrich`, `net`, `consolidate`, `brief`, `scan` and `context` call the predicate. The
     compile's `subject` exclusion stays local (it is compile-specific). No regex, prefix list or
     path test for operational content remains outside `memory_layout.py`.
3. **R2 The derivations it applies to, named.** {#r2}
   - **`pagerank` pass** (stamped): `build_adjacency(exclude_operational=True)` drops every
     `operational_ids` member, its nodes and its edges. This is where the `savestate_` /
     `focus_summary_` miss ([[#facts-gates]]) is fixed.
   - **`memory-compile` and `memory-compile:pattern`** (stamped): their operational test is the
     predicate. Save-states and digests were already excluded by mtype; a `workflow/` doc is not a
     memory row.
   - **`Store.concept_df`** (the co-mention base rate `assoc.py` reads): counts only
     non-operational entities.
   - **`QueryEngine.co_occurrence`** (the co-mention counts `graphread` serves): skips
     operational entities.
   - **Staleness:** `_DERIVE_PASS_MODULES` gains `memory_layout.py` for `pagerank` and both
     compile passes, so a change to the predicate marks them behind code.
   - **Untouched:** the `ingest` and `gmd` passes (entities, anchors, `rel:` edges, `mentions`),
     BM25 (`content_rank`, `_mentions_bm25_stats`) and embeddings, so `workflow/` docs,
     save-states and digests stay findable by name, anchor, `rel:`, phrase and recall.
4. **R3 Ranking: operational hits below code/docs unless the query names them.** {#r3}
   - **Default `rmx context`.** In `context._rank_entries` the "docs first" key becomes
     "non-operational first": in each co-mention linkage an operational entry sorts after every
     other (hits before non-hits stays the first key). The ref-level hit lists (`content_rank`,
     `context.py:778/792`, and the grep floor's hits) are stably partitioned the same way: each
     part keeps its order, operational hits come last, and a token budget cuts them first.
     Nothing is removed.
   - **scan-prompt** (UserPromptSubmit push hook): its injected entries are partitioned the same
     way. Its PPR expansion keeps dropping operational members unless they are seeds.
   - **The recall pack** (`rmx memory recall --stdin-json … --scope both`, the push hook):
     operational memories (save-states, digests) are partitioned after the other memories.
     `rmx recall-state` and the SessionStart save-state leg, which ask for save-states by design,
     are unchanged.
   - **The exemption.** A query names an operational entity when a ref, seed or query term is an
     exact match for its name, its `<doc>#<anchor>` name, or its path under `workflow/` (resolved
     by bug-216 R6's rules). Only the named entity and, for a doc, its anchors are ranked like
     non-operational hits. Every other operational hit stays last.
5. **R4 Pre-registered acceptance, frozen in this spec before any build.** {#r4} Once this spec is
   approved, the sets' rules, the bands and the actions do not change after a run
   ([[feedback_go_no_go_ranges_not_predrop]]).
   - **Stores.** Throwaway only, under a short `mkdtemp()` root, built from one repo commit plus the
     memory bridge:
     - `W` keeps `workflow/` (a copy of this store);
     - `N`, the reference, is the same build with `workflow/*` in the throwaway's ignore spec.
     Each is measured on the pre-change code (BEFORE) and on the post-change code (AFTER),
     through the production entry points (`rmx context`, `rmx scan-prompt`, the recall hook's
     `rmx memory recall --stdin-json`, `rmx neighbors`) against the throwaway's own daemon
     ([[feedback_measure_the_path_users_run]]).
   - **The sets, drawn without looking at results.** A committed script,
     `eval/dq1/draw_queries.py`, draws with seed `20261113` and reads entity names, paths and
     headings only, never a ranking:
     - CODE/DOC set, drawn from `N`: 80 queries. These are 40 `kind=code` symbol names of at
       least 4 characters from `src/`, 20 GMD doc ids or headings under `docs/`, and 20
       three-word phrases (the rarest three body terms of 20 sampled `docs/` sections).
     - WORKFLOW set, drawn from `W`'s `workflow/` paths: 60 queries. These are 20 doc ids (plans,
       task specs, and at least 4 ch-bsd report ids), 20 `<id>#<anchor>` refs, 10 `rel:` edges
       from a non-`workflow/` doc into a `workflow/` doc, and 10 three-word phrases from plan
       titles.
     Both sets and the script are committed in the RED commit before any `src/` change, and that
     sha is cited in the summary.
   - **DOESN'T SKEW.** For each CODE/DOC query, compute the Jaccard of the top-10 entity names of
     `W` (AFTER) and `N` (AFTER) on `rmx context`'s ref-level hit list and on scan-prompt's
     injected entity set. When `N` returns fewer than 10, use `k = len(N's list)`. A `workflow/`
     or other operational entity in `W`'s top-k counts as a mismatch. Each surface reports its
     MEAN and its MINIMUM, with every per-query value. BEFORE is recorded beside it.
   - **USEFUL.** On `W` (AFTER), measured the same way BEFORE:
     - by name: `rmx context <id>` resolves to the doc, for 20/20;
     - by anchor: `rmx context <id>#<anchor>` resolves to the anchor, for 20/20;
     - by `rel:`: `rmx neighbors <workflow-id>` lists the citing doc, for 10/10;
     - by BM25: the target doc is in the default `rmx context "<phrase>"` output for at least
       8/10;
     - no count is lower AFTER than BEFORE.
   - **Bands and actions (lead ruling, 2026-11-13):**

     | gate | result | action |
     |---|---|---|
     | DOESN'T SKEW | mean ≥ 0.90 AND no query < 0.60, on both surfaces | pass |
     | DOESN'T SKEW | fails, with mean ≥ 0.80 on every surface | re-tune ONCE: extend R1's filter to BM25's corpus statistics (`_mentions_bm25_stats` N and avgdl, and the per-term df `content_rank` reads), the only change that touches skew outside R2/R3; re-measure on the same sets; the pass row decides, otherwise report |
     | DOESN'T SKEW | mean < 0.80 on a surface | report to the user with every per-query value; no tuning |
     | USEFUL | every bar met and no drop from BEFORE | pass |
     | USEFUL | only the BM25 bar missed, at 6/10 or 7/10 | re-tune ONCE: the exemption also matches a query equal (case-folded) to a workflow doc's title; re-measure; the pass row decides, otherwise report |
     | USEFUL | a name, anchor or `rel:` miss, any drop from BEFORE, or BM25 below 6/10 | report to the user with every miss; no tuning (a name, anchor or `rel:` miss is a defect, not a band) |

     A re-tune is one pre-registered change, measured once; the sets never change.
   - **Report.** `workflow/measurements/dq1-skew-useful-<date>.md` (GMD): the sets' sizes and
     sha, every per-query value for both surfaces and both builds, the USEFUL hits and misses,
     each band reached, any re-tune and its result, and the commit and store build of each run.
6. **R5 The superseding memory.** {#r5} `feedback_operational_content_same_partition_not_skewing`,
   GMD per MEMORY-RULES (type `feedback`, fresh id, `created` frozen), with `rel: supersedes ->
   [[feedback_operational_content_not_in_graph]]` (lead ruling: the old memory's "exclude at
   INGEST" is reversed for `workflow/`, and MEMORY-RULES' tree makes a reversed rule a supersede;
   the old file stays as history, and its `MEMORY.md` line is replaced by the new one). It is written at approval, not before, then
   linted, indexed in `MEMORY.md`, and verified by a `rmx memory recall` for a phrase unique to
   it. Text: [[#appendix-memory]].
7. **R6 Rollout: the derive re-runs.** {#r6}
   - **Stores:** this repo's store; every fleet repo found by the installed hook marker
     (`grep -l "refmatrix: refresh" <repo>/.git/hooks/post-commit` over `~/github`,
     `~/claude_tools` and `~/enduris`, skipping `_frameworks_and_libraries`;
     [[project_fleet_hooks_found_by_marker_not_hub]], the bug-209 rule) that holds a
     `.refmatrix/` catalog; and the global store `~/.refmatrix/`. The list is printed first.
   - **Per store, after the deploy:** re-run the `pagerank` pass and both compile passes through
     the store's daemon (the compile with its own `--apply` rules; 26.6), and record the stamps
     in `workflow/measurements/dq1-rollout-<date>.md`. The cached aggregates (`concept_df`,
     `operational_ids`) refresh on their own.
   - **Gates:** this repo's store re-derives with the deploy (announced). Each OTHER fleet store's
     live re-derive is user-gated and recorded as done (with the date of the user's go) or `held`.
     No ignore file changes, and no row is deleted.
8. **R7 The profile is unchanged.** {#r7} `.claude/PROJECT_PROFILE.md` `#corpus` keeps `workflow` as
   a corpus root: it is still ingested.

## Acceptance criteria {#acceptance}

1. **AC-1 (R1) Membership.** A sandbox store holds:
   - `workflow/plans/p.md` (GMD, id `p`, anchor `#a`, and a same-named concept `p` that
     `denotes` it);
   - `src/pkg/workflow/x.py`;
   - a save-state `savestate_s1` (mtype `session/recall-state`, with `savestate_s1#root`);
   - a digest `focus_summary_s1` (mtype `session/digest`);
   - `docs/d.md`;
   - a curated memory `project_session_0328`.

   `operational_ids` holds `p`, `p#a`, the concept `p`, `savestate_s1`, `savestate_s1#root` and
   `focus_summary_s1`, and not `x.py`, `d.md` or `project_session_0328`. Mutations, each FAILS it:
   match `workflow` as any path segment (`x.py` joins); `"session" in name`
   (`project_session_0328` joins); drop the anchor rule (`p#a` missing); drop the mtype rule
   (a digest renamed `notes_s2` with mtype `session/digest` is missed). {#ac-1}
2. **AC-2 (R2) Out of the derivations, still findable.** On AC-1's store, every entity mentions
   concept `alpha`:
   - `build_adjacency` has no `operational_ids` node;
   - `concept_df[alpha]` counts `d.md`, `x.py` and `project_session_0328` only;
   - `co_occurrence("alpha")` lists no operational entity;
   - the compile's input excludes the save-state and the digest;
   - `content_rank(["alpha"])` still scores `p.md`;
   - `rmx memory recall` for a phrase unique to `savestate_s1` returns it;
   - `rmx context "<a phrase from p.md's title>"` lists `p.md`.

   Mutations, each FAILS it: keep the old regex in `build_adjacency` (`savestate_s1` and
   `focus_summary_s1` are nodes); drop operational `mentions` at ingest instead (the recall and
   the phrase miss). {#ac-2}
3. **AC-3 (R1) One predicate, mechanical.** An AST check over `src/refmatrix/` finds no
   `_OPERATIONAL_RE`, no `_is_operational_anchor` or `_is_session_card` body, and no string literal
   `savestate_`, `focus_summary_`, `^(session|digest)` or `workflow/` used as an operational test
   outside `memory_layout.py`. The eight modules call `memory_layout.is_operational` or
   `operational_ids`. Mutation: leave `ppr._is_operational` as a regex: FAILS. {#ac-3}
4. **AC-4 (R2) Passes know their module.** `derive_pass_modules` for `pagerank` and both compile
   passes includes `memory_layout.py`. On a copy of the module tree (`_DERIVE_SRC_DIR`), editing
   the predicate flips all three to `behind_code`. Mutation: omit it from `pagerank`: FAILS. {#ac-4}
5. **AC-5 (R3) Below unless named.** On AC-1's store:
   - `rmx context alpha`'s hit list and co-mention lists place `p.md`, `savestate_s1` and
     `focus_summary_s1` after `d.md` and `x.py`; at a budget that fits two entries, no
     operational entry is printed;
   - `rmx context p` ranks `p.md` and `p#a` first, while `savestate_s1` stays last;
   - `rmx scan-prompt` on a prompt naming `alpha` injects `d.md` before `p.md`, and on a prompt
     naming `p` injects `p.md`;
   - the recall pack for a query matching `savestate_s1` and `project_session_0328` lists the
     curated memory first, unless the query names `savestate_s1`.

   Mutations, each FAILS it: no partition (`p.md` ties by score); exempt every operational hit
   when one is named (`savestate_s1` rises on `rmx context p`); exempt on a substring match
   (`rmx context pl` lifts `p.md`). {#ac-5}
6. **AC-6 (R4) The frozen gates.**
   - The R4 sets and script are committed before the first `src/` change (their sha precedes the
     GREEN commits).
   - The report exists, with each gate's band and the action taken.
   - A pass requires the pass band, reached directly or after the one pre-registered re-tune.
   - A report-band result goes to the user with its numbers, and the bands are not edited.
   {#ac-6}
7. **AC-7 (R5) The memory exists and is found.** It lints with 0 errors, carries `rel: supersedes ->
   [[feedback_operational_content_not_in_graph]]`, replaces the old memory's `MEMORY.md` line, and
   `rmx memory recall` for a phrase unique to it returns it. {#ac-7}
8. **AC-8 (R6) The rollout record.** `workflow/measurements/dq1-rollout-<date>.md` lists the marker
   search's output and, per store, the three derive stamps and the user's go (date) or `held`.
   {#ac-8}

## Rulings folded (lead, 2026-11-13) {#rulings}

- The exemption covers the named entity only: accepted.
- The memory supersedes `feedback_operational_content_not_in_graph`, not amends.
- Bands: mean Jaccard ≥ 0.90 with no query below 0.60; name 20/20, anchor 20/20, `rel:` 10/10,
  BM25 ≥ 8/10, no drop from BEFORE. They freeze at approval.
- The pass / re-tune-once / report actions follow the lead's Q9 direction.

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/memory_layout.py` | R1 `is_operational`, `operational_ids` |
| `src/refmatrix/pagerank.py`, `ppr.py`, `enrich.py`, `net.py`, `consolidate.py`, `brief.py`, `scan.py`, `context.py` | R1 call the predicate (private gates removed); R2 `build_adjacency`; R3 the partitions in `context._rank_entries`, the hit lists and scan-prompt |
| `src/refmatrix/store.py` | R2 `concept_df`; `_DERIVE_PASS_MODULES` (`pagerank`, both compile passes) gain `memory_layout.py` |
| `src/refmatrix/query.py` | R2 `co_occurrence` |
| `src/refmatrix/cli.py` / `verbs.py` (the recall pack's ordering) | R3 |
| `eval/dq1/draw_queries.py`, `eval/dq1/queries-*.txt` (new) | R4 frozen sets (RED commit) |
| `eval/dq1/measure.py` (new) | R4 runs through the production entry points |
| `tests/test_dq1_operational_weights.py` (new) | AC-1..AC-5 |
| `workflow/measurements/dq1-skew-useful-<date>.md`, `workflow/measurements/dq1-rollout-<date>.md` (new) | AC-6, AC-8 |
| the memory dir: the R5 file and its `MEMORY.md` line | R5, AC-7 |

## Definition of done {#done}

- RED and GREEN runs recorded under `workflow/review-output/`, the mutation check noted, and the
  R4 sets committed before the first `src/` change.
- The implementation summary at
  `workflow/implementation_summaries/task-dq1-operational-content-out-of-graph.md`.
- Committed on branch `task-dq1-operational-content-out-of-graph` and merged `--no-ff` to
  `master`, with every store's rollout row recorded (done or `held`).

## History {#history}

- **Revision 1** (`f19a28b`) followed Q8 = a literally: a `workflow/*` ignore line, a purge
  through 22.6 R3, a backup gate, and a lint-parity carve-out.
- **Revision 2** (`d9296bd`) followed Q9 but homed the gate in `pagerank.py` and also filtered the
  BM25 statistics.
- **Revision 3** (`2032cf4`) follows the lead's Q9 direction: the predicate is
  `memory_layout.is_operational`, BM25 is untouched (filtering its statistics is now only the
  DOESN'T-SKEW re-tune), the recall pack is ranked, the gates have pre-registered actions, and
  there is no ignore line, purge or 22.6 dependency.
- **Revision 4** folds the lead's rulings on revision 2's open items ([[#rulings]]): `supersedes`,
  and revision 2's accepted bands and sets, mapped onto revision 3's action table.
{#history-revs}

## Appendix: the amendment memory's text {#appendix-memory}

Frontmatter: `id: feedback_operational_content_same_partition_not_skewing`, `title: "Operational
content stays in the same partition, useful and not skewing what is returned"`, `tags: [feedback,
derive, ranking, operational-content]`, `type: feedback`. Body:

> `# Operational content: same partition, useful, not skewing {#root}`
>
> `workflow/` (plans, task specs, ch-bsd reports, summaries) stays ingested in the project
> partition, findable by name, anchor, `rel:` and phrase. Save-states and STM digests stay in the
> store and in memory recall. One predicate, `memory_layout.is_operational`, keeps all three out of
> co-mention and concept-weight derivation (pagerank, the memory compile, `concept_df`,
> co-occurrence). Default `rmx context`, scan-prompt and the recall pack rank them below code and
> docs unless the query names that doc or anchor.
>
> `**Why:**` the user, Q9, 2026-11-13: "I'm okay with it being in the same partition as long as
> it is useful and doesn't skew whats returned". This supersedes the parent rule, whose mechanism
> (exclude at ingest) is reversed for `workflow/`. Its reasons stand (operational text co-mentions everything and goes
> stale), and they are met by the weights and the ranking, not by removal. Two frozen query sets
> pin the conditions: DOESN'T SKEW (code/doc top-10 Jaccard against a store without `workflow/`)
> and USEFUL (workflow docs found by name, anchor, `rel:` and phrase).
>
> `**How to apply:**` a new kind of operational content joins the one predicate, never a private
> regex or an ingest exclusion. Check any ranking change against the frozen sets.
>
> `rel: supersedes -> [[feedback_operational_content_not_in_graph]]`
