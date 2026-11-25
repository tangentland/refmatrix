---
gmd: "0.1"
id: agent-brief-probes-b0
title: "Brief: probes-b0 — I1.b0, probes P1-P11 and the prefilter cost baseline (isolated agent)"
tags: [agent-brief, measurement, plan-32, probes]
metadata:
  node_type: brief
  created: 2026-11-25
---

# probes-b0 {#root}

rel: implements -> [[task-I1.b0-probes]]

You are one isolated agent (a local `rmxtest` user). Do task I1.b0 exactly as specced in
`workflow/plans/plan-32-tasks/task-I1.b0-probes.md` in your clone: read it first, then ADR 0007
`#open` and `#context-facts`. {#role}

- **Scope:** every probe you can run headless (P3-P11, and P1's no-prompt half), each with its
  positive control, plus the cost baseline. **Leave P1's prompting half and P2 for the lead**
  (they need an interactive session); write their probe directories and `run.sh` entries so the
  lead can run them, and mark their rows `pending (lead, interactive)`. {#scope}
- **Where:** throwaway projects under your HOME only; never edit any real project's `.claude/`
  or the user's `~/.claude`. Read-only against every live store; never `find /`; never export
  `REFMATRIX_ROOT`. {#where}
- **Output:** `workflow/measurements/instruction-probes.md` (GMD, lint 0 with
  `./scripts/lint-gmd.sh`) and `workflow/measurements/instruction-probes/`; commit both on your
  branch. Evidence holds key names, lengths, hashes, event/tool names and nonces only (AC-3).
  Tag any verdict that contradicts ADR 0007 `#context-facts` `ARCH-DRIFT` (AC-5). {#output}
- **Report** (REPORT.md, as the start prompt says): the commit sha, one line per probe
  (verdict, Claude Code version, mode), the cost band, every `ARCH-DRIFT`, and what is left for
  the lead. {#report}
