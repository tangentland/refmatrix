"""Shared harness for task 21.1's RED tests (agent context-usage telemetry).

Not a test module (no `test_` prefix): helpers the `test_task21_1_*.py` files and the AC-1b /
AC-4 / AC-4b sections of `tests/test_mcp_session_pointer.py` import.

Every helper works INSIDE task 23.0's sandbox: `HOME`, the global store and the per-test
`REFMATRIX_ROOT` are already redirected by the conftest before `refmatrix` is imported. What
lives here is the subprocess half the spec asks for explicitly (21.1 #test-strategy: "Subprocess
tests additionally pass `HOME`, `REFMATRIX_ROOT` and `RMX_HUB_MODELS=0` explicitly, because
bug-088's recorder cannot see a child's connects"), and the live-log guard of the AC preamble.

The live-log guard compares `(inode, size)` by `os.stat`, never by reading the file: the
sandbox's audit hook refuses an `open` of a live path, read or write (23.0 R3), and an append-
only log whose size did not move gained no line, so the AC preamble's "line counts are
unchanged" is asserted without a read.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

# The main dev tree (the workstation's live project store) -- a clone of it runs this suite.
_DEV_TREE = Path("/Users/tholley/claude_tools/refmatrix")

# Environment that would make a child think it runs under Claude Code or carries a session:
# the suite itself usually runs inside a Claude Code Bash call, so these are present in the
# test process's own env and would leak into every child (and into in-process resolution).
CLAUDE_ENV = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT",
              "RMX_SESSION", "RMX_INVOCATION_SOURCE", "CLAUDE_PROJECT_DIR")


# ---- the AC preamble: live logs untouched ---------------------------------------------------

def live_log_paths() -> list[Path]:
    """The four live logs the AC preamble names, for every live store a run could reach: the
    checkout's own `.refmatrix/`, the main dev tree's, and the REAL home's global store."""
    real_home = Path(os.environ.get("RMX_SANDBOX_REAL_HOME") or "/Users/tholley")
    stores = {REPO / ".refmatrix", _DEV_TREE / ".refmatrix", real_home / ".refmatrix"}
    out = []
    for s in sorted(stores):
        for name in ("query.log", "recall-events.jsonl"):
            out.append(s / name)
    return out


# Strings a test MINTED (session ids, prompt bodies) that may appear in a row it leaked into a
# live log. Tests register them through `mark_token`; the sandbox paths are always markers.
TEST_TOKENS: set[str] = set()


def mark_token(*tokens: str) -> None:
    """Register strings this test minted (a session id, a unique prompt) so the live-log
    guard attributes a live row carrying one to the test (21.1 r2 #s2, bug-134)."""
    TEST_TOKENS.update(t for t in tokens if t)


def _path_spellings(p: str) -> set[str]:
    out = {p}
    for a, b in (("/private/tmp/", "/tmp/"), ("/private/var/", "/var/")):
        if p.startswith(a):
            out.add(b + p[len(a):])
        elif p.startswith(b):
            out.add(a + p[len(b):])
    return out


def _test_markers() -> set[str]:
    """What makes a live row the TEST's: a path under the sandbox root (every sandbox store,
    `$RMX_HOME`, `REFMATRIX_ROOT`, pytest's tmp base), in either macOS spelling, or a token
    the test minted."""
    marks: set[str] = set()
    for k in ("RMX_SANDBOX_ROOT", "REFMATRIX_ROOT", "RMX_HOME"):
        v = os.environ.get(k)
        if v and len(v) > 8:
            marks |= _path_spellings(v.rstrip("/"))
    marks.add("/pytest-of-")              # pytest's own tmp base (tmp_path roots)
    return marks | set(TEST_TOKENS)


def live_snapshot(paths: "list[Path] | None" = None) -> dict:
    snap = {}
    for p in (paths if paths is not None else live_log_paths()):
        try:
            st = os.stat(p)
            snap[str(p)] = (st.st_ino, st.st_size)
        except FileNotFoundError:
            snap[str(p)] = (0, 0)
    return snap


