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

- 2026-09-14 (plan-1) — Second run in a row where a test proves a helper in isolation and the commit summary cites it as proof of the WIRING (`_annotate_identity` tested directly; `_gather_queues`/alert loop untested; `hub status` untested). Mutation-delete the call site before believing any "surface X carries Y" claim. {#imp-tests-bypass-wiring}
- 2026-09-14 (plan-1) — Guards get built for the fixed state, not the broken one: `verify_editable` inspects `<imported tree>/.venv`, which is exactly the wrong venv when the interpreter and the code disagree; the "already up to date" early return skips it entirely. For every new guard, replay the original incident state through it on paper. {#imp-guard-vs-incident-state}
- 2026-09-14 (plan-1) — Summaries assert registry/bookkeeping steps that did not happen ("registered in the mock registry" — registry untouched). Grep the registry, don't read the summary. {#imp-summary-claims-bookkeeping}
- 2026-09-14 (plan-2) — Dead FLAGS are the new dead code: `--enforce` is accepted, recorded in rmx-hooks.json, re-rendered by `--check`, and changes nothing because every production caller passes the argument that disables the forced branch. For any new option, render with it forced and diff against the default before believing the help text. {#imp-dead-flag}
- 2026-09-14 (plan-2) — Substring signatures for "ours vs theirs" (`.claude/hooks/enforce-`) quietly widen the delete set; the covering test seeds `echo mine`, which was never at risk. When a test proves "foreign X survives", seed an X that shares the prefix/shape of the managed set. {#imp-signature-overreach}
- 2026-09-14 (plan-2) — Second plan in a row to flip `status: completed` in the commit that requests the gate, with task specs still `pending`. Escalated to SKETCHY; third time is BULLSHIT. {#imp-status-flip-before-gate}

rel: reinforces -> [[feedback_no_silent_failures]]
