---
gmd: "0.1"
id: i1a-memory-edits
title: "I1.a: the memory edits for the lead (C8, C9, C10, C11, C13, C17, C18, R007)"
tags: [review-output, plan-32, i1, contradictions, memory]
metadata:
  node_type: brief
  created: 2026-11-25
  author: build-i1a
---

# I1.a memory edits, for the lead {#root}

rel: implements -> [[task-I1.a-contradiction-edits#lead-edits]]

Memory files are the lead's ([[task-I1.a-contradiction-edits#lead-lead]]). Each edit below names
the file, the action under `MEMORY-RULES.md` `#amend-tree`, and the exact text. Dir:
`~/.claude/projects/-Users-tholley-claude-tools-refmatrix/memory/`. Every file read at the
clone's base `0c798f28` on 2026-11-25; re-read before writing. After writing: lint each file
(`python3 tools/gmd/lint.py <path>`), run the bridge, and check each with `rmx memory recall` on
the phrase given (AC-8). {#lead}

## Summary {#summary}

| # | File | Action | Why this action | Recall phrase (AC-8) |
|---|---|---|---|---|
| C17 | `feedback_rmxgrep_no_plain_escape` | amend: new `feedback_rmxgrep_plain_env_is_standing` | same rule + a refined scope (≥80% kept) | "inert at the shim" |
| R007 | `feedback_refmatrix_dev_deploy_split` | amend: new `feedback_deploy_tree_copy_only_under_grant` | same rule + an exception (granted copies) | "names every file that differs" |
| C8 | `feedback_deploy_tree_is_the_runtime` | overwrite in place, bump `updated:` | one sentence corrected | "relaunch-fleet" |
| C9 | `feedback_proportionate_process` | overwrite in place, bump `updated:` | one clause corrected | "SKETCHY earns no second round" |
| C10 | `feedback_track_questions_by_id` | amend: new `feedback_question_ids_are_the_pops_counter` | same rule + the ledger moved and the counter's scope changed | "the POP's counter, across sessions" |
| C11 | five superseded memories | index lines removed from `MEMORY.md` | a superseded memory has no index line | n/a (check `MEMORY.md`) |
| C13 | `feedback_no_silent_failures` | amend: new `feedback_stm_capture_is_a_memory_path` | the carve-out is withdrawn and STM capture named (Q56 = a) | "STM capture is a memory path" |
| C18 | `reference_hook_output_cap_measured` | overwrite in place, bump `updated:` | one figure replaced by a pointer | "HOOK_COMMAND_BUDGET_BYTES" |

{#summary-table}

Note on C13: the carve-out in the file today is "file-sync hooks (rmx sync / curator queue):
masking IS fine" ([[instruction-census-2026-11-24#c13]]); the file names no capture hooks. The
amendment withdraws that bullet as a whole and names STM capture, as the spec and ADR 0007 C13
say. If the lead means to keep masking on `rmx sync` / curator hooks, that is a new question,
not this edit. {#c13-note}

## C17: `feedback_rmxgrep_plain_env_is_standing.md` (new) {#c17}

````markdown
---
gmd: "0.1"
id: feedback_rmxgrep_plain_env_is_standing
title: "RMXGREP_MODE=plain in the global settings is the user's standing setting, not a violation; never /usr/bin/grep"
tags: [feedback, retrieval]
metadata:
  node_type: memory
  type: feedback
  originSessionId: <this session's id>
  created: 2026-11-25
  updated: 2026-11-25
---

# The global `RMXGREP_MODE=plain` is the user's setting; the grep rule stands {#root}

`RMXGREP_MODE=plain` in the global settings is the user's standing setting and is not a
violation; the value is inert at the shim. What stays: never `/usr/bin/grep`; a grep reading a
pipe stays byte-exact. {#rule}

**Why:** ADR 0007 C17 and the user's Q57 = b (L221, 2026-11-24): the settings stay as they are
and the rule is reworded to match them. The shim treats any value but `rich` as auto, so the env
line routes nothing around the index ([[instruction-census-2026-11-24#c17]]). {#why}

**How to apply:** do not flag or remove the global env line, and do not count it as a bypass in
a review. A caller still never sets `env RMXGREP_MODE=…` on a command to reach the real grep,
never calls `/usr/bin/grep`, and never pipes input to reach it; lookups stay `rmx context`,
`rmx grep`, `tldr`. {#how}

rel: amends -> [[feedback_rmxgrep_no_plain_escape]]
````

## R007: `feedback_deploy_tree_copy_only_under_grant.md` (new) {#r007}

````markdown
---
gmd: "0.1"
id: feedback_deploy_tree_copy_only_under_grant
title: "The deploy tree is never edited in place; a file is copied into it only under a user grant, and a deploy names every dirty file first"
tags: [feedback, deploy]
metadata:
  node_type: memory
  type: feedback
  originSessionId: <this session's id>
  created: 2026-11-25
  updated: 2026-11-25
---

# Copies into ~/refmatrix only under a grant; a deploy reads its status first {#root}

refmatrix is edited only in `~/claude_tools/refmatrix`. The deploy tree is never edited in
place. A file is copied into it only under a grant the user has given; a granted copy leaves it
dirty, so a deploy first reads `git -C ~/refmatrix status --short` and names every file that
differs. {#rule}

**Why:** the user's Q57 = b (L221, 2026-11-24): the standing `cp … ~/refmatrix/src/…` grants in
`.claude/settings.local.json` stay, so the old "do not cp" line is reworded to match them
(ADR 0007 `#r007-q57`). A dirty deploy tree would make "deploy only from a committed `master`
sha" false without anyone seeing it. {#why}

**How to apply:** Edit and Write never target `~/refmatrix/**`. A `cp` into it happens only under
an existing grant. Before a fast-forward, run `git -C ~/refmatrix status --short`; name every file
that differs, and resolve it before the pull. {#how}

rel: amends -> [[feedback_refmatrix_dev_deploy_split]]
````

## C8: `feedback_deploy_tree_is_the_runtime.md` (overwrite) {#c8}

Bump `updated: 2026-11-25`. Replace the two lines

```text
- Deploy = `git -C ~/refmatrix pull --ff-only origin master && rmx daemon restart --relaunch`.
  The hub self-restarts on the version handshake.
```

with

```text
- Deploy = `git -C ~/refmatrix pull --ff-only origin master && rmx daemon restart --relaunch`,
  then the hub and fleet steps of `workflow/ORCHESTRATION.md` `#release` step 3
  (`rmx hub relaunch-fleet`; a stale hub: `rmx hub stop` + one `launchctl kickstart`). The
  version handshake did not restart the hub in 90 s (0.85.0, 0.85.1).
```

If `hub.py`'s handshake is meant to restart the hub, the 90 s miss gets a `bug_registry.md` row
(the lead allocates the id). {#c8-registry}

## C9: `feedback_proportionate_process.md` (overwrite) {#c9}

Bump `updated: 2026-11-25`. In `#rule`, replace

```text
one review pass unless it finds BULLSHIT or SKETCHY;
```

with

```text
one review pass unless it finds BULLSHIT (SKETCHY earns no second round, L213);
```

## C10: `feedback_question_ids_are_the_pops_counter.md` (new) {#c10}

````markdown
---
gmd: "0.1"
id: feedback_question_ids_are_the_pops_counter
title: "Q ids come from the POP's counter, across sessions; the ledger is the POP"
tags: [feedback, questions, decisions]
metadata:
  node_type: memory
  type: feedback
  originSessionId: <this session's id>
  created: 2026-11-25
  updated: 2026-11-25
---

# A question's id is the POP's next `Q<n>`, across sessions {#root}

A question to the user takes the next id from the POP's counter, across sessions (never reset per
session, never reused), and its row goes in `workflow/plan-of-plans.md` `#questions` before it is
asked. `workflow/open-questions.md` no longer exists. Everything else in
`feedback_track_questions_by_id` stands: show the id, end each reply with the open ids, an
interpreted answer stays open until confirmed. {#rule}

**Why:** ADR 0007 C10: the user, 2026-11-15, "any L, D, or Q must be placed in the POP before being
amended to a plan" (`feedback_ldq_enter_pop_first`); the per-session counter and the separate
ledger file were left in this rule after the move. {#why}

**How to apply:** read the POP's highest `Q<n>` (open and finished rows) before asking; add the
row; then ask. A plan's own D label is also a valid id ([[feedback_plan_d_labels_are_valid_ids]]).
{#how}

rel: amends -> [[feedback_track_questions_by_id]]
rel: depends-on -> [[feedback_ldq_enter_pop_first]]
rel: related-to -> [[feedback_plan_d_labels_are_valid_ids]]
````

The body's bare `[[feedback_plan_d_labels_are_valid_ids]]` in `#how` may be dropped if the lint
warns: the `rel:` line carries the edge. {#c10-note}

## C11: index lines to remove from `MEMORY.md` {#c11}

The five superseded memories of [[instruction-census-2026-11-24#superseded-indexed]] lose their
index lines (the files stay; the supersession edges stay):

1. `feedback_rmx_binary_is_deploy.md` (superseded by `feedback_deploy_tree_is_the_runtime`)
2. `feedback_rmxgrep_plain_escape.md` (by `feedback_rmxgrep_no_plain_escape`)
3. `feedback_bsd_iterate_before_surfacing.md` (by `feedback_lean_process_reset`)
4. `feedback_operational_content_not_in_graph.md` (by
   `feedback_operational_content_same_partition_not_skewing`)
5. `feedback_plan_decisions_are_questions.md` (by `feedback_plan_d_labels_are_valid_ids`)

If the renderer restores a line, it waits for I1.h's index rule
([[task-I1.a-contradiction-edits#lead-edits]]). {#c11-list}

## C13: `feedback_stm_capture_is_a_memory_path.md` (new) {#c13}

````markdown
---
gmd: "0.1"
id: feedback_stm_capture_is_a_memory_path
title: "STM capture is a memory path: no masking on any hook between a memory and the store, sync and capture hooks included"
tags: [feedback, hooks, memory, stm]
metadata:
  node_type: memory
  type: feedback
  originSessionId: <this session's id>
  created: 2026-11-25
  updated: 2026-11-25
---

# No masking carve-out: STM capture is a memory path {#root}

The "file-sync hooks (rmx sync / curator queue): masking IS fine" carve-out of
`feedback_no_silent_failures` is withdrawn. STM capture is a memory path: the `rmx focus hook`
entries (`input`, `tool`, `tool-pre`, `say`) surface their failures like every other hook
between a memory and the store (`CLAUDE.md` `#no-silent-failures`, "hooks (STM capture
included)"). {#rule}

**Why:** the user, Q56 = a (L221, 2026-11-24): STM is promoted to durable memory, so a silent
capture failure loses it (ADR 0007 C13). {#why}

**How to apply:** no `2>/dev/null` and no `|| true` on a capture or sync hook. A failure is
counted and surfaced once at SessionStart, exit 0. The four installed entries still mask until
I1.b's install window ([[task-I1.b3-dispatcher#ac-8]]); that is known, not a reason to add a
new masked entry. {#how}

rel: amends -> [[feedback_no_silent_failures]]
````

## C18: `reference_hook_output_cap_measured.md` (overwrite) {#c18}

Bump `updated: 2026-11-25`. In `#how`, replace

```text
**How to apply:** budget every generated hook COMMAND (not every event) at 0.9 × 10,000 = 9,000 B;
```

with

```text
**How to apply:** budget every generated hook COMMAND (not every event) at
`hook_budget.HOOK_COMMAND_BUDGET_BYTES` (`src/refmatrix/hook_budget.py`, 0.95 × the cap; each
channel's share is `CHANNEL_BUDGET_BYTES`);
```

The measured facts in `#fact` stay as written.
