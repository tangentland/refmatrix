---
gmd: "0.1"
id: task-3.4-internal-cli-allowlist
title: "Task 3.4: the parity test reads an explicit internal-only allowlist, and fails on an agent-facing command with no verb"
tags: [task, plan-3, verbs, parity]
metadata:
  node_type: task
  status: pending
  plan: plan-3-verbs-parity
  created: 2026-10-06
---

# Task 3.4: internal-only CLI allowlist in the parity gate {#root}

> Plan: [plan-3-verbs-parity](../plan-3-verbs-parity.md)
> Status: Pending
> Depends on: [[task-3.3-plan-3-verbs-parity]]

rel: part-of -> [[plan-3-verbs-parity]]
rel: implements -> [[deferral_registry]]

## Why {#why}

On 2026-10-06 the user accepted CLI-only commands for internal and test-harness surfaces: "I'm
okay with internal harness/testing cli only commands". The `deferral_registry.md` row records
that decision and names the gap it leaves.

`tests/test_verb_parity.py` checks verb→CLI pairing, and nothing checks the reverse. A new
agent-facing click command with no verb is indistinguishable from an accepted internal one, so
the anti-drift rule ("every capability an agent can call is a verb first") is enforced only when
someone remembers it. ch-bsd r2 #s-4 and r3 #s-4 flagged that the row pointed at no task spec;
this is that spec. {#why-lead}

## Requirements {#requirements}

- **`verbs.INTERNAL_CLI`.** A dict mapping each click command path to a one-line reason, next to
  `CLI_MAP` and `MCP_ONLY`. It is seeded with `derive log`, `derive diff`, `derive status`,
  `learn on`, `learn off` and `learn status`, plus `grep-learn` when plan-16's task 16.1 lands. The
  reasons quote the deferral row.
- **A reverse check in `test_verb_parity.py`.** Walk the click tree. Every leaf command path is
  either a CLI twin in `CLI_MAP`, or a key in `INTERNAL_CLI`, or a member of a named, reviewed
  `LEGACY_UNPAIRED` set. That set is the commands present today that are neither. Each of them is
  listed in the implementation summary with a decision (verb it, or move it to internal), so the
  set shrinks rather than becoming a second allowlist nobody reads.
- **Allowlist hygiene.** An `INTERNAL_CLI` entry whose path no longer resolves fails the test.

## Acceptance criteria {#acceptance}

1. Adding a new click command that is in neither list fails the test with a message naming the
   path and both places it could go. This is shown RED by adding a throwaway command inside the
   test via `click.Group.add_command` on a COPY of the group, never on `cli.main` itself.
2. Removing `derive log` from `INTERNAL_CLI` fails the test.
3. A stale `INTERNAL_CLI` key fails the test.
4. The `deferral_registry.md` row's graduation column points at this task. When this task
   completes, the row moves to resolved.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/verbs.py` | `INTERNAL_CLI`, `LEGACY_UNPAIRED` |
| `tests/test_verb_parity.py` | reverse walk + hygiene |
| `workflow/deferral_registry.md` | row → this task, then resolved |
