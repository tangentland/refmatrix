---
gmd: "0.1"
id: task-14.2-learning-toggle
title: "Task 14.2: one learning toggle, honoured by every site that learns"
tags: [task, grep, learning, toggle]
metadata:
  node_type: task
  status: complete
  created: 2026-10-05
---

# Task 14.2: one learning toggle, one resolver {#root}

> Plan: [plan-14-grep-learning-measurement](../plan-14-grep-learning-measurement.md)
> Status: Complete
> Depends on: —

rel: part-of -> [[plan-14-grep-learning-measurement]]

## Requirements {#requirements}

A single operator-level switch turns the grep→graph learning loop off and on, and **every** site
that can learn honours it. `--learn/--no-learn` already exists per invocation; what is missing is
state that outlives one process, because the daemon's drain and a hook-spawned child both learn
without ever seeing my shell flag. {#req-lead}

Resolution order, decided once in one function: {#req-order}

1. env `RMX_LEARN` — `0`/`off`/`false`/`no` ⇒ off, `1`/`on`/`true`/`yes` ⇒ on. A one-off override.
2. per-store marker `<store root>/learn.off` ⇒ off.
3. user-global marker `~/.refmatrix/learn.off` ⇒ off.
4. otherwise ON (the shipped default does not change).

A marker FILE, not a config key in the catalog: a bash hook (task 14.3) and a CLI whose daemon is
down must both answer the question with a `[ -f ]` test and no store access, no socket, no Python
import. {#req-marker}

Sites that must consult it — a site that keeps learning while the toggle is off is the bug this
task exists to prevent: {#req-sites}

| Site | File | Behaviour when off |
|------|------|--------------------|
| the grep fallback broker | `cli.py` `_broker_learn_from_grep` | enqueue/RPC skipped |
| the `rmx context` grep backstop | `cli.py` `_maybe_learn_grep_backstop` | no hits collected for teaching |
| the daemon's queue drain | `daemon.py` `_drain_learn_queue` | drains nothing, leaves the queue intact, REPORTS the skip with its depth |
| the daemon op | `daemon.py` `_op_learn_from_grep` | answers `{"added": 0, "skipped": "learning-disabled"}` |
| the ref-learn call | `daemon.py` (the `_learn_grep_hits` call on the ref path) | skipped |

CLI surface: `rmx learn status` prints the effective state AND which rule decided it; `rmx learn
off` / `rmx learn on` write/remove the per-store marker, `--global` targets `~/.refmatrix`. {#req-cli}

No silent suppression (CLAUDE.md#no-silent-failures — this is a memory-adjacent path). The
suppression is recorded in `answered_by`'s sibling field `learn` on every grep row (task 14.1), the
daemon names a skipped drain in its log with the queue depth, and an EXPLICIT `--learn` on the
command line that the toggle overrides says so once on stderr. A default-on invocation silenced by
the toggle stays quiet on stderr — that is the operator's own setting, and a line per grep would
make the toggle unusable. {#req-loud}

## Acceptance criteria {#acceptance}

1. `RMX_LEARN=0 rmx grep PATTERN` on a store with no index hit: the fallback answers, the learn
   queue stays empty, the telemetry row says `learn: false`.
2. Same with the per-store marker present and no env var. Same with the global marker.
3. `rmx grep --learn PATTERN` with the toggle off: still does not learn, and says why on stderr
   exactly once.
4. The daemon drain with the toggle off leaves a non-empty queue at its original depth and logs the
   skip including that depth — nothing is dropped.
5. `_op_learn_from_grep` with the toggle off returns `skipped: "learning-disabled"` and adds no
   concept.
6. `rmx learn status` names the deciding rule (`env` / `store-marker` / `global-marker` /
   `default`), and `rmx learn off` then `rmx learn status` agree.
7. With the toggle ON, every one of the above behaves exactly as it does today — the default path
   is unchanged.

## Files to create {#files-to-create}

| File | Purpose |
|------|---------|
| `src/refmatrix/learn_switch.py` | the ONE resolver: `learning_enabled(root)`, `decision(root)`, `set_enabled(root, on)`, marker paths |

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/cli.py` | consult the resolver in the broker + the context backstop; add the `rmx learn` command group; thread the effective state into the telemetry row |
| `src/refmatrix/daemon.py` | consult it in `_drain_learn_queue`, `_op_learn_from_grep`, and the ref-path learn |

## Implementation notes {#implementation-notes}

One resolver, imported by both `cli.py` and `daemon.py`. Four call sites growing their own
env-var check is the exact shape of [[feedback_reuse_shared_stoplist]] (one junk-token defect, four
copies) and of [[feedback_check_the_sibling_condition]] (a gate fixed on one of its conditions).
The function takes the store root so a per-store marker is possible; it must not import `store` or
open anything. {#one-resolver}

The daemon is long-lived and resolves the toggle **per drain tick**, not at boot — an operator who
flips the marker expects the next tick to honour it, and a value cached at startup is how a
"shipped" switch does nothing ([[feedback_restart_daemon_after_promote]]). {#per-tick}

## Test strategy {#test-strategy}

`tests/test_learn_switch.py` for the resolver (all four rules, precedence between them, malformed
env values) and `tests/test_learn_toggle_sites.py` for the five sites, each driven through its real
entry point against a real store under a short `tmp_path` root. The daemon drain case must assert
the queue depth AFTER the skipped drain — a test that only asserts "nothing was added" passes
against an implementation that silently ate the queue. {#tests}
