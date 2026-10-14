---
gmd: "0.1"
id: task-16.6-learned-row-validation
title: "Task 16.6 (Wave-1 slice): the learned-evidence sidecar (replayable from facts.log), THE re-run verifier and its line-set API, read-time marks with a named reader, and the provenance backfill (audit/prune/repair in plan-22; the learn-time write in 16.1)"
tags: [task, grep, learning, validation, provenance, wave-1]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
  revised: 2026-10-14
---

# Task 16.6: the learned-evidence sidecar, its verifier, read-time marks and the backfill {#root}

> Plan: [plan-16-invisible-grep-shim](../plan-16-invisible-grep-shim.md)
> Status: Pending (revision round 2, 2026-10-14, answering the re-review
> `bsd-plan16-22-spec-rereview-32dde06` and `plan-review-2026-10-14#t9`; [[#rev-round-2]]).
> Revision 6 of plan-16's specs was the first revision of 16.6 after its first spec review (r5,
> `bsd-plan16-spec-review-r5-cd7c923`).
> The user asked for it on 2026-10-07: "rmx grep learning entries should be cullable and/or at
> least have a validation process to check for stale entries". The CULL half lives in plan-22
> ([[#split]]).
> **Wave:** 1, after plan-23's task 23.1 (`bind(partition_name)`, the durable queue and bounded drain), and
> before plan-22's 22.1a ([[plan-review-2026-10-14#t8-wave1]]).
> **Depends on:** plan-23 task 23.1 (queue + `bind(partition_name)` drain), plan-23 task 23.0 (the shared
> test sandbox). It does NOT depend on task 16.1 (d6d, [[plan-review-2026-10-14#t8-amendments]]).
> Task 16.1 depends on THIS task: its learn-time provenance write (16.1 R10) needs this table.

rel: part-of -> [[plan-16-invisible-grep-shim]]
rel: depends-on -> [[plan-23-bounded-write-harness]]
rel: depends-on -> [[task-23.1-queue-and-drain]]
rel: depends-on -> [[task-23.0-test-sandbox]]
rel: related-to -> [[task-16.1-argv-faithful-learner]]
rel: related-to -> [[project_global_relative_rows_repair]]
rel: amends -> [[plan-review-2026-10-07#contradictions]]
rel: amends -> [[bsd-plan16-spec-review-r5-cd7c923]]
rel: amends -> [[bsd-plan16-22-spec-rereview-32dde06]]
rel: derives-from -> [[plan-review-2026-10-14#t6]]
rel: derives-from -> [[plan-review-2026-10-14#t9]]
rel: derives-from -> [[plan-review-2026-10-14#t8-amendments]]
rel: motivates -> [[plan-22-audited-removal-and-repair]]
rel: motivates -> [[task-22.1-audit-classes]]
rel: motivates -> [[task-22.2-repair-then-remove]]
rel: motivates -> [[task-22.3-bug-086-global-repair]]
rel: specifies -> [[task-22.1-audit-classes#r1-verify]]
rel: related-to -> [[task-23.4-option-a-measurement]]

## Revision round 2 (2026-10-14) {#rev-round-2}

Answers [[bsd-plan16-22-spec-rereview-32dde06]] and [[plan-review-2026-10-14#t9]] (`#t9-fixes`).
Later rows win over the revision-6 table below.

| finding / decision | answered in |
|---|---|
| re-review b-1 (re-run calls matching rows stale: cutoffs, absolute-path `--exclude`, exit 2) / #t9-fixes "closes its three false-stale holes" | R2 [[#r2-argv]] (verify-time token filter), R2 exit-status bullet (`tool-error` → `unverifiable`); AC-3 d/e/f, AC-3b; mutations in AC-10 |
| re-review b-2 (sidecar has no `facts.log` form; rebuild erases it) / #t9-fixes "16.6 provenance gets a `facts.log` event" | R1d [[#r1d]] (`learned_provenance`, `learned_provenance_move`, both replay paths); R5 routes through it; AC-9 + two mutations |
| re-review b-3 (marks have no reader) | R4 [[#r4-reader]] (option (a): 22.1 reads them, [[task-22.1-audit-classes#r1-marks]]); [[#r4-lower-bound]] states the reading requirement |
| re-review b-4 (22.1's Python translation contradicts R2; R2 returns verdicts, not the line set) / #t9-fixes "22.1 calls 16.6's verifier, which returns the matching line set" | R2 [[#r2]] (the contract: `matching_lines`, `permissive_matching_lines`, `verify`, `hash_line`); AC-3 a/c; 22.1 [[task-22.1-audit-classes#r1-verify]] calls it |
| re-review s-3 (census ACs need live catalogs) / #t9-fixes "sandbox-safe catalog clones" | AC-5 split: 5a sandbox fixture, 5b operator census on a `cp` of `catalog.read.duckdb` (23.4 R1's procedure); [[#test-strategy]] |
| re-review s-5 (plan-22 repairs change the key columns) / #t9-fixes "22.2/22.5 update provenance keys" | R1 "Key-column updates belong to plan-22" + `move_learned_provenance`; R1d's move event |
| re-review m-1 (false dialect premise; dead `python` branch) | R1 `dialect` row (no `python`); R2 has no `python` branch; plan [[plan-16-invisible-grep-shim#open-after-revision]] item 3 closed |
| re-review m-4 (vocabulary drift; "22.1b"; `root` setter) | verdicts `stale-line`/`missing-file` (R2, R4, R1 `last_mark`); `UNVERIFIABLE_REASONS` is the one `unverifiable` definition; [[#split]] cites 22.1; R1 `root` row names 22.5's import |
| re-review m-5 (which reading defines the set) | R2 `verify` bullet: the union over readings, `none` read permissively; AC-3h |
| re-review m-6 (AC-6 count fails on correct code) | AC-6 counts DISTINCT evidence identities |
| r5 b-r5-1 (partial at the re-review) | closed by b-1, b-2, b-4 above |

## Revision 6 changelog {#revision-6}

Answers spec review r5 ([[bsd-plan16-spec-review-r5-cd7c923]]), the plan-22 review items that name
16.6, and the 2026-10-14 decision log ([[plan-review-2026-10-14]]) with its close-out.

| finding / decision | answered in |
|---|---|
| d6d (16.6 split by dependency; settles plan-16 dn-2 and plan-22 #b-7) | header (wave 1, after 23.1, no 16.1 dependency); [[#split]]; the learn-time write is 16.1 R10 |
| #t8-amendments d1c/d6d (16.6's leftover dependency on 16.1 removed; the Wave 1 slice is R4/R5 + sidecar) | header; [[#split]]; `rel:` edge to 16.1 is `related-to`, not `depends-on` |
| decision-log review #b-3 (16.6 header inverts Wave 1 → Wave 2) | header; plan [[plan-16-invisible-grep-shim#waves]] |
| plan-22 #b-7 / r5 s-r5-5 (16.6 has no wave; "(draft)" blocks `approved`) | header; "(draft)" removed from [[#requirements]] and [[#acceptance]]; R1b closes the legacy-writer window |
| r5 b-r5-1 / plan-22 #b-2 (provenance cannot replay the caller's rules; Python `re` is the only verifier) | R1 [[#r1]] (`tool`, `bin`, `dialect`, `match_argv`, `line_hash`); R2 [[#r2]] (the verifier re-runs the recorded tool, never Python `re` for those rows); AC-3 |
| #t6-fixes "16.6 records a line hash" / plan-22 #b-1 (no hash recorded) | R1 `line_hash`; R3 [[#r3]] |
| #t6-fixes "provenance carries tool + dialect + line hash" | R1 |
| #t6-fixes / r5 s-r5-3 (read-time marks record reader-rule drops as staleness) | R4 [[#r4]] (a reader-rule drop with an unchanged hash writes nothing); AC-4 + mutation |
| #t6-fixes / r5 s-r5-4 / plan-22 #s-6 (sidecar keyed on `evidence_rowid`, rewritten by `replica_merge`'s `SELECT DISTINCT`) | R1 key = `(entity_id, linkage_id, concept_id, file, line, rules_sha)`; R1c [[#r1c]] merge step; AC-2 + mutation |
| decision-log review #m-3 (`stale_seen` rides a coalescing, overflow-dropping queue) | R4 "lower bound" paragraph [[#r4-lower-bound]]; AC-8 |
| decision-log review #s-1 (only the sidecar got a `replica_merge` fix) | R1c covers the sidecar; the other tables are plan-23's (not edited here) |
| d1a/d1b (tests sandboxed by task 23.0) | [[#test-strategy]] |
| plan-22 #m-3 (plan line ~138 said 16.6 prunes) | plan [[plan-16-invisible-grep-shim#tasks]] row 16.6 (closed in r5; re-checked) |

## Revision 5 changelog (history) {#revision-5}

Applied the plan review's C1/C2/C3 ([[plan-review-2026-10-07#contradictions]]; user 2026-10-07:
"apply all the consolidations, don't delete moves repair them if possible"). Nothing was deleted:
every moved requirement and decision is kept below, marked with where it now lives.

| item | answered in |
|---|---|
| C1 the audit/prune engine moves to ONE audited removal plan | [[#split]]; plan-22 22.1/22.2 |
| C2 bug-086 has two vehicles | [[#split]]: plan-22 task 22.3 is the only one; R5 leaves global roots NULL for it |
| C3 `moved` rows deleted by default | [[#d-c]] amended (repair, never delete); [[#d-c-review]] closed by the user's answer |
| plan-16 header + table row (m-r4-1 family) | plan [[plan-16-invisible-grep-shim#tasks]] row 16.6 re-scoped |

## What stays in this task, what moved {#split}

d6d (user, 2026-10-14) splits 16.6 by DEPENDENCY, not by plan. Everything that needs no learner
change runs in Wave 1 after plan-23's 23.1; the learn-time provenance write moves into task 16.1
(Wave 2). plan-22's provenance-free classes (22.1a) and 22.3 do not wait for either.

| item | owner | where |
|---|---|---|
| R1 sidecar table `learned_evidence`, its key and its writer API | this task (Wave 1) | [[#r1]] |
| R1b legacy-writer rows until 16.1 lands | this task (Wave 1) | [[#r1b]] |
| R1c `replica_merge` carries the sidecar | this task (Wave 1) | [[#r1c]] |
| R2 the dialect-faithful verifier | this task (Wave 1) | [[#r2]] |
| R4 read-time `last_verified_at` / `stale_seen` marks, queued | this task (Wave 1), through plan-23's queue | [[#r4]] |
| R5 provenance backfill (project roots; global roots NULL) | this task (Wave 1) | [[#r5]] |
| R6 loud counting on every leg | this task (Wave 1) | [[#r6]] |
| the LEARN-TIME provenance write (tool, dialect, match tokens, line hash, `spawned_by`) | task 16.1 R10 (Wave 2), d6d | [[task-16.1-argv-faithful-learner#r10]] |
| the audit (`removal_audit`) and its classes (`ok`, `moved`, `ambiguous`, `stale-line`, `out-of-range`, `missing-file`, `duplicate`, `orphan-root`, `orphan-alias`, `empty-learned`) | plan-22 (22.1a provenance-free; 22.1 the flag-sensitive rest, which calls R2) | [[task-22.1-audit-classes]], [[task-22.1a-provenance-free-classes]] |
| repair then removal; manifest; row-level events; ablation gate | plan-22 | [[task-22.2-repair-then-remove]] |
| bug-086's global repair and the cross-store move | plan-22 | [[task-22.3-bug-086-global-repair]], [[task-22.5-cross-store-move]] |

rel: realizes -> [[plan-review-2026-10-07#contradictions]]
rel: realizes -> [[plan-review-2026-10-14#t6]]

## Why {#why}

Every grep-learned row is written by ONE writer, `_learn_grep_hits` (`daemon.py:4295` at
`b1c4324`). It is reached from three feeders:

- the RPC op `learn_from_grep` (`_op_learn_from_grep`);
- the learn-queue drain (`daemon.py:2135`);
- the daemon's context backstop (`daemon.py:4795-4806`), whose hits come from `rg -nH -i -F`
  (`context.py:915`).

Each feeder writes:

- a `query/<pattern>` concept, `protected=True`;
- an entity for each hit file, `protected=True`;
- a `mentions` link;
- one `linkage_evidence(file, line, detail="learned from grep '<pat>'")` row per hit (the
  pattern is `repr`-quoted). {#why-writes}

Nothing ever removes these rows, and nothing can tell they have gone stale:

1. **No provenance.** `linkage_evidence` is `(entity_id, linkage_id, concept_id, file, line,
   span_end, detail)` with no primary key (`duckdb_catalog.py:162`). It has no learned-at, source,
   root, tool, dialect or line-hash column. A learned file entity shares `UNIQUE(partition, kind,
   name)` with the ingester's entity, so learning a file the ingester owns PROTECTS the ingested
   row. Learned rows cannot be selected apart from ingested ones.
2. **Read-time verification sees staleness and forgets it.** `verify_evidence_rows`
   (`store.py:816`, called from `grep_evidence` at `store.py:3257`) drops a row whose file is
   unreadable, whose line is out of range, or whose line fails the READER's pattern, and counts it
   (`unreadable`, `dropped`). It writes nothing back, so the same dead row is re-read and
   re-dropped on every grep, forever. It also cannot tell "the line changed" from "the reader asked
   a different question" (s-r5-3).
3. **The only verifier speaks Python `re`.** `evidence_line_matches` (`store.py:759`) reads BRE
   `zzz\|alp` and `\(foo\)x` differently from BSD grep (probed in r5: grep matches `alpha` and
   `foox`; Python does not). A row taught correctly by a BRE grep re-verifies as stale under it
   (b-r5-1).
4. **`protected` blocks every reaper; `add_evidence` is an unconditional INSERT.** 16.1 adds
   store-side idempotence for NEW rows; the existing duplicates stay for plan-22. {#why-gaps}

Scale today: the global store holds 1,087 relative learned entities with 5,159 evidence rows, of
which about 700 read as unreadable on every global grep (bug-086). {#why-scale}

## Requirements {#requirements}

**R1. The sidecar `learned_evidence` (schema, key, writer API).** {#r1}

One row per (evidence row, reading). Columns:

| column | meaning |
|---|---|
| `entity_id`, `linkage_id`, `concept_id`, `file`, `line` | the evidence row's identity, the same five values as its `linkage_evidence` row (plan-22 #s-6's row identity) |
| `rules_sha` | sha256 hex of the canonical JSON `[tool, dialect, match_argv]`; the literal `none` when the row has no recorded rules (backfill, legacy writer) |
| `origin` | `learner` (16.1 R10), `context-backstop` (16.1 R10), `legacy-writer` (R1b), `backfill` (R5) |
| `source` | `grep-learn` |
| `learned_at` | epoch seconds; NULL for `backfill` (unknown, never invented) |
| `root` | the absolute PROJECT root the row was learned under (the store root's parent); NULL in the global store. The only writer that sets it on a global-origin row is plan-22's 22.5 `learned_import`, which sets it to the TARGET project root as it copies the row (m-4) |
| `pattern` | the pattern as the tool received it |
| `tool`, `bin` | `grep` / `rg` and the absolute binary that produced the hit; NULL when unknown |
| `dialect` | `bre`, `ere`, `fixed` (grep), `rust`, `pcre2` (rg), `mixed` when the kept tokens name more than one; NULL when unknown. These are exactly the values 16.1 R10 writes; there is no `python` value (m-1). Informational: R2 always re-runs `tool` itself |
| `match_argv` | the kept MATCH-class and CUTOFF-class tokens verbatim, in order, as 16.1 R1's table kept them (JSON list). Recorded whole; R2 FILTERS it at verify time ([[#r2-argv]]) |
| `line_hash` | `learned_verify.hash_line(raw)` of the matched line's bytes as the tool printed them, without the line terminator ([[#r3]]); NULL when not recorded |
| `spawned_by` | `shim`, `grep-tool-hook`, `rmx-grep`, `context-backstop`; NULL for `backfill`/`legacy-writer` |
| `last_verified_at`, `stale_seen`, `last_mark` | R4's marks; `last_mark` in `missing-file`, `out-of-range`, `stale-line` (plan-22's class names, m-4) |

- **Primary key `(entity_id, linkage_id, concept_id, file, line, rules_sha)`.** It never uses
  DuckDB's `rowid`, which `replica_merge` rewrites (s-r5-4). Two readings of one row (`grep -i foo`
  and `grep foo` both teach `query/foo`) are two sidecar rows; R2 calls the row `ok` when ANY of
  its readings passes.
- **Writer API:** `Store.add_learned_provenance(rows)` inserts with `ON CONFLICT DO NOTHING` on the
  key, inside the caller's transaction, and logs one `learned_provenance` event per row it actually
  inserted ([[#r1d]]). It is the only INSERT path of the table besides R1c's merge; R4's drain
  updates only the mark columns. 16.1 R10 calls it from `_learn_grep_hits`; R1b and R5 call it
  here.
- **Key-column updates belong to plan-22 (s-5).** Every plan-22 primitive that changes a column of
  this key moves the sidecar row in the SAME transaction and logs it: 22.2's `repoint_evidence`
  (`line`), `rename_entity` merge (`entity_id`), `remove_evidence` (delete / collapse), and 22.5's
  `learned_import` (`entity_id`, `file`, `root` in the target store). The owner is named in
  [[task-22.2-repair-then-remove#r2]] and [[task-22.5-cross-store-move#r2]]; this task supplies the
  table, the key and the `Store.move_learned_provenance(old_identity, new_identity)` helper they
  call (an UPDATE of the key columns on every reading of that identity, plus one
  `learned_provenance_move` event). When the new key already exists, the two rows collapse as R1c
  collapses them (earlier `learned_at` wins the non-mark columns, `stale_seen` = max, `last_mark`
  from the later `last_verified_at`).
- The DDL lives in `duckdb_catalog.py` beside `linkage_evidence`. `linkage_evidence` is untouched,
  so the migration is additive and reversible (d-a).

**R1d. The sidecar is replayable from `facts.log` (b-2).** {#r1d}
`rebuild_index_from_log` (`store.py:7566`) unlinks the catalog and replays `facts.log` only; a table
with no event is wiped by every `rmx rebuild-index` and every `rebuild_index` daemon op. So:
- **Event `learned_provenance`**, keyed by NAME, never by id: `{linkage, c, e_kind, e, file, line,
  rules_sha, origin, source, learned_at, root, pattern, tool, bin, dialect, match_argv, line_hash,
  spawned_by}`. Written by `add_learned_provenance` through `_log_events` (one append per call, the
  same `_log_enabled()` switch every event has), after the evidence events of the same call.
- **Event `learned_provenance_move`** `{linkage, c, e_kind, e, file, line, to: {e_kind, e, file,
  line, root}}` from `move_learned_provenance` (plan-22's repairs and import).
- **Both replay paths apply them:** `_apply_event_body` (`store.py:7460`) and the rebuild pass
  (`store.py:7566`, which today collects `evidence` events at `:7681` and applies them at
  `:7771`, after entities, protections and links). The two new ops are collected the same way and applied AFTER the evidence
  events, in log order, resolving names to ids at apply time. An event whose evidence row does not
  exist at apply time is counted `unresolved_provenance` and printed, never dropped silently.
- R4's marks (`last_verified_at`, `stale_seen`, `last_mark`) have NO event: they are derived,
  re-earned by later reads, and a rebuild resets them to NULL/0 (stated, counted in the rebuild's
  result as `marks_reset`).
- plan-22's `evidence_remove` replay removes the matching sidecar rows by the same identity
  ([[task-22.2-repair-then-remove#r3]]).

**R1b. No new evidence row without a sidecar row, from the day this slice lands (s-r5-5).** {#r1b}
Between this Wave-1 slice and 16.1, today's writer keeps teaching. So `_learn_grep_hits`, in the
same transaction as its `add_evidence` calls, calls R5's backfill routine for exactly the rows it
just inserted: `origin=legacy-writer`, `rules_sha=none`, `learned_at` = now, `root` = the
`project_root` argument, `pattern`, everything else NULL. This is not 16.1 R10's provenance (no
tool, dialect or hash is known on today's path); 16.1 R10 replaces this call. `legacy-writer` rows
are verified like backfilled rows (R2's `none` reading, `permissive_matching_lines`, [[#r2-permissive]]).

**R1c. `replica_merge` carries the sidecar (s-r5-4).** {#r1c}
- `learned_evidence` is added to the merge's table lists (`replica_merge.py:88`, `:433`, `:530` at
  `b1c4324`).
- A new step after step 9 (`replica_merge.py:335-355`) rebuilds it from both slots with the SAME
  remap step 9 applies to `linkage_evidence` (`COALESCE(canonical_id, entity_id)` and
  `COALESCE(canonical_id, concept_id)` through `remap_a`/`remap_b`), then collapses on the key:
  `last_verified_at` = max, `stale_seen` = max (both slots share history before the split, so a
  sum would double count), `last_mark` from the row with the later `last_verified_at`; every other
  column from the earlier `learned_at` (NULLs last).
- After the merge, every sidecar row joins exactly one `linkage_evidence` row on the five identity
  columns; a sidecar row that joins none is counted (`orphaned_provenance`) and printed by the merge,
  never silently dropped.

**R2. The verifier re-runs the row's own tool; it is THE verifier for learned rows (b-r5-1,
#t6-fixes, b-1, b-4).** {#r2}
Module `src/refmatrix/learned_verify.py` (new). Plan-22's 22.1 and 22.1a call these functions and
carry no matcher of their own ([[task-22.1-audit-classes#r1-verify]]). The cross-plan contract,
exact names and signatures:

```python
@dataclass(frozen=True)
class Rules:                       # one sidecar reading
    tool: str                      # "grep" | "rg"
    bin: str                       # absolute path
    dialect: str | None            # informational only
    match_argv: tuple[str, ...]    # as recorded (R1)
    pattern: str | None
    @property
    def rules_sha(self) -> str: ...

@dataclass(frozen=True)
class Unverifiable:
    reason: str                    # one of UNVERIFIABLE_REASONS

UNVERIFIABLE_REASONS = ("no-rules", "bin-missing", "timeout", "tool-error",
                        "permissive-subset", "unreadable")

def matching_lines(file_abs: Path, rules: Rules, *, timeout_s: float = 5.0
                   ) -> frozenset[int] | Unverifiable: ...
def permissive_matching_lines(file_abs: Path, pattern: str
                              ) -> frozenset[int] | Unverifiable: ...
def hash_line(raw: bytes) -> str: ...
def verify(rows: Iterable[SidecarRow], project_root: Path
           ) -> dict[Key, Verdict]: ...      # built on matching_lines
```

Verdicts (one vocabulary with plan-22, m-4): `ok`, `stale-line`, `missing-file`, `out-of-range`,
`unverifiable` (with its reason).

- **`matching_lines` (b-4): the current matching LINE SET of one file under one reading.** It
  re-runs `bin` with the FILTERED tokens ([[#r2-argv]]), then the canonical tail (`-nH --null` for
  grep; `-nH --null --no-heading --color never --no-config` for rg), then `-e <pattern>` (omitted
  when the filtered tokens already carry `-e`/`--regexp`, as the context backstop's rows do), then
  `-- <file_abs>`, with `stdin=/dev/null`, `cwd` = the file's directory and a per-file timeout. It
  parses `file\0LINE:` records and returns every LINE. Python `re` is never used for a row with
  rules. `verify` calls it once per `(file, rules_sha)` and shares the set across that file's rows;
  22.1 classifies `moved`/`grown`/`shrunk` on the same set.
- **Verify-time token filter (b-1.1, b-1.2).** {#r2-argv} `match_argv` is recorded whole (R1), but
  only PATTERN-SEMANTICS tokens are replayed; the file was already selected and a cutoff only
  hides lines:
  - grep keeps: `-i --ignore-case -y -w --word-regexp -x --line-regexp -F --fixed-strings -E
    --extended-regexp -G --basic-regexp -e PAT --regexp=PAT --regexp PAT -a --text -U --binary
    --binary-files=V --binary-files V`;
  - rg keeps: `-i --ignore-case -s --case-sensitive -S --smart-case -w --word-regexp -x
    --line-regexp -F --fixed-strings -e PAT --regexp=PAT -P --pcre2 -U --multiline
    --multiline-dotall -a --text --binary`;
  - everything else in `match_argv` is dropped: the cutoffs (`-m N`, `--max-count`, and `-l`
    recorded as `-m 1`) and every file-selection token (`-r -R --recursive -S -O -p` for grep, where
    `-S` is a symlink flag, `--include --exclude --exclude-dir --include-dir -d -D --directories
    --devices -I --mmap`; rg `-g --glob --iglob -t --type -T --type-not -u -uu -uuu --hidden
    --no-ignore* -L --follow -d --max-depth`). The filter is per tool (grep `-S` is dropped, rg
    `-S` is kept). Without it, `-l` re-runs as `-m 1` and hides a still-matching later line, and
    BSD grep matches `--exclude` against the WHOLE absolute operand, so an exclude that names a
    parent directory prints nothing (both probed in the re-review, `#ev-verifier`).
  - The filter is a pure function `verify_argv(tool, match_argv) -> tuple[str, ...]`, unit-tested
    against 16.1 R1's table so every keep:match and keep:cutoff token is assigned to exactly one
    side (no token unclassified).
- **Exit status (b-1.3).** rc 0 → the parsed set; rc 1 with no output → the empty set; any other rc
  (2 = parse error, an upgraded or swapped `bin` that now rejects the pattern), a signal, or rc 0/1
  with unparsable output → `Unverifiable("tool-error")`, KEPT and counted, never `stale-line`.
  `bin` missing or not executable → `Unverifiable("bin-missing")`; the timeout →
  `Unverifiable("timeout")`.
- **`permissive_matching_lines`: the reading for rows WITHOUT rules** (`rules_sha=none`:
  `backfill`, `legacy-writer`). {#r2-permissive} A line is in the set when ANY of: a
  case-insensitive substring match; `evidence_line_matches(text, pattern, regex=True,
  ignore_case=True)` (`store.py:759`); `identifier_variant_regex(pattern)` (`store.py:786`) matches.
  This is not a dialect translation: it is today's reader, widened. It names its subset (r5's
  second fix): a pattern containing a BRE/POSIX/rg construct Python reads differently (`\|`,
  `\(`, `\)`, `\{`, `\}`, `\<`, `\>`, `[[:`, `\p{`, `\P{`) gets
  `Unverifiable("permissive-subset")`, because Python `re` COMPILES `[[:digit:]]` and `\<foo\>` and
  silently mis-matches them (`#ev-verifier`). Such rows are rare by construction: since 0.65.1
  (`583ad1c`) `cli.py:6168-6178` refuses BRE escapes on the teach path, so pre-provenance rows were
  never taught from them.
- **`verify`** decides `missing-file` (unreadable or missing; `Unverifiable("unreadable")` when
  the stat itself errors) and `out-of-range` (line > file length) before any re-run; then a row is
  `ok` when its line is in the UNION of its readings' sets, `stale-line` when every reading
  returned a set and the line is in none, and `unverifiable` (first reason) when it is in none and
  at least one reading was `Unverifiable` (m-5's union rule, also used by 22.1). A `none` reading
  goes through `permissive_matching_lines`; a row whose only reading is `none` is therefore decided
  here too, not left to plan-22.
- The verifier is subprocess-bound, so it runs in R4's drain pre-step and in plan-22's audit,
  NEVER on the read path.

**R3. The line hash (#t6-fixes, plan-22 #b-1).** {#r3}
`line_hash` = `learned_verify.hash_line(raw)` = sha256 hex of the line's bytes without the line
terminator. ONE function: 16.1 R10 calls it on the bytes the tool printed at learn time, R4 on the
current line, and plan-22's 22.1 on the lines of `matching_lines`'s set when it pairs a hashed
`moved` set. Here it serves two readers: R4 compares it to the current line to tell `stale-line`
candidates from a reader-rule drop, and plan-22's per-`(concept, file)`-set repair (#t6-fixes
`#b-1`) may use it as an optional extra on rows that have it. A backfilled or legacy row has
`line_hash` NULL; nothing computes one from the current file (that would certify a possibly stale
line as current).

**R4. Read-time marks: staleness only, never the reader's own filtering (s-r5-3, d-b).** {#r4}
- `verify_evidence_rows`'s stats split today's `dropped` into `out_of_range` and `reader_rule`
  (the line was read and fails the READER's pattern, case or regex flag), and add `missing_file`
  (= today's `unreadable`). The existing keys stay for their readers: `unreadable` unchanged,
  `dropped` = `out_of_range` + `reader_rule`.
- For each LEARNED row the read touches (a sidecar join on the five identity columns), the read
  path enqueues at most one candidate, through plan-23's durable queue (no lock, no inline write):
  - kept by the reader, and `line_hash` equal or NULL → `seen`;
  - `missing_file` → `missing-file`; `out_of_range` → `out-of-range`;
  - current line hash ≠ `line_hash` (kept OR dropped by the reader) → `changed`;
  - **a `reader_rule` drop whose line hash equals `line_hash`, or whose `line_hash` is NULL,
    enqueues NOTHING.** The row is healthy; the reader asked a different question (16.1 R8:
    `-i`-taught rows are dropped for a case-sensitive `rmx grep` by design).
- **The drain** runs in plan-23's bounded `bind(partition_name)` drain (23.1). A pre-step OUTSIDE the lock
  re-checks each candidate: `missing-file`/`out-of-range` are re-stat'ed (a transient read error
  does not mark); `changed` candidates go through R2's `verify` under the row's OWN readings. Then,
  inside the batch: `seen` and a `changed` that R2 calls `ok` set `last_verified_at`; a
  re-confirmed `missing-file`, `out-of-range`, or a `changed` that R2 calls `stale-line` adds 1 to
  `stale_seen` and sets `last_mark` to that verdict. `unverifiable` writes nothing and is counted
  by reason.
- Nothing is deleted. `stale_seen` is never a removal trigger here.
- **The marks have a named reader (b-3, option (a)).** {#r4-reader} Plan-22's 22.1 READS them
  ([[task-22.1-audit-classes#r1-marks]]): it orders its re-verification so rows with
  `stale_seen > 0` or a non-NULL `last_mark` are verified first, lists each marked row with its
  `last_mark` and `stale_seen` in the plan manifest, and reports the `last_verified_at` age per
  class. A mark never decides a class: 22.1 re-verifies every row through R2 regardless, and the
  class comes from that run. `rmx learn status` prints the aggregate counts.
- **`stale_seen` is a LOWER BOUND (decision-log review #m-3).** {#r4-lower-bound} plan-23's queue
  coalesces by key and drops on overflow (with a counted overflow). A coalesced or dropped mark
  undercounts `stale_seen`, which can only DELAY a plan-22 removal, never cause one. The overflow
  count is printed by `rmx learn status` as `marks dropped (overflow): N`. The reading requirement
  on every consumer: `stale_seen` is used for ORDERING and REPORTING only, printed with the label
  "at least", never compared to a threshold, never an exact count; 22.1 states the same
  ([[task-22.1-audit-classes#r1-marks]]).

**R5. Provenance backfill (d6d Wave 1).** {#r5}
One idempotent routine, `backfill_learned_provenance(store, rows=None)`, run once as a migration
(a daemon op, through `bind(partition_name)` in bounded batches) and by R1b for the writer's own new rows:
- selects `linkage_evidence` rows with `detail LIKE 'learned from grep%'` that have no sidecar row;
- inserts, through `add_learned_provenance` (so each row also gets its `learned_provenance` event,
  R1d), `origin=backfill`, `source='grep-learn'`, `rules_sha=none`, `learned_at` NULL, `pattern`
  parsed from `detail` (`ast.literal_eval` of the `repr` tail; an unparsable detail is counted
  `unparsed_detail` and still gets a row with `pattern` NULL);
- sets `root` = the project root (the store root's parent) for project stores, and leaves it NULL
  in the global store. Repairing, moving or removing those rows (bug-086) is plan-22's (22.5 sets
  `root` on the rows it imports; 22.3 removes), not this task's;
- never computes `line_hash` (R3).
A second run inserts 0 rows and logs 0 events.

**R6. No silent failures.** {#r6} Every skipped, unreadable, unverifiable (per
`UNVERIFIABLE_REASONS`), unparsed, orphaned, unresolved-on-replay or overflowed row is counted per
reason and printed (`rmx learn status`, the backfill op's result, the merge's result, the rebuild's
result). Project rule: memory-path discipline applies to the store.

## Acceptance criteria {#acceptance}

1. **Key and readings.** A row taught under two readings (`-i` and none) has two sidecar rows with
   different `rules_sha`, both joining the one `linkage_evidence` row on the five identity
   columns. `add_learned_provenance` of the same key twice leaves one row and logs one event.
2. **Merge survival (s-r5-4).** Two slots, each with learned rows, one of whose entities is
   deduplicated (remapped) by the merge. After `replica_merge`, every sidecar row joins exactly one
   `linkage_evidence` row, the sidecar row count equals the distinct-key count of both inputs, and
   `stale_seen` is the max of the two inputs. Mutation "key the sidecar on `rowid`" and mutation
   "leave `learned_evidence` out of the merge's table lists" each FAIL it.
3. **The re-run verifier (b-r5-1, b-1, b-4).** Sidecar rows recorded as 16.1 R10 records them
   (`tool=grep`, `bin=/usr/bin/grep`; rg rows with the `rg` on PATH, resolved to an absolute path).
   Each row below must verify as stated, and `matching_lines` must return the stated set:
   - a. BRE `zzz\|alp` on a line `alpha` → `ok`; BRE `\(foo\)x` on `foox` → `ok`;
   - b. `-i` with `ALPHA` on `alpha` → `ok`;
   - c. `[[:digit:]]` on `a1` → `ok`; `\<foo\>` on `foo bar` → `ok` (both compile in Python and
     mis-match there);
   - d. **cutoff:** `match_argv=['-m','1']` (from `-l`), row line 2; line 1 is then edited to
     match too → row `ok`, and `matching_lines` = {1, 2};
   - e. **absolute-path exclude:** `match_argv=['-r','--exclude=*<parent-dir-name>*']`, the
     fixture file under a directory whose name the glob matches → `ok`;
   - f. **tool error:** a grep row with pattern `a\{` and an rg row with pattern `a{` (both exit 2,
     no output) → `unverifiable` with reason `tool-error`, kept, counted;
   - g. a row whose `bin` does not exist → `unverifiable` (`bin-missing`), kept, counted;
   - h. a two-reading row (`none` + `-i`) whose line matches only case-insensitively → `ok` (union).
   Pre-registered mutations, each FAILS this AC: "verify with `evidence_line_matches`" (a, c
   become `stale-line`); "replay `match_argv` whole" (d, e become `stale-line`); "map rc 2 to the
   empty set" (f becomes `stale-line`). No row in a-h may ever classify `stale-line`.

   **3b. The token filter is total.** `verify_argv` assigns every keep:match and keep:cutoff token of
   16.1 R1's table, for both tools, to exactly one of keep/drop; an unassigned token fails the test.
   Mutation "drop grep `-i` instead of `-S`" FAILS row b.

   **3c. The permissive reading names its subset.** A `none` row with pattern `foo\|bar` (or
   `[[:digit:]]`) → `unverifiable` (`permissive-subset`), never `stale-line`; a `none` row whose
   line holds `Foo_Bar` for the pattern `foo bar` → `ok` (identifier variant); a `none` row whose
   line no longer holds the text under any reading → `stale-line`. Mutation "drop the subset
   check" FAILS the first bullet.
4. **Reader-rule drops write nothing (s-r5-3).** An `-i`-taught row (`match_argv=['-i']`,
   `line_hash` = the current line's) read by a case-sensitive `grep_evidence` is dropped by the
   reader and enqueues NO candidate (queue file byte size unchanged). In the same fixture:
   - a row whose file was deleted → one `missing-file` candidate → after the drain
     `stale_seen == 1`, `last_mark = missing-file`;
   - a row whose line was edited but still matches its own rules → `changed` → after the drain
     `last_verified_at` set, `stale_seen == 0`;
   - a row whose line was edited so its own rules fail → `stale_seen == 1`, `last_mark =
     stale-line`.
   Mutation "mark every reader drop" FAILS the first bullet.
5. **Backfill (s-3: a sandbox test plus an operator census).**
   - **5a, sandbox test.** On a fixture store inside the 23.0 sandbox holding `learned from grep`
     rows, including a global-shaped fixture store (store root = the sandbox's redirected
     `~/.refmatrix`): the backfill leaves no learned evidence row without a sidecar row; the
     global fixture's rows have `root` NULL; every backfilled row has `line_hash` NULL; a second
     run inserts 0 and logs 0 events; an unparsable `detail` is counted, not skipped silently.
     Mutation "skip rows silently" FAILS it.
   - **5b, operator census (not a suite test; the 23.0 guard forbids a live store in pytest).**
     The operator copies each target store's lock-free read snapshot `catalog.read.duckdb` with
     `cp` into a short tmp dir off every watched tree (the procedure of
     [[task-23.4-option-a-measurement#r1]]: never the writer slot, no `Store()` on a live root, no
     `rmx` call, no socket), records the snapshot's mtime and size, runs the backfill on the copy
     through a sandbox daemon, and logs counts (rows, sidecar rows inserted, `unparsed_detail`,
     global rows with `root` NULL) to `workflow/review-output/16.6-backfill-census.log`, cited in
     the implementation summary. The census is a measurement, not a gate.
6. **No window before 16.1 (R1b; m-6).** After this slice, a `learn_from_grep` op on a tmp store,
   run twice with the same hits, writes evidence rows (duplicates included: `add_evidence` is still
   an unconditional INSERT until 16.1) and one `legacy-writer` sidecar row per DISTINCT evidence
   identity (the five columns); a query for learned evidence identities with no sidecar row
   returns 0. Mutation "remove R1b's call" FAILS it.
7. **Bounded drain.** 1,000 marks drain in ⌈1000/N⌉ batches under plan-23's lock-hold probe
   (23.2's fixture), each hold within the bound. Mutation "write the mark inline under
   `_store_lock`" FAILS it (the probe sees a hold on the read path).
8. **Overflow is counted (#m-3).** Enqueueing past the queue cap leaves `rmx learn status` printing
   `marks dropped (overflow): N` equal to plan-23's overflow counter.
9. **Rebuild keeps provenance (b-2).** Write learned rows with sidecar rows under two readings,
   then apply `move_learned_provenance` to one identity, then run `rebuild_index_from_log` on a
   sandbox COPY of the store: the sidecar after the rebuild equals the sidecar before it on every
   column except the three mark columns (which are NULL/0, counted `marks_reset`), and the moved
   row sits at its new identity. The same holds through `_apply_event_body` replay. Mutations "no
   `learned_provenance` event" and "no `learned_provenance_move` event" each FAIL it.
10. Mutations that must FAIL a test, each with its AC above: sidecar on `rowid` (2); sidecar not
    merged (2); Python `re` verifier (3); `match_argv` replayed whole (3); rc 2 read as no-match
    (3); filter drops a pattern token (3b); permissive subset check removed (3c); mark every
    reader drop (4); backfill skips silently (5a); remove R1b (6); inline mark (7); overflow
    uncounted (8); no provenance event (9); no move event (9).

The audit/prune/repair acceptance moved to plan-22. {#acceptance-moved}

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/duckdb_catalog.py` | `learned_evidence` DDL + primary key |
| `src/refmatrix/store.py` | `add_learned_provenance` (+ `learned_provenance` events); `move_learned_provenance` (+ `learned_provenance_move` event); both ops in `_apply_event_body` and in `rebuild_index_from_log`'s pass; `verify_evidence_rows` stats split (`missing_file`, `out_of_range`, `reader_rule`); `grep_evidence` enqueues R4 candidates for learned rows |
| `src/refmatrix/learned_verify.py` (new) | R2: `Rules`, `Unverifiable`, `UNVERIFIABLE_REASONS`, `verify_argv`, `matching_lines`, `permissive_matching_lines`, `hash_line`, `verify` |
| `src/refmatrix/replica_merge.py` | table lists + the sidecar step (R1c) |
| `src/refmatrix/daemon.py` | R4 drain consumer (pre-step + batch apply) on plan-23's drain; R5 backfill op; R1b call in `_learn_grep_hits` |
| `src/refmatrix/cli.py` | `rmx learn status`: mark counts ("at least"), overflow, unverifiable-by-reason/unparsed counts |
| `tests/test_learned_evidence.py` (new) | AC-1, AC-2, AC-4..9 |
| `tests/test_learned_verify.py` (new) | AC-3, AC-3b, AC-3c |

## Test strategy {#test-strategy}

- **Sandbox (d1a/d1b).** Every test runs inside task 23.0's shared sandbox: `$HOME`, the global
  root, the registry and the LaunchAgents dir point at a tmp dir before `refmatrix` is imported;
  store roots are injected; spawned `rmx` children refuse sockets outside the tmp dir; the conftest
  guard fails any test touching `~/.refmatrix` or a registered live store. Stores live under a
  SHORT `mkdtemp()` root.
- Real `Store`, real `Daemon`, real `/usr/bin/grep` and `rg` for R2 (skipped with a printed reason
  when absent). The rebuild AC runs on a COPY made inside the sandbox.
- **Census (s-3).** No test reads a live catalog. AC-5b is an operator step on a `cp` of the
  `catalog.read.duckdb` snapshot (23.4 R1's procedure), logged under `workflow/review-output/`;
  every AC that gates is a sandbox fixture test.
- The drain ACs use plan-23's 23.2 lock-hold fixture, not a timer.
- Pre-registered mutations: [[#acceptance]] item 9.

## Decisions {#decisions}

- **d-a. Provenance lives in a SIDECAR table** {#d-a}. AMENDED in revision 6 (s-r5-4, b-r5-1,
  #t6-fixes): the key is the evidence row's five identity columns plus `rules_sha`, and the
  columns are R1's. *Original (2026-10-07, superseded):* `learned_evidence(evidence_rowid, source,
  learned_at, root, pattern, flags, last_verified_at, stale_seen)`. Ingest's `linkage_evidence` is
  untouched either way, so the migration is cheap and reversible.
- **d-b. Audit and prune run on demand; read-time verification records marks** {#d-b}. AMENDED in
  revision 6 (s-r5-3): the marks record staleness under the row's OWN rules, never the reader's
  filtering (R4). Nothing deletes automatically: no scheduled prune.
- **d-c. (moved to plan-22, and AMENDED by the user 2026-10-07: "don't delete moves, repair them
  if possible").** `prune --apply` removes the non-`ok` classes EXCEPT `moved`, which is
  re-pointed. {#d-c}
- *(original d-c, superseded):* `prune --apply` removes every non-`ok` class by default: `moved`,
  `stale-line`, `out-of-range`, `missing-file`, `duplicate` and `orphan-root`. `--class` narrows
  it. The dry run remains the default.
- **d-d. Scope** {#d-d}. AMENDED by d6d (user, 2026-10-14): Wave 1, after plan-23's 23.1, with no
  dependency on 16.1; the learn-time write is 16.1 R10. *Original (2026-10-07, superseded):*
  "inside plan-16, after 16.1".

**For the spec review (ch-bsd r7 #m-5) — ANSWERED by the user 2026-10-07:** `moved` is the one
class whose row could be re-pointed instead of deleted. The user's answer ("don't delete moves,
repair them if possible") made re-pointing the DEFAULT and moved it, with the whole engine, to
[[task-22.2-repair-then-remove]] R1. Kept here as history. {#d-c-review}

The read-time marks (d-b) are writes on a READ path, so they never take `_store_lock` inline. They
go through plan-23's queue and its bounded drain (the 0.72.3 lesson in
`project_grep_learn_wall_and_queue`). {#d-b-write-path}
