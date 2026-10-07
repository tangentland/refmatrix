---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-07 (session b38025a7). Prior handoff archived at
`workflow/past_handoffs/009-bsd-r1-r2-remedy-bugs-073-074_2026-10-06.md`.

rel: supersedes -> [[handoff-009-bsd-r1-r2-remedy-bugs-073-074]]

## State {#state}

- **Branch:** `bsd-r1-remedy`, 33 commits ahead of `master`, UNMERGED. The tree was clean at save.
- **master:** `master` = `origin/main` = deploy `~/refmatrix` = **1452875 / 0.76.0**. NOTHING from
  this branch is deployed. Push is pending (the user pushes).
- **Live processes:**
  - The project daemon was relaunched twice today after wedges (bug-085); the last pid is 22418.
  - The hub was relaunched once (pid 15591, the sole listener on :7777).
- **Suite at the round-5 remedy tree:** 2527 passed, 1 failed (`r5-remedy-full2.log`). The 1 is
  `test_installed_hooks_match_generated`: the expected rewriter drift from bug-080, which clears
  with `rmx install-hooks --apply --force` AFTER deploy. Since then the grep tests pass (258) after
  `d559567`, but the full suite has not been re-run. {#state-body}

## What this session did {#did}

**Audit rounds 3 to 6 on the remedy** (r3 16, r4 12, r5 8, r6 12 findings). Each round's blockers
were fixed with tests shown RED on the old code first, and mutation-proven where the auditor asked.
- bug-076 to bug-084 fixed: verify before the cap, `-i`/`-w` on every path, the spelling bridge,
  `-c` dir rows, one total-order read, cwd-independent rows printed resolved, and the delegate
  learning honestly.
- bug-080: `Path.exists()` returns False on PermissionError on Python 3.14, so the unreadable-marker
  report was dead. Fixed in `learn_switch`, `rmxgrep`, `rmxrg` and the rewriter. `rmxrg` had no
  learn toggle at all.
- **User decision, option 1:** the Python re-implementation of grep's output will be DELETED by
  plan-16 task 16.5, not patched further.

**Plan-16 (invisible grep shim)** has specs for 16.1 to 16.5 at revision 4, after spec review r4
(NEEDS-REVISION).
- User decisions:
  - d-1: grep is observed, not answered;
  - d-2: `RMXGREP_TEACH` folds into the learn switch;
  - d-3: invisible shim;
  - 16.4: precision gate kept (complete outputs, n≥30, forward oracle, closure rule);
  - 16.5 option 1.
- **d-4 was revised today:** the `-f/--flags` bundle is REMOVED (`d559567`, done in code). `-f FILE`
  is grep's pattern file.
- Interim: `RMXGREP_MODE=plain` is set in both settings files.

**External calls:** model loads come from the local cache only (`43e0fa5`,
`models_local.load_local`). PyPI and the explicit eval-setup calls are allowed (user).

**Test isolation:** a live-socket recorder lives in `tests/conftest.py`, in record mode. Findings
are in memory `project_suite_reaches_live_sockets`.

## Next {#next}

1. **Round 6 remedy (user said "ok to move forward as suggested").** Report:
   `workflow/bullshit/2026-10-07-0924-r6-merge-unpinned-and-the-eval-model-still-calls-out-92c374c.md`.
   - #b-1: the dedup test must assert `len(rows) == 1` and `merged == 1`, not a set size.
   - #b-2: in `eval/retrievers/coderankembed_retriever.py`, set `HF_HUB_OFFLINE` and
     `TRANSFORMERS_OFFLINE` BEFORE importing `sentence_transformers` (they are frozen at import).
     Prove it under a socket guard.
   - #s-1: TURN OFF delegate teaching. `_grep_delegate` runs the real tool and teaches NOTHING
     (output unchanged). Approved by the user.
   - #s-2: a partial model cache must fail loudly as `ModelNotCached`, never load silently.
     Missing tokenizer, `modules.json` or pooling files → error. Also surface a reranker load
     failure on `rmx context`.
   - #s-3: bug row for the global store's wrong `base` (see memory
     `project_global_relative_rows_repair`).
   - #s-5: bug or deferral row for the recorder's blind spots (subprocesses, the viascope socket,
     `::1`) and the deferred test isolation.
   - MEH: the r5 #m-1 docstring, unsetting `HF_HUB_OFFLINE` after the offline tests, `--fetch`
     help/error text, and implementation summaries for 43e0fa5, 92c374c and d559567.
   - Then **ch-bsd round 7**. Do NOT run the full suite from auditors; that is targeted only (memory
     `project_suite_reaches_live_sockets`).
2. **Plan-16 revision 5** for spec review r4
   (`workflow/bullshit/2026-10-07-0918-plan16-spec-review-r4-floor-options-and-click-argv-33809ab.md`).
   - With the bundle gone, d-4 shrinks to the index-only options (`--limit`, `-k`, `--linkage`,
     `--no-fallback`) on the hand-off route and on the floor.
   - Parse raw argv so `--` survives click (b-r4-2).
   - Also: the FIFO AC hang, keyed throttle lines everywhere, 16.2 AC-4 needing `-r`, plan header
     staleness.
   - Then spec review r5, until APPROVE.
3. **Merge `bsd-r1-remedy` → `master`** (`--no-ff`) once a code round is clean. Then deploy:
   1. `git -C ~/refmatrix pull --ff-only origin master`;
   2. `rmx daemon restart --relaunch`;
   3. `rmx install-hooks --apply --force`.

   After the deploy the user removes `RMXGREP_MODE` from `~/.claude/settings.json` only once 16.2
   ships, not before.
4. **After deploy:** the global-store relative-row repair. Recover 476, forget 611, as a tested
   daemon op with a backup and a dry run (memory `project_global_relative_rows_repair`).
5. **plan-15** stays `in-progress` until the remedy branch audits clean.

## Open, not forgotten {#open}

- **bug-085** (daemon wedge): the op is unknown. Samples are in
  `workflow/review-output/daemon-*-wedge-*.txt`. It needs an op-start log line per daemon op, or
  py-spy. Suite isolation is deferred by the user.
- **bug-081:** BRE read as fixed strings by the explicit `rmx grep`, including the stdin path.
  Fixed by 16.5.
- The pytest run's HF connection is gone since `43e0fa5`. The deployed hub workers still call
  huggingface.co until deploy.
