"""The test sandbox (task 23.0): ONE module for the pytest process, every child it spawns, and
the scripts that prove the suite left nothing behind.

Why it exists. bug-088: one full run made 72 in-process connects to live daemon/hub sockets, and
the record-only `_recording_connect` (conftest, 2026-10-07) could neither stop them nor see a
spawned `rmx` at all. bug-101: the suite wrote 143,108 `facts.log` events and 235 `query.log`
fixture rows into the LIVE global store, because it ran with the developer's real `$HOME`. Every
Wave 0 review asked for the same isolation (plan-review-2026-10-14 d1a/d1b), so it is built once.

Three shapes, each defined exactly once here (the user's standing rule, 2026-10-15: converge
repeated shapes into one function):

- `sandbox_env()`  -- the redirect of every HOME-derived path (R1). The conftest applies it to
  `os.environ` (`redirect()`); the spawn hook applies the SAME values to a child's env
  (`child_env()`).
- `violation()`    -- the deny rule (R3). The audit hook in the pytest process and the audit
  hook `sitecustomize.py` installs in every child call the same function over the same deny set
  (`<RMX_SANDBOX_ROOT>/deny.json`, written once by the process that captured the real paths).
- `child_env()`    -- the propagation of the sandbox into a child (R4), applied from the
  `subprocess.Popen` / `os.posix_spawn` / `os.exec` audit events, so a test that builds its own
  `env={...}` cannot launch an unsandboxed child by forgetting a key.

Rulings followed (plan-review-2026-10-14 d9bo, 2026-10-15): a violation is appended to a
per-test record AND raised, and the conftest fails any test whose record is non-empty, so an
`except Exception: pass` cannot swallow it; `SandboxViolation` is NOT an `OSError`; in a child
the hook writes the touches log and `os._exit(86)`; the test id comes from
`PYTEST_CURRENT_TEST`.

Limits, stated (not hidden): the audit hook sees what CPython audits. A C library that opens a
file itself (DuckDB's `duckdb.connect`, Lance) raises no `open` event, so a live catalog opened
ONLY through DuckDB is caught by the redirect (R1/R2), not by the refusal. `os.stat` /
`os.path.exists` are not audited either (a probe of existence is not refused).

This file must import under any Python 3 a test may spawn (a hook script's `/usr/bin/python3`
gets `sitecustomize` through PYTHONPATH too), so it uses no syntax newer than 3.8.
"""
from __future__ import annotations

import atexit
import json
import os
import plistlib
import pwd
import shutil
import sys
import tempfile
import threading
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent
DENY_FILE = "deny.json"
HUB_PORT = 7777
CHILD_EXIT = 86
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", "::",
                            "::ffff:127.0.0.1", "ip6-localhost"})
TOUCHES_REL = Path("workflow") / "review-output" / "live-socket-touches.log"
# Test modules whose refusals are DELIBERATE probes (AC-2/AC-3/R3). The proof wrapper's
# "touches log gains 0 lines" check (AC-4) excludes exactly these and nothing else.
DELIBERATE_PROBE_MODULES = ("tests/test_sandbox_refusal.py::", "tests/test_sandbox_children.py::")


class SandboxViolation(Exception):
    """A sandboxed process touched a live path. Deliberately NOT an `OSError` (d9bo #5): the
    suite and `src/` are full of `except OSError` best-effort sites that would eat it."""


# Per-test record of violations (d9bo #5), keyed by the pytest node id the violation happened
# under. The conftest pops its own test's entry in `pytest_runtest_makereport` and fails it.
RECORD: dict = {}
NO_TEST = "<no-test>"

_STATE = {"deny": None, "mode": "raise", "installed": False, "outer": None, "sandbox": None}
_local = threading.local()


# ---- R1: the real paths, captured before the redirect ------------------------------------


def real_home(env=None) -> Path:
    """The live home the deny set protects.

    `RMX_SANDBOX_REAL_HOME` first: a nested sandbox (a child pytest, a re-imported conftest)
    runs with `$HOME` already redirected and must still protect the OUTER home. Then the
    outer `$HOME`, which is how the AC-2/AC-3 mutation gates point the whole run at a decoy
    home with listening decoy sockets (d9bo #3). The password database last."""
    env = os.environ if env is None else env
    v = env.get("RMX_SANDBOX_REAL_HOME") or env.get("HOME")
    return Path(v) if v else Path(pwd.getpwuid(os.getuid()).pw_dir)


