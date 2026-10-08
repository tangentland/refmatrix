---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-10-07 (session 94f97944). Prior handoff archived at
`workflow/past_handoffs/010-bsd-r3-r6-plan16-specs_2026-10-07.md`.

rel: supersedes -> [[handoff-010-bsd-r3-r6-plan16-specs]]

## State {#state}

- **Branch:** `bsd-r1-remedy`, ~80 commits ahead of `master`, unmerged. The merge gate is a CLEAN
  ch-bsd round. **Round 10 was launched on `a3a324e..06711cd` and its result is NOT yet read.**
  Read `workflow/bullshit/` for an r10 report (newer than
  `2026-10-07-1210-r9-context-read-path-wrong-partition-a3a324e.md`); commit it, then remedy or merge.
- **Deployed:** master = `aeee560` = **0.76.3** (three hotfixes cherry-picked today):
  - 0.76.1: bug-085, batched Lance deletes;
  - 0.76.2: bug-090, a fixed launchd PATH;
  - 0.76.3: bug-093, the bulk watch semantic pass.

  All 8 daemons are verified on 0.76.3. The hub process is still 0.76.2 (functionally fine).
- **Lance compacted by hand:** refmatrix 1.3 GB→105 MB, viascope 925→229 MB, cliquedb
  1.1 GB→62 MB. Backups deleted at the user's request.
- **Dev venv:** bug-092 is fixed. `.venv-eval` no longer borrows dependencies from the ambient
  PYTHONPATH.

{#state-body}

## What this session did {#did}

- **bug-085 named by py-spy.** Per-entity Lance deletes under `_store_lock`; fixed and deployed.
  py-spy 0.4.2 is a uv tool at `~/.local/bin`, used with `sudo -n`.
- **bug-093.** The watch semantic pass did per-row upserts (61 s → 15 s on a `cli.py` re-sync);
  fixed and deployed.
- **ch-bsd rounds 6–9 remediated** (round 10 pending):
  - offline models;
  - rerank warnings on every route;
  - context reads on a private snapshot with partition binding under the mirror lock;
  - a real rerank budget;
  - no model calls under the lock;
  - `vector_delete_failed` on every path.
- **Explorations:** concept similarity, agent context usage, and the adaptive memory budget.
- **ADR-0004:** its helix half supersedes plan-11 (user). An amendment adds the relation taxonomy
  from `docs/ideas.txt`, proximity tiers, Aster's counters + adaptive merge, the
  decay-never-loses-knowledge rules, and the adjacency-shape evidence across six stores (heavy
  tail; 2-hop saturation not hub-driven; dense ids save 15–42% and ORDER does not).
- **Specs:** plans 17, 19 and 20, plan-21 (agent context), plan-22 (audited removal + REPAIR),
  plan-23 (bounded-write harness).
- **Plan review applied (C1–C12);** `workflow/plan-review-2026-10-07.md` has the wave order.

{#did-body}

## Next {#next}

1. **Read and act on ch-bsd round 10.** Remedy or merge `bsd-r1-remedy` → `master` (`--no-ff`).
   Then deploy: ff `~/refmatrix`, `rmx hub relaunch-fleet`, `rmx install-hooks --apply --force`.
2. **Wave 0 (docs):** plan-16 revision 5 + its spec review; spec reviews of plans 17/19/21/22/23.
3. **Wave 1:** plan-23 first (the harness), then 17.1/17.2, 19.1/19.2, 21.1, and 22.1–22.3
   (bug-086 is 22.3).
4. **Needs the user's time:** the 19.5 hook-limit probe (scratch project), and the 20.1 gold-label
   review.

{#next-body}

## Open, not forgotten {#open}

- **bug-093 follow-ups:** yield the writer between files in the watch flush (plan-23); add an
  op-start log line per daemon op (unowned).
- **bug-088:** tests can still reach live sockets. Second sighting today: a test of mine sent a
  bulk-forget DRY RUN to the live daemon (nothing deleted). The refuse stage is deferred.
- **bug-089:** fixed on the branch (the `search-dense` reranked render).
- **bug-091:** an FSEvents timing flake.
- **bug-081:** fixed by 16.5.
- The second implicit `npm install` (`eval/memaware/run.sh:39`) is assumed "leave it" and awaits
  the user's confirmation.

{#open-body}
