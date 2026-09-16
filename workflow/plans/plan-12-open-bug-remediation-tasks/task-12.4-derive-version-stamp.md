---
gmd: "0.1"
id: task-12.4-derive-version-stamp
title: "Task 12.4: a store says which code derived its graph"
tags: [task, plan-12, store, health, store-decay]
metadata:
  node_type: task
  status: complete
  plan: plan-12-open-bug-remediation
---

# Task 12.4: a store says which code derived its graph {#root}

> Plan: [[plan-12-open-bug-remediation]]
> Status: Complete
> Bug: bug-039
> Depends on: [[task-12.5-pyc-invalidation]]

rel: part-of -> [[plan-12-open-bug-remediation]]
rel: derives-from -> [[project_store_decays_behind_green_health]]

## Requirements {#requirements}

- bug-039: this project's own store was structurally UNDER-DERIVED — 7 of 12 fixed scan-prompt
  prompts sat at a 1-bundle / 10-node floor — while `daemon_up`, `dev_tree`, version parity and
  `rmx install-hooks --check` all read green. A `reingest --force` took the set to 2.46x tokens.
  The store had not been force-re-derived since 0.49.1, across ten days and several ingest changes.
- The missing fact is not "did the FILES change" (`stale_files` already answers that, and answered
  `35`, which reads as log churn). It is **"did the CODE that derived this graph change"**, and
  nothing records it.
- New table `derive_stamps(partition_id, pass_name, version, at)`, created by the same
  `CREATE TABLE IF NOT EXISTS` schema block every store already applies on open, so an existing
  store gains it without a migration step.
- Every ingest pass that writes derived graph state stamps itself on completion:
  `Store.stamp_derive(pass_name)` writes the running `refmatrix.__version__` and the wall clock,
  upserting on `(partition_id, pass_name)`.
- `Store.derive_status()` returns `{passes: [{pass_name, version, at}], oldest_version,
  running_version, stale: bool}`. `stale` is True when any stamped pass carries a version that is
  not the running one, **or** when a partition holds tracked files and has no stamp at all (the
  pre-0.71 case — an unstamped store is the exact condition that hid for ten days, so it must read
  stale, not unknown).
- Surfaced where a human already looks: the daemon `health` op carries `derive` and
  `rmx daemon status` prints one line when it is stale — `derive: 0.49.1 (running 0.71.0) — stale;
  rmx reingest --force` — and prints nothing when it is current. A green surface stays quiet.
- Version comparison is EXACT STRING INEQUALITY, not ordering: a store derived by a NEWER version
  than the running binary is also a mismatch worth saying (that is a rolled-back deploy).
- No silent skips: a pass that cannot stamp logs why; the count of stamped passes is returned.

## Files to Create / Modify {#files}

- modify `src/refmatrix/store.py` (schema, `stamp_derive`, `derive_status`)
- modify `src/refmatrix/ingest.py` / the pass drivers that complete a derive (stamp call sites)
- modify `src/refmatrix/daemon.py` (`_op_health` carries `derive`)
- modify `src/refmatrix/cli.py` (`daemon status` renders the stale line)
- create `tests/test_derive_stamp.py`
- modify `workflow/bug_registry.md` (bug-039 -> fixed)

## Test Strategy (RED first) {#test-strategy}

`tests/test_derive_stamp.py`, over a tmp store:
- `stamp_derive` writes the running version; a second stamp for the same pass UPDATES rather than
  accreting a row
- `derive_status` on a store stamped by the running version: `stale` False
- **the incident replay**: stamp a pass with `"0.49.1"` while running 0.71.x -> `stale` True, and
  `oldest_version` names 0.49.1
- a store with tracked files and NO stamps at all reads `stale` True (the ten-day case)
- an EMPTY store with no tracked files reads `stale` False — a store nobody ingested into is not
  decayed, and a false positive on every fresh store would train the signal away
- a NEWER stamp than the running version also reads stale (rollback)
- the ingest pass drivers actually call `stamp_derive`: run the real pass over a tmp tree and read
  the stamp back. A test that calls `stamp_derive` directly proves the helper, not the wiring
  ([[impression_bsd_tests_bypass_wiring]])
- `_op_health` returns `derive` with the same shape, and `daemon status` prints the line when
  stale and NOTHING when current (both asserted)
- mutation check: deleting the stamp call in the pass driver turns the wiring test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation noted.
- `workflow/implementation_summaries/task-12.4-derive-version-stamp.md`.
- Branch `task-12.4-derive-version-stamp`, merged `--no-ff` to `master`.
