---
gmd: "0.1"
id: bsd-plan19-21-spec-diffcheck-r9-ebccb20
title: "plan-19 + plan-21 r9 diff check: every r8 finding closed at its text; the identity ASSIGNMENT has no single home (helix-facing), a t-watermark over a liveness filter drops rows, and a second sitecustomize collides with 23.0's"
severity: SKETCHY
plan: plan-19-adaptive-memory-budget, plan-21-agent-context-usage
task: spec-diffcheck-19.0-19.6-21.1-21.3
round: 9
tags: [bsd, audit, spec-review, diff-check, stm, helix, d9bm, d9bi, plan-19, plan-21]
---

# ch-bsd r9 diff check of plans 19 and 21 at `ebccb20` {#root}

**Commit reviewed:** `ebccb20` on `wave0-spec-reviews` (`git log -1` confirmed). Diff
`23ad703..ebccb20 -- workflow/plans/plan-19-* workflow/plans/plan-21-*`: 11 files, +638/-109.
**`src/`:** `git diff 23ad703 ebccb20 -- src/` is empty, so every cite read at `23ad703` holds.
**Written:** 2026-10-15T03:44:04-0700.

**Method:** read-only.
- Read the full diff against the r8 report and against decisions d9bm (as amended in `ebccb20`:
  "N = 8 newest", hub = member of ≥ 4) and d9bi in `workflow/plan-review-2026-10-14.md:388,392`.
- Hand-checked AC-7i's H1-H5 legs and each new mutant.
- Spot-checked 34 of the reviser's new cites at `ebccb20`. All 34 are correct: `cli.py`
  5097/5149/5228/6199/7518/10317/10763/11371/12155/12367/1234/1963-1967/8969-9013; `daemon.py`
  527/644/658-661/1362/1816/2499/2741/2862/3535/3651/3670/3816/4714/5265/5276/6067/6108/6336;
  `verbs.py` 585/813/956/1157; `scan.py:1036`; `hooks.py` 111/131-147; `search_hooks.py:309`;
  `hub.py` 88/100; `modelsrv.py:45`; `store.py` 2578/2692.
- Read `stm.py:127-392` and `cli.py:11990-12250` (the recall degrade paths), the `_errors.`
  string constants and the stdin parses in `src/`, and the `sitecustomize` mechanism of 23.0 R4.
- `tools/gmd/lint.py` on all 11 files: 0 errors. Deferral sweep of the added lines: one hit,
  "helix plan (a Wave 4 draft, not yet a file)". That names the consumer; it does not defer
  plan-19 work.

No live store or socket was opened, and nothing under `plans/` or `src/` was edited.

rel: derives-from -> [[bsd-plan19-21-spec-rereview-r8-23ad703]]
rel: specifies -> [[plan-19-adaptive-memory-budget]]
rel: specifies -> [[plan-21-agent-context-usage]]
rel: contradicts -> [[feedback_no_silent_failures]]

## Round-8 findings: status {#prior-status}

