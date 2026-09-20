---
gmd: "0.1"
id: impl-adr-0003-partition-audit-fingerprint
title: "ADR-0003: the partition audit and the measurement fingerprint"
tags: [implementation-summary, partitions, measurement, adr-0003]
metadata:
  node_type: implementation-summary
  status: complete
  created: 2026-09-20
---

# ADR-0003: the audit, and the fingerprint the audit feeds {#root}

rel: implements -> [[adr-0003-canonical-partition-layout]]
rel: derives-from -> [[partition-layout-survey]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: related-to -> [[plan-13-cross-partition-sweep]]

## Why both, and why in this order {#why}

The fleet survey found four partition layouts, six zero-row orphan registrations and ~143MB of
vectors for partitions that no longer exist. Then a fair question: **with these variations, how can
we be sure of any measured number?** The answer is that for numbers compared against a STORED
number, we cannot — and three proofs landed within one hour: {#why-lead}

- a stale `[UNVERIFIED]` daemon served a MemAware run and moved `scan-prompt` 0.433 → 0.444 with no
  code change (bug-055);
- `rmx context` measured 0.478/0.186 against a recorded 0.511/0.248, still unattributed;
- that 0.511 turned out to be a HELD-OUT question set, tabled beside numbers from another one.

Paired comparisons within one run survive, because both arms share every confound. Longitudinal
ones do not. So the audit answers "what shape is this store" and the fingerprint answers "may this
number sit in a table with that one" — the second needs the first.

## What shipped {#shipped}

| where | what |
|---|---|
| `partitions.py` | `expected_partitions()` + `audit()` — the ADR-0003 decision logic, **pure**: it takes facts, never a store |
| `daemon.py` | `_op_partition_audit` gathers catalog facts under `_store_lock`, in `CLI_OPS` (interactive pool) |
| `cli.py` | `rmx partition audit [--json] [--fleet]`, exits 1 on drift so it can gate |
| `fingerprint.py` | `compose()` (pure) → `trustworthy` + `reasons` + a comparability `key`; `same_conditions()`; `require()`; `gather()` reads the surfaces that already report each fact |
| `cli.py` | `rmx fingerprint [--json]`, exits 1 when the conditions are not trustworthy |

**Read-only is a property of the signature, not a docstring promise.**
`test_audit_is_pure_and_takes_no_store` asserts `audit()`'s parameters contain no `store`, `root` or
`conn` — because "the repair tool damaged the thing it was auditing" is a failure this project can
afford exactly once. {#purity}

**`require()`'s override does not launder.** A deliberate measurement of a known-bad condition is
legitimate — plan-13's arms measure a drifted encoding on purpose — so `accept_reasons` records what
was accepted while `trustworthy` stays False. An override matching no reason still raises, so a
stale accept-list cannot wave through a NEW problem. {#override}

## Severity is three-valued on purpose {#severity}

`drift` means the store is not the canonical shape. `warn` means something is wrong inside a
canonical one (an unembedded project partition answers every dense query with nothing, silently).
`info` is reported and does NOT make a store non-canonical — whether session partitions should be
embedded is deliberately undecided until plan-13's gate returns, and an audit that called an
undecided question drift would train its own signal away. {#severity-lead}

## TDD record {#tdd}

- RED `pytest-partition-audit-red.log` (collection error — no module), `pytest-fingerprint-red.log`.
- GREEN `pytest-audit-fingerprint-green.log` — **42 passed**.
- Wiring tests, not helper tests ([[impression_bsd_tests_bypass_wiring]]): the op runs against a
  REAL `Store` and reads the real catalog; the command runs end to end through `CliRunner` on a real
  store with the daemon down.

**Mutations.** Laundering the override (`trustworthy = True` after an accept) kills
`test_require_can_be_overridden_but_says_so_loudly`.

**The second mutation killed nothing, and that was the useful one.** Deleting the `name != active`
guard — so an empty ACTIVE partition would be called an orphan — left all 19 tests green, because a
canonical active partition short-circuits on `name in expected` long before the orphan branch. The
guard is only reachable when the active partition is NON-canonical (`rmx -p scratch`), and nothing
tested that. `test_an_empty_NON_canonical_active_partition_is_not_an_orphan_either` now does, and
the same mutation kills it. A test that passes for the wrong reason is the shape this ledger keeps
finding. {#mutation-lesson}

## Not done here {#open}

The audit cannot run against the fleet until it IS the fleet: every live daemon serves 0.72.4 and
answers `unknown op: 'partition_audit'`. Remediation follows the deploy, and every repair is
announced and backed up before it touches a live catalog. {#open-lead}
