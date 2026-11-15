---
gmd: "0.1"
id: pop-2026-11-13-contra-d
title: "contra-d: grep surface + graph integrity (T5, T6)   (files read: 19)"
tags: [plan-review, pop-2026-11-13, report]
metadata:
  node_type: report
  created: 2026-11-13
---

## contra-d: grep surface + graph integrity (T5, T6)   (files read: 19) {#root}

Files read: the brief, the lead's draft (re-read after it changed on disk), the bug-216 spec on dev master and on the clone branch (they are identical), plan-16 and tasks 16.1 and 16.5, tasks 25.4 and 25.5, plan-22 and its dependency section, ADR-0004, the `#t10`/`#t11` wave lists in plan-review-2026-10-14, the POP rows for plans 13, 16, 20, 22 and 25, the bug rows listed in the brief, the headers of plans 13 and 20, the bug-185 spec (its R2), and the grep rewrite hooks. The clone and the repo were not modified.

### CD-1 [K1/K6] 25.4 and 25.5 build BRE translation into the grep code that 16.5 deletes, and nothing reconciles the two plans
- side A: `workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.4-grep-bre-translation.md:94` "b1 | Translate BRE → Python `re` and take the regex path, rather than delegating every BRE | the index, the stdin filter and the fallback keep working and learning". Its files table (`:226` onward) changes `_grep_stdin`, `_grep_delegate` and `_grep_rg_fallback`.
- side A': `task-25.5-substring-bre-metas.md:64` "**R2 Drop-in legs read BRE.** On the explicit-path legs (files or directories) and the stdin leg … translated by `bre_to_py`".
- side B: `workflow/plans/plan-16-invisible-grep-shim-tasks/task-16.5-explicit-grep-hands-off.md:170` "**R1. Named paths: exec the real grep**". `:181-182` "**R2. Piped stdin: exec the real grep …** `_grep_stdin` and `_grep_stdin_addendum` are DELETED". `:190` "The pattern has no BRE metacharacter … [or the call goes to the floor]". `:222` "**BRE concepts are not read by `rmx grep`**". `:230` "Deleted: … `_grep_delegate`, `_grep_stdin` …". `:301` "`fixed by task-16.5 R3`: bug-081".
- side B': `plan-16-invisible-grep-shim.md:478` "Task 16.5 now brings them IN scope: named-path and pipe calls exec the real grep, BRE patterns route to the grep floor".
- More conflicts:
  - 25.4 AC-3 expects a path-less `rmx grep "alpha\|beta"` to answer from the index and learn `query/alpha\|beta`. 16.5 R3 sends that pattern to the floor.
  - 25.4 AC-7 tests `rmxgrep` "in rich mode". `plan-16:115` says "Delete the rich branch and `RMXGREP_MODE`".
  - 25.4 cross-references plan-16 only by a bare `rel: related-to` (`:35`). Plan-16 never mentions 25.4, 25.5, bug-167 or bug-174. None of the four plan-25 spec-review ledgers mention plan-16.
- The draft frames it the wrong way: `workflow/plan-review-2026-11-13.md:83-85` (F6) calls these "one contract: `rmx grep` is a faithful drop-in". plan-16 `#d-1` (`:228`) says the opposite: grep is now observed, not answered, and the index is asked by name.
- why it matters: T5 "plan-16 with 25.4/25.5" (`plan-review-2026-11-13.md:166`) would build a translator for three legs, plus a test file and a superseded-test rename, and 16.5 would then delete them. bug-081, bug-167 and bug-174 each have two fixes planned.
- proposed resolution: 16.5 wins on the named-path and stdin legs, because it is the user's decision of 2026-10-07 (`plan-16:158`). 25.5 R2 and the file/stdin half of 25.4 drop out. What survives is the path-less index leg (25.5 R4's measured band). It must be reconciled with 16.5 R3 condition 1, which floors every BRE meta. That is a user decision: translate on the index leg, or keep the floor. If 0.83.0 needs bug-167 fixed before plan-16 lands, ship it only as an interim fix, with an explicit "deleted by 16.5" note.

