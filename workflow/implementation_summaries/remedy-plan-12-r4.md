---
gmd: "0.1"
id: remedy-plan-12-r4
title: "Implementation summary: plan-12 ch-bsd round 4 remedy"
tags: [summary, plan-12, remedy, bsd]
metadata:
  node_type: summary
  task: plan-12-open-bug-remediation
  created: 2026-09-16
---

# Remedy: ch-bsd plan-12 round 4 {#root}

rel: part-of -> [[plan-12-open-bug-remediation]]
rel: amends -> [[remedy-plan-12-r3]]

## The detector rebuilt the blind spot it detects {#cache}

I claimed a wrong cache key "costs a recompute, never a wrong answer". ch-bsd reproduced the
counterexample: an **mtime-preserving restore at the same size** (`cp -p`, `rsync -t`, `tar -p`,
any `os.utime`) reads as a cache HIT and returns the OLD hash — so `behind_code` is False and the
gate **silently does not fire**. A miss, in the one direction that matters.

The shape is this repo's own bug-037 — *"a mutation check edited `45` -> `20` — the SAME byte
length — and the source was then restored from a backup"* — and `tools/pyc_guard.py` exists because
CPython treats `(mtime, size)` as a content identity. My cache reproduced that one layer up, inside
the function that replaced mtime with a hash *because mtime was unreliable*.

Key is now `(path, mtime_ns, ctime_ns, ino, size)`. `ctime_ns` moves on both restore shapes
(in-place `utime`, and replace-then-`utime`); `ino` catches the replace shape twice over. The cache
stays unbounded, with the measurement in the comment: ~145 B/entry, about one entry per deploy — an
eviction policy would be more code than the leak.

What ch-bsd's probe cleared: 2000 alternating same-size rewrites on APFS produced **0** identical
`mtime_ns`, so the rapid-write collision I was actually worried about cannot happen.

## The label was wrong on the one day it exists for {#release-day}

`all(v["never_stamped"] for v in per.values())` spanned EVERY partition. A `memory-<project>`
partition has no tracked files, so it honestly answers `never_stamped: False`, and the aggregate
collapsed — on release day, the single day `derive_unstamped` is the correct classification. The
row rendered `derive-drift@?`. Cold either way, so r2's safety property held, but a reader learned
nothing. Now aggregated over the STALE partitions only.

## A composite that carried two partitions' facts {#composite}

`{**own, ...}` kept `passes` and `code_hash` from the DEFAULT partition while `reason` and
`oldest_version` came from `worst` — which was the first partition *alphabetically* with
`behind_code`. The composite is now built explicitly, carries no per-partition rows at all, and
picks `worst_partition` by oldest version via `_version_key`. Third time this shape has regrown;
the rule is now in the docstring: **a composite describes the store, never one partition.**

## The walk stays in the tick {#cost}

Measured by ch-bsd: 3 partitions 4.68 ms, 10 → 15.95 ms, 30 → 49.31 ms (~1.6 ms/partition). Fleet
maximum is 3, so ~40 ms across 8 stores against a 15 s watchdog interval — 0.27% duty cycle. It
would want moving near 30 partitions; nothing is close.

## Evidence {#evidence}

- Full suite at the parent commit (`7e2e0a0`): **2021 passed, 0 failed**,
  `workflow/review-output/pytest-plan-12-r3.log`.
- Mutations, each killing its test: cache key back to `(path, mtime, size)` fails the
  restore replay; `never_stamped` over every partition fails the release-day test.
