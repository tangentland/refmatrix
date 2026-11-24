---
gmd: "0.1"
id: agent-brief-fix-handoff
title: "Small-fix brief: bug-318, the compaction handoff file is over the Read cap and mostly milestone noise"
tags: [agent-brief, small-fix, bug-318, handoff, compaction]
metadata:
  node_type: brief
  created: 2026-11-24
---

# fix-handoff: bug-318 {#root}

rel: implements -> [[bug-registry]]
rel: related-to -> [[task-compaction-as-handoff]]

You are one isolated small-fix agent (ORCHESTRATION `#task-small`): you write the tests and the
fix, show each test failing before the fix by its E line, run the verify set, commit, and report.
Read `workflow/bug_registry.md` row **bug-318** first. {#role}

## Where {#where}

Your clone is on branch `fix-bug318-handoff-size` at master `0dc1a605`. Work and commit there
only. You are read-only against every live store; test stores go under a short `mkdtemp()` root;
never export `REFMATRIX_ROOT`; never `find /`. Follow CLAUDE.md `#test-discipline` (extend the
existing test files for the handoff and STM capture; no new per-bug file; real states). {#where-rules}

## Evidence {#evidence}

The first live auto-compact (session 8adeba5c, 2026-11-24) wrote a 62,591 B handoff
(`.refmatrix/handoffs/<session>.txt`). Claude Code's Read returned lines 1-391 of 572 and flagged
the view PARTIAL (31,070 tokens over a 25,000 cap), so the read gate was satisfied by a page that
looked whole. About 330 lines were the STM digest's `## Milestones`, most of them junk, verbatim:

```
- git commit: 0 errors  [1 file changed, 1 insertion(+), 1 deletion(-)]
- git commit: 1  [2 files changed, 22 insertions(+), 2 deletions(-)]
- git checkout: ?? .venv-eval
- git merge: 9edfdbf1 master:fatal: Not a valid object name 9edfdbf1
- git init: Usage: rmx install-hooks [OPTIONS]
- git commit: gmd lint: 1 files, 1 GMD docs, 0 errors, 8 warnings [phase 1 doc-level]
```

The diffstat tail is also stale: it is HEAD's diffstat at capture time, whatever command ran. {#evidence-lines}

## Fix (three parts) {#fix}

1. **Milestones are real events.** A `git` event is recorded only when the command actually ran
   that git verb as a command (not `git` inside a quoted string, an echo, a `rmx focus note`, a
   grep pattern), and its terse is `<verb> <short-sha> <subject>` read from git (for commit /
   merge / cherry-pick / revert / tag / reset / pull: the resulting HEAD's subject, only when HEAD
   moved), never from the command's stdout. A verb that moved nothing (a failed commit, `checkout
   -- path`, a no-op pull) is not a milestone. Read `_GIT_MILESTONE_RE`, `_git_milestone_subcmd`,
   `_git_diff_summary` in `src/refmatrix/cli.py` and the capture call site first; decide the
   minimal change; say in the report what a milestone is now. {#fix-1}
2. **Bounded digest and handoff.** The digest's `## Milestones` keeps the newest 30, deduped by
   sha, with a line saying how many older ones were cut and where the full list is
   (`rmx focus context` / `rmx focus export`). The handoff file
   (`handoff.py`, the writer near `<store>/handoffs/<session>.txt`) is bounded at **40,000 bytes**
   (≈ 20k tokens at the 2 B/token measured here, under the 25k Read cap): sections are cut in
   reverse priority (milestones and touched lists before the save-state head, git state,
   anomalies and active goal), and the cut is stated in the file. Use the existing
   `hook_budget` helpers (`fit_blocks`) if they fit; do not hand-roll. {#fix-2}
3. **In-flight agents.** Near the top (after the active goal), an `## Agents in flight` section:
   the background Agent launches in the session transcript that have no completion notification
   yet (name / description, the agent id, launch time), read from the same transcript the
   `/goal` reader already locates (`handoff.py`, R6 / L198). If this part alone pushes the change
   past ~100 `src` lines or needs a second module beyond handoff, stop after parts 1-2, say so in
   the report, and leave part 3 for the lead. {#fix-3}

## Tests {#tests}

- Through the entry points: the PostToolUse capture (a hook envelope with a compound Bash command
  and its output → the recorded event), `rmx save-state` / the handoff writer (a store whose STM
  holds 200 milestones → a file ≤ 40,000 B that states the cut and keeps the head sections).
- Each new test seen failing at `0dc1a605` for the intended reason (record the E lines).
- Planted must-fail cases: the six junk lines above as captured commands must yield no milestone
  or a real-subject one. {#tests-list}

## Verify set {#verify}

Your tests + every test file importing a module you changed (list them by grep) + the repo guards
(verb parity, `install-hooks --check` / generated-config tests, the wallclock/budget census).
Logs to `workflow/review-output/fix-bug318-*.log`. Note any failure that is identical at base by
its E line. {#verify-set}

## Report {#report}

To `REPORT.md` (the path in the start prompt): the commit sha(s), what a milestone is now, the
handoff size on the 200-milestone fixture before/after, each test's RED E line, the verify-set
counts, and the [[self-audit]] answers for this change. Do not edit the bug registry; the lead
closes the row. {#report-shape}
