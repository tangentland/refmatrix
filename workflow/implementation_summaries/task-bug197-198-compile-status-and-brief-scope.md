---
gmd: "0.1"
id: impl-task-bug197-198-compile-status-and-brief-scope
title: "bug-197/198 GREEN: an unknown compile scope is one scope record; brief takes its own compile_scope"
tags: [implementation-summary, bug-197, bug-198, memory, compile, derive, brief, verbs, plan-26]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-11-10
---

# bug-197/198 GREEN: unknown compile scope, brief compile_scope {#root}

rel: derives-from -> [[bsd-task-26.6-r2-remedy-315fdc9#m-1-r2]]
rel: derives-from -> [[bsd-task-26.6-r2-remedy-315fdc9#m-2-r2]]
rel: implements -> [[bug_registry#registry]]

RED `09ca9e7` (24 failing), GREEN `8c296c9`. Only `src/refmatrix/store.py`, `cli.py` and
`verbs.py` changed. No tests were written in this step. The contracts are the bug-197 and bug-198
rows in `workflow/bug_registry.md` and the RED files `tests/test_bug197_unknown_compile_scope.py`,
`tests/test_bug198_brief_compile_scope.py`, and the `memory brief` row of `tests/test_verb_parity.py`.

## bug-197: an unknown compile scope {#bug-197}

- **`Store._memory_compile_status(self, side_rows: list) -> dict`** no longer raises on a compiled
  subject whose `compiled_scope` this rmx does not know. It counts those rows by name and adds
  `scopes[<name>] = {"unknown": True, "needs_compile": True, "compiled_subjects": n}`. The partition
  verdict, the top-level memory-scope fields, and every known scope's record stay as they were.
  Before the fix, the raise inside `derive_status` took down the whole partition verdict: ping
  health, `rmx daemon status`, the `derive_status` op, and `rmx derive status`. {#store}
- **`render_memory_compile_warning(status, *, partition=None) -> str`** prints
  `memory-compile: scope <name>: unknown to this rmx[ (partition p)]; N compiled subject(s) carry
  it — run the rmx that wrote them, or recompile` for an unknown record. It suggests no
  `--scope <name>` command, because this rmx cannot run that scope. {#renderer}
- **`rmx daemon status`** now prints `derive: error — <message>  [UNVERIFIED]` when the
  `derive_status` op replies `ok: false`. Before, an error reply fell through to an empty result
  and nothing was printed. The bug-197 RED author found this; it breaks the no-silent-failures
  rule. {#daemon-status}

## bug-198: brief's compile scope {#bug-198}

- **`verbs.memory(..., compile_scope: Literal["memory", "pattern"] | None = None, ...)`** is the
  brief action's compile scope. `_memory_payload("brief", a)` sends it to the unchanged
  `memory_brief` op under the wire key `scope`. Recall's `scope` is no longer forwarded on brief.
  {#verb}
- **Fail-closed before any daemon call.** If `action == "brief"` and `compile_scope` is not in
  `consolidate.SCOPES`, the verb raises `VerbArgsError` naming `compile_scope`. The check runs
  before `memory_partition` and `require_daemon`. It sits in the verb body because `Verb.run` (the
  MCP path) does not enforce the `Literal`. {#validate}
- **Schema.** The `rmx_memory` verb now has `descriptions=_MEMORY_DESCRIPTIONS`. `scope` is
  described as recall-only (project | global | both). `compile_scope` is described as brief-only
  (memory | pattern), and the text says what each corpus holds. {#schema}
- **CLI.** `rmx memory brief --scope` has dest `compile_scope`,
  `type=Choice(consolidate.SCOPES)`, and defaults to `consolidate.DEFAULT_SCOPE`. It goes to the
  verb as `compile_scope`, and `--compile` plans that same scope. `cli.py` imports `consolidate`
  at module level as `_consolidate_mod` for the decorator. `brief` already loads it, so this adds
  no startup cost. {#cli}

## Verification {#verification}

- RED files + parity: 189 passed (`workflow/review-output/bug197-198-green.log`). {#v-red}
- Wider set (RED files, `test_memory*`, `test_derive*`, `test_brief*`, `test_verb_parity`,
  `test_docs_generated`, `test_mcp_tools`): 710 passed, 1 failed
  (`workflow/review-output/bug197-198-green-wide.log`). The one failure is
  `test_brief_real_daemon.py::test_an_unknown_class_fails_loudly_through_the_daemon`, with DuckDB
  `Could not set lock`. That is open bug-127. The same error happens with the RED head's `src`
  checked out (`bug197-198-green-bug127-at-red-head.log`). `tests/test_daemon_status*.py` does not
  exist. The CLI tree doc lists commands only, so it did not need regenerating. {#v-wide}
- Mutations: each was applied, its tests run, and the code restored in a separate command, with
  the restore checked by grep. {#v-mut}

| # | Mutation | Killed by | Log |
|---|----------|-----------|-----|
| 1 | unknown scope raises again (`store.py`) | 8 of 9 bug-197 tests | `bug197-198-green-mut1.log` |
| 2 | recall `scope` leaks into the brief op (`verbs.py`) | `test_recalls_scope_never_becomes_the_brief_compile_scope` | `bug197-198-green-mut2.log` |
| 3 | CLI `--scope` ignored (`cli.py`) | 2 bug-198 CLI tests + parity `memory-brief` | `bug197-198-green-mut3.log` |
| 4 | compile_scope validation dropped (`verbs.py`) | 4 invalid-value tests (verb + `Verb.run`) | `bug197-198-green-mut4.log` |

## Gaps flagged {#gaps}

- **No test covers the `derive: error — <message>` line in `rmx daemon status`.** Removing it
  would not fail any test. This goes to `ch-test-engineer`; no test was written here. {#gap-derive-error}
- **bug-127** is still open. The test opens `Store(root)` directly at
  `tests/test_brief_real_daemon.py:145` while its daemon holds the writer, which is one likely
  second opener. {#gap-bug127}
- `compile_scope` sent with a non-brief action is ignored, in the same way as the other
  per-action params. Nothing in the contract asked for that to be refused. {#gap-non-brief}
