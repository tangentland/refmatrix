---
gmd: "0.1"
id: task-15.1-per-pass-code-identity
title: "Task 15.1: each pass is stale on its OWN code, not on a shared hash"
tags: [task, derive, store]
metadata:
  node_type: task
  status: complete
  created: 2026-10-06
---

# Task 15.1: per-pass code identity {#root}

> Plan: [plan-15-derive-impact-tracking](../plan-15-derive-impact-tracking.md)
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-15-derive-impact-tracking]]

## Requirements {#requirements}

`derive_code_hash()` takes an optional `pass_name` and hashes only the modules that derive THAT
pass. The mapping is explicit, named in one place, and documented per entry — not inferred.
{#req-lead}

| pass | modules |
|---|---|
| `ingest` | `ingest.py` |
| `semantic` | `ingest.py` |
| `gmd` | `ingest_gmd.py` |
| (unknown pass) | the union of all mapped modules — an unmapped pass must be treated as MAXIMALLY stale, never as clean |

`store.py` leaves every set. It is in the current union because the schema and the write helpers live
there, but no pass's extraction depends on a read method, and that is precisely the false positive
this task exists to remove. {#req-store}

`derive_status()` reports `behind_code` **per pass** as well as in aggregate, and the aggregate stays
`any(pass.behind_code)` so the hub alert's meaning does not change. Each pass's entry names its own
hash and the modules it covers, so a reader can see WHY a pass is implicated. {#req-status}

The existing cache key (path, mtime_ns, ctime_ns, ino, size per module) is kept exactly as it is.
bug-037 was a same-length edit served from stale bytecode, and ch-bsd plan-12 r4 found that scar
rebuilt inside this very function's first cache; the key is load-bearing and this task does not
touch it. {#req-cache}

## Acceptance criteria {#acceptance}

1. `derive_code_hash("gmd") != derive_code_hash("ingest")` when `ingest.py` and `ingest_gmd.py`
   differ — the two passes are distinguishable at all.
2. Editing `store.py` changes NEITHER. Editing `ingest_gmd.py` changes `gmd` and not `ingest`.
3. `derive_code_hash()` with no argument keeps its current meaning (the union) so existing callers
   are unaffected.
4. An UNMAPPED pass name hashes the union, i.e. it is conservative. A test asserts this explicitly,
   because the tempting default — "no modules, so nothing to compare, so clean" — is a gate that
   cannot fire.
5. `derive_status()["passes"][i]` carries `behind_code`, `code_hash`, and `modules`; the top-level
   `behind_code` equals `any()` of them.
6. **On this store, `gmd` reports `behind_code: False` with no re-derive** (plan acceptance #1), and
   the test that pins it says what it would mean if it ever flipped.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/store.py` | `_DERIVE_PASS_MODULES`, `derive_code_hash(pass_name=None)`, per-pass `behind_code` in `derive_status`, `stamp_derive` stamps its pass's hash |

## Test strategy {#test-strategy}

`tests/test_derive_pass_identity.py`, real stores under `tmp_path`. Drive the hash by WRITING to copies
of the modules in a temp tree and pointing the resolver at them, rather than monkeypatching the hash
function — a test that fakes the hash cannot see a mapping error. One case per acceptance criterion,
each RED first. The `store.py`-does-not-matter case must assert on a REAL edit to a copy of
`store.py`, since that is the exact false positive being fixed. {#tests}
