---
gmd: "0.1"
id: bsd-pattern-control-point-claim-without-census
title: "PATTERN: a fix placed at a named choke point claims to cover every caller without a census of the guarded resource's constructors (4 runs)"
tags: [bsd, pattern, control-point, census]
metadata:
  node_type: bsd-pattern
  occurrences: 4
  first_seen: 26.2 r2 9204814
  last_seen: 03d7b27
---

# PATTERN: control-point claim without a census {#root}

A fix is placed at a named choke point, and its docstring or docs claim "every X" passes through it.
The RED set is drawn from the callers already known to reach that point, so the suite can only
confirm the premise. Sightings: 26.2 r2 (`9204814`), bug-212 r1 `#s-1`, and bug-212 r2/r3 `#b-1`
(`_store_rw()` refuses a git-tracked catalog, but `verbs.local_write` and four direct `Store(root)`
opens never reach it; 10/10 probes wrote the tracked catalog). {#shape}

rel: evidence-for -> [[bsd-bug212-r2-67f55cb#b-1]]

**Rule:** before accepting a check at "the" control point, grep or AST-scan every construction of the
guarded resource, probe one caller per family, and land a bypass test that fails when `src/` adds a
new direct construction outside an allowlist. {#rule}

**Amended 2026-11-14 (bug-212 r4, 03d7b27, fourth occurrence):** the census must key on the guarded
RESOURCE, not one constructor of it. r2 prescribed a scan for read-write `Store(`; `rmx compact` and
`migrate-to-duckdb --overwrite` reach the same catalog file through `open_duckdb` and a rename, so the
scan stayed green. Enumerate every way the guarded file is opened or replaced (class constructor, raw
opener, rename/unlink onto its name), give the "sees" guard one site per family, and treat a
prescribed scanner as a hypothesis to probe too. {#amend-census-the-resource}

Evidence: `workflow/bullshit/2026-11-14-0040-bug212-r4-03d7b27.md` on branch
`task-bug212-worktree-hook-crashes` (`028349b`); the typed edge lands when that branch merges.