def assert_live_logs_unchanged(before: dict) -> None:
    """The AC preamble's per-test guard -- STAT ONLY (21.1 ch-bsd r2 #s2, bug-134; converged
    with 23.0). A test process may never OPEN a live log: 23.0's audit hook refuses it
    (`SandboxViolation: open on live target …/.refmatrix/query.log`), and the r2 version that
    read the appended bytes here tripped it. So:
    - an inode change or a SHRINK fails here (truncation and rotation are never the user's);
    - growth is NOT judged here: the main dev tree's `query.log` grows with every hook of
      whichever Claude session works there. Each growth is recorded -- (path, inode, start,
      end, this test's nodeid, its markers: sandbox paths and minted tokens) -- to the
      sandbox's growth ledger, and attributed ONCE by 23.0's end-of-run content check
      (`rmx_sandbox.check_logs` / `growth_leaks`, run by scripts/sandbox-proof.sh), which
      fails on an appended row carrying a recorded marker."""
    import rmx_sandbox
    bad: dict = {}
    marks = sorted(_test_markers())
    nodeid = os.environ.get("PYTEST_CURRENT_TEST", "?").rsplit(" (", 1)[0]
    for k, (ino0, size0) in before.items():
        try:
            st = os.stat(k)
            ino1, size1 = st.st_ino, st.st_size
        except FileNotFoundError:
            ino1, size1 = 0, 0
        if (ino1, size1) == (ino0, size0):
            continue
        if ino0 and ino1 != ino0:
            bad[k] = f"inode changed {ino0} -> {ino1} (rotated or replaced)"
            continue
        if size1 < size0:
            bad[k] = f"shrank {size0} -> {size1} (truncated)"
            continue
        rmx_sandbox.record_growth({"path": k, "ino": ino1, "start": size0 if ino0 else 0,
                                   "end": size1, "nodeid": nodeid, "markers": marks,
                                   "t": time.time()})
    assert not bad, f"a LIVE log was rotated or truncated during the test: {bad}"


# ---- env + subprocess -----------------------------------------------------------------------

def clean_env(**extra) -> dict:
    """os.environ minus every Claude/session variable, plus the clone's `src` FIRST on
    PYTHONPATH (absolute: a relative path breaks children that chdir), plus `extra`.
    `extra` values of None delete the key."""
    env = {k: v for k, v in os.environ.items() if k not in CLAUDE_ENV}
    pp = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and p != str(SRC)]
    env["PYTHONPATH"] = os.pathsep.join([str(SRC)] + pp)
    env["RMX_HUB_MODELS"] = "0"
    env.setdefault("HF_HUB_OFFLINE", "1")
    for k, v in extra.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)
    return env


def rmx_env(root: Path, **extra) -> dict:
    """The env for a child `rmx` against the sandbox store `root` (the AC-1 recipe: `HOME` =
    the sandbox home, `REFMATRIX_ROOT` = tmp, `RMX_HUB_MODELS=0`)."""
    return clean_env(HOME=os.environ["HOME"], REFMATRIX_ROOT=str(root), **extra)


def rmx_bin() -> str:
    """`rmx` as the sandbox PATH resolves it: the eval venv's console script (the interpreter's
    own bin dir is first on the sandbox PATH), importing `refmatrix` from PYTHONPATH = SRC."""
    return str(Path(sys.executable).parent / "rmx")


def run_rmx(args, *, root: Path, cwd: Path | None = None, input: str | None = None,
            timeout: float = 120, **extra) -> subprocess.CompletedProcess:
    env = rmx_env(root, **extra)
    return subprocess.run([rmx_bin(), *map(str, args)], input=input, env=env,
                          cwd=str(cwd or root.parent), capture_output=True, text=True,
                          timeout=timeout)


