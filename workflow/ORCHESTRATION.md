---
gmd: "0.1"
id: orchestration
title: "Operating procedure: how the lead runs planning, tasks, reviews and releases"
tags: [workflow, governance, orchestration, process]
metadata:
  node_type: governance
  created: 2026-11-15
  updated: 2026-11-15
---

# Operating procedure {#root}

How work moves through this repo. **Rewritten lean on 2026-11-15 (L165)** after the user asked
why development had slowed to a crawl. Measured over 11-13..15: 731 commits, 40 touching `src/`;
+5.1k `src` lines against +63.6k lines of plans, specs and reviews; specs reviewed 5-9 rounds
before any code; 50 ch-bsd reports in one day. The rule now: **ceremony scales with risk**, and
code, not prose, is the output. Where [[tdd-governance]] or [[PLANNING_WORKFLOW]] say more, this
file wins.

rel: derives-from -> [[workflow-practice-review-2026-11-15]]
rel: amends -> [[tdd-governance]]
rel: amends -> [[PLANNING_WORKFLOW]]
rel: depends-on -> [[plan-of-plans#ledgers]]

## 1. Roles {#roles}

- **The lead** (the main session) dispatches, decides, merges, releases, deploys and does every
  write to a live store (announced, backed up first). It writes no `src/` or tests beyond a
  one-line literal or config change, which it may make itself on a task branch. {#roles-lead}
- **Agents** work in their own clone, `/Volumes/littlebig/<project>-<worker>`, and are
  **read-only against every live store**: lookups via `scripts/rmx-master` read verbs or the
  read-only MCP tools; tests on throwaway stores under a short `mkdtemp()` root; never export
  `REFMATRIX_ROOT`. Agents allocate no registry ids. {#roles-agents}
- **Models.** Plans and specs on Fable (`model: fable`); everything else on the agent default.
  {#roles-models}
- **Briefs** name the clone, branch, base sha, what to read, the expected artifact, and the
  hard rules above. Agents in flight at a save-state are listed in the handoff. Every ruling an
  agent needs is sent to it, not only written to the POP. {#roles-briefs}

## 2. Planning path {#planning}

1. **Spec just in time:** a task is specced when it is next in the queue, not earlier.
2. **One page.** ch-architect writes the goal, the acceptance criteria (each with the test that
   proves it), the files, and the risks. No fold tables, no revision history in the spec.
3. **One architect read**, no ch-bsd round on a spec. Open decisions go to the user with a
   recommendation.
4. **Merge** and set `status: approved` in the POP row.

## 3. Task and bug path {#task}

**Small** (one module, a test-side fix, or under ~100 `src` lines, no change to a shared path):
one agent writes the test and the fix, shows the test failing before the fix by its E line,
runs the verify set below, and reports. The lead reads the diff and merges. No mutations, no
ch-bsd. {#task-small}

**Large** (a shared path: ingest, the store, daemon ops, hook output, the CLI contract; or
several modules):

1. **RED** (ch-test-engineer): failing tests, proven RED at base by their E lines.
2. **GREEN** (ch-implementer): `src/` only.
3. **Mutations** on the `src/` change only; one at a time, each must FAIL a test, not hang.
4. **Verify** (below).
5. **Review: one ch-bsd pass** over the range, in its own clone, with named questions.
   BULLSHIT → fold, then one confirm-lite. SKETCHY → the implementer folds and the lead checks
   the diff; no new round. MEH → noted or folded in the same commit; no round.
6. **Summary** (short, on the branch), **merge** `--no-ff`.

**Verify set** (both sizes): the task's tests, plus every test file importing a changed module
(listed by grep). Never a branch full suite. Failures compared by E line with the last
release's full-suite log. {#task-verify}

**Tests stay lean.** A fold adds to the feature's existing test file; no new
`test_*_r<n>.py` / `*_remedy_*` file per review round. Test behaviour, not source text: a test
that greps `src/` is allowed only as a guard on a stated rule. {#task-tests}

## 4. Release and deploy path {#release}

1. **Release commit** on `master` bumps `pyproject.toml` and `src/refmatrix/__init__.py`. A
   change to a shared path is **major** (`0.N.0`); a fix confined to a few modules is **minor**
   (`0.N.x`); when unsure, major.
2. **Gate on merged `master`:** major → the full suite; minor → the verify set. Compared by E
   line with the previous release's log.
3. **Deploy:** `git -C ~/refmatrix pull --ff-only origin master`; `rmx daemon restart
   --relaunch`; `rmx version -v` (no `[DEV TREE]`); `rmx hub relaunch-fleet` (a stale hub:
   `rmx hub stop` + one `launchctl kickstart`); `rmx install-hooks --check`, re-install only
   when out of sync.
4. **Live check** of the release's claim, after backing up `catalog.read.duckdb`, `facts.log`
   and `active`. A store-changing release needs its own user go.

## 5. Lead discipline {#discipline}

- **The POP is the source of truth** for order, scope and status: a merge, release, admission
  or scope change updates [[plan-of-plans]] in the same commit. Finished items move to
  [[pop-finished]]. {#pop-truth}
- **Ledgers, minimal.** A `Q<n>` for every question to the user (open ids listed at the end of
  the reply); an `L<n>` only for a decision that changes scope, order or what is built. No rows
  for relays, bookkeeping or "the agent did what was ruled". {#ledgers}
- **Proportionate process.** Before running a band, a round or a table, say what it buys in
  this case; propose the lighter path first. {#proportionate}
- **Measure before deciding**, read-only, on a copy of `catalog.read.duckdb`. {#measure}
- **Registry:** every defect found gets a `workflow/bug_registry.md` row. {#registry}
- **Watch long runs:** tail an agent's log after its expected duration. {#watch}
- **One test process at a time on this machine** (`lockf
  /private/tmp/claude-501/rmx-test-lane.lock`); batch fixes waiting on a gate into one release.
  {#one-suite}
- **Commits:** own paths by pathspec; batch doc edits (each commit re-ingests the large GMD files
  and holds the store writer, bug-177); never commit to `release`. {#commits}

## 6. Persisting a review report {#reports}

Copy a ch-bsd report to `workflow/bullshit/<UTC-stamp>-<subject>-r<n>-<sha>.md`, add its
`INDEX.md` row and `last_run.log` line, and copy any new IMPRESSIONS bullet whole. Lint
(`./scripts/lint-gmd.sh`, 0 errors) before the commit.
