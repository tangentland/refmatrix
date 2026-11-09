---
gmd: "0.1"
id: task-25.1-recall-hook-byte-budget
title: "Task 25.1: per-prompt recall goes through the verb, and every UserPromptSubmit / SessionStart producer fits a UTF-8 byte budget set by a measured delivery cap; recall packs pointers-first after the four-source merge (bug-164; builds task 19.1)"
tags: [task, plan-25, bug-164, memory-recall, scan-prompt, hooks, budget, pack, verbs, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-09
---

# Task 25.1: recall hook byte budget {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08; revision rounds 1-3 2026-11-09, [[#rev-round-1]],
> [[#rev-round-2]], [[#rev-round-3]]; r3 folded, a short r4-lite confirm is next)
> Bug: bug-164 (cliquedb priority 1)
> Depends on: task 3.7 MERGED to `master` ([[plan-25-cliquedb-field-report#overlap]]); plan-26
> merged (its 26.4 owns the save-state mtype fix this task re-asserts on the packed path, and its
> 26.7 regroups `MEMORY.md`, which R3's curated-hook lookup reads); 23.0's
> test sandbox (completed 0.79.1); 21.1's single `delivered` emission site (released 0.80.0).
> Builds: [[task-19.1-pack-recall-under-budget]] R1-R8 with the deltas in [[#deltas]]; runs
> [[task-19.5-measure-delivery]] R1 (the probe) as R0.

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: depends-on -> [[task-26.4-savestate-mtype-normalisation]]
rel: depends-on -> [[task-26.7-memory-index-by-subject]]
rel: realizes -> [[task-19.4-keep-derived-layers-current]]
rel: related-to -> [[task-26.6-compile-subject-hygiene]]
rel: realizes -> [[task-19.1-pack-recall-under-budget#requirements]]
rel: amends -> [[task-19.1-pack-recall-under-budget]]
rel: realizes -> [[task-19.5-measure-delivery]]
rel: derives-from -> [[bug_registry#registry]]
rel: derives-from -> [[bsd-plan25-spec-r1-2f4a1df]]
rel: derives-from -> [[bsd-plan25-spec-r2-5b8ed15]]
rel: derives-from -> [[bsd-plan25-spec-r3-2f64edb]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: related-to -> [[project_recall_hook_savestate_noise_fix]]
rel: related-to -> [[task-24.2a-hook-verbs-explicit-session]]
rel: related-to -> [[task-24.6-context-and-observation]]

## Why {#why}

The per-prompt recall hook (`hooks.py:331-336`, `rmx memory recall --stdin-json --k 5 --scope both
--json --timeout 5`) delivers almost nothing. 21.1's `recall-events.jsonl` (byte counts only, read
by [[bsd-plan25-spec-r1-2f4a1df#probes]]) gives this baseline: {#why-lead}

| store | channel | p50 / p90 / max | over 10 kB |
|---|---|---|---|
| refmatrix | `prompt_recall` | 15,445 / 19,037 / 30,679 B | 102 of 130 |
| refmatrix | `scan_prompt` | 7,205 / 9,787 / 11,555 B | 9 of 138 |
| refmatrix | `session_start` | 24,680 B | — |
| cliquedb | `prompt_recall` | 22,258 / 28,622 / 59,196 B | 123 of 129 |
| cliquedb | `scan_prompt` | max 7,511 B | — |
| cliquedb | `session_start` | 35,395 B | — |

Claude Code passes hook output whole only up to ~10k characters and shows a ~2 KB preview beyond
that ([[reference_hook_output_10k_cap]]). So the hook cliquedb most wants working arrives as a
preview on 95% of prompts. scan-prompt, its sibling on the same event, also overflows on its own
(`--max-tokens 2000` is a token count, not a byte cap).

Three code facts shape the fix (read at `fbee6c9`):

- **The per-prompt argv never reaches the verb.** `--stdin-json` takes the hybrid branch of
  `cli._memory_recall_impl` (`cli.py:12526-12755`). That branch tries `_replica_memory_recall`
  first (`cli.py:11347`: replica slot plus the hub's shared model workers) and falls back to the
  daemon `memory_recall` RPC. `verbs.memory_recall` (`verbs.py:908`, rows in
  `_memory_recall_rows` `:961`) has its own dense leg (`verbs.py:1054-1077`) that never tries the
  replica. Two computations of "which rows" for one question: the sixth sighting of that shape
  ([[bsd-plan25-spec-r1-2f4a1df#s1]]). With no daemon and no replica + workers, the CLI raises
  "needs the daemon up …" (`cli.py:12570-12574`).
- **The budget must hold after the merge.** A hook-mode call merges rows from the replica or
  daemon dense leg, the `--recent` / `--session-start` leg, and the global store (`_merge_scope`,
  `cli.py:11992`). A budget on one source leaks the others.
- **`session/*` exclusion misses a mis-typed save-state.** `savestate_7c4e19d2a8f3` came back
  with mtype `project`. Its FILE says `metadata.type: project` (hand-authored; 4 of cliquedb's
  `savestate_*.md` files). The fix is a memory-layer fact OWNED by
  [[task-26.4-savestate-mtype-normalisation]] (plan-26 lands first,
  [[plan-of-plans#override-2026-11-08b]]); this task re-asserts it on the packed path ([[#r2b]]).

## Deltas from task 19.1 {#deltas}

19.1's requirement text is this task's contract except where listed here. Every 19.1 AC and
mutation is carried (AC-14 maps them) unless a row below says otherwise.

| 19.1 | here | reason |
|---|---|---|
| R1 single `DEFAULT_HOOK_BUDGET_BYTES` = 9,500 | an event-aware table in `hook_budget.py` ([[#r1]]) set from R0's three outcomes; per-channel names are 21.1's (`prompt_recall`, `scan_prompt`, `session_start`, `precompact`) | UserPromptSubmit has four producers (scan-prompt, recall, the focus input hook, 3.7's undrained `curator status`) |
| Files: packer in `cli.py` | `recall_pack.pack` over the generic whole-block fitter `hook_budget.fit_blocks`, called by the VERB | the override: verb-side logic the mod reuses; one fitter for recall and scan-prompt |
| (none) | the hybrid replica-first leg moves INTO `verbs._memory_recall_rows` ([[#r5]]) | orchestrator decision S1 (a); closes plan-3's open "dense path is a second which-rows" |
| (none) | scan-prompt gets a byte cap (`--max-bytes`) through the same fitter ([[#r0b]]) | it reaches 11,555 B alone; the plan's goal fails through the sibling hook otherwise |
| depends on 19.5 R1 | R0 runs it | it was never run |
| R2 subjects | kept, AC-3's stale-subject leg included (AC-6) | 19.1 AC-3 |
| 19.4 AC-4, recall leg (moved from plan-26, `696c3cb` `#plan-19`) | AC-6: a subject marked `stale` (19.4 R5, written by 26.6) is absent from recall, including with `--include-subjects`; mutation "stale subject visible in recall" in AC-14 | it needs 19.1 R2, which this task builds; plan-26 r2 hands it here |
| R3 bodies for the top hits | per-prompt pack carries POINTERS only under its budget; bodies are tested on `session_start` | 12 hook lines at 250-370 B each fill 3.0-4.4 kB; no 2.0 kB body fits ([[bsd-plan25-spec-r1-2f4a1df#m1]]) |
| AC-2 reach on the local 20-prompt set, ≥ 5x | reported, not gating; AC-3 gates on the frozen fixture | the committed fixture is the reproducible gate |
| folded riders #w1c-s2, #w1c-m4 | stay with 19.1 | they are time budgets, not byte budgets |

## Requirements {#requirements}

0. **R0 Probe the delivery cap first** (19.5 R1, in a SCRATCH Claude Code project, never this
   repo's settings). Probe hooks emit 9,000 / 10,000 / 11,000 characters of ASCII and of a 3-byte
   character on UserPromptSubmit and SessionStart. A second run puts TWO hooks of 6,000 chars on
   one event; a third puts FOUR hooks of 3,000. Both multi-hook runs are made on UserPromptSubmit
   AND on SessionStart (r3 #m9: the per-hook vs per-event answer is recorded per event, never
   assumed equal). Record the cap and its unit (chars or bytes), the preview size, per-hook vs
   per-event for each event, and whether PreCompact stdout reaches the agent. It also records,
   read-only, the bytes every NON-rmx hook installed in the user's global settings adds to each
   event:
   - UserPromptSubmit: `~/.claude/hooks/caveman-mode-tracker.js`, one `additionalContext` JSON
     of ~200-250 B when a caveman mode is active and nothing otherwise (read 2026-11-09; its
     `/caveman-stats` branch blocks the prompt and is not a per-turn producer);
   - SessionStart: `~/.claude/hooks/caveman-activate.js`, a standalone install with no
     `skills/caveman/SKILL.md`, so it prints its fallback ruleset (~1.2 KB) plus a statusline
     nudge when `statusLine` is unset ([[bsd-plan25-spec-r3-2f64edb#probes]]).
   Commit the table to `workflow/measurements/hook-output-cap-probe.md`.
   The unit of budgeting is the GENERATED HOOK COMMAND, because that is what Claude Code caps:
   UserPromptSubmit has `scan_cmd` (scan-prompt `;` curator status: ONE command, one stdout),
   `focus_input_cmd` and the recall command. SessionStart has `sess_cmd` (the disowned background
   sync `;` curator status, `hooks.py:187-191`), the recall command (`hooks.py:296-300`), the
   `ingest-gmd --detach` command (one line) and, on resume only, `rmx focus context --top N`
   (`hooks.py:313-320`, uncapped today). Exactly one of three outcomes is recorded PER EVENT and
   sets `hook_budget` ([[#r1]]); UserPromptSubmit and SessionStart may land in different
   outcomes:
   - **(A) per-hook cap.** Each hook command's budget is `0.9 × cap`. Inside `scan_cmd`,
     scan-prompt and curator status SHARE that one budget: `scan_prompt` + `curator_status` ≤
     `0.9 × cap`, with the split written next to the constant.
   - **(B) per-event cap, residual ≥ `MIN_USEFUL_RECALL_BYTES`** (2,000 B: header + 6 hook
     lines). `EVENT_BUDGET[event] = 0.9 × cap − NON_RMX_RESERVE_BYTES[event]` (that event's
     measured non-rmx bytes rounded up to 512 B) is split across the event's rmx producers by
     `hook_budget.EVENT_SPLIT[event]`: UserPromptSubmit over `scan_prompt`, `curator_status`,
     `focus_input`, `prompt_recall`; SessionStart over `curator_status`, `session_start`,
     `focus_context` and one line for `ingest-gmd --detach`. EVERY producer's share is a hard
     byte cap it enforces on itself (no "measured max + margin" shares).
   - **(C) per-event cap, residual < `MIN_USEFUL_RECALL_BYTES`.** scan-prompt's share is cut
     until recall gets `MIN_USEFUL_RECALL_BYTES`, and the split is recorded with both numbers.
   The probe is recorded before GREEN; ACs read the constants, never the probe. {#r0}
0b. **R0b scan-prompt is byte-capped too.** `scan.scan_prompt(..., max_bytes=)` and
    `rmx scan-prompt --max-bytes N` (default `hook_budget.budget("scan_prompt")`): the rendered
    text (bundles, content block, helix lines and the composite) is fitted by
    `hook_budget.fit_blocks` in its existing render order, whole blocks only, with a one-line
    `+N blocks omitted` trailer. The hook argv gets no new flag (the default applies).
    **Every other rmx producer on the event is capped the same way:** `rmx curator status`
    (3.7's verb `curator(action="status")` after its merge; today it prints up to `--limit 10`
    repo-relative paths of any length plus overflow text on every prompt) fits its lines through
    `fit_blocks` to `budget("curator_status")`, and `focus hook --event input` fits whatever it
    prints to `budget("focus_input")`. On SessionStart the same rule covers the resume command:
    `rmx focus context` (3.7's `focus` verb dispatcher after its merge) gains `--max-bytes`
    (default `budget("focus_context")`), fitted through `fit_blocks` in its render order with the
    one-line omitted trailer; the generator passes no flag (r3 #m9). {#r0b}
1. **R1 One budget module, one unit.** `src/refmatrix/hook_budget.py` holds `CHANNEL_BUDGET_BYTES`
   (keys `prompt_recall`, `scan_prompt`, `curator_status`, `focus_input`, `session_start`,
   `focus_context`, `precompact`), `HOOK_COMMAND_CHANNELS` (which channels share one generated
   hook command: `scan_cmd` = `scan_prompt` + `curator_status`; `sess_cmd` = `curator_status`),
   `EVENT_SPLIT` and `NON_RMX_RESERVE_BYTES` (both keyed by event: `UserPromptSubmit`,
   `SessionStart`), `MIN_USEFUL_RECALL_BYTES`, `budget(channel) -> int` and the pure
   `fit_blocks(blocks, max_bytes, *, trailer) -> Fitted(text, kept, dropped, payload_bytes)`.
   PROVISIONAL values until R0, ONE set used everywhere in plan-25 (r3 #m7): `prompt_recall`
   4,000; `scan_cmd` 5,000 = `scan_prompt` 4,500 + `curator_status` 500; `focus_input` 256;
   `session_start` 9,000; `focus_context` 1,500; `precompact` 9,000;
   `NON_RMX_RESERVE_BYTES` = {`UserPromptSubmit`: 512, `SessionStart`: 1,536} (caveman tracker
   ~250 B and caveman-activate ~1.2 KB plus the nudge, each rounded up to 512 B). Under a per-event
   SessionStart cap of 10,000 B the provisional `session_start` 9,000 does NOT fit beside the
   reserve; that is why R0 must replace it before GREEN, not a reason to keep it.
   `--max-bytes N` / verb `max_bytes=N` override a channel;
   `RMX_HOOK_BUDGET_BYTES`, when set, overrides every channel and is never interpolated into an
   argv; a non-integer value exits non-zero naming the variable. The unit is UTF-8 bytes of the
   rendered payload (19.1 R1's reason: bytes ≥ chars, so either harness unit is safe). {#r1}
2. **R2 Subjects are not hits** (19.1 R2 unchanged): default `exclude_mtype` becomes
   `['session/*', 'subject']` in hook modes and in the verb; `--include-subjects` opts back in;
   a subject with `metadata.stale = true` stays hidden even with the opt-in. {#r2}
3. **R2b Save-states stay out of the pack (re-asserted, not re-implemented).** 26.4 makes the
   bridge store `session/recall-state` for any file under `savestates/` or with an id starting
   `savestate_`. This task adds NO second rule: recall's exclusion stays mtype-only. AC-5 asserts
   the packed per-prompt argv does not name a mis-typed save-state. If 26.4 has not merged, 25.1
   waits; it does not build a name-based filter. {#r2b}
4. **R3 `--pack`** (19.1 R3): header line naming channel, hit count and budget; one hook line per
   named hit, ALL before any body; whole bodies only, greedily in rank order; a `+N more: <cmd>`
   trailer; scope-correct fetch pointers (R6). On `prompt_recall` the expected payload is
   pointers only (d3). {#r3}
5. **R4 After the merge, once; hooks passed in.** `recall_pack.pack(rows, *, hooks, max_bytes,
   channel, query, mode, k_more) -> Packed(text, spans, named, more, payload_bytes)` is pure (no
   I/O, no telemetry, no store). `hooks: Mapping[str, str]` is the mapping
   `memory_index.load_hooks(memdir)` (`memory_index.py:188`) returns, UNCHANGED: its keys are the
   index link targets (`parse_hooks`, `hooks[rel]` at `memory_index.py:181`), which are relative
   PATHS at HEAD and in every dir plan-26 / plan-27 leaves un-organised, and ids in dirs 26.1
   organises (26.1 AC-4: the reader accepts both key shapes). The pack's lookup for a row is
   therefore **the row's memory id first, then the row's path relative to the memdir** (r3 #m2);
   a row found under neither falls back to the first sentence, 19.1 R3(b). The VERB builds the map
   for the project memdir and, for global rows, from the global store's curated memory dir when
   one is registered, else nothing. `pack` is
   called exactly once per invocation on the final row list: after every source is merged
   (`_merge_scope`) and excluded, in every hook mode (`--recent`, `--session-start`,
   `--stdin-json`, dense, hybrid). {#r4}
6. **R5 Recall rows come from the verb, for EVERY caller; the CLI renders.** (orchestrator S1 (a),
   extended 2026-11-09 by decisions d6-d8 and, in r3, d10)
   - **Root-correct move.** `_replica_memory_recall` (`cli.py:11347`) moves to
     `recall.replica_memory_recall(root, *, partition, query, k, kinds, fuse, rerank, left,
     warnings, embedder_policy)` over `search.cached_replica(root)` (the primitive `memory_partition` already
     uses). It reads NO CLI global and no CWD: `_reader_store()` and `_resolve_partition()` are
     replaced by the explicit `root` / `partition`. So an MCP call with `project=cliquedb` from a
     refmatrix session reads cliquedb's replica.
   - **The partition is `verbs.memory_partition(root)`** (`verbs.py:376`, "THE routing every
     memory verb must use"), resolved by the verb and passed explicitly. Not 3.7's
     `discovery.resolve_partition` (the PROJECT partition, from `-p` / `$RMX_PARTITION` / the cwd
     marker) and not HEAD's `_resolve_partition()` (`cli.py:11394`). HEAD's replica leg binds the
     project partition while its RPC leg uses `_memory_partition_default` (`cli.py:11453`), which
     returns a legacy `memory-<p>` partition where one exists; one resolver closes that
     divergence (r3 #m3 b, AC-4 (h)).
   - **The A/B switch stays.** `RMX_RECALL_REPLICA_FIRST=0` (`cli.py:11369`) moves with the leg
     into `recall.replica_memory_recall` and is read in the CALLING process (the hook's `rmx`, the
     `rmx mcp` server, the interactive CLI), never forwarded to the daemon; with it set the verb
     goes straight to the daemon RPC. AC-4 (d) forces the replica leg off through it (r3 #m3 c).
   - **The embedder, per caller** (decision d10, r3 #s1). HEAD's leg embeds ONLY through the
     hub's shared worker (`modelsrv.shared_available` → `RemoteEmbedder(SharedWorkerClient)`,
     `cli.py:11380-11390`) and returns None otherwise, "never a locally spawned model"
     (`cli.py:11364`). 3.7 makes `recall.shared_embedder(root)` THE daemonless accessor (hub
     worker, else a private worker, else one cached in-process model; its `graph_recall` and
     `ann_search` verbs use it). After the move:
     - **hook modes** (`--stdin-json`, `--session-start`, `--recent`, PreCompact) stay HUB-ONLY:
       a private-worker spawn or an in-process load (6-33 s) cannot fit the 5 s per-prompt
       budget. The verb takes `embedder_policy: Literal["hub_only", "shared"] = "shared"` and
       passes it to the moved function; the CLI passes `"hub_only"` in every hook mode (its
       parity twin is the hook-mode flag set), MCP never passes it;
     - **interactive and MCP callers** embed through `recall.shared_embedder(root)`, exactly as
       3.7's graph verbs do (`embedder_policy="shared"`), and the verb's `warnings` name which
       embedder served (hub worker, private worker, in-process).
     One package, one accessor, one documented exception (the hook's latency budget) instead of
     two silent policies.
   - **The body fetch moves with it.** Replica-served hits are resolved to memory rows from the
     same replica (the CLI's `_fetch_memory` logic, root-explicit), never by the daemon-only
     `_call(root, "memory_get")`; the daemon fetch remains for daemon-served hits.
   - `verbs._memory_recall_rows`' dense branch tries the replica leg first, then the daemon RPC
     (the CLI's order today). The verb's own dense leg (`verbs.py:1054-1077`) becomes the daemon
     fallback, not a parallel path.
   - **Every caller goes through it (d6):** the hook modes, MCP `rmx_memory_recall` (`mcp.py:142`)
     and the interactive `rmx memory recall "q"` (table and `--json`, `hook_mode` False at
     `cli.py:12323`). The CLI-only `kind=doc` leg moves into the verb as a `kinds` value the verb
     honours, owned by this task. After 25.1 there is one which-rows computation for recall.
   - **Accepted consequence (d7):** MCP and interactive query recall are served from the replica
     snapshot when it and the shared workers answer, so they may lag the writer by the replica
     rotation interval. The rerank default is resolved where the call runs
     (`reranker.rerank_enabled()` in the calling process on the replica leg, the daemon's default
     on the RPC leg); the verb's `warnings` name which leg served and whose default applied.
   - **No daemon, no hub worker, HOOK mode (d8, narrowed by d10):** the verb raises
     `VerbAbsentError("memory recall needs the daemon up (dense embedder lives there) or a replica
     + shared model workers")`. The CLI catches it, prints NOTHING to stdout, exits 0, and records
     it through the EXISTING degrade recorder, not a new row key (r3 #m3 a): `_degrade_or_raise`
     (`cli.py:12340`) → `_RecallCall.degraded(e)` (`cli.py:12862`) →
     `telemetry.classify_outcome(type(e), e, budgeted=True)`. `VerbAbsentError` is not a budget
     type (`telemetry._budget_exception_types`) and not an `OSError`, so the row reads
     `outcome: "error"`, `error: "VerbAbsentError: memory recall needs the daemon up …"`, counted
     in the hook-cost report, never silent. Today (`cli.py:12570-12574`) the same case raises
     `ClickException` and exits 1, a user-visible hook error; this is a deliberate change of the
     failure surface.
   - **No daemon, no hub worker, interactive / MCP:** the verb does NOT raise for want of the hub;
     `shared_embedder` serves (private worker, else the cached in-process model) and `warnings`
     names it. It raises only when `shared_embedder` itself fails (`ImportError` without the
     `[dense]` extra → `VerbError("dense extra not installed: …")`, as 3.7's graph verbs do).
   - `verbs.memory_recall(..., pack: bool = False, max_bytes: int | None = None,
     include_subjects: bool = False)` returns `{"text", "spans", "named", "more",
     "payload_bytes", "warnings"}` when `pack`. `cli._memory_recall_impl` prints the verb's
     `text` (or renders its rows as the table); it computes no rows of its own.
   - The verb's `trigger` (24.2a d9) is NOT added here; 24.2a adds it on top. {#r5}
7. **R6 Scope-correct fetch** (19.1 R6): `rmx memory get --scope {project,global}` and the
   `rmx_memory` get action's `scope`; with `--scope global` it reads the global store and never
   returns a same-named project row; a global hit's pointer reads `--scope global`. {#r6}
8. **R7 Hooks** (19.1 R4 amended): the generator emits `--pack` in place of `--json` on the three
   recall commands, never interpolates a budget variable, and raises `--k` (SessionStart 30,
   per-prompt 12, PreCompact 30). PreCompact follows R0: if its stdout does not reach the agent,
   the PreCompact recall command is dropped and the promote / save-state legs stay. {#r7}
9. **R8 Loud overflow and arithmetic** (19.1 R5, R7): never empty, never over N; distinct named
   hits + trailer N = hits retrieved; bodies ⊆ named; a body never counts as a second named hit.
   {#r8}
10. **R9 Spans to the one emitter** (19.1 R8): the pack returns per-named-hit byte spans; 21.1's
    single site (`_RecallCall`, `cli.py:12837`) emits `delivered` from them, never for a trimmed
    hit. The packer emits nothing. {#r9}

## Acceptance criteria {#acceptance}

All ACs run in 23.0's sandbox on the frozen fixture ([[#fixture]]) through the GENERATED hook
argv: the test builds the hook config with `hooks._claude_hook_block(...)`, takes the command of
the entry under test, and runs it with `bash -c`, the envelope on stdin and the sandbox `HOME`.
Unit tables (AC-9) are in addition, never instead ([[feedback_measure_the_path_users_run]]).
{#acceptance-lead}

1. **AC-1 The cliquedb shape, before and after.** On the fixture the per-prompt argv for the
   question prompt prints > 10,000 B at HEAD (RED, recorded) and ≤ `budget("prompt_recall")`
   after; the SessionStart argv likewise against `budget("session_start")` (the whole SessionStart
   event is bounded by AC-12b); PreCompact against its budget or, if R0 drops it, the generated
   config has no PreCompact recall command.
2. **AC-2 Budget for every N, multibyte.** For N ∈ {2000, 4000, 9000} via `--max-bytes`, every
   channel's payload is ≤ N UTF-8 bytes on a fixture whose hook lines and bodies carry ≥ 4 of
   `—` / `→` each. Pre-check recorded before GREEN: the chars-counting mutation exceeds N on
   every N, or the fixture is densified first (19.1 AC-1).
3. **AC-3 Reach.** Distinct non-subject, non-session memories the model receives (the whole
   payload if ≤ R0's cap, else the first `preview` bytes) ≥ 8 for the per-prompt argv after;
   recorded for HEAD (expected ≤ 1).
4. **AC-4 One rows computation, every source.** (restated, S1)
   - (a) The AC-1 bound holds with: daemon up, `--scope both`, a tmp global store of 10 global
     memories; `--session-start`; `--recent --since 1h`. RED at HEAD.
   - (b) **No daemon, replica + a sandbox shared worker present** (the test starts the real
     `modelsrv` worker on the sandbox `models.sock`): `verbs.memory_recall(query=…, pack=True)`
     returns rows from the replica within the budget. RED at HEAD: the verb never consults the
     replica and raises / returns empty.
   - (c) **No daemon, no hub worker, HOOK mode only** (d10): the per-prompt argv prints nothing
     on stdout, exits 0, spawns no private worker and loads no in-process model (asserted: no new
     `modelsrv` child of the hook's process and no `sentence_transformers` import in it), and the
     recall row carries `outcome: "error"` with `error` starting `VerbAbsentError:` (R5's
     recorder, no new key); `verbs.memory_recall(..., embedder_policy="hub_only")` raises `VerbAbsentError`
     with the R5 message. RED at HEAD: exit 1.
   - (e) **MCP, cross-project, real worker.** Two sandbox stores A and B (B's memories distinct),
     a real `modelsrv` worker on the sandbox `models.sock`, no daemons. B is REGISTERED in the
     sandbox registry, and the test first asserts `mcp._resolve_root({"project": "B"})` returns
     B's root (r3 #m4: on a miss `_resolve_root`, `mcp.py:49-67`, falls through to
     `REFMATRIX_ROOT` and then the cwd store with no error, which would read A's rows and look
     exactly like the mutation below). Then MCP `rmx_memory_recall` called from A's root with
     `project=B` returns B's rows (none of A's) from B's replica. RED at HEAD: the MCP verb never
     consults a replica and raises. A mutation that leaves the moved function reading the CWD's
     store returns A's rows and fails. The silent fallback itself is bug-181, not fixed here.
   - (f) **Interactive path.** `rmx memory recall "q"` (table) and `--json` name the same hits as
     the verb for the same query, including a `kind=doc` row on the fixture.
   - (d) **Rows parity:** with the replica leg forced on and forced off (worker present / absent,
     and `RMX_RECALL_REPLICA_FIRST=0` in the calling process; daemon up in all three), the
     per-prompt argv's named hits equal the verb's named hits.
   - (g) **No daemon, no hub worker, INTERACTIVE** (d10, r3 #s1): `rmx memory recall "q"
     --json` and MCP `rmx_memory_recall` answer from the replica with the query embedded by
     `recall.shared_embedder` (a private worker in the sandbox), exit 0, and the verb's `warnings`
     name the private worker. RED at HEAD: the interactive CLI raises "needs the daemon up …"
     (`cli.py:12570-12574`).
   - (h) **Legacy memory partition** (r3 #m3 b): on a store whose memories live in a legacy
     `memory-<p>` partition, the replica leg and the daemon RPC leg return the same named hits
     for the same query. RED at HEAD: the replica leg binds the project partition
     (`cli.py:11394`) and returns none of them.
   - A mutation that budgets project rows before `_merge_scope` fails (a).
5. **AC-5 Mis-typed save-state, packed path.** The fixture holds `savestate_fx01.md` with
   `metadata.type: project` and the body best matching the question prompt. After 26.4 the packed
   per-prompt argv (daemon up, and the AC-4 (b) replica leg) does not name it and the trailer does
   not count it. A regression guard at the 25.1 base (26.4 merged), recorded as such.
6. **AC-6 No subject noise** (19.1 AC-3). 0 `mtype=subject` rows on the per-prompt argv (HEAD ≥ 1
   on the fixture's 5 seeded subjects, recorded); `--include-subjects` brings live subjects back;
   a subject SEEDED with `metadata.stale = true` + `stale_since` stays out even with the opt-in.
   This leg also carries 19.4 AC-4's recall leg (moved from plan-26 r2): a subject marked `stale`
   (19.4 R5, written by 26.6) is absent from recall on the per-prompt argv, the SessionStart argv
   and the verb, including with `--include-subjects`. After 26.6 merges, the stale mark is also
   produced by 26.6's real compile path on the fixture, not only seeded.
7. **AC-7 The CLI prints the verb.** `verbs.memory_recall(query=<prompt>, k=12, scope="both",
   pack=True)`'s `text` equals the per-prompt argv's stdout byte for byte, with the replica leg on
   (AC-4 (b) setup) AND off. The parity test lists `pack` / `max_bytes` / `include_subjects` /
   `embedder_policy` with their CLI twins.
8. **AC-8 Environment.** The generated argv runs with `RMX_HOOK_BUDGET_BYTES` unset (exit 0,
   within the table); `=3000` (≤ 3000 B); `=abc` (exit non-zero, stderr names the variable).
9. **AC-9 Pack and fitter contract.** Arithmetic (R8) on every AC-1..AC-4 payload; unit tables
   over `recall_pack.pack` and `hook_budget.fit_blocks`: hook lines before bodies, whole bodies,
   trailer count and the quoting of a multi-line query, loud overflow when the header plus one
   line exceeds N. Bodies appear on the `session_start` channel of the fixture (≥ 2 bodied hits),
   never on `prompt_recall` at its default budget (d3). One pack runs over a PATH-keyed memdir
   (the `MEMORY.md` links and the hooks sidecar keyed by relative path, as at HEAD) and one over an
   id-keyed memdir (26.1's organised shape): in both, every named hit prints its curated hook, not
   its first sentence (r3 #m2).
10. **AC-10 Delivered events and spans** (19.1 AC-6). A pack naming 7 of 12 retrieved hits (3
    bodied) leaves 12 `retrieved` and 7 `delivered` events sharing one `query_id`; each span
    slices exactly its hook line / body out of the payload bytes; the 4 unbodied hits have null
    body fields. Pre-check recorded before GREEN: the fixture puts ≥ 3 `—` before the LAST hook
    line and in every body (≥ 6 B of excess before each checked span), so character spans miss on
    every bodied hit. No `delivered` event for a trimmed hit. A global hit's `delivered` event is
    in the tmp global root's file with `scope=global` (19.1 AC-6's global leg).
11. **AC-11 Global pointer** (19.1 AC-7). With a project row and a global row both named `X`, the
    pack's printed fetch command for the global hit returns the global row; `rmx memory get X`
    (no scope) returns the project row.
12. **AC-12 scan-prompt bound.** The generated scan-prompt command on the fixture's question
    prompt (composite on) prints ≤ `budget("scan_prompt")` bytes; RED at HEAD when the fixture's
    bundles exceed it (the fixture is sized to push scan-prompt past 10,000 B at HEAD, like the
    measured 11,555 B maximum). The fixture's curator queue holds 30 long paths (> 120 chars
    each). Under outcome (A), each generated UserPromptSubmit hook COMMAND's stdout (`scan_cmd` =
    scan-prompt + curator status; the focus input command; the recall command) is ≤ `0.9 × cap`.
    Under (B)/(C), the sum of all generated UserPromptSubmit commands on one event is ≤
    `EVENT_BUDGET`. In every outcome `rmx curator status` alone is ≤ `budget("curator_status")`
    (RED at HEAD with the long-path queue).
12b. **AC-12b SessionStart bound** (r3 #m9). The fixture's STM ring for the resumed session is
    sized so `rmx focus context --top N` prints > 3,000 B at HEAD, and its curator queue holds the
    30 long paths. With the `resume` matcher, the generated SessionStart commands run in order
    (`sess_cmd`, recall, `ingest-gmd --detach`, `focus context`). Under (A) each command's stdout is
    ≤ `0.9 × cap`, and `focus context` alone is ≤ `budget("focus_context")` (RED at HEAD: it has
    no cap). Under (B)/(C) the sum of all generated SessionStart commands is ≤
    `EVENT_BUDGET["SessionStart"]`, which already subtracts `NON_RMX_RESERVE_BYTES["SessionStart"]`
    for caveman-activate. The measured non-rmx SessionStart bytes from R0 are quoted beside the
    assertion.
13. **AC-13 Generator and isolation.** `rmx install-hooks --check` clean after `--apply` in the
    sandbox; the three recall commands contain `--pack`, no `--json`, no `$`; 23.0's guard records
    0 connects to any live socket.
14. **AC-14 Mutations that must FAIL a test** (19.1's twelve plus this task's):
    budget applied before the merge (AC-4 a); chars instead of bytes (AC-2); bodies before hook
    lines (AC-9); a cut body (AC-9); a missing trailer count (AC-9); spans in characters
    (AC-10); the generator keeping `--json` (AC-13); interpolating `${RMX_HOOK_BUDGET_BYTES}` into
    the argv (AC-8, AC-13); dropping the `subject` exclusion (AC-6); stale subject visible in recall, with or without
    `--include-subjects` (AC-6; moved from 26.6); counting a body as a second
    named hit (AC-9); `memory get --scope global` falling back to the project row (AC-11); a
    `delivered` event for a trimmed hit (AC-10); the packer calling a telemetry writer (AC-10: 14
    not 7); the CLI computing its own rows instead of printing the verb's text (AC-7); the verb
    skipping the replica leg (AC-4 b); scan-prompt not fitted (AC-12); curator status not fitted
    (AC-12); the moved replica leg reading the CWD store (AC-4 e); the interactive path computing
    its own rows (AC-4 f); the no-daemon hook exiting 1 or recording no `VerbAbsentError` outcome
    (AC-4 c); a global hit's `delivered` event in the project file (AC-10); **hook mode embedding
    through `shared_embedder`** (a private-worker spawn or in-process load on the per-prompt argv:
    AC-4 (c) sees the child process, and the hook overruns its 5 s budget); the interactive / MCP
    path kept hub-only (AC-4 g raises); the replica leg binding the project partition instead of
    `verbs.memory_partition(root)` (AC-4 h); the pack looking hooks up by id only (AC-9 path-keyed
    memdir prints first sentences); `focus context` not fitted (AC-12b); a single
    `NON_RMX_RESERVE_BYTES` for both events (AC-12b under (B)/(C) overflows with caveman-activate's
    bytes).

## Fixture and measurement {#fixture}

- `tests/fixtures/plan25/memory/`: 30 synthetic GMD memory files, bodies sized to cliquedb's
  measured distribution (2.0-8.7 KB), each with a curated hook; 5 subject rows (one stale) seeded
  through the daemon op the store uses; `savestate_fx01.md` mis-typed, placed where 26.3 puts
  save-states; 10 global memories; enough indexed docs that scan-prompt exceeds 10,000 B at HEAD.
  Synthetic text only; the README records the size distribution it reproduces and its source
  (the 21.1 byte counts above) ([[feedback_no_raw_prompts_in_public_repo]]).
- Prompts: authored for the test (a question, a bare ack, a symbol-only prompt), committed.
- **Before / after table** (bytes per hook invocation, fixture store, HEAD vs GREEN, three runs
  each): SessionStart, per-prompt (question), per-prompt (ack), scan-prompt, PreCompact, and the
  UserPromptSubmit event sum. Written to the summary and `workflow/measurements/plan-25-hook-bytes.md`.
- **Live check after deploy** (not a gate): the 21.1 byte distribution table above, re-read from
  `recall-events.jsonl` on refmatrix and cliquedb after a week of use (counts and bytes only).

## Files to create {#files-to-create}

| file | purpose |
|---|---|
| `src/refmatrix/hook_budget.py` | the budget table, `EVENT_SPLIT`, `budget()`, `fit_blocks()`; pure |
| `src/refmatrix/recall_pack.py` | `pack()`, `Packed`; pure; orders recall blocks and calls `fit_blocks` |
| `tests/test_task25_1_recall_budget.py` | AC-1..AC-14 |
| `tests/fixtures/plan25/` | synthetic memory + global fixtures, prompts, README |
| `workflow/measurements/hook-output-cap-probe.md` | R0's table and outcome |
| `workflow/measurements/plan-25-hook-bytes.md` | the before / after table (shared with 25.2, 25.3) |

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/verbs.py` (`memory_recall`, `_memory_recall_rows`, `rmx_memory` get) | root-explicit replica-first leg and its body fetch; the `kind=doc` leg; `pack`, `max_bytes`, `include_subjects`; default `exclude_mtype` adds `subject`; get `scope`; hooks map from `load_hooks` |
| `src/refmatrix/mcp.py` (`rmx_memory_recall`, `:142`) | unchanged surface; behaviour now replica-first via the verb (d6, d7) |
| `src/refmatrix/cli.py` (`curator status`, after 3.7) / `verbs.curator` | `fit_blocks` to `budget("curator_status")` |
| `src/refmatrix/cli.py` (`focus context`) / 3.7's `verbs.focus` dispatcher | `--max-bytes`, `fit_blocks` to `budget("focus_context")` (R0b) |
| `tests/test_mcp_memory_recall_routing.py` | its `daemon.call` mock no longer proves the route; AC-4 (e) runs a real worker |
| `src/refmatrix/cli.py` (`memory recall`, `_memory_recall_impl`, `_replica_memory_recall`, `memory get`, `scan-prompt`) | the hybrid branch calls the verb and renders; `_replica_memory_recall` moves out; `--pack`, `--max-bytes`, `--include-subjects`; `memory get --scope`; `scan-prompt --max-bytes` |
| `src/refmatrix/recall.py` | `replica_memory_recall(root, *, partition, embedder_policy, …)` beside 3.7's `shared_embedder` (d5, d10); `RMX_RECALL_REPLICA_FIRST` read here |
| `src/refmatrix/scan.py` | `max_bytes` through `hook_budget.fit_blocks` |
| `src/refmatrix/memory_index.py` | none expected: `load_hooks` exists (`:188`); re-read after 26.7 |
| `src/refmatrix/hooks.py` (`:296-300`, `:331-336`, `:357-362`) | `--pack`, raised `--k`, PreCompact per R0 |
| `src/refmatrix/mcp.py` (if its tool schema is hand-listed) | the new verb params |
| `tests/test_verb_parity.py` | the new params' twins |
| `workflow/bug_registry.md` | bug-164 → fixed at merge, with the mechanism and the before / after; bug-181 (MCP silent cwd fallback) is NOT closed by this task |

## Test strategy {#test-strategy}

- RED first: AC-1, AC-4 (a)(b), AC-6, AC-11, AC-12 against HEAD (after 3.7 and plan-26 merge),
  recorded with byte counts; a RED that passes at HEAD is not a RED
  ([[feedback_red_test_must_fail_at_head]]).
- No mock of recall, the verb, the packer, the fitter, the bridge or the hook generator. The only
  stand-ins are 23.0's sandbox redirections and a REAL sandbox `modelsrv` worker for AC-4 (b)/(d);
  the embedder is the real local model (`HF_HUB_OFFLINE=1`).
- The generated argv carries `HOOK_ENV`'s `PATH="$HOME/bin:…"` prefix; under the sandbox `HOME`
  there is no `~/bin/rmx`, so the dev venv's `rmx` must be first on the inherited PATH. The test
  asserts which `rmx` ran (its module `__file__` under the dev tree).
- Mutation run per [[feedback_commit_before_mutation_revert]] and
  [[feedback_clear_pycache_after_mutation]].

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| d1 | Provisional budgets before R0 | `prompt_recall` 4,000 B; `scan_cmd` 5,000 B = `scan_prompt` 4,500 + `curator_status` 500 (r3 #m7: one set; the command is the unit since d9, so its two producers split the 5,000 the plan always quoted); R0's outcome replaces all of them before GREEN |
| d2 | Where the save-state mtype fix lives | in the bridge, owned by 26.4; 25.1 re-asserts only |
| d3 | Per-prompt `--k` 12 under ~4,000 B | yes, as a POINTER list: 12 hook lines at 250-370 B fill the budget and no body fits; the trailer covers the rest; bodies are a `session_start` feature |
| d4 | Does 25.1 land 19.1 R6 (`memory get --scope`) | yes, with AC-11 |
| d5 | Home of the moved replica leg | `recall.py`, beside 3.7's `shared_embedder` (both are "rows without the writer"), root-explicit over `search.cached_replica(root)`, imported by the verb; never two copies; its embedder per d10 |
| d6 | Does MCP / interactive query recall go replica-first too | yes (orchestrator 2026-11-09): one which-rows path for hooks, MCP and the interactive CLI; this task owns the `kind=doc` leg |
| d7 | Replica lag on MCP / interactive recall | accepted: results may lag the writer by the replica rotation interval; the warnings say which leg served |
| d8 | No daemon and no hub worker on a hook | exit 0, nothing injected, counted through the existing recorder (`outcome: "error"`, `error: "VerbAbsentError: …"`); today it exits 1 (a hook error). Interactive and MCP callers: per d10 |
| d10 | Daemonless embedder policy (r3 #s1, decided as the user would) | hook modes stay hub-only (5 s budget; a spawn or in-process load is 6-33 s); interactive and MCP embed through 3.7's `recall.shared_embedder(root)`, as its graph verbs do; `warnings` name the embedder |
| d11 | SessionStart budget (r3 #m9) | same per-command unit and per-event reserve as UserPromptSubmit; R0 probes both events; `focus context` capped through `fit_blocks`; AC-12b |
| d9 | Budget unit | the generated hook COMMAND (what Claude Code caps); producers sharing a command share its budget; every rmx producer is hard-capped; non-rmx hooks get a measured reserve |

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan25-spec-r1-2f4a1df]] and the orchestrator's decisions of 2026-11-09.

| finding | change | anchor |
|---|---|---|
| S1 the argv never reaches the verb | decision (a): the replica-first hybrid leg moves into `verbs._memory_recall_rows`, the CLI renders the verb's text; AC-4 restated as (a)-(d) with a RED-able replica leg and a named no-daemon error; AC-7 runs with the replica leg on and off | [[#why]], [[#r5]], AC-4, AC-7, d5 |
| S2 dropped 19.1 items | stale-subject leg (AC-6), multibyte span pre-check (AC-10), global pointer AC (AC-11), all twelve 19.1 mutations (AC-14); the delta table now says every 19.1 AC/mutation is carried unless listed | [[#deltas]], AC-6, AC-10, AC-11, AC-14 |
| S3 no per-event branch; scan-prompt overflows alone | R0 has three outcomes (A per-hook, B per-event split, C per-event residual below minimum); all four UserPromptSubmit producers (incl. 3.7's `curator status`) in `EVENT_SPLIT`; scan-prompt byte-capped through the same fitter (R0b, AC-12); the 21.1 distribution is the cited baseline | [[#r0]], [[#r0b]], [[#r1]], [[#why]], AC-12 |
| M1 no body fits under 4,000 B | d3 rewritten: the per-prompt pack is a pointer list; bodies tested on `session_start` (AC-9) | [[#r3]], d3, AC-9 |
| M2 one channel, two names | `prompt_recall` everywhere (21.1's name) | [[#r1]], [[#deltas]] |
| plan-26 r2 (`696c3cb`, `#plan-19`) hands over 19.4 AC-4's recall leg | delta row; AC-6 asserts a 26.6-marked stale subject is absent from recall incl. `--include-subjects`; mutation added to AC-14 | [[#deltas]], AC-6, AC-14 |
| M3 `pack()` needs hooks | `hooks` mapping parameter; the verb builds it with `memory_index.load_hooks` for the project and the global memdir | [[#r4]] |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan25-spec-r2-5b8ed15]] with the orchestrator's decisions of 2026-11-09.

| finding | change | anchor |
|---|---|---|
| S1 MCP change unstated; moved leg bound to the CWD; interactive path keeps its own rows | `recall.replica_memory_recall(root, *, partition, …)` over `search.cached_replica(root)`; MCP and interactive recall go through the verb (d6), the `kind=doc` leg moves into the verb; replica lag accepted (d7); AC-4 (e) cross-project MCP with a real worker, (f) interactive parity | [[#r5]], d5-d7, AC-4, AC-14 |
| S2 split by producer, cap by hook command; uncapped producers; non-rmx producer uncounted | budget per generated hook command (d9); scan-prompt + curator status share `scan_cmd`'s budget; curator status and focus input hard-capped through `fit_blocks`; R0 records non-rmx hook bytes (caveman tracker ~200-250 B) as `NON_RMX_RESERVE_BYTES`; AC-12 asserts per command, with a long-path curator queue | [[#r0]], [[#r0b]], [[#r1]], AC-12, d9 |
| M1 "today's degrade line" is exit 1 today | decision d8: exit 0, nothing injected, counted `degraded`; text corrected | [[#r5]], AC-4 (c), d8 |
| M2 body fetch unnamed | replica-served hits fetched from the same replica; named in R5 | [[#r5]] |
| M3 19.1 AC-6 global leg missing | added to AC-10 and AC-14 | AC-10, AC-14 |

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan25-spec-r3-2f64edb]] (DIRTY 0B/4S/9M at `2f64edb`). Its three decision-bearing
findings were decided in the report as the user would; this fold adopts them. Every `src` line
cited below was re-read at master `9bcf464`.

rel: derives-from -> [[bsd-plan25-spec-r3-2f64edb]]

| finding | change | anchor |
|---|---|---|
| S1 moved leg keeps a hub-only embedder for every caller; 3.7 makes `shared_embedder` THE accessor | d10: hook modes stay hub-only (a spawn or in-process load, 6-33 s, cannot fit the 5 s budget; HEAD's leg says "never a locally spawned model", `cli.py:11364`); interactive and MCP embed through `recall.shared_embedder(root)` as 3.7's graph verbs do (3.7 `verbs.py:2336,2361`); `embedder_policy` verb param; AC-4 (c) hook-only, new AC-4 (g), mutations "hook mode spawns a private worker" and "interactive kept hub-only" | [[#r5]], d5, d8, d10, AC-4, AC-7, AC-14 |
| M2 hooks map keyed by path at HEAD | lookup by id, then the relative path; AC-9 runs a path-keyed and an id-keyed memdir; mutation "id-only lookup" | [[#r4]], AC-9, AC-14 |
| M3 (a) invented `degraded` key | the existing recorder: `_degrade_or_raise` → `_RecallCall.degraded` → `classify_outcome(..., budgeted=True)` = `outcome: "error"`, `error: "VerbAbsentError: …"` | [[#r5]], d8, AC-4 (c), AC-14 |
| M3 (b) partition | `verbs.memory_partition(root)` passed explicitly; AC-4 (h) on a legacy `memory-<p>` store; mutation | [[#r5]], AC-4 (h), AC-14 |
| M3 (c) `RMX_RECALL_REPLICA_FIRST` | stays, moves into `recall.replica_memory_recall`, read in the calling process; AC-4 (d) uses it | [[#r5]], AC-4 (d) |
| M4 AC-4 (e) depends on `project=B` resolving | B registered in the sandbox registry and its resolution asserted first; the silent fallback logged as bug-181 (open, not fixed here) | AC-4 (e), [[#files-to-modify]] |
| M7 provisional numbers in three forms | one set: `scan_cmd` 5,000 = `scan_prompt` 4,500 + `curator_status` 500; R1 and d1 agree, and the plan's `#deltas` and q2 follow | [[#r1]], d1 |
| M9 SessionStart not covered | R0 runs the multi-hook probes on SessionStart too and measures caveman-activate (~1.2 KB); `NON_RMX_RESERVE_BYTES` and `EVENT_SPLIT` keyed by event; `focus context` byte-capped (`focus_context` 1,500 provisional); new AC-12b; mutations | [[#r0]], [[#r0b]], [[#r1]], AC-1, AC-12b, AC-14, d11 |
