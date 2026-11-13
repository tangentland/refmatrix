---
gmd: "0.1"
id: bsd-pattern-control-point-claim-without-census
title: "PATTERN: a fix placed at a named choke point claims to cover every caller without a census of the guarded resource's constructors (3 runs)"
tags: [bsd, pattern, control-point, census]
metadata:
  node_type: bsd-pattern
  occurrences: 3
  first_seen: 26.2 r2 9204814
  last_seen: 67f55cb
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
