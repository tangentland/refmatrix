---
gmd: "0.1"
id: task-dq1-operational-content-out-of-graph
title: "Task D-Q1: workflow/ out of the store at ingest (fleet-wide, removed through plan-22's audited path); save-states and STM digests stay in the store and in recall but out of co-mention and concept-weight derivation"
tags: [task, d-q1, q8, operational-content, ingest, ignore, derive, pagerank, memory, t6, fleet]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
---

# Task D-Q1: operational content out of the graph {#root}

> Status: Drafting (2026-11-13, spec wave G22, un-held by Q8 = a).
> Track: T6, queue item 9: "D-Q1's live purge … (**user-gated**)", after 22.2
> ([[plan-review-2026-11-13#queue]]). The live purge and every fleet step are user-gated per store.
> Depends on: bug-216 merged and live (`should_ignore` is THE ingest predicate; R5's recount is
> [[#r3]]'s counter); task 22.6 R3 built and deployed (the manifest-backed purge of a path that
> became ignored). [[#r4]] (the derive filter) depends on neither and may build earlier; its live
> effect is a `pagerank` re-derive.

rel: implements -> [[plan-review-2026-11-13#d-q1]]
rel: derives-from -> [[plan-review-2026-11-13#spec-gaps]]
rel: derives-from -> [[open-questions]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r1]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r2]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r3]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r5]]
rel: depends-on -> [[task-22.6-removal-entry-points#r3]]
rel: amends -> [[feedback_operational_content_not_in_graph]]
rel: depends-on -> [[project_fleet_hooks_found_by_marker_not_hub]]
rel: depends-on -> [[feedback_store_calls_via_daemon]]

## The decision {#decision}

D-Q1, confirmed by Q8 = a (user, 2026-11-13; [[open-questions]] row Q8): `workflow/` is OUT at
ingest, removed through plan-22's audited path after 22.6 R3, and "rel: edges into it lose
targets"; save-states and STM digests stay IN the store and in memory recall, excluded from
co-mention by a derive-time filter. The rule this applies is
[[feedback_operational_content_not_in_graph]]: operational content "co-mentions nearly
everything, so it dominates co-mention weights", and it "goes stale and then actively contradicts
current code". {#decision-text}

## Facts at `1cf3b9f` (bug-216 read on its branch at `4b4b96e`) {#facts}

- **Ignore grammar** (`ingest.IgnoreSpec`, bug-216 branch): a bare name (`workflow`) matches that
  path segment ANYWHERE in the tree; a line containing `/` is anchored to the project root and
  fnmatch'd, so `workflow/*` matches `workflow/...` at the root and nothing deeper (`fnmatch`'s
  `*` crosses `/`). A leading `/` is not a supported anchor (`"/workflow"` never matches a
  relative path). {#facts-grammar}
- **A path that becomes ignored** is purged by sync's `should_ignore` branch
  (`sync.py:195-196`, `s.purge_path`), today with no manifest; 22.6 R3 makes that branch derived
  cleanup that first writes a manifest of every LEARNED row under the path (ingest-derived rows
  are purged as today, and come back by re-ingest). The daemon route over explicit paths is
  `daemon._op_sync_files` (under `d._store_lock`, `sync.sync_files`). {#facts-purge}
- **Memory recall reads `mentions`.** `recall.hybrid_memory_recall` fuses dense ANN with
  `store.content_rank` (BM25 over the `mentions` forward index). A save-state's body terms are
  therefore part of how `rmx memory recall` finds it, and must stay. {#facts-recall}
- **Three operational predicates, none of which sees save-states everywhere:**
  - `pagerank._OPERATIONAL_RE` = `^(session|digest)[-_]` on NAMES, imported by `ppr.py`,
    `enrich.py`, `net.py`; `consolidate._OPERATIONAL_RE` is a copy, re-exported by `brief.py`.
    It misses `savestate_*` (save-states, mtype `session/recall-state`) and `focus_summary_*`
    (STM digests, mtype `session/digest`, written by `handoff.py` / `cli.py`).
  - `scan._is_operational_anchor` matches `savestate_`, `session-`, `focus_summary_` (with
    `#anchor` sections) but not `digest-`.
  - `consolidate.DEFAULT_EXCLUDE_MTYPES = ("session", "session/*", "digest", "digest/*",
    "subject")` filters by MTYPE (the compile only).

  So the `pagerank` derive pass (`build_adjacency(exclude_operational=True)`) keeps every
  save-state and digest, and their `#anchor` concepts, in the centrality graph today, and
  `Store.concept_df` (the co-mention base rate `assoc.py` reads) counts them. {#facts-predicates}
- **The lint/ingest parity gate** (bug-216 R3, `scripts/check-gmd-parity.py`, run by
  `scripts/lint-gmd.sh` over `CLAUDE.md docs/ workflow/ eval/` and the profile) fails when a GMD
  doc in its scope is excluded from ingest. With `workflow/*` in this repo's ignore spec, every
  `workflow/` doc would fail it. {#facts-parity}

## Requirements {#requirements}

1. **R0 Read before building.** {#r0}
   - The inventory of [[#facts-predicates]] is re-read at the build sha, and every reader of a
     `mentions` aggregate that weights a CONCEPT (centrality, document frequency, co-occurrence
     counts, clustering) is listed in the summary with "filtered by R4" or "not a concept weight,
     unchanged" and the reason. The list is closed only when an `rmx grep` for the three
     predicates' names and for `concept_df` / `build_adjacency` callers finds no unlisted site.
   - For each store in [[#r6]], read-only, on a snapshot copy (the ONE census procedure,
     [[task-16.6-learned-row-validation#r7]]): tracked paths under `<project>/workflow/`;
     entities with such a path; learned rows under it (what 22.6 R3's manifest will hold); the
     count of nested `workflow` directories elsewhere in the tree (why [[#r1]] anchors the line);
     save-state and digest entity counts.
2. **R1 `workflow/` is excluded at ingest by the ignore spec.** {#r1} Each project store's
   `.refmatrix/.refmatrix_ignore` gains the line `workflow/*` under a comment naming D-Q1 and this
   task. Anchored (a line with `/`), so a nested `src/.../workflow/` directory stays in the corpus;
   never the bare `workflow` line, which would match any segment ([[#facts-grammar]]). Every walk
   honours it through bug-216's `should_ignore` (R2); no walker keeps a private rule. The line is
   runtime state, written by the rollout ([[#r6]]), not committed.
3. **R2 Existing `workflow/` entities leave through plan-22's audited path, never a bare sync
   purge.** {#r2}
   - **Order gate.** The ignore line is never written to a store whose daemon lacks 22.6 R3,
     because the watcher's next sync of any `workflow/` file would take the unaudited branch.
     The rollout command asks the store's daemon for its version and refuses below the release
     that ships 22.6 R3, naming both.
   - **The purge.** With the line in place, ONE daemon call `_op_sync_files` over every tracked
     path under `<project>/workflow/` (listed from `tracked_files` through the read snapshot):
     each takes sync's ignored branch, so 22.6 R3's `purge_path` writes its cleanup manifest of
     learned rows first, removes them through 22.2's row primitives, and purges the
     ingest-derived rows. The manifest id and the per-kind counts are printed;
     `rmx removal restore --manifest <id>` is the way back for learned rows, and removing the
     ignore line plus a re-ingest for the rest. No `Store()` is opened and no bare `purge_path` is
     called ([[feedback_store_calls_via_daemon]]).
   - **User-gated, per store.** Before the call: the dry-run counts of [[#r0]] and [[#r3]] are
     shown, the store is announced, and a backup is taken (a fresh read snapshot through
     `_op_snapshot`, `facts.log` and the ignore file copied to
     `<store>/backups/dq1-<stamp>/`, paths printed; any copy failure stops the rollout for that
     store before the line is written). The line and the call run only on the user's go.
4. **R3 `docs → workflow` `rel:` edges are counted before and after.** {#r3} With bug-216 R5's
   `scripts/check-rel-landing.py` (on a read-only copy), the rollout records for each store:
   authored `rel:` lines in files OUTSIDE `workflow/` whose target id is a `workflow/` doc; how
   many land before the purge; and after it, how many are `target_unresolved` and how many sit as
   bug-216 R10 pending references. The loss is accepted by the decision ("rel: edges into it lose
   targets"); it is reported, not repaired. Plain `[[workflow-id]]` wikilinks outside `workflow/`
   are counted the same way, on their own line.
5. **R4 Save-states and STM digests stay in, but out of co-mention and concept-weight
   derivation, through ONE predicate.** {#r4}
   - **One predicate.** `memory_layout.is_operational(*, mtype: str | None, name: str) -> bool`:
     True when `mtype` is `session`, `session/*`, `digest` or `digest/*` (consolidate's list less
     `subject`, which is compile-specific and stays there); otherwise, for rows with no mtype
     (concept anchor nodes such as `savestate_x#root`), True when the name's base (before `#`)
     starts with `savestate_`, `focus_summary_`, `session-`, `session_`, `digest-` or `digest_`.
     That is the union of [[#facts-predicates]]'s three; it must keep curated memories whose names
     merely contain "session" (`project_session_0328`) out of it.
   - **The derive passes it touches.**
     - `pagerank` (`pagerank.build_adjacency(exclude_operational=True)`, the stamped pass):
       drops every operational entity and its anchor concepts from the adjacency, replacing
       `_OPERATIONAL_RE`. `_DERIVE_PASS_MODULES["pagerank"]` gains `memory_layout.py`, so a
       change to the predicate marks the pass behind code.
     - `memory-compile` and `memory-compile:pattern` (`consolidate`): `DEFAULT_EXCLUDE_MTYPES` and
       `_OPERATIONAL_RE` are replaced by the predicate (plus `subject`, kept local); the two
       pass entries gain `memory_layout.py`.
     - `Store.concept_df` (the co-mention base rate `assoc.py` reads; a cached aggregate, not a
       stamped pass): counts only `mentions` rows whose entity is not operational.
     - `QueryEngine.co_occurrence` (the co-mention counts `graphread` serves): skips operational
       entities, as `--include-sessions` already does for session cards (`cli.py:5302`).
   - **What it does NOT touch, stated so recall is kept:** the `gmd` pass still emits
     save-states' and digests' body terms (`mentions`), embeddings stay, and
     `content_rank` / `_mentions_bm25_stats` (memory recall's BM25 leg,
     [[#facts-recall]]) are unchanged. `rmx memory recall` and `rmx recall-state` return them as
     before.
   - **Read-side callers converge on it too.** `ppr.py`, `enrich.py`, `net.py`, `brief.py` and
     `scan._is_operational_anchor` call the predicate; no module keeps its own regex or prefix list
     ([[feedback_converge_repeated_shapes]]).
6. **R5 The amendment memory.** {#r5} A new memory file, written once this spec is approved (the
   decision is final), `feedback_operational_content_out_at_ingest_and_derive.md` in the
   refmatrix memory dir, GMD per MEMORY-RULES (type `feedback`, `created` frozen, fresh id) with
   `rel: amends -> [[feedback_operational_content_not_in_graph]]` (same rule, refined scope: the
   amend branch of the decision tree). Its text is [[#appendix-memory]]. It is linted with
   `tools/gmd/lint.py`, added to `MEMORY.md`, and verified by a `rmx memory recall` for a phrase
   unique to it ([[feedback_verify_memory_by_recall_not_get]]).
7. **R6 Fleet rollout by hook marker; per-store gates.** {#r6}
   - **Stores:** every fleet repo found by the installed hook marker (`grep -l "refmatrix:
     refresh" <repo>/.git/hooks/post-commit` over `~/github`, `~/claude_tools` and `~/enduris`,
     skipping `_frameworks_and_libraries`; [[project_fleet_hooks_found_by_marker_not_hub]], the
     bug-209 rule) that has a `.refmatrix/` catalog, plus the global store `~/.refmatrix/` for R4
     only (it is memory-only: no `workflow/`, no ignore line). The list is printed first.
   - **Per store, in order:** R0 counts → R3 "before" counts → announce + backup (R2) → the
     user's go → the ignore line (R1) → the purge call (R2) → R3 "after" counts → a `pagerank`
     re-derive through the daemon (R4's live effect) → one row in
     `workflow/measurements/dq1-rollout-<date>.md`. A store that already carries a `workflow`
     line (viascope) is reported and its line is replaced by `workflow/*` only if R0 found a
     nested `workflow` directory there; otherwise it is left alone.
   - A store whose repo has no `workflow/` directory gets the line anyway (it costs nothing and
     holds the rule) and records 0 purged.
8. **R7 The parity gate excludes `workflow/` by design.** {#r7} `scripts/lint-gmd.sh` keeps
   `workflow/` in the LINT scope and drops it from `PARITY_ARGS`, with a comment naming D-Q1: a
   `workflow/` doc is lint-only, excluded from ingest on purpose, so its ingest parity is not a
   defect. bug-216 R3's must-fail fixture still fails for a doc in any other scope.
9. **R8 The profile says so.** {#r8} `.claude/PROJECT_PROFILE.md` `#corpus` keeps `workflow` as a
   lint and grep root and states that it is excluded from ingest (D-Q1); R0 lists every reader of
   `.claude/hooks/hooks.env` `CORPUS_PATHS`, and the value changes only if one of them feeds
   ingest.

## Acceptance criteria {#acceptance}

1. **AC-1 (R1) The line is anchored.** On a sandbox project whose ignore file holds `workflow/*`:
   `workflow/plans/p.md`, `workflow/README.md` are ignored by `should_ignore` and by every walker
   (bug-216 R2's walker enumeration); `src/pkg/workflow/a.md` and `docs/workflow.md` are not.
   Mutation: write the bare `workflow` line: FAILS (`src/pkg/workflow/a.md` is ignored). {#ac-1}
2. **AC-2 (R2) The purge is audited.** A sandbox daemon whose store tracks `workflow/a.md` (with a
   learned grep row and its sidecar) and `docs/d.md`. After the line and the rollout's purge call:
   `workflow/a.md` has no tracked row and no entity; a cleanup manifest holds the learned row
   with its sidecar; `rmx removal restore --manifest <id>` puts the learned row back; `docs/d.md`
   is untouched; a rebuild from a copy of `facts.log` agrees with the live catalog. Mutations,
   each FAILS it: call `purge_path` directly (no manifest); write the line on a daemon reporting a
   version below 22.6 R3's (the order gate must refuse, and the ignore file must be unchanged);
   continue after a failed backup copy (the injection must leave the ignore file unchanged). {#ac-2}
3. **AC-3 (R3) The edge count.** `docs/d.md` carries `rel: depends-on -> [[w-plan]]` and a plain
   `[[w-plan]]`, where `w-plan` is `workflow/plans/w-plan.md`. Before: 1 authored, 1 landed; after:
   1 authored, 0 landed, 1 `target_unresolved` (or pending), and the wikilink line counted apart.
   Mutation: count only lines inside `workflow/`: FAILS (before reads 0). {#ac-3}
4. **AC-4 (R4) Out of the derives, still in recall.** A sandbox store holds a save-state
   (`savestate_s1`, mtype `session/recall-state`, a GMD file with `{#root}` and a unique phrase),
   a digest (`focus_summary_s1`, mtype `session/digest`), and a curated memory
   `project_session_0328`, all mentioning concept `alpha`. After R4:
   - `build_adjacency` holds no node for the save-state, `savestate_s1#root` or the digest, and
     holds `project_session_0328`;
   - `concept_df[alpha]` counts only `project_session_0328`;
   - `co_occurrence("alpha")` lists no operational entity; the compile's input excludes both;
   - `rmx memory recall "<the unique phrase>"` returns `savestate_s1`, and `content_rank` on that
     phrase scores it.
   Mutations, each FAILS it: keep `_OPERATIONAL_RE` in `build_adjacency` (the save-state is a
   node); match names with `"session" in name` (`project_session_0328` drops); drop operational
   `mentions` at ingest instead (the recall misses the save-state). {#ac-4}
5. **AC-5 (R4) One predicate, mechanical.** A check over `src/refmatrix/` finds no
   `_OPERATIONAL_RE`, no `_is_operational_anchor` body of its own, and no string literal
   `savestate_`, `focus_summary_` or `^(session|digest)` outside `memory_layout.py`. Mutation:
   leave `ppr._is_operational` as a regex: FAILS. {#ac-5}
6. **AC-6 (R4) The pass knows its module.** `derive_pass_modules("pagerank")` and both compile
   passes include `memory_layout.py`; on a copy of the module tree (`_DERIVE_SRC_DIR`), editing
   the predicate flips `pagerank` to `behind_code`. Mutation: omit `memory_layout.py`: FAILS. {#ac-6}
7. **AC-7 (R7) The gate stays green by design.** `scripts/lint-gmd.sh`'s `PARITY_ARGS` holds no
   `workflow/`; `check-gmd-parity.py` over a fixture whose ignore spec holds `workflow/*` fails
   when given `workflow/` (naming the line) and passes when not. With this repo's line in place,
   `./scripts/lint-gmd.sh` exits 0. {#ac-7}
8. **AC-8 (R5) The memory exists and is found.** The file lints with 0 errors, carries
   `rel: amends -> [[feedback_operational_content_not_in_graph]]`, has a `MEMORY.md` line, and
   `rmx memory recall` for a phrase unique to it returns it. {#ac-8}
9. **AC-9 (R6) The rollout record.** `workflow/measurements/dq1-rollout-<date>.md` lists the
   marker search's output and, per store: the R0 counts, the backup path, the manifest id, R3's
   before and after counts, the pagerank re-derive stamp, and the user's go (date). A store
   without the go is listed as `held`. {#ac-9}

## Open items {#open-items}

- **The ignore line's form.** [[#r1]] writes `workflow/*`, the one anchored form the existing
  grammar supports, instead of adding a `/workflow` anchor to the grammar. If the lead prefers a
  grammar change (gitignore's leading-slash anchor), it belongs to bug-216's `IgnoreSpec`, not here.
- **R4's build slot.** R4 has no dependency on 22.6 and is cheap; the queue places the whole task at
  item 9. Building R4 earlier is a queue decision for the lead.

## Files {#files}

| file | change |
|---|---|
| `src/refmatrix/memory_layout.py` | R4 `is_operational(mtype, name)` |
| `src/refmatrix/pagerank.py`, `ppr.py`, `enrich.py`, `net.py`, `scan.py`, `consolidate.py`, `brief.py` | R4: call the predicate; the private regexes and prefix lists removed |
| `src/refmatrix/store.py` | R4: `concept_df` filter; `_DERIVE_PASS_MODULES` (`pagerank`, both compile passes) gain `memory_layout.py` |
| `src/refmatrix/query.py` | R4: `co_occurrence` skips operational entities |
| the rollout entry (a maintenance CLI flag on an existing command, through the daemon; listed per the verb-parity rule) | R2, R3, R6 |
| `scripts/lint-gmd.sh` | R7 `PARITY_ARGS` without `workflow/` |
| `.claude/PROJECT_PROFILE.md` | R8 `#corpus` line |
| `tests/test_dq1_operational_content.py` (new) | AC-1..AC-7 |
| `workflow/measurements/dq1-rollout-<date>.md` (new) | AC-9 |
| the memory dir: `feedback_operational_content_out_at_ingest_and_derive.md` (new), `MEMORY.md` | R5, AC-8 |

## Definition of done {#done}

- RED run and GREEN run recorded under `workflow/review-output/`, mutation check noted.
- Implementation summary at `workflow/implementation_summaries/task-dq1-operational-content-out-of-graph.md`.
- Committed on branch `task-dq1-operational-content-out-of-graph`; merged `--no-ff` to `master`;
  every store's rollout row recorded (done or `held`).

## Appendix: the amendment memory's text {#appendix-memory}

Frontmatter: `id: feedback_operational_content_out_at_ingest_and_derive`, `title: "Operational
content: workflow/ out at ingest; save-states and digests in the store, out of co-mention"`,
`tags: [feedback, ingest, derive, operational-content]`, `type: feedback`. Body:

> `# Operational content: two different exclusions {#root}`
>
> `workflow/` (plans, handoffs, ch-bsd reports, summaries) is excluded at INGEST in every fleet
> store by the ignore line `workflow/*` (anchored; never the bare `workflow`, which matches any
> segment). Save-states (`session/recall-state`) and STM digests (`session/digest`) stay in the
> store and in `rmx memory recall`, but one predicate, `memory_layout.is_operational`, keeps them
> out of every co-mention and concept-weight derivation (pagerank, `concept_df`, co-occurrence,
> the memory compile).
>
> `**Why:**` the user's Q8 = a, 2026-11-13 (D-Q1 confirmed). The parent rule's reasons hold:
> operational text co-mentions everything and goes stale. But a save-state is a memory a later
> session must recall, so removing it from the store (the parent rule's mechanism) would break
> recall; only its weight in the graph is the pollution. `rel:` edges into `workflow/` lose their
> targets, accepted.
>
> `**How to apply:**` never re-include `workflow/` docs in ingest; a new operational memory type
> joins `is_operational`, never a private regex. The lint gate keeps linting `workflow/`, and the
> parity check leaves it out by design.
>
> `rel: amends -> [[feedback_operational_content_not_in_graph]]`
