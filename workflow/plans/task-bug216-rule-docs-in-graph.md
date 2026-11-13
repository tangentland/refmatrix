---
gmd: "0.1"
id: task-bug216-rule-docs-in-graph
title: "Task bug-216: GMD rel: edges bind to the doc they cite — bare doc-id targets resolve doc-first, the rule docs reach the graph, and the gate checks both"
tags: [task, bug-216, gmd, ingest, ignore, linkages, graph]
metadata:
  node_type: task
  status: approved
  created: 2026-11-13
  updated: 2026-11-13
  revision: 4
---

# Task bug-216: the rule docs reach the graph {#root}

> Status: Approved by the lead on the user's direction (2026-11-13: fix bug-216); revision 2 ([[#rev-2]]) widens it to the misbound bare doc-id class; decisions
> taken as the user would, with reasons. Fleet ignore files are NOT changed by this task
> ([[#fleet]]); that is the user's decision.
> Depends on: none.

rel: derives-from -> [[bug_registry]]
rel: derives-from -> [[measurement-task-21.5-relation-gaps-2026-11-13#gmd-gap-correction]]
rel: related-to -> [[task-bug179-lint-ingest-anchor-parity]]
rel: related-to -> [[feedback_operational_content_not_in_graph]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]

## Why {#why}

Recount against the ingester's own evidence (`linkage_evidence` file + line, read-only copy of the
live store, 2026-11-13): 4,048 of 4,490 authored wikilink `rel:` lines landed. 316 did not resolve at
ingest; 247 of those target the project's two rule docs: `[[claude#…]]` 209 (no-silent-failures 103,
no-workarounds 41, no-mocks 38, before-commit 15, …) and `[[project-profile#…]]` 38. Every ch-bsd
finding that says "this violates the no-silent-failures rule" is a dangling edge in the graph,
while `./scripts/lint-gmd.sh` resolves it. {#why-numbers}

Two exclusions stack:

1. `.refmatrix/.refmatrix_ignore` lists `CLAUDE.md` and `.claude` (added 2026-09-04: "program data,
   not knowledge"). Ten days later the cat-herder bootstrap made CLAUDE.md (`id: claude`) and
   `.claude/PROJECT_PROFILE.md` (`id: project-profile`) GMD docs with anchors. {#why-ignore}
2. `ingest._is_ignored` drops EVERY hidden-directory segment, so `.claude/PROJECT_PROFILE.md` is
   excluded by code even with the ignore file fixed. {#why-hidden}

The lint gate's scope (CLAUDE.md, docs, workflow, eval, the profile, the memory dir) is wider than
the ingest scope, and nothing compares the two — the same "two parsers, never compared" shape as
bug-036 and bug-179. {#why-scope}

The user's rule [[feedback_operational_content_not_in_graph]] keeps operational process out of the
graph; CLAUDE.md and the profile are durable project rules and facts, not process, so including
them is consistent with it. The rest of `.claude/` (agent and command templates, settings, hooks)
stays out. {#why-consistent}

## Requirements {#requirements}

1. **R1 Re-include lines.** `IgnoreSpec` accepts `!<path>` lines (anchored, relative to the project
   root; a glob is allowed). A path matching a re-include is NOT ignored, overriding (a) every
   ignore pattern in the spec, wherever it appears, and (b) the built-in hidden-directory rule in
   `_is_ignored`. It never overrides `INGEST_IGNORE_DIRS` (node_modules, venvs, …). A re-include
   applies to files only; a `!dir` line re-includes nothing and is reported once, loudly, when the
   spec loads. {#r1}
2. **R2 One predicate.** Every walk that honours the ignore spec — `ingest_path`'s walk, the
   watcher, `_sync_paths` (including its purge of a path that became ignored), and `ingest-gmd`'s
   walk — goes through `should_ignore(p, root)`; no walk keeps a private copy of `_is_ignored`. A
   test enumerates the walkers. {#r2}

   R2 supersedes task 26.1 AC-2's assertion that the doc walk reads dot-dirs
   (`tests/test_memory_bridge.py::test_ac2_doc_ingest_keeps_its_own_walk`, lead ruling
   2026-11-13): that test now expects the `should_ignore` set with the exclusions counted and
   named, and keeps 26.1's intent — the memory rule never leaks into doc ingest. {#r2-supersedes-261}
3. **R3 Scope parity in the gate.** `scripts/check-gmd-parity.py` (run by `lint-gmd.sh`) fails,
   naming each file and the rule that excluded it, when a GMD doc in the lint scope (outside the
   memory dir, which reaches the store through the bridge) is excluded by `should_ignore` for this
   repo. Its fixture proves it FAILS on a must-fail case
   ([[feedback_clean_corpus_hides_a_dead_gate]]). {#r3}
4. **R4 This store's configuration.** In this repo's `.refmatrix/.refmatrix_ignore` (runtime state,
   not committed): remove the `CLAUDE.md` line; keep `.claude`; add `!.claude/PROJECT_PROFILE.md`.
   Applied by the lead after merge + deploy, announced first, with a backup of the file; the
   daemon's normal sync ingests the two docs. {#r4}
5. **R5 A committed recount.** `scripts/check-rel-landing.py <catalog> <roots…>` prints the
   evidence-based recount (authored wikilink `rel:` lines vs `linkage_evidence` rows at the same
   file and line; categories: landed, landed at another line, file not ingested, target
   unresolved — with the unresolved grouped by target doc). Read-only on the catalog path it is
   given; counts and paths only. Not a gate (line drift is benign). {#r5}

## Acceptance criteria {#acceptance}

1. **AC-1 (R1).** `should_ignore` on a throwaway tree: with `.claude` in the spec and
   `!.claude/PROJECT_PROFILE.md`, the profile is NOT ignored and `.claude/agents/x.md` IS;
   `CLAUDE.md` removed from the spec is not ignored; `!node_modules/x.md` stays ignored; a `!dir`
   line is reported. Mutations: drop the hidden-dir override; let re-include beat
   `INGEST_IGNORE_DIRS`. {#ac-1}
2. **AC-2 (R1, R2).** End to end on a throwaway store (short `mkdtemp` root): a repo whose
   CLAUDE.md has `{#no-silent-failures}` and a doc with `rel: contradicts ->
   [[claude#no-silent-failures]]` — with the re-include config, the ingest creates the
   `claude#no-silent-failures` node and one `contradicts` edge with its evidence row; with the old
   config, no node and the line counted unresolved. Same for a `.claude/PROJECT_PROFILE.md` anchor.
   Run through the watcher/sync path as well as `ingest-gmd`. {#ac-2}
3. **AC-3 (R2).** A path that BECOMES re-included after an ingest is picked up by the next sync; a
   path that becomes ignored is purged (existing behaviour, re-asserted). {#ac-3}
4. **AC-4 (R3).** The parity script exits non-zero on a fixture repo whose lint scope contains a
   GMD doc the ignore spec excludes, naming the file and the rule; exits 0 when re-included; and on
   this repo after R4's config is mirrored into the fixture. {#ac-4}
5. **AC-5 (R5).** The recount script on a fixture catalog reproduces hand-computed categories
   exactly. {#ac-5}
6. **AC-6 (live, after deploy + R4).** `check-rel-landing.py` on a fresh read-only copy of this
   store: the `claude` and `project-profile` unresolved groups fall from 209 / 38 to 0 (anchors that
   no longer exist in the docs are listed, not counted as fixed). Recorded in the implementation
   summary. {#ac-6}

## Fleet {#fleet}

Every fleet store's `.refmatrix_ignore` carries the same `.claude` / `CLAUDE.md` lines (cliquedb,
viascope, cliquet, atldb checked 2026-11-13). Changing them is a fleet action and the user's call;
this task ships the mechanism (R1-R3) and a recommendation, not the edits.
**Decided (user, Q2): after bug-216 deploys, the `CLAUDE.md` ignore line is removed fleet-wide** (announced
first, each store's ignore file backed up), and each store's recount is reported.

## Out of scope {#out-of-scope}

- bug-218 (reinforcement reads `reinforces` edges reversed) — its own fix.
- The 69 other unresolved targets (bsd-0661-e2e-memory-bridge ×13, bsd-impressions anchors ×9,
  impl-remedy ids, …): listed by AC-6's run for a follow-up, not fixed here.
- Ingesting `workflow/past_handoffs/` (66 lines): operational content, excluded by rule.

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/ingest.py` | `IgnoreSpec` re-include lines; `should_ignore` applies them over the spec and the hidden-dir rule, never over `INGEST_IGNORE_DIRS` |
| `src/refmatrix/sync.py`, `src/refmatrix/daemon.py` (watcher), `src/refmatrix/ingest_gmd.py` (walk) | route through `should_ignore` where a walk keeps its own rule |
| `scripts/check-gmd-parity.py` | the scope-parity check (R3) |
| `scripts/check-rel-landing.py` (new) | R5 |
| `docs/INTEGRATION.md` (ignore-file section) | document `!path` |

## Revision 2 (2026-11-13, after ch-bsd `bsd-215m1`) {#rev-2}

`bsd-215m1` showed the lead's first diagnosis was incomplete. The 66.9% the probe reported is real:
of 5,431 `rel:` evidence rows in refmatrix, 3,662 (67.4%) land on a target with NO path, and at least
1,909 of those cite a doc that IS ingested under exactly that id. Every such target doc has two
entities of the same name — a `doc` with a path and a `concept` with none — and a bare doc-id link
binds the concept. Anchored links (`[[doc#id]]`) bind correctly. The rule-doc exclusion (R1-R4) is a
real but much smaller part. {#rev-2-finding}

rel: derives-from -> [[bsd-215m1-measurements-r1#b1]]

**Mechanism (code, `ingest_gmd._resolve_target_eid`):** after the batch dict, it tries
`store.get_entity(kind, name)` for `("concept", "doc", "memory")` in that order. Concept-first is
right for an anchor (`doc#id` is a concept node) and wrong for a bare doc id: a same-named concept
(minted by the plain-wikilink `mentions` branch, `store.add_concept(target_doc)`, or by extraction)
wins over the doc. The edge then reaches only other docs citing the same id, so 2-hop GMD metapaths
measured co-citation, not item → cited doc. {#rev-2-mechanism}

6. **R6 Bare doc-id targets bind the doc.** For a target with no `#anchor`, resolution order is
   `doc`, `memory`, then `concept` (a concept only when no doc or memory of that name exists — a
   GMD id that is only a concept). Anchored targets keep concept-first. The batch dict
   (`eid_by_name`) obeys the same rule (it must not cache a concept id under a bare doc id that a
   later file in the batch defines as a doc). Applies to `rel:` edges and to plain wikilinks'
   resolution step alike. {#r6}
7. **R7 Repair existing edges.** A re-ingest of a GMD doc rewrites its `rel:` edges to the bound
   doc and removes its rows to the path-less same-named concept (evidence rows too). After deploy
   the lead runs a forced GMD re-ingest of `docs/`, `workflow/` and the memory bridge (announced,
   backed up, through the daemon), then the recount. No direct DB surgery. {#r7}
8. **R8 The recount classifies binding.** `check-rel-landing.py` (R5) counts a line as landed only when
   its `linkage_evidence` row joins a LIVE `entity_links` row whose two entities both still exist
   (an evidence row without one is STALE, bug-219); it then classifies every landed row by its target: doc / memory with a path, anchor node with a path, path-less concept that
   shares its name with an ingested doc (MISBOUND), other path-less concept. {#r8}

**Acceptance (rev 2):**

- **AC-7 (R6).** Throwaway store: doc A carries `rel: derives-from -> [[b-doc]]` and a plain
  `[[b-doc]]` mention; doc B has `id: b-doc`. Ingest A before B, B before A, and both in one batch:
  in every order the `derives-from` row's `entity_id` is B's `doc` entity (kind `doc`, B's path),
  never a path-less concept. An anchored `[[b-doc#sec]]` still binds B's `sec` node. A memory
  target (`--as-memory`) binds the memory. Mutations: restore concept-first for bare ids; let the
  batch dict cache the concept. {#ac-7}
- **AC-8 (R7).** A store holding a misbound row (built at HEAD), re-ingested with the fix: the row
  to the path-less concept and its evidence are gone; the row to B's doc exists. {#ac-8}
- **AC-9 (R8).** On a fixture catalog the recount's binding classes equal hand-computed values,
  including a MISBOUND row. {#ac-9}
- **AC-6 (live) amended:** after the forced re-ingest, MISBOUND rows fall to 0 (or each remaining
  one is listed with why), and the rule-doc groups fall from 209 / 38 to 0. {#ac-6-rev}

Out of scope stays as written; the reinforcement direction is bug-218.

## Revision 3 (2026-11-13, user decision: a `denotes` link replaces the forced re-ingest) {#rev-3}

The user asked whether the path-less concept could simply be linked to its doc, then accepted the
lead's recommendation: keep R6 (new edges bind the doc directly) AND add the link, which replaces
R7's forced re-ingest as the repair for existing edges and as a safety net for every producer that
mints a same-named concept. {#rev-3-decision}

7. **R7 (replaced) `denotes` links.** A new linkage `denotes` (concept → the doc or memory entity
   whose GMD id equals the concept's name, including the concept's `same_as` variants). (a) A
   one-time derive op, run through the daemon (`_op_*`, announced, backed up), adds the link for
   every existing path-less concept whose name is an ingested doc or memory id; idempotent;
   counted and printed. (b) GMD ingest maintains it: ingesting a doc or memory with id X links
   every concept named X (and its variants) to it; purging the doc removes the links. (c) A concept
   name matching two targets (doc and memory) links both and is counted. `same_as` is NOT used:
   the typed-edge walk excludes it by design (`store.py` `_expand_cfg` docstring: variant
   aliasing, not a relation). {#r7-denotes}
9. **R9 Walkers treat `denotes` as transparent.** The typed-edge candidate expansion
   (`store.py` ~5660), `rmx neighbors`, `build_context`'s degree walk and PageRank's edge set
   follow `denotes` as a zero-cost hop (no decay, not counted as a hop). PageRank folds a
   concept's typed in-edges onto its `denotes` target. {#r9}

**Acceptance (rev 3)** — AC-8 is replaced:

- **AC-8 (R7, replaced).** A store built at HEAD with a misbound `derives-from` row to a path-less
  concept: after the derive op, `denotes` links that concept to the doc; the original row is
  untouched; a second run adds nothing. A doc ingested AFTER the concept exists gets the link at
  ingest; purging the doc removes it. Mutations: link via `same_as`; skip the variants. {#ac-8-rev3}
- **AC-10 (R9).** From doc A whose only edge to doc B is through a misbound concept, the expansion
  walk with `RMX_EXPAND_HOPS=1` reaches B; `rmx neighbors A` lists B; PageRank gives B the in-edge.
  Mutation: the walk treats `denotes` as a counted, decayed hop → B falls out at hops = 1. {#ac-10}
- **AC-6 (live) amended again:** after deploy, run the derive op (announced, backed up); the recount
  (R8) reports misbound rows that now reach a doc via `denotes` as BOUND-VIA-DENOTES, and rows
  reaching nothing fall to the unresolved residue; the rule-doc groups fall to 0 after R4. {#ac-6-rev3}

**Contracts confirmed (lead, 2026-11-13, from `red-216` rev 2/3 RED `4c28cbb`):** the derive op is
`OPS["denotes_link"]` returning `{"added": n}`; `denotes` is stored like `rel:` edges (concept side =
the concept, entity side = the doc) and covers the concept's `same_as` group (`b-doc`, `b_doc`,
`b doc`); the recount's `--json` adds `stale` and `binding` {`doc_or_memory`, `anchor_node`,
`misbound`, `bound_via_denotes`, `other_concept`} with `sum(binding) == landed` and `authored =
landed + landed_other_line + stale + file_not_ingested + target_unresolved`; AC-10 observes the walk
via `store.content_rank`, neighbours via `graphread.neighbors_payload(…, depth=1)`, PageRank via
`pagerank.build_adjacency`. **Finding:** a GMD doc whose TITLE spells its hyphenated id mints the
same-named path-less concept by itself (title terms) — a second producer of misbound concepts;
R7's `denotes` link covers it, and the live recount (AC-6) reports how many concepts came from
titles. {#rev-3-contracts}

## Revision 4 (2026-11-13, lead decisions on red-216's RED ambiguities) {#rev-4}

`red-216` committed RED for AC-1..AC-5 (`a08d80b`, `05628d2`; 40 failed, 18 guards pass; a scratch
reference implementation satisfies all 58). Its ambiguities, decided as the user would:

10. **R10 Pending references re-resolve on ingest.** GMD ingest skips unchanged files (content hash;
    sync on mtime) and nothing retries a dangling `rel:` target when it later appears, so R4 alone
    leaves the 247 rule-doc lines unresolved. Every unresolved `rel:` target is recorded as pending
    (source entity, verb, target ref, file, line); ingesting a doc, memory or anchor whose name
    matches a pending target resolves those edges (with evidence) and clears them. Same hook point
    as R7's `denotes` maintenance ("on ingest of X"). Counted and printed; a pending row whose
    source is purged is removed with it. No forced re-ingest. {#r10}
11. **R11 Built-in include for the rule docs.** Precedence (`INGEST_IGNORE_DIRS` always wins — R1): an explicit
    `!path` line, then an explicit ignore pattern, then a BUILT-IN include of `CLAUDE.md` at the root and
    `.claude/PROJECT_PROFILE.md` when either carries GMD frontmatter, then the built-in
    hidden-directory and `INGEST_IGNORE_DIRS` rules. Fresh clones and CI therefore pass R3's gate
    with no ignore file; a store whose ignore file lists `CLAUDE.md` (the fleet today) keeps
    excluding it until that line is removed (the user's fleet decision). {#r11}
12. **R12 One ignore list.** `watch.py`'s private `IGNORE_DIRS` additions (`__pycache__`, `dist`,
    `build`) move into `INGEST_IGNORE_DIRS`; `watch.py` keeps no list of its own (R2). {#r12}

Accepted as RED wrote them: `!dir` is reported on stderr once per spec load; the hidden-dir
exclusion message names "hidden" and a spec exclusion quotes its pattern; the parity script reads
the spec from the scanned files' project root; `check-rel-landing.py --json` keys
(`authored, landed, landed_other_line, file_not_ingested, target_unresolved,
unresolved_by_target_doc`, plus R8's binding classes); "counted unresolved" is observed through
`ingest-gmd`'s report. `ingest-gmd <subdir>` finds the project root by walking up to `.refmatrix/`
(tested). {#rev-4-accepted}

- **AC-11 (R10).** Ingest a doc citing `[[b-doc]]` before b-doc exists → the line is pending;
  ingest b-doc → the edge exists with evidence and the pending row is gone; purge the citer → its
  pending rows go. Mutation: never clear pending rows. {#ac-11}
- **AC-12 (R11).** No ignore file: CLAUDE.md and the profile (with GMD frontmatter) are ingested;
  a profile without frontmatter stays out (hidden-dir rule); a root CLAUDE.md without frontmatter
  is ingested like any root `.md` (no new exclusion — lead, 2026-11-13); an explicit `CLAUDE.md` ignore line excludes it; `!` beats an
  explicit ignore. R3's gate exits 0 on a fixture with no ignore file. {#ac-12}
- **AC-13 (R12).** A `dist/x.md` is ignored by every walker; `watch.py` defines no ignore list. {#ac-13}

## Revision 5 (2026-11-13, spec-t4 finding; lead decision: replay fidelity) {#rev-5}

The GREEN (`2fc5554`) added GMD-path writes that facts.log never records: `clear_rel_evidence`
deletes `rel:` evidence with no event, and `pending_refs` rows are never logged. Both replay paths
append every `evidence` event, so after a changed doc is re-ingested the catalog holds one evidence
row per `rel:` line and a replay holds the old ones too; and a replay loses every pending row.
Declaring pending refs "outside replay" was rejected: a rebuild would silently lose dangling refs
that should bind later (no silent loss on memory paths; decay never loses knowledge). {#rev-5-why}

rel: reinforces -> [[feedback_decay_never_loses_knowledge]]

13. **R13 Replay fidelity for bug-216's writes.** Every GMD-path write bug-216 adds is a facts.log
    event that `rebuild_index_from_log` — the ONE replay path — applies (amended 2026-11-13: the
    incremental `apply_log_delta` / `_apply_one_event` / `_apply_event_body` is RETIRED by d9bu,
    `workflow/plan-review-2026-10-14.md` row d9bu, CONFIRMED under d9ck: no caller in `src/`, 16.6
    owns its deletion, so R13 adds NO branch to it): a per-file `rel:`-evidence-clear event, and
    pending-ref add / delete / per-file clear events, named by entity kind and name (never ids),
    partition-qualified, applied in log order relative to `evidence` events. Old logs without
    these events still replay as before. The `pending_refs` schema comment ("not replayed from
    facts.log") is corrected with it. {#r13}

- **AC-14 (R13).** Throwaway store, facts.log on: ingest v1 of a doc with two `rel:` lines (one to
  an existing target, one to a missing target), then v2 with changed `rel:` lines (a verb change,
  a moved line, a second missing target). A FRESH catalog rebuilt from a copy of the log by
  `rebuild_index_from_log` (only; d9bu, see #r13) holds the same `linkage_evidence`
  rows (by names, as a multiset: no duplicates) and the same `pending_refs` rows as the source
  catalog. Then the missing target is ingested: the pending ref binds (edge + evidence, row gone)
  identically in the catalog and the rebuild. Guard: a log holding only the pre-R13 ops still
  replays one evidence row per `evidence` event. Mutations, each failing: drop the clear event;
  drop the pending events; the rebuild ignores them.
  Test: `tests/test_bug216_replay_fidelity.py`. {#ac-14}

## Revision 6 (2026-11-13, green-216 #green-flags 5 and 6 + an R13 gap; lead decisions) {#rev-6}

Three items before merge, one revision. {#rev-6-lead}

- **R13 covers `purge_entity` too.** It deletes the source's `pending_refs` rows without an event
  of its own; its `tombstone` event exists, and the rebuild must honour it for the source's
  pending rows (rebuild only, d9bu — see #r13). R13's full list of writes: `clear_rel_evidence`,
  `add_pending_ref`, `delete_pending_ref`, `clear_pending_refs_for_file`, and `purge_entity`'s
  pending delete. AC-14 adds: two citers with pending refs, one purged; the rebuild holds the
  survivor's row and none of the purged citer's, with no row left on a dead source. The rebuild
  never materializes a citer that did not survive its tombstone, so no mutation of the replay
  itself can leave the purged citer's rows; the test pins the outcome (and fails while pending
  rows are not logged at all). {#r13-purge}
14. **R14 The `denotes` derive is a verb** (flag 5; ".claude/PROJECT_PROFILE.md" #constraints:
    every capability an agent can call is a verb first, CLI and MCP expose it). Verb
    `rmx_derive_denotes` (`verbs.derive_denotes(root, *, partition=None, timeout=None)`), CLI
    twin `rmx derive denotes` (partition via `rmx -p`, as `memory compile`), MCP tool generated
    from the verb; all return the op's counts `{added, concepts, targets, multi_target}`, the CLI
    printing each as `key=value`. Daemon down: the CLI exits non-zero with the reason on stderr
    and writes nothing; the MCP tool returns an `error`. {#r14}
15. **R6b Prestage names its exclusions in the result** (flag 6, #no-silent-failures). The
    `prestage_hashes` op and the CLI's `ingest-gmd --prestage` (both branches) pass `ignored=` to
    the walk as ingest does; the op's result carries `ignored` (count) and `ignored_paths`
    (names), and the CLI prints `render_ignored_line` on stdout. {#r6b}

rel: amends -> [[#r13]]
rel: amends -> [[#r2]]

- **AC-15 (R14).** `rmx_derive_denotes` is a verb with CLI twin `("derive", "denotes")`, wiring
  `calls`, and an MCP tool; `tests/test_verb_parity.py` covers it (PAIRING + CLI_INVOKE rows). On
  a store with one doc `b-doc` and the concept `b-doc` (3 spellings) the verb, the CLI and the
  MCP tool return / print added 3, concepts 3, targets 1, multi_target 0; a second run adds 0.
  Daemon down: CLI non-zero, stderr names the daemon, no link written; MCP returns an error.
  Mutations: the CLI swallows the error; the CLI bypasses the verb; the verb drops counts.
  Test: `tests/test_bug216_surfaces.py`. {#ac-15}
- **AC-16 (R6b).** A memdir with `.hidden/y.md`, prestaged (doc walk) through the op and through
  the CLI (daemon down and daemon up): the result / stdout counts 1 and names the path. Guard:
  `--as-memory` prestage still names it in `walk_skipped`. Mutations: the op leaves it on
  stderr; the CLI does not print it. Test: `tests/test_bug216_surfaces.py`. {#ac-16}
- **R2 base (spec-t56).** The segment rules (hidden-dir, `INGEST_IGNORE_DIRS`) apply only BELOW
  the project root: `watch.is_relevant` and `sync._sync_one` called `should_ignore(p, root)` on
  absolute paths with no `base`, so a project under `<x>/.hidden/` or `<x>/build/` (R12 put
  `build`, `dist`, `__pycache__` in the list) synced nothing — the class `ingest-gmd <dir>`'s
  `base=` fixed. A `build/` dir INSIDE the project is still ignored. {#r2-base}
- **AC-17 (R2 base).** Projects at `<mkdtemp>/.hidden/proj` and `<mkdtemp>/build/proj`, each with
  `docs/d.md` and in-project `build/x.md` / `dist/y.md`: the watcher, sync, `ingest_path` and
  `ingest-gmd` routes land `docs/d.md` and not the in-project ignore dirs; `watch.is_relevant`
  agrees. Mutations: drop `base=` (absolute parts); skip the segment rules under a root.
  Test: `tests/test_bug216_watch_base.py`. {#ac-17}
