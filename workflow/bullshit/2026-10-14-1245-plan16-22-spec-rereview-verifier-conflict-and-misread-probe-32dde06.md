---
gmd: "0.1"
id: bsd-plan16-22-spec-rereview-32dde06
title: "plan-16 rev 6 + plan-22 spec re-review: 16.6's re-run verifier is right and 22.1's Python translation contradicts it, but the re-run calls matching rows stale (cutoffs, absolute-path excludes, exit 2), rebuild wipes the sidecar, the marks have no reader, and d8c's '>= 114' misreads the probe"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-rereview-16.1-16.6-22.1-22.5
round: 6 (plan-16) / 2 (plan-22)
tags: [bsd, audit, spec-review, grep, provenance, removal, repair, bug-086, global-store, cross-plan]
---

# ch-bsd spec re-review: plan-16 revision 6 and plan-22 (pre-implementation) {#root}

**Commit reviewed:** `32dde06`, branch `wave0-spec-reviews`. **Written:** 2026-10-14T12:45-0700.
`src/` is unchanged since `b1c4324` (`git diff --stat b1c4324 HEAD -- src` is empty), so the code
line numbers the specs cite at `b1c4324` hold at HEAD.

**Scope:** the plan-16 plan and tasks 16.1 to 16.6 (revision table `#revision-6`); the plan-22
plan and tasks 22.1, 22.1a, 22.2, 22.3, 22.4 and 22.5 (`#rev-2026-10-14`). Prior reviews: r5
(`bsd-plan16-spec-review-r5-cd7c923`), plan-22 r1 (`bsd-plan22-spec-review-3104a81`), and the
decision-log review (`bsd-decision-log-review-a192ba2`). Decisions come from
`plan-review-2026-10-14`, where the `#t8` close-out wins.

**Method:**
- I checked every revision-table claim against the spec text, and every code fact against HEAD.
- I ran probes in a throwaway `mktemp -d` directory, since deleted:
  - BSD grep 2.6.0 and rg 15.1.0, each re-run in 16.6 R2's exact form;
  - Python `re` on the same patterns;
  - click 8.3.3 on 16.5 R0's `help_option_names: []` replica.
- I parsed the live global `~/.refmatrix/facts.log` read-only with `python3 -I`, using scripts in
  my scratchpad. That is a log file, not a catalog.
- I read `workflow/review-output/global-relative-resolve-probe.log`.
- I read the launchd plists' `WorkingDirectory`.

I touched nothing in `src/`, `tests/`, any store, any plan file or any ledger. I made no `rmx` call,
opened no `Store()` and ran no suite.

rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: amends -> [[bsd-plan22-spec-review-3104a81]]
rel: related-to -> [[bsd-decision-log-review-a192ba2]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

## Live evidence {#evidence}

### The verifier: re-run versus Python `re` {#ev-verifier}

16.6 R2's form is `bin <match_argv> -nH --null -e PAT -- FILE`.

| case | BSD grep 2.6.0 / rg 15.1.0 (re-run) | Python `re` (22.1's translation target) |
|---|---|---|
| BRE `zzz\|alp` on `alpha` | grep: `a.txt\0 1:alpha` | literal `\|` → no match |
| BRE `\(foo\)x` on `foox` | grep: `2:foox` | no match |
| `[[:digit:]]` on `a1` | grep: match | **compiles** (FutureWarning) and returns **False**. Not caught as "does not compile" |
| `\<foo\>` on `foo bar` | grep: match | **compiles**, returns **False** |
| BRE `a+b` on `a+b` / `aab` | grep: matches `a+b` only (BRE `+` is literal) | matches `aab` only |
| rg `\p{Greek}` | rg: compiles | `re.PatternError: bad escape \p` |
| `-e '-x'` | grep: `d.txt\0 1:-x` | — |
| grep `a\{`, rg `a{`, rg `(` | **exit 2, no output** (parse error) | — |
| `-m 1` on a file whose line 1 was edited to match too (recorded row: line 2) | grep prints `1:alpha2` only. **Line 2 still matches and is absent** | — |
| `--exclude='*bsdp*'`, file named relatively (`a.txt`) | prints the hit, rc 0 | — |
| the same exclude, file named ABSOLUTELY (`/tmp/bsdp.X/a.txt`) | **no output, rc 1**: BSD matches the exclude against the whole path | — |
| `--include='a.txt'`, absolute path | prints the hit (basename matched) | — |
| rg `-g '!*bsdp*'`, absolute path | prints the hit (rg ignores globs on named files) | — |

### The global facts.log, as a proxy for the 1,087 {#ev-facts}

The log names more entities than the catalog: 2,997 relative learned files against the catalog's
1,087 (plan-22 r1 #m-4). So these counts describe the POPULATION the 1,087 were drawn from. They
are not the 1,087 themselves.

- **Where the relative learned files resolve:**

  | where it resolves | files |
  |---|---|
  | as `$HOME/<rel>`, inside the probe's three walk trees (`~/github`, `~/claude_tools`, `~/enduris`) | 942 |
  | as `$HOME/<rel>`, **outside** them | **1,337** |
  | not under `$HOME` | 718 |

- **Of the 2,279 that exist as `$HOME/<rel>`, 2,034 (89%) lie under NO project store root.** By
  prefix:
  - `github/atollogy/*` outside `bdep`: 520
  - `lib/python3.10`: 194
  - `Library/Application Support`: 189
  - `Library/Mail`: 121
  - and so on.

  Only 245 lie under a project root: viascope 184, atldb 41, refmatrix 16, cliquedb 4.
- **Protection source.** Every global `protect` event on a pytest-tmp entity (1,655) and on a
  relative learned entity (3,007) DIRECTLY follows an `entity` event for the same name, with 0
  exceptions. Applied to the global store, 22.2 R5's attribution rule therefore yields `upsert`
  for all of them.

### The probe log and the launchd roots {#ev-roots}

`global-relative-resolve-probe.log`, in full:

| line | value |
|---|---|
| `entities` | 1087 |
| `exists@` | 0: 695, 1: 388, 2: 4 |
| `verified@` | 0: 725, 1: 362 |
| `unique verified, by root` | `{'/Users/tholley': 362}` |
| walk | 972,849 files in 14.4 s |
| walk result | `{'verified@0': 563, 'verified@1': 476, 'verified@2': 48, 'cands@0': 417, 'cands@1': 518, 'cands@2': 152}` |

The 8 launchd daemons (`~/Library/LaunchAgents/com.refmatrix.daemon.*.plist`, `WorkingDirectory`)
are:
- atldb, cliquedb, cliquet, orderly, viascope (all under `~/github/atollogy/bdep`);
- `~/claude_tools/refmatrix`;
- `~/enduris/thiquet`;
- **`/Users/tholley` (label `tholley`, the GLOBAL store).**

So "the 8 registered roots" include the global store's own root. **All 362 rows verified under
that root and under none of the 7 project roots.**

### Spec facts verified at HEAD (no finding) {#ev-verified}

- `rebuild_index_from_log` (`store.py:7566`) unlinks `catalog.db` and replays only `facts.log`.
  Every table without a log event is wiped ([[#b-2]]).
- `evidence_line_matches` (`store.py:759`), `identifier_variant_regex` (`:786`),
  `verify_evidence_rows` (`:816`), `is_memory_only_root` (`:503`), `_bulk_purge_ids` (`:6032`),
  `discovery._roots_from_launchd` (`discovery.py:70`) and `_learn_grep_hits`
  (`daemon.py:4295 @ b1c4324`) are where the specs say.
- The context backstop at `daemon.py:4795-4806` calls `rg -nH -i -F … -e TERM…` at
  `context.py:912-926`, as 16.1 R10 describes.
- **The cli.py BRE refusal.** Since 0.65.1 (`583ad1c`), `cli.py:6168-6178` refuses BRE escapes
  (`\|`, `\(`, …) on today's teach path. So pre-provenance rows were never taught from a BRE
  alternation, and 22.1's permissive reading is safe for them. It is not safe for rows that lose
  their provenance later ([[#b-2]]).
- **16.5 R0, probed on click 8.3.3** with `help_option_names: []` and an UNPROCESSED catch-all:
  - `-e --help f.txt`, `--help`, `-ekey f` and `--limit 5 x` all reach `argv` verbatim;
  - the `parse_args` override keeps `--`.
- `plan-of-plans.md:47` lists the 16.6 slice in Wave 1 (`#t8-wave1`).
- 19.4 R5 sets the compiled-subject `stale` mark.

## The cross-plan conflict, adjudicated {#conflict}

**Which verifier is consistent with r5 #b-r5-1 and `#t6-fixes`: 16.6 R2 (re-run the recorded
tool).**
- r5's fix was: re-run the tool, never Python `re`; OR name the subset Python can evaluate and mark
  everything else `unverifiable`.
- `#t6-fixes` says "the verifier speaks grep's dialect".

22.1 `#r1-verify` takes neither path:
- it translates "BRE / ERE / fixed / rg" to Python `re` with no named subset;
- its only `unverifiable` exit is "cannot be translated or does not compile".

The probes show silent mistranslations that COMPILE: POSIX classes, `\<`/`\>`, BRE-literal `+`.
22.1 classifies those rows `stale-line`, and 22.2 R9 removes them. A Python grep-dialect translator
is also exactly the "Python re-implementation of grep" that plan-16 deletes after four audit
rounds.

**Implementability.**
- **Re-run: implementable.** BRE `\|` and `\(\)`, rg's Rust syntax and `\p{…}`, and `-e -x` all
  verify by re-running. It is subprocess-bound, which is why 16.6 R2 keeps it off the read path.
  Its verdict rule has three holes that turn matching rows into `stale` ([[#b-1]]).
- **Translation: implementable only for a named subset** (`fixed`; ERE/rust without classes,
  escapes or lookaround). Everything else must be `unverifiable`.

**The resolution is spec-settleable and needs no user decision:**
- 22.1 calls 16.6's verifier;
- 16.6 R2 exposes the current matching line set that 22.1's set classification needs ([[#b-4]]).

**`stale_seen` as exact.** Plan-22 does NOT treat it as exact anywhere. It does not read it at
all ([[#b-3]]).

## Prior findings: status {#prior-status}

### Plan-16 (r5 and the r4 partials) {#prior-16}

| id | status | evidence |
|---|---|---|
| b-r5-1 (provenance cannot replay the rules) | **partial** | 16.6 R1 records `tool`/`bin`/`dialect`/`match_argv`/`line_hash`, R2 re-runs the tool, and AC-3 has mutation power (the probe confirms `evidence_line_matches` fails `zzz\|alp`). But plan-22 22.1 contradicts it ([[#b-4]]), the re-run's verdict rule is unsafe ([[#b-1]]), and rebuild erases the provenance ([[#b-2]]) |
| b-r5-2 (BRE-routing mutation blind) | **closed** | 16.5 `#ac-5-seed`: a literal `alpha$` line seeded by `grep -rnF`, which survives substring verification; a pre-check fails loudly at 0 rows; AC-5b's literal output excludes the line |
| s-r5-1 (click parses `--help`; `-k` clusters) | **closed** | R0 `help_option_names: []`; `--help` only as the first argument; cluster walk on `e f m A B C d D`. Probed on click 8.3.3 |
| s-r5-2 (AC-4b vs pruning) | **closed** | 16.1 R1b prunes only recursive re-runs; 16.2 AC-4b kept, with a mutation |
| s-r5-3 (reader-rule drops as staleness) | **closed** | 16.6 R4: a `reader_rule` drop with an equal or NULL hash enqueues nothing; AC-4 plus mutation |
| s-r5-4 (`evidence_rowid` key) | **closed** | key = 5 identity columns + `rules_sha`; R1c merge step; AC-2 plus two mutations. Residue: 22.2 changes key columns ([[#s-5]]) |
| s-r5-5 (16.6 unscheduled) | **closed** | 16.6 header: Wave 1 after 23.1, no 16.1 dependency; plan `#waves`; `plan-of-plans.md:47` |
| s-r5-6 (route 2 absorbs other spawners) | **closed** | 16.1 R6 `spawned_by` (refused if missing); 16.4 `#r1-forward` route 2 = `shim` only; AC-3 rows |
| m-r5-1 … m-r5-7 | **closed (7)** | 16.5 R6 / 5d-5f / R3+R4 `fold_index_flags` / 16.2 R2b `sys.executable` / 16.1 `#r1-space-forms` / 16.4 raw-text `$` rule / d-4 + AC-5c2 |
| r4 b-r4-2, s-r4-2, s-r4-7 (r5 partials) | **closed (3)** | via s-r5-1, b-r5-2 and s-r5-2 above |
| plan-22 b-7 (16.6 has no wave) | **closed** | as s-r5-5 |
| plan-22 b-1 / b-2 / s-6, 16.6 side (hash, rules, row identity) | **closed in 16.6** | R1 `line_hash`, `match_argv`, the 5-column key. The 22.1 side of b-2 is the conflict ([[#b-4]]) |
| DL #b-3 (16.6 inversion), DL #s-1 (merge), DL #m-3 (lossy `stale_seen`) | **closed** | header; R1c; `#r4-lower-bound` + AC-8. DL #m-3 exposes that the marks have no consumer ([[#b-3]]) |

Tally: **r5: 14 closed, 1 partial, 0 open. r4 partials: 3 closed. Cross-plan and DL items: all
closed in 16.6.**

### Plan-22 (r1, 22 findings) {#prior-22}

| id | status | evidence |
|---|---|---|
| b-1 (`moved` key) | **closed** | 22.1 R1 per `(concept, file)` set; the hash is an optional extra; AC-1 two-hit shift plus mutation; AC-2 hash pairing |
| b-2 (no flags) | **partial** | pre-provenance rows are permissive (AC-3, with mutation): closed. Provenance rows go through a Python translation that contradicts 16.6 ([[#b-4]]) |
| b-3 (no row-level replay) | **partial** | 22.2 R3 adds `evidence_remove`/`evidence_repoint`/`entity_rename`; R4 restores by name with an intent log. But the 16.6 sidecar has no log form, so AC-3's "rebuild reproduces the post-apply state" cannot hold for provenance ([[#b-2]]) |
| b-4 (the 48, candidate roots, units) | **partial** | the 48 are kept (d6a); units are stated; the candidate procedure is named. But 22.1a's candidate set is not the probe's, so AC-5 cannot reproduce 476/48/563, and the candidates are not de-duplicated ([[#s-1]]) |
| b-5 (gate on the wrong stores) | **closed** | 22.2 R7: a clone of THIS store; a pre-check; a frozen `query.log` set; a bootstrap CI. Residue [[#m-7]] |
| b-6 (`empty-learned` ≤ 747) | **closed** | 22.1 R2 redefined; AC-6 exact recount; d6c `#why-not-df` |
| b-7 (no wave) | **closed** | 22.1a in Wave 1; `#t8-wave1` chain in `#dependencies` |
| b-8 (live global writes) | **closed** | sandbox in every test strategy; explicit-root refusal (22.2 R8 / AC-11); pytest entities in 22.3; bug-101 logged. Residue [[#s-3]] |
| s-1 (bind / two partitions) | **closed** | 22.2 R6 + AC-8 with mutation |
| s-2 (lossy queue, intent log, re-check) | **closed** | R6 `bounded_steps`, `changed_since_audit`; R4 intent log; AC-9 |
| s-3 (rename collision, memory-only global) | **closed** | R2 merge-on-collision; 22.5 moves the rows, never rewrites them in global; AC-7, 22.5 AC-4 |
| s-4 (learned protection) | **closed** | R5 `protect.source` plus log attribution; AC-6. The global log makes open item 9 empty ([[#ev-facts]]) |
| s-5 (alias canonical) | **closed** | 22.1a `orphan-alias:repairable` by exact name; AC-2 plus a `canonical_name` mutation |
| s-6 (removal primitive) | **closed** | R2 row identity, `remove_evidence`/`repoint_evidence`, purge only when no link; AC-5 |
| s-7 (22.3 AC scope) | **closed** | 22.3 AC-2: TOTAL `unreadable` over a pre-registered set; residuals explained by class; mutation |
| m-1, m-2, m-4, m-6 | **closed (4)** | exact recounts; tick-stopped read-only AC; restore from the manifest; `#interface` |
| m-3 (plan-16 row says prune) | **closed** | the plan-16 16.6 row says "nothing here removes a row". Plan-22's open item 5 is stale ([[#m-3]]) |
| m-5 (plan close with 22.4) | **open** | open item 3 |
| m-7 (ADR "only") | **partial** | `#scope` narrows the wording to policy/class removal; the ADR edit is left open (open item 4) |

DL items touching plan-22:
- **closed:** #b-1 (`stale-subject`, d8a), #b-2 (R5 + d8b), #b-3 (22.1a split, 22.3 R3 rewritten),
  #s-5 (d8g, one verb on both surfaces), #s-7 (restore re-embeds);
- **partial:** #b-4 (22.5 owns the move; the global store is excluded; but "≥ 114" is misread and
  misframed as a lower bound, [[#s-2]]).

Tally: **17 closed, 4 partial, 1 open.**

## New findings {#findings}

### BULLSHIT b-1: 16.6 R2 calls a still-matching row `stale` in three ways: cutoff tokens, path filters applied to an absolute path, and tool errors {#b-1}

**Spec:** 16.6 R2 (re-run `bin` with `match_argv` … `-- <file>` on that ONE file, absolute; `ok`
when `line` is in the output); 16.1 R10 (`match_argv` = every kept MATCH- and CUTOFF-class token);
16.1 R1's keep:match row, which also holds the file-selection tokens (`-r -R --include --exclude
--exclude-dir -d -D`, rg `-g -t --max-depth`).

**What:**
1. **Cutoffs.** `-l` is recorded as `-m 1`. Take a file where row line 2 still matches, and line 1
   is edited so that it matches too. The re-run prints only line 1 (probed), so line 2 is absent
   and the row is `stale`. `-rl` is a habitual agent grep.
2. **Path filters on an absolute path.** BSD grep matches `--exclude` against the WHOLE operand
   path. Probed: `--exclude='*bsdp*'` hits relatively, and prints nothing with rc 1 absolutely. A
   caller's exclude that matches any parent directory name makes every row it taught `stale`.
3. **Tool errors.** A regex the `bin` now rejects gives exit 2 with no output, so the row is
   `stale`. Probed: grep `a\{`, rg `a{` and rg `(`. The causes are a grep or rg upgrade at the
   recorded path, or a MacPorts GNU grep at the same `bin`. R2 maps only "bin missing" and
   "timeout" to `unverifiable`.

**Why it is bullshit:** R2 is named the verifier for plan-22's audit and for R4's `changed` marks.
22.2 R9 removes `stale-line`. So each hole is a deletion of correct knowledge on a re-check, with
nothing in AC-3 able to see it. This is the decay rule, broken through the very fix for b-r5-1.

**Fix:**
- At verify time, keep only the PATTERN-semantics tokens: `-i -y -w -x -F -E -G`, rg
  `-s -S -P -U --multiline-dotall`, and `-a/--text/--binary-files` if wanted. Drop the cutoff and
  file-selection tokens: the file was already selected.
- Name the file as the learner saw it. Run with `cwd` = the learned root and the stored relative
  path. Or, simpler, drop the path filters as above.
- Exit ≥ 2 with no output → `unverifiable` (kept, counted by reason).
- AC-3 rows: `-m 1` with an earlier added match; `--exclude` matching a parent directory; an
  unparseable pattern. Each must verify `ok` or `unverifiable`, never `stale`. Mutation: "pass
  `match_argv` whole" FAILS.

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### BULLSHIT b-2: the sidecar has no `facts.log` form, so a rebuild erases every provenance row and re-opens b-r5-1 through plan-22's permissive reading {#b-2}

**Spec:** 16.6 R1 (DDL in `duckdb_catalog.py`; writer `add_learned_provenance`; no log event);
R1c (survives `replica_merge` only); 22.2 R3/AC-3 ("rebuild reproduces the post-apply state");
22.1 `#r1-verify` (rows without rules get the permissive Python reading).

**What:**
- `rebuild_index_from_log` deletes `catalog.db` and replays `facts.log` only (`store.py:7566`).
  `rmx rebuild-index` and the daemon op `rebuild_index` are production paths.
- After any rebuild, every learned row comes back with no sidecar row. A re-run of R5 marks it all
  `backfill`, `rules_sha=none`.
- That loses `tool`/`dialect`/`match_argv`/`line_hash` for good. 22.1 then verifies those rows
  under the permissive Python reading. A post-16.1 row taught by `grep 'a\|b'` (the learner now
  re-runs BRE) fails literal AND Python-regex. It becomes `stale-line`, and 22.2 removes it.
- r4 measured 56.6% of agent grep patterns with a BRE meta. This is b-r5-1 again, triggered by a
  rebuild.

**Why it is bullshit:** this is the same class as plan-22 r1 #b-3 ("recoverability asserted on a
log that cannot replay it"), now on the provenance table that both plans treat as durable. 22.2
AC-3 cannot detect it, because it compares evidence `(file, line)` and renames, not sidecar rows.

**Fix:**
- A `learned_provenance` log event, keyed by NAME (`linkage`, `c`, `e_kind`, `e`, `file`, `line`,
  `rules_sha` plus columns), written in the same call as `add_learned_provenance`. Both replay
  paths apply it, and 22.2's `evidence_repoint`/`evidence_remove` replays carry it.
- R4's marks stay derived, with no event.
- 16.6 AC: write rows, rebuild on a copy, and the sidecar equals the pre-rebuild sidecar except
  for the marks. Mutation "no event" FAILS.
- 22.2 AC-3 adds "equal sidecar rows".

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### BULLSHIT b-3: the read-time marks have no consumer: plan-22 never reads `stale_seen`, `last_mark` or `last_verified_at` {#b-3}

**Spec:** 16.6 R4 ("`stale_seen` is an input to plan-22's audit"), `#r4-lower-bound` ("consumers
must not read it as exact"), AC-4, AC-7, AC-8; plan-22 22.1, 22.1a, 22.2.

**What:** I searched every plan-22 file. The only mention of a mark is 22.1a R3: "It enqueues NO
`stale_seen` marks". No class, priority, report column or gate reads `stale_seen`, `last_mark` or
`last_verified_at`. 22.1 re-runs the verifier itself. R4 nonetheless builds:
- a read-path enqueue;
- a durable queue registrant;
- a drain with a subprocess pre-step outside the lock;
- three ACs and a printed overflow counter.

All of it feeds only aggregate counts in `rmx learn status`.

**Why it is bullshit:** this is "a safety net with no reader" for the third time:
- 16.6's original;
- plan-17's orphan list (DL #b-5);
- now the marks.

A SKETCHY pattern seen three times escalates. It is also the question the brief asked: plan-22
does not treat `stale_seen` as exact, because it does not treat it at all.

**Fix:** pick one.
- (a) 22.1 consumes the marks: it re-verifies first the rows with `stale_seen > 0` or a
  `last_mark`, and reports `last_verified_at` age per class. 22.1 AC: a marked row is listed with
  its mark.
- (b) R4 shrinks to the counters `rmx learn status` prints, and the sidecar columns are dropped.

Either way, 16.6 R4's "input to plan-22" sentence must name the reading requirement.

rel: contradicts -> [[bsd-decision-log-review-a192ba2]]

### BULLSHIT b-4: 22.1 `#r1-verify` contradicts 16.6 R2, r5 #b-r5-1 and `#t6-fixes`, and 16.6's API cannot give 22.1 the set it classifies on {#b-4}

**Spec:** 22.1 `#r1-verify` ("`evidence_line_matches` … the one matcher, with the pattern first
translated … to Python `re`. No second matcher"), R1 (`unverifiable` = "cannot be translated"),
AC-4; 16.6 R2 (`learned_verify.verify(rows, project_root) -> {key: verdict}`; "runs … in plan-22's
audit"; "Python `re` is NEVER used for these rows").

**What:**
- **Two verifiers for one row,** contradicting each other in both plans' own words. See
  [[#conflict]]. Translations that compile silently but are wrong (`[[:digit:]]`, `\<foo\>`,
  BRE `a+b`) classify `stale-line`, which 22.2 R9 removes.
- **AC-4 cannot tell them apart:** `foo\|bar` passes under both.
- **API mismatch.** 22.1 R1 needs `N`, the current matching LINE SET per `(concept, file)` under
  the row's rules, to decide `moved`/`grown`/`shrunk`. 16.6 R2 returns per-key verdicts only. Its
  "one run per `(file, rules_sha)`" computes `N` and throws it away.

**Why it is bullshit:** a cross-plan contradiction on a deletion path, in which the losing spec
deletes correctly taught rows. 16.6's own open item 1 names it, and plan-22 does not.

**Fix (spec-settleable):**
- 22.1 `#r1-verify` uses 16.6's verifier. Delete "No second matcher" and the translation.
- 16.6 R2 adds `learned_verify.matching_lines(file_abs, rules) -> set[int] | Unverifiable`, which
  `verify` is built on.
- 22.1 AC-4 adds a `[[:digit:]]` row and a `\<foo\>` row, verified `ok`. Mutation "translate to
  Python `re`" FAILS.
- Pre-provenance rows keep the permissive Python reading (safe: [[#ev-verified]], the 0.65.1
  refusal), as long as [[#b-2]] stops new rows from losing provenance.

rel: contradicts -> [[bsd-plan16-spec-review-r5-cd7c923]]

### SKETCHY s-1: 22.1a's candidate set is not the probe's, so AC-5 cannot reproduce 476 / 48 / 563, and identical files count twice {#s-1}

**Spec:** 22.1a R1 ("Candidate roots = `$HOME` … plus every file found by a suffix walk over
`~/github`, `~/claude_tools` and `~/enduris`, the probe's three trees"); AC-5 ("with exclusions
OFF reports the 2026-10-07 split 476 / 48 / 563 … every difference explained by an entity
created or tombstoned after 2026-10-07 … or a file changed since").

**What:**
- The 476/48/563 split is the probe's WALK pass. `$HOME` was a separate first pass: verified@1 =
  362, all under `/Users/tholley`.
- On the log population, 1,337 relative learned files exist as `$HOME/<rel>` OUTSIDE the three
  trees ([[#ev-facts]]). Adding `$HOME` therefore moves some of the 563 into `verified@1`, by a
  difference that AC-5's explanations do not allow. AC-5 fails on correct code, or is passed by
  hand-waving.
- A relative `claude_tools/x` resolves both as `$HOME/claude_tools/x` and as the walk's
  `~/claude_tools/x`. That is ONE file but TWO candidates, so the entity reads `verified@2` and
  becomes `ambiguous:root` (kept forever) unless candidates are de-duplicated by `realpath`.

**Fix:**
- De-duplicate candidates by `realpath`.
- AC-5 reproduces the probe with the probe's candidate set (walk only, exclusions off). It then
  reports the `$HOME`-added split beside it as its own delta, which is the one 22.5/22.3 apply.
- AC: one file reachable both ways resolves `verified@1`.

### SKETCHY s-2: d8c's "≥ 114 forgotten" misreads the probe, 22.5 R1 calls it a lower bound, and the forget bucket includes rows that read correctly today {#s-2}

**Spec:** d8c; plan-22 d-6 and open item 2; 22.5 `#root`, R1 ("the decision log's '≥ 114
forgotten' is a lower bound to compare against").

**What:**
- **The 362 were not verified by project roots.** The "8 registered roots" include
  `/Users/tholley`, which is the global store's own root (launchd `com.refmatrix.daemon.tholley`).
  All 362 verified there and 0 under the 7 project roots ([[#ev-roots]]).
- **So "476 − 362 = 114 under no store root" does not follow.** The forget bucket can be anywhere
  from 0 to 476. "≥ 114" is not a lower bound, and plan-22 open item 2's "can exceed 114" still
  anchors on it.
- **The likely count is far above 114.** In the log population, 89% of `$HOME`-resolvable learned
  files lie under no project root (`Library/`, `lib/python*`, `github/atollogy/*` outside
  `bdep`).
- **Those rows read correctly TODAY.** `grep_evidence` resolves global rows against `$HOME`, so
  they are not bug-086's symptom (exists@0 = 695). Forgetting them repairs nothing.

**Why it matters:** the user's knowing consent (d8c) was given on a number derived from a
misreading. 22.5 R1 does show the real counts before the apply, which is the saving grace, so this
is SKETCHY, not BULLSHIT.

**Fix:**
- Delete "lower bound" from 22.5 R1 and plan-22 open item 2. Replace it with the [[#ev-roots]]
  fact.
- 22.5 R1's dry run adds a bucket, `forget (no owner) / readable today`.
- The user re-decides ([[#user-decisions]]).

### SKETCHY s-3: several ACs need live catalogs, which the 23.0 sandbox forbids {#s-3}

**Spec:** 22.1a AC-5/6/7 and test strategy ("AC-5..7 run on clones under the scratch dir");
22.1 AC-6 ("on a clone of this repo's catalog"); 16.6 AC-5 ("the global copy's rows have `root`
NULL"); 23.0 guard ("fails any test touching `~/.refmatrix` or a registered live store").

**What:**
- Making the clone reads the live store, which a suite test inside the guard cannot do.
- The counts drift, so these ACs are not deterministic CI tests.
- An APFS clone of a writer slot (`catalog.A/B.duckdb`) taken under a live daemon can miss
  WAL-resident commits.

**Fix:**
- Split each such AC into a sandbox test on a fixture store, plus an OPERATOR step that clones
  `catalog.read.duckdb` (the lock-free snapshot) or a daemon-produced snapshot. The step's output
  is logged under `workflow/review-output/` and cited in the summary.
- Say so in each test strategy.

### SKETCHY s-4: 16.2 AC-1 commits real transcript greps to the public repo with no scrubber {#s-4}

**Spec:** 16.2 AC-1 ("`tests/fixtures/grep_differential.txt`: at least 40 invocations replayed
from real transcript greps").

**What:** transcript greps carry patterns and paths from other work trees, such as
`~/github/atollogy/...`. d8f and memory `feedback_no_raw_prompts_in_public_repo` say: commit a hash
plus a REDACTED fixture. 16.2 says neither.

**Fix:** the raw extraction goes to a gitignored path, and its hash is committed. The committed
fixture goes through a scrubber that rewrites paths onto the sandbox fixture tree and replaces
non-repo patterns. Add a test that greps the fixture for `/Users/` and `atollogy`.

rel: contradicts -> [[feedback_no_raw_prompts_in_public_repo]]

### SKETCHY s-5: plan-22's repairs change the sidecar's key columns, and neither plan says who updates them {#s-5}

**Spec:** 16.6 R1 (PK includes `file` and `line`); 22.2 R2 `repoint_evidence` ("updates `line`"),
`rename_entity` (changes `entity_id` on merge), AC-1 ("sidecar row intact"); 22.5 R2.2 (rewrites
`file` relative to the target root).

**What:**
- Every repair changes a column of the sidecar key, yet only `remove_evidence` says the sidecar
  follows.
- A re-point that leaves the sidecar on the old line orphans it. R1c then counts the row
  `orphaned_provenance` at the next merge, and the repaired row reads as pre-provenance (see
  [[#b-2]]'s consequence).
- AC-1's "intact" can pass with a stale key.

**Fix:**
- Each primitive updates the sidecar key in the same transaction.
- Each `facts.log` event carries the sidecar change ([[#b-2]]).
- 22.2 AC-1: after a re-point, the sidecar row joins the evidence row on all five columns.
- 22.5 AC-3: imported sidecar rows join in the target.

### SKETCHY s-6: d8d's mark-and-filter predicate has no owner, and plan-22 only lists it {#s-6}

**Spec:** plan-22 open item 1; d8d ("every `query.log` / `recall-events.jsonl` reader skips rows
whose cwd or root is a pytest temp dir (one shared predicate)").

**What:** a decided behaviour with no task: rule 9a. Plan-22 rightly disowns it, but 22.2 R7's
gate already implements the predicate locally ("excluding rows whose cwd or root is a pytest temp
dir"). So the first copy is about to be written without the shared one.

**Fix:** the orchestrator assigns it. 23.0 owns the predicate (it "prevents new ones" and already
defines the pytest tmp shape). 22.2 R7 and the plan-21/19 readers import it. This is not a user
decision.

### MEH m-1: plan-16 open item 3 rests on a false premise, and the `python` dialect has no writer {#m-1}

- `#t6-fixes` names no dialect enum ("provenance carries tool + dialect + line hash"). 16.6 R1's
  "the decision log's four" and the plan's open item 3 are wrong.
- No writer produces `dialect=python` (16.1 R10 maps to `bre`/`ere`/`fixed`/`rust`/`pcre2`/
  `mixed`; the backstop writes `fixed`). So 16.6 R2's `python` branch is dead by spec.

**Fix:** drop `python` and its branch, and close open item 3.

### MEH m-2: plan-16 open item 4 is stale, and two plan-of-plans rows lag {#m-2}

- `plan-of-plans.md:47` already lists the 16.6 slice in Wave 1, and `plan-review-2026-10-07#order`
  is marked superseded there.
- Row 16 still says "+ tasks 16.7-16.10", which moved to plan-21.
- Row 22's task count says "yes (4)", but there are 6 specs.

**Fix:** close the item and fix both rows.

### MEH m-3: three plan-22 open items are already settled {#m-3}

- **Item 5:** the plan-16 16.6 row says "nothing here removes a row".
- **Item 7:** 19.4 R5 sets the `stale` subject mark.
- **Item 9:** every global protect event on the in-scope entities follows an `entity` event
  ([[#ev-facts]]). The `unknown` bucket is empty on the store 22.3 applies to, and "unknown =
  asserted" is the safe default for project stores.

### MEH m-4: vocabulary drift across the two plans {#m-4}

- `gone-file` (16.6 R2/R4) versus `missing-file` (22.1a).
- `stale` (16.6 R2) versus `stale-line` (22.1).
- `unverifiable` has three definitions:
  - no rules / bin missing / timeout (16.6);
  - "cannot be translated" (22.1);
  - plus [[#b-1]]'s exit-2 case.
- 16.6 `#split` cites a nonexistent "22.1b".
- 16.6 R1 says `root` is "NULL in the global store until plan-22's 22.3", but 22.3 never sets it.
  22.5 moves the rows, and its import should set `root` to the target.

### MEH m-5: 22.1 does not say which reading defines a set when a row has several {#m-5}

A row can carry sidecar readings `none` plus a recorded one, or `-i` plus plain. 16.6 R2 says "ok
when ANY reading passes". 22.1's `N` is undefined across readings. State that `N` is the union over
the row's readings, with `none` read permissively, and add an AC.

### MEH m-6: 16.6 AC-6's count equality fails on correct code {#m-6}

Until 16.1, `add_evidence` is an unconditional INSERT, so a re-teach adds duplicate evidence rows.
Under `ON CONFLICT DO NOTHING` they share one sidecar row. "The same number of `legacy-writer`
sidecar rows" must therefore count DISTINCT evidence identities.

### MEH m-7: 22.2 R7's displacement is positive by construction whenever a candidate was retrieved {#m-7}

"1 − Jaccard@10 after removing candidates from the baseline list" compares 9 survivors against a
new top-10 that promoted the 11th result. Every query that retrieved a candidate therefore shows
displacement, and the gate refuses any candidate that is ever retrieved. Compare equal-length
lists (the baseline's top-10 non-candidates against the new top-10), or state that refusing is
the intent.

### MEH m-8: the global store's "root" has two spellings {#m-8}

- 22.3 R3 uses `--root ~/.refmatrix`, while 22.5 R1 says the global store's project root is
  `$HOME`.
- The code has two predicates:
  - `discovery.is_global_root`: `user_home()`;
  - `store.is_memory_only_root`: `~/.refmatrix`.

22.2 R8's "named root must equal the resolved root of the daemon" must say which spelling it
compares, or 22.3's own command can be refused.

## Open-after-revision items, classified {#open-items}

### Plan-16 {#open-16}

| item | real user decision? | why |
|---|---|---|
| 1 two verifiers | **no, the specs settle it** | r5 and `#t6-fixes` already chose the re-run; see [[#b-4]] |
| 2 `legacy-writer` vs re-backfill | **no** | R1b is strictly more informative (`learned_at`, `root`) and closes the window. d6d moved the RULE-bearing write to 16.1, not every write. Keep R1b; fix AC-6 ([[#m-6]]) |
| 3 widened dialect list | **no** | its premise is false; drop `python` ([[#m-1]]) |
| 4 wave lists | **no** | already done in plan-of-plans ([[#m-2]]) |

### Plan-22 {#open-22}

| item | real user decision? | why |
|---|---|---|
| 1 owner of d8d | **orchestrator, not the user** | assign it to 23.0 ([[#s-6]]) |
| 2 the 362 / "≥ 114" | **YES** | the split is computable (22.5 R1), but forgetting rows that read correctly today is a policy the user consented to on a misread number ([[#s-2]]) |
| 3 plan close with 22.4 | **light user call** | the spec can propose "complete with 22.4 transferred to the helix plan" |
| 4 ADR-0004 "only" | **YES** | an ADR edit (and whether `prune-noise --drop` survives the decay rule) |
| 5 plan-16 row | **no** | already closed ([[#m-3]]) |
| 6 where "ambiguous" persists | **no** | manifest plus re-audit is enough, or a sidecar column agreed with plan-16 |
| 7 plan-19's stale mark | **no** | 19.4 R5 ([[#m-3]]) |
| 8 walk exclusions | **user confirms, non-blocking** | AC-5 reports both splits; the user sees the delta |
| 9 protections with no source | **no** | empty on the global store; "unknown = asserted" is the safe default ([[#m-3]]) |

## User decisions needed {#user-decisions}

1. **(s-2) The global rows that read correctly today but lie under no project store.** These are
   the 362 `$HOME`-relative rows and any of the 476 outside project roots. The log population puts
   it at about 89% of the resolvable ones. Choose one:
   - (a) forget them, audited and restorable (d8c as written);
   - (b) leave them in global untouched, because they are not bug-086's symptom and the 0.65.0
     guard blocks NEW tracking, not existing evidence;
   - (c) decide after 22.5 R1's dry-run counts.
2. **ADR-0004 wording** (plan-22 open item 4).
3. **Plan-22 close with 22.4 deferred** (open item 3).

## Verdict {#verdict}

**Plan-16: NEEDS-REVISION.**
- 16.1, 16.3, 16.4 and 16.5 are approvable: every r5 item is closed, and the click and BSD facts
  were re-probed.
- 16.2 needs the scrubber ([[#s-4]]).
- 16.6 needs [[#b-1]], [[#b-2]] and [[#b-3]].

**Plan-22: NEEDS-REVISION.**
- 22.1 must use 16.6's verifier ([[#b-4]], [[#m-5]]).
- 22.1a needs [[#s-1]].
- 22.2 needs [[#s-5]] and [[#b-2]]'s AC.
- 22.5 needs [[#s-2]].
- Several ACs need the operator/sandbox split ([[#s-3]]).
- 22.3 and 22.4 hold as written (modulo [[#m-8]]).

| | prior closed | partial | open | new B | new S | new M |
|---|---|---|---|---|---|---|
| plan-16 | 14 r5 + 3 r4 + cross/DL items | 1 (b-r5-1) | 0 | 3 (b-1, b-2, b-3) | 1 (s-4) | 3 (m-1, m-2, m-6) |
| plan-22 | 17 | 4 (b-2, b-3, b-4, m-7) | 1 (m-5) | 1 (b-4) | 3 (s-1, s-2, s-5) | 4 (m-3, m-5, m-7, m-8) |
| both | | | | | 2 (s-3, s-6) | 1 (m-4) |

**18 new findings: 4 BULLSHIT, 6 SKETCHY, 8 MEH.**

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 32dde06 (SPEC re-review: plan-16 rev 6 tasks 16.1-16.6 + plan-22 22.1/22.1a/22.2/22.3/22.4/22.5, pre-implementation; written 2026-10-14T12:45-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 18 new (4B/6S/8M); plan-16 r5: 14 closed, 1 partial (b-r5-1); plan-22 r1: 17 closed, 4 partial, 1 open | [[bsd-plan16-22-spec-rereview-32dde06]]: cross-plan conflict adjudicated for 16.6 R2 (re-run the recorded tool, per r5 + #t6-fixes); 22.1's Python translation contradicts it (probed: `[[:digit:]]`, `\<foo\>`, BRE `a+b` compile in re and mis-match) and 16.6's API returns verdicts, not the line set 22.1 needs. BULLSHIT: 16.6 R2 calls matching rows stale (`-m 1` cutoff, BSD `--exclude` matched against the absolute path, exit-2 parse errors; all probed); sidecar has no facts.log event so rebuild_index_from_log erases provenance and re-opens b-r5-1; R4 marks have no plan-22 consumer (third "net with no reader"). SKETCHY: 22.1a $HOME+walk candidates cannot reproduce the probe's 476/48/563 and double-count one file; d8c's "≥114" misreads the probe (the 362 verified under /Users/tholley = the global store's own launchd root, 0 under the 7 project roots; log proxy: 89% of $HOME-resolvable learned files lie under no project root, all readable today); live-clone ACs vs 23.0 guard; 16.2 fixture of real transcript greps unscrubbed (d8f); repairs change sidecar key columns; d8d predicate unowned. No code, no live-store opens, no suite; facts.log parsed read-only. |
```

last_run.log line:

```
2026-10-14T12:45:19-0700 commit=32dde06 verdict=DIRTY findings=18 (4B/6S/8M) report=2026-10-14-1245-plan16-22-spec-rereview-verifier-conflict-and-misread-probe-32dde06.md
```

IMPRESSIONS.md bullets:

```
- plan-16/22 re-review (32dde06): "re-run the caller's tool" is the right verifier, but a re-run is only as faithful as the tokens it replays: cutoff tokens (-m 1 from -l), path filters matched against a now-absolute path (BSD --exclude), and exit 2 all turn a matching row into "stale". Review a re-run verifier for what it must DROP, not only what it keeps.
- A provenance table outside facts.log is erased by rebuild_index_from_log; check every new catalog table for a log event before believing "durable".
- Read a probe's "by root" as "relative to which base", not "contained in which store": the 8 registered roots included the global store's own $HOME, and a decision (d8c) was taken on the misreading.
```
