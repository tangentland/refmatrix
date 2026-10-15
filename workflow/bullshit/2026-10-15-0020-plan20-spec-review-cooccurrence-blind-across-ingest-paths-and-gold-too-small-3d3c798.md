---
gmd: "0.1"
id: bsd-plan20-spec-review-3d3c798
title: "plan-20 spec review r1: the co-occurrence signal is blind across ingest paths (79% of name-cluster pairs share no entity), and the gold set cannot support a 0.95 precision rule fit on itself"
severity: BULLSHIT
plan: plan-20-concept-similarity-eval
task: spec-review-20.1-20.3
round: 1
tags: [bsd, audit, spec-review, concepts, similarity, evaluation, helix, merge]
---

# ch-bsd spec review of plan-20, round 1 (pre-implementation) {#root}

**Commit:** 3d3c798c253fceac371e01bb919423eb6f73a75b (branch `wave0-spec-reviews`; HEAD moved to
331b414 during the run; `git diff 3d3c798..331b414` touches no plan-20 file and no ADR-0004 line)
**Date:** 2026-10-15T00:20:14-0700
**Author:** Todd Holley / Opus 5.5 / plan author (210f9b4, 2026-10-07; drift edit 097e7b1, 2026-10-14)
**Files reviewed:** `workflow/plans/plan-20-concept-similarity-eval.md`, task specs 20.1, 20.2, 20.3
**Mode:** read-only. Data came from scratchpad COPIES of `catalog.read.duckdb`: refmatrix (sha256
`da870acd…`) and cliquedb (sha256 `bdfce6fb…`). Each was opened with `duckdb.connect(read_only=True)`
in a fresh process. No live slot, socket or `Store()` was opened. No plan, spec or src was edited.

