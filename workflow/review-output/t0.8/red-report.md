---
gmd: "0.1"
id: t0-8-red-report
title: "T0.8 (bug-196) RED report"
tags: [red, tdd, plan-29, task-29.4, t0-8, bug-196, telemetry]
---

# T0.8 (bug-196) RED report {#root}

Branch `task-t0.8-bug196`, cut at `c4b44d0`, in `/Volumes/littlebig/refmatrix-t08`. One file changed
under `tests/`: `tests/test_task21_1_agent_usage_report.py` (+1 helper, +1 test). `src/` is
byte-identical to `c4b44d0` (`git diff c4b44d0 --stat` lists only the test file and logs).

rel: implements -> [[task-t0-suite-trust-sweep#t0-8]]
rel: derives-from -> [[bug_registry]] {bug: "bug-196"}

## Nodes and base E lines {#nodes}

Run: `workflow/review-output/t0.8/red-base.log`, file-only, at the branch tip (src = `c4b44d0`).
pytest exit 1; collected 34; 31 passed / 3 failed / 0 skipped; no SkipGate lines.

| Node | Role | Base E line (at `c4b44d0` src) |
|------|------|-------------------------------|
| `test_ac6_frozen_fixture_prints_the_exact_counts` | R8.1 RED record (R8.3, unedited) | `E assert []` at `:392` (`rec` has no line holding 34; report prints `cli.log: memory recall commands=244`) |
| `test_ac6_cli_log_recalls_are_split_per_channel` | R8.1 RED record (R8.3, unedited) | `E assert []` / `where [] = chan('prompt_recall', 5)` at `:434` |
| `test_t0_8_a_call_in_cli_log_and_query_log_is_counted_once` | **new**, R8.2 / AC-8.2 | `E assert []` / `where [] = chan('prompt_recall', 3)` at `:584` |

The two AC-6 E lines are the same as in `release-0.84.0-full.log` (`:392 AssertionError`
`assert []`; `:434` `chan('prompt_recall', 5)` `assert []`), compared by E line (R0.2).

### What the new node pins {#new-node}

Fixture (all in the AC-6 window, every end row with its phase=start row, bodies are
`sha256:` placeholders, no prompt text):

- pre-21.1, cli.log only: 2 prompt_recall, 2 session_start, 1 precompact, 1 recall;
- paired, the same call in cli.log AND as a `kind=recall` query.log row: 2 prompt_recall,
  1 session_start, 2 precompact, 3 recall (2 agent queries + 1 agent `--recent`);
- post-21.1, cli.log only: 1 prompt_recall (its query.log row never written).

Correct output: query.log leg prompt_recall 2 / session_start 1 / precompact 2 / recall 3 (base
behaviour, asserted unchanged for prompt_recall and recall); cli.log leg 3 / 2 / 1 / 1. Double
count (M8.2) puts 5 / 3 / 3 / 4 on the cli.log leg; each is asserted absent for its channel.
Lines holding `commands=` are excluded, so a kept `commands=<n>` header cannot satisfy or break it.

Two realism points the test encodes, both read from code at `c4b44d0`:

1. **No shared call id.** query.log rows carry `ts, cwd, root, session, query_id, invocation`
   + the three flags (`telemetry.log_query.__exit__`, `:598`-`:630`; flags from
   `cli._RecallCall.close_row`, `cli.py:13328`). cli.log end rows carry
   `ts, argv, cwd, pid, source` (`telemetry.log_cli_invocation`, `:379`). The only common
   fields are `cwd` (both `Path.cwd()`/`os.getcwd()`), invocation (`invocation` == `source`,
   both `invocation_source()`), the channel (flags vs argv flag names), and `ts`.
2. **`ts` can differ by a second.** `log_query` exits inside `main()`; `cli_entry` stamps the
   end row in its `finally` (`cli.py:15228`). One paired call has its cli.log end row at
   `+1s`. An exact-`ts` key double counts it.
3. **Pairing is per call.** The post-21.1 unpaired row means a cut-over rule ("drop cli.log
   after the first `kind=recall` row") fails.

The node does not pin the key itself; R0 picks it (R8.2). It forces the key to tolerate a 1s
`ts` offset and to leave an unpaired post-21.1 cli row counted.

## Feasibility and mutation-to-node map {#mutations}

A throwaway sketch of the cli.log leg (never committed; script at `/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/070141d0-80c6-4c13-95a2-56f192e2a1de/scratchpad/sketch.py`,
applied to `src/refmatrix/telemetry.py` and reverted with
`git checkout -- src/refmatrix/telemetry.py` in its own command after each run;
`__pycache__` cleared after the loop; `git status` clean after.

| Variant | Logs | Result | Failing nodes (E line) |
|---------|------|--------|------------------------|
| per-channel cli leg, pair by cwd + channel + invocation + `0 <= ts_cli - ts_q <= 1s`, one-shot consume | `sketch-good.log` | 34 passed | none (the spec is satisfiable as written) |
| same, exact `ts` | `sketch-exact.log` | 1 failed / 33 passed | new node (`chan('prompt_recall', 3)` `assert []`) |
| **M8.2**: per-channel, no dedupe | `sketch-m82.log` | 1 failed / 33 passed | new node (`chan('prompt_recall', 3)` `assert []`) |
| **M8.1**: every cli.log recall to one channel | `sketch-m81.log` | 3 failed / 31 passed | frozen fixture (`:392` `assert []`), split test (`:434` `chan('prompt_recall', 5)`), new node (`:584`) |

Map for GREEN's mutation table: M8.1 → `test_ac6_cli_log_recalls_are_split_per_channel` and
`test_ac6_frozen_fixture_prints_the_exact_counts` (AC-8.1); M8.2 →
`test_t0_8_a_call_in_cli_log_and_query_log_is_counted_once` (AC-8.2).

## Mock rows {#mocks}

None added. The new node patches nothing; it uses the file's existing autouse `_guard`
(env `delenv` + live-log snapshot) and the task 23.0 sandbox store. No dependency is patched.

## Stale citations reconciled at `c4b44d0` {#stale}

| Spec citation | At `c4b44d0` | Status |
|---------------|--------------|--------|
| `recall_channel` `telemetry.py:1313` (at `f45b9a3`) | `:1313` | holds |
| `agent_usage_report` `:1866` | `:1866`; the cli.log leg is `:1967`-`:1983` | holds |
| AC-8.1 breakdown 201 / 6 / 3 / 34 = 244 | recomputed from the committed fixture's cli.log with `recall_channel` over argv flag names + `source`: prompt_recall 201, recall 34, session_start 6, precompact 3 (sum 244; sources hook 210, unknown 34) | holds |
| Both AC-6 tests fail on the same E line in 0.84.0 | `:392` and `:434` E lines identical to `release-0.84.0-full.log` | holds |
| bug-196 row: fix = `recall_channel(..., invocation=source)` from argv flag names | flags survive in the fixture's argv; `source` is `hook`/`unknown` | holds |

## Not followable / for the lead {#lead}

1. **AC-8.1's 201 / 6 / 3 on the frozen fixture are asserted by no test.** The frozen-fixture
   test asserts 34 (and not 68) only; the synthetic split test covers the mechanism. R8.3 forbids
   editing the AC-6 tests and `#t0-8-files` allows only a new R8.2 test, so I added none. If the
   lead wants the four fixture figures pinned, that is a new node outside the file list.
2. **The new node pins format A** (the cli.log leg counts only calls absent from query.log; the
   query.log leg stays as is). A GREEN that prints a combined per-channel total
   (query.log + cli-only) instead would print prompt_recall 5 and fail on the absence check.
   I read R8.2 against the existing query.log leg (which already prints per-channel counts), so
   a combined line would show each paired call in two lines. If the lead reads R8.2 otherwise,
   the absence assertions need a ruling.
3. **R8.2 asks R0 to record the pairing key.** At `c4b44d0` no shared call id exists (see
   point 1 in [[#new-node]]). A key that needs a new writer field (e.g. `pid` on query.log
   rows) cannot pair historical rows and would need the fixture amended. That is a RED change,
   to be raised before GREEN builds it.
4. Logs force-added under `workflow/review-output/t0.8/` (the directory is gitignored).

## Ruling L130 addition {#l130}

The new node now opens with AC-8.1 on the frozen fixture: it copies `tests/fixtures/agent_usage/`
`query.log` + `cli.log` into the sandbox store and asserts one line per channel, 201
`prompt_recall`, 6 `session_start`, 3 `precompact`, 34 `recall`. The same `chan` matcher is used,
and `commands=` lines are excluded. Then the synthetic AC-8.2 store replaces both logs. The AC-6
tests are untouched (R8.3). Commit `099f90d`.

rel: amends -> [[#nodes]] {ruling: "L130"}

| Run (file only, `lockf`-wrapped) | Log | Exit | Collected | Result | New node's E line |
|------|-----|------|-----------|--------|-------------------|
| base (src = `c4b44d0`) | `red-base-l130.log` | 1 | 34 | 31 passed / 3 failed / 0 skipped | `:551` `assert chan(fx, "prompt_recall", 201)` → `E assert []` |
| sketch, tolerant key | `sketch-good-l130.log` | 0 | 34 | 34 passed | none |
| sketch M8.1 | `sketch-m81-l130.log` | 1 | 34 | 31 passed / 3 failed | `:551` (fixture block), plus AC-6 `:392`, `:434` |
| sketch M8.2 | `sketch-m82-l130.log` | 1 | 34 | 33 passed / 1 failed | `:601` `chan(out, "prompt_recall", 3)` → `E assert []` |

**Why it fails at base, and that this is the intended reason.** The base report over the fixture
prints the single total `cli.log: memory recall commands=244 excluded_test_rows=0 unparseable=0`
(in the node's failure output, `red-base-l130.log`). It prints no per-channel line, and the
fixture's query.log holds no `kind=recall` row, so no `outcomes:` or `memory_recall <channel>`
line exists either. The `commands=` line is excluded by the matcher, so `chan(fx,
"prompt_recall", 201)` is `[]`.

**What the fixture-first order costs.** At base the node now stops at the fixture block, so its
synthetic AC-8.2 assertions are not reached at base. Their base E line (`chan('prompt_recall', 3)`
`assert []`) is recorded by the previous tip `b490810` (`red-base.log`), and that part of the test
is unchanged. The M8.2 run shows the synthetic block still fails on its own when the fixture
block passes. Revised mutation map: M8.1 → both AC-6 nodes + the new node at `:551`; M8.2 → the
new node at `:601`.
