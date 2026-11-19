"""bug-212 r6 RED: ch-bsd r5 (`workflow/bullshit/2026-11-14-0318-bug212-r5-355eb1f.md`, DIRTY
0B/1S/3M, GO) and the lead's ruling L98 (`workflow/plan-review-2026-11-13.md`, 2026-11-14).

WHY each group exists:

s-1 (SKETCHY). `rmx migrate-to-duckdb` asked git about the SOURCE store
    (`_refuse_tracked_catalog_open(root, dst)`), but the file `migrate_catalog` unlinks and
    rebuilds is `dst`. So `--out` into ANOTHER repo's tracked catalog, from an ignored store,
    exited 0 with ` M .refmatrix/catalog.duckdb` in that repo -- the one write the check exists
    to stop -- while `--out` to a harmless path from a tracked store was refused. L98: aim the
    check at the destination (`dst.parent`, `dst`); the default dst (`<root>/catalog.duckdb`)
    keeps today's refusal (pinned by the r5 test
    `test_migrate_to_duckdb_overwrite_refuses_a_git_tracked_catalog`).
m-1 (MEH). MCP `rmx_save_state`'s isError reply on `SaveStateIncompleteError` was only the
    message: `target`, `remove_failed`, `lint`, ... -- the fields the /save-state template tells
    an agent to act on -- were dropped. L98: `{**e.result, "error": str(e)}`, still isError.
m-2 (MEH, ruled). A bridge that is only DEFERRED behind a running ingest job ("ingest job <id>
    still running after <n>s ...; will be bridged by the next save-state / SessionStart")
    self-heals, yet r5 made it fail the save (exit 1 / isError). L98: a stderr warning naming
    the job, exit 0, `sync.deferred = {job, reason}` in the result; MCP not isError with the
    field present. Every OTHER bridge failure still raises.

S1 (2026-11-19, one catalog backend) deleted s-1's two tests with `rmx migrate-to-duckdb`;
m-1 and m-2 stay.

Everything is real: git, the CLI, the MCP stdio server, a throwaway daemon with a real running
`ingest_gmd_start` job (the wait is shortened through the existing `RMX_BRIDGE_WAIT_S`, never by
patching the function under test), the store. Stand-in: the registered rmx-lookalike process
as the busy daemon (`busy_store`, r5).
"""
from __future__ import annotations

import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import mcp as mcp_mod
from refmatrix import verbs
from tests.test_bug212_hooks_in_worktrees import _base_env
from tests.test_bug212_r1_remedy import (  # noqa: F401 -- `tracked_repo` is used by name
    _target_catalog, tracked_repo,
)
from tests.test_bug212_r4_red import (  # noqa: F401 -- fixtures are used by name
    _errors, ignored_store_repo,
)
from tests.test_bug212_r5_red import (  # noqa: F401 -- fixtures are used by name
    _mcp, _text, busy_store,
)
from tests.test_memory_bridge import GMD, _big_dir, live  # noqa: F401 -- `live` by name


# =============================================================================================
# m-1: MCP rmx_save_state's isError reply carries the result
# =============================================================================================

@pytest.mark.timeout(300)
def test_mcp_save_state_error_reply_carries_the_result(busy_store):
    """m-1 (L98): a busy daemon makes the promote fail. MCP `rmx_save_state` replies `isError`,
    and its body is the RESULT with the error added -- `target` (the handoff file, which
    exists), `remove_failed`, `lint`, `promoted`, and `error` naming the failure -- not the bare
    message. At c854bad the body is `{"error": "<message>"}` only."""
    from refmatrix import stm
    repo = busy_store
    session = "bug212-r6-mcp"
    stm.Stm(repo.store, session).record("note", "a focus event for the bug-212 r6 MCP probe")
    memdir = repo.base / "memdir"
    memdir.mkdir()
    replies, text = _mcp(repo, repo.proj, [("rmx_save_state", {
        "session": session, "memory_dir": str(memdir), "sync": False, "lint": False,
        "message": "bug-212 r6 MCP probe"})])
    assert 2 in replies and 99 in replies, f"the MCP server stopped answering\n{text}"
    res = replies[2].get("result") or {}
    raw = " ".join(c.get("text", "") for c in res.get("content", []))
    assert res.get("isError") is True, f"not an isError reply: {raw[:600]!r}"
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        pytest.fail(f"the isError reply body is not the JSON result: {raw[:600]!r}")
    missing = sorted(k for k in ("target", "remove_failed", "lint", "promoted", "error")
                     if k not in body)
    assert not missing, f"the isError reply dropped {missing} of the result: {raw[:600]!r}"
    assert Path(body["target"]).is_file(), f"the reply's target does not exist: {body['target']}"
    assert "busy" in body["error"] and "save-state wrote" in body["error"], body["error"]


