---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-11-10 (session 7aea273d, continued over several compactions). Prior handoff archived
at `workflow/past_handoffs/018-wave0-plan24-specs-hypertree_2026-10-20.md`. The user is
restarting the client; this is the resume point.

rel: supersedes -> [[handoff-018-wave0-plan24-specs-hypertree]]
rel: depends-on -> [[plan-of-plans#goal-2026-11-10-progress]]

## State {#state}

- **Deployed: 0.81.2** (hub + 8 daemons). Nothing released since. Do NOT deploy plan-26 work
  until bug-199/200 and the 26.2/26.3 merges land and a release is cut.
- **master** is 32+ commits ahead of `origin/main` (`6f593ca`); the user pushes
  (`git -C /Users/tholley/claude_tools/refmatrix push origin master:main`). gmd upstream pushed
  (`efb514a`).
- **Merged today:** 26.1 follow-up r3 (`25af9ca`), ac6-fixture (`69ecb21`, bug-156 fixed;
  fixture's old bug-137 renumbered bug-196), wave0-spec-reviews (`9eaf00b`, bug-191 fixed, lint
  gate exit 0), bug-195 cut-hook repair (`102524d`, live repair applied + 29 curated hooks
  restored), 26.6 compile hygiene (`8a867bc`; still in-progress: R3 residual after 26.7),
  bug-197/198 (`a0056fc`).
- **Agents:** `.claude/agents/ch-{implementer,test-engineer,bsd,architect,alignment}.md` now carry
  `effort: high` (`93086ed`, `2713b0e`). Subagents do not inherit the session's `/effort`.

## In flight — three littlebig clones {#in-flight}

All three were told to pause, commit WIP with a handoff body, and stop (2026-11-10 ~12:15).

| clone (`/Volumes/littlebig/…`) | branch | state at save | next step |
|---|---|---|---|
| `refmatrix-plan26-2` | `task-26.2-bridge-move-safety` | RED `27e21dc`+`75cd42e` (25 tests); spec decisions `82a5caf`, AC-4c `aff8953`; GREEN was mid-run (src uncommitted at save; expect a `wip(26.2 GREEN)` commit) | read the wip commit body; finish GREEN; ch-bsd r1 |
| `refmatrix-plan26-3` | `task-26.3-savestate-subfolder` | GREEN `3733dab`/`640e32d`; ch-bsd r1 GO (`56111ce`, report persisted); remedy RED `994dd96` (#rm-newer-copy, 7 failing); remedy GREEN was mid-run (src uncommitted; expect `wip(26.3 remedy-r1 GREEN)`) | finish remedy GREEN (reword the "crash mid-move" message); focused ch-bsd r2; merge |
| `refmatrix-bug199-200` | `task-bug199-200-repair-index-and-brief-old-scope` | GREEN done `e473610`/`e2a85cd`/`fa16806`, handoff `20b6293`; 13/13 RED pass; mutation M3 (MEMORY.md not backed up) SURVIVED | test-engineer: a test asserting `<backup dir>/MEMORY.md` equals the pre-apply index; then ch-bsd r1 over `771117c..HEAD`; merge; mark bug-199/200 fixed |

Merge order between 26.2 and 26.3 is free; the SECOND to merge carries 26.2 AC-4c (save-state
pair + another duplicate id). 26.3's pair rule lives in the walk (`memory_layout`); 26.2's
`split_claims` must not add a second exemption.

**26.3 merge after `task-user-level-state-commands`** (the handoff pair now installs at user
level; `.claude/commands/{save,recall}-state.md` are deleted): keep the deletion on the
modify/delete conflict, take that branch's template recall-state, and drop AC-7's project-copy
parameter + `test_ac7_the_installed_command_is_the_template`
([[impl-task-user-level-state-commands#in-flight]]).

## Open items {#open}

- **Before the next release:** bug-199, bug-200 (fix in the bug199-200 clone), 26.2, 26.3.
- **Pre-existing failures (registered):** bug-127/168 (`test_brief_real_daemon` DuckDB lock),
  bug-170 (hooks-sync test under the sandbox HOME), bug-190 (rerank load flakes), bug-196 (AC-6
  recall per-channel split), bug-194 (truncated status frame under load).
- **Plan-26 order after these:** 26.4 → 26.5 (now owns the rollback-moves-`savestates/`-back AC,
  `b5ed7b3` in the 26.3 clone) → 26.7 → 26.6 R3 residual → 26.8; then bug-185 → 23.2 → 23.1 →
  23.3 ∥ 23.5; plan-25 (25.1 R10 now splits `rmx_bus_pub`'s `about` field, `d6e0ec1`) and
  plan-27 after their dependencies.
- **User-level edits this session (not in the repo):** `~/.claude/statusline.sh` (project | Ctx
  coloured purple ≥70 / auto-mode rgb(255,204,0) ≥80 / bold rgb(200,0,0) ≥90 with save/HANDOFF
  words | Tok | Wk | model+version; weekly count fixed); 8 project `.claude/statusline.sh` files
  are thin wrappers (refmatrix committed `48e6586`; the others uncommitted in their repos);
  `~/.claude/MEMORY-RULES.md` `#frontmatter` notes save-state `updated:` is an ISO timestamp.
- **littlebig:** only the three in-flight clones plus four October store-copy scratch dirs
  (kept by the user's choice) remain.

## Resume {#resume}

1. `/recall-state`; read this file and `workflow/plan-of-plans.md#goal-2026-11-10-progress`.
2. `git -C` each in-flight clone: read the newest commit body (the agent's handoff).
3. Start fresh agents (they now run at `effort: high`) from those commits, in the order above.
