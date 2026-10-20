---
gmd: "0.1"
id: task-3.4-internal-cli-allowlist
title: "Task 3.4: every invocable CLI path is classified exactly once — verb twin, dispatcher action, internal, hidden alias, or a shrink-only legacy set"
tags: [task, plan-3, verbs, parity, cli]
metadata:
  node_type: task
  status: completed
  plan: plan-3-verbs-parity
  created: 2026-10-06
  rewritten: 2026-10-19
---

# Task 3.4: classify every invocable CLI path in the parity gate {#root}

> Plan: [[plan-3-verbs-parity]]
> Status: Approved (rewritten 2026-10-19 to the ch-bsd plan-3 r8 build list)
> Depends on: [[task-3.3-plan-3-verbs-parity]]

rel: part-of -> [[plan-3-verbs-parity]]
rel: implements -> [[deferral_registry]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r8-d4bf001#t34-build]]
rel: derives-from -> [[bsd-plan3-verbs-parity-r8-d4bf001#s-4]]

## Why {#why}

On 2026-10-06 the user accepted CLI-only commands for internal and test-harness surfaces: "I'm
okay with internal harness/testing cli only commands" (`deferral_registry.md` line 47).
`tests/test_verb_parity.py` checks verb → CLI pairing and nothing checks the reverse, so a new
agent-facing click command with no verb is indistinguishable from an accepted internal one. {#why-lead}

The first version of this spec (2026-10-06) did not match the surface it gates. ch-bsd plan-3 r8
#s-4 walked the click tree at `d4bf001` and found **195 invocable paths** (193 leaves plus the
`invoke_without_command` groups `learn` and `queue`) and six defects in the old three-way split:
no slot for dispatcher-action twins; seven memory WRITE commands that build their own daemon
payloads instead of calling `verbs.memory`; `derive unstamp` and bare `rmx learn` unseeded; six
hidden aliases unaddressed; a copy instruction that mutates the real tree; and a 140-path
"handful" with no rule against growth. This rewrite is r8's `#t34-build` list. {#why-r8}

## Decisions (orchestrator, 2026-10-19) {#decisions}

- **The seven memory writes are ROUTED, not excepted.** `memory forget`, `reclassify`, `retag`,
  `link`, `score`, `bulk-forget` and `dedup` call `verbs.memory(action=…)`, as `list`, `search`,
  `promote` and `brief` already do. CLAUDE.md: "CLI and MCP expose it, never implement it". {#d-route}
- **Five classes, exactly one each.** CLI_MAP twin / `CLI_ACTIONS` / `INTERNAL_CLI` /
  `HIDDEN_ALIASES` / `LEGACY_UNPAIRED`. {#d-five}
- **LEGACY_UNPAIRED is pinned at 140 and may only shrink.** The test carries a frozen baseline. {#d-pin}

## Requirements {#requirements}

### R1 — `verbs.INTERNAL_CLI` {#r1-internal}

`INTERNAL_CLI: dict[tuple[str, ...], str]`, keyed by click path tuples (the shape of `CLI_MAP`
values), next to `CLI_MAP` and `MCP_ONLY`. Exactly these eight keys:

`("derive","log")`, `("derive","diff")`, `("derive","status")`, `("derive","unstamp")`,
`("learn",)` (the bare invocation), `("learn","on")`, `("learn","off")`, `("learn","status")`.

Each reason quotes the user's words from the deferral row: "internal harness/testing cli only
commands". **`grep-learn` is NOT seeded** — it does not exist and hygiene (R6) would fail; task
16.1 adds it when it lands.

### R2 — `verbs.CLI_ACTIONS` {#r2-actions}

`CLI_ACTIONS: dict[tuple[str, ...], tuple[str, str]]` — click path → (dispatcher verb, action).
Exactly these 15:

| path | verb | action |
|------|------|--------|
| `memory list` / `search` / `promote` / `brief` | `rmx_memory` | `list` / `search` / `promote` / `brief` |
| `memory forget` / `reclassify` / `retag` / `link` / `score` | `rmx_memory` | same name |
| `memory bulk-forget` | `rmx_memory` | `bulk_forget` |
| `memory dedup` | `rmx_memory` | `dedup` |
| `task push` / `pop` / `current` / `swap` | `rmx_task` | same name |

Every action is a member of its verb's `action` `Literal`. Wiring class for all 15 is `calls`.
The verb's own `CLI_MAP` twin (`memory get`, `task list`) is NOT repeated here.

### R3 — the seven memory writes call the verb {#r3-route}

`memory forget`, `reclassify`, `retag`, `link`, `score`, `bulk-forget`, `dedup` call
`verbs.memory(root, action=<x>, partition=_resolve_partition(), …)` with the command's options
as the verb's own parameter names (`retag --set` → `replace`, `link SRC` → `id`/`name`,
`bulk-forget --id/--name/--mtype` → `ids`/`names`/`mtypes`). They no longer call
`_memory_daemon_call` or `daemon_mod.ping` for the op. Behaviour that must survive:

- **Preview then write.** `reclassify` and `bulk-forget` keep their dry-run preview + confirm;
  both calls go through the verb (`dry_run=True`, then `dry_run=False`).
- **`bulk-forget`'s 600 s write.** The real delete passes `timeout=600.0`; `verbs.memory` must
  honour an explicit `timeout` on WRITE actions (today it is ignored outside the read budget;
  the 120 s default stays when none is given).
- **Absent vs busy (Q11).** Only `VerbAbsentError` may fall back to the in-process store, as the
  commands do today when no daemon is up; `VerbBusyError` is a ClickException.
- **Rendering** reads the verb's result (`forgotten`, `changed`, `tags`, `src_id`/`concept_id`,
  `signal`/`concept_ids`/`components`, `folded`/`edges_migrated`), including
  `_say_vector_delete_failures`.

### R4 — `verbs.HIDDEN_ALIASES` {#r4-hidden}

`HIDDEN_ALIASES: dict[tuple, tuple]` for the six `_alias` copies: `add-concept` → `add concept`,
`add-entity` → `add entity`, `add-linkage-type` → `add linkage-type`, `list-entities` →
`list entities`, `list-linkages` → `list linkages`, `list-queries` → `list queries`. A key is a
hidden command, its value is a visible command with the SAME callback, and the target's own
classification applies. "Skip hidden" is not a rule: task 16.1's `grep-learn` will be hidden and
belongs in `INTERNAL_CLI`.

### R5 — `verbs.LEGACY_UNPAIRED` {#r5-legacy}

`LEGACY_UNPAIRED: dict[tuple, tuple[str, str]]` — path → (category, reason) for the remaining
**140** paths. `verbs.LEGACY_CATEGORIES` is the closed set of categories:

| category | meaning |
|----------|---------|
| `verb-it` | agent-facing; owes a verb (the decision is "verb it") |
| `operator` | daemon / hub / launchctl / replica / partition / schedule administration |
| `maintenance` | store maintenance, repair, migration, derive passes |
| `hook` | invoked by a generated Claude Code hook, not by an agent |
| `harness` | test, eval, telemetry or debug harness |

Grouping by family is fine (one reason string per family). The implementation summary carries
the decision table (path → category). The set can only SHRINK: the test pins it to a frozen
140-path baseline (subset AND `len <= 140`). Moving a path out (a new verb, or `INTERNAL_CLI`)
is allowed; adding one is a test failure.

### R6 — the reverse walk and hygiene in `tests/test_verb_parity.py` {#r6-walk}

- The walk takes the group as a PARAMETER and yields every invocable path: each leaf and each
  `invoke_without_command` group; hidden commands included.
- Every path is in **exactly one** of the five classes. A path in none fails with
  `rmx <path>` and both remedies (a verb + `CLI_MAP` twin, or `INTERNAL_CLI` with a reason); a
  path in two fails naming both classes.
- A key in any of the five maps that does not resolve to an invocable path fails, naming the map
  and the key.

## Acceptance criteria {#acceptance}

1. **AC-1 (new command fails, on a real copy).** `g = copy.copy(cli.main); g.commands =
   dict(cli.main.commands); g.add_command(click.Command("zz-probe"))`; walking `g` reports
   `rmx zz-probe` with both remedies, and afterwards `"zz-probe" not in cli.main.commands`. {#ac-1}
2. **AC-2.** `monkeypatch.delitem(verbs.INTERNAL_CLI, ("derive", "log"))` → the walk reports
   `rmx derive log`. `INTERNAL_CLI` is exactly the eight R1 keys, each reason quoting the user. {#ac-2}
3. **AC-3 (hygiene).** A stale key in any of `CLI_MAP`, `CLI_ACTIONS`, `INTERNAL_CLI`,
   `HIDDEN_ALIASES`, `LEGACY_UNPAIRED` (and a stale `HIDDEN_ALIASES` target) fails. {#ac-3}
4. **AC-4 (exactly one).** Every invocable path of `cli.main` is in exactly one class; listing a
   path twice fails naming both. {#ac-4}
5. **AC-5 (CLI_ACTIONS).** Exactly the 15 R2 entries; each action is in its verb's `Literal`. {#ac-5}
6. **AC-6 (wiring).** For each of the 15, the recorder pattern of `test_cli_twin_calls_its_verb`
   (CliRunner + `sig.bind` against the real verb signature) proves `action=<x>` and the argv's
   options reach the verb, and the CLI renders the verb's canned result (canary). The seven
   writes are RED at HEAD (they reach `daemon.call`). `bulk-forget`'s write carries
   `timeout=600.0`. {#ac-6}
7. **AC-7 (hidden).** `HIDDEN_ALIASES` is the six R4 pairs; each key is hidden, each target
   visible with the same callback. {#ac-7}
8. **AC-8 (legacy shrink-only).** Every `LEGACY_UNPAIRED` value is `(category, reason)` with a
   category in `LEGACY_CATEGORIES` and a non-empty reason; the key set is a subset of the frozen
   140-path baseline and `len <= 140`. {#ac-8}
9. **AC-9 (docs).** Plan-3 Task Breakdown lists 3.4 with `rel: specifies`; deferral row 47 →
   resolved on completion; implementation summary at
   `workflow/implementation_summaries/task-3.4-internal-cli-allowlist.md` with the LEGACY
   decision table. {#ac-9}
10. **AC-10.** Every pre-existing test in `tests/test_verb_parity.py`, `tests/test_mcp_parity.py`
    and the memory/task CLI tests stays green. {#ac-10}

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/verbs.py` | `INTERNAL_CLI`, `CLI_ACTIONS`, `HIDDEN_ALIASES`, `LEGACY_UNPAIRED`, `LEGACY_CATEGORIES`; write actions honour an explicit `timeout` |
| `src/refmatrix/cli.py` | the seven memory writes call `verbs.memory` |
| `tests/test_verb_parity.py` | reverse walk, hygiene, exactly-one, shrink-only baseline, CLI_ACTIONS wiring (written RED by the test engineer) |
| `workflow/deferral_registry.md` | row 47 → resolved on completion |
| `workflow/implementation_summaries/task-3.4-internal-cli-allowlist.md` | summary + LEGACY decision table |

## Test strategy {#test-strategy}

RED tests are in `tests/test_verb_parity.py` (section "task 3.4"). The recorder doubles extend
the registered `verbs.<fn>` recorder row in `workflow/test_mock_registry.md`. RED run:
`workflow/review-output/task3.4-3.5-red.log`.

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the summary (drop one
  `CLI_ACTIONS` key; route one write back to `_memory_daemon_call`; add a LEGACY key).
- `@ch-bsd` over the task's range finds no unaddressed BULLSHIT.