# =============================================================================================
# m-2: a bridge only deferred behind a running ingest job is a warning, not a failure
# =============================================================================================

DEFER_DOCS = 1500


def _start_running_job(base: Path, root: Path) -> str:
    """A REAL ingest job on the daemon (a big as-memory dir), so the bridge's own ingest is
    refused with "ingest already active" and waits on it."""
    other = _big_dir(base, "other", DEFER_DOCS)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(other)], "as_memory": True,
                                              "memory_mtype": "curated",
                                              "partition": verbs.memory_partition(root)},
                   timeout=30)
    assert resp.get("ok"), resp
    return resp["result"]["job_id"]


def _session_and_memdir(base: Path, root: Path, session: str) -> Path:
    from refmatrix import stm
    stm.Stm(root, session).record("note", "a focus event for the bug-212 r6 deferral probe")
    memdir = base / "memory"
    memdir.mkdir()
    (memdir / "mine_r6.md").write_text(GMD.format(id="mine_r6", body="mine"), encoding="utf-8")
    return memdir


def _job_status(root: Path, jid: str) -> str:
    r = dm.call(root, "ingest_gmd_status", {"job_id": jid}, timeout=10)
    return ((r.get("result") or {}).get("job") or {}).get("status")


@pytest.mark.timeout(300)
def test_a_deferred_bridge_is_not_a_failed_save_state_verb(live, monkeypatch):
    """m-2 (L98), the verb: `verbs.save_state` (promote off, the bridge ON) while a real ingest
    job runs, with the bridge wait shortened through `RMX_BRIDGE_WAIT_S`. It RETURNS; the
    result's `sync.deferred` is `{job: <id>, reason: ...}` naming the still-running job, and
    `sync.error` is empty. At c854bad it raises `SaveStateIncompleteError`."""
    base, root = live
    jid = _start_running_job(base, root)
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "0.2")
    memdir = _session_and_memdir(base, root, "bug212-r6-defer-verb")
    try:
        res = verbs.save_state(root, session="bug212-r6-defer-verb", memory_dir=str(memdir),
                               promote=False, lint=False, sync=True)
    except verbs.SaveStateIncompleteError as e:
        pytest.fail(f"a bridge only deferred behind running job {jid} failed the save: {e}")
    sync = res.get("sync") or {}
    deferred = sync.get("deferred") or {}
    assert deferred.get("job") == jid and "running" in str(deferred.get("reason", "")), \
        f"sync.deferred does not name the running job {jid}: {sync}"
    assert not sync.get("error"), f"a deferral is still reported as sync.error: {sync}"
    assert Path(res["target"]).is_file()


@pytest.mark.timeout(300)
def test_a_deferred_bridge_is_a_stderr_warning_and_exit_0(live, monkeypatch):
    """m-2 (L98), the CLI: `rmx save-state --no-promote --no-lint` while a real ingest job runs.
    Exit 0, a stderr line naming the job id, no `Error:` line. At c854bad: exit 1."""
    base, root = live
    jid = _start_running_job(base, root)
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "0.2")
    memdir = _session_and_memdir(base, root, "bug212-r6-defer-cli")
    r = CliRunner().invoke(cli_mod.main, ["save-state", "-s", "bug212-r6-defer-cli",
                                          "--memory-dir", str(memdir), "--no-promote",
                                          "--no-lint"])
    text = f"exit {r.exit_code}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert r.exit_code == 0, f"a bridge deferred behind running job {jid} failed the save\n{text}"
    assert jid in r.stderr, f"no stderr warning naming the running job {jid}\n{text}"
    assert not _errors(r.stderr), f"a deferral printed an `Error:` line\n{text}"


