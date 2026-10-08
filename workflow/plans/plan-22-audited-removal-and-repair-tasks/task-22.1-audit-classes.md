---
gmd: "0.1"
id: task-22.1-audit-classes
title: "Task 22.1: a read-only audit that classifies every learned row and the concept cull candidates"
tags: [task, audit, grep-learning, concepts]
metadata:
  node_type: task
  status: pending
  created: 2026-10-07
---

# Task 22.1: the audit {#root}

> Plan: [plan-22-audited-removal-and-repair](../plan-22-audited-removal-and-repair.md)
> Status: Pending
> Depends on: 16.6 R1/R5 (provenance, backfill)

rel: part-of -> [[plan-22-audited-removal-and-repair]]

## Requirements {#requirements}

1. **R1 Learned-row classes.** Each row is re-read with the existing verifier
   (`evidence_line_matches`, under the row's recorded flags; no second matcher):
   - `ok` — the line still matches.
   - `moved` — the claimed line no longer matches, the matching text is on EXACTLY ONE other line in
     the same file, and the content hash of that line equals the recorded one. The new line is
     recorded for 22.2.
   - `ambiguous` — the text is on several lines, or a relative path resolves to several files.
     These rows are kept and reported.
   - `stale-line` — the pattern no longer matches anywhere in the file.
   - `out-of-range` — the line number is past the end of the file and nothing matches elsewhere.
   - `missing-file` — the file is unreadable or absent.
   - `duplicate` — the same `(concept, entity, line)` appears more than once.
   - `orphan-root` — a relative path with no recorded root (bug-086's shape). Where exactly one
     candidate root makes it verify, the candidate is recorded.
2. **R2 Concept cull classes** (from the concept exploration):
   - `orphan-alias` — an alias row with no `same_as` edge and no other edge.
   - `empty-learned` — a protected `query/*` concept whose learned evidence is all non-`ok` after
     R1.
3. **R3 Read-only.** Catalog and Lance bytes are unchanged by an audit. Plan-23's queued
   `stale_seen` marks are the only write.
4. **R4 Output.** Counts per class and per pattern; `--list` for rows; `--json` for 22.2. Exit 0
   when the scan completes.

## Acceptance criteria {#acceptance}

1. A fixture with one row of each class audits each row to exactly its class, `moved` included,
   with the right new line.
2. A file edit that moves a matched line by N lines turns that row `moved` (not `stale-line`).
   Duplicating the line elsewhere turns it `ambiguous`.
3. The catalog file hash is unchanged after an audit.
4. On catalog COPIES of this repo and the global store: class counts are reported, `orphan-alias`
   ≈ 9,182 and `empty-learned` ≤ 747 here, and `orphan-root` covers the 1,087 relative entities
   globally.
