---
gmd: "0.1"
id: bsd-0661-e2e-memory-bridge
title: "ch-bsd end-to-end audit — refmatrix 0.66.1 memory bridge + whole project"
severity: BULLSHIT
plan: refmatrix-0.66.1
task: e2e-audit
tags: [bsd, audit, memory-bridge, deploy-drift, daemon]
---

# ch-bsd findings — fix(memory): save-state runs the memory bridge (0.66.1) + project sweep {#root}

**Commit range:** 69a1b37..f56a365 (0cb365d = the 0.66.1 bridge change; f56a365 = click.echo follow-up)
**Date:** 2026-09-14
**Author:** Todd Holley / Claude Fable 5.1 / orchestrator (team-lead)
**Files changed (range):** 10 (cli.py, handoff.py, hooks.py, verbs.py, 2 templates, 2 tests, pyproject, __init__)
**Scope:** whole project — src/refmatrix (49k lines), tests/ (147 files), docs/, README, installed hooks, deploy tree, live daemon/hub.
**Method note:** the audit's own grep calls were rewritten to `rmx grep` by the installed PreToolUse hook; that write path crash-looped the project daemon six times (see [[#bs-3]]). Evidence collection switched to Python after 18:57.

## Findings {#findings}

### BULLSHIT: the new memory bridge silently drops 19 of 202 curated memory files {#bs-1}

**File:** `src/refmatrix/ingest_gmd.py:309` (`parse_gmd` returns None when `gmd:` is absent), `src/refmatrix/ingest_gmd.py:768-774` (the None is `continue`d, never counted), `src/refmatrix/cli.py` `_sync_memory_dir` / `_ingest_gmd_sync`
**What:** 0.66.1 makes `ingest-gmd --as-memory` over `~/.claude/projects/<slug>/memory/` THE bridge (save-state, SessionStart hook, templates). It only ingests files with `gmd:` frontmatter.
**Why it's bullshit:** 20 of 203 files in the live memory dir have no `gmd:` frontmatter (19 memories + MEMORY.md). They are skipped before they reach the store, and `IngestStats.report()` has no skipped counter, so save-state prints a green "memory bridge ... ingested 184 doc(s)" while a tenth of the corpus never lands. The legacy `rmx memory sync-disk` (cli.py:10105) ingests those same files (id | name | stem, no gmd requirement) — but nothing runs sync-disk any more, and README:150 + docs/ARCHITECTURE.md:328 still advertise it as the way to ingest curated memories. Two bridges, different coverage, different metadata (`source_mtime` only from sync-disk), neither documented as canonical.
**Evidence:** memory-dir census: total 203, gmd 183, non-gmd 20. Store lookups: `rmx memory get feedback_no_silent_failures` → "no memory matching"; same for `project_daemon_arch`, `feedback_refmatrix_dev_deploy_split`, `project_phase_c_shipped`. GMD ones resolve (`feedback_rmx_first_retrieval id=2580625 source=ingest_gmd_as_memory`). Daemon log job 1e398984b803: "pass1-skip 1/204 ... pass2-skip 184/184" — 204 candidates in, 184 processed, 20 vanished without a line.
**Fix:** (a) bridge the memory dir with `lenient=True` (parse_gmd already supports it; doc_id falls back to stem, matching sync-disk identity) or route non-GMD files through the sync-disk upsert; (b) add `skipped_non_gmd` to `IngestStats` and print it; (c) pick ONE bridge, delete or alias the other, fix README:150 / ARCHITECTURE:328.
**Pattern match:** YES — memory [[feedback_no_silent_failures]] ("drop 2>/dev/null + || true on memory-critical paths"); this is the same failure in a different coat: a silent skip on the memory-critical path.

rel: contradicts -> [[feedback_no_silent_failures]]

### BULLSHIT: `rmx` on PATH, the daemon, and the hub all execute the DEV tree, not ~/refmatrix {#bs-2}

