---
gmd: "0.1"
id: bsd-plan2-hooks-reproducible-03f46b8
title: "plan-2-hooks-reproducible: the installed file equals the render, but --enforce is a dead flag, --force still deletes foreign hooks, and the docs were dropped"
tags: [bsd, findings, plan-2, hooks]
severity: BULLSHIT
plan: plan-2-hooks-reproducible
task: task-2.1-plan-2-hooks-reproducible, task-2.2-plan-2-hooks-reproducible, task-2.3-plan-2-hooks-reproducible
metadata:
  node_type: bsd-report
  commit_range: cabce24..03f46b8
---

# ch-bsd findings — plan-2-hooks-reproducible (cabce24..03f46b8) {#root}

**Commits:** ea8a4fe (0.67.0 code, tasks 2.1/2.2), eca77ca (merge), 03f46b8 (task 2.3 migration of this repo)
**Date:** 2026-09-14
**Author:** Todd Holley / Fable 5.1 / orchestrator
**Files changed:** 17 (+853/-74)

rel: evidence-for -> [[plan-2-hooks-reproducible]]
rel: amends -> [[bsd-0661-e2e-memory-bridge]]

## What is verified real {#verified}

- `hooks.render_managed(REPO, flags)` rendered in `.venv-eval` equals the committed `.claude/settings.json` hook set: ordered-equal, set-equal, zero unmanaged entries, `statusLine` preserved. `rmx install-hooks --check` (deployed 0.67.0, `~/refmatrix/src`) exits 0. `.claude/settings.local.json` holds no hooks. This closes the reproducibility half of #bs-4.
- Loudness contract holds by render, not by test: every generated command containing `memory recall`, `ingest-gmd`, `save-state`, or `focus summarize` has no `2>/dev/null`, `>/dev/null`, or `|| true`. The PreCompact checkpoint is `rmx save-state --no-promote --no-sync -m "auto: pre-compact checkpoint"` with nothing swallowed. This closes the silenced-bridge half of #bs-4.
- The three opt-out knobs from #sk-5 (`memory_hooks`, `primer`, `scan_prompt`) are now reachable from the CLI and recorded in `.claude/rmx-hooks.json`; `test_install_hooks_cli_flags_reach_the_block` proves two of them land in the file. #sk-5 closed.
- `ingest-gmd --detach` with no daemon raises before the in-process fallback (`cli.py`, the `(detach or progress) and not ping` guard); `ingest_gmd_start` is registered in `OPS`.
- PreCompact cost claim holds. Measured read-only on the live store: `focus context --top 15` 0.14 s, `focus summarize` 0.13 s, `memory recall --recent --since 1h` 0.17 s; pre-bridge `save-state` history in cli.log is 181-259 ms, and `--no-sync` skips the only 30 s step (`handoff.py:396-403`).
- `~/.claude/hooks/rmxgrep-rewrite.py` refresh lost nothing: the live file equals the deploy-tree render byte for byte; the only difference from the dev-tree render is the baked wrapper path (`~/refmatrix/bin` vs `~/claude_tools/refmatrix/bin`, `search_hooks.py` resolves it at install time). The template has one history entry (69a1b37) so there is no earlier render to have lost.
- Enforcement commands are byte-identical to what this repo's pre-migration `.claude/settings.json` carried (compared against `git show cabce24:.claude/settings.json`). The cat-herder template itself is not in this repo, so drift between it and `_add_enforce_entries` is unguarded (see #m-7).
- TDD record is genuine: RED log shows the 16 new tests failing on missing symbols/behavior; GREEN 74 passed 1 skipped; re-run today (`workflow/review-output/pytest-bsd-plan2-03f46b8.log`) 41 passed including the repo-sync guard. No test mocks the function it claims to test; the two monkeypatches (`cli._root`, `daemon.ping`) redirect to a tmp project and a daemon-absent branch. Mutation reasoning: `test_check_detects_hand_edit` and `test_check_reports_missing_generated_entry` fail if `check()` returns True unconditionally; `test_installed_hooks_match_generated` fails on any edit to the committed file.

## Findings {#findings}

### BULLSHIT: `--enforce` (forced on) is a dead flag — the CLI accepts it, the generator ignores it {#b-1}

