---
name: ch-bsd
description: Runtime-integration audit (the bullshit detector) over a commit range via the ch-bsd agent
argument-hint: [optional commit range or short hash — defaults to HEAD~1..HEAD]
allowed-tools: [Task, Read, Grep, Glob, Bash]
model: inherit
enabled: true
---

# Bullshit Detector

Run the runtime-integration audit. Scope: the commit range/hash in the argument, else
`HEAD~1..HEAD`. The question this answers: does the committed code actually execute in
production paths, or is it dead on arrival?

## Steps

1. Dispatch `ch-bsd` with the commit range as its prompt. It loads cross-run memory from
   `workflow/bullshit/` (INDEX.md, IMPRESSIONS.md), then audits EVERY changed line for:
   dead code, stub resolvers/components, unregistered mocks, frontend placeholders,
   unregistered handlers, configs/workers without startup, stale deferrals to completed
   plans, and cheap fixes (test bent to broken code, workaround-instead-of-fix, silent
   scope shrink). On plan-completion audits it also verifies E2E passage (if applicable).
2. The agent writes findings to `workflow/bullshit/{date}-{slug}-{hash}.md`, appends to
   INDEX.md/IMPRESSIONS.md, overwrites `last_run.log`, and returns a verdict + finding
   counts by severity.

## Triage {#triage}

- **BULLSHIT** — dead/unwired code or cheap fix. Block the next task until addressed. A
  single cheap-fix BULLSHIT is enough to block the commit.
- **SKETCHY** — needs explicit justification in writing, or fix next session.
- **MEH** — fix in next sweep.
- Unaddressed BULLSHIT findings are first priority at next session start.

Report a consolidated summary: verdict, counts by severity, and the findings file path.