def _account_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def plist_roots(agents_dir: Path) -> list:
    """`REFMATRIX_ROOT` of every `com.refmatrix.daemon.*` plist (d8c counts 8 stores; the
    record-only guard knew none of them, viascope's included)."""
    out = []
    if not agents_dir.is_dir():
        return out
    for plist in sorted(agents_dir.glob("com.refmatrix.daemon.*.plist")):
        data = plistlib.loads(plist.read_bytes())
        r = (data.get("EnvironmentVariables") or {}).get("REFMATRIX_ROOT")
        if r:
            out.append(Path(r))
    return out


def registry_roots(registry: Path) -> list:
    """Every root in a `registry.json` (the shape `discovery.load_registry` reads)."""
    if not registry.is_file():
        return []
    data = json.loads(registry.read_text() or "[]")
    roots = data.get("roots", data) if isinstance(data, dict) else data
    return [Path(str(r)) for r in roots] if isinstance(roots, list) else []


def _variants(p: Path) -> set:
    """The path as named AND as resolved (`/tmp` vs `/private/tmp`), both matched."""
    out = {os.path.abspath(str(p))}
    try:
        out.add(os.path.realpath(str(p)))
    except OSError:
        pass
    return out


def build_deny(repo: Path, env=None) -> dict:
    """R3's ONE deny set, from the real paths. Read BEFORE the audit hook is installed (the
    registry and the plists name the stores the hook will then refuse)."""
    env = os.environ if env is None else env
    homes = [real_home(env)]
    if _account_home() not in homes:
        homes.append(_account_home())
    roots = {repo / ".refmatrix"}
    for h in homes:
        roots.add(h / ".refmatrix")
        roots.update(plist_roots(h / "Library" / "LaunchAgents"))
        roots.update(registry_roots(h / ".refmatrix" / "registry.json"))
    paths = set()
    for r in roots:
        paths |= _variants(r)
    ports = {HUB_PORT}
    if env.get("RMX_SANDBOX_HUB_PORT"):
        # The AC-2 mutation gate moves the hub-port probes onto a decoy listener (d9bo #3);
        # the real 7777 stays denied either way.
        ports.add(int(env["RMX_SANDBOX_HUB_PORT"]))
    return {"paths": sorted(paths), "ports": sorted(ports),
            "touches": str(repo / TOUCHES_REL)}


# ---- R1: the redirect --------------------------------------------------------------------


def make_root(env=None) -> Path:
    """ONE short root: `/tmp/rmx-[<tag>-]XXXXXXXX`, so `<root>/r/N/.refmatrix/rmxd.sock` stays
    far under macOS's ~104-byte `sun_path` (AC-5). The tag (AC-4's wrapper draws it) makes
    every sandbox path carry the run's mark."""
    env = os.environ if env is None else env
    tag = env.get("RMX_SANDBOX_TAG")
    prefix = f"rmx-{tag}-" if tag else "rmx-"
    root = Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp"))
    atexit.register(_remove_root, root)
    return root


def remove_tree(root: Path) -> None:
    """Remove a sandbox tree; what could not be removed is COUNTED on stderr, not dropped."""
    _remove_root(root)


def _remove_root(root: Path) -> None:
    if not root.exists():
        return
    failures: list = []
    if sys.version_info >= (3, 12):
        shutil.rmtree(root, onexc=lambda fn, p, exc: failures.append((p, exc)))
    else:
        shutil.rmtree(root, onerror=lambda fn, p, exc: failures.append((p, exc[1])))
    if failures:
        sys.stderr.write(f"rmx sandbox: {len(failures)} path(s) under {root} not removed; "
                         f"first: {failures[0]}\n")