**File:** `src/refmatrix/hooks.py:363-371` (`_add_enforce_entries.want`), `src/refmatrix/cli.py:7476-7479` (`--enforce/--no-enforce`), `src/refmatrix/hooks.py:930-937` (`_install_claude_hooks` always passes `project_root=project_root`)
**What:** Plan step 1, task 2.1 files list ("emitted when `<project>/.claude/hooks/<script>` exists (auto) or forced"), the implementation summary ("or forced"), and the docstring all say `enforce=True` forces the four entries. The `want()` helper only honours `enforce is True` when `rel is None`, and `rel` is never None because every production caller passes `project_root`. With `enforce=True` and no scripts on disk the render is identical to `enforce=None`.
**Why it's bullshit:** A CLI option that changes nothing is dead code with a help string. It is also self-concealing: `record_flags` writes `"enforce": true`, `check()` re-renders with the same dead branch, so `--check` stays green while the project never gets the hooks the operator asked for. The only test of forced mode (`test_enforce_entries_follow_scripts_on_disk`) asserts `enforce=False` drops entries; nothing asserts `enforce=True` adds them.
**Evidence:** `_claude_hook_block(tmp/.refmatrix, project_root=tmp, enforce=True)` with an empty `.claude/` renders zero enforcement entries; the same call with `project_root=None` renders four. `rmx install-hooks --enforce --apply` therefore equals `rmx install-hooks --apply`.
**Fix:** In `want()`, return True whenever `enforce is True` (before the exists check), and add the missing assertion to the test. Effort: two lines.
**Pattern match:** NO (first sighting of an accepted-but-ignored flag; see [[#impressions]]).

rel: contradicts -> [[task-2.1-plan-2-hooks-reproducible#files]]

### BULLSHIT: `--force` still deletes hand-authored hooks — the prefix signature `.claude/hooks/enforce-` eats any user script with that name shape {#b-2}

**File:** `src/refmatrix/hooks.py:1001-1011` (`_RMX_HOOK_SIGNATURES`), `src/refmatrix/hooks.py:1017-1030` (`_strip_rmx_hooks`), `src/refmatrix/hooks.py:964-975` (legacy strip applies the same signatures to `settings.local.json`)
**What:** Task 2.2 requirement: "Hand-authored non-rmx hooks in settings.json survive `--force`." The new signature tuple matches the substring `.claude/hooks/enforce-`, not the two script names the generator emits. Any project hook whose script is named `enforce-<anything>.sh` (the cat-herder naming convention for exactly this kind of hook) is classified rmx-managed, stripped on `--force`, and not re-added. The same strip runs unconditionally against `settings.local.json` on every apply.
**Why it's bullshit:** This is #bs-4's failure mode ("a forced reinstall would have deleted them") re-created one layer down. The covering test (`test_force_keeps_foreign_hooks_and_other_keys`) uses `echo mine`, which shares no prefix with anything, so the requirement is proven only for hooks that were never at risk.
**Evidence:** Probe: seed `settings.json` with `PreToolUse/Bash → $CLAUDE_PROJECT_DIR/.claude/hooks/enforce-my-own-policy.sh`, run `install(..., apply=True, force=True)`, the entry is gone (`"enforce-my-own-policy" in settings.read_text()` → False). `check()` then reports nothing because the entry was never managed.
**Fix:** Replace the prefix with the exact names `.claude/hooks/enforce-test-to-file.sh` and `.claude/hooks/enforce-rmx-grep.sh`; extend the foreign-hook test with a same-prefix script. Effort: three lines.
**Pattern match:** YES — [[bsd-0661-e2e-memory-bridge#bs-4]] (forced reinstall deleting hooks).

rel: contradicts -> [[task-2.2-plan-2-hooks-reproducible#requirements]]

### BULLSHIT: task 2.3's doc deliverables were dropped without a word; README and INTEGRATION now name the wrong file {#b-3}

**File:** `README.md:248` ("`.claude/settings.local.json` | PostToolUse enqueue · Stop flush · SessionStart primer · UserPromptSubmit scan-prompt"), `docs/INTEGRATION.md:95` ("`rmx install-hooks` writes a JSON block into `.claude/settings.local.json`"), `docs/hooks/intuition-style-hooks.md:12-14,147`
**What:** Task 2.3 "Files to Create / Modify" lists "README hooks table lists every generated event; `docs/hooks/intuition-style-hooks.md` points at install-hooks as the generator." The diffstat touches neither, `docs/INTEGRATION.md` is untouched, and the implementation summary lists no omission. The README table names the file this release stopped writing and lists four of the nine generated events.
**Why it's bullshit:** Scope shrunk silently (rule 10). The docs are the onboarding surface for other projects; after 0.67.0 they instruct a reader to look in a file that a fresh install leaves empty of hooks. The plan title is "install-hooks produces the whole production config" and the README still describes the 0.65 shape.
**Evidence:** `git diff cabce24..03f46b8 --stat` has no README/docs entries; `grep -rn settings.local.json README.md docs/` returns six live references.
**Fix:** Update the README table to the nine events (PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop, SessionStart×3 matchers, PreCompact) and the target file; make `INTEGRATION.md:95` and the intuition-style doc say `settings.json` and point at `install-hooks --check`. Effort: 20 lines of prose.
**Pattern match:** YES — [[bsd-plan1-deploy-runtime-cabce24#m-6]] (summary overstates what shipped) and the [[bsd-impressions#imp-summary-claims-bookkeeping]] impression.

rel: contradicts -> [[task-2.3-plan-2-hooks-reproducible#files]]

### SKETCHY: `check()` proves less than the plan says — duplicates, unmarked rmx commands, extra keys, and foreign hooks are all invisible {#s-4}

**File:** `src/refmatrix/hooks.py:466-474` (`_managed_entries` returns a set of `(event, matcher, command)`), `src/refmatrix/hooks.py:499-525` (`check`)
**What:** Plan Q3 decided "settings.json has ONE author"; the docstring at `hooks.py:79-81` says "a hook that exists only in a settings file is a template bug". `check()` compares sets of managed triples, so it cannot see: (a) a duplicated rmx block (fires twice, passes); (b) a hand-added `rmx …` command with no marker and none of the eleven signatures (e.g. `rmx context foo`, passes); (c) drift in any key other than `command` (`timeout` 5000 → 1, passes); (d) any non-rmx hook at all (not even listed).
**Why it's sketchy:** (a) and (c) are silent runtime differences the check is advertised to catch. (b) and (d) may be intentional (foreign hooks are a documented survivor of `--force`), but then the docstring and Q3 overstate the guarantee. Pick one: either report unmanaged entries as informational lines so the operator sees the second author, or compare full ordered entry lists for managed events.
**Evidence:** Probe in a tmp project after `--apply --force`: duplicate Stop block → `check` True; appended `rmx context foo --degree 2` → True; `timeout` edited → True.
**Fix:** Compare `(event, matcher, json.dumps(entry, sort_keys=True))` as a multiset; emit `? event/matcher: cmd` lines for unmanaged hooks (non-failing) or gate them behind `--strict`. Update the docstring to whatever is chosen.
**Pattern match:** YES — [[bsd-impressions#imp-guard-vs-incident-state]] (guard built for the fixed state).

### SKETCHY: plan marked `completed` before this gate ran; task specs still `pending` {#s-5}

**File:** `workflow/plans/plan-2-hooks-reproducible.md:7` (`status: completed`, flipped in 03f46b8), `workflow/plan-of-plans.md:22`, `workflow/plans/plan-2-hooks-reproducible-tasks/task-2.{1,2,3}-*.md:8` (`status: pending`)
**What:** The plan's own execution contract (`#execution`) is "then `@ch-bsd` over the plan's commit range — remedy and re-review until the verdict is CLEAN; then `metadata.status` → `completed`". The flip is in the same commit that requests the review. All three task specs remain `pending` while their plan is `completed`.
**Why it's sketchy:** Second occurrence in two plans ([[bsd-plan1-deploy-runtime-cabce24#m-9]] was MEH); escalated per the ledger rule. The graph now says a completed plan has zero completed tasks.
**Fix:** Flip the plan back to `in-review` (or equivalent) until #b-1..#b-3 close; set task statuses when tasks merge.
**Pattern match:** YES — 2nd sighting.

rel: contradicts -> [[plan-2-hooks-reproducible#execution]]

### SKETCHY: the Stop `focus summarize --promote` hook is new behaviour the requirement said not to add, and its no-daemon branch opens the store directly {#s-6}

**File:** `src/refmatrix/hooks.py:196-201` (Stop entry), `src/refmatrix/cli.py:1101-1142` (`focus_summarize`; `else: eid = _store().add_memory(**args)` at the no-daemon branch)
**What:** Task 2.1 requirement 1: "Rendering with defaults equals the union of what settings.local.json + settings.json run in this repo today (minus the swallowed redirections)." The four hand-authored hooks in #bs-4 were composite-every, PreCompact promote, PreCompact checkpoint, resume focus-context. A Stop-time promote was not among them; it is an addition justified only by a code comment citing a memory ([[feedback_save_state_includes_promote]]). It now runs in the foreground at every turn end of every session.
**Why it's sketchy:** Cost is fine (0.13 s measured; `add_memory` upserts by name so no row growth). The concern is the branch it schedules: with the daemon down, `focus_summarize` calls `_store().add_memory` on the active slot from a CLI process — the project constraint says store access routes through the daemon — and any failure is a red hook error on every turn. The plan did not decide this; write it down or drop the entry to `stop_promote=False` by default.
**Evidence:** Prior report's installed-only list (four entries, no Stop promote); `cli.py` no-daemon fallback.
**Fix:** Either record the decision in the plan's Decisions Log (and make the no-daemon branch a loud refusal like `ingest-gmd --detach` now does), or default `stop_promote` to False.
**Pattern match:** YES — [[bsd-impressions#imp-two-paths]] (daemon vs direct store).

### SKETCHY: the new `--detach` guard calls a busy daemon "no daemon" and tells the operator to start one; the SessionStart catch-up is skipped exactly then {#s-11}

**File:** `src/refmatrix/cli.py:8073-8079` (`if (detach or progress) and not daemon_mod.ping(root): raise ClickException("no daemon running … `rmx daemon start`")`), `src/refmatrix/daemon.py` (`ping`: 0.5 s probe, 2 retries — its own docstring says a probe "cannot tell a DEAD daemon from a BUSY one")
**What:** Observed live during this audit at ~20:02: `rmx daemon status` reported `busy pid=53244 (alive, not answering yet)`; the exact SessionStart hook command `rmx ingest-gmd --as-memory --detach '<memdir>'` printed `Error: no daemon running for … (rmx daemon start)` and did nothing. Re-run after the watchdog kickstart (pid 60822): `ingest job 6312242d65d5 started (209 files)`, all content-hash skips, ~65 s in the daemon's background pool.
**Why it's sketchy:** The guard is the right idea (no 25 s foreground fallback) and it is loud, but its message is wrong in the busy case and the plan's Q1 decision ("the SessionStart catch-up bridge … cover[s] the store") is false whenever the daemon is mid-write at session start — the common case right after a deploy or a large ingest. Nothing retries; the hook line says to start a daemon that launchd is already supervising.
**Evidence:** cli.log / this audit's shell transcript; `rmx daemon status` output before and after 20:03:41 (`hub.log:1311 watchdog kickstarted`).
**Fix:** Distinguish socket-absent from socket-busy in the message ("daemon busy — retry or run without --detach"), and either retry the `ingest_gmd_start` RPC with a longer timeout on the hook path or queue the job through the hub. Effort: small; the state is already visible to `daemon status`.
**Pattern match:** YES — [[bsd-impressions#imp-two-paths]] (ping-false is also the switch that sends `memory sync-disk` to a direct `Store()` open, which failed on 53244's WAL lock at the same moment; not this diff, plan 4/5 territory).

### MEH: flags are recorded only through the `claude` path, so `--check` cannot describe what `--no-claude` installs {#m-7}

**File:** `src/refmatrix/hooks.py:442-446` (`if apply and claude and scope == "project": record_flags`)
**What:** `install-hooks --no-claude --apply` (git hooks, agent-env, search hooks) writes files but never records flags; `--check` then answers "no rmx-hooks.json — run --apply". The `search` and `agent_env` state (three scripts under `~/.claude/hooks`, the `env` block in `settings.local.json`) is outside `check()` entirely, so a dev-venv apply that re-bakes the rewriter's wrapper path to the dev tree passes `--check`. `rmx-hooks.json` records `version` but nothing reads it. `_install_agent_env` writing `settings.local.json` is correct: `BASH_ENV` is a `$HOME` path, per-machine by nature.
**Fix:** Record flags whenever `apply and scope == project`; have `check()` also compare `render_scripts()` against the on-disk scripts (that is the second author of production behaviour).

### MEH: mock registry catch-all is now stale by two sites; cat-herder template drift unguarded {#m-8}

**File:** `workflow/test_mock_registry.md:27` ("monkeypatch.setattr sites (184, unregistered)"), `tests/test_hooks_reproducible.py:206,221,239-240`
**What:** Three new `monkeypatch.setattr` sites (`cli._root` ×2, `daemon.ping`) land under the parking-lot row, whose count was not updated. Neither mocks the SUT. Separately, `_add_enforce_entries` claims byte-identity with "the template's commands"; the template lives outside this repo (no match under `src/refmatrix/templates/`), so nothing in CI would notice the two diverging.
**Fix:** Bump the count or register the two sites; vendor the four enforcement command strings as a fixture the template repo can import, or add a comment naming the template file they mirror.

### MEH: none of the four new hook commands has executed from a hook yet {#m-9}

**File:** `.refmatrix/cli.log` (135 rows after 19:49:49, all `focus hook`, `grep`, `sync`, `install-hooks --check`, `memory sync-disk`; zero `source=hook` rows for `focus summarize --promote`, `save-state --no-sync`, `focus context --top 15`, or `ingest-gmd --detach`)
**What:** The running Claude Code session still executes the configuration it loaded at startup; the summary's follow-up says a restart is needed. The detached bridge's outcome (skips, failures) surfaces only in `rmxd.log`; the hook is loud about launch, not result (plan-5 task 5.2 covers overlap, not outcome).
**Fix:** After the restart, confirm one `source=hook` row per new command in cli.log and attach it to the plan; consider having `ingest-gmd --detach` print the job id so the next `save-state` can report it.

### MEH: deploy tree is one commit behind {#m-10}

**File:** `~/refmatrix` at `eca77ca`; master at `03f46b8`
**What:** No `src/` difference between the two (verified), so the fleet runs 0.67.0 code identical to master. Noted because plan-1's contract is a fast-forward of master.

## Incident observed during the audit (not this diff) {#incident}

Daemon pid 53244 (started 19:49:43 by the plan-1 relaunch) stopped answering pings by ~20:00 with no log line after its startup banner; `rmx memory sync-disk` (agent-instruction step, a CLI write) fell back to a direct store open and failed on the WAL lock 53244 still held; the hub watchdog kickstarted the daemon at 20:03:41 (pid 60822). No `FatalException` was written to `daemon.stderr.log` for this restart. The memory impression written by this run reached the store on the re-run of the detached bridge, not via `sync-disk`. Owner: plan 4 (daemon resilience) and the sync-disk fallback in plan 5.

## Deferral sweep {#deferrals}

No hard deferrals in the changed files. Soft hits: `hooks.py:130,151` ("best-effort") describe the focus-event plumbing, which the loudness contract explicitly exempts; not correctness gaps. No references to plan 2 remain in `src/`.

## Impressions carried forward {#impressions}

- A flag whose branch is unreachable from every production caller is the same shape as a resolver that returns `[]`: the surface exists, the behaviour does not. Render with the flag forced and diff — reading the option list is not verification. {#imp-dead-flag}

## Verdict {#verdict}

**DIRTY — 11 findings (3 BULLSHIT, 4 SKETCHY, 4 MEH).**

The core of #bs-4 and #sk-5 is closed and verified by rendering, not by reading tests: one generator, the committed file equals its output, the memory-path commands are loud, the opt-outs are reachable. What blocks closure is that the same commit ships a dead `--enforce` flag documented as working (#b-1), a `--force` that still deletes a class of hand-authored hooks (#b-2, the very failure this plan was opened for), and drops the doc deliverables so the README now names the wrong file (#b-3). All three are minutes of work. Plan 2 should not carry `completed` until they land; #s-4 and #s-6 need a written decision, not necessarily code; #s-11 is a message fix plus a retry, and it is the one that will be seen at every session start after a deploy.

rel: contradicts -> [[plan-2-hooks-reproducible#execution]]
rel: evidence-for -> [[feedback_no_silent_failures]]