@pytest.mark.timeout(300)
def test_a_deferred_bridge_is_not_an_mcp_error(live, monkeypatch):
    """m-2 (L98), MCP: `rmx_save_state` (promote off, bridge on) while a real ingest job runs
    replies NOT isError, and the reply carries `sync.deferred` naming the job."""
    base, root = live
    jid = _start_running_job(base, root)
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "0.2")
    memdir = _session_and_memdir(base, root, "bug212-r6-defer-mcp")
    rep = mcp_mod.handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
        "name": "rmx_save_state", "arguments": {
            "root": str(root), "session": "bug212-r6-defer-mcp", "memory_dir": str(memdir),
            "promote": False, "lint": False}}})
    res = rep.get("result") or {}
    raw = " ".join(c.get("text", "") for c in res.get("content", []))
    assert res.get("isError") is not True, \
        f"a bridge deferred behind running job {jid} replied isError: {raw[:600]!r}"
    body = json.loads(raw)
    deferred = (body.get("sync") or {}).get("deferred") or {}
    assert deferred.get("job") == jid, f"the reply carries no sync.deferred for {jid}: {raw[:600]!r}"


# ---- GUARD: any OTHER bridge failure still fails the save -----------------------------------

@pytest.mark.timeout(300)
def test_a_refused_bridge_still_fails_the_save_verb_and_mcp(tracked_repo):
    """GUARD (passes at c854bad; against a fix that reads every bridge error as a deferral): a
    bridge REFUSED on a tracked catalog is a failure -- `verbs.save_state` raises
    `SaveStateIncompleteError` naming the memory bridge, and MCP `rmx_save_state` replies
    isError. (The CLI's exit 1 for the same case is the r5 test
    `test_save_state_whose_memory_bridge_is_refused_says_so_on_stderr_and_exits_non_zero`.)"""
    from refmatrix import stm
    repo, layout = tracked_repo
    assert not dm.ping(repo.store), "fixture: a daemon answers"
    stm.Stm(repo.store, "bug212-r6-guard").record("note", "guard probe")
    memdir = repo.base / "memdir"
    memdir.mkdir()
    probe = repo.base / "verb_probe.py"
    probe.write_text(
        "import json, sys\nfrom refmatrix import verbs\n"
        "try:\n"
        "    verbs.save_state(__import__('pathlib').Path(sys.argv[1]), session='bug212-r6-guard',"
        " memory_dir=sys.argv[2], promote=False, lint=False, sync=True)\n"
        "except verbs.SaveStateIncompleteError as e:\n"
        "    print(json.dumps({'raised': True, 'msg': str(e), 'deferred': "
        "(e.result.get('sync') or {}).get('deferred')}))\n"
        "else:\n"
        "    print(json.dumps({'raised': False}))\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(probe), str(repo.store), str(memdir)],
                       cwd=str(repo.proj), env=_base_env(), capture_output=True, text=True,
                       timeout=240)
    assert r.returncode == 0, _text(r)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["raised"] and "memory bridge failed" in out["msg"] and not out.get("deferred"), \
        f"[{layout}] a refused bridge did not fail the save verb: {out}"
    replies, text = _mcp(repo, repo.proj, [("rmx_save_state", {
        "session": "bug212-r6-guard", "memory_dir": str(memdir), "promote": False,
        "lint": False})])
    res = (replies.get(2) or {}).get("result") or {}
    assert res.get("isError") is True, f"[{layout}] MCP replied success on a refused bridge\n{text}"
