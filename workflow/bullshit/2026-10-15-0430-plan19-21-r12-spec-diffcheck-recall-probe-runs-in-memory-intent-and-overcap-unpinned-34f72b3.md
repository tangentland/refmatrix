---
gmd: "0.1"
id: bsd-plan19-21-spec-diffcheck-r12-34f72b3
title: "plan-19 + plan-21 r12 diff check: every r11 finding closed at its specified text and AC-2b's op sequence verified against cli.py; four MEH text edits remain (a close-vs-reply race in the non-budget leg, a broken-pipe mutation with no killing leg, the over-cap rule unpinned, a dead VerbBusyError source cited)"
severity: MEH
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-diffcheck-19.0-19.6-21.1-21.3
round: 12
tags: [bsd, audit, spec-review, diff-check, stm, helix, plan-19, plan-21]
---

# ch-bsd r12 diff check of plans 19 and 21 at `34f72b3` {#root}

**Commit reviewed:** `34f72b3` on `wave0-spec-reviews` (confirmed with `git log -1`). The diff
`954f601..34f72b3` over `workflow/plans/plan-19-*` and `workflow/plans/plan-21-*` covers 6 files,
+169/-49. `git diff 954f601 34f72b3 -- src/` is empty.

**Written:** 2026-10-15T04:30:14-0700.

**Method:** read-only.
- Read the full diff against [[bsd-plan19-21-spec-diffcheck-r11-954f601]].
- Traced AC-2b's traffic at HEAD through these code paths:
  - `cli.py:11944-11950`: the budget clock, then `_memory_intent`;
  - `cli.py:11120-11222` and `:11240-11259`: the partition default, the legacy probe, and
    `_apply_memory_partition_default`;
  - `cli.py:12004-12025` and `:12185-12245`;
  - `daemon.py:571-596` (`ping`), `:613-668` (`call`), `:671-694` (`_recv_line`);
  - `discovery.py:150-226`, `verbs.py:194-205`, `modelsrv.py:71-86`, `telemetry.py:96-118`;
  - `stm.py:127-202`.
- Read 19.6's `topic_hubs` definition (`:265-271`) to check m11-3's invariant.
- `tools/gmd/lint.py` on all 6 files: 0 errors. The only warnings are cross-doc `dangling-doc`
  warnings from single-file scans.

No live store or socket was opened. Nothing outside this report and `last_run.log` was edited.

rel: derives-from -> [[bsd-plan19-21-spec-diffcheck-r11-954f601]]
rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]

## Round-11 findings: status {#prior-status}

