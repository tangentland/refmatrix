---
gmd: "0.1"
id: bsd-impressions
title: "ch-bsd impressions — refmatrix"
tags: [bsd, impressions]
---

# ch-bsd impressions {#root}

- 2026-09-14 — Memory-critical paths keep growing silent drops: `|| true` in hooks, `parse_gmd → None → continue` in the bridge, `except: pass` in subject filing. Next run: grep every new path that touches `~/.claude/projects/*/memory` for a swallowed branch first. {#imp-silent-memory}
- 2026-09-14 — "Two ways to do X" is the recurring shape here: two memory bridges (sync-disk vs ingest-gmd), two hook sources (template vs hand-edited settings), two runtimes that turned out to be one (deploy venv → dev src). Whenever a diff adds a second path, ask which one production actually takes. {#imp-two-paths}
- 2026-09-14 — DuckDB index drift is a fourth-time recurrence and now reachable from a READ command via grep-learn. Any diff touching `_learn_grep_hits`, `upsert_entity`, or `_is_fatal_invalidation` gets escalated a level. {#imp-index-drift}
- 2026-09-14 — Tests in this repo lean on `monkeypatch.setattr` of the function under test (bridge test mocks `_sync_memory_dir`). Run the mutation check ("would it fail if the real path were broken?") on every new test before trusting the green. {#imp-mock-the-sut}

rel: reinforces -> [[feedback_no_silent_failures]]
