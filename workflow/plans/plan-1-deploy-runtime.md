---
gmd: "0.1"
id: plan-1-deploy-runtime
title: "Deploy runtime: `rmx`, daemons, and hub execute the deploy tree, and say so"
tags: [plan, remediation, bsd]
metadata:
  node_type: plan
  status: completed
  created: 2026-09-14
  bsd_findings: "#bs-2"
---

# Proposed Plan: Deploy runtime: `rmx`, daemons, and hub execute the deploy tree, and say so {#root}

**Date:** 2026-09-14
**Status:** Accepted
**Location:** `workflow/plans/plan-1-deploy-runtime.md` — permanent home; stage is `metadata.status`.

rel: evidence-for -> [[bsd-0661-e2e-memory-bridge]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: specifies -> [[task-1.1-plan-1-deploy-runtime]]
rel: specifies -> [[task-1.2-plan-1-deploy-runtime]]
rel: specifies -> [[task-1.3-plan-1-deploy-runtime]]

## Context {#context}

BSD #bs-2: `~/refmatrix/.venv` is an editable install of the DEV checkout (`__editable__.refmatrix-0.66.0.pth` →
`/Users/tholley/claude_tools/refmatrix/src`, written 2026-09-14 18:00 by last session's save-state step 4). `~/bin/rmx`, every
per-store daemon, and the hub import dev source; a "deploy fast-forward" changes nothing; the fleet ran uncommitted code all day.
Nothing in `rmx daemon status`, `rmx hub status`, or `rmx --version` reveals which tree is imported. Three memories
(`feedback_rmx_binary_is_deploy`, `feedback_refmatrix_dev_deploy_split`, `reference_editable_venv_distinfo_lag`) and the
save-state feedback memory assert or instruct the wrong thing.

## Proposed Approach {#proposed-approach}

1. `upgrade.runtime_identity()` → `{version, import_path, install_root, editable_target, dev_tree: bool}`; surfaced by
   `rmx --version --verbose`, `rmx daemon status`, `rmx hub status` (one line: `code: <import_path> [DEV TREE]`), and a
   hub alert when any supervised daemon reports `dev_tree=True`.
2. `rmx upgrade --from-dev` re-verifies after `pip install -e <install_root>` that the editable target IS the install root
   (test on a tmp venv-less fake: parse the `.pth` it would write).
3. Operate: reinstall the deploy venv editable from `~/refmatrix`, relaunch daemon + hub, verify; supersede the wrong memories
   with one correct `feedback_deploy_tree_is_the_runtime` memory; fix save-state feedback step 4 text.

## Open Questions {#open-questions}

### Q1: Q1 Where does the identity check live? {#q1}
**Status:** RESOLVED

**Decision:** `upgrade.py` (already owns install-root + interpreter discovery); status commands call it. No new module.
**Rationale:** see Decisions Log.

### Q2: Q2 Alert or refuse when dev_tree is detected on a daemon? {#q2}
**Status:** RESOLVED

**Decision:** Alert (hub `queues` channel + red status line). Refusing would strand a workstation that only has the dev tree.
**Rationale:** see Decisions Log.

### Q3: Where does the recurrence guard actually fire? {#q3}
**Status:** RESOLVED (after ch-bsd bsd-plan1 #b-1/#b-2, 2026-09-14)

**Decision:** (a) `upgrade.upgrade()` calls `runtime_identity()` FIRST on every path — `--check`,
"already up to date", changed head — and raises when `dev_tree` is true; `verify_editable` also runs
on the up-to-date path. (b) `rmx daemon restart --relaunch` compares the new daemon's `code_path`
to this CLI's `import_path` and fails loud on mismatch, because ff + relaunch IS the documented
deploy path and never enters `upgrade()`. (c) The `global:queues` alert gates on `dev_tree`
(`_queue_row_is_hot`). (d) `hub status` renders three states: verified path, `[DEV TREE]`, and
`[UNVERIFIED vX]` for a daemon whose ping carries no code path; the hub reports its own identity.
**Rationale:** the first cut guarded the fixed state, not the incident state (the deploy tree was
at master's sha and the check looked at the imported tree's venv).

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Q1 Where does the identity check live? | `upgrade.py` (already owns install-root + interpreter discovery); status commands call it. No new module. | 2026-09-14 |
| Q2 | Q2 Alert or refuse when dev_tree is detected on a daemon? | Alert (hub `queues` channel + red status line). Refusing would strand a workstation that only has the dev tree. | 2026-09-14 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 1.1 | runtime_identity + status surfaces | — |
| 1.2 | upgrade --from-dev reinstalls from the install root and re-verifies | 1.1 |
| 1.3 | Operate + memories | 1.1, 1.2 |

## Execution contract {#execution}

TDD per [[tdd-governance]]: RED test recorded to `workflow/review-output/` before GREEN; mutation check on every new test;
implementation summary per task under `workflow/implementation_summaries/`; then `@ch-bsd` over the plan's commit range —
remedy and re-review until the verdict is CLEAN; then the plan's `metadata.status` → `completed`.
