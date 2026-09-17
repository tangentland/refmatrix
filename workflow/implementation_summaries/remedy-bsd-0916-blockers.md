---
gmd: "0.1"
id: impl-remedy-bsd-0916-blockers
title: "Remedy round: the five BULLSHIT findings of the bug-041/042/043 post-deploy audit"
tags: [implementation-summary, ch-bsd, remedy, memory, daemon, hub]
metadata:
  node_type: implementation-summary
  status: complete
  audit: bsd-bug-041-042-043-00d0ded
  created: 2026-09-16
---

# Remedy round: the five BULLSHIT findings of the bug-041/042/043 post-deploy audit {#root}

rel: derives-from -> [[bsd-bug-041-042-043-00d0ded]]
rel: reinforces -> [[feedback_check_the_sibling_condition]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]
rel: related-to -> [[feedback_read_identifiers_at_write_time]]

## Why this round existed {#why}

The bug-041/042/043 work landed AFTER `@ch-bsd`'s CLEAN range (`c92274b..34aeddf`) and shipped to
the fleet as 0.72.2 with 22 tests, six killing mutations, and no adversarial audit. The audit found
**14 findings (5 BULLSHIT, 4 SKETCHY, 5 MEH)**. Two of the three fixes were correct about the defect
and wrong about the constraint it lives under. {#why-lead}

## The five blockers {#blockers}

| # | what it was | what shipped |
|---|---|---|
| **b-1** | `memory_index` capped LINES; the loader cuts CHARACTERS. `--check` said "in sync" on an index still losing its tail | `MAX_INDEX_CHARS` (env `RMX_MEMORY_INDEX_CHARS`) drives the fold; `write()` prints `STILL OVER` when folding runs out |
| **b-2** | `write()` reported to stdout — the MCP JSON-RPC channel — and save-state calls it with no `out=` | defaults to stderr; an explicit `out=` still wins |
| **b-3** | the bug-041 poll loop destroyed any request not fully arrived inside one 1 s slice | `_recv_line` takes an in/out `acc` that survives a timeout; both loss paths log |
| **b-4** | `src/` did not compile on the Python `pyproject` declares | two PEP 701 f-strings hoisted out; a guard that tests the DECLARED floor |
| **b-5** | four new test doubles, registry untouched (the most-repeated finding in the ledger) | three rows; `_Pool` marked MUST GRADUATE |

And the one the user asked about directly:

- **s-3** — bug-043 fixed `pending_refine` and left `hot`, in the commit whose message is about
  sibling conditions. `hot` now announces on arrival, on material change, and re-asserts every
  `HOT_REASSERT_S` (6 h). The 23-tick / 13 h 47 m stretch now alerts **once**. {#s3}

## Where the audit was wrong, and how that was settled {#corrections}

Both corrections came from measuring, not from arguing — which is the same discipline the audit was
applying to the code. {#corrections-lead}

### b-1's prescribed unit was wrong {#unit}

The finding said "cap the rendered BYTES". The loader counts **characters**. Settled against the
session banner (`MEMORY.md is 30.3KB (limit: 24.4KB) … 38 of 197 lines were cut off, starting at
line 160`) on the live 197-line / 31,607-byte / 31,043-char index:

| unit | budget | first line past | lines cut | matches banner |
|---|---|---|---|---|
| bytes | 24.4 KiB | 157 | 41 | no |
| **chars** | 24.4 KiB | **160** | **38** | **both numbers** |

`chars/1024 = 30.3 KiB` also reproduces the banner's size exactly. The audit's related complaint —
that `MAX_LINE_CHARS` counts characters against a byte budget — dissolves: characters were the right
unit all along. A byte cap would have over-folded a multi-byte index by roughly 3x and dropped
entries that fit. {#unit-table}

### b-4 was narrower than the defect {#floor}

The audit tested Python 3.11 and found `daemon.py:1325`. Compiling the whole tree at the DECLARED
floor (3.10, which is installed) found **`cctree.py:575` as well**. The guard added reads
`requires-python` from `pyproject.toml`, locates that interpreter and runs `compileall`, so it
generalises instead of chasing one file.

It is a subprocess test for a measured reason: `ast.parse(feature_version=(3, 10))` does **not**
reject PEP 701 — it was tried first and parsed the broken file happily. The test skips loudly when
no floor interpreter exists rather than passing on a check it did not perform. {#floor-body}

## A superseded contract, changed in the open {#superseded}

`test_a_hot_row_alerts_every_tick` asserted "hot means wrong NOW; repetition is the point". That
belief was argued without ever measuring the firing rate, and the rate refutes it: 37 of 60 live
messages carried a hot row, and one project sat at `stale_files: 37` for 23 consecutive ticks.
Repetition was not conveying "still wrong" — it was training the reader to ignore the channel, which
is the missed-incident failure the old contract claimed to prevent.

The test was rewritten under the opposite contract with the rate recorded in its docstring, and
renamed to say what it now asserts. It was not quietly flipped; a test that reverses meaning while
keeping its name is how a contract change hides. {#superseded-body}

## Verification {#verification}

| gate | result |
|---|---|
| b-1/b-2 RED | 7 failed — `pytest-bsd-b1b2-RED.log` |
| b-1/b-2 GREEN | 27 passed incl. the existing index suite — `pytest-bsd-b1b2-GREEN.log` |
| b-3 RED | 2 failed (the split request was genuinely lost) — `pytest-bsd-b3-RED.log` |
| b-3 GREEN | 9 passed — `pytest-bsd-b3-GREEN.log` |
| s-3 RED | 5 failed — `pytest-bsd-s3-RED.log` |
| s-3 GREEN | 48 passed with `test_plan1_remedy` + `test_hub` — `pytest-bsd-s3-GREEN.log` |
| b-4 | `compileall` clean on a real Python 3.10 |
| GMD lint | 0 errors, 14 warnings (baseline) |

**b-1 was proven on the live artifact, not only in tests**: the real index regenerated
`197 -> 150 lines, 23,843 chars`, `check()` in sync, under the 24,986-char loader limit, with 48 old
project notes folded into a pointer and nothing deleted. A backup was taken first. {#verification-live}

## Registry {#registry}

bug-045 (b-1), bug-046 (b-4), bug-047 (b-3), bug-048 (s-3). bug-043's own row was corrected: it
claimed `stale_files: 0` on all five cited alerts, but 13:11:49 carried 9 and 12:22:39 carried 3 —
right about the defect, wrong about one of its own identifiers. {#registry-body}

## The 30-second grep wall (bug-049) {#grep-wall}

Found in the `query.log` telemetry rather than by an audit, and chased on the user's
instruction before the benchmark re-run so the wall would not sit inside the measurements.

**Symptom:** `rmx grep` printed its hits and then blocked ~30 s. 104 of 1,165 `grep-replica`
calls pinned at 30,178-30,222 ms — a ~10 ms spread over 11 days, which is a timeout, not work.
Rising: 7% of calls on 09-14, 5% on 09-15, **17% on 09-16**. Reproduced live on the deployed
build: **30.425 s** with `user 0m0.259s`. {#wall-symptom}

**Cause:** four `learn_from_grep` call sites each passed a timeout and inherited
`daemon.call`'s default `retries=2`. Measured against a socket that accepts and never answers:

| call | elapsed |
|---|---|
| `call(timeout=10.0)` (default retries) | **30.16 s** |
| `call(timeout=10.0, retries=0)` | 10.00 s |

Worst case per site: 90.15 s for the context backstop (`timeout=30.0`), 30.15 s for the two grep
brokers, and **180.45 s** for the sync `_grep_run` site, which was `timeout=60.0` AND unwrapped.
Underneath it: `learn_from_grep` is not in `CLI_OPS`, so it runs on `bg_pool` and takes
`_store_lock` — every grep was asking for a write on the very lock whose contention made it slow,
and `except Exception: pass` meant it never said so. {#wall-cause}

**Fix, in two parts.** The bound alone would have left the cause: N greps still meant N write
attempts.

1. One shared `_broker_learn_from_grep` — `retries=0`, 2 s, failures named on stderr — replaces
   all four sites.
2. `learn_queue.py`: the default path APPENDS to a durable JSONL queue (no socket, no lock); the
   daemon's existing 30 s flush tick drains it coalesced by pattern and deduped by (file, line).
   The queue also survives a daemon restart, which the fire-and-forget RPC never did.

**The drain YIELDS the writer between entries** — corrected during review. The first version took
`_store_lock` once for the whole batch and had a test asserting exactly that, which is starvation
written as a test: a deep queue would hold the writer against ingest, recall and save-state,
trading the CLI's 30 s wall for a stalled daemon. Coalescing is what makes the queue cheap (N greps
become M patterns with duplicate hits folded away); the single acquisition was never the point.
Releasing mid-batch is safe *here* because each entry is its own write — the lock is never released
inside an `s.transaction()`, which is the rule `ingest_path` follows and `_sync_paths` deliberately
does not. A time budget (`RMX_LEARN_DRAIN_BUDGET_S`, 5 s) and the shutdown event both stop the
drain, and whatever they cut off is REQUEUED rather than dropped to make a tick look fast.

Every loss is counted: malformed lines, unusable hits, and overflow past `MAX_QUEUE_LINES` (newest
wins). `_store_health` reports `learn_queue_pending`, because a queue nothing reports is a quieter
way to lose work — a tick that stopped draining would otherwise show up only as retrieval slowly
getting worse. {#wall-fix}

**Proven end to end** on a throwaway store: grep **0.187 s** and one queued record -> drain applies
1 pattern, 1 file -> the same grep is then served FROM THE INDEX (`[mentions] query/zzq_target`)
instead of the rg floor. The learning loop works through the queue. {#wall-proof}

**Mutation-checked.** Restoring the batch-wide lock kills both anti-starvation tests, with the
competitor reporting `only got the lock after 20/20 entries`. The first attempt at that mutation
used a bare `acquire()` with no release and DEADLOCKED the run instead of failing it — a mutation
that hangs proves nothing, and worse, the restore was chained after the hung command and did not
run, leaving the mutation in the tree until it was checked. Both were caught and the tree verified
byte-identical to its pre-mutation backup. {#wall-mutation}

## Still open {#open}

4 SKETCHY and 5 MEH, none addressed here: `s-1` (flush budget 5→15 s puts the degraded stop at 59 s
worst case against launchd's `ExitTimeOut = 45`, which is the SIGKILL that corrupts the ART index —
the most serious of the remainder), `s-2` (`_inflight_ops` keyed by op NAME, so it loses the op it
exists to name), `s-4` (partly addressed by the `STILL OVER` line), and `m-1`..`m-5`. {#open-body}
