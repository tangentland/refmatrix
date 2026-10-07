---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-06 (session b92019bc, continued). Prior handoff archived at
`workflow/past_handoffs/008-task-15.4-bugs-065-069-070-072-073-074_2026-10-06.md`
— it was written mid-session and the two ch-bsd rounds overtook it.

rel: supersedes -> [[handoff-008-task-15.4-bugs-065-074]]

## State {#state}

**CORRECTED.** This said `master` = 24523f3, which was wrong and was repeated
to the user several times. `master` is **1452875** (= `origin/main` = deploy =
0.76.0). Every commit of this session's remedy sits on **`bsd-r1-remedy`**,
**13 commits unmerged**, now at `607e9db` (the top commit is a peer session's
docs-only one). The "13 ahead of origin/main" figure was computed from HEAD, so
the count was right and the label was not. Thanks to the peer session for
catching it.

`bsd-r1-remedy` = **4f70a0b** for my work, clean tree. Full suite
**2475 passed / 0 failed**
(`workflow/review-output/pytest-bug073-074-full.log`, 16m28s), and the log is
attributable: `find src -newermt "2026-10-06 16:41:07" -name '*.py'` EMPTY with
a sanity probe proving the check fires. GMD lint 0 errors / 555 docs.
`rmx install-hooks --check` in sync. {#state-body}

**NOT DEPLOYED.** `~/refmatrix` and the fleet are at **1452875 / 0.76.0**.
Everything after that sha — the whole r1 remedy, both ch-bsd rounds' fixes,
bug-073 and bug-074 — exists only on `master`. `origin/main` is at `1452875`
too. {#state-deploy}

## Two sessions shared this tree on 2026-10-06 {#two-sessions}

Two Claude sessions worked in `~/claude_tools/refmatrix` concurrently. Read both halves of this
file in that light. {#two-sessions-lead}

- **Session b92019bc (`refmatrix-5e`)** wrote everything else in this handoff: task 15.4,
  bugs 065–074, two ch-bsd rounds. It works on branch **`bsd-r1-remedy`**.
- **Session a9e25baf (`helix-unified-bitmap-structure`)** worked on the helix-unification design
  and spike. It committed only docs and evidence, ON `bsd-r1-remedy` (at the user's direction),
  on top of `4f70a0b`:
  - `docs/adr/0004-unified-location-space-index.md` (Proposed) and the ADR-0003/0004 index rows;
  - `workflow/bug_registry.md` **bug-075**: GMD section text read by dense embed and rerank is
    the first 8 body lines, capped at 500 chars;
  - `eval/spikes/2026-10-06-loc-coloc/`.
  It made no `src/` or `tests/` changes. Headline result: `BM25 + 2.0 × sentence co-location`
  beats BM25 on cliquedb lines/merge and MemAware test-720
  (memory `project_sentence_coloc_measured`).

**Branch facts, read at 2026-10-06 ~22:30, because this file's State section disagrees:** {#two-sessions-refs}

- `master` = **1452875** (0.76.0), not 24523f3.
- `24523f3`, `8ebb691`, `7a7efa0` and `4f70a0b` exist only on **`bsd-r1-remedy`**.
- The "master = 24523f3" in [[#state]] describes `bsd-r1-remedy`; its merge to master is
  still pending.

**Incident, recorded so it is not repeated.** At 22:05 session a9e25baf ran `git checkout -b`
in the shared tree, switching it off `bsd-r1-remedy` for about 7 minutes, and committed there.
It then restored `bsd-r1-remedy`, re-applied its work staged, and deleted its own branch. The
other session verified every commit of its own stayed reachable, and its full-suite log
(16:41–16:58) predates the switch. **Rule: in a shared tree, never switch branches. Stage your own
paths and commit on the branch that is checked out, or use a separate worktree.** {#two-sessions-incident}

- The `post-checkout` hook backgrounds `rmx sync` but keeps git's stdout open, so a checkout
  blocks until the sync finishes. On a busy daemon that took more than 10 min.
- At handoff the daemon was busy, not wedged (a filesystem walk; it answers ping). Do not
  restart it while queued writes drain.
- `MEMORY.md` is now 23,583 bytes; headroom against the cap is ~800 bytes.

## The arc {#arc}

One ask ("recall state", then "proceed with the task and the 3 bugs") became
task 15.4, six bug fixes, two audit rounds and a read-path change. The audits
are the spine of it: **r1 DIRTY (13 findings), r2 DIRTY (11)**, and r2's three
BULLSHIT findings were regressions *I* introduced while remediating r1 — two of
them strictly worse than the deployed build. {#arc-body}

## What landed {#landed}

- **Task 15.4 / plan 15** — `sessions`/`embed`/`pagerank` stamp; coverage named
  per partition kind; missing is reported without being an alert.
- **bug-065** — an as-memory ingest implies memory vectors, at the BRIDGE (the
  user caught the first cut sitting in `finalize_save_state`, which covered one
  caller of four).
- **bug-069** — locate's third caller reports its skips; two stale doubles.
- **bug-070** — the canonical match is a spelling bridge, not a family; chosen
  by measuring four arms, three worse.
- **bug-072** — a broken derive detector no longer reads as a clean store.
- **bug-073** — `ILIKE` threw the caller's CASE away. `grep_evidence("ERROR")`
  and `("error")` returned byte-identical rows where real grep matched ERROR in
  0 files and error in 52. Found because the user asked what the ILIKE issue
  was.
- **bug-074 — the user's fix, and the biggest result of the session.** An index
  row named a `file:line` where the pattern was NOT: for a code symbol the
  ingest attaches keyword evidence to the enclosing symbol's `def` line.
  Verifying keyword presence per row took precision from 0.000–0.542 to
  **1.000 on every pattern that still answers**, with `error`/`ERROR` returning
  zero rows and falling through to the real floor. +2–3.6 ms p50.

## What the audits cost me, recorded because it will recur {#lessons}

- **A clean run on a nondeterministic defect is not evidence of absence.** I
  declared bug-070's order half unreproducible and nearly deleted a correct
  fix. Gate power depends on input size: 2 files hold argv order by luck 18/40,
  4+ files 0/40. My probe used two.
- **My "control" was rmx.** The rewrite hook replaces even an absolute-path
  `/usr/bin/grep`, and `RMXGREP_MODE=rich` is set here. I saw the fallback
  banner on the control's own output, said it meant the control was rewritten,
  and still read the agreeing numbers as "no defect".
- **Three fixtures in one session pointed evidence at files or lines that
  cannot exist.** bug-074's verification found all three. A fixture that
  asserts against an unreachable state is a test of nothing.
- **I invalidated three suite runs by working while they ran** — the third by
  my own mutation loop moving `cli.py`'s mtime. #b-3's error in a different
  costume, three times.
- **Targeted runs are not the gate.** I called the grep surface green at 112
  passed across 8 files; the full suite found 6 more failures in a file I had
  not thought to check.

rel: reinforces -> [[feedback_never_explain_away_a_failing_guard]]
rel: reinforces -> [[feedback_commit_before_mutation_revert]]

## Next {#next}

1. **ch-bsd ROUND 3 over `ae39044..24523f3`.** r2 closed DIRTY and said "plan-15
   may not close. Round 3." On top of its 11 findings, everything in bug-073 /
   bug-074 and the three fixture rewrites are unaudited. This is first
   priority — four of r1's five blocker fixes were already audited once and two
   came back as regressions.
2. **Merge `bsd-r1-remedy` into `master`** — 13 commits, never merged, which
   is why the State line above was wrong. CLAUDE.md's workflow is one branch
   per task merged back `--no-ff`. NOT done here on purpose: r2 closed DIRTY so
   round 3 is owed first, and the branch now carries a peer session's commit
   (`607e9db`), so the merge is the user's call rather than mine.
3. **Deploy** — nothing from the remedy is live. Fleet 8/8 + hub on 0.76.0 at
   `1452875`.
4. **Push** — `origin/main` is at `1452875`, ~10 commits behind.
5. **Re-run the grep-learning replay.** bug-074 LOWERS the measured index share
   (18.5% → 31.7% counted the low-precision answers) while raising quality, so
   `docs/measurements/grep-learning-replay.md` is stale and needs a re-run plus
   a scope line. Same class as the #s-4 problem corrected this session.
6. **plan-15 stays `in-progress`** until round 3 closes.
7. **bug-070's other half** — `c.name ILIKE '%pattern%'` is still a substring
   over names. bug-074's verification now cleans its output, so the breadth is
   a cost question (74 rows fetched to keep 4) rather than a correctness one.
   Re-decide with that in mind.

## Open, not forgotten {#open}

- **r2's #s-4 disagreement is unresolved.** It reports the multi-word figure as
  80.6%; both tokenisations I can construct give 0/28 → 24/27 = 88.9% from the
  committed JSON. I kept the number I can verify and flagged it back rather
  than match an unverified one. Round 3 should settle it.
- `MEMORY.md` is 23,269 bytes against a ~24,400-byte cap — **1,131 bytes of
  headroom**. The cap that bites is BYTES, not the 200 lines the rule doc says
  (`impression_bsd_cap_in_the_wrong_unit`). Keep new index lines terse.
- Hub runs UNSUPERVISED: `launchctl print gui/501/com.refmatrix.hub` says
  `state = not running` while the process is alive. Pre-existing plist drift;
  I restarted the hub by hand rather than kickstart a second one onto :7777.
- `RMXGREP_MODE=rich` in `.claude/settings.local.json` — bug-066's config half,
  and now known to make any shell `grep` control useless.
- `docs/measurements/` vs `workflow/measurements/` split still undecided.
- `eval/production/grep_evidence_breadth.py` — new instrument, no test.

rel: realizes -> [[feedback_save_state_means_handoff]]
rel: related-to -> [[impression_bsd_substring_signature_widens]]
