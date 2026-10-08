---
gmd: "0.1"
id: impl-remedy-bsd-r5-c8278b1
title: "Remediation of ch-bsd r5 (4d54f6a..c8278b1): rows printed as read, the unreadable note pinned on every leg"
tags: [implementation-summary, bsd, remediation, grep]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r5-c8278b1
  created: 2026-10-07
---

# Remediation of ch-bsd r5 {#root}

rel: implements -> [[bsd-r1-remedy-r5-c8278b1]]
rel: amends -> [[impl-remedy-bsd-r4-4d54f6a]]

Round 5 was DIRTY with 8 findings (2 BULLSHIT, 3 SKETCHY, 3 MEH). Both of round 4's claimed fixes
held under mutation: the total order (bug-083) and the cwd-independent row set (bug-084). {#lead}

| finding | change | proof |
|---|---|---|
| #b-1 | `verify_evidence_rows` returns each row with the RESOLVED path it was read from, and de-duplicates after resolution (`stats["merged"]`). | `test_a_relative_row_is_printed_resolved_and_merged` was RED (relative path printed). The cwd test now also asserts that the printed path exists. The mutation "keep the unresolved path" fails it. |
| #b-2 | Tests for the unreadable count on the daemon op field, the RPC path's note and the in-process path's note, and for the `-w` bound on bridged spellings. | Mutations on the op field, the RPC read, the CLI note and the variant `\b` each FAIL (`r5-b2-tests.log`; restores byte-identical). |
| #s-2 | `_grep_delegate` teaches nothing when any output-shaping flag (`-c -h -l -L -o -q -Z`, or their long forms) changes the line shape. Previously `-c` taught counts as line numbers and `-h` taught text as files. | `test_the_delegate_teaches_nothing_from_non_line_output[-c,-h]` were RED. 16.5 deletes the branch. |
| #s-3 | `refmatrix.daemon.ping` (→ False) row added to the mock registry. | — |
| #m-2 | `learn status` counts and reports malformed log lines. A test pins the 24 h window. | `test_learn_status_shows_only_the_last_24h_and_counts_malformed` |
| #m-1 | `stats["unreadable"]` now counts only the rows read before the cap stopped the read. This is a docstring-level MEH: no caller reads it as a total. | — |

**Not changed here (#s-1, global store).** `base = store.root.parent` is wrong for the GLOBAL store.
There, relative rows were learned from many cwds, and only 387 of its 1,087 relative rows resolve
under `$HOME`. The others are counted as unreadable, which is not silent. Fixing them needs a data
decision (forget them, or attempt a re-resolution), and that decision is taken to the user.

Also this session: the project daemon wedged (bug-085, open) and was restarted at the user's
direction, along with the hub. An orphan unsupervised hub had been holding :7777.
