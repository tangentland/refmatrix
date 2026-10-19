---
gmd: "0.1"
id: impl-task-3.4-internal-cli-allowlist
title: "Task 3.4: every invocable CLI path classified exactly once; the seven memory writes call the verb"
tags: [implementation, plan-3, verbs, parity, cli]
metadata:
  node_type: implementation-summary
  date: 2026-10-19
---

# Task 3.4: the reverse parity walk {#root}

rel: implements -> [[task-3.4-internal-cli-allowlist]]
rel: evidence-for -> [[bsd-plan3-verbs-parity-r8-d4bf001#s-4]]
rel: implements -> [[deferral_registry]]
rel: part-of -> [[plan-3-verbs-parity]]

TDD GREEN for the RED group committed at `0965546` (`tests/test_verb_parity.py`, section
"task 3.4"). Built from the r8 `#t34-build` list. No tests were written in this step.

## What changed {#changes}

- **`src/refmatrix/verbs.py`**: added `CLI_ACTIONS` (15), `INTERNAL_CLI` (8, each reason quotes
  the user's 2026-10-06 words), `HIDDEN_ALIASES` (6), `LEGACY_CATEGORIES` (the closed set of
  five) and `LEGACY_UNPAIRED` (140), next to `CLI_MAP` / `MCP_ONLY`. `_legacy(category,
  reason, *paths)` builds one family per reason and raises at import on an unknown category.
  `memory()` now honours an explicit `timeout` on WRITE actions (`120 s` stays the default).
- **`src/refmatrix/cli.py`**: `forget`, `reclassify`, `retag`, `link`, `score`, `bulk-forget`
  and `dedup` call `verbs.memory(action=…)` through one helper, `_memory_write(action, local,
  **kw)`. It returns the verb's result when a daemon is up, runs `local()` (the in-process
  store, the same code these commands ran with no daemon) ONLY on `VerbAbsentError`, and turns
  `VerbBusyError` / `VerbError` into a ClickException. `reclassify` and `bulk-forget` keep the
  dry-run preview and the confirm, with both calls going through the verb. `bulk-forget`'s
  delete passes `timeout=600.0`. Rendering reads the verb's result keys. The bare `ping` gates
  and their `_memory_daemon_call` payloads are gone from all seven.
- **`workflow/deferral_registry.md`** row 47 is marked RESOLVED.

Exact signatures:

```python
def _memory_write(action: str, local: "Callable[[], dict]", **kw) -> dict  # cli.py
CLI_ACTIONS: dict[tuple[str, ...], tuple[str, str]]
INTERNAL_CLI: dict[tuple[str, ...], str]
HIDDEN_ALIASES: dict[tuple[str, ...], tuple[str, ...]]
LEGACY_CATEGORIES: dict[str, str]
LEGACY_UNPAIRED: dict[tuple[str, ...], tuple[str, str]]
```

## Per-AC status {#acs}

| AC | Status | Where |
|----|--------|-------|
| AC-1 new command fails, real copy | GREEN | the walk lives in the test; the maps supply the classes |
| AC-2 `INTERNAL_CLI` is the 8 R1 keys, each quoting the user | GREEN | `verbs.INTERNAL_CLI` |
| AC-3 stale-key hygiene over all five maps | GREEN | every key resolves; `gen-cli-tree --check` ok |
| AC-4 exactly one class per path | GREEN | 195 paths = 26 twins + 15 + 8 + 6 + 140 |
| AC-5 `CLI_ACTIONS` = 15, each action in its verb's Literal | GREEN | `verbs.CLI_ACTIONS` (no Literal change was needed) |
| AC-6 the 15 action twins call the verb; bulk-forget carries 600 s | GREEN | `cli._memory_write` + the seven commands |
| AC-7 six hidden aliases | GREEN | `verbs.HIDDEN_ALIASES` |
| AC-8 LEGACY categorised, shrink-only | GREEN | `verbs.LEGACY_UNPAIRED` |
| AC-9 docs | DONE | this file, deferral row 47 |
| AC-10 pre-existing parity / MCP / memory CLI tests | GREEN except one (see [[#flag]]) | |

## LEGACY_UNPAIRED decision table {#legacy-table}

Counts: **verb-it 50, operator 43, maintenance 27, hook 11, harness 9** (140).

| category | reason (family) | paths |
|----------|-----------------|-------|
| verb-it | graph read an agent runs to navigate the matrix | `neighbors`, `co-occur`, `top`, `describe`, `recall`, `search-dense`, `concept timeline`, `pairs show` |
| verb-it | cross-project canon view | `canon find`, `canon siblings`, `canon link` |
| verb-it | low-level matrix edit / saved-query surface | `add concept`, `add entity`, `add linkage-type`, `link`, `unlink`, `list entities`, `list linkages`, `list queries`, `run`, `save-query` |
| verb-it | entity curation the primer tells agents to use | `protect`, `unprotect`, `noise`, `unnoise`, `forget` |
| verb-it | STM focus read / navigation mid-session | `focus tail`, `focus topics`, `focus show`, `focus subject`, `focus subjects`, `focus clear-subject`, `focus composite`, `focus detour`, `focus detours`, `focus return`, `focus clear` |
| verb-it | session-history lookup | `session list`, `session recall`, `session show`, `session stats` |
| verb-it | refinement-queue review the gmd-curator agent drives | `refine list`, `refine show`, `refine accept`, `refine reject`, `curator scan`, `curator drain` |
| verb-it | shared tag vocabulary | `taxonomy list`, `taxonomy add`, `taxonomy remove` |
| hook | invoked by a generated Claude Code hook | `focus hook`, `focus record`, `focus summarize`, `scan-prompt`, `primer`, `grep`, `sync`, `curator status`, `install-hooks` |
| hook | the memory bridge (SessionStart, save-state) | `ingest-gmd`, `memory sync-disk` |
| operator | per-store daemon lifecycle | `daemon start`, `daemon stop`, `daemon restart`, `daemon status` |
| operator | launchd supervision | `daemon launchctl install/kickstart/print/status/uninstall`, `hub launchctl install/status/uninstall`, `session launchctl install/status/uninstall` |
| operator | hub lifecycle and fleet control | `hub start`, `hub stop`, `hub status`, `hub pause`, `hub resume`, `hub relaunch-fleet`, `ui`, `mcp`, `bus sub` |
| operator | replica slot rotation | `replica audit`, `replica merge`, `replica path`, `replica refresh`, `replica status` |
| operator | partition layout (ADR-0003) | `partition add`, `partition audit`, `partition drop`, `partition list`, `partition merge`, `partition rename` |
| operator | scheduled per-project jobs | `schedule add`, `schedule list`, `schedule remove` |
| operator | install, identity and store setup | `init`, `upgrade`, `version`, `info`, `watch` |
| maintenance | derive / ingest pass | `reingest`, `rebuild`, `embed`, `pagerank`, `graphify-warm`, `tldr-warm`, `session ingest`, `memory compile`, `pairs compile`, `focus rebuild`, `focus promote-edges`, `coref link` |
| maintenance | repair, compaction, cleanup | `checkpoint`, `compact`, `compact-log`, `repair-index`, `vacuum`, `prune-noise`, `untrack`, `merge-verb-aliases`, `audit-same-as`, `queue`, `queue clear` |
| maintenance | migration, export, import | `migrate-to-duckdb`, `export`, `import`, `dump-log` |
| harness | telemetry, log and debug inspection | `telemetry`, `cli-log`, `log`, `cctree`, `stats`, `fingerprint`, `tools-primer`, `focus size`, `focus export` |

Judgement calls, so a reviewer can contest them: `bus sub` is `operator` because it streams to a
terminal and agents already have `rmx_bus_read`. `grep` is `hook` because agents reach it through
the grep-rewrite-guard PreToolUse rewrite, not as a capability of its own. `curator scan/drain`
are `verb-it` because the shipped gmd-curator agent template calls them.

## Runs {#runs}

- RED: `workflow/review-output/task3.4-3.5-red.log` (test engineer, `0965546`).
- GREEN, the three target files: `workflow/review-output/task3.4-3.5-green-targets.log`,
  86 passed.
- Plan-3 + memory files: `workflow/review-output/task3.4-3.5-green-plan3.log`.
- Full suite: `workflow/review-output/task3.4-3.5-green-full.log`: 2990 passed, 21 failed, 19
  skipped. 19 of the failures are the clone-only DEV TREE refusals (`upgrade`, `launchctl`/plist,
  `daemon restart --relaunch`: "this interpreter runs a DEV TREE", "refusing to render a plist
  against a dev tree", "… is a dev tree"). 1 is the gmd repo-scope gate (`docs/INDEX.md`
  dangling ADR ids), and 1 is the forget test flagged in [[#flag]].
- Plan-3 + memory files: 417 passed, 1 failed (the same flagged test).
- Mutation check (drop a `CLI_ACTIONS` key, route a write back to `_memory_daemon_call`, add a
  LEGACY key): see [[#mutation]].

## Mutation check {#mutation}

Log: `workflow/review-output/task3.4-3.5-mutation.log`. These are the three mutants the spec's
definition of done names, each applied to the committed GREEN tree and then reverted:

| mutant | killed by |
|--------|-----------|
| drop `CLI_ACTIONS[("task", "swap")]` | `test_every_invocable_cli_path_is_classified_exactly_once` |
| route `memory forget` back to `_memory_daemon_call` behind `ping` | `test_cli_action_twin_calls_its_dispatcher_verb[memory-forget]` |
| add a LEGACY key (`("memory", "get")`, already a twin) | `test_every_invocable_cli_path_is_classified_exactly_once` |
| `verbs.memory` ignores an explicit write `timeout` | **survives**; see [[impl-task-3.5-r8-remedy#mutation]] |

## Flagged {#flag}

`tests/test_lance_drop_failures_loud.py::test_memory_forget_carries_the_count_from_the_daemon`
patches `cli._memory_daemon_call` and `daemon.ping`, the exact seam AC-6 removes from `memory
forget`. Its intent (the daemon's `vector_delete_failed` count reaches stderr) still holds through
the verb's result, and `_say_vector_delete_failures` is still called on it. The test needs its
seam moved to `verbs.memory` (or a real daemon) by `ch-test-engineer`. The implementer does not
edit tests.
