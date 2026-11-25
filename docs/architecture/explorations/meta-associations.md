---
gmd: "0.1"
id: exploration-meta-associations
title: "Exploration: seven candidate meta-level associations, measured on existing logs before any is built (M4, Q84 = a)"
tags: [exploration, measurement, m-lane, retrieval, associations, recall]
metadata:
  node_type: exploration
  status: provisional
  created: 2026-11-25
---

# Exploration: candidate meta-level associations, measured first {#root}

**Date:** 2026-11-25
**Status:** Measured, provisional until reviewed. The pre-registration ([[#prereg]]) was committed
alone at `82fb7997` before any result was computed; results, deviations and limits follow it.
**Motivation:** The weights carry ingest structure only, and the measured ceiling is recall, not
ranking. The user chose to measure seven candidate associations on the logs already on disk before
building any (Q84 = a, L252). Brief: [[agent-brief-meta-assoc-measure]].

rel: implements -> [[agent-brief-meta-assoc-measure]]
rel: derives-from -> [[measurement-task-21.5-usage-weight-2026-11-13]]
rel: derives-from -> [[measurement-task-21.5-r12-pilot-2026-11-13]]
rel: depends-on -> [[plan-of-plans#questions]]

## Pre-registration {#prereg}

Written after counting what the logs hold (volumes and record shapes only) and before computing
any reach, rate or AUC. Nothing below changes after the pre-registration commit; a deviation is
reported as a deviation in the results. {#prereg-note}

### Data {#data}

Read-only APFS clones (`cp -c`) under a short `mkdtemp()` root, `chmod a-w`, deleted at the end:
the dev store's `recall-events.jsonl` (2026-10-20 → 11-25), `query.log`, `stm/`, `sessions/`,
`catalog.read.duckdb` (DuckDB `read_only=True` under `.venv-eval`); the project's Claude Code
transcripts (13 main sessions 2026-11-03 → 11-25 plus their `subagents/`); the curated memory
dir; `git log` of `master` at `6cc9e265`; `workflow/bug_registry.md`. The doc carries counts,
rates, intervals and hashed ids only. {#data-sources}

### Common definitions {#defs}

- **Thread.** One transcript stream: the main loop of a session, or one subagent. Tool calls are
  ordered by transcript timestamp within a thread. Primary analyses use the main loop; subagent
  rows are reported as a separate stratum.
- **File key.** A touched or retrieved item normalised to one key: a repo file as its
  repo-relative path (dev-tree, `~/refmatrix` and `/Volumes/littlebig/<clone>/` prefixes
  stripped); a memory file as `memory/<stem>`. Anything else (concept terms, subjects, scratch
  files, tool-result files) has no key and is never gold.
- **Retrieved keys of a query.** The keys of every `retrieved` or `delivered` row of its
  `query_id`: memory rows by name; code rows by the path before `::`; doc rows by name or path;
  concept rows only when the name is a GMD `doc-id#anchor` that resolves to a file. Term concepts
  and subjects carry no key (the r12 pilot: 0/64 C+I on them).
- **Touch.** In a thread: `Read` / `Edit` / `MultiEdit` / `Write` / `NotebookEdit` of a
  `file_path`, or a Bash command token that is a path resolving to a repo or memory file
  (`bash_path`), or `rmx context <X>` / `rmx-master context <X>` whose `<X>` names a file key.
  Never bare names (`bash_name` was 0/46 CAUSED).
- **Query unit and window.** One `query_id`. Hook queries (`scan_prompt`, `prompt_recall`,
  `session_start`, `precompact`) are joined to the main loop by session and time; their window is
  the next 10 main-loop tool calls, ending early at the next user prompt. Agent queries
  (`context`, `recall`) are joined to the Bash call that issued them (same session, nearest call
  at or before the event); their window is the next 10 calls in that thread.
- **Gold.** A key touched in the window that the thread did not touch in its previous 200 tool
  calls (a new touch; re-touches are a reported stratum, not the primary). A gold is **missed**
  when it is not among the query's retrieved keys. A touch is proximity, not use (r12 pilot
  [[measurement-task-21.5-r12-pilot-2026-11-13#verdict]]); every reach is therefore read
  against the controls below, never alone.
- **Split.** Time-ordered. For each candidate, T* is the 60th percentile of its evaluation units'
  timestamps; associations are fitted only on evidence strictly before T*, evaluated on units at
  or after T*.
- **Reach@k.** The candidate's top-k ranked keys for the unit's cue contain the gold; k ∈ {5, 10,
  20}, primary k = 10. **False-reach@10** = the share of the top-10 keys not touched in the
  window (1 − precision@10), averaged over units.
- **Controls (every recall candidate).** (a) *popularity*: the top-k keys by new-touch count
  before T*, the same list for every unit; (b) *placebo*: the candidate applied to the cue of a
  random held-out unit from another session (`random.Random("m4-<candidate>")`). **Lift** =
  reach@10(candidate) − max(reach@10(popularity), reach@10(placebo)).
- **Intervals.** Wilson 95% for proportions; lift by paired bootstrap over units (2,000
  resamples, seed `m4`), plus a session-cluster bootstrap as a sensitivity row where the units
  come from ≥ 5 sessions. AUC by the Mann-Whitney statistic with a bootstrap interval.
- **Volume.** Evidence units per week over the last 14 days of data (2026-11-11 → 11-25).
- **Underpowered.** A candidate with fewer than 30 held-out evaluation units (or fewer than 15
  positive outcomes for 5, or 100 flagged deliveries for 6) is "measure more" whatever its point
  estimate.

### Bands for the recall candidates (1-4) {#bands-recall}

Applied in this order:

1. Underpowered → **measure more** (collect, then refit on the same split rules).
2. Lift ≥ 10 pp, its 95% lower bound ≥ 3 pp, false-reach@10 no worse than the best control's
   + 5 pp, and volume ≥ 20 evidence units a week → **build** as its own linkage (never folded
   into `mentions.weight`).
3. Lift < 3 pp, or its 95% upper bound < 5 pp → **drop**.
4. Otherwise (a real but small or uncertain lift, or a large lift on too little volume) →
   **measure more**.

{#bands-recall-list}

### Per candidate: metric, cue, split, control {#per-candidate}

1. **Search-resolution bridge (query → file).** Units: held-out query units with a missed gold,
   all channels, primary = main loop. Association fitted on train missed pairs: query term t →
   gold F, `score(F | q) = Σ_{t ∈ q} idf(t) · c(t, F) / (c(t) + 2)`, terms with c(t) ≥ 2 only;
   query terms = the prompt (hook queries) or the `rmx context` argument (agent queries),
   tokenised and filtered by `scan._PROMPT_STOPWORDS`. Bands [[#bands-recall]]. Reported
   strata: channel group (push: hook; pull: agent), re-touch gold, subagent threads.
2. **Co-change (file ↔ file).** Commits on `master` before T* touching ≤ 30 files;
   `cc(a, b)` = commits touching both, `score(F | cue) = Σ_{a ∈ cue} cc(a, F) / (n(a) + 1)`.
   Units and gold: candidate 1's held-out missed new-touch golds that are repo files. Primary cue:
   the query's retrieved keys (top 10 by rank), the product's path (association expands what
   retrieval found). Secondary cue: the thread's last 3 touched keys before the query. Bands
   [[#bands-recall]]. Symbol ↔ symbol co-change is out of scope (reported as not measured).
3. **Error → fix (signature → files).** Cues: tool results with `is_error` true in the
   transcripts (the STM ring stores no tool output), normalised to a signature: exception or
   first error line, digits, paths, quoted strings and hex collapsed, first 120 chars. Units: a
   held-out error followed in the same thread, within 20 calls, by an `Edit` / `MultiEdit` /
   `Write` of a repo file (the fix gold); missed = the gold not retrieved by any query in that
   window. Association: train signature → fix-file counts, exact signature match. Controls as
   above (popularity = files most edited after errors in train). Bands [[#bands-recall]]. Second
   leg, reported with the same bands: held-out `bug_registry.md` rows whose symptom has token
   Jaccard ≥ 0.5 with a train row, reach = the train row's files cover a file of the new row.
4. **Decision provenance (file → ruling).** Commit bodies citing `L\d+`, `Q\d+`, `bug-\d+`.
   Association: train commits' touched files → cited ids, `score(id | files) = Σ_f c(f, id) /
   (n(f) + 1)`. Units: held-out commits citing at least one id already cited before T*; cue = the
   commit's touched files; gold = those re-cited ids. Popularity = most-cited ids in train;
   placebo = the files of a random held-out commit. Bands [[#bands-recall]]. Also reported: the
   share of held-out citations that re-cite a pre-T* id (the evidence the association can use).
5. **Staleness (memory ↔ the code it names).** Memories with repo paths in their body. Churn =
   commits touching the named files in the 7 days after the memory's `updated:` (else
   `created:`); outcome = the memory is the target of a `supersedes` or `amends` edge from a
   memory created 7 to 35 days after that date. Only memories with 35 days of follow-up enter.
   Split by the memory's date; the threshold (churn ≥ median of train positives) fitted on train.
   Metric: held-out AUC of churn, and the outcome rate above vs below the threshold. Control:
   the outcome rate of memories naming no repo path; placebo churn = churn of the same number of
   random repo files. Bands: underpowered (< 15 positives) → measure more; AUC ≥ 0.70 with lower
   bound ≥ 0.60 → build (as a staleness flag on delivery, demote-only); AUC < 0.60 or upper bound
   < 0.65 → drop; else measure more.
6. **Corrections (delivered → contradicted, demote-only).** A delivered item with a key is
   *flagged* before T* when any of: (S1) the next user prompt of the session is a correction
   (pre-registered lexicon: starts with `no`, `wrong`, `that's not`, `not what`, `stop`,
   `don't`, `undo`, `revert`, `incorrect`, `you're wrong`); (S2) it is a memory that is the
   target of a `supersedes`/`amends` edge from a memory created before T*; (S3) its file was
   changed by a commit whose subject starts `Revert` within 7 days after the delivery. Metric on
   the product path: among held-out deliveries, the touch rate (gold-style, either new or
   re-touch) of flagged items vs unflagged items: RR = touch(flagged) / touch(unflagged);
   precision as a negative = 1 − touch(flagged), read against 1 − touch(unflagged). Also
   reported: the share of deliveries that were already superseded at delivery time (S2's
   prevalence). Bands: underpowered (< 100 flagged held-out deliveries) → measure more; RR ≤ 0.5
   with upper bound < 0.8 → build (demote-only); RR ≥ 0.8 or the interval includes 1 → drop;
   else measure more. Reported per signal S1, S2, S3 and pooled.
7. **Read depth (cue → anchor).** Partial reads: `Read` with `offset`/`limit`, and Bash
   `sed -n 'a,bp' <file>` (the main loop's common read form), on files of ≥ 300 lines. Line
   ranges are mapped to GMD heading sections of the file as of the last commit before the read
   (`git show`), falling back to the clone's current file when the path is not in git. Train:
   anchor read counts per file. Metric (held-out reads of files with ≥ 5 train reads): the share
   of reads whose range falls inside the file's train top-3 anchors; control = the share expected
   if reads fell on sections in proportion to their size. Payload: bytes of the anchor sections
   covering the read vs bytes of the whole file, and coverage (the sections hold ≥ 90% of the
   read's lines). Bands: underpowered (< 30 held-out reads) → measure more; top-3 share ≥ 0.6,
   ≥ 2× its control, median payload cut ≥ 50% at coverage ≥ 0.9 → build; top-3 share < 1.5× its
   control or coverage < 0.7 → drop; else measure more.

{#per-candidate-list}

### Not re-run (known negatives) {#known-negatives}

More graph hops, PRF, term cliques, the phrase layer and usage-weighted term scores are measured
negatives (`project_retrieval_negatives_2026_09`, `project_structural_signal_lead_wins`,
[[measurement-task-21.5-usage-weight-2026-11-13#verdict]]). The `eval/production` harness and
MemAware Layer A replay corpora without the transcripts' touch timelines, so the recall
candidates are measured on the logged product path (the queries the hooks and the agent really
ran) instead; the results say where that differs from the harness. {#known-negatives-note}

## Results {#results}

Scripts: `workflow/measurements/meta-associations-2026-11-25/` (`m4_common.py` loads; one script
per candidate). Run 2026-11-25 on the copies named in [[#data-sources]]; the copies were deleted
after the run. Counts and rates only. {#results-scripts}

### The join, before any candidate {#join}

1,852 query units in `recall-events.jsonl` carry at least one row; 1,807 join a transcript (43 are
in two sessions with no transcript, 2 agent queries have no matching Bash call). By group: push
(hook) main loop 1,642, pull (agent) main loop 149, pull in a subagent 16. Hook queries never
reach subagents. 734 units have a new-touch gold in their window; of the 1,572 new-touch golds,
the query itself had retrieved **43 (2.7%)**. The missed set is therefore almost every new touch;
read [[measurement-task-21.5-r12-pilot-2026-11-13#verdict]] before taking a touch as use. {#join-counts}

T* per candidate (UTC): C1 2026-11-15 03:13, C2 11-15 03:21, C3 errors 11-14 08:50, C3 bug rows
11-10 19:50, C4 11-14 20:59, C5 2026-09-16 (memory dates), C6 11-15 10:30, C7 11-15 01:58. The
held-out query units of C1, C2 and C6 come from 4 sessions, so the session-cluster bootstrap was
not run for them ([[#defs]]: it needs ≥ 5). {#split-dates}

### One line per candidate {#verdicts}

| # | candidate | metric (held-out) | result, 95% interval | band | action |
|---|---|---|---|---|---|
| 1 | search-resolution bridge | reach@10 of missed new-touch golds, n = 289 units | 0.055 [0.034, 0.088]; popularity 0.173, placebo 0.062; **lift −11.8 pp [−17.3, −6.2]** | drop | drop |
| 2 | co-change, cue = retrieved | same units, repo-file golds, n = 274 | 0.022 [0.010, 0.047]; popularity 0.120, placebo 0.015; **lift −9.9 pp [−13.9, −5.8]** | drop | drop as a recall bridge |
| 3 | error → fix (transcript errors) | reach@10 of the fix file, n = 93 | 0.043 [0.017, 0.105]; popularity 0.086, placebo 0.011; **lift −4.3 pp [−8.6, −1.1]** | drop | drop |
| 3b | error → fix (bug rows) | matched-row files reach the new row's files, n = 114 | 0 of 114 rows match a train row at Jaccard ≥ 0.5; popularity 0.447; **lift −44.7 pp [−54.4, −35.1]** | drop | drop |
| 4 | decision provenance | reach@10 of a re-cited id, n = 99 commits | 0.172 [0.110, 0.258]; popularity 0.152, placebo 0.051; **lift +2.0 pp [−5.1, +10.1]** | drop | drop; L-row stratum below |
| 5 | staleness | AUC of 7-day churn → superseded/amended 7-35 days later | **0.337 [0.174, 0.523]** on 2 positives of 45 | measure more (underpowered) | wait for follow-up; see [[#c5]] |
| 6 | corrections (demote-only) | RR = touch(flagged) / touch(unflagged), held-out deliveries | pooled **0.20 [0.00, 0.56]** (n flagged 1,134); stratified to memories, S2 **1.96 [0.18, 20.9]** | build as pre-registered; overturned by stratification | drop the use-based signal; see [[#c6]] |
| 7 | read depth | held-out partial reads of large `.md` inside the file's train top-3 anchors, n = 120 | **0.300 [0.225, 0.387]** vs size control 0.285 (1.05×); coverage ≥ 0.9: 0.300 | drop | drop |

{#verdicts-table}

Volume (evidence a week, 2026-11-11 → 11-25): C1 252 missed-pair units (about half that in
distinct prompts: two hook channels per prompt); C2 644 commits of ≤ 30 files, 238 evaluation
units; C3 80 error → fix episodes, 62 new bug rows; C4 493 citing commits, 50 re-citing units; C5
27.5 new memories, 13.5 `supersedes`/`amends` edges; C6 5,716 keyed deliveries, 3.0
correction-followed units; C7 391 partial reads of large `.md` files (1,908 of all files). Volume is
not what failed any candidate except 5 and the S1 leg of 6. {#volume}

### Candidate 1: search-resolution bridge {#c1}

Fitted on 432 train units with a missed new-touch gold (1,797 usable terms); 217 of the 289
held-out units carry at least one usable term. In sample the scorer reaches 0.72 of its own train
golds (a check that it works, not a result); held out it reaches 0.055, below the placebo. 61% of
held-out missed golds were never a train gold at all, which caps any term → file memory. Strata,
reach@10 and lift: push 0.059, −10.2 pp [−15.7, −4.7] (n 255); pull 0.029, −23.5 pp (n 34);
subagent 0 of 14; re-touch golds 0.127 vs popularity 0.493, −36.6 pp. Sensitivity (not
pre-registered): one unit per prompt window, n 134, −10.4 pp [−17.9, −3.0]; removing the
retrieved keys from every ranking changes nothing. False-reach@10: 0.967 (popularity 0.937). {#c1-detail}

### Candidate 2: co-change {#c2}

1,949 train commits of ≤ 30 files (of 2,855 on master). Only 125 of 274 held-out units have a
retrieved cue with any co-change history. The secondary cue (the thread's last 3 touched files)
reaches 0.055, lift −6.6 pp [−10.9, −1.8]. Co-change itself generalises: in held-out commits, one
file's top-10 co-change list holds another file of the same commit 0.605 [0.570, 0.640] of the time
(750 cues over 346 commits). It predicts what changes together, not what the agent opens after a
retrieval miss. {#c2-detail}

### Candidate 3: error → fix {#c3}

642 tool errors in the transcripts (540 in subagents), 235 followed within 20 calls by a repo-file
edit; 232 of those fixes were missed by every query in the window (subagents receive no hook
queries). 0.688 [0.588, 0.773] of held-out errors repeat a train signature, but most repeats are
harness errors (unread-file edits, hook and permission denials): with those removed (n 39) the
association reaches 0 of 39, popularity 3. Bug rows: symptoms are long prose and no held-out row
reaches Jaccard 0.5 with a train row; post hoc, Jaccard ≥ 0.15 matches 21 rows and reaches 6 of 114,
and the nearest train row at any similarity reaches 26 of 114, against popularity's 51. {#c3-detail}

### Candidate 4: decision provenance {#c4}

1,407 of 2,855 commits cite an L, Q or bug id. Only 0.145 [0.125, 0.167] of held-out citations
re-cite an id cited before T*: most citations name a ruling made that day. On the 99 re-citing
commits the association ties popularity. Post-hoc strata, each underpowered: re-cited L-rows 4 of
11 (popularity 1), re-cited Q ids 3 of 11 (popularity 1), bug ids 15 of 84 (popularity 15). The
L/Q stratum is the only positive point estimate in this run: 22 units in the 10.5 held-out days
(about 2 a day), so it could reach 30 held-out units within weeks if it were pre-registered as its
own candidate. {#c4-detail}

### Candidate 5: staleness {#c5}

430 memory files, 155 naming a repo file, 162 `supersedes`/`amends` edges onto 117 targets. The
35-day follow-up admits only memories dated before 2026-10-21, and most edges are from November, so
the split holds 50 train memories (3 positives) and 45 held-out (2 positives). Held-out AUC 0.337
[0.174, 0.523]; placebo churn 0.442; outcome rate naming no file 4 of 78, naming files 2 of 45. Six
memories superseded within 7 days were counted negative (the literal reading). November's
memories, which carry most of the 13.5 edges a week, enter only once they have 35 days of
follow-up, from late December 2026. {#c5-detail}

### Candidate 6: corrections {#c6}

18,183 keyed deliveries over 1,747 query units; held-out 7,284. Flags fitted before T*: S1 36
items (from only 8 correction-followed units in the whole log), S2 117 memories, S3 none (master
has no `Revert` commit). Held-out touch: S1-flagged 0 of 214, unflagged 55 of 7,070 (RR 0; Wilson
bounds on the ratio [0.00, 2.95], so the interval includes 1: drop); S2-flagged 2 of 938 vs 53 of
6,346, RR 0.26 [0.00, 0.70] (query-cluster bootstrap; Wilson bounds [0.05, 1.21]); pooled 0.20
[0.00, 0.56]. As pre-registered, S2 and pooled read "build". The review rule says stratify: S2
flags only memories, and held-out memory deliveries are touched 5 of 3,692 against 50 of 3,592 for
repo files. Within memories, S2's RR is 1.96 [0.18, 20.9]. The effect is the item kind, not the
flag. A memory's body is delivered inline, so a later file touch cannot see whether it was used:
the product-path metric is blind exactly where S1 and S2 flag. {#c6-detail}

Prevalence, reported as asked: of 8,016 memory deliveries in the logged queries, 374 (4.7%) were
already the target of a `supersedes` edge when delivered and 1,628 (20.3%) of an `amends` edge
only; 304 of 1,567 query units that delivered a memory (19.4%) delivered at least one superseded
memory. Superseded-at-delivery is a deterministic fact the store holds, not an association to
learn; whether to filter it is a separate question for the lead. {#c6-prevalence}

### Candidate 7: read depth {#c7}

6,983 partial reads with a file key (6,519 of them `sed -n`), 522 in the main loop; 1,727 on
markdown or memory files, 927 of those on files of ≥ 300 lines (112 files). Held-out reads of files
with ≥ 5 train reads: 120 over 18 files, 46 of them on one file. Top-3 anchors by train frequency
hold 0.300 of held-out reads; the size control is 0.285. Train concentration is low too: a
file's top 3 sections take a median 0.448 of its section hits. Reads are narrow (median 2
sections), and the sections a read actually overlaps are a median 0.116 of the file's bytes, an
oracle cut of 0.884; per-file popularity does not find those sections, so the cut needs a cue that
predicts the section, which this candidate did not have. {#c7-detail}

### The strongest baseline was not a candidate {#popularity}

The popularity control, one fixed list of the files most often newly touched before T*, reaches
0.173 of C1's held-out units (any missed gold in its top 10). For comparison on a different
denominator, the queries themselves had retrieved 2.7% of all new-touch golds. It beat every recall
candidate. It was a control, not a candidate, so no
band applies; whether a pre-registered "hot files" candidate is worth measuring is for the lead.
How much of it is a few hub files touched every session (the train top 10 hold 0.198 of train
golds) was not measured further. {#popularity-note}

## Deviations from the pre-registration {#deviations}

1. **C3 signature normaliser.** The first run picked `Exit code N`, the first line of every failed
   Bash result, as the signature, collapsing 288 of 642 errors into one; the normaliser now skips
   that line (237 distinct signatures). The lift was −4.3 pp in both runs.
2. **C7 scope.** GMD sections exist only in markdown; the first run also counted `.py` files (their
   `# comment` lines parsed as headings). Primary is now `.md` and memory files. The all-files run:
   0.438 inside top-3 vs control 0.479 (0.91×), the same band.
3. **C6 intervals and stratum.** The query-cluster bootstrap degenerates to [0, 0] when a flagged
   arm has no touch, so Wilson-bound ratios are reported beside it; the kind stratum was added under
   the review rule (stratify) and decides the action.
4. **C4.** No file cap on commits (the pre-registration set none); T* is the 60th percentile of
   citing commits, since re-citing units exist only once T* is fixed.
5. **Not pre-registered, reported as sensitivity only:** C1/C2 one unit per prompt window and
   retrieved-keys-excluded rankings; C3 code-errors-only stratum and the bug-row Jaccard sweep; C4
   id-kind strata; C5 the feedback/project/reference stratum (n 18, AUC 0.484).

{#deviations-list}

## What could not be measured, and why {#not-measured}

- **Use.** Every recall gold is a touch, which is proximity ([[#join-counts]]). No pairs were
  labelled in this run.
- **Tool outputs in the STM ring.** The ring stores no tool output; C3 used the transcripts (13
  sessions, 2026-11-03 → 11-25) instead. Recall events before 2026-11-09 have no transcript.
- **Symbol ↔ symbol co-change.** Out of scope as pre-registered.
- **S3 reverts.** Master has no `Revert` commit.
- **Use of delivered memories.** Inline delivery leaves no touch to observe (C6).
- **C5 at power.** 2 held-out positives; the 35-day follow-up excludes the month with most edges.
- **Session clustering for C1, C2, C6.** The held-out units come from 4 sessions.
- **`eval/production` and MemAware Layer A.** They replay queries without the transcripts' touch
  timelines, so they cannot score a post-miss touch; the logged product path was used instead.

{#not-measured-list}

## Pre-registration: candidate 8, activity mode {#prereg-c8}

Added to the brief by L253 (Q87 = a) after the seven above were measured. Written before any
candidate-8 result was computed; committed alone as the second pre-registration. The first
pre-registration ([[#prereg]]) stands unchanged. Known before writing: the record shapes, that the
STM ring stores local wall-clock times (America/Los_Angeles) and holds subagent tool events mixed
with the main loop's, and C6's finding that memory use is invisible to touches. {#prereg-c8-note}

rel: implements -> [[agent-brief-meta-assoc-measure#candidates-list]]

### Question and data {#c8-question}

Does the agent's activity mode, read from the STM ring at query time, change how likely a
delivered item of a given kind is to be used, by more than kind alone and more than popularity
alone? Clusters existing is not the test. Data: fresh `cp -c` copies of the STM rings,
`recall-events.jsonl`, the transcripts with their `subagents/*.meta.json`, and the memory dir;
deleted after the run. {#c8-question-text}

### Mode features {#c8-features}

- **Ring event categories (7):** `read`, `search`, `edit`, `bash`, `test`, `agent`, `other`.
  `Read` → read; `Edit`/`MultiEdit`/`Write`/`NotebookEdit` → edit; `Bash` by its command: `test`
  when it runs `pytest` or `lane-mini.sh`/`lane-local.sh`; else by the first word after stripping
  `cd … &&`, `VAR=value`, `timeout N`, `nice`, `sudo -u X`: `search` for `grep`, `rg`, `rmxgrep`,
  `find`, `ls`, `tree`, and `rmx`/`rmx-master` `context|grep|query|search|neighbors|where|locate|
  memory recall|memory search`; `read` for `cat`, `sed`, `head`, `tail`, `less`, `wc`, `awk`,
  `jq`, `diff`; else `bash`. `Agent`, `SendMessage`, `Task*` → agent; `Grep`/`Glob` and the
  read-only refmatrix MCP tools → search; ring kinds `git`, `say`, `input`, `reason` and anything
  else → other. The STM ring records no `Agent`/`SendMessage` call, so `agent` is folded into
  `other` for every window (the ring cannot see it; a limit, not a choice).
- **Window:** the last 20 ring events of the session at or before the moment; the feature is the
  six category shares.
- **Clusters:** k-means (k-means++, `random.Random("m4-8")`, 20 restarts) on train windows (one
  per ring event before T*, at most 20,000 sampled), k ∈ {3, 4, 5, 6} chosen by mean silhouette on
  a 3,000-window train sample. Held-out windows take the nearest centroid.

{#c8-features-list}

### Labels and lag (descriptive and banded) {#c8-labels}

- **Labels:** each subagent thread's calls, categorised the same way, give sliding 20-call
  windows assigned to the nearest centroid; per `agentType`, the share of its windows in its modal
  cluster, and the normalised mutual information between `agentType` and cluster. Descriptive.
- **Lag:** synthetic switches between labelled threads: pairs (A, B) of subagent threads with ≥ 40
  calls whose modal clusters differ; sequence = last 20 calls of A, then the first 40 of B; lag =
  B calls until the window's cluster first equals B's modal cluster, censored at 40. Median and
  IQR over up to 500 pairs (`random.Random("m4-8-lag")`).
- **Labelled pilot leg:** the 2026-11-13 R12 pilot's pair labels lived in that session's scratchpad
  and are not on disk (searched 2026-11-25); not measured.

{#c8-labels-list}

### Use test on the product path {#c8-use}

- **Units:** deliveries (query unit × delivered key), joined to touch windows exactly as C6;
  `touched` = the key is touched in the query's window. Mode = the cluster of the session's ring
  window at the query time. T* = the 60th percentile of delivery times; models are fitted on
  deliveries before T*, scored on deliveries at or after it.
- **Kinds:** `memory` (`memory/…`); `ruling` (`workflow/plan-of-plans.md`); `bug row`
  (`workflow/bug_registry.md`); `doc` (other `.md`); `code` (everything else). Primary analyses
  exclude `memory` (its use cannot be seen as a touch, C6); memory rates are reported only.
- **Models:** M0 kind-only `(t_k + 0.5) / (n_k + 1)`; M1 kind × mode, shrunk to M0 with prior
  strength 20: `(t_km + 20·M0_k) / (n_km + 20)`; P0 popularity = the key's count of touched train
  windows; P1 = `(P0 + 1) · M1 / M0` (popularity re-weighted by mode).
- **Metrics:** held-out AUC of each model for `touched`; Δ1 = AUC(M1) − AUC(M0) (mode vs no
  mode), Δ2 = AUC(P1) − AUC(P0) (mode vs the popularity baseline; the lead's added control).
  Bootstrap over query units, 2,000 resamples, seed `m4`. Heterogeneity: Pearson χ² of touched ×
  mode within each kind, summed over kinds, against 1,000 permutations of mode within kind (it
  includes mode's main effect; the Δs decide). Effect size: per kind, the max / min use rate
  across modes with ≥ 50 deliveries, Wilson-bounded.
- **Secondary outcome:** explicit `used` rows of `recall-events.jsonl` (125, from `context` by
  name, focus notes, memory get by name) counted by kind × mode. Descriptive.

{#c8-use-list}

### Bands for candidate 8 {#c8-bands}

Applied in this order:

1. Fewer than 30 touched held-out deliveries of non-memory kinds, or fewer than 3 modes with ≥ 100
   held-out deliveries → **measure more**.
2. Δ1 ≥ 0.03 and Δ2 ≥ 0.03, both 95% lower bounds > 0, heterogeneity p < 0.01, median lag ≤ 10
   events → **build** (a mode-aware kind prior as its own signal, never folded into
   `mentions.weight`).
3. max(Δ1, Δ2) < 0.01, or both 95% upper bounds < 0.02 → **drop**.
4. Otherwise → **measure more**.

{#c8-bands-list}

Volume: held-out-style evidence a week over 2026-11-11 → 11-25 (deliveries, ring events). {#c8-volume}

## Results: candidate 8, activity mode {#c8-results}

Script `cand8_activity_mode.py`, run 2026-11-25 on fresh copies (deleted after); output in
`run-output-c8-2026-11-25.txt`. Pre-registration `183c9e9c`. {#c8-results-note}

| # | candidate | metric (held-out) | result, 95% interval | band | action |
|---|---|---|---|---|---|
| 8 | activity mode | AUC gain of a kind × mode prior over kind alone (Δ1) and of popularity × mode over popularity (Δ2); non-memory deliveries, n = 3,595, 46 touched | **Δ1 +0.089 [+0.014, +0.166]**; **Δ2 −0.001 [−0.073, +0.061]** (AUC: kind 0.660, kind × mode 0.750, popularity 0.797, popularity × mode 0.796); heterogeneity p 0.059 | measure more | do not build; mode adds nothing over the popularity baseline |

{#c8-table}

- **Clusters.** 63,544 ring events in 71 sessions. Silhouette picked k = 3 (0.274; k 4-6 at
  0.215-0.234). Centroid shares: mode 0 bash-heavy (bash 0.54), mode 1 read/search (read 0.35,
  search 0.24), mode 2 non-tool-heavy (other 0.40, the ring's say/input/reason/git events). Every
  mode appears in all 4 held-out sessions.
- **Labels.** 331 labelled subagent threads, 173 `agentType` values; the five largest types sit
  in mode 1 for 0.68-0.81 of their windows; NMI(agentType, mode) 0.077. The modes separate
  "reading" from "running" and "talking", not one role from another.
- **Lag.** 500 synthetic switches: median 6 events, IQR [1, 12], 16 censored at 40.
- **Use by kind × mode** (held-out touched / delivered): doc 2/654, 10/751, 5/1,794 (mode 1 vs
  mode 2: 4.78, Wilson bounds [1.11, 20.4]); code 3/51, 1/74, 3/86; ruling 1/11, 4/27, 8/44; bug
  row 2/24, 1/23, 6/56; memory 0/806, 0/849, 5/2,031. Heterogeneity within kind: χ² 15.3,
  permutation p 0.059.
- **Bands, in order.** Not underpowered (46 touched ≥ 30; 3 modes ≥ 100). Build fails on Δ2. Drop
  fails (Δ1 ≥ 0.01, its upper bound 0.166). → measure more.
- **Secondary outcome.** Of 125 explicit `used` rows, 112 carry no file key; the 13 with one are 1
  doc and 12 memories, too few to read by mode.
- **Volume.** 5,720 deliveries with a mode a week; 12,196 ring events a week.

{#c8-results-list}

Could not measure: the 2026-11-13 pilot's labels (not on disk); the `agent` category (the STM
ring records no `Agent`/`SendMessage` call); session clustering (4 held-out sessions). {#c8-not-measured}

## M5: the popularity prior {#m5}

Brief [[agent-brief-m5-popularity-prior]] (Q89 = a, L254). In M4 the popularity control beat
every recall candidate ([[#popularity]]); M5 measures it as a pre-registered candidate.

rel: implements -> [[agent-brief-m5-popularity-prior]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]

### Pre-registration {#m5-prereg}

Written before any M5 result was computed; committed alone. Known before writing: M4's results,
the record shapes, and that `scan_prompt` delivers a median 21.5 items a query (IQR 10-30),
each with a `bytes` value. {#m5-prereg-note}

- **Data.** Fresh `cp -c` copies of `recall-events.jsonl`, the STM rings, the transcripts with
  `subagents/`, the memory dir; deleted after the run. One project (refmatrix): "per project" is
  this store only; no second project is measured.
- **Joins and split.** M4's `m4_common.py` and `build_units` unchanged (thread, file key, touch,
  window, new-touch gold, [[#defs]]). T* is fixed at M4's C1 value, 2026-11-15 03:13:18 UTC;
  held-out = units at or after it, through the copy time.
- **Units.** `scan_prompt` query units. Q1 gold: new-touch golds the unit's own `scan_prompt`
  query did not retrieve. Q2 gold: all new-touch golds in the window.
- **The prior.** `P_W(t)` = keys ranked by the number of new touches (a key's first touch by a
  thread within that thread's previous 200 calls; main loop and subagents) in the W days strictly
  before t; W ∈ {3, 7, 14}. Ties by key. W* is chosen on train units (best reach@10, ties to the
  smaller W) and reported on held-out with the other two W beside it. M4's fixed list (train
  missed golds before T*) is reported as the reference.
- **Controls.** *Chance*: k keys drawn uniformly from the keys newly touched in the W* days before
  t (`random.Random("m5")`); *time placebo*: `P_W*` computed at the time of a random held-out unit
  from another session (`random.Random("m5-time")`).

{#m5-prereg-defs}

#### Q1: reach of what scan-prompt missed {#m5-q1}

Metric: reach@10 of missed golds (k ∈ {5, 10, 20} reported); lift = reach@10(P_W*) −
reach@10(chance), paired bootstrap over units (2,000, seed `m5`). Recency value = reach@10(P_W*) −
reach@10(time placebo). Bands: fewer than 30 held-out units → measure more; lift ≥ 10 pp with
lower bound ≥ 5 pp → **pass** to Q2; lift < 3 pp or upper bound < 5 pp → **drop** (Q2 not
banded); else measure more. Recency: value ≥ 3 pp with lower bound > 0 → a windowed prior; else a
static list serves as well (the action says which). {#m5-q1-bands}

#### Q2: blend beside scan-prompt {#m5-q2}

Primary blend, at the query's own budget: with n = the items `scan_prompt` delivered, keep its
top n − ⌈n/4⌉ by rank and add the prior's top ⌈n/4⌉ keys not already among them. Secondary: the
8-slot form (its top 6 + the prior's top 2). Metric: Δ = reach(blend) − reach(scan-prompt's n
items alone) on all new-touch golds, paired bootstrap over units. Cost: payload bytes (each prior
item costs the median `bytes` of delivered code/doc item lines; dropped items give back their own
`bytes`), and false reach (the share of the list's keyed items not touched in the window).
Bands (only if Q1 passes): fewer than 30 held-out units → measure more; Δ ≥ 5 pp, lower bound ≥ 2
pp, false reach no worse than scan-prompt alone + 5 pp, payload change ≤ +25% → **build** the
blend; Δ < 2 pp or upper bound < 3 pp → **drop**; else measure more. {#m5-q2-bands}

#### Q3: stability and already held {#m5-q3}

Day-to-day: Jaccard of `P_W*` top-10 at each held-out day's 00:00 UTC with the previous day's.
Already held: per held-out unit, the share of `P_W*`'s top ⌈n/4⌉ the session had already touched
(any thread) before the query; also the share delivered earlier in the session by any channel.
Bands on the mean already-held share (touched or delivered): ≥ 50% → the prior must be deduped
against the session before delivery; 15-50% → dedupe re-deliveries only; < 15% → no dedupe. {#m5-q3-bands}

#### Q4: who it serves {#m5-q4}

Q1 lift and Q2 Δ split by M4's three activity modes (the ring window at the query; modes re-fitted
by `cand8_activity_mode.py`'s exact procedure on the new copies, centroids reported to compare with
M4's) and by the gold's kind (code, doc, ruling, bug row, memory). A stratum is **served** when its
lift's lower bound > 0 and **not served** when its upper bound < 3 pp; else undetermined. If Q2
builds and only some modes are served, the action gates the prior to those modes. {#m5-q4-bands}

Volume: held-out-style units a week over 2026-11-11 → 11-25. {#m5-volume}