### CD-2 [K3] The draft queue puts plan-22 before both things it depends on (16.6 and 17.1)
- side A: `workflow/plan-review-2026-11-13.md:165-167` "7. T6 — bug-218, bug-219, bug-186, then plan-22. / 8. T5 — plan-16 with 25.4/25.5. / 9. T4 tail — plan-17, plan-18."
- side B: `workflow/plans/plan-22-audited-removal-and-repair.md:206` "22.1a needs: 23.0 (sandbox), 16.6's Wave-1 slice". `:208` "22.2 needs: 22.1a …, 16.6's Wave-1 slice". `:231` "22.2 R4 calls 17.1's `vectors_restore(..., id_map=)` (d9z)". `:200` "17.1 lands before 22.2's restore is built (d9z)". Its edges are `rel: depends-on -> [[task-16.6-learned-row-validation]]` and `[[task-16.1-argv-faithful-learner]]` (`:227-228`).
- side C (order of record): `workflow/plan-review-2026-10-14.md:480` "After 23.1: 17.1 → 17.2 → 17.4; 16.6 slice → 22.1a → 22.2 → (22.5 ∥ 22.6) → 22.3". The draft says it amends `#t11-folded-waves` (`:19`) but does not say it is reversing this edge.
- why it matters: queue item 7 cannot start plan-22. 22.1a has no sidecar to read, and 22.2 has no `vectors_restore` to call.
- proposed resolution: split T5. 16.6's Wave-1 slice is a write-path and graph task with no dependency on 16.1. Queue it right after T4's 23.1, ahead of plan-22, with 17.1 also ahead of 22.2. Only 16.1 → 16.2 ∥ 16.3 → 16.5 → 16.4 (and 22.1) stay in T5's later slot.

### CD-3 [K6] Five of the bugs the draft assigns to T5/T6 already have an owner in another track
- side A: `workflow/plan-review-2026-11-13.md:124` T5 holds "bugs 081, 086, 102, 106, 107, 167, 174, 180". `:125` T6 holds "bug-218, bug-219, bug-186, bug-119-121, bug-124; plan-22".
- side B, the registry and specs:

  | bug | draft track | owner per registry/spec | owner's track | quote |
  |---|---|---|---|---|
  | bug-086 | T5 | task 22.3 | T6 | `task-22.3-bug-086-global-repair.md:3`; 16.6 `:273` "plan-22 task 22.3 is the only one" |
  | bug-106 | T5 | task 23.1 R3.5 | T4 | `task-23.1-queue-and-drain.md:1003` "Learn's evidence write is insert-if-absent (nb23-2, bug-106 …)" |
  | bug-107 | T5 | task 22.6 R4 | T6 | `plan-22:117` "a BUG (bug-107) … 22.6 R4" |
  | bug-186 | T6 (queue item 7) | bug-185 R6 | T4 (queue item 3) | `bug_registry.md:237` "planned, owner [[task-bug185-bulk-gmd-ingest#r6]] … fixed IN bug-185" |
  | bug-120 | T6 | 16.6 R1f | T5 | `bug_registry.md:173` "task 16.6 owns the deletion"; `plan-22:265` d-29 "deleted by 16.6 R1f … bug-120 closes by removal" |

- Related stale row: `bug_registry.md:134` bug-081 still says "The explicit `rmx grep` still needs BRE → ERE translation", which 16.5 R8 (`:301`) supersedes.
- why it matters: under P5 rule 2 ("new bugs enter a track by tag"), each of these would be scheduled twice.
- proposed resolution: track membership follows the owning task. T5 = 081, 102, 167, 174, 180 (plus 120 through 16.6). T6 = 086, 107, 119, 121, 124, 218, 219. T4 = 106, 186. Refresh bug-081's fix column to point at 16.5 R3.

### CD-4 [K1] The approved bug-185 spec pins the concept-first resolution that bug-216 R6 reverses
- side A: `workflow/plans/task-bug185-bulk-gmd-ingest.md:93` "**R2 Pass 2 is written in bulk, in a pinned order that reproduces HEAD's resolution.**" `:103` "in HEAD's precedence `concept`, `doc`, `memory`, at most one statement per kind. This replaces `_resolve_target_eid`'s per-target `get_entity` calls."
- side B: `workflow/plans/task-bug216-rule-docs-in-graph.md:148-153` "**R6 Bare doc-id targets bind the doc.** For a target with no `#anchor`, resolution order is `doc`, `memory`, then `concept` … The batch dict (`eid_by_name`) obeys the same rule". Rev 3 and rev 4 also add pass-2 writes that bug-185 does not batch: `denotes` maintenance (R7, `:187-195`) and pending-reference resolution (R10, `:231-237`).
- why it matters: bug-216 ships in T1 and bug-185 builds next in T4 (queue item 3). An implementer who follows bug-185's text literally reintroduces the misbinding (67.4% of `rel:` rows land on a target with no path). Its RED would also assert concept-first.
- proposed resolution: bug-216 wins (newer, user-directed). Before bug-185 builds, revise R2.2 to "R6's precedence (doc-first for a bare id, concept-first for an anchor)" and add R7/R10's writes to its batching scope.

