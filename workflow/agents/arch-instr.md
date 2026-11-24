---
gmd: "0.1"
id: agent-brief-arch-instr
title: "Architect brief: ADR 0007 instruction architecture + the pre-mod / post-mod re-triage (plan-32 step 4)"
tags: [agent-brief, ch-architect, adr, instructions, plan-32, mod]
metadata:
  node_type: brief
  created: 2026-11-24
---

# arch-instr: ADR 0007 and the re-triage {#root}

rel: implements -> [[plan-32-instruction-architecture]]

You are ch-architect (on Fable). Write **ADR 0007** and a **re-triage table** for the user to
decide. Planning work only: no `src/` or test changes. {#role}

## Inputs (read all) {#inputs}

- [[plan-32-instruction-architecture]]: the principle (deliver each rule at the earliest
  mandatory event where it is actionable; inject once; record use; enforcement over reminder)
  and the T1-T10 table, including the Claude Code facts verified 2026-11-24.
- `workflow/measurements/instruction-census-2026-11-24.md`: 205 rules typed T1-T10, where each
  is stated, its trigger and target mechanism, the first build list, and contradictions C1-C19.
- `workflow/plan-of-plans.md` `#queue` (every pre-mod row) and rows C2, B1, I1, H1; L210-L215.
- `workflow/plans/plan-24-mod-transport.md` + `docs/architecture/explorations/claude-code-mod-transport.md`
  `#facilities` (what the mod adds).
- `docs/external_reviews/cat-herder-merge-2026-11-24.md` (H1; distribution).

## Where {#where}

Clone `/Volumes/littlebig/refmatrix-adr-instr`, branch `adr-instruction-architecture` at
`c5051951`. Write `docs/adr/0007-instruction-architecture.md` (GMD; status `Proposed`) and
`workflow/plans/plan-32-tasks/retriage-2026-11-24.md`; zero errors from `./scripts/lint-gmd.sh`;
commit in the clone. Read-only on every live store (lookups via
`/Users/tholley/claude_tools/refmatrix/scripts/rmx-master`); never `find /`.

## ADR 0007 must decide {#decide}

1. The delivery contract per type T1-T10 (mechanism, trigger, inject-once marker, the telemetry
   row each delivery writes, the 10,000-char cap and how a delivery stays under it).
2. Generation and ownership: every hook/rule/skill is GENERATED (`hooks.py` family, the
   installed config must equal the generated one) and lives as package data in
   `src/refmatrix/templates/`; one source per rule, every other mention a pointer.
3. Distribution: `rmx init` / `install-hooks` now; what moves to the plugin post-mod (agents,
   skills, commands, hooks), and how H1's template merge avoids building twice.
4. Usage telemetry (agents, skills, commands, injected rules via `InstructionsLoaded` and the
   hooks' own rows) feeding the roster decision per project and later `session.measure` tuning.
5. **The 19 contradictions:** for each, which source wins and why (one line each), and the
   edit that removes the loser. Mark any that are the user's call rather than evidence.
6. The always-on budget: what stays always-on (T8 principles + T10 pointers, a byte target),
   and the fate of MEMORY.md + PRIMER (28 KB that state no rule in full).

## The re-triage table {#retriage}

One row per pre-mod POP queue row (C1-C2, P1, T0.9, A1, W1, E1, T1, 4-16, M2, M3, B1, I1, H1)
plus the census's build list grouped into tasks: **keep pre-mod / build natively now /
move post-mod / re-spec onto a mod facility / drop**, each with a one-line reason naming the
mechanism or mod facility. Leading candidates: rows 12, 14, 15 and plan-19 (injection tuning).
The user decides row by row, so state your recommendation and what changes if they choose
otherwise.

## Report (as text, to the lead) {#report}

The commit sha, the ADR's decisions in one line each, the re-triage table, and the
contradictions you mark as the user's call.