rel: evidence-for -> [[plan-20-concept-similarity-eval]]
rel: contradicts -> [[plan-review-2026-10-14#t10-waves]]
rel: related-to -> [[refmatrix/adr-0004-unified-location-space-index#amend-shape]]
rel: related-to -> [[task-22.4-merge-writes]]
rel: related-to -> [[task-23.0-test-sandbox]]

## Verdict {#verdict}

**NEEDS-REVISION. DIRTY: 11 findings (2 BULLSHIT, 5 SKETCHY, 4 MEH).**

The plan is not approvable for Wave 4. The signal it expects to win is computed on a construct that is
zero by construction for most of the pairs that matter. The gold set is too small to show the
precision the rule must meet. The threshold is fit on the same pairs it is scored on.

**Verified true:**
- `embedder.py:313-349` is `_extract_concept` (the next def is at :352).
- All six stores exist on disk.
- The read snapshot is still daemon-maintained after d9ao (`daemon.py:1782`).
- The 20.1 strata can be filled on refmatrix: 10,476 pairs with df ≥ 2 on both sides, 6,730
  cross-namespace, 919 case-only, 1,082 symbol-vs-word.
- The pre-registered stop rule in 20.3 R1 and the df bucket edges are stated before data.
- GMD lint: 0 errors on all four files. The only warnings are cross-doc wikilinks, which
  single-file mode does not resolve.

{#verdict-body}

## Findings {#findings}

### BULLSHIT b-1: "entity-set Jaccard / lift / NPMI" is blind across ingest paths, so the first-class signal is zero on the pairs it must judge {#b-1}

**File:** task-20.2 R1(a)(b)(e); plan `#why` (the AUC 0.929 cite)

**What:** The spec scores co-occurrence on "the two concepts' entity sets", meaning the raw
`entity_links.entity_id` set for each `concept_id`.

**Evidence (copies, partition `refmatrix` / `cliquedb`, noise=0, `same_as` excluded):**
- Silver(b) pairs (20.1's name rule, both df ≥ 2) that share NO entity: **8,237 of 10,476 (79%)**
  on refmatrix and **4,014 of 6,508 (62%)** on cliquedb.
- Grouped by which kinds of entity link to each side, the largest refmatrix groups are:
  - code-only vs concept-only: 3,116;
  - code vs concept+memory: 1,452;
  - code vs concept+doc+memory: 1,092;
  - code vs concept+doc: 570.
- Examples:
  - `keyword/count` is mentioned by 64 code entities. `count` is mentioned by 447 anchored concept
    nodes and 3 docs. They have no common entity.
  - `keyword/store` (384 code) vs `STORE` (4 concept).
  - `keyword/migrate` (2 code) vs `Migrate` (2 concept + 2 doc).
- Jaccard AUC of silver(b) against df-matched random pairs is **0.547** on refmatrix and **0.615**
  on cliquedb. Random pairs share an entity 13% / 17% of the time; name-matched pairs 21% / 38%.

**Why it's bullshit:** Code ingest hangs `keyword/x` on code entities. Prose ingest hangs `x` on
`doc#anchor` concept nodes, memories and docs. The two populations never intersect, so the score
says which ingest path produced each concept, not whether the two concepts mean the same thing.
This covers exactly the stratum the gold set over-samples: ≥ 50 cross-namespace pairs of the form
`x` / `keyword/x`, plus most symbol-vs-word traps. R3 will then report "no signal is safe" (or pick
the name rule) for an artifactual reason.

The cited prior (AUC 0.929, `project_cooccurrence_beats_dense_for_doc_similarity`) measured
doc-to-doc pair overlap on 256 cliquedb markdown docs. That is a different construct, carried over
to concepts without a check.

**Fix:** 20.2 R1 has to define the co-occurrence unit.
- Roll each linking entity up to a common unit before intersecting:
  - a code symbol to its file;
  - an anchored concept `doc#a` to its doc file;
  - a memory to itself.
- And/or add a second-order signal: the cosine of the two concepts' co-concept profiles over those
  units.
- Name the linkages counted. Is `lead` in? Is `same_as` out?
- Add a pre-run AC: per stratum, report the share of silver(b) pairs with |A∩B| ≥ s after roll-up.
  A stratum where that share is below a stated floor is reported as "unmeasurable by co-occurrence"
  and is not folded into the AUC.

**Pattern match:** YES. This is "the benchmark measures a different path than the one used"
(`feedback_measure_the_path_users_run`).

rel: contradicts -> [[project_cooccurrence_beats_dense_for_doc_similarity#claim]]

### BULLSHIT b-2: the gold set cannot support the decision R3 makes, and θ is fit on the pairs it is scored on {#b-2}

**File:** task-20.1 R2; task-20.2 R2, R3; consumer task-22.4 R2

**What:** About 200 gold pairs, with ≥ 40 in the symbol-vs-word stratum. R3 chooses θ "on gold where
precision is ≥ 0.95 on the trap stratum", and R2 reports AUC and P@k on the same gold, per store and
pooled.

**Why it's bullshit:**
1. **40 pairs cannot show 0.95.** If all 40 trap pairs were predicted merges and every one were
   correct, the one-sided 95% Clopper-Pearson lower bound would be 0.928 (two-sided 0.912). It takes
   ≥ 59 correct predicted merges with zero errors to reach 0.95. Most trap pairs will be labelled
   `distinct`, so the predicted merges in the stratum will be far fewer than 40.
2. **The trap metric is precision, and precision is 0/0 when the rule predicts no trap merge.** That
   is a vacuous pass.
3. **θ is chosen on gold and then reported on gold.** The reported numbers are optimistic by
   construction. There is no held-out split.
4. **Per-store gold metrics split about 200 pairs over 4 stores.** That is about 50 pairs, and about
   10 trap pairs, per store, which is noise.
5. **The support `s` in the R1(b) gate is never given.** It is a free parameter fit after the data.
6. **The consumer needs a bound R3 never produces.** 22.4 R2 merges "nothing below the rule's
   precision bound". R3 produces a point estimate.

**Fix:**
- Pre-register `s` and the θ-selection rule in 20.2 before 20.1 freezes.
- Split gold into tune and held-out halves (or k-fold), stratified. Report only held-out numbers.
- The gate becomes: the one-sided 95% Clopper-Pearson lower bound of precision over ALL predicted
  merges is ≥ 0.95, AND the trap stratum's false-merge rate has an upper bound ≤ a stated value.
  "Zero predicted merges" means "no rule".
- Size gold for that gate. For example, ≥ 120 trap pairs and ≥ 300 total, or state the precision
  the planned size can actually show.
- Pool for decisions. Per-store results are descriptive only.
- Output the bound 22.4 consumes, and add `rel: specifies -> [[task-22.4-merge-writes#requirements]]`.

**Pattern match:** YES (`bsd-impressions` line 74, plan-13 r2, "who builds the set").

### SKETCHY s-1: the labeller is shown the signal under test, and "merge" is never defined {#s-1}

**File:** task-20.1 R2; plan d-3

**What:** The gmd-curator labels pairs "citing the evidence it looked at (definitions, top
co-occurring entities)".

**Why it's sketchy:**
- Top co-occurring entities ARE the inputs to signals (a) and (b). Labels conditioned on
  co-occurrence will inflate co-occurrence's AUC.
- There is no written definition of `merge` versus `distinct`. For example: is the class `Store`
  vs the word "store" distinct always, or only when the defined symbol's role differs?
- The 50-pair agreement has no pre-registered threshold and no consequence if it is low.
- The wave list says "the user's 20.1 labels", while the spec says the curator labels and the user
  reviews 50.

**Fix:**
- The labeller sees each concept's own definitions, `defines` sites and source/prose lines
  separately. It never sees overlap lists or similarity scores.
- Write a one-paragraph labelling guide whose criterion is: "an alias in the term map would lose
  nothing".
- Pre-register κ ≥ 0.6 (or agreement ≥ 0.9) on the 50. If it falls short, the user labels the full
  trap stratum.
- Store the evidence shown with each label.

### SKETCHY s-2: the name signal and its fusion cannot be measured, and silver(a)'s "trivially high" floor is trivially zero {#s-2}

**File:** task-20.1 R1(a), R2; task-20.2 R1(d)(e)

**Evidence:**
- Every gold pair is a name-cluster pair, so signal (d) is 1 on all of gold and its gold AUC is 0.5
  by construction. Fusion (e) "gated by (d)" on gold equals (a)/(b) alone.
- On silver, positives are defined by the name rule. Only 2 of 10,476 df-matched negatives
  name-match, so (d)'s silver AUC is about 1.0, which is circular.
- Silver(a): on the refmatrix copy, **all 39,225 `same_as` alias concepts have zero non-`same_as`
  links**. Their entity sets are empty, every co-occurrence signal is 0 for them, and 8,510 have no
  vector.

**Fix:**
- State that the name rule is the candidate generator, not a scored signal. The deliverable is then
  "within a name cluster, merge iff …".
- Drop (d) from the AUC tables, or add gold pairs that do not name-match.
- Drop silver(a), or score an alias through its canonical's set and say so.

### SKETCHY s-3: "read-only" is one kwarg assertion on one of three scripts, and the sandbox it cites does not cover eval scripts {#s-3}

**File:** task-20.2 AC-3; task-20.1 (no AC); task-20.3 R4 (no AC); plan `#drift-2026-10-14`

**Why it's sketchy:**
- A test that asserts `read_only=True` on catalog opens is passed by each of these:
  - opening the copy through `Store()`, where `CATALOG_DDL` and the `canonical_name` index run on
    every open and mutate the COPY, breaking 20.1 AC-1's hash and 20.2 AC-1's byte-identity;
  - calling `build_context` or `rmx context`, which learn the hit;
  - `daemon.call` to a live socket;
  - a Lance `optimize` or `cleanup` call.
- 20.1's `build.py` and 20.3's `dense_synonyms.py` have no read-only AC at all.
- The drift note puts "every test and evaluation" inside 23.0's sandbox. 23.0 is a pytest
  `conftest.py` plus audit hook, so a directly-run eval script is outside it. 23.0 R3 also refuses
  READ opens of the repo and registered roots, so the copy step cannot run inside it.
- No copy procedure is specified, and the Lance copy is not hashed in the manifest. Copying a
  dataset with 559 versions while it is being written can tear.
- bug-112: a second in-process `connect` to a re-copied path returns the old instance.

**Fix:**
- Specify one copy step: `catalog.read.duckdb` plus `vectors/<partition>/concept.lance` at a
  recorded version, copied to content-hashed filenames under a scratch dir. Both hashes go in the
  MANIFEST.
- Scripts accept only those paths. They refuse any path inside a `.refmatrix/` that holds
  `rmxd.sock` or `active`.
- Use raw `duckdb.connect(read_only=True)` only. An AST allow-list test forbids importing
  `refmatrix.store`, `daemon` or `context`.
- Re-hash the copies after each run.
- Add an AC whose named mutations each fail it: `read_only=False`, `Store()` open, `daemon.call`,
  a Lance write.
- Run the scripts' tests under 23.0's audit hook.

### SKETCHY s-4: the requirements commit raw pairs from private stores to the public repo, against d8f and the plan's own drift note {#s-4}

**File:** task-20.1 R5, AC-3, `#files`; task-20.3 AC-2; plan `#drift-2026-10-14` (d8f)

**What:**
- 20.1 commits `pairs-<store>.jsonl` and `gold.jsonl` under `eval/production/concept_pairs/`,
  which is not gitignored.
- 20.3 lists the top accepted pairs in `eval/production/REPORT.md`, which is tracked.
- Both include code identifiers from cliquedb, viascope, cliquet, atldb and orderly.
- The drift note says only a hash and a redacted fixture are committed, but the requirement text
  was never changed.

**Fix:**
- Raw sets go under the gitignored `eval/datasets/concept_pairs/`.
- Commit MANIFEST.json (hashes, seed, counts) and a redacted fixture.
- AC-3 becomes: "the manifest commit precedes `score.py`'s first run, and `score.py` refuses a set
  whose hash is not in a committed manifest".
- REPORT lists only pairs from refmatrix's own store, or lists pairs by hash.

**Pattern match:** YES (a decision row is not a spec edit; p16/22 r6, p23/17 r6).

### SKETCHY s-5: the population and df are undefined, and dangling rows feed the sets {#s-5}

**File:** task-20.1 R1, R3; task-20.2 R1; task-20.3 R1

**Evidence (copies):**
- No partition is named. refmatrix's copy holds 20,495 `sessions-refmatrix` concepts, none
  embedded.
- Noise is not addressed: 28,285 `phrase/*` rows, all embedded. ADR-0004 deletes `phrase/*`, and
  these rows would set 20.3's random-pair band.
- Anchored `doc#anchor` concepts embed their body (`embedder.py` docstring) and are not separated.
- 4,205 `entity_links` rows have a `concept_id` that is a code, memory or doc entity.
- df is not defined: which linkages, and is `same_as` excluded?
- cliquedb's copy has **5,298 dead-entity and 8 dead-concept `entity_links` rows** (the d9an class),
  which would count as members.

**Fix:** 20.1 R1 should say:
- project partition only, `kind='concept'`, `noise=0`;
- `#`-anchored concepts excluded or stratified;
- entity sets inner-joined to existing `entities` rows;
- df = distinct linking entities over the named linkages;
- excluded counts reported;
- the copy precondition: taken after 22.2 has removed d9an/d9ar rows on that store, or exclusions
  counted.

### MEH m-1: stale and inconsistent numbers {#m-1}

**File:** plan `#why`, `#scope`

**What:**
- "75,276 concepts": the 2026-10-15 copy has 85,003 in partition `refmatrix` (56,718 non-noise).
- "collapses 25,324 of them into 5,363 clusters": the exploration says those clusters cover 14,653
  rows (`#data`).
- "747 empty protected `query/*` rows" was withdrawn by plan-22 d-3 (#b-6) and d6c.
- "9,182 orphan aliases" is presented as a count, while plan-22 presumes no count.

**Fix:** Mark these as 2026-10-07 exploration figures or re-measure them. Change 25,324 to 14,653.
Drop 747, or cite plan-22 d-3.

### MEH m-2: 20.3's go result has no pre-registered meaning {#m-2}

**File:** task-20.3 R3, AC-2

**What:** The band stop is pre-registered. What acceptance rate makes dense synonyms usable by the
helix is not. The 30-pair user review has the same problem as s-1.

**Fix:** Pre-register the go rule, e.g. "accept-rate lower 95% bound ≥ 0.5 → listed for the helix
plan; else closed as a negative result".

### MEH m-3: df buckets are undefined for a pair, and the hapax bucket contradicts ADR-0004 {#m-3}

**File:** task-20.2 R4

**What:**
- A pair has two dfs, and the spec does not say which one sets the bucket.
- ADR-0004 `#amend-shape` says hapax rows "never [feed] co-occurrence evidence".
- Silver(b) requires df ≥ 2, so its hapax bucket is empty.

**Fix:** Bucket by `min(df_a, df_b)`, drop hapax for the co-occurrence signals, and report the
hapax count.

### MEH m-4: bookkeeping and edges {#m-4}

**What:**
- 20.3 says "Depends on: 20.2" but has no `rel: depends-on -> [[task-20.2-signal-evaluation]]`.
- The plan cites plan-22, task 23.0 and d8f in prose with no `rel:`.
- 20.1 cites "the ch-bsd impression" without `[[bsd-impressions]]`.
- 20.2 R4 cites the adjacency-shape spike without a `rel:` to `spike-2026-10-07-adjacency-shape`.
- The drift note's "Usage counters referenced here" points at nothing in plan 20.
- ADR-0004 `#rule-no-delete` still says "plan-20's rule (task 22.4)", and the exploration's
  `#transition-summary` still says "the writes are task 22.4", after d9j.
- The wave list places 20.1 only as "the user's labels" and never schedules its `build.py`.
- plan-of-plans row 20 does not mention Wave 4 or the 22.4 hand-over.

**Fix:** Add the edges, delete the counters line, update the two stale pointers to "the helix plan
(d9j)", and put 20.1's build in a wave.

## Needs a user decision {#user-decisions}

1. **Who labels, and how much.** The curator proposes and the user reviews 50 (d-3, a default
   taken), versus the user labelling the full trap stratum. b-2's sizing implies about 300 gold
   pairs with ≥ 120 traps, and that is user time.
2. **The precision target.** Is 0.95 a point estimate (as written) or a one-sided lower bound? Only
   the bound means anything for 22.4, and it decides the gold size.
3. **Whether d8f covers concept names from the private stores.** Can REPORT name pairs from
   cliquedb or viascope (s-4)?
4. **When the 20.1 copies are taken.** Now (Wave 0, before the 22.2 dangling-link removal and
   before d9ao's frozen-slot recovery), or after Wave 1's cleanup on each store (s-5).

## Method {#method}

- The decision rows were read at HEAD: d1a/d1b, d8f, d9e, d9i-d9k, d9x, d9ac, d9ae, d9an-d9at and
  `#t10-waves`.
- Also read: ADR-0004 `#rule-no-delete`, `#amend-gates`, `#amend-shape` and `#amend-2026-10-14`;
  task 22.4; plan-22 d-3/d-17/d-21; 23.0 R1-R3; the bug-112 registry row; and the exploration.
- The measurement scripts were run from the scratchpad with `.venv-eval/bin/python -I` on the copies.
- Binomial bounds come from `scipy.stats.beta.ppf`.

{#method-body}
