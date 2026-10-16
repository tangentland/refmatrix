---
gmd: "0.1"
id: bsd-plan16-22-spec-diffcheck-r11-d8188ee
title: "plan-16 + plan-22 spec diff check r11: round 10 (d8188ee) closes all 7 r10 findings. Plan-16 is approval-ready. d9cb(b), the c-match rule, is not in the 22.6 text, and as decided it closes 1 of 4 restore re-attach shapes. The entity_rename fold rule claims links move, R3 replay says they do not, and AC-6d holds no rename log."
severity: SKETCHY
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-diffcheck-r11-16.3-16.6-22.2-22.6
round: 15 (plan-16) / 11 (plan-22)
tags: [bsd, audit, spec-review, diff-check, vacuum, orphan-drop, restore, reattach, fold-ops, d9bz, d9cb]
---

# ch-bsd r11 diff check: plans 16 and 22 after revision round 10 (`d8188ee`) {#root}

**Commit reviewed:** HEAD `d8188ee` on `wave0-spec-reviews`, diffed against `451b505` for
`workflow/plans/plan-16-*` and `plan-22-*` (6 files, +315/-111). `src/` unchanged since `23ad703`;
master is `b381b6d`. **Written:** 2026-10-15T04:24-0700.

**Method (read-only):**
- I checked every r10 finding and decisions d9bz and d9cb against the text at HEAD.
- I ran four probes from `scratchpad/r11/` with the DEPLOY interpreter
  (`~/refmatrix/.venv/bin/python -I`). They used the r10 scratch copies:
  - cliquedb: the r6 catalog with the 04:01 log;
  - refmatrix: the 00:25 catalog+log pair.
- The probes:
  - `ownapp.py` runs the own-appends rule (`#r5-own-appends`) and the revivable predicate on the
    real copies, and also measures d9cb(b) and d9cb(c);
  - `reattach_model.py` is an event-model fixture of the vacuum and the rebuild under three rule
    sets: d9bz, d9bz + d9cb(b), and the fix below;
  - `ac12.py` is 16.6 AC-12's scan as specified, run over HEAD and a fixture tree.
- GMD lint on the 15 plan-16/22 files: 0 errors.

**Nothing changed:** no store or socket was opened, no spec or source was edited, and nothing was
committed.

