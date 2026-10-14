---
gmd: "0.1"
id: bsd-bug105-hotfix-r5-fccca72
title: "bug-105 hotfix r5: the live-merge fence holds (no path reaches a non-dry-run merge under a daemon) and every r4 repair-path survivor is killed, but the fence left a producer-less job API plus a dead lock-yield path, kept by an unanchored 'next async big-op'; the deploy runbook relaunches one daemon and names no consistent backup method; the offline merge's remap is still half-pinned; and, outside the diff, the daemon's own snapshot drops its DuckDB lock"
severity: BULLSHIT
plan: bug-105
task: hotfix-fccca72-r5
tags: [bsd, audit, bug-105, fragments, partition, merge, fence, runbook, lock, mutation]
---

# ch-bsd findings r5: bug-105 r4 remedies (325d702 + fccca72) {#root}

**Commit:** fccca72 (docs) on top of 325d702 (fix + tests + the r4 report).
- Range under audit: fb285cc..fccca72. Base of the hotfix: a434f51.
- Clone: `/Volumes/littlebig/refmatrix-bug105`, branch `bug-105-fragment-partition`.

**Date:** 2026-10-14 (written 2026-10-14T16:31:17-0700)
**Author:** Todd Holley / Opus 5.5 / orchestrator
**Files changed (fb285cc..fccca72):** 7
- Source: cli.py (`partition merge`: `--async` removed, ping fence before the confirm prompt, offline merge only), daemon.py (`_periodic_flush` extracted; `_op_partition_merge` refuses a non-dry-run; async/sync live merge and `_merge_repair_line` deleted).
- Tests: `tests/test_fragment_repair_audit_r4.py` (new, 10 tests), `test_fragment_repair_audit_r3.py` (P5/P6 removed), `test_bigop_nonblocking.py` (async merge test now asserts the refusal).
- Docs: the r4 report, `workflow/implementation_summaries/bug-105-fragment-partition.md`.

**Binding user decision d9ae:** ship the repair, fence the live merge, and move the merge redesign to the helix plan (d9ac). #b4-1 and #s4-1 are judged closed if the fence holds; this audit does not ask for a safe live merge.

rel: amends -> [[bsd-bug105-hotfix-r4-fb285cc]]
rel: amends -> [[bsd-bug105-hotfix-r3-27b3653]]

## Evidence base {#evidence}

All logs are in `workflow/review-output/` in the clone.

- **Interpreter:** `.venv-eval/bin/python` with `PYTHONPATH=<clone>/src` prepended. `bsd-bug105-r5-q0.log` shows `refmatrix.__file__` = `/Volumes/littlebig/refmatrix-bug105/src/refmatrix/__init__.py`.
- **Mutation family at HEAD:** 102 passed (`bsd-bug105-r5-family-head.log`). It is the r4 12-file family plus `test_fragment_repair_audit_r4.py`.
- **Broad families at HEAD:** 580 passed, 4 skipped (`bsd-bug105-r5-families-head.log`). That is the claimed 536-test list, plus `_r3`, `_r4`, `test_snapshot_policy` and `test_verb_parity`. The claimed `bug105-r5-families.log` (536 passed, 4 skipped) agrees.
- **Mutations:** 17 mutants run against the full 102-test family, not the 41-test subset in `bug105-r5-mutations.log`. 12 killed, 5 survive (`bsd-bug105-r5-mutations.log`, script `bsd-bug105-r5-mutate.py.txt`).
- **Probes:** Q1-Q4 (`bsd-bug105-r5-probe-tests.py.txt`, results in `bsd-bug105-r5-probes.log`). Q1, Q3 and Q4 pass. Q2's first half passes; its second half fails, and that failure led to [[#s5-3]]. The probe file was copied into `tests/` only for the run and then removed.
- **Lock probes:**
  - `bsd-bug105-r5-q2b-lock.log`: a second process writes into a live daemon's active slot.
  - `bsd-bug105-r5-lockexp.log` and `bsd-bug105-r5-q2c-lock-mechanism.log`: the mechanism, and the reverse direction.
  - Scripts are the matching `.py.txt` files.
