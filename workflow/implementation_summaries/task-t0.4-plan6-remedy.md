---
gmd: "0.1"
id: impl-task-t0-4-plan6-remedy
title: "T0.4 GREEN: the plan-6 remedy (facade deleted, wrapper plumbing gone, registry guarded, phrase families)"
tags: [implementation-summary, t0, t0-4, plan-6, duckdb-view, search-hooks, mock-registry, deferrals, bug-008]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-18
---

# T0.4 GREEN: the plan-6 remedy {#root}

rel: implements -> [[task-t0-suite-trust-sweep#t0-4]]
rel: implements -> [[plan-6-deferrals-docs-benchmark#q1]]
rel: evidence-for -> [[bsd-plan6-deferrals-docs-benchmark-r1-e0b7df6]]
rel: depends-on -> [[self-audit]]

Branch `task-t0.4-plan6-remedy` in `/Volumes/littlebig/refmatrix-t04-green`, base `c8ff7a3e`
(master). RED (red-t04, `8533d258`, `1907379b`) merged at `3bb81ed8`. GREEN commits:
`578b48ea` (R4.1, R4.3, R4.5-R4.7, R4.9) and `5eae7916` (R4.2 registry). Interpreter: the dev
tree's `.venv-eval` with `PYTHONPATH=<clone>/src`; test runs on the mini lane
(`scripts/lane-mini.sh`), logs under `workflow/review-output/t04-*.log`. {#lead}

## What was built {#built}

- **R4.1 (#b-1, plan-6 Q1 "Delete").** The three facts were re-checked at `c8ff7a3e` and all
  hold ([[#r0-facts]]), so `src/refmatrix/duckdb_view.py`, `tests/test_duckdb_read_routing.py`
  and `tests/test_duckdb_parity.py` are deleted. In `store.py` the `_read_via_duckdb` /
  `_duck_view` / `_read_conn` state, the flag branch of `_read()` and its close step are gone;
  `Store._read(self)` keeps its name and returns `self._connect()`, the one SELECT entry point the
  read sites call. Stale mentions: the `_connect` comment, `daemon._load_from_snapshot`'s
  docstring, and four places in `docs/ARCHITECTURE.md` (box, module table, dependency flow, the
  phase-1 paragraph, which now says the facade was deleted). Task 6.1's "Correction to this spec"
  paragraph gains an anchor `{#correction}` and a superseded note citing this task.
  {#built-r4-1}
- **R4.3 (#s-1).** `search_hooks.wrapper_paths()` is deleted; the signature is now
  `render_scripts() -> dict[str, str]` (no `wrappers=`); `hooks.install` records no `wrappers`
  flag; `hooks.check` calls `render_scripts()` and never reads the key, with a comment saying
  why an old flags file still carrying it is not drift. The module docstring describes runtime
  resolution (the rewriter's `_wrapper()` order, bug-008, bug-066). {#built-r4-3}
- **R4.2 (#b-2), registry side.** RED's guard listed 18 files. 93 registry rows had been
  appended below the Graduation Log table, outside `#registry`, so the guard could not see them:
  they move back into the registry table (the two 4-column plan-3 rows reshaped to the 5-column
  form). That registered 6 files; the other 12 (the six r1 names among them) get a row each,
  written from the patch site. Census after: 0 unregistered
  (`workflow/review-output/t04-registry-census-3.log`). {#built-r4-2}
- **R4.5 (#s-3, G7).** `cli._render_grep_rows`'s docstring: `-v` and `-L` are "refused, falls
  back to rg". `session_ingest.py` and `vectors.py` are not touched (derive pass modules,
  [[task-t0-suite-trust-sweep#r4-5-derive-hold]]); RED's allow-list holds them. A census of the
  phrase guard on this tip: no offenders, no stale entry, no pass-module entry beyond the two
  (`workflow/review-output/t04-phrase-census.log`). {#built-r4-5}
- **R4.6 (#m-2).** `_op_embed_locked`'s shutdown-cancel return is
  `{"embedded": 0, "remaining": len(rows), "cancelled": True, "degraded": degraded}`.
  {#built-r4-6}
- **R4.7 (#m-4).** `Store._log_event`: "Called after the catalog commit". {#built-r4-7}
- **R4.9 (G8).** Neither claim holds; the todo row is closed with the evidence ([[#r0]]).
  `docs/ARCHITECTURE.md`'s module table no longer says "~50 subcommands"; it points at the
  generated tree. `scripts/gen-cli-tree.py --check` → `ok: docs sections match their render`.
  {#built-r4-9}
- **R4.8 (#m-5).** No conftest check: red-t04's probe
  (`/Volumes/littlebig/refmatrix-t04-red/workflow/review-output/t04-r48-probe.log`) shows an
  assigned `PYTHONPATH` runs green at the full count (12 passed, both forms), and a degraded
  interpreter (lance made unimportable) fails loudly (11 failed, `ImportError`). The spec's first
  branch applies. {#built-r4-8}

## R0: the three facts at the base {#r0-facts}

| Fact | Check at `c8ff7a3e` | Holds |
|---|---|---|
| No production setter of `RMX_READ_VIA_DUCKDB` | `grep -rn` over the repo (src, tests, scripts, `.claude`): only `duckdb_view.py:7`, `store.py:1368-2519`, `tests/test_duckdb_read_routing.py` (a `monkeypatch.setenv`) and workflow prose; `grep -rl` over `~/Library/LaunchAgents/` → rc 1; `.claude/hooks/hooks.env` (clone and dev tree) → rc 1; `~/.claude/settings.json`, `~/.bashrc`, `~/.bash_profile`, `~/.zshrc`, `~/.profile` → none | yes |
| The facade mounts SQLite only | `DuckCatalogView.__init__`: `attach_file(..., read_only=True, db_type="SQLITE")` over `catalog.db` | yes |
| No production read reaches it | the only import was `store.py:2527`, inside `_read()` behind `if not self._read_via_duckdb: return self._connect()`; nothing else imports `duckdb_view` / `DuckCatalogView` / `ReadConnection` (`backend.py` has its own `_DuckRow`) | yes |

After R4.1: `grep -rn "RMX_READ_VIA_DUCKDB\|duckdb_view\b\|DuckCatalogView" src tests` is empty.
{#r0-facts-after}

## R0: per finding (AC-4.5) {#r0}

| Finding | R0 at `c8ff7a3e` | Outcome |
|---|---|---|
| #b-1 facade, Q1 | holds: the module, both tests and the flag present | fixed by `578b48ea` |
| #b-2 registry "every file" | holds: guard RED at base with 18 files, r1's six among them | fixed by `5eae7916` (rows) and RED `8533d258` (the guard) |
| #s-1 wrapper plumbing | holds: `wrapper_paths()`, `render_scripts(wrappers=)`, `record_flags(wrappers=)`, the install-time docstring | fixed by `578b48ea` |
| #s-2 task 6.4 summary | the summary exists (W1-d `c40006b`); it records no test for the `memory_partition` warning branch | closed by RED `8533d258` (`tests/test_plan3_remedy_r4.py::test_memory_partition_guesses_loudly_on_an_answered_error`, mutation M4.4 in red-t04's log) |
| #s-3 `cli.py` `-v` docstring | holds ("for now we honor it as a no-op") | fixed by `578b48ea` |
| #s-3 `session_ingest.py:5` "later phases" | holds | allow-listed, owned by 29.2 AC-29 |
| #s-3 `vectors.py:14` "for now" | holds | allow-listed, owned by 29.2 AC-29 |
| #s-3 guard is five literals, meta-test counts | holds | closed by RED `8533d258` (phrase families, set-based meta-test) |
| #m-1 bug-008 row "NOT verified live" | closed: the row reads "Graduated live 2026-09-16" and "CAVEAT CLEARED 2026-10-01" | closed by `855940f` and W1-d |
| #m-2 cancel return drops `degraded` | holds | fixed by `578b48ea` |
| #m-3 artifact test checks one figure | closed: the test loops over all four | closed by the 6.3 follow-up (spec #t0-4-lead) |
| #m-4 `_log_event` "SQLite commit" | holds | fixed by `578b48ea` |
| #m-5 assigned `PYTHONPATH` | the probe reads green at the full count; a degraded interpreter fails loudly | closed by the conftest checkout guard + SkipGate, evidence red-t04's `t04-r48-probe.log` |
| G7 five docstrings | `ingest_gmd`, `embedder`, `sync` clean; `store._log_event` held "SQLite commit"; `duckdb_view` present | fixed by `578b48ea` (two pass-module lines allow-listed, owned by 29.2 AC-29); todo row closed |
| G8 README 0.961 / ARCHITECTURE 24/80 | neither holds: `eval/production/results/csn_python/metrics.json` committed, guarded by `tests/test_eval_artifact_cited.py`; the CLI tree is generated (213 commands), guarded by `tests/test_docs_generated.py` | closed by tasks 6.2/6.3; the stale "~50 subcommands" fixed by `578b48ea`; todo row closed |

rel: derives-from -> [[task-29.2-mypy-gate#ac-29]]

## Acceptance, by evidence {#acceptance}

- **AC-4.1.** `grep -rn RMX_READ_VIA_DUCKDB src tests` empty at `5eae7916`; RED's
  `test_the_duckdb_read_facade_flag_is_named_nowhere_in_src_or_tests` runs in the verify set.
- **AC-4.2.** Guard RED at base (18 files), 0 after; M4.2 is RED's planted-file test.
- **AC-4.3.** Rendered scripts, sha256 at `RMX_CLAUDE_HOOKS_DIR=/fixed/hooks`, base (red-t04)
  and tip (`workflow/review-output/t04-render-hash-tip.log`): `rmxgrep-rewrite.py dcc9f276…`,
  `grep-rewrite-guard.sh 14077d2e…`, `grep-tool-teach.sh 8924552e…`: identical. The fixture
  install carrying the old key reads in sync ([[#self-audit]] 1). Mutation M4.3 on `src/`:
  [[#mutations]].
- **AC-4.4.** M4.5a/b/c/d are RED's (its mutation logs); M4.6 on `src/`: [[#mutations]].
- **AC-4.5.** [[#r0]].

## Mutations on the `src/` change {#mutations}

Each on a throwaway commit (branches `t04-mut-m46`, `t04-mut-m43`, never merged), run on the
mini lane.

| Mutation | Commit | Test file | Result |
|---|---|---|---|
| M4.6: drop `"degraded"` from the cancel return | `d57953de` | `tests/test_deferrals_clean.py` | 1 failed, 20 passed: `test_op_embed_carries_degraded_on_a_shutdown_cancel`, E `assert None == {'memory_content_missing': 1}` (`t04-green-mut-m46.log`) |
| M4.3: `hooks.check` reports a leftover `wrappers` key as drift | `e2fde7a2` | `tests/test_search_hooks.py` | 1 failed, 28 passed: `test_an_install_recorded_with_wrappers_reads_in_sync`, E line "- flags carry a stale wrappers key" (`t04-green-mut-m43.log`) |

## Verify set {#verify}

The RED files plus every test file importing a changed module (`store`, `daemon`, `hooks`,
`search_hooks`, `cli`): 311 files (`grep -rlE` over `tests/`), effectively the suite. Run
`t04-green-verify` at `5eae7916`: PENDING.

An earlier 41-file run at `578b48ea` (`t04-green-early`, before RED's tip): 7 failed, 617
passed. Five were callers of the removed API that RED had already rewritten
(`render_scripts() takes 0 positional arguments`, `AttributeError: wrapper_paths`); two were
`test_mcp_session_pointer` `assert 0 == 2`, bug-282 (mini lane only).

## ch-bsd r1 fold, registry side (L186) {#fold-r1}

ch-bsd r1 (`workflow/bullshit/2026-11-18-2300-t04-r1-5eae7916.md`, id `bsd-t04-r1-5eae7916`, persisted on master after this branch's base; the typed edge is added at merge) was DIRTY 1B/2S/2M with src clean. The registry side is in `27d71d3e`:
- **B1.** Row 74 states what the R4.2 guard enforces (external boundaries, each target named)
  and gives internal patch sites to POP T1 step 4 (patched busy/down tests to a real busy daemon,
  Q45 = a) and step 3 (consolidation). Row 39 (`_MiniHub`) is permanent (L186, option b): the
  real `Bus` and `Hub._op_bus_*` run on the real socket path, only the hub process lifecycle is
  absent; the row says plainly that no test runs `Hub.run()` end to end
  (`test_bug129_hub_pidfile.py` reaches only its stand-down paths, `test_task4_6_r5_remedy.py`
  records it).
- **S2.** One row per target in its own file: `hub.time.time` (test_alert_refinement_repeat),
  `reranker.time.time` (test_rerank_cost_budget), `discovery.os.kill` and the `subprocess.run`
  beside it (test_plan5_remedy), `sys.stdin` and `subprocess.run` (test_mcp_session_pointer).
- **M2.** The 8 four-cell rows are 5 columns. The bug-269 row no longer names its deleted file
  in the Test File(s) cell.
- S1 and M1 are red-t04's (guard tightening). Every new hit its tightened guard lists is
  registered after it lands ([[#fold-r1-hits]]).


red-t04's tightened guard (`6a188d4f`: per-double registration, module-object swaps, a
row-width check, `\s+` in the phrase families) is merged at `5df3c6b9`. At the merged tree it
listed 9 files whose doubles no row naming the file named (its 5eae7916 list had 13; the S2 rows
had already cleared 4). Each file gets a row naming every leaf, written from its patch site:
`test_cli_time_phases` (`subprocess.run`), `test_daemon_shutdown` (`os._exit`), `test_hub`
(`hub.os.kill`), `test_hub_plist_devtree` (`launchctl.hub_is_loaded`, `_stop_hub_before_bootout`,
`_wait_hub_loaded`), `test_plan1_remedy` (`launchctl.is_loaded`), `test_plan4_remedy_r2`
(`launchctl.LAUNCH_AGENTS_DIR`, `loaded_env`, `_require_darwin`, `BOOTOUT_WAIT_S`, `is_installed`;
`daemon.os._exit` in its own row), `test_plan4_remedy_r3` (`launchctl.HUB_SETTLE_S`,
`BOOTOUT_WAIT_S`), `test_task4_6_r5_remedy` (`launchctl.plist_path`, `hub_plist_path`,
`hub_is_loaded`, `hub_status`); the bug-178 r2 row now writes `store.time`. Census on the merged
tree: 0 width errors, 0 unregistered (`workflow/review-output/t04-fold-census-2.log`).
{#fold-r1-hits}

Fold confirm: `t04-green-fold` at `d380d9ca` (`test_mock_registry_coverage.py`,
`test_deferrals_clean.py`) read 66 passed but exited 1 on the bug-229 leak gate: a private
`refmatrix.embed_worker` outlived the task-6.1 test
`test_op_embed_reports_degraded_rows_to_its_caller` (a bare `Daemon` whose workers were never
closed; also in red-t04's base-src runs, intermittent). red-t04's `0038f810` (test-only) gives
the three bare-Daemon `_op_embed` tests a fixture that calls `d._close_workers()`; its lane-mini
run at `0038f810` (those two files plus `test_search_hooks.py`): 95 passed, exit 0, no leak.
{#verify-fold}

## Not done, flagged {#flags}

- A fixture script of mine short-circuited on a failed `ls` with `$T` empty and wrote a planted
  `wrappers` key into the clone's own `.claude/rmx-hooks.json`. Caught on the next `git status`
  and restored with `git checkout`; no live tree or store was touched. The rerun used a
  `set -euo pipefail` script that checks its tmp root.

## Self-audit {#self-audit}

```
1 real:     `rmx install-hooks --apply` then `--check` through refmatrix.cli.main (dev code),
            isolated HOME + RMX_CLAUDE_HOOKS_DIR + project under /private/tmp/claude-501,
            a legacy `wrappers` key planted in .claude/rmx-hooks.json →
            "wrappers recorded by this apply: False" / "hooks in sync … check rc=0"
            (workflow/review-output/t04-install-hooks-cli.log)
2 wiring:   tests/test_search_hooks.py (fixture install via hooks.install/hooks.check, the
            functions `rmx install-hooks` calls); test_op_embed_carries_degraded_on_a_shutdown_cancel
            enters via the daemon op `_op_embed` on a real Daemon with its real _shutdown_event
3 census:   wrapper_paths: 1 src caller (hooks.py:617, removed) + 3 tests (rewritten by RED);
            render_scripts: hooks.check, install_search_hooks, 3 tests — all call it with no args;
            rmx-hooks.json readers: hooks.check only (grep FLAGS_FILE / rmx-hooks.json);
            facade: grep list in #r0-facts, all removed; _op_embed returns: dense-missing error and
            `not rows` run no extraction (nothing to report), skipped_empty / cancel / final
            carry `degraded`
4 bound:    N/A — no timeout, budget or RPC changed
5 busy:     N/A — R4.3 is file-only (no daemon); R4.6 changes one dict on a path the op already
            takes when the daemon is stopping (its busy/down behaviour is unchanged)
6 guard:    no new src guard; the cancel branch fires on d._shutdown_event set before phase 2
            (a daemon stop during an embed), reached by `rmx embed` / save-state's drain; the RED
            test sets the real event
7 loud:     forced drift (a hand-edited user-global script) → `rmx install-hooks --check`
            exit 1, "hooks drift … - script grep-tool-teach.sh differs from the generator's render"
8 handoff:  session_ingest.py:5 and vectors.py:14 → [[task-29.2-mypy-gate#ac-29]] (self-expiring
            allow-list entries). Corrected after ch-bsd r1 B1 (L186): r1 at 5eae7916 said
            "nothing else deferred", but registry rows 74 and 39 still deferred to the finished
            "plan 6 sweep". Row 74 → internal patch sites owned by POP T1 steps 3 and 4 (Q45 = a);
            row 39 (_MiniHub) → permanent with its reason (L186 amended, option b): no test runs
            the Hub.run() lifecycle end to end, and the row says so instead of naming an owner
```
