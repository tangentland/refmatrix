---
gmd: "0.1"
id: impl-bug-241-reingest-gmd-pass
title: "0.83.1: bug-241 (markdown reaches the GMD pass on every code+docs ingest, tldr cache or not) + bug-240 (a file given to ingest is refused, naming rmx sync -f) (implementation summary)"
tags: [implementation-summary, bug-241, bug-240, bug-216, gmd, ingest, reingest, mcp]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-14
---

# bug-241: markdown reaches the GMD pass on every code+docs ingest {#root}

rel: derives-from -> [[bug_registry]]
rel: related-to -> [[impl-task-bug216-rule-docs-in-graph]]

Branch `task-bug241-rule-docs-gmd-on-reingest`, base master `78c0c11` (0.83.0). RED by red-216
at `a2ac833` (+ mutation logs `8f99332`): `tests/test_bug241_rule_docs_reingest.py`, 28 RED /
68 pass. GREEN `b1bc9d1` (src only, `src/refmatrix/ingest.py`). No test edited. {#commits}

## Cause {#cause}

Measured by red-216 (`bug241-trace.log`): `ingest._ingest_path_inner` ran `_ingest_tree` only
`if source in ("auto", "tree") and n == 0`, and `_ingest_tree` was the ONLY code+docs pass that
routed markdown to `ingest_gmd_paths`. With `.tldr/cache/semantic/metadata.json` or
`call_graph.json` (the live refmatrix tree has both) the tldr pass answered first, so `rmx ingest`
and `rmx reingest --force` GMD-parsed no markdown at all: the rule docs stayed plain relpath rows
with no anchors, bug-216's repair-by-reingest was a no-op live, and the reingest's coverage line
said "never stamped: gmd". The RED fails exactly on the reingest route with a cache (metadata or
call graph, fresh or with a prior plain row); the sync route and the no-cache tree were already
right. {#cause-text}

## Fix {#fix}

- **One routing.** `_ingest_markdown_gmd(s, root, *, ignore_root=None)` is THE code+docs routing
  of markdown to the GMD pass: every `GMD_EXTS` file under `root` that `should_ignore` keeps
  (judged against `ignore_root`, the project root — the same predicate every walker uses), a
  legacy relpath `doc` row purged first (guarded on its existence, as before), one batched
  `ingest_gmd_paths(..., lenient=True, project_root=root)`. Returns the docs ingested.
  {#fix-helper}
- **Both callers.** `_ingest_tree` no longer collects markdown in its walk; it calls the helper
  once at the end (its walk still goes through `should_ignore`, as bug-216 R2 pins).
  `_ingest_path_inner` calls the helper whenever the tree pass did NOT run — a tldr metadata or
  call-graph cache answered, or `--source` was explicit — so markdown is GMD-routed exactly once
  per ingest, whichever primary source answered. {#fix-callers}
- **`--source metadata|tldr|graphify` (explicit).** Markdown is still GMD-routed. `source` chooses
  where CODE structure comes from; none of those sources covers markdown, and every other markdown
  pass in `_ingest_path_inner` (ADR, plain markdown records) already runs for every `source`.
  Skipping the GMD routing under an explicit source would recreate this bug for anyone who passes
  one. `source=tree` and `auto` with no cache are unchanged (the tree pass routes). Code semantics
  of `source=` are untouched. {#fix-source}
- **The gmd stamp.** `ingest_gmd_paths` stamps the `gmd` derive pass when it runs, so a cached
  tree now gets it. Probe (`bug241-stamp-probe.log`): `rmx reingest --force --no-sessions
  --no-embed` on the RED's metadata-cache shape leaves `derive_stamps` = gmd, ingest, pagerank,
  semantic, and the coverage line reads only `derive coverage[proj]: skipped this run: embed` — no
  `never stamped: gmd`. {#fix-stamp}
- **The failure fallback is loud now.** The GMD pass's `except` (registering the files as plain
  docs) used to swallow the error and a nested `except: pass`; it now prints the error and counts
  every file it could not register (stderr). It moved into the helper, so it is this change's
  code. {#fix-loud}

## Out of scope, touched or not {#out-of-scope}

The plain relpath `doc` row that coexists with the GMD doc row (red-216's side measurement; live
`docs/SYSTEM.md` + `refmatrix/SYSTEM`) is NOT changed. This fix keeps the existing behaviour: the
helper purges a legacy relpath row before the GMD pass, as `_ingest_tree` always did, and the
later plain markdown pass (`_build_markdown_record`) still runs for every changed markdown file,
re-creating a relpath row — on the cached path now exactly as on the tree path. {#out-of-scope-text}

## Runs {#runs}

Absolute `PYTHONPATH=/Volumes/littlebig/refmatrix-bug241/src`; logs in `workflow/review-output/`:

- `tests/test_bug241_rule_docs_reingest.py`: **96 passed** (`bug241-green-iter1.log`).
- The bug-216 family + the ingest / gmd / reingest / sync / watch / derive / workflow_ignore files
  (+ memory_bridge, bug179, session_ingest, verb_parity, docs_generated): **795 passed**
  (`bug241-family.log`).
- Full suite at `b1bc9d1` (`bug241-full.log`): **18 failed, 4978 passed, 1 skipped**, against
  `release-0.83.0-full.log`'s 14 failed, by E line:
  - 14 in `tests/test_bug240_ingest_file_arg.py` / `test_bug240_ingest_file_arg_mcp.py`: bug-240's
    RED, committed onto this branch by another agent during the run (`36341f5`, `7145c19`, on top
    of `b1bc9d1`); RED by design, not this change.
  - `test_catalog_measure::test_rewrite_bytes_is_the_median_of_the_runs` (`KeyError:
    'rewrite_bytes_all'`): not in the baseline run; passes alone at `b1bc9d1` AND at the base
    `78c0c11` (30 passed each, `bug241-catalog-measure-{tip,base}.log`) — load-dependent, not this
    change.
  - `test_brief_real_daemon` (DuckDB lock conflict) and `test_task21_1_agent_usage_report` ×2:
    same E lines as 0.83.0.
  - The baseline's `test_plan4_remedy`, `test_repo_hooks_in_sync` and `test_search_hooks` ×9
    failures did not recur.

{#runs-list}

## Mutations {#mutations}

Each alone in a throwaway clone of `b1bc9d1`, restored with `git checkout -- src` in its own
command, `__pycache__` cleared; suite = the bug-241 file:

| mutation | result | log |
|---|---|---|
| restore the `n == 0` gate for markdown (the cached path skips the helper) | 28 failed | `bug241-mut-n0-gate.log` |
| route markdown around `should_ignore` | 12 failed | `bug241-mut-no-ignore.log` |

{#mutation-table}

## bug-240: a file given to ingest is refused, naming `rmx sync -f` {#bug-240}

Second item of the same 0.83.1 branch. RED by red-216 at `36341f5` (CLI, 6 RED) and r2
`7145c19` (refuse shape per the lead's ruling + `tests/test_bug240_ingest_file_arg_mcp.py`: 14 RED,
4 directory guards). GREEN `a7b3d35` (src: `ingest.py`, `daemon.py`, `verbs.py`, `cli.py`). No
test edited. {#bug-240-commits}

### Cause {#bug-240-cause}

`rmx ingest CLAUDE.md` exited 0 with `ingested 0 entities` and wrote nothing (0.83.0 deploy,
four fleet stores): `click.Path(exists=True)` accepts a file, and `ingest_path` on a file walks no
tree. The MCP tool reached the same walk by another road: `rmx_ingest` answered `{job_id, status:
running}` and the job ended `done` with nothing ingested; with the daemon down it answered "not
running", which tells an agent to start one and retry the same wrong call. {#bug-240-cause-text}

### Fix {#bug-240-fix}

- **One check.** `ingest.refuse_file_target(path)` raises `IngestFileTargetError` (a
  `ValueError`: a caller mistake) with `rmx ingest takes a directory; for one file use rmx sync
  -f <path>` when the path exists and is not a directory. A path that does not exist is left to
  the caller's own existence check (the CLI's `click.Path(exists=True)`). {#bug-240-helper}
- **Three call sites, the entry points a file arrives through**, each answering before it does
  anything else (lead ruling: one check, called where needed, never a second copy of it):
  {#bug-240-sites}
  - the `rmx_ingest` verb, BEFORE `_call` reaches `require_daemon`, converted to `VerbArgsError`
    (MCP `isError`; a `VerbError`, so the verb route's test holds daemon up and down);
  - the daemon op `_op_ingest_path_start`, before `_register_ingest_job` (no job, no
    `status: running`);
  - `ingest_path` itself, first line: covers the blocking op `_op_ingest_path` (the CLI's daemon
    route, rendered by `_DaemonWriter._call` as one `Error:` line) and the CLI's in-process
    route.
- **CLI rendering.** At `a7b3d35` the `ingest` command turned `IngestFileTargetError` from the
  in-process route into a `click.ClickException`. Since L112 M1 (below) the command calls the
  same helper itself, before `_store(write=True)`, and renders it as one `Error:` line, exit 1.
  `rmx ingest <dir>` and `rmx_ingest(path=<dir>)` are unchanged. {#bug-240-cli}
- **Not done (flag).** A path that does not exist still reaches the daemon from the verb/op routes
  unchanged (the CLI refuses it via click). Outside bug-240's ruling; the lead logs it as a
  separate bug, not in 0.83.1.
  {#bug-240-not-done}

### Runs and mutations {#bug-240-runs}

- bug-240 files (`tests/test_bug240_ingest_file_arg.py` + `_mcp.py`): **18 passed**
  (`bug240-green-iter1.log`).
- The bug-216 family + bug-240/241 + ingest / gmd / reingest / sync / watch / derive /
  workflow_ignore / memory_bridge / bug179 / session_ingest / verb_parity / docs_generated / mcp /
  verbs files: **956 passed, 1 skipped** (`bug240-family.log`; the skip is
  `test_repo_hooks_in_sync::test_installed_hooks_match_generated`, "hooks belong to another
  checkout of this commit" -- a clone artifact).
- Full suite at `13ffd77` (`bug241-bug240-full.log`): **3 failed, 4993 passed, 1 skipped**
  (59:30). The three are `test_brief_real_daemon` (DuckDB lock `IOException`) and
  `test_task21_1_agent_usage_report` ac6 ×2, the same E lines as `release-0.83.0-full.log`
  (checked by the lead too). `test_catalog_measure` did not recur.
- Mutations, each alone in a throwaway clone of `a7b3d35`, restored with `git checkout -- src`
  in its own command, `__pycache__` cleared, the fix confirmed present after the batch; suite =
  both bug-240 files: {#bug-240-runs-list}

| mutation | result | log |
|---|---|---|
| drop the refusal (`refuse_file_target` never raises) | 14 failed | `bug240-green-mut-no-refusal.log` |
| refusal text without `rmx sync -f` | 14 failed | `bug240-green-mut-unnamed.log` |
| no verb-level check | 3 failed (MCP daemon-down ×2, verb daemon-down) | `bug240-green-mut-no-verb-check.log` |
| no `ingest_path_start` check | 1 failed (`ingest_path_start`) | `bug240-green-mut-no-start-check.log` |

{#bug-240-mutation-table}

## ch-bsd r1 fold, ruling L112 {#l112}

ch-bsd r1 on `13ffd77` (report `workflow/bullshit/2026-11-14-2324-bug241-bug240-r1-13ffd77.md`,
persisted by the lead on dev master, so not linked from this branch): DIRTY 0B/2S/2M. RED by red-216 at `b509e1b`
(`tests/test_bug241_r2_l112.py`, 8 RED + 1 guard). GREEN `1a34a30` (src `ingest.py`,
`daemon.py`, `cli.py`; docs `INTEGRATION.md`, `SYSTEM.md`). No test edited. {#l112-commits}

- **S1, the GMD pass yields.** `_ingest_markdown_gmd(..., yield_lock=None, yield_every=10)` passes
  both to `ingest_gmd_paths`. `ingest_gmd_paths` yields every `yield_every` docs, and every N
  node-ops inside a doc. `_ingest_path_inner` passes its own hook and cadence on the cached
  route, and so does `_ingest_tree` on the tree route. On the daemon route the hook is
  `_CommitWindow.boundary` (COMMIT, release the lock, reopen). Measured on a 211-markdown copy
  of this tree (docs/ + workflow/plans), through a cooperative `ingest_path` with a timing hook
  (`bug241-l112-yield-gap-{200,10}.log`): {#l112-s1}

  | yield_every | GMD phase | yields | max hold | p50 hold |
  |---|---|---|---|---|
  | 200 (daemon default) | 96.6 s | 40 | 12.0 s | 1.1 s |
  | 10 | 101.3 s | 80 | 11.3 s | 0.5 s |

  Before the fix the whole phase was one hold. The cadence barely moves the ~12 s maximum, so
  that hold comes from a stretch with no yield in it. Its cause is not measured, and I name no
  mechanism. The ruling threads the caller's cadence through, so the daemon's GMD phase uses
  200.
- **S2, a failed GMD pass is counted and loud.** The fallback adds the files it covered to
  `Store.gmd_pass_failures` and keeps the error in `gmd_pass_last_error`, following the
  `vector_delete_failures` precedent. `_op_ingest_path` returns the delta as `gmd_pass_failed`,
  plus `gmd_pass_error` when it is non-zero. On both routes `cli._ingest` turns a non-zero count
  into one `Error: GMD pass failed (<error>): N markdown file(s) under <path> were registered as
  plain docs, not GMD-parsed; M entities ingested otherwise` line, exit 1. That covers
  `rmx ingest`, `tldr-warm`, `graphify-warm` and reingest step 1. The MCP job's result carries
  the same fields (`rmx_ingest_status`), but the job still ends `done`; the ruling did not cover
  that. The RED's input is real (`id: [a, b]`); the parser was not hardened (bug-244, L112a).
  {#l112-s2}
- **M1.** `rmx ingest` calls `refuse_file_target` before `_store(write=True)`, so a busy daemon
  no longer answers first. It is the same helper, not a copy. {#l112-m1}
- **M2.** The `--source` help, INTEGRATION's source-priority section and SYSTEM's override line
  now say that `--source` picks where code structure comes from and markdown always goes to the
  GMD pass. The stale "graphify ... the only ingest" comment in `_ingest_path_inner` is fixed.
  {#l112-m2}

### Runs and mutations {#l112-runs}

- `tests/test_bug241_r2_l112.py`: **9 passed** at `1a34a30` (`bug241-l112-green-iter1.log`).
- The family run (L112 + bug-240/241 + the bug-216 family + ingest / gmd / reingest / sync /
  watch / derive / mcp / verbs / verb_parity / docs_generated ...) at `1a34a30`: **964 passed,
  1 failed, 1 skipped** (`bug241-l112-family.log`). The failure was mine:
  `test_verb_parity::test_daemon_writer_ingest_uses_the_verb_payload` (`assert {'entities': 3}
  == 3`). `1a34a30` had changed `_DaemonWriter.ingest_path` to return the op's dict. `bba7313`
  restores the int contract and keeps the result on `last_ingest_result` for `_ingest`. verb_parity
  + L112 then: **176 passed** (`bug241-l112-green-iter2.log`).
- Full suite at `bba7313`: **4 failed, 5001 passed, 1 skipped** (58:11,
  `bug241-l112-full.log`). Compared by E line with `release-0.83.0-full.log`:
  - `test_brief_real_daemon` (DuckDB `IOException` lock conflict) and `test_task21_1` ac6 ×2 have
    the baseline E lines.
  - `test_gmd_lint_requires_version::test_the_repo_scope_is_clean_under_the_stricter_gate` was
    mine and has been fixed. The uncommitted draft of this summary carried
    `rel: derives-from -> [[bsd-bug241-bug240-r1-13ffd77]]`, and that report lives only on dev
    master, so the edge dangled on this branch. The edge is now prose; the file then passed
    **9/9** (`bug241-l112-gmdlint.log`).
  - `test_catalog_measure` did not recur.
- Mutations, each alone in a throwaway clone (S1/S2-count at `1a34a30`, the rest at `bba7313`),
  restored with `git checkout -- src` in its own command, `__pycache__` cleared, the fix
  confirmed present after the batch; suite = the L112 file (+ the bug-240 CLI file for M1):
  {#l112-runs-list}

| mutation | result | log |
|---|---|---|
| S1: drop the yield pass-through at `_ingest_path_inner` → `_ingest_markdown_gmd` | 2 failed (metadata, call_graph) | `bug241-l112-mut-s1-inner.log` |
| S1: drop the yield pass-through at `_ingest_tree` → `_ingest_markdown_gmd` | 1 failed (none / tree route) | `bug241-l112-mut-s1-tree.log` |
| S2: delete the fallback's count | 4 failed (op ×2, CLI ×2) | `bug241-l112-mut-s2-count.log` |
| S2: drop the CLI exit | 2 failed (CLI daemon, in-process) | `bug241-l112-mut-s2-cli-exit.log` |
| M1: remove the early CLI `refuse_file_target` | 4 failed (L112 M1, bug-240 in-process ×3) | `bug241-l112-mut-m1-early.log` |

{#l112-mutation-table}

## ch-bsd r2 fold, ruling L114 {#l114}

ch-bsd r2 on `bba7313` found MEHs only and gave GO (report
`workflow/bullshit/2026-11-15-0152-bug241-bug240-r2-bba7313.md` on dev master). RED by red-216
at `111e4b0` (`tests/test_bug241_r3_l114.py`, 3 RED + 1 guard), merged onto the summary tip at
`5808a58`. GREEN `044ff2a` (src `ingest.py`, `daemon.py`, `cli.py`). No test edited.
{#l114-commits}

- **M1, the GMD pass yields per doc.** `_ingest_markdown_gmd` no longer takes the caller's
  code-unit `yield_every`: 200 on the daemon (`RMX_INGEST_YIELD_EVERY_UNITS`), meant for cheap
  per-file units. It passes `gmd_doc_yield_every()` to `ingest_gmd_paths`, which reads
  `RMX_INGEST_YIELD_EVERY` and defaults to 1 doc. The daemon's `ingest_gmd` job now reads the
  same function, so one knob serves both GMD routes. Both code+docs routes (cached, and
  `_ingest_tree`) reach the helper, so the cadence is set in one place. bsd measured 211 docs:
  max hold 15.0 s → 5.4 s, p95 9.9 s → 1.3 s, same total time. This also answers the ~12 s
  stretch from L112 #l112-s1: that was the code cadence, not a phase without a yield hook.
  {#l114-m1}
- **M2, a failed GMD pass ends the agent's job `error`.** `_run_detached_job` takes an optional
  `failure(result)` verdict. `ingest_path_start` passes `ingest.gmd_pass_failure_message`, and
  the job ends `status: error` with that sentence as its `error`, keeping `result` beside it.
  `cli._ingest` prints the same function's sentence as its `Error:` line. Why `error` rather than
  `done` + `warning`: the CLI exits 1 on the same condition, so one condition gets one verdict
  and one wording on both routes; and `done` is what a polling agent reads as success.
  {#l114-m2}
- **Nit.** `_DaemonWriter.__init__` sets `last_ingest_result = {}`. {#l114-nit}

### Runs and mutations {#l114-runs}

- L114 + L112 + verb_parity: **180 passed** (`bug241-l114-green-iter1.log`).
- Family (L114 + L112 + bug-240/241 + the bug-216 family + ingest / gmd / reingest / sync /
  watch / derive / mcp / verbs / verb_parity / docs_generated ...): **969 passed, 1 skipped**
  (`bug241-l114-family.log`; the skip is the clone-artifact `test_repo_hooks_in_sync` skip).
- No branch full suite (lead, L114): the release suite on merged master is the gate.
- Mutations, each alone in a throwaway clone of `044ff2a`, restored with `git checkout -- src`
  in its own command, `__pycache__` cleared, the fix confirmed present after the batch; suite =
  the L114 file. The per-doc cadence is set once, in the helper both routes call, so one
  mutation there covers both routes; each mutation below fails both route cases.
  {#l114-runs-list}

| mutation | result | log |
|---|---|---|
| M1: the helper passes the code cadence (200) | 2 failed (cached, tree) | `bug241-l114-mut-m1-helper-200.log` |
| M1: `gmd_doc_yield_every()` returns 200 | 2 failed (cached, tree) | `bug241-l114-mut-m1-knob-200.log` |
| M2: the job buries the failure in `result` (`failure=None`) | 1 failed | `bug241-l114-mut-m2-buried.log` |

{#l114-mutation-table}

## Next {#next}

AC-6 live: after deploy, the lead re-runs bug-216 R4's `rmx reingest --force --no-sessions` and
`scripts/check-rel-landing.py` on a fresh read-only copy (bug-216 #ac-6). {#next-text}
