---
gmd: "0.1"
id: plan-of-plans
title: "Plan of Plans"
tags: [planning]
metadata:
  node_type: index
---

# Plan of Plans — current state and the queue to mod start {#root}

**The single source of truth for what is next and for the state of every live plan** (the user,
2026-11-15: "the source of truth must be the POP"; [[orchestration#pop-truth]]). Every commit
that changes state updates this file in the same commit. A plan or task file's
`metadata.status` **follows** the row here: where the two differ, this file is right and the
file is corrected ([[#pending-bookkeeping]]). This file holds **current state only**. A finished
plan, task, ruling, decision or question is appended whole to [[pop-finished]] and deleted here
in the same commit. `@ch-gap-master` keeps this current.

**How rows cite evidence.** A sha in code is a commit on `master`. `L<n>` up to L124 is a row of
[[plan-review-2026-11-13#lead]]; L125 on is a row of [[#rulings]]. `D-Q1` to `D-Q7` are the
user's decisions in [[plan-review-2026-11-13#decisions]]. Answered questions are in
[[pop-finished]]. Review documents are evidence; none of them holds state this file lacks.
{#evidence}

## Queue to mod start {#queue}

One ordered list. It is the freeze line's work ([[#freeze]]) in the order the user approved on
2026-11-14 (L104, L106), as amended by L117 (plan-30 after plan-29), L118 (29.4's runner first),
Q28 = a, and L128 and L129 (Q32-Q36 = a). Nothing outside this list is built before the mod
([[#freeze-rule]]). {#queue-lead}

**Lanes.** {#lanes}

- **T, the test lane.** Builds. RED and GREEN are written in parallel littlebig clones; their
  verify runs queue, one test process at a time on this machine. A major release (`0.N.0`)
  gates on one full suite on merged `master`; a minor release (`0.N.x`) gates on the task
  tests, the family and every importer of a changed module ([[orchestration#one-suite]],
  [[orchestration#release]]; L118, L119, L131).
- **P, the planning lane.** Specs, spec reviews, bookkeeping. It runs no tests and never waits
  on T.
- **M, the measurement lane.** Read-only runs on copies and review rounds; no `src/`. One at a
  time beside T.
- **Tracks.** At most two tracks build at once, plus one lane
  ([[plan-review-2026-11-13#p5]]). 29.5 is the exception: it runs alone.

| # | work, in order | lane | waits on | user gate | state | evidence |
|---|---|---|---|---|---|---|
| 1 | **29.4 stage 2:** T0.2 with the reaper and the sandbox roots (bug-170, 168, 127, 229; bug-253's helper, which retires the 18 venv pins) ∥ T0.3 (bug-130, 190, 091, 228, 231; the wall-clock census) ∥ T0.8 (bug-196) | T; three branches in parallel | — (stage 1 merged `a0c7560`) | none | **in progress:** T0.8's RED is accepted (L130) | L48, L121, L122, L130; [[task-29.4-suite-health#fold-stages]] |
| M1 | **T0.6:** plan-7's dense and fused re-run | M | — | none | approved | [[task-t0-suite-trust-sweep#t0-6]] |
| 2 | **29.4 stage 3:** T0.4 (plan-6's gate) → T0.5 (plan-8's gate; it changes an MCP tool, so `/mcp` reconnect at its release) | T | 1 | none | approved | L122: two self-expiring allow-list entries, removed by 29.2 R7; [[task-t0-suite-trust-sweep#t0-4]] |
| 3 | **29.4 stage 4:** the test tiers and the sharded runner, 8 shards | T | 1 (the reaper) | none | approved | L121; the first AC is the live-touch proof ([[task-29.4-suite-health#ac-12]]) |
| 4 | **29.4 stage 5: T0.7** — the clean run on the runner. It is 29.5's baseline and it closes plans 6, 7, 8 and 15. One release point follows | T | 2, 3, M1 | none of its own; a hook-drift stop is cleared only by an install window | approved | [[task-t0-suite-trust-sweep#r7-4]]; [[task-29.4-suite-health#r10]] |
| 5 | **Plan-31, the items that do not wait for plan-29:** 31.5 step 0 first (the full-payload capture runs to 400 prompts, plan-31 D2), then 31.3, 31.4, 31.1 (bug-244, bug-255, bug-258) and then 31.6 (bug-251, bug-257; after 31.1, both edit `ingest_gmd.py`) | T, beside 1-4 | its specs approved (L125) | 31.4 changes the upstream GMD linter and one MEMORY-RULES line (plan-31 D10, decided). Any fleet re-derive or reingest 31.6 needs goes to the user (L125) | **specs written** on `spec-plan31a` and `spec-plan31b`; ch-bsd next; approved on a MEH-only GO | L125, L132; [[#decisions]]; [[plan-31-pre-mod-loose-ends#order]] |
| 6 | **29.1** registry triage: every open row ends `fixed`, `scheduled`, `deferred` or `closed`. A row owned by a post-mod task is `scheduled` to it with the note `post-mod` | P, with a short T run | 4 | none | approved | L117 (`P<n>` tracks); [[task-29.1-registry-triage#root]] |
| 7 | **29.5** split the giant modules: ADR 0006 (layout and layering) first; then the `cli` package; then `Store` as mixins in sibling modules. **Alone:** nothing else is in flight, and it is released alone | T, exclusive | 4, 6 | the merge is a store event (plan-29 D23 = a: export, count, record the loss) and the release is store-changing, so it has its own go | approved | L105, L108, L113, L115; [[task-29.5-split-giant-modules#r9-store-event]] |
| 8 | **29.3** (its query half first) ∥ **29.2** (the mypy gate; R7's normalised derive hash; `rmx derive rehash`) → 29.4f (import-derived families) → **29.6** (citations and pins re-pointed) | T | 7 | 29.2 R7's release is one announced window with two deploys: A, then `derive rehash`; B, then a re-derive of exactly the edited passes. Each has its own go | approved | L108-L111; [[plan-29-code-quality#order]] |
| 9 | **31.2** purge, vacuum and replay agree about learned evidence (bug-107, bug-247, bug-259, bug-260), with 22.6 R4 | T | 7 | the store write for the existing orphaned rows (plan-31 D14) is the lead's, announced and backed up | spec written; ch-bsd judges its two departures (L132) | L132; [[#decisions]]; [[#flags]] F5 |
| 10 | **Plan-30, with G22 and G30:** 30.0 ∥ 30.5 → 30.1 → 30.2 → 30.3 → 30.4 → **G22** (operational content out of the derivations; after release C) → 30.6 (with **G30**, the `denotes` fold evaluation, folded in). Releases A (30.5), B (30.1-30.3), C (30.4) | T | 8 (plan-29 released) | release B: the fleet-wide `pagerank` re-derive in one announced window, backups first (go given, plan-30 D2); 30.3 moves the adjacency caches to a backup directory (D3). G22: each fleet store's re-derive | approved; 30.6's spec is pending | L116, L117; L60-L74, L128; [[plan-30-materialisation#order]]; [[task-dq1-operational-content-out-of-graph]] |
| M2 | **The cross-partition `rel:` probe:** does a project doc's `rel:` to a memory id bind across partitions? One read-only probe; its answer settles 26.5's twin purge | M | — | none | admitted (L128); no spec | L106, L128; [[plan-review-fable-2026-11-14-memory#s10]] |
| 11 | **T2 memory organisation:** 26.5 (with bug-208, 213, 220) → 26.7 → the 26.6 R3 residual → 26.8 → 26.9 ∥ plan-27 (27.0 → 27.1 → 27.2a, 27.2 → 27.3 → 27.4 → 27.5 → 27.6) | T; a second track beside 10 | 8; 26.5 waits on M2 | 26.8: the `--apply` go, and at AC-8 the MEMORY-RULES text and the forget step ([[#decisions]]). 26.9: per-document approval. Plan-27: the 27.2a conversions, the viascope2 archive, cliquedb at its session boundary. The migration start itself is delegated (L78) | approved | L1, L9-L13, L37, L47, L55, L63-L66, L78; [[plan-26-memory-organisation#user-gates]]; [[plan-27-memory-fleet-rollout#user-gates]] |
| M3 | **G32, the m1 r2-lite confirm:** a ch-bsd round over the 21.5 measurement corrections (`4b57796..` the four files' head) | M | — | none | admitted (L128); never run | L36, L54, L128 |
| 12 | **Hook-side items kept before the mod:** 10.3 (the compaction marker); 25.3's STM half (no dependency); 25.2 (built only if its R0 replay passes L34's bands, else not built, L43) → 25.3's helix half (after 25.2 and 10.3) | T | 8; 25.2's R0 waits on M3 | 10.3's new PreCompact entry reaches live stores only through an install window of its own (25.1b's window is post-mod) | approved | L16, L19, L30, L34, L41, L43, L54; [[task-25.2-thin-prompt-gate#r0]] |
| 13 | **T4 bounded writes:** bug-185 → 23.2 → 23.1 (as 23.1b → 23.1a → 23.1c, [[#decisions]]) → 23.3 ∥ 23.5. It adopts bugs 194, 203 and 207. Then **bug-218** R1-R7 (its R0, which confirms the `suspected` row, may run any time after plan-29) | T | 8; 23.5's R9 waits on step 11's 26.6 R3 residual (L1) | bug-185: R9's STOP bands and its index build on every fleet catalog. bug-218: the per-store re-orientation `--apply` (L49) | approved | L1, L3, L4, L31, L46, L50, L52, L57, L62; L49, L69, L74; [[plan-23-bounded-write-harness#merge-order]] |
| 14 | **T3, after 31.5:** 31.5 steps 1-3 (measure each block's use, then cut and tighten) → 21.2 → 21.4 | T | 5's capture; 12 | an install window for 21.4 R4 (the windows its spec names, 10.4's and 16.3's, are post-mod); the user approves 21.4's drafted question set | approved | Q27 = b; L51; [[plan-31-pre-mod-loose-ends#t5]] |
| 15 | **21.5 phase M:** the R12 re-measure on the revised matcher; no `src/` | M | M3; 14 (31.5 feeds it) | the local transcript archive is announced (L53) | approved (rev 4); phase B is frozen | L35, L36, L53, L56; D-Q4; [[task-21.5-tool-used-signal#r14]] |
| 16 | **The plan-24 freshness revision, to approval** — the last pre-mod step. Its evidence is 31.5, 21.5 phase M and 30.6. It records D1 as superseded (D-Q5), moves the tool-event builder into 24.6, adds the 24.8 R5 rows, and re-probes on the current Claude Code | P, then ch-bsd spec rounds | 10, 14, 15; and the tree is final (8, 10) | the user's decisions on what the rounds leave open | not started; plan-24 is `drafting` | L128, L129; [[#flags]]; [[plan-24-mod-transport]] |
| 17 | **Mod start:** 24.0 ∥ 24.1, when plan-24 is approved | T | 16 | — | — | L128 |
| 18 | **After the mod's initial work: re-evaluate every post-mod item** against the mod as built. Each gets keep, re-spec onto the mod's surface, merge or drop, with a one-line reason entered in [[plan-of-plans#rulings]] first. No post-mod item is built before this step | P | the mod's initial work finished | the user's decisions on the verdicts | — | L127, L129; [[plan-of-plans#post-mod]] |

**After the mod's initial work** (not part of this queue): every post-mod item is re-evaluated
against the mod as built (keep, re-spec, merge or drop) before any is built (L127, L129).
{#queue-after}

### What sequences around 29.5 {#queue-quiet}

29.5 needs `cli.py`, `store.py`, `daemon.py` and `verbs.py` quiet. Read from each spec's Files
section. {#queue-quiet-lead}

| group | tasks | rule |
|---|---|---|
| **Free of the four modules:** may run beside plan-29 at any time, 29.5's window included | M lane: T0.6, G32, the `rel:` probe, 25.2's R0 replay (after G32), bug-218's R0. Build: 31.3 (scripts, `lint-gmd.sh`), 31.4 (`tools/gmd/lint.py`, docs), T0.2 (`conftest.py`, scripts), T0.3 (tests, `eval/`), T0.8 (`telemetry.py`), 29.1 (docs and a checker). P lane: plan-31's spec reviews, 30.6's spec, plan-24's amends notes | no ordering against 29.5 |
| **Edit the four modules and are scheduled before 29.5:** merged before its window opens, or held until after it | T0.4 (`cli.py`, `daemon.py`, `store.py`), T0.5 (`cli.py`, `verbs.py`), T0.7 (`daemon.py`), 31.5 step 0 (`cli.py`, `verbs.py`, with `scan.py`, `hooks.py`), 31.1 (`cli.py`, `daemon.py`, with `ingest_gmd.py`), 31.6 (one method in `store.py`, with `ingest_gmd.py`; after 31.1) | all on `master` at step 4's sha, which is 29.5's baseline |
| **Edit the four modules and come after 29.5:** built on the split tree | 29.3, 29.2; 31.2 (`daemon.py`, and `store_removal.py`, which exists only after the split); 30.4 (`store.py`, `daemon.py`); G22 (`cli.py`, `store.py`, `verbs.py`); 26.5, 26.7, the 26.6 R3 residual, 26.9, 27.0; 10.3, 25.2, 25.3; bug-185, 23.1, 23.3, 23.5; bug-218 R1-R7; 21.2, 21.4; 31.5's cut | none starts its RED before 29.5 merges; 29.6 re-points their citations |
| **No `src/` at all** | 30.0, 30.6 with G30, 21.5 phase M, 26.8, 27.1 to 27.6 except 27.0 | live steps and measurements; they wait only on what they measure or roll out |

### Releases {#queue-releases}

Adopted by L135 (lead, 2026-11-15) as the release plan; the kind of each release (major / minor) is restated in its release commit (L131).

One test lane, and a major release (`0.N.0`) costs one full suite of about an hour on merged
`master` (L118, L119, L131). Every task below changes a shared path, so each group is a major
release. The grouping is the fewest gates the fixed points allow; the fixed points are in the
last column. {#queue-releases-lead}

| release | holds | fixed by |
|---|---|---|
| R1 | 29.4 stages 2-5 (T0.2 to T0.8), with plan-31's early items: 31.5 step 0, 31.3, 31.4, 31.1, 31.6 | 29.4 has one release point, after stage 5 ([[task-29.4-suite-health#r10]]). 31.5's capture count starts at this deploy |
| R2 | 29.5, alone | L105: released alone; its merge is a store event |
| R3 | 29.3, 29.2 (deploy A, then deploy B), 29.4f; 29.6 is docs | L107, L109: one announced window, two deploys; the pass-file edits ship with 29.2 R7 |
| R4 | plan-30 release A (30.5), with 31.2 | [[plan-30-materialisation#releases]]; 31.2's store write (plan-31 D14) runs after the deploy, on its own go |
| R5 | plan-30 release B (30.1-30.3), with T2's code: 26.5, 27.0, 26.7, the 26.6 R3 residual | release B's fleet `pagerank` re-derive is one announced window; 26.8's rollout and plan-27's migrations follow as live steps |
| R6 | plan-30 release C (30.4), with 10.3, 25.2, 25.3 and 26.9 | one install window for 10.3's PreCompact entry; bug-182's overruns are re-counted after C (L128) |
| R7 | G22, with T4: bug-185, 23.2, 23.1b, 23.1a, 23.1c, 23.3, 23.5 | G22 is after release C (L128); its per-store re-derives and bug-185's index build each have their own go; 23.5's R9 needs R5's residual (L1) |
| R8 | bug-218 R1-R7, with 31.5's cut, 21.2 and 21.4 | bug-218 needs bug-185 merged; one install window for 21.4 R4; bug-218's re-orientation has its own go |

Eight full-suite gates. 30.6 (with G30), 21.5 phase M and the plan-24 freshness revision ship no
`src/` and need no release. A store-changing step runs one at a time, announced and backed up,
after its release deploys ([[orchestration#release]]). {#queue-releases-body}

### Standing notes on the queue {#queue-notes}

- **Specs are on master as they stand** ([[#freeze-specs]]). A stale citation is reconciled by
  the RED author before the test is written; [[#queue-stale]] lists what is already known.
- **No task that touches `cli.py` or `store.py` is in flight during step 7.** Everything in
  steps 9-15 builds on the post-29.5 tree; 29.6 re-points the specs' line citations once.
- **Rules plan-29 sets for every later task.** Every later write method joins 29.2's writer
  `Protocol`. A broad `except` already owned by an approved spec is allow-listed with that
  task's id, not pulled into 29.3 (bug-223 by bug-218; bug-123 by 18.3; bug-119 by 17.4).
  29.3's query half lands before 29.2's strict `query`. G22's BEFORE and AFTER are both taken
  after 29.3 ([[plan-review-fable-2026-11-14-queue#p29-4]]).
- **G22 changes `consolidate.py`,** so its release is the trigger for plan-29's held rows on
  that file ([[#dormant]]; L110).
- **Standing deploy go** (the user, L106): a plan-29 release whose suite equals the baseline by
  E line deploys with the user told first. A release that changes a store on disk (29.5's merge,
  29.2 R7's two deploys, plan-30 release B, G22's re-derives) is outside it and has its own go
  ([[orchestration#release]]).
- **Install windows are user-gated and batched** where they fall together: 10.3's PreCompact
  entry and 21.4 R4.
- **Delegated starts** (L78): plan-27's migration runs when its own preconditions hold, with the
  user told at the start. Every other user gate in the table stops the queue.
- **bug-182's overruns are re-counted after plan-30 release C** (L128); its fix stays post-mod
  with 25.1b. {#queue-notes-list}

### Known stale points, reconciled at RED {#queue-stale}

From the 2026-11-14 reviews, for the tasks in the queue. The specs were approved on 2026-11-13
at `1cf3b9f`; 0.83.0 and 0.84.0 shipped after. {#queue-stale-lead}

| task | what the RED author reconciles first | evidence |
|---|---|---|
| 26.5 | the reroute's cause comes from `classify_transport_error`, not a second classifier; a `deferred` bridge is "not proven"; a refused tracked catalog counts as `rerouted_failed`; AC-1's "never from the cwd" is false at its own resolver; an MCP `project` naming another store is a `VerbArgsError`; the twin purge re-pends each inbound `rel:` first (M2's answer) | [[plan-review-fable-2026-11-14-memory#s5]], [[plan-review-fable-2026-11-14-memory#s7]], [[plan-review-fable-2026-11-14-memory#s8]], [[plan-review-fable-2026-11-14-memory#s21]], [[plan-review-fable-2026-11-14-memory#s11]], [[plan-review-fable-2026-11-14-memory#s10]] |
| 26.8, 27.6 | "zero errors" passes with nothing bridged when the bridge is deferred; the absence of stale subjects from recall is assertable now; 26.8's baseline is the deployed build | [[plan-review-fable-2026-11-14-memory#s7]], [[plan-review-fable-2026-11-14-memory#s9]], [[plan-review-fable-2026-11-14-memory#s12]] |
| 26.9 | AC-1 is not RED at HEAD: restate it as a guard plus the planted-family measurement | [[plan-review-fable-2026-11-14-memory#s22]] |
| 27.1 | **AC-0 orders a tree walk the user forbade:** start from the known roster and `discover_roots()`; `install-hooks --check` cannot see git hooks (bug-209) | [[plan-review-fable-2026-11-14-memory#b3]], [[plan-review-fable-2026-11-14-memory#s30]] |
| 27.3, 27.4 | 27.3 is half done (the `~/enduris/thiquet` LaunchAgent is already uninstalled); 27.4 starts the daemon before it writes | [[plan-review-fable-2026-11-14-memory#s13]], [[plan-review-fable-2026-11-14-memory#s8]] |
| 25.3 | R8's hub degree must say whether `denotes` rows count | [[plan-review-fable-2026-11-14-memory#s14]] |
| 10.3 | R4 exits non-zero on SessionStart, which drops the command's stdout; its text assumes 25.1b ships in the same window | [[plan-review-fable-2026-11-14-memory#s19]] |
| 21.2, 21.4 | three of 21.2's nine gold files are `cli.py` or `store.py`: re-freeze after 29.5; both take their baseline from one catalog copy made after bug-241 went live (it is live, `4c6a0c6`) and before G22 deploys | [[plan-review-fable-2026-11-14-memory#s31]] |
| bug-185 | the golden is recorded on the post-bug-241 tree; a silent fallback in `ingest_path`'s GMD dispatch is counted and exits non-zero | [[plan-review-fable-2026-11-14-store#bug185-silent-fallback-in-ingest-path]] |
| 23.1 | **R11 rebuilds the promote path bug-212 removed:** `_write_or_local` gains `create=`, no `Store(` in `handoff.py`; R8's merge text is stale after bug-216 and bug-227 | [[plan-review-fable-2026-11-14-store#t231-promote-digest-predates-bug212]] |
| 23.3, 23.5 | 23.3 is stale against 26.2; 23.5 AC-5 omits `pending_refs` | [[plan-review-fable-2026-11-14-store#task233-stale-vs-26-2]], [[plan-review-fable-2026-11-14-store#t235-ac5-omits-pending-refs]] |
| bug-218, G22 | fleet stores are found from the known roster, never by a tree walk | [[plan-review-fable-2026-11-14-store#fleet-list-stale]] |
| G22 | **AC-5 orders a row that is never in the pack;** the `denotes` fold against the exclusion needs a row and an AC; its adjacency edits land on plan-30's rewritten build | [[plan-review-fable-2026-11-14-store#dq1-recall-leg-and-fifth-gate]], [[plan-review-fable-2026-11-14-store#dq1-denotes-fold-vs-exclusion]] |
| G30 (in 30.6) | its precondition names the forced reingest after bug-241 and the recorded recount (done, `4c6a0c6`) | [[plan-review-fable-2026-11-14-store#denotes-eval-precondition-names-the-reingest]] |
| 22.6 R4 (in 31.2) | its `rel:` fixtures and mutations predate `clear_rel_evidence` | [[plan-review-fable-2026-11-14-store#s226-rel-fixtures-predate-rel-evidence-clear]] |
| every spec with an AST pin or a qualified name on `cli.py` / `store.py` | re-proven to fail on its synthetic bypass after 29.5 | [[plan-review-fable-2026-11-14-store#ast-pins-break-under-29-5]] |

## Plans {#plans}

Live plans only: in progress, approved and waiting, dormant, or post-mod. Finished plans (1, 3,
4, 5, 9, 11, 12, 14) are in [[pop-finished]]. The **status** column is the value the plan file's
`metadata.status` carries. **Where** says which queue step holds the remaining work, or that it
is post-mod. {#plans-lead}

| # | plan | status | what remains | where | evidence |
|---|---|---|---|---|---|
| 2 | [[plan-2-hooks-reproducible]] | in-progress | Tasks built. Three riders are open. r9 #s-3 (a write resolves its partition off the lagging snapshot) is 23.5's folded rider. r9 #s-2, #m-4 and r5's rerank-rate rider are 25.1b R16, R17 and R0. The plan closes when all land | #s-3: step 13. The rest: post-mod with 25.1b | D-Q6, L51; [[task-23.5-read-path-and-holder-bounds#w1c-rider]] |
| 6 | [[plan-6-deferrals-docs-benchmark]] | in-progress | Tasks built. Closes when T0.4 lands (the ch-bsd r1 remedy), with two named, self-expiring exceptions | step 2 | D-Q6, L122; [[task-t0-suite-trust-sweep#t0-4]] |
| 7 | [[plan-7-longmemeval]] | in-progress | Tasks built; symbolic results reported. Closes on T0.6 (dense and fused re-run) and T0.7, which re-owns its four deferral rows as "no host plan; backlog" | steps M1, 4; the four rows are post-mod ([[#post-mod]]) | D-Q6, L33, L128; [[task-t0-suite-trust-sweep#t0-6]] |
| 8 | [[plan-8-derived-coverage-notes]] | in-progress | Tasks built. Closes when T0.5 lands (the ch-bsd r5 remedy). Deferral rows 43 and 44 are held with the frozen 19.2 | step 2; the two rows are post-mod with 19.2 ([[#post-mod-rule]]) | D-Q6, L48; [[task-t0-suite-trust-sweep#t0-5]] |
| 10 | [[plan-10-injection-dedup]] | approved | rev 5: names-only dedupe of the per-prompt payloads (Q13), no non-human gate (Q10). 10.3, the compaction marker, is built before the mod (25.3 reads it). The dedupe itself (10.5 the read-back probe, 10.6 presentation, 10.4 the non-human predicate, 10.2) needs 25.1b and moved post-mod with it | 10.3: step 12. 10.5, 10.6, 10.4, 10.2: post-mod ([[#post-mod]]) | L15, L30, L59, L83, L84, L128; `e2010bd` |
| 13 | [[plan-13-cross-partition-sweep]] | drafting | **Dormant.** Its sessions question waits for a sessions gold set; 21.4's gold set covers code and docs only | [[#dormant]] | the user, 2026-10-07 (C9); d4b |
| 15 | [[plan-15-derive-impact-tracking]] | in-progress | Tasks built and deployed. Closes on T0.7 (the r13 remedy and a clean full suite) with T0.8 (bug-196) | steps 1, 4 | D-Q6, L48; [[task-t0-suite-trust-sweep#t0-7]] |
| 16 | [[plan-16-invisible-grep-shim]] | approved | 16.1 → 16.2 ∥ 16.3 → 16.5 → 16.4, and the 16.6 Wave-1 slice. Grep learning stays off until 31.2. bug-081, 102, 167 and 174 close when 16.5 lands (its R3 floor); bug-222 is 16.5 R2's; bug-120 goes with 16.6 R1f. The bug-174 re-measure (30 or more `bre_meta_literal` rows, or 2026-12-31) reports in 16.4 | post-mod ([[#post-mod]]) | L2, L5, L32, L42, L49, L50, L52; [[task-16.4-measurement#r4-reopen]] |
| 17 | [[plan-17-nightly-store-maintenance]] | approved | 23.4 first (its verdict reopens 17.1, L21), then 17.1 → 17.2 (which hosts 26.6's compile tick, L28) → 17.4 → 17.3 (user-gated) | post-mod ([[#post-mod]]) | L21, L28, L40 |
| 18 | [[plan-18-duckdb-store-maintenance]] | approved | 18.2, 18.3. A real reclaim is refused on a git-tracked catalog (store review D2, L106). 18.1's measurement is re-taken before 18.2's hand runs | post-mod ([[#post-mod]]) | L106; [[plan-review-fable-2026-11-14-store#decided]] |
| 19 | [[plan-19-adaptive-memory-budget]] | approved | Built by other tasks (L14): 19.1 by 25.1 (shipped); 19.3 by 26.7; 19.4 by 26.6 and its R3 residual, its tick by 17.2; 19.5 R1 by 25.1; 19.6 R8a by 10.3 and R5 by 10.6; 19.0 R1 by 25.3. **Frozen** (D-Q3, L26): 19.2, the rest of 19.5, 19.6's phasing, cache and Table C. 19.0's remainder (R0, R2-R7; bugs 100, 103, 104) follows 25.3 (L41) | 19.3, 19.4: step 11. Everything frozen and 19.0's remainder: post-mod ([[#post-mod]]) | D-Q3, L14, L26, L41, L51, L128 |
| 20 | [[plan-20-concept-similarity-eval]] | drafting | 20.1 (labels; needs the user's 50-pair review), 20.2 (after G22 and with bug-216 live), 20.3 (conditional) | post-mod ([[#post-mod]]) | L22, L128 |
| 21 | [[plan-21-agent-context-usage]] | in-progress | 21.2 → 21.4 (pull side); 21.5 phase M. **Frozen** (D-Q3, D-Q4): 21.3 and 21.5 phase B. 21.6 waits on 24.6 R4. 21.7 is a drafting row with no spec | 21.2, 21.4: step 14. Phase M: step 15. 21.3, phase B, 21.6, 21.7: post-mod ([[#post-mod]]) | D-Q3, D-Q4, L35, L51, L128; `b1be2e4` |
| 22 | [[plan-22-audited-removal-and-repair]] | approved | 22.6 R4 is built inside 31.2. The rest: 22.1a → 22.2 → 22.5 ∥ 22.6 → 22.3, then 22.1 (needs 16.1). 22.1a walks only registered store roots (store review D3, L106). 22.4 is two deferral rows with no host plan (L22) | R4: step 9. The rest: post-mod ([[#post-mod]]) | L2, L6, L22, L49, L69, L106 |
| 23 | [[plan-23-bounded-write-harness]] | in-progress | 23.2 → 23.1 → 23.3 ∥ 23.5. 23.1 closes bug-099, bug-106 and bug-177; 23.5 carries plan-2's #s-3 rider and the `memory_compile` hold (R9). 23.4 is a read-only measurement with an approved op table (store review D4) | step 13. 23.4: post-mod ([[#post-mod]]) | L1, L4, L21, L31; [[plan-23-bounded-write-harness#merge-order]] |
| 24 | [[plan-24-mod-transport]] | drafting | The mod: 24.0 ∥ 24.1 → 24.2a → 24.2 → 24.3 → 24.4 → 24.5 → 24.6 → 24.7 → 24.8. Specs written 2026-10-20; ch-bsd r6 was DIRTY (0B/1S/1M) and the r7 fold was never confirmed. Its freshness revision to approval is the last pre-mod step; 24.6 takes the tool-event builder; D1 is superseded (D-Q5) | steps 16, 17 | L128, L129; [[bsd-plan24-spec-review-r6-34fedb1]] |
| 25 | [[plan-25-cliquedb-field-report]] | in-progress | 25.2 (bug-165), 25.3 (bug-166). 25.1b (the hook output ladder; bug-182 as R15, bug-224 as R18, plan-2's riders) | 25.2, 25.3: step 12. 25.1b: post-mod ([[#post-mod]]) | D-Q2, L15, L34, L39, L43, L44, L68 |
| 26 | [[plan-26-memory-organisation]] | in-progress | 26.5 → 26.7 → the 26.6 R3 residual → 26.8 → 26.9 | step 11 | L1, L9, L10, L37; `3be7676` |
| 27 | [[plan-27-memory-fleet-rollout]] | approved | 27.0 → 27.1 → 27.2a, 27.2 → 27.3 → 27.4 → 27.5 → 27.6, after 26.8 | step 11 | L10, L13, L78 |
| 28 | [[plan-28-handhold-outcome-experiment]] | approved | 28.1 → 28.2 → 28.3 → 28.4 → 28.5: one leg, the paired re-entry series (L83). It needs 10.2 built, 21.5 phase M reported, G32 clean and bug-216 live. The charter decision (G18) follows its report | post-mod ([[#post-mod]]) | L78, L80, L83, L86-L89; `b1be2e4` |
| 29 | [[plan-29-code-quality]] | in-progress | 29.4 stages 2-5 (stage 0 and stage 1, T0.1', are merged), then 29.1, 29.5, 29.3, 29.2, 29.4f, 29.6. `consolidate.py` is not edited by plan-29; its held rows and one silent handler wait for the next release that changes that file (L110) | steps 1-4, 6-8 | L104-L111, L113, L115, L118, L121-L124, L126, L130; `3b930e4`, `a0c7560` |
| 30 | [[plan-30-materialisation]] | approved | 30.0-30.5 and 30.6 (spec pending; G30 folds into it). It fixes bug-243 (30.4) and bug-246 (30.5). D1-D3 are decided | step 10 | L116, L117, L128; `df75516` |
| 31 | [[plan-31-pre-mod-loose-ends]] | drafting | Six tasks: 31.1 bug-244 and bug-255; 31.2 bug-107 and bug-247 with 22.6 R4; 31.3 the bug-242 guard; 31.4 retire the standing lint warnings; 31.5 scan-prompt measured per block, then cut (Q27 = b; bug-256); 31.6 bug-251, one wikilink resolver (Q30 = a). Specs in flight; approved on a ch-bsd MEH-only GO. D1-D10 and D14 are decided | steps 5, 9, 14 | L125; [[#decisions]] |

### Standalone tasks {#standalone}

| task | status | what it is | where | evidence |
|---|---|---|---|---|
| [[task-t0-suite-trust-sweep]] | in-progress | The suite-trust sweep. It is 29.4's body. T0.1' is merged; T0.2 to T0.8 remain | steps 1-4, M1 | L48, L121-L124, L126; `0e55687`, `a0c7560` |
| [[task-bug185-bulk-gmd-ingest]] | approved | Bulk GMD ingest; it also fixes bug-186 and bug-221 and emits bug-216 R13's events | step 13 | L3, L4, L46, L50, L52, L57, L62; `327703d` |
| [[task-bug218-reinforcement-edge-direction]] | approved | Reinforcement reads its edges in one orientation; hosts bug-223 | step 13 | L49, L52, L69, L74; `0a40f4b` |
| [[task-dq1-operational-content-out-of-graph]] (G22) | approved | `workflow/`, save-states and digests stay in the partition and leave the derivations (D-Q1, Q8 = a, Q9) | step 10, after plan-30 release C | L60, L61, L65, L67, L69, L71, L74, L128 |
| [[task-bug216-denotes-fold-evaluation]] (G30) | approved | Per-type evaluation of the `denotes` PageRank fold; a measurement, folded into 30.6 | step 10 | L7, L29, L128; `b1be2e4` |
| G32, the m1 r2-lite confirm | admitted | A ch-bsd confirm of the 21.5 measurement corrections; no spec file | step M3 | L36, L54, L128 |
| the cross-partition `rel:` probe | admitted | One read-only probe; no spec file | step M2 | L106, L128 |
| [[task-compaction-as-handoff]] | drafting | Compaction as save-state, then a pulled recall-state (Q17 a) | post-mod ([[#post-mod]]) | L90-L93 |
| [[task-agent-start-context]] | drafting | A generated agent-start hook (Q15) | post-mod ([[#post-mod]]) | L85 |
| [[task-linked-readonly-store]] | drafting | A `.refmatrix` symlink in a clone makes a linked, read-only store (Q16 a); usage is measured first (queue review D2) | post-mod ([[#post-mod]]) | L88, L106, L128 |

### Tracks {#tracks}

A bug's track is its owning task's track (L8). 29.1 writes the track into every `scheduled`
registry row. {#tracks-lead}

| track | before the mod | post-mod |
|---|---|---|
| **T0 instrument trust** (inside 29.4) | bug-170, 168, 127, 229, 253 (T0.2); 130, 190, 091, 228, 231 (T0.3); 196 (T0.8); the gates of plans 6, 7, 8, 15 | bug-088 and bug-101 stay deferred by the user; the runner shards only once a live touch fails the session |
| **T2 memory organisation** | 26.5 (bug-208, 213, 220), 26.7, 26.6 R3, 26.8, 26.9, plan-27; the `rel:` probe | backlog 206, 210 |
| **T3 context delivery** | 10.3; 25.2 (bug-165); 25.3 (bug-166); 21.2, 21.4; G32; 21.5 phase M; 31.5 | plan-10's dedupe (10.5, 10.6, 10.4, 10.2); 25.1b (bug-182, bug-224, plan-2's riders; the `legs_ms` pair); 19.0's remainder (bugs 100, 103, 104); 19.2; 19.5's remainder; 19.6's frozen parts; 21.3; 21.5 phase B; 21.6; 21.7; plan-28; compaction-as-handoff; agent-start-context |
| **T4 write path** | bug-185 (bug-186, 221); 23.2; 23.1 (bug-099, 106, 177); 23.3; 23.5 (bug-136's rider); adopted 194, 203, 207 | 23.4; the 16.6 slice (bug-120); plan-17; plan-18; backlog 097 |
| **T5 grep surface** | — | 16.1-16.5 (bug-081, 102, 167, 174, 222); backlog 180; 22.1 after 16.1 |
| **T6 graph integrity** | bug-218 (bug-223); 31.2 with 22.6 R4 (bug-107, 247); G22; G30 (in 30.6) | plan-22's rest (bug-086 is 22.3; bug-219's census is 22.1a's); plan-20; backlog 119, 121, 124 |

## Pre-mod freeze (user, 2026-11-15) {#freeze}

**The freeze line.** Before the mod transition (plan-24) begins, only this work is admitted:

1. **Plan-29** code quality: 29.4's stages → 29.1 → 29.5 → 29.3 ∥ 29.2 → 29.4f → 29.6
   (L118, Q29 = a).
2. **Plan-30** adjacency + bitmap materialisation (30.0-30.5), plus **30.6** edge-type value
   measurement ([[plan-30-materialisation#t6]]), with G30 folded into it; and G22 after release C
   (L128).
3. **Plan-31** pre-mod loose ends ([[plan-31-pre-mod-loose-ends]]): 31.1 bug-244 and bug-255,
   31.2 bug-107 + bug-247, 31.3 the bug-242 ledger-anchor guard, 31.4 retire the standing lint
   warnings, 31.5 the scan-prompt injection measured per block, then cut and tightened
   (Q27 = b), 31.6 bug-251, one wikilink resolver for lint and ingest (Q30 = a).
4. **From the L106 queue** (the user, Q28 = a, 2026-11-15; [[freeze-triage-2026-11-15]]; as
   amended by L128):
   T2 memory organisation (26.5 → 26.7 → 26.6 R3 → 26.8 → 26.9 ∥ plan-27), with the
   cross-partition `rel:` probe first; bug-218; 25.2, 25.3, 10.3, with G32 first; T4 bounded
   writes (bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5); 21.2 → 21.4, after 31.5; 21.5 phase M; 22.6 R4
   folded into 31.2.
5. **The last pre-mod step** (L128, L129): the plan-24 freshness revision, to approval. The mod
   starts when it is approved.

The order is [[#queue]]. {#freeze-list}

**Specs on master (2026-11-15).** The approved frozen spec branches are merged as they stand (the user: "although they are stale, they should be actionable still"): `spec-wave-t2` (26.5-26.9, plan-27) `3be7676`, `spec-wave-t4` (bug-185, plan-17/18 records) `327703d`, `spec-wave-t3b` (plan-10 10.2-10.6) `e2010bd`, `spec-wave-t3c` (21.5, plan-28 record) `b1be2e4`, `spec-wave-t56` (bug-218, 22.6 with R4; plan-16 / rest of plan-22 as post-mod records) `0a40f4b`, `spec-wave-t3a` (plan-19, 25.1b record, 25.2/25.3 inputs) at this commit. Stale citations are reconciled by RED and GREEN at build time (TDD_GOVERNANCE: stale ground truth is reconciled before the test). Every freeze item except 30.6 and plan-31 now has an approved spec on master. {#freeze-specs}

**Amended by L128 (2026-11-15, Q32-Q36 = a).** Admitted: G22 (after plan-30 release C), G30 (folded into 30.6), G32 (the m1 r2-lite confirm; 25.2 and 21.5 phase M wait on it), the cross-partition `rel:` probe (26.5 needs it). Moved post-mod: plan-10's dedupe 10.5 / 10.6 / 10.4 / 10.2 (10.3 and 31.5 stay). **The last pre-mod step:** the plan-24 freshness revision to approval (evidence: 31.5, 21.5 phase M, 30.6; 24.6 takes the tool-event builder); the mod starts when it is approved. The L127 re-evaluation of every post-mod item runs after the initial mod work is finished (L129). {#freeze-amended}

**The rule.** Nothing else is admitted before the mod except a bug that breaks something live
(a crash, data loss, a wrong answer on the production path, a wedge). Everything else — new ideas,
the lead's included — goes to the post-mod list below, with one line saying why it waits. A bug
found during the frozen work is logged in the registry as always; it joins the queue only if it
breaks something live, else it is marked `post-mod`. The goal the freeze serves (the user,
2026-11-15): the core concept/graph representation more useful, context succinct and relevant,
performance improved, busywork removed, loose ends tied up — "at some point I need to stop adding
things and let the work finish." {#freeze-rule}

rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[plan-30-materialisation]]
rel: depends-on -> [[plan-31-pre-mod-loose-ends]]
rel: depends-on -> [[orchestration]]

## Post-mod list {#post-mod}

Admitted after the mod transition, not before (each with why it waits). **Every item here is re-evaluated against the mod before it is built (L127): keep, re-spec onto the mod surface, merge, or drop. The re-evaluation runs after the initial mod work is finished (L129).**

- **Branch-aware GMD lint** (resolve links against the target branch ∪ `master`; bug-249's shape) —
  the code-span-then-wikilink workaround is cheap and rare.
- **Generated frontmatter / heading anchors** — new tooling; reduces ceremony but adds a feature.
- **A before/after node check on GMD edits** (an edit is a graph mutation) — new machinery.
- **Injection presentation work beyond plan-31 31.5** — the mod changes how context is delivered;
  tool-keyed rules are its design input ([[design-note-tool-keyed-context-2026-11-15]]).
- **bug-248** (transaction rollback leaves log events and bitmap bits) — a design change; nothing
  live is known to roll back mid-write today.
- **bug-250** (a missing path is not refused on the verb/op ingest routes) — validation; the
  daemon's ingest errors on a missing path anyway.
- **Pre-split rows / filter bitmaps** — already deferred with a trigger ([[plan-30-materialisation#deferred]]).
- **Inline term introspection (`term...`)** (the user, 2026-11-15: "the ability to inline access
  the metadata of a word/term/concept using something like adding an ellipsis… making every
  word/term introspectable (descend into its associative network)"): an ellipsis-marked prompt
  term gets the top scan-prompt tier and a fuller associative bundle (neighbours, defining docs,
  memories, depth 2 for that term only); interactive descent in the hub graph view / the mod. An
  explicit pull that replaces scan-prompt's guess at which words matter. A UX feature: the mod.
  **Extension (the user, 2026-11-15):** `w1...w2` / `w1...w2...w3` name seeds whose connecting
  subgraph to explore (a steered multi-seed walk: paths / connector set between the named terms,
  the opposite of the unconstrained degree-2 walk that retrieved ~5x worse); three terms read as
  waypoints. `..` (two dots) walks the type/instance axis instead (`is_a` / kind / instance-of:
  `function..` = instances, `Store..parse` = the instance's type or siblings). Open: telling it
  apart from prose ellipsis, Rust/Swift ranges and dotted paths (operators only when glued to
  tokens, ignored inside code spans); the gestures compile to the `rmx query` DSL, not a second
  engine.
- **From freeze-triage-3 (L128, Q32 / Q36 = a):** plan-10's dedupe 10.5 / 10.6 / 10.4 / 10.2 (needs 25.1b); 19.0's remainder with bug-100 / 103 / 104; 19.2; the frozen parts of 19.5 and 19.6; 21.3; 21.5 phase B; 21.6; 21.7; plan-20; plan-7's four W4-a deferral rows; the linked read-only store and its measurement; the `legs_ms` pair (follows 25.1b); bug-182, bug-224, bug-167 / bug-174 with their hosts (bug-182's overruns re-counted after plan-30 release C).
- **From the L106 queue (Q28 = a):** compaction-as-handoff, agent-start context, 25.1b (new hook
  features; the mod replaces the hook surface); plan-28 (paired series); 23.4, the 16.6 slice and
  plan-17 (nightly maintenance); plan-22 except 22.6 R4; plan-16 (grep shim; learning stays off
  until 31.2); plan-18 (duckdb maintenance).

### Also post-mod by the freeze rule {#post-mod-rule}

Two groups the list above does not name. The freeze line does not admit them, so the rule makes
them post-mod; each keeps its last decided state. {#post-mod-rule-lead}

| item | last decided state | evidence |
|---|---|---|
| plan-8's deferral rows 43 and 44 | held with the frozen 19.2 | L48 |
| the registry backlog: 206, 210, 097, 180, 119, 121, 124; the `--like` selector | outside the goal; 29.1 gives each row a status | L33; [[plan-review-2026-11-13#queue]] |

## Dormant and held {#dormant}

| item | state | reopens when | evidence |
|---|---|---|---|
| plan-13 (13.0-13.6) | dormant | a sessions gold set exists | the user, 2026-10-07 (C9); d4b |
| 22.4 and the two merge entry points | deferral rows, no host plan | plan-20 produces a merge signal | L22 |
| `consolidate.py`'s six declared rows and one silent handler | held | the next release that changes that file's behaviour | L110; [[task-29.3-converge-shapes#c-pass-rows-held]] |
| bug-088, bug-101 (suite reach to live sockets) | deferred by the user | the user un-defers them | [[plan-review-2026-11-13#f8]] |

## Open flags {#flags}

The compilation of plans 2-31 flags two kinds of thing: a contradiction between the consolidation
and the freeze, and a dependency of plan-24's start that is neither met nor admitted. Everything
else is admitted by [[#freeze]], named in [[#post-mod]], or post-mod by the rule. Six of the
flags it first raised were answered by the user on 2026-11-15 (Q32-Q36 = a, L128, L129) and are
in [[pop-finished]]. What is left: {#flags-lead}

- **F5. 31.2 folds 22.6 R4; 22.6 R4 names the post-mod 16.6 slice.** The freeze line: "22.6 R4
  folded into 31.2". The 22.6 spec: "R4 (the sync edit fix) needs only 16.6's Wave-1 slice and
  may land first", and the rows R4 keeps include "its sidecar rows". The post-mod list: "23.4,
  the 16.6 slice and plan-17 (nightly maintenance)". 31.2's spec is written on `spec-plan31b`
  (`a4d245a`) and was not read for this flag; its ch-bsd round checks that R4 stands without the
  sidecar. If it names the slice as a dependency, that is a new admission and goes to the user.
  {#f5}
- **Plan-24's start: no dependency is left that is neither met nor admitted.** Task 3.7, the one
  dependency plan-24 declares on built work, is met (`91ddbe0`, 0.81.0). Its approval, its
  re-plan and the tool-event builder are all inside step 16 (L128). Two things step 16 must not
  miss, because plan-24 still states the opposite: `#decisions` lists D1 as in force,
  `#phase-now` says 24.0 and 24.1 "start now", and `#phase-held` says the hook-shaped specs are
  "kept as records, not built" (L38 and G27 owed these amends notes and the 24.8 R5 rows for
  plan-10 and 25.1-25.3); and 24.6 needs 24.0's "before" window closed, a week of pre-mod
  hook-cost data, so 24.0 runs first and its week passes while 24.1-24.5 build. The probes ran
  on Claude Code 2.1.304 and this machine runs 2.1.325; `skill.prompt` and an installed plugin
  against a `--plugin-dir` copy are unprobed ([[plan-24-mod-transport#probes-consequences]]).
  {#p-notes}

## Status lifecycle (files follow this file) {#status-lifecycle}

```
drafting → approved → in-progress → completed
```

- **drafting** — being designed; not every task has a spec.
- **approved** — every task has a written spec under `workflow/plans/<plan>-tasks/`; ready to build.
- **in-progress** — at least one task has shipped and at least one remains.
- **completed** — done. The plan's row is appended to [[pop-finished]] and deleted here; the
  plan file stays in place with `status: completed`.

A plan can also be **dormant** ([[#dormant]]) or **post-mod** ([[#post-mod]]); those are
positions, not `metadata.status` values. The stage is set **here first**, in the row's status
column; the plan file's `metadata.status` is then edited to match, in the same commit. Files stay
put; links never rot. {#status-lifecycle-body}

## Ledgers: rulings, decisions, questions {#ledgers}

The user, 2026-11-15: "any L, D, or Q must be placed in the POP before being amended to a plan".
A ruling (`L<n>`), a plan decision (`plan-N D<n>`) or a question to the user (`Q<n>`) is entered
here first, with its state; only then is it amended into a plan, spec or task file, which cites
the row here ([[orchestration#pop-truth]]). A row that is resolved and applied is appended to
[[pop-finished]] and then deleted here, in one commit. Earlier rows: L1-L124 in
[[plan-review-2026-11-13#lead]], Q1-Q22 in [[open-questions]], Q23 on in [[pop-finished]].

### Rulings (L125 on) {#rulings}

| L | date | source | ruling | applied to |
|---|---|---|---|---|
| L125 | 2026-11-15 | the user: "for p31, once bsd is happy they are approved" | plan-31's plan and task specs are **approved on ch-bsd MEH-only GO**, the MEHs folded before the merge; no separate user approval. Their `plan-31 D<n>` decisions are entered in [[#decisions]] first and take the architect's recommendation, **except** a decision that changes a store on disk (31.2's fate for the existing orphaned learned rows; any fleet re-derive or reingest 31.6 needs), which goes to the user ([[orchestration#release]] step 4) | plan-31 row; `plan-31-pre-mod-loose-ends.md` at merge |
| L126 | 2026-11-15 | ch-bsd r1 of T0.1' (MEH-only 5, GO; [[bsd-t01-r1-fff91a8]]) | GO; mutations M1.1-M1.11 recorded by the reviewer. MEH-1: RED adds a chained-clone case run with `GIT_DIR`/`GIT_WORK_TREE` exported at an unrelated repo, plus M1.12 'drop the scrub' (must turn it red). MEH-2: the three gate-root helpers copy the resolver unconditionally, stale comment dropped. MEH-3: the mock-registry row states the current clone behaviour. MEH-4: the summary keeps `task-t0.1-skip-gate-memdir.md`; `#t0-1-files` is amended. MEH-5: anchored to stage 2, no fold now. The lead checks the fold (small MEHs, [[orchestration#task]] step 5); then merge `--no-ff` | T0.1' branch; `task-t0-suite-trust-sweep#t0-1-files` |
| L127 | 2026-11-15 | the user: "all of the post-mod feature work needs to be re-evaluated to make sure they are still relevant to the design" | Every post-mod item ([[#post-mod]], plus the post-mod plans 16, 17, 18, 22 except 22.6 R4, 28, the frozen parts of 19, 21.3 / 21.6 / 21.7, 25.1b) is re-evaluated against the mod design before any is built: each gets **keep** (as specced), **re-spec** (onto the mod's surface), **merge** (into another item or a plan-24 task) or **drop**, with a one-line reason, entered here first. It runs with the plan-24 freshness revision, because that revision fixes the design it is measured against (Q33); until then no post-mod item is scheduled | [[#post-mod]] header; plan-24 revision brief |
| L128 | 2026-11-15 | Q32-Q36 = (a) (the user, with L127) | Applied to [[#freeze]] and [[#post-mod]] in this commit: **post-mod** plan-10's dedupe 10.5 / 10.6 / 10.4 / 10.2 with 25.1b (10.3 and 31.5 stay pre-mod) (Q32); **the freeze's last step** is the plan-24 freshness revision to approval, with 31.5, 21.5 phase M and 30.6 as evidence, and the L127 re-evaluation of every post-mod item (Q33); **24.6 builds** the tool-event builder (`stm.tool_event_fields`) in that revision (Q34); **admitted** G22 (after plan-30 release C) and G30 (folded into 30.6) (Q35); **admitted** G32 and the cross-partition `rel:` probe; **post-mod** 19.0 rest (+ bug-100/103/104), 19.2, 19.5/19.6 frozen parts, 21.3, 21.5 phase B, 21.6, 21.7, plan-20, plan-7 W4-a rows, linked-readonly-store, `legs_ms`; bug-182, bug-224, bug-167/174 follow their post-mod hosts, bug-182's overruns re-counted after plan-30 release C (Q36). Source: freeze-triage-3 (arch-triage, `42f5aa0`) | [[#freeze]], [[#post-mod]]; Q32-Q36 → [[pop-finished]] |
| L129 | 2026-11-15 | the user: "the re-eval of the post-mod work can happen after the initial mod work is finished" | Amends L127 and L128's Q33 step: the plan-24 freshness revision to approval stays the **last pre-mod step**, without the post-mod re-evaluation. The L127 re-evaluation (keep / re-spec / merge / drop for every post-mod item) runs **after the initial mod work is finished**, against the mod as built; no post-mod item is built before it | [[#freeze]], [[#post-mod]] |
| L130 | 2026-11-15 | T0.8 RED (red-t08, `04a2c9b`; report `workflow/review-output/t0.8/red-report.md` on the branch) | RED accepted: one new node RED at base (`assert []`, a call in both cli.log and query.log is not counted once), the AC-6 pair the red record for R8.1. (1) The new R8.2 test also asserts the frozen fixture's per-channel counts 201 / 6 / 3 / 34 (the AC-6 tests stay untouched, R8.3). (2) The cli.log section counts only calls query.log does not hold: the spec's intent, accepted. (3) The pairing key is cwd + channel + invocation + `ts` within 1 s; no new log field (old rows stay matchable). The RED author's throwaway fix sketch was reverted (`src/` clean at `c4b44d0`) and is not given to GREEN | T0.8 branch |
| L131 | 2026-11-15 | the user: "I thought we decided targeted testing for minor releases and full testing for majors" | Terminology corrected to the user's (L119's substance unchanged): **major** = `0.N.0`, full suite on merged master; **minor** = `0.N.x`, the targeted set (task tests + family + importers of changed modules). The lead had written "minor (0.N.0) / patch (0.N.x)". A release that changes a shared path (ingest, store, daemon ops, a hook's output, the CLI contract) is major; unsure → major. ORCHESTRATION `#release` relabelled | [[orchestration#release]] |
| L132 | 2026-11-15 | arch-31b's specs 31.1 / 31.6 / 31.2 (`spec-plan31b` `a4d245a`) | Scope accepted for ch-bsd: **31.6 R5** (unlink the superseded edge on re-bind) stays although beyond the plan's wording, because without it the 62 misbound edges remain; 31.6's AC is all three classes at 0 (unresolved 37, misbound 62, stale 8 = bug-251's real extent of 107 lines). 31.2's two departures (ingest-derived orphans recorded as counts in the manifest, not rows; no restore command, 22.2 being post-mod) go to ch-bsd to judge. Folds: bug-257 → 31.6 R5; bug-258 → 31.1; bug-259 and bug-260 → 31.2 (its invariant catalog == rebuild). Order: 31.1 before 31.6 (both edit `ingest_gmd.py`). The 31.6 re-bind reingest of each store is its own user go | `task-31.1`, `task-31.6`, `task-31.2`; plan-31 `#t6`, `#order` at merge |
| L133 | 2026-11-15 | ch-bsd spec r1 of 31.5 / 31.3 / 31.4 (DIRTY 3B/8S/11M; report held with `spec-plan31a` until its merge) | All 22 fold; arch-31a revises on Fable, then a bsd confirm-lite r2. **B1:** the POP's D1 row mis-described the capture as "prompt sha256 only" (the lead's error); D1 stands with the fold: the capture dir writes its own `.gitignore` (`*`), proven by a test, because atlftpd ignores nothing under `.refmatrix/` and three repos' default branches lack the line while `save-state --commit` runs `git add -A` (bug-261). **B2:** 31.3 builds the shared gate-tree helper itself (the copy-the-lint-script edit has hit the same helpers three times: T0.1, 31.3, 31.6); no deferral to 29.3. **B3:** bug-256 gets a requirement, an AC and a mutation in 31.5; the failure is counted in the capture record, not only on the stderr the hook discards. **S1:** the cost band is measured on a copy of the live catalog in fresh processes (bsd measured 140-370 ms for four builds; the token stop fired on 53% of past prompts). **S2:** the capture outcome goes in the capture record, not the already-written `query.log` row. **S3:** a capture-only switch, with an AC. **S4-S7, M2-M11:** as the report proposes. **S8:** moot, Q37 = (a). **M1:** labels are D1-D10 already (`3f6de0b`). **M3:** D7's ledger edit lands before 31.3's GREEN starts. **M8:** 31.4 and 31.6 each name the other's linter change and the order (31.1 → 31.6; 31.4 never in flight with 31.6) | `spec-plan31a`; POP D1 row |
| L134 | 2026-11-15 | arch-31b's revision of 31.1 / 31.6 / 31.2 (`spec-plan31b` `d788602`) | (2) 31.2 takes the learned-row halves of 22.6 R3 and R5 in a narrowed form beside R4: within plan-31 `#t2`'s own scope (the deleted file, vacuum's log), not a new admission; the freeze line says so. (4) "The audited removal path" in the POP's D14 row is the lead's wording, not the user's: it means dry run whose counts equal the measured split, manifest first (22.6 R2's path, 22.2 R4's record form), a logged event, and the lead's backed-up run; plan-22's engine and `--confirm` stay post-mod. (5) The manifest writes no vectors file (22.2 R4 asks for one): a third departure for ch-bsd to judge, with L132's two. (1) and (3) go to the user as Q38 and Q39 | `task-31.2`; [[#freeze]] |
| L135 | 2026-11-15 | arch-triage's queue additions (`triage-3` `b817f62`) | Applied to [[#queue]]: row 18 (the L127 re-evaluation after the mod's initial work, L129), [[#queue-quiet]] (which admitted tasks edit `cli.py` / `store.py` / `daemon.py` / `verbs.py`, so sequence around 29.5) and [[#queue-releases]]. The release grouping was a proposal; the lead adopts it as the plan (sequencing is the lead's): eight major releases R1-R8, 31.5's capture riding R1 (its 400-prompt window starts at R1's deploy). Plan-31's placement was read before the L133 / L134 folds and is re-checked when its specs merge | [[#queue]] |
{#rulings-table}

### Plan decisions {#decisions}

Open decisions first; a decided row keeps its answer and the plan anchor it was amended into.
Allocated ranges in flight: plan-31 D1-D10 (specs 31.5 D1-D6, 31.3 D7, 31.4 D8-D10; branch `spec-plan31a`),
plan-31 D11+ (specs 31.1 / 31.6 / 31.2, branch `spec-plan31b`); none entered yet.

| D | plan | decision | options (recommendation first) | state | amended into |
|---|---|---|---|---|---|
| plan-31 D14 | plan-31 (31.2) | What happens to the existing orphaned learned evidence rows (28,164 on the refmatrix store, 26%, `measurement-learned-rows-cli-store-2026-11-14`)? | — | **decided by the user, 2026-11-15:** "migrate them if they can be resolved, if not, delete them". Resolvable rows are re-attached to their current entity; the rest are deleted through the audited removal path with a manifest (never a silent drop; `feedback_decay_never_loses_knowledge`). Measured by arch-31b on a store copy (2026-11-15): 30,131 orphaned learned rows, 30,078 (99.8%) resolvable (file present, a live same-named entity, the concept), restoring 2,717 query-to-file associations; about 53 to delete. **Re-measured after `903f7f5`** (two review docs archived): 29,824 resolvable, 307 to delete, 2,697 pairs; the dry run at the store event binds. What "resolved" means is Q38. The store write is the lead's, announced and backed up | to be amended into `task-31.2` by arch-31b |
| plan-31 D7 | plan-31 (31.3) | The 15 id-less dated bullets in six folded ledger memories | (rec) the lead appends ids to them, merged together with 31.3; alt: allow-list | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.3` at the spec merge |
| plan-31 D8 | plan-31 (31.4) | Disposition of the four standing warning classes | (rec) all four fail the gate (`--strict`), none retired | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.4` at the spec merge |
| plan-31 D9 | plan-31 (31.4) | `amended-by` / `superseded-by` inverse verbs on 5 older memories | (rec) drop them; add the forward edge on `project_daemon_ingest_hard_death_open` first | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.4` at the spec merge |
| plan-31 D1 | plan-31 (31.5) | Where the injection capture is on | (rec) on by default in every store, local and bounded (64 MiB / 42 days). **Corrected 2026-11-15 (bsd-31a B1):** the capture stores block payload text, which echoes up to eight prompt terms per call (the prompt itself only as sha256); the capture dir therefore writes its own `.gitignore` (`*`) and a test proves it; alt: marker-file opt-in | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D2 | plan-31 (31.5) | How 'a week' is counted | (rec) 400 prompts, 6 sessions of ≥ 20, ≥ 80 per block kind; closes at 800 | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D3 | plan-31 (31.5) | The per-kind band action table | (rec) confirm it before the numbers; the composite's cut (`--no-composite` in the generated hook) is re-asked with the number in hand | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D4 | plan-31 (31.5) | What to do about `ignored` | (rec) report only; handed to 10.6 and the mod design note | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D5 | plan-31 (31.5) | A kind whose band is ambiguous or under-sampled | (rec) `shrink` by default; S3 ablation only on the user's go | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D6 | plan-31 (31.5) | The capture after 31.5 | (rec) stays on, bounded; 21.5 phase M, plan-10 and 30.6 read it | **decided** by L125 (the architect's recommendation; not a store-on-disk change) | to be amended into `task-31.5` at the spec merge |
| plan-31 D10 | plan-31 (31.4) | Changing the upstream GMD linter (`~/claude_tools/gmd`: a `--strict` flag, the `session/recall-state` enum line) and one line in the user's global `~/.claude/MEMORY-RULES.md` | (rec) yes: `--strict` upstream, opt-in, passed only by `scripts/lint-gmd.sh` | **decided by the user** (Q37 = a, 2026-11-15): `--strict` and the `session/recall-state` enum line upstream, plus one line in `~/.claude/MEMORY-RULES.md`; spec anchors `task-31.4-retire-standing-warnings#r1`, `#r3`, `#ac-4`-`#ac-6` | — |
| plan-31 D11 | plan-31 (31.1) | A markdown file refused for a non-string `id:`/`title:` on `rmx ingest` / `rmx sync` | (rec) the rest lands, then one `Error:` line naming the file and exit 1 (as L112 S2 and 26.2) | **decided** by L125 (recommendation; no fleet file has the shape) | to be amended into `task-31.1` at the spec merge |
| plan-31 D12 | plan-31 (31.6) | Case and dash folding in wikilink resolution | (rec) drop it: the lint fails what it folded and names the exact id (46 links here: 11 repo files fixed in the task, 35 memory-file links the lead's edit; cliquedb 110 and cliquet 3 at their next re-vendor) | **decided** by L125 (recommendation; re-binding a store is a separate user go) | to be amended into `task-31.6` |
| plan-26 · L11 | plan-26 (26.8) | Apply ADR-0005 Appendix A's MEMORY-RULES text, which carries the marker condition? | — | **open:** the user approves the text at 26.8 AC-8 (L11) | [[task-26.8-refmatrix-live-rollout]] AC-8 |
| plan-26 · L12 | plan-26 (26.8) | Does the forget flow gain step 5, `rmx memory forget <id>`? ADR-0005 A.2 states the tension with the decay rule | — | **open:** put to the user in the same AC-8 window (L12, L47 O5); applied only on acceptance | [[task-26.8-refmatrix-live-rollout]] AC-8 |
| plan-26 · 26.5 split | plan-26 (26.5) | Split 26.5 into the verb (bug-208, bug-213) and the bug-220 reroute, so the rollout does not wait on the reroute? It would amend L37 | — | **open:** proposed by the memory review ([[plan-review-fable-2026-11-14-memory#o5]]); no ruling | — |
| plan-27 · 27.3 | plan-27 (27.3) | Delete the retired `~/enduris/thiquet` store after the tombstone? | — | **open:** the user decides at 27.3 | [[task-27.3-thiquet-store-repoint]] |
| plan-23 · 23.1 split | plan-23 (23.1) | 23.1 is built as three tasks: 23.1b (R1.6, AC-20: the `_FairLock` owner), 23.1a (R1.1-R1.5, R2-R10: the harness, queue and tail), 23.1c (R11, AC-21: `hook_writes`, closes bug-177) | — | **decided, not amended:** settled by the store review "as the user would" under L106 ([[plan-review-fable-2026-11-14-store#decisions-settled]]); the 23.1 spec is still one task | [[task-23.1-queue-and-drain]] |
| plan-24 · D1 | plan-24 | The hook-shaped work retargets to the mod instead of being built on hooks | — | **superseded by the user, 2026-11-13 (D-Q5):** verb-side logic builds on the hook transport now. Not yet amended into plan-24; step 16 does it ([[#flags]]) | [[plan-24-mod-transport#decisions]] |
| plan-28 · G18 | plan-28 | The charter decision on the paired series' result; the T3 re-plan follows it | — | **open, post-mod:** put to the user with plan-28's report | [[plan-28-handhold-outcome-experiment]] |
| plan-18 · Q-A, Q-E | plan-18 (18.3) | Q-A: `requires_arming` for the reclaim step. Q-E: accept the reclaim's memory cost | Q-A: `True`. Q-E: accept, with the per-store peak stated first | **open, post-mod:** both still read "Recommended" | [[task-18.3-offline-reclaim#open-questions]] |
| plan-22 · d9b | plan-22 (22.5) | R4's forget of rows that have no owner | — | **open, post-mod:** user-gated at 22.5 (L45) | [[task-22.5-cross-store-move]] |
| plan-20 · 20.1 | plan-20 (20.1) | The user's review of 50 labelled pairs, which freezes the pair set | — | **open, post-mod** | [[task-20.1-labelled-pair-set]] |
| plan-16 · 16.4 R4 | plan-16 (16.4) | Translate BRE metacharacters on the path-less index leg, or keep 16.5 R3's floor? | keep the floor (L32) | **conditional, post-mod:** reopened as a user question only if the queued re-measure (30 or more `bre_meta_literal` rows, or 2026-12-31) reads "translate" (L42, L49) | [[task-16.4-measurement#r4-reopen]] |
| plan-29 · 29.5 R0 | plan-29 (29.5) | A non-zero count of stamps under an unmapped pass name: wait for 29.2 R7's rehash, or release with those stamps reading `behind_code`? | — | **conditional:** arises only if R0 counts one; it then stops the task before phase 2 and goes to the user (L108) | [[task-29.5-split-giant-modules#r0]] |
| plan-10 · bands | plan-10 (10.5, 10.2) | 10.5's read-back probe in its middle band, and 10.2 R7's 5-15% band, each read "the user decides" | — | **conditional, post-mod:** only if a measurement lands in that band | [[task-10.5-versioned-block-gate]] |
{#decisions-table}

### Questions to the user {#questions}

Next id: **Q40**. Open: Q38, Q39. Each reply that asks anything ends with the ids still open.

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q38 | 2026-11-15 | plan-31 D14 says "migrate them if they can be resolved, if not, delete them". What does "resolved" mean for the 30,131 orphaned learned rows? (Split re-measured by arch-31b after the 2026-11-15 archive commit `903f7f5`, which moved two review docs that 254 orphans name; the dry run at the store event binds, since the split follows the tree.) | (a) **matched to the current entity** (concept is a `query/` concept, exactly one same-named entity of the learner's kind, file on disk): **29,824 re-attached, 307 deleted** with a manifest (11 concept gone, 42 no entity, 254 file gone); at read time only rows whose recorded line still holds the pattern are served (recommended: a learned row is a query-to-file association; a moved line is a serve-time question the line check already answers); (b) **the recorded line still holds the pattern**: **12,645 re-attached** (9,634 literal, 3,011 regex only), **17,486 deleted**. Under either reading, a file that is archived or moved takes its learned rows to the manifest | open |
| Q39 | 2026-11-15 | bug-203 (`rmx sync -i` reaches the read replica when a daemon is up) is not on the freeze line; 31.2 rewrites what `sync -i` does, and arch-31b wrote the routing fix in (AC-14). Admit it into 31.2? | (a) admit it into 31.2 (recommended: the same lines are rewritten anyway; leaving it means re-opening them after the mod); (b) cut it from 31.2, bug-203 stays post-mod | open |
{#questions-table}

## Pending bookkeeping (2026-11-15) {#pending-bookkeeping}

The POP rewrite and the archive of the alternate sources landed together on 2026-11-15 (record in [[pop-finished]]). {#pending-bookkeeping-body}

**File statuses that do not yet follow this file.** The 2026-11-15 bookkeeping pass applied the
rest (branch `bookkeeping-1115`; the applied rows are in [[pop-finished]]). Each row left has its
reason. {#pending-status}

| file | edit | why it is still here | evidence |
|---|---|---|---|
| `plan-24-mod-transport.md` | dated amends notes for D-Q5 and L128 on `#decisions`, `#phase-now` and `#phase-held`, and the citation of its `plan-24 · D1` row | **stays:** the plan-24 freshness revision writes them ([[#queue]] step 16) | L38, L128; [[#flags]] |
| `plan-31-pre-mod-loose-ends.md` | `status: drafting` → `approved` | **stays:** set in the commit that merges its specs after a ch-bsd MEH-only GO | L125 |
| `task-26.5-memory-organise-verb.md` | cite the `plan-26 · 26.5 split` row | **stays:** the split is a proposal with no ruling, and no text in the spec holds it yet | [[#decisions]] |
| `bug_registry.md` rows 164, 181, 167, 174 and the suite figures in `CLAUDE.md` | not edited by hand | **stays:** 29.1 owns them ([[#queue]] step 6) | [[task-29.1-registry-triage#root]] |

## Notes {#notes}

- A plan is **approved** only when every task in it has a written spec under
  `workflow/plans/<plan>-tasks/`.
- The Complete Plan Gate (see `CLAUDE.md`) still applies before implementing a multi-task plan.
- See `workflow/PLAN_GOVERNANCE.md` for staleness rules and the question-forcing gate.
