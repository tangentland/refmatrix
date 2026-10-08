---
gmd: "0.1"
id: impl-remedy-bsd-r3-bb5b97f
title: "Remediation of ch-bsd r3 (ae39044..bb5b97f): the four blockers and #s-1"
tags: [implementation-summary, bsd, remediation, grep]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r3-bb5b97f
  created: 2026-10-06
---

# Remediation of ch-bsd r3 {#root}

rel: implements -> [[bsd-r1-remedy-r3-bb5b97f]]
rel: amends -> [[impl-remedy-bsd-r1-1452875]]

Round 3 was DIRTY with 16 findings (4 BULLSHIT, 7 SKETCHY, 5 MEH). The user asked for them to
be fixed in this order: #s-1, #b-1, #b-2, #b-3, #b-4. This summary covers those five, plus
#m-5, which was a two-line fix in a file already being edited. It also covers the `unreadable`
half of #s-6, because the cap note needed the same plumbing. The other SKETCHY and MEH findings
are listed under [[#second-pass]]. None of them was closed quietly. {#lead}

## What changed {#changed}

**#s-1: egg-info re-tracked, and a benchmark overwritten.** `git rm -r --cached
src/refmatrix.egg-info`. `metrics.json` is restored from `4f70a0b^`. Committed alone as
`9eed544`. {#s-1}

**#b-1 (bug-076): verification ran after the cap.** `Store.grep_evidence` now pages the SQL
(page = max(4 x limit, 256)) until it has `limit + 1` verified rows or runs out of rows. The
`+ 1` lets it set `stats["capped"]` without reading the whole result. `_op_grep_indexed`
returns `capped` and `unreadable` alongside the rows. All three CLI index paths call
`_grep_index_notes`, which prints the cap note and the unreadable count on stderr; stdout stays
grep bytes only. {#b-1}

**#b-2 (bug-077): `-i` on the daemon RPC, and grep's case rule on the floor.**
- The RPC in `_grep_run` now sends `ignore_case`.
- The floor maps no flag to rg `-s` and to grep without `i`. Before this, no flag meant
  smart-case `-S` in rg and `-i` in grep.
- The `--regex` help text no longer says "case-insensitive". {#b-2}

**#b-3 (bug-078): the spelling bridge survives verification.** A multi-word pattern can reach
its concept through the canonical bridge. For those rows, `identifier_variant_regex` builds the
pattern's words joined by `_`, `-`, a space, or nothing, matched case-insensitively. A row whose
line holds one of those spellings is kept. Single-word patterns get no variants, so `ERROR`
stays case-sensitive and `error:` still needs its colon.

The decision is option (a) from the audit: keep the reach, keep the precision. The index read
answers only path-less invocations, which are exploration reads where bug-067's bridge is the
documented feature. A drop-in read of named files never reaches this code.

Other changes for #b-3:
- The two bridge guards assert `_op_grep_indexed` again, through a new `_reach` helper. They do
  this on corpus lines that hold the identifier, which is where ingest-time evidence really
  lands.
- `_concept_names` (`verify=False`) is kept only for the three tests that are about the SQL
  predicate.
- The instrument passes `verify=` explicitly and reports `verified_rows` / `answered_verified`
  next to the predicate columns, so its committed numbers reproduce. {#b-3}

**#b-4 (bug-079): directory zeros and argv spelling.**
- `grep()` keeps `paths` as the argv strings instead of converting them to `Path` objects.
- `argv_count_rows` expands a directory into its walked files: `rg --files --sort path`, or
  `os.walk` when rg is absent. A failure of `rg --files` raises; it does not drop rows.
- The nothing-matched branch prints a bare `0` only for a path-less read.
- `argv_rank` matches the raw spelling before it tries `normpath`. Without that, `f0.txt
  ./f0.txt` sorted both spellings under the first argument. {#b-4}

**#m-5.** `_teach` now raises when the pattern is not in the corpus. It used to fall back to
line 1. {#m-5}

## Evidence {#evidence}

**RED at `bb5b97f`.**
- `workflow/review-output/r3-remedy-red.log`: 13 failed. They cover verify-before-cap (5), the
  RPC `-i` test and the two floor case tests (3), the variant spellings (3), and the two bridge
  guards (2). Each failed for the reason its finding names: `[]` from the cap,
  `ignore_case` missing from the RPC args, `ERROR here` printed.
- `workflow/review-output/r3-b4-red.log`: 5 failed, run against the stashed (unfixed)
  `cli.py`. {#red}

**GREEN.**
- `workflow/review-output/r3-remedy-grep-all3.log`: all 18 grep test files, 233 passed.
- `workflow/review-output/r3-remedy-full.log`: the full suite, 2496 passed, 0 failed
  (976 s). {#green}

**Live check, on a scratch copy of the live replica (`r3-remedy-live-copy.log`).**

| Pattern | Before (r3 table) | After |
|---|---|---|
| `error` | 13 rows | 96 of 96, 31 ms; `unreadable=213` now reported |
| `partition` | 51 rows | 100 rows, `capped=True` |
| `build context` | 0 | 1 |
| `scan prompt` | 0 | 4 |
| `replica bundle` | 0 | 4 |

The raw rows that verification still drops were each read by hand. All of them sit on `def`
lines or unrelated lines that hold no spelling of the identifier, so dropping them is bug-074
working as intended. {#live}

## Second pass: the remaining SKETCHY and MEH items {#second-pass}

These were done the same day, at the user's direction ("then do 2"), before round 4. Each test
below was shown RED on the unfixed code. Logs are in `workflow/review-output/r3-*.log`.

| Finding | What changed | Proof |
|---|---|---|
| #s-2 | The second `Store.upsert_vector` stub is gone from `test_op_embed_reports_a_real_remaining_count`. It now asserts `remaining == 5 == pending_embeddings_count`, and the mock registry row says both copies are removed. | The test passes unstubbed. |
| #s-3 | `test_grep_indexed_regex_anchors` is back on `_op_grep_indexed` with verification on. README.md:3 now ends in `parser`, so both anchors verify. | Mutation M7 (the op ignores `regex`) makes it FAIL (`r3-s3-mut.log`). |
| #s-4 (r2 #s-2) | The shadowing `esc` in `doWhere` is deleted. Five raw innerHTML sites are now escaped. The audit named three; the new test found two more, `app.js:961` and the `d.code` exit line. | `test_app_js_has_one_escape_and_server_text_goes_through_it` is RED on the old `app.js`. |
| #s-4 (r2 #s-4) | `task-3.4-internal-cli-allowlist` is written, and the deferral row points at it. | GMD lint 0 errors. |
| #s-4 (r2 #m-4) | `raising=False` is dropped at `tests/test_derive_stamp.py:276`. | That file passes. |
| #s-5 | A SUPERSEDED banner is on `grep-learning-replay.md`, `docs/INDEX.md` and `plan-14.md`. The re-measure is plan-16 task 16.4. | — |
| #s-6, path half | `_grep_rg_fallback` hands the broker ABSOLUTE paths (`normpath(join(cwd, f))`); the display keeps grep's spelling. Rows already learned with relative paths stay until relearned. | `tests/test_grep_learned_paths_absolute.py` was RED (`'file': 'f.txt'`). |
| #s-7 | `-w` reaches verification: `word=` on `grep_evidence`, the op, and all three CLI callers, plus `\b` on the bridged variants. | Three tests RED, including the RPC carrying `word`. |
| #m-1 | The replay doc defines "multi-word" as `len(split()) > 1` and states that "containing a space" gives 80.6%. r2's figure was right. | — |
| #m-2 | **It found a real defect, bug-080.** Python 3.14's `Path.exists()` does not raise on a permission error, so r1 #m-3's `except OSError` was dead. It had been verified only with `exists` patched to raise. `_marker_present` stats the path instead. Both tests now use a real `chmod 000`, and the class-level patch is gone from the registry. | RED on the old `learn_switch.py` (`r3-m2-sib-red.log`). |
| #m-3 | `handoff.md#state-deploy` says the work is on the unmerged branch. bug-073/074 are marked `fixed (bsd-r1-remedy, unmerged)`. | — |
| #m-4, error half | The floor passes the tool's stderr through and exits 2 on a tool error, on every branch. A bare `except: pass` around the learn broker now prints to stderr. | Two e2e tests against `/usr/bin/grep` were RED (exit 1, then 0). |
| #m-5 | `_teach` raises. | — |

Also logged: **bug-081**, the BRE false negatives (`\b` and `^` read as fixed strings). It is open
for the explicit `rmx grep`, and plan-16 removes the drop-in exposure. {#second-pass-table}

## Still open {#open}

- **bug-080's siblings: CLOSED** at the user's direction. `bin/rmxgrep` and the rendered rewriter
  now use stat-based checks that report an unreadable marker to `~/.refmatrix/learn-switch.log`,
  and `rmx learn status` shows it. While fixing these, I found that `bin/rmxrg` had no learn toggle
  check at all; it now has the same block. 4 tests were RED on the old code. **Deploy note:** the
  rewriter is a generated hook, so after the deploy `rmx install-hooks --force` must refresh
  `~/.claude/hooks/rmxgrep-rewrite.py`, or `--check` reports drift.
- **bug-081** in the explicit `rmx grep`. {#still-open}
