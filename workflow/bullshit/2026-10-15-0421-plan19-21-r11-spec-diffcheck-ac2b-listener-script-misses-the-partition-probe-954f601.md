---
gmd: "0.1"
id: bsd-plan19-21-spec-diffcheck-r11-954f601
title: "plan-19 + plan-21 r11 diff check: every r10 finding closed and the 23.0 amendment matches its implementation, but AC-2b's new listener scripts model [ping, recall] while the hook's real traffic is [ping, partition_list, ping, recall], so both new legs fail at GREEN"
severity: SKETCHY
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-diffcheck-19.0-19.6-21.1-21.3
round: 11
tags: [bsd, audit, spec-review, diff-check, stm, helix, d9bx, d9ca, plan-19, plan-21, plan-23]
---

# ch-bsd r11 diff check of plans 19 and 21 at `954f601` {#root}

**Commit reviewed:** `954f601` on `wave0-spec-reviews` (confirmed with `git log -1`). The diff
`f6400aa..954f601` over `workflow/plans/plan-19-*`, `workflow/plans/plan-21-*` and
`task-23.0-test-sandbox.md` covers 9 files, +349/-66. `git diff f6400aa 954f601 -- src/` is empty.

**Written:** 2026-10-15T04:21:36-0700.

**Method:** read-only.
- Read the full diff against [[bsd-plan19-21-spec-diffcheck-r10-f6400aa]] and against decisions
  d9bx, d9ca and d9at (`workflow/plan-review-2026-10-14.md:373`, `:403`, `:406`).
- Read these code facts at HEAD:
  - `cli.py:11122-11225` (`_memory_partition_default`, `_legacy_memory_partition_exists`);
  - `cli.py:12004-12025` (`_left`, `_degrade_or_raise`) and `:12185-12245` (the recall legs);
  - `discovery.py:150-226`, `daemon.py:41-42`, `:527-533`, `:571-720`, `verbs.py:194-221`;
  - `telemetry.py:96-118`, `hooks.py:26` and `:311-315`.
- Read the 23.0 implementation at `/Volumes/littlebig/refmatrix-task-23.0`, HEAD `7ba1dd4`
  (`tests/sandbox_site/rmx_sandbox.py:53-58`, `:423-541`, and `sitecustomize.py`), read-only.
- Hand-checked these: AC-7i H5 (both orders), H6's next-prompt leg, the record-cap rule and its
  leg, and every AC-2b leg traced through the hook's real daemon traffic.
- Ran `tools/gmd/lint.py` on all 9 files: 0 errors.

