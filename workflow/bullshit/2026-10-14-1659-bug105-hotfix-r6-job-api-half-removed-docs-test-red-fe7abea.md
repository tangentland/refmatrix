---
gmd: "0.1"
id: bsd-bug105-hotfix-r6-fe7abea
title: "bug-105 hotfix r6: the fence, the runbook and the remapped counter hold, but removing the job API left test_docs_generated red (ARCHITECTURE.md still lists `rmx daemon job`), and three stale readers remain, one of them the exact 'next async big-op' deferral r5 flagged"
severity: BULLSHIT
plan: bug-105
task: hotfix-fe7abea-r6
tags: [bsd, audit, bug-105, fragments, partition, merge, fence, runbook, mutation]
---

# ch-bsd findings r6: bug-105 r5 remedies (104322b, bf3f781, fe7abea) {#root}

**Commit:** fe7abea, on top of bf3f781 (a test tightened) and 104322b (the r5 remedies plus the r5 report).
- Range under audit: fccca72..fe7abea. Base of the hotfix: a434f51.
- Clone: `/Volumes/littlebig/refmatrix-bug105`, branch `bug-105-fragment-partition`.

**Date:** 2026-10-14 (written 2026-10-14T16:59:08-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed (fccca72..fe7abea):** 7
- Source:
  - cli.py: `rmx daemon job` removed; the fence now uses `require_daemon`; the merge prints `remapped=`; new hint text.
  - daemon.py: `_op_job_status`, its OPS entry, `_jobs` and `_jobs_lock` removed.
  - store.py: `remapped` counter added; `merge_partition` docstring updated.
- Tests:
  - `test_fragment_repair_audit_r4.py`: 6 new tests.
  - `test_bigop_nonblocking.py`: one test removed.
- Docs: the r5 report and the implementation summary (runbook rewritten).

**Binding decision d9ae:**
- The live merge stays fenced, the repair ships, and the merge redesign belongs to the helix plan.
- r5 #s5-3 is now bug-110 in the main tree and is outside this diff.

rel: amends -> [[bsd-bug105-hotfix-r5-fccca72]]

## Evidence base {#evidence}

All logs are in `workflow/review-output/` in the clone. That directory is gitignored.

- **Interpreter:** `.venv-eval/bin/python` with `PYTHONPATH=<clone>/src` prepended. `bsd-bug105-r6-q0.log` confirms `refmatrix.__file__` is in the clone.
- **Mutation family at HEAD:** the r5 13-file family (r4 family plus `_r4`), 107 passed (`bsd-bug105-r6-family-head.log`).
- **r6 probes:** P1-P4 (`bsd-bug105-r6-probe-tests.py.txt`), 4 passed at HEAD (`bsd-bug105-r6-probes-head.log`). The file was copied into `tests/` only for the runs and then removed.
- **Mutations:** 17 mutants, each run against the family and then against the probes (`bsd-bug105-r6-mutations.log`, script `bsd-bug105-r6-mutate.py.txt`).
- **Generated docs:**
  - `test_docs_generated.py` at HEAD: 2 failed, 5 passed (`bsd-bug105-r6-docs-generated.log`).
  - `scripts/gen-cli-tree.py --check` at HEAD reports drift (`bsd-bug105-r6-gen-cli-tree-check.log`).
  - The same check at fccca72 (a `git archive` copy under `/private/tmp/claude-501`, since deleted) prints "ok" (`bsd-bug105-r6-docs-generated-fccca72.log`).
- **Runbook commands:** `--help` for every command the runbook names (`bsd-bug105-r6-runbook-help.log`). I also ran a read-only `launchctl list` for the `com.refmatrix.*` labels.
- **Not run:** the full suite. It reaches live sockets (project_suite_reaches_live_sockets), so I ran targeted files only. No throwaway daemon was needed: the r4 `live` fixture spawns its own under `/tmp/r4f-*` with HOME, RMX_HOME and the model socket isolated, and leaves nothing behind.
- **Restore:** after each mutant, `git checkout -- <file>` and `__pycache__` cleared; the loop printed `RESTORED clean`. HEAD is fe7abea, `git status` is clean, and no `__pycache__` is left under `src/`, `tests/` or `scripts/`.
- **Isolation:** no live store, live socket, main-tree file or the bug109 clone was touched.

## r5 status {#r5-status}

| r5 id | Status | Evidence |
|-------|--------|----------|
| #b5-1 job API producer gone, consumer kept; lock-yield path unreachable | **partial; carried to [[#b6-1]]** | Done: the op, the OPS entry, `_jobs`, `_jobs_lock` and `rmx daemon job` are gone. No reader is left in verbs, mcp, hub, hooks or templates. `test_r5_the_dead_job_api_is_gone` kills J1 (re-registering the op). The `lock`/`progress` parameters now name the helix merge (d9ac) as their caller, which anchors the deferral. Not done: the ARCHITECTURE.md line r5 named (now a red test), plus three stale readers ([[#b6-1]]). |
| #s5-1 runbook relaunches one daemon, names no consistent backup | **closed** | Step 1: `pull --ff-only origin master`, then `rmx hub relaunch-fleet`, `rmx version -v` and `rmx hub status`. Step 2: per store, `hub pause`, `daemon stop`, copy the slot plus `.wal`, `daemon start`, `hub resume`. Every command exists with those arguments ([[#runbook]]). Residual MEH: [[#m6-2]]. |
| #s5-2 remap half-pinned, no `remapped` counter, `manifest:` unpinned | **closed** | N1, N2, F4, M31 and M32 are killed by the family. `remapped` is in the report and the CLI line. The count is correct ([[#remapped]]). The CLI's printed value is unpinned: R5 survives the family and is killed by P4 ([[#m6-1]]). |
| #m5-1 fence decided with `ping` | **closed in behaviour; the busy branch is unpinned** | The fence asks `require_daemon`: up refuses (F6 and F7 killed), busy refuses, absent runs offline. The probe in bf3f781 failed on real code and fe7abea reverted it. F5 (busy treated as absent) survives the family. My P1 kills it with a call-ordered `require_daemon` (absent at the preview, busy at the fence), so it is not equivalent ([[#m6-1]]). The `isinstance(s, _DaemonWriter)` guard r5 suggested was not added. Nothing in that window writes: an offline preview holds the slot's DuckDB lock in the CLI process, and a daemon that is up at the second `_store()` gets the read-only replica (r5 Q1). Not re-filed. |
| #m5-2 offline-merge text omits hub pause; stale hint | **closed in the CLI output; the docstring is stale** | The refusal names `rmx hub pause` and `rmx hub resume`. The kickstart hint is gone, and H2 (restore it) is killed. The refusal's `hub pause` text is unpinned: H1 survives the family and is killed by P2. The `partition merge` docstring (cli.py:4172) and the daemon op's refusal (daemon.py:4068) still say only "`rmx daemon stop` ... offline" ([[#m6-1]]). |

## Mutations {#mutations}

17 mutants. The family kills 11. Of the 6 family survivors, my probes kill 4. The 2 that survive both are near-equivalent offline, as in r5.

| Mutant | Family (107) | r6 probes |
|--------|--------------|-----------|
| F3 daemon dry-run merge without `_store_lock` | survives | survives (SELECT-only; low risk, as in r5) |
| F4 CLI merge drops the `manifest:` print | **killed** | |
| M5 merge without the pre-flush | survives | survives (near-equivalent offline, as in r3/r5) |
| N1 remap the concept half only | **killed** (2) | |
| N2 `changed` computed from remapped rows | **killed** | |
| M31 no `id_map` | **killed** (4) | killed (P3, P4) |
| M32 remap the entity half only | **killed** (3) | killed (P4) |
| R1 `remapped` never incremented | **killed** (2) | killed (P3, P4) |
| R3 `remapped` counts every bit, not just rewritten ones | survives | **killed** (P3) |
| R4 CLI line omits `remapped=` | **killed** | killed (P4) |
| R5 CLI prints `remapped=0` (a constant) | survives | **killed** (P4) |
| F5 fence: busy treated as absent | survives | **killed** (P1) |
| F6 fence: up treated as absent | **killed** | killed (P2) |
| F7 fence never refuses | **killed** | killed (P1, P2) |
| H1 refusal drops `rmx hub pause` | survives | **killed** (P2) |
| H2 post-merge hint back to `kickstart -k` | **killed** | |
| J1 `job_status` op re-registered | **killed** | |

**r5 survivors re-run:**
- F4, N1 and N2 are now killed.
- F3 and M5 survive. Both are near-equivalent, as in r5.

## Is the `remapped` counter right? {#remapped}

**Yes, for what it claims to count.**
- **What it counts:** the number of fragment-bit occurrences whose (concept, entity) pack the collision `id_map` rewrote, before deduplication (store.py:4394-4402).
- **Exact-value test (P3):** seed one collided bit with both halves remapped, plus an untouched DST bit. The report's `remapped` equals an independent count of the old fragment bits that touch a collision id. R3 (count every bit) fails P3.
- **CLI test (P4):** the offline CLI prints the true value: `remapped=` is at least 1 on a seed with a colliding concept.
- **Caveats:** two semantic points to document, neither wrong ([[#m6-1]]):
  - `remapped` overlaps `kept`/`moved`; it is not a separate bucket. A remapped bit is still classified (it is `moved` when it sits in SRC's row). So the code comment "a remap is visible, not 'kept'" overstates it.
  - Two source bits that remap onto the same packed value count 2 in `remapped` but 1 in `kept`/`moved`.
- **Scope:** `rmx repair-index --fragments` passes no `id_map`, so its `remapped` is always 0. The daemon's rmxd.log repair line does not print it, which is fine because there is nothing to report there.

## Runbook commands {#runbook}

Each command was checked against `--help` in the clone (`bsd-bug105-r6-runbook-help.log`).

| Runbook step | Exists | Notes |
|--------------|--------|-------|
| `git -C ~/refmatrix pull --ff-only origin master` | yes | `origin master` restored. |
| `rmx hub relaunch-fleet` | yes, no required args | Runs `daemon restart --relaunch` for every launchd-loaded root in `discover_roots()`, which always includes the global store. `launchctl list` shows a label for the home/global store (`tholley-…`), so the fleet covers it. Unsupervised roots print `skip`. |
| `rmx version -v` | yes | Prints the import path, code root, venv tree and a `[DEV TREE]` flag. |
| `rmx hub status` | yes | |
| `rmx hub pause <store>` | yes, `[TARGET]` = project name or path | Default auto-resume after 30 min (`-m`). |
| `rmx daemon stop` | yes, **no target argument** | Acts on `_root()`: the cwd or `REFMATRIX_ROOT`. A clean stop exits 0, and the plist's `KeepAlive: {SuccessfulExit: false}` does not respawn it, so launchd does not race the copy. |
| `rmx daemon start` | yes | On a supervised store it defers to `launchctl kickstart`, so no orphan. Also cwd/`REFMATRIX_ROOT`-scoped. |
| `rmx hub resume <store>` | yes, `[TARGET]` | |
| `rmx repair-index --fragments [--dry-run]` | yes | Daemon-routed; the dry run is write-free on a live daemon (r5 Q3). |

## Findings {#findings}

### BULLSHIT (scope shrunk silently; the suite is red at HEAD): the job API removal left the generated CLI doc, and with it `test_docs_generated`, failing, plus three stale readers {#b6-1}

**Files:**
- docs/ARCHITECTURE.md:354 (CLI tree still lists `│ ├── job  Status of a daemon background job (e.g. partition merge --async…`, and the header says 213 commands);
- tests/test_bigop_nonblocking.py:173-193;
- src/refmatrix/daemon.py:715-717;
- src/refmatrix/store.py:1693-1697;
- docs/system_design_review.md:227.

**What:**
- r5's #b5-1 fix listed five deletions, including "the ARCHITECTURE.md line". 104322b did four of them.
- The CLI tree in ARCHITECTURE.md is GENERATED and checked against the code by `tests/test_docs_generated.py` (plan-6 task 6.2).
- At fe7abea that test fails 2 of 7: `test_cli_tree_section_equals_its_render` and `test_check_mode_reports_drift_and_apply_fixes_it`.
- The same check at fccca72 prints "ok". This diff caused the failure.
- 104322b's "families incl. verb/MCP parity and hooks 591 passed" did not include that file, so the red went unseen.

The leftovers:
1. `test_live_merge_is_refused_even_async`'s docstring (test_bigop_nonblocking.py:190-191) still says **"The job API stays for the next async big-op."** That is the exact unanchored deferral r5 #b5-1 quoted, and it is now false: the job API is gone.
   - The `_fake_daemon` fixture still sets `d._jobs` and `d._jobs_lock` (lines 177-178), state no code reads.
   - Its section header still reads "3. daemon async job API".
2. daemon.py:715-717 keeps the comment "Background jobs (big ops run off the RPC thread …) id -> {state, phase, …}". It sits above nothing; the two lines it described were deleted.
3. store.py:1693-1697 still says "the daemon's merge op does not hold the lock". r5 asked for that comment to be corrected. The daemon op holds `_store_lock` for its dry run and refuses any real merge.
4. docs/system_design_review.md:227 lists "async job API" as a current fix for big ops starving the hooks.

**Why it's bullshit:**
- The commit claims #b5-1 closed while one named piece of the prescribed fix was silently dropped (rule 10, scope shrunk silently).
- It leaves a project test failing. "Tests pass (all)" is a before-commit gate, and a red generated-doc test blocks the merge.
- The stale docstring re-states the deferral the finding was about.

**Fix (about 5 minutes):**
1. Run `PYTHONPATH=src .venv-eval/bin/python scripts/gen-cli-tree.py` to regenerate the ARCHITECTURE.md CLI tree, then re-run `tests/test_docs_generated.py`.
2. In test_bigop_nonblocking.py: delete the `_jobs`/`_jobs_lock` fixture lines, rename the section header, and drop the "job API stays" sentence.
3. Delete the orphan comment in daemon.py:715-717.
4. Rewrite store.py:1693-1697: no caller passes `lock` today; the offline merge runs without a concurrent writer.
5. Mark the system_design_review.md line as historical, or drop "async job API" from it.
6. Add `tests/test_docs_generated.py` to the family list the remedy commits cite.

**Pattern match:** YES.
- It is #b5-1's own shape again: a removal that misses a reader. This time the reader is a generated doc and a test fixture.
- It is also the 0916 pattern ("the prescription is applied narrower than written").

### MEH: unpinned operator surface: the CLI's `remapped` value, the fence's busy branch, and the refusal's hub-pause text; stale docstrings {#m6-1}

**Files:**
- cli.py:4204-4218 (fence) and :4256 (`remapped=` print);
- cli.py:4169-4172 (docstring);
- daemon.py:4068-4070 (op refusal text);
- store.py:4402 (comment);
- tests/test_fragment_repair_audit_r4.py:290-306.

**What:**
- **Survivors that are killable:** R5, F5 and H1 survive the 107-test family. My P1, P2 and P4 kill each of them in about 15 lines. fe7abea's message calls F5 "equivalent for this probe". It is equivalent only for that probe: a call-ordered `require_daemon` (absent at the preview, busy at the fence) kills it.
- **Safety:** F5 does not open a write path. After the fence, `_store()` refuses busy itself, so only the message would change. That is why this is MEH and not higher.
- **How the F5 tightening went:** bf3f781 was committed as "kills F5" without being run against unmutated code. It failed there, and fe7abea reverted it. The revert is honest, but the fix was a better probe, not a weaker assertion.
- **`.get` default:** the CLI prints `fr.get('remapped', 0)`. The repair always returns the key, so the default hides nothing today. But a regression that drops the key would print 0 silently: `fr['remapped']` matches the other counters.
- **Stale guidance:** the `partition merge` docstring and the daemon op's refusal still give the pre-#m5-2 recipe (no `hub pause`). Only the CLI refusal, which is what the operator sees first, was updated.
- **Comment:** "a remap is visible, not 'kept'" (store.py:4402) is inaccurate: remapped bits are still counted in `kept`/`moved` ([[#remapped]]).

**Fix:**
- Adopt P1, P2 and P4 from `bsd-bug105-r6-probe-tests.py.txt`. P3 is optional; it pins the exact count.
- Use `fr['remapped']`.
- Add `rmx hub pause`/`resume` to the docstring and the op's refusal.
- Say in the report docstring that `remapped` overlaps `kept`/`moved` and is counted before deduplication.

### MEH: the runbook's per-store steps do not say how to target a store {#m6-2}

**File:** `workflow/implementation_summaries/bug-105-fragment-partition.md` [[impl-bug-105-fragment-partition#deploy]] step 2, and the TDD section.

**What:**
- `rmx hub pause <store>` and `rmx hub resume <store>` take a target. `rmx daemon stop`, `rmx daemon start` and `rmx repair-index --fragments` do not: they act on the cwd's store or `REFMATRIX_ROOT`.
- "Per store" leaves the operator to run each block from inside that project, or to export `REFMATRIX_ROOT=<project>/.refmatrix`. That includes the global store at `~/.refmatrix`.
- A wrong cwd stops or repairs the wrong store (feedback_backgrounded_cd_stays_in_subshell).
- Steps 3-4 also say nothing about running per store, but the repair has to run on every store in the fleet.
- The summary's TDD section is stale:
  - it still cites "536 passed … at 325d702" and "`bug105-r5-mutations.log` (8/8 killed)";
  - it lists ch-bsd rounds r1-r4 only;
  - it omits r5, `bug105-r6-*.log` and fe7abea's F5 note.

**Fix:**
- Write steps 2-4 as one per-store block that begins with `export REFMATRIX_ROOT=<project>/.refmatrix`, and list the stores, or say "every row of `rmx hub status`".
- Refresh the TDD section.

## Verdict {#verdict}

**DIRTY: 3 findings (1 BULLSHIT, 0 SKETCHY, 2 MEH).**
- r5's 5 ids:
  - closed: #s5-1, #s5-2;
  - closed in behaviour with unpinned residue: #m5-1, #m5-2 (folded into [[#m6-1]]);
  - partial: #b5-1 (carried to [[#b6-1]]).
- Mutants: 17 run. The family kills 11; the r6 probes kill 4 of the 6 family survivors. F3 and M5 remain, near-equivalent, as in r5.
- Mutation family: 107 passed. `test_docs_generated`: 2 failed (caused by this diff).

**Is it safe to merge, deploy (fleet relaunch) and run the live repair per the runbook?**

**Merge: no, not yet.** One test is red at HEAD because of this diff (`test_docs_generated`, [[#b6-1]]). The fix is one generator command plus four comment and docstring edits, with no runtime change. Once that file passes, merge.

**Deploy (fleet relaunch) and live repair per the runbook: yes, after that merge.**
- Every command the runbook names exists with those arguments.
- `relaunch-fleet` covers every launchd-supervised store, including the global store.
- The backup method gives a consistent copy: hub paused, daemon cleanly stopped, and launchd does not respawn on exit 0.
- The repair dry run is write-free on a live daemon (r5 Q3).
- The live merge is unreachable: up refuses, busy refuses, and the daemon op refuses any non-dry-run.
- Run steps 2-4 inside each store, from its project directory or with `REFMATRIX_ROOT` set ([[#m6-2]]).

rel: contradicts -> [[claude#before-commit]]
rel: contradicts -> [[claude#no-mocks]]

## Ledger lines (for the orchestrator to apply) {#ledger}

last_run.log:

```
2026-10-14T16:59:08-0700 commit=fe7abea verdict=DIRTY findings=3 (1B/0S/2M) report=2026-10-14-1659-bug105-hotfix-r6-job-api-half-removed-docs-test-red-fe7abea.md
```

INDEX.md row:

```
| fe7abea (fccca72..fe7abea, bug-105 hotfix r6: 104322b r5 remedies + bf3f781 test tightened + fe7abea reverted; written 2026-10-14T16:59) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 3 (1B/0S/2M); r5 5: 2 closed (#s5-1 runbook, #s5-2 remap pins + counter) / 2 closed-in-behaviour with unpinned residue (#m5-1, #m5-2) / 1 partial (#b5-1 -> #b6-1) | [[bsd-bug105-hotfix-r6-fe7abea]]. B: job API removed from OPS/CLI but the GENERATED CLI tree in docs/ARCHITECTURE.md still lists `rmx daemon job` -> tests/test_docs_generated.py 2 failed at fe7abea (gen-cli-tree --check ok at fccca72); the remedy's family list skipped that file; test_bigop docstring still says "The job API stays for the next async big-op" + fixture sets _jobs; orphan daemon.py:715 comment; store.py:1693 "daemon's merge op does not hold the lock" uncorrected. M: R5 (CLI prints constant remapped), F5 (fence busy branch) and H1 (refusal hub-pause text) survive the 107 family; all killed by r6 probes P1/P2/P4 (F5 is NOT equivalent; bf3f781 was committed unrun, fe7abea reverted); remapped overlaps kept/moved. M: runbook steps 2-4 need cwd/REFMATRIX_ROOT per store; TDD section stale. remapped counter exact (P3). Runbook commands all exist; relaunch-fleet covers the launchd-supervised global store. 17 mutants: family 11 killed, probes +4, F3/M5 near-equivalent. Merge after regenerating the doc; deploy + live repair safe per runbook. |
```

IMPRESSIONS.md bullets:

```
- A removal is not done until the generated docs agree: bug-105 r6 deleted `rmx daemon job` and left docs/ARCHITECTURE.md's generated CLI tree listing it, so test_docs_generated went red; the remedy's hand-picked "families" never ran it. Any CLI or OPS change: run scripts/gen-cli-tree.py --check (#b6-1).
- "Equivalent for this probe" is not "equivalent": bf3f781 was committed as "kills F5" without a run on real code, then reverted; a call-ordered require_daemon fake kills F5 in 15 lines. Ask whether a better probe exists before accepting a survivor (#m6-1).
- The deferral sentence outlives the code it defended: "the job API stays for the next async big-op" survived in a test docstring after the job API itself was deleted. Grep the finding's quoted phrase after every remedy.
```
