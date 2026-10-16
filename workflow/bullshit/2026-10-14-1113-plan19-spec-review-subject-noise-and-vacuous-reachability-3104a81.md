---
gmd: "0.1"
id: bsd-plan19-spec-review-3104a81
title: "plan-19 spec review r1: the recall it packs is led by label-only subject nodes, the hook argv breaks when its env var is unset, the never-lose check passes by definition, and the floor is zero for every memory nobody has recalled yet"
severity: BULLSHIT
plan: plan-19-adaptive-memory-budget
task: spec-review-19.1-19.5
round: 1
tags: [bsd, audit, spec-review, memory, recall, hooks, budget, memory-index, decay, plan-19]
---

# ch-bsd spec review of plan-19, round 1 (pre-implementation) {#root}

**Commit reviewed:** `3104a81`, branch `wave0-spec-reviews`. While I worked, HEAD moved to `1bc9e24`
(a `handoff.md`-only commit by another agent). No plan file changed between the two commits.
**Written:** 2026-10-14T11:13:27-0700.

**Method:** I read the plan, tasks 19.1–19.5, [[exploration-adaptive-memory-budget]],
[[exploration-session-phased-context]], [[plan-review-2026-10-07]] (C4–C7, C11, waves), ADR-0004
`#amend-counter-rules`, and tasks 17.2, 21.1 and 23.1 (the dependencies 19.x names). Then I checked
every factual claim against HEAD:

- **Code:** `hooks.py`, `memory_index.py`, `handoff.py`, `verbs.memory_recall`, `store.py`
  (subjects), `consolidate.apply_plan`, `cli.py` (`memory compile`, `ingest-gmd --detach`,
  `memory get`), and the `daemon.py` subject/compile ops.
- **Live state, read-only:**
  - the installed `.claude/settings.json` hooks;
  - `MEMORY.md` and the memory dir;
  - `query.log` kinds;
  - `rmx memory list --type subject`;
  - two per-prompt recalls and one SessionStart recall, run with the DEPLOYED `rmx` (the hook argv,
    output to the scratchpad).

Nothing in `src/`, `tests/`, a store, a plan file, INDEX.md, IMPRESSIONS.md or last_run.log was
touched. No dev-venv `rmx` was run, and no `Store()` was opened.

rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: depends-on -> [[plan-review-2026-10-07]]
rel: related-to -> [[exploration-session-phased-context]]
rel: contradicts -> [[refmatrix/adr-0004-unified-location-space-index#rule-floor]]
rel: contradicts -> [[feedback_decay_never_loses_knowledge]]
rel: contradicts -> [[claude#no-silent-failures]]

## Live evidence {#evidence}

### Claims checked {#ev-claims}

| claim | where | at HEAD | status |
|---|---|---|---|
| SessionStart recall `hooks.py:277` | 19.1, plan | line 277, `--session-start --k 10 --scope both --json --timeout 10` | holds |
| per-prompt recall `hooks.py:313` | 19.1, plan, phased doc | line 313 | holds |
| PreCompact recall `hooks.py:340` | 19.1 | line 340 | holds |
| SessionStart 26,567 B | plan, 19.1 | **16,629 B today** (7 rows; the 7-day window holds 7) | point-in-time; see [[#m-2]] |
| per-prompt 16,347 B | plan, 19.1 | 15,153 B on a sample prompt (global leg timed out) | consistent |
| MEMORY.md 22,812 chars / 137 lines | plan, 19.3 | **22,368 chars / 134 lines** (22,784 B) | drifted ([[#m-2]]) |
| fold by mtime `memory_index.py:275` | plan, 19.3 | `key=lambda e: e.mtime` at 275 | holds |
| `render` `:239`, `MAX_INDEX_CHARS` `:63` | 19.3 | 239, 63 | holds |
| `STILL OVER` `:349` | 19.3 | line 351 | off by 2 ([[#m-1]]) |
| feedback never folds | plan | only `projects` are folded | holds |
| 86 projects folded, 134 inline | 19.3, exploration | **95 folded; 131 inline** (53 feedback + 11 reference + 67 project) | drifted |
| 39 compiled subjects | 19.3, exploration | 39 `mtype=subject` rows, **15 of them `unlabeled-N`** | holds; see [[#s-7]] |
| 0 memory-recall rows in `query.log` | plan, 19.2 | 9,270 rows: grep 6,553, scan 2,546, context 137, dsl 18, neighbors 16 | holds |
| `memory compile --apply` at `cli.py:12576` | 19.4 | `memory_compile` is at **12695** | stale ([[#m-1]]) |
| only `memory_compile_apply` is a daemon op | 19.4 R1 | `daemon.py:6286`; planning runs in the CLI | holds |
| `_ss_update_index` `handoff.py:224` | 19.4 | 224 | holds |
| `stm.topic_composites` `stm.py:790` | phased doc | at 789–790 | holds |
| MCP `rmx_memory_get` | 19.2 R3 | **does not exist**; the MCP tool is `rmx_memory` with `action=get` (`verbs.py:1026` → daemon op `memory_get`) | wrong ([[#b-6]]) |
| ≈500 memory rows | 19.2 R2 | 326 files on disk (162 project, 53 feedback, 11 reference, 34 save-state, 66 impressions) + 39 subjects + session cards | order of magnitude holds |

### Per-prompt recall is led by subject nodes (#obs-subjects confirmed) {#ev-subjects}

I ran the installed per-prompt argv (`--stdin-json --k 5 --scope project --json`) with the DEPLOYED
build on `{"prompt":"whats next?"}`. **All 5 rows are compiled subject nodes**:
`subject_collaboration` (13 chars of content), `subject_drift` (5), `subject_kickstart` (9),
`subject_tandem` (6) and `subject_fixes` (5).

On `"check r13 first then whats next"`, 1 of 5 rows was `subject_unlabeled_19`, with 12 chars.

The mechanism is in the code. `Store.upsert_subject` (`store.py:2618`) stores a subject as a
`kind=memory`, `mtype=subject`, **protected** row whose content is the bare label, so it is embedded
and competes in dense recall. The default exclusion in `verbs.memory_recall` is only `session/*`.

### Hook topology {#ev-hooks}

Installed `.claude/settings.json`:

- **UserPromptSubmit** runs three hooks in parallel:
  - `scan-prompt --max-tokens 2000`;
  - `focus hook --event input`;
  - the memory recall.
- **SessionStart** runs:
  - the recall;
  - the detached `ingest-gmd --as-memory '<live memdir>'` bridge, as a daemon job
    (`ingest_gmd_start`);
  - `focus context --top 15` on resume;
  - the p20-0 guardrail compiler.

`hooks.py:263-265` says outright that the harness runs an event's hooks in parallel.
`HOOK_ENV` is just `export RMX_INVOCATION_SOURCE=hook; ` (`hooks.py:26`).

### Who carries a `rel:` edge {#ev-rel}

298 of the 326 memory files carry at least one `rel:` line:

| type | with `rel:` |
|---|---|
| project | 141 of 162 |
| feedback | 47 of 53 |
| reference | 10 of 11 |
| save-state | 34 of 34 |

## Findings {#findings}

### BULLSHIT: the recall that 19.1 packs is led by label-only `subject_*` nodes, and no 19.x task owns that {#b-1}

**Spec:** the 19.1 R2/R3 inputs; 19.1 AC-2 and 19.2 R3, which consume them; 19.3, which promotes
subjects; [[exploration-session-phased-context#obs-subjects]]
**What:** the exploration flagged it and the live probe confirms it ([[#ev-subjects]]): on a short
prompt, every per-prompt hit is a subject node whose whole content is 5–13 characters.

- **19.1 makes it worse.** It raises the per-prompt `--k` from 5 to 12 and spends a hook line on
  every hit. On a cold prompt, that means 12 lines of `subject_drift — drift`.
- **19.1 AC-2 is gameable.** It counts "DISTINCT memories named". A subject row is a `kind=memory`
  row, so a payload of 12 subject labels passes ≥ 5x.
- **19.2 R3 records them as hits.** Subject nodes enter the never-decaying `lifetime_hits` and
  outrank real memories in 19.3's value fold.
- **No owner.** 19.3 uses subjects in the INDEX and says nothing about them in RECALL. 19.4 R1
  re-runs compile nightly, which adds more such rows ([[#s-7]]).

**Why it is bullshit:** a defect seen on every turn sits directly upstream of three tasks, and none
of them owns it. Every delivery number 19.5 reports would include it.
**Fix:**
- In 19.1 R2: exclude `mtype=subject` from dense and recent hits by default. Alternatively, expand a
  subject hit into its top members' hook lines. Either way, say which.
- Define "memory" in AC-2 to exclude subject rows.
- Add an AC: on `"whats next?"` against a catalog copy, the pack has 0 rows of `mtype=subject`.
- Mutation: drop the exclusion.

**Pattern match:** YES. The derived layer leaks into the primary surface (the operational-content
rule).

rel: contradicts -> [[feedback_operational_content_not_in_graph]]

### BULLSHIT: `--max-chars ${RMX_HOOK_BUDGET_CHARS}` in the hook argv breaks every recall hook in a shell where the variable is unset, and AC-4 passes on it {#b-2}

**Spec:** 19.1 R1, R3, AC-4
**What:** R1 already makes the env the DEFAULT when `--pack` is given without the flag. R3 then
interpolates it into the generated command anyway.

- `HOOK_ENV` exports only `RMX_INVOCATION_SOURCE`, and no shell sets `RMX_HOOK_BUDGET_CHARS` by
  default.
- So the command becomes `--max-chars --timeout 10`. Click then parses `--timeout` as the value of
  `--max-chars` and exits 2 ("not a valid integer").
- That happens on every prompt, SessionStart and PreCompact.
- AC-4 only checks that the string contains `--pack --max-chars`, so the broken command passes it.

**Why it is bullshit:** the AC cannot fail on the defect that disables the whole channel this plan
exists to fix.
**Fix:** R3 emits `--pack` only and lets R1's default apply, or bakes the numeric default into the
argv at generation time. Add an AC that RUNS the generated argv with the variable unset, and a
mutation that interpolates an unset variable.

### BULLSHIT: 19.3's reachability check, the plan's never-lose guard, passes by definition {#b-3}

**Spec:** 19.3 R4, AC-2, AC-5; the plan's `#goal`
**What:** R4 treats a memory as reachable if a "type fold line naming the recall command" covers it.
That is true of any folded member by construction, so the check cannot list one. The commands the
lines name do not reach every member either:

- **`--subject <slug>`.** `verbs.memory_recall` truncates `subject_leaves` to `[:k]`, with k = 10.
  A subject with 11 or more members reaches only 10.
- **`rmx memory list`.** It defaults to `-n 20`, and the fold line covers 95.
- **`rmx memory search <term>`.** It needs a term the reader does not have.

AC-2 deletes a subject line, but a member that still matches a type fold line stays "reachable" by
the same fiat. The vacuity mutation in AC-5 (an empty memory set) is the only vacuity it tests.
**Why it is bullshit:** this is the check that implements [[feedback_decay_never_loses_knowledge]]
for the index, and it can stay green while members are unreachable.
**Fix:**
- Define reachable OPERATIONALLY: the command printed on the line, executed against the
  memory-dir and catalog copies, returns the memory. Alternatively, the line enumerates the member.
- Fold lines name a command that enumerates every member (for example `--subject X --k <size>`, or
  a list scoped to the fold).
- AC: a subject with 15 members, 5 of them folded, all of which the printed command returns.
- Mutation: `[:k]` left at 10.

### BULLSHIT: 19.2's floor is zero for every memory that has never been recalled, which contradicts ADR-0004 #rule-floor, and 19.3 folds those first {#b-4}

**Spec:** 19.2 R5, AC-3; 19.3 R2/R3
**What:** `floor = base * log1p(lifetime_hits + 2*lifetime_used)` gives 0 when both counts are 0.
ADR-0004 #rule-floor says "A floor, never zero".

- **Day one.** No usage history exists, so all 326 memories start with no row and a floor of 0.
- **What folds first.** 19.3's value fold then folds by name, but the knowledge that is never
  recalled is exactly what the user's rule protects ("rarely-touched knowledge is exactly what
  memory exists to keep").
- **Undefined terms.** `base`, `asserted_floor`, the per-event recency increment, and the
  `first_seen` of a memory with no events (file creation, or first event?) are all undefined.
- **AC-3 cannot see it.** AC-3 tests only a memory with 1 hit and 1 use, so it cannot fail on a
  zero floor. Its "`== floor` after 10 half-lives" depends on the undefined increment.

**Why it is bullshit:** the ONE decay library (C4) ships a formula that violates the rule it
implements, and no AC exercises the zero case.
**Fix:**
- Use `floor = base * (1 + log1p(…))`, or a positive prior. Seed `first_seen` from the file's
  frontmatter `created`.
- Give `base` and `asserted_floor` numbers in the spec.
- AC: a never-recalled memory has `recency_effective > 0`, and it is not folded before a memory with
  equal score and newer `created`.
- Mutation: `log1p` without the `+1`.

### BULLSHIT: the queue 19.2 must use coalesces by key and drops on overflow, and the event schema it must use has no name, so the "exact, never-decaying" counts can undercount permanently {#b-5}

**Spec:** 19.2 R1, R2, R4; 23.1 R1; 21.1 R5; ADR-0004 #rule-no-undercount
**What:**

- **Coalescing.** 23.1's `BoundedQueue` "read and coalesce[s] by key at drain", which is the
  learn-queue dedup. It counts an overflow past `max_lines` and then drops it. 19.2 R4 adopts it
  with no `key_fn` and no overflow rule. Coalescing two `delivered` events for X into one, or
  dropping overflow, undercounts a lifetime field that by design can never be corrected.
- **Identity.** 21.1 R5's event carries `id` (the entity id), but 19.2 R1 keys by NAME precisely
  because a purge-and-re-add changes the id. An event queued before the purge and drained after it
  resolves to nothing.

AC-4 tests only the number of lock holds.
**Why it is bullshit:** two dependency specs, read together, break R2 (exact counts) and
#rule-no-undercount, and no AC sees either.
**Fix:**
- 19.2 R4: `key_fn` = a per-event unique id, or a coalesce that SUMS. Overflow blocks or spills to a
  second file; it never drops a usage event.
- 21.1 R5 adds `name` (and `partition` by NAME).
- ACs: 2 events for one key → count 2; overflow → no loss; a purge between enqueue and drain →
  counted on the name.
- Mutations: a dedup coalesce; drop on overflow.

### BULLSHIT: the "use" signal has an instrumentation trap that inflates a never-decaying counter on every recall, and AC-1 cannot see it {#b-6}

**Spec:** 19.2 R3, AC-1, Files
**What:** R3 counts a use when a memory is "fetched by name (`rmx memory get` / MCP
`rmx_memory_get`)".

- **The trap.** `verbs.memory_recall` calls the daemon op `memory_get` ONCE PER DENSE HIT
  (`verbs.py:766`). MCP has no `rmx_memory_get`: its tool is `rmx_memory` with `action=get`, which
  maps to the same op (`verbs.py:1026`). The natural single instrumentation point, the op, therefore
  counts every per-prompt recall hit as a use. `lifetime_used` never decays and weighs 2x in the
  floor.
- **AC-1 cannot fail on it.** AC-1 delivers through SessionStart, which is the `memory_recent` path
  and never calls `memory_get`.
- **The focus-note half has no implementation.** "Name or anchor appears in a later focus note or
  STM ref" names no module (`stm.py` and the focus hook are not in Files), no matcher and no AC.

**Fix:**
- Count `used` at the user-facing CLI `memory get` command and at the MCP `rmx_memory` get action,
  never in the op.
- AC: one dense recall of 5 hits leaves `lifetime_used == 0`.
- Mutation: the counter moved into `_op_memory_get`.
- Specify the focus-note matcher (exact `name`/`[[name#anchor]]` tokens, the same session, a
  window), with its own AC, or drop it from R3.

### BULLSHIT: the 19.x tests and measurements reach live sockets and stores by default, and bug-088's refuse stage is deferred {#b-7}

**Spec:** 19.1 Test strategy (RED), AC-1; 19.2 AC-1; 19.4 AC-1, AC-2; 19.5 R4
**What:** no spec names a sandbox (a tmp `HOME`, a tmp global root, a tmp registry, its own model
worker). Several paths default to the live system:

- **19.1's RED test** runs "the generated SessionStart argv". That argv has `--scope both`, so its
  global leg goes to `~/.refmatrix/rmxd.sock`. Its sibling hook bakes the LIVE memdir path in.
- **19.2 AC-1** enqueues under `_root()`, which is the bug-088 second-sighting shape.
- **19.4 AC-1** "runs only the SessionStart bridge". The generated bridge command carries the live
  memdir, and with R2 the bridge now REWRITES `MEMORY.md` and `.memory_hooks.json` there.
- **19.4 AC-2** drives 17.2's hub tick. The hub enumerates `discovery.load_registry()`, the live
  registry, and the step is `memory_compile`, which plans AND applies (it unlinks and relinks
  `part-of`).
- **The 19.1 AC-1/AC-2 and 19.5 measurements** "on a catalog COPY through the CLI" still need a
  daemon and models. That is the live `models.sock` (66 connects per suite run in bug-088) and the
  live global store for `--scope both`.

**Why it is bullshit:** bug-088 is open. Its refuse stage was deferred by the user, and auditors run
targeted files only because of it. These specs add tests that write to the live memdir and to live
stores' subject graphs.
**Fix:**
- Add a shared "Sandbox" section, referenced by every 19.x test strategy: a short tmp root; `HOME`
  → tmp (with `HF_HOME` at the real cache); a tmp global root and registry; `--memory-dir` passed
  explicitly; `--scope project` unless the global leg is under test, and then a tmp global store.
- Add an AC per task asserting that the conftest recorder logged 0 live connects for that file.

rel: contradicts -> [[project_suite_reaches_live_sockets]]

### SKETCHY: PreCompact is treated as a delivery channel, but nothing shows its stdout reaches the agent {#s-1}

**Spec:** 19.1 R3 (PreCompact `--k 30`); 19.2 R3 (`precompact` channel); 19.5 R1
**What:** the documented hook contract adds stdout to the context only for SessionStart and
UserPromptSubmit. PreCompact stdout is shown in transcript mode. If that holds, every PreCompact
"hit" is recorded as `delivered` without reaching the agent: a permanent inflation of
`lifetime_hits`, and of recall effort spent on k=30. 19.5 R1's probe uses UserPromptSubmit only.
**Fix:**
- 19.5 R1 also probes PreCompact (does a marker line appear in the post-compact context?).
- Until it is shown, 19.2 records `precompact` as `retrieved`, never `delivered`.

### SKETCHY: the ~10k cap is probed per hook, but the hooks share an event {#s-2}

**Spec:** 19.5 R1; 19.1 R1 default 9,500
**What:** on UserPromptSubmit, scan-prompt (up to 2,000 tokens, roughly 6–8k chars) and the 9,500-char
recall run in parallel. SessionStart adds `focus context` on resume. If the harness caps the EVENT's
combined additional context, a 9,500 budget overflows on every prompt, and both payloads degrade to
previews. The probe installs one throwaway hook.
**Fix:** R1 probes two hooks on one event (5k + 6k), records per-hook vs per-event, and sets the
per-channel default from that. This is also the input the phased-allocation task needs
([[#placement]]).

### SKETCHY: 19.1's arithmetic and baseline contradict R2 and R3 {#s-3}

**Spec:** 19.1 R2, R5, AC-2, AC-3
**What:**

- **Double count.** R2 emits a hook line for ALL hits before any body, so a body hit is also a hook
  line. R5's "hook lines + bodies + `+N more` = hits retrieved" therefore double-counts every body,
  and AC-3 fails on a correct implementation or forces a wrong one.
- **"Same retrieval".** AC-2's "measured against the same retrieval" contradicts R3, which raises k
  from 5 to 12.
- **Undefined prompts.** "20 recorded prompts (from this session's transcript)" names no session.
- **Baseline unit.** The baseline is "today's first 2 KB preview", but 19.5 R2 uses "whole when under
  the limit, else first 2 KB".

**Fix:**
- R5: distinct hits named (one hook line each) + `+N more` = retrieved; bodies ⊆ named.
- AC-2 fixes both k values, names the prompt file under `eval/production/memory_delivery/`, and uses
  19.5's baseline definition.

### SKETCHY: global-scope hits and the durability of the lifetime record are undefined {#s-4}

**Spec:** 19.1 R2(b); 19.2 R1, R4, AC-2
**What:**

- **Wrong fetch pointer.** The pack's pointer `(rmx memory get <name>)` is wrong for `scope=global`
  rows, because `rmx memory get` has no `--scope`. It fails, or returns a same-named project row.
- **Undefined home for global hits.** For a global hit, 19.2 does not say which store's queue and
  `memory_usage` table get the event.
- **Integer partition key.** `(partition_id, name)` is keyed by an integer that a partition rebuild
  reassigns. bug-098's repair rebuilt a partition, which would orphan the "never-decaying" history.
- **A non-derivable record in a rebuildable store.** The table lives only in the DuckDB catalog,
  which this project rebuilds offline (the 09-14 crash-loop fix, slot reconciliation). AC-2 tests
  only a bridge re-ingest.
- **Partition binding.** The drain must bind the partition explicitly per row, not through
  `with_partition` across a yield (the bug-098 race).

**Fix:**
- Key by partition NAME.
- Keep the drained queue as an append-only log that can replay the table, and add an AC: drop the
  table, replay it, and get identical rows.
- Define the global-hit route, and give the pack a scope-correct pointer.

### SKETCHY: "asserted = `rel:`-anchored" covers 91% of memories, so 19.3's asserted-last fold degenerates {#s-5}

**Spec:** 19.2 R5; 19.3 R3, AC-3; ADR-0004 #rule-asserted-floor
**What:** 298 of 326 memory files carry an outbound `rel:` ([[#ev-rel]]). If "rel:-anchored" means
"has a `rel:` line", then 141 of 162 project memories are asserted. R3's "asserted fold only after
every non-asserted entry has folded" then leaves about 21 foldable project entries, and AC-3 (all
feedback forced cold) cannot notice.
**Fix:** define asserted as feedback, protected, or the TARGET of an inbound `rel:` from another
memory or doc. Add an AC on the real distribution.

### SKETCHY: the dependency headers are circular and incomplete {#s-6}

**Spec:** 19.3 header ("Depends on: 19.2, 19.4"); 19.4 header ("Depends on: 19.3; 17.2"); 19.2
header ("Depends on: 19.1")
**What:**

- 19.3 and 19.4 depend on each other.
- 19.2 R4 requires 23.1's `BoundedQueue` and 21.1 R5's schema, but its header names only 19.1.

The waves happen to order them correctly. The task headers do not.
**Fix:**
- 19.3 depends on 19.2 only, and runs on a static catalog copy.
- 19.4 depends on 19.3 and 17.2.
- 19.2 depends on 19.1, 23.1 and 21.1 R5.

### SKETCHY: a nightly compile churns subjects, and the index is not regenerated after it {#s-7}

**Spec:** 19.4 R1, R2, R3; 19.3 R1
**What:** `consolidate.apply_plan` unlinks the compiler's own prior leaves and relinks them. It
**never removes a stale compiled subject NODE** (protected, embedded). Several things follow:

- **Recall noise accretes.** On a nightly schedule, every label drift leaves another empty
  `subject_*` row in dense recall ([[#b-1]]).
- **Order-dependent slugs.** 15 of the 39 labels are `unlabeled-N`, which is cluster-order
  dependent. After a re-compile, `--subject unlabeled-21` in `MEMORY.md` can point at a DIFFERENT
  cluster: a wrong answer, not an empty one.
- **No regeneration after compile.** R2 regenerates the index on bridged memory writes, not after
  the compile step. Subject lines stay stale until the next memory write.
- **Header-only lines.** An `unlabeled-N` header carries no meaning on 19.3's subject line.

**Fix:**
- The compile step regenerates `MEMORY.md` for that store's memdir.
- Stale compiled subject nodes with 0 leaves are excluded from recall (not deleted; removal goes
  through plan-22).
- Unlabeled clusters get a stable id (for example a hash of the sorted members) or render as their
  top member.
- AC: a re-compile that reorders clusters leaves every printed `--subject` command returning its
  printed members.

### SKETCHY: 19.4 adds a concurrent, non-atomic writer of `MEMORY.md` and the hook sidecar {#s-8}

**Spec:** 19.4 R2; 19.3 R5, R6
**What:** today one path rewrites the index (save-state, `_ss_update_index`). It does a
read-modify-`write_text` of `MEMORY.md`, then `memory_index.write`, which `write_text`s
`.memory_hooks.json`, neither of them atomically. R2 adds the bridge, which runs as a DAEMON job
(`ingest_gmd_start`) at every SessionStart. Problems:

- **Torn sidecar.** It can run concurrently with another session's save-state or PreCompact
  checkpoint. A torn sidecar read loses the curated hooks of folded entries (bug-050), which is
  curated knowledge.
- **Memdir.** R2 does not say how the memdir is derived for an arbitrary `--as-memory` target (a
  subdirectory, `impressions/`, a single file).
- **Self-call.** Inside the daemon, 19.3 R5's "read through the daemon" would be a call to its own
  socket.

**Fix:**
- Atomic writes (tmp + `os.replace`) and a lock file around the index-and-sidecar pair.
- Resolve the memdir as the configured memory root of the partition, never the target path.
- The in-daemon render reads the replica directly.
- AC: two concurrent regenerations leave the sidecar complete.

### SKETCHY: the index render depends on the wall clock, so `check()` never reads in-sync and the layout flips with the daemon {#s-9}

**Spec:** 19.3 R2, R5; 19.2 R5 (decay at read time)
**What:**

- **Clock dependence.** The scores decay at read time, so `render()` changes with `now()`.
  `_ss_update_index` calls `check()` and then `write()` on every save-state, so `check` effectively
  never reads in sync, and the index churns with no memory change.
- **Determinism only per instant.** "Ties break by name, so the output is deterministic" holds only
  per instant.
- **Layout flip.** R5's no-daemon fallback renders the OLD layout, so the index flips between two
  layouts according to daemon health.

**Fix:**
- Quantize the scores, or snapshot them at render and record them in a sidecar.
- `check()` compares against the recorded snapshot.
- The fallback renders from the last snapshot, not from the mtime layout.

### SKETCHY: the phased-context placement needs a schema field and a scan-prompt owner that do not exist {#s-10}

**Spec:** [[exploration-session-phased-context#placement]]; 21.1 R5; 19.1 Out of scope
**What:** the exploration places the phase field in 21.1's event schema. 21.1 R5 is
`{ts, channel, invocation, query_id, id, rank, stage}`, with no `phase`. It also gives scan-prompt
phasing to "plan-19", but 19.1 explicitly excludes scan-prompt's budget, and no plan-21 task
mentions scan-prompt. See [[#placement]].

### MEH: stale line references {#m-1}

- 19.4 cites `cli.py:12576`; `memory_compile` is at 12695.
- 19.3 cites `STILL OVER` at `:349`; it is at `:351`.

### MEH: quoted baselines have drifted; ACs should freeze theirs at RED time {#m-2}

The quoted numbers have moved:

| figure | spec | today |
|---|---|---|
| MEMORY.md chars | 22,812 | 22,368 |
| MEMORY.md lines | 137 | 134 |
| folded projects | 86 | 95 |
| inline entries | 134 | 131 |
| SessionStart payload | 26,567 B | 16,629 B |

19.3 AC-1's "1.5x of 134" should be "1.5x of the inline count measured on the frozen copy".

### MEH: the plan's #design still names a save-state fallback that C6 removed {#m-3}

The plan's `#design` 19.4 bullet says "or on save-state until that tick exists". That contradicts
19.4 R1 and C6.

### MEH: the 19.1 R3 deploy is not tied to the C11 window {#m-4}

19.1 R3's deploy does not name the C11 batched window (16.2/16.3, 21.3), which plan-of-plans says
19.1 joins.

### MEH: the `+N more` trailer embeds the raw user prompt {#m-5}

The trailer `rmx memory recall "<query>"` embeds the raw user prompt (quotes, newlines). The
session-start and recent modes need a mode-specific trailer.

### MEH: 19.5 R2 does not use the C7 recall-event schema {#m-6}

19.5 R2 does not read 21.1 R5's `retrieved` and `delivered` events, which C7 requires.

## Placement of "budget allocation by STM phase" {#placement}

**Recommendation:** add it as **task 19.6, in wave 3**. Scope it to the per-event budget (memory
recall AND scan-prompt) rather than to recall alone, because if [[#s-2]] finds the cap is per-event,
phasing IS the split between those two hooks.

**Hard prerequisites:**

- **19.1**, a packer with an allocation knob (hook lines vs bodies vs breadth pointers).
- **[[#b-1]]'s subject exclusion.** Otherwise "cold" payloads are subject noise, and any
  fixed-vs-phased comparison measures that noise.
- **19.5**, the per-event cap probe and the fixed-allocation baseline.
- **21.1 R5**, the event schema, **amended to carry `phase` and `name`**. 21.1 must ship it, and
  the phased doc's "plan-21 records the phase" needs a 21.1 R5 edit now, or the comparison needs a
  second instrument.
- **19.2.** It is not needed for the phase signal. It is needed for the `used` read-back that scores
  the comparison.

**Design notes for the spec:**

- **What the phase sees.** The recall hook runs in PARALLEL with `focus hook --event input`
  ([[#ev-hooks]]), so the phase is classified against the STM state BEFORE this prompt. That is the
  right signal ("what the session already knew"), but the spec must state it, and the tests must not
  assume ordering.
- **Pre-register first.** Write the comparison criterion and its threshold to disk before the run,
  following [[project_helix_phase2_decision_criterion]]. Keep turn count only as a logged covariate,
  never as a signal, until the comparison says otherwise.
- **Owner of scan-prompt phasing.** No plan owns it today. Either 19.6 takes it (recommended, since
  19.5 already measures scan-prompt as a channel) or plan-21 gets a task. Decide it before writing
  19.6.

## Verdict {#verdict}

**NEEDS-REVISION.** 23 findings: 7 BULLSHIT, 10 SKETCHY, 6 MEH.

The direction is right and the numbers mostly hold. The blockers fall into three groups:

- **Can't-fail ACs:** [[#b-2]], [[#b-3]], [[#b-6]].
- **Knowledge-loss vectors in the "never lose" plan:** [[#b-3]], [[#b-4]], [[#b-5]], and
  [[#s-4]] / [[#s-8]].
- **An unowned recall defect sitting upstream of every measurement:** [[#b-1]].
- **Unsandboxed tests that write to live state:** [[#b-7]].

## User decisions needed {#decisions}

1. **Subject rows in recall ([[#b-1]]):** exclude `mtype=subject` from recall by default, or expand
   a subject hit into its members? And should stale compiled subject nodes stay protected but
   recall-invisible ([[#s-7]])?
2. **Phased context ([[#placement]]):** accept task 19.6 in wave 3, with per-event scope that
   includes scan-prompt? Or should plan-21 own scan-prompt phasing?
3. **The `asserted` definition ([[#s-5]]):** inbound-`rel:` target, feedback, protected? Today's
   wording covers 91% of memories.
4. **PreCompact ([[#s-1]]):** keep it as a recall channel at all if the probe shows its stdout never
   reaches the agent?
5. **bug-088 ([[#b-7]]):** plan-19's tests need the sandbox the user deferred. Pull the refuse stage
   (or at least the tmp `HOME` / global root / registry fixture) forward ahead of wave 1?

## Ledger entries (to merge) {#ledger}

INDEX.md row:

```
| 3104a81 | 2026-10-14 | Todd Holley / Opus 4.x / spec-author (plan-19 drafting) | DIRTY | 23 (7B/10S/6M) | plan-19 spec r1: subject_* nodes lead per-prompt recall unowned (5/5 on "whats next?"); ${RMX_HOOK_BUDGET_CHARS} unset breaks all recall hooks, AC-4 blind; 19.3 reachability true by fiat; floor log1p(0)=0 vs ADR rule-floor; 23.1 coalesce/overflow undercounts; recall's internal memory_get = "use" trap; bug-088 unsandboxed ACs incl. hub tick on live registry. NEEDS-REVISION. [[bsd-plan19-spec-review-3104a81]] |
```

last_run.log:

```
2026-10-14T11:13:27-0700 commit=3104a81 verdict=DIRTY findings=23 (7B/10S/6M) report=2026-10-14-1113-plan19-spec-review-subject-noise-and-vacuous-reachability-3104a81.md
```

IMPRESSIONS.md bullets:

- "Never-lose specs keep proving never-lose with a check that is true by definition. A fold line
  'naming a command' reaches by fiat. Demand an OPERATIONAL reachability check: run the printed
  command, see the member (plan-19 r1 #b-3)."
- "Counters with no decay are irreversible, so every instrumentation point is a one-way door. Check
  which internal callers hit the same op: verbs.memory_recall calls memory_get per hit (plan-19 r1
  #b-6). Check that the queue does not coalesce (#b-5)."
- "Derived memory rows (subject_*, protected, label-only content) leak into primary recall, and a
  nightly re-compile would accrete them. Watch every plan that schedules a derive step for
  recall-surface pollution (plan-19 r1 #b-1/#s-7)."
