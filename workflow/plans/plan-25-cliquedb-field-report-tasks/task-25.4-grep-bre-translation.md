---
gmd: "0.1"
id: task-25.4-grep-bre-translation
title: "Task 25.4: rmx grep reads a BRE the way the platform grep does — any backslash escape triggers one BRE-to-Python translation every grep leg uses, differential-tested against /usr/bin/grep and GNU grep; whatever is not provably translated goes to the real grep, never silently literal (bug-167)"
tags: [task, plan-25, bug-167, grep, bre, drop-in, dialect, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-09
---

# Task 25.4: grep BRE translation {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08; revision round 1 2026-11-09, [[#rev-round-1]])
> Bug: bug-167 (BRE escapes; cliquedb priority 5). Out of scope and logged separately: bug-173
> (the `# rmx grep fallback via rg` line on every call, cliquedb item 5) and bug-174 (substring
> mode reads unescaped BRE metas literally).
> Depends on: task 3.7 merged (it edits `cli.py`; no 3.7 hunk is in the grep block). Independent
> of 25.1-25.3.

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: derives-from -> [[bug_registry#registry]]
rel: derives-from -> [[bsd-plan25-spec-r1-2f4a1df]]
rel: depends-on -> [[project_grep_surface_defect_family]]
rel: related-to -> [[project_grep_output_shape_one_resolver]]
rel: related-to -> [[plan-16-invisible-grep-shim]]

## Why {#why}

`rmx grep -n "B0\|group_key" file` exits 2 with `Error: grep: BRE escape '\\|' is not supported
(pass -E for ERE, or -F for a literal match)`. The guard is `cli.py:6407-6419`: in the default
substring mode, `\|`, `\(`, `\)`, `\{`, `\}` raise `click.UsageError`. It was added on purpose
(bus `85e22d5d06dd`, `tests/test_grep_stdin_dialect.py::test_bre_alternation_fails_loud`): before
it, `a\|b` matched literally, a silent wrong answer, and exit 2 is the drop-in wrappers'
fall-back-to-the-real-tool signal (`bin/rmxgrep:126`, `bin/rmxrg:108`). Through the wrappers the
answer is right; at the `rmx grep` CLI, which agents and the PreToolUse rewrite reach directly, it
is a hard error where grep answers. {#why-lead}

Every OTHER backslash escape takes the substring path and answers wrongly in silence (dev tree,
stdin leg, [[bsd-plan25-spec-r1-2f4a1df#probes]]): `rmx grep 'foo\.py'` prints the literal line
`foo\.py` and misses `foo.py`; `a\+b`, `\bab`, `ab\b` match nothing where grep matches. `\.` is
probably the most common escaped pattern an agent writes.

The oracles agree almost everywhere. `/usr/bin/grep` (BSD grep 2.6.0-FreeBSD, "GNU compatible")
and GNU grep 3.12 (`/opt/local/bin/ggrep`) agree on 26 of 27 patterns in the bsd's sweep. The one
divergence is `a\{,1\}b`: BSD exits 2 ("invalid repetition count(s)"), GNU matches. The platform
grep (the one the wrappers fall back to) is BSD, so BSD is the authority where they differ.

`# rmx grep fallback via rg` on every call (cliquedb item 5) is a stderr line (`cli.py:6901`,
`err=True`) and is bug-173; whether the index answers plain literals at all is plan-14 / plan-16's
measurement. Substring mode reading `a.b` literally is bug-174.

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| b1 | Translate BRE → Python `re` and take the regex path, rather than delegating every BRE | the index, the stdin filter and the fallback keep working and learning; delegation runs `rg` first (`_grep_delegate`), and rg reads `\|` as a literal pipe |
| b2 | ONE function, `grep_dialect.bre_to_py(pattern) -> Translated(regex, needs_backrefs, has_alternation)`, raising `UntranslatableBRE` | the pattern reaches four legs; translating per leg is bug-058's failure |
| b3 | Translation runs only for a BRE: no `-E`, `-F`, `--regex`, `-P`; `rmxrg`'s injected `-E` never translates | ERE and rg read `\|` as a literal pipe already |
| b4 | Trigger: the pattern contains ANY backslash | `\.`, `\*`, `\[`, `\b`, `\1` are silently wrong today, not only the five the guard names |
| b5 | Not provably translated → the REAL GREP FIRST with the original argv (never rg, never `UsageError`, never literal) | the platform grep is the authority |
| b6 | Patterns with no backslash keep today's substring path | changing what `a.b` means for every call is bug-174, with its own measurement |
| b7 | `-o` (and `--color`) with an alternation in the pattern → real grep | grep's `-o` is leftmost-LONGEST (`echo ab \| grep -o 'a\|ab'` prints `ab`); Python's alternation is leftmost-first |

## Requirements {#requirements}

1. **R1 `bre_to_py`.** In a new `src/refmatrix/grep_dialect.py`, pure. Outside brackets:
   - operators: `\|` → `|`; `\(` `\)` → `(` `)`; `\{m\}`, `\{m,\}`, `\{m,n\}` → `{m}`, `{m,}`,
     `{m,n}`; `\+` → `+`; `\?` → `?`;
   - word anchors: `\<` → `\b(?=\w)`; `\>` → `\b(?<=\w)`; `\b`, `\B`, `\w`, `\W`, `\s`, `\S` kept;
   - escaped literals: `\.`, `\*`, `\[`, `\]`, `\\`, `\^`, `\$`, `\/` → the Python-escaped literal;
   - back-references `\1`-`\9` kept and `needs_backrefs` set;
   - literal in BRE, operator in Python: `|`, `(`, `)`, `{`, `}`, `+`, `?` → escaped;
   - `*` at the start, after `\(` or after `\|` is literal (escaped);
   - `^` is an anchor only at the start / after `\(` / after `\|`; `$` only at the end / before
     `\)` / before `\|`; elsewhere escaped;
   - `\{,n\}` raises `UntranslatableBRE` (BSD exits 2, GNU matches; the platform grep decides via
     b5); any other escape not listed raises.
   Inside a bracket expression:
   - a backslash is LITERAL (POSIX): `[\.]` → `[\\.]`; `[a\]` is the set `{a, \}`;
   - `]` first (or after `^`) is literal; POSIX classes (`[:alpha:]`, `[:digit:]`, `[:space:]`,
     `[:alnum:]`, `[:upper:]`, `[:lower:]`, `[:punct:]`, `[:xdigit:]`, `[:blank:]`, `[:cntrl:]`,
     `[:print:]`, `[:graph:]`) map to explicit ranges; an unknown class or an equivalence /
     collating element (`[=a=]`, `[.a.]`) raises;
   - a literal `[` and the pairs `&&`, `--`, `||`, `~~` are escaped so Python emits no
     nested-set FutureWarning (the test runs with `-W error::FutureWarning`). {#r1}
2. **R2 One entry, every leg, grouped.** In `cli.grep` the guard at `cli.py:6407-6419` is replaced:
   when b3 / b4 hold, `pattern` becomes `bre_to_py(pattern).regex` and `regex = True` BEFORE the
   stdin branch, the `-w` / `-x` wrapping and the index / fallback fork, so every leg reads the
   translated pattern. `-w` wraps as `\b(?:p)\b` and `-x` as `^(?:p)$` on EVERY leg (the file leg
   builds `\b{p}\b` / `^{p}$` ungrouped at `cli.py:6450-6453`, and the stdin leg groups only `-x`;
   both are fixed, for translated and native regex alike). The original pattern is kept for
   `query.log`'s `body`, the learned concept name and delegation. {#r2}
3. **R3 Real grep for the rest.** `UntranslatableBRE`; `needs_backrefs` on a leg that would reach
   rg; or b7 (`-o` / `--color` with `has_alternation`) → `_grep_delegate(..., grep_first=True)`
   (new argument) runs `grep` before `rg` with the ORIGINAL argv; the stderr note names the reason
   (`# rmx grep delegated to grep (BRE back-reference)`). {#r3}
4. **R4 The fallback reads the translation.** `_grep_rg_fallback` (`cli.py:6803`) receives the
   translated pattern with `regex=True` and passes it to rg as a regex (no `-F`) and to `grep` as
   `-E`; a translation using a construct rg lacks (back-references, look-around from `\<` / `\>`)
   routes per R3 instead. The learned concept is `query/<original pattern>`. {#r4}
5. **R5 The old guard's test is superseded, not deleted silently.**
   `test_bre_alternation_fails_loud` becomes `test_bre_alternation_matches_like_grep`, with a
   docstring naming bus `85e22d5d06dd`, this task, and why the contract changed (the silent wrong
   answer it prevented is still prevented: the pattern now matches as grep matches). {#r5}

## Acceptance criteria {#acceptance}

Production path: the `rmx grep` CLI as the PreToolUse rewrite and the wrappers invoke it, in 23.0's
sandbox on a fixture project. The oracle is the real tools; the test runs with
`-W error::FutureWarning`. {#acceptance-lead}

1. **AC-1 The reported calls.** `rmx grep -n "B0\|group_key" <file>` and `rmx grep -n 'foo\.py'
   <file>` exit 0 and their stdout equals `/usr/bin/grep`'s byte for byte (RED at HEAD: exit 2;
   the literal `foo\.py` line).
2. **AC-2 Differential table.** For each pattern below and each of (explicit file, stdin pipe,
   `-c`, `-l`, `-i`, `-w`, `-x`, `-v`, `-o`), `rmx grep` stdout and exit equal `/usr/bin/grep`'s
   AND GNU grep's on the same fixture; where they differ, the row records both and asserts rmx
   equals `/usr/bin/grep`. Patterns: `a\|b`, `\(ab\)\{2\}`, `ab\{1,2\}c`, `a\{,1\}b` (divergence
   row: BSD exit 2, so rmx exit 2 via R3), `a\+b`, `a\?b`, `\<word\>`, `\>a`, `\ba`, `ab\b`,
   `^a\|b$`, `a|b` (literal pipe in BRE), `(x)`, `{1}`, `a+`, `*star`, `x^y$z`,
   `[[:digit:]]\+`, `[]a]`, `[^]a]`, `[\.]`, `[a\]`, `[a&&b]`, `\(a\)\1` (back-reference),
   `foo\.py`, `\.\*`, `a\\b`, `\w\+`. `-o` rows include `a\|ab` (R3 delegation). RED at HEAD:
   every row with a backslash.
3. **AC-3 Path-less (index + fallback).** In a project whose index has no concept for the
   pattern, `rmx grep "alpha\|beta"` exits 0 and its file:line set equals `grep -rn
   "alpha\|beta" <root>` restricted to indexed files (RED at HEAD: exit 2); the learned concept is
   `query/alpha\|beta`.
4. **AC-4 Dialects untouched.** `rmx grep -E 'a\|b'` and `rmxrg 'a\|b'` (rg dialect, `-E`
   injected) match a literal pipe, as `grep -E` / `rg` do; `rmx grep -F 'a\|b'` matches the
   literal backslash-pipe; `rmx grep 'a.b'` keeps substring semantics (b6, bug-174), asserted so a
   change to it is deliberate.
5. **AC-5 `-w` / `-x` grouping.** `rmx grep -w 'a\|b'` and `rmx grep -x 'a\|b'` equal grep on the
   file leg and the stdin leg; and `rmx grep -E -x 'a|b'` (native regex, no translation) likewise
   (RED at HEAD on the file leg: ungrouped `^a|b$`).
6. **AC-6 Back-reference and delegation.** `rmx grep '\(ab\)\1' file` equals `/usr/bin/grep` on
   file and stdin; the stderr note names the delegation whenever the real tool answered.
7. **AC-7 Wrappers.** `rmxgrep 'B0\|group_key' file` in rich mode returns the same bytes without
   taking the wrapper's fallback branch (asserted by its stderr marker).
8. **AC-8 Unit table.** `bre_to_py` over every R1 rule, including anchor and leading-`*`
   positions, every POSIX class, backslash inside brackets, the four nested-set pairs, `\<` / `\>`
   vs `\b`; unknown classes, `[=a=]`, `\{,n\}` and unlisted escapes raise `UntranslatableBRE`.
9. **AC-9 Mutations that must FAIL a test:** translate but leave `regex=False` (AC-1); translate
   after the stdin branch (AC-2 stdin leg); trigger only on the old five escapes (AC-1 `foo\.py`);
   skip escaping Python-only operators (AC-2 `a|b`, `(x)`); `\<` → `\b` (AC-2 `\>a`); copy
   brackets verbatim (AC-2 `[\.]`, `[a\]`); ungrouped `-x` (AC-5); answer `-o` with alternation in
   Python (AC-2 `a\|ab -o`); delegate rg-first (AC-6); translate under `-E` (AC-4); translate
   `\{,n\}` GNU-style (AC-2 divergence row).

## Files to create {#files-to-create}

| file | purpose |
|---|---|
| `src/refmatrix/grep_dialect.py` | `bre_to_py`, `Translated`, `UntranslatableBRE` |
| `tests/test_task25_4_grep_bre.py` | AC-1..AC-9, differential against `/usr/bin/grep` and GNU grep |

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/cli.py` (`grep`, `:6407-6419`, `:6450-6453`; `_grep_stdin` `:6113`; `_grep_delegate` `:6541`; `_grep_rg_fallback` `:6803`) | translate once before the fork; grouped `-w` / `-x` on both legs; `grep_first`; translated regex into the fallback |
| `tests/test_grep_stdin_dialect.py` | R5 supersession of `test_bre_alternation_fails_loud` |
| `workflow/development_resources.md` | GNU grep (`ggrep`, MacPorts `/opt/local/bin`) named as a test dependency |
| `workflow/bug_registry.md` | bug-167 → fixed at merge (bug-173 / bug-174 stay open) |

## Test strategy {#test-strategy}

- RED first: AC-1, AC-2, AC-3, AC-5 at HEAD, recorded with exit codes.
- The oracle is the real tool. GNU grep is a required test dependency: if `ggrep` is absent the
  test FAILS naming the gap (never a skip); `workflow/development_resources.md` records how to
  install it.
- The fixture is synthetic text; the differential runner is committed so the sweep is re-runnable
  like `workflow/review-output/grep-flag-sweep.py` (the 0.73.0 precedent).

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| e1 | Translate vs delegate every BRE | translate (b1); delegation for what is not provably translated (b5, b7) |
| e2 | GNU grep as a required test dependency | yes; BSD and GNU disagree at the edges (`\{,n\}`) and the drop-in must know where |
| e3 | Substring-mode `a.b` | out of scope; logged as bug-174 |
| e4 | Where BSD and GNU disagree | follow `/usr/bin/grep` (the platform grep the wrappers fall back to) |

## Revision round 1 (2026-11-09) {#rev-round-1}

Answers [[bsd-plan25-spec-r1-2f4a1df]] and the orchestrator's decisions of 2026-11-09.

| finding | change | anchor |
|---|---|---|
| S8 most escapes stay silently literal; AC-2 contradicts b4 | trigger on ANY backslash (b4); the full escape set in R1; `foo\.py` in AC-1/AC-2; `\.\*` is now consistent with the trigger | [[#why]], [[#decisions]] b4, [[#r1]], AC-1, AC-2 |
| S9 translation rules disagree with both greps | `\<` / `\>` as look-around word starts/ends; backslash literal inside brackets; nested-set pairs escaped (test under `-W error`); `-o` / `--color` with alternation delegated (b7); `(?:…)` grouping for `-w` / `-x` on every leg; `\{,n\}` follows BSD via delegation; six cases added to AC-2 and AC-8 | [[#r1]], [[#r2]], [[#r3]], AC-2, AC-5, AC-8, AC-9 |
| M8 bug-167 also carries item 5; `a.b` unlogged | bug-167 split: the fallback-banner row is bug-173, substring `a.b` is bug-174, both logged 2026-11-09 | header, [[#why]], e3 |
