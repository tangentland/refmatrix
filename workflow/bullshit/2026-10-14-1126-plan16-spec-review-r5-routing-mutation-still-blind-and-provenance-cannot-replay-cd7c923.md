---
gmd: "0.1"
id: bsd-plan16-spec-review-r5-cd7c923
title: "plan-16 spec review r5: the raw-argv parser and the per-route option table hold, but AC-5b's BRE-routing mutation still cannot fire (bug-074 verification drops the seeded rows), and 16.6's provenance cannot replay the caller's rules for the deletion engine that consumes it"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim
task: spec-review-16.1-16.6
round: 5
tags: [bsd, audit, spec-review, grep, drop-in, learning, provenance, measurement]
---

# ch-bsd spec review of plan-16, round 5 (pre-implementation) {#root}

**Commit reviewed:** `cd7c923` (revision 5 of the plan and tasks 16.1-16.6), branch
`wave0-spec-reviews`. **Written:** 2026-10-14T11:26:23-0700.

**Method:** I read the plan and all six specs, and checked every revision-5 claim against the
spec text AND the live facts, not the changelog:
- click 8.3.3 (`.venv-eval`), on a replica of `grep()`'s context settings with a `parse_args`
  override, and on one with today's `-k`/`--limit` declared;
- BSD grep 2.6.0, for every value flag in 16.1 R1's new `value` column, `--include` pruning on
  non-recursive operands, BRE `\|` and `\(\)`, and the AC-4 backreference timing;
- rg 15.1.0 on a named file with `-t`/`--glob` (16.3 AC-9 power);
- `/bin/sh` `$PWD` with a symlinked and a stale `PWD` (16.2 R2b);
- code at HEAD: `cli.py` `grep()`, `_split_grep_argv`, `_grep_bare_flags`, `_GREP_*` sets,
  `cli_entry`, `cli_log`; `telemetry.py` `OUTCOMES`, `_outcome_of`, `log_cli_invocation`;
  `store.py` `evidence_line_matches`, `verify_evidence_rows`, `grep_evidence`'s verify path;
  `replica_merge.py` step 9; `ingest.py` `DOC_EXTS`.
- Cross-plan: plan-22 and its review `bsd-plan22-spec-review-3104a81` (b-1, b-2, b-7, s-6, m-3),
  plan-23's consumer list, `plan-review-2026-10-07#order`, `plan-of-plans`.

All probes ran in a `mkdtemp` dir and my scratchpad. Nothing in `src/`, `tests/`, any store, any
plan file, INDEX.md, IMPRESSIONS.md or last_run.log was touched. No suite, no mutation, no
dev-venv `rmx`.