| r8 id | status | evidence at `ebccb20` |
|---|---|---|
| ns-1 hub pairs | **closed (d9bm applied)**. The assignment gap is [[#s9-1]]. | 19.6 R9 has the three-condition rule, `topic_hubs` (≥ 4 of the 8 newest by first-collapse `turn`, computed once from the input cache) and `snapshot_eligible`. R1 now defines its figure through `topic_hubs`, and the `return` row is amended. **Legs by hand:** H1 own line (hubs {hub1, hub2}, each in 4 of 4); H2 represented by S1 (`a` is not a hub, J = 2/4); H3 represented by S3 (3 snapshots, so no hubs); H4 represented (hub1/hub2 are in only 2 of the 8 newest). **Mutants:** drop hubs → H1 is represented; count only non-hubs → H2 gets its own line; threshold 3 → H3 own line; threshold 5 → H1 represented; all snapshots → H4 own line (4 of 10). Each fails its leg. H5 kills its mutant only under an order the test cannot set ([[#s9-1]]). |
| ns-2 dead-owner rows | **closed in mechanism**; new defect [[#s9-2]] | D6 now has two sets, `ended_sessions`, the per-root watermark, `owner_alive` and the lock-unavailable guard. AC-4b (ix) is added. |
| nm-1 `ps-failed` | **closed** | D6 "Unowned rows": a null `owner_start` counts as unowned. The (vii) sub-leg is added, and the mock is registered. |
| nm-2 lock | **closed in mechanism**; gaps [[#m9-2]], [[#m9-3]], [[#m9-4]] | D8 `_errors_locked` + `_append_error_rows`; halving by tmp + `os.replace`; the claim-rename migration; append before rename; AC-4b (x), (xi), (xii)(a). |
| nm-3 AC-6f | **closed**; new defect [[#s9-3]] | Commands are chosen by `focus hook --event` argv; the suffix is asserted and stripped; a global-daemon listener is added; stderr must be empty. |
| nm-4 envelope | **closed for the focus hook**; [[#s9-4]] for D9's other callers | The R5 row records `envelope-no-session` / `envelope-unreadable`; a falsy session raises; AC-6 has envelope legs. |
| nm-5 budget skip | **closed**; gaps [[#m9-5]], [[#m9-6]] | 21.1 R3/R4 `outcome`/`budget_s`/`CALL_OUTCOMES`; R7 adds `expired_reads`; AC-2b; 19.5 R2 counts attempted prompts; 19.2 AC-12 adds `max_hold_s`; 21.3 renames `timeout` to `skipped_budget`. |
| nm-6 equivalent mutant | **closed** | 19.4 R1 states 0.78.2. The mutant is replaced by "single-flight guard removed". |
| nm-7 cites | **closed** | All 34 spot-checked cites are correct (see method). |

### Disputes {#disputes}

- **19.1 `store.py:2620`: the reviser is right.** `Store.upsert_subject` is at `store.py:2692`
  at both `23ad703` and `ebccb20` (`:2690` at `331b414`). My r8 table's `:2620` was wrong.
- **19.4 R1's narrowing is right.** `daemon.call` (`daemon.py:658-661`) breaks after a post-send
  TIMEOUT. `ConnectionResetError`, `BrokenPipeError` and `JSONDecodeError` are still retried
  after a send (`:664-670`). So "never re-sends after a send" was too broad, and "never re-sends
  after a post-send timeout" is exact.

## Findings {#findings}

### SKETCHY s9-1: the identity ASSIGNMENT (live cluster → snapshot) has no single function; helix, the render and R1's replay all need it, and AC-7i's import check demands imports the render does not use {#s9-1}

**File:** `task-19.6-phased-context-and-topic-cache.md` R9 ("Among eligible snapshots … highest-
Jaccard … ties … at most one live cluster per prompt"), R1, AC-7i H5 and the import check; and
plan-19's header, interface 2 ("so helix can recompute topic identity from the cache alone").

**What:**
- `topic_hubs` and `snapshot_eligible` are PREDICATES. The rest of the identity rule has no
  named home: the highest-J choice, the newest-turn / smaller-`<cid>` tie-break, and the
  one-live-cluster-per-snapshot assignment. `derive_snapshots(graph, cache) -> cache` returns the
  cache, not which live cluster each snapshot represents.
- **Three consumers need that map:**
  - **The render** must know which snapshot stands for the EXPANDED live cluster, so it does not
    also show that snapshot as a collapsed line. The cache's own expansion update is written
    "after the input record", so on this prompt the cache does not reflect it.
  - **R1's replay** records "the share of non-selected live clusters represented by a snapshot
    they share exactly TWO members with".
  - **Helix** (d9bi).
  - Each would re-implement the assignment loop. That is the duplicate the converge rule forbids.
- **The import check works against this.** It requires `composite.py` to import `topic_hubs` /
  `snapshot_eligible`, which a correct render never calls (dead imports). It also bans any
  function "computing a member-set Jaccard" in the replay script, yet R1's own persistence
  figure is "Jaccard with the same cluster's previous member set".
- **H5's kill depends on order.** "Run with each of the two matching orders" names no way for
  the test to set that order. If the implementation processes {hub1, hub2, b} first, the
  "recompute hubs mid-call" mutant survives.
- **The input of `topic_hubs` is unstated.** It is not said whether a snapshot whose cluster was
  expanded (it "leaves the collapsed set") still counts toward the 8 newest. The cache file
  carries no schema version, although helix will read it.

**Fix (edit, no decision):**
- R9 adds ONE function: `stm.match_snapshots(live: list[frozenset], cache) -> dict[int, str |
  None]`. It maps the live-cluster index to the representing `<cid>`, or `None` for a new
  snapshot.
  - It computes `topic_hubs(cache)` once, and builds the pairs through `snapshot_eligible`.
  - It processes live clusters in a DEFINED order: descending member count, ties by the sorted
    member tuple. It assigns highest J first, with the stated tie-breaks, one live cluster per
    snapshot.
- Also add `stm.member_jaccard(a, b)`, the one Jaccard.
- **Callers:** `derive_snapshots` calls `match_snapshots`. `composite.py` calls it to drop the
  expanded cluster's snapshot from the collapsed set, or `PrePromptState` carries the map. R1's
  replay calls it.
- **Import check:** the render and the replay import `match_snapshots` / `member_jaccard`. No
  `len(x & y) / len(x | y)` and no `>= 4`-of-snapshots count appears outside `stm.py`.
- **H5** uses the defined order: N1 (10 members) is processed first, so the mid-call-recompute
  mutant always fails. Drop "each of the two matching orders".
- **State the cache contract:** `topic_hubs` counts every snapshot record in the cache file,
  whatever its collapsed / expanded state, and the cache file carries `schema: 1`.
- Add `match_snapshots` and the cache schema to the plan-19 header's helix interface 2.

**Pattern match:** YES (user's converge rule; r7 #s-1 → r8 #ns-1 → this: the identity rule is now
right, but where it lives is not yet one place).

### SKETCHY s9-2: the per-root `t` watermark over a LIVENESS-filtered set loses the older rows of an owner that was alive when a newer dead owner's rows were consumed {#s9-2}

**File:** 21.1 D6 set (2) ("with `t` above the per-root watermark … consumed by advancing that
watermark") and AC-4b (ix).

**What:**
- Set (2) is "dead owner AND `t` > watermark", and consuming it advances the watermark.
- **How a row is lost.** Live owner A writes a row at t = 10, and ended owner B wrote one at
  t = 20.
  1. The next SessionStart prints B's row and advances the watermark to 20.
  2. When A later ends, A's row (t = 10 < 20) is never selected.
- This is the normal case in this shared tree: two concurrent sessions, one ends, a third
  starts.
- AC-4b (ix) passes only because P2 writes BEFORE P3. Its stated order hides the defect.

**Fix:**
- Key consumption by OWNER, not by `t`. A dead owner writes no more rows, so "all rows of
  `(pid, pid_start)`" is a closed set.
- The per-root file holds `{root, consumed: [[pid, pid_start, t_max], …]}`.
- Set (2) = rows of dead owners not in `consumed`. Printing them adds the owner to `consumed`,
  under the same lock hold.
- A `consumed` entry is pruned once its `t_max` is older than the 24 h recall window
  (`handoff.py:508`, `window_s=86400.0`).
- **AC-4b (ix) reordered:**
  1. P3 (live) writes FIRST, then P2 writes and exits.
  2. P1 prints P2's row once.
  3. P3 exits, and the next run prints P3's row once.
- **Mutation:** a `t`-only watermark. P3's row is never printed, so the test fails.

### SKETCHY s9-3: AC-6f's "test-only `sitecustomize.py` … beside 23.0 R4's" cannot work: Python imports ONE `sitecustomize`, so either 23.0's child refusal or the connect logger is silently absent {#s9-3}

**File:** 19.0 AC-6f, "a connect logger". The colliding file is 23.0 R4:
`tests/sandbox_site/sitecustomize.py`.

**What:**
- `site` runs `import sitecustomize`, and the first one on `sys.path` wins.
- **If the logger's directory comes first,** the hook children lose 23.0's audit-hook refusal.
  That is a sandbox hole on exactly the run that exercises socket connects (d9bo (3): "no
  mutation run may reach a live path").
- **If 23.0's comes first,** the logger never installs and `connects.log` is always empty. That
  detector cannot fail; only the listeners still catch the mutants.

**Fix:**
- One hook, converged. 23.0's `sandbox_site/sitecustomize.py` appends every `AF_UNIX`
  `socket.connect` target to `$RMX_SANDBOX_CONNECT_LOG` when that variable is set. No second
  `sitecustomize`.
- **AC-6f gains two control legs:**
  - a child, with the variable set, connecting to a test listener writes exactly one log line
    (the detector can fail);
  - in the same environment, a child dialling a deny-set path still exits 86 (23.0's refusal is
    still loaded).

### SKETCHY s9-4: D9's one reader records `envelope-unreadable` for input that two of its three callers legitimately accept as prose, and the spec's "fallback outside the envelope path" contradicts AC-4b (xii)(c) {#s9-4}

**File:** 21.1 D9; AC-4b (xii)(c).

**What:**
- **Raw text is valid input today on both paths:**
  - `scan.read_stdin_prompt` (`scan.py:1036-1054`): "We accept either the envelope or raw text",
    with `JSONDecodeError` treated as prose.
  - `_resolve_query` (`cli.py:9001-9010`): `{`-prefixed text that fails `json.loads` without
    `--stdin-json` is "treat as prose".
- **D9 records a row on any non-JSON.** On unparseable or non-object input it prints a stderr
  line and records `envelope-unreadable`. A row in the machine-wide log is surfaced on
  SessionStart, so a prose prompt such as `fix the {braces` would raise an error line.
- **The spec contradicts itself.** It says the prose fallback stays "OUTSIDE the envelope path"
  with "the 'looked like JSON but isn't' branch unchanged". That branch IS a `json.loads` of
  stdin outside `read_hook_envelope`, which (xii)(c) forbids.
- **The prompt keys diverge.** `scan` reads `prompt`, `user_prompt`, `text` or `message`;
  `_resolve_query` reads only `prompt`. "Read `prompt` from the returned dict" silently drops
  three keys on the scan path.

**Fix:**
- New signature: `read_hook_envelope(raw, *, root, hook, require_session, prose_ok: bool) ->
  HookEnvelope(envelope: dict | None, prose: str | None)`.
- With `prose_ok=True` (scan-prompt, and `_resolve_query` without `--stdin-json`), unparseable
  input returns `prose=raw.strip()` and records nothing.
- `envelope-unreadable` is recorded only when `prose_ok=False`: the STM hooks, and
  `--stdin-json`, which keeps its `ClickException`.
- `stm.HOOK_PROMPT_KEYS` is ONE tuple. State whether it is scan's four keys or `prompt` alone;
  this is a behaviour change on one path, so record it.
- (xii)(c) holds as written.
- **AC:** `printf 'fix the {braces'` piped to `rmx scan-prompt` adds no row, and the prompt
  equals the text.
- **Mutation:** `prose_ok` ignored, so the row appears.

### MEH m9-1: `owner_alive`'s `None` conflates "unowned" with "lookup unavailable"; D7 still calls `_proc_start(os.getpid())`, outside AC-4b (xii)(b)'s set; `read_pid_pointer` keeps a private liveness check; `_proc_info` bypasses the check {#m9-1}

**What:**
- **The guard has no allowed way to run.** D6/D7 guard "`_proc_start(os.getpid())` is None", but
  (xii)(b) allows `_proc_start(` only in {`owner_alive`, `write_pid_pointer`,
  `read_pid_pointer`, `record_pointer_error`}. And `owner_alive` returns the same `None` for a
  null owner as for an unavailable lookup.
- **A private liveness check stays allow-listed.** `read_pid_pointer` judges liveness itself:
  `d.get("pid_start") != _proc_start(pid)` (`stm.py:387`).
- **The check can be bypassed.** `_proc_info(` (`stm.py:127`, called by `owner_lookup` at
  `:249`) is not checked.

**Fix:**
- Add `stm.liveness_available() -> bool`, called once per SessionStart run by D6 and D7.
- `read_pid_pointer` uses `owner_alive(pid, d.get("pid_start")) is True`.
- (xii)(b)'s set becomes {`owner_alive`, `liveness_available`, `write_pid_pointer`,
  `record_pointer_error`}. Add a second set equality: the callers of `_proc_info(` are
  {`_proc_start`, `owner_lookup`}.

### MEH m9-2: AC-4b (xii)(a) flags every string constant containing `_errors.`, which includes docstrings and the report text D6 requires {#m9-2}

**What:**
- At HEAD, `handoff.py:509`, `:522` and `:529` and `verbs.py:537` are string constants
  containing `_errors.jsonl`, outside `stm.py`.
- 21.1's Files row requires handoff's text to "name the new path".
- So the check fails at GREEN unless docstrings are edited to dodge it.

**Fix:**
- Scope the check to WRITE operations: `open` with mode `w`/`a`/`x`, `write_text`,
  `write_bytes`, `os.replace`, `os.rename`, `unlink`, where the path expression contains an
  `_errors` constant or derives from `pointer_dir()`. Exclude docstrings and message f-strings.
- handoff takes the path from one `stm.errors_log_path()`.

### MEH m9-3: AC-4b (x)'s identity fails at GREEN once a later halving drops an earlier `errors-truncated` row {#m9-3}

**What:**
- 4,000 rows of about 200 B is roughly 800 KB against 256 KiB, so the log halves at least
  three times.
- Each halving drops the oldest half by line count. A truncated row written by an earlier
  halving is eventually dropped, and its `dropped` count leaves the file.
- So "line count + Σ `dropped` = 4,000 + T" cannot hold. `dropped_by_root` and `unseen_dropped`
  have the same flaw.

**Fix:**
- D6/D8: a halving that removes `errors-truncated` rows adds their counts into the new row:
  `dropped` = lines removed + Σ the removed rows' `dropped`, and likewise per scope.
- Mutation: no rollup, so the identity fails.

### MEH m9-4: the migration claim's crash adoption reads `mtime`, which `os.rename` preserves; in production a live claim is "older than 60 s" at once {#m9-4}

**What:**
- **Live claims look abandoned.** A legacy `_errors.jsonl` was last appended days ago. After the
  claim rename, its `_errors.migrating.<pid>.jsonl` already has that old mtime. A concurrent
  SessionStart therefore adopts a migration that is still running.
- **The duplicate check does not cover the rest.** The idempotence check stops duplicate rows.
  The first run's final rename, though, then hits `FileNotFoundError`, whose handling is
  unspecified, and the `migrated=` counts are wrong.
- **One row is not idempotent.** The `legacy-unreadable` row's `t` is new on each run, so the
  `(t, reason)` key cannot match it.
- **(xi) cannot see the race.** Its fixture legacy file is fresh.

**Fix:**
- Claim name `_errors.migrating.<pid>.<sha1(pid_start)[:8]>.jsonl`, adopted only when
  `owner_alive(...) is False`. The weaker alternative: `os.utime(claim)` right after the rename.
- The final-rename `FileNotFoundError` is counted (`migrate-claim-lost`).
- `legacy-unreadable` takes `t` = the legacy file's mtime.
- (xi) sets the legacy file's mtime to one day old before the concurrent pair, and asserts
  `migrated=2` exactly once.

### MEH m9-5: `skipped_budget` is defined as "the `_degrade_or_raise` path", which also catches non-budget `OSError`s; `CALL_OUTCOMES` has no bypass check {#m9-5}

**What:**
- **Non-budget failures are mislabelled.** The daemon-RPC leg degrades on `(VerbBusyError,
  TimeoutError, socket.timeout, OSError)` (`cli.py:12241-12244`). A refused or reset connection
  would be recorded as `skipped_budget`, which inflates the figure 19.5 reads.
- **The vocabulary is unguarded.** The r8 rev table says each converged helper has a bypass
  check. Nothing stops 21.3 or a new emitter from writing its own literal outcome.

**Fix:**
- Classify by exception type:
  - `VerbBusyError`, `TimeoutError` or `socket.timeout` → `skipped_budget`;
  - any other `OSError` → `error`. The hook still degrades.
- `telemetry.log_query` validates `outcome` against `CALL_OUTCOMES` (plus 21.3's
  nudge-specific values) and counts an unknown value (`outcome-invalid`).
- AC-2b gains a leg: a listener that accepts and closes at once logs `outcome=error`.

### MEH m9-6: 19.2 AC-12's `max_hold_s` "equals" the recorder (two clocks), and its structural mutant is killed only by timing {#m9-6}

**What:**
- **Exact equality is unreachable.** 23.1 AC-19 compares the same pair "within 50 ms". Exact
  float equality between production-measured `hold_s` and the test recorder will not hold.
- **The structural mutant survives.** "All 1,000 events in one hold" satisfies "≤ 2 holds per
  500 events", and is killed only if that hold exceeds 0.5 s, which depends on machine speed.

**Fix:**
- Use "within 50 ms (23.1 AC-19)".
- Assert `holds == 2` (batch 500; plus finalize if any) structurally, beside the ≤ 0.5 s
  bound.

### MEH m9-7: text residue {#m9-7}

- **Stale "K = 8" notes.** d9bm was amended in `ebccb20` to "N = 8 newest". plan-19
  `#decisions` d9bm and 19.6 R9 still say "(d9bm's text writes 'K = 8' …)". Delete both
  parentheticals.
- **Two spliced RED sentences in 19.0 AC-6.** "RED at post-109 `master`: … row count … RED at
  post-bug-109 `master`: … composite block's topics". Split them so each RED claim sits under
  its own leg.
- **AC-6f runs no `--event say` (Stop) command.** Add it, or state why it is exempt.

## Verdict {#verdict}

**11 findings (0 BULLSHIT, 4 SKETCHY, 7 MEH). DIRTY.** Every r8 finding is closed at its
quoted text. None of the new findings needs a user decision; all are edit-level.

### Approval readiness, per task {#readiness}

| task | verdict | what is left |
|---|---|---|
| 19.0 | **needs edit** (small) | [[#s9-3]] (one sandbox hook plus two control legs), [[#m9-7]] |
| 19.1 | **ready** | the cite dispute is resolved in the reviser's favour |
| 19.2 | **needs edit** (one line) | [[#m9-6]] |
| 19.3 | **ready** | none |
| 19.4 | **ready** | the narrowing is verified |
| 19.5 | **ready** | [[#m9-5]]'s reclassification lands in 21.1 |
| 19.6 | **needs edit; helix-facing** | [[#s9-1]] (`match_snapshots`, `member_jaccard`, defined order, cache schema), [[#m9-7]] |
| 21.1 | **needs edit** | [[#s9-2]], [[#s9-4]], [[#m9-1]] to [[#m9-5]] |
| 21.3 | **ready** | `CALL_OUTCOMES` validation is 21.1's |
| 21.2, 21.4 | **ready** | unchanged |

**Helix (d9bi).** Of the four named interfaces:
- `PrePromptState`: no blocker.
- 21.1's events and `block_*` fields: no blocker (`RECALL_EVENT_FIELDS_V1` carries them).
- 19.2's usage record: no blocker.
- The topic cache: **blocked on [[#s9-1]]**. Without `match_snapshots` and a cache schema, helix
  cannot "recompute topic identity from the cache alone" without copying the assignment loop.

**Next step:** one edit pass, then a diff check against this report. No full round is needed.

## Ledger {#ledger}

Appended to `last_run.log`. Per the caller's "read-only otherwise", `INDEX.md` and
`IMPRESSIONS.md` were not edited.
