---
gmd: "0.1"
id: task-bug216-rule-docs-in-graph
title: "Task bug-216: the project's rule docs (CLAUDE.md, the project profile) reach the graph, and the gate fails when lint scope and ingest scope disagree"
tags: [task, bug-216, gmd, ingest, ignore, linkages, graph]
metadata:
  node_type: task
  status: approved
  created: 2026-11-13
  updated: 2026-11-13
---

# Task bug-216: the rule docs reach the graph {#root}

> Status: Approved by the lead on the user's direction (2026-11-13: "lets fix 216"); decisions
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
