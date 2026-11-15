"""bug-240 RED, the agent routes: `rmx_ingest(path=<FILE>)` is refused, naming `rmx sync -f`.

WHY (bug-240, lead ruling 2026-11-14: REFUSE, in the SHARED ingest path so CLI and MCP agree).
`rmx ingest <FILE>` exited 0 with `ingested 0 entities`; the CLI half is
`test_bug240_ingest_file_arg.py`. The MCP tool reaches the same walk by another road:
`rmx_ingest` -> `verbs.ingest` -> daemon op `ingest_path_start` -> a background job running
`_op_ingest_path` -> `ingest_path` on a file, which walks no tree. The tool answers
`{job_id, status: running}` and the job ends `done` with nothing ingested -- a success for a
write that never happened. With the daemon down the verb answers "not running", which tells an
agent to start a daemon and retry the same wrong call.

Routes, each on a throwaway store under a SHORT `/tmp` mkdtemp root (macOS `sun_path`):
  mcp-stdio  a real `rmx mcp` server process (dev rmx, this checkout via PYTHONPATH), JSON-RPC
             `tools/call rmx_ingest {root, path}` -> the reply must be `isError` naming
             `rmx sync -f`; daemon up and daemon down
  verb       `verbs.VERBS["rmx_ingest"].run(root, {path})` in this process -> `VerbError`
             naming `rmx sync -f`; daemon up and daemon down
  op         `daemon.call(root, "ingest_path" | "ingest_path_start", {path})` on the real
             daemon socket -> `ok: false` naming `rmx sync -f` (the shared layer the CLI's
             daemon-up route and the MCP tool both reach)
Guard: `rmx_ingest(path=<dir>)` over MCP still starts a job that ends `done` with the
directory's files ingested.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from devbin import dev_env, dev_rmx  # bug-253: the dev rmx, defined once (tests/devbin.py)

REPO = Path(__file__).resolve().parents[1]
RMX = dev_rmx()
NAMED = "rmx sync -f"

FILES = {"CLAUDE.md": ('---\ngmd: "0.1"\nid: claude\ntitle: "rules"\ntags: [t]\n---\n\n'
                       "# Rules {#root}\n\n## Section x {#x}\n\nRule text.\n"),
         "docs/notes.md": "# Notes\n\nPlain markdown.\n",
         "src/pkg/a.py": "def hello():\n    return 1\n"}


def _env(root: Path) -> dict:
    return {**dev_env(), "REFMATRIX_ROOT": str(root), "RMX_INVOCATION_SOURCE": "eval"}


def _rmx(env: dict, *args: str, timeout: int = 300, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(RMX), *args], env=env, capture_output=True, text=True,
                          timeout=timeout, **kw)


def _wait_sock(root: Path) -> None:
    for _ in range(120):
        if list(root.glob("*.sock")):
            return
        time.sleep(0.5)
    raise AssertionError(f"daemon socket never appeared under {root}")


@contextlib.contextmanager
def _make_store(up: bool):
    assert RMX.exists(), f"dev rmx missing at {RMX}"
    base = Path(tempfile.mkdtemp(prefix="b240m.", dir="/tmp")).resolve()
    p = base / "proj"
    for rel, text in FILES.items():
        f = p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    root = p / ".refmatrix"
    env = _env(root)
    c = {"proj": p, "root": root, "env": env, "up": up}
    try:
        r = _rmx(env, "init", "--path", str(p), "--no-hooks", "--no-agents",
                 "--no-memory-hooks")
        assert r.returncode == 0, r.stdout + r.stderr
        if up:
            r = _rmx(env, "daemon", "start", "--no-watch", timeout=180)
            assert r.returncode == 0, r.stdout + r.stderr
            _wait_sock(root)
        yield c
    finally:
        if c["up"]:
            _rmx(env, "daemon", "stop", timeout=120)
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(params=["up", "down"], ids=["daemon_up", "daemon_down"])
def store(request):
    with _make_store(request.param == "up") as c:
        yield c


@pytest.fixture
def up_store():
    """The op routes dial the daemon socket, so they run with a daemon only."""
    with _make_store(True) as c:
        yield c


def _mcp(c, tool: str, arguments: dict) -> dict:
    """One `tools/call` against a real `rmx mcp` stdio server; returns the call's `result`."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": tool, "arguments": {"root": str(c["root"]), **arguments}}},
    ]
    r = _rmx(c["env"], "mcp", input="".join(json.dumps(m) + "\n" for m in msgs),
             timeout=120)
    replies = [json.loads(ln) for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    call = [m for m in replies if m.get("id") == 2]
    assert call, f"no reply to tools/call (rc={r.returncode})\nstdout:{r.stdout}\nstderr:{r.stderr}"
    assert "result" in call[0], f"JSON-RPC error, not a tool reply: {call[0]}"
    return call[0]["result"]


def _text(result: dict) -> str:
    return " ".join(part.get("text", "") for part in result.get("content", []))


@pytest.mark.parametrize("rel", ["CLAUDE.md", "docs/notes.md"])
def test_the_mcp_tool_refuses_a_file_naming_sync(store, rel):
    res = _mcp(store, "rmx_ingest", {"path": str(store["proj"] / rel)})
    assert res.get("isError") is True, (
        f"rmx_ingest(path=<file>) answered success: {_text(res)}")
    assert NAMED in _text(res), f"the refusal must name `{NAMED}`: {_text(res)}"


def test_the_verb_refuses_a_file_naming_sync(store):
    from refmatrix.verbs import VERBS, VerbError
    with pytest.raises(VerbError) as ei:
        out = VERBS["rmx_ingest"].run(store["root"], {"path": str(store["proj"] / "CLAUDE.md")})
        raise AssertionError(f"verb rmx_ingest(path=<file>) returned {out}")
    assert NAMED in str(ei.value), f"the VerbError must name `{NAMED}`: {ei.value}"


@pytest.mark.parametrize("op", ["ingest_path", "ingest_path_start"])
def test_the_daemon_op_refuses_a_file_naming_sync(up_store, op):
    from refmatrix import daemon as daemon_mod
    r = daemon_mod.call(up_store["root"], op, {"path": str(up_store["proj"] / "CLAUDE.md")},
                        timeout=60, retries=0)
    assert r.get("ok") is False, f"op {op}(path=<file>) answered ok: {r}"
    assert NAMED in str(r.get("error")), f"op {op} refusal must name `{NAMED}`: {r}"


def _rows_for(root: Path, path: Path) -> list[tuple]:
    import duckdb
    active = root / "active"
    slot = (root / f"catalog.{active.read_text().strip()}.duckdb") if active.exists() else None
    cat = slot if slot is not None and slot.exists() else root / "catalog.duckdb"
    con = duckdb.connect(str(cat), read_only=True)
    try:
        return [tuple(r) for r in con.execute(
            "SELECT kind, name FROM entities WHERE path = ?", [str(path)]).fetchall()]
    finally:
        con.close()


def test_guard_the_mcp_tool_still_ingests_a_directory(store):
    res = _mcp(store, "rmx_ingest", {"path": str(store["proj"])})
    if not store["up"]:
        # Daemon down: unchanged -- an error that says the daemon is absent, not the file
        # refusal (a directory is not a file).
        assert res.get("isError") is True, _text(res)
        assert NAMED not in _text(res), f"a directory was refused as a file: {_text(res)}"
        return
    assert res.get("isError") is False, _text(res)
    job_id = json.loads(_text(res))["job_id"]
    from refmatrix.verbs import VERBS
    status = None
    for _ in range(240):
        st = VERBS["rmx_ingest_status"].run(store["root"], {"job_id": job_id})
        status = (st.get("job") or {}).get("status")
        if status != "running":
            break
        time.sleep(0.5)
    assert status == "done", f"directory ingest job ended {status!r}: {st}"
    r = _rmx(store["env"], "daemon", "stop", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    store["up"] = False
    for rel in FILES:
        assert _rows_for(store["root"], store["proj"] / rel), f"directory ingest lost {rel}"
