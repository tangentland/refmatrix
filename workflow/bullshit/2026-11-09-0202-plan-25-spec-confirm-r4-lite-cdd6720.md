---
gmd: "0.1"
id: bsd-plan25-spec-confirm-r4-lite-cdd6720
title: "ch-bsd focused confirm r4-lite, plan-25 r3 fold at cdd6720: DIRTY 0B/1S/5M; all 13 r3 findings closed in text, one new SKETCHY from d10's leg order"
tags: [bsd, spec-review, plan-25, recall, embedder, grep, bre, locale, measurement, bug-registry]
severity: SKETCHY
plan: plan-25-cliquedb-field-report
task: "25.1-25.5"
---

# ch-bsd focused confirm r4-lite: plan-25 revision round 3 {#root}

**Commits reviewed:** `9bcf464` (bug-173 → bug-180 renumber) and `cdd6720` (r3 fold). HEAD at
write time is `c5f91e4`. Nothing after `cdd6720` touches plan-25, plan-19 or `src/`.
**Date:** 2026-11-09T02:02:24-0800
**Author:** Todd Holley / Opus 5.5 / orchestrator (fold)
**Scope:** this is a confirm, not a full round. It checks every r3 finding against the fold's text
and against the code it cites. It also checks the fold's claims, not just its revision tables.
Read-only throughout:
- master `src/`;
- the 3.7 clone `/Volumes/littlebig/refmatrix-task-3.7` (`d093f65`);
- the bug-178 clone `/Volumes/littlebig/refmatrix-bug178` (`d13c4d7`);
- counts from `.refmatrix/query.log` and `cli.log`. No store was opened.

rel: part-of -> [[plan-25-cliquedb-field-report]]
rel: derives-from -> [[bsd-plan25-spec-r3-2f64edb]]
rel: evidence-for -> [[task-25.1-recall-hook-byte-budget]]
rel: evidence-for -> [[task-25.5-substring-bre-metas]]

## Probes {#probes}

- **Cited lines, re-read at master.** All of these are correct:
  - `cli.py`: `:11364` ("never a locally spawned model"), `:11369` (`RMX_RECALL_REPLICA_FIRST`),
    `:11394` (`with_partition(_resolve_partition())`), `:11453` (`_memory_partition_default`),
    `:12340` (`_degrade_or_raise`), `:12837` / `:12862` (`_RecallCall` / `.degraded`),
    `:12570-12574` (`ClickException`), `:6296-6301` (help), `:6324` (`grep`),
    `:6606` / `:6621` (`_index_may_answer` … `return not paths`), `:5970` (`-G` →
    `delegate`);
  - `verbs.py:376` (`memory_partition`, "THE routing every memory verb must use");
  - `memory_index.py:181` (`hooks[rel]`);
  - `hooks.py:187-191`, `:296-300`, `:313-320` (the SessionStart commands).
- **Degrade chain.** In hook mode, `_degrade_or_raise` passes a `VerbError` through as itself.
  `_RecallCall.degraded` then calls `classify_outcome(type(e), e, budgeted=True)`.
  `VerbAbsentError` is neither in `_budget_exception_types()` nor an `OSError`, so the result is
  `("error", "VerbAbsentError: <msg>")`. The fold's text matches the code exactly.
- **3.7 line-delta table** in `#overlap`: all 13 positions match `d093f65`. The five
  "byte-identical" function bodies were compared by AST source segment, and all 5 are identical.
- **`shared_embedder`** (3.7 `recall.py:623`): it serves the hub worker, else a private worker,
  else one cached in-process model. 3.7's graph verbs call it ONLY in their
  `except VerbAbsentError:` branch (`verbs.py:2322-2336`, `:2357-2361`).
- **Locale re-probe** on `café x` / `naïve_y`, using both `/usr/bin/grep` and `ggrep`:

  | probe | `LC_ALL=C` | `en_US.UTF-8` |
  |---|---|---|
  | `-o '\w\+'` | `caf`, `x`, `na`, `ve_y` | `café`, `naïve_y` |
  | `-c 'caf\b'` | 1 | 0 |
  | `-x 'caf.\? x'` | exit 1 | match |

  Under `env -i`, which leaves the locale unset, the result is the C answer. With
  `LC_CTYPE=en_US.ISO8859-1` it is 0. Delegation is the correct rule for both.