| r11 id | status | evidence at `34f72b3` |
|---|---|---|
| s11-1 AC-2b traffic | **closed.** Residue: [[#m12-1]], [[#m12-2]], [[#m12-4]] | The listener is now an op dispatcher that records the sequence. The non-budget leg closes after the 2nd `ping` and expects [`ping`, `partition_list`, `ping`] with `ConnectionRefusedError`. The mid-answer leg reads the request, then closes, and expects 4 ops with `JSONDecodeError`. R4's route list and the OSError-before-BrokenPipe order are in. Both mutations are in. |
| m11-1 nudge `error` | **closed** | 21.3 R3: the tuple and the prose list both carry `error`. |
| m11-2 migration on `None` | **closed** | D6 step 1 has the `None` clause. AC-4b (ix) asserts all three skip lines with the legacy file and watermark unchanged. `proc_identity` is `None` whenever `_proc_info` is (`stm.py:197-202`), so the leg reaches the clause. |
| m11-3 record cap | **closed at the text specified.** Residue: [[#m12-3]] | R3, AC-7i2, the mutation and header item 2 all match the r11 replacement text. |
| m11-4 `cluster_cid` | **closed** | The byte-identical formula is in 19.4 R6, 19.6 R9 and header item 2. 19.4 has the Files `stm.py` row. |
| m11-5 AC-6f load proof | **closed** | `RMX_SANDBOX_PRELOAD=<tmp>/mark.py` writes to `loaded.log`, and the AC requires ≥ 1 line per command. |
| m11-6 residue | **closed** | The 19.6 parenthetical now reads "maps to S2". 21.1's verb-route hedge is replaced by "`budgeted=False` by design". |

### AC-2b re-traced against `cli.py` at HEAD {#trace}

**The four requests, in order:**

1. **`ping`.** `memory_recall` calls `_memory_intent` (`cli.py:11950`). That calls
   `_apply_memory_partition_default` (`:11258`), then `_memory_partition_default`, then
   `_legacy_memory_partition_exists`. With no reader store, the probe runs
   `daemon_mod.ping(root)` (`:11202`).
2. **`partition_list`.** The probe calls `daemon_mod.call(…, "partition_list", retries=0)`
   (`:11208`). The dispatcher answers `{"ok": true, "result": {"rows": []}}`, so `found=False`.
3. **`ping`.** The body's own probe at `:12192` is SKIPPED, because `_partition_override` is
   already set. The replica leg returns `None`: `shared_available` sees no `models.sock` file and
   never connects. `require_daemon(retries=0)` then calls `daemon_status`, which sends one
   `ping` (`:12226`).
4. **`memory_recall`.** `_memory_daemon_call(retries=0)` (`:12240`) sends the recall request.

The four ops are correct. The cited call sites for ops 1 and 2 are correct. R4's list of
VerbBusyError sources is not: see [[#m12-4]].

**Mid-answer leg:**
- The listener reads the whole line, then closes. `_recv_line` gets `b""`, and `json.loads`
  raises `JSONDecodeError`.
- With `retries=0`, `call` re-raises it (`daemon.py:657-668`).
- `classify_outcome` produces `"JSONDecodeError: …"`.
- The run is deterministic.

**Mutation "JSONDecodeError omitted from the tuple":** killed. The run ends in a traceback and
exits nonzero.

**Mutation "op-sequence drift":** killed by the exact-list assertion.

**Mutation "BrokenPipe → consumer-closed under `budgeted=True`":** NOT killed. See [[#m12-2]].

### m11-3: `topic_hubs` is invariant under the cap {#trace-hubs}

- `topic_hubs(cache)` reads only the 8 newest records, ranked by `turn` descending with ties to
  the smaller `<cid>`, whatever their `state` (`task-19.6…md:265-271`).
- Candidates exclude exactly those 8. Removing a record ranked below the top 8 leaves the top 8
  unchanged.
- The second write is the last write of the prompt. So `topic_hubs`, computed on the file the
  next reader loads, equals `topic_hubs` on the pre-eviction cache.
- "Oldest" is the exact reverse order: the smallest `turn`, with ties to the larger `<cid>`.
- **AC-7i2 leg, checked by hand.** The cache has 66 records. The 1st-oldest is `expanded`; the
  2nd-oldest is matched. The two oldest candidates are the 3rd and 4th records, so the result is
  64 records with `evicted` = 2. That matches the spec.

### m11-4: the pinned hash {#trace-hash}

The formula is `hashlib.sha256("\n".join(sorted(members)).encode("utf-8")).hexdigest()[:8]`.
- It is identical in 19.4 R6 (`:101-102`), 19.6 R9 (`:250-251`) and header item 2.
- `"\n"` separates {`ab`, `c`} from {`a`, `bc`}.
- The 19.4 Files row assigns the build to whichever task merges first.

## Findings {#findings}

### MEH m12-1: in the non-budget leg, the listener replies before it closes, so the recall connect can still be queued in the backlog and fail with an error other than `ConnectionRefusedError` {#m12-1}

**File:** 21.1 AC-2b, non-budget leg ("after answering the SECOND `ping` … closes its listening
socket").

**What:** The leg's text came from my r11 replacement.
- The listener writes the 2nd ping's reply, and only then closes the listening socket.
- If the listener thread is descheduled between those two steps, the hook may already have read
  the reply, returned from `require_daemon`, and connected for `memory_recall`. That connection
  sits in the backlog.
- Closing the listener then resets the queued connection. The client gets `ECONNRESET`, or
  `JSONDecodeError` on EOF.
- The `error` starts `ConnectionResetError` or `JSONDecodeError` instead of
  `ConnectionRefusedError`. That is a flaky assertion, not a defect in the code under test.

**Fix:** replace "the dispatcher listener, after answering the SECOND `ping` (round-11
#s11-1), closes its listening socket and leaves the socket file in place, so" with:
> the dispatcher listener, on the SECOND `ping`, reads that request line, closes its LISTENING
> socket (leaving the socket file in place), and only then writes `{"ok": true}` on the
> already-accepted connection (round-12 #m12-1: closing before replying means no later connect can
> be queued in the backlog), so

### MEH m12-2: the mutation "daemon-socket `BrokenPipeError` mapped to `consumer-closed` under `budgeted=True`" has no leg that kills it {#m12-2}

**File:** 21.1 mutations (round 11, #s11-1, second clause); R4's ordering sentence.

**What:**
- R4 now orders the `OSError` test before the `BrokenPipeError` mapping.
- No AC produces a `BrokenPipeError` on the daemon socket. The mid-answer leg reads before
  closing, specifically to remove that race.
- So the listed mutation survives every leg. The same is true of a mutant that tests `OSError`
  before `TimeoutError`, which would make budget timeouts `error`.

**Fix:**
- Append to AC-2b's **Validation leg**:
  > `telemetry.classify_outcome(BrokenPipeError, BrokenPipeError(32, "Broken pipe"),
  > budgeted=True)` returns `("error", "BrokenPipeError: [Errno 32] Broken pipe")` and with
  > `budgeted=False` returns `("consumer-closed", None)`; `classify_outcome(TimeoutError,
  > TimeoutError(), budgeted=True)[0]` and `classify_outcome(socket.timeout, socket.timeout(),
  > budgeted=True)[0]` are `"skipped_budget"` (round-12 #m12-2).
- In the mutation entry, change "(R4: the `OSError` test runs first)" to "(AC-2b validation
  leg's `classify_outcome` assertions)".
- Add the mutation "the generic `OSError` test placed before the timeout test under
  `budgeted=True` (AC-2b validation leg)".

### MEH m12-3: the cap's no-candidate rule is frozen for helix but no leg pins it {#m12-3}

**File:** 19.6 R3 "Record cap" ("When no candidate remains, eviction stops … counted
`topic-cache-over-cap=<n>`"), AC-7i2, mutations.

**What:**
- The only cap leg has plenty of candidates.
- A mutant that, once candidates run out, falls back to evicting an `expanded`, matched or
  8-newest record survives every leg. So does a mutant that drops the over-cap count.
- Evicting an 8-newest record moves `topic_hubs`, and that is exactly the helix invariant m11-3
  froze.

**Fix:**
- Append to AC-7i2 after the record-cap leg:
  > **Over-cap leg** (round-12 #m12-3): a cache of 66 records whose 8 newest are `collapsed` and
  > whose other 58 are all `expanded`, with a prompt whose live graph adds no snapshot, leaves all
  > 66 records after the second write; the event carries `topic-cache-evicted` = 0 and
  > `topic-cache-over-cap=2`; `topic_hubs` on the written cache equals `topic_hubs` on the input.
- Add the mutation:
  > (round 12, #m12-3) the cap evicting outside the candidate set when none remains, or the
  > overflow not counted (AC-7i2 over-cap leg)

### MEH m12-4: R4 names "the partition probe's catch (`:12195`)" as a `VerbBusyError` source; the hook never runs it {#m12-4}

**File:** 21.1 R4, "Every `VerbBusyError` reaches the degrade path" sentence. This was my r11
replacement text.

**What:**
- `memory_recall` runs `_memory_intent` at `cli.py:11950`, before the body.
- That call sets `_partition_override` through `_apply_memory_partition_default` (`:11258`). So
  the body's branch at `:12192-12196`, `_left(10.0)` and its catch, never runs on any CLI
  invocation.
- The probe that does run catches every exception itself (`:11214` and
  `_memory_partition_default`'s outer `except`), so it never raises `VerbBusyError`.
- The citation sends the implementer to unreachable code.

**Fix:** replace "`_left`'s deadline (`cli.py:12007`), the partition probe's catch (`:12195`), the
replica leg (`:12214`) and `require_daemon`'s busy classification" with:
> `_left`'s deadline (`cli.py:12007`), the replica leg (`:12214`) and `require_daemon`'s busy
> classification

Then add after "Each is classified `skipped_budget`.":
> (The legacy-partition probe runs first, in `_memory_intent` (`cli.py:11950` → `:11258`),
> catches every exception itself (`:11214`) and raises nothing; the body's second probe at
> `:12192-12196` is skipped because `_partition_override` is already set; round-12 #m12-4.)

## Verdict {#verdict}

**4 findings (0 BULLSHIT, 0 SKETCHY, 4 MEH). DIRTY. No blocker.**
- Every r11 finding is closed at its specified text.
- AC-2b's op sequence and both of its r11 mutations are verified against `cli.py` at HEAD.
- `topic_hubs` is invariant under the cap.
- The hash is pinned identically in all three places.
- The four MEHs are text-only edits. Three of them correct gaps in my own r11 replacement text.

### Approval readiness, per task {#readiness}

| task | verdict | what is left |
|---|---|---|
| 19.0, 19.1, 19.2, 19.3, 19.4, 19.5 | **approval-ready** | 19.0 AC-6f still cannot run until 23.0 merges. At `7ba1dd4` none of AC-3's amendment legs has a test yet (`git grep` finds the names only in `rmx_sandbox.py`). This blocks execution, not approval. |
| 19.6 | **ready after one leg + one mutation** | [[#m12-3]] (helix-facing) |
| 21.1 | **ready after three text edits** | [[#m12-1]], [[#m12-2]], [[#m12-4]] |
| 21.2, 21.3, 21.4 | **approval-ready** | 21.3 AC-5 is blocked on 23.0's merge in the same way as 19.0 AC-6f. |

**Closing path:** apply the four replacements verbatim. A diff check limited to those four
edits then closes plans 19/21 without another full round.

## Ledger {#ledger}

Appended to `last_run.log`. Per the caller's "read-only otherwise", `INDEX.md` and
`IMPRESSIONS.md` were not edited.
