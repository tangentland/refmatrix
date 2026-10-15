---
gmd: "0.1"
id: bsd-plan16-22-spec-rereview-r4-878647c
title: "plan-16 + plan-22 spec re-review r4: every r3 blocker is answered and the recovered probe re-runs (reproduced, 18 <= 60), but 22.1's hash step deletes rows whose line was edited and still matches, and the periodic facts.log compaction erases the sidecar's provenance events and every protect source the plans rely on"
severity: BULLSHIT
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-rereview-r4-16.1-16.6-22.1-22.6
round: 8 (plan-16) / 4 (plan-22)
tags: [bsd, audit, spec-review, grep, provenance, removal, repair, bug-086, bug-107, facts-log, compaction, census, cross-plan]
---

# ch-bsd spec re-review r4: plan-16 (16.1-16.6) and plan-22 (22.1, 22.1a, 22.2-22.6) {#root}

**Commit reviewed:** `878647c`, branch `wave0-spec-reviews`. **Written:** 2026-10-14T14:14-0700.
The round-3 revision is `a820b22`, and `878647c` adds d9p-d9u. While this review ran, HEAD moved to
`bc06ee9` (`224495c` d9v/d9w; `bc06ee9` 23.0 isolation tiers). Neither commit touches a plan-16 or
plan-22 file. `src/` is unchanged since `b1c4324`, and every code line cited below was read at HEAD.

**Scope:**
- plan-16 and 16.1 / 16.6 (`#rev-round-3`). 16.2-16.5 are unchanged since r3.
- plan-22 and 22.1, 22.1a, 22.2, 22.3, 22.5, 22.4 (`#rev-round-3`), plus the NEW 22.6.
- `plan-review-2026-10-14` `#t9-approvals` (d9k-d9o), `#t11-approvals` (d9p-d9u) and `#t10-waves`.
- The prior review: [[bsd-plan16-22-spec-rereview-r3-6091648]].

**Method (all read-only):**
- **Transcript.** I extracted the `2026-10-07T09:31:35Z` Bash call (line 2686,
  `toolu_01AoQVrMA99DaazFFhpJEi53`) and its result (line 2687) from
  `b38025a7-964a-49ec-bdbf-8f7e34918303.jsonl` with `python3 -I`. I diffed the extraction against
  22.1a `#appendix-probe`, byte by byte and as a Python AST.
- **Probe re-run.** I made a `cp -p` of `~/.refmatrix/catalog.read.duckdb` (sha256 `70ce0415…34cd`)
  and of `~/.refmatrix/facts.log` into the scratchpad. On those copies I re-ran the extracted probe
  VERBATIM with `.venv-eval/bin/python -I`, plus a churn script for AC-5b's `C`/`M`. The walk read
  the real trees, and no `refmatrix` module was imported.
- **Logs and code.** I parsed both `facts.log` files, this repo's `rmxd.log` and its `cli.log`
  read-only. I read `sync.py`, `ingest.py`, `ingest_gmd.py`, `store.py`, `daemon.py`, `cli.py`,
  `discovery.py` and `launchctl.py` at HEAD.
- **Probes.** BSD `/usr/bin/grep` under `env -i LC_CTYPE=…`, `locale -a`, and `rg --help` (15.1.0)
  through a Python subprocess.

**No `rmx` call was made on purpose, but the rewrite hook ran two.** One shell `grep` (over plan
text) and one `rg --help` were rewritten by the PreToolUse hook into the deployed `rmx grep`. After
that I did every search with Python. I opened no `Store`, sent no daemon op, ran no suite, and
edited no source, test, plan, registry or ledger file.

rel: amends -> [[bsd-plan16-22-spec-rereview-r3-6091648]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]]

## Live evidence {#evidence}

### The recovered probe: source, re-run, and the AC-5b gate {#ev-probe}

**The source is right, but the quote is not byte-for-byte.** The transcript's Bash call at
`2026-10-07T09:31:35.988Z` writes to `global-relative-resolve-probe.log` with `tee -a`. Its result
at `09:31:53Z` reads `walked 972849 files in 14.4s` and
`{'verified@0': 563, 'cands@2': 152, 'verified@1': 476, 'verified@2': 48, 'cands@1': 518, 'cands@0': 417}`.
The same lines are in the committed log. The catalog it read was a `cp -L` of
`~/.refmatrix/catalog.read.duckdb` with mtime `02:29` local (`09:29Z`), taken at line 2658.

Compared with the heredoc body (1,962 bytes, sha256
`c096e7ae6bb5491d0856f18a6d848b75dd29a89111a46f2cd0f773bad195598a`), the appendix:
- omits the three import lines;
- drops the comment `# candidates: home-relative first, then suffix matches anywhere walked`;
- re-wraps two lines (the `SKIP` literal and the `if L and any(...)` line).

