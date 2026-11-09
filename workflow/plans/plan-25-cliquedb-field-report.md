---
gmd: "0.1"
id: plan-25-cliquedb-field-report
title: "Plan 25: cliquedb's 2026-11-08 field report — recall that reaches the model, nothing injected on a bare ack, clean STM refs, a helix line said once, and grep's BRE alternation"
tags: [plan, bugs, hooks, memory-recall, scan-prompt, stm, helix, grep, cliquedb, budget]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-08
  updated: 2026-11-08
---

# Plan 25: cliquedb field report (bug-164..167) {#root}

**Date:** 2026-11-08 (session 8d9a255f).
**Status:** Drafting. Plan and task specs 25.1-25.4 written; spec review (`@ch-bsd`, `@ch-architect`)
is next. No `src/` or `tests/` change is made by this document.
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
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_green_tests_are_not_a_working_command]]
rel: reinforces -> [[feedback_no_raw_prompts_in_public_repo]]
rel: reinforces -> [[feedback_reuse_shared_stoplist]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: specifies -> [[task-25.1-recall-hook-byte-budget]]
rel: specifies -> [[task-25.2-thin-prompt-gate]]
rel: specifies -> [[task-25.3-stm-ref-admission-and-helix-repeat]]
rel: specifies -> [[task-25.4-grep-bre-translation]]

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
- When 25.1 / 25.3 merge, 19.0 and 19.1 get a revision row naming what was realized here
  (a doc edit done at merge time, not in this draft).

### Deltas from plan-19 {#deltas}

| plan-19 text | plan-25 change | why |
|---|---|---|
| 19.1 R1: one `DEFAULT_HOOK_BUDGET_BYTES` (9,500) | a per-channel table, one owner: `prompt` 4,000 B, `session_start` 9,000 B, `precompact` 9,000 B (PROVISIONAL until 25.1 R0's probe) | UserPromptSubmit shares the model's input with scan-prompt (`--max-tokens 2000` plus a composite) and the focus input hook; a per-event cap would sink a 9,500 B recall. cliquedb asked for "under ~4KB". |
| 19.1 files: the packer in `cli.py` | the packer in a library module the verb calls (`recall_pack.py`); `verbs.memory_recall` takes `max_bytes` / `pack` | the user's override: budgeting is verb-side logic the mod reuses; plan-24's mod calls `rmx_memory_recall` ([[task-24.6-context-and-observation]]) and must get the same pack. |
| 19.1 depends on 19.5 R1 (the probe) | 25.1 R0 RUNS that probe as its first step | 19.5 R1 depends on nothing and was never run (no file under `workflow/measurements/`). |
| 19.1 R2 (subjects) | kept; the mis-typed save-state half of bug-164 is OWNED by [[task-26.4-savestate-mtype-normalisation]] and only re-asserted on the packed path ([[task-25.1-recall-hook-byte-budget#r2b]]) | one owner for the bridge rule; plan-26 lands first |
| 19.0 R1: `command_refs` for the tool path | plus the prose path (`_extract_refs`), plus a right boundary on `_PATH_RE`, plus existence for slash refs | the junk cliquedb saw comes through both sites |

## Proposed approach {#approach}

### One principle: the gate and the budget are verbs' business, the hook is an argv {#principle}

Every rule this plan adds is a pure function in a library module, called by the verb layer and by
the CLI twin, never written into `cli.py` or into a hook string:

- the byte budget and the packer: `recall_pack` (25.1), reached through `verbs.memory_recall`;
- the thin-prompt gate: `terms.prompt_gate` next to the stoplist it reuses (25.2), called by
  `scan.scan_prompt` (which 24.2a R4's `rmx_scan_prompt` wraps) and by the recall verb's
  prompt trigger;
- the ref admission predicate: `stm.admit_ref` / `stm.command_refs` (25.3), called by both
  extraction sites and the focus rebuild;
- the helix repeat memory: `helix` with an explicit session (25.3), the shape 24.2a R2 requires;
- the BRE translation: one function `grep_dialect.bre_to_ere` (25.4) that every grep leg reads.

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
- **25.1 before 25.2.** Both edit the per-prompt recall path in `cli._memory_recall_impl` and the
  hook generator. 25.2's after-measurement is taken on 25.1's packed payload, so its noise number
  is about the gate, not about an overflow that already hid the noise.
- **25.2 owns the gate helper**; 25.1 does not need it. 25.2's gate decides whether recall RUNS;
  25.1's budget decides how much of what ran is SAID. They compose; neither reads the other's
  constants.
- **25.3 after 25.2** for one reason: both change what scan-prompt emits, and 25.3's helix ACs
  need prompts that pass 25.2's gate (a bare ack no longer reaches helix at all). 25.3's STM half
  has no dependency and may be built in parallel in its own clone.
- **25.4 is independent** (`cli.py` grep block only, plus a new module). It may land in any slot
  after 3.7.

### File overlap with task 3.7 (3.7 merges first) {#overlap}

Read 2026-11-08 by `git diff 591a2fb 3281c53 --stat -- src` in the 3.7 clone.

| file | 3.7 changes | plan-25 task | conflict risk |
|---|---|---|---|
| `src/refmatrix/hooks.py` | `HOOK_ENV` gains the two fork-safety exports; curator `status --drain 2>/dev/null` → `status \|\| true` in the scan-prompt and SessionStart commands | 25.1 (recall argv), 25.2 (none expected), 25.3 (none) | textual: `HOOK_ENV` also changed on master (bug-163 PATH prefix, 0.80.2) — 3.7's merge resolves that, 25.1 rebases on the result. `install-hooks --check` golden files move twice. |
| `src/refmatrix/cli.py` | 1,675 lines: many read commands become verb adapters (`top`, `describe`, `focus *`, `curator`, `recall_cmd`'s embedder path, `scan_prompt_cmd` neighbourhood, `_stamp_derive_pass`) | 25.1 (`memory recall` render / exclusion), 25.2 (`scan_prompt_cmd` envelope → gate), 25.3 (`_tool_event_fields`), 25.4 (grep BRE block) | no hunk of 3.7 touches `_memory_recall_impl`, `_tool_event_fields` or the grep BRE block; `scan_prompt_cmd` is adjacent to a 3.7 hunk. Line numbers in these specs are master's and WILL move. |
| `src/refmatrix/verbs.py` | +1,290: `focus` dispatcher, `curator`, `graph`, `session_memories`, `snapshot_read` / `local_write` | 25.1 (`memory_recall` gains `max_bytes` / `pack`), 25.2 (recall gate) | `memory_recall` itself is not in 3.7's diff; the module grows around it. |
| `src/refmatrix/recall.py` | +325: `shared_embedder`, `_process_embed_client`, `graph_recall`, `ann_search` (embed-client code) | 25.1 does not edit it; it CALLS whatever recall uses after 3.7 | none textual; 25.1's fixture runs dense recall through 3.7's embed client, so its RED is taken after 3.7 merges. |
| `src/refmatrix/stm.py`, `scan.py`, `helix.py`, `terms.py`, `context.py` | not touched | 25.2, 25.3 | none |
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
- **No plan-19 completion.** 19.1 R6 (`memory get --scope`), R8's `delivered` spans beyond what
  the pack must return, 19.2-19.6 stay in plan-19. 25.1 lists exactly which 19.1 requirements it
  lands.
- **`# rmx grep fallback via rg`** (cliquedb item 5) is a stderr line (`cli.py:6901`,
  `click.echo(..., err=True)`), not stdout; whether the index answers plain literals is a separate
  question (plan-14 / plan-16 measure it). Out of scope; 25.4 records the observation only.
- **No raw cliquedb prompt or memory text is committed.** Every fixture is synthetic, shaped to the
  measured sizes ([[feedback_no_raw_prompts_in_public_repo]]).

## Task list {#tasks}

| task | bug | what | RED on |
|---|---|---|---|
| [[task-25.1-recall-hook-byte-budget]] | bug-164 | probe the cap; pack recall under a per-channel byte budget after the four-source merge; mis-typed save-states excluded | the generated per-prompt argv emits > 10,000 B on the fixture store |
| [[task-25.2-thin-prompt-gate]] | bug-165 | one gate: < 2 content terms and no identifier-shaped token → scan-prompt and the prompt recall inject nothing | the generated scan-prompt + recall argvs on "yes next" emit > 0 B of content hits |
| [[task-25.3-stm-ref-admission-and-helix-repeat]] | bug-166 | one ref-admission predicate at both extraction sites and the rebuild; helix says a line once per session, counting what it suppressed | a replayed `focus hook` envelope stores `s.repla`; a second identical prompt re-emits the helix line |
| [[task-25.4-grep-bre-translation]] | bug-167 | BRE → ERE translation feeding every grep leg; differential tests against BSD and GNU grep | `rmx grep -n 'B0\|group_key' file` exits 2 |

## Acceptance for the plan {#acceptance}

- bug-164..167 reach `fixed` with the mechanism named, each verified on the deployed build against
  the cliquedb store (read-only, sizes only, nothing copied into the repo) after the release.
- Each task: RED recorded on the generated hook argv or the CLI (the production path), GREEN
  recorded, at least one mutation per new guard that FAILS a test, implementation summary.
- `rmx install-hooks --check` clean; verb parity green (every new verb parameter has its CLI twin).
- The before/after table per hook (bytes per invocation on the frozen fixture store) is in the
  implementation summaries and in `workflow/measurements/plan-25-hook-bytes.md`.
- A bus reply on `proj:refmatrix:bugs` to `ae9c57ed7f13` once deployed, so cliquedb can verify
  next session (their offer, `fb3fefdff19b`).
- `@ch-bsd` over the plan's commit range, remedied to CLEAN.

## Open decisions {#open-decisions}

Recorded with a recommendation; each task spec repeats the ones it owns.

| # | decision | recommendation |
|---|---|---|
| q1 | Pull 19.1 / 19.0 R1 forward into plan-25 (build them here) or write independent fixes | pull forward ([[#prior-specs]]); a second packer is the defect shape this repo keeps fixing |
| q2 | Per-prompt recall budget before the probe | 4,000 B provisional; 25.1 R0's probe replaces it before GREEN |
| q3 | Fix for mis-typed save-states | settled by plan-26: the bridge normalises (26.4); 25.1 re-asserts on the packed path and adds no second rule |
| q4 | Does the thin-prompt gate also suppress the STM composite | no: the composite is session-derived, not prompt-derived, and keeps its own `--composite-every` cadence; measured in 25.2 AC-5 |
| q5 | Add an `ACK_WORDS` set beside the stoplist ("next", "ok", "continue", "go", "please") | yes, applied IN ADDITION to `_PROMPT_STOPWORDS` per [[feedback_reuse_shared_stoplist]]; otherwise "please continue" passes a 2-term gate |
| q6 | Helix repeat memory: sidecar file or derive from `helix.log` | sidecar `stm/<session>.helix.json`, the existing per-session sidecar pattern |
