---
gmd: "0.1"
id: bug_registry
title: "Bug Registry — known bugs, root causes, and fixes"
tags: [process, bugs, governance]
metadata:
  node_type: registry
---

# Bug Registry {#root}

Curated log of bugs encountered and fixed — sibling to the mock and deferral registries. Where
[[test_mock_registry]] classifies test-side mocks and [[deferral_registry]] tracks deferred
functionality, this registry captures **bugs**: what broke, why, and the fix — so the same mistake
is not re-derived across sessions. Managed the same way (curated, classified, GMD-linted);
`@ch-gap-master` keeps it current, `@ch-bsd` mines it for recurring cheap-fix patterns.

rel: part-of -> [[test_mock_registry]]

## When to log {#when}

The threshold is LOW — when in doubt, log it. Log an entry whenever:

- The user reports an error, bug, or problem ("doesn't work", "broken", "shows wrong X").
- A test, build, lint, or type check fails, or a runtime/import/type/syntax error occurs.
- You fix something that was broken, or change error-handling / validation logic.
- You edit the same file more than twice to get one thing right (a signal it was a bug).

**Before fixing:** search this registry first — the fix may already be known. If `rmx` is present,
`rmx memory search "<symptom>"` also surfaces past occurrences.

## Status {#status}

| Status | Meaning |
|--------|---------|
| `open` | Reproduced, not yet fixed |
| `fixed` | Fix landed + verified |
| `recurring` | Seen again after a prior fix — needs a durable/root fix |

## Registry {#registry}

| ID | Symptom / error | File(s) | Root cause | Fix | Tags | Status | Seen |
|----|-----------------|---------|------------|-----|------|--------|------|
| bug-001 | deploy venv `.pth` → dev checkout; `rmx`/daemons/hub ran uncommitted code (2026-09-14) | `~/refmatrix/.venv/.../__editable__.refmatrix-*.pth`, save-state memory step 4 | absolute `pip install -e <dev tree>` into the deploy venv | `upgrade.runtime_identity` + `verify_editable`; `rmx version -v`; memory rewritten (0.66.3) | deploy, venv | fixed | 1 |
| bug-002 | `rmx install-hooks --enforce` accepted but ignored (want() only honoured it with no project root) | src/refmatrix/hooks.py | forced branch unreachable from every production caller | `if enforce is True: return True` (0.68.1) | hooks | fixed | 1 |
| bug-003 | `--force` stripped user hooks named `enforce-*.sh` | src/refmatrix/hooks.py `_RMX_HOOK_SIGNATURES` | prefix signature `.claude/hooks/enforce-` | exact script names (0.68.1) | hooks | fixed | 1 |
| bug-004 | daemon wedged 300 s adopting a mute `models.sock`; `test_daemon_falls_back_when_shared_socket_does_not_answer` timed out | src/refmatrix/modelsrv.py, daemon.py `_model_client` | probe used the worker op timeout; a socket timeout (an OSError) triggered reconnect with the default timeout | bounded `info(timeout=PROBE_TIMEOUT_S)`, no retry on TimeoutError (0.68.1) | daemon, models | fixed | 1 |
| bug-005 | Claude Code shell snapshots contained `set -o #`; user function bodies had grep rewritten to rmxgrep | bin/rmxgrep, hooks.AGENT_BASHRC_SECTION, cli.py `_grep_stdin_addendum` | BASH_ENV alias + expand_aliases + RMXGREP_MODE=rich in the snapshot shell; index note on stdout | note → stderr (0.66.2); piped stdin = real grep; grep()/rg() functions (cf3d87d) | grep, hooks | fixed | 1 |
| bug-006 | `rmx ingest-gmd --detach` said "no daemon running" to a busy daemon; SessionStart catch-up skipped after every deploy | src/refmatrix/cli.py ingest_gmd | ping cannot tell busy from absent | discovery.daemon_status busy → retry then busy-specific error (0.68.1) | daemon, bridge | fixed | 1 |
| bug-007 | `rmx_where` / `rmx_locate` / `rmx locate` returned stale (or empty) results from a long-lived process after the store changed; `test_locate_verb_finds_an_ingested_file_by_basename` → `{'results': []}` | src/refmatrix/search.py `cached_replica` | the cached read-only DuckDB connection stays bound to the OLD `catalog.read.duckdb` inode after the daemon's tmp+rename snapshot; the MCP server / hub never reopen | `_snapshot_sig` (ino, mtime_ns, size) recorded at open; `cached_replica` reopens when it changes (plan-3 r1 remedy) | search, replica, staleness | fixed | 1 |

<!--
Entry conventions:
- ID: bug-NNN, zero-padded, monotonic.
- Symptom: the exact error string or user complaint (quote errors verbatim).
- Root cause: WHY it broke, not just where.
- Fix: what changed to resolve it (file:function or the concrete edit).
- Tags: kebab keywords for search (e.g. auth, off-by-one, import, migration).
- Seen: occurrence count; bump + flip Status to `recurring` if it reappears.
-->
