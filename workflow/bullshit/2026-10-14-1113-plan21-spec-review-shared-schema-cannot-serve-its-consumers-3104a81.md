---
gmd: "0.1"
id: bsd-plan21-spec-review-3104a81
title: "plan-21 spec review r1: the ONE recall-event schema has no session, contradicts 19.2's key, and has no production emitter; the replay and -E claims do not reproduce as stated"
severity: BULLSHIT
plan: plan-21-agent-context-usage
task: spec-review-21.1-21.4
round: 1
tags: [bsd, audit, spec-review, telemetry, context, recall-events, phased-context]
---

# ch-bsd spec review of plan-21, round 1 (pre-implementation) {#root}

**Commit reviewed:** `3104a81` (plan-21 plan + task specs 21.1-21.4, unchanged since `drafting`).
HEAD moved to `1bc9e24` during the run (a concurrent agent's `handoff.md` commit); nothing under
`workflow/plans/`, `src/` or `docs/` changed between the two. Branch `wave0-spec-reviews`.
**Written:** 2026-10-14T11:13:22-0700.

**Method:** I read the plan, all four task specs, the two explorations
(`agent-context-usage.md`, the new `session-phased-context.md`), the plan review (C7/C8/C9/C11),
19.2 and 19.5, and the plan-13 header. I checked every factual claim against code at HEAD:
`telemetry.py` (`INVOCATION_SOURCES`, `invocation_source`, `log_query`), `mcp.py` (`serve_stdio`,
`_verb_tool`), `verbs.py` (`context`, `resolve_session`), `cli.py` (`context` routes,
`_should_via_replica`, the `telemetry` command, grep cardinality), `daemon._op_context`,
`context.LINKAGE_LABELS`, `stm.latest_session`, `stm.topic_composites`, `scan._stm_seed_ids`,
`hooks.py:313`, plus `git show d0273a5` (0.76.2) and `2cd73b9`. Live evidence came from READ-ONLY
parses of `.refmatrix/query.log`, `.refmatrix/cli.log`, `~/.refmatrix/query.log`, and the 89
project transcripts.

No `src/`, `tests/`, store, plan file, INDEX.md, IMPRESSIONS.md or last_run.log was touched. No
dev-venv `rmx` was run and no suite was run. One `grep -E` on a scratch file went through the
deployed `rmx grep` as every agent grep does; its row did not land in the project log.

rel: specifies -> [[plan-21-agent-context-usage]]
rel: related-to -> [[exploration-session-phased-context]]
rel: related-to -> [[plan-review-2026-10-07]]
rel: related-to -> [[bsd-plan16-spec-review-r4-33809ab]]
rel: contradicts -> [[claude#no-silent-failures]]

## Live evidence {#evidence}

### What reproduces {#ev-reproduces}

- **3 CLI context calls.** `query.log` has exactly 3 `kind=context` rows before the replay
  (2026-10-06 09:39 / 14:14 / 14:15, all `context-replica`, `invocation=unknown`).
- **~1,100 greps.** 1,119 `grep-replica` rows from 2026-09-23 to 2026-10-07T11:06 (837 `dropin`,
  21 `index`). The exploration's 1,107 / 825 / 21 match a cut a few minutes earlier.
- **MCP not logged.** `_op_context` (`daemon.py:4687`) and `verbs.context` (`verbs.py:538`) write no
  `query.log` row. `mcp.py` never sets `RMX_INVOCATION_SOURCE` (the only setters are `hooks.py:26`,
  `scheduler.py:133` and `ui/server.py`).
- **0 MCP `rmx_context` calls.** The transcripts have one `mcp__refmatrix__rmx_context`
  `tool_use` ever, outside the window.
- **Citations.** `LINKAGE_LABELS` is at `context.py:40`, the per-prompt recall hook at
  `hooks.py:313`, and `topic_composites` at `stm.py:790`. `09db9a6` and `2cd73b9` are on HEAD.

### What does not reproduce {#ev-not-reproduce}

- **The replay ran on the replica route.** All 20 replay rows (2026-10-07 11:06:35-11:07:13) are
  `source=context-replica`. That route builds the bundle with no `reranker=` argument, both at
  0.76.2 (`d0273a5`) and at HEAD (`cli.py:5099-5117`). `2cd73b9` fixed the DAEMON route's no-anchor
  hand-off.
- **No `-E` zero-cardinality defect in recent data.** None of the 115 October `grep-replica`
  rows with `|` in the pattern and `cardinality=0` has `outcome=ok`: every one is `empty`. 242
  October `ok` rows have cardinality > 0, and a live `-E` alternation row written by a concurrent
  agent at 2026-10-14T11:08:31 logged `cardinality: 15`. The only zero-cardinality `ok` rows are 14
  from 2026-09-06, all BRE `\|` patterns, outside the window. BRE `\|` now fails loudly.
- **The recall figure is double counted.** The exploration's "68 agent memory recalls" is 34
  `phase=start` intent rows plus 34 end rows in `cli.log`. The real count is 34.

### Pollution and session facts {#ev-pollution}

- **Test rows in the live global log.** `~/.refmatrix/query.log` holds 235 `alpha|beta` grep rows
  from 2026-10-01 to 10-07, in duplicated pairs at 40-50 ms. That is test-fixture shape, so
  the suite writes telemetry into the live global store. The instrument plan-21 builds is already
  contaminated by the suite (bug-088 family).
- **What an agent Bash call carries.** The env has `CLAUDECODE` and `CLAUDE_CODE_SESSION_ID`.
  `query.log` rows carry neither a session nor a query id.
- **How the STM session is chosen.** `stm.latest_session` (`stm.py:127`) picks the STM ring with the
  newest mtime. `verbs.resolve_session` and `scan._stm_seed_ids` use it when `RMX_SESSION` is
  unset. With concurrent sessions in one tree, which is the case today, they read another session's
  STM.

## Findings {#findings}

### BULLSHIT b-1: the ONE recall-event schema has no session and no join key {#b-1}

**File:** `task-21.1` R5, plan `#consolidations`.
**What:** The fields are `{ts, channel, invocation, query_id, id, rank, stage}`.

**Why it's bullshit:** Three declared consumers need a session, and the schema cannot give them one:
- **19.2 R3** defines a use as a name that "appears in a later focus note or STM ref **within the
  same session**".
- **21.3 AC-4** reports "context calls **per session** before/after over ≥ 3 sessions".
- **The phased-context comparison** scores read-back per session.

`query.log` rows have no session either, so 21.3 AC-4 cannot be computed at all. `query_id`
appears on events but not on the `query.log` row, so an event cannot be joined to its query. The
only session resolver available to MCP and to the CLI is `latest_session`, which picks the wrong
ring under concurrency.

**Evidence:** the record dict in `telemetry.log_query.__exit__` (no session/query_id). The
Bash env carries `CLAUDE_CODE_SESSION_ID`. Hook envelopes carry `session_id`.

**Fix:**
- Add `session` (hook envelope `session_id` → `CLAUDE_CODE_SESSION_ID` → `RMX_SESSION`; NEVER
  `latest_session`) and `query_id` to BOTH the `query.log` row and every event.
- Add an AC: two concurrent sessions in one tmp root log disjoint sessions.

**Pattern match:** YES. This is the shared-contract-built-for-one-consumer shape (C7 exists
because the counts would double).

### BULLSHIT b-2: the schema's identity field contradicts its own consumer {#b-2}

**What:** 21.1 says `id` is a "memory|entity id". 19.2 R1 says "**Keyed by name, not entity id**",
so that a purge-and-re-add keeps its history. 19.2 AC-5 lists "keyed by entity id" as a mutation
that MUST fail.

`channel` is undefined in 21.1. 19.2 R3's channel enum is
`session_start | prompt | precompact | cli | mcp`, which folds the `invocation` axis (`cli`/`mcp`)
into `channel`. `telemetry.py:393-402` keeps those two axes apart on purpose ("overloading the name
across the two logs would make every later join silently wrong").

**Why it's bullshit:** 19.2 has to consume the "ONE" schema, and as written that schema carries the
key 19.2 is forbidden to use. Whichever spec is implemented first decides the other's failure.

**Fix:**
- Events carry `name` (the stable key) and `entity_id` (for code), plus `kind`.
- Define `channel` as a closed enum of SURFACES (`session_start`, `prompt_recall`, `scan_prompt`,
  `precompact`, `context`, `recall`, `nudge`). `invocation` stays separate.
- Amend 19.2 R3 to match.

### BULLSHIT b-3: R5 has no production emitter, and its test passes on a fixture {#b-3}

**What:** R5 says "Every recall surface logs events". 21.1's files-to-modify lists none of the
surfaces that exist today: `scan.py` / scan-prompt, the per-prompt recall hook (`hooks.py:313`),
SessionStart recall, `context.py` / the context verb, and MCP recall. The only test is "a pack which
delivers 3 of 10". That pack is 19.1's, and 19.1 is not built. 21.1 "depends on nothing", so the
pack can only be a test fixture. No sink is named either: `query.log`? a new file? plan-23's
`BoundedQueue`, which 19.2 R4 routes events through?

**Why it's bullshit:** As specified, 21.1 can close with a schema module and an event writer whose
only caller is a test, which is dead on arrival by construction. The rule "No other recall log
format may be added" has no AC either.

**Fix:**
- R5 names each existing surface and the call site that emits `retrieved` and `delivered` there.
- R5 names the sink.
- Add an AC: one real `scan-prompt` and one real per-prompt recall run, through the CLI on a tmp
  store, write those events, and each surface's mutant (emitter removed) fails.
- 19.1's pack joins as a later emitter.

### SKETCHY s-1: "delivered" has two incompatible definitions {#s-1}

The definitions:
- **21.1:** "inside the payload the agent received (19.1's pack)".
- **19.2 R3:** "19.1's pack lines/bodies, NOT merely retrieved and then trimmed". This is
  producer-side.
- **19.5 R2:** "the whole output when under the limit, else its first 2 KB". This is consumer-side,
  after the hook-output cap.

The plan says "19.5 compares `retrieved` with `delivered`", but 19.5 R2 never mentions
`retrieved`. It counts names in recorded payloads. An emitter logging at write time cannot know
about the cap, so 19.2 would count hits that 19.5 says were never seen.

**Fix:** Each `delivered` event records `offset_bytes` and `bytes` inside the emitted payload, plus
`payload_bytes`, so seen-vs-emitted can be recomputed against the cap 19.5 R1 measures. Define
`delivered` = emitted, and derive `seen` = `offset_bytes + bytes ≤ cap`.

### SKETCHY s-2: the schema cannot compare fixed vs phased allocation without a second instrument {#s-2}

This was the user's ask (2026-10-14, `session-phased-context#placement`). At injection time 21.1
records no session (b-1), no prompt ordinal, no STM state, no overlap between the prompt and
`topic_composites`, no allocation arm or policy version, no payload position (s-1), and no
item kind. Its `used` stage ("fetched by name, or cited later") has no emitter and no definition
of "cited later". Read-back is exactly the score the exploration names (`#prereq-compare`).

Two code facts complicate the comparison further:
- **The baseline is not fixed.** `scan._stm_seed_ids` already seeds scan-prompt from STM
  (`RMX_SCAN_ENRICH_STM` defaults on).
- **It reads the wrong session.** `_stm_seed_ids` takes `latest_session`, which under concurrent
  sessions conditions on another session's focus (see the proposed bug row below).

The exploration's "fixed vs phased on the same sessions" cannot score read-back for the arm that
was not delivered. It needs a per-prompt arm that is logged (randomized or alternating).

**Fix:** Adopt [[#schema-recommendation]] in 21.1 R5 now. It costs a few fields per event, and
adding them after events start flowing makes the history incomparable.

### SKETCHY s-3: 21.1 AC-4 (reproduce the exploration's counts) cannot fail {#s-3}

`--days 14` is anchored on the run date. From 2026-10-14 it covers a different window than
2026-09-23..10-07. Inside the original window, a correct tool reports **23** context calls, not 3,
because the replay's own 20 rows are `context-replica` / `unknown` and nothing distinguishes them
from agent calls. The tolerance "to within rows written since" absorbs any number. The recall
figure the exploration quotes (68) is double counted (34).

**Fix:**
- Give `agent-usage` `--since/--until`.
- Freeze a copy of `query.log` and `cli.log` as a fixture with expected counts 3 / 1,119 / 34
  (stating the cut, `2026-10-07T11:06`).
- Make the expected figures exact.
- Exclude `phase=start` rows (`summarize_context` already does).

### SKETCHY s-4: R3 (`-E` cardinality) names a defect the October data does not show {#s-4}

See [[#ev-not-reproduce]]. The test strategy says AC-3 is "RED … (0 today)". Every `-E` row in the
recent data that logged 0 was a no-match, and today's live `-E` row logged 15. AC-3 most likely
passes at HEAD, which makes it a RED test that is not RED (`feedback_red_test_must_fail_at_head`).

The real cardinality gap in the data is `grep-stdin`: `cardinality: null` on all 3,521 rows in the
window.

**Fix:** Before committing R3, reproduce it on HEAD on a tmp store. If it does not reproduce, drop
R3 or re-scope it to the stdin rows, and correct the exploration's `#telemetry` bullet.

### SKETCHY s-5: the CLI daemon route stays unlogged, and R2's scope names a verb that does not exist {#s-5}

- **The CLI daemon route.** `rmx context` takes the daemon route when no replica reader exists
  (`cli.py:5136-5163`), and that route writes no `query.log` row; only the replica and direct
  routes log. R2 puts the row "caller side (verb/CLI)", and AC-1 tests MCP only. A row written in
  `verbs.context` never covers this route, because it does not call the verb.
- **`ann_search`.** R2 covers it "when called as verbs", but it has no verb (`cli.py:10718` calls
  the op directly).
- **"MCP tools".** R4 reports p50/p95 for "MCP tools", but only context/recall get rows. `rmx_query`,
  `rmx_search`, `rmx_where` and `rmx_memory` stay invisible.

**Fix:** Add one AC per route (MCP, CLI-replica, CLI-daemon, CLI-direct): each writes exactly one
row. Either name the tools R4 covers, or log at `_verb_tool` for all verbs.

### SKETCHY s-6: the agent's own calls stay `unknown`, and AC-2 enshrines it {#s-6}

Every agent `rmx context` / `rmx grep` from Bash runs without a tty and without a hint, so it logs
`unknown` (all 5,292 window rows except scan-prompt hooks). AC-2 makes "non-tty, no env →
`unknown`" the contract, and it already passes at HEAD. `agent-usage` therefore cannot separate the
agent from scripts, the replay harness (s-3), the eval harnesses, or tests.

**Fix:**
- When `CLAUDECODE` is set and no explicit source is given, log `agent`. An explicit
  `RMX_INVOCATION_SOURCE` still wins, so hooks stay `hook`.
- Harnesses (`eval/production/*`, the 21.2 replay, the 21.4 runner) set `internal`.
- Add `agent` to `INVOCATION_SOURCES`.

### SKETCHY s-7: tests and replays touch live sockets and live logs (bug-088) {#s-7}

**21.1 AC-1** spawns the real stdio server. That reaches the context op on a tmp-store daemon, and
`_maybe_rerank` can reach the hub's `models.sock` at `Path.home()/.refmatrix`. The conftest
recorder cannot see a subprocess's connects (bug-088's own caveat). The live global
`query.log` already carries 235 fixture rows ([[#ev-pollution]]), which are the very data
`agent-usage` will read.

Other gaps:
- **21.2 AC-1 and 21.3 AC-3** run "on a catalog copy" without saying how a live catalog is copied
  without opening `Store()` on it.
- **21.3 AC-1** runs "through the Bash hook path", which resolves `.refmatrix` by walking up from
  the cwd.

**Fix:**
- Subprocess tests get `HOME` = tmp (or an explicit socket-dir override), `REFMATRIX_ROOT` = tmp,
  and `RMX_HUB_MODELS=0`.
- Each test asserts that the live `query.log` / `cli.log` line counts are unchanged.
- Catalog copies come from the replica reader file, the documented read path.

### SKETCHY s-8: 21.4's causal story for the unreranked NL replay is wrong {#s-8}

21.4 `#why` and the plan's `#why` attribute the 0/1/5 NL result to "the no-anchor hand-off dropped
[the reranker] until `2cd73b9`". The replay rows are `context-replica`, a route that has never
been given a reranker ([[#ev-not-reproduce]]). Re-running the same CLI replay on the branch stays
unreranked. R2's two-route measurement is the right design, but the narrative invites re-running
the wrong command and reading the old number as "reranked"
(`feedback_causal_story_before_evidence`).

**Fix:** Correct both `#why` blocks and the exploration's `#replay` caveat. The NL replay ran on
the replica route, which never reranks. Only the daemon / MCP route reflects `2cd73b9`.

### SKETCHY s-9: the C9 harness cannot judge two of its three declared clients {#s-9}

21.4 R1's gold is "~30 questions with known **code** answers".
- **Plan-13** (dormant "re-scoped onto" this harness) asks whether reaching sessions + memory +
  code in one sweep changes the reachable set. A code-only gold can only penalize session
  inclusion, and R3's kind-aware prior (code before memory) is the opposite hypothesis.
- **ADR-0004's sentence co-location / bug-075** concern GMD section text, which code gold cannot
  score.

Two further gaps:
- **AC-3** keeps any change that "improves hit@5" with no margin. With n≈30, one question is
  3.3 points, so noise passes.
- **"Someone other than the person tuning"** is undefined in an agent workflow.

**Fix:**
- Either a mixed-kind gold (code / doc-section / memory / session strata, each reported
  separately), or narrow C9 and re-open plan-13's harness question.
- Pre-register a minimum win (e.g. ≥ 2 questions net on hit@5, and no stratum regresses).
- Name who builds and freezes the set (user decision).

### SKETCHY s-10: 21.4 AC-4 greps runtime artifacts instead of generator output {#s-10}

`.refmatrix/PRIMER.md` and `.refmatrix/CLAUDE.md` are gitignored runtime state (`.gitignore:18`),
written by the primer generator and by `hooks.py:1023`. A test that greps them checks whatever the
live tree last generated. It passes or fails on deploy state, not on the code.

**Fix:** Run the generators into a tmp dir and grep their output. Grep only committed surfaces
(CLAUDE.md, plan-16 files) in place.

### SKETCHY s-11: "tests" / TESTED BY is undefined, but the nudge gates on it {#s-11}

`src/` has no `tested_by` linkage (zero hits), and `LINKAGE_LABELS` has none. Yet the specs depend
on it:
- 21.2 R3 adds a "TESTED BY" label.
- 21.2 R5 lists "up to 5 tests".
- 21.2 AC-4 tests a "tested-by relation type".
- 21.3 R2 prints "m tests", and its noise gate is "≥ 1 caller or test".

Without a definition (callers whose path is under `tests/`? a `test_` prefix? an entity kind?), two
implementers produce different gates, and AC-4 cannot be written.

**Fix:** Define it in 21.2 R3, as a derived view over `called_by`/`calls` filtered by a named
predicate, and test it.

### SKETCHY s-12: 21.2 AC-1 (≥ 8 of 9) is scored by the implementer against an unfrozen set {#s-12}

The 9 identifiers are not listed in the spec. They are recoverable only from `query.log`
2026-10-07T11:06:35-11:06:52:

`_op_context`, `_apply_rerank_safe`, `installed_flags`, `shared_reranker`, `_drop_lance_for_purge`,
`session_launchctl_install`, `_MIN_RERANK_CHARS`, `_should_via_replica`,
`test_run_watcher_picks_up_new_file`.

"Hit" is undefined, and the baseline 4/4/1 classification per name is recorded nowhere.

**Fix:** Commit the 9 names with gold `path:line` before any change. Define a hit as "the first
DEFINED BY row equals gold `path:line`". Record the per-name baseline.

### SKETCHY s-13: the latency decision (d-3) was dropped silently, and 21.3's 300 ms may be infeasible {#s-13}

The exploration's d-3 (≤ 1 s vs ≤ 100 ms index-only) was never decided, and 21.2 has no latency
AC. 21.3 R3 sets a 300 ms deadline on a lookup whose measured replica cost for these same
identifiers is 330-949 ms (`latency_ms` of the replay rows). It does not say whether the 300 ms is
in-process time or hook wall time, which includes interpreter startup.

**Fix:** Decide d-3. Specify the nudge's lookup as an index-only query (defines + counts, no
`build_context`) with its own AC, and state which clock the 300 ms is measured on.

### MEH m-1: R1's "`mcp` joins `INVOCATION_SOURCES`" is already true {#m-1}

`telemetry.py:57` already lists `mcp`. Reword R1 to "the server sets it", and keep the AC-5
mutation.

### MEH m-2: `rmx telemetry agent-usage` does not parse against today's CLI {#m-2}

`telemetry` is a `@main.command` with flags (`cli.py:7509`), not a group. Either convert it to an
`invoke_without_command` group (keeping `--context` etc.) or use a flag. `--days` also diverges
from the existing `--since`.

### MEH m-3: `rmx hooks status` does not exist {#m-3}

21.3 R4 names `rmx hooks status`, and no `hooks` group exists. 21.3's files list omits `cli.py`.

### MEH m-4: the dependency and sink disagree with plan-of-plans {#m-4}

`plan-of-plans` row 21 lists a dependency on plan-23. The plan says 21.1 "depends on nothing".
19.2 R4 routes the same events through plan-23's queue. Name the sink, and the dependency follows
from it.

### MEH m-5: C11 (batch hook deploys) is not carried {#m-5}

21.3 regenerates hooks, and 21.4 regenerates `.refmatrix/CLAUDE.md` through install-hooks.
`plan-of-plans` names 21.3 in C11, but plan-21 says nothing about the batching.

### MEH m-6: 21.3's parser source does not fit both hooks {#m-6}

- **Undeclared dependency.** 21.3 R1 uses "16.1's argv parser", but 16.1 is not in the Depends
  line, which names 16.2 and 21.2.
- **The Grep tool has no argv.** The PostToolUse(Grep) envelope carries `pattern`.
- **The Bash command may be rewritten.** PostToolUse(Bash) may see the command after
  `grep-rewrite-guard` rewrote it (`rmx grep …`).

The parser contract should cover all three inputs.

### MEH m-7: d-4 (a habit memory) is undecided and unplanned {#m-7}

The exploration's d-4 asked whether a feedback memory should route identifier lookups to
`rmx_context`. It is neither decided nor dropped explicitly.

## Schema recommendation for phased context {#schema-recommendation}

The ONE event, written at the surface that emits it. Fields marked (P) exist for the fixed-vs-phased
comparison; the rest close b-1/b-2/s-1.

| field | meaning |
|---|---|
| `ts`, `session` | session from the envelope `session_id` / `CLAUDE_CODE_SESSION_ID` / `RMX_SESSION`, never `latest_session` |
| `turn` (P) | prompt ordinal within the session |
| `query_id` | shared with the `query.log` row of the same call |
| `channel` | surface enum (b-2); `invocation` stays a separate field |
| `name`, `entity_id`, `kind` | stable key (19.2), code id, and `code\|doc\|memory\|session\|subject` |
| `rank`, `stage` | `retrieved \| delivered \| used` |
| `offset_bytes`, `bytes`, `payload_bytes` | position inside the emitted payload, so "seen" is recomputable against any cap (s-1) |
| `arm`, `policy` (P) | `fixed \| phased`, plus the allocation policy version; the arm is chosen per prompt and logged |
| `stm_session`, `stm_events_n`, `focus_topics_n`, `overlap` (P) | the RAW phase inputs at injection: which ring was read, its size, the number of composite topics, and the prompt-term ∩ composite-member overlap |
| `phase` (P) | the label the pre-registered rule computes from those inputs (`cold\|warm\|shift`) |
| `used` events: `evidence`, `ref_query_id`, `lag_turns` (P) | what showed the use (`memory_get`, `context_by_name`, `file_read`, `cited_in_answer`, `focus_note`), which delivered event it points back to, and after how many turns; hook-originated refs are excluded so the helix confound cannot recur |

The raw phase inputs are what make one instrument enough. The threshold is still pre-registered,
but a rejected threshold can be re-scored from the same events without re-running sessions.

## Proposed bug row (to merge) {#proposed-bug}

**`stm.latest_session` picks the newest STM ring by mtime.** `scan._stm_seed_ids` and
`verbs.resolve_session` (when `RMX_SESSION` is unset, which covers MCP and the agent's Bash calls)
therefore condition on ANOTHER session's focus whenever two sessions share a tree.

- **Files:** `src/refmatrix/stm.py:127`, `src/refmatrix/scan.py:517`, `src/refmatrix/verbs.py:519`.
- **Fix direction:** prefer the envelope's `session_id` or `CLAUDE_CODE_SESSION_ID`, and use
  `latest_session` only as the last resort, saying so on the answer.

## Verdict {#verdict}

**NEEDS-REVISION** (23 findings: 3 BULLSHIT, 13 SKETCHY, 7 MEH)

The three BULLSHIT findings sit in the one artifact other plans import (21.1 R5). They must close
before 19.2 or 19.5 is specced against it. 21.2-21.4 are sound in direction; their findings are
about definitions, sandboxing and claims that do not reproduce.

rel: contradicts -> [[claude#no-mocks]]

## Ledger entries (to merge) {#ledger}

### INDEX.md line {#ledger-index}

```
| 3104a81 (plan-21 spec review r1, 21.1-21.4 + session-phased-context fold; HEAD 1bc9e24 at write; written 2026-10-14T11:13:22-0700) | 2026-10-14 | Todd Holley / Opus 5.5 / orchestrator | DIRTY | 23 (3B/13S/7M) | [[bsd-plan21-spec-review-3104a81]]. NEEDS-REVISION: C7 schema has no session/join key, contradicts 19.2's name key, no production emitter; replay was replica-route (never reranked); -E cardinality defect not reproduced; recall 68 = 34 double counted; phased-context fields proposed. |
```

### last_run.log line {#ledger-last-run}

```
2026-10-14T11:13:22-0700 commit=3104a81 verdict=DIRTY findings=23 (3B/13S/7M) report=2026-10-14-1113-plan21-spec-review-shared-schema-cannot-serve-its-consumers-3104a81.md
```

### Impressions {#ledger-impressions}

- 2026-10-14 (plan-21 r1): A SHARED SCHEMA IS SPECCED BY ITS FIRST CONSUMER. C7's "ONE"
  recall-event schema was written from 21.1's point of view. It has no session, although 19.2 and
  21.3 need one, and its `id` field is the key 19.2's mutation list forbids. Read every declared
  consumer's AC against the shared fields before approving a contract.
- 2026-10-14 (plan-21 r1): A NUMBER IN AN EXPLORATION IS A QUERY SOMEONE RAN ONCE. Re-run it. Here
  "3 context calls" held. "68 recalls" counted intent rows twice. "-E reads 0" did not reproduce in
  October. "Unreranked because of the hand-off" was a route the reranker never reached. An AC that
  says "reproduces the exploration's counts" inherits each of those errors.
- 2026-10-14 (plan-21 r1): THE SUITE ALREADY WRITES THE TELEMETRY THE NEXT PLAN WILL READ. There
  are 235 fixture grep rows in the live `~/.refmatrix/query.log`. A telemetry plan's first AC is
  that its tests do not write to the log it measures.
