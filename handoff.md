---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-05 (session d259aee1 — opened 2026-09-15, resumed across twenty
days; see [[#stale-context]]). Prior handoff archived at
`workflow/past_handoffs/005-grep-contract-plan3-r8-bsd-rounds_2026-10-01.md`.

## State {#state}

`master` = **c555839**, 13 ahead of `origin/main` (0.73.0 deployed; fleet 8/8 +
hub on v0.73.0 as of 2026-10-01). Full suite **2238 passed** at `e0b7df6`;
HEAD collects 2245 after round 8.

GMD lint was **0 errors** at `c555839` and is **4 errors** now — not mine. The
other session's `84cd783` ("Namespace GMD doc ids by project") renamed ADR doc
ids, so four memory files citing `[[adr-0002-subject-memory-container]]` no
longer resolve (`feedback_mcp_first_agent_stm` ×2,
`project_memory_compile_design`, `project_memory_compile_shipped`). Left for
whoever owns that sweep — a half-applied id migration should be finished by its
author, not patched by a passer-by. Flagged, not fixed.

**Someone else is working in this tree.** At handoff time the checkout sits on
branch `gmd-conformance-sheep`/`gmd-conformance-sweep` at `84cd783`
("Namespace GMD doc ids by project"), with 12 modified `.claude/agents/*.md` and
an untracked `tools/gmd/audit.py` — none of it mine. I staged only `handoff.md`
and ran save-state WITHOUT `--commit` so their in-flight work was not swept into
my commit. Do not assume a clean tree belongs to you.

## Completed this session {#completed}

- **plan-3 round 8** (`0e3002f`, `5960208`, merged `273cc16`) — remedies ch-bsd
  plan-3 r7 (DIRTY 2B/2S/2M), every finding against round 7's own work.
  `_replica_bundle` takes `on_error` so both `skipped` legs can fire; promote's
  GLOBAL write bounded (`timeout=_left(30.0), retries=0`) after still costing
  180.2 s; one `_echo_skipped` with `app.js` reading `skipped`; promote
  subtracts its probe. **Plus the THIRD `_replica_bundle` caller
  (`_locate_one_project`), which no finding named** — found by sweeping callers.
  7/7 mutations load-bearing.
- **0.73.0** (`720cea7`, `7e76610`) — `_resolve_output_shape` as the single
  output-shape decision; `_grep_run`'s duplicate fallback deleted; hub reaps
  `global:queues` past 3 days (bus **3,196 → 163**).
- **GMD gate** (`40edd2f`) — a missing `gmd:` key is now an ERROR, with a
  reasoned line-1 opt-out. Seven `eval/` docs converted (60 anchors); two flat
  files opted out. 9 tests, mutation-checked.
- **Five ch-bsd rounds, all DIRTY** — plan-3 r7, plan-6 r1 (first audit ever),
  plans 8/9/10 r5. Reports in `workflow/bullshit/`; `last_run.log` carries all
  three.

## Outstanding {#outstanding}

**Bugs — 6 open, 1 remedied-on-a-hypothesis** (registry is 66 rows):

- **bug-065** `rmx save-state` writes memory rows `memory recall` CANNOT see —
  the bridge inserts without vectors and `finalize_save_state` has zero
  occurrences of `embed`. **Start here**: it is a memory path, in the command
  whose job is durability, and the fix is bounded (drain the embed queue,
  counted and printed). See [[feedback_verify_memory_by_recall_not_get]].
- **bug-062 / 063 / 064 / 066** the grep family — see
  [[project_grep_surface_defect_family]]. 062/063/064 are one function (the rg
  fallback's argv construction). **bug-066 needs your decision first**:
  `RMXGREP_MODE=rich` in `~/.claude/settings.json` + `settings.local.json`
  overrides a TTY probe that already decided plain, so every agent grep is an
  index query with ERE semantics. Drop it, scope it, or accept it — it is config,
  so not an agent's call.
- **bug-055** evals score against `[UNVERIFIED]` daemon code. **bug-015**
  remedied, root cause still a hypothesis; waits for the next wedge's stack dump.

**Plans — 5 `in-progress`, none flippable:**

| plan | blocker |
|---|---|
| 2 | #s-2, #s-3 (replica-first probe unscoped — a WRITE resolves off a lagging snapshot; do this one first), #m-4 |
| 3 | round 8 landed; a round-9 re-review is the auditor's call |
| 4 | #s-2, #s-3, #s-4 (live `hub.log` test pollution, 154 lines and growing), #m-5, #m-6 — three are one-liners |
| 6 | #b-1 **the plan says both Delete and Keep for `duckdb_view.py`** — needs a DECISION, not code. plan-6's reading: Delete is correct, the reversal was mistaken on all three of its facts. #b-2 the "every file" registry claim |
| 8 | `corroborated`'s call site deletable with 108 GREEN while producing 44% of briefs; `parse_gmd` zero callers |
| 9 | paperwork only — two missing summaries + one number |
| 10 | the negative result is WRONG for the larger half: measured on `--format json`, which omits the STM composite (59% of the payload, byte-identical 7/7 pairs) |
| 7 | "dense blocked bug-030" is STALE — bug-030 is fixed and reachable; the dense rows are missing for want of a RE-RUN |

## Stale context, twice {#stale-context}

This session opened 2026-09-15 and resumed over twenty days. Early turns planned
plan-4/plan-2 remediation that plan-12 had already shipped; it surfaced only
because `render_hub_plist` already carried a fix a finding said was missing.
Later, three mutation-running auditors were spawned into ONE working tree and
clobbered each other's evidence — my error. **On resume, re-read `git log` and
the version before acting on a recalled plan, and give every parallel auditor its
own `git worktree --detach`.**

## Lessons recorded as memory {#lessons}

- [[feedback_red_test_must_fail_at_head]] — three faked-collaborator tests in one
  session; mutation checking cannot catch it, running the suite at HEAD can.
- [[feedback_verify_memory_by_recall_not_get]] — bug-065's standing rule.
- [[project_grep_surface_defect_family]] — six rows, one root shape.
- [[feedback_commit_before_mutation_revert]] and
  [[feedback_verify_fix_reachable_from_master]] from earlier in the session.

## User Preferences {#user-preferences}

- Lookups via `rmx context` / `rmx grep` / `tldr`; `sed -n` only for known line
  ranges, never discovery. The user pushes to GitHub.
- Commit messages via `-F` or a quoted heredoc — **never `-m` with backticks**:
  on 2026-10-01 bash command-substituted them and `rmx save-state` EXECUTED.
- After a deploy, message every project on `proj:<name>:features`.
- Plans first, TDD, BSD re-review until clean. A plan flips to `completed` only
  on a clean gate, never on my say-so.
