# Slot Rotation Drift — A vs B Merge Recovery

**Status**: open, blocked by lack of merge tool.
**Discovered**: 2026-06-03 session, while verifying `rmx memory recall` correctness against viascope hooks.
**Severity**: data loss in front of users — `memory recall` silently misses 271 memory-viascope rows from any cwd that resolves to the writer slot.

## What we observed

viascope store at `/Users/tholley/at/bdep/viascope/.refmatrix/`:

| Category | A-only | B-only | A∩B | A total | B total |
|----------|--------|--------|-----|---------|---------|
| memory-viascope memories (kind=memory AND partition_id=3) | **280** | **9** | 105 | 385 | 114 |
| All memories (kind=memory, any partition) | 283 | 12 | 216 | 499 | 228 |
| All entities (any kind) | 1133 | 1457 | 115004 | 116137 | 116461 |

Active marker = B → writes/reads land on the slot with **only 114 of 385** memory-viascope memories. Every `memory recall`, `memory list`, and hook-driven UserPromptSubmit recall misses 271 memories.

B-only rows are mostly recent (id range 1323344–1382286), kind breakdown:
- concept: 1306 (grep learn-on-miss additions)
- code: 104
- doc: 35
- memory: 12

So neither slot is a superset — both directions have unique data. **Naive reseed in either direction loses data.**

## Root cause

`rmx replica refresh` ran cleanly: `mode=noop-delta, applied=0`. The daemon's replay log shows nothing new since the last sync. Yet 271 memory rows exist in A that B never received. **These rows were written outside the tracked write log.**

Likely sources (per existing memories):
- `project_session_0322_to_0327` notes "0.3.30 rewire `rmx sync` fully to the daemon; never direct-write the catalog under it" — so direct-write was a real, recently-plugged hole.
- Pre-0.3.30 imports (e.g. `rmx memory import-sqlite` carrying 866 `imp-memory-*` rows) may have bypassed the log.
- Anything that hit `Store` directly without going through `daemon_mod.call(..., op, ...)` would have skipped the log.

Once a row escapes the log, the rotation's delta-apply is structurally incapable of catching it — the log is the only source the catch-up reads.

## Recovery requirement: full merge, not reseed

The drift is bidirectional. Recovery has to:
1. Build the union of all rows across both slots.
2. For ids present in both, prefer the row with the newer `updated_at`.
3. Preserve FK integrity across `entities`, `memory_content`, `linkage_evidence`, `entity_links`, `embeddings_meta`, and any other dependent tables.
4. Write the merged catalog into a fresh file.
5. Stop daemon, atomically swap merged file into the active slot, mirror to the other slot, set marker.
6. Restart daemon, verify counts match expectations.

## Implementation sketch

A new daemon op + CLI: `rmx replica merge [--dry-run]`.

```
def _op_replica_merge(d, args):
    # 1. Stop accepting writes (acquire d._store_lock for the duration)
    # 2. Identify the set of tables to merge — schema is rich:
    #      entities, memory_content, partitions, linkages,
    #      linkage_evidence, entity_links, embeddings_meta, ...
    # 3. For each table:
    #      ATTACH slot_a AS a; ATTACH slot_b AS b;
    #      CREATE TABLE merged.t AS
    #          SELECT * FROM (
    #              SELECT * FROM a.t
    #              UNION ALL BY NAME
    #              SELECT * FROM b.t
    #              WHERE NOT EXISTS (
    #                  SELECT 1 FROM a.t WHERE a.t.id = b.t.id
    #                          AND a.t.updated_at >= b.t.updated_at
    #              )
    #          );
    # 4. Validate FK integrity on merged
    # 5. Swap: cp merged -> catalog.A; cp merged -> catalog.B;
    #          mark active=A; clear offset files; restart daemon
    # 6. Return per-table {added_from_a, added_from_b, kept_intersection}
```

Open design questions:
- **Schema enumeration**: where to get the canonical table list? `s._read().execute("SHOW TABLES")` is fragile if backend differs. Probably `backend.py`'s migration scripts hold the canonical list.
- **Tables without `updated_at`**: some auxiliary tables may not have one — fall back to "if both exist, keep A" (or B) by convention. Document the rule per table.
- **Concurrent writes**: hold `d._store_lock` for the whole merge. May take minutes for large stores — acceptable for an explicit recovery command. Optional: progress logging.
- **Partition table merges**: `partitions(id, name, kind, created_at, meta)` has a UNIQUE on `name`. If A and B disagree on id↔name binding (shouldn't happen, but check), the merge needs a remap pass.
- **`vectors_updated_at`**: when an entity merges in from the "loser" slot, its embedding may or may not exist in the lance dataset. Probably safe to NULL the field on merge-in so subsequent `rmx embed` picks it up.

## Acceptance criteria

- `rmx replica merge` runs to completion on the viascope store.
- Post-merge counts: A and B have IDENTICAL row counts in every table.
- `rmx memory recall "perspective box rendering"` returns hits from both pre-merge cohorts (e.g., some id < 232986 AND some id > 1323344).
- No FK integrity violations (referential check passes).
- The 12 B-only memory rows survive.
- The 280 A-only memory-viascope rows are recoverable via recall.

## Workaround until merged

Hook recall queries hit slot B → misses 271 rows. To recall the full set today:
- Manually copy slot A's memory_content rows into slot B for the missing 271 ids (one-shot SQL).
- Accept that any further drift between now and merge-tool ship requires a fresh diff + re-copy.

## Related

- 0.4.2 `1aa2c63` — fixed `memory recall` JSON path to use daemon RPC (not stale `_store()`). Made the drift visible by surfacing hits with resolvable names instead of silent `[]`.
- 0.4.3 `5ac068b` — `_store()` now binds to active rotation slot, not legacy `catalog.duckdb`. Eliminates the legacy-file-frozen-at-bootstrap class of bug; orthogonal to slot-vs-slot drift.
- Memory: `project_replica_rotation_hardened` (0.3.16–0.3.18) — rotation hardening earlier in the cycle; addressed crash safety but not unlogged-write replication.
- Memory: `project_daemon_arch` — per-store unix-socket daemon owns the DuckDB catalog; the log-based catch-up assumed every write goes through the daemon.

## Next-session entry point

1. Confirm drift still present: `cp catalog.A.duckdb /tmp/A; cp catalog.B.duckdb /tmp/B; python3` with diff script (template above).
2. Enumerate full table list — start by reading `backend.py` migration scripts.
3. Prototype the merge SQL on `/tmp/A` + `/tmp/B` (out-of-tree, no daemon contention).
4. Wrap as `_op_replica_merge` + `rmx replica merge` CLI.
5. Test on viascope. Verify recall returns the 280 A-only rows.
6. Also prophylactic: ship a `rmx replica audit` command that diffs both slots and reports drift so this doesn't fester silently.

## Drift detection going forward

Even after merge, the drift class can recur if any code path bypasses the daemon write log. Hard preventive measures:
- Audit every `Store` write call site under `cli.py` — anything outside `_op_*` handlers OR routed through `daemon_mod.call(...)` is a candidate for re-drift.
- Consider a daemon assertion: on rotation swap, count rows in both slots; if delta-apply applied N rows but row-count delta != N, log a warning.
- Add a periodic `rmx replica audit --json` to a hook or launchd ticker to surface drift early.
