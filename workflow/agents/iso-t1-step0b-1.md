---
gmd: "0.1"
id: agent-brief-iso-t1-step0b-1
title: "Isolated agent brief: T1 step 0b, half 1 — move /tmp test roots onto short_root"
tags: [agent-brief, isolated, t1, test-hygiene, bug-229]
metadata:
  node_type: brief
  created: 2026-11-18
---

# T1 step 0b, half 1: move `/tmp` test roots onto `short_root` {#root}

You are an isolated small-fix agent (L174/L176) in your own clone. Ruling L185 (Q53 = b). Read
`CLAUDE.md` `#test-discipline`, then `tests/test_tmp_root_census.py` (the census and its rules)
and `tests/sandbox_site/rmx_sandbox.py::short_root`.

rel: implements -> [[plan-of-plans#queue]]

## The job {#job}

`tests/tmp_root_allow.json` lists `mkdtemp` sites whose root is `/tmp` or `/private/tmp`. Each entry
whose `reason` says "move it to rmx_sandbox.short_root(prefix) when its file is next touched" is to be
MOVED: in the listed site, replace the `/tmp` root with `rmx_sandbox.short_root(<prefix>)` (keep the
call's prefix; `short_root` returns a str, like `mkdtemp`), import `rmx_sandbox` the way the files
already on `short_root` do (see `tests/test_bug212_r1_remedy.py`), and delete that entry from the
allowlist. Only the entries whose key starts with one of YOUR files:

- `tests/test_bug112_duckdb_reopen.py`
- `tests/test_bug113_replica_merge_recovery.py`
- `tests/test_bug178_bulk_write.py`
- `tests/test_bug178_r2.py`
- `tests/test_bug212_hooks_in_worktrees.py`
- `tests/test_bug212_r2_red.py`
- `tests/test_bug212_r4_red.py`
- `tests/test_bug212_r6_red.py`
- `tests/test_bug212_r7_red.py`
- `tests/test_bug216_binding.py`
- `tests/test_bug216_hidden_no_pollution.py`
- `tests/test_bug216_ignore_reinclude.py`
- `tests/test_bug216_rel_landing.py`
- `tests/test_bug216_remedy_r1.py`
- `tests/test_bug216_remedy_r2.py`
- `tests/test_bug216_remedy_r3.py`
- `tests/test_bug216_remedy_r4.py`
- `tests/test_bug216_remedy_r5.py`
- `tests/test_bug216_remedy_r6.py`
- `tests/test_bug216_replay_fidelity.py`
- `tests/test_bug216_rev4.py`

Do not touch any other file's entries (another agent has the other half; `test_bug115_liveness_under_load.py`
waits for T0.4). If a site cannot move (it must be a real `/tmp`, e.g. it tests `/tmp` handling or
needs a path outside the sandbox), leave it and its entry, and rewrite that entry's reason to say
WHY in one line, with no "when … next touched" wording.

## Verify {#verify}

With `PYTHONPATH=src ~/.venv-lane/bin/python -m pytest -q -p no:cacheprovider`, output to
`../0b.log`: `tests/test_tmp_root_census.py` plus every file you edited. Before: record counts.
After: the census passes and every edited file passes. If a file fails BEFORE your edit too, say so
(do not fix unrelated failures). One commit: `T1 step 0b (half 1): …` with the moved count and any
kept site with its reason.

## Report {#report}

In the REPORT.md the prompt names: commit sha, entries moved / kept (with reasons), the
before/after allowlist size for your half, and the test counts.
