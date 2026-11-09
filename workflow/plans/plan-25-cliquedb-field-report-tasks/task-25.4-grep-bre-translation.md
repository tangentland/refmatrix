---
gmd: "0.1"
id: task-25.4-grep-bre-translation
title: "Task 25.4: rmx grep reads a GNU/BSD BRE the way grep does — one BRE-to-ERE translation every grep leg uses, differential-tested against /usr/bin/grep and GNU grep; an untranslatable BRE goes to the real grep, never to a usage error (bug-167)"
tags: [task, plan-25, bug-167, grep, bre, drop-in, dialect, cliquedb]
metadata:
  node_type: task
  status: pending
  plan: plan-25-cliquedb-field-report
  created: 2026-11-08
  updated: 2026-11-08
---

# Task 25.4: grep BRE translation {#root}

> Plan: [[plan-25-cliquedb-field-report]]
> Status: Pending (spec drafted 2026-11-08)
> Bug: bug-167 (cliquedb priority 5, "minor"; hit twice in one session)
> Depends on: task 3.7 merged (it edits `cli.py`; no 3.7 hunk is in the grep block). Independent
> of 25.1-25.3.

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
rel: derives-from -> [[bug_registry#registry]]
rel: depends-on -> [[project_grep_surface_defect_family]]
rel: related-to -> [[project_grep_output_shape_one_resolver]]
rel: related-to -> [[plan-16-invisible-grep-shim]]

## Why {#why}

`rmx grep -n "B0\|group_key" file` exits 2 with `Error: grep: BRE escape '\\|' is not supported
(pass -E for ERE, or -F for a literal match)`. The guard is `cli.py:6407-6419`: in the default
substring mode any `\|`, `\(`, `\)`, `\{`, `\}` raises `click.UsageError`. It was added on purpose
(bus `85e22d5d06dd`, `tests/test_grep_stdin_dialect.py::test_bre_alternation_fails_loud`): before
it, `a\|b` matched as a literal and returned a silent wrong answer, and exit 2 is the drop-in
wrappers' fall-back-to-the-real-tool signal (`bin/rmxgrep:126`, `bin/rmxrg:108`). So through the
wrappers the answer is right; at the `rmx grep` CLI (which agents and the PreToolUse rewrite reach
directly) it is a hard error where grep answers. {#why-lead}

Probed 2026-11-08 on this workstation against a 9-line file:

| pattern (BRE, no flags) | `/usr/bin/grep` (BSD grep 2.6.0-FreeBSD) | GNU grep (`/opt/local/bin/ggrep`) | `rmx grep` |
|---|---|---|---|
| `B0\|group_key` | alternation (3 lines) | alternation | exit 2 |
| `a\(b\)` | group | group | exit 2 |
| `ab\{2\}` | interval (`abb`) | interval | exit 2 |
| `a\+b`, `a\?b` | GNU extensions honoured | honoured | substring (literal `\+`) |
| `(bar)`, `ab{2}`, `a+b` | literals | literals | substring: literals (correct) |

So both greps a drop-in must equal read GNU's BRE extensions, and today's guard covers only some of
them: `\+` / `\?` still take the literal substring path and silently miss. That is the
[[project_grep_surface_defect_family]] shape again: one contract (read the pattern the way grep
reads it), honoured on some paths and not others.

`# rmx grep fallback via rg` on every call (cliquedb item 5) is a stderr line (`cli.py:6901`,
`click.echo(..., err=True)`); it does not touch stdout bytes. Whether the index answers plain
literals at all is plan-14 / plan-16's measurement. Both are out of scope here and recorded only.

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| b1 | Translate BRE → Python-`re` ERE and take the regex path, rather than delegating every BRE to the real tool | the index, the stdin filter and the fallback all keep working and learning; delegation would run `rg` first (`_grep_delegate`), and rg reads `\|` as a LITERAL pipe, which is wrong |
| b2 | ONE function, `grep_dialect.bre_to_ere(pattern) -> str`, raising `UntranslatableBRE` | the pattern reaches four legs (index match, stdin filter, explicit-file read, rg / grep fallback); translating per leg is bug-058's failure |
| b3 | Translation runs only when the pattern is BRE: no `-E`, no `-F`, no `--regex`, no `-P`; `rmxrg`'s injected `-E` therefore never translates | ERE and rg dialect read `\|` as a literal pipe already |
| b4 | Trigger: the pattern contains ANY BRE escape grep treats as an operator (`\|`, `\(`, `\)`, `\{`, `\}`, `\+`, `\?`, `\<`, `\>`) | the probe shows `\+` / `\?` miss today, not only the five the guard names |
| b5 | An untranslatable BRE (back-references the fallback's rg cannot run, an unknown POSIX class) is delegated to the REAL GREP FIRST with the original argv, never rg, never `UsageError` | the real grep is the authority; rg-first would answer wrongly |
| b6 | Plain patterns with no BRE escape keep today's substring path | changing what `a.b` means for every call is a separate decision with a measured cost, not a side effect of this bug |

## Requirements {#requirements}

1. **R1 `bre_to_ere`.** In a new `src/refmatrix/grep_dialect.py`, pure:
   - `\|` → `|`; `\(` `\)` → `(` `)`; `\{m,n\}` → `{m,n}`; `\+` → `+`; `\?` → `?`; `\<` `\>` →
     `\b`;
   - characters that are literal in BRE and operators in ERE are escaped: `|`, `(`, `)`, `{`, `}`,
     `+`, `?`;
   - `*` at the start of the pattern, after `\(` or after `\|` is literal (escaped);
   - `^` is an anchor only at the start / after `\(` / after `\|`, `$` only at the end / before
     `\)` / before `\|`; elsewhere they are escaped;
   - bracket expressions are copied with `]`-first and `^`-first handling, POSIX classes
     (`[:alpha:]`, `[:digit:]`, `[:space:]`, `[:alnum:]`, `[:upper:]`, `[:lower:]`, `[:punct:]`,
     `[:xdigit:]`) mapped to explicit ranges; an unknown class raises;
   - `\1`-`\9` are kept (Python `re` supports them) and mark the result `needs_backrefs`;
   - `\.`, `\*`, `\[`, `\]`, `\\`, `\w`, `\W`, `\s`, `\S`, `\b`, `\B` are kept. {#r1}
2. **R2 One entry, every leg.** In `cli.grep`, the guard at `cli.py:6407-6419` is replaced: when
   b3 / b4 hold, `pattern` is replaced by `bre_to_ere(pattern)` and `regex = True`, BEFORE the
   stdin branch, the `-w` / `-x` wrapping and the index / fallback fork, so every leg reads the
   translated pattern. The original pattern is kept only for `query.log`'s `body` and for
   delegation. {#r2}
3. **R3 Untranslatable → real grep.** `UntranslatableBRE`, or `needs_backrefs` on a leg that
   would reach rg, calls `_grep_delegate` with a `grep_first=True` argument (new) so `grep` runs
   before `rg`, with the ORIGINAL argv; the stderr note names the reason
   (`# rmx grep delegated to grep (BRE back-reference)`). {#r3}
4. **R4 The fallback reads ERE.** `_grep_rg_fallback` (`cli.py:6803`) receives the translated
   pattern with `regex=True` and passes it to rg as a regex (no `-F`), and to `grep` as `-E`. The
   learned concept is named after the ORIGINAL pattern (`query/<pattern>`), so the index's name for
   the query is the one the user typed. {#r4}
5. **R5 The old guard's test is superseded, not deleted silently.**
   `test_bre_alternation_fails_loud` becomes `test_bre_alternation_matches_like_grep` with a
   docstring naming bus `85e22d5d06dd`, this task and why the contract changed (the silent
   wrong answer it prevented is still prevented: the pattern now matches as grep matches). {#r5}

## Acceptance criteria {#acceptance}

Production path: the `rmx grep` CLI as the PreToolUse rewrite and the wrappers invoke it, in 23.0's
sandbox on a fixture project. {#acceptance-lead}

1. **AC-1 The reported call.** `rmx grep -n "B0\|group_key" <file>` exits 0 and its stdout equals
   `/usr/bin/grep -n "B0\|group_key" <file>` byte for byte (RED at HEAD: exit 2, `BRE escape`).
2. **AC-2 Differential table, three legs.** For each pattern in the table below and each of
   (explicit file, stdin pipe, `-c`, `-l`, `-i`, `-w`, `-x`, `-v`), `rmx grep` stdout and exit
   equal `/usr/bin/grep`'s AND GNU grep's on the same fixture; where BSD and GNU differ, the row
   records both and asserts rmx matches BSD (the grep on PATH, which the wrapper falls back to).
   Patterns: `a\|b`, `\(ab\)\{2\}`, `ab\{1,2\}c`, `a\+b`, `a\?b`, `\<word\>`, `^a\|b$`, `a|b`
   (literal pipe in BRE), `(x)`, `{1}`, `a+`, `*star`, `x^y$z`, `[[:digit:]]\+`, `[]a]`,
   `[^]a]`, `\(a\)\1` (back-reference), `\.\*`. RED at HEAD: every row with an operator escape.
3. **AC-3 Path-less (index + fallback).** In a project whose index has no concept for the
   pattern, `rmx grep "alpha\|beta"` exits 0 and its file:line set equals `grep -rn
   "alpha\|beta" <root>` restricted to indexed files (RED at HEAD: exit 2); the learned concept is
   `query/alpha\|beta`.
4. **AC-4 Dialects untouched.** `rmx grep -E 'a\|b'` and `rmxrg 'a\|b'` (rg dialect, `-E`
   injected) match a literal pipe, as `grep -E` / `rg` do; `rmx grep -F 'a\|b'` matches the
   literal backslash-pipe; `rmx grep 'a.b'` keeps substring semantics (b6), asserted so a future
   change to it is deliberate.
5. **AC-5 Back-reference.** `rmx grep '\(ab\)\1' file` equals `/usr/bin/grep` on file and stdin,
   and the stderr note names the delegation when the fallback leg is reached.
6. **AC-6 Wrappers.** `rmxgrep 'B0\|group_key' file` in rich mode returns the same bytes without
   falling back (the wrapper's fallback branch is not taken: asserted by its stderr marker).
7. **AC-7 Unit table.** `bre_to_ere` over every R1 rule, including the anchor and leading-`*`
   positions and each POSIX class; an unknown class raises `UntranslatableBRE`.
8. **AC-8 Mutations that must FAIL a test:** translate but leave `regex=False` (AC-1); translate
   after the stdin branch (AC-2 stdin leg); skip escaping ERE-only metas (AC-2 `a|b`, `(x)`);
   delegate rg-first (AC-5); translate under `-E` (AC-4); drop `\+` / `\?` from the trigger
   (AC-2).

## Files to create {#files-to-create}

| file | purpose |
|---|---|
| `src/refmatrix/grep_dialect.py` | `bre_to_ere`, `UntranslatableBRE`, the trigger predicate |
| `tests/test_task25_4_grep_bre.py` | AC-1..AC-8, differential against `/usr/bin/grep` and GNU grep |

## Files to modify {#files-to-modify}

| file | change |
|---|---|
| `src/refmatrix/cli.py` (`grep`, `:6407-6419`; `_grep_delegate` `:6541`; `_grep_rg_fallback` `:6803`) | translate once before the fork; `grep_first`; ERE into the fallback |
| `tests/test_grep_stdin_dialect.py` | R5 supersession of `test_bre_alternation_fails_loud` |
| `workflow/development_resources.md` | GNU grep (`ggrep`, MacPorts `/opt/local/bin`) named as a test dependency |
| `workflow/bug_registry.md` | bug-167 → fixed at merge |

## Test strategy {#test-strategy}

- RED first: AC-1, AC-2, AC-3 at HEAD, recorded with the exit codes.
- The oracle is the real tool. GNU grep is a required test dependency: if `ggrep` is absent the
  test FAILS naming the gap (never a skip, per the tests rule); `workflow/development_resources.md`
  records how to install it.
- The fixture is synthetic text; the differential runner is committed so the sweep is re-runnable
  like `workflow/review-output/grep-flag-sweep.py` (the 0.73.0 precedent).

## Open decisions {#open-decisions}

| # | decision | recommendation |
|---|---|---|
| e1 | Translate vs delegate every BRE to the real grep | translate (b1); delegation is the fallback for what cannot be translated |
| e2 | Make GNU grep a required test dependency | yes; BSD and GNU disagree at the edges and the drop-in must know where |
| e3 | Fix substring-mode `a.b` (grep reads `.` as any char) while here | no (b6); it changes every plain call and needs its own measurement and bug row; log it if not already logged |
