---
gmd: "0.1"
id: task-linked-readonly-store
title: "Linked read-only store: a clone's .refmatrix symlinked to a live store reads the graph and never writes or talks to a daemon"
tags: [task, store, subagents, safety, read-only]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-14
---

# Task: linked read-only store {#root}

> Status: drafting (2026-11-14). The user's design (Q16, "we can just check if the refmatrix dir
> is a symlink"), scheduled as Q16 a; **post-mod** since L128 (re-evaluated against the mod first, L127 and L129;
> [[plan-of-plans#post-mod]]); built on bug-212's
> store-level write check (bug-212, branch `task-bug212-worktree-hook-crashes`). Until it ships, agents use `scripts/rmx-master`. A ch-bsd spec round
> precedes approval.

rel: depends-on -> [[bug_registry#registry]]
rel: related-to -> [[task-agent-start-context]]

## Why {#why}

Subagents work in littlebig clones that have no store, so `rmx` there degrades to grep (Q15
measurement: 522 of 662 agent `rmx` calls were `rmx grep`). Pointing a clone's `.refmatrix/` at the
dev store with a symlink gives them the real graph, but every cwd-walking caller in the clone (the
test suite on dev code, the PostToolUse `rmx sync` hook) would then reach the live store, and dev
code talking to the live daemon or hub trips the version handshake (CLAUDE.md hard rule). The
symlink is therefore only safe if being linked switches the store into a full read-only mode.
Subagents are read-only against live stores by rule (`feedback_subagents_read_only_on_live_stores`);
this task makes the store enforce it. {#why-body}

## Requirements {#requirements}

1. **R1 Detect.** {#r1} A store is LINKED when its `.refmatrix` path is a symlink (checked on the
   unresolved path the caller found, before any `resolve()`), or when the resolved store dir lies
   outside the project root that found it. One function decides, in `store.py`.
2. **R2 No writes.** {#r2} bug-212's single store-level write check refuses every read-write open
   of a linked store with one `Error:` line naming the link and its target and saying writes go to
   the target's own tree. No other code path opens a linked store read-write (bug-212's AST guard
   covers it).
3. **R3 No daemon, no hub.** {#r3} A linked store never starts, connects to, pings or registers a
   daemon, and never contacts the hub: reads open the target's lock-free read snapshot
   (`catalog.read.duckdb` or the inactive slot per the existing reader order) read-only, in process.
   So dev code in a clone never meets the live daemon's version handshake.
4. **R4 Hooks.** {#r4} The sync/ingest hooks that land on a linked store print one note line
   ("linked read-only store: skipped") and exit 0; never silent, never an error loop.
5. **R5 Version skew is loud.** {#r5} If the snapshot's schema is newer or older than the reading
   code supports, the read fails with one `Error:` line naming both versions; no partial answer.

## Acceptance {#acceptance}

- **AC-1:** in a throwaway pair (store A, clone B with `B/.refmatrix -> A/.refmatrix`), `rmx context`
  from B answers from A's snapshot; A's daemon socket sees no connection (no ping, no op).
- **AC-2:** every write verb from B (`sync`, `ingest`, `memory add`, `protect`, `init`, `partition
  drop`) is refused with the one line; A's catalog and `facts.log` are byte-identical afterwards.
  Mutation: the link check removed → AC-2 fails.
- **AC-3:** the PostToolUse sync hook in B prints the note and exits 0.
- **AC-4:** a dev-version client in B never contacts the hub (no version handshake record).
- **AC-5:** a snapshot whose schema version differs from the reader's fails loudly (R5).

## Files {#files}

`src/refmatrix/store.py` (link detection, the write check), the root resolver in `cli.py` /
`discovery.py`, the daemon client entry (`daemon.call` / `require_daemon`), the hook bodies in
`hooks.py`, tests `tests/test_linked_readonly_store*.py`, `docs/INTEGRATION.md`,
`.claude/PROJECT_PROFILE.md#corpus` (replace the rmx-master instruction once shipped).

## Done {#done}

Implementation summary `workflow/implementation_summaries/task-linked-readonly-store.md`; the
littlebig clone recipe gains the symlink step; `scripts/rmx-master` is retired or kept as an alias.
