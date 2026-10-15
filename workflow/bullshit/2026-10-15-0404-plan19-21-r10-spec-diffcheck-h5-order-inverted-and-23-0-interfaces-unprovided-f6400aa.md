---
gmd: "0.1"
id: bsd-plan19-21-spec-diffcheck-r10-f6400aa
title: "plan-19 + plan-21 r10 diff check: every r9 finding closed and all four reviser departures verified; H5 now feeds its mutant the order that hides it, AC-2b's legs stop at require_daemon, and 23.0 neither specifies nor implements the two env interfaces the specs consume"
severity: SKETCHY
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-diffcheck-19.0-19.6-21.1-21.3
round: 10
tags: [bsd, audit, spec-review, diff-check, stm, helix, d9bx, plan-19, plan-21]
---

# ch-bsd r10 diff check of plans 19 and 21 at `f6400aa` {#root}

**Commit reviewed:** `f6400aa` on `wave0-spec-reviews`. `git log -1` confirmed it, and it is also
the last commit to touch `task-21.1`. The diff `ebccb20..f6400aa -- workflow/plans/plan-19-*
workflow/plans/plan-21-*` covers 7 files, +505/-151. `git diff ebccb20 f6400aa -- src/` is empty.

**Written:** 2026-10-15T04:04:03-0700.

**Method:** read-only.
- Read the full diff against [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]] and against d9bx
  (`workflow/plan-review-2026-10-14.md:403`).
- Read these code facts at HEAD:
  - `telemetry.py:13`, `:96-118` and `:405-440` (`classify_outcome(exc_type, exc_val)`);
  - `cli.py:12005-12030` (`_degrade_or_raise`), `:12200-12245` (the recall legs), `:8990-9013`
    (`_resolve_query`), `:11225-11237` and `:1995-2011` (the `say` branch);
  - `scan.py:1036-1054`; `stm.py:127`, `:197-262` and `:346-392`; `hooks.py:128-154`;
  - `verbs.py:194-221` (`require_daemon`, `_call`), `discovery.py:162-226` (`daemon_status`,
    `pid_is_rmx`) and `daemon.py:622-668` (`call`).
- Read the 23.0 sources:
  - its spec on this branch, `task-23.0-test-sandbox.md`, last touched at `8a81112`;
  - the in-flight implementation at `/Volumes/littlebig/refmatrix-task-23.0`, HEAD `26f80f2`
    (`tests/sandbox_site/sitecustomize.py`, `rmx_sandbox.py`).
- Hand-checked AC-7i H5, H6, H7 and H8, the m9-3 roll-up algebra, and the consumed-by-owner set.
- `tools/gmd/lint.py` on all 7 files: 0 errors. The only warnings are dangling-doc warnings from the
  single-file scan.
- Deferral sweep of the added lines: there are two "blocked until 23.0 provides" lines. Each is
  anchored to d9bx and to 23.0 R4, so neither is an unanchored deferral. Their provider is missing:
  see [[#s10-3]].

No live store or socket was opened. Nothing under `plans/`, `src/` or the littlebig clone was edited.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r9-ebccb20]]
rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: depends-on -> [[task-23.0-test-sandbox]]

## Round-9 findings: status {#prior-status}

