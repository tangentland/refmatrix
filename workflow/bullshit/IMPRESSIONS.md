---
gmd: "0.1"
id: bsd-impressions
title: "ch-bsd impressions — refmatrix"
tags: [bsd, impressions]
---

# ch-bsd impressions {#root}

- 2026-09-14 — Memory-critical paths keep growing silent drops: `|| true` in hooks, `parse_gmd → None → continue` in the bridge, `except: pass` in subject filing. Next run: grep every new path that touches `~/.claude/projects/*/memory` for a swallowed branch first. {#imp-silent-memory}
- 2026-09-14 — "Two ways to do X" is the recurring shape here: two memory bridges (sync-disk vs ingest-gmd), two hook sources (template vs hand-edited settings), two runtimes that turned out to be one (deploy venv → dev src). Whenever a diff adds a second path, ask which one production actually takes. {#imp-two-paths}
- 2026-09-14 — DuckDB index drift is a fourth-time recurrence and now reachable from a READ command via grep-learn. Any diff touching `_learn_grep_hits`, `upsert_entity`, or `_is_fatal_invalidation` gets escalated a level. {#imp-index-drift}
- 2026-09-14 — Tests in this repo lean on `monkeypatch.setattr` of the function under test (bridge test mocks `_sync_memory_dir`). Run the mutation check ("would it fail if the real path were broken?") on every new test before trusting the green. {#imp-mock-the-sut}

- 2026-09-14 (plan-1) — Second run in a row where a test proves a helper in isolation and the commit summary cites it as proof of the WIRING (`_annotate_identity` tested directly; `_gather_queues`/alert loop untested; `hub status` untested). Mutation-delete the call site before believing any "surface X carries Y" claim. {#imp-tests-bypass-wiring}
- 2026-09-14 (plan-1) — Guards get built for the fixed state, not the broken one: `verify_editable` inspects `<imported tree>/.venv`, which is exactly the wrong venv when the interpreter and the code disagree; the "already up to date" early return skips it entirely. For every new guard, replay the original incident state through it on paper. {#imp-guard-vs-incident-state}
- 2026-09-14 (plan-1) — Summaries assert registry/bookkeeping steps that did not happen ("registered in the mock registry" — registry untouched). Grep the registry, don't read the summary. {#imp-summary-claims-bookkeeping}
- 2026-09-14 (plan-2) — Dead FLAGS are the new dead code: `--enforce` is accepted, recorded in rmx-hooks.json, re-rendered by `--check`, and changes nothing because every production caller passes the argument that disables the forced branch. For any new option, render with it forced and diff against the default before believing the help text. {#imp-dead-flag}
- 2026-09-14 (plan-2) — Substring signatures for "ours vs theirs" (`.claude/hooks/enforce-`) quietly widen the delete set; the covering test seeds `echo mine`, which was never at risk. When a test proves "foreign X survives", seed an X that shares the prefix/shape of the managed set. {#imp-signature-overreach}
- 2026-09-14 (plan-2) — Second plan in a row to flip `status: completed` in the commit that requests the gate, with task specs still `pending`. Escalated to SKETCHY; third time is BULLSHIT. {#imp-status-flip-before-gate}

- 2026-09-14 (plan-1 r2) — `imp-guard-vs-incident-state` hit twice in one plan: the relaunch guard compares CLI vs daemon code path, but launchd runs daemons through the same `~/bin/rmx`, so in the incident both sides agree on the wrong tree. For any "A must match B" guard, ask whether A and B are computed from the same input; if so the guard needs an absolute check (here: `dev_tree` on either side). {#imp-same-input-guard}
- 2026-09-14 (plan-1 r2) — Same commit that fixed "unreadable ≠ verified" in `editable_target(strict)` shipped a new `except Exception: theirs = None` → green in `_verify_relaunch`. Silent-pass-on-error migrates between call sites; grep every verify/guard function in the diff for `except` + fall-through, not just the one the finding named. {#imp-silent-pass-migrates}
- 2026-09-14 (plan-1 r2) — Remediation quality is up: 7/9 closed, live surfaces match claims, registry actually updated, plan status honest. The residual is one dict-key read. {#imp-plan1-r2-progress}

- 2026-09-14 (plan-3) — Third run where the cited test proves EXISTENCE, not the claim: `_click_cmd(path)` for "calls the verb", a `no_twin` set that excludes all 14 `memory_recall` params for "defaults match". Count the population vs the compared set before crediting any "every X has a Y" test. PATTERN filed. {#imp-existence-check-tests}
- 2026-09-14 (plan-3) — Verb-layer migrations move code but not tests: 18 verbs, 0 new tests, summaries 3.2/3.3 have no TDD section; the recorded full log had 4 failures the commit message reported as 2. Re-run the cited log's files at HEAD; a log that disagrees with the commit message is not a record. {#imp-migration-no-tests}
- 2026-09-14 (plan-3) — GOOD: plan status stayed `in-progress`, the widen mutation fails, table output is byte-identical, deployed 0.68.1 serves 28==28. The status-flip streak broke at two. Keep the escalation armed but note the correction. {#imp-status-flip-corrected}

rel: reinforces -> [[feedback_no_silent_failures]]

- 2026-09-14 (plan-2 r2) — Cost claims are measured on an idle daemon: the Stop promote was "0.13 s" on paper and 55 s / 15 s / 6.6 s in the first three live firings while the bridge and a post-commit sync held the writer. For any foreground hook, read its `source=hook` latencies from cli.log after the fleet has been busy, not the one-off timing. {#imp-cost-measured-idle}
- 2026-09-14 (plan-2 r2) — Remedies that follow my own one-line fix suggestion verbatim can still be wrong (`record_flags` now runs for `--no-claude` but does not record `claude`, so `--check` reports false drift). Re-probe the exact scenario the finding named after every remedy; the finding's suggested fix is a hint, not the acceptance test. {#imp-verbatim-fix}
- 2026-09-14 (plan-2 r2) — Round-2 quality: 9/11 closed, each reproduced by probe; `check()` is now a real guard (six mutation classes detected). The residual is a decision on real numbers, not code. {#imp-plan2-r2-progress}

- 2026-09-14 (plan-1 r3) — Third round closed everything that mattered; the guard was re-checked by replaying the incident on paper AND by the live relaunch at e6c4081 printing the deploy `code=`. Keep doing both: a unit test with faked identities cannot see a `.pth`. {#imp-plan1-r3-closed}
- 2026-09-14 (plan-1 r3) — Registry omission is now 2-for-2 in plan 1 (FakeBus/FakeHub this time). Next unregistered mock in any plan-1 commit is BULLSHIT per the 3-strike rule. {#imp-registry-2-strikes}
- 2026-09-14 (plan-1 r3) — "Fallback carries an error field" is not the same as "the error is surfaced": `identity_error` is written by two producers and read by none, so a failed identity renders as clean. When a fallback adds a diagnostic key, grep for its readers before calling it visible (I did not, in r2). {#imp-unread-diagnostic-field}

- 2026-09-14 (plan-2 r3) — A bound applied to a CALL is not a bound on the COMMAND: `--timeout 5` covers `memory_add` and the same hook then makes two 60 s × 3 subject calls. For any "bounded"/"timeout" remedy, enumerate every RPC the command can make in every STM state (subject set, global, no daemon) and spy the kwargs of each; the test that patches `call` to raise proves only the first. {#imp-partial-bound}
- 2026-09-14 (plan-2 r3) — Fixes land at the quoted line and not in the sibling: busy≠absent was fixed in `ingest-gmd --detach` (r2) while `focus summarize` ten lines from the new code kept the bare `ping` gate. Grep the diff's file for every other `if daemon_mod.ping(root)` before crediting a busy/absent fix. {#imp-fix-at-quoted-line}
- 2026-09-14 (plan-2 r3) — The pid-file + listening-socket simulation is now the reference probe for daemon-state paths; it found #b-1, #s-2 and #s-3 where the patched tests measured 1.25 s of a 7.4 s path. When a test patches `daemon_status` or `ping`, run the simulation instead of reading the assertion. {#imp-socket-sim-probe}
