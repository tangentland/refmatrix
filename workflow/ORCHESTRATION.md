---
gmd: "0.1"
id: orchestration
title: "Operating procedure: how the lead runs planning, tasks, reviews and releases"
tags: [workflow, governance, orchestration, process]
metadata:
  node_type: governance
  created: 2026-11-15
---

# Operating procedure {#root}

How work actually moves through this repo: who does what, in which order, and what gates each
step. Adopted 2026-11-15 from the practice of the 0.83.0 / 0.83.1 / plan-29 / plan-30 cycle (the
user: Q23-Q26 = a; [[workflow-practice-review-2026-11-15]]). CLAUDE.md
`#task-completion-workflow` summarises this file; this file is the procedure.

rel: derives-from -> [[workflow-practice-review-2026-11-15]]
rel: amends -> [[tdd-governance]]
rel: amends -> [[PLANNING_WORKFLOW]]
rel: depends-on -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[open-questions]]

## 1. Roles {#roles}

- **The lead** (the main session) orchestrates. It writes no `src/` and no tests. It dispatches
  agents, rules on findings, allocates registry ids, commits by pathspec on `master`, merges,
  releases, deploys, and does every write to a live store, announced and backed up first.
  {#roles-lead}
- **Agents** work in their own clone, `/Volumes/littlebig/<project>-<worker>` (never the dev
  tree, never a git worktree). They are **read-only against every live store**; lookups go
  through `scripts/rmx-master` read verbs or the read-only MCP tools; test suites use throwaway
  stores under a short `mkdtemp()` root; `REFMATRIX_ROOT` is never exported. {#roles-agents}
  - Two agents on one branch (RED and GREEN) share it by
    `git fetch <other clone> <branch> && git merge --ff-only FETCH_HEAD`.
  - A reviewer gets its own clone, and never works in a clone where another agent's suite runs.
  - Agents allocate no registry ids; they report defects and the lead numbers them on `master`.
- **Models.** Planning authors (plans, task specs, ADRs, spec revisions) run on Fable
  (`model: fable`); RED, GREEN, reviews and measurements keep their agent's default model.
  {#roles-models}
- **Briefs.** Each dispatch names the clone, branch and base sha, the evidence to read, the hard
  rules above, the expected artifact, and the reply shape. Agents in flight at a save-state get
  their brief written to `workflow/agents/inflight-<date>.md`. {#roles-briefs}

## ch-bsd is the gate {#bsd-gate}

ch-bsd carries the review weight (the user, 2026-11-15: "bsd really carries the weight"). In the
0.83.1 / plan-29 / plan-30 cycle it found every finding that changed what shipped: a 17-minute
store-lock hold, a failure reported only to a log, a 15 s residual lock gap, a stale-forever
publish sequence, and the evidence that settled plan-30 D12; it also corrected its own earlier
round (L108). What makes it work, and so what every bsd brief carries: {#bsd-gate-body}

- **It runs things.** Its own clone, probes and timings on throwaway stores or read-only snapshot
  copies, and it re-runs the claimed mutations itself. A finding states what was measured.
- **The brief names the questions.** Each dispatch lists the specific claims to test (the
  production route, the lock discipline, the loud-failure path, the cost under load), not "review
  this".
- **It is iterated to clean before the user sees a decision** (r1 full depth, then confirm-lite
  rounds to MEH-only GO).
- **Its ledger compounds.** IMPRESSIONS bullets carry its lessons across runs; the lead persists
  them whole.

## 2. Planning path {#planning}

The default for plans, task specs and spec revisions. The SDD chain (`/ch-specify` →
`/ch-implement`) stays available when the user asks for it. {#planning-default}

1. **Draft.** ch-architect (Fable) writes the plan and every task spec, `metadata.status:
   drafting`, on a branch in a clone. Each AC names the test that proves it and whether it is RED
   at base, characterization, a gate or a measurement; each spec lists must-fail mutations, the
   caller census, files and risks.
2. **Spec review r1.** ch-bsd, full depth, in its own clone; the report is written in that clone
   or returned as text.
3. **Ruling.** The lead persists the report ([[#reports]]) and writes `L<n>` in
   [[plan-review-2026-11-13#lead]]: each finding folded, deferred (with an owner) or overruled,
   with the reason.
4. **Revision** by the same author on Fable, with a fold table per spec.
5. **Confirm-lite r2..rN** until MEH-only GO; the MEHs fold before the merge.
6. **User decisions only now.** The plan's `plan-N Dk` decisions go to the user, each with a
   recommendation (AskUserQuestion). A measurement that removes a decision's premise means the
   decision is re-asked with the number in hand.
7. **Merge** `--no-ff` to `master`; code-span citations become wikilinks; `status: approved`;
   plan-of-plans row; registries. A review report that links docs not yet on `master` travels on
   the plan branch until its merge.

## 3. Task and bug path {#task}

1. **RED** (ch-test-engineer) — failing tests from the criteria, proven RED at base **by reading
   the E lines** (the intended reason, not just "failed"). Real inputs before patches; a patch of
   a dependency (never the unit under test) is registered in `test_mock_registry`.
2. **GREEN** (ch-implementer) — production code only, no tests authored.
3. **Mutations** — commit the fix first; one mutation at a time, restored in its own command;
   clear `__pycache__` after the batch; confirm the fix is present after the restore. Each
   mutation must make a test FAIL, not hang. The table goes in the summary.
4. **Verify** — the task's files + the family + every test that imports a changed module
   (until 29.4 R6 derives families, list them by grep and say how). **No branch full suite**:
   the full suite runs once per minor release, on merged `master`; a patch release gates on the
   narrower set ([[#release]]); failures compared **by
   E line** with the last release's full-suite log, never by test name. (The user, 2026-11-15:
   "it's taken most of the day to get one patch release out" — 0.83.1 ran four full suites;
   Q29 = a.)
5. **Review** — ch-bsd over the commit range, in its own clone. The lead persists the report and
   rules (`L<n>`). Findings fold as a new RED → GREEN round, then a confirm-lite until MEH-only
   GO. For small MEH folds the lead may check the RED → GREEN pair and the mutation table itself
   instead of another bsd round, and says so in the ruling. `/ch-review` (four-phase) is optional:
   for large `src/` changes or on request (Q23).
6. **Record** — implementation summary on the branch (`workflow/implementation_summaries/`);
   registry rows by the lead.
7. **Merge** `--no-ff` to `master`.

## 4. Release and deploy path {#release}

1. **Release commit** on `master`: bump `pyproject.toml` and `src/refmatrix/__init__.py` only.
   **Pick the version by scope** (the user, 2026-11-15): a change that alters behaviour on a
   shared path — ingest, the store, the daemon ops, a hook's output, the CLI's contract — or
   whose changed modules are imported by most of the suite is a **minor** release (`0.N.0`); a
   fix confined to a few modules with no such change is a **patch** (`0.N.x`). When unsure, it is
   minor.
2. **The gate on merged `master`, by release kind:**
   - **minor (`0.N.0`): the full suite**, compared by E line with the previous release's log.
     A clone cannot see failures that need the dev tree's live `.refmatrix/`, so a green branch
     run is evidence, not the gate.
   - **patch (`0.N.x`): the narrower set** — the task's tests, its family, and every test that
     imports a changed module (until 29.4 R6 derives families, listed by grep and named in the
     release commit), run on merged `master`, compared by E line.
   - Never a branch full suite ([[#task]]).
3. **Deploy:** `git -C ~/refmatrix pull --ff-only origin master`; `rmx daemon restart --relaunch`;
   `rmx version -v` (no `[DEV TREE]`); `rmx hub relaunch-fleet`; a STALE hub gets `rmx hub stop`
   plus ONE `launchctl kickstart`; `rmx install-hooks --check`, re-installing only when out of sync.
4. **Live verification** of the release's claim, after backing up `catalog.read.duckdb`,
   `facts.log` and `active`. A release that changes the store on disk (a derive flip, a fleet
   re-derive, a slot surgery) needs its own user go.

## 5. Lead discipline {#discipline}

- **The POP is the source of truth** (the user, 2026-11-15; consolidation finding F1). Every
  commit that changes state updates [[plan-of-plans]] in the same commit: a ruling that changes
  order or scope, an admission or a move to post-mod, a merge, a release, a status flip. Review
  docs, `L<n>` rows and triage files are evidence the POP row links to; they never hold state the
  POP lacks. A plan or task file's `metadata.status` follows the POP, not the other way. {#pop-truth}
- **Measure before deciding**, read-only: copy `.refmatrix/catalog.read.duckdb` to the
  scratchpad and open the copy with duckdb `read_only=True` under `.venv-eval`; never `Store()`
  on a live slot. State go/no-go bands before measuring. {#measure}
- **Ledgers.** Every ruling is an `L<n>` row; every question to the user is a `Q<n>` in
  [[open-questions]] or a plan's own `Dk`; each reply that asks anything ends with the ids still
  open. {#ledgers}
- **Registry at once.** Every defect anyone finds gets a `workflow/bug_registry.md` row from the
  lead in the same turn, even when its fix is out of scope. {#registry}
- **Reports** ([[#reports]]): the lead persists every review. {#reports-rule}
- **Watch long runs.** After an agent's long run should have ended, tail its log and check the
  process; never assume the agent noticed. {#watch}
- **One suite at a time on this machine.** Never start a test run while a full suite runs; a
  concurrent family run slowed the 0.83.1 gate to 17% in 35 minutes. Batch fixes waiting on a
  gate into one release and one gate. {#one-suite}
- **Commits.** Own paths by pathspec; merge messages through a file (`git merge -F <file>`;
  `-F -` fails); never commit to `release`; the user pushes. {#commits}

## 6. Persisting a review report {#reports}

1. Copy the report into `workflow/bullshit/<UTC-stamp>-<subject>-r<n>-<sha>.md`; its `last_run`
   line names that file and a UTC timestamp.
2. Add its INDEX row to `workflow/bullshit/INDEX.md` and its line to `last_run.log`.
3. Copy its IMPRESSIONS bullets into `workflow/bullshit/IMPRESSIONS.md` as whole blocks, each
   ending in exactly one `{#id}` (bug-242).
4. `./scripts/lint-gmd.sh` → 0 errors before the commit.
