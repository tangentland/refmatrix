---
gmd: "0.1"
id: plan-25-cliquedb-field-report
title: "Plan 25: cliquedb's 2026-11-08 field report — recall that reaches the model, nothing injected on a bare ack, clean STM refs, a helix line said once, and grep's BRE alternation"
tags: [plan, bugs, hooks, memory-recall, scan-prompt, stm, helix, grep, cliquedb, budget]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-08
  updated: 2026-11-09
---

# Plan 25: cliquedb field report (bug-164..167) {#root}

**Date:** 2026-11-08 (session 8d9a255f).
**Status:** Drafting. Plan and task specs 25.1-25.4 written; ch-bsd spec review r1 DIRTY 0B/9S/9M
folded in revision round 1 ([[#rev-round-1]]); r2 DIRTY 0B/3S/7M folded in revision round 2
([[#rev-round-2]]); task 25.5 added for bug-174; spec review r3 is next. No `src/` or `tests/` change is made by this document.
**Location:** `workflow/plans/plan-25-cliquedb-field-report.md`; stage is `metadata.status`.
**Ordering authority:** the user's override [[plan-of-plans#override-2026-11-08]] as amended the
same day by [[plan-of-plans#override-2026-11-08b]]: task 3.7, then plan-26 (memory-layer
organisation), then plan-27 (its fleet rollout), then THIS plan, then plan-24.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[bug_registry#registry]]
rel: implements -> [[plan-of-plans#override-2026-11-08]]
rel: implements -> [[plan-of-plans#override-2026-11-08b]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: depends-on -> [[plan-26-memory-organisation]]
rel: depends-on -> [[plan-27-memory-fleet-rollout]]
rel: depends-on -> [[task-26.4-savestate-mtype-normalisation]]
rel: related-to -> [[plan-24-mod-transport]]
rel: related-to -> [[task-24.2a-hook-verbs-explicit-session]]
rel: related-to -> [[task-24.6-context-and-observation]]
rel: amends -> [[task-19.1-pack-recall-under-budget]]
rel: amends -> [[task-19.0-stm-cluster-hygiene]]
rel: amends -> [[task-19.5-measure-delivery]]
rel: derives-from -> [[bsd-plan25-spec-r1-2f4a1df]]
rel: derives-from -> [[bsd-plan25-spec-r2-5b8ed15]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_green_tests_are_not_a_working_command]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: specifies -> [[task-25.1-recall-hook-byte-budget]]
rel: specifies -> [[task-25.2-thin-prompt-gate]]
rel: specifies -> [[task-25.3-stm-ref-admission-and-helix-repeat]]
rel: specifies -> [[task-25.4-grep-bre-translation]]
rel: specifies -> [[task-25.5-substring-bre-metas]]

## Context {#context}

cliquedb's session filed five observations on `proj:refmatrix:bugs` (bus `ae9c57ed7f13`) and a
priority order (bus `fb3fefdff19b`). Item 1 (rerank timeout) closed as bug-162 in 0.80.2. The other
four are [[bug_registry#registry]] rows bug-164..bug-167, all `open`. The consumer's verdict is the
reason this plan exists: "I navigated by known paths and direct reads, not rmx_context. The injected
hook context costs tokens on every turn and rarely changes what I do." {#context-lead}

Measured on deployed 0.80.2 against the cliquedb store, read-only (session 8d9a255f):

| bug | what was measured |
|---|---|
| bug-164 | per-prompt recall hook (`hooks.py:331-336`) on "yes next" → 29,151 B, 5 rows, bodies 2.0-8.7 KB plus 430-600 B metadata each; a real question → 16,647 B; SessionStart `--session-start --k 10` → 7,011 B. Over ~10k chars the model gets a ~2 KB preview ([[reference_hook_output_10k_cap]]), so the per-prompt recall effectively never arrives. `savestate_7c4e19d2a8f3` came back with mtype `project`: its FILE is hand-authored with `metadata.type: project` (read 2026-11-08; 4 of cliquedb's savestate files carry it), so the hook-mode `session/*` exclusion cannot see it. |
| bug-165 | "a - next", "yes next", "i - next" get ~500 tokens of unrelated savestate «NEXT» content hits from scan-prompt AND the largest recall payload. Under `terms.STOPWORDS` "yes", "a", "i" are stopwords and "next" is not. |
| bug-166 | (a) refs `S/as.sh`, `s.repla`, `s.count`, `cliquedb.pk`, `pk8a.kitem` in the STM composite. `stm._PATH_RE` = `[\w./-]+\.[A-Za-z]{1,5}` (`stm.py:55`) has no right boundary, so `s.replace(` matches as `s.repla` and `re.search(` as `re.searc`; it runs over the whole Bash command at `cli._tool_event_fields` (`cli.py:2012`) and over prose at `stm._extract_refs` (`stm.py:2006`). (b) helix (`helix.annotate`, `helix.py:307-345`) re-emits `docs/adr32-35_chat_history.md: last worked 2026-06-30 (131d ago)` on nearly every prompt; nothing remembers that a session has already been told. |
| bug-167 | `cli.py:6407-6419` raises `UsageError` (exit 2) on any `\|`, `\(`, `\{` in substring mode. macOS `/usr/bin/grep` (BSD grep 2.6.0-FreeBSD, "GNU compatible") and GNU grep (`/opt/local/bin/ggrep`) both accept `\|`, `\+`, `\?`, `\(…\)`, `\{n\}` in BRE (probed 2026-11-08). |

## Two of these are already specified, and that decides the shape of the plan {#prior-specs}

bug-164 is the problem plan-19 task 19.1 was written for, and bug-166(a) is task 19.0 R1 (bug-104)
reached through a second admission site. Both specs are APPROVED (2026-10-15) and unbuilt. Writing
a second packer or a second command-ref extractor here would be the "two ways to do X" failure
this repo keeps paying for ([[feedback_converge_repeated_shapes]]). So: {#prior-specs-lead}

- **25.1 BUILDS 19.1's packer** under the override, with the deltas in [[#deltas]], instead of
  specifying a new one. 19.1's requirement text is the contract; 25.1 lists which of its
  requirements land here, which are amended, and which stay with 19.1.
- **25.3 BUILDS 19.0 R1's ref admission** (the `stm.command_refs` function and its code-noise
  set) and extends the same predicate to the prose path. 19.0 R0, R2-R7 (subagents, hand-backs,
  typos, the resolver, the fixture, the pre-prompt snapshot) stay with 19.0.
- 19.0, 19.1 and 19.5 carry a revision row NOW (2026-11-09, bsd r1 #m9) naming which of their
  requirements 25.1 / 25.3 realize, so no builder follows their stale text.

### Deltas from plan-19 {#deltas}

| plan-19 text | plan-25 change | why |
|---|---|---|
| 19.1 R1: one `DEFAULT_HOOK_BUDGET_BYTES` (9,500) | one budget module `hook_budget` with 21.1's channel names: `prompt_recall` 4,000 B, `scan_prompt` 5,000 B, `session_start` 9,000 B, `precompact` 9,000 B (PROVISIONAL), plus an `EVENT_SPLIT` over all four UserPromptSubmit producers, set by one of R0's three outcomes | UserPromptSubmit shares the model's input with scan-prompt (`--max-tokens 2000` plus a composite) and the focus input hook; a per-event cap would sink a 9,500 B recall. cliquedb asked for "under ~4KB". |
| 19.1 files: the packer in `cli.py` | the packer in a library module the verb calls (`recall_pack.py` over `hook_budget.fit_blocks`); `verbs.memory_recall` takes `max_bytes` / `pack`; the per-prompt hybrid replica-first leg moves INTO the verb so the CLI only renders | the user's override: budgeting is verb-side logic the mod reuses; plan-24's mod calls `rmx_memory_recall` ([[task-24.6-context-and-observation]]) and must get the same pack. |
| 19.1 depends on 19.5 R1 (the probe) | 25.1 R0 RUNS that probe as its first step | 19.5 R1 depends on nothing and was never run (no file under `workflow/measurements/`). |
| 19.1 R2 (subjects) | kept; the mis-typed save-state half of bug-164 is OWNED by [[task-26.4-savestate-mtype-normalisation]] and only re-asserted on the packed path ([[task-25.1-recall-hook-byte-budget#r2b]]) | one owner for the bridge rule; plan-26 lands first |
| 19.0 R1: `command_refs(cmd)` for the tool path | `command_refs(cmd, *, root=None, cwd=None)` (shape-only when `root=None`, the form 19.0's rebuild calls); plus the prose path, a right boundary on `_PATH_RE`, and an existence check for every path-shaped candidate | the junk cliquedb saw comes through both sites |
| (none) | scan-prompt is byte-capped through the same fitter (25.1 R0b) | it reaches 11,555 B on its own (21.1 telemetry) |

## Proposed approach {#approach}

### One principle: the gate and the budget are verbs' business, the hook is an argv {#principle}

Every rule this plan adds is a pure function in a library module, called by the verb layer and by
the CLI twin, never written into `cli.py` or into a hook string:

- the byte budget and the packer: `hook_budget` + `recall_pack` (25.1), reached through
  `verbs.memory_recall`, whose rows now include the root-explicit replica-first leg for EVERY
  caller (hooks, MCP, the interactive CLI: one computation of "which rows"); every rmx
  UserPromptSubmit producer, curator status included, is fitted by the same
  `hook_budget.fit_blocks`, budgeted per generated hook command;
- the ack-only gate: `terms.prompt_gate` next to the stoplist it reuses (25.2), called by
  `scan.scan_prompt` (which 24.2a R4's `rmx_scan_prompt` wraps) and by the recall verb's
  prompt trigger;
- the ref admission predicate: `stm.admit_ref` / `stm.command_refs` (25.3), called by both
  extraction sites and the focus rebuild;
- the helix repeat memory and hub rule: `helix` with an explicit session (25.3), the shape 24.2a R2
  requires;
- the BRE translation: one function `grep_dialect.bre_to_py` (25.4) that every grep leg reads.

When plan-24's mod lands, it calls the same verbs with its own budget (the mod has no 10k cap,
[[plan-24-mod-transport#goals]] G2) and gets the same gate and the same pack. Nothing here is
throwaway shell-surface work. {#principle-tail}

### Ordering and dependencies {#ordering}

```
3.7 ──► plan-26 ──► plan-27 ──► 25.1 ──► 25.2 ──► 25.3 ──► (plan-24)
                                 25.4 (independent of 26/27 and of 25.1-25.3; any slot after 3.7)
```

- **plan-26 / plan-27 before 25.1** (the amendment). 26.4 makes a save-state's mtype
  `session/recall-state` at the bridge, which removes the mis-typed save-state from recall before
  25.1 packs it; 26.7 regroups `MEMORY.md`, which 25.1's pack reads for curated hooks (19.1 R3(b));
  27 migrates cliquedb's dir last, so the live after-check on cliquedb runs on the organised dir.
  25.4 does not touch the memory layer and need not wait for 26/27; the recommendation is still
  to run it in the plan-25 slot so the release that closes cliquedb's report closes all four rows.
- **3.7 first** (the override). Its branch (`task-3.7-verb-it-backlog`, clone
  `/Volumes/littlebig/refmatrix-task-3.7`, HEAD `3281c53`, base `591a2fb`) touches files this plan
  edits; see [[#overlap]]. Every 25.x branch is cut from `master` AFTER 3.7 merges.
- **25.1 before 25.2.** 25.1 moves the per-prompt rows into the verb, where 25.2's gate lives, and
  both edit the hook generator. 25.2's after-measurement is taken on 25.1's packed payload, so its noise number
  is about the gate, not about an overflow that already hid the noise.
- **25.2 owns the gate helper**; 25.1 does not need it. 25.2's gate decides whether recall RUNS;
  25.1's budget decides how much of what ran is SAID. They compose; neither reads the other's
  constants.
- **25.3 after 25.2** for one reason: both change what scan-prompt emits, and 25.3's helix ACs
  need prompts that pass 25.2's gate (a bare ack no longer reaches helix at all). 25.3's STM half
  has no dependency and may be built in parallel in its own clone.
- **25.4 is independent** (`cli.py` grep block only, plus a new module). It may land in any slot
  after 3.7. **25.5 follows 25.4** (it reuses the translator and the entry point) and carries a
  pre-registered measurement before its index-leg decision.

### File overlap with task 3.7 (3.7 merges first) {#overlap}

Read 2026-11-08 by `git diff 591a2fb 3281c53 --stat -- src` in the 3.7 clone.

| file | 3.7 changes | plan-25 task | conflict risk |
|---|---|---|---|
| `src/refmatrix/hooks.py` | `HOOK_ENV` gains the two fork-safety exports; curator `status --drain 2>/dev/null` → `status \|\| true` in the scan-prompt and SessionStart commands, so `curator status` now prints on EVERY prompt in the UserPromptSubmit event (counted in 25.1's `EVENT_SPLIT`) | 25.1 (recall argv), 25.2 (none expected), 25.3 (none) | textual: `HOOK_ENV` also changed on master (bug-163 PATH prefix, 0.80.2) — 3.7's merge resolves that, 25.1 rebases on the result. `install-hooks --check` golden files move twice. |
| `src/refmatrix/cli.py` | 1,675 lines: many read commands become verb adapters (`top`, `describe`, `focus *`, `curator`, `recall_cmd`'s embedder path, `scan_prompt_cmd` neighbourhood, `_stamp_derive_pass`) | 25.1 (`memory recall` render / exclusion), 25.2 (`scan_prompt_cmd` envelope → gate), 25.3 (`_tool_event_fields`), 25.4 (grep BRE block) | no hunk of 3.7 touches `_memory_recall_impl`, `_tool_event_fields` or the grep BRE block; `scan_prompt_cmd` is adjacent to a 3.7 hunk. Line numbers in these specs are master's and WILL move. |
| `src/refmatrix/verbs.py` | +1,290: `focus` dispatcher, `curator`, `graph`, `session_memories`, `snapshot_read` / `local_write` | 25.1 (`memory_recall` gains `max_bytes` / `pack`), 25.2 (recall gate) | `memory_recall` itself is not in 3.7's diff; the module grows around it. |
| `src/refmatrix/recall.py` | +325: `shared_embedder`, `_process_embed_client`, `graph_recall`, `ann_search` (embed-client code) | 25.1 moves `_replica_memory_recall` here (d5), beside `shared_embedder` | none textual; 25.1's fixture runs dense recall through 3.7's embed client, so its RED is taken after 3.7 merges. |
| `src/refmatrix/stm.py`, `scan.py`, `helix.py`, `terms.py`, `context.py` | not touched | 25.2, 25.3 | none |
| `workflow/bug_registry.md` | adds bug-171 and bug-173 (an in-process `Embedder()` per daemonless call, cited in 3.7's `recall.py` and `tests/test_task3_7_remedy_r4.py`) | 25.4 / 25.5 close bug-167 / bug-174; plan-25's rg-fallback note is bug-180 | id collision removed in r3 (#s4): plan-25's row, logged 11 minutes after 3.7's, was renumbered bug-173 → bug-180 on master before 3.7 merges; the merge still conflicts textually at the table tail (append-only, keep both sides) |
| `tests/test_verb_parity.py`, `tests/transport_guard.py` | 3.7 rewrites both | 25.1 / 25.2 add verb params (parity rows) | additive after 3.7 |

### File overlap with plan-26 (plan-26 merges first) {#overlap-26}

Read from the plan-26 task specs' file lists on 2026-11-08 (drafts; re-read at 25.1's start).

| file | plan-26 task | plan-25 task | note |
|---|---|---|---|
| `src/refmatrix/ingest_gmd.py` | 26.2, 26.4 (mtype resolution ~`:943`) | none (25.1 no longer edits it) | 25.1 re-asserts 26.4's rule; no edit |
| `src/refmatrix/memory_index.py` | 26.1, 26.3, 26.7 (index by subject) | 25.1 (export the curated-hook lookup for the pack) | 25.1 reads whatever 26.7 leaves; it must not re-parse `MEMORY.md` itself |
| `src/refmatrix/cli.py` | 26.2 / 26.4 (`_bridge_stats`), 26.5, 26.6 | 25.1, 25.2, 25.3, 25.4 | different functions; line numbers move |
| `src/refmatrix/verbs.py`, `mcp.py` | 26.5 (`memory organise` verb) | 25.1, 25.2 (recall params) | additive |
| `src/refmatrix/handoff.py` | 26.3 (savestates/ subfolder), 26.7 | none | 25.1's fixture places its save-state where 26.3 puts them |
| `src/refmatrix/consolidate.py`, `store.py`, `daemon.py` | 26.6 (subject hygiene), 26.7 | none | 19.1 R2's subject exclusion is independent of 26.6's label quality |

### What this plan will NOT do {#non-goals}

- **No ranking change.** bug-165's noise is attacked by not running retrieval on a thin prompt,
  not by retuning BM25 / rerank. Rerank works again (bug-162); 25.2 measures noise WITH it.
- **No mod work.** The verbs gain parameters the mod will pass; the mod itself is plan-24.
- **No plan-19 completion beyond 19.1 and 19.0 R1.** 19.0 R0, R2-R7, the 19.1 folded riders and
  19.2-19.6 stay in plan-19. 25.1 lists which 19.1 items it lands (all R1-R8 and their ACs and
  mutations, with the deltas).
- **`# rmx grep fallback via rg`** (cliquedb item 5) is a stderr line (`cli.py:6901`), not stdout;
  it is logged as bug-180 (split from bug-167 on 2026-11-09 as bug-173, renumbered in r3 because
  the task-3.7 branch owns bug-173) and stays open when 25.4 closes
  bug-167. Substring-mode `a.b` (bug-174) is IN scope as task 25.5 (orchestrator 2026-11-09).
- **No raw cliquedb prompt or memory text is committed.** Every fixture is synthetic, shaped to the
  measured sizes ([[feedback_no_raw_prompts_in_public_repo]]).

## Task list {#tasks}

| task | bug | what | RED on |
|---|---|---|---|
| [[task-25.1-recall-hook-byte-budget]] | bug-164 | probe the cap (three outcomes); per-prompt rows through the verb; pack recall pointers-first after the merge; byte-cap scan-prompt; every UserPromptSubmit producer in one event budget | the generated per-prompt argv emits > 10,000 B on the fixture store |
| [[task-25.2-thin-prompt-gate]] | bug-165 | one ack-only gate: a prompt made only of stopwords / ack words / list markers → scan-prompt and the prompt recall inject nothing; a single content word passes | the generated scan-prompt + recall argvs on "yes next" emit > 0 B of content hits |
| [[task-25.3-stm-ref-admission-and-helix-repeat]] | bug-166 (both halves) | one ref-admission predicate at both extraction sites and the rebuild; helix says a line once per session, never annotates a hub neighbour, and logs every suppression | a replayed `focus hook` envelope stores `s.repla`; a second identical prompt re-emits the helix line |
| [[task-25.4-grep-bre-translation]] | bug-167 | any backslash-escaped BRE translated once for every grep leg; anything not provably the same language (compile failure, stacked quantifier, locale-inexact class) to the real grep; differential tests against BSD and GNU grep in two locales |
| [[task-25.5-substring-bre-metas]] | bug-174 | unescaped `. * [ ^ $` read as BRE on the drop-in legs via 25.4's translator; the index leg decided by a pre-registered count of changed real calls | `rmx grep 'a.b' file` misses `axb` | `rmx grep -n 'B0\|group_key' file` exits 2 |

## Acceptance for the plan {#acceptance}

- bug-164..167 reach `fixed` with the mechanism named, and bug-174 reaches `fixed` or stays open
  with its measured band (25.5 R5), each verified on the deployed build against
  the cliquedb store (read-only, sizes only, nothing copied into the repo) after the release.
- Each task: RED recorded on the generated hook argv or the CLI (the production path), GREEN
  recorded, at least one mutation per new guard that FAILS a test, implementation summary.
- `rmx install-hooks --check` clean; verb parity green (every new verb parameter has its CLI twin).
- The before/after table per hook (bytes per invocation on the frozen fixture store) is in the
  implementation summaries and in `workflow/measurements/plan-25-hook-bytes.md`.
- A bus reply on `proj:refmatrix:bugs` to `ae9c57ed7f13` once deployed (it cites the fallback note
  as bug-180, never bug-173), so cliquedb can verify
  next session (their offer, `fb3fefdff19b`).
- `@ch-bsd` over the plan's commit range, remedied to CLEAN.

## Open decisions {#open-decisions}

Recorded with a recommendation; each task spec repeats the ones it owns.

| # | decision | recommendation |
|---|---|---|
| q1 | Pull 19.1 / 19.0 R1 forward into plan-25 (build them here) or write independent fixes | pull forward ([[#prior-specs]]); a second packer is the defect shape this repo keeps fixing |
| q2 | Per-prompt recall budget before the probe | 4,000 B provisional (`scan_prompt` 5,000 B); R0's outcome (A / B / C) replaces both before GREEN |
| q3 | Fix for mis-typed save-states | settled by plan-26: the bridge normalises (26.4); 25.1 re-asserts on the packed path and adds no second rule |
| q4 | Does the thin-prompt gate also suppress the STM composite | no: the composite is session-derived, not prompt-derived, and keeps its own `--composite-every` cadence; measured in 25.2 AC-5 |
| q5 | `ACK_WORDS` beside the stoplist, and how aggressive the gate is | decided 2026-11-09: `ACK_WORDS` applied IN ADDITION to the stoplist; gate ACK-ONLY prompts only; a single content word or an issue / task number is never gated |
| q6 | Helix repeat memory: sidecar file or derive from `helix.log` | sidecar `stm/<session>.helix.json`, the existing per-session sidecar pattern |
| q7 | The helix phase-2 criterion's reading after dedupe | decided 2026-11-09: `rendered + suppressed` (both logged), `rendered` reported beside it, until a new pre-registered criterion supersedes it |
| q8 | The hub neighbour behind the repeated helix line | decided 2026-11-09: fixed in 25.3 (R8), not parked |

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan25-spec-r1-2f4a1df]] (DIRTY 0B/9S/9M at `2f4a1df`) with the orchestrator's
decisions of 2026-11-09. Every finding is folded; per-task detail is in each spec's own
revision-round-1 table.

| finding | change | anchor |
|---|---|---|
| S1 per-prompt argv never reaches the verb | (a): the replica-first hybrid leg moves into `verbs._memory_recall_rows`; the CLI renders; AC-4 restated with a RED-able replica leg and a named no-daemon error | [[#principle]], [[#deltas]], [[task-25.1-recall-hook-byte-budget#r5]] |
| S2 dropped 19.1 ACs / mutations | all carried into 25.1 (stale subject, span pre-check, global pointer, twelve mutations) | [[task-25.1-recall-hook-byte-budget#rev-round-1]] |
| S3 no per-event branch; scan-prompt overflows | R0 three outcomes; `EVENT_SPLIT` over scan-prompt + recall + focus input + 3.7's `curator status`; scan-prompt byte cap | [[#deltas]], [[#overlap]], [[task-25.1-recall-hook-byte-budget#r0]] |
| S4 false gates | ack-only gate; the bsd's measured false-gate set as must-pass rows; gate rate re-measured | [[#tasks]], q5, [[task-25.2-thin-prompt-gate#rev-round-1]] |
| S5 unkillable boundary mutation | `docs/notes.md5sum` witness; `S/as.sh` as the existence witness | [[task-25.3-stm-ref-admission-and-helix-repeat#rev-round-1]] |
| S6 criterion reading | `rendered + suppressed` | q7, [[task-25.3-stm-ref-admission-and-helix-repeat#r9]] |
| S7 hub neighbour parked | in-plan: 25.3 R8 + AC-9 | q8, [[#tasks]] |
| S8 / S9 BRE coverage and rule errors | trigger on any backslash; full escape set; bracket, word-anchor, `-o`, `-w`/`-x` grouping rules; BSD as authority on `\{,n\}` | [[#principle]], [[task-25.4-grep-bre-translation#rev-round-1]] |
| M1 / M2 / M3 | pointers-only per-prompt pack; `prompt_recall` everywhere; `hooks` map into `pack` | [[task-25.1-recall-hook-byte-budget#rev-round-1]] |
| M4 / M5 / M6 / M7 | `_PATH_RE` users and the `overlap` instrument; failure on the row; resolver reuse; existence check replaces the extension list | [[task-25.3-stm-ref-admission-and-helix-repeat#rev-round-1]] |
| M8 out-of-scope items need rows | bug-167 split: bug-173 (fallback note; renumbered bug-180 in r3), bug-174 (substring `a.b`) logged 2026-11-09 | [[#non-goals]], [[bug_registry#registry]] |
| M9 plan-19 revision rows now | rows added to 19.0, 19.1, 19.5 | [[#prior-specs]] |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan25-spec-r2-5b8ed15]] (DIRTY 0B/3S/7M at `5b8ed15`) with the orchestrator's
decisions of 2026-11-09. Per-task detail is in each spec's revision-round-2 table.

| finding | change | anchor |
|---|---|---|
| S1 MCP / CWD / interactive path | root-explicit `recall.replica_memory_recall(root, …)`; MCP and interactive recall through the verb; `kind=doc` leg owned by 25.1; replica lag accepted | [[#principle]], [[task-25.1-recall-hook-byte-budget#rev-round-2]] |
| S2 budget unit | per generated hook command; every rmx producer hard-capped; non-rmx reserve measured | [[#principle]], [[task-25.1-recall-hook-byte-budget#r0]] |
| S3 BRE rules vs both greps | `-w` word-constituent rule; compile failures and stacked quantifiers untranslatable; locale-aware classes; divergence table | [[#tasks]], [[task-25.4-grep-bre-translation#rev-round-2]] |
| M1 / M2 / M3 | no-daemon hook: exit 0, counted `degraded` (decision d8); body fetch named; 19.1 AC-6 global leg | [[task-25.1-recall-hook-byte-budget#rev-round-2]] |
| M4 `where are we` | not gated; AC-3 row | [[task-25.2-thin-prompt-gate#rev-round-2]] |
| M5 / M6 / M7 | suppressed notes count toward the neighbour cap; p99 over all linked entities; "head" defined | [[task-25.3-stm-ref-admission-and-helix-repeat#rev-round-2]] |
| U6 bug-174 unscheduled | task 25.5 added | [[#tasks]], [[#non-goals]], [[task-25.5-substring-bre-metas]] |
