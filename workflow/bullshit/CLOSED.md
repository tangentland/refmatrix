---
gmd: "0.1"
id: bsd-closed-findings
title: "ch-bsd closed findings: each with the evidence that closed it (fix sha on master or L-row)"
tags: [ch-bsd, ledger, closed-findings, f5]
metadata:
  node_type: ledger
  created: 2026-11-24
---

# Closed ch-bsd findings {#root}

Rows move here from [[bsd-open-findings]] only with evidence. Not imported anywhere: a history,
read on demand. The `outcome` column is F5's precision measure: `upheld` (fixed) or `overruled`
(ruled not a defect). {#purpose}

rel: implements -> [[refmatrix/ch-bsd-assessment-2026-11-23#f5]]

The `question` column is as in [[bsd-open-findings#question-column]]; the tally is `python3 scripts/bsd-tally.py`. Backfilled 2026-11-25 from each row's report: five reports name questions (t02-r1, t03-r1, 315-r1, bug318-r1; the rest are `unnamed`). {#question-column}


Backfill (2026-11-24, post-reset reports 2026-11-15 onward): level is the report's own label;
`SKETCHY → BULLSHIT (F8)` and `GATE (F8)` are the re-ratings in
[[refmatrix/ch-bsd-assessment-2026-11-23#f8-tables]], re-probed at master in
[[bsd-reprobe-c7550ad5]]. Every sha below passes `git merge-base --is-ancestor <sha> master`
(master `9414fcd9`). {#backfill-note}

| id | report | level | question | finding (one line) | outcome | evidence | closed |
|---|---|---|---|---|---|---|---|
| 31a-spec-r1-B1 | [[bsd-spec-31a-r1-c0de7dd]] | BULLSHIT | unnamed | capture text would land in fleet repos' git status; D1 decided on a "sha256 only" POP row | upheld | fixed `3225a16` (merged `606c0c83`): capture dir writes its own `.gitignore`; confirmed [[bsd-spec-31a-r2-3225a16]]; L133, L140 | 2026-11-15 |
| 31a-spec-r1-B2 | [[bsd-spec-31a-r1-c0de7dd]] | BULLSHIT | unnamed | shared gate-tree helper deferred to 29.3, which has no slice for it | upheld | fixed `3225a16` (merged `606c0c83`): 31.3 builds the helper; confirmed [[bsd-spec-31a-r2-3225a16]]; L133 | 2026-11-15 |
| 31a-spec-r1-B3 | [[bsd-spec-31a-r1-c0de7dd]] | BULLSHIT | unnamed | bug-256 routed into 31.5 with no requirement, AC or mutation | upheld | fixed `3225a16` (merged `606c0c83`); confirmed [[bsd-spec-31a-r2-3225a16]]; L133 | 2026-11-15 |
| 31b-spec-r1-B1 | [[bsd-spec-31b-r1-a4d245a]] | BULLSHIT | unnamed | on the sync route a refused file loses its rows and the refusal goes quiet (probe) | upheld | fixed `7ceedb4` (merged `662abfa8`), three-arm probe re-run in [[bsd-spec-31b-r2-7ceedb4]]; L139, L147 | 2026-11-15 |
| 31b-spec-r1-B2 | [[bsd-spec-31b-r1-a4d245a]] | BULLSHIT | unnamed | 31.2 "nothing prunes them here" is a deferral with no anchor | upheld | fixed `7ceedb4` (merged `662abfa8`): one manifest per batch, bug-263 the retention anchor; confirmed [[bsd-spec-31b-r2-7ceedb4]]; L139 | 2026-11-15 |
| t02-r1-B1 | [[bsd-t02-r1-1121b4e]] | BULLSHIT | SA-6, SA-2 | bug-267 in-host path in `src/` runs only under a `signal.signal` test double | upheld | fixed `6bf00829` (fold `a7b30b39`, merged `b0d5eabf`); confirm-lite in the same report (host probe: stop 1.0 s, exit 7); L169 | 2026-11-15 |
| t02-r1-B2 | [[bsd-t02-r1-1121b4e]] | BULLSHIT | SA-8, SA-3 | seven `/tmp` roots in touched files stay allow-listed "move it … next" | upheld | fixed `eb9ae87e` (fold `a7b30b39`, merged `b0d5eabf`): roots on `short_root`; L169 | 2026-11-15 |
| t03-r1-B1 | [[bsd-t03-r1-041e3ab]] | BULLSHIT | SA-3, SA-4 | hub-shared client close unbounded at stop (45 s per role; 5.5 s measured) | upheld | fixed `1bb7e9d3` + `937d21c` (merged `c42a2b04`); confirm-lite in the same report (`_close_workers` 0.000 s); L177, L180, L181 | 2026-11-16 |
| t04-r1-B1 | [[bsd-t04-r1-5eae7916]] | BULLSHIT | unnamed | two mock-registry rows defer to the closed plan-6 sweep | upheld | fixed `0038f810` (merged `21728dac`); confirm-lite in the same report; L186 | 2026-11-18 |
| t05-r1-b-1 | [[bsd-t05-r1-61b0666c]] | BULLSHIT | unnamed | a compiling brief drops every unembedded memory with `skipped=0` | upheld | fixed `fa6d6f3e` + `521f32b6` (merged `a22cdaa2`); held on fresh corpora in [[bsd-t05-confirm-3f9ce2a3]], closed in [[bsd-t05-confirm2-521f32b6]]; L188, L189 | 2026-11-19 |
| t05-cl-b-1-r2 | [[bsd-t05-confirm-3f9ce2a3]] | BULLSHIT | unnamed | after `--save` the next compiling brief counts its saved brief rows as unembedded (18 vs 3) | upheld | fixed `521f32b6` (merged `a22cdaa2`); confirmed [[bsd-t05-confirm2-521f32b6]]; L189 | 2026-11-19 |
| s1-r1-b-1 | [[bsd-s1-r1-be1c6b6c]] | BULLSHIT | unnamed | kept fragment-file moves and `_unread_fragment_dirs` have no test (MX4/MX5 survive) | upheld | fixed `0d0655a0` (merged `72b07b6d`); MX4/MX7 killed in [[bsd-s1-confirm-0d0655a0]]; L191 | 2026-11-19 |
| s1-r1-b-2 | [[bsd-s1-r1-be1c6b6c]] | BULLSHIT | unnamed | D1=b deferral to 29.2 R7 deploy B has no requirement there | upheld | fixed `f7737a5e` (29.2 `#r7-s1-sqlite`, AC-30); confirmed [[bsd-s1-confirm-0d0655a0]]; L191 | 2026-11-19 |
| t06-r1-b-1 | [[bsd-t06-r1-982c3d36]] | BULLSHIT | unnamed | the `-rr` rows are mostly unreranked (recall-rr = dense top 50 on 86/120; bug-303) | upheld | fixed `9d574536` (merged `c222c1c3`); confirmed [[bsd-t06-confirm-9d574536]] (0/120); L196 | 2026-11-24 |
| t06-r1-b-2 | [[bsd-t06-r1-982c3d36]] | BULLSHIT | unnamed | the ‡ wider-pool mechanism is false in README, PERFORMANCE, REPORT and the artifact | upheld | fixed `9d574536` (merged `c222c1c3`); confirmed [[bsd-t06-confirm-9d574536]]; L196 | 2026-11-24 |
| 294a-r1-b-1 | [[bsd-294a-r1-1bb14a5b]] | BULLSHIT | unnamed | a failed merge gate passes on re-run; a different merge inherits it (bug-304) | upheld | fixed `f639c6b2` + `54747fce` (merged `bfc34358`); confirmed [[bsd-294a-confirm-54747fce]]; L197, L207 | 2026-11-24 |
| cah-r1-b-1 | [[bsd-cah-r1-cbbe9e3f]] | BULLSHIT | unnamed | read gate keyed by `session_id` only: teammates denied, a teammate lifts the lead's gate (bug-307) | upheld | fixed `8daaa0aa` (fold to `4784cdd5`, merged `641401c4`); confirmed [[bsd-cah-confirm-4784cdd5]]; L202 | 2026-11-24 |
| cah-r1-b-2 | [[bsd-cah-r1-cbbe9e3f]] | BULLSHIT | unnamed | a subagent's PreCompact cuts its own summary and gets the lead's handoff (bug-307) | upheld | fixed `8daaa0aa` (fold to `4784cdd5`, merged `641401c4`); confirmed [[bsd-cah-confirm-4784cdd5]]; L202 | 2026-11-24 |
| cah-r1-b-3 | [[bsd-cah-r1-cbbe9e3f]] | BULLSHIT | unnamed | an unwritable `handoffs/` traps the session for 24 h (bug-308) | upheld | fixed `8daaa0aa` (fold to `4784cdd5`, merged `641401c4`); confirmed [[bsd-cah-confirm-4784cdd5]]; L202 | 2026-11-24 |
| b300-r1-b-1 | [[bsd-b300-r1-5d28d2a5]] | BULLSHIT | unnamed | the L199 length applies only when a block matched; a title/tag-only query flips order | upheld | fixed by `9312ef1d` (merged `09175133`); confirmed [[bsd-b300-confirm-9312ef1d]]; L209 | 2026-11-24 |
| scanorder-r1-S2 | [[bsd-scanorder-r1-ca22b79]] | SKETCHY → BULLSHIT (F8) | unnamed | named identifiers cut by PPR + `max_concepts` before the reorder; tier 1 empty on the real hook | upheld | fixed `5b38d71c` (merged `62cafc95`); real-hook re-probe and killed mutant A5-S2 in [[bsd-reprobe-c7550ad5]]; L120 (`workflow/archive/plan-review-2026-11-13.md`) | 2026-11-24 |
| scanorder-r1-S3 | [[bsd-scanorder-r1-ca22b79]] | SKETCHY → BULLSHIT (F8) | unnamed | composite marked sent when `fit_blocks` dropped it, then suppressed as unchanged | upheld | fixed `5b38d71c` (merged `62cafc95`); re-probed in [[bsd-reprobe-c7550ad5]]; L120 | 2026-11-24 |
| t02-r1-S3 | [[bsd-t02-r1-1121b4e]] | SKETCHY → BULLSHIT (F8) | unnamed | second pool drain outside `_StopDeadline`; conftest adds 30 s slack to absorb it | upheld | fixed `6bf00829` (merged `b0d5eabf`): helper and slack deleted; re-probed in [[bsd-reprobe-c7550ad5]]; L169 | 2026-11-24 |
| 315-r1-S1 | [[bsd-315-r1-51bbdfb]] | SKETCHY → BULLSHIT (F8) | SA-7 | injection capture flips scan-prompt / recall exit to 1 (surrogate prompt, unlistable dir; bug-276) | upheld | fixed `83125cc6` (merged `655fad9f`); re-probed in [[bsd-reprobe-c7550ad5]] (rc 0, byte-equal stdout); L178 | 2026-11-24 |
| 315-r1-S2 | [[bsd-315-r1-51bbdfb]] | SKETCHY → BULLSHIT (F8) | SA-3 | unchanged composite re-sent, skewing `suppressed_unchanged` (bug-277) | upheld | fixed `83125cc6` (merged `655fad9f`); re-probed in [[bsd-reprobe-c7550ad5]]; L178 | 2026-11-24 |
| 315-r1-S4 | [[bsd-315-r1-51bbdfb]] | SKETCHY → BULLSHIT (F8) | unnamed | bug-268 fixed on one of five focus-graph readers | upheld | fixed `83125cc6` (merged `655fad9f`); all five readers rc 0 in [[bsd-reprobe-c7550ad5]]; L178 | 2026-11-24 |
| t04-r1-S1 | [[bsd-t04-r1-5eae7916]] | SKETCHY → BULLSHIT (F8) | unnamed | mock-registry guard blind to module-object swaps; a live unregistered swap passed | upheld | fixed `0038f810` (merged `21728dac`); confirm-lite in the same report (all 7 r1 shapes seen); L186 | 2026-11-18 |
| s1-r1-s-1 | [[bsd-s1-r1-be1c6b6c]] | SKETCHY → BULLSHIT (F8) | unnamed | the kept `_migrate_*` moves are dead in effect on DuckDB | upheld | fixed `0d0655a0` (merged `72b07b6d`): moves deleted; confirmed [[bsd-s1-confirm-0d0655a0]]; L191 | 2026-11-19 |
| 294a-r1-s-1 | [[bsd-294a-r1-1bb14a5b]] | SKETCHY → BULLSHIT (F8) | unnamed | `tier_of` puts `test_suite_tiers.py` in `devtree` (not run in any clone or lane) | upheld | fixed `f639c6b2` (merged `bfc34358`); re-probed in [[bsd-reprobe-c7550ad5]] (devtree = the 6 L192 files); L197 | 2026-11-24 |
| cah-r1-s-1 | [[bsd-cah-r1-cbbe9e3f]] | SKETCHY → BULLSHIT (F8) | unnamed | deny by exit 2 = click usage error; a rollback `rmx` blocks every tool call (bug-308) | upheld | fixed `8daaa0aa` (merged `641401c4`); confirmed [[bsd-cah-confirm-4784cdd5]]; L202 | 2026-11-24 |
| cah-r1-s-2 | [[bsd-cah-r1-cbbe9e3f]] | SKETCHY → BULLSHIT (F8) | unnamed | PreCompact save-state unbounded; the bound test asserted over an empty list | upheld | fixed `4784cdd5` (merged `641401c4`): 10 s bound; confirmed [[bsd-cah-confirm-4784cdd5]]; L202, L204 | 2026-11-24 |
| cah-cl-s-3 | [[bsd-cah-confirm-4784cdd5]] | SKETCHY → BULLSHIT (F8) | unnamed | MCP `rmx_memory_recall(recent, pack)` raised `VerbArgsError` (map sends `recent` to retired `precompact`) | upheld | fixed `a1e4a6a0` (merged `641401c4`); real `rmx mcp` stdio call and killed mutant in [[bsd-reprobe-c7550ad5]]; L208 | 2026-11-24 |
| t08-r1-S1 | [[bsd-t08-r1-e314b19]] | GATE (F8) | - | pairing invariants unpinned (8 of 16 mutations survived) | upheld | fixed `aca629cb` + `c168f310` (merged `e997154d`); M8.5/6/13-16 killed in [[bsd-reprobe-c7550ad5]]; L143 | 2026-11-24 |
| t08-r1-S2 | [[bsd-t08-r1-e314b19]] | GATE (F8) | - | new printed counters have no fixture; a silent drop survives | upheld | fixed `aca629cb` (merged `e997154d`); M8.7-M8.9 killed in [[bsd-reprobe-c7550ad5]]; L143 | 2026-11-24 |
| t02-r1-S1 | [[bsd-t02-r1-1121b4e]] | GATE (F8) | - | no test checks AC-5's in-process daemon is stopped (X1 survives) | upheld | fixed `eb9ae87e` (merged `b0d5eabf`); X1 killed in [[bsd-reprobe-c7550ad5]]; L169 | 2026-11-24 |
| t02-r1-S2 | [[bsd-t02-r1-1121b4e]] | GATE (F8) | - | L154 resource-tracker exemption has no test (X2 survives) | upheld | fixed `eb9ae87e` (merged `b0d5eabf`); X2 killed in [[bsd-reprobe-c7550ad5]]; L169 | 2026-11-24 |
| t03-r1-S1 | [[bsd-t03-r1-041e3ab]] | GATE (F8) | - | abandon branch's kill and retired flag unpinned (M3, M4 survive) | upheld | fixed `e3e131c8` (merged `c42a2b04`); M3/M4 killed in [[bsd-reprobe-c7550ad5]]; L177 | 2026-11-24 |
| t03-r1-S2 | [[bsd-t03-r1-041e3ab]] | GATE (F8) | - | two stop guards reached, not pinned (M5, M6 survive) | upheld | fixed `e3e131c8` (merged `c42a2b04`); M5/M6 killed in [[bsd-reprobe-c7550ad5]]; L177 | 2026-11-24 |
| t03-r1-S3 | [[bsd-t03-r1-041e3ab]] | GATE (F8) | - | the census's L159 readiness form is fooled 5 of 5 | upheld | fixed `1bb7e9d3` (merged `c42a2b04`); S3a/S3b killed in [[bsd-reprobe-c7550ad5]]; L177 | 2026-11-24 |
| 315-r1-S3 | [[bsd-315-r1-51bbdfb]] | GATE (F8) | - | M2-1a survives: the stopwords fixture never holds `the` as a concept | upheld | fixed `dfbfdc3d` (merged `655fad9f`); M2-1a killed in [[bsd-reprobe-c7550ad5]]; L178 | 2026-11-24 |
| t05-r1-s-1 | [[bsd-t05-r1-61b0666c]] | GATE (F8) | - | G7 survives though the real-mirror harness can kill it | upheld | fixed `f97977b8` (merged `a22cdaa2`); closed in [[bsd-t05-confirm-3f9ce2a3]], G7 killed again in [[bsd-reprobe-c7550ad5]]; L188 | 2026-11-24 |
| b300-r1-s-1 | [[bsd-b300-r1-5d28d2a5]] | SKETCHY (handed off) | - | a re-added memory is ranked by a forgotten same-name memory's blocks; handed to bug-302 | upheld | bug-302 fixed `9edfdbf1` + `21125243` (merged `6c6aa048`, release 0.85.1 `69e10ffd`); L209 | 2026-11-24 |
| t03-confirm-A2 | 2026-11-16 bsd-t03 confirm-lite (`4a0f4498`) | GATE (rated by the lead under P1, L218) | - | mutation A2 (`retire()` never sets `_retired`) survived the t03 verify set | upheld | L181 fold `5f418cdb` added the B1-node assertion; `ff6dd09a` logs the mutant failing in 1.16 s; both on master | 2026-11-24 |
| b318-r1-B1 | [[bsd-bug318-r1-9954e391]] | BULLSHIT | SA-1 | milestone capture judges `cd <repo> && git` against the hook cwd | upheld | fold 2 `ee36bb10` (per-call repo through cd/pushd/subshell/-C); closed by the confirm-lite probes; merged `4ae4ecef` | 2026-11-25 |
| b318-r1-B2 | [[bsd-bug318-r1-9954e391]] | BULLSHIT | SA-3 | only the first ref-moving git call in a command counts | upheld | fold 2 `ee36bb10` + fold 3 `b7ae4b00` (a content verb beats every non-content verb); lead verify: mutant `2654e11f` (old rule) fails 3 cases of `test_a_content_verb_beats_every_other_ref_moving_verb`; merged `4ae4ecef` | 2026-11-25 |
| b318-r1-B3 | [[bsd-bug318-r1-9954e391]] | BULLSHIT | SA-7 | failed pre-read swallowed; missing pre record falls back to the last milestone's sig | upheld | fold 2 `ee36bb10` (pre errors parked and said; no ring fallback); closed by the confirm-lite fallback probe; merged `4ae4ecef` | 2026-11-25 |
| b318-r1-G1 | [[bsd-bug318-r1-9954e391]] | GATE | - | mutant M4 (no reverse-priority cut order) survives | upheld | M4 killed by `test_a_digest_over_the_cap_loses_milestones_before_topics_and_arc` (`ee36bb10`); merged `4ae4ecef` | 2026-11-25 |
| b318-r1-G2 | [[bsd-bug318-r1-9954e391]] | GATE | - | mutant M7 (dedup by terse, not sha) survives | upheld | M7 killed by `test_digest_keeps_one_line_per_sha_and_the_content_verb` (`ee36bb10`); merged `4ae4ecef` | 2026-11-25 |
| c2-r1-g-1 | [[bsd-c2-r1-9afff800]] | GATE | SA-6 | the boot sweep's young-.tmp keep (`hook_writes.py:327`, 60 s) was unpinned; mutant `c819b066` survived | upheld | fixed `e1421d17` (merged `6b27f219`): `test_the_boot_sweep_keeps_a_young_tmp_and_removes_an_old_one` fails on the mutant (`{'kept': 0, 'removed': 5} == {'kept': 2, 'removed': 3}`) | 2026-11-25 |
| i1b1-r1-b-1 | [[bsd-i1b1-r1-2f392131]] | BULLSHIT | SA-3 | `rules replay` rebuilds tool_input from the ring's lossy `detail`; a bind on `content`/`new_string` (or a Bash key other than `command`) reads a silent hits 0 | upheld | fixed `9c7394dd` (merged `bf29ded2`): replay names `unmeasurable: bind[0].match.content is not stored in the ring`; probe re-run GO ([[bsd-i1b1-confirm-87a599c4#probes]]); F1 killed | 2026-11-25 |
| i1b1-r1-b-2 | [[bsd-i1b1-r1-2f392131]] | BULLSHIT | none: dead-symbol lint for new src modules | `KIND_DIR` has no reader, so a deny under `.claude/rules/` compiles (and is also a native always-on rule); `compile_project` dead | upheld | fixed `9c7394dd` (merged `bf29ded2`): `KIND_DIR` read in `_parse`, a deny under rules/ refused; `compile_project` deleted; F2 killed | 2026-11-25 |
| i1b1-r1-g-1..g-4 | [[bsd-i1b1-r1-2f392131]] | GATE | - | survivors: replay drops `unless` (M27b); `require_unit=False` for triggers/checks (X2); the `not force` overwrite guard (X1); a marked hook with no generated counterpart (X3) | upheld | fixed `4bac1ce9` (merged `bf29ded2`): M27b, X2, X3, X1 each fail a named test ([[bsd-i1b1-confirm-87a599c4#mutants]]) | 2026-11-25 |

{#closed-table}