def sandbox_env(root: Path, real: Path, base=None) -> dict:
    """THE redirect (R1): every variable that names a HOME-derived location, computed once.

    `HOME` moves first because `launchctl.LAUNCH_AGENTS_DIR` is computed at IMPORT time;
    `RMX_HOME` is the global store, registry, taxonomy and hub sockets; `REFMATRIX_ROOT` is a
    session default under the sandbox (the autouse fixture replaces it per test, R2); `PATH`
    pins `rmx` to the interpreter's own venv, never `~/bin/rmx` (the deploy build); the
    model cache stays the real one (read-only, offline) because the suite loads models.
    `PYTHONPATH` gains `tests/sandbox_site` so every child installs the same refusal (R4)."""
    base = os.environ if base is None else base
    home = root / "h"
    pp = [p for p in base.get("PYTHONPATH", "").split(os.pathsep) if p]
    if str(SITE_DIR) not in pp:
        pp.insert(0, str(SITE_DIR))
    venv_bin = os.path.dirname(sys.executable)
    path = [p for p in base.get("PATH", "").split(os.pathsep) if p and p != venv_bin]
    return {
        "HOME": str(home),
        "RMX_HOME": str(home / ".refmatrix"),
        "RMX_SANDBOX_ROOT": str(root),
        "RMX_SANDBOX_REAL_HOME": str(real),
        "REFMATRIX_ROOT": str(root / "r" / "session" / ".refmatrix"),
        "HF_HOME": base.get("HF_HOME") or str(real / ".cache" / "huggingface"),
        "PATH": os.pathsep.join([venv_bin] + path),
        "PYTHONPATH": os.pathsep.join(pp),
    }


def enter(repo: Path) -> dict:
    """Create the root, capture the real paths, write `deny.json`, turn the refusal ON.

    Called by the conftest BEFORE `redirect()` (R1: the real paths are captured first). A
    nested sandbox (the parent's `RMX_SANDBOX_ROOT` carries a `deny.json`) inherits the
    parent's deny set instead of re-reading the live registry, which the parent already
    denies.

    Once per PROCESS: `from tests.conftest import source_of` (two test modules do) executes
    the conftest a second time under another module name, and a second root mid-session
    would move `HOME` under every test that follows."""
    if _STATE["sandbox"] is not None:
        return _STATE["sandbox"]
    parent = os.environ.get("RMX_SANDBOX_ROOT")
    inherited = Path(parent) / DENY_FILE if parent else None
    if inherited is not None and inherited.is_file():
        deny = json.loads(inherited.read_text())
    else:
        deny = build_deny(repo)
    real = real_home()
    root = make_root()
    (root / "h" / ".refmatrix").mkdir(parents=True)
    (root / "r" / "session" / ".refmatrix").mkdir(parents=True)
    (root / DENY_FILE).write_text(json.dumps(deny, indent=1))
    Path(deny["touches"]).parent.mkdir(parents=True, exist_ok=True)
    install(deny, mode="raise")
    _STATE["sandbox"] = {"root": root, "real": real, "deny": deny}
    return _STATE["sandbox"]


def redirect(sb: dict) -> None:
    """Apply `sandbox_env()` to this process: the R1 env assignments, once per process (a
    second conftest execution must not reset a test's monkeypatched `REFMATRIX_ROOT`)."""
    if sb.get("redirected"):
        return
    os.environ.update(sandbox_env(sb["root"], sb["real"]))
    sb["redirected"] = True


def assert_under_sandbox(sb: dict, paths: dict) -> None:
    """Fail the session (pytest.UsageError) if any named path escaped the sandbox root."""
    root = os.path.realpath(str(sb["root"]))
    bad = {k: str(v) for k, v in paths.items()
           if not (os.path.realpath(str(v)) + "/").startswith(root + "/")}
    if bad:
        import pytest
        raise pytest.UsageError(
            f"sandbox: paths outside {root} after the redirect (was a refmatrix import moved "
            f"above it?): {bad}")


_counter = {"n": 0}


def new_store_root(root: Path) -> Path:
    """A fresh, existing per-test `.refmatrix` under the sandbox (R2; d9bo #7: the fixture
    creates it)."""
    _counter["n"] += 1
    d = root / "r" / str(_counter["n"]) / ".refmatrix"
    d.mkdir(parents=True)
    return d


# ---- R4: the child env -------------------------------------------------------------------


