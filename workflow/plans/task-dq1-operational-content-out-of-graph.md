---
gmd: "0.1"
id: task-dq1-operational-content-out-of-graph
title: "Task D-Q1: operational content stays in the partition, out of the skew — one predicate keeps workflow/, save-states and digests out of co-mention and concept-weight derivation, and default ranking puts them below code/docs; pre-registered DOESN'T-SKEW and USEFUL gates"
tags: [task, d-q1, q8, q9, operational-content, derive, pagerank, ranking, context, scan-prompt, measurement, t6, fleet]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-14
  revision: 7
---

# Task D-Q1: operational content stays in the partition, out of the skew {#root}

> Status: Drafting. Revision 7 (2026-11-14) answers ch-bsd `bsd-spec-t56-r5` ([[#rev-7]]).
> Revision 6 answered `bsd-spec-t56-r4` under the lead's L67 ruling, which amends L61 S3
> ([[#rev-6]]); revision 5 answered r3 under L61 ([[#rev-5]]);
> earlier revisions are in [[#history]].
> Track: T6. Queue slot after bug-216; the lead places it in the POP rewrite (L61 M6).
> Depends on: bug-216 merged and live (a bare doc id binds the doc, so a `workflow/` doc and its
> anchors are found by name). Nothing here depends on plan-22.
> Nothing is excluded at ingest and nothing is deleted.

rel: implements -> [[plan-review-2026-11-13#d-q1]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[open-questions]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r6]]
rel: supersedes -> [[feedback_operational_content_not_in_graph]]
rel: amends -> [[refmatrix/adr-0003-canonical-partition-layout#not-exclusion]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[feedback_converge_repeated_shapes]]
rel: depends-on -> [[feedback_measure_the_path_users_run]]
rel: depends-on -> [[feedback_go_no_go_ranges_not_predrop]]
rel: depends-on -> [[feedback_clean_corpus_hides_a_dead_gate]]
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
- **Four operational gates exist, they disagree, and none sees `workflow/`.** Each plays one of two
  roles: excluding an entity from a derivation's inputs, or filtering an output list. {#facts-gates}
  - `pagerank._OPERATIONAL_RE = (?i)^(session|digest)[-_]`. `build_adjacency(
    exclude_operational=True)` (the `pagerank` derive pass) excludes matching entities from its
    inputs. `ppr.py` (`:229`, `:301`), `net.py:195` and `enrich.py:163` import it and DROP
    matching entities from their output lists. It misses save-states (`savestate_*`, mtype
    `session/recall-state`) and STM digests (`focus_summary_*`, mtype `session/digest`), so the
    `pagerank` pass keeps both.
  - `consolidate._OPERATIONAL_RE` is a copy. It filters the compile's input rows (`:130`, beside
    `DEFAULT_EXCLUDE_MTYPES`) and its label candidates (`:210`). `brief.py` re-exports it as
    `OPERATIONAL_RE` and skips findings with it (`:323`, `:406`).
  - `scan._is_operational_anchor` (`savestate_`, `session-`, `focus_summary_`, case-sensitive)
    drops non-seed members from scan-prompt's PPR expansion (`scan.py:825`).
  - `context._is_session_card` (`session-`) is a FILTER at `context.py:360`, `:671` and `:834`
    (session cards are hidden unless `--include-sessions`) and a sort key at `:1265` for the
    cards that were opted back in.
- **An anchor node carries its doc's path.** `ingest_gmd.py:1539-1542` upserts every
  `<doc>#<anchor>` concept with the doc's `path`. A path rule therefore covers a doc's anchors.
  {#facts-anchor-path}
- **The read-side caches** (`concept_df` and the BM25 statistics) are dropped together by
  `Store._invalidate_content_rank_caches` (`store.py:5292-5301`) at write boundaries. They are
  keyed on the partition id only. {#facts-caches}
- **Memory recall reads `mentions`.** `recall.hybrid_memory_recall` fuses dense ANN with
  `content_rank` (BM25 over `mentions`), so `mentions`, BM25 scoring and embeddings stay
  untouched. That is how save-states are recalled and how `workflow/` docs are found by phrase.
  {#facts-recall}
- **Existing tests pin the gates:** `tests/test_scan_prompt_dedup.py:20,70-75` (imports
  `_is_operational_anchor`; four members, and the non-members `project_scan_prompt_junk_gate#root`
  and `scan-prompt`), `tests/test_brief_detectors.py:228` (`brief.OPERATIONAL_RE is
  consolidate._OPERATIONAL_RE`), and `tests/test_plan7_10_remedy_r4.py:267` (uses
  `brief.OPERATIONAL_RE`). {#facts-tests}

## Requirements {#requirements}

1. **R0 Inventory, before the build.** {#r0} Every reader that aggregates `mentions` or typed
   edges into a CONCEPT weight, and every site that filters or orders an output list by an
   operational test, is listed in the summary against [[#r2]]'s table, with the reason for each
   placement. BM25 scoring and embeddings are "unchanged by decision". The list closes only when an
   `rmx grep` for the four gates' names, for `OPERATIONAL_RE`, and for the callers of
   `build_adjacency`, `concept_df` and `co_occurrence` finds no site outside the table.
2. **R1 One predicate module, two facets: `memory_layout`.** {#r1}
   - **`is_operational(*, name, kind=None, mtype=None, path=None, project_root=None) -> bool`** is
     True when:
     - `mtype` is `session`, `session/*`, `digest` or `digest/*`; or
     - the name's base (before `#`) starts with `session-`, `session_`, `digest-`, `digest_`,
       `savestate_` or `focus_summary_`, matched CASE-INSENSITIVELY as the old `(?i)` regex did
       (`Session-x` and `DIGEST_x` match). A curated memory whose name merely contains "session",
       such as `project_session_0328`, stays out; or
     - `path`, relative to `project_root`, starts with `workflow/` (a prefix of the relative path,
       never a segment match, so `src/pkg/workflow/x.py` stays out). Because an anchor node
       carries its doc's path ([[#facts-anchor-path]]), a `workflow/` doc's anchors are covered by
       this rule; no name-set rule is needed.

     Operational status comes from mtype, name prefix and path only. A concept that `denotes` a
     `workflow/` doc is NOT operational: a term concept such as `exploration` (the id of
     `workflow/templates/exploration.md`) is also what `docs/` and `src/` mention (r3 S2).
   - **`is_session_card(name) -> bool`**, the separate session-card facet (r3 S1): the name's base
     starts with `session-`, case-insensitively. It drives ONLY `context`'s `include_sessions`
     filter, which stays exactly what it is today.
   - **`operational_ids(store) -> frozenset[int]`**: the ids of the bound partition's entities
     for which `is_operational` holds (name, kind, mtype and path read in one query; project root
     from the store). It is cached on the `Store` instance under `_operational_ids_cache`, keyed by
     the partition id. `Store._invalidate_content_rank_caches` drops it with `_conceptdf_cache`
     (its attribute tuple gains the name), and a reader `Store` opened on a swapped snapshot starts
     with no cache, so a newly ingested `workflow/` doc is a member at the next read (r3 M4).
   - **The adjacency caches key on code, not on a hand-bumped constant (r4 M1, r5 M2).** Both
     tiers of `pagerank.cached_adjacency` add the module function
     `refmatrix.store.derive_code_hash("pagerank")` (`store.py:822`) to their key.
     That is the content hash of the `pagerank` pass's modules, which include `memory_layout.py`
     ([[#r2]] staleness row; AC-4). Any edit to `is_operational`'s rules therefore changes the key
     with no version to remember. Revision 6's `OPERATIONAL_RULES_VERSION` constant is dropped.
   - **Convergence.** `pagerank._OPERATIONAL_RE`, `consolidate._OPERATIONAL_RE`,
     `brief.OPERATIONAL_RE`, `scan._is_operational_anchor` and `context._is_session_card` are
     removed; the sites in [[#r2]] call `memory_layout`. The compile's `subject` exclusion and
     brief's own process-node gates (`_WORKFLOW_NODE_RE`, `_MEMORY_ID_RE`, name rules about
     authored nodes, not operational content) stay where they are.
3. **R2 Every site, its role, its call form (L61 S3 as amended by L67).** {#r2} Derivation sites
   EXCLUDE operational ids from their inputs. Graph WALKERS read the excluding adjacency
   (`ppr.py:211/:269`, `net.py:139` and `enrich.py:126` call `build_adjacency`; `context.py:637`
   calls `cached_adjacency`), so they inherit the exclusion: an operational entity never appears
   in a walk's output and never seeds a walk. Their own operational checks are unreachable and are
   deleted. "Rank last, never remove" holds for the NAME-MATCHED legs only: the `content_rank` and
   grep-floor hit lists, `rmx context`'s ref-level hit list, scan-prompt's matched-concept
   injection, and the recall pack. `context`'s session-card filter is today's behaviour, unchanged
   (r3 S1).

   | site | role | call form | what a member gets |
   |---|---|---|---|
   | `pagerank.build_adjacency(exclude_operational=True)`, the stamped `pagerank` pass | derivation | `operational_ids(store)` | excluded from the adjacency (nodes and edges) |
   | `consolidate`'s compile input (`:130`), the stamped `memory-compile` and `memory-compile:pattern` passes | derivation | `is_operational(name=, mtype=)` per memory row | excluded from clustering (as today for session/digest mtypes) |
   | `Store.concept_df` | derivation | `operational_ids(store)` | not counted in any concept's df |
   | `QueryEngine.co_occurrence` | derivation | `operational_ids(store)` | not counted as a co-mention |
   | `pagerank.cached_adjacency` (in-process and on-disk tiers, `pagerank.py:172-215`) | derivation cache | its key gains `derive_code_hash("pagerank")` | an adjacency built under older rules is never served: the on-disk file is rebuilt (r4 M1, r5 M2) |
   | `ppr.py:229`, `:301` (walker) | unreachable | none; the site's own check is deleted | excluded by the adjacency |
   | `net.py:195` (walker) | unreachable | none; the site's own check is deleted | excluded by the adjacency |
   | `enrich.py:163` (walker) | unreachable | none; the site's own check is deleted | excluded by the adjacency |
   | `scan.py:825`, scan-prompt's PPR expansion (walker) | unreachable | none; `_is_operational_anchor` is deleted | excluded by the adjacency; an operational entity is never a PPR seed (`present = [sid … if sid in adj]`) |
   | `context._ppr_expand` (`context.py:637`, the degree ≥ 1 walk) | unreachable for operational ids | none; its `:671` session-card filter stays as today (also unreachable on this leg, since session cards are operational) | excluded by the adjacency |
   | scan-prompt's matched-concept injection (the prompt-term match leg) | output, name-matched | `operational_ids(store)` membership | ranked last among injected entries; the named entity is exempt ([[#r3]]) |
   | `brief.py:323` (contradicted), `:406` (orphan concept) | output | `is_operational(name=)` (endpoints are names; a `workflow/` endpoint is caught by `_WORKFLOW_NODE_RE`, unchanged) | findings with an operational endpoint are listed after the others and counted `operational` (today: skipped); L65 |
   | `consolidate.py:210`, compile label candidates | output | `is_operational(name=)` | a candidate only when no other candidate exists |
   | `context.py:360`, `:671`, `:834` | output, FILTER | `is_session_card(name)` | session cards hidden unless `--include-sessions` (unchanged) |
   | `context._rank_entries` (`:1265`), the ref-level hit lists (`context.py:778/792`) and the grep floor's hits | output, name-matched | `operational_ids(store)` membership | ranked last; the named entity is exempt ([[#r3]]) |
   | the recall pack (`rmx memory recall --stdin-json … --scope both`) | output, name-matched | `is_operational(name=, mtype=)` per memory | ranked last among the memories; the named one is exempt |

   - **Staleness:** `_DERIVE_PASS_MODULES` gains `memory_layout.py` for `pagerank` and both
     compile passes, so a predicate change marks them behind code.
   - **Untouched:** the `ingest` and `gmd` passes (entities, anchors, `rel:` edges, `mentions`),
     BM25 scoring and its statistics (only the SKEW re-tune touches the statistics, [[#r4]]), and
     embeddings.
4. **R3 The exemption: an exact name or anchor names it.** {#r3} It applies to the name-matched
   legs only ([[#r2]]); a walk never reaches an operational entity (L67). A query names an
   operational entity when a ref or query term is an exact (case-folded) match for its name, its
   `<doc>#<anchor>` name, or its path under `workflow/`, resolved by bug-216 R6's rules. Only that
   entity, plus a named doc's anchors, ranks like a non-operational entry; every other operational
   entry stays last. `rmx recall-state` and the SessionStart save-state leg ask for save-states by
   design and are unchanged.
5. **R4 Pre-registered acceptance, frozen in this spec before any build (L60, L61).** {#r4} Once this
   spec is approved, the recipe, the sets' rules, the formula, the bands and the actions do not
   change after a run ([[feedback_go_no_go_ranges_not_predrop]]).
   - **The recipe (r3 S4).** Everything runs inside task 23.0's sandbox
     ([[task-23.0-test-sandbox]]): redirected `$HOME` and `RMX_HOME`, the local model cache only
     (`HF_HUB_OFFLINE`), the sandbox guard on.
     - **Each build has its own memory-dir COPY, slugged for that build's root (r4 S1).** ADR-0005
       resolves a memdir's store from its project slug, so a copy that keeps this project's slug
       would resolve to the LIVE project store. W's copy lives at
       `$SANDBOX_HOME/.claude/projects/<slug of W's unpacked root>/memory`, and N's at the same
       path under N's root's slug.
     - **The order inside `eval/dq1/build.py` (r5 S1).** Before each bridge run, it resolves the
       copy's store with the bridge's own resolver, `cli._root_from_projects_slug(<copy path>)`
       (the ADR-0005 slug match against discovered roots). It prints the result and asserts that
       it equals that build's throwaway `.refmatrix/`. ONLY THEN does it run the bridge. On a
       mismatch, or when nothing resolves, it exits non-zero with no write to any store
       (AC-13).
     - **W and N are both FRESH builds of one commit's tree** (`git archive <sha>` unpacked into
       the sandbox; no worktree, and never a copy of the live store). Each gets its own throwaway
       store and daemon, and both run the same steps: `rmx ingest`, the bridge over that build's
       memdir copy, `rmx pagerank`, and `rmx memory compile --apply` for both scopes. They differ ONLY in
       N's `.refmatrix/.refmatrix_ignore` line `workflow/*`.
     - **BEFORE** builds W and N from the RED commit (pre-change code). **AFTER** builds them from
       the GREEN head. The query sets are the same for both.
     - Measurement goes through the production entry points (`rmx context`, `rmx scan-prompt`,
       `rmx neighbors`) against each throwaway daemon ([[feedback_measure_the_path_users_run]]).
   - **The sets, drawn without looking at results.** A committed script,
     `eval/dq1/draw_queries.py`, draws with seed `20261113` and reads names, paths, headings and
     corpus term frequencies only, never a ranking:
     - CODE/DOC set, drawn from N only: 40 `kind=code` symbol names of at least 4 characters from
       `src/`, 20 GMD doc ids under `docs/`, and 20 three-word phrases (the rarest three body terms
       of 20 sampled `docs/` sections);
     - WORKFLOW set: 20 doc ids (plans, task specs, ch-bsd reports), 20 `<id>#<anchor>` refs, 10
       `rel:` edges from a non-`workflow/` doc into a `workflow/` doc, and 10 three-word
       rarest-term phrases from sampled `workflow/` sections. It is read from W's `workflow/`
       paths, the only place they exist. Each `rel:` edge is recorded as `(S, verb, target)`,
       where `S` is the source node parsed from the citing GMD file. Only edges whose `S` is an
       ANCHORED concept (`<doc>#<anchor>`, including `#root`) are eligible, never the synthetic
       root (r5 M1).

     Both sets and the script are committed in the RED commit before any `src/` change, and that
     sha is cited in the summary.
   - **DOESN'T SKEW (r3 S5).** For each CODE/DOC query and surface (`rmx context`'s ref-level hit
     list, and scan-prompt's injected entity set):
     - `k = min(10, len(N's list))`;
     - `TW` and `TN` are the top-k entries of W's and N's lists, compared by entity identity
       `(kind, name, path relative to the project root)`, since ids differ between builds;
     - `OP` is every entry of `TW ∪ TN` that is operational under [[#r1]].

     The score is **`J = |(TW ∩ TN) − OP| / |TW ∪ TN|`**: an operational entry counts in the union
     and never in the intersection. Each surface reports its MEAN, its MINIMUM and every per-query
     value. BEFORE is recorded beside AFTER.
   - **USEFUL.** On W, AFTER, measured the same way BEFORE:
     - name: `rmx context <id>` resolves to the doc, for 20/20;
     - anchor: `rmx context <id>#<anchor>` resolves to the anchor, for 20/20;
     - `rel:`: for each sampled edge, `rmx neighbors <S> --linkage <verb> --limit <L>` lists the
       `workflow/` doc, for 10/10. `L` is at least the walk's cardinality: the harness reads it
       from a first call's `cardinality` and re-asks with that limit, because the default
       `--limit 50` lists in id order and could cut the target (r5 M1). `S` is the anchored node
       that carries the citing `rel:` line. `rmx neighbors` reads LINKS, not
       the adjacency: `graphread.neighbors_payload` (`graphread.py:42-52`) calls
       `QueryEngine.neighbors` (`query.py:273-302`), which walks `Store.load_bitmap(linkage,
       concept_id)` from the resolved concept. That is the stored direction of a `rel:` edge
       (concept side = the source node, entity side = the target), so the walk starts at `S` and
       reaches the target doc. Revision 5's "`rmx neighbors <workflow-id>` lists the citing doc"
       read the edge backwards, and a doc id does not resolve as a concept (r4, L67: "confirm
       from code");
     - BM25: the target doc is in the default `rmx context "<phrase>"` output, for at least 8/10;
     - no count may be lower AFTER than BEFORE.
   - **Bands and actions (L60; L61 S6):**

     | gate | result | action |
     |---|---|---|
     | DOESN'T SKEW | mean ≥ 0.90 AND no query < 0.60, on each surface | pass |
     | DOESN'T SKEW | otherwise, with every mean ≥ 0.80 and every query ≥ 0.45 | re-tune ONCE: extend [[#r1]]'s exclusion to BM25's corpus statistics (`_mentions_bm25_stats` N and avgdl, and the per-term df `content_rank` reads), then re-measure on the same sets; the pass row decides, otherwise report |
     | DOESN'T SKEW | a mean < 0.80 or a query < 0.45, or still failing after the re-tune | report to the user with every per-query value |
     | USEFUL | every bar met, no drop from BEFORE | pass |
     | USEFUL | only the BM25 bar missed | re-tune ONCE, BM25 channel only: [[#r3]]'s exemption also covers a query whose terms ALL appear in one `workflow/` doc's title or in one of its section headings (that doc only), then re-measure; the pass row decides, otherwise report |
     | USEFUL | a name, anchor or `rel:` miss, or any drop from BEFORE | report to the user straight away: a resolution miss is a defect, not a band (rev 3's rule, restored) |

     A re-tune is one pre-registered change, measured once; the sets never change.
   - **Report.** `workflow/measurements/dq1-skew-useful-<date>.md` (GMD): the recipe's commit shas,
     the sets' sizes and sha, every per-query `J` for both surfaces and both builds, the USEFUL
     hits and misses, each band reached, and any re-tune with its result.
6. **R5 The superseding memory.** {#r5} `feedback_operational_content_same_partition_not_skewing`,
   GMD per MEMORY-RULES (type `feedback`, fresh id, `created` frozen), with
   `rel: supersedes -> [[feedback_operational_content_not_in_graph]]`. The old memory's "exclude at
   INGEST" is reversed for `workflow/`, and MEMORY-RULES' tree treats a reversed rule as a
   supersede. Steps, at approval and not before:
   - the old file stays as history, and its `MEMORY.md` line is replaced by the new one;
   - the new file is linted and verified by a `rmx memory recall` for a phrase unique to it;
   - in the same commit, ADR-0003's `rel: depends-on -> [[feedback_operational_content_not_in_graph]]`
     is repointed to the new memory. It cannot be repointed earlier, because a link to a memory
     that does not exist yet fails the repo gate (r3 M5).

   Text: [[#appendix-memory]].
7. **R6 Rollout: derive re-runs on project stores.** {#r6}
   - **Stores:** this repo's store, and every fleet repo found by the installed hook marker
     (`grep -l "refmatrix: refresh" <repo>/.git/hooks/post-commit` over `~/github`,
     `~/claude_tools` and `~/enduris`, skipping `_frameworks_and_libraries`;
     [[project_fleet_hooks_found_by_marker_not_hub]], the bug-209 rule) that holds a project
     `.refmatrix/` catalog. The list is printed first.
   - **Per store, after the deploy:** `rmx pagerank` and both compile passes run through the
     store's daemon, and the stamps go in `workflow/measurements/dq1-rollout-<date>.md`. The caches
     refresh on their own.
   - **Gates:** this repo's store re-derives with the deploy (announced). Each other fleet store's
     live re-derive is user-gated, and is recorded with the date of the user's go or as `held`.
   - **The global store `~/.refmatrix/` is out of this rollout (r3 M6).** It is a deferral row in
     [[deferral_registry#registry]]: its `pagerank` stamp reads `behind_code` until it is
     re-derived, so the gap stays visible.
   - No ignore file changes and no row is deleted.
8. **R7 The profile is unchanged.** {#r7} `.claude/PROJECT_PROFILE.md` `#corpus` keeps `workflow` as
   a corpus root: it is still ingested.

## Acceptance criteria {#acceptance}

Every AC below is in `tests/test_dq1_operational_weights.py` unless it says otherwise, in task 23.0's
sandbox.

1. **AC-1 (R1) Membership** (`test_ac1_membership`). A sandbox store holds:
   - `workflow/plans/p.md` (GMD, id `p`) with an anchor `#a`;
   - `workflow/templates/exploration.md` (id `exploration`) and a concept `exploration`, mentioned
     by `docs/d.md` and `denotes`-linked to that doc;
   - `src/pkg/workflow/x.py`;
   - a save-state `savestate_s1` (mtype `session/recall-state`, with `savestate_s1#root`);
   - a digest `focus_summary_s1` (mtype `session/digest`) and a digest `notes_s2` (mtype
     `session/digest`);
   - entities named `Session-x` and `DIGEST_y`;
   - `docs/d.md`, and a curated memory `project_session_0328`.

   `operational_ids` holds `p.md`, `p#a`, `exploration.md`, `savestate_s1`, `savestate_s1#root`,
   `focus_summary_s1`, `notes_s2`, `Session-x` and `DIGEST_y`. It does NOT hold the concept
   `exploration`, `x.py`, `d.md` or `project_session_0328`.

   Mutations, each FAILS it:
   - match `workflow` as any path segment (`x.py` joins);
   - `"session" in name` (`project_session_0328` joins);
   - the path rule tests `kind='doc'` only (`p#a`, a concept carrying the doc's path, is missed;
     r3 M1);
   - every `denotes` concept joins (`exploration` joins);
   - drop the mtype rule (`notes_s2` is missed);
   - case-sensitive prefixes (`Session-x` and `DIGEST_y` are missed).
   {#ac-1}
2. **AC-2 (R2) Derivation sites exclude; recall and phrase still find**
   (`test_ac2_derivations`). On AC-1's store, every entity mentions concept `alpha`:
   - `build_adjacency` has no `operational_ids` node, and keeps `exploration` with `d.md`'s edge;
   - `concept_df[alpha]` counts `d.md`, `x.py` and `project_session_0328` only;
   - `co_occurrence("alpha")` lists no operational entity;
   - the compile's input excludes the save-state and both digests;
   - `content_rank(["alpha"])` still scores `p.md`;
   - `rmx memory recall` for a phrase unique to `savestate_s1` returns it;
   - `rmx context "<a phrase from p.md's title>"` lists `p.md`.

   Mutations, each FAILS it:
   - keep the old regex in `build_adjacency` (`savestate_s1` and `focus_summary_s1` become nodes);
   - drop operational `mentions` at ingest instead (the recall and the phrase both miss).
   {#ac-2}
3. **AC-3 (R1, R2) One module, mechanical** (`test_ac3_one_predicate`). An AST check over
   `src/refmatrix/`:
   - finds no `_OPERATIONAL_RE` and no `OPERATIONAL_RE`;
   - finds no `_is_operational_anchor`, `_is_session_card` or `_is_operational` body;
   - finds no string literal `savestate_`, `focus_summary_`, `^(session|digest)` or `workflow/`
     used as an operational test outside `memory_layout.py`;
   - finds each site in [[#r2]]'s table calling the form its row names.

   Mutation: leave `ppr._is_operational` as a regex: FAILS. {#ac-3}
4. **AC-4 (R2) Passes know their module** (`test_ac4_pass_modules`).
   `derive_pass_modules` for `pagerank` and both compile passes includes `memory_layout.py`. On a
   copy of the module tree (`_DERIVE_SRC_DIR`), editing the predicate flips all three to
   `behind_code`. Mutation: omit `memory_layout.py` from `pagerank`'s modules: FAILS. {#ac-4}
5. **AC-5 (R2, R3) Each behaviour class** (`test_ac5_ranking`). On AC-1's store plus a session card
   `session-abc`:
   - **walkers inherit the exclusion (L67).** No output of `ppr` (both entry points), `net`,
     `enrich`, scan-prompt's PPR expansion or `context._ppr_expand` (degree ≥ 1), for seeds
     `alpha` or `d.md`, holds an id in `operational_ids`;
   - **name-matched legs rank last, never remove.** `rmx context alpha`'s hit list lists `p.md`,
     `savestate_s1` and `focus_summary_s1` after `d.md` and `x.py`. At a budget that fits two
     entries, neither operational entry is printed. scan-prompt's matched-concept injection for a
     prompt naming `alpha` injects `d.md` before `p.md`;
   - **the session-card filter is unchanged.** `session-abc` is absent from `rmx context alpha` and
     present with `--include-sessions`, while `p.md` is present in both, ranked last (r3 S1);
   - **the exemption.** `rmx context p` ranks `p.md` and `p#a` first, with `savestate_s1` still
     last. scan-prompt on a prompt naming `p` injects `p.md` through the match leg, although `p`
     never seeds PPR. The recall pack lists
     `project_session_0328` before `savestate_s1` unless the query names `savestate_s1`;
   - **brief and labels.** A contradicted pair with an operational endpoint is listed after the
     others and counted `operational`. A compile label is an operational name only when no other
     candidate exists.

   Mutations, each FAILS it:
   - `build_adjacency(exclude_operational=False)` (the walk outputs hold `p.md`, `p#a` and
     `savestate_s1`);
   - no partition on the name-matched legs (`p.md` ties by score);
   - the session filter uses full `is_operational` (`p.md` disappears from default context);
   - the match leg drops operational entries (scan-prompt naming `p` injects nothing);
   - exempt every operational entry when one is named (`savestate_s1` rises on `rmx context p`);
   - exempt on a substring match (`rmx context pl` lifts `p.md`).

   AC-3's check also asserts that the five walker sites hold no operational check of their own.
   {#ac-5}
6. **AC-6 (R1) The cache follows the data** (`test_ac6_cache_invalidation`). With the daemon's
   `Store` holding a computed `operational_ids`, an in-process ingest of a new `workflow/plans/q.md`
   makes `q.md` a member at the next read. Mutation: leave `_operational_ids_cache` out of
   `_invalidate_content_rank_caches`: FAILS (r3 M4). **On-disk adjacency (r4 M1, r5 M2):** on a
   copy of the module tree (`_DERIVE_SRC_DIR`, as AC-4), an `adjacency.cache.npz` / `.json` pair
   is written. Then `is_operational`'s prefix list gains a name, with no other change. The next
   `cached_adjacency` call does not serve the old pair: it rebuilds and rewrites it, and the
   rebuilt adjacency excludes the new name. Mutation: leave the code hash out of the disk key (the
   stale file is served, and the new member is a node): FAILS.
   {#ac-6}
7. **AC-7 (R4) The measuring code can fail** (`tests/test_dq1_measure.py`, against
   `eval/dq1/measure.py`). These are fixture list pairs; no store is involved:
   - an identical non-operational pair scores 1.0;
   - a planted divergence (W `[op, a..e, x, y, z, w]` vs N `[a..j]`) scores 1/3, below 0.60, and
     `measure.py` reports that query below the floor;
   - a pair where both lists carry the same operational `op` (`[op, a..i]` both sides) scores 0.9;
   - with N `[a..e]` and W `[a..e, f..j]`, `k = 5` and the score is 1.0;
   - **the gate reads AFTER (r4 M3).** A query whose BEFORE pair is the planted divergence (1/3)
     and whose AFTER pair is identical (1.0): `measure.py` prints that query's verdict as `pass`,
     scored 1.0, and records BEFORE's 1/3 beside it.

   Mutations, each FAILS it:
   - turn the mismatch rule off (the shared-`op` pair reads 1.0);
   - take `k` from W's list (the short-N pair reads 0.5);
   - score against BEFORE (the AFTER-identical query prints `report`, 1/3).
   {#ac-7}
8. **AC-8 (R4) The re-tune can change an outcome** (`tests/test_dq1_measure.py`). On a sandbox
   store where a `workflow/` doc's title holds every term of a fixture phrase, and a token budget
   cuts that doc from `rmx context "<phrase>"` without the re-tune, the re-tune puts it in the
   output. A phrase whose terms do not all appear in one title or heading is unchanged. Mutation:
   the re-tune requires the query to EQUAL the title (the fixture outcome no longer changes; r3 S6).
   {#ac-8}
9. **AC-9 (R4) The frozen gates.**
   - The R4 sets and script are committed before the first `src/` change (their sha precedes the
     GREEN commits).
   - The report exists with the recipe's shas, each gate's band and the action taken.
   - A pass is a pass band, reached directly or after the one pre-registered re-tune.
   - A report-band result goes to the user with its numbers, and the bands are not edited.
   {#ac-9}
10. **AC-10 (R1) The ported tests** (r3 M2). The assertions of `tests/test_scan_prompt_dedup.py`,
    `tests/test_brief_detectors.py` and `tests/test_plan7_10_remedy_r4.py` that pin the removed
    gates are ported to `memory_layout.is_operational`. Their non-member rows
    (`project_scan_prompt_junk_gate#root`, `scan-prompt`) stay, as regression guards, and the
    identity assertion becomes "`brief` imports the predicate from `memory_layout`". None of these
    tests is deleted. {#ac-10}
11. **AC-11 (R5) The memory and the ADR repoint.** The memory lints with 0 errors, carries
    `rel: supersedes -> [[feedback_operational_content_not_in_graph]]`, replaces the old memory's
    `MEMORY.md` line, and a `rmx memory recall` for a phrase unique to it returns it. In the same
    commit, ADR-0003's `depends-on` names it, and `./scripts/lint-gmd.sh` exits 0. {#ac-11}
12. **AC-12 (R6) The rollout record.** `workflow/measurements/dq1-rollout-<date>.md` lists the
    marker search's output and, per project store, the derive stamps and the user's go (date) or
    `held`. The global store's deferral row exists. {#ac-12}
13. **AC-13 (R4) The mis-slug guard runs before any write** (`tests/test_dq1_measure.py`, r5 S1).
    In the sandbox, a second throwaway store `Z` exists (discovered). A memdir copy is placed under
    the slug of Z's project root, and `build.py` is asked to bridge it for W. `build.py` exits
    non-zero and names both roots, and Z's catalog files and `facts.log` are byte-identical
    afterwards (W's too). A copy under W's own slug resolves to W, and the bridge runs. Mutation:
    assert AFTER the bridge runs: FAILS (Z's `facts.log` changes). {#ac-13}

## Open items {#open-items}

None. The last one, brief's findings under "rank last", is CLOSED by L65 (lead, 2026-11-14): brief
stays an output site, and its findings with an operational endpoint are listed last.
`_WORKFLOW_NODE_RE` is untouched. L65 also accepts ADR-0003's `depends-on` repoint landing with
R5's commit.

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/memory_layout.py` | R1 `is_operational`, `is_session_card`, `operational_ids` |
| `src/refmatrix/pagerank.py`, `ppr.py`, `enrich.py`, `net.py`, `consolidate.py`, `brief.py`, `scan.py`, `context.py` | R2 the table's call forms; the private gates removed; walker checks deleted; name-matched legs rank last; `cached_adjacency`'s keys gain `derive_code_hash("pagerank")` |
| `src/refmatrix/store.py` | R2 `concept_df`; `_invalidate_content_rank_caches` drops `_operational_ids_cache`; `_DERIVE_PASS_MODULES` (`pagerank`, both compile passes) gain `memory_layout.py` |
| `src/refmatrix/query.py` | R2 `co_occurrence` |
| `src/refmatrix/cli.py` / `verbs.py` (the recall pack's ordering) | R2, R3 |
| `eval/dq1/draw_queries.py`, `eval/dq1/queries-*.txt` (new) | R4 frozen sets (RED commit) |
| `eval/dq1/build.py` (new) | R4 the sandbox recipe for W and N; per-build slugged memdir copies; prints and asserts each bridge run's resolved store root |
| `eval/dq1/measure.py` (new) | R4 the formula and the bands |
| `tests/test_dq1_operational_weights.py`, `tests/test_dq1_measure.py` (new) | AC-1..AC-8, AC-13 |
| `tests/test_scan_prompt_dedup.py`, `tests/test_brief_detectors.py`, `tests/test_plan7_10_remedy_r4.py` | AC-10 ported |
| `docs/adr/0003-canonical-partition-layout.md` | the decision-log line (in this revision); the `depends-on` repoint with R5 |
| `workflow/measurements/dq1-skew-useful-<date>.md`, `workflow/measurements/dq1-rollout-<date>.md` (new) | AC-9, AC-12 |
| the memory dir: the R5 file and its `MEMORY.md` line | R5, AC-11 |

## Definition of done {#done}

- RED and GREEN runs recorded under `workflow/review-output/`, with the mutation check noted. The R4
  sets are committed before the first `src/` change.
- Implementation summary at
  `workflow/implementation_summaries/task-dq1-operational-content-out-of-graph.md`.
- Committed on branch `task-dq1-operational-content-out-of-graph` and merged `--no-ff` to
  `master`; every project store's rollout row is recorded (done or `held`).

## Revision 7 (2026-11-14, ch-bsd r5) {#rev-7}

| finding | answered in |
|---|---|
| S1 (the mis-slug guard has no AC; its order is unpinned) | [[#r4]] the order inside `build.py` (resolve with `cli._root_from_projects_slug`, assert, then bridge); [[#ac-13]] + mutation |
| M1 (the `rel:` channel could report false defects) | [[#r4]] only anchored-`S` edges are drawn; `rmx neighbors <S> --linkage <verb> --limit <cardinality>` |
| M2 (`OPERATIONAL_RULES_VERSION` was bumped by hand, unchecked) | [[#r1]] both cache tiers key on `derive_code_hash("pagerank")`, which covers `memory_layout.py`; the constant is dropped; AC-6 edits the rules and sees a rebuild |

rel: derives-from -> [[plan-review-2026-11-13#lead]]

## Revision 6 (2026-11-14, ch-bsd r4 + L67) {#rev-6}

L67 (lead, dev master `a3a459b`) amends L61 S3: its "rank last at the walkers" contradicted the
derivation exclusion the walkers read.

| finding | answered in |
|---|---|
| B1 (walker rows unreachable; AC-5 walker assertions could not hold; operational seeds dropped) | [[#r2]]: walker rows "unreachable: excluded by the adjacency; the site's own check is deleted"; rank-last for the name-matched legs only; [[#r3]] scoped to those legs; AC-5 walk-output assertion, mutation `build_adjacency(exclude_operational=False)`, the match-leg injection of `p`; the ADR-0003 line and the memory text match |
| L67's code check of USEFUL's `rel:` channel | it reads links, not the adjacency (`graphread.py:42-52` → `query.py:273-302`, `load_bitmap`). The check found the channel's query backwards; [[#r4]] now asks `rmx neighbors <S>` from the source node |
| S1 (a memdir copy keeps the live slug) | [[#r4]] per-build slugged copies; `build.py` prints and asserts the resolved root, exiting before any write |
| M1 (disk adjacency cache key) | [[#r2]] `cached_adjacency` row; AC-6 on-disk leg (the key itself is revision 7's code hash) |
| M3 (AC-7's BEFORE mutation had no fixture) | AC-7 BEFORE-divergent / AFTER-identical query, the printed verdict |
| M4 (brief open item) | [[#open-items]] closed by L65 |

rel: derives-from -> [[plan-review-2026-11-13#lead]]

## Revision 5 (2026-11-14, ch-bsd r3 + L61) {#rev-5}

| finding | answered in |
|---|---|
| S1 (`_is_session_card` is a filter) | [[#facts-gates]]; [[#r1]] `is_session_card` facet; [[#r2]] context rows; AC-5 session rows + mutation |
| S2 (`denotes` made term concepts operational) | [[#r1]]: mtype, name prefix and path only; AC-1 `exploration` row + mutation |
| S3 (call form and role per site) | [[#r2]] table; AC-3 checks the forms; AC-5 one row per behaviour class + the "scan by name only" mutation |
| S4 (the W/N recipe; the bridge can reach live) | [[#r4]] recipe: 23.0 sandbox, memdir copy, fresh builds of one commit, the same named passes, differing only in N's ignore line |
| S5 (Jaccard undefined; measuring code unproven) | [[#r4]] formula; AC-7 with three mutations |
| S6 (the re-tune could not change any outcome) | [[#r4]] BM25-only re-tune (all of a query's terms in one title or heading); name/anchor/`rel:` misses go straight to report; AC-8 |
| M1 (an unfailable mutation) | AC-1 "path rule tests `kind='doc'` only", named test `test_ac1_membership` |
| M2 (tests pinning the gates) | [[#facts-tests]]; AC-10 ports them |
| M3 (case) | [[#r1]] case-insensitive prefixes; AC-1 row + mutation |
| M4 (cache key) | [[#r1]] `_operational_ids_cache` dropped by `_invalidate_content_rank_caches`; AC-6 |
| M5 (ADR-0003) | the ADR-0003 decision-log line [[refmatrix/adr-0003-canonical-partition-layout#d-2026-11-14-dq1]]; the `depends-on` repoint with R5 |
| M6 (the global store; queue slot) | [[#r6]] global store as a deferral row; the header's queue line |

rel: derives-from -> [[plan-review-2026-11-13#lead]]

## History {#history}

- **Revision 1** (`f19a28b`) followed Q8 = a literally: a `workflow/*` ignore line, a purge through
  22.6 R3, a backup gate, and a lint-parity carve-out.
- **Revision 2** (`d9296bd`) followed Q9; L60 accepted its direction.
- **Revision 3** (`2032cf4`) moved the predicate to `memory_layout` and pre-registered the action
  bands.
- **Revision 4** (`95720fe`, `e4dc31b`) reconciled revision 3 with L60.
- **Revision 5** (`02d6459`) answers r3 under L61: two facets, no `denotes` clause, a per-site
  table, a pinned recipe, a defined and proven Jaccard, a BM25-only re-tune, and project stores
  only.
- **Revision 6** answers r4 under L67: walkers inherit the exclusion, rank-last is scoped to the
  name-matched legs, per-build slugged memdir copies, the rules version keys the adjacency caches,
  and the `rel:` channel is queried from its source node.
- **Revision 7** answers r5: `build.py`'s guard resolves and asserts before bridging (AC-13),
  the `rel:` channel draws only anchored sources with an explicit linkage and limit, and the
  adjacency caches key on the `pagerank` pass's code hash.
{#history-revs}

## Appendix: the superseding memory's text {#appendix-memory}

Frontmatter: `id: feedback_operational_content_same_partition_not_skewing`, `title: "Operational
content stays in the same partition, useful and not skewing what is returned"`, `tags: [feedback,
derive, ranking, operational-content]`, `type: feedback`. Body:

> `# Operational content: same partition, useful, not skewing {#root}`
>
> `workflow/` (plans, task specs, ch-bsd reports, summaries) stays ingested in the project
> partition, findable by name, anchor, `rel:` and phrase. Save-states and STM digests stay in the
> store and in memory recall. One module, `memory_layout`, decides what is operational (by mtype,
> name prefix and path). Derivations (pagerank, the memory compile, `concept_df`, co-occurrence)
> exclude it from their inputs; graph walks (ppr, net, enrich, scan-prompt's and `rmx context`'s
> expansion) read that excluding adjacency, so they never reach it. Name-matched lists (search
> hits, `rmx context`'s hit list, scan-prompt's matched terms, the recall pack) rank it last and
> never remove it, unless the query names that doc or anchor. Session cards keep their own filter
> (`--include-sessions`).
>
> `**Why:**` the user, Q9, 2026-11-13: "I'm okay with it being in the same partition as long as
> it is useful and doesn't skew whats returned". This reverses the old rule's mechanism (exclude at
> ingest), so it supersedes it. The old rule's reasons stand: operational text co-mentions
> everything and goes stale. They are met by the weights and the ranking, not by removal. Two
> frozen query sets pin the conditions: DOESN'T SKEW (code/doc top-10 Jaccard against a store
> without `workflow/`) and USEFUL (workflow docs found by name, anchor, `rel:` and phrase).
>
> `**How to apply:**` a new kind of operational content joins `memory_layout.is_operational`,
> never a private regex and never an ingest exclusion. Check any ranking change against the frozen
> sets.
>
> `rel: supersedes -> [[feedback_operational_content_not_in_graph]]`
