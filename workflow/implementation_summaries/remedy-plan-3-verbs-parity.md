---
gmd: "0.1"
id: impl-remedy-plan-3-verbs-parity
title: "Plan-3 remediation after ch-bsd plan-3 r1 (8ba4799): wiring proven, defaults compared, verbs tested for real"
tags: [implementation-summary, plan-3, remediation]
metadata:
  node_type: implementation-summary
  plan: plan-3-verbs-parity
---

# Plan-3 remediation (round 1) {#root}

rel: implements -> [[plan-3-verbs-parity]]
rel: evidence-for -> [[bsd-plan3-verbs-parity-8ba4799]]

| Finding | Fix |
|---------|-----|
| #bs-1 "calls it" was an existence check | `verbs.CLI_WIRING` (`calls` / `payload`); 23 click twins now call `verbs.<fn>` (focus context/note/change-subject, task ×5, hub queues (new), bus ×10, locate, ingest-status, memory add/get, save-state, recall-state, projects); `context`/`query`/`ingest` build payloads via `payload_context`/`payload_query`/`payload_ingest`; `test_cli_twin_calls_its_verb` records the call while the command runs — see [[plan-3-verbs-parity#decisions-log]] Q4 |
| #bs-2 parity excluded every recall param | verb `k=10`, `query=None`; PAIRING covers all 26 twins; `SHAPE_DIFFERENCES` must justify any same-named exclusion (`test_no_twin_exclusions_are_honest` caught `rmx_context.linkage` on first run) — Q5 |
| #bs-3 no tests for 18 migrated verbs | `tests/test_verbs_migrated.py`: real spawned daemon (task, memory get/list/search/retag/forget, recall_state with memory_dir, ingest_status list+poll, where, search, locate), real `Bus` over the real hub socket (`_MiniHub`) for all 10 bus verbs — Q9 |
| #sk-4 second "which rows" in cli.py | `verbs.recent_rows` shared by verb + CLI fallback; `payload_memory_recall` + `annotate_hit` on the dense path; `ann_similarity`/`display_score` single-sourced; CLI daemon-down widen test — Q7 |
| #sk-5 CLI --recent vs tool rows | named `include_session=True` for non-hook modes, `False` for hook modes; `--exclude-mtype` wins; in PAIRING — Q6 |
| #sk-6 fakes unregistered; bus untested for real | registry rows for `fakermx`, `hub.rpc` fake, `_MiniHub`, `discovery.discover_roots` pin, the wiring recorder; graduation-log entry; real bus round-trip test |
| #sk-7 silent swallows | `warnings` in the recall result; global failure → warning (`both`) / fatal (`global`); `context_error` per row; CLI prints warnings on stderr; `memory_partition` logs — Q8 |
| #meh-8 `memory(action=recall)` narrowed; get/forget with no key | `_RECALL_FORWARD` forwards since/since_seconds/recent/exclude_mtype/include_session/subject/kinds/fuse/degree; `keyed()` raises `VerbArgsError` |
| #meh-9 schemas undocumented; dead `session` prop; alias precedence | `@verb(descriptions=…)` (`_RECALL_DESCRIPTIONS`); `_TRANSPORT_PROPS` = root/project with descriptions (`session` only where declared); `Verb.run` canonical-first |
| #meh-10 dead `mode_hint`, redundant ping | deleted (`test_dense_path_pings_once`) |
| #meh-11 registry deferral pointed at plan 3 | re-pointed to task 5.3 |

Also: `verbs.resolve_session` honours `$RMX_SESSION` and is the CLI's `prefer_latest` resolver (reads and writes land in the same ring); `verbs.save_state` gained `memory_dir`/`lint`/`sync` + `subject` in the result; `verbs.memory_add` gained `metadata`/`to_global`; `verbs.recall_state` gained `memory_dir`; `verbs.bus_history` gained `status`; `_bus_sender` falls back to the hostname outside a store; `rmx bus channels --glob`; `rmx hub queues`.

## Found by the real tests {#found}

