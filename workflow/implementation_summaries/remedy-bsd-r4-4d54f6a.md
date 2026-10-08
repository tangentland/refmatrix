---
gmd: "0.1"
id: impl-remedy-bsd-r4-4d54f6a
title: "Remediation of ch-bsd r4 (bb5b97f..4d54f6a): two blockers fixed, three superseded by deleting the code (task 16.5)"
tags: [implementation-summary, bsd, remediation, grep]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r4-4d54f6a
  created: 2026-10-07
---

# Remediation of ch-bsd r4 {#root}

rel: implements -> [[bsd-r1-remedy-r4-4d54f6a]]
rel: amends -> [[impl-remedy-bsd-r3-bb5b97f]]
rel: related-to -> [[task-16.5-explicit-grep-hands-off]]

Round 4 came back DIRTY with 12 findings (5 BULLSHIT, 3 SKETCHY, 4 MEH). The user chose option 1
(2026-10-07, "simplify, go with option 1"):
- fix the two blockers that live in code that stays, the paging (#b-1) and the paths (#b-5);
- remove the other three blockers by DELETING the Python re-implementation of grep's output, as
  plan-16 task 16.5.

Blockers #b-2, #b-3 and #b-4 all sit in that re-implementation, as does most of the drop-in bug
family. It is not patched a fifth time. {#lead}

## Fixed {#fixed}

| finding | change | proof |
|---|---|---|
| #b-1 (bug-083) | `grep_evidence` makes ONE read in a TOTAL order (`path, line, linkage, concept, entity`), verified lazily with `verify_evidence_rows(stop_after=cap+1)`. No `OFFSET`. | `test_a_capped_read_never_duplicates_or_loses_a_tied_row` RED on the old code (10 rows, 7 distinct). Replica copy: no duplicates; `Q` in 66 ms vs 1004 ms paged. |
| #b-5 (bug-084) | Relative row paths resolve against `base` = `store.root.parent`, not the process cwd. | `test_a_relative_row_verifies_regardless_of_the_cwd` RED. Replica copy: `error` = 88 rows from the root, from `src/` and from `/tmp`. |
| #b-5 sibling and plan-16 #m-5 (bug-082) | `_grep_delegate` teaches absolute paths, names a failed teach on stderr instead of a bare `except: pass`, and counts unparsable lines. | `test_the_delegate_branch_teaches_absolute_paths_too` RED (`'./a.txt'`). |
| SKETCHY: untested working paths | New tests for the RPC cap note, `-w` on the replica and direct read paths, and the rewriter's once-a-minute report. | Mutations M1 (CLI ignores RPC `capped`), M2 (`word=False` at both in-process callers) and M3 (throttle off) each FAIL their test (run in place, restored byte-identical). |
| SKETCHY: unregistered patch | `cli._root` row in the mock registry. | — |
| MEH: bridge help text | `--regex` help states that multi-word patterns match identifier spellings case-insensitively on the index read. | — |
| MEH: learn-switch.log | `learn status` shows only reports from the last 24 h, with a readable time. | `test_learn_status_says_unreadable_not_absent` updated to a current timestamp. |

## Superseded by task 16.5 (code to be deleted, not patched) {#superseded}

- **#b-2:** the `-c` directory walk is a second listing (`argv_count_rows` / `_walk_files`).
- **#b-3:** directory spellings in `argv_rank`.
- **#b-4:** `-l`/`-L` exit 2.
- **#m-4:** pre-existing `-A/-B/-C` drop and the dotfile skip.
- **MEH:** `_grep_stdin_addendum` dropping `-i`/`-w`.
- **The 13 surviving mutations in that code:** the rendering, `-c zzz nosuch.txt`, the case letters
  in the grep branch, and the shims' throttles (16.2 rewrites those).
- **bug-081's live false negative:** 16.5 R3 moves the path-less floor to real grep.

16.5's differential (R5/AC-1) carries every case round 4 found, and its acceptance requires those
cases to DIFFER on the current code first. {#superseded-list}

## Evidence {#evidence}

- Grep tests: `workflow/review-output/r4-b1b5-green.log` (241 passed).
- Live copy: `r4-b1b5-live.log`.
- RED runs: `r4-b1b5-red.log` and `r4-delegate-red.log`.
- New-test runs: `r4-sketchy-tests.log`.
- Full suite: `r4-remedy-full.log`.