- **Percentile.** One hub of degree 100 and n = 41:
  - nearest-rank p99 = 100 (`d[40]`) for any second-largest degree;
  - `statistics.quantiles` exclusive gives `158 − 0.58 × d₂`: 156.26 for d₂ = 3 (the spec's
    156.3, inclusive 61.2, matching the r3 table) and 155.1 for d₂ = 5;
  - at n = 200 with a unique maximum, nearest-rank p99 is below the hub.
- **Logs, for 25.5 R3's join.**
  - `query.log` `kind=grep` rows: 7,788 rows, of which **0 carry `pid`**. Their `ts` has
    one-second resolution.
  - `cli.log` grep rows carry `pid`.
  - Joining the 35 path-less rows on (ts, pattern ∈ argv) gives 20 unique matches, 15
    ambiguous and 0 unmatched.
- **Registry merges**, simulated with `git merge-file` against the true merge bases:
  - **3.7** (base `591a2fb`): one tail conflict, master's 170-181 rows against 3.7's 171 and
    173. Keeping both sides yields exactly one `bug-173`, which is 3.7's.
  - **bug-178** (base `cba1745`, before the renumber): the clone still holds the OLD plan-25
    `bug-173` row. The 3-way merge drops it cleanly, because master deleted it and the clone did
    not touch it. The only conflict is the tail (179/180/181 against 178), and the merged file
    has 0 `bug-173` rows. No other file on either clone branch cites bug-173, bug-180 or bug-181.
- **Lint and links.** Each of the 8 touched plan files reports 0 errors (only dangling-doc
  warnings in single-file mode). Every `[[doc#anchor]]` between plan-25, plan-19, the bsd reports,
  plan-of-plans and the registry resolves: 0 misses.

## Per-r3 status {#r3-status}