def run_hook(cmd: str, *, root: Path, envelope=None, cwd: Path | None = None,
             timeout: float = 120, raw: str | None = None, **extra
             ) -> subprocess.CompletedProcess:
    """Run a GENERATED hook command line exactly as Claude Code does: `/bin/bash -c <cmd>`,
    the envelope as JSON on stdin, cwd = the project dir."""
    env = rmx_env(root, **extra)
    data = raw if raw is not None else (json.dumps(envelope) if envelope is not None else "")
    return subprocess.run(["/bin/bash", "-c", cmd], input=data, env=env,
                          cwd=str(cwd or root.parent), capture_output=True, text=True,
                          timeout=timeout)


def run_hook_bytes(cmd: str, *, root: Path, envelope=None, cwd: Path | None = None,
                   timeout: float = 120, **extra) -> subprocess.CompletedProcess:
    """`run_hook` with stdout kept as BYTES (R10's one unit: payload byte spans)."""
    env = rmx_env(root, **extra)
    data = json.dumps(envelope).encode() if envelope is not None else b""
    return subprocess.run(["/bin/bash", "-c", cmd], input=data, env=env,
                          cwd=str(cwd or root.parent), capture_output=True,
                          timeout=timeout)


# ---- the generated hook config --------------------------------------------------------------

def hook_block(root: Path) -> dict:
    from refmatrix.hooks import _claude_hook_block
    return _claude_hook_block(root, project_root=root.parent)


def hook_entries(root: Path, event: str | None = None) -> list[tuple[str, str | None, str]]:
    """[(event, matcher, command)] of the generated config."""
    out = []
    for ev, entries in hook_block(root)["hooks"].items():
        if event and ev != event:
            continue
        for e in entries:
            for h in e.get("hooks", []):
                out.append((ev, e.get("matcher"), h["command"]))
    return out


def generated_cmd(root: Path, event: str, needle: str) -> str:
    """The ONE generated command of `event` containing `needle`; fails loudly when absent
    (the assertion IS the RED reason for an entry this task adds)."""
    hits = [c for ev, _m, c in hook_entries(root, event) if needle in c]
    assert len(hits) == 1, (
        f"expected exactly one generated {event} command containing {needle!r}; got {hits}")
    return hits[0]


def generated_entry(root: Path, event: str, needle: str) -> tuple[str | None, str]:
    hits = [(m, c) for ev, m, c in hook_entries(root, event) if needle in c]
    assert len(hits) == 1, (
        f"expected exactly one generated {event} entry containing {needle!r}; got {hits}")
    return hits[0]


# ---- log readers ----------------------------------------------------------------------------

def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def query_rows(root: Path) -> list[dict]:
    return jsonl(root / "query.log")


def events(root: Path) -> list[dict]:
    return jsonl(root / "recall-events.jsonl")


def global_root() -> Path:
    from refmatrix import hub
    return Path(hub.global_store_root())


def line_count(path: Path) -> int:
    return len(path.read_text().splitlines()) if path.exists() else 0


# ---- a real sandbox daemon ------------------------------------------------------------------

class SandboxDaemon:
    """A real `rmx daemon start --no-detach --no-watch` child on a sandbox root. Foreground,
    so no launchd and no fork: the test owns the process and stops it."""

    def __init__(self, root: Path, *, boot_timeout: float = 120.0, **extra):
        self.root = root
        self.env = rmx_env(root, **extra)
        self.log = open(root.parent / "daemon-test.stderr.log", "wb")
        self.proc = subprocess.Popen(
            [rmx_bin(), "daemon", "start", "--no-detach", "--no-watch"],
            env=self.env, cwd=str(root.parent), stdout=self.log, stderr=subprocess.STDOUT)
        from refmatrix import daemon as daemon_mod
        deadline = time.time() + boot_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                break
            if daemon_mod.ping(root, timeout=0.5, retries=0):
                return
            time.sleep(0.2)
        self.stop()
        raise RuntimeError(f"sandbox daemon never answered ping on {root}: "
                           f"{(root.parent / 'daemon-test.stderr.log').read_text()[-2000:]}")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=30)
        self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


# ---- the real MCP stdio server --------------------------------------------------------------