- **Restore:** each mutant was restored with `git checkout -- <file>`, and `__pycache__` was cleared after each one. The loop printed `RESTORED clean`. HEAD is fccca72, `git status` is clean, and no `__pycache__` is left under `src/` or `tests/`.
- **Isolation:** throwaway daemons ran under `/tmp/r5p-*`, `/tmp/r5q-*` and `/tmp/r5n-*`, with HOME, RMX_HOME and the model socket isolated. No process or directory of mine remains. No live store, live socket, main-tree file or the bug109 clone was touched.

## r4 status {#r4-status}

| r4 id | Status | Evidence |
|-------|--------|----------|
| #b4-1 rebind hold hands queued ops the dropped SRC binding | **closed by the fence (d9ae)** | See [[#fence]]. No path runs a non-dry-run `merge_partition` inside a daemon or beside a live one. F1 (the daemon runs the live merge) is killed by 2 tests; F2 (the CLI fence removed) is killed by 1. |
| #b4-2 M1/M11/M12/M14 alive a third round (+M24/M25) | **closed** | Re-run on the 102-test family: M1, M11, M12, M14, M24, M25 and M25b (the `manifest=` field) are each killed by a dedicated `_r4` test. |
| #s4-1 a SRC write between merge chunks orphans its entity | **closed by the fence** | No live merge remains, so nothing writes concurrently. An offline merge holds the DuckDB lock in its own process: q2c(b) shows a daemon spawned mid-write does not come up. A busy daemon refuses the merge (Q2). The folded remap-pin residual (N1/N2) is carried to [[#s5-2]]. |
| #m4-1 remap invisible in the report; `manifest=` unpinned | **still open; escalated into [[#s5-2]]** | There is still no `remapped` counter, because `remapped` in store.py:4394 is a local dict. The merge's `manifest=` log line was deleted with the live merge, so N4 is moot. The repair-index log's `manifest=` is pinned (M25b killed). The offline CLI merge's `manifest:` print is unpinned: F4 survives. |
| #m4-2 no implementation summary or registry row | **closed for the summary; the registry row is in the main tree** | fccca72 adds the summary. It lints with 0 errors (2 dangling cross-doc warnings to main-tree ids). Per the caller, the bug-registry row lives in the main tree. This audit did not read the main tree, so that row is not verified here. |

**Mutants this round (102-test family):**

