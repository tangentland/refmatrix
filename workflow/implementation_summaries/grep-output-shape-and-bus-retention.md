---
gmd: "0.1"
id: impl-grep-output-shape-and-bus-retention
title: "One output-shape resolver for rmx grep; hub retention for global:queues"
tags: [implementation, grep, hub, bus]
metadata:
  node_type: implementation-summary
  date: 2026-10-01
---

# One output-shape resolver for `rmx grep`; hub retention for `global:queues` {#root}

rel: evidence-for -> [[bug_registry#registry]]

Two asks, one session: make the `rmx grep` flag handling correct at the root
rather than a fourth time, and have the hub reap its own `global:queues`
backlog. Both landed at `86ac5d9`.

## The finding that reframed the grep work {#unmerged}

bug-058's fix was **committed on 2026-09-23 and never merged**. The registry row
recorded it as `fixed 2026-09-23` with verification detail, but
`git merge-base --is-ancestor 7222b60 master` was false, `_index_may_answer`
appeared 0 times on master, and `tests/test_grep_dropin_contract.py` was absent
from it. The work sat on `task-grep-dropin-contract` for eight days.

So bug-059 (`-c` prefix) and bug-060 (`-o` ignored) were **not** new defects in
a third copy of the render logic, which is how I first wrote both rows. They
were bug-058's own symptoms, still live. The correction is in both rows.

The lesson belongs in the process, not in the code: **verify a fix is reachable
from `master` before recording it as fixed.** A row that reads "fixed" is the
thing the next session trusts instead of re-measuring.

## The duplicate renderer {#duplicate}

`_grep_run` carried an inlined COPY of `_grep_rg_fallback` — whose docstring
already said it had been "extracted from `_grep_run`". The extraction happened;
the original was never deleted. bug-058 then patched BOTH copies rather than
removing one; its own comment called them "SIBLING" blocks "fixed together". So
`-c` was fixed twice and `-o` was missed twice.

The duplicate is deleted. `_grep_run` calls the one implementation, passing a
`learn_broker` for the single behaviour it genuinely has (it reports what was
learned). `test_the_fallback_renderer_exists_exactly_once` fails the build if a
second builder or a second banner reappears — structural, and earned.

## One resolution point {#resolver}

`_resolve_output_shape(gf, paths)` owns the four decisions — `with_filename`,
`line_number`, `only_matching`, `count` — and renderers consult it instead of
reading `gf`. The tool is always asked for canonical `file:line:text` (`-nH`),
never for the caller's layout, because handing `-c` through is exactly what
produced the `file:1` prefix nobody could switch off. ONE parse of that
canonical output feeds both the render and the learn broker, so a reshaped view
cannot cost the graph a hit.

Three parse-time gates also hid `-o`, and all three are open now: the
stdin-only gating of `_GREP_STDIN_SHORT`/`_LONG`; a `--flags` letter set
(`irIRnLlcvwFEH`) that rejected `h`/`o` while argv accepted them positionally;
and click claiming `-h` as its own `--help` alias.

### Behaviour change, stated plainly {#behaviour-change}

A bare single-file read now prints **bare lines**, as grep and ripgrep both do
(`grep ERROR t.txt` → `alpha ERROR`, verified by direct exec). Two bug-058
assertions required `file:line:text` there; that was the shim's shape, and the
same file's docstring calls such a divergence "every script and every agent on
this machine getting wrong answers". Provenance is opt-in via `-n`/`-H` and
composes, which is the property worth holding.

## Hub retention {#retention}

`Bus.reap_channel(channel, older_than_days=)` over the existing
`purge(status="all", before_ts=)`. The cutoff is built with the same local-time
`strftime` format `publish` stamps, because `purge` compares `ts < ?` as TEXT —
a UTC cutoff compares wrong without erroring. A non-positive window is REFUSED
rather than read as "everything".

`Hub._bus_retention_once` runs on the tick that already wakes to publish: the
producer owns its retention, and a sweep needing its own thread is a thread that
can go missing unnoticed. Scoped to `BUS_RETENTION_CHANNELS`
(`global:queues`) at `BUS_RETENTION_DAYS` (3, `RMX_HUB_BUS_RETENTION_DAYS`,
`<=0` disables). Agent-authored `proj:*` reports are never reaped on a timer —
the reports buried by this noise are the reason the work exists.

## Gates {#gates}

RED `workflow/review-output/pytest-shape-retention-red.log` (15 failed / 2
passed). GREEN `pytest-shape-retention-green.log` — **91 passed** across
`test_grep{,_output_shape,_dropin_contract,_stdin_dialect}`,
`test_bus_retention`, `test_hub_watchdog`, `test_rmxgrep`, `test_learn_queue`,
`test_telemetry_outcomes`.

Real-grep comparison by direct exec, **8 of 8 byte-identical**: `-o`, `-c`,
bare, `-n`, `-H`, `-c` over two files, `-h` over two files, and `-c` with no
match (`0`, exit 1 — the tool no longer counts, so that branch says it).

Mutations `pytest-shape-retention-mutations.log`, 7 of 7 kill their target:
G1 `-o` never forwarded; G2 prefix always on; G3 line numbers always on; G4
count always prefixed; G5 no-match count silent; G6 retention call deleted from
the tick; G7 zero window accepted.

**G6 is the one worth reading.** It PASSED on the first attempt, because the
wiring test called `_bus_retention_once` directly while calling itself a wiring
test — the exact pattern this ledger keeps filing. The test now drives
`_queue_alert_loop` for one tick, and G6 fails it.

## Process note {#process-note}

I lost the entire implementation mid-session by running `git checkout --
src/refmatrix/` to revert a mutation while the work was still uncommitted, and
had to replay every edit. The mutation loop MUST run against committed code; the
plan-3 round earlier in this session did commit first, and that is why it was
safe. Not a code defect, so not a registry row — but it cost a full rebuild.
