---
gmd: "0.1"
id: bsd-plan16-22-spec-rereview-r8-23ad703
title: "plan-16 + plan-22 spec re-review r8: round 7 closes all 9 r7 findings, and the two r6 partials close with them. bug-117 (0.78.3) then landed underneath the specs. 22.2 R3 still tells the implementer to resolve every row op's concept 'as kind concept' and says doc/memory rows are 'never rebuilt', which is now false. Every name-keyed op the specs add is spelled without `c_kind`. Followed literally, a rebuild revives the `rel:` evidence rows plan-22 removes, which are its dominant case. Plan-16 also does not account for the learn.off operator state."
severity: BULLSHIT
plan: plan-16-invisible-grep-shim, plan-22-audited-removal-and-repair
task: spec-rereview-r8-16.2-16.3-16.4-16.6-22.1a-22.2-22.6
round: 12 (plan-16) / 8 (plan-22)
tags: [bsd, audit, spec-review, removal, replay, bug-117, c-kind, edge-records, learn-off, d9av, d9aw, d9ay]
---

# ch-bsd spec re-review r8: plans 16 and 22 after round 7 (`26573ca`), against 0.78.3 (`23ad703`) {#root}

**Commit reviewed:** `23ad703` on `wave0-spec-reviews`.
- Round-7 revision: `26573ca` (d9av, d9aw, d9ay).
- `src/` since r7: 0.78.2 (bug-115/116) and 0.78.3 (bug-117, `391ffeb`: `edge_records.py` and `c_kind` on every edge event).
- No plan-16 or plan-22 byte changed between `26573ca` and HEAD. The decision log gained d9ba.

**Written:** 2026-10-15T03:18-0700.
**Author of the revisions:** Todd Holley / Opus 5.5 / spec-reviser (Wave 0 revision round 7).

**Method (read-only):**
- **Source at HEAD.** `store.py` (`rebuild_index_from_log` passes 1-3 including the new Pass 2b, `_replay_concept`, `_apply_event_body`, `apply_log_delta`, `add_evidence`, `purge_path`, `purge_entity` logging, `dump_catalog_to_log`) and `edge_records.py`.
- **Hook and switch code.** `learn_switch.py`, `search_hooks.py` (the teach-hook stand-down), `hooks.py` (wiring of `enforce-rmx-grep.sh`), `.claude/hooks/enforce-rmx-grep.sh` (`0611d2f`), `ingest_gmd.py`, `sync.py`.
- **The specs.** Every r7 finding was checked against the spec text at HEAD.
- **Marker state.** `~/.refmatrix/learn.off` is present (written 00:29). `.refmatrix/learn.off` is absent.
- **What I did not touch.** I opened no store and no socket, edited no spec or source, and made no commit.

