---
gmd: "0.1"
id: impl-remedy-plan-2-hooks-reproducible
title: "Plan-2 remediation after ch-bsd bsd-plan2 (03f46b8)"
tags: [implementation-summary, plan-2, remediation]
metadata:
  node_type: implementation-summary
  plan: plan-2-hooks-reproducible
---

# Plan-2 remediation {#root}

rel: implements -> [[plan-2-hooks-reproducible]]
rel: evidence-for -> [[bsd-plan2-hooks-reproducible-03f46b8]]

| Finding | Fix |
|---------|-----|
| #b-1 dead `--enforce` | `want()` returns True whenever `enforce is True`; test renders with no scripts on disk |
| #b-2 prefix signature deletes user hooks | `_RMX_HOOK_SIGNATURES` names the two exact scripts; test seeds `enforce-my-own-policy.sh` and proves it survives `--force` |
| #b-3 docs dropped | README hooks table (nine events, settings.json, `--check`), `docs/INTEGRATION.md`, `docs/hooks/intuition-style-hooks.md`; `tests/test_docs_hooks_target.py` |
| #s-4 check() blind spots | multiset of full entry JSON (duplicates, extra keys), foreign hooks listed as `?` lines, search scripts compared to `render_scripts()` |
| #s-5 status before gate | plan back to `in-progress`; task specs `complete` |
| #s-6 Stop promote | decision Q4 recorded; `focus summarize --promote` refuses loudly with the daemon down |
| #s-11 busy ≠ absent | `ingest-gmd --detach` distinguishes busy (retries `RMX_DETACH_WAIT_S`, busy-specific message) from absent |
| #m-7 flags only via claude path | recorded on every project-scope `--apply` |
| #m-8 registry / template drift | mock registry rows; enforcement command strings documented as mirroring cat-herder `.claude/settings.json` |
| #m-9 hooks not yet run | requires a Claude Code restart (user action) |

Also: the `set -o #` chain (rmxgrep piped-stdin rule, function-not-alias bashrc) shipped in cf3d87d.
