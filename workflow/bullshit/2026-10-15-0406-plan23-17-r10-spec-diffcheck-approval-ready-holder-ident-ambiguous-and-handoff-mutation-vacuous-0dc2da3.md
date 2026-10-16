---
gmd: "0.1"
id: bsd-plan23-17-spec-diffcheck-r10-0dc2da3
title: "plan-23 + plan-17 spec diff check r10: all 10 r9 findings closed at the quoted text. 23.5 and 17.4 are APPROVAL-READY; 7 MEH, no BULLSHIT, no SKETCHY. R1.9's flush and AC-7's RMX_DAEMON_FLUSH_S=3600 case can fail. bug-112's AST test exists and covers private readers. The raw ATTACH sites are not a freshness hazard (measured), so 23.5 does not wait on them. The MEH: writer_holder is ambiguous when one thread has two entries; the hand-off mutation passes vacuously without forced contention (measured); two typed-refusal sites remain; the grep_indexed half cannot discriminate; the hub row has no AC; 23.1's body still states the old owner order; 17.4's unknown-op fixture uses an op Wave 1 adds."
severity: MEH
plan: plan-23-bounded-write-harness
task: spec-diffcheck-r10-23.5-and-17.4
round: 10
tags: [bsd, audit, spec-review, diff-check, plan-23, plan-17, read-path, bitmap-freshness, bug-112, cross-plan, restore, wave-1]
---

# ch-bsd spec diff check r10 of plan-23 task 23.5 and plan-17 task 17.4 {#root}

**Revision reviewed:** `0dc2da3` (round 9, from `git log -1 --
workflow/plans/plan-23-bounded-write-harness-tasks/task-23.5-read-path-and-holder-bounds.md`). It
was diffed against `9dd923c` for these files:
- the 23.5, 17.4 and 23.1 task files;
- the plan-23 and plan-17 headers;
- `workflow/bug_registry.md`;
- `workflow/plan-review-2026-10-14.md`.

**HEAD at write time:** `c8ff69d` on `wave0-spec-reviews`. It moved from `0dc2da3` during the run
through `f6400aa` (plans 19/21), `451b505` (plans 16/22) and `c8ff69d` (ledgers). None of these
touches plan-23, plan-17 or `src/`, and `src/` is 0.78.3 (`b381b6d`). **Written:**
2026-10-15T04:06:25-0700.

**Method.** Read only: no plan or source edit, and no live store or socket.
- **The bug-112 fix branch.** `/Volumes/littlebig/refmatrix-bugs112-118` (branch `bugs-112-113-118`,
  now committed `7c38c46`, `0fed0d5`, `462bd0b`) was read but not run.
- **The DuckDB 1.5.2 probe.** On scratch files: raw `ATTACH … READ_ONLY` held across a replace,
  and the reader chain (scratchpad `att.py`).
- **The `_FairLock` probe.** A simulation of the hand-off, in the old and the new owner order
  (scratchpad `fl.py`).
- **The op census.** A read-only pass over the live `facts.log` files of refmatrix (1.51 M lines),
  global (310 k) and thiquet (scratchpad `ops.py`).

rel: derives-from -> [[bsd-plan23-17-spec-diffcheck-r9-b84fd8d]]
rel: specifies -> [[task-23.5-read-path-and-holder-bounds]]
rel: specifies -> [[task-17.4-factslog-backup-snapshot]]
rel: related-to -> [[plan-review-2026-10-14]]

## r9 findings: status {#prior-status}

