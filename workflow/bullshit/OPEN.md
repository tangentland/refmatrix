---
gmd: "0.1"
id: bsd-open-findings
title: "ch-bsd open findings: every BULLSHIT, GATE and handed-off SKETCHY until closed with evidence"
tags: [ch-bsd, ledger, open-findings, f5]
metadata:
  node_type: ledger
  created: 2026-11-24
---

# Open ch-bsd findings {#root}

Imported by `CLAUDE.md` (always loaded, re-read after compaction), so an unaddressed finding
cannot scroll out of view (L216, 2026-11-24; ch-bsd assessment F1 + F5). {#purpose}

**Rules.** A row is added for every BULLSHIT and GATE, and for every SKETCHY that is handed to
another task instead of folded. A row leaves only with evidence: `fixed <sha>` (the sha reachable
from `master`, checked with `git merge-base --is-ancestor`) or `ruled <L-row>`; it then moves to
[[bsd-closed-findings]] with that evidence. ch-bsd re-checks the open rows in its range on every
run and carries the rest in its report's "Carried over" section; the lead updates this file when
persisting a report. Keep this file to open rows only. {#rules}

rel: implements -> [[refmatrix/ch-bsd-assessment-2026-11-23#f5]]
rel: depends-on -> [[bsd-closed-findings]]

| id | report | level | finding (one line) | consequence | owner / next | opened |
|---|---|---|---|---|---|---|
| t02-r1-S4 | [[bsd-reprobe-c7550ad5]] (from 2026-11-15-2009-t02-r1-1121b4e) | SKETCHY (handed off) | `register_spawn` has no adopter; per-test leak attribution missing | no leak unseen (ledger + reaper fail the session); attribution only | T0.9 `#c-kit` (`tests/daemons.py`, `recorded_daemon`) | 2026-11-15 |

{#open-table}

**Backfill pending:** the post-reset reports (2026-11-15 onward) are being checked row by row
(agent `bsd-open-backfill`); pre-reset reports (2026-09-14 → 11-14, 254 runs) are not
backfilled. {#backfill}
