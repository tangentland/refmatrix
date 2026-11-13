---
gmd: "0.1"
id: task-bug216-denotes-fold-evaluation
title: "Task bug-216b: the per-type evaluation of bug-216's `denotes` relation and its PageRank fold, after bug-216 is live, with bands written before the run"
tags: [task, bug-216, denotes, pagerank, ranking, measurement, adr-0004]
metadata:
  node_type: task
  status: drafting
  created: 2026-11-13
  updated: 2026-11-13
---

# Task bug-216b: evaluate the `denotes` fold per type {#root}

> Status: Drafting (spec wave 2026-11-13, G30). A measurement-lane task (plan-review L29).
> Depends on: [[task-bug216-rule-docs-in-graph]] merged and deployed, its `denotes_link` derive
> op run on the live refmatrix store, and its live recount (AC-6) recorded. Nothing here runs
> before that.
> Builds no `src/`. Its harness is an `eval/production/` script over throwaway copies.

rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r7-denotes]]
rel: depends-on -> [[task-bug216-rule-docs-in-graph#r9]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#gate-prior]]
rel: implements -> [[refmatrix/adr-0004-unified-location-space-index#gate-depth]]
rel: derives-from -> [[refmatrix/adr-0004-unified-location-space-index#d-2026-11-13-denotes]]
rel: related-to -> [[measurement-task-21.5-relation-gaps-2026-11-13#gmd-gap-correction]]
rel: related-to -> [[measurement-injection-already-held-2026-11-13#design-replay-v2]]
rel: reinforces -> [[feedback_go_no_go_ranges_not_predrop]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

## Why {#why}

bug-216 R7 adds a linkage `denotes`: a path-less concept minted by a bare doc-id `rel:` target
links to the doc or memory whose GMD id it spells. R9 makes every walker treat it as a zero-cost
hop and folds the concept's typed in-edges onto its target in PageRank. The user accepted rev 3
and confirmed it ("rev 3-4 stand": the Q8 row of session f0521bff in [[open-questions]], not
the save-state Q8 of session 37b7498f). Contra-d
CD-7 found that R9 changes a ranking input that ADR-0004's gates reserve for measurement:
"cumulative-weight ordering [is] opt-in per relation type, after measurement" and "the per-type
prior … moves only on a per-type evaluation". L7 resolved it: R7 and R9 ship as specced, ADR-0004
records `denotes` as a binding repair (not an alias merge), and the fold is evaluated per type
after deploy. L29 makes that evaluation this task, with bands written first. {#why-body}

The question: on the production ranking path, does `denotes` (and its fold) keep every use an
agent actually made visible, and does what it moves rank better or worse than what it displaces?
{#why-question}

## Decisions {#decisions}

| # | decision | reason |
|---|---|---|
| e1 | Two arms over throwaway copies, the SAME code in both: **ON**, a read-only APFS clone of the live catalog after the derive op; **OFF**, a second clone with every `denotes` row deleted, then PageRank and the adjacency cache rebuilt on that copy by the production command | the benchmark path is the production path; only the data differs, so no `src/` switch is added for a measurement |
| e2 | The code is bug-216's deploy sha, run by the dev interpreter checked out at that sha against stores under a short `mkdtemp()` root. The sha and `refmatrix.__file__` are recorded per arm and asserted equal | the version must not differ between arms (`scanprompt_graph_delta.py`'s rule); never a dev-venv `rmx` against a live store |
| e3 | Confounds held down as in `eval/production/scanprompt_graph_delta.py`: `RMX_RERANK=0`, composite intra-edges 0, one frozen prompt set, same order in both arms | the cross-encoder is nondeterministic under load; STM is session state a re-derive does not change |
| e4 | The fold-isolated arm (**FOLD-OFF**: ON with its `pagerank` table and adjacency cache taken from OFF) runs only if R0 finds those two are the fold's only inputs. It is report-only | L29 names the fold; R9's walker transparency also reads `denotes`. If they cannot be separated by data, a harm reading is attributed by the user, not guessed |
| e5 | Uses come from the labelled sets already on record: 10.5's design-replay sets (11 labelled CAUSED+INFORMED and 16 R12 explicit uses on prompt channels) plus 21.5 phase M's labelled CAUSED+INFORMED pairs when phase M has reported | a "use" must be an act the agent made, not a proximity count (L18's rule) |
| e6 | Corpus: refmatrix. cliquedb only if its store has had the derive op AND the user allows the read-only copy (ruled, [[#o-2]]) | bug-216's derive op runs on the refmatrix store first; a fleet store is the user's |

## Requirements {#requirements}

1. **R0 Probe the arms (read-only).** On throwaway clones only, establish and record:
   - that deleting `denotes` rows on a copy, then running the production PageRank command and
     invalidating the adjacency cache there, leaves a store that `rmx scan-prompt`, `rmx context`
     and `rmx neighbors` open cleanly;
   - whether the `pagerank` table plus the adjacency cache are the fold's only inputs, which
     decides whether e4's FOLD-OFF arm can run;
   - the wall time of one arm over the prompt set;
   - that the copies register with no hub, no launchd label and no live socket (the 23.0
     sandbox's connect-log rule).

   The probe's numbers go into the measurement file. {#r0}
2. **R1 The frozen prompt set.** The prompt calls of 10.5's design replay
   ([[measurement-injection-already-held-2026-11-13#design-replay-v2]]): each call's prompt text is
   read from the local transcript and never committed (d8f). The call-id list's sha256 is
   committed before any arm runs. A call whose prompt cannot be re-read is counted
   `prompt_missing` and dropped from both arms. The transcripts read are archived exactly as
   [[task-21.5-tool-used-signal#r14-archive]] archives phase M's, under
   `/Volumes/littlebig/refmatrix-measurement-archive/bug216-denotes-eval/`, so a re-run can be
   reproduced after Claude Code prunes them. The archive is mode `0700`, never committed (only
   a sha256 manifest is), and its creation is announced to the user. {#r1}
3. **R2 The harness.** `eval/production/denotes_fold_eval.py` runs the production `scan-prompt`
   and per-prompt recall for every call in R1 against each arm's store and records each call's
   delivered item keys (`telemetry.item_key`) in rank order. It writes only under its `mkdtemp()`
   root and the measurement file. {#r2}
4. **R3 The measures.** {#r3}
   - **M1 Uses kept visible (primary).** For each use in e5, whether its item is delivered for its
     prompt in each arm. The counts: `use_kept_both`, `use_lost_on` (delivered by OFF, not ON),
     `use_gained_on` (delivered by ON, not OFF), `use_lost_both`, and `use_item_missing` (the
     item no longer exists in the corpus; excluded from both arms).
   - **M2 What moves, and is it relevant.** Over calls whose delivered sets differ between arms,
     the next-touch rate of ON-only items against OFF-only items. An item counts as touched when
     the main loop, in the original session, touched its file at prompt lag 0-3 after that
     prompt, excluding files touched earlier in the session (the method of
     [[measurement-task-21.5-relation-gaps-2026-11-13#method]]). The difference's 95% CI comes from
     a bootstrap over sessions.
   - **M3 Citation reach (the repair's benefit).** For every authored `rel:` line that bug-216's
     recount classes `bound_via_denotes`: whether `rmx context <citing doc>` returns the cited
     doc in its top 20, and whether `rmx neighbors <citing doc>` lists it, in each arm.
   - **M4 Size of the change.** The share of calls whose delivered set changes, the mean Jaccard
     between arms, and the displacement of the top 150 PageRank entities (the primer's window).
5. **R4 Bands, written here before any run.** Read in this order; the first row that holds is the
   reading. {#r4}

   | condition | reading | action |
   |---|---|---|
   | fewer than 10 uses resolvable in both arms, OR fewer than 100 calls whose delivered sets differ | not established | report-only; re-run once 21 days of post-deploy data add uses (21.5 phase M's labels count) |
   | M1: `use_lost_on ≥ 1`, OR M2: the ON-only rate is below the OFF-only rate with the CI excluding 0 | `denotes` harms ranking | a new task spec disables the PageRank fold (R9's fold sentence), while R7's link and R6's binding stay (L7: the fold, not the link). If FOLD-OFF ran and does not reproduce the harm, the walker transparency is the cause, and the user decides. The user is told before any change |
   | M1: `use_lost_on = 0`, AND M2: the ON-only rate is at least the OFF-only rate, or the CI includes 0 | `denotes` holds | nothing changes. ADR-0004's decision log records the result, and the `denotes` per-type prior stays flat (1.0) |

   M3 and M4 are reported and carry no band: M3 is the repair working as designed, and M4
   is the size of the change. A `use_gained_on` count is reported beside `use_lost_on` and never
   offsets it, the same shape as L34's "drops 0 CAUSED/INFORMED and 0 explicit uses".
6. **R5 Record the result in ADR-0004.** The architect appends the reading and the measurement's
   link to ADR-0004's decision log, under [[refmatrix/adr-0004-unified-location-space-index#d-2026-11-13-denotes]].
   {#r5}

## Acceptance criteria {#acceptance}

The harness tests run in 23.0's sandbox, on a fixture store built by the real ingester, through
the real CLI. AC-5 is the run on real data. {#acceptance-lead}

1. **AC-1 The arms differ where they must.** Take a fixture in which doc A reaches doc B only
   through a misbound concept with a `denotes` link (bug-216 AC-10's shape). The ON arm's
   `rmx neighbors A` lists B and its PageRank gives B the in-edge; the OFF arm's does neither.
   The harness refuses to report when no call's delivered set differs between arms and no M3
   line differs (`arms identical`, exit 1). **Mutation:** OFF built without deleting the
   `denotes` rows: AC-1 fails on `arms identical`. {#ac-1}
2. **AC-2 Same code.** Each arm's record carries the sha and `refmatrix.__file__`, and the harness
   exits 1 when they differ. **Mutation:** one arm run from another checkout: exit 1. {#ac-2}
3. **AC-3 The use counter.** A fixture use whose item is delivered only in OFF counts
   `use_lost_on=1` and reads the harm row; delivered only in ON counts `use_gained_on=1` and
   reads the holds row; an item absent from both corpora counts `use_item_missing=1`.
   **Mutations:** arms swapped makes the band flip; gained counted as lost makes the holds case
   read harm. {#ac-3}
4. **AC-4 Nothing live.** 21.1's stat-only live-log guard over the live store's files, before and
   after the harness; no socket outside the tmp root (23.0's connect log). **Mutation:** the
   harness pointed at a live root fails the guard. {#ac-4}
5. **AC-5 Run once on real data, banded.** R0's probe, then both arms (and FOLD-OFF if R0
   allows) over R1's set on clones of the live refmatrix catalog after the derive op. The band
   is read per R4, and the clones are deleted. It is not a pass/fail gate on the number, but it
   is a gate on the run: exit 0, `prompt_missing` printed, and every R3 count printed even when
   0. {#ac-5}

## Files {#files}

| file | change |
|---|---|
| `eval/production/denotes_fold_eval.py` (new) | R0's probe mode, R2's harness, R3's measures, R4's band reading |
| `tests/test_bug216_denotes_fold_eval.py` (new) | AC-1 to AC-4 |
| `workflow/measurements/denotes-fold-eval-<date>.md` (new, GMD) | R0's probe, the counts, the band reading; counts and hashes only |
| `docs/adr/0004-unified-location-space-index.md` | R5's result line in the decision log |

## Test strategy {#test-strategy}

- RED first on AC-1, AC-3 and AC-4 (no harness exists); AC-2's guard is proven by its mutation.
- No mock of the store, the ranking path or the ingester. The fixture is built by the real
  `ingest-gmd` and the real derive op.
- Output is captured to `workflow/review-output/pytest-bug216-denotes-eval.log`.

## Lead rulings (2026-11-13) {#open}

rel: derives-from -> [[plan-review-2026-11-13#lead]]

**Decision rows.** The lead ruled on the user's pattern and chose option (a) on both items. The
user is told and may overturn either one, which would be a dated revision before AC-5 runs.
The options are kept below as the record. {#open-rulings}

| item | ruling | effect |
|---|---|---|
| O-1 | the band reads ON vs OFF, the `denotes` type as a whole; FOLD-OFF is report-only, run when R0 allows it | e1, e4, [[#r4]] as written; no measurement switch in `src/` |
| O-2 | refmatrix only, until cliquedb's store has the derive op AND the user allows a read-only copy | e6 as written |
{#open-rulings-table}

1. **O-1, isolating the fold. RULED (a).** (a, recommended) Band on ON vs OFF (the relation type as a
   whole, ADR-0004's per-type unit), and run FOLD-OFF as report-only when R0 allows it. (b) Add a
   measurement-only parameter to `pagerank.build_adjacency` to switch the fold alone. This is
   more precise, but it puts a measurement switch into `src/`. {#o-1}
2. **O-2, cliquedb. RULED (a).** (a, recommended) refmatrix only, until cliquedb's store has the derive op
   and the user allows a read-only copy for this task. (b) Ask the user now, so both corpora run
   together. {#o-2}

## Definition of done {#done}

- R0 recorded; AC-1 to AC-4 RED then GREEN; AC-5 run and banded; a ch-bsd round over the
  measurement CLEAN or MEH-only; R5's line in ADR-0004.
- Implementation summary at `workflow/implementation_summaries/task-bug216-denotes-fold-evaluation.md`
  (the run's sha, the band, the mutation table).
- Committed on branch `task-bug216-denotes-fold-evaluation`, merged `--no-ff` to `master`.