| id | status at `0dc2da3` |
|---|---|
| nb23-r9-1 (the snapshot drops dirty bits) | **CLOSED.** R1.9 puts the flush inside `_snapshot_catalog`'s `_store_lock` body, before `CHECKPOINT`, and a flush error is loud. R7/AC-3 add the order check. AC-7 adds the `RMX_DAEMON_FLUSH_S=3600` query case and its mutation. R8 adds the bitmap column. Verification is in [[#verified]]. |
| nb23-r9-2 (the bug-112 gate) | **CLOSED.** The header, plan-23 `#dependencies` and `#tasks` carry the hard gate (OPEN: none of `7c38c46`/`0fed0d5`/`462bd0b` is in the dev repo, and `master` is `b381b6d`). The "known exception" is deleted. AC-7 has the positive case, the chain case and the bare-connect mutation. R1.10 names the opener. |
| ns23-r9-1 (the cross-plan interface) | **CLOSED.** 23.5 stands alone. The edge is `related-to`. Hold 2 is unconditionally plain under `Daemon._inflight("compact")`. `#cross-plan-18` lists five items, consistent with d9bw(c) ([[#cross-plan]]). |
| ns23-r9-2 (the untyped refusal) | **CLOSED** for `_call`. `code` is set in ONE builder (`_note_refused`), `verbs.BUSY_CODES` exists, and AC-2 has an MCP case plus a dropped-code mutation. Residue: [[#nm23-r10-3]]. |
| nm23-r9-1 (the registry value) | **CLOSED.** The value is an `InflightEntry` NamedTuple read by attribute. Both readers (`:1529`, `:1579`) and all five test sites are named. Every `_inflight_ops` reader in `src/` and `tests/` was checked against that list, and none is missing. Residue: [[#nm23-r10-1]]. |
| nm23-r9-2 (the lock passed as a value) | **CLOSED.** The argument rule exists, `_writer_lock` takes `d` (so the rule needs no exemption), and AC-3 has the `_periodic_flush` mutation. |
| nm23-r9-3 a/b/c/d | **CLOSED** in text. (a) hand-off under `_mu`, with a pointer from 23.1. (b) the bounded use-lock seam. (c) `_heartbeat_params()`, with AC-8 set after import (2.6 s). (d) the consecutive-refusal counter, with an AC-5 case that can fail (T_dump comes from row `updated_at`, `store.py:7589-7673`). Residue: [[#nm23-r10-2]] for (a), [[#nm23-r10-4]] for (d). |
| ns17-r9-1 (the torn tail) | **CLOSED.** One `_cut_copy` is shared by the probe and step 2, and the rebuild, the fold and the install all run on the cut copy. AC-9's main (c) run ends torn, and the uncut mutation fails (fold → fallback → `source: backup`). |
| ns17-r9-2 (fold drift) | **CLOSED.** `FOLD_OPS`, an unknown op fails and is named, and an AST pin against `rebuild_index_from_log`'s dispatch (`store.py:7969-8027`, all `op ==` / `op in`). Residue: [[#nm17-r10-1]]. |
| nm-x-r9-1 (bug-119, `--json`) | **CLOSED.** The bug-119 row's scope note retires `apply_log_delta` (d9bu) and separates torn-final (exit 0) from corrupt-interior (non-zero). `rmx rebuild --from-log --json` is in 17.4's files table (`cli.py`). The CLI-tree render (`scripts/gen-cli-tree.py`) shows only commands and help, so the new flag needs no regenerated doc as long as the `rebuild` docstring is unchanged. |

{#prior-status-body}

## Claims verified {#verified}

| claim | result |
|---|---|
| R1.9's flush and the AC-7 `RMX_DAEMON_FLUSH_S=3600` case can FAIL | **Yes.** `Store.link` (`store.py:4622-4650`) only adds the bit to the cache and to `_dirty_fragments`. `_op_link` (`daemon.py:6156`) runs no transaction. The only flushes are COMMIT (`:4564`), `_periodic_flush` (`daemon.py:233`, interval read at thread start `:2103`; 23.1 R6.1 keeps the same `_runner` tick and knob) and close. 23.1 does not move `_op_link` onto `batch_transaction` (grep: no `_op_link` in 23.1). So with a 3600 s flush and no other write, the snapshot without R1.9 lacks the bit, and `query` misses E. |
| `has_dirty_fragments` / `flush_fragments` exist at the cited lines | `store.py:1093` (all bindings, the bug-105 audit) and `:4194` (it flushes every binding under its own partition). |
| bug-112's AST test exists by the cited name and covers private readers | `tests/test_bug112_duckdb_reopen.py::test_every_file_backed_duckdb_connect_goes_through_open_duckdb` exists. It fails on any `<…duckdb…>.connect(<non-:memory:>)` in `src/` outside `backend.open_duckdb`. A private read is `_open_read_store` → `Store(…, read_only=True)` → `DuckDBBackend.connect` → `open_duckdb(read_only=True)` (`backend.py:385`), a `:memory:` instance plus `ATTACH … READ_ONLY` + `USE`. No `import duckdb as` / `from duckdb import` alias escapes it. AC-7's bare-connect mutation fails both the AST test and the chain case. |
| Raw `ATTACH … READ_ONLY` outside `open_duckdb` (`_MemMirror` `daemon.py:465`, `replica_merge` `:195/:471/:594`, `replica_audit`) | **Not a freshness hazard for 23.5.** Measured on 1.5.2: a raw ATTACH of P held in a `:memory:` instance, then a replace, then a fresh RO ATTACH reads the NEW file (case 1). The same holds with a file-backed writer connection holding `ATTACH P`, which is the replica_audit shape (case 2). An ATTACH-only chain A→B→C reads the newest file (case 3). The instance cache that bug-112 fixes is keyed by `duckdb.connect(file)`, and ATTACH from `:memory:` does not use it. These sites matter for WRITE opens: they are unregistered in `_HOLDERS`, so `_close_stale_holders` cannot free a path they hold, which gives "Unique file handle conflict". That is 18.3's and 23.1's reopen concern. **23.5 does NOT need to wait for the bug-batch remedy of those sites.** Its gate is bug-112's read-only opener merged to `master`, and that is already its header gate. |
| `verbs.BUSY_CODES` → `VerbBusyError` | `VerbBusyError(VerbError)` is at `verbs.py:37`, and `_call` maps `ok: false` to plain `VerbError` today (`:219-220`). The change lands at one site. Every existing `except VerbBusyError` in `cli.py` (~25) gets the busy semantics by design. For example, `rmx memory recall` degrades to `_reader_store()` (`cli.py:12117`), which is the documented busy path. |
| `InflightEntry` readers | src: the dispatcher `:3253/:3267`, `_final_flush` `:1529` and `_drain_pool` `:1579`. tests: `test_inflight_registry.py:67, :91, :151, :169-170, :196` and `test_daemon_shutdown_drain.py:148`. The spec names all of them. `:88` and `:131` compare `_names(d)`, which reads through `:67`. The test daemons are bare `dm.Daemon(...)` with no tick threads, so the flakiness argument does not apply to them today. It is harmless. |
| `_heartbeat_params()` | The module constants are read at import (`:63`, `:66`), and the heartbeat re-reads `RMX_HEARTBEAT_S` at start (`:1331`). AC-8's "set after import", giving 2.6 s against 50 s, discriminates. |
| 17.4 `FOLD_OPS` against real logs | The live op sets are a subset of replay's dispatch set: refmatrix has 11 ops, global 6 and thiquet 3, with 0 unparseable lines. No production log carries an op the fold would reject. |
| GMD lint | 0 errors on all five revised files. Warnings are dangling cross-doc ids only. |

{#verified-body}

## Cross-plan consistency {#cross-plan}

23.5 `#cross-plan-18` was read against d9bw and the plan-18 files as the reviser has them now
(18.2 modified in the working tree, 18.3 unchanged since `b84fd8d`). Plan-18 itself is not
reviewed here.
- **Item 5 (18.3 owns the compaction port)** equals d9bw(c) ("Q-C closed: 18.3 owns the port of
  23.5's compaction hold onto `_catalog_hold`").
- **Items 2-4 are already carried by the working-tree 18.2:**
  - its header cites `#cross-plan-18`;
  - the D1 row and R8 use 23.5 R4's ONE `lock hold:` line at a per-label 2 s threshold;
  - R8 lists the flush before `CHECKPOINT`, L0 inside the `_store_lock` body, and the `pin_to`
    link after `_store_lock` but before `_snapshot_lock` as `after_locked` callbacks. This
    matches 23.5 R5.1 and item 3.
- **Not yet applied on the plan-18 side, for the reviser (not findings against 23.5):**
  - 18.2 R11 "The numbers" still says "One `rmxd.log` line is written for any hold over D1's 2 s
    edge, whatever the label" (`task-18.2…:363`). That contradicts its own R8 and item 2.
  - R11 does not yet enter `Daemon._inflight(label)` (item 1).
  - R11 defines only `after` (post-release) callbacks, while R8 relies on `after_locked`.
  - 18.3 R8 still reads "**Not ported**" (`task-18.3…:372`), and Q-C (`:698`) is still open.
- **One gap belongs to 23.5:** item 1 inherits [[#nm23-r10-1]]. A `_catalog_hold` called from a
  bg op gives one thread two entries, and the per-label alarm threshold of item 2 needs the
  INNER label.

{#cross-plan-body}

## Findings: task 23.5 {#findings-235}

### MEH nm23-r10-1: `writer_holder` is "the entry whose ident equals the owner's ident", but one thread can carry two entries, so the name and item 2's per-label threshold are ambiguous {#nm23-r10-1}

- R2's worker-side wrapper sets `ident` for EVERY pool submission, cli and bg (task `:359`).
- R4 adds `Daemon._inflight(name)` entries with `kind="tick"` for `snapshot` and `compact`.
- After R1.4, the `snapshot` op runs on the bg pool. It calls `_snapshot_catalog`, which enters
  `Daemon._inflight("snapshot")`. The `compact_factslog` op enters `Daemon._inflight("compact")`
  in the same way.
- Each case therefore has two entries with the same ident: `op`/`compact_factslog` and
  `tick`/`compact`.
- Under plan-18, `catalog_maintain` (an op) calls `_catalog_hold("<label>")`, and item 2's
  per-label threshold must use the helper's label, not the op's. "The entry whose ident equals"
  picks whichever the dict yields first.

**Fix (spec text, R4 "The name"):** "If several entries share the owner's ident, `writer_holder`
names the most recently registered one (the innermost `Daemon._inflight`). `held_s` comes from
the lock's `_owner_since`. The alarm's label, and any per-label threshold, use the same entry."
AC-6 adds a bg op that enters `Daemon._inflight("inner")` under the lock: `writer_holder.op ==
"inner"`. Mutation: the first match instead of the last FAILS.

### MEH nm23-r10-2: the hand-off mutation passes vacuously unless the test forces hand-offs; measured 0 null-owner samples with the old order and no hold {#nm23-r10-2}

AC-6 says: "Two threads contend `_FairLock` 2,000 times with hand-offs; … Mutation: the owner set
by the woken waiter after `ev.wait` … FAILS."

A simulation of `_FairLock` (`daemon.py:273-323`) with the old and new owner order:

| setup | old order (null-owner samples) | new order |
|---|---|---|
| tight `acquire(); release()` | **0** in 3 runs (350-430 k samples each) | 0 |
| a ~100 µs hold inside, 1,994-1,999 hand-offs per run | 2.3 M-134 M | 0 |

So the case fails only if each holder holds long enough for the other thread to queue. Under
the GIL, a tight loop rarely hands off.

**Fix (AC-6 text):** "each acquire holds ≥ 100 µs (`time.sleep(0.0001)`), and the test counts
hand-offs (a waiter woken by `_pass_or_release_locked`, through a seam counter) and requires ≥
1,000. Fewer fails the case as vacuous."

### MEH nm23-r10-3: the typed refusal is read at `_call` only; `memory_partition` still turns an ANSWERED busy into a guessed partition, and AC-2's `deadline` half cannot be observed through the verb path {#nm23-r10-3}

- **`memory_partition`.**
  - It calls `daemon_mod.call(root, "partition_list", …)` directly (`verbs.py:261`), not `_call`.
  - On `ok: false` it logs and returns the project default (`:271-278`, "An ANSWERED error …
    is the one case the project default is a legitimate guess"). The memory write verbs route
    through it (`memory_add` `:658`).
  - After 23.5, `partition_list` goes through `_cli_read` with `partition=None`, which reaches
    the writer only when `_open_read_store` returns None (`daemon.py:4895-4990`). That is rare,
    but a `writer_busy` answer there is a guessed partition for the next write. That is the
    split-brain family the function exists to prevent (bsd-plan3-r4 #s-4), and R1.1's "read by
    `_call` only" rules it out of the fix.
- **The `deadline` half of AC-2.**
  - `daemon.call` sends `deadline_s = timeout` and sets the socket timeout to the same `timeout`
    (`daemon.py:645-650`).
  - The server's expiry is server-receive + `deadline_s`, which is never before the client's own
    timeout. A `DeadlineExceeded` answer therefore arrives after the client has already raised a
    socket timeout, which `_call` maps to `VerbBusyError` on its transport branch.
  - So "the raw response carries `code: "deadline"`" cannot be observed through
    `rmx_memory_search`, and the class assertion passes without the code.

**Fix:**
- R1.1: `BUSY_CODES` is read by ONE helper, `verbs._raise_for_answer(r, op, root)`, used by
  `_call` AND by `memory_partition`'s answered branch. A busy code raises `VerbBusyError`; only a
  non-busy answered error keeps the logged default.
- AC-2:
  - `memory_partition` against a daemon that answers `partition_list` with `code: "writer_busy"`
    (the `_open_read_store`-None seam) raises `VerbBusyError` and returns no name.
  - The deadline half sends a raw request with `deadline_s=0.2` and a 5 s read timeout, behind a
    cli pool blocked for 0.5 s, and asserts `code: "deadline"`. Its `VerbBusyError` mapping is
    asserted on `_raise_for_answer` directly.

### MEH nm23-r10-4: AC-7's `grep_indexed` half cannot fail under R1.9's mutation; the refusal counter's hub row has no AC and no named key path {#nm23-r10-4}

- **`grep_indexed`.**
  - After 23.5 R3 and 23.1 R9, a learned hit is applied by the learn drain inside 23.1's
    `batch_transaction`, whose COMMIT flushes fragments (`store.py:4562-4566`).
  - So the `grep_indexed` bullet is green with or without R1.9. That is fine as regression
    coverage, but it is not R1.9 coverage, and the mutation clause names only `query`.
  - Fix: say so ("the `grep_indexed` case is regression coverage; R1.9's discriminating case is
    the non-transactional `link` op"), or replace it with an `unlink` op, which is also
    non-transactional (`_op_unlink`, `daemon.py:6167`).
- **The hub row.**
  - The hub carries only health keys it names explicitly into a queue row (`hub.py` ~`:640-700`).
    Hotness then comes from `_queue_row_is_hot` / `_hot_signature` (`:1211`), the pattern 18.2
    R7 spells out.
  - Fix: R5 puts `factslog_compaction_refused` in `stats(include_health)["health"]`, and the
    hub copies it into the row when `>= 1`, with `_queue_row_is_hot` and `_hot_signature`
    naming it.
  - AC-5 adds: the hub row for the store is hot with that reason after the three refusals.
    Mutation: the key not copied FAILS.

{#findings-235-body}

## Findings: task 23.1 (pointer only) {#findings-231}

### MEH nm23-r10-5: 23.1's body and its mutation still state the old owner order; only the header points at the amendment {#nm23-r10-5}

- 23.1 R1.6 item 1 (`task-23.1…:449-452`) still says `_owner` is set "by … the woken waiter
  after `ev.wait` returns True".
- Its mutation list (`:1056-1057`) still names "`_owner` not set on the woken-waiter path".
- The round-9 header line says to build to 23.5 R4's order, so an implementer reads two orders
  in one file.

**Fix (23.1 text):**
- Item 1: "set by the fast path in `acquire`, and by `_pass_or_release_locked` under `_mu` to the
  chosen waiter's ident before `ev.set()` (23.5 R4); the woken waiter does not write it".
- The mutation: "`_owner` not set at hand-off in `_pass_or_release_locked`".

## Findings: task 17.4 {#findings-17}

### MEH nm17-r10-1: the unknown-op fixture is `evidence_remove`, which Wave 1 adds to replay; once it lands, the fixture is a known op and the case flips {#nm17-r10-1}

- AC-9 uses "a fixture live log carrying one event with `op: "evidence_remove"` (not yet in
  replay)".
- d9bl's `evidence_remove` lands in 16.6/22.x in Wave 1, and 17.4 is also Wave 1. Whichever lands
  second breaks:
  - either the fixture is now in `FOLD_OPS` and the unknown-op case passes for the wrong reason
    (it prints `source: live`),
  - or the case must be rewritten at the 22.x commit.

**Fix (AC-9 text):** the fixture op is a reserved name no replay will ever dispatch
(`op: "__rmx_test_unknown_op__"`). The test asserts that name is absent from the AST-read dispatch
set, so the precondition cannot silently go false.

{#findings-17-body}

## Approval readiness {#approval}

| task | verdict | what remains |
|---|---|---|
| 23.5 | **APPROVAL-READY** | [[#nm23-r10-1]]..[[#nm23-r10-4]] are spec-text edits, and none changes the design. The implementation gate stays OPEN: bug-112's fix is not reachable from `master`, and the branch sha set will grow (d9bw(d) adds `_writer_lost` before merge), so the gate command should use the MERGE sha. 23.5 does NOT wait on the raw-ATTACH remedy ([[#verified]]). |
| 17.4 | **APPROVAL-READY** | [[#nm17-r10-1]] (one fixture name). |
| 23.1 | READY (unchanged) | [[#nm23-r10-5]] (a two-line text sync with the round-9 pointer). |

{#approval-body}

## Verdict {#verdict}

**DIRTY (MEH only). 7 findings: 0 BULLSHIT, 0 SKETCHY, 7 MEH.**
- All 10 r9 findings are closed at the quoted text. Every load-bearing claim was checked:
  - against `src/` 0.78.3: the R1.9 flush path, the `InflightEntry` readers, `BUSY_CODES`'s
    single site, and `_heartbeat_params`;
  - against the bug-112 branch: the AST test name and its coverage;
  - by measurement: raw ATTACH freshness, the `_FairLock` hand-off, and the live log op sets.
- Trend for plans 23/17: 19 → 17 → 10 → 9 → 9 → 11 → 10 → **7 (0B/0S)**.

{#verdict-body}

rel: contradicts -> [[claude#no-silent-failures]]