| Mutant | Result |
|--------|--------|
| M1 tick guard reads `_dirty_fragments` | killed (`test_periodic_flush_persists_another_bindings_dirty_bits`) |
| M11 `links_skipped` never incremented | killed |
| M12 SQLite unlink-all | killed (write-path test) |
| M14 no `_canonical_verb` on `linkage_types` | killed |
| M24 CLI drops `unread_dirs` | killed |
| M25 / M25b rmxd.log loses counters / `manifest=` | killed |
| F1 daemon runs a live merge | killed (2 tests) |
| F2 CLI ping fence removed | killed |
| M31 / M32 no `id_map` / entity-half-only remap | killed (P7) |
| N6 offline merge drops the home rebind | killed (P3) |
| F3 daemon dry-run merge without `_store_lock` | **survives**. The dry run is SELECT-only, so this is low risk. |
| F4 CLI offline merge does not print `manifest:` | **survives** ([[#s5-2]]) |
| M5 merge without the pre-flush | **survives**. Near-equivalent offline (r3). |
| N1 remap the concept half only | **survives** ([[#s5-2]]) |
| N2 `changed` computed from remapped rows | **survives** ([[#s5-2]]) |

## Is the fence closed? {#fence}

**Yes. No path reaches a non-dry-run merge while a daemon runs.**

**Daemon op `partition_merge`:**
- It raises unless `dry_run`.
- The `async` key is ignored and refused (r4 test, sync and async).
- The dry run runs under `_store_lock` with `dry_run=True` hard-coded.
- `merge_partition(dry_run=True)` returns before any write or flush (store.py:1698 guards the pre-flush).

**Other callers:**
- `merge_partition` has exactly two callers in `src/`: the daemon op and the CLI.
- verbs.py, mcp.py and hub.py have none. Templates have none.

**CLI, daemon up:**
- `ping` returns True, and the command refuses before the confirm prompt (F2 killed).

**CLI, daemon busy but alive (busy ≠ absent):**
- `ping` returns False. The command then calls `_store()`, which calls `verbs.require_daemon`.
- That check sees a live rmx pid and raises VerbBusyError, so the command exits with "daemon busy … writes go through the daemon".
- Q2 reproduces this with a real daemon and a failing ping. The command exits 1, and the catalog still has both partitions.

**CLI, busy-to-up flip between the two checks** (the only other interleaving):
- `_store()` returns a `_DaemonWriter`.
- `_DaemonWriter.__getattr__` hands `merge_partition` to the read-only replica Store.
- Q1 shows the first SQL write raising `InvalidInputException: Cannot execute statement of type "DELETE" … read-only mode`. The exit code is 1, and the live partitions are unchanged.
- All SQL writes in the merge come before its filesystem renames (store.py:1800-1950), so nothing moves.
- The fence holds, but only by accident. See [[#m5-1]].

**CLI, daemon absent:**
- The command opens the slot itself and runs the offline merge.
- A daemon spawned during the merge, such as the hub watchdog's respawn, does not come up: q2c(b) shows no ping in 30 s, because the CLI process holds DuckDB's lock and never copies the file.
- A daemon that comes up BEFORE the merge command runs makes it refuse.

**Can the offline merge run while a daemon holds the store?** Not through any CLI path. But DuckDB's lock is not the backstop people assume: a live daemon drops it after its first snapshot ([[#s5-3]]). The CLI's tri-state check is the only real guard, and it holds.

## Findings {#findings}

### BULLSHIT (dead code + unanchored deferral): the fence left a producer-less job API and a lock-yield merge path that nothing in production calls {#b5-1}

**Files:**
- daemon.py:712-719 (`self._jobs`, `_jobs_lock`), :3896-3907 (`_op_job_status`, registered at :6223);
- cli.py:2894-2928 (`rmx daemon job`);
- docs/ARCHITECTURE.md:354;
- store.py:1648-1697 (`merge_partition(lock=, chunk=, progress=)` and its docstring and comments);
- tests/test_bigop_nonblocking.py (`test_job_status_unknown_and_listing`, and the "job API stays" docstring).

**What:**
- 325d702 deleted the only writer of `d._jobs`, the async merge. The registered op and the CLI command remain:
  - `rmx daemon job` can only ever print "no jobs this daemon run".
  - Its help still says "(e.g. `partition merge --async`)", and `rmx partition merge --async` is now "No such option" (Q4).
- The summary and the rewritten test say the API is "kept for the next async big-op". That names no plan or task (rule 9a).
- `merge_partition`'s `lock` and `progress` parameters have no production caller:
  - the CLI's offline merge passes neither;
  - the daemon's dry run holds the lock itself and passes none.
- So the docstring's "queued ops (the always-on prompt hooks above all) interleave instead of timing out" describes a path that cannot run.
- store.py:1693-1697 still says "the daemon's merge op does not hold the lock".
- The r2 and r3 lock-yield tests (P1-P3, r2 lock tests, bigop chunk=1) pin behaviour on that unreachable path.

**Why it's bullshit:** this is the checklist's first item: an op whose only producer was removed, kept alive by a deferral with nothing behind it. The commit message even says "The async/sync merge code behind the op and `--async` are removed rather than left dead". It removed the producer and left the consumer.

**Fix:**
1. Delete `_op_job_status` and its OPS entry, `_jobs`/`_jobs_lock`, `rmx daemon job`, `test_job_status_unknown_and_listing` and the ARCHITECTURE.md line. A future async big-op re-adds them with its producer. About 60 lines removed; check `test_verb_parity` stays green.
2. For `lock`/`chunk`/`progress`, do one of these:
   - delete them, or
   - keep them and name the helix plan's merge task id in the docstring, as the substrate that task reuses.
   Either way, correct the stale docstring and the :1693-1697 comment.

**Pattern match:** YES. It is the "fix removes the producer, leaves the surface" shape, and also r4 #b4-2's "addressed with only its easy half".

### SKETCHY: the deploy runbook relaunches one daemon and names no consistent backup {#s5-1}

**File:** `workflow/implementation_summaries/bug-105-fragment-partition.md` [[impl-bug-105-fragment-partition#deploy]], steps 1-2.

**What:**
1. Step 1 deploys with `rmx daemon restart --relaunch`. That restarts ONE store's daemon.
   - `rmx hub relaunch-fleet`'s own docstring (cli.py:2740-2744) records why it exists: "a plain relaunch restarts one store and the hub's version handshake does not restart the rest" (plan-4 r1 #b-6).
   - Every other store keeps running the pre-fix, linkage-keyed fragment cache, so it keeps flushing bits into the wrong partition: the defect this deploy exists to stop.
   - On those stores, step 3's `rmx repair-index --fragments` reaches an old daemon with no `repair_fragments` op and fails. That failure is safe, but nothing in the runbook explains it.
   - The step also drops `origin master` from `git -C ~/refmatrix pull --ff-only`, and has no `rmx version -v` / deploy-path check (feedback_deploy_tree_is_the_runtime).
2. Step 2 says "back up the ACTIVE slot (`catalog.<A|B>.duckdb`)" with no method.
   - With the daemon up, a `cp` of the slot is not a consistent copy: it can catch a write or a checkpoint mid-flight, and it omits `catalog.<X>.duckdb.wal`.
   - The manifest records drops only, so this backup is the ONLY restore point for `moved` bits.

**Is the dry run write-free on a live store?** Yes, Q3 proved it.
- Test: seed a foreign bit and a dead-entity bit, start the daemon, run `rmx repair-index --fragments --dry-run`, stop it, then read `bitmap_fragments` and `entities`.
- Result: they are byte-identical to a baseline start/stop with no dry run.
- The dry run reported `moved=1 dropped_dead=1` and wrote `backups/fragments-repair-…-dryrun.jsonl`.
- The apply then fixed the store, and a second dry run read `moved=0 dropped_dead=0`.
- Code read: there is no flush, no cache clear and no rebind on `dry_run`, and no snapshot is requested.
- Its only writes are the manifest and one rmxd.log line. It holds `_store_lock` for the scan: about 1.2 s on the repaired 704k-bit copy (`bsd-bug105-timing.log`), more before the repair.

**Fix:** rewrite steps 1-2:
1. `git -C ~/refmatrix pull --ff-only origin master`, then `rmx hub relaunch-fleet`, then confirm the version and code path for every store with `rmx version -v` and `rmx hub status`.
2. Per store, take a consistent backup by one of these methods:
   - `rmx hub pause <root>`, `rmx daemon stop`, copy `catalog.<active>.duckdb` and any `.wal`, `rmx daemon start`, `rmx hub resume`; or
   - copy `catalog.read.duckdb` immediately after a forced snapshot, which is a CHECKPOINT plus a copy under `_store_lock`.
   Steps 3-4 are right as written.

**Pattern match:** YES. It is the 0916 pattern, "a prescription narrower than the defect", and the deploy-step gap plan-4 r1 #b-6 already named once.

### SKETCHY (escalated, second sighting): the offline merge's remap is still half-pinned and invisible {#s5-2}

**Files:** store.py:4393-4404 (`id_map` remap) and cli.py:4283-4284 (merge `manifest:` print).

**What:**
- The fence keeps the OFFLINE merge, so the collision remap is still a production path.
- N1 (remap only the concept half) and N2 (compute `changed` from the remapped rows) still pass all 102 family tests.
- r4 asked for its probes Q1-Q3 to be adopted (`bsd-bug105-r4-probe-tests.py.txt`). They kill both mutants, and they were not adopted. 325d702's message does not mention them.
- The `remapped` counter requested in #m4-1 was not added: a remapped bit is still counted `kept`.
- The offline CLI merge's `manifest:` line is unpinned (F4 survives).

**Why SKETCHY:** this is #m4-1 seen a second time (MEH → SKETCHY), together with the remap half of #s4-1 that was folded in at r4.

**Fix:**
- Adopt r4 Q1-Q3 as offline-merge tests.
- Either add `remapped=<n>` to the report and the CLI line, or record in the summary that it was declined.
- Assert `manifest:` in `test_offline_cli_merge_runs_and_prints_the_repair`. The seed needs a dead bit so a manifest exists.

**Pattern match:** YES (r4 #m4-1, #s4-1 remap pins).

### SKETCHY (pre-existing, outside the diff): a live daemon's own snapshot drops its DuckDB lock {#s5-3}

**File:** daemon.py:2659-2675 (`_snapshot_now`: `CHECKPOINT`, then `shutil.copy2(self.store.db_path, tmp)` inside the daemon process).

**What:** DuckDB locks the catalog with a POSIX `fcntl` lock. POSIX drops every such lock a process holds on a file when that process closes ANY descriptor for the file. `copy2` opens and closes one. The lock probes show the effect:

| Probe | Result |
|-------|--------|
| lockexp / q2c(a1): A holds the file | B is blocked: "Conflicting lock is held" |
| q2c(a2): after `CHECKPOINT` only | still blocked |
| q2c(a3): after `CHECKPOINT` + `copy2` | B opens and commits |
| q2b: real throwaway daemon (its lsof shows `catalog.A.duckdb` open) | a second process opened that slot read-write and committed `CREATE TABLE` while the daemon answered ping |

**Why it matters here:** the boot snapshot runs before the socket binds, so for a live daemon the "Conflicting lock" backstop is gone. Every guard against a second writer is the CLI's own up/busy/absent decision. That decision holds for this fence ([[#fence]]), so this does not block bug-105. Any other path that misreads busy as absent writes straight into a live catalog instead of failing.

**Fix (separate bug row):**
- Snapshot without closing an fd on the locked file. For example, have DuckDB itself write the snapshot (`ATTACH … ; COPY FROM DATABASE`, or `EXPORT`), or copy through a descriptor the store keeps open.
- Add a test asserting that a second process cannot open a live daemon's slot after its first snapshot.

**Pattern match:** NO new pattern. It explains the 2026-09-14 "Conflicting lock" boots being intermittent.

### MEH: the CLI fence decides with `ping`, so a busy-to-up flip sends the real merge to the read-only replica {#m5-1}

**File:** cli.py:4238 (`if daemon_mod.ping(root): raise …`) and :4257 (`s = _store()`).

**What:**
- `ping` cannot tell busy from absent; `_store()`'s docstring records that lesson as plan-5 #b-1.
- In Q1, a daemon that is busy at the fence and up at `_store()` produces a `_DaemonWriter`. `merge_partition(dry_run=False)` then falls through `__getattr__` to the read-only replica.
- The user sees a raw DuckDB `InvalidInputException` (exit 1) instead of the fence message. No write happens.

**Fix:**
- Replace both `ping` decisions with one `verbs.require_daemon(root)`: up or busy refuses, absent runs offline.
- Make the offline branch refuse any writer that is not a direct `Store` (`isinstance(s, _DaemonWriter)`).
- About 6 lines, plus a test using Q1's flip.

### MEH: the offline-merge instructions omit the hub watchdog, and the post-merge hint is stale {#m5-2}

- The refusal message and docstring say "`rmx daemon stop`, merge, then start the daemon again". They do not mention `rmx hub pause`.
- With the `auto` policy, the hub respawns a stopped daemon after two no-process ticks (hub.py:288-305): about 30 s at the 15 s interval.
  - If the respawn lands before the merge, the merge is refused.
  - If it lands during the merge, the daemon cannot open the slot (q2c(b)), so launchd churns until the merge ends.
  - Neither case corrupts anything; both confuse the operator.
- After an offline merge, the CLI still prints "restart the daemon to drop any cached SRC partition binding (`… kickstart -k`)". The daemon is stopped at that point.
- If SRC was the daemon's configured home partition, a start re-creates SRC at open (`_ensure_partition`).

**Fix:**
- Say `rmx hub pause <root>` / `rmx hub resume <root>` around the offline merge.
- Change the hint to "start the daemon", and warn when SRC is the store's configured partition.

## Verdict {#verdict}

**DIRTY: 6 findings (1 BULLSHIT, 3 SKETCHY, 2 MEH).**
- r4's 5 ids:
  - 3 closed: #b4-1 and #s4-1 by the fence, and #b4-2.
  - #m4-1 is open and escalated into [[#s5-2]].
  - #m4-2 is closed for the summary; the registry row is in the main tree.
- Mutants: 17 run, 12 killed, 5 survive (F3, F4, M5, N1, N2).
- Families: 580 passed, 4 skipped.

**Safe to merge, deploy and run the live repair?**
- **Merge: no, not yet.** [[#b5-1]] is a BULLSHIT finding, and the ledger blocks on it. The fix is a deletion, and none of it is unsafe at runtime. Fold in [[#s5-2]] and the two MEHs if they are cheap.
- **Deploy + live repair: yes, once merged, but only with a corrected runbook ([[#s5-1]]).**
  - Relaunch the whole fleet, then verify every store's version.
  - Take a consistent per-store backup: daemon paused and stopped, or a fresh snapshot copy.
  - Then dry run, read every counter, and apply.
  - The repair path is sound:
    - the dry run is write-free on a live daemon (Q3);
    - the apply is idempotent (a second dry run reads 0);
    - every repair counter and log field is pinned.
- **As the runbook is written, no:** step 1 leaves every other store on the defective cache.
- **A live `rmx partition merge`** is unreachable: refused up, refused busy, and read-only on a flip. Offline merges remain available with the daemon stopped and the hub paused.

rel: contradicts -> [[claude#no-mocks]]
rel: contradicts -> [[claude#task-completion-workflow]]
rel: contradicts -> [[claude#development-commands]]

## Ledger lines (for the orchestrator to apply) {#ledger}

last_run.log:

```
2026-10-14T16:31:17-0700 commit=fccca72 verdict=DIRTY findings=6 (1B/3S/2M) report=2026-10-14-1631-bug105-hotfix-r5-fence-holds-job-api-dead-runbook-one-daemon-fccca72.md
```

INDEX.md row:

```
| fccca72 (fb285cc..fccca72, bug-105 hotfix r5: 325d702 + fccca72 docs; written 2026-10-14T16:31) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 6 (1B/3S/2M); r4 5: 3 closed (#b4-1/#s4-1 by the d9ae fence, #b4-2) / 1 escalated (#m4-1 -> #s5-2) / 1 closed-summary (#m4-2, registry row in main tree) | [[bsd-bug105-hotfix-r5-fccca72]]. FENCE HOLDS: daemon op refuses non-dry-run (F1 killed), CLI refuses daemon-up (F2 killed), busy -> require_daemon refuses (Q2), busy->up flip lands merge on the read-only replica, raises before any write (Q1); no verbs/MCP/hub caller. r4 survivors M1/M11/M12/M14/M24/M25(+M25b) all killed on the 102-test family. B: fence removed the only _jobs producer but kept _op_job_status + `rmx daemon job` (help names removed --async, Q4) "for the next async big-op" (no plan) + merge_partition lock/progress have no production caller (stale lock-yield docstring + comment). S: runbook step 1 relaunches ONE daemon (hub relaunch-fleet exists for exactly this, plan-4 r1 #b-6) and step 2 names no consistent backup method; dry run proven write-free on a live daemon (Q3). S (2nd sighting): N1/N2 remap mutants survive, r4 Q1-Q3 not adopted, no remapped counter, merge manifest print unpinned (F4). S (pre-existing): daemon snapshot CHECKPOINT+shutil.copy2 closes an fd -> POSIX fcntl lock dropped; second process wrote into a live daemon's slot (q2b); lock backstop absent fleet-wide. M: fence uses ping (busy==absent); offline-merge text omits `rmx hub pause`, stale kickstart hint. 17 mutants, 12 killed. Families 580 passed. Merge after #b5-1; deploy+repair safe with the corrected runbook. |
```

IMPRESSIONS.md bullets:

```
- A fence that deletes the producer must delete the consumer: bug-105 r5 removed the async merge and kept `_op_job_status` + `rmx daemon job` + the lock-yield params "for the next async big-op". Grep every reader of the state the removed code wrote (#b5-1).
- A deploy runbook is code: "rmx daemon restart --relaunch" restarts ONE store; the fleet step (`rmx hub relaunch-fleet`) exists because that gap was found once already (plan-4 r1 #b-6) and the bug-105 summary reintroduced it (#s5-1). Check every runbook against the deploy primitives, not the prose.
- DuckDB's "Conflicting lock" is not a backstop under a live daemon: its own snapshot (CHECKPOINT + shutil.copy2 in-process) drops the POSIX lock, and a second process wrote into the live slot (bug-105 r5 #s5-3). Every busy-vs-absent decision is load-bearing; probe the second writer, never assume the lock.
```