rel: amends -> [[bsd-plan16-spec-review-r4-33809ab]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: related-to -> [[bsd-plan22-spec-review-3104a81]]
rel: related-to -> [[bsd-pattern-sibling-render-path]]
rel: contradicts -> [[claude#no-silent-failures]]

## Live evidence {#evidence}

### click 8.3.3 {#ev-click}

| input (after `grep`) | result |
|---|---|
| `-- -x f.txt`, `parse_args` override | raw `['--','-x','f.txt']`, click argv `['-x','f.txt']`: the override DOES see `--` (16.5 R0's probe confirmed) |
| `-e --help f.txt` (only `--help` declared, as R0 specifies) | **click prints the help text and exits 0.** The grep never runs |
| `-- --help f` | raw keeps `--`; no help. Correct |
| `-ekey f` (today's `-k` declared) | `BadParameter 'ey' is not one of 'doc','code'`: click takes `k` out of grep's `-e key` |
| `-fkcode f` (today) | argv `['-f','f']`, `kind=code`: grep's `-f kcode` silently became `-k code` + `-f f` |
| `/usr/bin/grep -ekey k.txt` | prints `key`, rc 0: `-ekey` IS grep's `-e key` |

### BSD grep 2.6.0 {#ev-bsd}

- **Value flags.** `-C 1`, `-A 1`, `-m 1`, `-d skip`, `-D skip`, `--label L`, `--binary-files text`,
  `--include G`, `--include-dir G`, `--exclude-dir G`, `--max-count 1`, `--directories skip`,
  `--devices skip`, `--regexp P`, `--file F` all consume the next token. `--context 1` and
  `--color always` read the value as the pattern. `-C alpha` is `Invalid argument`. 16.1 R1's
  `value` column is **correct**.
- **`--include` pruning on non-recursive operands.**
  - `grep -i -nH --null alpha sub` (a directory, no `-r`): `Is a directory`, rc 2.
  - The same with `--include=*.py --include=*.PY` prepended: **no output, rc 1.**
  - `grep --include=*.py --include=*.txt alpha a.py nosuch`: rc **0**; unpruned it is rc 2 with
    `No such file or directory`.
- **BRE vs Python `re`.** `grep -c 'zzz\|alp'` on `alpha` → 1; `re.search(r'zzz\|alp','alpha')` →
  None. `grep -c '\(foo\)x'` on `foox` → 1; Python matches only the literal `(foo)x`.
- **AC-4 timing.** `\(.*\)\1Z` over 2 MB of 80-column random text: 3.09 s, rc 1. The
  self-calibrating `T_bare ≥ 3 s` rule holds. `.txt` is in `DOC_EXTS`, so the learner re-runs it
  and times out as AC-4 expects.

### Shell, rg, code {#ev-other}

- `/bin/sh` with `PWD` = a symlink spelling of the cwd keeps it; with a stale `PWD` or none it
  resets to the physical path. 16.2 R2b's Python rule matches both. m-r4-5 is closed.
- rg 15.1.0: `rg --no-config -t rust alpha a.py` and `--glob='*.nomatch'` both print `alpha`, rc 0.
  16.3 AC-9's mutation can fire.
- `grep_evidence` (`store.py:3257`) verifies every index row with `verify_evidence_rows` under the
  READER's pattern and `regex` flag; an emptied answer falls to the floor by design.
- `telemetry.OUTCOMES = ("ok","empty","consumer-closed","error")` (`telemetry.py:69`); an unknown
  `outcome` falls through `_outcome_of` to `ok`. `rmx cli-log --errors` filters
  `r.get("exit_code", 0) != 0` (`cli.py:9519`), which is True for `null`.
- `replica_merge.py:335-355` rebuilds `linkage_evidence` with `INSERT … SELECT DISTINCT` (no PK).
- `_parse_grep_flags` is called from `src/` only as `_parse_grep_flags(None)` (`cli.py:6127`), as
  16.5 d-4 says. Its letter form is still called by `tests/test_grep_case_every_path.py:73`,
  `tests/test_grep_output_shape.py:151` and `tests/test_grep_learned_paths_absolute.py:39`.

## Status of r4 findings {#prior-status}

| id | status | evidence |
|---|---|---|
| b-r4-1 rmx options on the path-less floor | **closed** | d-4 has a floor column for every option; AC-5c-5g; mutations "run the floor under `-k`/`--no-fallback`". The `-k` floor default is dn-1, for the user. Residue: [[#m-r5-2]] |
| b-r4-2 click's leftover argv | **partially closed** | R0 reads the raw tail (probed: the override sees `--`), refuses repeats, takes value flags from 16.1's table (probed correct); R0b collects every `-e`; R5 rows. Holes: click still parses `--help` after the capture, and the `-k` cluster rule's "no other reading" is false ([[#s-r5-1]]) |
| s-r4-1 bundle `I`/`r`/`R` | **closed** | the bundle is gone at HEAD (`d559567`); AC-3 `-I`/`-r`/`-R` rows; R7 scan for "default ON" |
| s-r4-2 AC-5 oracle and empty-store mutation | **partially closed → escalated** | literal file sets: closed. The seeded store does NOT give the BRE-routing mutation power ([[#b-r5-2]]) |
| s-r4-3 AC-4 FIFO | **closed** | slow regular file + `RMX_GREP_LEARN_TIMEOUT_S=1`; timing probed |
| s-r4-4 keyed lines | **closed** | 16.2 R2/R3/AC-6 in lines with cwd; `learn status` counts lines; 16.3 routes no-rg through the learner (AC-5c); 16.4 R1-keyed joins by epoch + cwd |
| s-r4-5 16.4 joins | **closed** | the exact join is deleted (16.4 line 74-76); shlex tokens; `unattributable` never route 3; `ts` defined in 16.1 R6; learn-off a stated confound. New facets: [[#s-r5-6]], [[#m-r5-6]] |
| s-r4-6 sandbox | **closed** | 16.5 `#sandbox`; residue [[#m-r5-4]] |
| s-r4-7 16.2 AC-4 | **partially closed** | AC-4 now `-ri` (passes). The new AC-4b cannot pass under 16.1 R1b ([[#s-r5-2]]) |
| m-r4-1 stale plan lines | **closed** | status line, out-of-scope bullet marked superseded, `#cost` list |
| m-r4-2 wording | **closed** | 16.1 R1b "ADDS … BEFORE"; 16.3 glob rule "BOTH" only |
| m-r4-3 `cli.log` lost on exec | **closed** | R6 `handed-off` record + AC-7. Follow-on: readers ([[#m-r5-1]]) |
| m-r4-4 single-file Grep branch | **closed** | 16.3 AC-9 + mutation; power probed |
| m-r4-5 `$PWD` vs `getcwd` | **closed** | 16.2 R2b rule + rows; `/bin/sh` behaviour probed equal |
| m-r4-6 no-op flags / BRE concepts | **closed** | R3 `-r -R -H -s` no-ops; BRE concepts' reader named; 16.4 `bre_concept_share` |
| m-r4-7 snapshots / models | **closed** | ≤ 10 snapshots + nearest-later line-hash rule; `RMX_SHARED_MODELS=0` (exists, `modelsrv.py:59`) |
| m-r4-8 `--include` case | **closed** | upper-case globs; mixed case named |

Tally: **13 closed, 4 partially closed (one escalated), 0 open.**

### Cross-plan items from the plan-22 review {#status-plan22}

| id | status | evidence |
|---|---|---|
| plan-22 m-3 (plan-16 line ~138 says 16.6 prunes) | **closed** | the plan's 16.6 row now says the engine MOVED to plan-22; no "non-`ok`" text left outside 16.6's marked history |
| plan-22 b-7 (16.6 has no wave) | **open** | revision 5 adds no wave; `plan-review-2026-10-07#order` still lists only 16.1-16.5 ([[#s-r5-5]]) |
| plan-22 b-1 / b-2 / s-6 (no hash, no flags, unstable rowid) | **open in 16.6, which owns the sidecar** | [[#b-r5-1]], [[#s-r5-4]] |

## New findings {#findings}

### BULLSHIT b-r5-1: 16.6's provenance cannot reproduce the caller's matching rules, and plan-22 will delete correctly taught rows on it {#b-r5-1}

**Spec:** 16.6 R1, d-a; consumed by 22.1 R1 ("re-verify under the row's recorded flags") and
22.2 R2 (`stale-line` removal).
**What:** R1 records "the pattern and its matching flags (`-i`, `-w`, `-F`/regex), so it can be
re-checked under the caller's own rules". After 16.1, the learner re-runs the caller's OWN tool
with its whole keep-match row: BSD BRE/ERE, `-x`, `-y`, rg's Rust regex, `-S` smart-case, `-P`
PCRE2, `-U` multiline, `-s`. The sidecar records three of those and no tool or dialect.
- The only verifier in the codebase is Python `re` (`evidence_line_matches`). Probed: BRE
  `zzz\|alp` matches `alpha` in grep and NOT in Python; `\(foo\)x` matches `foox` in grep and
  only `(foo)x` in Python. r4 measured 56.6% of agent grep patterns carrying a BRE meta.
- So every BRE-alternation or BRE-group row 16.1 teaches correctly re-verifies as `stale-line`, and
  22.2 removes it. That is knowledge loss from a missing column.
- d-a also records no line content hash, which 22.1's `moved` keys on (plan-22 b-1).

**Why it is bullshit:** 16.6 is the provenance owner for a deletion engine. The spec states a
purpose ("re-checked under the caller's own rules") that its columns cannot serve, and no AC
re-verifies a BRE-taught row.
**Fix:**
- R1 records `tool`, `bin`, the kept MATCH-class tokens verbatim (16.1 R1's keep-match and cutoff
  rows, as the learner already has them), and the matched line's content hash.
- Re-verification of a learned row RE-RUNS that tool on that file (the plan-22 b-1 fix), never
  Python `re`, or the spec names the subset Python can evaluate and marks everything else
  `unverifiable` (kept).
- AC: a row taught by `grep 'a\|b'` and one by `grep '\(foo\)x'` re-verify `ok`; mutation "verify
  with `evidence_line_matches`" fails it.

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### BULLSHIT b-r5-2: AC-5b's "route BRE patterns to the index" mutation still cannot fire, now on a seeded store (third round) {#b-r5-2}

**Spec:** 16.5 AC-5 lead ("a misrouted call would answer from the index and differ"), AC-5b,
test-strategy row "route BRE patterns to the index".
**What:** revision 5 seeds `query/alpha$` through the REAL learner. The learner runs BSD BRE, so
the seeded rows are lines that END in `alpha`. Under the mutation, `rmx grep 'alpha$'` reads the
index with the default substring rule, and `grep_evidence` verifies each row
(`store.py:3257`): no fixture line contains the literal text `alpha$`, so every row is dropped,
the answer empties, and the call falls to the floor by design. The output equals the floor's, and
the mutation survives.
**Why it is bullshit:** this is the third round of the same blind mutation: r3 s-r3-2 asked for a
store that has rows, r4 s-r4-2 found it not adopted, r5 adopted a seeding that verification
erases. SKETCHY seen three times escalates.
**Fix:**
- Give the fixture a line containing the literal text `alpha$` (not at end of line), and seed
  `query/alpha$` from `grep -F 'alpha$'` so that row verifies under substring.
- AC-5b's literal expected output for `'alpha$'` excludes that line (BRE anchors), so the mutation
  prints it and fails.
- Pre-check in the test: with the mutation's routing, the index read returns ≥ 1 verified row.

rel: contradicts -> [[impression_bsd_guard_cannot_fire]]

### SKETCHY s-r5-1: R0's "exactly ONE parser" still runs click's help parser after the capture, and the `-k` cluster rule misreads grep's `-e`/`-f` clusters {#s-r5-1}

**Spec:** 16.5 R0 ("rmx's options are NOT declared to click (only `--help` and the `argv`
catch-all), so there is exactly ONE parser"; "`-k` inside a cluster … is refused … grep has no
`-k`, so the cluster has no other reading"); AC-3.
**What:**
- The override stores the raw tail and then calls click, which still parses. With `--help`
  declared and `-e` unknown to click, `rmx grep -e --help f.txt` prints rmx's help and exits 0
  (probed). R0's own rule says a grep value-flag's value is never an rmx option, and AC-3 tests it
  only for `--limit`.
- `-ekey` and `-fkeys.txt` are grep's `-e key` and `-f keys.txt` (probed: `grep -ekey` prints
  `key`). A cluster rule that refuses any cluster containing `k` refuses valid grep. The reading
  click has today is worse: `-fkcode f` silently becomes `-k code` + `-f f` (probed).

**Fix:**
- Set `add_help_option=False` (or `help_option_names: []`) and let `parse_rmx_grep_argv` treat
  `--help` as an rmx option in rmx position only.
- The cluster rule walks the cluster left to right with 16.1's `value` letters: a letter that
  takes a value ends the cluster (`-ekey` = `-e key`); `k` is refused only in flag position.
- AC-3 rows: `-e --help f.txt` reaches grep; `-ekey f.txt` and `-fkeys.txt f.txt` route named,
  verbatim.

### SKETCHY s-r5-2: 16.2 AC-4b cannot pass, because 16.1 R1b's `--include` pruning changes grep's exit on non-recursive operands {#s-r5-2}

**Spec:** 16.2 AC-4b; 16.1 R1b (pruning ADDED to every re-run), R1 exit-status rules, AC-4.
**What:** AC-4b expects the learner to record `skipped reason=tool-error` for
`rmxgrep -i PAT dir`. The learner's re-run carries R1b's `--include`s (the caller passed none).
Probed: with them, BSD grep skips the directory silently and exits 1, so the learner records
`no-hits`, not `tool-error`. The same pruning turns an extension-less missing operand from rc 2
into rc 0, so R1's "exit 2 with hits" rule and 16.1 AC-4 depend on the fixture's file names.
This is the second time AC-4 has been unpassable as written (r4 s-r4-7).
**Fix:** either scope R1b's `--include`s to recursive re-runs (`-r`/`-R`/`-d recurse`, where the
103 s cost lives), or expect `outcome=no-hits` in AC-4b and record `tool_exit` from the pruned run
under its own name. State which, and give 16.1 AC-4's missing operand a corpus extension.

### SKETCHY s-r5-3: 16.6 R4's read-time marks record the READER's filtering as staleness {#s-r5-3}

**Spec:** 16.6 R4, AC-3; 16.1 R8 ("`-i`-taught lines … are dropped for a case-sensitive
`rmx grep`").
**What:** `verify_evidence_rows` drops a row whenever its line fails the READER's pattern, case or
regex flag, and counts that in the same `dropped` bucket as an out-of-range line. A valid
`-i`-taught row read by a case-sensitive `rmx grep` is dropped by design (16.1 R8). If R4 marks on
that drop, `stale_seen` grows on healthy rows, and 22.1's audit reads it. AC-3 uses a truly stale
row, so a mutation "mark every reader drop" passes it.
**Fix:** a mark is written only when the row fails under ITS OWN recorded rules ([[#b-r5-1]]) or its
file/line is gone; a reader-rule drop writes nothing. AC: a `-i`-taught row read case-sensitively
enqueues no mark.

### SKETCHY s-r5-4: 16.6 d-a keys the sidecar on `evidence_rowid`, which a replica merge rewrites {#s-r5-4}

**Spec:** 16.6 d-a; (plan-22 s-6, carried to the sidecar's owner).
**What:** `linkage_evidence` has no PK. `replica_merge.py` step 9 rebuilds it with
`INSERT … SELECT DISTINCT`, which assigns fresh rowids and collapses duplicates; the new sidecar is
not in the merge's table lists (`replica_merge.py:88/433/530`). After a merge every
`evidence_rowid` points at a different row or none.
**Fix:** key the sidecar on `(entity_id, linkage_id, concept_id, file, line)`, add it to the
merge's table lists with the same remap, and add an AC that merges two slots and checks every
sidecar row still joins.

### SKETCHY s-r5-5: 16.6 has no wave, and both dn-2 options leave plan-22's wave-1 dependency unmet {#s-r5-5}

**Spec:** 16.6 header ("Depends on: 16.1"; status `drafting`, "Requirements (draft)", "Acceptance
(draft)"); plan `#decisions-needed` dn-2; `plan-review-2026-10-07#order`; plan-22 22.1 "Depends on:
16.6 R1/R5".
**What:** the wave order schedules 16.1-16.5 only. 22.1 sits in wave 1 and needs 16.6 R1/R5; 16.6
waits on 16.1 (wave 2). Keeping 16.6 (dn-2 default) or folding it into 16.1 (dn-2 alternative)
both put the provenance in wave 2. Plan-22's review filed this as BULLSHIT b-7; it is counted
there, not twice. For plan-16 the gap is that a task whose ACs are marked draft blocks `approved`.
**Fix:** split by dependency, not by plan.
- Sidecar DDL + R5 backfill + R4 marks need no 16.1 (only plan-23's queue): wave 1, after plan-23.
- R1's learn-time write goes into 16.1 (the same `_learn_grep_hits` change as its idempotence),
  wave 2. Until then, the old ping's writes also get a provenance row or are re-backfilled.
- Drop "(draft)" from 16.6's sections once [[#b-r5-1]]/[[#s-r5-3]]/[[#s-r5-4]] are answered.

### SKETCHY s-r5-6: 16.4's route 2 absorbs the Grep-tool and explicit `rmx grep` learner records {#s-r5-6}

**Spec:** 16.4 R1 step 4 (route 2 = a record that is a candidate for no segment); 16.1 R6 fields.
**What:** segments are leading `grep`/`rg` in Bash commands. A learner record spawned by 16.3's
Grep-tool hook or by 16.5's explicit `rmx grep` (named route or floor) matches no such segment,
so it reads as route 2, "it ran inside a script". 16.1 R6 has no field naming the spawner, so the
harness cannot separate them.
**Fix:** 16.1 R6 adds `caller` (`shim`, `grep-tool-hook`, `rmx-grep`); 16.4 joins Grep-tool
records to Grep `tool_use`s and `rmx-grep` records to `rmx grep` segments, and route 2 counts
`caller=shim` only. AC-3 rows for both.

### MEH m-r5-1: the `handed-off` cli.log record is mis-read by both existing readers {#m-r5-1}

**Spec:** 16.5 R6, AC-7.
**What:** `outcome="handed-off"` is not in `telemetry.OUTCOMES`, so `_outcome_of` reports it as `ok`;
`rmx cli-log --errors` keeps rows with `exit_code != 0`, which includes `null`, so every
named-path `rmx grep` lists as an error with exit "None". Name the `OUTCOMES` addition and both
reader changes; `log_cli_invocation`'s `exit_code: int` becomes optional.

### MEH m-r5-2: AC-5d/5f's miss pattern is absent from disk, so a floor leak is invisible in the output {#m-r5-2}

**Spec:** 16.5 AC-5d, 5f.
**What:** `alpha_missing` matches nothing anywhere, so a floor that ran under `-k code` prints the
same nothing. Only the learner record shows it, and the sandbox sets `RMX_LEARN=0` where learning
"is not the subject". Use a pattern that is on disk only in a `.md` file and not in the index,
and assert empty stdout; run 5d/5f with learning ON.

### MEH m-r5-3: R4's deletion list leaves the index-flag folder unnamed {#m-r5-3}

**Spec:** 16.5 R3 condition 3, R4, AC-3.
**What:** R4 deletes `_GREP_VALUE_FLAGS` but not `_grep_bare_flags`, which reads it, nor
`_GREP_FORMAT_FLAGS` (`nHhroRasIbTup`), whose "ignored on the index" letters `h o a b I` contradict
R3's whitelist. Only `-I` has an AC. Name what folds `-i -w -n -l -c -F -E` into the index read,
delete or rewrite the format sets, and add AC-3 rows `-o`/`-h` path-less → floor. R4 should also
list the three other test files that call `_parse_grep_flags` with letters ([[#ev-other]]).

### MEH m-r5-4: `grep_learn.spawn()`'s interpreter is unnamed {#m-r5-4}

**Spec:** 16.5 R1, `#sandbox`; 16.2 R2b.
**What:** the shim spawns `"$RMX" grep-learn`. The Python spawn does not say what it runs. A
`which("rmx")` build runs the DEPLOY code under `.venv-eval` tests, which the sandbox guard (it
checks `store_root`, not the binary) cannot see. Specify `sys.executable -m refmatrix.cli
grep-learn`, and add the binary to the guard.

### MEH m-r5-5: the `value` column's long space forms have no class rows {#m-r5-5}

**Spec:** 16.1 R1 table, `#r1-unknown`.
**What:** the `value` column lists `--include --exclude --exclude-dir --include-dir --regexp --file
--max-count --directories --devices --after-context --before-context` as space-form value flags,
but the class table has rows for their `=` forms only (plus `--binary-files V` and `--label L`).
Built literally, `grep -r --include '*.py' x .` kills the teach as `unknown-flag:--include`. Say
that every `value` long flag has its space form as a row, and add the space forms to AC-1's
coverage.

### MEH m-r5-6: 16.4's `$` rule cannot tell an anchor from a variable after shlex {#m-r5-6}

**Spec:** 16.4 R1 step 3 (`unattributable` when the pattern token carries `$`).
**What:** shlex removes quotes (probed: `'alpha$'` → `alpha$`, `"$x"` → `$x`), so every
end-anchored grep is `unattributable` and leaves the gate's n, already thin. Decide on the raw
text: `$` inside single quotes is literal.

### MEH m-r5-7: a truncated floor exits 0 even when grep exited 2 {#m-r5-7}

**Spec:** 16.5 R3 ("the exit code is grep's unless the cap truncated (then 0, with the note)").
**What:** an unreadable file plus more than N lines turns grep's rc 2 into 0. Keep 2 when grep
returned 2.

## Verified, no finding {#verified}

- 16.5 R0b's value-flag list and its `--context`/`--color` exclusion match BSD 2.6.0 exactly.
- The `parse_args` override receives the raw tail with `--` at its position.
- 16.5 AC-1's power cases (`-- -x f.txt`, `-i foo -- --limit 3`) do differ on the current command.
- 16.5 AC-4's backreference file reaches the 3 s floor at ~2 MB, and `.txt` is in the corpus.
- 16.2 R2b's cwd rule equals `/bin/sh`'s `$PWD` for symlinked, stale and unset `PWD`.
- 16.3 AC-9's single-file mutation fires (rg ignores `-t`/`--glob` on a named file).
- `RMX_SHARED_MODELS=0` exists (`modelsrv.py:59`).

## Decisions needed: assessment {#decisions}

- **dn-1 (`-k`/`--linkage` on the floor): confirm the default, correct its reason.** The spec says
  translating `-k code` to `--include` globs is "a wider reading of kind". For line hits it is not:
  a file entity's kind comes from `CODE_EXTS`, the same set. The real blockers are that a caller's
  own `--include` ORs with the translated ones (probed in r4: widening), that BSD globs are
  case-sensitive, and that `--linkage` has no file-level translation at all. Refusing is the
  correct default for those reasons.
- **dn-2 (where 16.6 lives): neither option as stated.** Split by dependency ([[#s-r5-5]]): the
  sidecar, backfill and marks to wave 1 after plan-23 (unblocking plan-22 b-7), the learn-time
  write into 16.1. Either dn-2 option alone keeps plan-22's wave 1 blocked.

## Verdict {#verdict}

**NEEDS-REVISION.**

| prior findings | closed | partially closed | open |
|---|---|---|---|
| r4 (17) | 13 | 4 | 0 |
| plan-22 cross items (3) | 1 (m-3) | 0 | 2 (b-7 → [[#s-r5-5]]; b-1/b-2/s-6 → [[#b-r5-1]], [[#s-r5-4]]) |

**15 new findings: 2 BULLSHIT, 6 SKETCHY, 7 MEH.**

16.1-16.3 are close: one AC each ([[#s-r5-2]], [[#m-r5-5]]). 16.4 needs [[#s-r5-6]]. 16.5's d-4
table and raw-argv parser hold; it needs [[#b-r5-2]] and [[#s-r5-1]]. 16.6, reviewed for the first
time, is not approvable: [[#b-r5-1]], [[#s-r5-3]], [[#s-r5-4]], [[#s-r5-5]].

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| cd7c923 (SPEC review r5, plan-16 tasks 16.1-16.6 rev 5, pre-implementation; written 2026-10-14T11:26:23-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | NEEDS-REVISION | 15 new (2B/6S/7M); r4: 13 closed, 4 partial (s-r4-2 escalated), 0 open; plan-22 m-3 closed, b-7 open | [[bsd-plan16-spec-review-r5-cd7c923]]: d-4 per-route table and the raw-argv parse_args override hold (override sees `--`; 16.1 value column matches BSD 2.6.0 exactly). BULLSHIT: AC-5b's BRE-routing mutation survives the seeded store because grep_evidence's bug-074 verification drops every BRE-taught `query/alpha$` row under the substring rule and the call falls to the floor (third round, escalated); 16.6 R1 provenance records -i/-w/-F only, no tool/dialect/hash, and the only verifier is Python re (probed: BRE `\|` and `\(\)` match in grep, not in re), so plan-22 would remove correctly taught BRE rows. SKETCHY: click still parses --help after the capture (`-e --help f` prints help, rc 0) and the -k cluster rule misreads `-ekey`; 16.2 AC-4b unpassable (R1b --include pruning makes `grep -i PAT dir` rc 1 silent, probed); 16.6 R4 marks reader-rule drops as staleness; sidecar keyed on evidence_rowid, rewritten by replica_merge SELECT DISTINCT; 16.6 unscheduled (plan-22 b-7); 16.4 route 2 absorbs Grep-tool and explicit rmx-grep learner records. No code, no mutations, no live-store access, no suite run. |
```

IMPRESSIONS.md bullets:

```
- plan-16 r5 (cd7c923): a seeded store is not enough to arm a routing mutation when the read path VERIFIES rows under the caller's rules: bug-074 verification erased the seeded `query/alpha$` rows and the misrouted call fell to the same floor. Seed a row that survives the reader's verification, and pre-check that the mutated route returns it.
- plan-16 r5: "provenance so it can be re-checked under the caller's own rules" must store the tool and dialect, not three flags; the codebase's only verifier is Python re, which reads BRE `\|`/`\(\)` differently. A provenance owner feeding a deletion engine is reviewed for what the engine will DO with the gaps.
- plan-16 r5: overriding click's parse_args to capture raw argv still lets click parse afterwards; whatever stays declared (`--help`) can still eat a grep value. "One parser" means click parses nothing.
```
