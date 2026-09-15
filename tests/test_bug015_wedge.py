"""bug-015: the project daemon wedged three times in an hour (ping alive,
heartbeat stale, every op stalled, no job lines) with no way to see why.
Working hypothesis: a daemon-side rerank on the hub's broken shared worker
(BrokenPipe on every op) waited at the worker's 300 s default inside an op.

1. `SIGUSR1` dumps every thread's stack into daemon.stderr.log — the next
   wedge is diagnosable.
2. The daemon's shared-worker client is bounded (SHARED_OP_TIMEOUT_S) so a
   broken worker costs an op seconds, not five minutes.
3. `scan-prompt` — the other per-prompt hook — bounds its rerank probe and
   score like `memory recall` does, and the generator passes `--timeout 5`.
4. The hub drops a worker whose pipe broke so the next call recreates it
   instead of failing forever.
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import tempfile
import time
from pathlib import Path

from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import modelsrv, reranker, scan
from refmatrix.hooks import _claude_hook_block
from refmatrix.store import Store
from refmatrix.subproc import recv_frame, send_frame
from tests.test_hooks_reproducible import _cmds


def test_sigusr1_dumps_every_thread_stack_to_the_daemon_stderr_log():
    base = Path(tempfile.mkdtemp(prefix="rmxw-", dir="/tmp"))
    root = base / "proj" / ".refmatrix"; root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    try:
        os.kill(pid, signal.SIGUSR1)
        # launchd routes stderr to daemon.stderr.log; a spawned daemon to rmxd.stderr
        logs = [root / "daemon.stderr.log", root / "rmxd.stderr"]
        deadline = time.monotonic() + 5
        text = ""
        while time.monotonic() < deadline:
            text = "".join(l.read_text() for l in logs if l.exists())
            if "serve_forever" in text:
                break
            time.sleep(0.1)
        assert "Thread 0x" in text and "serve_forever" in text, text[-800:]
        assert dm.ping(root), "the dump must not stop the daemon"
    finally:
        dm.stop_daemon(root); shutil.rmtree(base, ignore_errors=True)


def test_daemon_shared_worker_client_is_bounded(tmp_path, monkeypatch):
    seen = {}

    class _Client:
        def __init__(self, role, *, log=None, timeout=None):
            seen["timeout"] = timeout

        def info(self, *, timeout=None):
            return {"model": "x"}
    monkeypatch.setattr(modelsrv, "shared_enabled", lambda: True)
    monkeypatch.setattr(modelsrv, "shared_available", lambda timeout=0.5: True)
    monkeypatch.setattr(modelsrv, "SharedWorkerClient", _Client)
    d = dm.Daemon(tmp_path / ".refmatrix"); d._log = lambda msg: None
    d._model_client("rerank")
    assert seen["timeout"] == dm.SHARED_OP_TIMEOUT_S and 5.0 <= dm.SHARED_OP_TIMEOUT_S <= 60.0


def test_scan_prompt_bounds_its_reranker(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(reranker, "shared_reranker",
                        lambda log=None, **kw: seen.update(kw) or None)
    root = tmp_path / ".refmatrix"
    s = Store(root); s.init()
    try:
        with s.with_partition("p"):
            c = s.add_concept("wedge")
            s.link("mentions", c, s.upsert_entity(kind="doc", name="a.md", path="a.md"))
        scan.scan_prompt(s, "tell me about wedge", composite=False, rerank_timeout=2.0)
    finally:
        s.close()
    assert seen.get("timeout") == 2.0 and seen.get("probe_timeout") == 1.0, seen


def test_scan_prompt_cli_and_generator_carry_the_timeout(tmp_path, monkeypatch):
    cmd = cli_mod.main.commands["scan-prompt"]
    opt = next(p for p in cmd.params if p.name == "timeout")
    assert opt.default == 5.0
    block = _claude_hook_block(tmp_path / ".refmatrix")
    ups = [c for _, _, c in _cmds(block, "UserPromptSubmit") if "rmx scan-prompt" in c]
    assert ups and all("--timeout 5" in c for c in ups), ups


class _BrokenWorker:
    def __init__(self):
        self.calls = 0

    def call(self, op, req, blob=None):
        self.calls += 1
        raise BrokenPipeError(32, "Broken pipe")

    def close(self, timeout=0.0):
        pass


def test_model_server_drops_a_worker_whose_pipe_broke():
    srv = modelsrv.ModelServer(log=None)
    broken = _BrokenWorker()
    srv._clients["rerank"] = broken
    a, b = socket.socketpair()
    rw = a.makefile("rwb")
    send_frame(rw, {"role": "rerank", "op": "rerank", "query": "q", "docs": ["d"]})
    a.shutdown(socket.SHUT_WR)
    srv._handle(b)
    hdr, _ = recv_frame(rw)
    assert hdr["ok"] is False and "BrokenPipe" in hdr["error"]
    assert "rerank" not in srv._clients, "a worker whose pipe broke must be dropped"
    assert broken.calls == 1
