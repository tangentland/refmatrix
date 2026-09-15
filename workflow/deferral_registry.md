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

## Graduation Log {#graduation-log}

| Date | Item | Trigger fired | Notes |
|------|------|---------------|-------|
| — | — | — | — |