**File:** `~/refmatrix/.venv/lib/python3.14/site-packages/__editable__.refmatrix-0.66.0.pth` (content: `/Users/tholley/claude_tools/refmatrix/src`), `/Users/tholley/bin/rmx` (shebang `~/refmatrix/.venv/bin/python`)
**What:** The brief, the memory ledger ([[feedback_rmx_binary_is_deploy]], [[feedback_refmatrix_dev_deploy_split]]) and the deploy discipline all say `rmx` runs the deploy tree at ~/refmatrix (git 69a1b37, 0.66.0, clean).
**Why it's bullshit:** The deploy venv's editable install points at the dev checkout. `~/refmatrix/.venv/bin/python -c "import refmatrix"` → `/Users/tholley/claude_tools/refmatrix/src/refmatrix/__init__.py 0.66.1`. `rmx --version` → 0.66.1 while `~/refmatrix/src/refmatrix/__init__.py` says 0.66.0 and dist-info says 0.66.0. The project daemon (pid 30339, `/Users/tholley/bin/rmx daemon start`) and the hub (pid 17914) therefore run whatever is on the dev working tree at their start time — during this audit that was UNCOMMITTED staged code. Every "promote dev → deploy" step in the save-state template, the version handshake, and the "avoid dev-venv commands, they trip the hub handshake" guidance are void: there is no separate deploy runtime.
**Evidence:** `.pth` mtime Sep 14 18:00 (same minute as the `~/refmatrix` dir mtime); `ls ~/refmatrix/src/refmatrix` exists but is never imported.
**Fix:** `~/refmatrix/.venv/bin/python -m pip install -e ~/refmatrix` (from the deploy dir), verify `refmatrix.__file__` is under ~/refmatrix/src, restart daemon + hub (`rmx daemon restart --relaunch`), then re-verify `rmx --version` == deploy tree version. Add a guard to `rmx daemon status` / `hub status` that prints `refmatrix.__file__` so this drift is visible.
**Pattern match:** YES — memories [[feedback_rmx_binary_is_deploy]], [[reference_editable_venv_distinfo_lag]] both describe dist-info/runtime lag; this is the inverted, worse case.

rel: contradicts -> [[feedback_refmatrix_dev_deploy_split]]
rel: contradicts -> [[feedback_rmx_binary_is_deploy]]

### BULLSHIT: a READ surface (`rmx grep`) writes to the store and crash-loops the daemon; the boot-time "repair" repairs the wrong index {#bs-3}