rel: amends -> [[bsd-plan16-22-spec-rereview-r7-331b414]]
rel: specifies -> [[plan-16-invisible-grep-shim]]
rel: specifies -> [[plan-22-audited-removal-and-repair]]
rel: contradicts -> [[task-22.2-repair-then-remove#r3]]
rel: contradicts -> [[task-16.6-learned-row-validation#r1d]]

## What bug-117 changed underneath the specs {#bug117-facts}

| fact at `23ad703` | where | consequence for the specs |
|---|---|---|
| Every edge event (`link` / `unlink` / `evidence`) carries `c_kind`, written through `edge_records.edge_fields` / `edge_event` | `store.py` `link`, `unlink`, `add_evidence`, `purge_entity`'s unlinks, `dump_catalog_to_log` | Name-keyed events now name the concept by `(c_kind, c)`. The specs' row ops do not |
| Rebuild link LWW key = `(partition, linkage, c_kind, c, e_kind, e)`. Legacy (kindless) keys are resolved in Pass 2b and merged by max `ts` | `rebuild_index_from_log` Pass 2 and 2b | 22.2 R3's `(partition, linkage, c, e_kind, e)` is stale. A kindless `unlink` is resolved by the legacy rule, which can pick another kind |
| The legacy rule `resolve_legacy_kind`: `concept` wins, else a name held by exactly one kind, else None (counted) | `edge_records.py` | It is the ONE rule. Plan-22's naming and reborn logic must use it, not a rule of its own |
| Rebuild resolves an evidence row's concept by `(c_kind, c)`. Doc and memory concept ends are now REBUILT | Pass 3 evidence loop (`name_to_id.get((ev["c_kind"], ev["c"]))`) | r7 `#code-facts` ("rebuild resolves `c` ONLY as kind `concept`") is obsolete. So is every spec sentence built on it |
| Incremental replay resolves through `_replay_concept`: exact `c_kind`, or for a legacy event the kinds present in the LIVE catalog | `store.py` `_replay_concept` | For legacy events the rebuild uses all LOGGED keys, tombstoned ones included. The two paths differ ([[#m-3]]) |
| The rebuild now returns `links_unresolved`, `evidence_unresolved`, `links_skipped_dead`, `evidence_skipped_dead` | `rebuild_index_from_log` return value | Pass 3 skips are no longer silent. The ACs can assert these counters ([[#m-4]]) |
| `edge_event` rejects any op other than `link` / `unlink` / `evidence` (`EDGE_OPS`) | `edge_records.py` | Row ops must spell their identity with `edge_fields`, not `edge_event` |
| `add_evidence` is a plain `INSERT` with no uniqueness, and no live path deletes `linkage_evidence` except `vacuum` step 3 | `store.py` `add_evidence`, `vacuum` | The rebuild's evidence multiplicity is only correct if every live delete has an event that time-orders against the appends ([[#s-1]]) |

## Round-7 findings: status {#prior-status}

| r7 id | status | evidence at HEAD |
|---|---|---|
| b-1 (remove pass after all appends) | **closed** (residue [[#b-1]]) | 22.2 [[task-22.2-repair-then-remove#r3]] "ONE row pass, appends and row ops together, in TIMESTAMP order", with ties by log position. The lockstep text is in 16.6 [[task-16.6-learned-row-validation#r1d]]. R9 step 4 now logs `evidence_remove` for a named dead concept. AC-3d covers both fixtures; AC-3e covers the 3-copy timeline with three mutations; 16.6 AC-9c covers `_row_pass_events`. I traced AC-3d and AC-3e against today's `ts` sort, and the mutation "remove after all appends" fails both, as claimed. d-24 is recorded in plan-22 |
| s-1 (restore reinserts a reused dead id) | **closed** | 22.2 R4 "Every recorded dead id is re-checked": `id_map` first, then `LinkLiveness.dead_side`, then `restore_dead_id_reused`. AC-4c adds the reused-id fixture and its mutation |
| s-2 (restored concept new id, inbound rows old id) | **closed** | 22.2 R4 "Restore maps every recorded old id through its own `id_map`": re-inserted rows get an event, surviving rows are updated in place with no event. 22.2 AC-4d and 22.6 AC-9c each carry two mutations. I traced both AC timelines through the rebuild and each holds the row once |
| s-3 (22.3 and R5 said no existing entity is purged) | **closed** | 22.3 [[task-22.3-bug-086-global-repair#r3]]: learner-attributed members are purged whole, N is printed first, and the bound is 90. 22.3 AC-1 records N. AC-5 is rewritten with G/K/U and the restated mutation. The stale R5 sentence is deleted. d-16 is amended and d-25 recorded (d9aw) |
| m-1 (8 "nameless" are reborn) | **closed** (residue [[#m-2]]) | 22.1a `unnamed:reborn` is defined, with 8 link-side and 896 evidence-side. 22.2 R9 step 4 has the reborn rule and step 5's reason is corrected. AC-3b and AC-8a each have a reborn clause with mutations |
| m-2 (AC-8c scope, predicate maps, bit half) | **closed** | `LinkLiveness` carries the `entity` and `linkage` maps. AC-8c now runs over the whole module, forbids anti-joins and whole-table id sets, and covers both halves of `repair_fragments`, with three mutations |
| m-3 (partitions) | **closed** | R9 step 4 logs one `unlink` per distinct last-wins `link` key, with that key's partition field. 22.1a condition (iii) is per partition. `inputs.facts_path` and `default_partition` are added. 16.6 R7 `--default-partition` (line 666). AC-3b and AC-8a each have a partition clause |
| m-4 (`ingest_ok`) | **closed** | 22.2 R2 `remove_evidence(..., ingest_ok=False)` has two named callers and an AST pin. `detail` and `ingest_ok` are in the event |
| m-5 (23.4 count, `dead-linkage`) | **closed** by plan-23 | `task-23.4` at `6fa243d` (d9ba): 5,298 entity-dead, 1 concept-dead and 0 `dead-linkage`, plus the `dead-linkage` class and its mutations |
| r6 s-1, s-4 (partial in r7) | **closed** | Closed with r7 s-1 and s-3 above |

**Totals for the r7 ids:** 9 of 9 closed. Both r6 partials are closed.

## New findings {#findings}

### BULLSHIT b-1: the row-op specs predate bug-117. R3 says to resolve `c` "as kind `concept`" and calls doc/memory rows "never rebuilt", and every name-keyed op is spelled without `c_kind` {#b-1}

**The spec at HEAD:**
- [[task-22.2-repair-then-remove#r3]] "*How `c` resolves*": "Each row op resolves `c` exactly as the `evidence` replay of the same row does: as kind `concept` (`store.py:8090` rebuild, `:7841` incremental). A row whose concept is a doc or memory entity is never rebuilt from its `evidence` event (r7 `#code-facts`, a pre-existing replay gap this plan does not change), so its row op also resolves nothing there".
- The same section's closing note: "The rebuild's resolution of an evidence row's concept only as kind `concept` … is pre-existing and unchanged here".
- Event spellings with no `c_kind`:
  - 22.2: `evidence_remove{linkage, c, e_kind, e, file, line, detail, keep, ingest_ok}`, `evidence_repoint{…identity, new_line}`, and R9's `unlink{linkage, c, e_kind, e}`.
  - 22.2 R3 gives the LWW key as `(partition, linkage, c, e_kind, e)`.
  - 22.6 R5: `evidence_orphan_drop{linkage, c, dead_entity_id, …}`.
  - 16.6 R1d: `learned_provenance{linkage, c, e_kind, e, …}` and `learned_provenance_move{linkage, c, e_kind, e, …}`.
- AC-3d's ingest fixture picks kind `concept` *because* "rebuild resolves an evidence row's concept only as kind `concept`, `store.py:8090`". AC-3e, AC-4d and 22.6 AC-9c also use kind `concept`.

**What is true at `23ad703`:**
- Rebuild and incremental replay resolve `(c_kind, c)` exactly, and a legacy event by `resolve_legacy_kind` ([[#bug117-facts]]). Doc and memory concept rows replay.
- The "gap this plan does not change" was closed by bug-117 after round 7 was written: `26573ca` 00:54, `391ffeb` 01:47.

**Trace, followed literally.** Concept `A` is a doc. That is the dominant shape: all 14,745 dangling-evidence rows on cliquedb are `rel:` edges.
1. R9 removes `B`'s row to `A` and logs `tombstone{doc, A}` plus `evidence_remove`.
2. Under R3's rule the remove "resolves as kind `concept`", finds no concept `A`, and is counted unresolved.
3. `A` is re-created later.
4. The rebuild now re-attaches `B`'s OLD `evidence` event (it carries `c_kind: doc`, or is legacy and resolves to `doc`) to the new `A`.
5. The live store does not hold that row, so rebuild ≠ live.

This is exactly r7 b-1's divergence, back for the dominant case. Removing concept-side rows through R2 for a purged doc concept has the same outcome. No AC sees it, because every fixture was moved to kind `concept` to dodge a gap that no longer exists.

**The second half: no `c_kind`.** A kindless `unlink` that R9 logs for a doc-concept link goes through Pass 2b's legacy rule. If any `concept` of that name is in the log, the rule picks `concept`. The `unlink` then lands on a different key from the kinded `link`, and the old link revives on re-creation.

**Why it is bullshit:**
- The spec defers to "a pre-existing gap this plan does not change", and that gap is closed (stale deferral, rule 9).
- The specs also assert the r7 code fact as current behaviour, which steers the implementer to a resolution that diverges from the code.
- The AC fixtures were chosen to avoid the now-dominant case.

**Fix (text only):**
1. Rewrite 22.2 R3 "How `c` resolves" as follows:
   > Every row op carries the concept end as `(c_kind, c)` and the entity end as `(e_kind, e)`, spelled with `edge_records.edge_fields(linkage, c_kind, c, e_kind, e, **extra)`. `edge_event` is not used, because it accepts only `link`/`unlink`/`evidence`. The op resolves its ends exactly as the `evidence` replay of the same row does: by `(c_kind, c)` (rebuild: `name_to_id`; incremental: `Store._replay_concept`). A legacy append (no `c_kind`) is resolved by the one rule, `edge_records.resolve_legacy_kind`, before the row pass matches identities. A row op is never written without `c_kind`.
2. Delete the "pre-existing and unchanged" note in `#rev-round-7`. Cite bug-117 (0.78.3) instead.
3. Respell the events with `c_kind`:
   - 22.2: `evidence_remove`, `evidence_repoint` and R9's `unlink`. The `unlink`'s `c_kind` is the dead concept's logged key kind, or the live concept's catalog kind.
   - 22.6 R5: `evidence_orphan_drop`.
   - 16.6 R1d: `learned_provenance` and `learned_provenance_move` (their `c_kind` is always `concept`, since `_learn_grep_hits` uses `add_concept`).
   - The R3 LWW key becomes `(partition, linkage, c_kind, c, e_kind, e)`.
4. Fixtures:
   - Switch AC-3d's ingest fixture and AC-3c's second fixture to `A` = a DOC. Keep AC-3e on kind `concept`, so both kinds are covered.
   - Add one fixture whose `B→A` evidence event is LEGACY (no `c_kind`) while the log also holds a `concept` named `A`, so the legacy rule is exercised against a kinded remove.
   - Mutations, each must FAIL:
     - "row ops resolve `c` as kind `concept`" (the doc fixture revives `B`'s row);
     - "`unlink` without `c_kind`" (the AC-3b re-create clause, with a `concept` of the same name in the log).

rel: contradicts -> [[task-22.2-repair-then-remove#r3]]
rel: contradicts -> [[task-16.6-learned-row-validation#r1d]]
rel: contradicts -> [[task-22.6-removal-entry-points#r5]]

### SKETCHY s-1: `evidence_orphan_drop`'s "entity does not exist at that point" cannot be evaluated by the rebuild's row pass, so a vacuumed orphan comes back doubled on a re-created entity {#s-1}

**The spec.** 22.6 [[task-22.6-removal-entry-points#r5]] says replay "deletes rows matching `(linkage, c, file, line, detail)` whose entity does not exist at that point; a match on a live entity is never deleted (`orphan_drop_skipped_live`)". 22.2 R3 places the op in the one timestamp-ordered pass.

**What is wrong:**
- **The rebuild has no "at that point".** It materializes every surviving entity BEFORE the row pass (Pass 3: entities, then flags, then links, then evidence). "Exists at that point" therefore means "exists at the end of the log".
- **The common sequence.** Sync re-ingests a GMD doc or a code file:
  1. `purge_path` tombstones the old entity at T1 and leaves its evidence rows orphaned, because `purge_entity` deletes no evidence.
  2. `vacuum` step 3 drops the orphans with `evidence_orphan_drop` at T2.
  3. Ingest re-creates the same name and appends fresh evidence at T3.
- **The result.** Live holds 1 copy. A rebuild appends the T0 copies onto the re-created entity. The T2 drop sees a live entity and skips (`orphan_drop_skipped_live`). The T3 copies are appended. The rebuild holds 2 copies of each row.
- **bug-117 widens it.** Doc and memory concept rows now replay too, and they were silently dropped before.
- **No AC covers it.** No fixture re-creates the entity after a vacuum.

**Fix:**
- State the predicate on the LOG timeline. In the row pass, `evidence_orphan_drop` at `T` deletes each copy appended at or before `T` that matches `(linkage, c_kind, c, file, line, detail)` and whose `(partition, e_kind, e)` was DEAD at `T`. "Dead at `T`" means its latest `tombstone` at or before `T` is at or after its latest `entity` event at or before `T`. Pass 2 already collects both timelines, so the rule needs a per-key list of `ts`, not new data.
- The incremental path keeps its catalog check, since in byte order "at that point" is literal.
- New 22.6 AC-5c, run on a sandbox store:
  1. Ingest `D` with one `rel:` evidence row.
  2. `purge_path(D)`.
  3. `vacuum`.
  4. Re-ingest `D`.
  5. Rebuild a copy. It must equal live on `linkage_evidence` by name, as a multiset.
- Mutation "orphan-drop checks the materialized catalog" FAILS AC-5c (the copy holds 2).

rel: contradicts -> [[task-22.6-removal-entry-points#r5]]

### SKETCHY s-2: plan-16 does not account for today's operator state: `learn.off` is set globally, the rewrite and the drain are off, and `enforce-rmx-grep.sh` stands down only because of the marker {#s-2}

**The state:**
- `~/.refmatrix/learn.off` exists. The user's instruction (2026-10-15, `0611d2f`) is "block the grep rewrite until the passive version exists".
- The global rewrite and the teach hook (`search_hooks.py` "The learn switch, both scopes") exit early on that marker, and so does the project hook `enforce-rmx-grep.sh` (`0611d2f`).
- `enforce-rmx-grep.sh` is wired by the generator (`hooks.py`, "enforce-rmx-grep.sh"). Its redirect tells the agent to use `rmx grep` for corpus searches, which is exactly what plan-16 d-1 retires ("grep is observed, not answered").

**What plan-16 says:** nothing on any of this. A search of plan-16 and its tasks finds no `learn.off`, no `enforce-rmx-grep`, and no re-enable step. Specifically:
- **16.4 cannot collect.** "The first run after 16.2 ships is the plan's acceptance run". With the global marker set, the shims take their learning-off early exit (16.2 R1) and spawn no learner. 16.4 then sees `n_complete = 0` indefinitely: a vacuous or never-run acceptance.
- **No owner for turning it back on.** No step says who runs `rmx learn on --global`, or when (after 16.2 deploys? after 16.5?).
- **Turning it back on re-arms the wrong redirect.** Removing the marker re-arms `enforce-rmx-grep.sh`, which sends every corpus grep back to `rmx grep`. That is the bug-115 cli-pool load the stand-down removed, and it is the opposite of d-1.
- **Stale text.** Plan-16 `#today` ("every bare grep is rewritten … exports `RMXGREP_MODE=rich`") and 16.2 `#rich` ("Today routes 1 and 2 run …") describe a state that is off today.

**Fix:**
1. Plan-16 `#today`: add one paragraph on the operator state since 2026-10-15. Global `learn.off` is set; route 1 (the rewrite) and the teach hook stand down; route 2's shims early-exit to the real tool; the daemon drains nothing; `enforce-rmx-grep.sh` stands down.
2. 16.3 owns `enforce-rmx-grep.sh`: retire it, or re-point its message to `rmx context` without blocking. Either way its marker stand-down becomes moot. AC: with the marker absent, a corpus `grep -rn X src` is NOT redirected to `rmx grep`.
3. 16.4 precondition: the acceptance window opens only after the user runs `rmx learn on --global` following 16.2's deploy. The harness prints the `learn_switch.decision` rule in its header, and refuses (or labels the run `learning-off`) when the decision is off.
4. Record the flip as a user decision. My recommendation: flip after 16.2 and 16.3 deploy together, so the rewrite comes back only when it feeds the passive shim and the redirect is gone.

rel: related-to -> [[task-16.4-measurement]]
rel: related-to -> [[task-16.3-grep-tool-hook-and-docs]]

### MEH m-1: 16.6 R1d's row pass must keep bug-117's Pass 2b and its counters; its line pins are stale {#m-1}

**What is stale:**
- R1d says `_row_pass_events` "replaces today's separate `evidence_events` list (`:7998`) and its per-partition loop in pass 3 (`:8087`)".
- At HEAD, the list is at `:8016`, and Pass 2b (`:8057`) rewrites it into `resolved_evidence`, with `c_kind` resolved by the legacy rule and `evidence_unresolved` counted. The pass-3 loop is at `:8147` and counts `evidence_skipped_dead`.
- AC-9c's AST clause ("no separate `evidence_events` loop is left") can be read as licence to delete Pass 2b's resolution loop. The bug-117 tests would then fail, so this is caught, but the spec should not invite it.

**Fix:**
- `_row_pass_events(events, partition)` takes the appends AFTER Pass 2b's resolution (every item carries `c_kind`) and keeps `evidence_unresolved` / `evidence_skipped_dead`.
- The AST clause targets pass 3 only.
- Cite by symbol (`Pass 2b`, `rebuild_index_from_log`), or re-read at `23ad703`.

### MEH m-2: naming and reborn must use the one legacy rule; the 15 two-kind reborn names resolve to `concept` {#m-2}

**The gap:**
- 22.1a's condition (iii) matches a covering event by "linkage and live-end name". For a dead CONCEPT side (`dangling-link:concept`, `dangling-evidence`), the covering event names the concept as `(c_kind, c)`, or by name only on legacy events.
- The r7 evidence-side reborn count says 896 names are live: 711 as `concept` only, 170 as `doc` only, and 15 as both. For those 15, the rebuild resolves legacy events to `concept` (preferred), so the "reborn entity" the reborn rule compares against must be the `concept` one.

**Fix:**
- In 22.1a (iii), an event covers key `(p, k, n)` iff its `c_kind == k`, or it is legacy and `resolve_legacy_kind(kinds logged for n in p)` returns `k`. The kinds logged for `n` include tombstoned keys, as the rebuild's `kinds_by_name` does. A legacy name the rule returns None for covers nothing and is counted `legacy_unresolved`.
- The reborn entity is picked the same way.
- Add an AC-8a row: a legacy covering event whose name is held by a `doc` and a `concept`.
- Re-measure the 15.

### MEH m-3: legacy resolution differs between incremental and rebuild, and plan-22's tombstones create exactly the state where it differs {#m-3}

**The difference:**
- `_replay_concept` resolves a legacy event over the kinds in the LIVE catalog.
- Rebuild Pass 2b resolves it over every LOGGED key, tombstoned ones included.
- Example: a tombstoned `concept X` and a live `doc X`. A legacy edge `c = X` attaches to `doc X` incrementally, but resolves to `concept` and is skipped-dead on a rebuild.

**Why it matters here:**
- 22.2 R3 and 16.6 R1d both claim the two paths agree.
- R9 tombstones named dead concepts, which manufactures this state.

**Impact is low today.** `apply_log_delta` has no caller (d9ao).

**Fix:**
- Qualify the "both replay paths" sentence: the two paths agree on kinded events, and legacy events follow each path's resolver.
- Log a bug-registry row for the resolver difference. The `src` fix is to resolve legacy events in `_replay_concept` over logged kinds too, or to drop `apply_log_delta`.

### MEH m-4: the rebuild's new counters make several ACs sharper (opportunity) {#m-4}

The rebuild now returns `links_skipped_dead`, `evidence_skipped_dead`, `links_unresolved` and `evidence_unresolved`. Use them:
- **AC-3b:** the first copy asserts `links_skipped_dead == 0`. Mutation "tombstone only, no `unlink`" then fails directly (2), without needing the re-create clause.
- **AC-3c, AC-3d, AC-3e and AC-9c:** assert `evidence_unresolved == 0` and the expected `evidence_skipped_dead`.
- **22.2 R9 step 5:** "pass 3 skips a row whose `cid` or `eid` does not resolve" becomes "skips and counts it (`links_skipped_dead` / `evidence_skipped_dead`, bug-117)".
- **22.2 R3:** "counted `skipped_unresolved`" names `apply_log_delta`'s counter. Name the rebuild's counters for the rebuild path.

### MEH m-5: line pins shifted under 0.78.3 {#m-5}

**What moved:**
- 22.2 R3 and 16.6 R1d, "read at `77ac38f`": `:7926`, `:7998`, `:8087`, `:8090`, `:7841` are now `:7941`, `:8016`, `:8147`, `:8150`, and `_replay_concept`.
- 22.6 `#facts`, "read at `3d3c798`", is shifted by bug-117's store.py edits.

**Fix:** the labels are honest, but cite these by symbol, or re-read at `23ad703`, as part of [[#b-1]]'s edit.

## Observation outside scope (not counted) {#observation}

The generated wrapper for the enforcement hooks is:

```
[ -x ".../enforce-rmx-grep.sh" ] && ".../enforce-rmx-grep.sh" || true
```

It is in `hooks.py`, and installed in `.claude/settings.json:153`. The same `|| true` wraps `enforce-test-to-file.sh`. Both scripts block with `exit 2` and a stderr message, and `|| true` turns that exit 2 into exit 0. Unless Claude Code reads the stderr regardless, neither hook can block.

I did not verify this at runtime, because `learn.off` makes `enforce-rmx-grep.sh` exit 0 before it decides anything. Worth one bug-registry check, because CLAUDE.md relies on `enforce-test-to-file` blocking.

## Decisions the user should make {#user-decisions}

1. **[[#s-2]] When does `learn.off` come off, and what happens to `enforce-rmx-grep.sh`?** I recommend flipping after 16.2 and 16.3 deploy together, with 16.3 retiring the redirect. 16.4's window opens only after the flip.
2. **[[#s-1]] Orphan-drop predicate on the log timeline (recommended), or log `evidence_remove` at purge time?** The second option means `purge_entity` removes its own evidence rows by name. It ends orphan creation outright, but it reverses r6 s-3's "purge deletes no evidence", and every purge caller then needs manifest coverage. The timeline predicate is the smaller change.

## Approval readiness {#readiness}

| task | verdict | what is left |
|---|---|---|
| 16.1 | **ready** | none |
| 16.2 | **needs edit pass** (one paragraph) | [[#s-2]] stale `#rich` "today" text |
| 16.3 | **needs edit pass** | [[#s-2]]: own `enforce-rmx-grep.sh` (retire or re-point) plus its AC |
| 16.4 | **needs edit pass** | [[#s-2]]: learning-on precondition, and a `learn_switch` decision in the header |
| 16.5 | **ready** | none |
| 16.6 | **needs edit pass** (small) | [[#b-1]]: `c_kind` on `learned_provenance` and `learned_provenance_move`. [[#m-1]]: Pass 2b. [[#m-3]]: the qualifying sentence. [[#m-5]]: pins |
| 22.1 | **ready** | none |
| 22.1a | **needs edit pass** | [[#m-2]] legacy-rule naming and reborn |
| 22.2 | **needs edit pass** (blocking for approval: [[#b-1]]) | [[#b-1]], [[#m-3]], [[#m-4]], [[#m-5]] |
| 22.3 | **ready** | none (inherits 22.2) |
| 22.4 | **ready** | none |
| 22.5 | **ready** | none (`learned_import` writes through the store APIs, which now log `c_kind`) |
| 22.6 | **needs edit pass** | [[#b-1]] (`c_kind` on `evidence_orphan_drop`), [[#s-1]] (the predicate and AC-5c) |

Nothing is blocked on design. Every item is a text edit, and only [[#s-1]] and [[#s-2]] need a user ruling.

## Verdict {#verdict}

DIRTY: 8 findings (1 BULLSHIT, 2 SKETCHY, 5 MEH). r7: 9 of 9 closed.

- **Plan-16:** approvable after one edit pass: [[#s-2]] in 16.2/16.3/16.4, plus [[#b-1]] and [[#m-1]] in 16.6.
- **Plan-22:** approvable after one edit pass: [[#b-1]], [[#s-1]], [[#m-2]] to [[#m-5]].