def child_env(env) -> None:
    """Propagate the sandbox into a child's env, IN PLACE (the spawn audit hook's job).

    Only adds; never overrides a key the test chose. `PYTHONPATH` always carries
    `sandbox_site` (the child's refusal). `HOME` comes with `RMX_HOME` and `HF_HOME` only
    when the test gave none: a child with no `HOME` resolves `Path.home()` from the password
    database, i.e. the live home; a test that set its own `HOME` meant `~/.refmatrix` to
    follow it, so `RMX_HOME` is left for it to derive."""
    if not isinstance(env, dict):
        return
    root = os.environ.get("RMX_SANDBOX_ROOT")
    if not root:
        return
    want = sandbox_env(Path(root), real_home(), base=os.environ)
    pp = [p for p in str(env.get("PYTHONPATH", "")).split(os.pathsep) if p]
    site_pp = [p for p in want["PYTHONPATH"].split(os.pathsep) if p == str(SITE_DIR)]
    for p in site_pp:
        if p not in pp:
            pp.insert(0, p)
    if pp:
        env["PYTHONPATH"] = os.pathsep.join(pp)
    for k in ("RMX_SANDBOX_ROOT", "RMX_SANDBOX_REAL_HOME"):
        env.setdefault(k, os.environ.get(k, want[k]))
    if "HOME" not in env:
        env["HOME"] = os.environ.get("HOME", want["HOME"])
        env.setdefault("RMX_HOME", os.environ.get("RMX_HOME", want["RMX_HOME"]))
        env.setdefault("HF_HOME", os.environ.get("HF_HOME", want["HF_HOME"]))


# ---- R3: the deny rule -------------------------------------------------------------------

# event -> indexes of the args that are paths. Reads AND writes (R3: "any open (write OR
# read), os.* mutation").
_PATH_EVENTS = {
    "open": (0,), "os.listdir": (0,), "os.scandir": (0,), "os.chdir": (0,),
    "os.remove": (0,), "os.rmdir": (0,), "os.mkdir": (0,), "os.rename": (0, 1),
    "os.link": (0, 1), "os.symlink": (0, 1), "os.truncate": (0,), "os.chmod": (0,),
    "os.chown": (0,), "os.utime": (0,), "os.chflags": (0,), "os.lchflags": (0,),
    "os.setxattr": (0,), "os.removexattr": (0,), "os.getxattr": (0,), "os.listxattr": (0,),
    "shutil.rmtree": (0,), "shutil.copyfile": (0, 1), "shutil.copymode": (0, 1),
    "shutil.copystat": (0, 1), "shutil.copytree": (0, 1), "shutil.move": (0, 1),
    "shutil.chown": (0,), "sqlite3.connect": (0,), "glob.glob": (0,),
    "pathlib.Path.glob": (0,), "pathlib.Path.rglob": (0,),
}
_SPAWN_EVENTS = {"subprocess.Popen": 3, "os.posix_spawn": 2, "os.exec": 2}


def _as_path(v) -> "str | None":
    if isinstance(v, bytes):
        v = os.fsdecode(v)
    elif isinstance(v, os.PathLike):
        v = os.fspath(v)
        if isinstance(v, bytes):
            v = os.fsdecode(v)
    if not isinstance(v, str) or not v or v.startswith("\0"):
        return None
    return os.path.abspath(v)


def _path_denied(path: str, deny_paths) -> bool:
    for d in deny_paths:
        if path == d or path.startswith(d + "/"):
            return True
    return False


def violation(event: str, args, deny: dict, dir_fd_relative: bool = False) -> "str | None":
    """THE deny rule: the live target this event touches, or None.

    Pure: no I/O, no audited call (it runs inside the audit hook). `dir_fd_relative`: the
    caller opens bare names relative to a directory DESCRIPTOR (shutil's fd-based rmtree and
    copytree), which the `open` audit event does not carry, so a relative name cannot be
    resolved against the cwd. Found 2026-10-15 on the first GREEN run: the sandbox's own
    cleanup `rmtree` opened its `.refmatrix` subdir by bare name with the cwd at the repo and
    read as the repo's live store. The absolute root of that traversal is checked by the
    `shutil.rmtree` / `shutil.copytree` event itself."""
    idx = _PATH_EVENTS.get(event)
    if idx is not None:
        for i in idx:
            if i < len(args):
                raw = args[i]
                if dir_fd_relative and isinstance(raw, (str, bytes)) and not os.path.isabs(raw):
                    continue
                p = _as_path(raw)
                if p is not None and _path_denied(p, deny["paths"]):
                    return p
        return None
    if event == "socket.connect" and len(args) >= 2:
        addr = args[1]
        if isinstance(addr, tuple) and len(addr) >= 2:
            host, port = addr[0], addr[1]
            if isinstance(host, bytes):
                host = host.decode(errors="replace")
            if (isinstance(host, str) and isinstance(port, int) and port in deny["ports"]
                    and (host.lower() in LOOPBACK_HOSTS or host.startswith("127."))):
                return f"{host}:{port}"
            return None
        p = _as_path(addr)
        if p is not None and _path_denied(p, deny["paths"]):
            return p
    return None