rel: amends -> [[bsd-plan16-22-spec-diffcheck-r10-451b505]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5-own-appends]]
rel: contradicts -> [[task-22.2-repair-then-remove#files-to-modify]]

## Round-10 findings: status {#prior-status}

| r10 id | status | evidence at HEAD |
|---|---|---|
| s-1 (`names_from_log` cannot name a both-dead concept) | **closed** | <ul><li>22.6 `#r5-own-appends` keys every drop on the orphan's own revivable appends.</li><li>`names_from_log` and `_row_op_c_kinds` are off the vacuum path.</li><li>AC-6c is rewritten: (a), (b), (c), the kind variant and three mutations.</li><li>16.6 AC-9d check 2 lists the vacuum scan as a caller.</li><li>d-30 is reworded.</li></ul> |
| s-2 (dead-at-`T` misses re-creation before the vacuum) | **closed** | <ul><li>`#r5-timeline` uses the tombstone-after-copy predicate in both the scan and the rebuild.</li><li>The AC-6b swapped and today's-shape variants are present, with mutations.</li><li>d-28 is amended.</li></ul> Residue: [[#s-1]]. |
| s-3 (`FOLD_OPS` rows named no fold rule) | **closed for the evidence ops** | <ul><li>All three rows state a rule.</li><li>AC-6d is present, and each of its three mutations fails on its named fixture (traced in [[#ac6d]]).</li></ul> Residue: [[#s-2]] (rename and re-point). |
| m-1 (scan key, key-only load) | **closed** | `#r5-scan` names the key, the DISTINCT load, the timelines in the same pass, and the streaming manifest. |
| m-2 (the helper's `n` and partition) | **closed** | <ul><li>22.2 `#r3` covers the partition and "identical" by name.</li><li>The helper raises on an orphan row (this is d9cb(d)).</li><li>d-31 is updated.</li></ul> |
| m-3 (AC-12 could not see docstrings) | **closed, and it can fail** | See [[#ac12]]. |
| m-4 (16.3 merge order, the test half) | **closed** | <ul><li>16.3 R5 carries the `SCRIPTS` edit and the not-rendered assertion.</li><li>master is still `b381b6d`, as the text says.</li></ul> |

**Totals:** 7 of 7 closed.

**d9bz:** fully in the text.

**d9cb:**
- (a) per-op counting is in the text (`#r5-timeline`), but cited as r10 s-2, not d9cb.
- (d) is in the text (22.2 `#r3`).
- **(b) the c-match rule is absent from every plan-22 file** ([[#s-1]]).
- (c), the narrow legacy-drift acceptance, is absent ([[#m-1]]).
- Neither 22.6 nor plan-22 cites d9cb.

## Probes {#probes}

### The own-appends rule on the real copies (`ownapp.py`) {#own-appends-real}

| | cliquedb | refmatrix |
|---|---|---|
| orphan keys / rows | 4,404 / 7,599 | 66,239 / 834,201 |
| matched `evidence` appends | 2,387 | 55,242 |
| revivable (a tombstone of the entity key after the append) | **0** | **0** |
| drops logged | 0 | 0 |
| `orphan_drop_unresolved` | 0 | 0 |
| `orphan_drop_unlogged` | **4,404** (every key) | **66,239** (every key) |
| wall / peak footprint | 1.0 s / 155 MiB | 2.8 s / 684 MiB (the probe also loads live copies) |

**Reconciles with r10:**
- The matched appends equal r10's 2,387 / 55,242.
- 0 are revivable, which is r10 `reborn_e.log`'s "0 have a later tombstone".
- On cliquedb, 2,336 matched appends name an entity that is live now and holds the identical copy (live holders); the other 51 name an entity that is not in the catalog. All 55,242 refmatrix appends are live holders.
- So under d9bz the vacuum logs NO drop on either store today and counts every orphan key unlogged. That is the d9bz memo's expectation.
- The "today's shape" variant of AC-6b is the real shape.

### d9cb(c): legacy-kind drift {#legacy-drift}

**Every** `evidence` append in both logs is legacy (no `c_kind`): 66,100 / 66,100 on cliquedb, 253,023 / 253,023 on refmatrix. Both logs predate 0.78.3.

For every one of them, `resolve` over the kinds logged up to the append equals `resolve` over the kinds at the end of the log: **0 drifts** on either store, and 0 on orphan keys.

d9cb(c)'s "narrow" holds on today's data. Today it applies to zero revivable appends anyway.

### d9cb(b): the 22.2 R4 restore re-attach case (`reattach_model.py`, `ownapp.py`) {#reattach}

**The shape.**
1. Entity `E` appends a row `a0`.
2. A non-engine purge (`untrack`) tombstones `E` and leaves the row orphaned.
3. `removal_restore` re-creates `E` and, through 22.2 R4's `id_map`, updates the SURVIVING row in place, with **no new append** (by design: "a second `evidence` event would double the row").
4. Later, `vacuum` finds a different orphan `X` on the same key `(linkage, file, line, detail)`.

`a0`'s entity key has a tombstone after it, so `a0` passes the revivable predicate. The vacuum logs a drop keyed on `a0`'s `(c_kind, c)`, and the rebuild then deletes `E`'s re-attached copy, which live holds.

**Model results** (rebuild compared with live, by name):

| fixture | d9bz | d9bz + d9cb(b) | fix ([[#s-1]]) |
|---|---|---|---|
| F1: re-attach; orphan `X` (logging off) on a DIFFERENT live concept | DIFF (rebuild 0, live 1) | EQUAL | EQUAL |
| F2: re-attach; orphan `X` on the SAME live concept (the relpath/abspath doc-pair shape) | DIFF | **DIFF** | EQUAL |
| F3: re-attach; orphan on the key is both-dead (d9cb(b) does not apply) | DIFF | **DIFF** | EQUAL |
| F4: re-attach, plus a legit purged `X'` on the same key and concept, whose drop is correct | DIFF | **DIFF**: the drop matches every revivable copy of `(c, key)`, `E`'s included | EQUAL |
| L1: AC-6b base (purge, vacuum, re-ingest) | EQUAL | EQUAL | EQUAL |
| L2: AC-6b swapped (purge, re-ingest, vacuum) | EQUAL | EQUAL | EQUAL |
| L3: AC-6c(a), both-dead, `N` re-created without an append | EQUAL | EQUAL | EQUAL |

**Real-data exposure.**
- Re-attach shapes today: **0** on both stores, because no matched append is revivable.
- The keys are widely shared, though. Every live-holder append that sits on an orphan key becomes F2/F3 the moment its entity is untracked and restored:

| live-holder appends on orphan keys | cliquedb | refmatrix |
|---|---|---|
| `c` equals an orphan's live concept (d9cb(b) cannot exclude them) | 194 | 46,320 + 798 |
| `c` differs from every live concept, but the key also holds a both-dead orphan (d9cb(b) does not apply) | 2,142 | 698 |
| `c` differs, live-concept orphans only (d9cb(b) closes these) | 0 | 7,426 |

So d9cb(b) would protect 0% of cliquedb's exposure and about 13% of refmatrix's.

### 16.6 AC-12 can fail (`ac12.py`) {#ac12}

**Over HEAD (before R1f), the scan as specified reports 17 hits:**
- `daemon.py:516,522,523`;
- `store.py:2531,7696,7755,7765,7772,7773,7775,7792,7842,7849,7856`;
- AST hits `tests/test_bug117_rebuild_non_concept.py:112,121` and
  `tests/test_memory_content_log.py:1` (the module docstring, a `Constant` node).

Every one of them is on R1f's delete or rewrite list. The scan's own module is excluded, and it holds the name list. The 0-hit claim for `scripts/` and `eval/` holds.

**The fixture-tree self-check** finds three hits:
- the text `def apply_log_delta`;
- the AST attribute `dst.apply_log_delta`;
- the AST constant naming `_apply_one_event`.

The excluded module, which holds the names, stays silent. The check is not vacuous.

### AC-6d on its named fixtures {#ac6d}

I traced the fold rules as written against the rebuild rules:
- "the fold ignores `evidence_remove`" gives 2 copies on 22.2 AC-3d's learned fixture against the rebuild's 1, so it fails;
- "the fold ignores `evidence_orphan_drop`" gives one copy too many on AC-6b base, so it fails;
- "the fold drops on dead-at-`T`" keeps the T0 copy on the swapped variant (2 against 1), so it fails.

The fold and the rebuild apply the same predicate, so fold == rebuild holds on the named logs. The gap is the ops the named logs do not hold ([[#s-2]]).

## New findings {#findings}

### SKETCHY s-1: d9cb(b) is decided but not written, and as decided it closes only F1 {#s-1}

**File:** `workflow/plans/plan-22-audited-removal-and-repair-tasks/task-22.6-removal-entry-points.md`, [[task-22.6-removal-entry-points#r5-own-appends]].

**What:**
- d9cb(b) says that when the orphan's concept is live, the scan also requires the append's `c` to match it. That rule appears nowhere in 22.6, plan-22 or the d-table.
- Even if added, it fails F2, F3 and F4 ([[#reattach]]). In F2 the orphan shares the concept; that is the dominant shape, 47,118 of refmatrix's 55,242 live-holder appends. In F3 the key holds a both-dead orphan, so the rule does not apply. F4 shows that the rebuild's drop matches every revivable copy of `(linkage, c_kind, c, file, line, detail)`, so even a correctly logged drop deletes a re-attached holder's copy.

**Why it matters:**
- Today there are 0 such rows, so nothing breaks now.
- From the day 22.6 R2's `untrack` and 22.2's `removal_restore` ship, an untrack, then a restore, then the nightly vacuum produces a rebuild that holds fewer rows than live.
- AC-9c (restore re-attach) and AC-6 never meet in one fixture, so no AC catches it.

**Fix: two clauses in `#r5-own-appends`, plus an AC.**

**(i) Replace "The vacuum logs ONE drop per DISTINCT `(partition field, c_kind, c)` among them:" with:**
> The vacuum logs ONE drop per DISTINCT `(partition field, c_kind, c, e_kind, e)` among them. The entity end comes from the append itself (its old incarnation's name). The rebuild matches the drop on the full `edge_records.row_key` plus `detail`, so a drop never touches another entity's copy on the same key (d9cb(b), r11 s-1 F4).

Then make the matching edits:
- in R5's first bullet: "its end is null" becomes "its end is the matched append's `(e_kind, e)`";
- in `#r5-timeline`: "whose `(linkage, c_kind, c, file, line, detail)` matches" becomes "whose `row_key` and `detail` match";
- in 16.6's `ROW_OPS` row: delete "(the one op with a null entity end)";
- in 22.6 files-to-modify, the `edge_records.py` row: delete the same words.

**(ii) Replace d9cb(b)'s c-match with a count guard. Add as a new bullet after the `c_kind` bullet:**
> **A copy a restore re-attached is not revivable (d9cb(b), r11 s-1).** For a matched revivable append whose entity key `(partition, e_kind, e)` is LIVE now, the scan compares two counts. `L` is the number of copies identical to the append (same `linkage`, `c`, `file`, `line`, `detail`) that the live entity of that name holds. `N` is the number of that key's matched appends with no tombstone after them. When `L > N`, the surplus copy is one 22.2 R4's `id_map` re-attached in place with no new append ([[task-22.2-repair-then-remove#r4]]). The append is not collected, and it is counted `orphan_drop_reattached` and printed. The catalog lookup is bounded by the matched appends.

**(iii) Add AC-6e:**
> **6e. A restore's re-attached row survives a later vacuum (r11 s-1, d9cb(b)).**
>
> **Setup:** doc `E` holds a `rel:` evidence row to doc `C` (an ingest row, so no `keep_learned` exemption applies). `rmx untrack` of `E`'s file orphans it, and `removal restore` of that manifest re-attaches it (22.2 R4, AC-9c's path; no new append). A second entity `X` holds an identical-key row on the SAME concept `C`; it was written with logging off and then raw-deleted, so `X`'s row is an orphan.
>
> **Run and assertions:**
> - `vacuum` deletes `X`'s row, logs no drop and prints `orphan_drop_reattached: 1` and `orphan_drop_unlogged: 1`.
> - A rebuild on a copy holds `E`'s row once, equal to live.
>
> **Variant:** the same, but a third entity `X'` (logged, then purged with a tombstone) also holds the key on `C`. `vacuum` logs one drop keyed `(…, e: X')`, and the rebuild holds `E`'s row once.
>
> **Mutations, each FAILS it:**
> - "drop without the entity end": the variant loses `E`'s row;
> - "no `L > N` guard": the base loses `E`'s row;
> - "d9cb(b)'s c-match only": the base loses `E`'s row, because `X` shares `C`.

d-30 then gains: "keyed on the matched append's entity end too; a re-attached copy (`L > N`) is not collected, counted `orphan_drop_reattached` (d9cb(b), r11 s-1)".

**Pattern match:** YES. This is the fourth round in which the vacuum drop's key has been too coarse in one dimension: concept (r9), timeline (r10), entity (r11).

rel: contradicts -> [[task-22.6-removal-entry-points#r5-own-appends]]
rel: depends-on -> [[task-22.2-repair-then-remove#r4]]

### SKETCHY s-2: the `entity_rename` fold rule asserts link moves that R3's replay does not make, and AC-6d holds no rename or re-point log {#s-2}

**File:** `task-22.2-repair-then-remove.md` [[task-22.2-repair-then-remove#files-to-modify]] (the `factslog-restore.py` row) and 22.6 AC-6d.

**What the spec says, in three places:**
- The fold rule: `entity_rename{merged}` "merges the two keys as `rename_entity` does: the entity count drops by one once the old key has no link left, and its links and evidence count under the surviving key".
- 22.2 R3 (`:225`): "On replay, `evidence_repoint` and `entity_rename` move only `linkage_evidence` rows".
- R2: no `link` / `unlink` event is specified for a merged rename's re-attached links.

**Why it matters:**
- **Links.** On a merged rename, the fold moves the links and the rebuild does not, so either the fold or the rebuild is wrong about links.
- **Entities.** The old entity is purged by `_bulk_purge_ids`, which logs a tombstone. A fold that also "drops the entity count by one" on the rename counts the removal twice.
- **The AC cannot see it.** AC-6d's fixtures are 22.2 AC-3d, AC-3f and AC-6b. None holds `entity_rename`, `evidence_repoint` or `learned_provenance_move`. 22.2 AC-3's replay fixture and AC-7's merge do hold them. So the first restore after a merged rename fails count verification. This is r10 s-3's failure mode, on the op the AC skipped.

**Fix, three edits:**

**(i)** 22.2 R2 `rename_entity`, after "re-attach to the existing entity", insert:
> Each re-attached link logs `unlink` of its old key and `link` of its new key through `edge_records.edge_event` (with `c_kind`), so the LWW pass moves it on a rebuild; `entity_rename` replays evidence only (R3).

**(ii)** In the fold row, replace "merges the two keys as `rename_entity` does: the entity count drops by one once the old key has no link left, and its links and evidence count under the surviving key" with:
> moves the old key's evidence copies to the surviving key (count-neutral for `evidence`); links follow their own `unlink` / `link` events and the entity count follows the old key's own `tombstone`, so the rename itself changes neither.

**(iii)** In 22.6 AC-6d's fixture list, after "AC-6b (base, swapped and partition variants)", add:
> ", 22.2 AC-3's replay fixture (re-point, `learned_provenance_move`, rename) and 22.2 AC-7's merge"

and add the mutation:
> "the fold keeps a merged rename's links on the old key" (AC-7's `links` count differs)

rel: contradicts -> [[task-22.2-repair-then-remove#files-to-modify]]
rel: depends-on -> [[task-17.4-factslog-backup-snapshot#r6-restore]]

### MEH m-1: d9cb is not cited, and (c) is not noted {#m-1}

**What is missing:** 22.6 `#rev-round-10` and plan-22 `#rev-round-10` cite d9bz only. d9cb(a) appears as "r10 s-2's per-op counting", d9cb(d) appears as r10 m-2, and d9cb(c) is absent.

**Fix:** append to 22.6's `#r5-own-appends` `c_kind` bullet:
> A legacy append resolved over the kinds logged up to the vacuum can miss a same-name `concept` logged later; accepted as narrow (d9cb(c)): compaction ends legacy appends, and r11 measured 0 drifts over 66,100 (cliquedb) and 253,023 (refmatrix) legacy appends, every `evidence` append in both logs.

Then add a row to both `#rev-round-10` tables:
> | d9cb (a) per-op `skipped_live`; (b) re-attach guard; (c) legacy drift accepted; (d) helper raises on an orphan | (a) [[#r5-timeline]]; (b) [[#r5-own-appends]] per r11 s-1; (c) the `c_kind` bullet; (d) [[task-22.2-repair-then-remove#r3]] |

### MEH m-2: "unresolved" is ambiguous about the revivable filter {#m-2}

`orphan_drop_unresolved` is "once per such append", but the text does not say whether that means among all matched appends or only revivable ones. Today the difference is 0 against a possible 66,100.

**Fix:** after "A legacy append that `resolve_c_kind` resolves to None" insert:
> "(among the revivable appends only; a non-revivable append is never resolved)"

## Per-task verdict {#readiness}

| task | verdict | what is left |
|---|---|---|
| 16.1, 16.2, 16.4, 16.5 | **ready** | none |
| 16.3 | **ready** | none |
| 16.6 | **ready** | the `ROW_OPS` wording follows [[#s-1]](i) if adopted, a one-clause edit |
| 22.1, 22.1a, 22.3, 22.4, 22.5 | **ready** | none |
| 22.2 | **needs a small edit** | [[#s-2]](i) and (ii) |
| 22.6 | **needs a small edit pass** | [[#s-1]] (entity end in the drop, the `L > N` guard, AC-6e); [[#s-2]](iii); [[#m-1]]; [[#m-2]] |

**One orchestrator ruling is needed.** [[#s-1]] replaces d9cb(b)'s c-match with "the drop carries the entity end, plus the `L > N` re-attach guard". d9cb(b) asked r11 to probe the c-match, and the probe shows it closes only F1.

## Verdict {#verdict}

DIRTY: 4 findings (0 BULLSHIT, 2 SKETCHY, 2 MEH). All 7 r10 findings are closed.

- **Plan-16 is approval-ready.** AC-12 fails on all 17 pre-R1f hits, and its two-mode self-check is not vacuous.
- **The own-appends rule on real data:** 0 drops, 0 unresolved, and every orphan key unlogged (4,404 on cliquedb, 66,239 on refmatrix). This is consistent with r10.
- **d9cb(c):** 0 drifts.
- **Plan-22** needs two short edits ([[#s-1]], [[#s-2]]). Both are fixture-proven gaps, with 0 affected rows in today's data.
