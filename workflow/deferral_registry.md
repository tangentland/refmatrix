---
gmd: "0.1"
id: deferral_registry
title: "Deferral Registry — deferred production functionality"
tags: [process, deferral, governance]
metadata:
  node_type: registry
---

# Deferral Registry {#root}

Companion to [[test_mock_registry]]. Where the mock registry classifies **test-side mocks**, this
registry tracks **deferred production functionality** — features intentionally not built yet,
shipped as **fail-closed seams** (an honest `feature_not_supported`-style raise), **inert
self-sentinels**, or **scaffolding with no current caller** — each gated on a concrete future
trigger (an Accepted-but-unimplemented ADR, a later phase, or a platform/deployment).

rel: part-of -> [[test_mock_registry]]

A deferral is **legitimate** only if it (a) fails closed or is inert — never a silent wrong
answer — and (b) names a concrete graduation trigger with an owner. A deferral that silently
self-resolves, or has no graduation owner, is a **bug**, not a deferral. `@ch-gap-master` curates
this registry; `@ch-bsd` flags stale deferrals.

## Classification {#classification}

| Classification | Meaning | Behavior now |
|----------------|---------|--------------|
| `fail-closed-seam` | Real seam that raises/refuses on the unbuilt path | Refuses honestly |
| `inert-sentinel` | Placeholder value/branch with no active effect | No effect |
| `scaffold-no-caller` | Structure built ahead of its first caller | Unreachable in prod |

## Registry {#registry}

| Item | Location | Classification | Graduation Trigger | Owner |
|------|----------|----------------|--------------------|-------|
| rewriter hook bakes the generator's tree (bug-008, recurring) | src/refmatrix/search_hooks.py `render_scripts` (`RMXGREP =`/`RMXRG =` absolute paths in `~/.claude/hooks/rmxgrep-rewrite.py`) | deferred-design | task 6.5 (`task-6.5-plan-6-deferrals-docs-benchmark`, acceptance criteria there): runtime resolution of the wrappers + refusal to write the user-global dir from a foreign tree; until then `rmx install-hooks --check` is the tripwire | plan 6 |
| `rmx memory sync-disk` alias of `ingest-gmd --as-memory` (bsd-plan5-r2 #b-2-r2) | src/refmatrix/cli.py `memory_sync_disk` (15 lines; forwards to `_sync_memory_dir`) | `scaffold-no-caller` (in this repo; the callers are the fleet's copies of the p20-0 compiler) | every cat-herder project's `.claude/p20-0/compile_guardrails.py` (template at ~/at/bdep/cat-herder, 8 fleet copies under ~/github/atollogy/bdep) calls `ingest-gmd --as-memory` — `grep -rl 'memory sync-disk' ~/github/atollogy/bdep/*/.claude ~/at/bdep/cat-herder` empty → delete the alias + `test_sync_disk_is_a_thin_alias_of_the_bridge` | user (template + fleet re-seed); this repo's copy already converted |

## Graduation Log {#graduation-log}

| Date | Item | Trigger fired | Notes |
|------|------|---------------|-------|
| — | — | — | — |