### CD-5 [K1] 16.1's "one predicate" is a second home for the ignore rule that bug-216 consolidates
- side A: `task-16.1-argv-faithful-learner.md:272-276` "`src/refmatrix/corpus.py` (new) holds the watcher's predicate … `is_relevant`, `IGNORE_DIRS`, `SUPPORTED_EXTS` (from `watch.py`) … The predicate is the WATCHER's". `:238` "grep: `--exclude-dir='.[A-Za-z0-9_-]*'`" (every hidden dir). `:254` "This is faithful by construction: it removes only files R3 would discard."
- side B: `task-bug216-rule-docs-in-graph.md:61-64` "**R2 One predicate.** Every walk … goes through `should_ignore(p, root)`; no walk keeps a private copy". `:244-245` "**R12 One ignore list.** `watch.py`'s private `IGNORE_DIRS` … move into `INGEST_IGNORE_DIRS`; `watch.py` keeps no list of its own". `:55-58` re-includes override "the built-in hidden-directory rule".
- why it matters: once bug-216 lands, `watch.IGNORE_DIRS` no longer exists. Also, `.claude/PROJECT_PROFILE.md` becomes part of the corpus, but 16.1's re-run prunes every dot-dir. That would quietly drop recall on the re-included rule docs, and 16.1's "faithful by construction" would no longer be true.
- proposed resolution: bug-216 wins. Revise 16.1 R1b/R3 before T5 builds: `corpus.is_relevant` delegates to `should_ignore`, and the hidden-dir prune keeps the spec's `!path` re-includes (for example by adding the re-included files as explicit operands).

### CD-6 [K2/K6] bug-219's fix deletes evidence on purge, outside the removal path ADR-0004 set and plan-22 owns
- side A: `bug_registry.md:270` (bug-219 fix) "purge evidence with the entity / edge it belongs to (one helper on every purge path)".
- side B: `docs/adr/0004-unified-location-space-index.md:377` "**Derived-index cleanup** is NOT knowledge removal … allowed outside plan-22 only with a manifest written before the change". `:388` "`vacuum`'s orphan-evidence delete is derived cleanup with a manifest and a `facts.log` event".
- side C: `plan-22-audited-removal-and-repair.md:103` "`dangling-evidence` (`linkage_evidence` rows of a live entity whose concept is dead), the owners of … what every purge leaves behind". `:257` d-21 "audited and removed as d-20".
- side D: `bug_registry.md:160` bug-107 describes this exact pattern as a defect: "`vacuum` then deletes the orphaned `linkage_evidence` with no log event".
- why it matters: queue item 7 runs bug-219 before plan-22. A purge-path helper without a manifest repeats bug-107. It could also remove learned grep evidence, which plan-22 classes as knowledge (`:96-98`).
- proposed resolution: bug-219 becomes the census input for plan-22's `dangling-link` and `dangling-evidence` classes, not a standalone delete. One gap is real: 7,752 rows have a dead entity side, and plan-22's class covers only a dead concept side. That widening is a plan-22 (22.1a) amendment. Only bug-219's "counts join a live edge" half (already bug-216 R8) ships alone.

### CD-7 [K2] bug-216's `denotes` link adds an alias-like relation and a ranking change without the gates ADR-0004 records
- side A: `task-bug216-rule-docs-in-graph.md:196-199` "**R9 Walkers treat `denotes` as transparent.** … follow `denotes` as a zero-cost hop (no decay, not counted as a hop). PageRank folds a concept's typed in-edges onto its `denotes` target."
- side B: `docs/adr/0004-unified-location-space-index.md:288` "Traversal depth and cumulative-weight ordering are opt-in per relation type, after measurement". `:297` "The per-type prior starts flat (1.0) and moves only on a per-type evaluation, so a hand-set weight cannot become an untested ranking change". `:339-341` "merges target the term-space alias map …, not new `same_as` rows".
- The bug-216 spec never cites ADR-0004. R7 avoids `same_as` by name (`:193-195`) but builds the same thing under a new name.
- why it matters: PageRank and expansion results change for every misbound concept. The handhold experiment's arm A is gated on bug-216 being live (`plan-review-2026-11-13.md:162`), so an unmeasured ranking change would flow into that baseline.
- proposed resolution: user or ch-architect decision. Either record that `denotes` is a binding repair, not a merge, as an ADR-0004 decision-log line, or ship R7 (the link) without R9's PageRank fold until a per-type evaluation is run. R6 (correct binding for new edges) is unaffected.