_FD_WALKERS = (os.sep + "shutil.py",)


def _caller_is_fd_walker() -> bool:
    """True when the Python frame that triggered the event is in `shutil` (fd-relative
    traversal; see `violation`). Frame 0 is this function, 1 the hook, 2 the caller of the
    audited C function."""
    try:
        f = sys._getframe(2)
    except ValueError:
        return False
    return f.f_code.co_filename.endswith(_FD_WALKERS)


def current_test() -> str:
    cur = os.environ.get("PYTEST_CURRENT_TEST")
    if not cur:
        return NO_TEST
    return cur.rsplit(" (", 1)[0] if cur.endswith(")") else cur


def set_outer_test(nodeid: "str | None") -> None:
    """The conftest's own item: an in-process `pytester` inner test overwrites
    `PYTEST_CURRENT_TEST`, and the touches log names both."""
    _STATE["outer"] = nodeid


def _touch_line(event: str, target: str, test_id: str) -> str:
    outer = _STATE["outer"] or test_id
    return f"{os.getpid()}\t{test_id}\t{outer}\t{event}\t{target}\n"


def _hook(event, args):
    deny = _STATE["deny"]
    if deny is None or getattr(_local, "busy", False):
        return
    spawn_idx = _SPAWN_EVENTS.get(event)
    if spawn_idx is not None:
        if spawn_idx < len(args):
            _local.busy = True
            try:
                child_env(args[spawn_idx])
            finally:
                _local.busy = False
        return
    if event != "socket.connect" and event not in _PATH_EVENTS:
        return
    target = violation(event, args, deny, dir_fd_relative=_caller_is_fd_walker())
    if target is None:
        return
    _local.busy = True
    try:
        test_id = current_test()
        line = _touch_line(event, target, test_id)
        with open(deny["touches"], "a") as fh:
            fh.write(line)
        msg = (f"{event} on live target {target} (test {test_id}; "
               f"sandbox {os.environ.get('RMX_SANDBOX_ROOT')})")
        if _STATE["mode"] == "exit":
            sys.stderr.write(f"SandboxViolation: {msg}\n")
            sys.stderr.flush()
            os._exit(CHILD_EXIT)
        RECORD.setdefault(test_id, []).append(f"{event} {target}")
    finally:
        _local.busy = False
    raise SandboxViolation(msg)


def install(deny: dict, mode: str) -> None:
    """Install the audit hook once per process; later calls replace the deny set and mode
    (a child pytest's conftest switches its sitecustomize hook from `exit` to `raise`).
    Audit hooks cannot be removed, which is the point."""
    _STATE["deny"] = deny
    _STATE["mode"] = mode
    if not _STATE["installed"]:
        sys.addaudithook(_hook)
        _STATE["installed"] = True


def install_from_env() -> None:
    """The child side (R4, `sitecustomize.py`): the SAME hook from `RMX_SANDBOX_ROOT`, in exit
    mode. Fail closed: a child that carries the sandbox site but cannot find its deny set
    exits rather than running unguarded."""
    root = os.environ.get("RMX_SANDBOX_ROOT")
    deny_file = Path(root) / DENY_FILE if root else None
    if deny_file is None or not deny_file.is_file():
        sys.stderr.write(
            f"SandboxViolation: tests/sandbox_site is on PYTHONPATH but no deny set at "
            f"{deny_file} (RMX_SANDBOX_ROOT={root!r}); refusing to run unguarded\n")
        sys.stderr.flush()
        os._exit(CHILD_EXIT)
    deny = json.loads(deny_file.read_text())
    extra = os.environ.get("RMX_SANDBOX_DENY_EXTRA", "")
    if extra:
        # Additive only: a test can name one more path to refuse (AC-3(b)'s decoy store,
        # d9bo #4), never fewer.
        add = set()
        for p in extra.split(os.pathsep):
            if p:
                add |= _variants(Path(p))
        deny = dict(deny, paths=sorted(set(deny["paths"]) | add))
    install(deny, mode="exit")