No live store or socket was opened. Nothing under `plans/`, `src/` or the littlebig clone was edited.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r10-f6400aa]]
rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: depends-on -> [[task-23.0-test-sandbox#rev-amend-r10]]

## Round-10 findings: status {#prior-status}

| r10 id | status | evidence at `954f601` |
|---|---|---|
| s10-1 H5 order | **closed** | H5 now runs both input orders. **By hand, order (a), N1 first, with the per-cluster mutant:** N1's J = 2/11, so it gets a new S4. The recompute then sees 4 of 4 snapshots holding `hub1`/`hub2`, so both are hubs, and {`hub1`, `hub2`, `b`} has no eligible snapshot: it gets its own line. The spec's answer is S3, so the mutant is killed. Order (b) pins that the result does not depend on order. A one-call AST check (no loop, no comprehension) is added, and it has a planted failing fixture. |
| s10-2 AC-2b reach | **budget leg closed. The non-budget and mid-answer legs are new defects:** [[#s11-1]] | The busy precondition is correct: `daemon.pid_path` is `rmxd.pid`, the same file `discovery._read_pid` reads, and `ps -o command=` shows `rmx-sandbox-helper`. The JSONDecodeError tuple entry and the verb-route sentence are added. |
| s10-3 23.0 interfaces | **closed** ([[#amend-23-0]]) | |
| m10-1 cache contract | **closed.** Residue: [[#m11-3]], [[#m11-4]] | `topic_match: dict[str, str]` keyed by `cluster_cid`. `load_topic_cache` treats a missing file and `{}` as an empty cache. The state does not gate eligibility. The 64-record cap is in place. The import-check clauses are replaced. The header and 21.1 R9 are updated. |
| m10-2 `proc_identity` | **closed.** Residue: [[#m11-2]] | The allowed `_proc_start(` set is now {`owner_alive`, `liveness_available`, `proc_identity`}. |
| m10-3 `unseen_dropped` | **closed** | Counts are carried only above the watermark. The stale sentence is replaced, and the news leg is added to (x). |
| m10-4 outcome home | **closed.** Residue: [[#m11-1]] | `OUTCOMES_BY_KIND` is defined empty in 21.1. 21.3 R3 adds the `"nudge"` entry, routes the row through `log_query`, adds a Files row and has two mutations. |
| m10-5 residue | **closed** | 19.0 has `control.log` and the `say` envelope carries a `session_id`. In 19.2, no finalize hold: R5's same-transaction offset commit is confirmed at `task-19.2…md:122-123`. 21.1's (xiii) RED list is updated. |

### The reviser's two additions {#additions}

1. **21.1 set (1): "own rows skipped: process lookup unavailable". ACCEPTED.** This is the right
   sibling of set (2)'s `ended_sessions skipped` line. Two things are left:
   - no AC asserts the line;
   - the migration's claim name has no matching `None` case.

   Both are in [[#m11-2]].
2. **19.0 AC-6f: the deny-set control's refused target also goes to `control.log`. ACCEPTED.**
   - It tests (a)'s "BEFORE the deny check" ordering in the consumer.
   - 23.0 AC-3 (a) asserts the same ordering in the provider.
   - The implementation does it: `_hook` calls `_log_unix_connect` before `violation`
     (`rmx_sandbox.py:438-440`).

### The 23.0 R4 amendment {#amend-23-0}

**Verified against `7ba1dd4`. It is purely additive to the approved 23.0 (d9at).**

| amendment text | implementation |
|---|---|
| (a) one `<target path>\t<pid>` line per `AF_UNIX` `socket.connect`, written BEFORE the deny check | `_log_unix_connect` writes `f"{path}\t{os.getpid()}\n"`, and only for `family == AF_UNIX` (`:461-477`). It runs before `violation()` (`:438-440`). |
| (a) a log path in the deny set exits 86 at install | `install_from_env` (`:513-519`) |
| (b) an absolute `.py` path, run with `runpy.run_path` AFTER `install_from_env()` installs the hook; a non-absolute path, a non-`.py` path or a raise exits 87 | `_run_preload` runs after `install(deny, mode="exit")` (`:521-541`) and catches `BaseException`. Its stderr line is `SandboxPreloadError: <path>: <Type>: <msg>`. |
| (c) `CHILD_EXIT = 86`, `PRELOAD_EXIT = 87` by name | `:57-58` |

**What the amendment leaves alone:**
- R1-R3, R5-R9, AC-1, AC-2 and AC-4 to AC-8 are untouched.
- The original R4 refusal ("exits the child nonzero") is still true, since 86 is nonzero.

**Not a plan-19/21 finding, but blocks 23.0's own merge:** none of AC-3's amendment legs has a
test at `7ba1dd4`. `git grep` finds `CONNECT_LOG`, `SANDBOX_PRELOAD`, `PRELOAD_EXIT` and
`CHILD_EXIT` only in `rmx_sandbox.py`, not in any `tests/test_sandbox_*.py`. The 23.0 implementer
must add those legs before merge. Until then, 19.0 AC-6f and 21.3 AC-5 stay blocked, as both say.

### Helix interface 2 and d9ca {#helix}

**The frozen contract is complete apart from two pins.**
- **What is in place:**
  - the functions: `match_snapshots`, `topic_hubs`, `snapshot_eligible`, `member_jaccard`,
    `derive_snapshots -> (cache, topic_match)`, `load_topic_cache` and `cluster_cid`;
  - the persisted shapes: `topic_match: dict[str, str]`, cache `schema: 1` with `state` per
    record, and the 64-record cap;
  - the rule that `state` does not gate eligibility;
  - the rule that a change after merge needs a decision row that names helix.
- **What is still missing:**
  - the byte serialization of the `cluster_cid` hash ([[#m11-4]]);
  - the exact eviction candidate set ([[#m11-3]]).
- **One hash.** `cluster_cid` is the single hash. It now includes 19.4 R6's `unlabeled-<h>` slug
  (`task-19.4…md:101`), as d9ca requires.
- **The cap is sound and testable in shape.** Evicting a record that no live cluster chose cannot
  change the greedy `match_snapshots` assignment: an unchosen candidate was never anyone's argmax.
  So the persisted `topic_match` still agrees with a helix recomputation on the evicted cache.

## Findings {#findings}

### SKETCHY (SUSPICIOUS) s11-1: AC-2b's non-budget and mid-answer listener scripts assume the hook sends [ping, recall]; at HEAD it sends [ping, `partition_list`, ping, `memory_recall`], so both legs end in `VerbAbsentError` and exit 1 {#s11-1}

**File:** 21.1 AC-2b, the non-budget leg ("answers exactly ONE ping … then closes its listening
socket") and the mid-answer leg ("answers the ping, then accepts the recall connection and closes
it"). R4 "Two routes reach the degrade path".

**What the hook actually sends.** The sandbox root has no replica, so `_replica_memory_recall`
returns `None` at `modelsrv.shared_available`. The hook runs `--stdin-json … --timeout 5` with no
`--partition` and no `RMX_PARTITION`, and it contacts the daemon socket in this order:
1. `_memory_partition_default(timeout=_left(10.0))` (`cli.py:12193`) calls
   `_legacy_memory_partition_exists`. With no reader store, that calls `daemon_mod.ping(root)` with
   the default `retries=2` (`:11202`).
2. If that ping answers, it then calls `daemon_mod.call(root, "partition_list", retries=0)`
   (`:11208`). The probe catches every exception from that call and prints a warning.
3. `require_daemon(root, retries=0)` makes a second ping (`:12226`).
4. `_memory_daemon_call("memory_recall", retries=0)` (`:12240`).

**Non-budget leg as written:**
- The listener's one answered ping is used up by step 1.
- Step 2 is refused. The probe catches it and prints a warning.
- Step 3 is refused, and the leg has no pid file, so the result is `VerbAbsentError`. That is a
  `ClickException`, so the command exits 1 (`cli.py:12230-12234`).
- The AC expects exit 0, `[]` and `outcome=error`.

**Mid-answer leg as written:**
- The answered ping is step 1.
- The "recall" connection that the listener accepts and closes is actually step 2, and the probe
  swallows it.
- Step 3's ping then meets a closed connection, so the result is again `VerbAbsentError` and exit 1.

**A race in the mid-answer leg.** A listener that closes WITHOUT reading the request races the
client's `sendall`:
- If the close wins, the client gets `BrokenPipeError`. Note that `classify_outcome` maps
  `BrokenPipeError` to `consumer-closed` today (`telemetry.py:110-113`), ahead of any
  `budgeted` branch.
- If the peer has unread data, the client can get `ECONNRESET`.

So even when the leg reaches step 4, the "`JSONDecodeError` left out of the tuple" mutant is not
killed deterministically.

**Severity.** This is not a vacuous pass. Both legs fail loudly at GREEN against a correct
implementation, which pushes the implementer toward bending either the test or the code. It is the
r10 s10-2 family again: an AC leg that does not reach the code it names.

**Fix (edit 21.1 AC-2b and R4):**
- **AC-2b, the listener.** Replace both listener sentences with:
  > The test listener is an op dispatcher. It reads each request line and answers by its `op`:
  > `ping` gets `{"ok": true}`, and `partition_list` gets
  > `{"ok": true, "result": {"rows": []}}`. It records the op sequence. At HEAD the hook's
  > traffic is `ping` (the legacy-partition probe, `cli.py:11202`), `partition_list` (`:11208`),
  > `ping` (`require_daemon`, `:12226`), then `memory_recall`.
- **Non-budget leg.** Add:
  > After answering the SECOND `ping`, the listener closes its listening socket and leaves the
  > file, so the `memory_recall` connect raises `ConnectionRefusedError`. Assert:
  > - the recorded ops are exactly [`ping`, `partition_list`, `ping`];
  > - exit 0 and `[]`;
  > - one `kind=recall` row with `outcome=error` and `error` starting `ConnectionRefusedError`;
  > - no recall event.
- **Mid-answer leg.** Add:
  > On `memory_recall`, the listener reads the full request line, then closes without replying,
  > so the client's `recv` sees EOF and `json.loads(b"")` raises. Assert:
  > - the recorded ops are exactly [`ping`, `partition_list`, `ping`, `memory_recall`];
  > - exit 0, `[]`, and no traceback;
  > - `error` starts `JSONDecodeError`.
- **R4, the route list.** Replace "Two routes reach the degrade path … (1) … (2) …" with:
  > Every `VerbBusyError` reaches the degrade path: `_left`'s deadline (`cli.py:12007`), the
  > partition probe's catch (`:12195`), the replica leg (`:12214`) and `require_daemon`'s busy
  > classification (`:12226`). Each is classified `skipped_budget`. The recall op's transport
  > `OSError` and `json.JSONDecodeError` (`:12241`) are classified `error`. Under
  > `budgeted=True`, the `OSError` test runs BEFORE the existing `BrokenPipeError` →
  > `consumer-closed` mapping, so a daemon-socket broken pipe is `error`, not `consumer-closed`.
- **Mutation.** Add: "the listener's op sequence drifts (a new daemon contact before
  `require_daemon`): AC-2b's sequence assertion fails, so the leg cannot silently stop short
  again."

**Pattern match:** YES. This is r10 s10-2, one layer further in: the precondition was fixed, but
the traffic model was not.

### MEH m11-1: the `"nudge"` outcome tuple has no `error`, so a nudge that raises is rewritten to `outcome-invalid: error` and loses its exception text {#m11-1}

**File:** 21.3 R3 (`OUTCOMES_BY_KIND["nudge"] = (…)`).

**What:**
- `log_query.__exit__` classifies an exception as `error` (`telemetry.py:118`).
- 21.1's validation then finds `error` missing from the nudge tuple and rewrites `error` to
  `"outcome-invalid: error"`.
- The real exception type and message are lost, and `--agent-usage` counts every genuine nudge
  failure as `outcome-invalid`.

**Fix:** append `"error"` to the tuple:
`("fired", "dedup", "gated", "not_identifier", "not_indexed", "disabled", "stale_set",
"skipped_budget", "error")`. Also add `error` (an exception in the hook) to R3's prose list.

### MEH m11-2: the migration claim's `proc_identity(os.getpid())[1]` raises `TypeError` when lookup is unavailable, and the new set (1) line has no assertion {#m11-2}

**File:** 21.1 D6 migration step 1 (`task-21.1…md:511`), set (1) (`:421-422`), AC-4b (ix)
pruning leg (`:1067-1070`).

**What:**
- **The claim.** `proc_identity` returns `None` when `_proc_start` fails. The claim is gated only
  on adoption by `liveness_available()`, not on the claim itself, so `None[1]` raises.
- **The new line.** AC-4b (ix)'s leg that makes `_proc_info` return `None` asserts only the
  `ended_sessions skipped` line. The reviser's new `own rows skipped` line is printed on the same
  run, and nothing checks it.

**Fix:**
- **D6 step 1:** add "When `proc_identity(os.getpid())` is `None`, the migration does not claim
  and prints `migration skipped: process lookup unavailable`; the legacy file is left in place
  for the next SessionStart."
- **AC-4b (ix):** after "prints `ended_sessions skipped: process lookup unavailable`", add "and
  `own rows skipped: process lookup unavailable`, and with a legacy `_errors.jsonl` present,
  `migration skipped: process lookup unavailable`, with the legacy file and the owner's watermark
  file unchanged".

### MEH m11-3: the record-cap rule leaves four things open: the hub-window claim is conditional, the tie order is not the reverse of "newest", the over-cap case with no candidates is unstated, and no leg pins "unmatched" {#m11-3}

**File:** 19.6 R3 "Record cap", AC-7i2 record-cap leg, mutations, plan-19 header item 2.

**What:**
- **The hub-window claim.** "Eviction never touches the 8 newest" is true only while there are
  enough evictable records older than the window. `expanded` and matched records are not
  evictable, and their number is not bounded.
- **Tie order.** `topic_hubs` ranks "newest" by `turn` with ties going to the smaller `<cid>`
  (`:263-264`). Eviction takes the oldest `turn` with ties also going to the smaller `<cid>`. That
  is not the reverse order. Records snapshotted on the same prompt share a `turn`, so ties are
  common.
- **No candidates.** Nothing says what happens when the cache is over 64 and no candidate is
  left.
- **"Unmatched" is untested.** The leg has no matched old record, so a cap that evicts a record
  `topic_match` maps to survives. Its `<cid>` would then be missing from the cache the render
  reads.
- **"Between prompts".** "Between prompts the file holds at most 64 records plus that prompt's new
  snapshots" really describes the state between the input hook's two writes. The header says "at
  most 64".

**Fix (replace the sentence in R3 starting "evicts, while the cache holds more than 64"):**
> evicts, while the cache holds more than 64, the oldest candidate. A candidate is a `collapsed`
> record that this prompt's `topic_match` does not map to and that is not among the 8 newest by
> `topic_hubs`' order. "Oldest" is the exact reverse of that order: the smallest `turn`, ties
> going to the LARGER `<cid>`. An `expanded` record is never evicted. When no candidate remains,
> eviction stops, and the overflow is counted `topic-cache-over-cap=<n>` on the same event.
> `topic_hubs` is therefore unchanged by construction.

Also make these edits:
- In R3, change "between prompts the file holds at most 64 records plus that prompt's new
  snapshots" to "after the second write the file holds at most 64 records (plus any counted
  over-cap); between the input hook's two writes it may also hold that prompt's new snapshots".
- In the header, change "the file holds at most 64 records" to "the input hook's second write
  leaves at most `TOPIC_CACHE_MAX = 64` records (PROVISIONAL, d9ca)".
- In AC-7i2's record-cap leg, use: "a cache of 64 records (the oldest `expanded`; the second-oldest
  represented by a third live cluster on this prompt) plus 2 new clusters leaves 64 records. The
  3rd- and 4th-oldest records are gone; the `expanded` record and the matched record are kept;
  `topic-cache-evicted` = 2; every `<cid>` in `topic_match` is in the written cache".
- Add a mutation: "the cap evicting a record `topic_match` maps to (AC-7i2: the matched record is
  gone)".

### MEH m11-4: `cluster_cid`'s byte serialization is not pinned, and 19.4 has no Files row to build it if it merges first {#m11-4}

**File:** 19.6 R9 (`:247-248`), 19.4 R6 (`:101`) and its Files table (`:178-182`), plan-19
header item 2.

**What:**
- **The serialization.** "sha256 over the sorted member names" does not say how the names are
  joined. With `"".join`, {`ab`, `c`} and {`a`, `bc`} hash the same. The value is persisted in
  cache files, in `pre.json` and in `MEMORY.md` subject slugs, and the helix freeze covers it.
- **The build order.** Neither 19.4 nor 19.6 depends on the other. 19.4's Files table has no
  `stm.py` row, so if 19.4 merges first, `stm.cluster_cid` has no builder.

**Fix:**
- In both R9 and R6, replace "the first 8 hex chars of sha256 over the sorted member names" with
  "`hashlib.sha256("\n".join(sorted(members)).encode("utf-8")).hexdigest()[:8]`".
- Add 19.4 Files row: "| `src/refmatrix/stm.py` | `cluster_cid(members)`, 19.6 R9's ONE
  member-set hash (d9ca); built here or by 19.6, whichever merges first |".
- Add `stm.cluster_cid` and its formula to header item 2.

### MEH m11-5: 19.0 AC-6f's "the file is empty" passes vacuously if a hook command's interpreter never loaded 23.0's hook {#m11-5}

**File:** 19.0 AC-6f, the connect-log paragraph.

**What:**
- The two controls are `python -c` children. They prove that the hook loads in THAT interpreter,
  not in the generated `rmx …` commands.
- A command whose interpreter skips `sitecustomize` writes nothing, so `connects.log` is empty and
  the assertion passes. Examples: a `-I` / `-E` / `-S` shebang, or a different `rmx` on `PATH`.

**Fix:** after "after the runs the file is empty", add:
> Each command also runs with `RMX_SANDBOX_PRELOAD=<tmp>/mark.py`, a test-owned file that appends
> its pid to `<tmp>/loaded.log` (23.0 R4 (b)). `loaded.log` gains at least one line per command
> run, so an empty `connects.log` cannot come from a child that never installed the hook.

### MEH m11-6: text residue {#m11-6}

- **19.6 mutation list.** "`match_snapshots` skipping `expanded` records (AC-7i H6's next prompt:
  the expanded cluster gets a new `<cid>`)": with S3 skipped, {`hub1`, `hub2`, `b`} still
  matches S2 at J = 2/4 (the newest remaining tie). Replace the parenthetical with "(AC-7i H6's
  next prompt: the cluster maps to S2, not S3)".
- **21.1 R4, verb route.** "unless the verb layer gains the same typed split; that change is out
  of this task's scope and is not claimed" is an open-ended hedge (rule 9a). Replace from "so rows
  written on that route" to the end of the sentence with: "so rows written on that route are
  classified with `budgeted=False` by design: an MCP call carries no hook budget, and a busy
  daemon there is an `error` the agent saw".

## Verdict {#verdict}

**7 findings (0 BULLSHIT, 1 SKETCHY, 6 MEH). DIRTY.**
- Every r10 finding is closed at its quoted text.
- Both reviser additions are verified.
- The 23.0 amendment matches `7ba1dd4` and is purely additive.
- `cluster_cid` is the single hash, including 19.4 R6's slug.

### Approval readiness, per task {#readiness}

| task | verdict | what is left |
|---|---|---|
| 19.0 | **ready after a one-sentence edit** | [[#m11-5]]. AC-6f stays blocked until 23.0 merges with its AC-3 amendment legs tested |
| 19.1, 19.2, 19.3, 19.5 | **ready** | |
| 19.4 | **ready after a one-row edit** | [[#m11-4]] |
| 19.6 | **ready after text edits** (helix-facing) | [[#m11-3]], [[#m11-4]], [[#m11-6]] |
| 21.1 | **needs edit** | [[#s11-1]] (listener op dispatcher, the sequence assertion, the route list), [[#m11-2]], [[#m11-6]] |
| 21.2, 21.4 | **ready** | |
| 21.3 | **ready after a one-word edit** | [[#m11-1]]. AC-5 is blocked on 23.0's merge |

**Next step:** one edit pass covering 21.1 AC-2b/R4 and the MEH text above, then a diff check
against this report.

## Ledger {#ledger}

Appended to `last_run.log`. Per the caller's "read-only otherwise", `INDEX.md` and
`IMPRESSIONS.md` were not edited.
