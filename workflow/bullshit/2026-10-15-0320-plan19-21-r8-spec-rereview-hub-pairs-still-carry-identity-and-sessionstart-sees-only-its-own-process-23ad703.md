---
gmd: "0.1"
id: bsd-plan19-21-spec-rereview-r8-23ad703
title: "plan-19 + plan-21 spec re-review r8: every round-7 finding closed; d9ax's two-hub residual is most identity matches, and per-owner SessionStart surfacing reaches only the same process"
severity: SKETCHY
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-rereview-19.0-19.6-21.1
round: 8
tags: [bsd, audit, spec-review, re-review, stm, session, bug-109, bug-115, bug-116, bug-117, plan-19, plan-21]
---

# ch-bsd spec re-review r8 of plans 19 and 21 at `23ad703` {#root}

**Commit reviewed:** `23ad703` on `wave0-spec-reviews` (confirmed with `git log -1`; tree clean).
The revision under review is `4fe8f36`, which touches 19.0, 19.2, 19.6, 21.1, plan-19 and plan-21
(d9ax, d9ay, one-shot migration). No other commit since `331b414` touches a plan-19/21 file.

**`src/` since round 7:** `git diff 331b414 23ad703 -- src/` touches `__init__.py`, `daemon.py`
(+105), `edge_records.py` (new), `ingest_records.py`, `search_hooks.py` and `store.py` (+127).
`stm.py`, `cli.py`, `verbs.py`, `handoff.py`, `hooks.py`, `hub.py`, `scan.py` and `composite.py`
did not change, so every r7-verified cite in those files still holds.

**Written:** 2026-10-15T03:20:32-0700.

**Method:** read-only.
- Re-read every new or changed line cite in the r7 revision at HEAD.
- Ran a `difflib` line map of `daemon.py` and `store.py` (331b414 → HEAD) over every
  `daemon.py:N` / `store.py:N` cite in the 13 spec files.
- Ran `rg` for `Stm(` in `src/` and `tests/`.
- Read `stm.py:225-400`, `:440-470` and `:556-620`, `verbs.py:535-575`,
  `handoff.py:508-575`, `hooks.py:120-345`, `cli.py:1205-1278` and `:1960-2006`, and the bug-115/116
  diff of `daemon.py`.
- Clustered copies of the 60 live `*.focus.json` (scratchpad) with dev `stm.cluster_focus`.
  No store or socket was opened.
- `tools/gmd/lint.py` on the 6 revised files: 0 errors; warnings are single-file dangling-doc
  warnings only.

Nothing was edited under plans, specs or `src/`.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r7-331b414]]
rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: contradicts -> [[feedback_no_silent_failures]]
rel: contradicts -> [[feedback_go_no_go_ranges_not_predrop]]

## Round-7 findings: status {#prior-status}

