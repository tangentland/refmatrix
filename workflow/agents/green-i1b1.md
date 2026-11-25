---
gmd: "0.1"
id: agent-brief-green-i1b1
title: "GREEN brief: task-I1.b1 units, compiler, fixture runner, --check legs, replay"
tags: [agent-brief, green, plan-32, i1, instructions, bug-209]
metadata:
  node_type: brief
  created: 2026-11-25
---

# GREEN: I1.b1 units and the parity gate {#root}

rel: implements -> [[task-I1.b1-units-and-check]]

You are the GREEN implementer for [[task-I1.b1-units-and-check]]. Read the spec (D1-D7, AC-1 to
AC-8, risks), ADR 0007 `#units`, `#binding`, `#fixtures`, `#contract`, `#installed-equals-generated`,
and RED's tests at `a07a7b83` with RED's notes `workflow/review-output/i1b1-red-notes.md`. You
change `src/` (and docs the change requires) to make RED's 53 failing tests pass. You write NO
tests and edit none of RED's. If a test looks wrong, stop and report it to the lead with the
reason. {#role}

## Where {#where}

- Your clone: `/Volumes/littlebig/refmatrix-i1b1-green`, branch `task-I1.b1-units-and-check` at `39e743a8`,
  the merge of RED's notes `e55961b4` (on `92aa1475`, which is RED `a07a7b83` with master
  `084ab198` merged in, bringing H1.a). The
  lead resolved one conflict in `tests/test_repo_hooks_in_sync.py` by keeping both test blocks.
  Commit at natural points. Never push, and never touch the dev tree.
- Read-only against every live store. Look things up with
  `/Users/tholley/claude_tools/refmatrix/scripts/rmx-master …` or the read-only refmatrix MCP
  tools. Never `find /`, and never export `REFMATRIX_ROOT`.
- Run tests only through `scripts/lane-local.sh /Volumes/littlebig/refmatrix-i1b1-green <sha>
  <log-name> <files…>` (or `lane-mini.sh`) on a committed sha.
- Any background wait has a deadline, and its match pattern cannot match itself. Read the lane
  log yourself after the run's expected time.

## Build {#build}

- Build the spec's Files table: `src/refmatrix/instructions.py` (new); `hooks.py`
  (`render_managed`/`check` legs, the git-hook leg, `check_artifacts`, `install` writes the
  compiled file); `cli.py` + `verbs.py` (a thin `rules replay` and `INTERNAL_CLI`); and the empty
  template packages. Every capability is a verb first; the CLI only exposes it.
- **H1.a consistency.** H1.a's AC-2 treats an installed agent or command that differs from the
  template ONLY by its frontmatter `id:` line as equal (an installed GMD doc carries its project's
  id). Your agents/commands classifier should class that file as `generated`, not `drift`; reuse
  one helper for this, don't write a second one. RED's AC-6 accepts either class, so nothing in
  RED's tests forces this. It still matters, because otherwise `--check` prints a false drift line
  for `gmd-curator.md` in every installed repo.
- D6: agent and command drift is printed and never fails, until H1.c.
- `src/` must be fully concrete. No silent failure: each refusal, unreadable file and failed
  fixture is loud (exit code plus stderr naming the file and the rule). Docstrings say WHY and
  name I1.b1, bug-209 and ADR 0007.
- Every `git` call in a stateful fixture gets a 2 s timeout. No daemon call anywhere on these
  legs.
- Bytes must be deterministic: a second `--apply` writes identical bytes.

## Lead rulings on RED's traps {#rulings}

- **Trap 4 (accepted):** a file under `.claude/rules/` with no `unit:` map is a native rule. It
  is local and listed, but it is neither compiled nor refused. This repo's `bug-registry.md`
  stays as it is.
- **Trap 5 (accepted):** the per-event `prefilter` is built only from dispatchable kinds (deny,
  ask, inject). `check` is not included until I1.e asks for it.
- **Traps 1-3 and 6-13 are binding as written.** That includes the `importlib.resources`
  template lookup, `--apply` not running fixtures, the `_USER_QUOTE` reason in `INTERNAL_CLI`,
  regenerating the CLI tree, and committing `.claude/rmx-instructions.json`.
- **M30 after H1.a.** This repo's `gmd-curator.md` now differs from its template only by its
  `id:` line. With the H1.a consistency rule above, the repo has no agent drift, so M30 may
  survive in `test_repo_hooks_in_sync.py`. That is expected; it is not your bug. Report M30's
  outcome as it happens. M20a (`hr::test_check_classes[agent-drift]`) carries the same rule
  through the CLI.

## Verify {#verify}

Run RED's four files (`test_instruction_units.py`, `test_hooks_reproducible.py`,
`test_repo_hooks_in_sync.py`, `test_verb_parity.py`), plus every test file that imports a module
you changed (list them by grep), plus the repo guards: `test_tmp_root_census`,
`test_suite_discipline`, `test_docs_generated`, `test_mock_registry_coverage`,
`test_deferrals_clean`, `test_wallclock_census`, `test_budget_outcome_census`, `test_verb_parity`
and `test_bug212_r4_red`. If the CLI tree or the generated docs change, regenerate what
`test_docs_generated` checks. Also run `./scripts/lint-gmd.sh` and get 0 errors.

## Mutations {#mutations}

After GREEN is committed, run every mutation in RED's notes plus spec AC-8, one at a time on the
`src/` change. The commit must hold the fix before you mutate. Restore each mutation with
`git checkout -- src/…` in its own command, and clear `__pycache__` after the batch. Each mutation
must FAIL its named test, not hang. Report a table of mutation, test, E line, killed yes/no.

## Real run (risk 1) {#real}

Run `--apply` then `--check` once in a throwaway git project under a short `mkdtemp()` root,
using the dev `rmx` (as `tests/devbin.py` builds it). Use a fresh HOME, never the live store, and
paste the output into the summary.

## Summary and report {#report}

Write `workflow/implementation_summaries/task-I1.b1-units-and-check.md` (GMD): what changed, the
lane logs, the mutation table, the real run, and a self-audit per `workflow/SELF_AUDIT.md`.
Report to the lead as text: shas, lane log names with pass/fail counts, the mutation table, any
test you believe is wrong (left unchanged, with the reason), and anything in the spec you could
not satisfy.
