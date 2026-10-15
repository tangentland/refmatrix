---
gmd: "0.1"
id: bsd-plan16-22-spec-rereview-r3-6091648
title: "plan-16 + plan-22 spec re-review r3: the verifier contract is implementable and 22.1/22.1a carry no matcher, but 22.1a's probe-reproduction gate cannot pass (the probe's walk had exclusions), 22.1's grown/shrunk deletes shifted rows, the re-run ignores locale, and the approved ADR-0004 amendment hands plan-22 entry points it disowns"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-rereview-r3-16.1-16.6-22.1-22.5
round: 7 (plan-16) / 3 (plan-22)
tags: [bsd, audit, spec-review, grep, provenance, removal, repair, bug-086, global-store, cross-plan, adr-0004]
---

# ch-bsd spec re-review r3: plan-16 (16.1-16.6) and plan-22 (22.1, 22.1a, 22.2-22.5) {#root}

**Commit reviewed:** `6091648`, branch `wave0-spec-reviews`. **Written:** 2026-10-14T13:26-0700.
`src/` is unchanged since `b1c4324`. While this review ran, HEAD moved to `097e7b1` (`3021cd6`
approved the ADR-0004 amendment as d9k and folded it into `#rule-no-delete`; `097e7b1` added the
`#t10-waves` list). Neither commit touches a plan-16 or plan-22 file. Where approval changes a
finding, the finding says so ([[#b-3]]).

**Scope:** plan-16 and its tasks 16.1-16.6 (revision tables `#rev-round-2`), plan-22 and its tasks
22.1, 22.1a, 22.2, 22.3, 22.4, 22.5 (`#rev-round-2`), the decision log `#t9`, and the ADR-0004
amendment `#amend-2026-10-14`. The prior review is [[bsd-plan16-22-spec-rereview-32dde06]].

**Method (all read-only):**
- I checked each revision-table row against the spec text and each cited code fact against HEAD
  (`store.py` 759/786/816/5692/5905/6976/7460/7566, `daemon.py` 4295/4795, `context.py` 893-935,
  `cli.py` 6160-6180, `discovery.py`, `taxonomy.user_home`, `duckdb_catalog.py:162`, `sync.py`
  195-245).
- I probed BSD grep 2.6.0 and rg 15.1.0 in throwaway `mktemp -d` dirs, using 16.6 R2's exact
  canonical forms, with `od -c` on the output. I also probed `LC_ALL=C` against `en_US.UTF-8`, and
  `\x0c` line numbering. The dirs were deleted afterwards.
- I parsed the global and refmatrix `facts.log` read-only, using `python3 -I` scripts in the
  scratchpad. The per-row permissive check used `.venv-eval`'s pure functions (`terms`,
  `evidence_line_matches`, `identifier_variant_regex`) on the files as they are on disk. It opened
  no `Store` and touched no socket.
- I counted files with `find` over `~/github ~/claude_tools ~/enduris`.
- I read the launchd plists.

I made no `rmx` call, opened no catalog, ran no suite, and edited no source, test, plan or ledger
file.

rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index#amend-2026-10-14]]

## Live evidence {#evidence}

### The verifier contract, probed {#ev-contract}

| probe | result | what it means for 16.6 R2 |
|---|---|---|
| `grep -nH --null -e 'zzz\|alp' -- /abs/a.txt` | `/abs/a.txt\0` `1:alpha`, rc 0 | the `file\0LINE:` parse works; BRE is re-run faithfully |
| `rg -nH --null --no-heading --color never --no-config -e alp -- /abs/a.txt` | the same bytes, rc 0 | one parser serves both tools |
| `grep -y …`, `grep -U …` | `-y` is `-i`; `-U` prints text lines normally | the keep list is right |
| `grep -e -r -nH --null -- f` | matches the line `-r here` | a value token must be consumed by its flag ([[#s-2]]) |
| grep `a\{` / rg `a{` | exit 2, no stdout | maps to `tool-error` as specified |
| `grep -P` (BSD) | exit 2, `invalid option` | 16.1 kills `-P`, so no grep row carries it |
| **`LC_ALL=C` vs `en_US.UTF-8`, BSD grep** | `a.b` on `a—b`: C → no match, UTF-8 → match. `-i café` on `CAFÉ`: C → no match. `na[[:alpha:]]ve` on `naïve`: C → no match. `env -i` behaves as C. rg matches in both locales | **locale is a pattern-semantics input that is not recorded** ([[#s-1]]) |
| launchd plists `com.refmatrix.daemon.*` | `EnvironmentVariables` carries only `PATH` (no `LANG`/`LC_*`) | the daemon, where R4's drain and plan-22's audit run, uses the C locale. The agent shell is `en_US.UTF-8` |
| file `one\x0ctwo\nthree target` | grep says line 2; Python `str.splitlines()` says line 3 | line numbering must be defined by splitting on `\n` ([[#m-2]]) |

**Verdict on implementability.** `matching_lines`, `verify_argv`, the exit-status map and
`UNVERIFIABLE_REASONS` can all be built as specified for BSD grep and rg. The canonical tails parse
on both. AC-3 a-g are passable, and they FAIL under their named mutations (`-m 1` replayed whole
leaves the stray `1` as an operand, so rc 2 → `tool-error` ≠ `ok`). The contract is right in shape.
Its holes are three inputs it does not record or define:
- the locale ([[#s-1]]);
- short-flag clusters and value arity ([[#s-2]]);
- line splitting ([[#m-2]]).

### Do 22.1 / 22.1a call it with no matcher of their own? {#ev-no-matcher}

**Yes.**
- 22.1 `#r1-verify` names the exact calls (`matching_lines`, `permissive_matching_lines`,
  `hash_line`), deletes the translation, and builds `N` from line sets. AC-4 has the
  Python-`re` mutation and a call-site assertion.
- 22.1a's `orphan-root` verification calls `permissive_matching_lines`. Its `missing-file`,
  `duplicate` and `orphan-alias` classes need no matcher.
- 22.5 step 3 reuses 22.1a's reading.

The remaining defects are in what the callers DO with the verifier's answers ([[#b-2]], [[#s-3]]).

### The probe's walk was not exclusion-free {#ev-walk}

The probe log reads: `walked 972849 files in 14.4s`. The script was never committed, and memory
`project_global_relative_rows_repair` says only "suffix-match … then VERIFY that the recorded line
holds the learned pattern". File counts over `~/github ~/claude_tools ~/enduris` today:

| walk rule | files today |
|---|---|
| no exclusions (22.1a AC-5b "exclusions OFF") | **2,178,771** |
| 22.1a's exclusion list ON | 648,666 |
| prune `.git`, `.venv*`, `node_modules` | 1,216,714 |
| prune `.git` only | 1,781,055 |
| prune hidden DIRS only | 1,453,589 |
| prune every hidden entry (files and dirs), `node_modules`, `__pycache__` | **974,684** (+1,835 vs the probe, a week of churn) |

So the probe walked roughly "skip dot-entries, `node_modules`, `__pycache__`". Neither of 22.1a's
two walks is that ([[#b-1]]).

### Learned rows the permissive reading cannot judge {#ev-subset}

Every distinct `(file, line, pattern)` taught in this repo's `facts.log` (31,608), checked against
the file as it is today:

| outcome | rows |
|---|---|
| permissive `ok` | 18,659 |
| permissive `stale-line` | 7,131 |
| missing file | 4,245 |
| **`permissive-subset` (the pattern holds `\|` `\(` `\)` `\{` `\}` `\<` `\>` `[[:` `\p{`)** | **1,511 (4.8%)** |
| out of range | 52 |
| multi-term context-backstop shape, stale only under the full-ref reading | 10 (negligible; no finding) |

- **Global log:** 69 of 495 `query/*` concepts are in the subset (181 evidence events). Examples:
  `query/^./tools/\|^./docs/gmd/` (2026-09-12, before 0.65.1) and
  `query/by[[:space:]]+group_id|…` (2026-09-16, AFTER 0.65.1, because the refusal at
  `cli.py:6168-6178` covers `\[|(){}]` in substring mode only, never POSIX classes or `-E`
  escapes).
- **Relative global learned entities in the log:** 26 of 2,999 have ONLY subset patterns.

### Learned rows already removed outside plan-22 {#ev-sync-purge}

- **The purge paths.** `purge_entity` (`store.py:5692`) ignores `protected`. It deletes the entity
  and its links, and leaves its `linkage_evidence` rows behind (the table has no FK,
  `duckdb_catalog.py:162`). `vacuum` step 3 later deletes those orphans with no `facts.log` event
  (`store.py:6993`).
- **Sync calls `purge_path` in three cases** (`sync.py:204-242`):
  - on an ignored path;
  - on a missing path;
  - on every changed GMD `.md` that has a `doc` entity named by its RELPATH. That is exactly the
    name the learner gives a `.md` hit (`daemon.py:4295`: `kind="doc"`, `name=rel`).
- **This repo's `facts.log`:**
  - 710 entities carry learned evidence, and 279 of them are `.md` files;
  - **241 of those are GMD documents today**;
  - 26 learned entities were tombstoned 47 times, with 55 `unlink` events of `query/*` mentions.
    The top ones are `task-16.6-learned-row-validation.md` (7), `task-21.1…` (5) and
    `task-22.2…` (3).

## Prior findings: status {#prior-status}

### From the 32dde06 re-review, plan-16 side {#prior-16}

| id | status | evidence |
|---|---|---|
| b-1 (three false-stale holes) | **closed** | 16.6 [[task-16.6-learned-row-validation#r2-argv]] token filter (cutoffs and file selection dropped, per tool); exit map (`tool-error`); AC-3 d/e/f with mutations. Probed: the forms parse, and `a\{`/`a{` exit 2. New, separate holes are [[#s-1]] and [[#s-2]] |
| b-2 (sidecar has no `facts.log` form) | **closed** | R1d `learned_provenance` / `learned_provenance_move`, both replay paths, `marks_reset`; 16.1 R10 logs it; 22.2 AC-3 sidecar equality. Residue in [[#m-1]] |
| b-3 (marks have no reader) | **closed** | R4 `#r4-reader` (option a); 22.1 `#r1-marks` (order, manifest listing, age per class, never decides a class); AC-4c with two mutations |
| b-4 (two verifiers; line-set API) | **closed** | R2 contract (`Rules`, `matching_lines`, `permissive_matching_lines`, `verify`, `hash_line`, `UNVERIFIABLE_REASONS`); 22.1 calls it ([[#ev-no-matcher]]) |
| s-4 (16.2 fixture unscrubbed) | **closed** | 16.2 `#ac-1-fixture`: raw extraction gitignored, sha256 committed, scrubber, privacy denylist test plus mutation |
| m-1 (dialect premise, `python` branch) | **closed** | R1 enum = 16.1 R10's; no `python` branch |
| m-2 (plan-of-plans rows) | **partial** | row 22 now says "yes (6)". Row 16's last cell still reads "+ tasks 16.7-16.10 for agent `rmx context` usage", and its Tasks cell says "no" although 6 specs exist ([[#m-6]]) |
| m-6 (AC-6 count) | **closed** | AC-6 counts DISTINCT evidence identities |
| r5 b-r5-1 (partial at 32dde06) | **closed** | through b-1, b-2 and b-4 above |

### From the 32dde06 re-review, shared items {#prior-shared}

| id | status | evidence |
|---|---|---|
| s-3 (census ACs on live clones) | **closed** | 16.6 AC-5a/5b, 22.1 AC-6a/6b, 22.1a AC-5/6/7 a/b, 22.3 R1: sandbox tests gate; operator censuses on a `cp` of `catalog.read.duckdb`, logged. Residue in [[#m-5]] |
| s-6 (d8d predicate unowned) | **closed** | `#t9-fixes`: 21.1 owns `telemetry.row_provenance`; 22.2 R7 calls it with `reader_root` = the original root; AC-10b plus mutation |
| m-4 (vocabulary) | **partial** | `stale-line`/`missing-file`, `UNVERIFIABLE_REASONS` shared; "22.1b" gone; `root` setter = 22.5. Residue: `out-of-range` still has two predicates ([[#m-3]]) |

### From the 32dde06 re-review and r1, plan-22 side {#prior-22}

| id | status | evidence |
|---|---|---|
| b-4 (22.1 Python translation) | **closed** | see [[#ev-no-matcher]] |
| s-1 (candidate set not the probe's) | **partial → escalated** | the realpath de-dup and the dropped `$HOME` candidate are right (AC-5a with three mutations). But "the probe's set = the walk with exclusions OFF" is false ([[#ev-walk]]), and so is the reproduction gate ([[#b-1]]). My 32dde06 fix text said "walk only, exclusions off" without checking the probe's file count: that error is mine |
| s-2 (d8c "≥ 114" misread) | **closed** | d9b; 22.5 `#root` states the misreading; R1 buckets 2/3 held with `no_owner_ruling: pending`; AC-1/1b with mutations; 22.1a `orphan-root:home-readable`. Residue in [[#m-4]] |
| s-5 (repairs change sidecar keys) | **closed** | 22.2 R2 "Owner of the sidecar's key columns"; AC-1 join on all five columns plus mutation; AC-7; 22.5 step 2 `learned_import` plus AC-3 |
| m-3 (open items already settled) | **closed** | plan-22 `#open-after-revision` 5/7/9 settled |
| m-5 (`N` across readings) | **closed in text** | 22.1 R1 union rule, partial-`Unverifiable` rule. Its AC cannot fail, see [[#s-4]] |
| m-7 (displacement by construction) | **closed** | 22.2 R7 equal-length lists; AC-10 passing case plus mutation |
| m-8 (two root spellings) | **closed** | 22.2 R8. Verified: `discovery.is_global_root` compares to `taxonomy.user_home()` = `~/.refmatrix` (honours `RMX_HOME`); AC-11 |
| r1 b-2 / r1 b-3 (partials) | **closed** | through b-4 / b-2 above |
| r1 b-4 (the 48, candidates, units) | **partial** | as s-1 |
| r1 m-5 (plan close with 22.4) | **closed** | d9j; 22.4 hand-over note |
| r1 m-7 (ADR "only") | **partial** | the amendment was drafted, then APPROVED at `3021cd6`. Plan-22's `#scope` now contradicts it ([[#b-3]]) |

**Tallies:**
- plan-16: 7 closed, 1 partial (m-2);
- shared: 2 closed, 1 partial (m-4);
- plan-22: 10 closed, 3 partial (s-1 escalated, r1 b-4, r1 m-7), 0 open.

## New findings {#findings}

### BULLSHIT b-1: 22.1a AC-5b's reproduction gate cannot pass on correct code, and it blocks 22.5 and 22.3 {#b-1}

**Spec:** 22.1a R1 ("Candidate set = the probe's, exactly … exclusions … OFF for the probe
reproduction"); AC-5b ("With exclusions OFF the audit reports the 2026-10-07 split 476 / 48 / 563 …
every difference is listed by entity with its cause: created or tombstoned after 2026-10-07 … or a
file changed since … An unexplained difference fails the census and blocks 22.5/22.3").

**What:**
- **The walk.** The probe walked 972,849 files. The "OFF" walk is 2,178,771 files today, and the
  "ON" walk is 648,666 ([[#ev-walk]]). Both differ from the probe by walk rule, not by churn.
  - The OFF walk adds `.git/`, `.venv*/`, `node_modules/` and `.claude/worktrees/` copies. Each
    copy adds suffix candidates: a worktree twin of `claude_tools/x` turns `verified@1` into
    `verified@2`.
  - The ON walk drops whole trees the probe kept, such as bdep `_frameworks_and_libraries`.
  - The only rule that reproduces 972,849 (974,684 today) prunes EVERY hidden entry plus
    `node_modules` and `__pycache__`. Neither list in the spec is that rule.
- **The verification rule.** The probe "verified the recorded line holds the learned pattern"
  under an unrecorded rule. 22.1a uses the permissive reading, which is case-insensitive, regex,
  identifier variants, and `Unverifiable` on the subset. Every verification difference is
  therefore "unexplained" under AC-5b's two allowed causes.
- So the census fails on a correct implementation and blocks 22.5 and 22.3, which is the bug-086
  repair. Or it passes by hand-waving, and then the gate is decoration.

**Why it is bullshit:** a blocking gate that is not satisfiable by the spec's own procedure. It
was introduced by answering 32dde06 s-1 with an unverified premise, and that premise was mine.

**Fix (spec-settleable):**
- Name the probe's walk as measured: prune every name starting with `.`, plus `node_modules` and
  `__pycache__`, with `followlinks=False`. Record the walk's file count in the census and require
  it within a stated churn tolerance of 972,849.
- Name the probe's verification as unrecorded. The census reports per-entity differences between
  the reproduction (probe walk, permissive reading) and the probe's split under a THIRD allowed
  cause, "verification rule differs", listed by entity. It gates only on those lists being
  complete, never on equality.
- The applied split (22.1a's exclusion list) is reported beside it unchanged.
- Recover the probe script if it exists in a transcript, and commit it under `eval/` or
  `workflow/review-output/`.

rel: contradicts -> [[bsd-plan16-22-spec-rereview-32dde06]]

### BULLSHIT b-2: 22.1's `grown`/`shrunk` has no rule for a shift, so an edit that shifts lines and changes the hit count removes correctly taught rows, and AC-5's own fixture shifts {#b-2}

**Spec:** 22.1 R1 (`grown`/`shrunk`: "Lines of `O` still in `N` stay; lines of `O` with no match
anywhere in the file are `stale-line` rows; new lines of `N` are REPORTED"; `stale-line`: "the
pattern matches nowhere in the file"); AC-5 ("Deleting one of three hit lines yields `shrunk` with
exactly one `stale-line` row"); 22.2 R9 (`stale-line` removed).

**What:** take `O = {10, 20, 30}`. Delete line 20, and the third hit shifts to 29, so
`N = {10, 29}`. Rows 20 and 30 are both outside `N`, while the pattern still matches in the file.
R1 has two readings, and neither works:
- **(a) "∉ N → `stale-line`".** Both rows are removed, so AC-5 sees 2, not 1. A pure shift plus
  one added hit (an import line plus a new use, the commonest edit) removes EVERY row of the set.
- **(b) "`stale-line` only when the pattern matches nowhere".** Both rows are unclassified, and
  AC-5 sees 0.

AC-5 can pass only if "deleting" means blanking a line in place, which is not how files change.
Reading (a) is the one an implementer gets from "with no match anywhere", read per row. 22.2 R9
then deletes knowledge whose text only moved, against the user's "don't delete moves, repair them".

**Fix:**
- Generalise `moved`'s pairing to every set. Pair `O∖N` with `N∖O` by hash when the rows carry
  one, else in line order.
- Leftover `O` rows (`|O| > |N|`) are `stale-line`. Leftover `N` lines are reported.
- A hashed row whose hash appears on no line is `stale-line` regardless.
- AC-5 uses real deletion and insertion with a shift:
  - delete one of three lines → one re-point, one `stale-line`, 0 ambiguous;
  - insert a line at the top plus one new hit → two re-points, one reported line, 0 removed.
- Mutation "∉ N → `stale-line`" FAILS it.

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### BULLSHIT b-3: the APPROVED ADR-0004 amendment makes `forget` and `memory bulk-forget` entry points to plan-22, plan-22 disowns them, and 22.2's manifest could not restore what they remove {#b-3}

**Spec:** ADR-0004 `#amend-2026-10-14` item 3, folded into `#rule-no-delete` at `3021cd6` (d9k):
"`forget`/`memory bulk-forget` are entry points to that path … they build the manifest and require
the confirm"; "`untrack` and `prune-noise --drop` … each prints what it removes and writes the same
manifest form". Plan-22 `#scope` (at HEAD): those commands are "not absorbed here … That amendment
is PENDING". Plan-22 `#open-after-revision` 4: "amendment PENDING". 22.2 R4: the intent record
holds "evidence rows …, sidecar rows, link weights, entity `protected`/`noise`, whether a vector
existed". `#t10-waves` Wave 4: "Draft the ADR-0004 helix plan: inherits … the approved amendment".

**What:**
- **No task owns the approved rule.** No plan-22 task turns `forget` or `memory bulk-forget` into
  a manifest builder. `removal_audit` emits only audit CLASSES, with no selector source. No task
  makes `untrack` or `prune-noise --drop` write "the same manifest form". The only pointer is a
  not-yet-written Wave-4 helix plan.
- **22.2's restore cannot carry them.** R4 records neither memory bodies (`memory_content`) nor
  entity `path`/`tldr`/`meta`. A `memory bulk-forget` routed through 22.2 is therefore not
  restorable, which contradicts the amendment's own "restore". 22.2 AC-4 compares no path, so a
  restored learned file entity without its `path` passes.
- **At `6091648` this was a user decision; at `097e7b1` it is in force.** Plan-22 now contradicts
  an approved ADR rule on who owns knowledge removal.

**Why it is bullshit:** rule 9a. A decided, in-force behaviour has no concrete near-term task, and
the plan the ADR names disowns it in writing.

**Fix:**
- Plan-22 `#scope` and open item 4 cite d9k.
- Add a task, 22.6 (Wave 1 or 2), "selector entry points":
  - `removal_audit --selector` builds a plan from `forget_by_selector`'s and
    `bulk_forget_memories`' selectors;
  - `rmx forget` and `rmx memory bulk-forget` print the manifest and require `--confirm`;
  - the intent record gains `memory_content` (body, mtype, tags, metadata) and entity
    `path`/`tldr`/`meta`;
  - AC-4 compares them.
- Name an owner for the `untrack`/`prune-noise --drop` manifest form, either 22.6 or a plan-17
  step.

rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]

### SKETCHY s-1: the re-run verifier does not record or pin the locale, so the daemon (C locale) calls UTF-8-taught rows `stale-line` {#s-1}

**Spec:** 16.6 R1 (`Rules`: `tool`, `bin`, `dialect`, `match_argv`, `pattern`), R2 ("re-runs `bin`
… with `stdin=/dev/null`, `cwd` = the file's directory"), R4 (drain pre-step in the daemon); 16.1
R0/R1 (the learner execs `bin` in the caller's environment); 22.1 (the audit is a daemon op).

**What:** BSD grep's `.`, `-i`, `-w` and POSIX classes depend on `LC_CTYPE` ([[#ev-contract]]).
- The learner runs in the agent's `en_US.UTF-8`, inherited from the shim or the hook.
- The verifier runs in the launchd daemon, whose plists set only `PATH`, so it runs in C.
- Probed: `a.b` on `a—b`, `-i café` on `CAFÉ`, and `na[[:alpha:]]ve` on `naïve` all match at learn
  time and miss at verify time. They become `stale-line`, and 22.2 R9 removes them.
- Em-dashes alone are pervasive in this repo's docs.
- rg is unaffected, and so are the context backstop's rows (both sides are the daemon).

This is the same class as 32dde06 b-1: the re-run replays fewer inputs than the original run.

**Fix:**
- 16.1 R10 records the learner's effective `LC_ALL`/`LC_CTYPE`/`LANG` in `Rules` (as `locale`,
  part of `rules_sha`).
- 16.6 `matching_lines` re-runs with exactly that environment, plus a scrubbed env (no
  `GREP_OPTIONS`/`GREP_COLOR*`).
- Pre-provenance rows use the permissive reading, which is locale-free Python.
- 16.6 AC-3 row: a grep row taught under `en_US.UTF-8` with `a.b` on `a—b`, verified by a daemon
  whose env has no `LANG` → `ok`. Mutation "inherit the daemon env" FAILS it.

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### SKETCHY s-2: 16.1 never says how short-flag clusters are recorded, and 16.6's token filter has no arity test {#s-2}

**Spec:** 16.1 R1 (one table per tool, "Short AND long forms … are rows of their own", "An unknown
token kills the teach"; the cluster walk is described only as 16.5 R0's); R10 (`match_argv` "verbatim
and in order", `-l` recorded as `-m 1`); AC-15 (`grep -rl --exclude=…` records "the `--exclude`
and `['-m','1']` tokens"); 16.6 R2 `verify_argv`, AC-3b ("assigns every … token … to exactly one of
keep/drop").

**What:**
- **Clusters.** `-rn`, `-rl` and `-rni` are the habitual agent greps, and no table row matches
  them. Either 16.1 kills them as `unknown-flag:-rn`, so most learning dies, or it records them
  verbatim. A verbatim `-rl` defeats 16.6's per-token filter: `-r` cannot be dropped, and `-l`
  cannot become `-m 1` inside a cluster. AC-15's `-rl` row presumes an expansion that no
  requirement states.
- **Arity.** AC-3b checks assignment, not value consumption. A filter that drops `-r` as a token
  turns `['-e','-r']` into `-e` followed by `-nH`: the pattern becomes `-nH`, the result is rc 1
  with an empty set, and the row is `stale-line` (probed: `grep -e -r` matches `-r here` when
  intact). AC-3d catches `-m 1`'s arity only by accident (rc 2 with hits → `tool-error`).

**Fix:**
- 16.1 R1 expands short clusters before classification with ONE shared walk (16.5 R0's, on the
  value letters `e f m A B C d D`), and R10 records the EXPANDED tokens.
- 16.1 AC-1 rows: `-rn`, `-rli`, `-rnie PAT`.
- 16.6 AC-3b adds arity rows (`['-e','-r']`, `['--exclude','x']`, rg `['-g','!x']`, `['-m','1']`)
  that must verify `ok`. Mutation "filter per token without consuming values" FAILS it.

### SKETCHY s-3: the permissive subset is not "rare by construction", and in 22.1a an `Unverifiable` entity falls into a REMOVAL class {#s-3}

**Spec:** 16.6 `#r2-permissive` ("Such rows are rare by construction: since 0.65.1 … pre-provenance
rows were never taught from them"); 22.1 `#r1-verify` (the same premise); 22.1a R1 ("A candidate
whose reading is `Unverifiable` does not count as verified"; outcomes: `verified@0` and not readable
→ `orphan-root:unresolved (removal candidate)`); 22.2 R9 ("`unverifiable` [is] never removed").

**What:**
- **The premise is false.** 1,511 of 31,608 distinct learned rows here (4.8%) and 69 global
  concepts are in the subset ([[#ev-subset]]). Some predate 0.65.1, and some are later, because
  POSIX classes and `-E` escapes were never refused. In 22.1 they are `unverifiable` forever: kept,
  which is safe, but never auditable. The spec should say how many.
- **The removal hole.** In 22.1a, an orphan-root entity whose patterns are all in the subset can
  never verify, either at a candidate or at `home_base`. It therefore lands in
  `orphan-root:unresolved`, a removal class. 22.2 R9's "never remove `unverifiable`" does not see
  it, because 22.1a has no unverifiable outcome. The log population holds 26 such relative global
  entities.

**Fix:**
- Delete the "rare by construction" sentence from 16.6 and 22.1. Cite the counts. Note that ERE
  `\(` is over-flagged, which is conservative.
- 22.1a adds the outcome `orphan-root:unverifiable` (no candidate decided, at least one reading
  `Unverifiable`): kept, counted by reason, and carried to 22.5 as held.
- AC: a relative entity whose only pattern is `a\|b` is never `unresolved`. Mutation "Unverifiable
  counts as not verified" FAILS it.

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]

### SKETCHY s-4: the readings-union ACs cannot fail on "N from the first reading only" {#s-4}

**Spec:** 16.6 AC-3h ("a two-reading row (`none` + `-i`) whose line matches only case-insensitively
→ `ok` (union)"); 22.1 AC-4b, first clause (the same fixture); the pre-registered mutation "`N` from
the first reading only FAILS it".

**What:** the `none` reading IS case-insensitive (`permissive_matching_lines`), so EACH reading
alone puts the line in its set. The mutation survives whichever reading comes first. 22.1 AC-4b's
second clause (one reading `Unverifiable`) catches it only if the unverifiable reading is not the
one taken first, and the spec does not fix the order.

**Fix:** use readings that DISAGREE. For example, the same pattern `a.c` recorded under `-F` and
under `-E`, on a line `abc`: only the `-E` reading holds it. Or use `-x` and plain. State the
reading order, and test both orders.

### SKETCHY s-5: sync and vacuum already remove learned rows outside plan-22, and the sidecar would orphan silently {#s-5}

**Spec:** 16.6 R1 ("the only INSERT path"), R1c (`orphaned_provenance` counted only at a merge), R6
("no silent failures"), AC-9; plan-22 `#root` principle ("the ONE removal path"); ADR
`#rule-no-delete` as amended (derived-index cleanup needs "a manifest written before the change").

**What ([[#ev-sync-purge]]):**
- **Today's removal path.** `purge_path` → `purge_entity` removes learned file entities, their
  `mentions` links and their protection, whatever `protected` says. It runs on:
  - every edit of a GMD `.md` (the relpath-named `doc` entity is the learner's own name for it);
  - every ignored path;
  - every deleted path.
- **The evidence.** It orphans their `linkage_evidence`, and `vacuum` deletes those orphans with no
  event. In this repo, 241 of 710 learned entities are on GMD documents, and 26 have already been
  tombstoned 47 times. So 16.1 teaches `.md` hits that the next edit-sync erases, and 22.1's
  `moved` repair never sees those files.
- **After 16.6.** None of `purge_entity`, `purge_path`, `_bulk_purge_ids` or `vacuum` touches
  `learned_evidence`. Every purge leaves sidecar rows on dead ids, counted only if a merge ever
  runs.
- **Rebuild diverges from live.** A rebuild replays every `evidence` event unconditionally,
  including those of re-created entities, so the evidence AND the provenance come back. 16.6 AC-9
  cannot see this, because its fixture has no purge.
- **The ADR.** The approved amendment lists none of these paths.

**Fix:**
- Log a bug row: learned rows are removed by sync's GMD legacy purge.
- 16.1 R3/R4 names a GMD `.md` hit by the ingester's doc-id entity, or the sync guard spares
  learned-only entities.
- 16.6 says who deletes sidecar rows on a purge: `purge_entity` deletes them by `entity_id` and
  counts them, or R6 adds a `rmx learn status` orphan count.
- The ADR amendment lists sync purge / `vacuum` / `fold_concept_dups` / `unprotect` as derived
  cleanup, exceptions, or entry points. That is a user decision on the now-approved text.

rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]

### SKETCHY s-6: the new census steps say "through a sandbox daemon pointed at the copy" but never say how a daemon opens a lone `catalog.read.duckdb` {#s-6}

**Spec:** 16.6 AC-5b, 22.1 AC-6b, 22.1a AC-5b/6b/7b, 22.3 R1 (all cite "the procedure of
[[task-23.4-option-a-measurement#r1]]"); 23.4 R1 (it opens the copy with ONE `duckdb.connect`,
never through a daemon).

**What:** the cited procedure does not contain the step these ACs rely on. A daemon opens
`catalog.<active>.duckdb` under an `active` marker, writes `facts.log` (16.6 AC-5b's backfill logs
events), and binds partitions. A lone `catalog.read.duckdb` in a tmp dir is none of that. The
operator will improvise, for example by renaming it to `catalog.A.duckdb` with `active=A`, plus an
empty or copied `facts.log`, and the census becomes unreproducible.

**Fix:** one shared operator script, `scripts/census_copy.sh` or a 23.0 helper:
- copy the snapshot to `<tmp>/.refmatrix/catalog.A.duckdb` and write `active`;
- copy `facts.log` when the census needs replay;
- start the sandbox daemon on it, with RMX_HOME pointed at a sandbox dir.

Every census AC cites the script. Not a user decision.

### MEH m-1: one log-order replay pass is not stated across 22.2's row ops and 16.6's provenance ops, and 16.6 AC-9 moves a sidecar row off its evidence {#m-1}

- 16.6 R1d applies `learned_provenance`/`_move` "AFTER the evidence events, in log order". 22.2 R3
  applies `evidence_remove/repoint/entity_rename` "in log order after the `evidence` appends".
- If the 22.2 ops replay as their own pass BEFORE the provenance pass, a re-pointed row's
  `learned_provenance` (line 10) finds no evidence at line 10. It is `unresolved_provenance`, and
  the provenance is lost. 22.2 AC-3 would catch this.
- **Fix:** state ONE post-evidence pass over all five ops in `ts` order.
- 16.6 AC-9 moves a sidecar row with no evidence row at the target. That state is impossible in
  production, and R1d's own unresolved rule would make a correct implementation FAIL the AC. Seed
  the evidence row at the new identity first.

### MEH m-2: contract details the implementer must guess {#m-2}

- rg `--no-config` is in 16.1's keep:match row but in neither 16.6 rg list, so AC-3b fails on the
  spec's own lists.
- `SidecarRow`, `Key` and `Verdict` are undefined. Say that `Key` = the five identity columns
  (the verdict is per evidence row, union over readings).
- `no-rules` has no trigger. It should be: a recorded-rules row with no pattern and no `-e`.
- Line numbering: `permissive_matching_lines`, `out-of-range` and 22.1's `hash_line` pairing must
  split on `b"\n"`, as grep does, never with `str.splitlines()`. Probed: a `\x0c` makes grep say
  line 2 and Python say line 3. There are 0 such files in this repo, and other stores are
  unchecked.

### MEH m-3: `out-of-range` still names two predicates {#m-3}

16.6 `verify` decides `out-of-range` = line past EOF, before any re-run. 22.1 R1 decides it =
"past the end AND the pattern matches nowhere" (else the set is moved, grown or shrunk). R4 marks
use 16.6's predicate; 22.1 reports its own. Give one of them another name, or define 22.1's in
terms of the set.

### MEH m-4: 22.5 bucket 2 mixes readable-today and unreadable rows, but the d9b ruling is about readable ones {#m-4}

22.5 `#root` says the no-owner rows "read correctly today". That is true for bucket 3. Bucket 2
(`orphan-root:resolved` under no project root) includes walk-resolved rows whose `$HOME/<rel>` does
NOT exist, which is bug-086's symptom. 22.1a records the readable-today attribute on every entity,
so split bucket 2 by it in the dry run, and the user rules on the right numbers.

### MEH m-5: plan-of-plans row 16 still lags (carried from m-2) {#m-5}

Row 16's dependency cell still says "+ tasks 16.7-16.10 for agent `rmx context` usage", and its
Tasks cell says "no" although 6 specs exist. The plan hands this to the orchestrator; it is one
edit.

### MEH m-6: 16.6 AC-3 relies on the rg on PATH being the deploy's {#m-6}

AC-3 records rg rows with "the `rg` on PATH, resolved to an absolute path". The launchd PATH puts
`/opt/local/bin` before `/usr/local/bin` and `/opt/homebrew/bin`. A second rg there would make
learn-time and verify-time agree only by PATH order. Pin it: `bin` is recorded absolute and never
re-resolved, which R2 already implies. One sentence.

## Cross-plan consistency {#cross-plan}

**Consistent:**
- verdict names (`ok`, `stale-line`, `missing-file`, `out-of-range` as a name, `unverifiable` with
  `UNVERIFIABLE_REASONS`);
- the sidecar key and its owners (16.6 supplies `move_learned_provenance`; 22.2 R2 and 22.5
  `learned_import` call it and own the moves);
- the `root` setter (22.5);
- the marks' reader (22.1);
- one verifier (d-11);
- the root spelling (22.2 R8; `is_global_root` = `~/.refmatrix`);
- the wave order (`#t10-waves`: 16.6 → 22.1a → 22.2 → 22.5 → 22.3 in Wave 1; 16.1 and 22.1 in
  Wave 2).

**Conflicts:**
1. Plan-22 `#scope` / open item 4 against the approved ADR `#rule-no-delete` ([[#b-3]]).
2. Replay order between 22.2 R3 and 16.6 R1d ([[#m-1]]).
3. 16.6/22.1 "rare by construction" against 22.1a's removal of `Unverifiable` entities
   ([[#s-3]]).
4. 16.1 R10's "verbatim" `match_argv` against 16.6's per-token filter for clusters ([[#s-2]]).
5. `out-of-range` predicates ([[#m-3]]).

## Open-after-revision items, classified {#open-items}

### Plan-16 {#open-16}

All four are closed. Item 4's two plan-of-plans cells are an orchestrator edit ([[#m-5]]). None
needs the user.

### Plan-22 {#open-22}

| item | real user decision? | why |
|---|---|---|
| 1 d8d owner | no, settled | 21.1 `telemetry.py` |
| 2 the no-owner rows | **YES, after the dry run** | d9b; split bucket 2 by readable-today first ([[#m-4]]) |
| 3 plan close | settled | d9j |
| 4 ADR "only" | **user already decided (d9k); plan-22 must follow** | the spec now contradicts the approved rule ([[#b-3]]). Listing the unlisted removal paths (sync purge, `vacuum`, fold, `unprotect`) IS a new user call on the ADR text ([[#s-5]]) |
| 5, 6, 7, 9 | settled | as stated |
| 8 walk exclusions | **no, the spec settles it** | the probe's walk rule is measurable ([[#ev-walk]]); [[#b-1]]'s fix |

## User decisions needed {#user-decisions}

1. **(s-5) ADR-0004 `#rule-no-delete` as approved omits live removal paths.** These are sync's
   `purge_path` (GMD edit / ignored / deleted, which removes protected learned rows), `vacuum`
   (unprotected empty concepts, orphan evidence with no event), `fold_concept_dups` and `unprotect`.
   For each, choose one: derived cleanup with a manifest, a listed exception, or an entry point to
   plan-22.
2. **(d9b, unchanged)** the no-owner global rows, after 22.5's dry run.

## Verdict {#verdict}

**Plan-16: NEEDS-REVISION.**
- 16.2, 16.3, 16.4 and 16.5 are approvable (16.2's scrubber closes s-4).
- 16.1 needs the cluster rule and the locale record ([[#s-1]], [[#s-2]]).
- 16.6 needs:
  - the locale-pinned re-run ([[#s-1]]);
  - the arity rows ([[#s-2]]);
  - the subset counts ([[#s-3]]);
  - the AC-3h fixture ([[#s-4]]);
  - the purge owner ([[#s-5]]);
  - [[#m-1]] and [[#m-2]].

The verifier contract itself is implementable as specified for BSD grep and rg (probed).

**Plan-22: NEEDS-REVISION.**
- 22.1a needs [[#b-1]] and [[#s-3]].
- 22.1 needs [[#b-2]] and [[#s-4]].
- Plan-22 `#scope` plus a new task need [[#b-3]].
- 22.5 needs [[#m-4]].
- The census steps need [[#s-6]].
- 22.2's engine, 22.3 and 22.4 hold.
- 22.5's d9b handling is correct: nothing is applied to buckets 2 and 3 on a `pending` manifest
  (AC-1b, with a mutation).

| | prior closed | partial | open | new B | new S | new M |
|---|---|---|---|---|---|---|
| plan-16 | 7 | 1 (m-2) | 0 | 0 | 2 (s-1, s-2) | 2 (m-2, m-6) |
| plan-22 | 10 | 3 (s-1, r1 b-4, r1 m-7) | 0 | 3 (b-1, b-2, b-3) | 1 (s-6) | 2 (m-3, m-4) |
| shared | 2 | 1 (m-4) | 0 | 0 | 3 (s-3, s-4, s-5) | 2 (m-1, m-5) |

**15 new findings: 3 BULLSHIT, 6 SKETCHY, 6 MEH.** s-3, s-4, s-5, m-1 and m-5 span both plans and
are counted once.

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 6091648 (SPEC re-review r3: plan-16 16.1-16.6 round 2 + plan-22 22.1/22.1a/22.2-22.5 round 2, pre-implementation; HEAD moved to 097e7b1 mid-review, ADR-0004 amendment approved d9k; written 2026-10-14T13:26-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 15 new (3B/6S/6M); 32dde06 items: plan-16 7 closed 1 partial, shared 2 closed 1 partial, plan-22 10 closed 3 partial 0 open | [[bsd-plan16-22-spec-rereview-r3-6091648]]: learned_verify contract implementable on BSD grep 2.6.0 + rg 15.1.0 (canonical tails parse; exit-2 map holds; AC-3 mutations bite); 22.1/22.1a carry no matcher. BULLSHIT: 22.1a AC-5b gate unsatisfiable (probe walked 972,849 = prune dot-entries+node_modules+__pycache__ (974,684 today); spec's OFF walk 2,178,771, ON 648,666; probe verify rule unrecorded) and it blocks 22.5/22.3; 22.1 grown/shrunk has no shift rule (delete a line -> shifted rows stale-line, AC-5's own fixture shifts); approved ADR #rule-no-delete makes forget/bulk-forget plan-22 entry points while plan-22 #scope disowns them and 22.2 R4 cannot restore memory bodies/entity path. SKETCHY: re-run ignores locale (daemon plists set only PATH -> C; probed a.b vs a—b, -i café vs CAFÉ, [[:alpha:]] vs ï); clusters/arity (-rn, -e -r); permissive subset 4.8% of rows not rare, Unverifiable-only orphan-root entity becomes a removal (26 in global log); union ACs vacuous; sync GMD legacy purge + vacuum remove learned rows today (241/710 learned entities on GMD docs, 26 tombstoned 47x) and would orphan sidecar rows; census "through a sandbox daemon" has no procedure. Read-only; probes in mktemp; facts.logs parsed with python3 -I. |
```

last_run.log line:

```
2026-10-14T13:26:36-0700 commit=6091648 verdict=DIRTY findings=15 (3B/6S/6M) report=2026-10-14-1326-plan16-22-r3-spec-rereview-probe-walk-unreproducible-and-shifted-sets-removed-6091648.md
```

IMPRESSIONS.md bullets:

```
- plan-16/22 r3 (6091648): before demanding "reproduce the probe", measure the probe's own inputs (file count, rule). 972,849 matched only a hidden-entry/node_modules/__pycache__ prune; my r2 fix "walk with exclusions off" was unverified and became a blocking gate that cannot pass.
- A re-run verifier must replay the ENVIRONMENT too: launchd daemons run in C locale, agents in UTF-8, and BSD grep's `.`/-i/[[:alpha:]] change meaning across them. Ask "what did the original run inherit?" not only "which tokens".
- Set-level repair specs: test them with a REAL line deletion (which shifts later lines), never an in-place blank; "grown/shrunk" without a shift rule deletes moved knowledge.
```
