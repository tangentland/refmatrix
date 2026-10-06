---
gmd: "0.1"
id: impl-plan-15-derive-impact-tracking
title: "Plan 15 summary (15.1-15.3): a derive now says what it changed — and three of my own claims had to be corrected"
tags: [implementation-summary, plan-15, derive, store, cli]
metadata:
  node_type: summary
  task: task-15.2-derive-history-and-counts
  created: 2026-10-06
---

# Plan 15 summary — tasks 15.1, 15.2, 15.3 {#root}

rel: realizes -> [[task-15.1-per-pass-code-identity]]
rel: realizes -> [[task-15.2-derive-history-and-counts]]
rel: realizes -> [[task-15.3-derive-surface]]
rel: part-of -> [[plan-15-derive-impact-tracking]]
rel: derives-from -> [[project_store_decays_behind_green_health]]
rel: reinforces -> [[feedback_green_tests_are_not_a_working_command]]

The ask was "make the version tracking richer so we have a way to understand the impact of changes".
Three of the four tasks are done. What is worth recording is not the feature — the task specs carry
that — but the four points where something I had written down turned out to be wrong, and what
corrected it. {#lead}

## 15.1 — per-pass code identity {#identity}

`derive_code_hash()` hashed `ingest.py` + `ingest_gmd.py` + `store.py` as one value handed to every
pass, so bug-067's `Store.grep_evidence` (a READ method, +80 lines) flipped this partition to
`behind_code: True` with nothing about extraction changed. Per-pass sets fix it: `gmd` →
`ingest_gmd.py`, tree passes → `ingest.py`, `store.py` in nobody's set, and an UNMAPPED pass falls
back to the union so a new pass is stale until someone maps it. {#identity-body}

**Correction 1 — the scheme tag the plan did not foresee.** A pre-15.1 stamp holds a UNION hash; a
per-pass hash covers one module set. The first cut compared them anyway and reported every legacy
stamp as behind — recreating the exact false positive the task existed to remove. Hashes are now
`p1:<digest>`, and a stamp is one of three states: tagged (comparable), untagged (an older scheme →
UNKNOWN, "re-derive to know"), NULL (no identity → BEHIND, the pre-existing contract, untouched).
The middle state deliberately does not alert: firing on it would hit every pre-15.1 store once and
get the alert switched off, which ch-bsd plan-12 #b-3 already measured happening. {#correction-1}

## 15.2 — the history and the counts {#history}

`derive_history` is append-only, capped at 50 per `(partition, pass)`, and records the partition's
structural shape after each pass. `entity_links` and `linkage_evidence` carry no `partition_id`, so
the counts scope them by joining `entities`; counting unscoped would report whole-store totals for
one partition and make every diff wrong in the same direction. A mutation that drops the scope is
killed. {#history-body}

**Cost, measured not asserted (plan acceptance #3): 18 ms median** (3 runs: 21/17/18) on the real
partition — 78,437 entities, 375,085 links, 129,355 evidence rows — against a derive measured in
minutes. {#cost}

**Correction 2 — the DuckDB backend has its own schema.** Adding the table to the SQLite
`CATALOG_DDL` alone left a fresh store without it. Found immediately because the history write
failed LOUDLY (`warning: derive history ... not recorded`) rather than silently — the
no-silent-failure rule working on its author. {#correction-2}

## 15.3 — the surface {#surface}

`rmx derive log` (per-derive counts + delta against the previous row of the SAME pass),
`rmx derive diff` (keys that moved, or the words "no change"), `rmx derive status` (per pass: which
modules, and whether it is behind by CODE, drifting by VERSION, or UNKNOWN). The warning line that
started all of this now attributes instead of leading with a version comparison that moves on every
bump. {#surface-body}

**Correction 3 — "a no-op derive diffs to all zeros" was wrong about the system.** Running the real
pass twice over an unchanged tree leaves every graph count identical and moves `bitmap_fragments`
**0 → 3**, because the first pass had not flushed fragments yet. Hiding that would be a lie; calling
it "the derive changed something" buries the question people ask. So counts split: GRAPH content
decides the verdict and a `materialized cache:` line reports the rest beside it. Found by measuring,
not designed. {#correction-3}

**Correction 4 — the renderer overclaimed.** My first line said "version drift only, deriving code
unchanged (no re-derive needed)" for any stale status. With no per-pass data that conclusion is
unsupported, and an existing test caught it. The claim now requires the evidence: without comparable
per-pass hashes the line falls back to naming the versions and the command. {#correction-4}

## The two defects a REAL run found that 11 green tests did not {#real-run}

Both from running `rmx derive status` / `log` once against the live store, which is
`feedback_green_tests_are_not_a_working_command` in one paragraph: {#real-run-lead}

1. **A busy daemon crashed the command.** The daemon answered `ping` and then timed out on the op,
   and the TimeoutError escaped as a traceback. Every test stubbed `ping` to False, so none of them
   could see it. Both reads now degrade to the lock-free replica and SAY so. This is
   `bsd-pattern-busy-is-not-absent`, reached from a new direction.
2. **A store older than the feature raised instead of answering.** The deployed daemon predates
   `derive_history`, so the live catalog legitimately lacks the table and `rmx derive log` died with
   a CatalogException. "No history" is a real answer for a store whose schema predates the feature,
   and it is now given — by CHECKING `information_schema` rather than catching an exception message,
   because narrowing on a message is how a real failure gets read as "absent".

Both are now pinned by tests that fail without the fix. {#real-run-tests}

## Verification {#verification}

| gate | result |
|---|---|
| RED first | `pytest-task15.1-RED.log` (7), `pytest-task15.2-RED.log` (10), `pytest-task15.3-RED.log` (10) |
| derive suites | **56 passed** (identity 7, history 11, surface 17, pre-existing stamp 21) |
| mutations | 7 of 7 load-bearing on 15.2; 7 of 7 on 15.1 |
| counts cost | 18 ms median on the real partition |
| CLI tree + verb parity | regenerated; 45 pass |
| `install-hooks --check` | in sync |
| GMD lint | 0 errors, 534 docs |

## Not done: 15.4 {#open}

Sessions, embed and pagerank still never stamp, so this project's `refmatrix` partition carries one
row out of five possible passes — "the graph was derived by X" remains a claim about one pass. The
spec is written and pre-registers the trap: an unstamped pass must NOT read as `behind_code`, or the
release that ships stamping turns the whole fleet hot once and gets the alert disabled. {#open-body}