# ---- AC-4: the content check over live logs ---------------------------------------------


def leak_reasons(line: str, tag: str, log_name: str) -> list:
    """Why one delta line of a live log is a sandbox leak (ns23-2: content, not size/mtime).

    A leaked row carries the run's tag (every sandbox path does), a pytest temp path, or --
    for `query.log` -- the d9g fixture shape: a learn/grep row whose body has `alpha|beta`
    and no `cwd`. Live activity carries none of these."""
    out = []
    # The tag as it appears in a sandbox path (`rmx-<tag>-`), never the bare 6 hex digits,
    # which a sha in an unrelated facts.log row matches by chance.
    if tag and f"rmx-{tag}-" in line:
        out.append("run tag")
    if "/pytest-of-" in line:
        out.append("pytest temp path")
    if log_name == "query.log":
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        if (isinstance(row, dict) and str(row.get("kind", "")) in ("learn", "grep")
                and "alpha|beta" in str(row.get("body", "")) and not row.get("cwd")):
            out.append("d9g fixture shape")
    return out


def snapshot(paths) -> dict:
    """`(inode, size)` of each log; a missing log is `(0, 0)`."""
    out = {}
    for p in paths:
        try:
            st = os.stat(p)
            out[str(p)] = [st.st_ino, st.st_size]
        except FileNotFoundError:
            out[str(p)] = [0, 0]
    return out


def delta_lines(path: str, before) -> list:
    """Bytes past the recorded size; the WHOLE file if the inode changed (a compaction
    rewrote it) or it shrank."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return []
    ino, size = before
    start = size if (st.st_ino == ino and st.st_size >= size) else 0
    with open(path, "rb") as fh:
        fh.seek(start)
        return fh.read().decode(errors="replace").splitlines()


def check_logs(snap: dict, tag: str, touches: str, touches_size: int) -> int:
    """Print one report line per log; return the number of offending rows (logs + touches)."""
    bad_total = 0
    for path, before in snap.items():
        lines = delta_lines(path, before)
        name = os.path.basename(path)
        bad = [(ln, leak_reasons(ln, tag, name)) for ln in lines]
        bad = [(ln, r) for ln, r in bad if r]
        print(f"{path}: delta_lines={len(lines)} failed_rows={len(bad)}")
        for ln, reasons in bad[:5]:
            print(f"  LEAK in {path} ({', '.join(reasons)}): {ln[:300]}")
        bad_total += len(bad)
    unexpected = []
    if os.path.exists(touches):
        with open(touches, "rb") as fh:
            fh.seek(touches_size if os.path.getsize(touches) >= touches_size else 0)
            for ln in fh.read().decode(errors="replace").splitlines():
                parts = ln.split("\t")
                outer = parts[2] if len(parts) >= 5 else ln
                if not outer.startswith(DELIBERATE_PROBE_MODULES):
                    unexpected.append(ln)
    print(f"{touches}: unexpected_new_lines={len(unexpected)}")
    for ln in unexpected[:5]:
        print(f"  TOUCH {ln}")
    return bad_total + len(unexpected)


def _main(argv) -> int:
    """`python rmx_sandbox.py snapshot OUT LOG...` / `check SNAP TAG TOUCHES TOUCHES_SIZE`.
    The shell wrappers (sandbox-proof.sh, the lane scripts) call these; the logic lives
    here once."""
    if len(argv) >= 3 and argv[0] == "snapshot":
        Path(argv[1]).write_text(json.dumps(snapshot(argv[2:])))
        return 0
    if len(argv) == 5 and argv[0] == "check":
        snap = json.loads(Path(argv[1]).read_text())
        n = check_logs(snap, argv[2], argv[3], int(argv[4]))
        print(f"sandbox-proof: {n} offending row(s)")
        return 1 if n else 0
    sys.stderr.write("usage: rmx_sandbox.py snapshot OUT LOG... | "
                     "check SNAP TAG TOUCHES TOUCHES_SIZE\n")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