**File:** `src/refmatrix/daemon.py:3316` (`_op_learn_from_grep` → `_learn_grep_hits` → `upsert_entity(protected=True)` under `_store_lock`, no exception guard), `src/refmatrix/daemon.py:871-888` (fast-exit on any DuckDB FatalException), boot line "repaired idx_entity_links_lk_concept"
**What:** Every `rmx grep` miss (and every agent grep, via the installed `grep-rewrite-guard.sh`) calls `learn_from_grep`, which UPSERTs entities.
**Why it's bullshit:** On this store the entities primary-key index is drifted (DuckDB `Failed to delete all rows from index. Only deleted 0 out of 1 rows`, entity 2580559 / 2506158 — ids in today's bridge-ingested range). The upsert throws FatalException, the daemon fast-exits, launchd restarts it, the next grep kills it again. `daemon.stderr.log` shows six restarts 18:51:01 → 18:57:09, each preceded in `rmxd.log` by `op learn_from_grep raised: FatalException`. Each boot logs "repaired idx_entity_links_lk_concept rows=2479xx" — a repair of a DIFFERENT index; the failing `PRIMARY_entities_0` is never repaired, so the loop is guaranteed to recur. `_t_context`'s learn (daemon.py:3579) has "learning is best-effort; never fail a read" — `_op_learn_from_grep` has no such guard. The fast-exit + supervisor restart is a workaround that makes the symptom disappear from the caller's view (the CLI gets a socket error, `|| true`) while the root cause ([[project_daemon_index_drift_recurrence]] "PARTIAL-FIX; second path still SIGABRTs") stays open.
**Evidence:** `cli.log` 18:50-18:57: 249 rows, 125 source=unknown (this audit's rewritten `grep` calls), 124 source=hook. `rmxd.log:7501,7531,7575` learn_from_grep FatalException lines; `daemon.stderr.log:80-95` six "daemon starting" boundaries with libc++abi duckdb::FatalException between them.
**Fix:** (1) wrap `_op_learn_from_grep` like the context learn: catch, log, return `{"added":0,"skipped":"store invalid"}` — a read must never take the daemon down; (2) on fast-exit, write a marker so the NEXT boot runs `repair-index` on `entities` (PK + UNIQUE), not only `idx_entity_links_lk_concept`; (3) `rmx daemon status` should surface "restarts in last 10 min" (the hub already counts restarts=0 — it is wrong; watchdog kickstarted twice).
**Pattern match:** YES — [[project_daemon_sigabrt_diagnosed]], [[project_daemon_index_drift_recurrence]], [[project_entities_unique_index_phantom_repair]]: fourth recurrence of the same family. Escalated.

rel: contradicts -> [[project_daemon_index_drift_recurrence]]

### BULLSHIT: the installed hooks are not what `install-hooks` generates, and the "loud" bridge failure is silenced in the real PreCompact path {#bs-4}

**File:** `.claude/settings.local.json` vs `src/refmatrix/hooks.py:68-286` (`_claude_hook_block`), `src/refmatrix/hooks.py:782-786` (`_RMX_HOOK_SIGNATURES`)
**What:** Diff of the generated block against the installed file:
- installed-only (hand-authored, nothing generates them): `scan-prompt --composite-every 3 --max-tokens 2000`; PreCompact `focus summarize --promote`; PreCompact `rmx save-state --no-promote -m "auto: pre-compact checkpoint" >/dev/null 2>&1 || true`; SessionStart(resume) `focus context --top 15`.
- template-only (generated, not installed): `scan-prompt --max-tokens 2000`; PreCompact `focus summarize` (no --promote).
**Why it's bullshit:** (a) The production hook config is unreproducible: `rmx install-hooks --claude --force` strips every command carrying `RMX_INVOCATION_SOURCE=hook` (all four hand-authored ones included) and writes the template, silently deleting the pre-compact checkpoint and STM promote. (b) The 0.66.1 diff's whole argument is that the bridge must be "synchronous and loud" ("A red `memory bridge FAILED` line is a loose end — fix or report it, never skip it", save-state.md:24). The only automated caller of save-state is that PreCompact hook, and it ends in `>/dev/null 2>&1 || true`. The loud path is silenced exactly where it runs unattended. (c) The same hook now runs the ~30 s synchronous bridge (job 1e398984b803: 204 files, 30 s, all skips) inside PreCompact, on the compaction critical path.
**Evidence:** rendered `_claude_hook_block(...)` vs `json.load(settings.local.json)` set-diff (4 installed-only, 2 template-only). `hooks.py:37-46` "--force re-install must OVERWRITE rmx-managed entries".
**Fix:** either promote the four hand-authored hooks into `_claude_hook_block` (with flags), or mark them non-rmx so `--force` keeps them. Make the PreCompact save-state hook print the bridge line (drop `>/dev/null`) or pass `--no-sync` there and let SessionStart catch-up do the work — pick one and write it down. Add a test that renders the block and diffs it against a fixture of the "reference install".
**Pattern match:** YES — [[feedback_no_silent_failures]] (`|| true` on the memory-critical path, third sighting in this audit).

rel: contradicts -> [[feedback_no_silent_failures]]

### BULLSHIT: stale / unanchored deferrals in shipped docstrings {#bs-5}

Rule 9a sweep over src/refmatrix (hard + soft families, 132 raw hits, triaged):
- `src/refmatrix/ingest_gmd.py:13` — "Full BM25 over node body text is deferred to v1." Body BM25 exists (`content_rank`, [[project_context_content_fusion]], [[project_context_nl_ref_fixes]]) and the project is at 0.66. Stale deferral; the module docstring describes a system that no longer exists.
- `src/refmatrix/store.py:646-648` — "Phase 1: log runs alongside the catalog as a verification target. Phase 2 will gate the catalog writes off and treat the log as authoritative." No task/plan exists for Phase 2; [[project_factslog_audit_verdict]] concluded facts.log has no history to recover and three write paths are unlogged. Unanchored deferral on a default-on feature (`RMX_LOG` defaults to "1", store.py `_log_enabled`).
- `src/refmatrix/duckdb_view.py:1-8` — "Phase 1 of the DuckDB+Lance migration. The SQLite catalog stays the system of record ... once the env flag RMX_READ_VIA_DUCKDB is set." The store now opens `backend=duckdb` natively (rmxd.log "store opened backend=duckdb"); the facade is reachable only via an env flag that no production path sets (only `tests/test_duckdb_read_routing.py` sets it). 133 lines of dead-in-production code kept alive by two tests.
- `src/refmatrix/embedder.py:203-206` — "Phase A stub: returns the entity name when the memory_content sidecar isn't present yet so A4 can land before B." Phase B shipped ([[project_phase_b_intuition_memory]]); the stub branch and its comment outlived the plan.
- `src/refmatrix/sync.py:200` — "`_ = yield_lock, yield_every  # unused for now`" — parameters plumbed "for forward compatibility" with no task that will use them.
- `src/refmatrix/launchctl.py:322-323` — "Linux supervisor support (systemd user unit) is not yet implemented." Honest runtime error, but names no plan. MEH-grade on its own.
**Fix:** delete the stale sentences (ingest_gmd, embedder), either file a concrete task for facts.log Phase 2 or rewrite the docstring to say it is a verification log only, remove `duckdb_view.py` + its two tests (or wire the flag into a documented mode), drop the unused sync params.

rel: contradicts -> [[project_factslog_audit_verdict]]

### SKETCHY: bridge collides with itself — single-active-ingest guard turns overlap into "memory bridge FAILED" {#sk-1}

**File:** `src/refmatrix/daemon.py:2563-2580` (`_register_ingest_job` raises `ingest already active`), `src/refmatrix/hooks.py:141-158` (SessionStart background bridge), `src/refmatrix/cli.py` `_sync_memory_dir`
**What:** SessionStart fires the bridge detached (30 s no-op on this dir). `rmx save-state` (manual, MCP, or the PreCompact hook) runs the same op synchronously. `ingest_path_start` / `embed_start` share the slot.
**Why it's sketchy:** Any overlap makes the second caller's bridge fail with RuntimeError → save-state prints FAILED (or swallows it in PreCompact). No retry, no wait-for-slot, no test. A user who runs `/save-state` within a minute of session start will see a red line for a non-problem — and learn to ignore red lines.
**Fix:** in `_sync_memory_dir`, on "ingest already active" poll `ingest_gmd_status` for the running job and treat its completion as success (same files, same content hashes) — or serialize through one daemon op. Add a test for the collision.

### SKETCHY: the bridge tests never run the bridge {#sk-2}

**File:** `tests/test_save_state.py:226-255`
**What:** `test_finalize_runs_memory_bridge_over_the_handoff_dir` monkeypatches `cli._sync_memory_dir` to a lambda; `test_sync_memory_dir_reports_missing_dir_not_raises` only exercises the missing-dir early return. `test_hooks.py` asserts substrings of the generated command.
**Why it's sketchy:** No test writes a GMD memory file to a tmp memdir, runs `_sync_memory_dir` against a tmp Store, and asserts a `kind=memory` row exists in the expected partition. Mutation check: break the partition argument in `_ingest_gmd_sync` (or make `parse_gmd` reject every file) — all 37 tests in the touched files still pass (verified: 37 passed). This is exactly how #bs-1 shipped.
**Mock registry:** `workflow/test_mock_registry.md` does not exist; 184 `monkeypatch.setattr` sites across tests/ are unregistered. Filed once, not per site.
**Fix:** one in-process test: tmp store, tmp memdir with one GMD + one non-GMD file, run `_sync_memory_dir`, assert both names resolve via `get_memory` (after #bs-1 fix) and the report counts them.

### SKETCHY: MCP/verbs parity drift — 30 tools, 10 verbs; session-start recall has no MCP path {#sk-3}

**File:** `src/refmatrix/verbs.py` (10 `@verb`s), `src/refmatrix/mcp.py:491-766` (30 `TOOLS`), `src/refmatrix/cli.py` memory_recall (widen logic lives only here)
**What:** `rmx_recall_state`, `rmx_memory`, `rmx_locate`, `rmx_task`, `rmx_where`, `rmx_search`, `rmx_ingest_status`, `rmx_queues`, and all nine `rmx_bus_*` tools call daemon/handoff directly, bypassing verbs.py. The project's own rule ([[project_verbs_layer_antidrift]]) is "new capabilities go through verbs.py; schemas generated; parity tests". The 0.66.1 `--session-start` widen-to-newest-k lives only in `cli.memory_recall`; `verbs.memory_recall` has no `session_start` at all, so an MCP client cannot do the orient pass the CLI hook does.
**Fix:** move recall's session-start/widen into `verbs.memory_recall` and have the CLI call it; migrate the direct-call tools behind verbs incrementally, starting with recall_state (it is already a pure function call).

rel: contradicts -> [[project_verbs_layer_antidrift]]

### SKETCHY: README headline benchmark has no committed artifact {#sk-4}

**File:** `README.md:22-30`, `docs/PERFORMANCE.md:224-230`, `eval/production/REPORT.md:24-31`, `eval/production/csn_code.py`
**What:** README and PERFORMANCE claim "CSN Python, production path (43 827 docs · 14 918 queries) MRR@10 0.961".
**Why it's sketchy:** The only production-harness artifact in the repo (`eval/production/REPORT.md`) is a 2 000-doc / 300-query run reporting 0.9883. `csn_code.py` prints metrics and writes nothing. The 0.961 figure exists only in the body of commit 57c7778. The one 0.96x number in `eval/results/` is Recall@10 of a bespoke variant (`rmx_bm25_idfpow15/metrics.json`), not MRR. The docs call this "the number to defend" — it cannot be re-derived from anything checked in.
**Fix:** have `csn_code.py` write `eval/production/results/<dataset>/metrics.json` and commit the full-corpus run; cite that path from README.

### SKETCHY: `install-hooks` cannot reach the opt-out branches its tests cover {#sk-5}

**File:** `src/refmatrix/hooks.py:68-70,288-311` (`install(..., memory_hooks=True)`, `_claude_hook_block(primer, scan_prompt, memory_hooks)`), `src/refmatrix/cli.py` `install_hooks` (passes git/claude/briefing/scope/apply/force/agent_env/search only), `tests/test_hooks.py:test_memory_hooks_opt_out`
**What:** Three knobs exist and are tested; no CLI flag, env var, or MCP path sets any of them to False.
**Fix:** expose `--memory-hooks/--no-memory-hooks`, `--primer/--no-primer`, `--scan-prompt/--no-scan-prompt` on `install-hooks`, or delete the parameters and the opt-out test.

### MEH: docs drift {#meh-1}

- `docs/ARCHITECTURE.md` command tree documents 24 of 80 top-level CLI commands; missing include save-state, recall-state, ingest-gmd, focus, hub, mcp, scan-prompt, reingest, grep-adjacent `locate`, `task`, `bus`, `cctree`, `ui`.
- `README.md:248` hooks table lists SessionStart = primer, UserPromptSubmit = scan-prompt; the memory recall hooks and the bridge are absent.
- `README.md:150` still teaches `rmx memory sync-disk` (see #bs-1).

### MEH: best-effort swallows on the save-state path {#meh-2}

`src/refmatrix/handoff.py:428-429` (subject filing `except Exception: pass`), `src/refmatrix/verbs.py:148-149` (legacy-partition detection `except Exception: pass` — a daemon error here silently reroutes memory writes to the project partition). 111 `except: pass|continue` sites package-wide (cli 27, daemon 23, store 17). Not all are wrong; these two sit on the memory path.

### MEH: widen-to-newest-k branch is untested {#meh-3}

`src/refmatrix/cli.py` memory_recall `if not rows and since_defaulted:` — code reads correctly (daemon op accepts `since_seconds=None`, `recent_memories` treats None as no window) but no test asserts the fallback fires only when `--since` was defaulted.

## Verified clean {#clean}

- Vendored search hooks (`grep-rewrite-guard.sh`, `rmxgrep-rewrite.py`, `grep-tool-teach.sh`) are byte-identical to `~/.claude/hooks/`.
- `default_memory_dir` slug encoding is shared (cli delegates to handoff); `_sync_memory_dir` and the SessionStart hook resolve the same dir and the same partition (`_memory_partition_default`).
- `finalize_save_state` is the single post-step for CLI and MCP save-state; `verbs.save_state` surfaces `sync`.
- `_ingest_gmd_sync` daemon-up path passes `partition`; daemon `_op_ingest_gmd` honors it and only refuses filesystem paths when `as_memory` is false.
- 37 tests in test_hooks / test_save_state / test_mcp_parity / test_hook_wiring pass under `.venv-eval`.
- Non-GMD memory files: identity semantics of the two bridges agree for GMD files (frontmatter `id`, else stem).

## Verdict {#verdict}

DIRTY — 15 findings (5 BULLSHIT, 5 SKETCHY, 3 MEH; #bs-5 bundles six deferral sites).
Blocking for "0.66.1 memory bridge = done": #bs-1 (coverage), #bs-4 (loud path silenced), #sk-1/#sk-2 (untested collision).
Blocking for the environment regardless of code: #bs-2 (no deploy runtime), #bs-3 (daemon crash-loop on grep).

rel: evidence-for -> [[feedback_no_silent_failures]]
rel: evidence-for -> [[project_daemon_index_drift_recurrence]]
