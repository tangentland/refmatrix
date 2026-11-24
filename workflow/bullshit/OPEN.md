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
| 294a-r1-s-2 | [[bsd-294a-r1-1bb14a5b]] | SKETCHY (handed off) | 56 of 213 `tier_unit` files spawn a process or connect to a unix socket at runtime; `tier_of` reads source only (bug-305) | no unsafe run (AC-12's live-touch guard fails the run); the unit tier is mis-classified, so it is not the fast, daemon-free tier it claims | T1 tier layout, bug-305 `open` (L197) | 2026-11-24 |

{#open-table}

**Backfill done (2026-11-24, agent `bsd-open-backfill`)** over the 31 post-reset reports
(2026-11-15 → 11-24, spec reviews and confirm-lites included), rulings searched in
[[plan-of-plans#rulings]] and `workflow/archive/`. BULLSHIT as labelled: 20, all closed `upheld`
with a fix sha reachable from master. SKETCHY re-rated BULLSHIT by F8: 13, 12 closed `upheld`
(8 by [[bsd-reprobe-c7550ad5]], 4 by their confirm-lites); t02 S4 was rated SKETCHY again by
the re-probe and stays open above. GATE (F8): 9, all closed `upheld` (killed in the re-probe).
Handed-off SKETCHY (t02 S4 counted here too): 3, 1 closed (b300 s-1 via bug-302), 2 open. Overruled: 0. Closed rows are
in [[bsd-closed-findings]]. Not rows, for the lead to rate: the t05 confirm-lite 2 note that
mutant MB1d (the op's brief exclusion) survives on `src`, handed to bug-295 (open), which is a
GATE by the P1 rubric; and t03 confirm-lite's A2 survivor (folded before merge, L181).
Pre-reset reports (2026-09-14 → 11-14, 254 runs) are not backfilled. {#backfill}