With the imports put back, the two parse to the SAME AST. The rules the spec states in
[[task-22.1a-provenance-free-classes#r1-probe]] are read correctly: the population SQL, the prune
set, the `$HOME/<rel>` candidate, `lstrip("./")`, case-sensitive `re.search`, the `re.error`
fallback and `splitlines()`. The defect is only the word "verbatim" ([[#m-1]]).

**The re-run today, verbatim, on a copy of the global read snapshot:**

| | probe 2026-10-07 | re-run 2026-10-14 | Δ |
|---|---|---|---|
| walked files | 972,849 | 973,158 | +309 (+0.03%; the spec says 973,157) |
| `verified@0 / 1 / 2` | 563 / 476 / 48 | 567 / 490 / 48 | +4 / +14 / 0 |
| `cands@0 / 1 / 2` | 417 / 518 / 152 | 418 / 534 / 153 | |
| population | 1,087 | 1,105 | +18 |

**The AC-5b bound, computed as specified:**
- `C` = 18 population entities with an `entity` or `evidence` event after `09:31:35Z`. All 18 were
  created after the instant: they are the +18 that joined the population. There are 0 tombstones.
- `M` = 12 entities with a candidate whose mtime or birthtime is later.
- `Σ|Δ_b|` = 18 ≤ 2·(18+12) = 60, so the verdict is **`reproduced`**.

**Can the gate fail?**
- **The bound can fail.** The worst case is about 2·1,105, and the bound is 60. A correct build
  still reads `drift` when a change is unobservable: a deleted candidate (the spec says so), an `mv`
  that keeps mtime and birthtime, a renamed directory, or a facts.log compaction after the instant
  ([[#b-2]], [[#m-2]]).
- **Neither verdict blocks, by design.** The census gates only on its output being complete, which
  is the r3 fix. The verdict is information for the user beside 22.5's dry run.
- **So r3 b-1 is closed.** The census can pass on correct code, it can fail on incomplete output,
  and the label can come out either way.

### The periodic facts.log compaction rewrites the log the plans replay {#ev-compaction}

- **What it emits.** `Daemon._compact_factslog_if_needed` (`daemon.py:2274`) runs every 1,800 s
  once the log passes 256 MiB. It calls `Store.dump_catalog_to_log` (`store.py:7210-7379`), which
  REPLACES `facts.log` with a snapshot. The snapshot holds only `linkage_type`, `entity`, `protect`,
  `noise`, `memory_content`, `link`, `evidence` and `track`. Each `protect` is emitted immediately
  after its own `entity` (`store.py:7272-7284`) and carries no `source`. No `tombstone`, `unlink`
  or `untrack` survives it.
- **This repo's `rmxd.log`.** It records compactions at 12:29:53, 13:00:18 and 14:00:44 today. The
  last one was 357,558,505 → 264,344,806 bytes. `facts.log`'s birth time is `Oct 14 14:00:18`. The
  current log holds 0 `tombstone`, 0 `unlink` and 0 `untrack` events. r3's "26 learned entities
  tombstoned 47 times" (cited in bug-107 and in 22.6 `#facts`) was counted between the 13:00 and
  14:00 compactions. It is no longer in the log.
- **Global store.** The log was last compacted at 2026-10-07T01:13:11 local (08:13Z, before the
  probe). It is 108 MB today against the 256 MiB threshold.
- **Protect adjacency.** In BOTH logs every `protect` event directly follows its own `entity`
  event: 2,255 of 2,255 here and 5,012 of 5,012 in the global log.

## Prior findings: status {#prior-status}

### The r3 findings {#prior-r3}

| id | status | evidence |
|---|---|---|
| b-1 (AC-5b gate unsatisfiable) | **closed** | Probe recovered; [[#ev-probe]] confirms the rules and re-runs it. The churn bound is computable and gives `reproduced` today, and the gate is completeness only. Residue: [[#m-1]], [[#m-2]] |
| b-2 (`grown`/`shrunk` deletes shifted rows) | **closed, with a new defect** | 22.1 R1 pairs rows and never tests membership. AC-5a-d use real deletion and insertion, with two mutations, and pass on the stated rule (checked by hand). But step 2's "hash on no line → `stale-line` regardless", which is MY r3 fix text, removes rows whose line was edited and still matches ([[#b-1]]) |
| b-3 (approved ADR entry points unowned; restore loses bodies) | **closed, with residue** | 22.6 R1/R2 own `forget`, `memory forget`, `memory bulk-forget`, `untrack` and `prune-noise --drop`. 22.2 R4 records whole entity rows and `memory_content`. 22.2 AC-4 compares path, tldr, meta and bodies, with two mutations. Plan-22 `#scope` and item 4 cite d9k. Residue: [[#s-4]], [[#m-6]] |
| s-1 (locale not recorded) | **closed** | 16.6 R1 `locale` is in `rules_sha`. R2 builds the env (recorded locale plus `PATH`; no `GREP_*`). There is `locale-missing`, AC-3i plus a mutation, and 16.1 R10 plus AC-15. Residue: [[#m-3]] |
| s-2 (clusters, arity) | **closed** | 16.1 `#r1-clusters` gives one expansion and records the expanded tokens. 16.6 `#r2-argv` consumes values, and AC-3b has arity rows plus two mutations. Residue: rg value letters ([[#m-4]]) |
| s-3 (subset not rare; `Unverifiable` → removal) | **closed** | The counts are cited in 16.6 and 22.1. 22.1a outcome 4 is `orphan-root:unverifiable`, with AC-5a plus a mutation. 22.2 R9, 22.5 bucket 5 and 22.3 R1 all keep it |
| s-4 (union AC cannot fail) | **closed** | 16.6 AC-3h and 22.1 AC-4b use `-F`/`-E` readings that disagree. `rules_sha` excludes the pattern, so both sets share one reading order and their matching readings sit at opposite ends. Both mutations bite |
| s-5 (sync and vacuum remove learned rows) | **partial** | d9o/d9p plus 22.6 R3-R6 and 16.6 R1e. But R4's GMD branch still purges the doc's whole GMD graph on every edit ([[#s-1]]), and several `purge_path` callers and non-`purge_path` removals are unclassified ([[#s-2]]) |
| s-6 (census procedure) | **partial** | 16.6 R7 gives one script and a read-only connection to the production function. But its `HOME` redirect empties every `Path.home()`-derived input, including the guard's deny set ([[#s-3]]) |
| m-1 (one replay pass; AC-9 state) | **closed** | 16.6 R1d and 22.2 R3 share one list and one order, including 22.6's `evidence_orphan_drop`. AC-9 seeds the evidence row first, and there is a third mutation |
| m-2 (contract details) | **closed** | `--no-config` is dropped, the types are defined, `no-rules` has triggers, and `split_lines` splits on `b"\n"` |
| m-3 (`out-of-range` two predicates) | **closed** | In 22.1 it is a label on leftovers (step 4). 16.6's per-row verdict feeds only the marks |
| m-4 (bucket 2 mixed) | **closed** | 22.5 R1 has buckets 2a and 2b, ruled separately |
| m-5 (plan-of-plans row 16) | **closed** | `878647c`: "yes (6)"; the stale 16.7-16.10 clause is gone |
| m-6 (rg on PATH) | **closed** | 16.6 R1 `bin` is never re-resolved. AC-3j has a fixture `rg` first on PATH |

### Partials carried into r3 {#prior-partials}

| id | status | evidence |
|---|---|---|
| plan-16 m-2 (plan-of-plans) | **closed** | as r3 m-5 |
| shared m-4 (vocabulary) | **closed** | `out-of-range` is single-sourced (r3 m-3); `UNVERIFIABLE_REASONS` is the same 7 names in 16.6 R2 and 22.1 R1 |
| plan-22 s-1 (escalated) / r1 b-4 | **closed** | through r3 b-1 |
| r1 m-7 (ADR "only") | **closed** | plan-22 `#scope` and item 4 cite d9k/d9o |

### The decisions since r3 {#prior-decisions}

| id | status | evidence |
|---|---|---|
| d9p (keep learned rows on ANY edit) | **closed in text** | 22.6 R4 names both edit branches; bug-107 is widened. Defects in how: [[#s-1]], [[#s-2]] |
| d9q (`memory forget` is an entry point) | **closed in text** | 22.6 R1: plan, then `--confirm`; `--yes` exits 2. `memory forget`'s `@click.confirmation_option` (`cli.py:12599`) IS its `--yes`. Gaps: [[#s-4]] |
| d9t (22.6 in Wave 1) | **closed** | 22.6 header and `#t10-waves` show `(22.5 ∥ 22.6)`. Plan-22 `#dependencies` is stale ([[#m-5]]) |

## New findings {#findings}

### BULLSHIT b-1: 22.1's hash step removes every hashed row whose line was edited but still matches; 16.6 calls the same row `ok` {#b-1}

**Spec:** 22.1 R1 set rule, step 1 ("A hashed row whose line is in `N` but whose hash differs is
NOT a fixed point") and step 2 ("Hashed rows … none → `stale-line` regardless of what else
matches"), plus the `stale-line` bullet ("… or a hashed row whose hash is on no line of `N`"). 22.2
R9 removes `stale-line`. Against it: 16.6 R4 / AC-4 bullet 2 ("a row whose line was edited but
still matches its own rules → `changed` → … `last_verified_at` set"), and 16.6 R3 (the hash "may
be used as an optional extra").

**What:**
- **The case.** A learned row `query/foo` sits at line 10, `x = foo()`. The line is edited in place
  to `x = foo(1)`.
- **What 22.1 does.** `N` still holds 10, but the hash differs. Step 1 rejects it, step 2 finds the
  hash on no line, and the row is `stale-line`. 22.2 then removes it.
- **Why it is everywhere.** 16.1 R10 records `line_hash` on EVERY learner row from Wave 2. Any edit
  to a hit line that keeps the pattern then deletes taught knowledge: an argument, a comment, a
  rename around the hit, or reformatting. That is the commonest edit there is.
- **The contradiction.** 16.6 judges the same row healthy, so the two halves of the one verifier
  contract disagree.
- **No AC sees it.** AC-2 swaps lines, AC-5b deletes a whole line, and AC-5c inserts lines.
- **Where it came from.** The rule is my r3 b-2 fix text, verbatim ("A hashed row whose hash
  appears on no line is `stale-line` regardless"). The revision applied it as written.

**Why it is bullshit:** a removal class whose premise ("hash gone = text gone") is false. It
deletes rows the pattern still holds, against [[feedback_decay_never_loses_knowledge]] and the
user's "don't delete moves, repair them".

**Fix (spec-only):**
- Make the hash a PAIRING key, never a staleness proof.
- Step 1: a row whose line is in `N` with no hash or an equal hash stays.
- Step 2: hashed rows pair by equal hash. One match → re-point. Several → `ambiguous`. None → fall
  through.
- Step 3: every row still unpaired, hashed or not, pairs in line order with the unclaimed lines.
- Step 4: only the rows left over are `stale-line`/`out-of-range`.
- AC-5b still holds: row 20 is the leftover.
- New AC-5e: hits `{10, 20}` hashed; line 10 is edited in place and still matches. The set is `ok`
  or `moved`, 0 rows are removed, and row 10 stays at 10. The mutation "hash on no line →
  `stale-line`" FAILS it.

rel: contradicts -> [[task-16.6-learned-row-validation#r4]]
rel: contradicts -> [[bsd-plan16-22-spec-rereview-r3-6091648]]

### BULLSHIT b-2: the periodic facts.log compaction drops the sidecar's provenance events and every protect `source`, and makes 22.2 R5's attribution call every protection `upsert` {#b-2}

**Spec:**
- 16.6 R1d: the sidecar is "replayable from `facts.log`". AC-9: "Rebuild keeps provenance".
- 22.6 R6 (d9o): `protect` events carry `source` "so user and learner actions stay
  distinguishable".
- 22.2 R5: existing protections are attributed `upsert` "iff every `protect` event for the name
  directly follows an `entity` event", and a `user`/`unknown` learned-only entity is NOT purged.
- Plan-22 `#open-after-revision` 9: "the `unknown` bucket is empty there".

**What ([[#ev-compaction]]):** no spec names `dump_catalog_to_log` or the compaction tick, which
ran three times today on this repo.
- **The sidecar.** The snapshot has no `learned_evidence` emitter. So after the first compaction
  following 16.6, `rebuild_index_from_log` rebuilds a store whose sidecar is EMPTY. Every learner
  row then loses its tool, argv, locale and hash for good. `marks_reset` will not count it, and
  `unresolved_provenance` will not see it. This re-opens 32dde06 b-2 through a production path.
  AC-9 never compacts.
- **The `source` field.** The snapshot re-emits `protect` without it, so 22.6 R6's field lasts only
  until the next compaction.
- **Attribution.** The snapshot writes every `protect` right after its own `entity`, so 22.2 R5's
  adjacency rule reads EVERY protection in a compacted log as `upsert`. That includes user
  protections: this repo's `cli.log` holds 2 `rmx protect` calls, both since compacted into the
  same shape. The "`unknown` = asserted" safety default can never fire on a compacted store.
- **Item 9 drew the wrong conclusion.** The 5,012/5,012 adjacency in the global log is the
  compactor's signature, not evidence that every global protection came from the learner.
- **22.1a AC-5b's `C`** parses `tombstone`/`unlink` events after the instant. A compaction after
  the instant erases them ([[#m-2]]).

**Why it is bullshit:** two approved guarantees (provenance survives rebuild; user protections are
distinguishable) are erased by an existing production rewriter that the specs never mention. The
safety rule that protects user-asserted entities from purge reads the compactor's output as
proof of the opposite.

**Fix:**
- **16.6.** `dump_catalog_to_log` emits one `learned_provenance` event per `learned_evidence` row
  (non-mark columns), after the evidence events. Add `store.py` (`dump_catalog_to_log`) to
  `#files-to-modify`. AC-9b: compact with `dump_catalog_to_log`, then rebuild; the sidecar is equal
  apart from the marks. The mutation "dump without `learned_evidence`" FAILS it.
- **22.6 R6.** The dump carries `source` on `protect` events. Any new event field these plans add
  has a dump clause and a compact-then-rebuild AC.
- **22.2 R5.** Attribute from `source` when present, and from `cli.log`/MCP argv (`protect` names)
  when recorded. NEVER use adjacency inside a compacted segment: the log's birth time and the
  daemon's compaction lines in `rmxd.log` mark that segment. Anything else is `unknown`
  (asserted). Fix item 9's text.

This changes how many learned-only entities 22.3 may purge (the 1,655 pytest-tmp entities are
learner-protected). If the stricter rule leaves them unpurgeable, the user should see that
number ([[#user-decisions]]).

rel: contradicts -> [[task-16.6-learned-row-validation#r1d]]
rel: contradicts -> [[task-22.2-repair-then-remove#r5]]
rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#a14-removal-scope]]

### SKETCHY s-1: 22.6 R4's GMD branch still runs `purge_path(abs)`, which purges the doc-id entity and every anchor concept at the path, and now on every edit {#s-1}

**Spec:** 22.6 R4 ("Both edit branches … call `purge_path(abs, keep_learned=True)`, which purges what
ingest derived from the file … and KEEPS [the learned rows and] the file entity they sit on"),
AC-5 (checks only the learned entity).

**What:**
- **What gets purged.** `purge_path` purges every entity whose `path` is the file
  (`store.py:5910-5926`). For a GMD doc that includes the doc-id `doc` entity and every `{#anchor}`
  `concept`, all with `path=str(path)` (`ingest_gmd.py:964-967`, `:1015-1018`).
  `purge_entity` unlinks both edge directions, so the inbound `rel:` edges from OTHER docs go too.
  Re-ingesting this doc does not re-create them; only re-ingesting the citing docs does.
- **Why it now fires on every edit.** The sync guard fires when a relpath-named `doc` entity exists
  (`sync.py:231`). R4 KEEPS the learned relpath entity, so for every learned GMD doc the guard
  fires on every edit from then on, where today it fires once per learn-then-edit cycle. This repo
  has 241 such docs (r3), and they are the plan and task specs, the most cross-linked files here.
- **Cost of each edit.** New ids, re-embedded vectors, and inbound edges lost until the citing docs
  change.

**Fix:**
- In the GMD branch, purge only the relpath entity's own ingest-derived rows. Never call
  `purge_path` on the GMD doc's entities.
- Make the guard skip a relpath entity whose remaining rows are all learned.
- AC-5b: after an edit of a learned GMD doc, the doc-id entity id and its anchor ids are unchanged,
  and an inbound `rel:` edge from a second doc survives. The mutation "`purge_path(abs,
  keep_learned=True)` in the GMD branch" FAILS it.

rel: contradicts -> [[task-22.6-removal-entry-points#r4]]

### SKETCHY s-2: removal paths 22.6 does not classify {#s-2}

**Spec:** plan-22 `#scope` table; 22.6 R3/R4 (sync's branches and `vacuum` only); d9o/d9p.

**What (call sites at HEAD):**
- **`ingest.py:1179-1180`.** The TWIN of sync's GMD legacy purge, on the `rmx ingest` path ("Mirrors
  the same guard in `sync._sync_paths`"). A re-ingest is not a deletion, yet it purges learned GMD
  rows with plain `purge_path`. That is either silent today, or a cleanup manifest (a removal)
  under R3's default.
- **`cli.py:8433-8434`.** `rmx sync --invalidate P` calls `purge_path` on files that exist.
- **`sync.py:209`.** The `not ap.exists() or not is_supported` branch also purges files that EXIST
  but have an unsupported extension. The learner gives `kind="doc"` to any non-code hit
  (`daemon.py:4322-4325`), and 100 of this repo's 706 learned entities have unsupported extensions
  (`.log` 70, `.json` 14, no extension 7). R3 calls this branch "deleted or ignored", which it is
  not.
- **`ingest_gmd.py:891-896`.** `--as-memory` runs a raw `DELETE FROM entities … kind='doc'`. It logs
  no tombstone (so a rebuild resurrects the row) and leaves links and evidence orphaned.
- **`store.py:1606`.** `merge_partition` deletes source entities and `memory_content`
  (`:1765`, `:1812`). It is a merge, the class d9o gave to the helix plan, but it is not listed.

**Fix:**
- R4 covers `ingest.py:1180`: the same guard, the same keep rule.
- R3's wording becomes "missing or ignored". An existing unsupported file keeps its learned rows,
  as d9p's "an edit is not a deletion" requires.
- `--invalidate` is listed as a re-ingest, so learned rows are kept.
- The `ingest_gmd` delete becomes `purge_entity` (tombstoned).
- `merge_partition` goes to the user ([[#user-decisions]]).

rel: contradicts -> [[plan-review-2026-10-14#t11-approvals]]

### SKETCHY s-3: 16.6 R7's `HOME` redirect empties every `Path.home()`-derived input, including the census guard {#s-3}

**Spec:** 16.6 R7 step 3 (`HOME="$T/home" RMX_HOME=… scripts/census_on_copy.py …`) and step 4 (the
audit hook denies "every store root in the registered daemon list"). 22.1a `#r1-applied`
(`candidate_trees`, `walk_prunes`, `home_base` "defaulting to `Path.home()`-relative values"),
AC-5b (passes `candidate_trees` explicitly, never `home_base`), and "the applied split is what 22.5
and 22.3 use". 22.3 R1 (census counts "must match" the live audit).

**What:**
- **The deny set is empty.** `launchctl.LAUNCH_AGENTS_DIR = Path.home() / "Library" /
  "LaunchAgents"` is bound at import (`launchctl.py:20`), and `discovery._roots_from_launchd`
  reads it (`discovery.py:70-83`). Under the redirect the registered-root list is EMPTY, so the
  guard denies nothing. Computing the list "before importing refmatrix" is not specified either:
  `HOME` is already redirected by then.
- **`home_base` defaults to `$T/home`.** Every readable-today attribute is then false, and the
  census's applied split moves bucket 3 (`home-readable`, held for d9b) into
  `orphan-root:unresolved` (removal) or `unverifiable`. That split is what 22.3 and 22.5 use, and
  22.3's comparison with the live audit diverges for a reason no `drift` explains.

**Fix:**
- The script takes the real home from `pwd.getpwuid(os.getuid()).pw_dir` before anything else.
- It derives the deny set from that home's LaunchAgents.
- It REFUSES a classifier census unless `--candidate-trees` and `--home-base` are explicit. It
  prints both in the log header.
- AC-5c gains two clauses, each with a mutation:
  - run with the redirect and no `--home-base` → exit nonzero;
  - the deny set is non-empty when a fixture plist exists.

rel: contradicts -> [[task-16.6-learned-row-validation#r7]]

### SKETCHY s-4: 22.6 R1's confirm contract cannot hold on a live store, and the daemon ops stay direct-delete {#s-4}

**Spec:** 22.6 R1 ("with `--confirm <sha256>`: rebuild the plan from the same selector; if its hash
differs … refuse"; files-to-modify: `cli.py`, `verbs.py`, `store.py`, `removal_audit.py`,
`sync.py`); 22.1a R4 (the plan manifest records "catalog identity (active slot + snapshot
version)"); AC-1 (refusal tested only for a second matching entity, on a quiet sandbox).

**What:**
- **The hash.** If the confirm hash covers the plan file as 22.1a R4 defines it, any write between
  plan and confirm changes the hash: a sync, a learn, an STM promote. This store's read snapshot
  rotated within the same minute as `facts.log`. On a live store `--confirm` then almost always
  refuses. The cheap way out an implementer will take is to drop fields from the hash; the spec
  should say which.
- **The ops.** `daemon.py` is not in 22.6's file list. The ops `forget` (`daemon.py:4384`, deletes
  when `dry_run` is false), `memory_forget` (`:5061`), `memory_bulk_forget` (`:5117`), `untrack`
  (`:4406`) and `prune_noise` (`:3899`) all stay direct-delete ops on the socket. A second removal
  path stays open below the CLI.
- **The fallback.** `rmx memory forget` falls back to `s = _store(); s.forget_memory(...)` when the
  daemon is down (`cli.py:12616-12619`). That is a direct write outside `removal_apply`, and R1 does
  not say to remove it.

**Fix:**
- The confirm hash = sha256 of the canonical selection: the selector plus the sorted member
  identities plus each member's row counts. No catalog version, timestamp or manifest id.
- AC-1b: an unrelated write between plan and confirm does NOT refuse. The mutation "hash the whole
  plan file" FAILS it.
- `daemon.py` joins the file list. The direct-delete ops are retired, or they accept only a
  confirmed plan id, and AC-1c sends a raw `forget` op with `dry_run=false` and expects refusal.
- The daemon-down fallback is refused, as every other write is.

rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-no-delete]]

### MEH m-1: the appendix is not the transcript's bytes, and the probe script runs outside "the ONE procedure" {#m-1}

- **Not byte-exact.** [[task-22.1a-provenance-free-classes#r1-probe]] and `#appendix-probe` say
  "verbatim", but the quote omits the imports and a comment and re-wraps two lines. It is
  AST-equal ([[#ev-probe]]). Either paste the 1,962-byte body exactly, or keep this form and record
  the source body's sha256 (`c096e7ae…598a`) with the line and tool-use id
  (`2686`, `toolu_01AoQVrMA99DaazFFhpJEi53`).
- **Outside the procedure.** 16.6 R7 says every census uses its procedure "and no other" and lists
  only production functions. 22.1a AC-5b item 1 runs `eval/spikes/global_relative_resolve_probe.py`.
  Either list it in R7 as `--census probe-reproduction`, or carve it out in writing.
- **No file list.** 22.1a has no `#files-to-modify` section: `removal_audit.py`, the spike script
  and the test file appear nowhere in its own spec. 22.6 is where `removal_audit.py` is named.

### MEH m-2: AC-5b's churn bound needs an uncompacted log, and its instant is the run, not the snapshot {#m-2}

- **Compaction.** `C` counts `tombstone`/`unlink` events and population leavers after the instant.
  A compaction after the instant erases both ([[#b-2]]). The global log has not been compacted
  since 2026-10-07T08:13Z, which is fine today. The census should print the log's birth time and
  the last compaction line from `rmxd.log`, and mark `C` as `undercounted (log compacted after
  the probe)` when one falls after it.
- **The instant.** The probe's catalog was the `09:29Z` snapshot. The instant should be that mtime,
  not the run time `09:31:35Z`. The 2.5-minute gap is negligible but should be named.

### MEH m-3: locale contract details {#m-3}

- **`UTF-8` is valid but not listed.** "Not in `locale -a` → `locale-missing`" misjudges a value
  `setlocale` accepts. `LC_CTYPE=UTF-8`, which macOS ssh and Terminal sessions commonly set, is
  absent from `locale -a` (288 entries; only `en_US.UTF-8` and `C.UTF-8` match). Yet
  `/usr/share/locale/UTF-8` exists, `env -i LC_CTYPE=UTF-8 /usr/bin/grep -c 'a.b'` on `a—b`
  prints 1, and C prints 0. Probe with `setlocale` in a child process, or with grep itself.
- **Two shapes, one hash.** 16.6 R1 stores `locale` as a JSON object. `Rules.locale` is a tuple of
  pairs. `rules_sha` is "canonical JSON" of either. Name one serialization (for example a
  `sort_keys` object, `separators=(',',':')`), so a sha recomputed from the column equals the
  stored key.
- **The queue record.** 16.1 R10's lead-in list of queue-record fields omits `locale`; only a
  sub-bullet defines it. The drain runs in the daemon, where the env is C. Add it to the list.

### MEH m-4: rg's short value letters miss `E` and `j` {#m-4}

- **What `rg --help` shows.** 16.1 `#r1-clusters` gives rg `e f g m t T A B C d M r`. `rg --help`
  (15.1.0, `/opt/local/bin/rg`) shows `-E ENCODING` and `-j NUM` too.
- **The effect.** `-Eutf8` expands to `-E -u -t f8`, which teaches under a wrong argv. `-j4` kills
  the teach.
- **The filter.** `-E/--encoding` is in neither of 16.6's rg keep/drop lists, so its arity is
  undefined there.

### MEH m-5: wave and test hand-over drift {#m-5}

- **AC-5 needs Wave 2.** 22.6 R4 "may land first" in Wave 1, but AC-5's last clause ("22.1's audit
  classifies the shifted row `moved`") needs 22.1, which is Wave 2. Use 16.6's `verify` verdict
  there, or move the clause to 22.1.
- **A test that will start failing.** 16.6 AC-11 asserts that `purge_path` and `vacuum` LEAVE the
  sidecar row. 22.6 R3/R5 deliberately change that, and no task retires or rewrites AC-11's test.
- **Stale order.** Plan-22 `#dependencies` still gives the Wave-1 chain without 22.6 and says
  "`#t10-waves` does not list 22.6 yet". That stopped being true at d9t.

### MEH m-6: 22.6 R7 / AC-8 name a command that does not exist {#m-6}

There is no `rmx fold-concept-dups`. The surface is `rmx memory dedup` (`cli.py:12628` →
`fold_concept_dups`) and MCP `rmx_memory` action `dedup` (`verbs.py:1029`).

## Cross-plan consistency {#cross-plan}

**Consistent at `878647c`:**
- `learned_verify` and its exact signatures: 16.6 R2, used by 22.1 R1-verify and 22.1a R1.
- `UNVERIFIABLE_REASONS`, the same 7 names in 16.6 R2 and 22.1 R1.
- `removal_audit.classify_provenance_free` / `classify_flag_sensitive`: 16.6 R7, 22.1a R3, 22.1 R5.
- `removal_audit.py` as 22.1a's module, named in 22.6.
- `scripts/census_on_copy.py`, owned by 16.6 R7 and cited by anchor from 22.1, 22.1a and 22.3.
- One replay list: 16.6 R1d = 22.2 R3, with 22.6's `evidence_orphan_drop`.
- The store-root spelling: 22.2 R8 vs 16.6 R7's `<store_root>/catalog.read.duckdb`.
- Every cited `src` line number (spot-checked 22 of them).

**Conflicts:**
1. 22.1 step 2 against 16.6 R4 / AC-4 ([[#b-1]]).
2. 16.6 R1d and 22.6 R6 against `dump_catalog_to_log` ([[#b-2]]).
3. 16.6 R7's redirect against 22.1a's `Path.home()` defaults ([[#s-3]]).
4. 16.6 R7 "no other" against 22.1a AC-5b's spike script ([[#m-1]]).
5. 16.6 AC-11 against 22.6 R3/R5 ([[#m-5]]).
6. 16.1's rg value letters against `rg --help` ([[#m-4]]).

## User decisions needed {#user-decisions}

1. **(b-2) How to attribute existing protections once the log has been compacted.** The spec fix
   is "`source`, else argv logs, else `unknown`". Under it, learner-protected learned-only entities
   with no surviving evidence (the 1,655 pytest-tmp entities among them) may be classed `unknown`
   and so never purged. Their learned rows would still be removed. The alternative is to accept
   that a user protection in a compacted segment is indistinguishable, and say so in the ADR. The
   user should see the count under each rule before choosing.
2. **(s-2) `merge_partition`.** Is it a merge entry point owned by the helix plan, as d9o made
   `fold_concept_dups`, or a listed exception?
3. **(d9b, unchanged)** the no-owner global rows, after 22.5's dry run.

## Verdict {#verdict}

**Plan-16: NEEDS-REVISION.**
- 16.2-16.5 stay approvable.
- 16.1 needs [[#m-3]] and [[#m-4]] (small).
- 16.6 needs [[#b-2]] (the dump emitter plus AC-9b) and [[#s-3]]. Its verifier contract stands
  (r3 s-1, s-2, s-4 closed).

**Plan-22: NEEDS-REVISION.**
- 22.1 needs [[#b-1]].
- 22.2 R5 and open item 9 need [[#b-2]].
- 22.6 needs [[#s-1]], [[#s-2]], [[#s-4]], [[#m-5]] and [[#m-6]].
- 22.1a needs [[#m-1]], [[#m-2]] and [[#s-3]]'s census inputs.
- 22.3, 22.4 and 22.5 hold.
- The recovered probe is real, re-runs to `reproduced` (18 ≤ 60), and its gate is satisfiable on
  correct code.

| | r3 closed | partial | open | new B | new S | new M |
|---|---|---|---|---|---|---|
| plan-16 | s-1, s-2, m-2, m-6 + 1 prior | 0 | 0 | 0 | 0 | 2 (m-3, m-4) |
| plan-22 | b-1, b-2, b-3, m-3, m-4 + 3 prior | 0 | 0 | 1 (b-1) | 3 (s-1, s-2, s-4) | 3 (m-1, m-5, m-6) |
| shared | s-3, s-4, m-1, m-5 + 1 prior | 2 (s-5, s-6) | 0 | 1 (b-2) | 1 (s-3) | 1 (m-2) |

**Totals.**
- **r3 ids:** 13 closed, 2 partial, 0 open.
- **Prior partials:** 5 closed.
- **Decisions:** d9p, d9q and d9t are closed in text.
- **New:** 12 findings, 2 BULLSHIT, 4 SKETCHY, 6 MEH.

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 878647c (SPEC re-review r4: plan-16 16.1/16.6 round 3 + plan-22 22.1/22.1a/22.2-22.5 round 3 + NEW 22.6, pre-implementation; d9p-d9u; HEAD moved to bc06ee9 mid-review, no 16/22 file touched; written 2026-10-14T14:14-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 12 new (2B/4S/6M); r3 ids 13 closed 2 partial (s-5, s-6) 0 open; prior partials 5 closed; d9p/d9q/d9t closed in text | [[bsd-plan16-22-spec-rereview-r4-878647c]]: recovered probe confirmed against transcript line 2686 (AST-equal; appendix not byte-exact) and re-run verbatim on a global read-snapshot copy: walked 973,158, verified 567/490/48 vs 563/476/48, C=18 M=12, Σ|Δ|=18 <= 60 -> reproduced; gate satisfiable, completeness-only. BULLSHIT: 22.1 step 2 "hash on no line -> stale-line" (my r3 fix text) removes every hashed row whose line was edited but still matches (16.6 R4 calls it ok); periodic facts.log compaction (dump_catalog_to_log, 3x today here, birth 14:00:18) emits no learned_evidence/no protect source and writes every protect after its entity, so the sidecar dies on rebuild-after-compaction and 22.2 R5 attributes ALL protections upsert (2,255/2,255 here, 5,012/5,012 global). SKETCHY: 22.6 R4 GMD branch purge_path purges doc-id + anchors + inbound rel: edges on every edit; unclassified removals (ingest.py:1180 twin, sync --invalidate, exists-but-unsupported branch 100/706 learned, ingest_gmd raw DELETE, merge_partition); census HOME redirect empties LaunchAgents deny set and home_base; confirm hash vs live writes + daemon forget/memory_forget/bulk_forget/untrack/prune_noise ops stay direct-delete. Read-only; copies in scratchpad; two hook-rewritten rmx grep calls noted. |
```

last_run.log line:

```
2026-10-14T14:14:39-0700 commit=878647c verdict=DIRTY findings=12 (2B/4S/6M) report=2026-10-14-1414-plan16-22-r4-spec-rereview-hash-proof-deletes-edited-rows-and-compaction-erases-provenance-878647c.md
```

IMPRESSIONS.md bullets:

```
- plan-16/22 r4 (878647c): my own r3 fix text ("hash on no line -> stale-line") became a removal rule that deletes every edited-but-matching row. Before handing a fix, run it against the commonest edit (change a hit line in place), not only the edit that motivated it.
- Any spec that says "replayable from facts.log" must name dump_catalog_to_log: the daemon compacts the log every 30 min past 256 MiB (3x today here) into a state snapshot with no tombstones, no new tables and protect-after-entity adjacency. Check the compactor's emitter list for every new event or field.
- A census that redirects HOME blinds every Path.home()-bound module constant (launchctl.LAUNCH_AGENTS_DIR); ask which inputs are bound at import before trusting a redirected guard.
```
