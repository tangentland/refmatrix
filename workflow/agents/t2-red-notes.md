---
gmd: "0.1"
id: agent-brief-t2-red-notes
title: "T2 (26.5-26.9, plan-27) RED author notes (arch-t2, 2026-11-15): what breaks if master's spec text is built without spec-t2-fresh"
tags: [agent-brief, t2, plan-26, plan-27, red, notes]
metadata:
  node_type: brief
  created: 2026-11-15
---

# T2 RED author notes {#root}

T2's RED starts from `spec-t2-fresh` `3a4d430` (in `/Volumes/littlebig/refmatrix-t2-fresh`) after
its ch-bsd confirm-lite (ruling L138), never from the `spec-wave-t2` text on master alone. Every
item below is already handled in `3a4d430`; this list is for a reader of the older text.

rel: related-to -> [[plan-of-plans#queue]]
rel: related-to -> [[plan-26-memory-organisation]]
rel: related-to -> [[plan-27-memory-fleet-rollout]]

## Cited code that moved {#moved}

- 26.5: the `ingest_gmd_paths` fallback is `_ingest_markdown_gmd`'s handler (`ingest.py`
  ≈1518-1540), and its bare `except: pass` is gone, so a RED for "the fallback counts its
  failures" passes at base. {#m1}
- 26.5: `daemon.py:3858` is `_op_ingest_gmd`; `_op_ingest_gmd_start` is ≈3889. {#m2}
- 26.5: the existing purge (`ingest_gmd.py` ≈1468-1496) matches doc id AND path, so it misses a
  twin named by relative path (stores built before 0.84.0 on a tldr cache). {#m3}
- 26.5: `mcp.py` needs no edit (its tool table is generated from `verbs.VERBS`). {#m4}

## Criteria that cannot be met, or are not RED, as written on master {#criteria}

- 26.5 AC-220 (e) "0 twins": unreachable with the cited purge for the relpath-named shape. {#c1}
- 26.5 AC-1 "never from the cwd": false at `_root_from_projects_slug`, which includes the
  caller's root; an unregistered store resolves to `no store` from outside. {#c2}
- 26.5's wrap-only list misses five direct callers (`test_bug216_remedy_r1/r2/r3.py`,
  `test_bug241_r2_l112.py`, `test_bug241_r3_l114.py`). {#c3}
- 26.5 AC-220 bounds: a literal `elapsed < N` would fail 29.4's wall-clock census; the ordering
  checks in (k) and (p) suffice. {#c4}
- 26.5 AC-5, 26.8 AC-4, every plan-27 apply: "zero errors" passes on a `deferred` bridge that
  bridged nothing. {#c5}
- 26.8 AC-0: viascope's expected diff cannot appear (both binaries render the widened index). {#c6}
- 26.9 AC-1: "RED at HEAD" is green since 26.6 merged (`8a867bc`). {#c7}
- 26.9 R3 as written removes `IMPRESSIONS.md`'s pointer lines and dangles 176
  `bsd-impressions#` citations (P7, to bsd). {#c8}
- 27.1 AC-0 orders a tree walk the user forbade. {#c9}
- 27.3 AC-4 uninstalls a LaunchAgent already removed on 2026-11-14. {#c10}
- 27.4 AC-2: cat-herder's recall check passes with no bridge run (the resolver says `no store`
  for it from a refmatrix session). {#c11}
