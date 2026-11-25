---
gmd: "0.1"
id: exploration-meta-associations
title: "Exploration: seven candidate meta-level associations, measured on existing logs before any is built (M4, Q84 = a)"
tags: [exploration, measurement, m-lane, retrieval, associations, recall]
metadata:
  node_type: exploration
  status: in-progress
  created: 2026-11-25
---

# Exploration: candidate meta-level associations, measured first {#root}

**Date:** 2026-11-25
**Status:** Pre-registration (this section is committed alone before any result is computed).
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
