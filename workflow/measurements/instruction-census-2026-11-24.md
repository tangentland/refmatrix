---
gmd: "0.1"
id: instruction-census-2026-11-24
title: "Instruction census: every stated rule, its type T1-T10, where it is stated, its trigger and target mechanism (plan-32 step 3)"
tags: [measurement, census, instructions, rules, hooks, plan-32]
metadata:
  node_type: measurement
  created: 2026-11-24
---

# Instruction census (2026-11-24) {#root}

rel: implements -> [[plan-32-instruction-architecture#steps]]
rel: derives-from -> [[plan-32-instruction-architecture#rule-types-mechanism-pre-mod-now-post-mo]]

Read-only census of every rule stated in the sources the brief names, at master `c7550ad5` (the sources are unchanged at `4de80d1a`, which adds only two briefs), from the brief `workflow/agents/census-rules.md` (committed at `4de80d1a`, after this branch's base). 205 distinct rules, each with ONE type from the plan-32 T-table and ONE target mechanism. Duplicates are merged into one row that lists every place the rule is stated. Role prose in agent files is not enumerated; only rules are. {#scope}

## Legend {#legend}

**Stated in.** `C` CLAUDE.md, `P` .claude/PROJECT_PROFILE.md, `GMD` ~/.claude/GMD.md, `MR` ~/.claude/MEMORY-RULES.md, `BR` .claude/rules/bug-registry.md, `RC` .refmatrix/CLAUDE.md (dev tree, untracked), `O` workflow/ORCHESTRATION.md, `PW` workflow/PLANNING_WORKFLOW.md, `SA` workflow/SELF_AUDIT.md, `PG` workflow/PLAN_GOVERNANCE.md, `a:<name>` .claude/agents/<name>.md (`.local` = the overlay), `f:<slug>` memory `feedback_<slug>`, `r:<slug>` memory `reference_<slug>`, `hook:<file>` an installed hook script, `AM` the p20-0 auto-mode rules in .claude/settings.local.json, `handoff` handoff.md. `plan-32` and `brief:` mark a rule the plan or the brief cites as an example; they do not count as a place. `#x` is the anchor. {#legend-sources}

**Today** is derived from the sources, not judged: `AO` full text always-on (CLAUDE.md, PROJECT_PROFILE, the global files, the unconditional rule); `AG` in an agent definition (loads for that agent only); `IX+REC` a memory: its title is always-on in the MEMORY.md index, its body arrives only by recall or a Read; `F` a doc the model must fetch. After the semicolon: a hook, auto-mode rule or test guard that already delivers or enforces it (`ENF` deny, `INJ` inject, `WARN` warn, `GUARD` a repo-wide test, `CMD` a slash command). {#legend-today}

**Target mechanism** is the plan-32 pre-mod column for the type: T1 PreToolUse deny (or auto-mode), T2 path-scoped `.claude/rules/*.md`, T3 a skill delivered by `paths:`, a PreToolUse inject or an agent `skills:` preload, T4 pre-commit / commit-msg / Stop / SubagentStop check, T5 SessionStart, T6 UserPromptSubmit, T7 agent file + overlay + SubagentStart, T8 the short principles block, T9 one SessionStart style, T10 nested CLAUDE.md or a pointer. {#legend-target}

## The table {#table}

### Live stores, deploy tree and runtime safety {#t-live}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R001 | Never run a dev-venv `rmx` with a bumped version against the live store (hub handshake restarts the fleet, DuckDB lock crashes) | T1 | `C#development-commands`, `P#commands`, `a:ch-bsd.local`, `a:ch-implementer.local`, `handoff#resume` | Bash: `.venv-eval/bin/rmx` or `python -m refmatrix.cli` with cwd or `REFMATRIX_ROOT` on a live `.refmatrix/` | PreToolUse deny (hooks.py) | AO, AG, F |
| R002 | Never open `Store()` directly on a live `.refmatrix/` from a shell; reads go to a copy or a daemon op | T1 | `C#development-commands`, `P#constraints`, `f:store_calls_via_daemon` | Bash: `python -c` / heredoc containing `Store(` with a live root | PreToolUse deny | AO, IX+REC |
| R003 | Subagents are read-only on every live store: no `rmx sync`, `ingest`, `ingest-gmd`, `reingest`, memory writes, curation, `partition`, `daemon`, `hub` | T1 | `P#corpus`, `O#roles-agents`, `f:subagents_read_only_on_live_stores` | PreToolUse Bash with `agent_id` set and an `rmx` write verb | PreToolUse deny keyed on `agent_id` / `agent_type` | AO, IX+REC, F |
| R004 | Never export `REFMATRIX_ROOT` in a shell that runs tests or dev code; never symlink or copy `.refmatrix/` into a clone | T1 | `P#corpus`, `O#roles-agents` | Bash: `export REFMATRIX_ROOT`, `ln -s`/`cp -r` naming `.refmatrix` | PreToolUse deny | AO, F |
| R005 | Measure a live store read-only: copy `catalog.read.duckdb` to the scratchpad and open the copy `read_only=True` | T1 | `C#development-commands`, `O#measure` | Bash: `duckdb.connect` on a path under a live `.refmatrix/` | PreToolUse deny (rule as reason) | AO, F |
| R006 | Live-store surgery (reingest, rebuild, slot swap, `prune-noise --drop`, `dedup`, `rebuild --from-log`) is announced, backed up first, and needs its own go | T3 | `C#permissions`, `O#roles-lead`, `O#release`, `a:gmd-curator`, `RC` | Bash: `rmx (reingest\|rebuild\|vacuum\|prune-noise --drop\|memory dedup)` on a live root | PreToolUse inject backup checklist (allow) + skill `live-surgery` | AO, AG, F |
| R007 | Edit refmatrix only in `~/claude_tools/refmatrix`; `~/refmatrix` is the deploy tree and is never edited or copied into | T1 | `f:refmatrix_dev_deploy_split`, `P#layout` | Edit/Write path under `~/refmatrix/**`; Bash `cp … ~/refmatrix/src` | PreToolUse deny | AO, IX+REC |
| R008 | Never `pip install -e` the dev tree into the deploy venv; `rmx version -v` must show `~/refmatrix/src`, no `[DEV TREE]` | T1 | `P#layout`, `f:deploy_tree_is_the_runtime`, `f:rmx_binary_is_deploy`, `r:editable_venv_distinfo_lag` | Bash: `~/refmatrix/.venv/bin/pip install` naming `claude_tools/refmatrix` | PreToolUse deny | AO, IX+REC |
| R009 | The `rmx` on PATH runs DEPLOY code; verify dev edits with `.venv-eval` / pytest, never with `rmx` | T10 | `C#memory-context-layer`, `f:rmx_binary_is_deploy`, `f:deploy_tree_is_the_runtime`, `f:refmatrix_dev_deploy_split` | none (intent, not a call pattern) | always-on pointer (≤ 1 KB list) | AO, IX+REC |
| R010 | Push to GitHub only from the dev repo (`git -C <dev> push origin master:main`), never from a `cd ~/refmatrix` shell; the user pushes | T1 | `f:push_from_dev_not_deploy`, `C#git-workflow`, `r:github_remote` | Bash: `git push` with cwd or `-C` = `~/refmatrix` | PreToolUse deny | AO, IX+REC |
| R011 | Deploy only from a committed `master` sha (fast-forward `~/refmatrix`) | T1 | `C#git-workflow`, `P#commands`, `O#release` | Bash: `git -C ~/refmatrix (pull\|merge)` while dev `master` is dirty or the ref is not `master` | PreToolUse deny | AO, F |
| R012 | Never commit to the `release` branch | T1 | `C#permissions`, `O#commits` | Bash: `git commit` / `push` with HEAD or target `release` | PreToolUse deny | AO, F |
| R013 | Never execute `rm -rf *` | T1 | `C#permissions` | Bash: `rm -rf *` | PreToolUse deny / permissions.deny | AO |
| R014 | Never revert or discard uncommitted work (checkout, `reset --hard`, stash drop) without the user's confirmation | T1 | `AM` | Bash git ref/working-tree change over a dirty tree | auto-mode hard_deny (exists) | -; AM hard_deny (p20-0) |
| R015 | Never externalize project content off-machine (Artifact tool, web services) | T1 | `AM` | Artifact / web tool call with project content | auto-mode hard_deny (exists) | -; AM hard_deny (p20-0) |
| R016 | Never put two writers on one logical database (one writer per store: the daemon) | T1 | `AM`, `P#primitives` | second writer open on a held DB | auto-mode hard_deny (exists) | AO; AM hard_deny (p20-0) |
| R017 | Read-only recon (grep/rg, `rmx context/query/grep`, ls, git status, cat) is always allowed | T1 | `AM` | any recon call | auto-mode allow (exists) | -; AM allow (p20-0) |
| R018 | Coordinator lane-scoped DB commands are drift: dispatch DB execution to a lane agent (advisory) | T1 | `AM` | main-thread DB command | auto-mode environment (exists) | -; AM environment (p20-0) |
| R019 | Standing grants: any command in the project tree, in `/Volumes/littlebig` (except `bleach series`, `Photos`), under `/private/tmp/claude-501/`; do not prompt for permission | T1 | `C#permissions`, `f:littlebig_permission_scope`, `f:private_tmp_claude_permission_scope` | any call targeting those trees | permissions.allow / auto-mode allow | AO, IX+REC |
| R020 | Never list, read, write or glob inside `/Volumes/littlebig/bleach series` or `/Volumes/littlebig/Photos`, nor recurse at the volume root | T1 | `f:littlebig_permission_scope` | Bash/Read/Write/Glob path under those dirs or `/Volumes/littlebig` root recursion | PreToolUse deny | IX+REC |
| R021 | Never `find /` (or `fd`/`bfs` from `/`); scope every search to the repo, a named sibling or `~/github`; every brief says so | T1 | `f:never_search_from_root`, `brief:census-rules` | Bash: `(find\|fd\|bfs) /( \|$)` | PreToolUse deny | IX+REC |
| R022 | Searches over `~/github/atollogy/bdep` prune `_frameworks_and_libraries`, `node_modules`, venvs, `target`, `build`, `dist` | T1 | `f:bdep_search_skip_frameworks`, `f:never_search_from_root` | Bash: `find`/`grep -r` over bdep without `-prune` | PreToolUse deny (rule as reason) | IX+REC |
| R023 | Find fleet repos from the known candidate list (hub registry, launchd roots, named repos); never walk `~/github` or `~/enduris` | T3 | `f:fleet_discovery_known_list_no_tree_walk` | Bash: a fleet `install-hooks` / hook audit loop | skill `fleet-hooks` via PreToolUse inject | IX+REC |
| R024 | Mac mini: probe read-only; system changes there are the user's; the lane never runs under `sudo` | T1 | `r:mac_mini_test_host` | Bash: `ssh …mini` with `sudo`/`port install`/system writes | PreToolUse deny | IX+REC |
| R025 | Never prefix commands with `rtk` (purged 2026-09-13) | T1 | `r:rtk_purged` | Bash: `^rtk ` | PreToolUse deny | IX+REC |
| R026 | Run `git` raw; never read git state through a filter that can drop rows | T1 | `a:gmd-curator`, `hook:grep-rewrite-guard.sh` | Bash git through a rewriter | already structural (guard passes git raw) | AG; ENF grep-rewrite-guard.sh (git exempt) |
| R027 | Never `cd` into another agent's git worktree; read it with `git -C` / absolute paths | T1 | `hook:worktree-cd-guard.sh` | Bash: `cd` into `*/.claude/worktrees/<name>` | PreToolUse deny (exists) | -; ENF worktree-cd-guard.sh |
| R028 | Before any git ref change, check for a second session; in a shared tree never switch branches, stage own paths only | T1 | `f:shared_tree_no_branch_switch`, `plan-32` | Bash: `git (checkout\|switch\|reset)` in the dev tree while another session/agent is live | PreToolUse deny | IX+REC |
| R029 | `rmx save-state --commit` runs `git add -A`; never use it while agents edit the tree | T1 | `f:save_state_commit_adds_all`, `plan-32`, `RC` | Bash: `rmx save-state .*--commit` with live agents | PreToolUse deny | IX+REC, F |
| R030 | Commit own paths by pathspec; never `git add -A` / `commit -a` in the shared dev tree | T1 | `O#commits`, `f:save_state_commit_adds_all`, `f:shared_tree_no_branch_switch` | Bash: `git add -A`, `git add --all`, `git add .`, `git commit -a` in the dev tree | PreToolUse deny | IX+REC, F |
| R031 | Batch doc edits into few commits (each commit re-ingests the large GMD files and holds the writer, bug-177) | T3 | `O#commits` | Bash: `git commit` touching only `workflow/**` / `docs/**` | PreToolUse inject (allow) | F |
| R032 | One branch per plan task, merged `--no-ff`; never delete branches | T1 | `C#git-workflow`, `C#task-completion-workflow`, `O#task` | Bash: `git branch -[dD]`, `git merge` on master without `--no-ff` | PreToolUse deny | AO, F |
| R033 | `.mcp.json` pointed at `.venv-eval/bin/rmx` stays uncommitted | T1 | `C#mcp-servers` | Bash: `git add`/`commit` including `.mcp.json` | PreToolUse deny / pre-commit | AO |
| R034 | Never hand-edit the generated rmx hook block in `.claude/settings.json`; change `hooks.py` / `search_hooks.py` and re-install | T1 | `P#primitives`, `P#constraints`, `a:ch-implementer.local`, `a:ch-bsd.local` | Edit/Write `.claude/settings.json` | PreToolUse deny (rule as reason) | AO, AG |
| R035 | Before `install-hooks --apply`: back up hooks + all settings files, diff the entry list after; `--no-claude` REAPS rmx hooks | T3 | `f:install_hooks_no_claude_reaps` | Bash: `rmx install-hooks .*--apply` | PreToolUse inject checklist (allow) | IX+REC |
| R036 | `launchctl install --force` can leave a service unloaded; check `launchctl list` before any kickstart | T3 | `f:launchd_install_force_leaves_it_unloaded`, `plan-32` | Bash: `rmx (daemon\|hub) launchctl install` | skill `release-deploy` via PreToolUse inject | IX+REC |
| R037 | Restart a stale hub with `rmx hub stop` + ONE `launchctl kickstart`; never `rmx hub start`; repeated `kickstart -k` piles orphans on :7777 | T1 | `f:hub_restart_via_launchctl`, `f:hub_kickstart_orphan_pileup`, `O#release` | Bash: `rmx hub start`; repeated `launchctl kickstart -k …hub` | PreToolUse deny with the recipe as reason | IX+REC, F |
| R038 | A running daemon serves the code it imported; restart affected daemons after a promote; a stop-path fix needs a SECOND restart to observe | T3 | `f:restart_daemon_after_promote`, `f:shutdown_fix_needs_a_second_restart` | state: deploy (`git -C ~/refmatrix pull`) | skill `release-deploy` | IX+REC |
| R039 | MCP server is a per-client stdio process: after deploying `mcp.py`, `/mcp` reconnect; orphans pile up | T3 | `C#mcp-servers`, `f:mcp_server_reload_and_orphans` | state: deploy whose diff touches `mcp.py` | skill `release-deploy` | AO, IX+REC |
| R040 | Hub UI assets are version-busted; bump the version on every UI change; register any new static asset in `index()` | T2 | `f:version_bust_ui_assets` | Edit `src/refmatrix/ui/**` | paths: rule `src/refmatrix/ui/**` | IX+REC |
| R041 | A `cd` inside a backgrounded `&&` list stays in the subshell; pin store-targeted `rmx` calls to their tree (`cd X \|\| exit`, print `pwd`) | T1 | `f:backgrounded_cd_stays_in_subshell` | Bash: `cd … && (…) &` followed by `rmx` | PreToolUse deny (rule as reason) | IX+REC |
| R042 | Every background watch loop has a deadline, and its `pgrep -f` pattern cannot match itself | T1 | `f:watch_loops_need_a_deadline` | Bash `run_in_background` with `until`/`while` and no `timeout` | PreToolUse deny (rule as reason) | IX+REC |
| R043 | Generated corpora live off the watched tree (`.gitignore` does not stop the watcher) | T2 | `f:generated_data_off_watched_tree` | Edit/Write under `eval/**` writing bulk data | paths: rule `eval/**` | IX+REC |
| R044 | Raw prompts, query logs, STM rings and transcripts never enter the public repo; commit a hash + redacted fixture | T4 | `f:no_raw_prompts_in_public_repo` | git commit staging log-derived fixtures | pre-commit scan | IX+REC |
| R045 | Live store health: `daemon.stderr.log` `FatalException` lines are the crash signature `status` cannot see | T3 | `P#commands` | state: deploy live check | skill `release-deploy` | AO |
| R046 | Do not share sensitive information or credentials | T8 | `C#permissions` | none | principles block | AO |

### Tests {#t-tests}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R047 | Every test run captures output to a file (`2>&1 \| tee workflow/review-output/<name>.log`) | T1 | `C#development-commands`, `P#commands`, `a:ch-test-engineer.local`, `a:ch-implementer.local`, `a:ch-implementer`, `a:ch-test-engineer` | Bash: `pytest` without `tee`/redirect | PreToolUse deny (exists, partial) | AO, AG; ENF enforce-test-to-file.sh (partial: allows `\| tail`/`\| head`/`\| wc` with no file) |
| R048 | Never `--ignore`, `-k` or skip away a failing group; fix the environment | T1 | `C#system-dependent-tests`, `C#test-discipline`, `a:ch-implementer`, `a:ch-test-engineer` | Bash: `pytest` with `--ignore`/`--deselect`/`-k not` | PreToolUse deny (rule as reason) | AO, AG |
| R049 | Extend, don't add: no per-round/bug/fix test files; 2+ variants are one parametrized test | T2 | `C#test-discipline`, `O#task-tests`, `a:ch-test-engineer.local`, `a:ch-architect.local`, `a:ch-bsd.local`, `a:ch-implementer.local` | Write/Edit `tests/**` | paths: rule `tests/**` | AO, AG, F; GUARD test_suite_discipline.py (round-named files) |
| R050 | One test file per feature, grouped by module (mirrors `src/` after 29.5) | T2 | `C#test-discipline` | Write `tests/**` | paths: rule `tests/**` | AO |
| R051 | Each feature change has a test through the entry point users call (CLI, verb, MCP, daemon op, hook) | T2 | `C#test-discipline`, `SA#q-wiring`, `a:ch-test-engineer.local` | Write/Edit `tests/**` | paths: rule `tests/**` | AO, AG, F |
| R052 | Real states, faked boundaries only: never patch the function under test, the value a guard reads, `ping`/`daemon.call`; mocks registered | T2 | `C#test-discipline`, `C#no-mocks`, `a:ch-test-engineer.local`, `a:ch-test-engineer`, `a:ch-bsd.local`, `a:general-purpose` | Write/Edit `tests/**` | paths: rule `tests/**` | AO, AG; GUARD test_mock_registry_coverage.py |
| R053 | A source-text test is only a guard on a stated rule and plants a must-fail case | T2 | `C#test-discipline`, `a:ch-bsd.local` | Write/Edit `tests/**` | paths: rule `tests/**` | AO, AG |
| R054 | A changed or vendored checker is proven to FIRE on committed must-fail fixtures; equal error counts are not evidence | T2 | `f:clean_corpus_hides_a_dead_gate`, `SA#q-guard` | Edit `tools/gmd/**`, `scripts/*lint*`, `tests/*census*` | paths: rule on checker files | IX+REC, F |
| R055 | No real waits: test-sized budget knob, one test per budget at the real default, short shutdown timeouts, gates not big data | T2 | `C#test-discipline`, `a:ch-bsd.local` | Write/Edit `tests/**` | paths: rule `tests/**` | AO, AG; GUARD test_wallclock_census.py |
| R056 | Daemon tests use a SHORT `mkdtemp()` root (`sun_path` ~104 B) and never a real `.refmatrix/` | T2 | `C#test-discipline`, `a:ch-test-engineer.local`, `O#roles-agents` | Write/Edit `tests/**` | paths: rule `tests/**` | AO, AG, F; GUARD test_tmp_root_census.py |
| R057 | A new test is seen failing first, for the intended reason (its E line); a RED test that passes at HEAD is not RED | T3 | `C#test-discipline`, `C#before-commit`, `O#task-small`, `O#task`, `f:red_test_must_fail_at_head`, `a:ch-implementer.local`, `a:ch-test-engineer.local` | Agent dispatch of ch-test-engineer / small-fix agent | skill `dispatch-red-green` (agent `skills:` preload) | AO, AG, IX+REC, F |
| R058 | Never red across releases: fix or `xfail(strict=True, reason="bug-NNN")`, with a registry row | T4 | `C#test-discipline` | state: merge / release gate | merge-gate check (`scripts/ptest.py --merge-gate`) + pre-commit | AO |
| R059 | Verify runs go to an isolated lane (`lane-mini.sh` preferred, `lane-local.sh`) on a committed sha; the `lockf` lane only for dev-tree tests and the release full suite | T3 | `C#test-discipline`, `O#one-suite`, `r:isolated_test_lanes`, `a:ch-test-engineer.local` | Bash: `pytest` (any) | skill `lane-verify` via PreToolUse inject | AO, AG, IX+REC, F |
| R060 | A branch runs its verify set (task tests + every importer of a changed module), never the full suite | T3 | `C#test-discipline`, `O#task-verify`, `a:ch-test-engineer.local`, `C#task-completion-workflow` | Bash: `pytest` (any) | skill `lane-verify` | AO, AG, F |
| R061 | Every verify set carries the repo-wide guards (tmp-root, suite-discipline, docs-generated, mock-registry, deferrals, wallclock, budget-outcome, verb parity …) | T3 | `f:verify_set_includes_repo_guards`, `plan-32` | Bash: `pytest`/lane script with a file list | skill `lane-verify` + PreToolUse check of the list | IX+REC |
| R062 | Failures are compared by E line with the last release's log; 'also fails at master' means the same error | T3 | `O#task-verify`, `O#release`, `f:compare_failures_by_error_not_name`, `C#task-completion-workflow` | state: verify result read | skill `lane-verify` | AO, IX+REC, F |
| R063 | Adding/removing/renaming a CLI command, option or op regenerates the CLI tree and adds `test_docs*`/`test_cli*` to the verify set | T2 | `f:family_list_misses_generated_checks` | Edit `src/refmatrix/cli.py`, `daemon.py` OPS | paths: rule `src/refmatrix/cli.py` | IX+REC; GUARD test_docs_generated.py |
| R064 | Mutations only on the `src/` change, one at a time; each must FAIL (not hang) a bounded run; restore in its own command and prove it | T3 | `O#task`, `f:mutation_must_fail_not_hang`, `a:ch-test-engineer.local` | Bash: a mutation loop (`sed -i`/`cp` on `src/` + `pytest`) | skill `mutation-loop` via PreToolUse inject | AG, IX+REC, F |
| R065 | Commit GREEN (with `src/`) before mutating: `git status --short src` empty; grep a fix line after the restore | T1 | `f:commit_before_mutation_revert`, `f:mutation_commit_must_hold_the_fix` | Bash: mutation loop with a dirty `src/` | PreToolUse deny (rule as reason) | IX+REC |
| R066 | Clear `src/**/__pycache__` after a mutation batch before believing any run | T3 | `f:clear_pycache_after_mutation` | state: mutation loop end | skill `mutation-loop` | IX+REC |
| R067 | Large change: RED and GREEN in different hands, even when the user says 'right now' | T3 | `O#task`, `C#task-completion-workflow`, `f:keep_red_and_green_separate_under_urgency`, `f:lean_process_reset`, `a:ch-implementer` | Agent dispatch for a large change | skill `dispatch-red-green` via PreToolUse(Agent) inject | AO, AG, IX+REC, F |
| R068 | Classify every task small or large before dispatch; small = one isolated agent writes test + fix, no mutations, no ch-bsd | T3 | `O#task-small`, `C#task-completion-workflow`, `f:lean_process_reset`, `a:ch-implementer.local` | Agent dispatch | skill `dispatch-red-green` via PreToolUse(Agent) inject | AO, AG, IX+REC, F |
| R069 | RED is the second view: at least one entry-point test, one busy/slow test on a real test daemon, one census test | T3 | `a:ch-test-engineer.local` | Agent start: ch-test-engineer | skill `dispatch-red-green` (preload) | AG |
| R070 | Known pre-existing failure `test_graph_landing.py::test_context_op_honors_partition_under_ambient_drift`: fix it, do not skip it | T7 | `a:ch-test-engineer.local` | Agent start: ch-test-engineer | agent overlay (stale? not checked) | AG |
| R071 | Tests run in Docker only, never on the host (template text) | T7 | `a:general-purpose`, `a:ch-test-engineer`, `a:ch-code-reviewer`, `a:ch-implementer`, `a:ch-performance-tuner` | Agent start | delete (contradicts C: no container) | AG |

### Code conventions (`src/`) {#t-code}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R072 | No mocks, stubs, placeholder branches or stale 'Phase N stub' code in `src/`; mocks only in `tests/`, registered | T2 | `C#no-mocks`, `C#before-commit`, `a:general-purpose`, `a:ch-implementer`, `a:ch-code-reviewer`, `a:ch-architect`, `a:ch-gap-master` | Edit/Write `src/**` | paths: rule `src/**` | AO, AG; GUARD test_deferrals_clean.py (deferral comments) |
| R073 | No silent failures on memory paths (no `2>/dev/null`, `\|\| true`, bare `except: pass`, uncounted skip); a stopping error is loud on the console | T2 | `C#no-silent-failures`, `P#constraints`, `f:no_silent_failures`, `f:errors_fail_loudly_on_the_console`, `a:general-purpose`, `a:ch-implementer`, `a:ch-implementer.local`, `SA#q-loud` | Edit/Write `src/**`, `hooks.py` | paths: rule `src/**` | AO, AG, IX+REC, F |
| R074 | No workarounds: a missing dependency is defined as a gap, the fix proposed, the user asked; read `development_resources.md` first | T8 | `C#no-workarounds`, `a:ch-implementer`, `a:ch-code-reviewer` | none | principles block | AO, AG |
| R075 | Docstrings say WHY and name the incident/date | T2 | `C#development-guidelines`, `a:ch-implementer.local` | Edit/Write `src/**` | paths: rule `src/**` | AO, AG |
| R076 | Match surrounding style, ~100 columns, type hints on new signatures; no formatter gate | T2 | `C#development-guidelines`, `P#commands` | Edit/Write `src/**` | paths: rule `src/**` | AO |
| R077 | Reason from the primitives and reuse existing infrastructure before adding a mechanism; collapse 'two ways to do X' | T8 | `C#development-guidelines`, `f:prefer_existing_infra`, `a:ch-implementer`, `a:ch-architect.local` | none | principles block | AO, AG, IX+REC |
| R078 | Every agent-facing capability is a `@verb` first; CLI and MCP are thin adapters; verb parity is a test | T2 | `P#primitives`, `P#constraints`, `a:ch-implementer.local`, `a:ch-bsd.local`, `C#before-commit` | Edit `src/refmatrix/{mcp,cli,verbs}.py` | paths: rule on those files | AO, AG; GUARD test_verb_parity.py |
| R079 | New daemon op = `_op_<name>` registered in `OPS` (`CLI_OPS` only for fast reads); writes under the store lock | T2 | `a:ch-implementer.local`, `a:ch-bsd.local` | Edit `src/refmatrix/daemon.py` | paths: rule `daemon.py` | AG |
| R080 | Code routes store access through the daemon (`_store(write)`); direct `Store()` only for bootstrap or read-only replicas | T2 | `P#primitives`, `P#constraints`, `f:store_calls_via_daemon`, `a:ch-architect.local` | Edit/Write `src/**` | paths: rule `src/**` | AO, AG, IX+REC |
| R081 | `daemon.call` defaults to `retries=2` (worst case 3 x timeout); best-effort paths pass `retries=0` and a small bound | T2 | `f:daemon_call_retries_multiply_timeouts`, `SA#q-bound` | Edit `src/**` adding `daemon.call(` | paths: rule `src/**` | IX+REC, F |
| R082 | Every token-quality gate reuses `scan._PROMPT_STOPWORDS`; never a hand-rolled set | T2 | `f:reuse_shared_stoplist` | Edit `src/refmatrix/{stm,scan,terms,concepts*}.py` | paths: rule on token paths | IX+REC |
| R083 | Repeated same-shape fixes at 2+ sites mean a missing common function: converge, then add a bypass check | T8 | `f:converge_repeated_shapes` | none | principles block | IX+REC |
| R084 | The main maintenance path exercises every core mechanism; correctness never hides behind an opt-in flag | T2 | `f:main_path_must_exercise_core_mechanisms` | Edit `src/refmatrix/ingest*.py`, `cli.py` | paths: rule on ingest paths | IX+REC |
| R085 | A dry-run pays the real cost when the data path forces it; never a fake cheap preview | T8 | `f:dry_run_match_real_cost` | none | principles block | IX+REC |
| R086 | Decay may demote, never lose knowledge (exact lifetime record, floor not zero, terminal tiers, audited removal) | T8 | `f:decay_never_loses_knowledge` | none | principles block | IX+REC |
| R087 | What is operational is decided by `memory_layout.is_operational` only; never a private regex or an ingest exclusion | T2 | `f:operational_content_same_partition_not_skewing`, `f:operational_content_not_in_graph` | Edit `src/refmatrix/{memory_layout,ingest*}.py` | paths: rule on those files | IX+REC |
| R088 | The benchmark path IS the production path (`eval/production/`) | T2 | `P#constraints`, `f:measure_the_path_users_run` | Edit/Write `eval/**` | paths: rule `eval/**` | AO, IX+REC |
| R089 | No implicit external calls: models load via `models_local.load_local`; `HF_HUB_OFFLINE` set before import | T2 | `f:external_calls_policy` | Edit `src/**` adding a model load | paths: rule `src/**` | IX+REC; GUARD test_models_offline.py |
| R090 | Injected context: most important first, one hook command under its byte cap, blocks labelled by kind, never repeat an unchanged block | T2 | `f:injection_presentation_rules`, `r:hook_output_10k_cap`, `r:hook_output_cap_measured` | Edit `src/refmatrix/{hooks,search_hooks,scan,composite*}.py` | paths: rule on hook producers | IX+REC |
| R091 | Hook changes: edit `hooks.py`/`search_hooks.py` + tests, then `rmx install-hooks --apply` here so settings match | T2 | `a:ch-implementer.local`, `P#primitives` | Edit `src/refmatrix/{hooks,search_hooks}.py` | paths: rule on hook generators | AO, AG |
| R092 | ADR first: a new class matching an existing ADR is checked against it | T2 | `hook:adr-gate.sh` | Edit/Write `src/**` adding `class X` | PostToolUse warn (exists) | -; WARN adr-gate.sh |
| R093 | Never SIGKILL a busy daemon (supervisor interactions) | T2 | `a:ch-architect.local` | Edit `src/refmatrix/{hub,launchctl,daemon}.py` | paths: rule on supervisor files | AG |
| R094 | Neutral agent/command definitions never hardcode project facts; those go in `.local.md` overlays / PROJECT_PROFILE | T2 | `a:ch-implementer`, `a:ch-architect`, `a:ch-alignment`, `a:ch-bsd`, `a:gmd-curator`, `P#root` | Edit `.claude/agents/*.md`, `src/refmatrix/templates/**` | paths: rule on agent/template files | AO, AG |

### GMD, docs and memory files {#t-gmd}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R095 | Persistent prose is GMD: frontmatter `gmd`/`id`/`title`/`tags`, an anchor on every heading, `rel:` edges for citations | T2 | `GMD#authoring`, `C#graph-markdown`, `P#constraints`, `MR#frontmatter`, `a:ch-doc-writer` | Write/Edit `docs/**`, `workflow/**`, memory dir, `CLAUDE.md` | paths: rule `{docs,workflow}/**/*.md` | AO, AG |
| R096 | Read GMD as a graph: follow wikilinks; a `supersedes` target is history only | T2 | `GMD#interpret` | Read of a GMD file | paths: rule `**/*.md` | AO |
| R097 | GMD lint zero errors before a commit (`./scripts/lint-gmd.sh` for repo docs; `tools/gmd/lint.py` for memory files) | T4 | `C#graph-markdown`, `C#before-commit`, `P#commands`, `MR#validation` | git commit staging `*.md` | pre-commit hook | AO; WARN lint-memory-gmd.sh (memory files only, warn mode) |
| R098 | Before committing a persisted report, run the repo-scope gate and chain the commit on its exit code (single-file lint is not enough) | T4 | `f:repo_gate_before_persisting_reports`, `O#reports`, `f:review_clones_cannot_see_dev_tree_failures` | git commit staging `workflow/**` | pre-commit hook | IX+REC, F |
| R099 | Memory files: GMD frontmatter (`node_type: memory`, `type`, `originSessionId`, `created` frozen, `updated`), id = filename stem, `# Title {#root}`, Why / How | T2 | `MR#frontmatter`, `MR#body` | Write/Edit memory dir `*.md` | paths: rule (memory dir; needs an additional-directory rule or the hook) | AO; WARN lint-memory-gmd.sh (lint only, not shape) |
| R100 | Cross-memory references are typed `rel:` edges, never bare `[[name]]`; never reference `MEMORY.md` as a node | T2 | `MR#edges` | Write/Edit memory dir `*.md` | paths: rule (memory dir) | AO; WARN lint-memory-gmd.sh (partial) |
| R101 | Amend vs overwrite vs supersede: typo → overwrite; new exception → new file `amends`; wrong → new file `supersedes` | T2 | `MR#amend-tree`, `a:gmd-curator` | Write to an existing memory subject | paths: rule (memory dir) | AO, AG |
| R102 | Forget flow: rewrite load-bearing inbound edges to `[[void]]`, drop decorative ones, update the index, then delete | T3 | `MR#forget` | Bash `rm` / delete of a memory file | PreToolUse inject (allow) + skill `forget-memory` | AO |
| R103 | `MEMORY.md` is a flat one-line index, not GMD, under 200 lines | T2 | `MR#index` | Write/Edit `MEMORY.md` | paths: rule (memory dir) | AO |
| R104 | Verify a saved memory by recalling a phrase unique to it (and embedding), never by `memory get` | T3 | `f:verify_memory_by_recall_not_get` | PostToolUse Write of a memory file | PostToolUse inject the check step | IX+REC |
| R105 | Write memory files BEFORE `rmx save-state` | T3 | `RC` | Bash/MCP save-state | skill `save-state` | F |
| R106 | ch-bsd ledger artifacts carry the real write time (`date +%FT%T%z`) in name, INDEX and `last_run.log`; no forged git dates | T2 | `a:ch-bsd.local` | Write `workflow/bullshit/**` | paths: rule `workflow/bullshit/**` | AG |
| R107 | `IMPRESSIONS.md` 50-line cap above `## Former anchors, restored`; one `{#id}` per line there | T2 | `a:ch-bsd.local`, `a:ch-bsd` | Edit `workflow/bullshit/IMPRESSIONS.md` | paths: rule + a line-count check | AG |
| R108 | Persist a review: copy to `workflow/bullshit/<UTC>-<subject>-r<n>-<sha>.md`, INDEX row, `last_run.log` line, new IMPRESSIONS bullets; lint; reports returned as text are persisted by the lead | T3 | `O#reports`, `r:subagent_reports_returned_as_text`, `a:ch-bsd` | Write `workflow/bullshit/*.md` | skill `persist-review` via paths: | AG, IX+REC, F |
| R109 | Reviews persist to `workflow/review-output/<plan>-<phase>-<reviewer>.md` before a chat summary | T7 | `a:general-purpose` | Agent start | agent file (contradicted by harness; see contradictions) | AG |
| R110 | New ADRs: `docs/adr/NNNN-slug.md`, GMD, status weighting, rows in `0000-adr-overview` and `docs/INDEX.md` | T2 | `a:ch-architect.local` | Write `docs/adr/**` | paths: rule `docs/adr/**` | AG |
| R111 | Explorations live in `docs/architecture/explorations/`, are written incrementally, get a Transition Summary, never deleted | T2 | `PW#exploration-workflow` | Write `docs/architecture/explorations/**` | paths: rule | F |
| R112 | gmd-curator: never edit code or non-GMD docs, never pick winners (mark `contradicts`), one fact in one place, no `rebuild --from-log` without confirmation | T7 | `a:gmd-curator` | Agent start: gmd-curator | agent file (exists) | AG |

### Planning, ledgers and the POP {#t-planning}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R113 | The POP is the source of truth: a merge, release, admission, status or scope change updates `plan-of-plans.md` in the SAME commit | T4 | `O#pop-truth`, `f:pop_is_source_of_truth`, `C#before-commit`, `PW#when-all-questions-are-resolved`, `plan-32` | git commit (merge, version bump, plan status flip) | commit-msg / pre-commit check | AO, IX+REC, F |
| R114 | L, D and Q rows are entered in the POP ledgers before any plan/spec is amended, which then cites the row | T2 | `f:ldq_enter_pop_first`, `O#ledgers` | Edit `workflow/plans/**` | paths: rule `workflow/plans/**` | IX+REC, F |
| R115 | Every question to the user gets a `Q<n>` (or `plan-N Dk`) id first; open ids are listed at the end of the reply; an interpreted answer stays open | T4 | `O#ledgers`, `f:track_questions_by_id`, `f:plan_d_labels_are_valid_ids`, `f:plan_decisions_are_questions` | Stop (reply asks the user something) | Stop hook block when open ids are missing | IX+REC, F |
| R116 | An `L<n>` only for a decision that changes scope, order or what is built; no rows for relays or bookkeeping | T8 | `O#ledgers`, `f:proportionate_process` | none | principles block | IX+REC, F |
| R117 | Proportionate process: say what a band, round or table buys before running it; propose the lighter path first | T8 | `O#proportionate`, `f:proportionate_process`, `f:lean_process_reset`, `plan-32` | none | principles block | IX+REC, F |
| R118 | Specs just in time: a task is specced when it is next in the queue | T3 | `O#planning`, `C#task-completion-workflow`, `f:lean_process_reset` | state: queue head changes | skill `spec` (ch-architect preload) | AO, IX+REC, F |
| R119 | Complete-plan gate: no production code until every task spec exists (`status: approved`) | T4 | `PG#lifecycle-gates`, `PW#plan-approval-gate`, `C#plans-pre-written` | git commit touching `src/` for a plan not `approved` | pre-commit check (or retire, see contradictions) | AO, F |
| R120 | A spec is one page: goal, ACs each naming its test (existing file, entry point, real fixture), files, risks = the self-audit questions | T3 | `O#planning`, `a:ch-architect.local`, `f:lean_process_reset` | Agent start: ch-architect; Write `workflow/plans/*-tasks/**` | skill `spec` (preload + paths:) | AG, IX+REC, F |
| R121 | One architect read per spec, no ch-bsd round on a spec; open decisions go to the user with a recommendation | T3 | `O#planning`, `f:lean_process_reset` | Agent dispatch of ch-bsd on `workflow/plans/**` | PreToolUse(Agent) deny with the rule | IX+REC, F |
| R122 | Planning authors (plans, specs, ADRs, spec revisions) are dispatched on Fable (`model: fable`) | T3 | `O#roles-models`, `f:planning_runs_on_fable`, `PW#default-planning-path`, `C#agent-skill-workflow` | Agent(ch-architect or a plan author) without `model: fable` | PreToolUse(Agent) inject (allow) | AO, IX+REC, F |
| R123 | Write proposed plans to disk BEFORE presenting questions; update the plan after each answer; handoff names the active plan | T2 | `C#planning-exploration-templates`, `PW#planning-mode-workflow` | Write `workflow/plans/**` (status drafting) | paths: rule `workflow/plans/**` | AO, F |
| R124 | Plan stage lives only in `metadata.status` (drafting → approved → in-progress → completed); plans never move | T2 | `PW#status-tracked-plan-lifecycle`, `PG#lifecycle-gates`, `C#plans-pre-written` | Edit `workflow/plans/*.md` | paths: rule `workflow/plans/**` | AO, F |
| R125 | Triage plan state from the latest consolidation and L-rows and a merged sha; read `metadata.status` last | T8 | `f:triage_from_decisions_not_file_status` | none | principles block | IX+REC |
| R126 | Staleness: 15-30 d verify, 31-60 d re-justify, 60+ d escalate | T5 | `PG#staleness` | SessionStart | SessionStart orientation line | F |
| R127 | Question-forcing: vague deliverables, missing signatures or unclear integration block approval | T8 | `PG#question-forcing` | none | principles block | F |
| R128 | Source-of-truth order: POP → `plans/` → `plans/<plan>-tasks/` | T10 | `PG#source-of-truth-order`, `C#planning-task-docs` | none | always-on pointer | AO, F |
| R129 | Decide spec-review questions as the user would, record decision rows, ask only for irreversible live-store steps (Wave 0-1 scope) | T8 | `f:follow_approval_pattern_wave01` | none | principles block (or retire as historical) | IX+REC |
| R130 | Run and iterate ch-bsd to clean before surfacing decisions (superseded by L165) | T8 | `f:bsd_iterate_before_surfacing` | none | retire (superseded, still indexed) | IX+REC |
| R131 | Cleanup phase after each plan: triage `todo.md`, graduate mocks, clear deferred Medium findings | T3 | `C#cleanup-phase` | Edit plan `status: completed` | skill `plan-close` via paths: | AO |
| R132 | Before-commit checklist (src concrete, verify log, mutations for large, lint, `install-hooks --check`, verb parity, POP row) | T4 | `C#before-commit` | git commit | pre-commit hook running the mechanical items | AO |
| R133 | When to pause: only a blocking dependency, ambiguity, a user request, or a store-changing decision | T8 | `C#when-to-pause` | none | principles block | AO |

### Dispatch, roles, briefs and review {#t-dispatch}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R134 | The lead dispatches, decides, merges, releases, deploys and does every live-store write; it writes no `src/` or tests beyond a one-line literal | T1 | `O#roles-lead` | Edit/Write `src/**` or `tests/**` from the main session (no `agent_id`) | PreToolUse deny (rule as reason) | F |
| R135 | Agents work in `/Volumes/littlebig/<project>-<worker>` clones, never a `git worktree`; check the volume is mounted | T1 | `C#task-completion-workflow`, `O#roles-agents`, `f:isolate_work_in_littlebig_clones` | Bash `git worktree add`; Agent `isolation: worktree` | PreToolUse deny | AO, IX+REC, F |
| R136 | A brief names clone, branch, base sha, what to read, the artifact, the hard rules (read-only, no `find /`, verify-set guards); every needed ruling is sent to the agent | T3 | `O#roles-briefs`, `f:never_search_from_root`, `f:verify_set_includes_repo_guards`, `f:subagents_read_only_on_live_stores`, `plan-32` | PreToolUse(Agent) | skill `brief` via PreToolUse(Agent) inject | IX+REC, F |
| R137 | Agents look things up through `scripts/rmx-master` read verbs or the read-only MCP tools; a clone has no store | T7 | `P#corpus`, `O#roles-agents` | SubagentStart | SubagentStart `additionalContext` | AO, F |
| R138 | Before removing a littlebig clone, check live agents' use (mtime, `lsof +D`, lane args, ask agents) | T3 | `f:clone_cleanup_checks_live_agent_use` | Bash `rm -rf /Volumes/littlebig/<project>-*` | PreToolUse inject checklist | IX+REC |
| R139 | Watch long runs: after an agent's expected run time, tail its log and `pgrep` the runner yourself | T8 | `O#watch`, `f:check_the_log_when_an_agent_idles_on_a_background_run` | none (time-based) | principles block | IX+REC, F |
| R140 | One ch-bsd pass per large change; BULLSHIT → fold + one confirm-lite; GATE → killing test or L-row; SKETCHY → implementer folds, lead checks diff; lead may raise, never lower | T3 | `O#task`, `C#task-completion-workflow`, `a:ch-bsd.local`, `a:ch-bsd`, `SA#loop`, `f:lean_process_reset`, `f:proportionate_process` | Agent dispatch ch-bsd; agent start ch-bsd | skill `bsd-pass` (ch-bsd `skills:` preload) | AO, AG, IX+REC, F |
| R141 | ch-bsd names the self-audit question that should have caught each BULLSHIT, or proposes a new question / lint | T3 | `SA#loop`, `O#task`, `a:ch-bsd.local` | Agent start ch-bsd | skill `bsd-pass` (preload) | AG, F |
| R142 | ch-bsd lists every test-discipline violation in every review (each at least SKETCHY) | T7 | `a:ch-bsd.local` | Agent start ch-bsd | agent overlay (exists) | AG |
| R143 | Never rate a finding down because a gap is disclosed or fits the letter of a spec | T7 | `a:ch-bsd` | Agent start ch-bsd | agent file (exists) | AG |
| R144 | Build agents answer the eight self-audit questions in the summary with evidence; 'N/A' needs a reason; an unanswered question blocks the merge | T4 | `SA#lead`, `O#task-small`, `O#task`, `a:ch-implementer.local`, `a:ch-test-engineer.local`, `a:ch-architect.local`, `a:ch-bsd.local` | SubagentStop of a build agent | SubagentStop block when `## Self-audit` is missing | AG, F |
| R145 | SA-1 Ran it for real: run the changed path the way a user/hook does, paste output; each flag once; a detector once on a catalog copy | T3 | `SA#q-real`, `f:green_tests_are_not_a_working_command`, `f:measure_the_path_users_run` | Agent start (build agents) | skill `self-audit` (preload) | IX+REC, F |
| R146 | SA-2 The test reaches the wiring (entry point, no patched SUT or guard input) | T3 | `SA#q-wiring` | Agent start (build agents) | skill `self-audit` (preload) | F |
| R147 | SA-3 Census of callers and siblings (every operand of a compound gate; every output of the same data) | T3 | `SA#q-census`, `f:check_the_sibling_condition` | Agent start (build agents) | skill `self-audit` (preload) | IX+REC, F |
| R148 | SA-4 The whole path is bounded; state the worst case per call and per resource class | T3 | `SA#q-bound` | Agent start (build agents) | skill `self-audit` (preload) | F |
| R149 | SA-5 Busy is not absent: try busy and down | T3 | `SA#q-busy` | Agent start (build agents) | skill `self-audit` (preload) | F |
| R150 | SA-6 The guard can fire: name the real state, show the caller reaches it | T3 | `SA#q-guard` | Agent start (build agents) | skill `self-audit` (preload) | F |
| R151 | SA-7 Failures are loud: force one, paste exit + stderr, also one failure outside the caught class | T3 | `SA#q-loud` | Agent start (build agents) | skill `self-audit` (preload) | F |
| R152 | SA-8 Nothing handed off on paper: deferrals have an AC or a registry row; a stated rule or count was run | T3 | `SA#q-handoff` | Agent start (build agents) | skill `self-audit` (preload) | F |
| R153 | ch-implementer writes no tests on the large path; on the small path it writes test AND fix | T7 | `a:ch-implementer`, `a:ch-implementer.local` | Agent start ch-implementer | agent overlay (exists) | AG |
| R154 | Subagents do not inherit `/effort`; set `effort:` in the agent frontmatter | T7 | `r:subagent_effort_not_inherited` | agent definition | frontmatter (done on 5 agents) | IX+REC; frontmatter effort: high (ch-implementer, ch-test-engineer, ch-bsd, ch-architect, ch-alignment) |
| R155 | ch-doc-writer writes to disk immediately and dispatches every Task in the background | T7 | `a:ch-doc-writer` | Agent start ch-doc-writer | agent file (exists) | AG |
| R156 | general-purpose: research via the discovery ladder; read large files with offset/limit; don't duplicate a parallel agent | T7 | `a:general-purpose` | Agent start general-purpose | agent file (exists) | AG |

### Bug registry and fixes {#t-registry}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R157 | Before fixing a bug, read `workflow/bug_registry.md` for a known fix and `rmx memory search` the symptom | T6 | `BR` | UserPromptSubmit carrying an error/symptom | UserPromptSubmit registry recall | AO |
| R158 | After fixing a bug, failed test/build/lint or user-reported problem, append a registry row (verbatim symptom, files, cause, fix, tags, status) | T4 | `BR`, `O#registry`, `plan-32` | git commit whose message names a fix / `bug-NNN` | commit-msg check: a registry row in the same commit | AO, F |
| R159 | Editing one file more than twice for one thing signals a bug: log it | T4 | `BR` | PostToolUse: 3rd Edit of one file in a session | PostToolUse counter inject | AO |
| R160 | A recurring bug bumps `Seen` and becomes `recurring` | T2 | `BR` | Edit `workflow/bug_registry.md` | paths: rule `workflow/bug_registry.md` | AO |
| R161 | Agents allocate no registry ids | T7 | `O#roles-agents` | SubagentStart | SubagentStart `additionalContext` | F |
| R162 | 'Fixed' only when the sha is reachable from `master` (`merge-base --is-ancestor` + grep a new symbol) | T4 | `f:verify_fix_reachable_from_master`, `plan-32` | git commit editing a registry row to `fixed` | pre-commit check on `bug_registry.md` | IX+REC |

### Release, deploy and session handoff {#t-release}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R163 | Release: bump `pyproject.toml` + `__init__.py`; shared path = major, few modules = minor; gate (major full suite, minor verify set) by E line; deploy (`git -C ~/refmatrix pull --ff-only`, `daemon restart --relaunch`, `version -v`, `hub relaunch-fleet`, stale hub fix, `install-hooks --check`); live check after backups; batch fixes into one release | T3 | `O#release`, `O#one-suite`, `C#development-commands`, `C#task-completion-workflow`, `P#commands`, `f:deploy_tree_is_the_runtime`, `a:ch-implementer.local`, `plan-32` | Edit of the version in `pyproject.toml`; Bash `git -C ~/refmatrix pull` | skill `release-deploy` via PreToolUse inject | AO, AG, IX+REC, F |
| R164 | Session handoff: rotate `handoff.md` to `past_handoffs/`; `rmx save-state` (promote STM, bridge, memory); list in-flight agents and background shells | T3 | `C#handoff-rotation`, `C#task-completion-workflow`, `f:save_state_means_handoff`, `f:save_state_includes_promote`, `f:watch_loops_need_a_deadline`, `O#roles-briefs`, `RC` | `/save-state`; PreCompact | skill/command `save-state` (exists) + PreCompact hook | AO, IX+REC, F; CMD /save-state; INJ PreCompact `rmx save-state --precompact` |
| R165 | 'Recall state' means resume: read checkpoint + git + memory + daemon state, then orient before acting | T5 | `C#session-start`, `f:recall_state_means_resume` | SessionStart | SessionStart (exists) | AO, IX+REC; INJ SessionStart recall (`memory recall --session-start`, `recall-state --handoff` on compact/clear, `focus context` on resume) |
| R166 | Session start: handoff, POP, `bullshit/last_run.log` (unaddressed BULLSHIT first), git vs handoff, daemon + hub status, active plan | T5 | `C#session-start` | SessionStart | SessionStart inject (partial today) | AO; INJ SessionStart (handoff/recall only) |
| R167 | After compaction or `/clear`, Read the named handoff file before any other action (every other call denied until then) | T5 | `RC` | SessionStart compact/clear | PreToolUse gate (exists) | F; ENF PreToolUse `rmx handoff gate`; INJ UserPromptSubmit `handoff remind`; PostToolUse Read `handoff pulled` |
| R168 | Use the refmatrix MCP tools for model-initiated STM/memory (`rmx_focus_note`, `rmx_change_subject`, `rmx_memory_add`), not Bash `rmx` | T1 | `f:mcp_first_agent_stm`, `C#write-decisions` | Bash `rmx (focus note\|change-subject\|memory add\|memory recall)` from the model | PreToolUse deny with the MCP twin named | AO, IX+REC |
| R169 | Never put backticks in a Bash `rmx focus note` argument (bash substitutes them) | T1 | `f:focus_note_no_backticks` | Bash `rmx focus note` with a backtick | PreToolUse deny | IX+REC |
| R170 | Write decisions immediately to a file; capture the WHY with `rmx_focus_note` at decision points | T8 | `C#write-decisions`, `PW#write-decisions-immediately`, `f:capture_reasoning_in_stm`, `RC` | none | principles block (bind to commit bodies per R171) | AO, IX+REC, F |
| R171 | Bind capture to an artifact the agent already produces (commit body, comment, ADR); never a new voluntary obligation | T8 | `f:bind_capture_to_mandatory` | none | principles block | IX+REC |
| R172 | Place every rule by the most automatic, reliable, repeatable, efficient injection event; never rely on recall | T8 | `f:rule_placement_by_injection_event`, `plan-32` | none | principles block | IX+REC |

### Judgment principles (no detectable trigger) {#t-judgment}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R173 | Measure before deciding, read-only on a copy of `catalog.read.duckdb` | T8 | `O#measure`, `C#development-commands` | none | principles block | AO, F |
| R174 | Name the mechanism only after measuring it; 'X costs N' ships, 'because Y' needs Y measured | T8 | `f:causal_story_before_evidence`, `plan-32` | none | principles block | IX+REC |
| R175 | Write go/no-go ranges (3-4 bands, incl. 'make it cheaper, re-measure') before measuring; never pre-drop on a guess | T8 | `f:go_no_go_ranges_not_predrop` | none | principles block | IX+REC |
| R176 | Ask what a change is FOR before making a measurable side benefit the gate | T8 | `f:measurable_benefit_is_not_the_reason` | none | principles block | IX+REC |
| R177 | Measure what a leg produced, not the wall clock, and repeat under load | T8 | `f:measure_the_outcome_not_the_wall` | none | principles block | IX+REC |
| R178 | Diagnose a hang with `ps -o etime,time` + `lsof -p` before theorising | T8 | `f:lsof_the_stuck_process` | none | principles block | IX+REC |
| R179 | Never explain away a failing guard with a story you already believe; read the assertion | T8 | `f:never_explain_away_a_failing_guard`, `plan-32` | none | principles block | IX+REC |
| R180 | Read every identifier (sha, count, ref name, 'I checked') at write time from its source; never recall one | T8 | `f:read_identifiers_at_write_time`, `f:a_verification_is_an_identifier` | none | principles block | IX+REC |
| R181 | Run the merged tree's tests and the repo gate in the dev tree before the merge commit; read ERRORs as failures | T4 | `f:review_clones_cannot_see_dev_tree_failures` | Bash `git merge --no-commit` / merge commit on dev master | pre-merge-commit check | IX+REC |
| R182 | Use TaskCreate only on real signals (>3 workstreams, fan-out, resume); ignore the clock reminder | T8 | `f:task_reminder_gate_on_signal` | none | principles block | IX+REC |

### Style and orientation {#t-style}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R183 | Caveman compressed mode | T9 | `hook:caveman-activate.js` | SessionStart | one SessionStart / output style | -; INJ SessionStart caveman-activate.js; INJ UserPromptSubmit caveman-mode-tracker.js (per prompt) |
| R184 | Prompt-relevant symbols and memories are injected per prompt | T6 | `RC`, `C#memory-context-layer` | UserPromptSubmit | UserPromptSubmit (exists) | AO, F; INJ `rmx scan-prompt`; INJ `rmx memory recall --stdin-json` |

### Reference facts (T10) {#t-reference}

| # | Rule | T | Stated in | Trigger event | Target mechanism | Today |
|---|---|---|---|---|---|---|
| R185 | Discovery ladder: `rmx context` → `rmx grep` → `tldr` → raw grep; in clones `scripts/rmx-master` | T10 | `C#discovery-tooling`, `P#corpus`, `a:general-purpose`, `a:ch-alignment`, `f:rmx_first_retrieval`, `f:grep_is_observed_not_answered`, `RC` | Grep tool / Bash grep on the corpus | always-on pointer + PostToolUse(Grep) teach | AO, AG, IX+REC, F; INJ grep-tool-teach.sh (PostToolUse Grep); ENF enforce-rmx-grep.sh + grep-rewrite-guard.sh (off: `learn.off` present) |
| R186 | Never `/usr/bin/grep` and no `RMXGREP_MODE` escape; a grep reading a pipe stays byte-exact | T1 | `f:rmxgrep_no_plain_escape`, `f:rmxgrep_plain_escape`, `f:grep_is_observed_not_answered`, `plan-32` | Bash `/usr/bin/grep`, `env RMXGREP_MODE=` | PreToolUse deny | IX+REC |
| R187 | Two venvs: `.venv-eval` (dev, tests) and `~/refmatrix/.venv` (deploy behind `~/bin/rmx`, daemons, hub) | T10 | `C#development-commands`, `P#layout`, `P#commands`, `f:deploy_tree_is_the_runtime` | none | nested CLAUDE.md / pointer | AO, IX+REC |
| R188 | Layout, primitives, glossary, stack, corpus roots, commands | T10 | `P#identity`, `P#stack`, `P#layout`, `P#primitives`, `P#glossary`, `C#project-overview` | none | nested CLAUDE.md per directory + pointer | AO |
| R189 | `rmx` query DSL, PQL, linkage taxonomy, noise, `--explain`, freshness contract, repair commands | T10 | `RC` | Read under `.refmatrix/` | nested `.refmatrix/CLAUDE.md` (exists, conditional) | F |
| R190 | Grep learning is off while `~/.refmatrix/learn.off` exists; read lookups append telemetry only | T10 | `P#corpus`, `f:subagents_read_only_on_live_stores` | none | pointer | AO, IX+REC |
| R191 | Hook output cap: 10,000 UTF-16 units of trimmed stdout per hook command; over it a 2,000-unit preview | T10 | `r:hook_output_10k_cap`, `r:hook_output_cap_measured` | Edit hook producers | folded into R090's paths: rule | IX+REC |
| R192 | Hook 'command not found' = launcher PATH; read `hook_non_blocking_error` records in the transcript | T10 | `f:hook_exit_127_check_launcher_path` | none | pointer | IX+REC |
| R193 | Claude Code Bash uses MacPorts bash 5.3 (`CLAUDE_CODE_SHELL`) since 2026-11-14 | T10 | `r:claude_code_shell_bash53` | none | pointer | IX+REC |
| R194 | Mac mini host facts (`ssh mini`, M1 16 GB, macOS 15.3.2) and isolated lanes `rmxtest1..3` on both machines | T10 | `r:mac_mini_test_host`, `r:isolated_test_lanes` | Bash `scripts/lane-*.sh` | skill `lane-verify` | IX+REC |
| R195 | GitHub topology: dev origin = GitHub (pins `id_rsa_4096`), deploy origin = dev repo | T10 | `r:github_remote` | Bash `git push` | folded into R010's deny reason | IX+REC |
| R196 | Editable venv runs current `src/` while dist-info version lags | T10 | `r:editable_venv_distinfo_lag` | none | skill `release-deploy` | IX+REC |
| R197 | `eval/` on `sys.path` shadows HuggingFace `datasets` | T10 | `r:eval_datasets_shadow` | Edit/Run under `eval/**` | nested `eval/CLAUDE.md` | IX+REC |
| R198 | `~/python_libraries` mixed-ABI tree: broken imports are usually cp311 wheels under 3.14 | T10 | `r:mixed_abi_python_tree`, `P#stack` | none | pointer | AO, IX+REC |
| R199 | One store, several disjoint trees via repeated `--watch-root` | T10 | `r:multi_watch_root_one_store` | none | recall (fine as is) | IX+REC |
| R200 | Claude Code `claude/channel` MCP push protocol | T10 | `r:claude_channel_mcp_push` | none | recall (fine as is) | IX+REC |
| R201 | Claude Code mod probe facts (subagents, `-p`, `/clear`, fetch, name collisions) | T10 | `r:claude_code_mod_probe_facts` | none | recall (fine as is) | IX+REC |
| R202 | Driving a second Claude in `screen`; long `stuff` pastes drop — write a file and stuff a pointer | T10 | `r:screen_pair_collab`, `r:screen_stuff_long_paste` | Bash `screen -X stuff` | PreToolUse inject (allow) | IX+REC |
| R203 | Settings-hygiene utilities live in `~/claude_tools/utilities/` | T10 | `r:utilities_dir` | none | recall (fine as is) | IX+REC |
| R204 | Templates for task specs, plans, explorations, handoffs live in `workflow/templates/` | T10 | `PW#templates`, `C#planning-exploration-templates` | Write `workflow/plans/**` | paths: rule `workflow/plans/**` | AO, F |
| R205 | Navigation table: prior work, code, architecture, decisions, gaps, plans, audit debt → first file to consult | T10 | `C#navigation-lookup`, `a:general-purpose` | none | always-on pointer | AO, AG |

## Totals {#totals}

### Rules per type {#totals-type}

| Type | Rules | Already delivered by a hook / auto-mode / guard |
|---|---|---|
| T1 | 41 | 8 |
| T2 | 43 | 11 |
| T3 | 41 | 1 |
| T4 | 13 | 1 |
| T5 | 4 | 3 |
| T6 | 2 | 1 |
| T7 | 12 | 1 |
| T8 | 26 | 0 |
| T9 | 1 | 1 |
| T10 | 22 | 1 |
| all | 205 | 28 |

A "delivered" count includes partial delivery (R047, R097, R099, R100, R166) and test guards that fire only when the guard file is in the run; enforcement that is switched off today (`enforce-rmx-grep.sh`, `grep-rewrite-guard.sh` while `learn.off` exists) does not count. {#totals-type-note}

### Stated in two or more places {#totals-multi}

**105** of 205 rules are stated in 2+ files: R001, R002, R003, R004, R005, R006, R007, R008, R009, R010, R011, R012, R016, R019, R022, R026, R029, R030, R032, R034, R037, R038, R039, R047, R048, R049, R051, R052, R053, R054, R055, R056, R057, R059, R060, R062, R064, R065, R067, R068, R071, R072, R073, R074, R075, R076, R077, R078, R079, R080, R081, R087, R088, R090, R091, R094, R095, R097, R098, R101, R107, R108, R113, R114, R115, R116, R117, R118, R119, R120, R121, R122, R123, R124, R128, R135, R136, R137, R139, R140, R141, R144, R145, R147, R153, R158, R163, R164, R165, R168, R170, R173, R180, R184, R185, R186, R187, R188, R190, R191, R194, R198, R202, R204, R205. {#totals-multi-list}

### Reachable only by recall or model fetch {#totals-recall}

**85** of 205 rules have no always-on text, no agent file and no live hook: they arrive only when a recall surfaces the memory or the model reads the doc. 71 of them show their title in the always-on MEMORY.md index (body by recall); **14** have not even that (fetched docs only): R031, R105, R111, R126, R127, R134, R146, R148, R149, R150, R151, R152, R161, R189. {#totals-recall-body}

Recall/fetch-only, by type: T1 15, T2 10, T3 20, T4 5, T5 1, T7 1, T8 20, T10 13. {#totals-recall-type}

### Always-on bytes per source (`wc -c`, 2026-11-24) {#totals-bytes}

| Source | Bytes |
|---|---|
| `~/.claude/CLAUDE.md` (imports only) | 133 |
| `~/.claude/GMD.md` | 2,052 |
| `~/.claude/MEMORY-RULES.md` | 4,849 |
| `~/claude_tools/CLAUDE.md` (ancestor; claude-mem table, no rules) | 505 |
| `CLAUDE.md` | 15,989 |
| `.claude/PROJECT_PROFILE.md` (`@` import) | 9,599 |
| `.refmatrix/PRIMER.md` (`@` import, generated, no rules) | 7,849 |
| `.claude/rules/bug-registry.md` (`globs:` not `paths:`, so unconditional) | 867 |
| memory `MEMORY.md` index (112 lines, under the 200-line / 25 KB cut) | 20,244 |
| **always-on total** | **62,087** |
| `.refmatrix/CLAUDE.md` (nested; loads when a file under `.refmatrix/` is read, e.g. the post-compaction handoff) | 10,212 |
| `workflow/ORCHESTRATION.md` (fetched) | 7,088 |
| `workflow/PLANNING_WORKFLOW.md` (fetched) | 8,689 |
| `workflow/SELF_AUDIT.md` (fetched) | 4,496 |
| `workflow/PLAN_GOVERNANCE.md` (fetched) | 1,973 |
| `.claude/agents/*.md` (18 files incl. overlays; each loads only for its agent) | 192,366 |
| the 91 `feedback_*` + 18 `reference_*` memory bodies (recall only) | 213,748 |

Not counted: SessionStart / UserPromptSubmit injections (variable per session; `rmx telemetry --context` measures them), the system prompt, skill and agent description listings. The always-on total matches plan-32's "~62 KB". Of it, the MEMORY.md index (the largest block: titles of rules whose bodies are elsewhere) and PRIMER (no rules) are 28,093 B, 45% of the total, and state no rule in full. {#totals-bytes-note}

## The first build list {#build-list}

rel: evidence-for -> [[plan-32-instruction-architecture#steps]]

The ten rules where moving to the target mechanism removes the most risk: each was re-derived,
broken or contradicted recently, and each is prose-only or only partly enforced today. Order is by
consequence (what a violation costs), then by how often it recurred. {#build-list-lead}

1. **R001 dev `rmx` with a bumped version against a live store → T1 PreToolUse deny.** Match
   `.venv-eval/bin/rmx` or `python -m refmatrix.cli` whose cwd or `REFMATRIX_ROOT` holds a live
   `.refmatrix/`. Stated in five places (CLAUDE.md hard rule, PROJECT_PROFILE, two overlays, the
   handoff's resume list): repetition standing in for enforcement. The consequence is the worst in
   the table (hub handshake restarts the fleet, in-process writes, DuckDB lock crashes). {#b1}
2. **R003 subagents read-only on live stores → T1 PreToolUse deny keyed on `agent_id`.** Every
   tool-hook envelope from a subagent carries `agent_id` (the fact bug-307 rests on). Prose-only in
   three places, and `gmd-curator.md` still instructs the opposite (contradiction C5). {#b2}
3. **R163 release and deploy (folds R036-R039, R045, R196) → T3 skill `release-deploy`, injected
   by PreToolUse on the version edit in `pyproject.toml` and on `git -C ~/refmatrix pull`.**
   plan-32 `#context`: "Today's release re-derived `--force`, `hub relaunch-fleet`, the hub
   restart". Eight sources state parts of it, and two disagree on the hub (C8). {#b3}
4. **R059-R062 lane verify and its guard set → T3 skill `lane-verify`, injected by PreToolUse on
   any `pytest` / `scripts/lane-*.sh`.** Repo-wide guards failed on master after merges whose
   verify sets left them out: bug-284 (`test_docs_generated.py`), bug-292
   (`test_tmp_root_census.py`), bug-296 (`test_wallclock_census.py`, after the T1 item-3 merge);
   `f:verify_set_includes_repo_guards` was written 2026-11-18 for that. The ch-test-engineer
   overlay still names the old `lockf` lane (C2). {#b4}
5. **R136 the brief → T3 skill `brief`, injected by PreToolUse(Agent).** plan-32 `#context` names
   "the brief shape" as re-derived at the release; `f:never_search_from_root` records a
   subagent's `find /` hanging 1 h 20 m because its brief did not forbid it. The hard rules a brief
   must carry (R003, R021, R061) are themselves prose-only. {#b5}
6. **R113 POP in the same commit → T4 commit-msg / pre-commit check.** A commit that merges,
   bumps the version or flips a plan `status` must stage `workflow/plan-of-plans.md`.
   `f:triage_from_decisions_not_file_status` (a 3.7 'in-progress' that had merged) and
   `f:ldq_enter_pop_first` ("rulings ... written straight into review docs and specs were how the
   POP fell behind") are both drift this check catches. {#b6}
7. **R097 / R098 GMD lint before commit → T4 pre-commit running `./scripts/lint-gmd.sh` when
   `*.md` is staged.** `f:repo_gate_before_persisting_reports`: four red commits landed on master
   on 2026-11-13, the fourth minutes after that memory was written. Today only memory-dir writes
   are linted, in warn mode. {#b7}
8. **R158 + R162 registry row for a fix, "fixed" only when reachable from master → T4
   commit-msg + pre-commit on `workflow/bug_registry.md`.** `f:verify_fix_reachable_from_master`:
   bug-058 was recorded fixed while committed on an unmerged branch. The row obligation is the one
   always-on rule file (`bug-registry.md`, unconditional), and it contradicts
   `ORCHESTRATION#roles-agents` for agents (C6). {#b8}
9. **R140 / R141 the ch-bsd pass → T3 skill `bsd-pass`, preloaded by ch-bsd's `skills:`.** The
   round and severity rules are stated in seven sources;
   [[refmatrix/ch-bsd-assessment-2026-11-23#f6]] counts ten definition copies with ten checksums,
   F8 found SKETCHY under-rated, and `f:proportionate_process` still gives SKETCHY a second round
   that L213 removed (C9). One preloaded skill is the single copy. {#b9}
10. **R064-R066 the mutation loop → T3 skill `mutation-loop` (PreToolUse inject on a mutation
    command) plus R065 as a T1 deny on a dirty `src/`.** Re-learned four times, four memories:
    2026-09-16 a shadowing `.pyc` (`f:clear_pycache_after_mutation`), 2026-09-20 a hang and a
    chained restore (`f:mutation_must_fail_not_hang`), 2026-10-01 uncommitted GREEN destroyed by
    `git checkout` (`f:commit_before_mutation_revert`), 2026-10-15 a tests-only pre-mutation
    commit (bug-115, `f:mutation_commit_must_hold_the_fix`). {#b10}

Next in value, not in the ten: R134 (the lead writes no `src/`; broken 2026-11-15 per
`f:keep_red_and_green_separate_under_urgency`), R029 / R030 (`git add -A` sweeps agents' edits),
R037 (`rmx hub start`), and the T2 `tests/**` rule (R049-R056: moving the 4 KB test discipline out
of always-on CLAUDE.md into a path rule that loads in every agent that touches a test). {#build-next}

## Contradictions between sources {#contradictions}

Each quotes both texts with their locations. Where one side is newer and says it wins, that is
noted; the older text is still loaded or fetched as written. {#contradictions-lead}

1. **Docker.** `.claude/agents/general-purpose.md#root`: "Tests run **in the Docker dev container
   only** — never on the host." Also `ch-code-reviewer.md`: "All backend tests run in Docker —
   never on host OS". Against `CLAUDE.md#development-commands`: "There is no container." And
   `ch-test-engineer.md#docker-only-execution` contradicts itself: "**ALL backend tests run in
   Docker.** Never use the host Python, host venv" then "No container. Python:
   `.venv-eval/bin/python` (host venv)." {#c1}
2. **Which lane a verify run uses.** `.claude/agents/ch-test-engineer.local.md` (Environment):
   "Verify with the task's tests plus every importer of a changed module, through
   `/usr/bin/lockf /private/tmp/claude-501/rmx-test-lane.lock`." Against
   `CLAUDE.md#test-discipline` rule 9: "The old single lane (`/usr/bin/lockf ...`) is only for
   tests that need the dev tree's live `.refmatrix/` and for the release gate's full suite." {#c2}
3. **ch-bsd on specs.** `CLAUDE.md#agent-skill-workflow`: "The default planning path is the one in
   `workflow/ORCHESTRATION.md` `#planning` (ch-architect on Fable → ch-bsd spec rounds → lead
   rulings → user decisions → merge)." and `PLANNING_WORKFLOW#default-planning-path`: "→ ch-bsd
   spec review r1 → lead ruling `L<n>` → revision on Fable → confirm-lite to MEH-only GO".
   Against `ORCHESTRATION#planning` step 3: "**One architect read**, no ch-bsd round on a spec."
   (ORCHESTRATION says it wins; the CLAUDE.md sentence misdescribes the section it cites.) {#c3}
4. **When task specs are written.** `PLAN_GOVERNANCE#lifecycle-gates`: "**Complete-Plan Gate:** Do
   not write production code for a plan until every task in it is fully specified (i.e. `status:
   approved`)." and `CLAUDE.md#plans-pre-written`: "`approved` requires every task spec under
   `workflow/plans/<name>-tasks/`. Do not write production code for a plan before that gate."
   Against `ORCHESTRATION#planning` step 1: "**Spec just in time:** a task is specced when it is
   next in the queue, not earlier." CLAUDE.md states both (`#task-completion-workflow` item 2:
   "specced just in time"). {#c4}
5. **Subagents writing a live store.** `.claude/PROJECT_PROFILE.md#corpus`: "**Subagents are
   read-only against every live store** (user, 2026-11-14): no `rmx sync`, `ingest`, `ingest-gmd`,
   `reingest` ..." Against `.claude/agents/gmd-curator.md` (rmx playbook, "Async"): "**All ingest,
   sync, and primer-rebuild operations MUST be backgrounded.**" followed by
   `nohup rmx ingest-gmd docs/ ...` and `nohup rmx ingest . ...`. PROJECT_PROFILE lists
   gmd-curator among the agents given read-only tools. {#c5}
6. **Agents and registry rows.** `.claude/rules/bug-registry.md` (no `paths:`, so loaded in every
   session and subagent): "AFTER fixing any bug, failed test/build/lint, or user-reported problem:
   append a row to the registry". Against `ORCHESTRATION#roles-agents`: "Agents allocate no
   registry ids." {#c6}
7. **Who bumps the version.** `.claude/agents/ch-implementer.local.md`: "Version bump in
   `pyproject.toml` AND `src/refmatrix/__init__.py` for every shipped change." Against
   `ORCHESTRATION#release` step 1: "**Release commit** on `master` bumps `pyproject.toml` and
   `src/refmatrix/__init__.py`." (a lead step at release; a bumped version on a branch is also what
   R001 guards against). {#c7}
8. **Hub after a deploy.** `.claude/PROJECT_PROFILE.md#commands`: "`rmx daemon restart --relaunch`
   (verifies the new pid + version) → hub self-restarts on version mismatch." and
   `f:deploy_tree_is_the_runtime`: "The hub self-restarts on the version handshake". Against
   `f:hub_restart_via_launchctl`: "its version handshake did not restart it within 90 s" and
   `ORCHESTRATION#release` step 3: "`rmx hub relaunch-fleet` (a stale hub: `rmx hub stop` + one
   `launchctl kickstart`)". {#c8}
9. **Does SKETCHY earn a review round.** `f:proportionate_process`: "one review pass unless it
   finds BULLSHIT or SKETCHY". Against `ORCHESTRATION#task` step 5 (L213): "SKETCHY → the
   implementer folds and the lead checks the diff; no new round." and
   `CLAUDE.md#task-completion-workflow`: "only BULLSHIT earns a second round". {#c9}
10. **Where Q ids live and how they count.** `f:track_questions_by_id`: "a simple counter starting
    at 1 each session" ... "(refmatrix: `workflow/open-questions.md`, grouped by session, with a
    `Next id` line)". Against `f:ldq_enter_pop_first`: "No separate ledger file holds live rows:
    ... Q1-Q22 (`open-questions`) are history." The POP continues one counter across sessions
    (Q54 on 2026-11-24), and `workflow/open-questions.md` does not exist at `c7550ad5`. {#c10}
11. **Plan decision labels.** `f:plan_decisions_are_questions`: "each one gets a `Q<n>` row in
    `workflow/open-questions.md` BEFORE the reply that asks it". Against
    `f:plan_d_labels_are_valid_ids` (which supersedes it): "It needs no `Q<n>` row". And
    `ORCHESTRATION#ledgers`: "A `Q<n>` for every question to the user". Both memories are in the
    always-on index. {#c11}
12. **Channel for reasoning notes.** `.refmatrix/CLAUDE.md` (Capture your reasoning): `rmx focus
    note "chose X over Y because Z; risk is W"` (a Bash call). Against `f:mcp_first_agent_stm`:
    "use the refmatrix **MCP tools** — `rmx_focus_note` ... NOT a Bash `rmx ...` shell-out" and
    `CLAUDE.md#write-decisions` (the MCP tool). {#c12}
13. **Masking on memory-path hooks.** `CLAUDE.md#no-silent-failures`: "Anything between a memory
    file and the store — bridges, hooks, save-state, recall — surfaces its failure: no
    `2>/dev/null`, `|| true`". Against `f:no_silent_failures`: "For file-sync hooks (rmx sync /
    curator queue): masking IS fine". The installed `.claude/settings.json` runs the STM capture
    hooks as `rmx focus hook --event input 2>/dev/null || true` (also `tool`, `tool-pre`, `say`).
    {#c13}
14. **Suite size.** `CLAUDE.md#development-commands`: "# Full suite (~13 min)";
    `CLAUDE.md#test-discipline`: "The suite is ~4,100 tests and 60 min";
    `PROJECT_PROFILE#layout`: "(pytest, ~1380 tests, ~13 min full run)";
    `ch-test-engineer.local.md`: "Full suite ~60 min / ~5,000 tests" (bug-299 collected 5,370).
    {#c14}
15. **Report files from subagents.** `.claude/agents/general-purpose.md#root`: "**Reviews persist
    to disk** — ... write the full report to `workflow/review-output/<plan>-<phase>-<reviewer>.md`
    BEFORE returning a chat summary." Against `r:subagent_reports_returned_as_text`: a subagent's
    report Write "can be refused ... the lead persists ch-bsd reports". {#c15}
16. **Docstrings.** `.claude/agents/ch-code-reviewer.md`: "Docstrings on public APIs only; no
    redundant comments on obvious code". Against `CLAUDE.md#development-guidelines`: "Docstrings
    say WHY and name the incident/date that motivated the code". {#c16}
17. **The grep escape.** `f:rmxgrep_plain_escape`: "Byte-exact needs ... → `RMXGREP_MODE=plain
    rmxgrep`". Against `f:rmxgrep_no_plain_escape` (supersedes it): "NOT `env RMXGREP_MODE=…`".
    `~/.claude/settings.json` `env` still sets `"RMXGREP_MODE": "plain"` (harmless since the
    shim treats any value but `rich` as auto, but it reads as the sanctioned escape). {#c17}
18. **Hook output budget.** `f:injection_presentation_rules`: "each hook command's output under a
    HARD limit of 9,500 B". Against `r:hook_output_cap_measured`: "budget every generated hook
    COMMAND ... at 0.9 × 10,000 = 9,000 B". {#c18}
19. **Who mutates.** `ch-test-engineer.local.md` (RED discipline): "Mutation check before calling
    a test done: break the code path it claims to cover and confirm the test fails." Against
    `ORCHESTRATION#task`: mutations come after GREEN, "on the `src/` change only", and
    `#task-small`: "No mutations". {#c19}

### Superseded memories still in the always-on index {#superseded-indexed}

The index line of each is always-on and states the old rule: `f:rmx_binary_is_deploy` (superseded
by `f:deploy_tree_is_the_runtime`), `f:rmxgrep_plain_escape` (by `f:rmxgrep_no_plain_escape`),
`f:bsd_iterate_before_surfacing` (by `f:lean_process_reset`; its index line says "historical"),
`f:operational_content_not_in_graph` (by `f:operational_content_same_partition_not_skewing`),
`f:plan_decisions_are_questions` (by `f:plan_d_labels_are_valid_ids`). {#superseded-list}

### Stated rule against installed enforcement {#rule-vs-installed}

- `enforce-test-to-file.sh` allows `| tail`, `| head`, `| wc` with no file (R047), and its
  message suggests `/test-output/`, not `workflow/review-output/`. {#riv-tee}
- `.claude/rules/bug-registry.md` uses `globs: **/*`, which Claude Code does not read as `paths:`,
  so the rule is always-on (plan-32 notes the same). {#riv-globs}
- The caveman mode tracker injects on every UserPromptSubmit; T9 says one SessionStart style,
  never per prompt (R183). {#riv-caveman}
- The grep redirect (`enforce-rmx-grep.sh`) and rewrite (`grep-rewrite-guard.sh`) both exit early
  while `~/.refmatrix/learn.off` exists (since 2026-10-15), so R185 / R186 are prose-only today;
  PROJECT_PROFILE `#corpus` says so. {#riv-grep}
- `.claude/settings.local.json` `permissions.allow` keeps
  `cp /Users/tholley/claude_tools/refmatrix/src/refmatrix/store.py ~/refmatrix/src/refmatrix/store.py`
  (and `cli.py`): a standing grant for exactly what R007 forbids. {#riv-cp-deploy}

## Not claimed {#not-claimed}

- **Role prose and template rules that do not apply here** were not enumerated: ch-bsd checks
  1-11 and its ledger phases, ch-alignment's pseudocode duties, the security, performance and
  work-summary checklists, and template rules for UI tiers (Playwright, JSDOM), real-auth and
  contract tests, migrations, Docker secrets, JSON-only config and pagination. {#nc-role}
- **Not read:** `.claude/commands/*.md` (18 commands), skills, the system prompt and harness
  rules, `project_*` / `savestate_*` / `impressions/` memories and the 182 folded project
  memories (the brief excludes them), and `subagent-checkpoint.sh` beyond its header (it states
  no rule to the model). {#nc-unread}
- **Memory bodies** were read through a digest (lead paragraph, How-to-apply, `rel:` lines) and in
  full where a quote is used; a rule stated only in a memory's Why paragraph may be merged into a
  neighbour or missed. {#nc-digest}
- **POP L-rows and the bug registry** were read for evidence of recent breaks (L180-L214,
  bug-250..317), not as rule sources: rulings that live only in an L-row are not rows here.
  {#nc-ledgers}
- **"Today" is derived** from where a rule is stated; it does not measure whether a recall
  actually surfaces a given memory, nor whether the CLI enforces the p20-0 auto-mode rules
  (`compile_guardrails.py` itself calls efficacy "a known limitation"). {#nc-today}
- **Borderline types** (judgment calls): R006 (T3, could be T1 ask), R031 (T3), R118 / R121 /
  R122 (T3 by tool trigger), R159 (T4 by counter), R134 (T1 though it is a role rule), R129 /
  R130 (kept as T8 rows though they may be retired). {#nc-borderline}
- **Stale facts not verified:** whether R070's named failing test still fails, and the exact
  agent list R154 says carries `effort: high` (read from frontmatter: ch-implementer,
  ch-test-engineer, ch-bsd, ch-architect, ch-alignment). {#nc-stale}
