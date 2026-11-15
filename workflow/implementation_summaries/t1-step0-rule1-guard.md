# T1 step 0: guard for test-discipline rule 1

`tests/test_suite_discipline.py` fails when `tests/` (recursive) holds a `.py` file whose stem
has `_r<digits>` or `_red` as a name component, contains `remedy`, or starts `test_bug<digits>`,
and the file is not in `tests/round_named_allow.json`. It also fails when an allowlist entry
has no file, so the list only shrinks as T1 step 3 consolidates. Paths in the list are relative
to `tests/`, sorted (a second test checks sorted and unique).

- Seeded with the 90 matching files on this branch (base b0d5eabf). The plan row says "today's
  111"; the count here is 90 under these patterns (`_r<n>` 49, remedy 38, `test_bug<N>` 51,
  `_red` 6, with overlap). The 21 difference is not found by any looser glob I tried; the lead
  should confirm which count is intended. `tests/fixtures/bug178_head_golden.json` is a fixture, not a test file, and is not matched.
- Before seeding (empty list): `E  Left contains 90 more items, first extra item: 'new round/bug/remedy/RED-named test file: test_bridge_move_safety_r1.py'` (1 failed, 2 passed; `workflow/review-output/t1-step0-before.log`). After: 3 passed (`t1-step0.log`).
- Rule 5: `test_guard_reports_a_new_round_file_and_a_stale_entry` runs the same `check()` over a
  tmp tree with new `_r7`, `remedy`, `test_bug123` and `_red` files and a stale entry; no patching.

## Self-audit
1 real:     `pytest -q tests/test_suite_discipline.py` → 3 passed; before seeding 1 failed (E line above). No rmx command changed.
2 wiring:   N/A, a test-only guard with no entry point; it scans the real `tests/` tree.
3 census:   N/A, no production code changed; the only other copy of the patterns is the prose in CLAUDE.md rule 1 and the T1 row. Count mismatch (90 vs 111) stated above.
4 bound:    N/A, one directory walk, no timeouts or RPC.
5 busy:     N/A, no daemon or worker involved.
6 guard:    new file / stale entry fire on a matching file absent from the list, or a listed file removed; reached by any commit touching `tests/`; test `test_guard_reports_a_new_round_file_and_a_stale_entry` (tmp tree) and the real-tree run seen failing with an empty list.
7 loud:     forced by the empty list → pytest exit 1 with the E line above.
8 handoff:  shrinking the list is T1 step 3 (plan row T1); the 90 vs 111 count is for the lead to confirm.
