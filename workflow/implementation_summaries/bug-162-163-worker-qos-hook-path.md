---
gmd: "0.1"
id: impl-bug-162-163-worker-qos-hook-path
title: "bug-162 / bug-163: shared model workers off Background QoS; generated hooks find rmx without the launcher's PATH"
tags: [implementation, bugfix, launchd, hooks, rerank, cliquedb]
metadata:
  node_type: implementation-summary
  date: 2026-11-08
---

# bug-162 / bug-163 {#root}

rel: implements -> [[bug_registry#registry]]

Two fixes from one session. The first comes from cliquedb's field report on the bus
(`ae9c57ed7f13` / `fb3fefdff19b`, 2026-11-08). The second is the Stop hook error this session
hit itself. The rest of that report is logged open as bug-164..167.

## bug-162: rerank timed out on every prompt {#bug-162}

Steps that found it, in order:

1. Reproduced in cliquedb. `rmx scan-prompt` on "yes next" gave
   `rerank skipped: no answer within the 4.9s budget`.
2. Called the shared worker directly. It answered `info` in 0.00 s and had `queue_depth` 0, but
   took 3.6-3.9 s to score 10 docs of 2160 chars.
3. Ran the same pool in a fresh process. It took 0.23 s on CPU and 0.07 s on MPS.
4. Ran the same fresh process under `taskpolicy -b`. It took 2.7-3.5 s, which reproduces the
   worker's number.
5. Read the hub plist. It has `ProcessType=Background`. The workers (pid 3206 rerank,
   3108 embed) are children of the hub, run at PRI 4, and sit at about 117% CPU.

Fix: `render_hub_plist` now renders `ProcessType=Standard`. The daemon plists still render
Background, because I did not measure them.

## bug-163: `rmx: command not found` in every hook {#bug-163}

This session's transcript has `hook_non_blocking_error` records, exit 127, on SessionStart,
UserPromptSubmit and Stop. Herdr started the session as `bash -l`. A login shell reads
`~/.bash_profile` and `~/.profile`. Only `~/.bashrc` puts `~/bin` on PATH.

Fix, in two parts:

1. `hooks.HOOK_ENV` now also exports `PATH="$HOME/bin:$HOME/.local/bin:$PATH"`. It is the one
   prefix every generated hook shares. `$HOME` expands when the hook runs, so the generated text
   is the same on every machine.
2. `~/.profile` now adds `~/bin` for login shells. This edit is outside the repo, and the user
   approved it.

## Tests {#tests}

`tests/test_bug162_163_worker_qos_hook_path.py` holds two tests. Both were RED before the fix,
and the second failed with the exact production error. Both pass after it. The hook test runs
EVERY generated rmx command under `/bin/sh` with `PATH=/usr/bin:/bin` and a fake
`$HOME/bin/rmx`.

## Rollout {#rollout}

1. Deploy.
2. Run `rmx hub launchctl install` from the deployed rmx, then restart the hub.
3. Run `rmx install-hooks` in each project so its settings pick up the new `HOOK_ENV`.
