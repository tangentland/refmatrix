---
gmd: "0.1"
id: remedy-plan-12-r3
title: "Implementation summary: plan-12 ch-bsd round 3 remedy"
tags: [summary, plan-12, remedy, bsd]
metadata:
  node_type: summary
  task: plan-12-open-bug-remediation
  created: 2026-09-16
---

# Remedy: ch-bsd plan-12 round 3 {#root}

rel: part-of -> [[plan-12-open-bug-remediation]]
rel: amends -> [[remedy-plan-12-r2]]

## The gate I shipped in r2 was fragile in exactly the way I guessed {#hash}

I asked ch-bsd to be hostile toward the mtime gate because I suspected it. It was, and the
demonstration was on this machine, that day: its own r1/r2 mutation harness restored `ingest.py`
and `ingest_gmd.py` **byte-for-byte**, which moved their mtimes while the content had not changed
since 09-13 / 09-16. Under the mtime gate every store in the fleet would have read "behind code"
because a test harness touched a file.

The gate is now a **content hash**, stamped at derive time:

- `derive_code_hash()` — blake2b over `ingest.py` / `ingest_gmd.py` / `store.py`, cached on
  `(path, mtime_ns, size)`. A wrong cache key costs a re-read of ~300 KB, never a wrong verdict,
  which is the right way round for something the hub's watchdog tick calls per store.
- `derive_stamps.code_hash` in BOTH catalog DDLs; `stamp_derive` writes it.
- `behind_code` compares the STORED hash to the current one. A stamp with no hash predates the
  column and counts as behind — that is the blind spot itself, not "no information".

What ch-bsd's probe CONFIRMED and I was right to rely on: `git pull --ff-only` genuinely does not
touch unchanged files (the deploy tree's three modules carry three different dates), and the
editable install does not rewrite sources.

Firing rate, now measured rather than asserted: 16 commits touched those three modules in ten days
on **4 distinct days**, against 34 version bumps — ~10x better than the version gate of r1.

## The latent trap I introduced in r2 {#drop}

`self._drop_worker(role, exc, worker=locals().get("w"))`. My worry was an unbalanced `finally`;
ch-bsd forced 50 consecutive failures and showed `_pending` returns to 0 every time, so that worry
was unfounded. The real defect was the other argument: `worker=None` does not mean "nothing to
drop" — `_drop_worker`'s guard reads `if worker is not None and cur is not worker: return`, so
None bypasses the identity check and closes the role's LIVE client. That is the incident commented
fifteen lines below it ("a drop here killed healthy workers under the whole fleet").

Unreachable today, because `_worker()` does no I/O that raises those exceptions. Disarmed anyway:
`w = None` before the `try`, `if w is not None:` before the drop. The test puts a healthy client in
`_clients`, makes `_worker()` raise, and asserts it is neither closed nor forgotten — and that
`_pending` still drains.

## The alert path could not see the product {#health}

`_store_health` called the DEFAULT partition's `derive_status()`, so a `memory-<project>` graph
derived by other code reached `rmx daemon status` and never reached the hub row or the hot gate —
the alert path being the one that matters for a store nobody is looking at. It now walks every
partition and reports the worst.

## Evidence {#evidence}

- Full suite at the parent commit (`184b13d`): **2016 passed, 0 failed**,
  `workflow/review-output/pytest-plan-12-r2.log`.
- Three mutations, each killing its test: dropping the `w is not None` guard; reverting
  `_store_health` to the default partition; (r2) deleting the partition walk.
- New tests include the identical-content rewrite replay — it writes `store.py` back byte-for-byte
  and asserts the verdict does not move.
