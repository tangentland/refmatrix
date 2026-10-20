---
gmd: "0.1"
id: task-3.7-verb-it-backlog
title: "Task 3.7: the verb-it backlog — 49 agent-facing CLI paths in eight families: 42 verbed, 7 re-decided"
tags: [task, plan-3, verbs, parity, backlog, deferral]
metadata:
  node_type: task
  status: in-progress
  plan: plan-3-verbs-parity
  created: 2026-10-19
  updated: 2026-10-19
  wave: "W2-d"
---

# Task 3.7: the verb-it backlog {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: In progress — wave W2-d ([[plan-review-2026-10-14#t11-folded-waves]]); the user chose to
> build it now (2026-10-19, after the 0.80.1 save-state).
> Depends on: [[task-3.4-internal-cli-allowlist]], [[task-3.6-r9-remedy]] (#6 re-files `curator scan`)

rel: part-of -> [[plan-3-verbs-parity]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r9-1acadd2#b-1]]
rel: amends -> [[task-3.4-internal-cli-allowlist#r5-legacy]]
rel: implements -> [[bsd-plan3-verbs-parity-r12-b18d7e8#m-1]]
rel: implements -> [[bsd-plan3-verbs-parity-r12-b18d7e8#m-2]]

## Why {#why}

ch-bsd plan-3 r9 #b-1 (BULLSHIT): task 3.4 classified 50 of the 140 `LEGACY_UNPAIRED` paths as
`verb-it` ("agent-facing; owes a verb") with no task, plan or registry row behind any of them.
The shrink-only pin stops the set GROWING; nothing scheduled it to SHRINK. Plan-3's thesis is
"every capability an agent can call is a verb first" (project-profile #constraints). This task is
the anchor: every `verb-it` path names one family below, and each family closes by gaining verbs
or by being re-decided with a reason. {#why-lead}

Task 3.6 #6 re-files `curator scan` as `maintenance` (the scheduler drives it, not the
gmd-curator agent), so the backlog is **49 paths**. {#why-count}

**2026-10-19 rewrite.** The approved version listed families and proposed verb names only. Two
read-only catalogs of all 49 paths (params, store route, daemon op, busy/absent handling, output
shape, agent evidence from templates and 12 workstation `cli.log` files) turned it into the
buildable per-family spec below. The catalogs found that NONE of the 49 paths words a transport
error through `classify_transport_error`, and several paths open the store in a way the project
forbids (see [[#defects]]). Verbing a family therefore also moves its CLI onto the verb's
routing — the CLI twin CALLS the verb, so the defects die with the old bodies. {#why-rewrite}

## Decisions {#decisions}

Decided by the orchestrator as the user would (standing instruction: drive spec questions to
ready-to-implement and record the reason). Each re-decision cites code-checked evidence.
{#decisions-lead}

| family | verbed paths | verb (MCP tool) | re-decided paths → category |
|--------|--------------|-----------------|-----------------------------|
| [[#fam-graph-read]] | `neighbors`, `co-occur`, `top`, `describe`, `recall`, `search-dense`, `concept timeline` (7) | `rmx_graph` | `pairs show` → `harness` |
| [[#fam-canon]] | `canon find`, `canon siblings`, `canon link` (3) | `rmx_canon` | — |
| [[#fam-matrix-edit]] | all 10 | `rmx_matrix` | — |
| [[#fam-curation]] | all 5 | `rmx_curate` | — |
| [[#fam-focus]] | `tail`, `topics`, `show`, `subject`, `subjects`, `clear-subject`, `detour`, `detours`, `return`, `clear` (10) | actions on `rmx_focus` | `focus composite` → `harness` |
| [[#fam-session]] | `session list`, `recall`, `show` (3) | `rmx_session` | `session stats` → `harness` |
| [[#fam-refine]] | `refine list`, `refine show` (2); `curator drain` (1) | `rmx_refine`; `rmx_curator_drain` | `refine accept`, `refine reject` → `operator` |
| [[#fam-taxonomy]] | `taxonomy list` (1) | `rmx_taxonomy` | `taxonomy add`, `taxonomy remove` → `operator` |

**42 verbed + 7 re-decided = 49.** Eight new MCP tools; `rmx_focus` gains an `action`. {#decisions-count}

## Shared contract for every new verb {#contract}

Applies to every family. Tests pin each clause per verb. {#contract-lead}

- **C1 — one verb, typed.** `@verb` in `verbs.py`; dispatchers take `action: typing.Literal[…]`
  (snake_case actions; CLI hyphens map to underscores). The MCP tool is generated from the
  signature (`set(TOOLS) == set(VERBS)` stays green). The return is a JSON-able `dict`. {#c1}
- **C2 — the CLI twin CALLS the verb.** Each verbed path becomes the verb's `CLI_MAP` twin or a
  `CLI_ACTIONS` entry with wiring class `calls`, proven by the recorder test with a canary. The
  click command parses options, calls the verb, renders the dict. Its old body (direct store
  access, inline daemon calls) is deleted, not kept as a fallback. Existing CLI options keep
  their meaning; output text may change where the old text came from a defect. {#c2}
- **C3 — reads never touch the writer slot.** A read goes through the daemon op with a bounded,
  single-attempt budget (`retries=0`, default `READ_BUDGET_S = MEMORY_READ_BUDGET_S`), or through
  the lock-free snapshot via the existing `read_store` / `read_with_fallback` helpers. Never
  `_store()` (the write accessor), never `Store(root, …)` on a live `.refmatrix/`, never an
  in-process `Daemon(...)`. {#c3}
- **C4 — writes go through the daemon.** Via `verbs._call` (or `global_write` for the global
  store); no write is retried silently past the caller's budget. {#c4}
- **C5 — transport errors are classified.** Every handler of a `daemon.call` / `global_call`
  transport exception words it through `classify_transport_error` (`write=True` for writes) and
  raises its type; `tests/transport_guard.py` covers every new function. busy ⇒ `VerbBusyError`,
  absent ⇒ `VerbAbsentError`, refusal (`ok:false`) ⇒ `VerbError` with the daemon's words — never
  an empty answer. {#c5}
- **C6 — parity rows.** `PAIRING` / defaults rows in `tests/test_verb_parity.py` for every twin;
  verbed paths leave `LEGACY_UNPAIRED`, and `LEGACY_BASELINE` shrinks by exactly those paths. {#c6}
- **C7 — partition.** A project-store verb forwards the CLI's `-p` / `RMX_PARTITION` partition
  (verb param `partition: str | None`) to every op it calls; a memory or session read uses the
  memory / sessions partition resolver the CLI uses today. {#c7}
- **C8 — no silent failure.** No `except Exception: pass`, no `{}` / `[]` stand-in for a failed
  leg. A leg that is skipped by design (e.g. no git repo) reports it in a `warnings` list. {#c8}

## Families {#families}

### graph-read {#fam-graph-read}

`rmx_graph(action=…)`. Read-only graph navigation beside `rmx_context` / `rmx_query`. Agent
evidence: the PRIMER header and the hooks.py CLAUDE briefing teach `neighbors`, `co-occur`,
`top`; cli.log shows `neighbors` 95 and `describe` 29 calls. {#fam-graph-read-lead}

| action | CLI path | route (C3) | params beyond `partition` |
|--------|----------|------------|---------------------------|
| `neighbors` | `neighbors` | snapshot (`read_store`) — today it reads through `_store()`, the WRITE accessor, so a busy daemon says "writes go through the daemon" | as the CLI |
| `co_occur` | `co-occur` | snapshot | as the CLI |
| `top` | `top` | snapshot | `linkage`, `concept`, `k` |
| `describe` | `describe` | snapshot | as the CLI |
| `recall` | `recall` | daemon `memory_recall` op (hybrid dense⊕symbolic, server-side embed, rerank) with `kinds`; `--concept` / `--symbolic` seeds become an explicit `candidate_ids` prefilter the op accepts (op extended); `--no-dense` ⇒ symbolic only | `query`, `k`, `kinds`, `concepts`, `symbolic`, `dense` |
| `dense` | `search-dense` | daemon `ann_search` op WITH `partition` (today omitted — ids resolve against the wrong partition under `-p`); names resolved from the same partition | `query`, `k`, `kinds` |
| `timeline` | `concept timeline` | graph leg from the snapshot; session leg through the daemon `memory_search` op on the sessions partition (budgeted); git leg via subprocess. A failed leg is a `warnings` entry, never `except: pass`; the direct `Store(...)` open in `_iter_session_memories` is gone | `concept`, `hops`, `since`, `until`, `k`, `git` |

- `recall` no longer loads `Embedder()` in the caller's process (the CLI and the MCP server
  both hand the embed to the daemon). `-s` values are validated as ints (`VerbArgsError`).
  {#fam-graph-read-recall}
- `top`: `gmd-curator.md` lines 290 and 511 teach `rmx top mentions -k N`, which treats
  `mentions` as the concept (2 of 3 logged calls failed). Rewrite both lines to a command that
  does what the comment says, checked against the real signature. {#fam-graph-read-top}
- **Re-decided: `pairs show` → `harness`.** A debug view of the `pairs compile` (maintenance)
  coref inventory; zero agent evidence in templates, primer, docs; 0 calls in 12 cli.logs.
  {#fam-graph-read-pairs}

### canon {#fam-canon}

`rmx_canon(action=find|siblings|link)`. Cross-project canon view beside `rmx_where`.
{#fam-canon-lead}

- `find` — federated read over every live store (`federated_concept`); the result carries
  `skipped` like `rmx_where`.
- `siblings` — snapshot read.
- `link` — write via `_call(root, "link_canon", …)` (the partition-correct op already exists),
  `write=True` classification.

### matrix-edit {#fam-matrix-edit}

`rmx_matrix(action=…)` with actions `add_concept`, `add_entity`, `add_linkage_type`, `link`,
`unlink`, `list_entities`, `list_linkages`, `list_queries`, `run`, `save_query`. The CLAUDE
briefing teaches `add` and `link`; that is the agent evidence that keeps the family verbed
rather than re-decided. Hidden aliases (`add-concept`, …) follow their targets.
{#fam-matrix-edit-lead}

- Writes via `_call` (C4/C5). Reads (`list_*`, `run`) from the snapshot.
- **Defect fixed here:** `_op_add_concept` (daemon.py ~4125) and `_op_upsert_entity` (~4110)
  ignore `partition`, while `link` / `unlink` / `link_canon` / `save_query` honour it, so
  `rmx -p X add concept foo` lands in the daemon's partition and a following `-p X link` cannot
  find it. Both ops honour `partition` (RED test first). {#fam-matrix-edit-partition}
- `list_entities` gains `limit` (default 200) and the CLI gains `--json` (a logged agent call
  `list entities --json` failed with exit 2).
- The daemon ops `iter_entities`, `list_linkages`, `list_saved_queries` have no callers and take
  the writer lock; delete them unless a verb in this task calls one. {#fam-matrix-edit-dead}

### curation {#fam-curation}

`rmx_curate(action=protect|unprotect|noise|unnoise|forget, name=…, like=…, namespace=…,
kind=…)`. The selector forms are exactly the CLI's; the `set_flag` / `forget` daemon ops already
take them. Agent evidence: every generated PRIMER.md header prints
`rmx protect|unprotect|noise|unnoise|forget <sel>`. {#fam-curation-lead}

- At least one selector is required (`VerbArgsError`).
- `forget` defaults to `dry_run=True` in the verb: it returns what WOULD be forgotten. A
  selector that is ONLY `kind` and/or `namespace` (no `name` / `like`) also requires
  `broad=True`, else `VerbArgsError` naming the count it would remove. The CLI twin keeps its
  confirmation / `-y` behaviour and passes `dry_run=False, broad=True` after it (logged operator
  wipes like `forget --kind code -y` still work). The forget op keeps its 600 s write budget.
  {#fam-curation-forget}

### focus {#fam-focus}

`rmx_focus` gains `action: Literal["context", "tail", "show", "topics", "subject", "subjects",
"clear_subject", "detour", "detours", "return", "clear"] = "context"`. `context` is today's
behaviour unchanged (existing MCP callers send no action). All STM actions resolve the session
through `resolve_session_source` (`purpose="read"` for reads, `"write"` for writes). The
`/detour` and `/return` command templates invoke `rmx focus detour|return`; no generated hook
runs any of these paths. {#fam-focus-lead}

- **Defect fixed here — `focus clear`:** it skips the resolver and clears `$RMX_SESSION` or the
  literal `"default"` ring; hooks do not export `RMX_SESSION`, so an agent clears the wrong ring
  and is told "focus cleared". `clear` resolves like every other write and an unresolved
  session is refused (the 21.1 D2 rule). {#fam-focus-clear}
- **Defect fixed here — `focus subjects`:** it lists subjects from the CODE partition while
  `change_subject` writes to `memory_partition(root)`, and a daemon `ok:false` prints "no
  subjects yet". `subjects` reads `memory_partition(root)` through `_call` (budgeted, C5); a
  refusal is a `VerbError`. {#fam-focus-subjects}
- **Re-decided: `focus composite` → `harness`.** It renders the STM topic composite the
  scan-prompt hook injects, reads the replica with no `--session` (composite.py calls
  `latest_session` directly); zero agent evidence. A debug view of a hook's output.
  {#fam-focus-composite}

### session {#fam-session}

`rmx_session(action=list|recall|show)` over the `sessions-<project>` partition.
{#fam-session-lead}

- Every read goes through daemon ops (`memory_iter`, `memory_get`, `memory_search`) with a
  bounded single-attempt budget, partition from the existing `_session_partition` resolver.
  busy ⇒ `VerbBusyError`; absent ⇒ the read-only snapshot. **Defect fixed here:**
  `_iter_session_memories` and `_resolve_session` open `Store(root, partition=…)` read-WRITE on
  the active writer slot whenever ping fails (a busy daemon included) and even when the daemon
  answered `ok:false` — the 2026-09-14 lock-crash shape. The CLI goes through the verb, so the
  helpers' direct opens are deleted. `concept timeline`'s session leg uses the same routing.
  {#fam-session-store}
- The pure helpers (`_session_meta_get`, `_session_meta_list`, `_session_passes_filters`,
  `_since_to_iso`) move to a library module the verb and CLI share.
- **Re-decided: `session stats` → `harness`.** Counter aggregation over every session card
  (turns, prompts, top branches / models / files): an analytics view; no agent evidence.
  It is re-routed onto the verb's `list` read so it, too, stops opening the writer slot.
  {#fam-session-stats}

### refine {#fam-refine}

`rmx_refine(action=list|show)` — read-only views of the hub's refinement queue through
`verbs._hub_rpc` (today the CLI bypasses it: a hub `ok:false` becomes an empty list or "unknown
error", a timeout a traceback). `rmx_curator_drain` — the curator queue drain the gmd-curator
agent runs (`gmd-curator.md` :138, :150). {#fam-refine-lead}

- **Re-decided: `refine accept`, `refine reject` → `operator`.** They are the human approval
  gate of the "no silent writes" refinement queue; the hub UI is the other surface for the same
  gate. Code check: `gmd-curator.md` never calls `rmx refine` (the old reason "the gmd-curator
  agent drives it" was false). {#fam-refine-gate}
- `curator drain`: verb + CLI twin share ONE drain (`gmd_curator.drain_queue`, which today
  swallows errors — fixed to surface them, C8). The drain renames the queue file atomically
  before reading it, so a watcher append during the drain lands in a fresh queue rather than
  being unlinked. {#fam-refine-drain}
- Defects found in the re-decided operator paths are logged as bug rows (accept KeyError on a
  gmd-curator candidate; reject has no pending check; accept writes project memories to
  `store_name` not `memory_partition`; candidate ids use per-process `hash()`), not fixed here.
  {#fam-refine-bugs}

### taxonomy {#fam-taxonomy}

`rmx_taxonomy()` — the shared tag vocabulary (read). {#fam-taxonomy-lead}

- **Parity fix:** `memory_add` (verb) returns `tag_warnings` for tags outside the vocabulary,
  the warning the CLI prints today and MCP adds never get.
- **Re-decided: `taxonomy add`, `taxonomy remove` → `operator`.** Vocabulary administration;
  zero agent evidence in templates or cli.log. {#fam-taxonomy-admin}
- **Defect fixed here (data loss):** a corrupt `~/.refmatrix/taxonomy.json` silently loads the
  defaults, and the next `add` / `remove` overwrites the user's file. Load fails loudly on a
  corrupt file and add / remove refuse to write over it. {#fam-taxonomy-corrupt}

## Folded deferral rows {#folded}

- **R52 — guard plants** ([[bsd-plan3-verbs-parity-r12-b18d7e8#m-1]]): `tests/transport_guard.py`
  gets an OUTER-first two-level plant (kills mutant Q5, the single-pass loop), a
  message-prepared-before-the-`try` plant, and a local-alias (`dial = daemon_mod.call`) plant.
  {#folded-r52}
- **R53 — two unclassified handlers** ([[bsd-plan3-verbs-parity-r12-b18d7e8#m-2]]):
  `global_recall_rows` routes its transport exception through
  `classify_transport_error(e, op=op, root=groot, timeout=timeout)` and re-raises its type;
  `cli.py` `_file_under_active_subject`'s catch-all narrows to the `RuntimeError`
  `_subject_upsert` / `_subject_link` raise for `ok:false`. {#folded-r53}

## Defects found by the catalogs {#defects}

Each gets a `workflow/bug_registry.md` row (bug-138 is reserved for AC-6's renumber; this task
takes the next free numbers). Fixed here: search-dense partition, timeline silent passes,
neighbors write accessor, session / timeline writer-slot opens, add_concept / upsert_entity
partition, focus clear session, focus subjects partition, taxonomy overwrite, drain swallow.
Logged open: the four refine operator bugs. {#defects-lead}

## Acceptance criteria {#acceptance}

Per family (each a separate RED → GREEN step): {#ac-family}

1. **Verbed paths** meet C1-C8; each fixed defect has a test that fails at the task's base
   (`591a2fb`) and passes after.
2. **Re-decided paths** move to their category in `LEGACY_UNPAIRED` with the reason above; the
   reason no longer says `verb-it`.

Global ACs:

- **AC-G1.** No path remains in category `verb-it`; the category itself is removed from
  `LEGACY_CATEGORIES` once empty (the shrink-only pin then forbids its return).
  `test_every_verb_it_path_names_its_task_3_7_family` is updated to assert the empty set and
  that each of the 49 paths is either a twin of the verb named in [[#decisions]] or in the
  re-decided category named there. {#ac-g1}
- **AC-G2.** `VERB_IT_FAMILIES` in `tests/test_task3_6_r9_remedy.py` mirrors [[#decisions]]
  (verbed vs re-decided) and partitions the 49 paths. {#ac-g2}
- **AC-G3.** Deferral rows 51 (the backlog), 52 and 53 move to resolved, citing this task. {#ac-g3}
- **AC-G4.** Plan-3 closes when this task is `completed`. {#ac-g4}
- **AC-G5.** `LEGACY_BASELINE` shrinks by exactly the 42 verbed paths (140 → 98); the total of
  invocable paths is unchanged. {#ac-g5}
- **AC-G6.** `rmx install-hooks --check` clean; generated CLI tree / tools-primer artifacts
  regenerated where a test pins them. {#ac-g6}

## Build order {#schedule}

One clone (`/Volumes/littlebig/refmatrix-task-3.7`), one branch, batches landing in order so
`verbs.py` / `cli.py` / `test_verb_parity.py` are never edited by two agents at once:

1. **Batch A:** focus, curation, taxonomy, curator drain, R52, R53.
2. **Batch B:** graph-read, canon.
3. **Batch C:** matrix-edit, session, refine; AC-G1..G6.

Each batch: `@ch-test-engineer` RED (run recorded) → `@ch-implementer` GREEN → relevant tests
logged. After batch C: full suite, mutation check, `/ch-review`, `@ch-bsd` iterated to clean,
summary, release.

## Definition of done {#done}

- Each family: RED (recorder/parity/defect rows) before GREEN; mutation check; summary rows in
  `workflow/implementation_summaries/task-3.7-verb-it-backlog.md`.
- `@ch-bsd` over the range: no unaddressed BULLSHIT.
