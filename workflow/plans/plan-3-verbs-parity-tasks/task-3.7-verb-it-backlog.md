---
gmd: "0.1"
id: task-3.7-verb-it-backlog
title: "Task 3.7: the verb-it backlog — 49 agent-facing CLI paths in eight families: 45 verbed, 4 re-decided"
tags: [task, plan-3, verbs, parity, backlog, deferral]
metadata:
  node_type: task
  status: in-progress
  plan: plan-3-verbs-parity
  created: 2026-10-19
  updated: 2026-10-20
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
rel: amends -> [[bsd-plan3-task37-spec-7d6c418]]
rel: amends -> [[bsd-plan3-task37-spec-r2-15232c5]]
rel: amends -> [[bsd-plan3-task37-spec-r3-090eb5e]]
rel: amends -> [[bsd-plan3-task37-spec-r4-1c501a4]]
rel: amends -> [[bsd-plan3-task37-spec-r5-925f121]]
rel: amends -> [[bsd-plan3-task37-spec-r6-5fc593e]]

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
| [[#fam-focus]] | all 11 (`tail`, `topics`, `show`, `subject`, `subjects`, `clear-subject`, `composite`, `detour`, `detours`, `return`, `clear`) | actions on `rmx_focus` | — |
| [[#fam-session]] | `session list`, `recall`, `show` (3) | `rmx_session` | `session stats` → `harness` |
| [[#fam-refine]] | `refine list`, `refine show` (2); `curator drain` (1) | `rmx_refine`; `rmx_curator` | `refine accept`, `refine reject` → `operator` |
| [[#fam-taxonomy]] | all 3 (`list`, `add`, `remove`) | `rmx_taxonomy` | — |

**45 verbed + 4 re-decided = 49.** Plus three paths from outside the 49 gain twins:
`curator status` (today `hook`) becomes `rmx_curator`'s twin ([[#fam-refine-drain]]), and
`stats` and `focus export` (today `harness`) become `rmx_graph.stats` / `rmx_focus.export`
([[#decisions-r2]]). So **48 paths leave `LEGACY_UNPAIRED` (140 → 92).** Eight new MCP tools;
`rmx_focus` gains an `action`. {#decisions-count}

Spec review r1 ([[bsd-plan3-task37-spec-7d6c418]], 15 findings) moved `focus composite` and
`taxonomy add`/`remove` from re-decided to verbed: composite's own help says "call it to pull the
composite on demand", and `rmx memory add` / `retag` output tells agents to "add via `rmx taxonomy
add`" — the "zero agent evidence" claims were false (S4). {#decisions-r1}

Spec review r2 ([[bsd-plan3-task37-spec-r2-15232c5]], M7 carried as B2) — decided, not deferred:
the CLAUDE briefing hooks.py writes teaches `rmx stats` (hooks.py ~793, ~823-824, plus the
`rmxst` alias ~951) and `rmx focus export` (~860), and `gmd-curator.md` teaches `rmx stats` three
times (~289, ~505, ~559). Both are agent-facing, so both are verbed here: `rmx_graph` action
`stats` (snapshot read; `stale` param for `--stale`) and `rmx_focus` action `export` (the whole
ring, line-numbered). They leave category `harness`. {#decisions-r2}

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
- **C3 — reads never touch the writer slot.** A read goes through a daemon op with the
  single-attempt budget its row in [[#budgets]] names, or through **`verbs.snapshot_read(root,
  fn, *, partition)`** — a NEW verb-layer reader (r1 B1: no such helper exists today; the CLI's
  `_read_store` raises `ClickException` and falls to `_store_rw`, and `search.cached_replica`
  caches a Store for the life of the process, the bug-136 hazard inside `rmx mcp`). Its contract:
  - opens `catalog.read.duckdb` read-only **per call** and closes it; never caches;
  - refuses any file that is not the replica (never the active writer slot);
  - daemon up, no snapshot yet → `VerbBusyError` worded as a read ("no read snapshot yet");
  - daemon truly ABSENT (classifier says absent) → opens the store read-only in-process EVEN
    when an old snapshot exists (r2 S2: with no daemon the snapshot is stale, so an in-process
    write would vanish from the next read); daemon busy is never treated as absent;
  - the result dict carries `source: "snapshot" | "in-process"`.

  Never `_store()` (the write accessor), never `Store(root, …)` read-write on a live
  `.refmatrix/`, never an in-process `Daemon(...)`. {#c3}
- **C4 — writes go through the daemon.** Via `verbs._call` (or `global_write` for the global
  store); no write is retried silently past the caller's budget. {#c4}
- **C4a — no daemon ⇒ in-process, decided for every family (r2 S2).** Today's CLI serves reads
  and writes in-process when no daemon runs, and the suite depends on it
  (`tests/test_describe.py` ~149-188, `tests/test_subject.py` "All daemon-down"). The verbs keep
  that: on `VerbAbsentError` ONLY (never busy, never path-too-long), a daemon read falls to
  `snapshot_read`'s in-process branch and a write to ONE new helper `verbs.local_write(root, fn,
  *, partition)` (the `_memory_write` local-fallback shape: opens the store read-write
  in-process, runs `fn`, closes). The result carries `source: "in-process"`. No existing test is
  rewritten to accept a new "requires the daemon" error. A call that reads AND writes does its
  reads inside `local_write`'s `fn` on the writer handle — it never holds a `snapshot_read`
  in-process handle while `local_write` opens the writer (r3 M3: bug-135's `StaleDuckDBInstance`);
  a test pins read-then-write in one call with no daemon. {#c4a}
- **C5 — transport errors are classified.** Every handler of a `daemon.call` / `global_call`
  transport exception words it through `classify_transport_error` (`write=True` for writes) and
  raises its type; `tests/transport_guard.py` covers every new function. busy ⇒ `VerbBusyError`,
  absent ⇒ `VerbAbsentError`, refusal (`ok:false`) ⇒ `VerbError` with the daemon's words — never
  an empty answer. {#c5}
- **C6 — parity rows.** `PAIRING` / defaults rows in `tests/test_verb_parity.py` for every twin;
  verbed paths leave `LEGACY_UNPAIRED`, and `LEGACY_BASELINE` shrinks by exactly those paths.
  **Action defaults (r1 S1):** today's defaults test checks only each verb's one `CLI_MAP` twin,
  and shared params conflict across actions (focus `top` 20 vs 60, `limit` 50 vs 20, `k` 10 vs
  40, `linkage` multi/None vs `"mentions"`). So a param whose default differs by action is typed
  `X | None = None` and resolved through `verbs.ACTION_DEFAULTS[(verb, action)]`; a new test
  walks EVERY `CLI_ACTIONS` twin (via `_ACTIONS_SEED` / `CLI_ACTION_INVOKE`) and asserts the click
  default equals the resolved verb default. No `"ALL"` escape for the new verbs. The existing
  `CLI_MAP`-twin defaults test reads `EFFECTIVE_DEFAULTS` derived from
  `ACTION_DEFAULTS[(verb, default action)]`, so `rmx_focus`'s `top: int | None = None` still
  equals `focus context`'s 20 (r2 M2). {#c6}
- **C7 — partition.** A project-store verb forwards the CLI's `-p` / `RMX_PARTITION` partition
  (verb param `partition: str | None`) to every op it calls; a memory or session read uses the
  memory / sessions partition resolver the CLI uses today. {#c7}
- **C8 — no silent failure.** No `except Exception: pass`, no `{}` / `[]` stand-in for a failed
  leg. A leg that is skipped by design (e.g. no git repo) reports it in a `warnings` list. {#c8}
- **C9 — params mirror the CLI (r1 M1).** Verb params are the CLI option names 1:1 in
  snake_case (list-typed where the click option is `multiple=True`), except render-only options
  that write a local file (`--out`), which stay CLI-only and are listed in the parity test's
  CLI-only set (r3 M1); the verb maps them to op arg
  names internally (`name` → the op's `names`, etc.). Exception: a CLI `--project` FILTER
  (session list/recall/stats, refine list) is named **`project_filter`** — `project` is the MCP
  transport's store-selector and the MCP layer overwrites a param of that name (r1 S2). {#c9}

## Route and budget per action {#budgets}

One `READ_BUDGET_S = MEMORY_READ_BUDGET_S` (10 s) does not fit every read (r1 S3). Each action's
route and default budget; every daemon call is single-attempt (`retries=0`) and every budget is
overridable by a `timeout` param. {#budgets-lead}

| verb.action | route | default budget |
|-------------|-------|----------------|
| graph.neighbors / co_occur / top / stats(stale=False) | `snapshot_read` | n/a (local) |
| graph.describe | its existing lock-free daemon op (`describe`), not the snapshot | 10 s |
| graph.stats(stale=True) | daemon `stats` op, `include_stale` | 10 s |
| graph.recall / dense | daemon op (server-side embed; cold model start) | 180 s |
| graph.timeline | snapshot + sessions `memory_search` op + git subprocess (30 s) | 60 s |
| canon.find | federated (as `rmx_where`; `federated_concept` reads cached replicas and takes no timeout — none is claimed) | n/a, `skipped` |
| canon.siblings, matrix.list_* / run | `snapshot_read` | n/a |
| canon.link, matrix writes, curate (not forget) | `_call` write | 60 s |
| curate.forget (not dry-run) | `_call` write | 600 s |
| focus.* (STM) | STM files | n/a |
| focus.subjects | `_call` on `memory_partition(root)` | 10 s |
| focus.clear_subject | local STM file op (cli.py ~1808), r2 M1 | n/a |
| focus.composite | `snapshot_read` + resolved session | n/a |
| session.list / recall / show | `_call` (`memory_iter` 100k rows / `memory_get` / `memory_search`); absent ⇒ C4a | 60 s |
| refine.list / show | `_hub_rpc` | hub default |
| curator.status / drain | `.refmatrix/curator.spool/` files (no lock) | n/a |
| taxonomy.* | `~/.refmatrix/taxonomy.json` under a file lock | n/a |

## Families {#families}

### graph-read {#fam-graph-read}

`rmx_graph(action=…)`. Read-only graph navigation beside `rmx_context` / `rmx_query`. Agent
evidence: the PRIMER header and the hooks.py CLAUDE briefing teach `neighbors`, `co-occur`,
`top`; cli.log shows `neighbors` 95 and `describe` 29 calls. {#fam-graph-read-lead}

| action | CLI path | route (C3) | params beyond `partition` |
|--------|----------|------------|---------------------------|
| `neighbors` | `neighbors` | `snapshot_read` — today it reads through `_store()`, the WRITE accessor, so a busy daemon says "writes go through the daemon" | as the CLI |
| `co_occur` | `co-occur` | `snapshot_read` | as the CLI |
| `top` | `top` | `snapshot_read` | `linkage`, `concept`, `k` |
| `describe` | `describe` | its existing lock-free daemon op (r1 S3) | as the CLI |
| `recall` | `recall` | a NEW daemon op `graph_recall` that runs exactly the CLI's algorithm server-side (see [[#fam-graph-read-recall]]) | `query`, `k`, `kinds`, `concept`, `symbolic`, `no_dense` |
| `dense` | `search-dense` | daemon `ann_search` op WITH `partition` (today omitted — ids resolve against the wrong partition under `-p`); names resolved from the same partition | `query`, `k`, `kinds` |
| `stats` | `stats` (outside the 49, [[#decisions-r2]]) | `stale=False` → `snapshot_read`; `stale=True` → the daemon `stats` op with `include_stale` (the replica's `tracked_files` is not refreshed — cli.py ~7681-7720 forbids `--via-replica --stale`), absent ⇒ C4a (r3 S1) | `stale` |
| `timeline` | `concept timeline` | graph leg from the snapshot; session leg through the daemon `memory_search` op on the sessions partition (budgeted); git leg via subprocess. A failed leg is a `warnings` entry, never `except: pass`; the direct `Store(...)` open in `_iter_session_memories` is gone | `concept`, `hops`, `since`, `until`, `k`, `git` |

- `recall` no longer loads `Embedder()` in the caller's process. It does NOT go through the
  `memory_recall` op (r1 B2): that op fuses BM25 with dense by default and reranks under the
  store lock, while the CLI is pure dense by default and `-s` is a RANKED input to fusion, not a
  filter. `graph_recall` runs the CLI's own code path server-side — `bitmap_prefilter` from
  `--concept` → `candidate_ids`; `dense_recall` by default; `hybrid_recall(symbolic_hits=…,
  candidate_ids=…)` when `-s` is given; the symbolic-only fallback when dense is unavailable or
  `no_dense` — with no rerank and no fusion unless the CLI does it, the embed outside the store
  lock, reads from a read store (the `memory_recall` bug-098 pattern). A test pins the rank
  order the base CLI (`591a2fb`) produces on a fixture store, with ONE deterministic test
  embedder injected into both paths (the base CLI's `Embedder()` and the daemon's
  `d._embedder()`), r2 M3. `-s` values are validated as ints
  (`VerbArgsError`). **No daemon (decided 2026-10-20, Batch B RED):** `recall` / `dense` follow
  C4a — on `VerbAbsentError` only, they run the SAME library function the `graph_recall` /
  `ann_search` op runs, in-process over a read-only store, with the embedder from the accessor the
  daemon uses (the hub's shared model worker when it is up); the result says `source:
  "in-process"`. Busy never runs in-process. This keeps today's daemonless CLI working; the
  "no `Embedder()` in the caller" rule binds the daemon-up path. {#fam-graph-read-recall}
- `top`: `gmd-curator.md` lines 290 and 511 teach `rmx top mentions -k N`, which treats
  `mentions` as the concept (2 of 3 logged calls failed). The comments want the most-referenced
  entities, which is `rmx primer`; rewrite both lines to it in the template
  (`src/refmatrix/templates/agents/gmd-curator.md`) AND the installed
  `.claude/agents/gmd-curator.md` (r1 M3). {#fam-graph-read-top}
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
  the writer lock; delete them unless a verb in this task calls one — from `OPS` AND from the
  daemon's interactive-pool op list (daemon.py ~6565, r1 M2). {#fam-matrix-edit-dead}

### curation {#fam-curation}

`rmx_curate(action=protect|unprotect|noise|unnoise|forget, names=…, like=…, namespace=…,
kind=…)`. The selector forms are exactly the CLI's; the `set_flag` / `forget` daemon ops already
take them. Agent evidence: every generated PRIMER.md header prints
`rmx protect|unprotect|noise|unnoise|forget <sel>`. {#fam-curation-lead}

- At least one selector is required (`VerbArgsError`).
- `forget` defaults to `dry_run=True` in the verb: it returns what WOULD be forgotten. A
  selector that is ONLY `kind` and/or `namespace` (no `names` / `like`) also requires
  `broad=True`, else `VerbArgsError` naming the count it would remove. The CLI twin keeps its
  confirmation / `-y` behaviour and passes `dry_run=False, broad=True` after it (logged operator
  wipes like `forget --kind code -y` still work). The forget op keeps its 600 s write budget.
  {#fam-curation-forget}

### focus {#fam-focus}

`rmx_focus` gains `action: Literal["context", "tail", "show", "topics", "subject", "subjects",
"clear_subject", "composite", "export", "detour", "detours", "return", "clear"] = "context"`
(`export` is `focus export`, outside the 49, [[#decisions-r2]]; the verb RETURNS the
line-numbered events, and `-o/--out` stays a CLI-only render option declared as such — an MCP
call never writes a file, r3 M1). `context` is today's
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
  refusal is a `VerbError`. The defect shows only when the memory partition differs from the
  project partition (legacy `memory-<p>` or `-p`), so its RED test sets that up (r1). {#fam-focus-subjects}
- **Defect fixed here — `focus composite`** (verbed per r1 S4: its help says "call it to pull
  the composite on demand"): it has no `--session` and `composite.py` calls `latest_session`
  directly, skipping the one resolver. The action resolves through `resolve_session_source`
  (`purpose="read"`) and reads via `snapshot_read`; the CLI gains `--session`. {#fam-focus-composite}

### session {#fam-session}

`rmx_session(action=list|recall|show)` over the `sessions-<project>` partition.
{#fam-session-lead}

- Every read goes through daemon ops (`memory_iter`, `memory_get`, `memory_search`) with a
  bounded single-attempt budget, partition from the existing `_session_partition` resolver.
  busy ⇒ `VerbBusyError`; absent ⇒ C4a (in-process read-only, never the writer slot
  read-write). **Defect fixed here:**
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
error", a timeout a traceback). `rmx_curator(action=status|drain)` — the curator queue the
gmd-curator agent reads and drains (`gmd-curator.md` :138, :150). {#fam-refine-lead}

- **Re-decided: `refine accept`, `refine reject` → `operator`.** They are the human approval
  gate of the "no silent writes" refinement queue; the hub UI is the other surface for the same
  gate. Code check: `gmd-curator.md` never calls `rmx refine` (the old reason "the gmd-curator
  agent drives it" was false). {#fam-refine-gate}
- **`rmx_curator` (r1 B3; redesigned at r4).** Drain today reads nothing: entries appended
  between the agent's `curator status` snapshot and its `curator drain` are lost, the hooks run
  `curator status --drain` on every prompt, and an MCP agent offered only a drain could not take
  the snapshot. Rounds r2-r4 patched a single shared queue file with a token, a lock, a
  generation counter and an in-place truncate, and each patch opened a new loss window (inode
  reuse, a counter reset, a crash mid-drain, entries held in daemon memory across a fast-exit).
  The shared mutable file is the defect, so it goes. **A spool directory replaces it:**
  - the daemon watcher (`_enqueue_curator`, daemon.py ~3115) writes each flush as ONE new file
    `.refmatrix/curator.spool/<time_ns zero-padded to 20 digits>-<uuid4>.jsonl` (names sort
    oldest-first) — written to a `.tmp` name, fsynced, then `os.rename`d into place. No lock,
    nothing held in memory, nothing a reader can see half-written; a write failure is logged with
    a count (C8). Readers glob `*.jsonl` only; the daemon deletes stale `*.tmp` files (its own
    crash leftovers) at startup (r5 M1);
  - ONE JSON-lines parser (r2 B1) reads every spool file: the watcher writes `{ts, path, reason}`
    per line, but `gmd_curator.read_queue` today reads each line as a raw path (its fixture uses
    raw paths, so it passes on a format nobody writes, and the scheduled `curator scan` finds zero
    files then deletes the queue). A bad line is counted and returned as a warning; an `OSError`
    is raised — EXCEPT `ENOENT` on a listed file or on the legacy rename, which means a
    concurrent drain took it: that file is skipped, kept out of the token and reported in
    `missing` (r5 S2). Fixtures use the watcher's format. Bug row logged;
  - `status(max_entries=500)` returns the parsed entries of the oldest files up to `max_entries`
    (whole files only), `token = [<spool file names it read>]` oldest first, and
    `spool = {files, bytes, remaining_files}` so a never-drained spool is visible (r5 M2);
  - `drain(token)` unlinks exactly those files. A name already gone is reported in `missing` (a
    concurrent drain took it — never an error, never a deletion of anything else); no token is a
    `VerbArgsError`. A file written after `status` is never in the token, so it can never be
    drained unread. RED test: status → hook `status --drain` → new flush → `drain(old token)`
    removes nothing new and the new entries are still returned by the next `status`;
  - `curator status --drain` (the generated hooks' form) is status-then-drain(token) through the
    verb; `scan_and_enqueue(drain=True)` (the scheduled `curator scan`) drains only via
    `drain(token)`; `gmd_curator.drain_queue`'s swallowed errors are surfaced (C8);
  - no src path other than `drain(token)` (and the daemon's startup `*.tmp` sweep) deletes a
    spool file, and nothing unlinks the legacy
    `curator.queue` (today cli.py ~9136 / ~9160 / ~9171 and `gmd_curator.drain_queue` do) — a
    test greps `src/` for both (r4 M1);
  - **rollout:** a daemon still running pre-3.7 code appends to the legacy `curator.queue` until
    it is restarted (every deploy restarts daemons). `status` first moves a legacy file into the
    spool with ONE `os.rename` (atomic), so its entries are drained like any other spool file;
    the remaining window — an old-code append through an fd opened before that rename — closes at
    the deploy's restart and is named in the release notes;
  - twins: `curator status` (no `--drain`) is the `CLI_MAP` twin (it leaves category `hook`);
    `curator drain` is a `CLI_ACTIONS` twin. The CLI passes the token: `curator status --json`
    emits it, `curator drain --token <names…|@file>` takes it back; `token` and `max_entries`
    (CLI `--max-entries`) get PAIRING rows. The existing click `curator status --limit` (default
    10, cli.py ~9105: sample paths printed in the hook's context line) stays a CLI-only render
    option, declared as such like `--out` (r6 S1). The gmd-curator agent's documented flow (`gmd-curator.md` ~136-150, ~692:
    `rmx curator status > /tmp/snap.txt` … `rmx curator drain`, no token) is rewritten to
    `status --json` → `drain --token @<file>` in the template AND the installed
    `.claude/agents/gmd-curator.md` (r5 S1). {#fam-refine-drain}
- Defects found in the re-decided operator paths are logged as bug rows (accept KeyError on a
  gmd-curator candidate; reject has no pending check; accept writes project memories to
  `store_name` not `memory_partition`; candidate ids use per-process `hash()`), not fixed here.
  {#fam-refine-bugs}

### taxonomy {#fam-taxonomy}

`rmx_taxonomy(action=list|add|remove)` — the shared tag vocabulary. Agent evidence: `rmx memory
add` / `retag` output tells agents to "add via `rmx taxonomy add`" (r1 S4). {#fam-taxonomy-lead}

- **Parity fix:** the `memory_add` verb AND the `rmx_memory` `retag` action return
  `tag_warnings` for tags outside the vocabulary (the warning the CLI prints today; MCP adds and
  retags never get it, r1 M6). The warning points at `rmx_taxonomy` (action `add`).
- `add` / `remove` write `~/.refmatrix/taxonomy.json` atomically (temp + rename) under an
  `fcntl` lock on a sidecar `taxonomy.json.lock` that is never deleted — never on the file the
  rename replaces (r6 M3; today: no lock). {#fam-taxonomy-admin}
- **Defect fixed here (data loss):** a corrupt `~/.refmatrix/taxonomy.json` silently loads the
  defaults, and the next `add` / `remove` overwrites the user's file. After the fix (r1 S5):
  - `add` / `remove` REFUSE to write over a corrupt file (`VerbError` naming the file);
  - `list` and tag validation DEGRADE: they report the corruption as a warning and validate
    against nothing — a corrupt vocabulary never blocks `memory add` / `retag`;
  - a read never writes (today `load` writes the default file on first read). {#fam-taxonomy-corrupt}

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
partition, focus clear session, focus subjects partition, focus composite session, taxonomy
overwrite and read-writes, curator drain race and swallow, curator queue parser format. Logged
open: the four refine operator bugs. {#defects-lead}

## Acceptance criteria {#acceptance}

Per family (each a separate RED → GREEN step): {#ac-family}

1. **Verbed paths** meet C1-C9 (incl. C4a); each fixed defect has a test that fails at the task's base
   (`591a2fb`) and passes after.
2. **Re-decided paths** move to their category in `LEGACY_UNPAIRED` with the reason above; the
   reason no longer says `verb-it`.

Global ACs:

- **AC-G1.** No path remains in category `verb-it`; the category itself is removed from
  `LEGACY_CATEGORIES` once empty (the shrink-only pin then forbids its return).
  `test_every_verb_it_path_names_its_task_3_7_family` is updated to assert the empty set and
  that each of the 49 paths is either a twin of the verb named in [[#decisions]] or in the
  re-decided category named there. Until batch C lands, the family's paths still in `verb-it`
  keep their `task-3.7#fam-…` reason (the test holds at every batch boundary). {#ac-g1}
- **AC-G2.** `VERB_IT_FAMILIES` in `tests/test_task3_6_r9_remedy.py` mirrors [[#decisions]]
  (verbed vs re-decided) and partitions the 49 paths. {#ac-g2}
- **AC-G3.** Three `workflow/deferral_registry.md` rows move to resolved, citing this task: "The
  49 `verb-it` CLI paths", "`tests/transport_guard.py` fixed-point loop unpinned by plant order",
  and "Two transport handlers render the raw exception outside the one classifier" (named by
  content; the registry has no row ids, r1 M4). {#ac-g3}
- **AC-G4.** Plan-3 closes when this task is `completed`. {#ac-g4}
- **AC-G5.** `LEGACY_BASELINE` shrinks by exactly the 48 paths that gain twins (45 verbed +
  `curator status` + `stats` + `focus export`; 140 → 92); the total of invocable paths is unchanged; the categories assert
  (`tests/test_verb_parity.py` ~642) is updated for the removed `verb-it` category. {#ac-g5}
- **AC-G6.** `rmx install-hooks --check` clean; `docs/ARCHITECTURE.md` `{#cli-hook-surface}`
  regenerated so `tests/test_docs_generated.py` passes; other generated CLI-tree / tools-primer
  artifacts regenerated where a test pins them (r1 M5). {#ac-g6}

## Build order {#schedule}

One clone (`/Volumes/littlebig/refmatrix-task-3.7`), one branch, batches landing in order so
`verbs.py` / `cli.py` / `test_verb_parity.py` are never edited by two agents at once:

1. **Batch A:** `snapshot_read` + `local_write` + `ACTION_DEFAULTS` (shared infrastructure),
   focus (incl. `export`), curation, taxonomy, curator, R52, R53.
2. **Batch B:** graph-read, canon.
3. **Batch C:** matrix-edit, session, refine; AC-G1..G6.

Each batch: `@ch-test-engineer` RED (run recorded) → `@ch-implementer` GREEN → relevant tests
logged. After batch C: full suite, mutation check, `/ch-review`, `@ch-bsd` iterated to clean,
summary, release.

## Remedy round 1 (2026-10-20) {#remedy-r1}

Sources: ch-bsd post-implementation audit [[bsd-plan3-task37-impl-41c3568]] (DIRTY, 2 BULLSHIT /
2 SKETCHY / 2 MEH; mutations 16/18 killed) and a ch-code-reviewer pass (0 Critical / 1 High /
8 Medium). Decisions by the orchestrator on the user's pattern, plus one user decision (R-OBJC).
Every code fix gets a RED test first, except pure deletions and docstrings. {#remedy-r1-lead}

| id | finding | decision |
|----|---------|----------|
| R-B1 | the generated per-prompt hook `curator status --drain` drains entries it never showed (prints 10, drains 15), so the gmd-curator's `status --json → work → drain --token` flow never sees them | the generated hooks run `curator status` WITHOUT `--drain`; only the curator agent's `drain --token` removes entries. The prompt line keeps showing the count until the curator runs (it is the reminder). `--drain` stays on the CLI for operators but drains only what that call printed (`max_entries = limit`) |
| R-B2 | `focus composite` ignores `-p`; `project_partition` skips the `.refmatrix/partition` marker (review M3) | ONE shared partition resolver used by the CLI's `_resolve_partition` and `verbs.project_partition` (flag → `RMX_PARTITION` → marker → store name); `rmx_focus` gains `partition: str \| None`, PAIRING row updated, the CLI passes its resolved partition |
| R-S1 | add-then-link fails: `link` / `unlink` / `canon link` resolve names on the lagging snapshot | the verbs send NAMES; `_op_link`, `_op_unlink`, `_op_link_canon` resolve them under the writer. Read-your-writes RED test against a real daemon |
| R-S2 | the "unknown partition reads EMPTY" guards are untested (M11, M18 survived) | one test per guard (`verbs.snapshot_read`, `Store.with_partition` read-only) asserting empty while partition 1 has rows; both mutations re-run and must die |
| R-M1 | two known base failures have no bug row | rows for the GMD repo-scope gate and the AC-6 clone-only fixture failure (not bug-138, which is reserved) |
| R-M2 | a legacy raw-path `curator.queue` adopted into the spool counts its lines unparseable and loses them | the one parser accepts a raw-path line as a legacy entry (`reason: legacy`) |
| R-H1 | no daemon: every `rmx_graph` recall/dense in the long-lived `rmx mcp` spawns a never-reaped embed worker | `recall.shared_embedder` caches ONE client per process (lock, one atexit close); test: N calls → one client |
| R-RM1 | `_op_ann_search` reads `d._st()` before taking the lock | pass a getter resolved inside `with lock` |
| R-RM2 | `_op_graph_recall` reads the partition name unlocked | fall back to `d.partition` |
| R-RM4 | `canon` link re-implements `_matrix_write` | call `_matrix_write` |
| R-RM5 | forget preview budget 60 s (was 600 s) | 600 s for preview and purge |
| R-RM6 | taxonomy add/remove lets `OSError` escape raw | `VerbError` naming the file |
| R-RM7 | dead `_DaemonWriter.unlink/link_canon/save_query`, `_since_to_iso`, `_TIMELINE_LINKAGES`, `_concept_files` | deleted; `tests/test_concept_timeline.py` points at `graphread` |
| R-RM8 | FakeDaemon rows promised graduation "when batch C lands" | graduate one payload test per family (canon, curation, matrix, focus) onto a spawned daemon, or rewrite the rows' terms — graduation chosen |
| R-L | lows: `with_partition` docstring; unused imports/vars; one `session_title` helper; `session show` refuses an ambiguous prefix like `refine show`; type hints on new signatures; `write_spool` fsyncs the directory; deprecation warning on the ignored `--via-replica` | all applied |
| R-OBJC | user, 2026-10-20: "yes, ship the OBJC fix with 3.7" | `HOOK_ENV` exports `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` and `TOKENIZERS_PARALLELISM=false` (exactly what `_reexec_for_fork_safety` sets), so hook processes skip the re-exec; RED test over the generated config; README hooks table regenerated |

**r1 test-side follow-ups (2026-11-08, `1df6c25`).** {#remedy-r1-test-followups}
R-L's directory fsync broke `test_write_spool_is_tmp_fsync_rename_and_never_visible_half_written`,
which pinned the event list to exactly `[fsync, rename]`. The test now identifies each fsync by
`fstat` and pins `fsync(regular file) → rename (within the spool dir) → fsync(spool dir)`, with the
file fsync on the renamed inode at its full size. Mutations, each RED then restored by
`git checkout`: drop the pre-rename file fsync; replace the rename with copy + unlink; drop the
directory fsync. R-RM7's kept `cli._concept_files` alias is deleted;
`tests/test_concept_timeline.py` imports `concept_files` from `graphread`.

## Remedy round 2 (2026-11-08) {#remedy-r2}

Source: ch-bsd re-audit `workflow/bullshit/2026-11-08-2256-task-3.7-remedy-r1-2a4096c.md` #s-1
(SKETCHY): R-H1's process-wide embed client `recall._EMBED_CLIENT` is never dropped, so after the
hub dies a daemonless process keeps the dead hub-shared client.

**RED (R2-S1).** `tests/test_task3_7_remedy_r2.py`, red log
`workflow/review-output/task-3.7/r2-red-embed-client.log`. A real `ModelServer` in a subprocess
is SIGKILLed after one successful call. Then: (1) `test_a_hub_crash_does_not_pin_the_process_to_its_dead_shared_client`.
After the first failed call, later calls must not hold the dead client. They must embed through a
fresh private worker that is shared across calls, and the in-process model may load at most once.
At HEAD all three calls fail with `ConnectionRefusedError` on the same dead client, and no fallback
runs. (2) `test_a_cached_client_that_fails_in_shared_embedder_is_dropped_not_retried` uses the
audit probe's shape: a cached client with no header and no hub. At HEAD the in-process model loads
3 times and the dead client stays cached. {#remedy-r2-red}

**GREEN must cover both paths.** The audit's fix (drop the cache in `shared_embedder`'s `except`
branch) turns only (2) green. On the real path `SharedWorkerClient.info()` returns its cached
header without touching the socket, so `RemoteEmbedder.dim` succeeds and the failure surfaces
later in `embed_texts`, outside that branch. After a failed call the client's `alive()` is False
(`close()` nulls `_sock`), which is one signal that `_process_embed_client` could check. R13
(`test_no_daemon_graph_calls_share_one_embed_client`) must stay green. {#remedy-r2-green-note}

**GREEN `4643541`.** `recall._process_embed_client` is the one place that judges the cached
client. A hub-shared client that was handed out and now reports `alive()` False is closed,
counted in `_EMBED_CLIENT_REBUILDS`, logged, and replaced by a fresh `new_model_client`. A
private `WorkerClient` is never rebuilt, because it respawns its own process. One atexit closer
handles whichever client is cached at exit. Log: `workflow/review-output/task-3.7/r2-green-embed-client.log`.
Registry row: bug-171. {#remedy-r2-green}

**RED for the MEH findings (R2-M1..M3).** {#remedy-r2-meh-red} The source is the same audit,
findings #m-1, #m-2 and #m-3. The tests are in `tests/test_task3_7_remedy_r2_meh.py` and the red
log is `workflow/review-output/task-3.7/r2-red-meh.log` (4 failed on their assertions; R12
`test_a_raw_path_legacy_queue_line_is_a_legacy_entry` stays green). No doubles are used.

- R2-M1 `test_drain_behind_an_oversized_head_file_reports_what_it_kept_on_stderr`. The spool is a
  15-path head file followed by three 2-path files, and the command is `curator status --drain`
  with limit 10. Every file must stay. Stdout must still carry the `curator-queue: 15 ... +5 more`
  line. Stderr must match `kept 1 spool file` and name `--limit`. As a control, with `--limit 100`
  the kept notice is silent. At HEAD stderr is `''`.
- R2-M2 `test_the_shipped_curator_template_does_not_say_a_hook_drains_the_spool`. The test reads
  the curator segments of the generated hooks (`hooks._claude_hook_block`). If none of them runs
  `--drain`, then no line of the shipped template may pair "hook" with draining. At HEAD template
  lines 139 and 145 match. The repo copy `.claude/agents/gmd-curator.md` is hand-maintained:
  `install_agents` skips an existing file without `--force`, and the copy has diverged in its GMD
  frontmatter and its extra sections. It needs the same two-line fix by hand. It is not covered by
  this test.
- R2-M3 `test_a_non_path_legacy_line_is_counted_bad_not_an_entry` and
  `test_a_non_path_raw_line_in_a_watcher_spool_file_is_counted_bad`. **Rule:** a non-JSON line is a
  legacy path only when it has no internal whitespace AND contains `/` or has a file suffix.
  Every other non-JSON line is a counted bad line and gets the existing `N unparseable line(s)`
  warning. The rule applies in every spool file, because an adopted `curator.queue` takes the
  normal spool name, so a file's origin cannot be observed. At HEAD both `not a path at all` and
  `Traceback (most recent call last):` become `reason: legacy` entries.

## Definition of done {#done}

- Each family: RED (recorder/parity/defect rows) before GREEN; mutation check; summary rows in
  `workflow/implementation_summaries/task-3.7-verb-it-backlog.md`.
- `@ch-bsd` over the range: no unaddressed BULLSHIT.
