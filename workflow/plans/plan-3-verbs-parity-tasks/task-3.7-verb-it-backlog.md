---
gmd: "0.1"
id: task-3.7-verb-it-backlog
title: "Task 3.7: the verb-it backlog — 49 agent-facing CLI paths in eight families, each family verbed or re-decided"
tags: [task, plan-3, verbs, parity, backlog, deferral]
metadata:
  node_type: task
  status: approved
  plan: plan-3-verbs-parity
  created: 2026-10-19
  wave: "W2-d (proposed; plan-review-2026-10-14 has no W2-d section in this clone — the orchestrator adds it in the dev tree)"
---

# Task 3.7: the verb-it backlog {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Approved — scheduled as wave W2-d (see [[#schedule]])
> Depends on: [[task-3.4-internal-cli-allowlist]], [[task-3.6-r9-remedy]] (#6 re-files `curator scan`)

rel: part-of -> [[plan-3-verbs-parity]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r9-1acadd2#b-1]]
rel: amends -> [[task-3.4-internal-cli-allowlist#r5-legacy]]

## Why {#why}

ch-bsd plan-3 r9 #b-1 (BULLSHIT): task 3.4 classified 50 of the 140 `LEGACY_UNPAIRED` paths as
`verb-it` ("agent-facing; owes a verb") with no task, plan or registry row behind any of them.
The shrink-only pin stops the set GROWING; nothing scheduled it to SHRINK. Plan-3's thesis is
"every capability an agent can call is a verb first" (project-profile #constraints). This task is
the anchor: every `verb-it` path names one family below, and each family closes by gaining verbs
or by being re-decided with a reason. {#why-lead}

Task 3.6 #6 re-files `curator scan` as `maintenance` (the scheduler drives it, not the
gmd-curator agent), so the backlog is **49 paths**. {#why-count}

## Families {#families}

| family | paths | proposed verb(s) | MCP tool(s) |
|--------|-------|------------------|-------------|
| [[#fam-graph-read]] | `neighbors`, `co-occur`, `top`, `describe`, `recall`, `search-dense`, `concept timeline`, `pairs show` (8) | `graph(action=…)` dispatcher | `rmx_graph` |
| [[#fam-canon]] | `canon find`, `canon siblings`, `canon link` (3) | `canon(action=find\|siblings\|link)` | `rmx_canon` |
| [[#fam-matrix-edit]] | `add concept`, `add entity`, `add linkage-type`, `link`, `unlink`, `list entities`, `list linkages`, `list queries`, `run`, `save-query` (10) | `matrix(action=…)` dispatcher | `rmx_matrix` |
| [[#fam-curation]] | `protect`, `unprotect`, `noise`, `unnoise`, `forget` (5) | `curate(action=…, sel=…)` | `rmx_curate` |
| [[#fam-focus]] | `focus tail`, `topics`, `show`, `subject`, `subjects`, `clear-subject`, `composite`, `detour`, `detours`, `return`, `clear` (11) | actions on `rmx_focus` (or a `focus_nav` dispatcher) | `rmx_focus` |
| [[#fam-session]] | `session list`, `recall`, `show`, `stats` (4) | `session(action=…)` | `rmx_session` |
| [[#fam-refine]] | `refine list`, `show`, `accept`, `reject`, `curator drain` (5) | `refine(action=…)` | `rmx_refine` |
| [[#fam-taxonomy]] | `taxonomy list`, `add`, `remove` (3) | `taxonomy(action=…)` | `rmx_taxonomy` |

Total 49. `tests/test_task3_6_r9_remedy.py::VERB_IT_FAMILIES` mirrors this table.

### graph-read {#fam-graph-read}

Read-only graph navigation beside `rmx_context` / `rmx_query`. Fast reads through the replica,
the `payload` wiring class allowed where the CLI reads replica-first.

### canon {#fam-canon}

Cross-project canon view beside `rmx_where`. `find` is a federated read (carries `skipped`);
`link` writes and goes through the daemon.

### matrix-edit {#fam-matrix-edit}

Low-level matrix edits and saved queries. The hidden aliases (`add-concept`, …) follow their
targets (task 3.4 R4). Candidate for re-decision as `operator` if no agent use is shown.

### curation {#fam-curation}

Entity curation the primer tells agents to use. One verb with a selector (`name` / `like` /
`namespace` / `kind`), daemon-routed writes.

### focus {#fam-focus}

STM navigation mid-session. Extends `rmx_focus` with actions rather than adding eleven tools.

### session {#fam-session}

Session-history lookup for recall.

### refine {#fam-refine}

The refinement queue the gmd-curator agent drives (`refine *`, `curator drain`).

### taxonomy {#fam-taxonomy}

The shared tag vocabulary agents validate memory tags against.

## Acceptance criteria per family {#acceptance}

For EACH family, exactly one of:

1. **Verbed.** {#ac-verbed}
   - a `@verb` with a typed signature (an `action` `Literal` for dispatchers) in `verbs.py`;
   - its MCP tool generated from that signature (`set(TOOLS) == set(VERBS)` stays green);
   - each path becomes a `CLI_MAP` twin or a `CLI_ACTIONS` entry with wiring class `calls` (or
     `payload` for replica-first reads), proven by the recorder test with a canary;
   - `PAIRING` / defaults parity rows in `tests/test_verb_parity.py` for the twin;
   - the paths leave `LEGACY_UNPAIRED` (the shrink-only pin then shrinks the baseline).
2. **Re-decided.** The family moves to `operator` / `maintenance` / `harness` /
   `INTERNAL_CLI` with the user's words or a reason checked against the code (as deferral row 47
   did), recorded in the implementation summary. {#ac-redecided}

Global ACs:

- **AC-G1.** Every `verb-it` entry's reason names `task-3.7#fam-<family>` and the path is in that
  family (`test_every_verb_it_path_names_its_task_3_7_family`, RED at 1acadd2). {#ac-g1}
- **AC-G2.** The families partition the 49 paths and each has an anchor here
  (`test_the_backlog_families_partition_and_are_anchored_in_the_spec`). {#ac-g2}
- **AC-G3.** `workflow/deferral_registry.md` carries the row pointing at this task; it moves to
  resolved when every family is verbed or re-decided. {#ac-g3}
- **AC-G4.** Plan-3 closes only when this task is `completed` OR the user explicitly carries it
  past plan-3's closure as a wave item (the closure note names it). {#ac-g4}

## Schedule {#schedule}

Wave **W2-d**. `workflow/plan-review-2026-10-14.md#t10-waves` in this clone has Wave 2 but no
`W2-d` entry; the orchestrator adds it in the dev tree. Families may land independently; each
landing shrinks `LEGACY_BASELINE` in `tests/test_verb_parity.py`.

## Definition of done {#done}

- Each family: RED (recorder/parity rows) before GREEN; mutation check; summary rows.
- `@ch-bsd` over the range: no unaddressed BULLSHIT.