| r7 id | status | evidence at `23ad703` |
|---|---|---|
| s-1 one hub member merges small clusters | **closed as decided (d9ax)**; the stated residual is the subject of [[#ns-1]] | 19.6 R9: "ELIGIBLE … only when the two member sets share **at least 2 members AND** Jaccard … ≥ `j_return`". The bound is corrected ("|A| + |B| ≤ 6 (union ≤ 5)"), `j_return`'s second use is acknowledged in R9 and in the `#ranges-thresholds` `return` row, and decision rows d9ax are in plan-19 `#decisions` and plan-review. I checked all 7 AC-7i legs by hand: 1/3, 1/5, 1/6, 2/4, 2/10, 4/21 (0.1905) and 2/11 (0.1818). Each threshold mutant flips a leg: 0.21 → 2/10, 0.19 → 4/21, 0.18 → 2/11, ≥ 3 shared → 2/4, and Jaccard-alone → {hub,a}/{hub,b} and 1/5. In IEEE doubles `2/10 == 1/5 == 0.2`, so the boundary is exact. |
| s-2 user-level log and watermark unscoped | **closed in mechanism**; the per-owner rule opens [[#ns-2]] and [[#nm-1]] | 21.1 D6: rows scoped `root` / `owner` / `owner_start`; `read_pointer_errors(*, root=None, owner=None, since)`; `unscoped-row` counted apart; three clauses (pointer, STM hook, truncation); `_errors.seen.<pid>` holding `{pid_start, t}`; `owner: null` rows reported by root and never consumed. D7 prunes the watermark files. D8 gives `record_pointer_error(reason, *, root, owner, **fields)`, with the call sites named (`cli.py:1985`, `:1991`; `verbs.py:562`, `:564`; `stm.py:368`), all correct at HEAD. AC-4b (vii) and (viii) carry the mutations. |
| s-3 two "for one release" legacy reads | **closed** | D3: "`read_pid_pointer` reads only `<pointer_dir>/<pid>.json` … no `src/` path reads it". D6: a one-shot migration with the original `t`, `root`, `migrated_from`, `legacy-unreadable`, a rename to `_errors.migrated.jsonl`, an idempotence key, and legacy pointers deleted. The unvisited-root limit is stated and bounded by the 24 h window (`handoff.py:508`, `window_s=86400.0`, verified). AC-4b (ii) and (vi) are rewritten. A deferral sweep of the added lines finds only the conditional "if a later plan revives slot merging" (19.2 R6), and that is a retirement, not deferred work. |
| s-4 `write` miss never pinned to its row | **closed** | 19.0 AC-6c: "Every child … runs with `CLAUDE_PID` = the test process's pid". The hook leg asserts one stderr line, one `pointer-unresolved` row with `owner` and `root`, and the row in `compose_recall_state`; so does `focus note`. 21.1 AC-4 adds read and write legs. Both mutants are listed. Traced at `stm.py:236-279`: `$CLAUDE_PID` wins when it names an ancestor, and the chain starts at `os.getpid()`, so a test pid that is a parent or grandparent of the `rmx` child is found. |
| m-1 sweep unbounded; "no daemon calls" unasserted | **closed**, with a gap in the new AC ([[#nm-3]]) | 19.0 R2 sets `SWEEP_READ_CAP = 4 MB`, with `sweep_cap` counted. The AC-4d per-sweep leg (six parks, ≤ 4 MB, at most four calls opened, `sweep_cap=2`) is arithmetically consistent with the 1 MB per-event cap. AC-6f adds listeners. |
| m-2 `swept` list breaks the sidecar iterators | **closed** | `<key>.swept.json` is beside `<key>.inflight.json`; `stm.py:468` is `_inflight_path`, verified. AC-4h's second park asserts the sweep and no `sweep-failed` row. |
| m-3 fixture timestamps below `t_lo` | **closed** | R6 "Replay clock" rebases entry `timestamp`s, envelope times and `os.utime` mtimes. The bound is never widened, and the mutation is listed. |
| m-4 (a) (iii-b) impossible | **closed** | 21.1 AC-4b (iii-b): surfaced + `unseen_dropped` = N. The three already-surfaced rows land in `dropped`. Consistent. |
| m-4 (b) `focus show` needs `LINE` | **closed** | `rmx focus topics` (`cli.py:1234`, no argument) prints a footer, also after "no topics yet". `cli.py:1210` is `@click.argument("line")`, verified. |
| m-4 (c) stale `cli.py:1923-1927` | **closed** | The Files row reads `:1926-1930`. |
| m-4 (d) `Stm.__init__` resolver tail | **closed** | R5 gets a `Stm.__init__` row (`stm.py:447`, verified), and AC-6 seeds a `default` ring. AC-6e's third check lists 13 `Stm(` calls; `rg` finds exactly those 13 at HEAD (`cli.py:1083/1563/1968`, `composite.py:106`, `hub.py:565`, `promote.py:167`, `scan.py:540`, `verbs.py:893/934/959/973/1030/1068`). No test constructs `Stm(` without a session argument, so removing the default breaks no existing test. |
| d9ay 19.2 slot merge | **closed** | R6 and AC-10 are RETIRED with reasons, and the original text is kept. `_refresh_replica_now` is a no-op (verified, now `daemon.py:2862-2876`). The bug-113 row is open. The `replica_merge.py` Files row is removed. plan-19 open item 4 is corrected. |

**Totals:** all 4 r7 SKETCHY and all 4 r7 MEH are closed, and d9ax and d9ay are applied.

### `src/` 0.78.2-0.78.3: what moved under the specs {#src-drift}

- **bug-116 deadline drop** (`daemon.py:3217-3272`). A CLI_OPS read that is not in `CLI_WRITE_OPS`
  (`daemon.py:6352`: `partition_add`, `partition_rename`, `stop`) and is still queued past the
  caller's `deadline_s` is not run: it is counted (`_note_expired_read`) and logged at most once a
  minute.
  - The CLI_OPS that plans 19/21 lean on: `memory_recall`, `memory_get`, `memory_search`,
    `memory_recent`, `memory_score`, `subject_list`, `subject_leaves`, `context`, `stats`,
    `ingest_gmd_status`, `mem_mirror_status`.
  - None of the specs adds a CLI_OPS write. The Stop / PreCompact promote is `memory_add`
    (`cli.py:~1327`), a bg-pool write, so it is never dropped.
- **`daemon.call` no longer re-sends after a send** (`daemon.py:629-670`). A post-send timeout
  breaks out of the loop. Only connect timeouts, JSON decode errors, resets and refusals are
  retried. This makes one 19.4 mutation equivalent: [[#nm-6]].
- **`ping` on the dispatcher, heartbeat on cli completions** (bug-115). This changes no spec
  claim. AC-6f's `ping` mutant still dials the socket, so the listener still accepts it.
- **`search_hooks.py` learn switch** and **bug-117 `edge_records.py`.** Neither is touched by
  plans 19/21.
- **Line drift.** `daemon.py` and `store.py` cites moved by +2 to +85 lines: [[#nm-7]].

## Findings {#findings}

### SKETCHY ns-1: d9ax's stated residual, two shared HUB members, is most of the identity matches it still makes; "hub ref" is undefined for R1's figure {#ns-1}

**File:** `task-19.6-phased-context-and-topic-cache.md` R9 "Which live cluster a snapshot stands
for" (**Residual, stated**), R1 (the "two hub members" share), and AC-7i.

**What:**
- d9ax closes the one-member case by construction. The residual it states is
  {hub1, hub2, a} vs {hub1, hub2, b} (J = 2/4), which still makes one line.
- **Measured** on copies of the 60 live focus graphs (`focus_graph(top=30)`, then
  `cluster_focus`; 243 clusters):
  - Hubs were taken as refs present in ≥ 20% of the graphs: `cli.py`, `daemon.py`, `store.py`,
    `__init__.py`, `pyproject.toml`, `refmatrix.store`, plus noise (`p.read`, `p.write`, `save`,
    `state`, a truncated path).
  - Label propagation partitions a graph, so same-graph clusters never share members. Identity is
    a cross-time question, and cross-session pairs are the available proxy for "different topic".
  - **Raw:** 28,900 cross-session pairs. The round-6 rule (J only) represents 623 of them; d9ax
    represents 426, and 310 of those 426 (73%) share hub members only.
  - **Noise stripped** (approximating 19.0's code-noise set; 221 clusters): d9ax represents 217
    pairs, and **136 (63%) rest on hub members only**.
  - 113 of 243 clusters (47%) have at least one other-session cluster that would represent them
    under d9ax.
- **R1 records the two-hub share, but cannot compute it.** "Hub ref" has no definition. The only
  instances are prose (`cli.py`, `daemon.py`), so the figure is unreproducible, and nothing acts
  on it ("recorded figures; Table A's bands and verdicts are unchanged").

**Why it's sketchy:** this is r7 #s-1's pattern one level up. The stated residual is the dominant
case in the measurable proxy. d9ax's acknowledgement covered the rule, not this measurement,
which did not exist when the user decided.

**Fix (needs the user; recommended (a)):**
- **(a) Amend d9ax.** Identity needs ≥ 2 shared members, AND ≥ 1 shared member that is not a hub,
  AND J ≥ `j_return`.
  - Define hub cache-relatively, so `derive_snapshots(graph, cache)` stays pure and adds no
    reads: "a ref that is a member of ≥ ⌈K/2⌉ (= 4) of the topic cache's current snapshots".
  - On the proxy this cuts represented pairs 426 → 116 (computed with the ≥ 20%-of-graphs hub
    definition; the cache-relative definition needs its own R1 figure).
  - AC-7i gains two legs, each with a cache of 4 snapshots that all contain `hub1` and `hub2`:
    {hub1, hub2, a} vs {hub1, hub2, b} gets its own line; {hub1, hub2, a} vs {hub1, a, c} is
    represented (shared non-hub `a`).
  - Add the mutation "hub exclusion dropped".
- **(b) Keep d9ax and band R1's figure.** Define hub as above, and pre-register: if the share of
  representations resting on hubs only is > 25%, adopt (a).
- **Either way:** R1's "hub refs" gets the definition, so the figure is computable.

**Pattern match:** YES ([[bsd-plan19-21-spec-rereview-r7-331b414#s-1]];
[[feedback_go_no_go_ranges_not_predrop]]).

### SKETCHY ns-2: per-owner SessionStart surfacing reaches only the SAME Claude process, so rows from a session that ended, including its last Stop's promote miss, surface on no SessionStart {#ns-2}

**File:** 21.1 R9 D6 ("The SessionStart writer (D4) surfaces its OWNER's rows"), D7, AC-4b (iii)
and (vii); 19.0 R5 Stop row ("the durable channel is the resolver's `pointer-unresolved` row …
which recall-state and the SessionStart surfacing report").

**What:**
- **The mechanism.** The watermark is `_errors.seen.<pid>`, keyed `(pid, pid_start)`. The writer
  surfaces `read_pointer_errors(owner=(P, P_start), …)`.
- **Which SessionStarts can see rows.**
  - A `startup` SessionStart is a NEW Claude process. Its owner has written no rows yet, and pid
    reuse is filtered by `pid_start`.
  - `claude --resume` / `--continue` also start a new process.
  - So only `clear` and `compact` (and an in-process `/resume`) can surface anything, and only
    rows from earlier in the same process.
- **What is lost from the surface.** A session's pointer failures, sweep / composite failures,
  and its FINAL Stop's `write` miss (19.0 R5's "durable channel") are never shown on any
  SessionStart after that process exits.
- **Then D7 prunes the dead pid's watermark.** Those rows reach only `rmx recall-state`.
  recall-state is NOT a hook: the generated SessionStart entries are `rmx curator status`,
  `rmx memory recall --session-start`, `ingest-gmd --detach` and `focus context` on resume
  (`hooks.py:209-297`). So recall-state is a manual surface, with a 24 h window.
- **This is a regression against the r6 design intent.** The SessionStart line was the automatic
  surface "where SessionStart output reaches the agent". It is caused by my own r7 fix
  ("watermark per owner"), which scoped the CONSUMER correctly but dropped the case where the
  owner is gone.
- **AC-4b (iii) passes with a synthetic owner** (the test pid), so it cannot see this.

**Fix:**
- The SessionStart writer surfaces two sets:
  - (1) its owner's rows since `_errors.seen.<pid>`, as written;
  - (2) its ROOT's rows whose owner is DEAD (`_proc_start(owner)` is `None` or ≠ `owner_start`)
    since a per-root watermark `_errors.seen.root.<sha1(root)[:12]>` `{t}`. These are printed as
    `ended_sessions: <reason>=<n>…` and consumed.
- Rows of a LIVE other owner stay untouched. That keeps r7's guarantee that no session consumes
  another live session's rows.
- D7 keeps per-root watermark files. They are tiny and keyed by root, so pruning is not needed;
  alternatively, prune when the root dir is gone.
- **New AC-4b leg (ix):**
  - Helper P2 writes one `pointer-unresolved` row in X, then exits (reaped).
  - P1's SessionStart in X prints `ended_sessions: pointer-unresolved=1` once; a second run
    prints none.
  - A live helper P3's row in X is not printed by P1.
- **Mutations:** "dead-owner rows never surfaced" (the leg fails); "live other-owner rows
  surfaced" (P3's row prints).
- 19.0 R5's Stop row then holds as written.

**Pattern match:** YES ([[bsd-impressions#imp-log-on-read-is-a-write]] family: a sink's scope
decides who it reports to; this time the scope is too narrow).

### MEH nm-1: `ps-failed` rows carry `owner` but `owner_start = null`, so no SessionStart surface can ever match them {#nm-1}

**What:**
- D8: "`write_pid_pointer`'s `ps-failed` row (`stm.py:368`) has its `pid` as the owner", and the
  writer adds `owner_start = _proc_start(owner)`.
- `ps-failed` is written exactly when `_proc_start(pid)` is `None` (`stm.py:362-369`), so
  `owner_start` is always null.
- So the row matches no `(P, P_start)` owner filter, and it is not in `unowned_in_root` (that
  counts `owner: null` only). Only manual recall-state shows it.

**Fix:** D6: "a row whose `owner_start` is null counts as unowned for surfacing
(`unowned_in_root`), whatever its `owner`". Add an AC-4b (vii) sub-leg with a `ps-failed` row
(`_proc_info` monkeypatched for that pid only).

### MEH nm-2: the error log is now machine-wide, and its halving, appends and migration have no lock {#nm-2}

**What:**
- **The halving is a read-modify-write with no lock.** `record_pointer_error` halves with
  `read_text` then `write_text` (`stm.py:305-307`). An append from another process between the
  read and the truncate is lost, and that loss is counted in no `errors-truncated` row.
- **D3 widens who writes.** Before, each root's own processes shared one file. Now every hook and
  MCP server of every project writes the same file, plus 19.0's three new reasons.
- **The migration's idempotence check is check-then-append.** Two SessionStarts in one root at
  once (two sessions in this shared tree, as today) both pass the check and both append.
- **No ordering rule.** The spec does not say the rename happens only after every append
  succeeded. `record_pointer_error` returns `False` when `pointer_dir()` was not created, because
  `global_store_root()` is absent.
- **Live volume is low** (1 row in this repo's legacy log), so this is MEH.

**Fix:**
- One `fcntl.flock` on `<pointer_dir>/_errors.lock` around both the append and the halving. The
  halving writes the kept half to a tmp file, then `os.replace`, under the lock.
- The migration first CLAIMS the legacy file by `os.rename` to `_errors.migrating.<pid>.jsonl`.
  The loser gets `FileNotFoundError`, which is counted and skipped. A later run picks up any
  `_errors.migrating.*` left by a crash.
- The rename to `.migrated` happens only after every append returned `True`.
- AC: two processes append 2,000 rows each while crossing `_ERRORS_MAX_BYTES`, and
  lines kept + Σ `dropped` = rows written + `errors-truncated` rows.

### MEH nm-3: AC-6f misses the global store's daemon socket, names entries by event, and asserts a vacuous exit 0 {#nm-3}

**What:**
- **One socket is not listened on.** Listeners sit at `daemon.socket_path(<sandbox root>)`,
  `hub_sock_path()` and `model_sock_path()`. A hook that dialled the global store's daemon,
  `daemon.socket_path(hub.global_store_root())` (in the sandbox, not a live target, so 23.0's
  audit hook allows it), would hit ENOENT. Every focus entry ends `2>/dev/null || true`
  (`hooks.py:131-147`), so that hook passes with 0 accepts.
- **"Entries" is ambiguous.** "The generated `session-start`, `input`, `tool-pre` and `tool`
  entries" could be read as whole events. Those events also carry `rmx scan-prompt`,
  `rmx memory recall`, `rmx sync --flush-queue` and `rmx curator status`, which dial the daemon
  legitimately.
- **"Each hook exited 0" is always true** under `|| true`.
- **The cite is stale.** `daemon.py:522` is now `:527`.

**Fix:**
- Run the command strings whose argv contains `focus hook --event <e>`, taken from the generated
  block.
- Add a listener at `daemon.socket_path(hub.global_store_root())`, or, stronger: a test-side
  `sitecustomize` (23.0 R4's mechanism) that logs EVERY `socket.connect` with an `AF_UNIX` target
  to a file, and assert the file is empty.
- Replace "exited 0" with "stderr of the un-redirected command is empty", running the argv
  without the `2>/dev/null || true` suffix.

### MEH nm-4: a focus hook envelope with no `session_id` "records nothing and prints one stderr line", and the generated command discards that stderr {#nm-4}

**What:**
- The 19.0 R5 focus-hook row's miss is the one STM-hook failure in the table with no row.
- The `input`, `tool-pre`, `tool` and `say` entries end `2>/dev/null || true`. Per bug-109's own
  docstring (`stm.py:293-295`), "stderr is not a channel" there.
- So the miss is silent on the production path. It is rare: Claude Code sends `session_id`.
- Separately, `Stm(root, "")` is not covered. The row says only "`Stm(root, None)` raises".

**Fix:**
- Add an `envelope-no-session` row (D8-scoped: `root`, and `owner` from `owner_lookup()`) beside
  the stderr line.
- Add an AC-6 leg: an envelope without `session_id` fed to the generated `--event input`
  command, which yields one row and no ring written.
- Make it "a falsy session (`None` or `""`) raises `ValueError`".

### MEH nm-5: opportunities 0.78.2 opens: a recall skipped at its budget is indistinguishable in telemetry, and 19.2's fold hold is unbounded against that budget {#nm-5}

**What:**
- **A budget skip is invisible.** The per-prompt recall (`--timeout 5`) and the SessionStart
  recall (`--timeout 10`) degrade to "recall skipped", `[]` and exit 0 (`cli.py:~12012-12025`).
  - Since 0.78.2 the daemon also drops the queued `memory_recall` read itself, so under load a
    skip is a real outcome that frees the worker.
  - 21.1 R3 writes "one row per call", but no `outcome`, and R11 emits events per item only. A
    skipped prompt looks like "recall ran, delivered 0", or is missing outright.
  - That is exactly the confound 19.5 / 19.6's per-prompt delivery figures cannot afford.
  - 21.3 already has `outcome=timeout` for the nudge, so the pattern exists.
- **19.2's fold competes with recall.** The fold holds `_store_lock` in `bind` holds, and
  `_op_memory_recall` takes `_store_lock` (`daemon.py:~6108`). AC-12 bounds the NUMBER of holds,
  not their duration.

**Fix:**
- **21.1 R3/R4.** The recall row (and the context row) carries `outcome` ∈ `ok`,
  `skipped_budget`, `error`, plus `budget_s`. R7's report prints skipped per channel. 19.5 counts
  `skipped_budget` prompts as attempted with 0 delivered, apart from "no recall".
- **Optional.** Expose the daemon's `_expired_reads` in `stats` / `daemon status`, so R7 can
  reconcile client skips with daemon drops.
- **19.2 AC-12.** Also assert 23.1's `RunResult.max_hold_s` ≤ a stated bound (for example 0.5 s,
  well under the 5 s per-prompt budget). Ownership of the bound stays plan-23's (d9az).
- **21.3.** If the nudge lookup is a daemon read, pass its deadline as `timeout` with
  `retries=0`, so the daemon drops it too.

### MEH nm-6: 19.4's mutation "`retries` left at the default" is equivalent since 0.78.2 {#nm-6}

**What:**
- 19.4 R1 has the hub call `memory_compile` with `retries=0`, "so a timed-out call is never
  re-sent onto a running compile". The mutation list says the default `retries` is killed by
  AC-2's single-flight check.
- Since bug-116, `daemon.call` never re-sends after `sendall` (`daemon.py:650-660`). With the
  default `retries=2`, a post-send timeout breaks out of the loop. The mutant behaves identically
  on the timeout path, and AC-2 ("a second call during a run returns `already_running`") never
  exercises it.
- The cited memory [[feedback_daemon_call_retries_multiply_timeouts]] now holds only for connect
  timeouts.

**Fix:** keep `retries=0` as defence. Replace the mutation with "single-flight guard removed
(AC-2: the second call starts a second compile)", or mark it equivalent and cite 0.78.2. Add one
clause to R1: "0.78.2 `daemon.call` never re-sends after a send; `retries=0` additionally stops a
connect-timeout retry".

### MEH nm-7: line cites drifted with 0.78.2-0.78.3, and four 21.1 cites were already wrong at r7 {#nm-7}

**Drift since `331b414`.** The symbol is unchanged; the line is new.

| file | cite | HEAD |
|---|---|---|
| plan-19 open item 4; 19.2 R6 + rev table | `daemon.py:2814-2828` | `:2862-2876` |
| 19.0 AC-6f + rev table | `daemon.py:522` | `:527` |
| 19.3 | `daemon.py:334` | `:339` |
| 19.3 | `:5180` / `:5191` / `:5193` | `:5265` / `:5276` / `:5278` |
| 19.3 | `:2693` | `:2741` |
| 19.3 | `:1782` | `:1816` |
| 19.4 | `daemon.py:5180` | `:5265` |
| 19.4 | `:3450` | `:3535` |
| 19.4 | `:5191` | `:5276` |
| 19.4 | `:6251` (registration) | (+85) |
| 19.4 | `:3566` / `:3585` | (+85) |
| 19.4 | `:1788-1795` | (+34) |
| 19.4 | `:2708-2716` | (+48) |
| 19.4 | `:2451-2460` | (+48) |
| 19.1 | `store.py:2618` | `:2620` |

**Wrong before r7.** These four were missed by r6/r7.

| file | cite | HEAD |
|---|---|---|
| 21.1 `#facts` line 47 | `_op_context` `daemon.py:4687` | `:4714` |
| 21.1 `#facts` line 47 | `verbs.context` `verbs.py:538` | `:585` |
| 21.1 R11 and `#facts` | `find_memory_any_partition` `store.py:2504` (and `:2504-2524`) | `:2578` |
| 21.1 R3 | `ann_search` `cli.py:10718` | `:10763` |

**Fix:** a cite-refresh pass at the approval commit, cites by symbol plus line, read at write
time.

## Verdict {#verdict}

**9 findings (0 BULLSHIT, 2 SKETCHY, 7 MEH). DIRTY.** Every round-7 finding is closed. Neither
plan has a blocker. The two SKETCHY findings are one design decision (ns-1) and one
surface-scope correction (ns-2).

### Approval readiness, per task {#readiness}

| task | verdict | what is left |
|---|---|---|
| 19.0 | **needs edit pass** (small) | [[#nm-3]] (AC-6f entries and listener), [[#nm-4]] (`envelope-no-session` row), [[#nm-7]] cite. No decision needed. |
| 19.1 | **ready** | one cite ([[#nm-7]]) |
| 19.2 | **ready after cite fix** | [[#nm-7]]; [[#nm-5]]'s `max_hold_s` assertion is recommended, not blocking |
| 19.3 | **ready after cite fix** | [[#nm-7]] |
| 19.4 | **needs edit pass** (small) | [[#nm-6]] (equivalent mutation), [[#nm-7]] |
| 19.5 | **ready** | [[#nm-5]] lands in 21.1 and is consumed here; one sentence ("`skipped_budget` = attempted, 0 delivered") once 21.1 has it |
| 19.6 | **blocked on a user decision** | [[#ns-1]]: amend d9ax with a cache-relative hub exclusion (recommended), or band R1's two-hub share |
| 21.1 | **needs edit pass** | [[#ns-2]] (dead-owner rows on SessionStart, per-root watermark, AC-4b (ix)), [[#nm-1]], [[#nm-2]], [[#nm-5]] (`outcome` on recall rows), [[#nm-7]] |
| 21.2, 21.3, 21.4 | **ready** | unchanged since round 6. [[#nm-5]]'s 21.3 clause is optional. |

- **Plan-21** can go to approval after one 21.1 edit pass and a diff check. No user decision is
  needed: ns-2's fix restores the r6 intent within the r7 scope rule.
- **Plan-19** can go to approval after the 19.0/19.4 edit pass and a cite refresh, plus the
  user's call on ns-1.
  - **Recommendation: (a).** It needs no new number (⌈K/2⌉ from the confirmed K = 8). It keeps
    `derive_snapshots` pure. On the proxy it removes 73% of the remaining hub-only merges.
  - If the user prefers to keep d9ax as decided, (b) adds a band and the hub definition, and no
    other change.

No further full round is needed. A diff check of the edit pass against this report is enough.

## Ledger entries {#ledger}

Appended to `last_run.log`. Per the caller's instruction ("read-only otherwise"), `INDEX.md` and
`IMPRESSIONS.md` were NOT edited this run. The orchestrator may roll this report into
`INDEX.md` as [[bsd-plan19-21-spec-rereview-r8-23ad703]].
