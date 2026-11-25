---
gmd: "0.1"
id: bsd-impressions
title: "ch-bsd impressions — refmatrix"
tags: [bsd, impressions]
---
# ch-bsd impressions {#root}

Window: the newest run bullets; this whole file is capped at 50 lines (`wc -l`). Fold the oldest bullets VERBATIM, ids unchanged, into one new `impression_bsd_ledger_*` memory, add one pointer line per folded id to [[bsd-impression-anchors]], and rewrite each `bsd-impressions#<id>` citation of a folded id to `bsd-impression-anchors#<id>`. Never delete an id.
rel: related-to -> [[bsd-impression-anchors]]

- 2026-11-25 (bug-318 confirm, ee36bb10): A CONFIRM REPLAYS THE r1 PROBE LIST VERBATIM BEFORE
  WIDENING. The fold coded "content verb wins" as "beats push/checkout/switch", so the exact r1
  probe (`git reset -q p && git commit`) still recorded `reset` with no rationale.
  {#imp-confirm-replays-r1-probes}
- 2026-11-25 (bug-318 r1, 9954e391): A CAPTURE RULE JUDGED ON THE HOOK ENVELOPE'S CWD MISSES THE
  ORCHESTRATED SESSION'S DOMINANT FORM. Subagent hooks land in the lead's ring with cwd = the dev
  tree while their commands run `cd /Volumes/littlebig/<clone> && git …` (360/551 live git
  events). Any STM capture keyed on cwd needs a test where envelope cwd differs from the target
  repo. {#imp-capture-cwd-is-not-the-repo}
- 2026-11-25 (bug-318 r1): A GAP DISCLOSED IN A DOCSTRING WITHOUT A COUNT IS THE CHEAP FIX AGAIN.
  "`cd X && git ...` is not followed" was the majority case. Ask for the real-data count before
  accepting a disclosed limitation. {#imp-disclosed-gap-needs-a-count}
- 2026-11-15 (scan-order r1): A SHAPE SCORE BUILT FOR RANKING IS NOT A CLASSIFIER. `> 0` on `_token_shape_score` admits every word of 12 or more letters through its length bonus, so `implementation` became a "named identifier". Reusing a ranking score as a gate needs its own threshold and a must-fail case of plain prose. {#imp-score-is-not-classifier}
- 2026-11-15 (T0 fresh r1, 5b04e2d): AN ORIGIN FALLBACK THAT FOLLOWS ONE HOP MISSES THE LAYOUT REVIEWERS ACTUALLY USE: CLONES OF CLONES. Count real origins before calling a residual "not live" (8 of 33 refmatrix clones point at another clone; every bsd review clone cut by the standard brief). {#imp-origin-chain-is-the-review-layout}
- 2026-11-15 (T0 fresh r1): "ROUTED TO TASK X'S RELEASE" WITH NO AC IN X IS A DEFERRAL WEARING A SCHEDULE. Check that the receiving spec holds the AC, both for P1 into 29.2 and for row 7's flags into 29.4 R2. {#imp-routed-needs-receiver-ac}
- 2026-11-15 (T0 fresh r1): A PROPOSAL'S COMMAND CAN CITE A FLAG THE RUNNER SPEC NEVER DEFINED (P5's `--files`). Diff each proposed invocation against the interface line. {#imp-proposal-flag-must-exist}
- 2026-11-15 (T0 fresh r2, f6b32e2): A RED WHOSE FIXTURE NEEDS THE MODULE UNDER CONSTRUCTION FAILS ON THE IMPORT AT BASE. Its stated-reason RED has to be a named mutation after GREEN, or the node never fails for the reason it guards. {#imp-fixture-needs-the-module}
- 2026-11-15 (T0 fresh r2): A CYCLE GUARD'S "FAILS, NOT HANGS" MUTATION IS ONLY AS SAFE AS THE BOUND BEHIND IT. Give the bound its own mutation. {#imp-bound-backs-the-cycle-mutation}
- 2026-11-15 (T0 fresh r2): "N FILES NAME X" IS A GREP RESULT. Separate "names it" from "reaches it through an import" and from "sits in the same list for another reason" before counting. {#imp-count-the-grep-not-the-list}
- 2026-11-15 (T0.1' r1, fff91a8): ALL 11 SPEC MUTATIONS KILLED, PLUS A GUARD+BOUND DOUBLE BREAK CAUGHT BY THE 30 S CHILD DEADLINE; convergence onto one resolver is real (the AC-1.7 static check alone kills M1.8). {#imp-t01-mutations-all-killed}
- 2026-11-15 (T0.1' r1): A DEFENSIVE ENV SCRUB (GIT_DIR STRIP) SHIPPED WITH A STATED HOOK SCENARIO AND NO TEST: real behaviour, mutation-invisible. Ask for a pinning case whenever GREEN adds a guard beyond the spec. {#imp-unpinned-defensive-guard}
- 2026-11-15 (T0.1' r1): RED-TIME `if <new file> exists` SCAFFOLDING OUTLIVES GREEN in fixture helpers; check RED's conditional copies at every GREEN review. {#imp-red-scaffold-outlives-green}
- 2026-11-15 (plan-31 specs 31.5/31.3/31.4 r1, c0de7dd): "LOCAL RUNTIME STATE" IS A CLAIM ABOUT EVERY REPO THE RELEASE REACHES. The spec checked `.gitignore` in refmatrix only; atlftpd ignores nothing under `.refmatrix/`, three repos' default branches lack the line, and `save-state --commit` runs `git add -A`. A new runtime dir that holds text ignores itself (`.gitignore` with `*` inside it). {#imp-local-state-is-a-fleet-claim}
- 2026-11-15 (plan-31 31.5 r1): A COST BAND MEASURED ON A TOY STORE PASSES THE CHEAP CASE. Hub words cost 2-3x identifiers in `build_context` on the live catalog copy, and the token stop that triggers the extra builds fired on 53% of prompts. Band the cost on a copy of the live catalog, in fresh processes, and count what each call built. {#imp-band-on-the-live-copy}
- 2026-11-15 (plan-31 31.5 r1): A BAND TABLE MUST BE TOTAL AND REACHABLE AT THE WINDOW'S N. Compute the Wilson table at the minimum n before writing the bands: at n = 80 no count reads `shrink`, and a two-interval rule left a cell with no band. {#imp-band-table-total-at-n}
- 2026-11-15 (plan-31 r1): THE FIFTH HAND-OFF WITH NO AC IN THE RECEIVER. bug-256 was routed into 31.5 after the spec was written, and the gate-tree helper was "suggested to 29.3", which has no such slice. When the lead routes a fold into a spec in review, the routing is a finding until the spec carries the AC. {#imp-handoff-without-sibling-ac-5th}
- 2026-11-15 (plan-31 31b r1): When a spec says a refused or skipped file "stays" or "is retried", read every pass that runs after the refusal in the same batch. A later pass that stamps the mtime undoes the retry. {#imp-later-pass-stamps-the-refused-file}
- 2026-11-15 (plan-31 31b r1): A row the code re-creates on every sync is not "legacy". Probe two syncs before you accept a guard built on the word; two specs (22.6 R4, bug-185 R10) inherited the premise. {#imp-legacy-row-recreated-each-sync}
- 2026-11-15 (plan-31 31b r1): "Taken whole by reference" has to be checked against the source's ACs, mutations and census record, not its prose. The prose came across; the ACs did not. {#imp-whole-by-reference-check-the-acs}
- 2026-11-15 (plan-31 31b r1): A producer census is not hypothetical when the store already holds 15,898 evidence-less edges on the verb. Find the writer (`link_part_of`) before you accept "one shipped entry". {#imp-census-find-the-writer}
- 2026-11-15 (plan-31 31b r1): When a probe copies a store to compare replicas, keep the project directory's name, or the partition re-scope fakes the result. {#imp-replica-probe-keeps-dir-name}
- 2026-11-15 (plan-31 31b r2): A fix that removes a broad purge also removes everything that purge was silently cleaning up. List what the purge deleted before accepting its replacement. {#imp-dropped-purge-drops-its-cleanup}
- 2026-11-15 (plan-31 31b r2): A freshness gate keyed on a stamp that every incremental pass refreshes proves nothing about a full re-derive. Ask which writer is the only one that sets the thing the gate reads. {#imp-gate-on-the-only-writer}
- 2026-11-15 (plan-31 31b r2): When a fold makes a broken route work (bug-203's `-i`), re-read that route for the defect the sibling route was just fixed for. {#imp-route-fixed-inherits-sibling-bug}
- 2026-11-15 (plan-31 31b r3): A purge that is moved has to take its pending-row bookkeeping with it, and the pending row's key must be the name the resolver will look up later, not the text the author wrote. {#imp-pending-key-is-the-lookup-name}
- 2026-11-15 (plan-31 31b r3): A marker that "only X writes" must name its writer's API. The convenient one may add a stamp, a hash or counts that turn the marker into something else. {#imp-marker-names-its-writer}
- 2026-11-15 (T0.8 r1): a pairing function that states one-to-one, earliest-eligible and a three-part key in its docstring passed with all five properties mutated away. The node only pinned the window width. A docstring invariant needs a must-fail input of its own. {#imp-docstring-invariant-needs-must-fail}
- 2026-11-15 (T0.8 r1): an appended per-invocation breakdown (`unknown=34`) satisfied an older tolerant `\bN\b` matcher and silently retired a mutation-killing node. When a line gains numbers, re-run the old mutation map against the new format. {#imp-new-numbers-satisfy-old-matcher}
- 2026-11-15 (T0.8 r1): a time-window join between two logs was checked against a copy of the live logs (613/613 within 1 s, none gained up to 30 s). Measuring the join on real rows settled the window question that reasoning about stamp order could not. {#imp-measure-join-on-real-rows}