| r3 | status | evidence |
|---|---|---|
| S1 embedder policy | **closed for hook and no-daemon; new gap at daemon-up / hub-down** ([[#n1]]) | [[task-25.1-recall-hook-byte-budget#r5]] "The embedder, per caller", d10. AC-4 (c) is now hook-only and asserts no child and no `sentence_transformers`. AC-4 (g) is present and RED at HEAD (`cli.py:12570`). Both mutations are in AC-14. "hook spawns private" is killed by (c)'s outcome assertion as well as its child check. "interactive kept hub-only" is killed by (g) raising. `shared_embedder(root)` fits as it exists on the branch: it takes root only, and the verb can tell hub, private and in-process apart by the returned client type. The verb parameter itself is MEH ([[#n2]]). |
| S2 C locale | closed | 25.4 b10. The `#r1` "locale gate first" bullet reads `LC_ALL` → `LC_CTYPE` → `LANG`, with unset meaning C. The C-locale table is in `#why`. The AC-2 C rows match the re-probe above. AC-8 includes C, POSIX, ISO8859-1 and unset. The mutation is present. 25.5 R2 "Locale (inherited)", AC-1 in both locales and the AC-5 mutation are present. |
| S3 25.5 bands | closed; one text defect, one soft trigger | [[task-25.5-substring-bre-metas#r3]]: the source is named, (b) and (c) both use denominator M, the minimum is M ≥ 30, and excluded rows are counted. [[task-25.5-substring-bre-metas#r4]]: below 30 → NO-GO, and NO-GO rows log flags and cwd. f4 is present. This is decidable as written for the first run, which is EXPECTED to fall below 30 and therefore be NO-GO. Two problems remain: the join key does not exist ([[#n3]]), and "first plan-of-plans review after 2026-12-31" is not an event ([[#n4]]). |
| S4 bug id | closed | Master has no `bug-173` text meaning the rg note: every remaining mention is a "renumbered from" history note. The bug-180 row is correct and records the renumber. `#overlap` has a `bug_registry.md` row with the 3.7 merge note. There is no bug-178 note. The simulated merge shows none is needed, but a single line would document it ([[#probes]]). |
| M1 25.5 edges | closed | (a) R2 supersedes 25.4 AC-4, and 25.4 AC-4 points back. (b) The help and docstring are rewritten, with AC-4b. (c) "explicit PATH arguments", AC-1 directory rows and a mutation. (d) `-G` is parsed, and AC-4 is RED at HEAD through the delegation note and no learned concept. |
| M2 hooks key | closed | R4 looks up by id, then by relative path. AC-9 runs a path-keyed and an id-keyed memdir. The mutation is present. |
| M3 chain / partition / A/B | closed | The chain was verified at the cited lines ([[#probes]]). `verbs.memory_partition(root)` is at `:376`, and the verb already bounds it with `timeout=_left(10.0)` (`verbs.py:1022`), so the hook budget holds. AC-4 (h) is present. `RMX_RECALL_REPLICA_FIRST` is at `:11369` and is read in the calling process. AC-4 (d) uses it. |
| M4 AC-4 (e) | closed | B is registered and `_resolve_root` is asserted first. bug-181 is logged. **Plan-25 does NOT depend on bug-181 being fixed**: AC-4 (e) guards its own test, and 25.1 does not change root resolution. bug-181 has no queue slot ([[#n5]]). |
| M5 percentile | closed | The method is `d[ceil(0.99n) − 1]`, compared with strict `>`. The fixture needs ≥ 200 entities with a unique maximum, which is asserted. The n = 41 unit row and its mutation are present. 100 vs 155.1 / 156.3 reproduce ([[#probes]]). |
| M6 25.2 text | closed | R5's union includes the list-marker shapes. `what now` is relabelled as a content word. |
| M7 one number set | closed; one arithmetic note ([[#n6]]) | `scan_cmd` 5,000 = 4,500 + 500 appears identically in R1, d1, `#deltas` and q2. `focus_context` 1,500 B is in R1 and `#deltas`. The reserves {UPS 512, SS 1,536} are in R1. The 19.1 `#rev-plan25` R1 row is reworded. 19.4 `#rev-plan25` exists, and its AC-6 / AC-14 mutation claim checks out. |
| M8 `#overlap` | closed | Re-stamped at `d093f65`. The table and deltas were verified. Rows for discovery, modelsrv and the registry are present. |
| M9 SessionStart | closed | R0 probes both events. `EVENT_SPLIT` and the reserve are keyed per event. R0b caps `focus context`. AC-12b CAN fail: at HEAD, `focus context --top N` prints > 3,000 B against a 1,500 B budget, and `hooks.py:313-320` passes no cap. |

## Findings {#findings}

### SKETCHY N1: with the daemon up and the hub down, d10 has interactive and MCP recall spawn a private worker instead of asking the warm daemon {#n1}

**File:** [[task-25.1-recall-hook-byte-budget#r5]] ("The embedder, per caller"; "tries the replica
leg first, then the daemon RPC"), d10. The 3.7 code it cites is `verbs.py:2322-2336`, `:2357-2361`.

**What:**
- **What the fold says.** Interactive and MCP callers embed through
  `recall.shared_embedder(root)`, "exactly as 3.7's graph verbs do". The replica leg runs BEFORE
  the daemon RPC.
- **What 3.7 actually does.** Its graph verbs call `shared_embedder` only after `_call(...)`
  raises `VerbAbsentError`. A live daemon always answers first.
- **What the text produces.** Take the case of the daemon up and the hub down, which is a normal
  state: a hub restart, or a split fleet as in `project_shared_worker_private_split`.
  - At HEAD, the replica leg returns None and the warm daemon answers in under a second.
  - Under 25.1 as written, the replica leg's `shared_embedder` builds a private worker or loads
    the in-process model, which takes 6-33 s on a one-shot `rmx memory recall`.
  - In the long-lived `rmx mcp` it also keeps a private worker resident while a daemon with a
    warm embedder is right there. That is the RSS and duplication family behind bug-171 and
    bug-173.
- **Why no test catches it.** No AC covers this case. AC-4 (d) runs the per-prompt (hook) argv
  only, and AC-4 (g) has no daemon.

**Fix (text):** order the `"shared"` policy as 3.7 does:
1. replica leg with the hub worker;
2. otherwise the daemon RPC;
3. only on `VerbAbsentError` from the daemon leg, the replica leg with `shared_embedder`.

Then:
- Add AC-4 (i): daemon up, hub down, interactive `--json` and MCP. The daemon RPC serves,
  `warnings` names the daemon leg, and no `modelsrv` child is spawned. RED-able by the mutation
  "shared policy tried before the daemon".
- Correct d10's wording: "as 3.7's graph verbs do, in the no-daemon branch only".

### MEH N2: `embedder_policy` as a named verb parameter is published in the MCP schema and has no click twin {#n2}

**What:** `verbs._schema_from_signature` builds the MCP tool schema from every named parameter.
Only `**kwargs` is excluded (`verbs.py:136`). So `embedder_policy` becomes an agent-visible
`rmx_memory_recall` argument, even though R5 says "MCP never passes it".

There is also no `--embedder-policy` click option. The parity test's `PAIRING` table cannot
express "twin = the hook-mode flag set", so AC-7's "lists … `embedder_policy` with their CLI
twins" cannot be met as worded.

**Fix:** pass it through the verb's existing `**internal` channel (as `trace` is,
`verbs.py:928`), so it is CLI-internal, invisible to MCP and needs no parity row. If it stays
public, add it to `PAIRING["rmx_memory_recall"]`'s no-twin set with a reason, and correct AC-7.

### MEH N3: 25.5 R3 joins `cli.log` to `query.log` "by pid and ts", but `query.log` has no `pid` {#n3}

**What:** none of the 7,788 `kind=grep` rows in `query.log` carries `pid`, and `ts` has
one-second resolution. On the 35 path-less rows, a (ts, pattern ∈ argv) join gives:
- 20 unique matches;
- 15 ambiguous, because one second holds the same pattern several times.

The key [[task-25.5-substring-bre-metas#r3]] names cannot be built. This defect originates in
r3's own recommended fix.

**Fix:** join on (`ts` second, pattern ∈ argv, `query.log` `root` = the store of `cli.log`'s
`cwd`, argv path-less). Exclude ambiguous matches and count them as a third excluded class beside
"no `answered_by`" and "join failed".

The first-run outcome does not change: M < 30 → NO-GO. NO-GO rows log flags and cwd, so later
runs need no join.

### MEH N4: the 25.5 re-measure trigger is not an event, and nothing owns it {#n4}

**What:** "at the first plan-of-plans review after 2026-12-31" names no defined event. Nothing
watches the `bre_meta_literal` count reach 30. The re-run is "a bug-174 row update, not a new
task", so the NO-GO default can persist indefinitely with nobody looking. This is a soft form of
rule 9a.

**Fix:**
- Put the trigger where it is read: the plan-of-plans row or goal queue, as "bug-174 re-measure:
  ≥ 30 `bre_meta_literal` rows or 2026-12-31".
- Give the count a reader. For example, the hook-cost report could print the running
  `bre_meta_literal` count.

### MEH N5: bug-181 is logged "Not scheduled" on a memory path {#n5}

**What:** bug-181 is a silent read of the wrong store on MCP memory recall. It falls under
CLAUDE.md `#no-silent-failures`, and the registry says "Not scheduled". Plan-25 does not depend on
it, because 25.1 AC-4 (e) guards its own test. But the defect has no slot in the plan-of-plans
goal queue, and r3 asked only for it to be logged.

**Fix:** give it a queue slot. Alternatively fold it into 25.1: the fix is about 5 lines (an
unresolvable `project` raises a `VerbError` naming the discovered names), and AC-4 (e)'s sandbox
already holds the registry fixture. One added assertion would cover it: `project=C`, which is
unregistered, raises.

### MEH N6: R1's per-event overflow note covers SessionStart only, but UserPromptSubmit's provisional sum also overflows under (B) {#n6}

**What:** under a per-event cap of 10,000 B:
- UserPromptSubmit's provisional producers sum to `prompt_recall` 4,000 + `scan_cmd` 5,000 +
  `focus_input` 256 = 9,256 B;
- the budget is `EVENT_BUDGET` = 0.9 × 10,000 − 512 = 8,488 B.

[[task-25.1-recall-hook-byte-budget#r1]] flags only SessionStart's 9,000 as not fitting. The rule
"R0 replaces all of them before GREEN" makes this harmless, but the asymmetry invites reading
UserPromptSubmit's numbers as already valid under (B).

**Fix:** extend that sentence to "both events' provisional sums exceed a per-event 10,000 B cap".

## Verdict {#verdict}

DIRTY: 6 findings (0 BULLSHIT, 1 SKETCHY, 5 MEH).
- **r3's findings.** All 13 are closed in text, and every cited line and number was verified.
  Three closures leave a residual: S1 (→ N1, N2), S3 (→ N3, N4) and M4 (→ N5).
- **New contradictions.** One: N1, d10's "exactly as 3.7's graph verbs do" is false under the
  replica-first order.
- **Approval readiness.** Plan-25 is approval-ready after N1 is folded. N1 is a text fold: the
  order rule, AC-4 (i), its mutation, and the d10 wording. N2-N6 are one-line text edits that can
  ride the same fold.
- **Next round.** No further full round is needed. A confirm of the N1 fold alone would
  suffice, and the orchestrator may self-verify it against this report.

rel: contradicts -> [[feedback_measure_the_path_users_run]]
rel: contradicts -> [[feedback_read_identifiers_at_write_time]]
rel: depends-on -> [[task-3.7-verb-it-backlog]]