### CD-8 [K5] 25.4 and 25.5 rest on a live rewrite that has been off since 2026-10-15
- side A: `task-25.4-grep-bre-translation.md:45` "at the `rmx grep` CLI, which agents and the PreToolUse rewrite reach directly". `:159` "Production path: the `rmx grep` CLI as the PreToolUse rewrite and the wrappers invoke it". The same claim is at `task-25.5-substring-bre-metas.md:47` and `:148`.
- side B: `plan-16-invisible-grep-shim.md` `#today-learn-off` (about `:71-87`) says "`~/.refmatrix/learn.off` exists … route 1's rewrite (`grep-rewrite-guard.sh`) … exit early". It is verified on disk: `~/.refmatrix/learn.off` is dated Oct 15 00:29, and `~/.claude/hooks/rmxgrep-rewrite.py:117` reads "With learning OFF the rewrite does not happen AT ALL". `.claude/PROJECT_PROFILE.md:79` still says the hook "rewrites bare grep to `rmx grep`; there is no escape".
- why it matters: the "drop-in" urgency for bug-167 and bug-174 assumes every agent grep goes through `rmx grep`. Today only explicit `rmx grep` calls do, and after plan-16 the rewrite feeds the passive shim, never `rmx grep`.
- proposed resolution: correct the premise in 25.4/25.5 when CD-1 is resolved. Fix the profile line too: it becomes graph-visible once bug-216 lands.

### CD-9 [K4] Status lines in this cluster disagree with each other
- **plan-16:** frontmatter `status: approved` (`:7`) and POP `workflow/plan-of-plans.md:39` say "APPROVED 2026-10-15 (d9ck; ch-bsd r13 …)". The body says "**Status:** Drafting (revision round 10 …" (`plan-16:17`), "Awaiting spec review r6 before `approved`" (`:43`), and "Next gate: `@ch-bsd` spec review r6 … then `approved`" (`:248`).
- **plan-22:** frontmatter `approved`, POP `:45` "APPROVED 2026-10-15 (d9cm …)". The body says "**Status:** Drafting — revision round 16" (`plan-22:17`).
- **bug-216 row:** `bug_registry.md:267` says "spec rev 2 adds R6-R8 (… repair by re-ingest …)" and "fleet ignore files are the user's decision". The spec has since replaced re-ingest with `denotes` (rev 3, `:180-195`), added R10-R12 (rev 4), and recorded the user's fleet decision (Q2, `:110-111`).
- **plan-20:** the draft says "plan-13 and plan-20 stay dormant" (`plan-review-2026-11-13.md:131-132`) and lists it under T6 as "plan-20 (dormant)" (`:125`). plan-20 is `status: drafting` (`plan-20:8`). `plan-review-2026-10-14.md` `#t11` says "plan-20 needs approval before Wave 4", and `plan-22:194` says 22.4 is "blocked until … plan-20 supplies the rule". It was never declared dormant.
- proposed resolution: under P1's POP rewrite, fix the body status lines of plans 16 and 22 to match the approvals, refresh bug-216's fix column, and replace "dormant" for plan-20 with what is really true: drafting, waiting on the user's 20.1 labels, and feeding 22.4 and the helix plan.

### Clean areas
- The bug-216 spec on dev master `0d2a270` is byte-identical to the one on the clone branch `task-bug216-rule-docs-in-graph`.
- bug-216's precedence rules are consistent with each other: R1 (`INGEST_IGNORE_DIRS` always wins), R4, R11, and the Q2 fleet decision.
- bug-119's scope was already narrowed to `rebuild_index_from_log` after d9bu retired `apply_log_delta`, so it does not conflict with 16.6 R1f.
- bug-102: owned by 16.5 R4, consistent with the draft putting it in T5.
- There is one verifier for learned rows (16.6 `learned_verify`): plan-16's open item 1 and plan-22's d-11 agree.
- plan-22's dependency on 21.1 R5 is already met (21.1 is `completed`, merged `768084b` and released in 0.80.0), so P3's freeze of 21.2-21.4 does not block it.
- The POP row for plan-22 ("16.6, 23") matches plan-22's own dependency section.
- plan-13 is dormant consistently across its body, POP row 13 and `#t11`.
- plan-16's interim `RMXGREP_MODE=plain` versus the older no-plain-escape memory: plan-16 already carries `rel: amends -> [[feedback_rmxgrep_no_plain_escape]]`, so the conflict is acknowledged.
