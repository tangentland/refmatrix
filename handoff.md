---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-01 (session d259aee1, long-running — it opened 2026-09-15 and its
early turns carried nine-day-stale context; see [[#stale-context]]). Prior
handoff archived at `workflow/past_handoffs/004-grep-contract-bus-retention-prior_2026-09-20.md`.

## Completed {#completed}

All on `master`, merged `--no-ff`, deployed. Deploy tree and fleet at **0.73.0**
(8/8 daemons + hub on v0.73.0, no STALE rows). Full suite **2,238 passed**
(`workflow/review-output/pytest-0.73.0-full.log`).

- **plan-3 round 7** (`763aaa0`, merged `b252a09`) — closed the r6 verdict's four
  findings: `memory get --degree N` routed through `verbs.attach_context` after a
  bare `NameError` on the deployed build (bug-026); `memory promote` through the
  bounded verb after 180.2 s + an empty message on a held writer (bug-027);
  `federated_concept`'s silent per-root swallow and `canon find`'s discarded
  `skipped` list; one test per unguarded `federated_where` leg. 8 of 8 mutations
  kill their target; regression 162 passed. **This landed nine days ago and the
  tree has moved far past it** — plan-12 and bugs 029–058 all post-date it.
- **grep output contract + hub bus retention** (`86ac5d9`, merged `720cea7`,
  version `7e76610`) — see [[#grep]] and [[#retention]]. bug-059, bug-060,
  bug-061 closed; bug-058's row corrected.

### The grep work {#grep}

`_resolve_output_shape(gf, paths)` is the single place the output shape is
decided; `_grep_run`'s inlined DUPLICATE of `_grep_rg_fallback` is deleted (one
builder, one banner, guarded by a test). The tool is always asked for canonical
`file:line:text` and the shape applied at render time. Three parse-time gates
that hid `-o` are open: the `stdin_mode` gating, the `--flags` letter set, and
click's `-h`/`--help` claim.

**Behaviour change:** a bare single-file read prints BARE lines, as grep and
ripgrep do. Provenance is opt-in via `-n`/`-H`. Verified 8/8 byte-identical to
real grep by DIRECT EXEC — a Bash-tool shell has `grep`/`rg` rewritten to the
shim and cannot serve as a control.

### The retention work {#retention}

`Bus.reap_channel` + `Hub._bus_retention_once` on the publish tick, 3 days,
`global:queues` only. First sweep **3,196 → 163** active; `proj:*` untouched.

## Git State {#git-state}

- `master` at `7e76610` = deploy tree. Lint: 1 pre-existing error, none in files
  touched this session. Registry 61 rows.
- Branches kept (never deleted): `remedy-plan3-r7`, `fix-bus-retention-grep-flags`,
  `task-grep-dropin-contract` (now merged), `remedy-plan4-r5` (zero commits, a
  stale label on `00d0ded` — plan-4's round-4 findings were already closed by
  plan-12, so it was abandoned deliberately).
- **Not pushed to GitHub** — the user pushes.

## Outstanding {#outstanding}

- **bug-055 `open`** — evals score against a daemon whose code path reads
  `[UNVERIFIED]`; an eval reported 0.72.4 numbers for unknown code, and
  restarting that daemon moved scan-prompt 0.433/0.230 → 0.444/0.257. Fix: the
  production harnesses assert the serving daemon's version and REFUSE to score
  against `[UNVERIFIED]`. Same family as [[#stale-context]] and bug-058's row.
- **bug-015 `remedied`, seen 3** — daemon wedge; bounded and instrumented, root
  cause still a hypothesis. Exit criterion is its own: the next wedge produces a
  `kill -USR1` stack dump.
- **Unfiled, deliberately** — a peer's backgrounded `psql … | grep -vE …` that
  produced a 0-byte file containing repo matches. Not reproducible here; has the
  pre-0.65.1 stdin-race signature. Both peers asked for a deterministic repro
  plus `rmx version -v`.
- **plan-2 and plan-4 still read `in-progress`** in plan-of-plans while plan-12
  closed their round-4/round-9 findings. Unverified whether that is stale
  bookkeeping or real remaining scope — worth one pass before trusting either.
- MEMORY.md is generated under a cap now (bug-042); it is not hand-edited.

## Stale context, and what it cost {#stale-context}

This session opened 2026-09-15 at `b9a89b1`/0.69.1 and resumed repeatedly over
sixteen days. Its early turns planned plan-4 and plan-2 remediation that
plan-12 had already shipped; the discrepancy surfaced only because
`render_hub_plist` already carried the fix a BSD finding said was missing. **On
resume after a long gap, re-read `git log` and the version before acting on a
recalled plan.** The same shape appears in bug-055 and in bug-058's row: a
recorded claim trusted instead of the running state.

## Lessons recorded as memory {#lessons}

- `feedback_verify_fix_reachable_from_master` — bug-058 read `fixed` for eight
  days while unmerged; verify reachability before writing a status.
- `feedback_commit_before_mutation_revert` — the mutation loop's
  `git checkout --` destroyed an uncommitted implementation; commit first.
- `project_grep_output_shape_one_resolver`, `project_bus_retention_global_queues`.

## Past Sessions {#past-sessions}

| # | Session | Date | Archive |
|---|---------|------|---------|
| 004 | prior (plans 7–13, bugs 041–058) | 2026-09-20 | `workflow/past_handoffs/004-grep-contract-bus-retention-prior_2026-09-20.md` |
| 003 | plan-12, bugs 041–043 | 2026-09-16 | `workflow/past_handoffs/003-plan-12-close-bug-041-043_2026-09-16.md` |

## User Preferences {#user-preferences}

- Lookups via `rmx context` / `rmx grep` / `tldr context`; `sed -n` only for
  line ranges already known, never for discovery.
- Plans first, TDD, BSD re-review until clean. The user pushes to GitHub.
- After a deploy, message every project on `proj:<name>:features` with the
  change set — done this session for all 8 projects.

## Hand-Off Notes {#hand-off-notes}

- Deploy recipe unchanged: commit on `master` → `git -C ~/refmatrix pull
  --ff-only origin master` → `launchctl kickstart -k gui/$UID/com.refmatrix.hub`
  → `rmx hub relaunch-fleet` → verify no STALE rows in `rmx hub status`.
- The retention sweep waits one full `QUEUE_ALERT_INTERVAL_S` (30 min) after a
  hub restart before its first tick. To force it now:
  `~/refmatrix/.venv/bin/python -c "from refmatrix.bus import Bus;
  print(Bus().reap_channel('global:queues', older_than_days=3))"` — back up
  `~/.refmatrix/bus/bus.db` first.
