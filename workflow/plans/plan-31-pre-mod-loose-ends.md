---
gmd: "0.1"
id: plan-31-pre-mod-loose-ends
title: "Plan 31: pre-mod loose ends — graph correctness and GMD hardening admitted under the freeze"
tags: [plan, gmd, graph-correctness, freeze, loose-ends]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-15
---

# Plan 31: pre-mod loose ends {#root}

**Date:** 2026-11-15. **Status:** drafting — the five items are admitted and registered; each
task spec is written (ch-architect on Fable) and reviewed (ch-bsd) when the plan reaches the head
of the queue, per [[orchestration#planning]]. **Origin:** the user, 2026-11-15: "write the freeze
line and register the five", after the lead's GMD assessment. The fifth item is plan-30's task 30.6.

rel: part-of -> [[plan-of-plans#freeze]]
rel: related-to -> [[plan-30-materialisation]]
rel: depends-on -> [[orchestration]]
rel: related-to -> [[task-21.5-tool-used-signal]]
rel: related-to -> [[plan-10-injection-dedup]]

## Why {#why}

The goal before the mod transition: the core concept/graph representation more useful, context
succinct and relevant, performance improved, busywork removed, loose ends tied up (the user,
2026-11-15). These four are the graph-correctness and GMD-hardening items that serve that goal and
survive the transition; GMD tooling that only adds features went to the post-mod list
([[plan-of-plans#post-mod]]).

## Tasks {#tasks}

### 31.1 One bad markdown file no longer demotes the batch (bug-244) {#t1}

A non-string frontmatter `id:` (or `title:`) is refused at parse time, so the file lands in
`skipped_unparseable`, counted and named, while the rest of the batch is GMD-parsed. The S2 / M2
tests of 0.83.1 use the list-valued `id:` as their real raising input; this task's RED gives them
another real raising input or a registered patch of `ingest_gmd_paths` (L112a). Fleet repos are
measured for the shape first. {#t1-body}

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

### 31.3 Ledger bullets must carry an anchor (bug-242 guard) {#t3}

A lint rule: in `workflow/bullshit/IMPRESSIONS.md` and the impression ledgers, every
`- 20YY-MM-DD` bullet ends with exactly one `{#id}`; a cut bullet fails the lint. RED with a
truncated-bullet fixture. About an hour. {#t3-body}

### 31.4 Retire the warnings nobody acts on {#t4}

The repo lint carries 89 standing warnings. Each warning class is either made an error (and its
instances fixed) or retired from the linter, with the reason recorded; the target is zero standing
warnings, so a new warning is read. Busywork removed, not added: no per-warning fixing of a class
that is retired. {#t4-body}

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
   - **redundant** — the target was in the DELIVERED payload: shown, not used or not trusted;
   - **avoidable** — the target was only in a DROPPED block (step 0's capture): the cap's cost;
   - **uncovered** — in neither: a relevance or coverage gap (input to 30.6);
   - and the outcome, **discovery calls per prompt**, compared before and after 0.84.0's
     ordering fix (a natural experiment on its deploy date), by prompt kind, and by an on/off
     alternation only if the before/after is confounded. A block earns its bytes when it moves
     calls out of `avoidable` and `uncovered` without growing `redundant`.
1. **Measure per block kind** (STM topic composite, content matches, symbol context, memory
   recall), from what is already logged: bytes per prompt, repetition across consecutive prompts
   (ch-bsd measured the composite at 59% of scan-prompt bytes and 100% repeated), and **use** by
   the 21.5 used-signal method (a later tool call or the reply touches an injected item; the
   2026-11-13 pilot found 7% caused, 19% caused + informed across all blocks, but did not split
   by block). Go/no-go bands are written before the run: a block used on under 5% of prompts is
   cut to on-change-only or dropped; 5-15% is shrunk; over 15% is kept and tightened.
2. **Cut and tighten** by the bands. Already clear without measuring: no stopword or typo tokens
   as STM topic members; no topic without a real symbol or file member; no repeat of an unchanged
   block ([[feedback_injection_presentation_rules]]); most relevant first under the cap.
3. **Ablation only if a band is ambiguous:** replay real prompts with the block removed and
   compare the agent's actions (task 21.7's method).

Runs right after 0.83.1, ahead of plan-10's dedup; feeds 21.5 phase M and 30.6. {#t5-body}

## Order {#order}

31.3 and 31.4 are small and may run at any point after 0.83.1. 31.1 after 0.83.1 (it changes
0.83.1's S2 test input). 31.5 right after 0.83.1. 31.2 after 29.5. All before the mod transition. {#order-list}

## Out of scope {#out-of-scope}

Branch-aware lint, generated frontmatter / anchors, a before/after node check on edits, and any
injection-presentation work beyond 31.5: post-mod list ([[plan-of-plans#post-mod]]). {#out-of-scope-body}