| r9 id | status | evidence at `f6400aa` |
|---|---|---|
| s9-1 assignment home | **closed.** H5 regression: [[#s10-1]]. Contract details: [[#m10-1]]. | 19.6 R9 now has one function per rule: `member_jaccard`, and `match_snapshots` (hubs once, a defined order, highest J, tie-breaks, one live cluster per snapshot). `derive_snapshots` makes one call and returns `(cache, topic_match)`. R3 states the cache contract (`schema: 1`, `state`, and the reader raises on any other schema). `topic_hubs` counts every record. The header's interface 2 is updated. H6, H7, H8 and AC-7i2 are added. The import check has a failing control. **H8 by hand:** J = 2/5 and 3/5, both eligible, so the 4-member cluster takes S. The input-order mutant gives the 3-member cluster S, so H8 kills it. |
| s9-2 `t` watermark | **closed.** Count residue: [[#m10-3]]. | D6 set (2) is consumed by owner (`consumed: [[pid, pid_start, t_max]]`), and rows above `t_max` still show. The prune rule holds: every row with `t ≤ t_max` lies outside the 24 h `since` window once `t_max` does. AC-4b (ix) is reordered so that P3 (live) writes first. The `t`-only mutant never prints P3's older row, so it fails. |
| s9-3 two `sitecustomize` | **closed in 19.0 / 21.3 text.** The provider is missing: [[#s10-3]]. | AC-6f adds no second hook and has two control legs. 21.3 AC-5 uses the preload. |
| s9-4 prose envelope | **closed** | `read_hook_envelope(…, prose_ok=) -> HookEnvelope`, with the prose fallback inside it. `HOOK_PROMPT_KEYS` holds scan's four keys in scan's order (`scan.py:1050`). The behaviour changes on both paths are recorded and match d9bx. `--stdin-json` keeps its `ClickException`. (xiii) is added. |
| m9-1 liveness | **closed in mechanism.** Allow-set gap: [[#m10-2]]. | `liveness_available()` exists, and `read_pid_pointer` goes through `owner_alive`. That change is safe: `write_pid_pointer` never writes a null `pid_start` (`stm.py:366-369`). The `_proc_info(` set {`_proc_start`, `owner_lookup`} matches `stm.py:201`, `:249`. |
| m9-2 write-scoped check | **closed** | `errors_log_path()`, the write-op list and a planted-fixture control. |
| m9-3 roll-up | **closed, departure accepted** ([[#departures]]). One stale sentence and the `unseen_dropped` semantics: [[#m10-3]]. | |
| m9-4 claim adoption | **closed** | The claim name now carries `start_token`. A claim is adopted only when `owner_alive(…, start_token=) is False`. A final-rename loss is counted. The `legacy-unreadable` row takes `t` from the legacy mtime, and `os.rename` keeps that mtime through adoption. (xi) has the one-day-old leg. |
| m9-5 outcome classification | **closed in the classifier.** AC-2b cannot reach that code: [[#s10-2]]. Nudge vocabulary: [[#m10-4]]. | |
| m9-6 hold count | **closed** | `holds == 2` is asserted structurally, and the clock check is "within 50 ms". The finalize hold is still conditional ("if the fold takes one"): [[#m10-5]]. |
| m9-7 residue | **closed** | The "K = 8" parentheticals are deleted, the RED sentences are split, and AC-6f now runs the `say` event (`hooks.py:152-154`; `cli.py:2005-2011` calls no daemon, as stated). |

### The reviser's departures and extra fixes {#departures}

1. **m9-3: `dropped` counts only non-truncation rows, plus the rolled-up counts. ACCEPTED; this is
   better than my "+ T" form.**
   - **Algebra.** Before a halving, N_file + D_file = A. The halving removes k non-truncation rows
     and truncation rows whose counts sum to Σd. It writes a new truncation row with
     `dropped` = k + Σd. Afterwards: (N_file − k) + (D_file − Σd + k + Σd) = A. The identity holds
     at any number of halvings, and no reader has to count truncation rows that are already gone.
   - **Per root.** The same algebra holds over `dropped_by_root`.
2. **s9-1: the render reads `PrePromptState.topic_match`, and `derive_snapshots` returns
   `(cache, topic_match)`. ACCEPTED.**
   - **Why.** The render sees only the post-derive cache. A snapshot the call adds can change the
     hub set, so a render-side `match_snapshots` on that cache could disagree with the writer. The
     map has to travel with the snapshot.
   - **What it leaves open.** It adds a third persisted field whose serialization is not stated:
     [[#m10-1]].
3. **`CALL_OUTCOMES` = the existing `ok` / `empty` / `consumer-closed` / `error`, plus
   `skipped_budget`, with `telemetry.classify_outcome` extended. ACCEPTED; a real catch.**
   - At HEAD, `classify_outcome(exc_type, exc_val)` (`telemetry.py:96`) already emits `empty` and
     `consumer-closed` (bug-052).
   - My r9 three-value tuple, enforced by the new `log_query` validation, would have rewritten
     every grep no-match row to `outcome-invalid`.
4. **21.3 AC-5 through `$RMX_SANDBOX_PRELOAD`. ACCEPTED in shape.** This is the correct sibling
   of s9-3. Its provider does not exist yet: [[#s10-3]].

## Findings {#findings}

### SKETCHY (SUSPICIOUS) s10-1: AC-7i H5 now puts {`hub1`, `hub2`, `b`} FIRST, which is exactly the order in which its listed mutant survives {#s10-1}

**File:** `task-19.6-phased-context-and-topic-cache.md` AC-7i H5 (diff line "passed to
`derive_snapshots` with {`hub1`, `hub2`, `b`} FIRST …") and mutation "the hub set recomputed after
each snapshot `derive_snapshots` adds in the same call (AC-7i H5)".

**What:**
- In the new design, `match_snapshots` is pure and adds no snapshot. `derive_snapshots` adds
  snapshots only AFTER its one `match_snapshots` call.
- So the mutant can exist only as a `derive_snapshots` that loops over the clusters in ITS input
  order, calling `match_snapshots([c], cache_so_far)` and adding each new snapshot before the next
  call. `match_snapshots`'s defined order never applies across those calls.
- **With `b` first, the mutant survives:**
  1. `b` is matched against S1-S3 while there are no hubs, so S3 represents it.
  2. N1 is then matched: J = 2/11, so it gets its own line.
  3. This is identical to the spec's output.
- The H5 text says "the defined order processes N1 first whatever the input order, so the mutant
  always sees 4 snapshots". That reasoning applies to a mutant that cannot exist.
- **Only N1-first kills it.** N1 adds S4, the recompute makes `hub1` and `hub2` hubs, and `b` gets
  its own line.
- No AC asserts that `derive_snapshots` calls `match_snapshots` once.

**Fix (edit):**
- **H5 runs BOTH input orders.** The input order is now settable through the graph's cluster list.
  The spec's result is the same in both: N1 gets its own line, and S3 represents {`hub1`, `hub2`,
  `b`}. With N1 first, the per-cluster mutant gives `b` its own line.
- **Add to AC-7i's import check:** the body of `stm.derive_snapshots` contains exactly ONE call of
  `match_snapshots`, and that call is not inside a `for`, a `while` or a comprehension. Planted
  fixture: a `derive_snapshots` that calls it in a loop is reported.
- **Restate the mutation** as "`derive_snapshots` calling `match_snapshots` per live cluster, adding
  each snapshot before the next call (H5, N1-first order; the import check)".

**Pattern match:** YES. This is the same H5 order problem as r9 s9-1, now inverted by its own fix.

### SKETCHY (SUSPICIOUS) s10-2: neither AC-2b leg reaches the code it claims; both stop at `require_daemon`, whose result depends on a pid file the AC never states {#s10-2}

**File:** 21.1 AC-2b (the round-8 budget leg and the round-9 non-budget leg). Mutation "(round 9,
#m9-5) a non-budget `OSError` classified as `skipped_budget` (AC-2b's non-budget leg)".

**What:**
- **What `require_daemon` does first.** Without a replica, the recall path calls
  `require_daemon(root, retries=0)` (`cli.py:12226`). That calls `discovery.daemon_status`
  (`discovery.py:189-226`): a 0.5 s ping, then `busy = pid_is_rmx(pid)` ONLY when a pid file
  exists. Up, busy and absent lead three different ways:
  - **busy:** `VerbBusyError`, so `_degrade_or_raise`.
  - **absent:** `VerbAbsentError`, which raises `ClickException` even in hook mode
    (`cli.py:12230-12234`). The hook exits nonzero, prints no `[]`, and the row says `error`.
- **Budget leg (a listener that never replies).** The ping times out, so `up` is False. The AC
  states no pid file:
  - With no pid file, the path is absent, so "exits 0 with `[]`, `outcome=skipped_budget`" fails at
    GREEN.
  - It passes only if the sandbox happens to hold a pid file naming a process whose `ps` argv
    contains "rmx" or "refmatrix". The pytest interpreter's path,
    `/Users/…/refmatrix/.venv-eval/bin/python`, contains "refmatrix", so a pid file naming the test
    process "works" by accident of the checkout path.
- **Non-budget leg (accept and close).** The ping fails the same way, so with no pid file the path
  is absent. That gives a `ClickException`, and so `outcome=error`, from `log_query`'s generic
  classification. The `_memory_daemon_call` `OSError` branch (`cli.py:12241-12244`) and the new
  `budgeted=True` classification are never executed.
  - **The mutant survives.** Mapping every `OSError` to `skipped_budget` leaves this leg green.
  - **The reset case is not an `OSError` at all.** If the ping did succeed, an accept-and-close on
    the recall connection gives an empty line, so `daemon.call` raises `json.JSONDecodeError`
    (`daemon.py:662-668`). That is a `ValueError`, not in the degrade tuple, so the hook dies with a
    traceback instead of degrading.

**Fix (edit):**
- **Budget leg.** State the busy precondition. The sandbox root's daemon pid file names a live
  helper process the test spawns, with "rmx" in its argv, for example `python -c` run through an
  `argv[0]` of `rmx-sandbox-helper`. Also assert `daemon_status(root, retries=0)["busy"] is True`
  before the hook runs, so the leg cannot pass through a different path. With that, the row's
  `skipped_budget` comes from `require_daemon`'s `VerbBusyError` under `budgeted=True`. Name that
  path in the AC.
- **Non-budget leg.**
  1. The test listener answers exactly ONE ping with a valid reply: a `{"ok": true}` line, which
     is what `daemon.ping` checks (`daemon.py:571-596`).
  2. It then closes its listening socket and leaves the socket file in place, so the recall op's
     connect raises `ConnectionRefusedError`, an `OSError`.
  3. Assert: exit 0, `[]`, one row with `outcome=error`, no recall event.
- **Classifier.** Add `json.JSONDecodeError` (a peer that closes mid-answer) to the degrade tuple
  at `cli.py:12241`, classified `error`, with a third leg: the listener answers the ping, then
  accepts the recall connection and closes it. Alternatively, record in R4 why a traceback is
  acceptable there. The first is the no-silent-failure-consistent choice.
- **R4 sentence:** `verbs._call` (`verbs.py:216-218`) wraps EVERY transport exception as
  `VerbBusyError`, so type classification cannot work on the verb (MCP) route. Rows on that route
  are classified with `budgeted=False` unless the verb gets the same typed split.

### SKETCHY (SUSPICIOUS) s10-3: `$RMX_SANDBOX_CONNECT_LOG` and `$RMX_SANDBOX_PRELOAD` exist only in decision d9bx; 23.0's spec does not specify them and its in-flight implementation does not have them {#s10-3}

**File:** 19.0 AC-6f, the connect log and control legs. 21.3 AC-5, the preload and control leg.
Their provider is `task-23.0-test-sandbox.md` R4 / [[task-23.0-test-sandbox#r4]].

**What:**
- **The cited anchor does not have them.** `task-23.0-test-sandbox.md` on this branch (last
  touched `8a81112`) never mentions either variable. Its R4 says the child "exits nonzero", not 86.
- **Nor does the implementation.** The littlebig implementation (HEAD `26f80f2`, summary
  untracked) defines `CHILD_EXIT = 86` (`tests/sandbox_site/rmx_sandbox.py:53`), so exit 86 is
  real and both specs cite it correctly. `grep` finds neither environment variable in that tree's
  `tests/` or `src/`.
- **Both consumer specs are honest about this.** Each says "blocked until 23.0 provides it", and
  21.3 says "not yet in 23.0's text".
- **The risk is the merge.** If 23.0 merges as it stands, the two ACs have no provider, and
  nothing on 23.0's side records that two other plans' ACs depend on these semantics.
  - **Log ordering.** Whether a refused dial is logged before `os._exit(86)` is unspecified.
  - **Preload form.** Whether the preload is a module name on `PYTHONPATH` or a file path is
    unspecified. 21.3 says "naming the module", but the test's module lives in a tmp dir.

**Fix (to 23.0's spec, per d9bx; plus one line in each consumer):**
- **23.0 R4 gains three sentences:**
  - (a) With `$RMX_SANDBOX_CONNECT_LOG` set, the child's audit hook appends one line, the target
    path, for every `AF_UNIX` `socket.connect` event, BEFORE the deny check, so a refused dial is
    also logged.
  - (b) With `$RMX_SANDBOX_PRELOAD` set to an ABSOLUTE `.py` path, `sitecustomize` executes that
    file (`runpy.run_path`) AFTER `install_from_env()`. The refusal is therefore already installed
    and cannot be bypassed by the preload. A preload that raises exits the child 87 with the
    traceback on stderr: loud, and distinct from 86.
  - (c) The refusal exit is `CHILD_EXIT = 86` by name.
- **23.0 AC-3 gains one leg for each:**
  - with the log variable set, a child connecting to an allowed tmp listener writes one line;
  - with the preload variable set to a file that writes a marker, the marker exists and a
    deny-set dial still exits 86.
- **Tell the 23.0 implementer before merge.** Their clone is mid-task.
- **21.3 AC-5** says "an absolute path to a test-owned `.py` file" in place of "naming the
  module".

**Pattern match:** YES. An interface cited by its consumer but absent at its owner: the r8 #nm-3
and r9 #s9-3 family.

### MEH m10-1: the helix-facing cache contract leaves four things unstated: the `topic_match` serialization, a missing cache file, the record bound, and whether `state` gates eligibility {#m10-1}

**File:** 19.6 R3 "Cache file contract", R9 "One assignment", AC-7i2. Plan-19 header interface 2.

**What:**
- **`topic_match` serialization.** `topic_match` is "keyed by the sorted member tuple of each live
  cluster" and is persisted in `pre.json`. JSON has no tuple keys, and `PrePromptState.topic_match:
  dict` gives no key or value types. Helix and the render must agree on that shape, and it is
  frozen after merge.
- **Missing cache file.** "A missing or different `schema` raises". On a session's first prompt
  the cache FILE is missing, which is not the same thing, and its handling is not stated.
  - **The pre-19.6 sentinel.** 21.1 writes `topic_cache = {}` until 19.6. `{}` has no `schema` key,
    so under the rule as written it raises.
- **Record bound.** R3 now says "Expansion flips `state`; it never removes the record (only R3's
  LRU bound decides what a `return` restores)", and the collapsed set "keeps every snapshot". No
  text removes a record at all. The file, and `pre.json`'s copy of it, grow for the whole session,
  and both are read and written twice per prompt on the hook path.
- **Eligibility vs `state`.** It is not stated whether an `expanded` record is eligible in
  `match_snapshots`. H6 needs it to be: the expanded cluster must map to its own snapshot on the
  next prompt.

**Fix (edit; do it before merge because of the helix freeze rule):**
- **`topic_match` shape.** `topic_match: dict[str, str]`, keyed by `stm.cluster_cid(members)`, the
  same member-set hash that names `<cid>` (19.4 R6). One hash function, no tuple keys. In JSON it is
  an object.
- **Missing file and the sentinel.** A missing cache file is the empty cache `{"schema": 1,
  "snapshots": []}`. `pre.json`'s pre-19.6 `{}` reads as empty and is never written by 19.6 code.
  AC-7i2 gains a missing-file leg: no raise, an empty map.
- **Records.** State a bound, for example a cap of 64 records, evicting the oldest `collapsed`
  record no live cluster matched in the last N turns, counted `topic-cache-evicted`. Or have R1's
  replay record the per-session maximum record count and file size, and pre-register the bound
  against it.
- **Eligibility.** State that `state` does not affect eligibility: every record is a candidate.
- **AC-7i import check.** Drop the clause "no use of the literal `4` … against a snapshot count".
  An AST check cannot decide "against a snapshot count". In its place: no module outside `stm.py`
  references `HUB_MIN_SNAPSHOTS`, and the replay script's `from refmatrix.stm import …` set equals
  {`match_snapshots`, `member_jaccard`, `topic_hubs`}.

### MEH m10-2: AC-4b (xii)(b)'s `_proc_start(` set has no member that can supply set (1)'s `P_start` or the migration claim's own `start_token`, so the set equality fails at GREEN {#m10-2}

**File:** 21.1 D6 set (1) ("`read_pointer_errors(owner=(P, P_start), …)`"; "a watermark file whose
`pid_start` differs from the owner's is ignored"), D6 migration step 1 (`<own
pid>.<start_token(own pid_start)>`), AC-4b (xii)(b).

**What:**
- **Who needs a start value.** Both the SessionStart surfacer (for P) and the migration (for its
  own pid) need a start value.
- **Who may produce one.** `owner_lookup()` returns `(pid, how)` with no start (`stm.py:236`).
  `liveness_available()` returns a bool. The allowed set is {`owner_alive`, `liveness_available`,
  `write_pid_pointer`, `record_pointer_error`}.
- **No compliant implementation exists.** The value can only come from a new `_proc_start(` call
  outside the set, which fails the check, or from a private read of the pointer file.

**Fix:**
- Add `stm.proc_identity(pid: int) -> tuple[int, str] | None`, the ONE accessor that returns
  `(pid, _proc_start(pid))` without judging liveness.
- Set (1), the per-owner watermark check and the migration's claim name use it.
  `record_pointer_error`'s `owner_start` stamp and `write_pid_pointer` may use it too.
- (xii)(b)'s set becomes {`owner_alive`, `liveness_available`, `proc_identity`} (plus
  `write_pid_pointer` and `record_pointer_error` if they keep their direct calls).

### MEH m10-3: `unseen_dropped` roll-up re-reports counts an owner was already shown, and one sentence still says `dropped` is "the total line count" {#m10-3}

**File:** 21.1 D6 "Counts roll up" and the following paragraph (`task-21.1…md:466-470`).

**What:**
- **How the double count arises:**
  1. P's SessionStart surfaces truncation row T1, with `unseen_dropped[P] = 5`, and P's watermark
     moves past `t1`.
  2. A later halving drops T1 and adds its 5 into T2.
  3. P's next `clear` / `compact` SessionStart surfaces T2 with 5 + new.
- **Why that breaks the stated rule.** "reports exactly how many of ITS unsurfaced rows were lost"
  no longer holds.
- **Why the roll-up is wrong here.** `dropped` / `dropped_by_root` are accounting totals, and
  rolling them up is right. `unseen_dropped` is a news counter.
- **The stale sentence.** "`dropped` stays the total line count" contradicts the new definition
  (non-truncation rows removed + rolled-up counts).

**Fix:**
- A removed truncation row's `unseen_dropped[key]` is carried into the new row ONLY when that row's
  `t` is above owner `key`'s watermark at halving time. This is the same test as for ordinary
  rows.
- Delete "stays the total line count", or replace it with "is the accounting total
  (non-truncation rows removed + rolled-up counts)".
- AC-4b (x) gains one assertion: after the multi-halving run, an owner whose watermark passed T1
  sees no T1 count in later `unseen_dropped`.

### MEH m10-4: `telemetry.NUDGE_OUTCOMES` has no home in 21.3's requirements or Files table, and 21.1's `log_query` references it before 21.3 exists {#m10-4}

**File:** 21.1 R4 ("plus 21.3's nudge values for `kind=nudge` (`telemetry.NUDGE_OUTCOMES`, owned by
21.3 R3)"); 21.3 R3, `#files-to-modify` and `#rev-round-9`.

**What:**
- **Only the rev table names it.** 21.3's rev table claims the tuple, but R3's body lists the
  values without naming `NUDGE_OUTCOMES`. Its Files table has no `telemetry.py` row. R3 does not
  say the `kind=nudge` row is written through `log_query`, the only place validation runs.
  `nudge.py` "writes the `query.log` row" by an unstated route.
- **The merge order breaks it.** 21.1 merges first, and its validation names a constant that does
  not exist yet.

**Fix:**
- 21.1 R4 defines `telemetry.OUTCOMES_BY_KIND: dict[str, tuple[str, ...]]`, with every kind
  defaulting to `CALL_OUTCOMES`. `log_query` validates against `OUTCOMES_BY_KIND.get(kind,
  CALL_OUTCOMES)`.
- 21.3 R3 adds `OUTCOMES_BY_KIND["nudge"] = ("fired", "dedup", "gated", "not_identifier",
  "not_indexed", "disabled", "stale_set", "skipped_budget")`, states that the row is written through
  `telemetry.log_query(kind="nudge")` with `t.outcome` set, and adds a `telemetry.py` row to its
  Files table.
- 21.3 gains a mutation: a nudge outcome outside the tuple is rewritten to `outcome-invalid`.

### MEH m10-5: text residue {#m10-5}

- **19.0 AC-6f, connect-log control (1).** It runs "first, same environment", and then "after the
  runs the file is empty". If both use `<tmp>/connects.log`, the control's line makes the hook
  assertion fail. Give the controls their own log path (`<tmp>/control.log`).
- **19.0 AC-6f `say` leg.** The STM hooks pass `require_session=True` (D9), so the `say` envelope
  must also carry a `session_id`, or the leg records `envelope-no-session` and never reaches
  `s.record("say", …)`. State it.
- **19.2 AC-12.** "a finalize hold, if the fold takes one" leaves the test conditional on the
  implementation. Decide: the fold's watermark commit rides the last batch hold, so there is no
  finalize hold and `holds == 2` is the total.
- **21.1 AC-4b (xiii) RED list.** The `--stdin-json` leg (one `envelope-unreadable` row) is also
  RED at HEAD, because today there is no row. List it.

## Verdict {#verdict}

**8 findings (0 BULLSHIT, 3 SKETCHY, 5 MEH). DIRTY.**
- Every r9 finding is closed at its quoted text.
- All four reviser departures and extra fixes are verified, and each is better than or equal to my
  r9 prescription.
- No finding needs a user decision. [[#s10-3]] is an edit to 23.0's spec that d9bx already decided.

### Approval readiness, per task {#readiness}

| task | verdict | what is left |
|---|---|---|
| 19.0 | **ready after a one-line edit, plus an external edit** | [[#m10-5]] (control log path, `say` session). [[#s10-3]] is 23.0's spec edit; AC-6f stays blocked until 23.0 merges with it |
| 19.1 | **ready** | unchanged |
| 19.2 | **ready** (nit) | [[#m10-5]] finalize wording |
| 19.3, 19.4, 19.5 | **ready** | unchanged. 19.5 reads `skipped_budget`, now classified by type |
| 19.6 | **needs edit; helix-facing** | [[#s10-1]] (H5 both orders, plus the one-call AST check), [[#m10-1]] (`topic_match` key, missing file, record bound, eligibility vs `state`, import-check clause) |
| 21.1 | **needs edit** | [[#s10-2]] (AC-2b preconditions and the reachable `OSError` leg; the `JSONDecodeError` degrade), [[#m10-2]], [[#m10-3]], [[#m10-4]] (the `OUTCOMES_BY_KIND` home), [[#m10-5]] |
| 21.2, 21.4 | **ready** | unchanged |
| 21.3 | **needs edit (small), plus an external edit** | [[#m10-4]] (R3 names the tuple and writes through `log_query`; Files row); [[#s10-3]] (preload as an absolute path; 23.0's spec) |

### Helix (d9bi / interface 2) {#helix}

**Nothing blocks helix's design.** All the pieces exist with one home each, and each is pure:
- `topic_hubs`;
- `snapshot_eligible`, called only from `match_snapshots`;
- `match_snapshots`, the ONE assignment, with a defined order;
- `member_jaccard`;
- `derive_snapshots -> (cache, topic_match)`;
- cache `schema: 1` with per-record `state`;
- `PrePromptState.topic_match`.

Helix can import `match_snapshots` and reproduce the writer's assignment from (live clusters,
cache). Two things remain:
- **Contract details.** Fix [[#m10-1]] before 19.6 merges: the `topic_match` key type, the
  missing-file semantics and the record bound. The header's rule makes any change to them after
  merge a decision-log row naming helix.
- **The H5 test hole.** [[#s10-1]] does not change the interface. It is a test hole that would let
  a per-cluster `derive_snapshots`, which breaks the "hubs once per call" guarantee helix relies
  on, merge green.

**Next step:** one edit pass covering 19.6, 21.1, 21.3 and the 23.0 R4 amendment, then a diff check
against this report.

## Ledger {#ledger}

Appended to `last_run.log`. Per the caller's "read-only otherwise", `INDEX.md` and
`IMPRESSIONS.md` were not edited.