bug-007 ([[bug-registry#registry]]): `search.cached_replica` kept a read-only connection bound to the OLD `catalog.read.duckdb` inode after the daemon's tmp+rename snapshot — a long-lived `rmx mcp` / hub served stale where/locate until restart. Fixed: `_snapshot_sig` recorded at open, reopen on change.

## TDD {#tdd}

RED `workflow/review-output/pytest-plan3-r1-red.log`: 51 failed / 12 passed (test_verb_parity 26 wiring + pairing, test_verbs_migrated 13, test_plan3_remedy 12). GREEN `pytest-plan3-r1-green.log`: 63 passed. Full suite `pytest-plan3-r1-full.log`: 25 failed / 1500 passed — 12 of the 25 were regressions from this remedy and were fixed before merge (10 JSON-mode CLI tests now read `result.stdout` because the daemon-down note is on stderr in every mode; the MCP routing test accepts the annotated row; `_bus_sender` keys on the project dir), the remaining 13 are the untracked plan-4 RED files (12) and the pre-existing `test_graph_landing` red (plan 6.4). Affected suites re-run: 203 passed.

Mutation checks (each on a scratch edit, reverted):
- remove the `_verbs.bus_pub(...)` call from `rmx bus pub` (restore the direct `hub_mod.rpc`) → `test_cli_twin_calls_its_verb[rmx_bus_pub]` FAILS ("never called verbs.bus_pub");
- set the verb's `k` back to 8 → `test_click_defaults_match_verb_defaults` FAILS;
- drop `("rmx_context", "linkage")` from `SHAPE_DIFFERENCES` → `test_no_twin_exclusions_are_honest` FAILS (observed live during the round);
- revert `_snapshot_sig` in `cached_replica` → `test_locate_verb_finds_an_ingested_file_by_basename` FAILS (observed live: `{'results': []}`);
- `global_recall_rows` swallowing again (`return []`) → `test_global_failure_surfaces_as_a_warning` FAILS.

All three recorded in `workflow/review-output/pytest-plan3-r1-mutations.log`. Mutation 3 leaked one message onto the LIVE bus (the test only patched `is_running`), deleted afterwards; the wiring fixture now fails closed (`hub.rpc`/`global_call`/`daemon.call` raise), so a bypassing twin can never reach a live service from the gate.

## Round 2 (bsd-plan3-r2, 209270d) {#round-2}

rel: evidence-for -> [[bsd-plan3-verbs-parity-r2-209270d]]

| Finding | Fix |
|---------|-----|
| #b-1 hub boundary swallowed `ok:false`; `bus pub` regressed to a KeyError; timeouts were tracebacks | `_hub_rpc` raises a typed `VerbError` with the hub's own error on `ok:false`, wraps `TimeoutError`/`OSError`; `queues` goes through it; tests on a real socket (`_QueuesHub`) + a recorded refusal at the CLI — Q10 |
| #b-2 busy called "not running"; twins string-matched | `VerbBusyError` / `VerbAbsentError` + `verbs.require_daemon` (`discovery.daemon_status`); `_call`, `memory`, `change_subject` use it; a socket timeout on an op is busy; CLI twins (`ingest-status`, `memory add/get`, `memory recall` fallback) and `mcp._t_memory_add` dispatch on the type — the in-process bootstrap fires on ABSENT only (asserted: no catalog file appears on a busy daemon); `federated_where`/`locate` carry `skipped: [{project, root, reason}]` — Q11 |
| #s-3 gate proved the call only | `test_cli_twin_calls_its_verb` binds the real signature, compares expected kwargs from option-carrying argv, and requires a canary from the canned result in the output; `rmx_focus` returns `dialogue`/`milestones`/`last_line`/`events_total` and `focus context` renders them — Q12 |
| #s-4 records | full suite re-recorded at the merge sha (`pytest-plan3-r2-full.log`); the two unlogged r1 mutations logged (`pytest-plan3-r1-mutations-2.log`: bug-007 revert fails `test_locate_verb_finds_an_ingested_file_by_basename`; the linkage shape row removed fails `test_no_twin_exclusions_are_honest`) |
| #m-5 | vacuous `ingest_status` assertion fixed; `queues` positive path on a real socket |

TDD: RED `workflow/review-output/pytest-plan3-r2-red.log` (7 failed / 1 passed), GREEN `pytest-plan3-r2-green.log` (177 passed across parity, remedy, migrated, MCP, subject, recall, locate, plan-1/2 suites). Mutations `pytest-plan3-r2-mutations.log`: (A) `_hub_rpc` swallowing `ok:false` again fails both hub-boundary tests; (B) classifying busy as absent again fails the typed-error test and the bootstrap-fallback test.

## Round 3 (bsd-plan3-r3, 76929a2) {#round-3}

rel: evidence-for -> [[bsd-plan3-verbs-parity-r3-76929a2]]

| Finding | Fix |
|---------|-----|
| #b-1 `_promote_digest` opened the slot under a busy daemon | classifies through `verbs.require_daemon`; busy → `{"error": "VerbBusyError: daemon busy pid=…"}` (no catalog file appears — asserted on a real silent socket, through `verbs.save_state` too) — Q13 |
| #b-2 `rmx locate` dropped `skipped`; `federated_query`/`concept` had none | one `_live_roots()` for all four fan-outs; `locate` prints each skipped store on stderr and "no matches (N stores skipped)"; `verbs.search` carries `skipped` — Q14 |
| #s-3 bare pings in `memory_partition` / `attach_context` | both classify (busy raises / is named; absent keeps the bootstrap default) |
| #s-4 socket-timeout-is-busy untested; promote bypassed the wrappers | `test_socket_timeout_on_an_op_is_busy` on a `_PingOnlyDaemon`; `_call` treats any transport exception as busy; promote's `memory_get` goes through `_call` and the hub write is wrapped into a typed VerbError |
| #m-5 reads refused on busy | `memory get` / interactive `memory recall` fall through to `_read_store()` with `# rmx: daemon busy …; reading the replica` on stderr (hook modes degrade to empty instead) — Q13 |
| observation: `hub queues` rendered busy as down | `_gather_queues` carries `daemon_busy` + `identity: unknown`; the CLI renders `busy` |

TDD: RED `workflow/review-output/pytest-plan3-r3-red.log` (9 failed / 1 passed), GREEN `pytest-plan3-r3-green.log` (10 passed) + `pytest-plan3-r3-green-suites.log` (surrounding suites). Mutations `pytest-plan3-r3-mutations.log`: (A) a bare ping in `_promote_digest` fails the promote test; (B) dropping the skipped print fails the locate test.