class McpServer:
    """`rmx mcp` as a child (the real stdio server, newline-delimited JSON-RPC). Its parent is
    the test process, so `os.getppid()` in the server == `os.getpid()` here: a pointer the test
    writes for its OWN pid is the server's owner pointer."""

    def __init__(self, root: Path, *, cwd: Path | None = None, **extra):
        self.root = root
        self.env = rmx_env(root, **extra)
        self.proc = subprocess.Popen(
            [rmx_bin(), "mcp"], env=self.env, cwd=str(cwd or root.parent),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        self._id = 0
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "task21.1-test", "version": "0"}})

    def request(self, method: str, params: dict | None = None, timeout: float = 180.0):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        box: dict = {}

        def _read():
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    box["eof"] = True
                    return
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("id") == self._id:
                    box["resp"] = obj
                    return
        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        if "resp" not in box:
            raise RuntimeError(f"MCP server gave no answer to {method} "
                               f"(eof={box.get('eof')}): {self.stderr_tail()}")
        return box["resp"]

    def tool(self, name: str, arguments: dict | None = None, timeout: float = 180.0) -> dict:
        """Call a tool; returns {"isError": bool, "text": str, "json": parsed-or-None}."""
        r = self.request("tools/call", {"name": name, "arguments": arguments or {}}, timeout)
        res = r.get("result") or {}
        text = "".join(c.get("text", "") for c in res.get("content") or [])
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        return {"isError": bool(res.get("isError")), "text": text, "json": parsed,
                "raw": r}

    def stderr_tail(self) -> str:
        if self.proc.poll() is None:
            return "(running)"
        return (self.proc.stderr.read() or "")[-2000:]

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=30)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---- a test-owned daemon-socket peer (AC-2b) ------------------------------------------------

class OpDispatcher:
    """A plain AF_UNIX listener at `daemon.socket_path(root)` that reads each request line and
    answers by its `op` (AC-2b): NOT a mock of `src/` -- the client code under test runs
    unchanged; this is the socket peer it talks to. `on_op(op, n, conn, server) -> bool` may
    take over a request (return True when it handled/closed the connection itself).
    Records the op sequence in `.ops`."""

    def __init__(self, root: Path, answers: dict | None = None, on_op=None):
        from refmatrix import daemon as daemon_mod
        self.path = daemon_mod.socket_path(root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.path.unlink()
        self.answers = answers if answers is not None else {
            "ping": {"ok": True},
            "partition_list": {"ok": True, "result": {"rows": []}},
        }
        self.on_op = on_op
        self.ops: list[str] = []
        self.counts: dict[str, int] = {}
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(self.path))
        self.sock.listen(16)
        self.listening = True
        self._stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def close_listener(self) -> None:
        """Close the LISTENING socket and leave the socket file in place (round-12 #m12-1)."""
        if self.listening:
            self.listening = False
            try:
                self.sock.close()
            except OSError:
                pass

    def _serve(self) -> None:
        while not self._stop and self.listening:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn) -> None:
        buf = b""
        try:
            conn.settimeout(30)
            while b"\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk:
                    conn.close()
                    return
                buf += chunk
            req = json.loads(buf.split(b"\n", 1)[0])
            op = req.get("op")
            self.ops.append(op)
            self.counts[op] = self.counts.get(op, 0) + 1
            if self.on_op is not None and self.on_op(op, self.counts[op], conn, self):
                return
            ans = self.answers.get(op)
            if ans is None:
                conn.close()              # an op this peer does not serve: close, no reply
                return
            conn.sendall(json.dumps(ans).encode() + b"\n")
            conn.close()
        except OSError:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self) -> None:
        self._stop = True
        self.close_listener()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


def spawn_rmx_named_helper(tag: str = "rmx-sandbox-helper") -> subprocess.Popen:
    """A live process whose argv contains "rmx" (AC-2b busy precondition; AC-4b helpers)."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", tag],
                            env=clean_env())


def reaped_pid() -> int:
    """The pid of a child the test started and reaped: a pid that no longer exists."""
    p = subprocess.Popen([sys.executable, "-c", "pass"], env=clean_env())
    p.wait(timeout=30)
    return p.pid
