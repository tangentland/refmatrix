---
gmd: "0.1"
id: plan-31-pre-mod-loose-ends
title: "Plan 31: pre-mod loose ends — graph correctness and GMD hardening admitted under the freeze"
tags: [plan, gmd, graph-correctness, freeze, loose-ends]
metadata:
  node_type: plan
  status: approved
  created: 2026-11-15
---

# Plan 31: pre-mod loose ends {#root}

**Date:** 2026-11-15. **Status:** approved — its six tasks (31.1-31.6) each have a task spec written by
ch-architect on Fable and approved on a ch-bsd MEH-only GO (ruling L125): 31.3, 31.4 and 31.5 by
L140, 31.1, 31.6 and 31.2 by L149 ([[plan-of-plans#rulings]]), per [[orchestration#planning]]. **Origin:** the user, 2026-11-15: "write the freeze
line and register the five", after the lead's GMD assessment. The fifth item is plan-30's task 30.6. 31.6 (bug-251) admitted by the user, Q30 = a, 2026-11-15.

rel: part-of -> [[plan-of-plans#freeze]]
rel: related-to -> [[plan-30-materialisation]]
rel: depends-on -> [[orchestration]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[plan-10-injection-dedup]]

## Why {#why}

The goal before the mod transition: the core concept/graph representation more useful, context
succinct and relevant, performance improved, busywork removed, loose ends tied up (the user,
2026-11-15). Tasks 31.1-31.4 and 31.6 are the graph-correctness and GMD-hardening items that serve that goal
and survive the transition, and 31.5 is the injection measurement (Q27 = b); GMD tooling that only adds features went to the post-mod list
([[plan-of-plans#post-mod]]).

## Tasks {#tasks}

### 31.1 One bad markdown file no longer demotes the batch (bug-244) {#t1}

A non-string frontmatter `id:` (or `title:`) is refused at parse time, so the file lands in
`skipped_unparseable`, counted and named, while the rest of the batch is GMD-parsed. The S2 / M2
tests of 0.83.1 use the list-valued `id:` as their real raising input; this task's RED gives them
another real raising input or a registered patch of `ingest_gmd_paths` (L112a). Fleet repos are
measured for the shape first. {#t1-body}

**Spec:** [[task-31.1-frontmatter-type-refusal]] (approved by L149 on ch-bsd r3's MEH-only GO).
It closes bug-244 with bug-255 (the lint refuses the same shapes, and the gate checks the two
sides agree), bug-258 (the skip reaches the caller on `rmx ingest` and `rmx sync`), bug-264
(a plain edit of a synced GMD doc no longer drops its anchors' inbound edges; moved here by
L144) and bug-206 (an anchor an edit removed is removed, on the bridge too; L148). No file in
the fleet has the shape (0 of 1,464 repo files, 0 of 1,057 memory files). `plan-31 D11`
(decided, [[plan-of-plans#decisions]]): the rest lands, then `Error:` and exit 1. The S2 / M2
tests get a registered patch. {#t1-spec}

### 31.2 Purge, vacuum and replay agree about learned evidence (bug-107, bug-247) {#t2}

`purge_path` stops deleting protected learned rows on an edited or deleted file (or drops them only
through an audited, logged path); `vacuum` logs what it drops; a rebuild from `facts.log` does not
resurrect evidence of a file changed in place. Inputs: the count in
[[measurement-learned-rows-cli-store-2026-11-14]] (28,164 orphaned learned evidence rows, 26%), the
order probe on branch `spec-29-7-learned-rekey` (`workflow/measurements/task-29.7-order-probe/`),
bug-107's classification question, and plan-22's audited-removal path. The spec decides what
happens to the existing orphans (re-attach, drop with a manifest, or keep), as a user decision.
Grep learning stays off until this lands. Runs after 29.5 (the purge code moves to
`store_removal.py`). {#t2-body}

**Spec:** [[task-31.2-learned-evidence-agreement]] (approved by L149 on ch-bsd r3's MEH-only
GO). It closes bug-107 and bug-247 with bug-259, bug-260 and bug-262 (the compaction and the
replica's two unapplied clears) and bug-203 (`rmx sync -i` reaches the writer; L136). It takes
22.6 R4 whole, without 16.6's sidecar, and the learned-row halves of 22.6 R3 and R5 (L134).
`plan-31 D14` (decided by the user, [[plan-of-plans#decisions]]): the orphaned learned rows
that resolve are re-attached and the rest are deleted with a manifest; what "resolved" means
is Q38, open, and the spec carries both readings. On the copy of 2026-11-15 the store holds
30,131 such rows, not the 28,164 above. The store write is the lead's `rmx vacuum`, after a
dry run. {#t2-spec}

### 31.3 Ledger bullets must carry an anchor (bug-242 guard) {#t3}

A lint rule: in `workflow/bullshit/IMPRESSIONS.md` and the impression ledgers, every
`- 20YY-MM-DD` bullet ends with exactly one `{#id}`; a cut bullet fails the lint. RED with a
truncated-bullet fixture. About an hour. {#t3-body}

**Spec:** [[task-31.3-ledger-anchor-guard]] (approved by L140 on ch-bsd r2's MEH-only GO). It is
a third step in `scripts/lint-gmd.sh`, not a rule in the vendored linter, and it builds the one
shared helper for the gate's test trees. The census found 15 whole dated bullets in six folded
ledgers that never had an id; `plan-31 D7` (decided, [[plan-of-plans#decisions]]) gives them
ids, and that edit lands before the task's GREEN starts (applied 2026-11-15). {#t3-spec}

### 31.4 Retire the warnings nobody acts on {#t4}

The repo lint carries 89 standing warnings. Each warning class is either made an error (and its
instances fixed) or retired from the linter, with the reason recorded; the target is zero standing
warnings, so a new warning is read. Busywork removed, not added: no per-warning fixing of a class
that is retired. {#t4-body}

**Spec:** [[task-31.4-retire-standing-warnings]] (approved by L140 on ch-bsd r2's MEH-only GO).
The 89 are four classes: `unknown-memory-type` 47, `rel-target-shape` 28, `ambiguous-stem` 9,
`unknown-verb` 5; 52 of them sit in the memory dir. All four fail the gate through one opt-in
linter flag and none is retired (`plan-31 D8`-`D10`, decided, [[plan-of-plans#decisions]]; D10
is the user's consent to change the upstream GMD linter, Q37 = a). {#t4-spec}

### 31.5 Scan-prompt injection: measure each block's use, then cut and tighten (Q27 = b) {#t5}

The user, 2026-11-15: reduce the scan-prompt injection before the dedup (plan-10) lands, tighten
what it injects, do not remove it, and "evaluate the STM impact — if it really doesn't provide
value, it's worth considering taking action." {#t5-ask}

0. **Capture the full payload first; past data measured a truncated one.** The user, 2026-11-15:
   "the injections have been truncated for so long that it's hard to say how effective they have
   been." Session 070141d0's own transcript: of ~56 scan-prompt outputs, nearly every one ended
   `[+N block(s) omitted by --max-bytes 4499]` (N = 1-7, mostly 4-5), and the omitted blocks were
   the per-symbol context blocks, while the content-match and STM-composite blocks that led the
   output survived. The 2026-11-13 pilot therefore measured what got through, not what the hooks
   produce. So, before any cut: for about a week of normal use, every scan-prompt and recall call
   logs its **full** uncapped payload by block, and which blocks were delivered and which dropped
   (logged only, not delivered: no extra context cost). Use is then measured against both: were
   delivered blocks used, and would dropped blocks have been (a later tool call or the reply
   touches an item that was only in a dropped block)? That separates "the content is useless"
   from "the useful content was the part being cut". The capture must not log raw prompt text
   into the repo ([[feedback_no_raw_prompts_in_public_repo]]).
0b. **The primary score: discovery calls avoided** (the user, 2026-11-15: "one way for us to
   score context relevance is if it reduces your usage of grep & other similar commands").
   From the transcripts, every discovery call after a prompt — the Grep and Glob tools, Read,
   and Bash `grep` / `rg` / `find` / `sed -n` / `cat` / `rmx grep` / `rmx context` — with its
   target (pattern, symbol, path), classified against that prompt's injection:
   - **ignored** — the target, and the answer the call went looking for, was in the DELIVERED
     payload, and the agent searched anyway. **Its own class of finding, against the agent, not
     the injection** (the user, 2026-11-15: "you ignoring input should be its own class of
     finding"): the content was relevant; the remedy is presentation (placement, labels, a
     `path:line` the agent can act on without re-checking) or the agent's instructions, never
     retrieval. Sub-cases recorded: read-and-re-verified (the agent checked a shown fact), unread
     (no sign the block was looked at), and distrusted-stale (the shown fact was out of date — that
     one IS an injection defect and moves to `uncovered`);
   - **avoidable** — the target was only in a DROPPED block (step 0's capture): the cap's cost;
   - **uncovered** — in neither: a relevance or coverage gap (input to 30.6);
   - and the outcome, **discovery calls per prompt**, compared before and after 0.84.0's
     ordering fix (a natural experiment on its deploy date), by prompt kind, and by an on/off
     alternation only if the before/after is confounded. A block earns its bytes when it moves
     calls out of `avoidable` and `uncovered`; `ignored` is scored separately, against the agent,
     and is reported per session as its own finding count.
1. **Measure per block kind** (STM topic composite, content matches, symbol context, memory
   recall), from what is already logged: bytes per prompt, repetition across consecutive prompts
   (ch-bsd measured the composite at 59% of scan-prompt bytes and 100% repeated), and **use** by
   the 21.5 used-signal method (a later tool call or the reply touches an injected item; the
   2026-11-13 pilot found 7% caused, 19% caused + informed across all blocks, but did not split
   by block). Go/no-go bands are written before the run: a block used on under 5% of prompts is
   cut to on-change-only or dropped; 5-15% is shrunk; over 15% is kept; tightened only by the
   member filter (R2.0) and the shrink knobs (amended by ruling L140: the per-item tighten had
   no knob or test and was dropped; [[task-31.5-scan-prompt-block-measure#actions-removed]]).
2. **Cut and tighten** by the bands. Already clear without measuring: no stopword or typo tokens
   as STM topic members; no topic without a real symbol or file member; no repeat of an unchanged
   block ([[feedback_injection_presentation_rules]]); most relevant first under the cap.
3. **Ablation only if a band is ambiguous:** replay real prompts with the block removed and
   compare the agent's actions (task 21.7's method).

Runs after 0.84.0 (which superseded the undeployed 0.83.1, L119); feeds 21.5 phase M and 30.6.
Plan-10's dedupe, which step 1 expected to follow it, is post-mod (ruling L128 in
[[plan-of-plans#rulings]]). {#t5-body}

**Spec:** [[task-31.5-scan-prompt-block-measure]] (approved by L140 on ch-bsd r2's MEH-only GO).
Five sub-steps (S0 capture, S0b discovery-call scoring, S1 bands, S2 cut, S3 conditional
ablation) over two releases with a measurement window of 400 to 800 prompts between them.
Three things in the steps above are corrected there:

- the "59% of bytes, 100% repeated" figure is one probe payload of 2026-10-01, not the corpus
  (about 11% of scan bytes);
- a class `followed` is added beside `ignored` / `avoidable` / `uncovered`, so that a fetch of
  a path the injection delivered is a candidate credit to the injection instead of a count
  against the agent;
- the capture stores block payload text, which carries prompt terms, locally in every store;
  its directory ignores itself (bug-261), and release A also takes bug-256.

`plan-31 D1`-`D6` are decided ([[plan-of-plans#decisions]]). {#t5-spec}

### 31.6 Lint and ingest resolve a wikilink target the same way (bug-251, Q30 = a) {#t6}

After 0.84.0's forced reingest, 37 authored `rel:` lines lint clean and land nowhere
([[bug_registry#registry]] bug-251): the lint (`tools/gmd/lint.py`, `_norm_id` and the stem
binding in `resolve_refs`) resolves a `[[doc]]` target by frontmatter `id`, by filename stem, and
by an id folded for case and `-` / `_`; the ingester binds the exact `id` only. `[[CLAUDE#…]]`
(29 lines, id `claude`), `[[bug-registry#registry]]` (6, id `bug_registry`) and
`[[system_design_review]]` (2, id `refmatrix/system_design_review`). One resolver, shared by lint
and ingest, so a link the gate passes is a link the graph holds. The spec decides which forms are
legal (the GMD spec names id or filename stem; whether case / dash folding stays, or the lint
fails what it folds), and how an ambiguous stem is refused on both sides. RED: the three real
shapes on a throwaway store, plus a lint-passes-ingest-misses parity census over the repo. AC: a
recount with `scripts/check-rel-landing.py` after a reingest shows `target_unresolved` 0 for every
target doc the lint accepts. {#t6-body}

**Spec:** [[task-31.6-one-wikilink-resolver]] (approved by L149 on ch-bsd r3's MEH-only GO).
The spec measured bug-251 at 107 lines, not 37: 37 unresolved, 62 bound to a same-named
path-less concept and 8 stale, and its acceptance is all three classes at 0 (L132). One
stdlib resolver, upstream first, with the forms id, project prefix and unique stem; `plan-31
D12` (decided, [[plan-of-plans#decisions]]) drops case and dash folding. By L136 it also
builds bug-185 R10's stale-edge unlink rule (bug-221; bug-257 is its duplicate) and cleans up
the 114 evidence-less edges bug-216's re-bind left, in the same user-gated reingest window
(Q40). {#t6-spec}

## Order {#order}

31.3 and 31.4 are small and may run at any point after 0.83.1. 31.1 after 0.83.1 (it changes
0.83.1's S2 test input). 31.5 right after 0.83.1. 31.2 after 29.5. 31.6 any time (it touches `tools/gmd/` and the GMD ingest's target resolution; not `store.py`). All before the mod transition. {#order-list}

**Amended 2026-11-15 by the 31.3 / 31.4 / 31.5 specs** (0.83.1 above reads 0.84.0, L119). The
order of record is row 5 and row 14 of [[plan-of-plans#queue]]; this is what the specs add:

- **31.5's release A, then 31.3 → 31.4 → 31.1 → 31.6.** 31.3 before 31.4: both edit
  `scripts/lint-gmd.sh`, and 31.3 builds the shared gate-tree helper the later tasks use. The
  lead's `plan-31 D7` edit lands before 31.3's GREEN starts.
- **31.4 and 31.6 are never in flight together:** both change `tools/gmd/lint.py`, which is
  vendored from the upstream GMD repository
  ([[task-31.4-retire-standing-warnings#overlap-31-6]]). 31.6's upstream commit is made on top
  of 31.4's.
- **31.5 is two releases.** Release A (the capture, the composite member filter, bug-256) ships
  first, because its window is counted in prompts (400 to 800) and accrues while plan-29 and
  the rest of plan-31 are built. The scorer is built during the window. Release B (the cuts)
  follows the read of the bands (queue row 14).
{#order-amended}

**Amended 2026-11-15 by the 31.1 / 31.6 / 31.2 specs** (rulings L139, L144):

- **The upstream linter order is 31.4 → 31.1 → 31.6**, never two in flight, each upstream
  commit on top of the previous and each re-vendor from the sha that holds the earlier ones:
  31.1 changes the linter too (bug-255).
- **31.1 before 31.6** also because both edit `ingest_gmd.py`, and because 31.1's fix for
  bug-264 must be in before 31.6's reingest binds anything.
- **31.2 after 29.5**, and after 31.1: it refines the method 31.1 builds for the GMD
  dispatch.
{#order-amended-31b}

## Out of scope {#out-of-scope}

Branch-aware lint, generated frontmatter / anchors, a before/after node check on edits, and any
injection-presentation work beyond 31.5: post-mod list ([[plan-of-plans#post-mod]]). {#out-of-scope-body}
