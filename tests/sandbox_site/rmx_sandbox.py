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

ch-bsd r1 (2026-10-15) added: the spawn rule (`spawn_violation()`: no spawn whose cwd is in
a denied root, no mutating `launchctl`, no `kill` of a live pid) shared by the audit hook and
the `bin/launchctl` shim; `os.kill` / `os.killpg` of a live daemon or hub pid (captured at
`enter()` from their pid files) refused; probe ownership (`PROBE_ENV`) in place of a module
allowlist; and the narrowed fd-walk exemption (`violation()`).

Limits, stated (not hidden): the audit hook sees what CPython audits. A C library that opens a
file itself (DuckDB's `duckdb.connect`, Lance) raises no `open` event, so a live catalog opened
ONLY through DuckDB is caught by the redirect (R1/R2), not by the refusal. `os.stat` /
`os.path.exists` are not audited either (a probe of existence is not refused). A non-Python
process is seen only through the `launchctl` shim on `PATH`: a shell's builtin `kill`, an
absolute `/bin/launchctl` from a shell script, `pkill` / `killall` by name, and `lsof` are not
refused. A pid captured at `enter()` that is reused later is refused too (a spurious failure,
never a reach).

This file must import under any Python 3 a test may spawn (a hook script's `/usr/bin/python3`
gets `sitecustomize` through PYTHONPATH too), so it uses no syntax newer than 3.8.
"""
from __future__ import annotations

import atexit
import glob
import json
import os
import plistlib
import re
import pwd
import runpy
import shlex
import shutil
import signal
import socket
import struct
import sys
import tempfile
import threading
import time
import weakref
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent
DENY_FILE = "deny.json"
HUB_PORT = 7777
# The two child exit codes, named once. Plans 19 (19.0 AC-6f) and 21 (21.3 AC-5) assert "a
# deny-set dial exits 86" in their control legs, so 86 is an interface, not a detail.
CHILD_EXIT = 86      # a child touched a deny-set target (or has no deny set): refused
PRELOAD_EXIT = 87    # the $RMX_SANDBOX_PRELOAD script raised (or is not an absolute .py)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", "::",
                            "::ffff:127.0.0.1", "ip6-localhost"})
TOUCHES_REL = Path("workflow") / "review-output" / "live-socket-touches.log"
# Live-log GROWTH seen by a per-test guard (21.1 r2 #s2, bug-134): the test process only
# stats a live log -- it may never open one (the audit hook refuses it) -- so each growth is
# recorded here as `{path, ino, start, end, nodeid, markers}` and attributed ONCE, by the
# end-of-run content check (`check_logs`), outside any sandboxed process.
GROWTH_REL = Path("workflow") / "review-output" / "live-log-growth.jsonl"
# A DELIBERATE refusal (a test marked `sandbox_probe`, or code inside
# `expect_sandbox_violation()`) runs with this variable set to the OWNER's test id; every
# touches-log line written then -- in-process or by a child, which inherits it -- carries that
# owner in its sixth field. AC-4's "touches log gains 0 lines" check excludes owned lines; the
# conftest's child-touch check excludes only lines the test ITSELF owns (an in-process inner
# test under a probe is not a probe). This replaced a module allowlist
# (`DELIBERATE_PROBE_MODULES`, ch-bsd r1 m2/s1, 2026-10-15): an accidental touch by ANY test
# in those three modules was excluded too.
PROBE_ENV = "RMX_SANDBOX_PROBE"
# `tests/sandbox_site/bin/`: the `launchctl` shim (S6), first on the sandbox `PATH`.
BIN_DIR = SITE_DIR / "bin"
HUB_PID = "hub.pid"          # refmatrix.hub.HUB_PID, under the real `~/.refmatrix/`
DAEMON_PID = "rmxd.pid"      # every store root's daemon pid file
# `launchctl` subcommands that change nothing (ch-bsd r1 s6): everything else -- bootout,
# bootstrap, kickstart, load, unload, enable, disable, kill, remove, submit, ... -- is refused.
# `HUB_LABEL` and the daemon labels are GLOBAL, so a sandboxed `install_hub` would boot out
# the LIVE hub whatever `HOME` says.
LAUNCHCTL_READ_ONLY = frozenset({"print", "print-cache", "print-disabled", "list", "blame",
                                 "help", "version", "error", "managerpid", "manageruid",
                                 "managername", "hostinfo", "getenv"})


class SandboxViolation(Exception):
    """A sandboxed process touched a live path. Deliberately NOT an `OSError` (d9bo #5): the
    suite and `src/` are full of `except OSError` best-effort sites that would eat it."""


# Per-test record of violations (d9bo #5), keyed by the pytest node id the violation happened
# under. The conftest pops its own test's entry in `pytest_runtest_makereport` and fails it.
RECORD: dict = {}
NO_TEST = "<no-test>"

_STATE = {"deny": None, "mode": "raise", "installed": False, "outer": None, "sandbox": None,
          "connect_log": None, "ledger": None, "at_fork": False, "session": None}
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


def read_pid(path: Path) -> "int | None":
    """The pid in a `rmxd.pid` / `hub.pid` (first token), or None when there is no file. A file
    that exists but does not parse is NAMED on stderr, not dropped silently."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    except OSError as exc:
        sys.stderr.write(f"rmx sandbox: cannot read pid file {path}: {exc}\n")
        return None
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        sys.stderr.write(f"rmx sandbox: pid file {path} does not hold a pid: {text[:40]!r}\n")
        return None


def live_pids(roots, homes) -> list:
    """The live processes a test must never signal (ch-bsd r1 s6): every store root's daemon
    (`rmxd.pid`) and every protected home's hub (`~/.refmatrix/hub.pid`). Read with the real
    paths, BEFORE the redirect and before the hook refuses those directories."""
    out = set()
    for f in [Path(r) / DAEMON_PID for r in roots] + [Path(h) / ".refmatrix" / HUB_PID
                                                     for h in homes]:
        pid = read_pid(f)
        if pid is not None and pid > 0:
            out.add(pid)
    return sorted(out)


LSOF = "/usr/sbin/lsof"


def listener_pids(ports) -> list:
    """The pids LISTENING on each TCP port, from `lsof -nP -t -iTCP:<p> -sTCP:LISTEN` (ch-bsd r2,
    2026-10-15): the live hub writes no `hub.pid` on this host, so the pid files alone left it
    signalable. lsof exits 1 with no output when nothing listens (not a failure); any other
    failure is PRINTED and the run proceeds with the pid-file pids only."""
    import subprocess
    out = set()
    for port in sorted(ports):
        argv = [LSOF, "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"]
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as exc:
            sys.stderr.write(f"rmx sandbox: {' '.join(argv)} failed ({exc}); listener pids for "
                             f"port {port} NOT captured, pid files only\n")
            continue
        if r.returncode not in (0, 1) or (r.returncode == 1 and r.stderr.strip()):
            sys.stderr.write(f"rmx sandbox: {' '.join(argv)} exited {r.returncode}: "
                             f"{r.stderr.strip()[:200]}; listener pids for port {port} NOT "
                             f"captured, pid files only\n")
            continue
        for tok in r.stdout.split():
            try:
                out.add(int(tok))
            except ValueError:
                sys.stderr.write(f"rmx sandbox: lsof printed a non-pid {tok!r} for port "
                                 f"{port}\n")
    return sorted(out)


def build_deny(repo: Path, env=None) -> dict:
    """R3's ONE deny set, from the real paths. Read BEFORE the audit hook is installed (the
    registry and the plists name the stores the hook will then refuse). `pids` (S6): the live
    daemons and hubs those paths name, plus whatever listens on a deny port (`lsof`), which
    `os.kill` / a spawned `kill` may not signal."""
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
            "pids": sorted(set(live_pids(sorted(roots), homes)) | set(listener_pids(ports))),
            "touches": str(repo / TOUCHES_REL),
            "read_allow": read_allow(repo)}


# The ONE file under a live `.refmatrix/` a test may READ (bug-230, 2026-11-14): this
# checkout's own ignore spec, which bug-216 R3's scope-parity step (`scripts/check-gmd-parity.py`
# -> `ingest.ignore_reason`) must read for `scripts/lint-gmd.sh` to judge the repo. It is
# configuration, not store data: a read-only open of it cannot lock a catalog, write a row or
# reach a socket. Read-only opens of exactly these paths are allowed (`violation`); a write-mode
# open, any `os.*` mutation of it, and every other file under the store stay denied.
#
# bsd-216 bug-230 r1 #m1: `_variants` adds the realpath, so a spec that is a SYMLINK put its
# target (e.g. `catalog.A.duckdb`) into the allow. A symlinked spec gets NO allow: an open of the
# link reads whatever it names, so no read through it is safe to wave through, and the gate then
# fails loudly (exit 86, which the exit-0 verdict reports) instead of reading a stand-in. For a
# regular file only the variants that are still the spec itself are kept (`/tmp` vs
# `/private/tmp`, or a symlinked `.refmatrix/` dir), never a different file name.
def read_allow(repo: Path) -> list:
    spec = Path(repo) / ".refmatrix" / ".refmatrix_ignore"
    if spec.is_symlink():
        return []
    return sorted(v for v in _variants(spec) if os.path.basename(v) == ".refmatrix_ignore")


# ---- R1: the redirect --------------------------------------------------------------------


def make_root(env=None) -> Path:
    """ONE short root: `/tmp/rmx-[<tag>-]XXXXXXXX`, so `<root>/r/N/.refmatrix/rmxd.sock` stays
    far under macOS's ~104-byte `sun_path` (AC-5). The tag (AC-4's wrapper draws it) makes
    every sandbox path carry the run's mark."""
    env = os.environ if env is None else env
    tag = env.get("RMX_SANDBOX_TAG")
    prefix = f"rmx-{tag}-" if tag else "rmx-"
    # RESOLVED (`/private/tmp/...` on macOS): code that compares a resolved cwd with an
    # unresolved `Path.home()` (cli._root_from_projects_slug) mis-resolved under `/tmp`'s
    # symlink, which no real home has (found 2026-10-15 in the first full sandboxed run).
    root = Path(os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir="/tmp")))
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
    pins `rmx` to the interpreter's own venv, never `~/bin/rmx` (the deploy build), then
    `BIN_DIR`'s `launchctl` shim (S6: a non-Python `launchctl bootout` is refused too); the
    model cache stays the real one (read-only, offline) because the suite loads models.
    `PYTHONPATH` gains `tests/sandbox_site` so every child installs the same refusal (R4)."""
    base = os.environ if base is None else base
    home = root / "h"
    pp = [p for p in base.get("PYTHONPATH", "").split(os.pathsep) if p]
    if str(SITE_DIR) not in pp:
        pp.insert(0, str(SITE_DIR))
    venv_bin = os.path.dirname(sys.executable)
    path = [p for p in base.get("PATH", "").split(os.pathsep)
            if p and p not in (venv_bin, str(BIN_DIR))]
    return {
        "HOME": str(home),
        "RMX_HOME": str(home / ".refmatrix"),
        "RMX_SANDBOX_ROOT": str(root),
        "RMX_SANDBOX_REAL_HOME": str(real),
        "REFMATRIX_ROOT": str(root / "r" / "session" / ".refmatrix"),
        "HF_HOME": base.get("HF_HOME") or str(real / ".cache" / "huggingface"),
        # The venv stays FIRST (code under test pins it there, `subproc._worker_env`); the shim
        # dir is second, ahead of `/bin` -- the venv carries no `launchctl`.
        "PATH": os.pathsep.join([venv_bin, str(BIN_DIR)] + path),
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
    # 29.4 R4 items 1 and 3: this process's forks write to THIS sandbox's ledger from now on
    # (an inner pytest's sitecustomize pointed it at the parent's), and `owner.json` lets the
    # next session tell a killed run's sandbox from a live one.
    _STATE["ledger"] = str(root / LEDGER)
    _register_at_fork()
    write_owner(root)
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
    # The attribution travels too (ch-bsd r1 s1/s3): a child given `env={"PATH": ...}` would
    # otherwise log its refusal as `<no-test>`, which no test's child-touch check reads.
    for k in (PROBE_ENV, "PYTEST_CURRENT_TEST"):
        if os.environ.get(k):
            env.setdefault(k, os.environ[k])
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
# event -> (argv index, cwd index or None). The env (R4) is the last argument of each.
_SPAWN_EVENTS = {"subprocess.Popen": (1, 2), "os.posix_spawn": (1, None),
                 "os.exec": (1, None)}
_SPAWN_ENV = {"subprocess.Popen": 3, "os.posix_spawn": 2, "os.exec": 2}
_KILL_EVENTS = ("os.kill", "os.killpg")
# shutil's fd-based tree walk (3.12-3.14): it opens, unlinks and rmdirs entries by BARE NAME
# relative to a directory DESCRIPTOR, which the `open` / `os.*` audit events do not carry.
_FD_WALK_FUNCS = frozenset({"_rmtree_safe_fd", "_rmtree_safe_fd_step"})
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_CMD_LEAD = frozenset({";", "&&", "||", "|", "&", "(", "then", "do", "else", "exec",
                       "command", "env", "nohup", "time"})


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


_WRITE_FLAGS = (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
                | getattr(os, "O_EXCL", 0))


def _read_only_open(args) -> bool:
    """An `open` audit event (`path, mode, flags`) that opens for reading only. Unknown flags
    are NOT read-only: the allow applies only when the event proves the open cannot write."""
    flags = args[2] if len(args) > 2 else None
    if not isinstance(flags, int) or flags & _WRITE_FLAGS:
        return False
    mode = args[1] if len(args) > 1 else None
    return mode is None or (isinstance(mode, str) and not any(c in mode for c in "wax+"))


def _path_denied(path: str, deny_paths) -> bool:
    for d in deny_paths:
        if path == d or path.startswith(d + "/"):
            return True
    return False


def _bare_name(raw) -> bool:
    """A single directory entry name (no separator): what an fd-relative walk passes."""
    if isinstance(raw, bytes):
        return b"/" not in raw
    return isinstance(raw, str) and os.sep not in raw


def _argv(v) -> list:
    if isinstance(v, (str, bytes, os.PathLike)):
        v = [v]
    out = []
    try:
        for a in v:
            if isinstance(a, (bytes, os.PathLike)):
                a = os.fsdecode(os.fspath(a))
            out.append(str(a))
    except TypeError:
        return []
    return out


def _commands(argv: list) -> list:
    """Each command an argv runs: the argv itself, plus every command of a `sh -c` script
    (split with shell punctuation, so `a; launchctl bootout x` yields the second)."""
    cmds = [argv]
    if argv and os.path.basename(argv[0]) in _SHELLS and "-c" in argv[1:]:
        i = argv.index("-c", 1)
        if i + 1 < len(argv):
            lex = shlex.shlex(argv[i + 1], posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            try:
                toks = list(lex)
            except ValueError:
                toks = argv[i + 1].split()
            cur: list = []
            for t in toks + [";"]:
                if t in _CMD_LEAD:
                    if cur:
                        cmds.append(cur)
                    cur = []
                elif "=" in t and not cur:
                    continue                     # `VAR=val cmd ...`
                else:
                    cur.append(t)
    return cmds


def _kill_targets(args: list) -> "list | None":
    """The pids a `kill` argv signals, or None for signal 0 / a listing (they change
    nothing). `kill -1 PID` is SIGHUP to PID; a `-1` AFTER the options is every process."""
    rest = list(args)
    while rest and rest[0].startswith("-") and rest[0] != "--":
        opt = rest.pop(0)
        if opt in ("-l", "-L"):
            return None
        if opt in ("-s", "-n"):
            if rest and rest.pop(0) == "0":
                return None
        elif opt[1:] in ("0", "s0"):
            return None
        break
    if rest and rest[0] == "--":
        rest.pop(0)
    out = []
    for a in rest:
        try:
            out.append(int(a))
        except ValueError:
            continue
    return out


def _signal_violation(pid: int, sig, deny: dict) -> "str | None":
    """Signal 0 (an existence probe) is allowed; any other signal to a live pid, to the group
    of one (`-pid`), or to every process (`-1`) is refused."""
    try:
        if int(sig) == 0:
            return None
    except (TypeError, ValueError):
        pass
    pids = deny.get("pids") or ()
    if pid == -1:
        return "pid -1 (every process)"
    if pid in pids or (pid < -1 and -pid in pids):
        return f"pid {pid}"
    return None


def spawn_violation(argv, cwd, deny: dict) -> "str | None":
    """THE spawn rule (ch-bsd r1 s6, m4), shared by the audit hook (every Python spawn) and the
    `launchctl` shim (every shell spawn that finds the shim on `PATH`): a child may not start
    with its cwd inside a denied root, run a mutating `launchctl` verb, or `kill` a live pid."""
    if cwd is not None:
        p = _as_path(cwd)
        if p is not None and _path_denied(p, deny["paths"]):
            return f"cwd {p}"
    for cmd in _commands(_argv(argv)):
        if not cmd:
            continue
        name = os.path.basename(cmd[0])
        if name == "launchctl":
            verb = cmd[1] if len(cmd) > 1 else ""
            if verb not in LAUNCHCTL_READ_ONLY:
                return f"launchctl {verb or '(no verb)'}"
        elif name == "kill":
            for pid in _kill_targets(cmd[1:]) or ():
                v = _signal_violation(pid, 15, deny)
                if v is not None:
                    return f"kill {v}"
    return None


def violation(event: str, args, deny: dict, fd_walk: bool = False) -> "str | None":
    """THE deny rule: the live target this event touches, or None.

    Pure: no I/O, no audited call (it runs inside the audit hook). `fd_walk`: the event was
    raised from shutil's fd-based tree walk (`_FD_WALK_FUNCS`), which opens entries by bare
    name relative to a directory DESCRIPTOR the event does not carry, so a bare name cannot be
    resolved against the cwd. Found 2026-10-15 on the first GREEN run: the sandbox's own
    cleanup `rmtree` opened its `.refmatrix` subdir by bare name with the cwd at the repo and
    read as the repo's live store. The exemption is that narrow and no wider (ch-bsd r1 b1:
    it once covered every relative path raised anywhere in `shutil.py`, so
    `shutil.copyfile(".refmatrix/catalog.read.duckdb", x)` from the repo cwd went through
    unrefused and unlogged): it never applies to a `shutil.*` event -- whose path is the
    walk's root, checked here -- nor to a name with a separator."""
    idx = _PATH_EVENTS.get(event)
    if idx is not None:
        allow = deny.get("read_allow")
        if allow and event == "open" and args and _read_only_open(args):
            p = _as_path(args[0])
            if p is not None and p in allow:
                return None                     # bug-230: the repo's ignore spec, read only
        exempt = fd_walk and (event == "open" or event.startswith("os."))
        for i in idx:
            if i < len(args):
                raw = args[i]
                if exempt and _bare_name(raw):
                    continue
                p = _as_path(raw)
                if p is not None and _path_denied(p, deny["paths"]):
                    return p
        return None
    if event in _KILL_EVENTS and len(args) >= 2 and isinstance(args[0], int):
        pid = args[0]
        if event == "os.killpg" and pid > 1:
            pid = -pid                        # the group, as `kill -PGID` names it
        return _signal_violation(pid, args[1], deny)
    spawn = _SPAWN_EVENTS.get(event)
    if spawn is not None:
        ai, ci = spawn
        argv = args[ai] if ai < len(args) else None
        cwd = args[ci] if ci is not None and ci < len(args) else None
        return spawn_violation(argv if argv is not None else (), cwd, deny)
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


def _in_fd_walk() -> bool:
    """True when the Python frame that raised the event is shutil's fd-based walk (see
    `violation`), identified by FUNCTION, not by file: frame 0 is this function, 1 the hook,
    2 the caller of the audited C function."""
    try:
        f = sys._getframe(2)
    except ValueError:
        return False
    return (f.f_code.co_name in _FD_WALK_FUNCS
            and f.f_code.co_filename.endswith(os.sep + "shutil.py"))


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
    """`pid  test  outer  event  target  owner` -- owner is the test id of the deliberate probe
    this ran under (`PROBE_ENV`), else `-`."""
    outer = _STATE["outer"] or test_id
    owner = (os.environ.get(PROBE_ENV) or "-").replace("\t", " ")
    return f"{os.getpid()}\t{test_id}\t{outer}\t{event}\t{target}\t{owner}\n"


def parse_touch(line: str) -> "dict | None":
    """One touches-log line as fields (the ONE parser: the AC-4 check and the conftest's
    child-touch check both read it). Lines written before the flag field have none."""
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 5:
        return None
    try:
        pid = int(parts[0])
    except ValueError:
        return None
    owner = parts[5] if len(parts) > 5 and parts[5] not in ("", "-") else None
    return {"pid": pid, "test": parts[1], "outer": parts[2], "event": parts[3],
            "target": parts[4], "probe": owner is not None, "owner": owner}


def touches_size(deny: dict) -> int:
    try:
        return os.path.getsize(deny["touches"])
    except FileNotFoundError:
        return 0


def touches_since(path: str, since: int) -> list:
    """Touches-log lines past byte `since` (all of them if the log shrank)."""
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return []
    with open(path, "rb") as fh:
        fh.seek(since if size >= since else 0)
        return fh.read().decode(errors="replace").splitlines()


def child_touches(path: str, since: int, nodeid: str, own_pid: int) -> list:
    """ch-bsd r1 s1: refusals a CHILD of test `nodeid` logged since `since` that were not
    deliberate. A child exits `CHILD_EXIT`; a spawner that ignores the code (a best-effort
    hook, `check=False`, a detached daemon) would otherwise let the test pass."""
    out = []
    for ln in touches_since(path, since):
        t = parse_touch(ln)
        if (t is not None and t["pid"] != own_pid and t["owner"] != nodeid
                and nodeid in (t["test"], t["outer"])):
            out.append(ln)
    return out


# Which outer test an in-process `pytester` inner test's record belongs to (ch-bsd r1 s2): the
# inner key is never popped by the outer report hook, so it is collected through this map.
RECORD_OUTER: dict = {}


def take_record(nodeid: str) -> tuple:
    """Pop `nodeid`'s own violations and those of any in-process inner test run under it:
    `(own, inner)`."""
    own = RECORD.pop(nodeid, None) or []
    inner = []
    for k in [k for k, o in RECORD_OUTER.items() if o == nodeid]:
        del RECORD_OUTER[k]
        inner += [f"{k}: {h}" for h in RECORD.pop(k, None) or []]
    return own, inner


def drain_record() -> dict:
    """Everything still recorded (ch-bsd r1 s2: `pytest_sessionfinish` fails on ANY leftover,
    not only `NO_TEST`), emptied."""
    left = {k: v for k, v in RECORD.items() if v}
    RECORD.clear()
    RECORD_OUTER.clear()
    return left


class probe_scope:
    """Mark everything inside as a DELIBERATE refusal probe owned by test `owner`:
    `PROBE_ENV` is set, so each touches-log line (this process's, and every child's -- it
    inherits the variable) names the owner. Used by the `sandbox_probe` marker (whole test)
    and by `expect_sandbox_violation()` (one block). `owner=None` is a no-op scope."""

    def __init__(self, owner: "str | None"):
        self.enabled = bool(owner)
        self.owner = owner
        self.prev = None

    def __enter__(self):
        if self.enabled:
            self.prev = os.environ.get(PROBE_ENV)
            os.environ[PROBE_ENV] = str(self.owner)
        return self

    def __exit__(self, *exc):
        if self.enabled:
            if self.prev is None:
                os.environ.pop(PROBE_ENV, None)
            else:
                os.environ[PROBE_ENV] = self.prev
        return False


class expect_sandbox_violation:
    """`with expect_sandbox_violation() as got:` -- the block MUST trigger at least one
    in-process refusal (ch-bsd r1 m5). Inside it the refusal is a probe (flagged lines); the
    raise is caught here, and the block's record entries are consumed, so the conftest does
    not flip the test. `got` lists the refusals. No refusal -> AssertionError. Any other
    exception propagates."""

    def __init__(self):
        self.got: list = []

    def __enter__(self):
        self._test = current_test()
        self._before = len(RECORD.get(self._test, []))
        self._scope = probe_scope(os.environ.get(PROBE_ENV) or self._test)
        self._scope.__enter__()
        return self.got

    def __exit__(self, etype, exc, tb):
        self._scope.__exit__(etype, exc, tb)
        hits = RECORD.get(self._test, [])
        self.got.extend(hits[self._before:])
        del hits[self._before:]
        if not hits:
            RECORD.pop(self._test, None)
        if etype is not None and not issubclass(etype, SandboxViolation):
            return False
        if not self.got:
            raise AssertionError("expected a SandboxViolation in this block; none was raised")
        return True


def _hook(event, args):
    deny = _STATE["deny"]
    if deny is None or getattr(_local, "busy", False):
        return
    env_idx = _SPAWN_ENV.get(event)
    if env_idx is not None and env_idx < len(args):
        _local.busy = True
        try:
            child_env(args[env_idx])
        finally:
            _local.busy = False
    if (env_idx is None and event not in _KILL_EVENTS and event != "socket.connect"
            and event not in _PATH_EVENTS):
        return
    if event == "socket.connect" and _STATE["connect_log"]:
        _log_unix_connect(args)
    target = violation(event, args, deny, fd_walk=_in_fd_walk())
    if target is None:
        return
    _refuse(event, target, deny)


def _refuse(event: str, target: str, deny: dict) -> None:
    """Log the touch, then: exit `CHILD_EXIT` (a child), or record it and raise (pytest)."""
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
        if _STATE["outer"] and _STATE["outer"] != test_id:
            RECORD_OUTER[test_id] = _STATE["outer"]
    finally:
        _local.busy = False
    raise SandboxViolation(msg)


def _log_unix_connect(args) -> None:
    """`$RMX_SANDBOX_CONNECT_LOG`: one `path<TAB>pid` line per AF_UNIX connect, written BEFORE
    the deny check so a refused dial is logged too (ch-bsd plan-19/21 r9 s9-3, r10 s10-3).

    It lives in THIS hook because CPython imports only the first `sitecustomize` on the path:
    plan-19's 19.0 AC-6f cannot ship a second one, so the connect census converges here."""
    if len(args) < 2 or getattr(args[0], "family", None) != socket.AF_UNIX:
        return
    path = _as_path(args[1])
    if path is None:
        return
    _local.busy = True
    try:
        with open(_STATE["connect_log"], "a") as fh:
            fh.write(f"{path}\t{os.getpid()}\n")
    finally:
        _local.busy = False


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
    log = os.environ.get("RMX_SANDBOX_CONNECT_LOG") or None
    if log is not None and violation("open", (log,), deny) is not None:
        # The log is written with the hook's re-entry guard up, i.e. unchecked: a log path
        # inside the deny set would be a write into a live store that nothing refuses.
        sys.stderr.write(f"SandboxViolation: RMX_SANDBOX_CONNECT_LOG={log} is a denied path\n")
        sys.stderr.flush()
        os._exit(CHILD_EXIT)
    _STATE["connect_log"] = log
    install(deny, mode="exit")
    # 29.4 R4 item 1: every exec'd child under the sandbox writes its own ledger line, and
    # registers the at-fork hook so a daemon's double fork (no exec) writes the final pid's.
    _STATE["ledger"] = str(Path(root) / LEDGER)
    ledger_write("exec")
    _register_at_fork()
    _run_preload(os.environ.get("RMX_SANDBOX_PRELOAD"))


def _run_preload(path: "str | None") -> None:
    """`$RMX_SANDBOX_PRELOAD`: an ABSOLUTE `.py` path run with `runpy.run_path` AFTER the hook
    is installed, so whatever it does is already refused like the child's own code. 21.3 AC-5
    injects its deadline delay this way (a second sitecustomize would never be imported). A
    preload that is not an absolute `.py`, or raises, exits the child PRELOAD_EXIT (87) with the
    cause on stderr -- never a child that runs without the setup its test asked for."""
    if not path:
        return
    try:
        if not (os.path.isabs(path) and path.endswith(".py")):
            raise ValueError(f"RMX_SANDBOX_PRELOAD must be an absolute .py path, got {path!r}")
        runpy.run_path(path, run_name="__rmx_sandbox_preload__")
    except BaseException as exc:  # SystemExit included: the child must not continue half-set
        sys.stderr.write(f"SandboxPreloadError: {path}: {type(exc).__name__}: {exc}\n")
        sys.stderr.flush()
        os._exit(PRELOAD_EXIT)


# ---- 29.4 R4 / R5: the spawn ledger, the reaper, test roots under the sandbox ------------
#
# bug-229 (found 2026-11-14): pid 89734, a `rmx daemon start --no-watch` from the bug-212 clone,
# served `/private/tmp/r1-hcn81cf7/proj/.refmatrix` with its own model workers for 20 hours
# while a full suite crawled at load 12-15. Its root was a `mkdtemp(dir="/tmp")` OUTSIDE the
# sandbox, so a reaper keyed on "sockets under the sandbox" could not see it, and the run that
# leaked it was most likely killed before teardown, so a teardown-only reaper could not either.
# So the reaper is keyed on the SPAWN (task-29.4 #r4): every Python process that starts under
# the sandbox writes one ledger line when it starts, the outermost session's finish stops and
# reports every live survivor, and the NEXT session's start sweeps the sandboxes killed runs
# left (`owner.json` tells a dead owner from a live one).
#
# A process is identified by (pid, start time), never by pid alone: a pid in a ledger may since
# have been reused by an unrelated process, which is reported and never signalled (#r4 item 2).
# The reaper never signals its own pid or an ancestor (ruling L142): an in-process `Daemon`'s
# `rmxd.pid` names the pytest process itself, so it is found through the weak instance registry
# (`track_inprocess`), never through its pid file.

LEDGER = "children.jsonl"
OWNER = "owner.json"
LEAK_LOG_REL = Path("workflow") / "review-output" / "leaked-processes.log"
# Only roots matching this are listed for the session-start sweep; nothing is searched (#r4 3).
ROOT_GLOB = "/tmp/rmx-*"
# A process its test stopped may still be exiting when the session finishes (a daemon's model
# worker a few hundred ms behind its daemon). It gets this long to go on its own before it is
# called a leak. Not a bound under test: it only delays a finish that HAS survivors.
FINISH_GRACE_S = 3.0
STOP_DAEMON_S = 20.0     # stop_daemon()'s grace for a leaked daemon (its drain, then SIGTERM)
TERM_WAIT_S = 5.0        # after SIGTERM, before SIGKILL
KILL_WAIT_S = 2.0        # after SIGKILL, before it is reported as surviving
SPAWN_GRACE_S = 10.0     # register_spawn: how long a fixture's own stop may take to land
_START_EPS = 1e-3        # start times are microseconds (darwin) or clock ticks (linux)

# darwin `struct kinfo_proc` (sysctl CTL_KERN / KERN_PROC / KERN_PROC_PID): `p_starttime`
# (a timeval) opens `kp_proc`, `p_stat` is the char at 36, `kp_eproc.e_ppid` the int at 560.
# Probed on this host 2026-11-15 (a running, a SIGSTOPped and a zombie `/bin/sleep`: p_stat 2,
# 4, 5; e_ppid equal to the parent's `os.getpid()`); the layout is the one psutil reads.
_KINFO_SIZE = 648
_KP_STAT, _KP_PPID = 36, 560
_SSTOP, _SZOMB = 4, 5
_LIBC: dict = {"h": None}


def _kinfo(pid: int) -> "bytes | None":
    import ctypes                       # lazily: ~7 ms, paid once per process
    if _LIBC["h"] is None:
        _LIBC["h"] = ctypes.CDLL(None, use_errno=True)
    mib = (ctypes.c_int * 4)(1, 14, 1, int(pid))
    buf = ctypes.create_string_buffer(1024)
    size = ctypes.c_size_t(len(buf))
    if _LIBC["h"].sysctl(mib, 4, buf, ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"sysctl(KERN_PROC_PID, {pid}): {os.strerror(err)}")
    if size.value == 0:
        return None                     # no such process
    if size.value < _KINFO_SIZE:
        raise OSError(f"sysctl(KERN_PROC_PID, {pid}) returned {size.value} bytes, not "
                      f"{_KINFO_SIZE}: an unknown kinfo_proc layout")
    return buf.raw[:size.value]


def proc_info(pid: int) -> "dict | None":
    """`{"start", "ppid", "state"}` of a process, or None when no such process exists.

    `start` is the process start time (darwin: epoch seconds to the microsecond; linux: clock
    ticks since boot), the identity a ledger line carries with its pid. `state` is `run`,
    `stopped` or `zombie`. Raises OSError when the platform call fails, and
    NotImplementedError on a platform with neither (the reaper cannot tell a reused pid there,
    so it must not guess)."""
    if pid <= 0:
        return None
    if sys.platform == "darwin":
        raw = _kinfo(pid)
        if raw is None:
            return None
        sec, usec = struct.unpack_from("qi", raw, 0)
        stat = raw[_KP_STAT]
        state = "zombie" if stat == _SZOMB else "stopped" if stat == _SSTOP else "run"
        return {"start": sec + usec / 1e6, "ppid": struct.unpack_from("i", raw, _KP_PPID)[0],
                "state": state}
    if os.path.isdir("/proc/self"):
        try:
            with open(f"/proc/{pid}/stat", "rb") as fh:
                data = fh.read().decode(errors="replace")
        except FileNotFoundError:
            return None
        rest = data.rsplit(")", 1)[1].split()
        state = {"Z": "zombie", "T": "stopped", "t": "stopped"}.get(rest[0], "run")
        return {"start": float(rest[19]), "ppid": int(rest[1]), "state": state}
    raise NotImplementedError(f"no process start time on {sys.platform}")


_KP_PID = 40          # extern_proc.p_pid (probed with the offsets above)


def process_table() -> dict:
    """`pid -> {"start", "ppid", "state"}` for every process on the machine (darwin:
    sysctl KERN_PROC_ALL, ~2 ms; linux: /proc). Used to find this session's live descendants,
    which a ledger read can miss: a child Popen'd in a test's last line may not have run its
    sitecustomize -- and written its line -- when the session finishes (found 2026-11-15, T0.2
    GREEN: case_leak_plain_child's session finished in 0.09 s, before its child's line)."""
    out: dict = {}
    if sys.platform == "darwin":
        import ctypes
        if _LIBC["h"] is None:
            _LIBC["h"] = ctypes.CDLL(None, use_errno=True)
        mib = (ctypes.c_int * 4)(1, 14, 0, 0)
        for _ in range(5):                  # the table can grow between the two calls
            size = ctypes.c_size_t(0)
            if _LIBC["h"].sysctl(mib, 4, None, ctypes.byref(size), None, ctypes.c_size_t(0)):
                raise OSError(ctypes.get_errno(), "sysctl(KERN_PROC_ALL) size")
            n = size.value + _KINFO_SIZE * 64
            buf = ctypes.create_string_buffer(n)
            size = ctypes.c_size_t(n)
            if _LIBC["h"].sysctl(mib, 4, buf, ctypes.byref(size), None,
                                 ctypes.c_size_t(0)) == 0:
                break
            if ctypes.get_errno() != 12:    # ENOMEM: it grew; ask again
                raise OSError(ctypes.get_errno(), "sysctl(KERN_PROC_ALL)")
        else:
            raise OSError("sysctl(KERN_PROC_ALL): the process table kept growing")
        raw = buf.raw[:size.value]
        for off in range(0, len(raw) - _KINFO_SIZE + 1, _KINFO_SIZE):
            sec, usec = struct.unpack_from("qi", raw, off)
            stat = raw[off + _KP_STAT]
            out[struct.unpack_from("i", raw, off + _KP_PID)[0]] = {
                "start": sec + usec / 1e6,
                "ppid": struct.unpack_from("i", raw, off + _KP_PPID)[0],
                "state": "zombie" if stat == _SZOMB else "stopped" if stat == _SSTOP else "run"}
        return out
    if os.path.isdir("/proc/self"):
        for d in os.listdir("/proc"):
            if d.isdigit():
                info = proc_info(int(d))
                if info is not None:
                    out[int(d)] = info
        return out
    raise NotImplementedError(f"no process table on {sys.platform}")


def live_descendants() -> dict:
    """`pid -> info` of every live (non-zombie) process descended from this one."""
    table = process_table()
    kids: dict = {}
    for pid, info in table.items():
        kids.setdefault(info["ppid"], []).append(pid)
    me = os.getpid()
    out: dict = {}
    todo = [me]
    while todo:
        for c in kids.get(todo.pop(), []):
            if c not in out and c != me:
                out[c] = table[c]
                todo.append(c)
    return {p: i for p, i in out.items() if i["state"] != "zombie"}


def _ps_command(pid: int) -> str:
    import subprocess
    try:
        r = subprocess.run(["/bin/ps", "-o", "command=", "-p", str(pid)], capture_output=True,
                           text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"<ps failed: {exc}>"
    return r.stdout.strip() or "<exited>"


def _same_process(pid: int, start) -> bool:
    """`pid` is still the process a ledger line recorded: alive, not a zombie, same start."""
    if start is None:
        return False
    info = proc_info(pid)
    return (info is not None and info["state"] != "zombie"
            and abs(info["start"] - float(start)) < _START_EPS)


def _alive(pid: int) -> bool:
    info = proc_info(pid)
    return info is not None and info["state"] != "zombie"


def _ledger_record(how: str) -> dict:
    pid = os.getpid()
    rec = {"pid": pid, "ppid": os.getppid(), "start": None, "how": how,
           "argv": list(getattr(sys, "orig_argv", None) or sys.argv or []),
           "cwd": None, "root": os.environ.get("REFMATRIX_ROOT"), "test": current_test(),
           "t": time.time()}
    try:
        rec["cwd"] = os.getcwd()
    except OSError as exc:              # a child started in a vanished cwd (bug-212's tests)
        rec["cwd_error"] = repr(exc)
    try:
        info = proc_info(pid)
        rec["start"] = info["start"] if info else None
    except (OSError, NotImplementedError) as exc:
        rec["start_error"] = repr(exc)
    return rec


def ledger_write(how: str) -> None:
    """Append this process's ONE ledger line (#r4 item 1): one `write` of one line under
    `O_APPEND`, so concurrent children never interleave. A child must not die of its own
    bookkeeping, but a line it could not write is said on its stderr, never dropped."""
    path = _STATE["ledger"]
    if not path:
        return
    _local.busy = True
    try:
        line = (json.dumps(_ledger_record(how), default=str) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 -- reported below, never swallowed
        sys.stderr.write(f"rmx sandbox: spawn ledger write to {path} failed ({exc!r}); pid "
                         f"{os.getpid()} is NOT in the ledger and the reaper cannot see it\n")
    finally:
        _local.busy = False


def _after_fork_child() -> None:
    ledger_write("fork")


def _register_at_fork() -> None:
    """Once per process: a fork child (no exec) writes its own line. A daemon double-forks,
    so its final pid exists only here (#r4 item 1)."""
    if _STATE["at_fork"] or not hasattr(os, "register_at_fork"):
        return
    os.register_at_fork(after_in_child=_after_fork_child)
    _STATE["at_fork"] = True


def write_owner(root: Path) -> None:
    """`<root>/owner.json`: the pid and start time of the process that owns this sandbox (#r4
    item 3). Written atomically, so a session-start sweep never reads half of one."""
    info = proc_info(os.getpid())
    rec = {"pid": os.getpid(), "start": info["start"] if info else None,
           "argv": list(getattr(sys, "orig_argv", None) or sys.argv or []),
           "cwd": os.getcwd(), "created": time.time()}
    tmp = Path(root) / (OWNER + ".tmp")
    tmp.write_text(json.dumps(rec))
    os.replace(tmp, Path(root) / OWNER)


def sandbox_root() -> Path:
    """This process's sandbox root: its own (`enter()`), else the inherited
    `RMX_SANDBOX_ROOT`. No sandbox is an error, never a fallback to `/tmp`."""
    sb = _STATE["sandbox"]
    if sb is not None:
        return Path(sb["root"])
    env = os.environ.get("RMX_SANDBOX_ROOT")
    if not env:
        raise RuntimeError("rmx sandbox: no sandbox root (RMX_SANDBOX_ROOT is unset); "
                           "short_root() makes test roots under it only")
    return Path(env)


def short_root(prefix: str) -> str:
    """A fresh directory under `<sandbox root>/t/` (task-29.4 #r5): a leaked root goes with the
    sandbox, a leaked daemon's pid file is under one directory, and two shards cannot collide
    on a root. Short: `/private/tmp/rmx-XXXXXXXX/t/<prefix>XXXXXXXX/proj/.refmatrix/rmxd.sock`
    is 62 bytes plus the prefix, far under macOS's 104-byte `sun_path`. Returns a str, like
    the `tempfile.mkdtemp(prefix=…, dir="/tmp")` it replaces."""
    t = sandbox_root() / "t"
    t.mkdir(exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=str(t))


def _ancestors() -> set:
    """This process and every ancestor up to launchd/init: the pids the reaper never signals
    (ruling L142). A pid whose parent cannot be read ends the walk; 0 and 1 are always in."""
    out = {0, 1}
    pid = os.getpid()
    while pid > 1 and pid not in out:
        out.add(pid)
        info = proc_info(pid)
        if info is None:
            break
        pid = info["ppid"]
    return out


def read_ledger(path, emit) -> list:
    """The ledger's records, ONE per pid (its latest line; a fork-then-exec child writes two
    with the same start), in order of first appearance. A line that does not parse is printed
    and counted, never skipped silently."""
    try:
        text = Path(path).read_text(errors="replace")
    except FileNotFoundError:
        return []
    by_pid: dict = {}
    bad = 0
    for ln in text.splitlines():
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
            pid = int(rec["pid"])
        except (ValueError, KeyError, TypeError):
            bad += 1
            emit(f"rmx sandbox: unreadable ledger line in {path}: {ln[:200]!r}")
            continue
        by_pid[pid] = rec
    if bad:
        emit(f"rmx sandbox: {bad} unreadable ledger line(s) in {path}; those processes are "
             f"not known to the reaper")
    return list(by_pid.values())


def _argv_text(argv) -> str:
    try:
        s = shlex.join(str(a) for a in argv)
    except TypeError:
        s = repr(argv)
    return s if len(s) <= 300 else s[:297] + "..."


def _signal(pid: int, start, sig, protected: set, emit) -> bool:
    """Send `sig` to the recorded process only: never a protected pid, never a pid whose
    start time no longer matches (it exited and the pid was reused between two steps)."""
    if pid in protected:
        emit(f"  NOT signalling pid={pid}: this process or an ancestor (ruling L142)")
        return False
    if not _same_process(pid, start):
        return False
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return False
    except (PermissionError, SandboxViolation) as exc:
        emit(f"  {signal.Signals(sig).name} to pid={pid} refused: {exc}")
        return False
    emit(f"  {signal.Signals(sig).name} sent to pid={pid}")
    return True


def _wait_gone(pid: int, start, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _same_process(pid, start):
            return True
        time.sleep(0.05)
    return not _same_process(pid, start)


def stop_process(pid: int, start, root, emit, protected: "set | None" = None) -> bool:
    """Stop one recorded process; every step is printed. True when it is gone.

    1. A SIGSTOPped process is sent SIGCONT first (#r4 item 8: a stopped process is still a
       leak, and it cannot drain or answer while stopped).
    2. `daemon.stop_daemon(root)` when the ledger gives a root AND that root's `rmxd.pid` names
       THIS pid: the pid is that root's daemon, and its own stop path drains it. A ledger root
       alone does not make a pid a daemon -- the sandbox gives every child a per-test
       `REFMATRIX_ROOT` -- and a pid file may name this very process (an in-process daemon),
       so neither case reaches `stop_daemon` (ruling L142).
    3. Still alive: SIGTERM, a bounded wait, then SIGKILL."""
    protected = _ancestors() if protected is None else protected
    if pid in protected:
        emit(f"  NOT stopping pid={pid}: this process or an ancestor (ruling L142)")
        return False
    info = proc_info(pid)
    if info is not None and info["state"] == "stopped":
        emit(f"  pid={pid} is stopped (SIGSTOP)")
        _signal(pid, start, signal.SIGCONT, protected, emit)
    if root and _same_process(pid, start):
        try:
            from refmatrix import daemon as _dm
        except ImportError as exc:
            emit(f"  refmatrix is not importable here ({exc}); pid={pid} is signalled instead "
                 f"of stop_daemon({root})")
        else:
            owner = _dm.read_pid(Path(root))
            if owner == pid:
                rep: dict = {}
                ok = _dm.stop_daemon(Path(root), timeout=STOP_DAEMON_S, report=rep)
                emit(f"  stop_daemon({root}) -> {'stopped' if ok else 'NOT stopped'} {rep}")
            else:
                emit(f"  {root}'s rmxd.pid names {owner}, not pid={pid}: not its daemon; "
                     f"signalled")
    if not _same_process(pid, start):
        return True
    if _signal(pid, start, signal.SIGTERM, protected, emit) and _wait_gone(pid, start,
                                                                           TERM_WAIT_S):
        return True
    if not _same_process(pid, start):
        return True
    _signal(pid, start, signal.SIGKILL, protected, emit)
    if _wait_gone(pid, start, KILL_WAIT_S):
        return True
    emit(f"  pid={pid} SURVIVED SIGKILL")
    return False


LATE_LINE_S = 2.0     # a live descendant with no ledger line yet: time for its sitecustomize


def _with_descendants(ledger, recs: list, protected: set, emit) -> list:
    """`recs` plus every live descendant of this process the ledger does not name. A Python
    child gets `LATE_LINE_S` to write its line (re-read); one that still has none -- a non-Python
    child, or one that never reached its sitecustomize -- is reported from the process table,
    which IS the live process (no reuse question), with `test` unknown and never guessed."""
    desc = {p: i for p, i in live_descendants().items() if p not in protected}
    missing = set(desc) - {int(r["pid"]) for r in recs}
    deadline = time.monotonic() + LATE_LINE_S
    while missing and time.monotonic() < deadline:
        time.sleep(0.1)
        recs = read_ledger(ledger, emit)
        missing = {p for p in missing if p not in {int(r["pid"]) for r in recs}}
        missing = {p for p in missing if _same_process(p, desc[p]["start"])}
    for p in sorted(missing):
        if _same_process(p, desc[p]["start"]):
            recs.append({"pid": p, "ppid": desc[p]["ppid"], "start": desc[p]["start"],
                         "argv": [_ps_command(p)], "cwd": None, "root": None, "t": None,
                         "test": "<no ledger line: a live descendant of this session>",
                         "how": "descendant"})
    return recs


# Ruling L154 (2026-11-15): the ONE exempt process. Loading the embedder in-process (torch)
# starts the stdlib's multiprocessing resource tracker as a child of the session; it ignores
# SIGTERM and ends by itself when its parent closes the pipe at exit, so it ends with its parent
# by construction. The tier-(b) verify run at 78489af reaped it (`green-verify-tierb.log`) and
# multiprocessing relaunched it at exit. Exempt only as a DIRECT child of this process with
# exactly this argv; printed and counted, never silent. No other helper is exempt.
_RESOURCE_TRACKER = re.compile(r"from multiprocessing\.resource_tracker import main;main\(\d+\)")


def _is_resource_tracker(rec: dict, info: dict) -> bool:
    if info.get("ppid") != os.getpid():
        return False
    argv = rec.get("argv") or []
    if len(argv) == 1:                      # a descendant read from `ps`: one command string
        try:
            argv = shlex.split(str(argv[0]))
        except ValueError:
            return False
    return (len(argv) == 3 and argv[1] == "-c"
            and _RESOURCE_TRACKER.fullmatch(str(argv[2])) is not None)


def reap_ledger(ledger, label: str, emit, grace: float = 0.0,
                descendants: bool = False) -> dict:
    """Stop every live survivor of `ledger`, each printed `<label> pid=<n> age=<s> spawned in
    <test> argv=<…> root=<…>` and stopped (`stop_process`). The ONE body behind the finish
    reaper (`LEAKED PROCESS`) and `sweep_orphans` (`ORPHAN from a killed run:`).

    `root=` is the ledger's `REFMATRIX_ROOT` for that pid, wherever it is (bug-229's root was
    outside the sandbox); with none the line says `root=unknown (cwd=…)` and does not guess. A
    live pid whose start time is not the ledger's is a reused pid: printed, never signalled. A
    line with no start time cannot be told from one, so it is printed and counted as a finding,
    never signalled. `grace`: how long survivors get to exit on their own first.
    `descendants`: also every live descendant of THIS process (`_with_descendants`); the
    finish reaper's own ledger only, never a dead owner's (its children are not ours)."""
    recs = read_ledger(ledger, emit)
    protected = _ancestors()
    if descendants:
        recs = _with_descendants(ledger, recs, protected, emit)
    out: dict = {"leaked": [], "reused": [], "unverified": [], "survived": [], "exempt": []}
    live = []
    for rec in recs:
        pid = int(rec["pid"])
        if pid in protected:
            continue        # this session or its parent chain, written by an outer sandbox
        info = proc_info(pid)
        if info is None or info["state"] == "zombie":
            continue
        start = rec.get("start")
        if start is None:
            emit(f"rmx sandbox: pid={pid} in {ledger} has no recorded start time "
                 f"({rec.get('start_error', 'none recorded')}); it cannot be told from a reused "
                 f"pid and is NOT signalled (spawned in {rec.get('test')})")
            out["unverified"].append(rec)
        elif abs(info["start"] - float(start)) >= _START_EPS:
            emit(f"rmx sandbox: pid={pid} in {ledger} is a reused pid (ledger start {start}, "
                 f"the live process started {info['start']}); not signalled")
            out["reused"].append(rec)
        elif _is_resource_tracker(rec, info):
            emit(f"rmx sandbox: pid={pid} exempt, not reaped: the stdlib multiprocessing "
                 f"resource tracker, a direct child of this session (spawned in "
                 f"{rec.get('test')}); it ends with its parent by construction (ruling L154)")
            out["exempt"].append(rec)
        else:
            live.append(rec)
    if live and grace > 0:
        _wait_all_gone(live, grace)
    for rec in live:
        pid, start, root = int(rec["pid"]), rec["start"], rec.get("root")
        if not _same_process(pid, start):
            continue                    # exited by itself (in the grace, or with its daemon)
        where = f"root={root}" if root else f"root=unknown (cwd={rec.get('cwd')})"
        born = rec.get("t") or (start if sys.platform == "darwin" else None) or time.time()
        age = time.time() - float(born)
        line = (f"{label} pid={pid} age={age:.0f}s spawned in {rec.get('test')} "
                f"argv={_argv_text(rec.get('argv') or [])} {where}")
        emit(line)
        gone = stop_process(pid, start, root, emit, protected)
        out["leaked"].append(dict(rec, line=line, stopped=gone))
        if not gone:
            out["survived"].append(rec)
    return out


def _wait_all_gone(recs: list, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not any(_same_process(int(r["pid"]), r["start"]) for r in recs):
            return
        time.sleep(0.1)


def _stderr_emit(line: str) -> None:
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def sweep_orphans(ledger_path, emit=None, label: str = "ORPHAN from a killed run:") -> dict:
    """#r4 item 9: stop the live survivors of a dead owner's ledger -- item 3's logic as a
    function (28.2's paired-run clone daemons sweep their own ledger with it before a run).
    Returns `reap_ledger`'s result; every orphan is printed (stderr by default)."""
    return reap_ledger(ledger_path, label, emit or _stderr_emit)


def _owner_alive(root: Path, emit) -> "bool | None":
    """True: the owner (pid AND start time) is running. False: dead, a killed run's sandbox.
    None: no readable `owner.json` -- not attributable, so never swept (a sandbox mid-`enter()`
    or one written before owner.json existed)."""
    f = root / OWNER
    try:
        rec = json.loads(f.read_text())
        pid, start = int(rec["pid"]), rec.get("start")
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        emit(f"rmx sandbox: {f} is unreadable ({exc!r}); that sandbox is not swept")
        return None
    if pid == os.getpid():
        return True
    if start is None:
        return _alive(pid)
    return _same_process(pid, start)


def sweep_killed_runs(emit) -> dict:
    """#r4 item 3, at session start: every `/tmp/rmx-*/owner.json` whose owner is no longer
    running is a sandbox a killed run left. Its ledger's survivors are stopped (`sweep_orphans`),
    each printed `ORPHAN from a killed run: …`, and its root is removed -- unless something
    survived, which keeps the root and says so. It does not fail the new session (plan-29 D13).
    Returns `{"orphans": [...], "roots": [...], "kept": [...]}`."""
    try:
        own = os.path.realpath(str(sandbox_root()))
    except RuntimeError:
        own = None
    out: dict = {"orphans": [], "roots": [], "kept": []}
    for owner in sorted(glob.glob(os.path.join(ROOT_GLOB, OWNER))):
        root = Path(os.path.realpath(os.path.dirname(owner)))
        if str(root) == own:
            continue
        if _owner_alive(root, emit) is not False:
            continue
        res = sweep_orphans(root / LEDGER, emit)
        out["orphans"] += res["leaked"]
        if res["survived"] or res["unverified"]:
            emit(f"rmx sandbox: killed run's sandbox {root} KEPT: {len(res['survived'])} "
                 f"orphan(s) survived, {len(res['unverified'])} unverifiable")
            out["kept"].append(str(root))
            continue
        remove_tree(root)
        out["roots"].append(str(root))
    return out


def live_store_roots(root: Path) -> list:
    """#r4 item 4: the store roots under the sandbox whose `rmxd.pid` names a live process,
    counted before anything is stopped or removed."""
    found = []
    for dirpath, _dirs, files in os.walk(str(root)):
        if DAEMON_PID in files:
            pid = read_pid(Path(dirpath) / DAEMON_PID)
            if pid is not None and _alive(pid):
                found.append((dirpath, pid))
    return found


# In-process daemons (#r4 item 6): conftest wraps `Daemon.__init__` to record each instance
# here, weakly, with the test that built it. The serving check and the stop are conftest's
# (they need `refmatrix.daemon`; this module imports under any Python 3 a child may run).
_INPROC: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_INPROC_OPS: dict = {"serving": None, "stop": None}


def track_inprocess(obj, root) -> None:
    _INPROC[obj] = {"root": str(root), "test": current_test()}


def set_inprocess_ops(serving, stop) -> None:
    """conftest's `serving(obj) -> bool` and `stop(obj, emit) -> bool`."""
    _INPROC_OPS["serving"], _INPROC_OPS["stop"] = serving, stop


def inprocess_leaks(emit) -> list:
    """Every tracked instance still serving: printed `LEAKED IN-PROCESS DAEMON root=<…> built
    in <test>`, stopped through conftest's `stop` (the registry; never its pid file, which
    names this process). Returns the printed lines with their tests."""
    serving, stop = _INPROC_OPS["serving"], _INPROC_OPS["stop"]
    if serving is None:
        return []
    out = []
    for obj, meta in list(_INPROC.items()):
        if not serving(obj):
            continue
        line = f"LEAKED IN-PROCESS DAEMON root={meta['root']} built in {meta['test']}"
        emit(line)
        if not stop(obj, emit):
            emit(f"  the in-process daemon on {meta['root']} did NOT stop")
        out.append((meta["test"], line))
    return out


# register_spawn (#r4 item 7): a fixture that owns a daemon registers it and grows no teardown
# of its own; the entry is checked when the node that owns the fixture is torn down.
_SPAWNS: list = []


def _fixture_node():
    """The node whose teardown finalizes the fixture calling `register_spawn`: the nearest
    pytest `SubRequest` on the stack (a function-scoped fixture's is its test item, a module
    fixture's its module). None outside a fixture: the entry belongs to the current test."""
    f = sys._getframe(2)
    while f is not None:
        req = f.f_locals.get("request")
        if type(req).__name__ == "SubRequest":
            return getattr(req, "node", None)
        f = f.f_back
    return None


def register_spawn(pid_or_daemon, root, why) -> None:
    """Register a process (a pid) or an in-process `Daemon` that a fixture owns. When the
    fixture's node is torn down, the entry's check asserts the stop answered (the root's
    socket no longer answers) and the process exited (or the daemon stopped serving); if not,
    THAT test fails by name, and the spawn is stopped (task-29.4 #r4 item 7, AC-5)."""
    e = {"root": str(root) if root is not None else None, "why": str(why),
         "test": current_test(), "node": _fixture_node(), "pid": None, "start": None,
         "daemon": None}
    if isinstance(pid_or_daemon, int) and not isinstance(pid_or_daemon, bool):
        info = proc_info(pid_or_daemon)
        if info is None or info["state"] == "zombie":
            raise ValueError(f"register_spawn: pid {pid_or_daemon} is not running ({why})")
        e["pid"], e["start"] = pid_or_daemon, info["start"]
    else:
        e["daemon"] = weakref.ref(pid_or_daemon)
    _SPAWNS.append(e)


def _root_answers(root) -> bool:
    if not root:
        return False
    try:
        from refmatrix import daemon as _dm
    except ImportError:
        return False
    return bool(_dm.ping(Path(root), timeout=0.5, retries=0))


def _spawn_running(e) -> bool:
    if e["pid"] is not None and _same_process(e["pid"], e["start"]):
        return True
    obj = e["daemon"]() if e["daemon"] is not None else None
    if obj is not None and _INPROC_OPS["serving"] is not None and _INPROC_OPS["serving"](obj):
        return True
    return _root_answers(e["root"])


def check_spawn(e, emit) -> "str | None":
    """None when the registered spawn stopped (given `SPAWN_GRACE_S` for a stop in flight);
    else the failure, after stopping it."""
    deadline = time.monotonic() + SPAWN_GRACE_S
    while _spawn_running(e):
        if time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    else:
        return None
    what = f"pid {e['pid']}" if e["pid"] is not None else "an in-process daemon"
    msg = (f"register_spawn: {what} (root {e['root']}; {e['why']}) registered in {e['test']} "
           f"was not stopped by its fixture's teardown (task-29.4 #r4 item 7)")
    emit(msg)
    if e["pid"] is not None:
        stop_process(e["pid"], e["start"], e["root"], emit)
    else:
        obj = e["daemon"]()
        if obj is not None and _INPROC_OPS["stop"] is not None:
            _INPROC_OPS["stop"](obj, emit)
    return msg


def due_spawns(nodeid: str, live_nodes) -> list:
    """Pop the entries whose owning node is no longer set up (`live_nodes`: pytest's setup
    stack after this item's teardown), or that were registered by this test outside a
    fixture."""
    due = [e for e in _SPAWNS
           if (e["node"] is None and e["test"] == nodeid)
           or (e["node"] is not None and e["node"] not in live_nodes)]
    for e in due:
        _SPAWNS.remove(e)
    return due


def claim_session(config) -> bool:
    """The reaper runs for the OUTERMOST session of a process only (#r4 item 2): the first
    config to claim it. An in-process inner session that loads this conftest again does not."""
    if _STATE["session"] is None:
        _STATE["session"] = config
    return _STATE["session"] is config


def failure_record(nodeid: str, phase: str, e_line: str) -> None:
    """One `failures.jsonl` record (#r2: written by conftest when `RMX_FAILURES_OUT` is set,
    one line per failed or errored phase; reaper findings are records too)."""
    out = os.environ.get("RMX_FAILURES_OUT")
    if not out:
        return
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"nodeid": nodeid, "phase": phase, "e": e_line}) + "\n")


def leak_log(repo: Path, lines: list) -> None:
    """Append to `<repo>/workflow/review-output/leaked-processes.log` (#r4 item 3): one line
    per orphan or leak, timestamped and naming the session that found it."""
    if not lines:
        return
    p = Path(repo) / LEAK_LOG_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(p, "a", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(f"{stamp}\tsession pid {os.getpid()}\t{ln}\n")


def reap_session(repo: Path, emit) -> int:
    """#r4 items 2, 4, 6 and 7 at the outermost session's finish. Returns the number of
    findings that fail the session: leaked processes, leaked in-process daemons, registered
    spawns nobody stopped, and ledger lines that cannot be verified."""
    root = sandbox_root()
    live = live_store_roots(root)
    if live:
        emit(f"rmx sandbox: {len(live)} store root(s) under the sandbox hold a live rmxd.pid "
             f"at session finish")
        for d, pid in live:
            emit(f"  {d} (pid {pid})")
    log: list = []
    findings = 0
    for test, line in inprocess_leaks(lambda ln: (emit(ln), log.append(ln))):
        findings += 1
        failure_record(test, "reaper", line)
    for e in list(_SPAWNS):
        _SPAWNS.remove(e)
        msg = check_spawn(e, emit)
        if msg:
            findings += 1
            log.append(msg)
            failure_record(e["test"], "reaper", msg)
    res = reap_ledger(root / LEDGER, "LEAKED PROCESS", emit, grace=FINISH_GRACE_S,
                      descendants=True)
    for rec in res["leaked"]:
        findings += 1
        log.append(rec["line"] + ("" if rec["stopped"] else "  (SURVIVED)"))
        failure_record(str(rec.get("test")), "reaper", rec["line"])
    for rec in res["unverified"]:
        findings += 1
        line = f"UNVERIFIED pid={rec['pid']} spawned in {rec.get('test')} (no start time)"
        log.append(line)
        failure_record(str(rec.get("test")), "reaper", line)
    for rec in res["reused"]:
        log.append(f"reused pid={rec['pid']} (ledger line from {rec.get('test')}); not signalled")
    exempt = len(res["exempt"])
    leak_log(repo, log)
    if findings:
        emit(f"rmx sandbox: {findings} leak(s) outlived their tests; the session FAILS "
             f"(bug-229; task-29.4 #r4); {exempt} exempt (stdlib resource tracker, L154). "
             f"Logged in {Path(repo) / LEAK_LOG_REL}")
    elif exempt:
        emit(f"rmx sandbox: 0 leaks; {exempt} exempt process(es) (the stdlib multiprocessing "
             f"resource tracker, which ends with this session by construction; ruling L154)")
    return findings


# ---- AC-4: the content check over live logs ---------------------------------------------


PATH_FIELDS = ("path", "cwd", "root")


def _path_field_values(row) -> list:
    """Every string under a `path` / `cwd` / `root` key, at any depth of a JSON row."""
    out: list = []
    stack = [row]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            for k, x in v.items():
                if k in PATH_FIELDS and isinstance(x, str):
                    out.append(x)
                elif k in PATH_FIELDS and isinstance(x, list):
                    out += [y for y in x if isinstance(y, str)]
                else:
                    stack.append(x)
        elif isinstance(v, list):
            stack.extend(v)
    return out


def leak_reasons(line: str, tag: str, log_name: str) -> list:
    """Why one delta line of a live log is a sandbox leak (ns23-2: content, not size/mtime).

    A leaked row carries the run's tag (every sandbox path does), a pytest temp path in a PATH
    field, or -- for `query.log` -- the d9g fixture shape: a learn/grep row whose body has
    `alpha|beta` and no `cwd`. Live activity carries none of these.

    `/pytest-of-` is matched in the row's `path` / `cwd` / `root` fields only (ch-bsd r1 s5,
    2026-10-15): the live watcher ingesting a ch-bsd ledger that QUOTES bug-101's
    `/private/var/folders/.../pytest-of-tholley/...` put that text in a facts.log row's free
    text and failed the check on live activity. The run tag stays a whole-line match: it is
    drawn fresh per run, so no pre-existing document can quote it."""
    out = []
    try:
        row = json.loads(line)
    except ValueError:
        row = None
    # The tag as it appears in a sandbox path (`rmx-<tag>-`), never the bare 6 hex digits,
    # which a sha in an unrelated facts.log row matches by chance.
    if tag and f"rmx-{tag}-" in line:
        out.append("run tag")
    if any("/pytest-of-" in v for v in _path_field_values(row)):
        out.append("pytest temp path")
    if log_name == "query.log":
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


def growth_ledger_path() -> Path:
    """Where per-test guards record live-log growth: `$RMX_LIVE_GROWTH_LEDGER`, else the repo's
    `workflow/review-output/live-log-growth.jsonl` (beside the touches log)."""
    env = os.environ.get("RMX_LIVE_GROWTH_LEDGER")
    return Path(env) if env else Path(__file__).resolve().parents[2] / GROWTH_REL


def record_growth(entry: dict, ledger: "Path | None" = None) -> None:
    """Append one growth record (one `write()` of one line, O_APPEND). The test process never
    opens the live log itself; the bytes are judged later by `growth_leaks`."""
    p = Path(ledger) if ledger is not None else growth_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(entry) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def growth_leaks(ledger: str, since: int) -> list:
    """The ONE attribution of recorded live-log growth (21.1 r2 #s2, bug-134): for each ledger
    record past byte `since`, read the live log's bytes `[start, end)` and return each
    COMPLETE row that carries one of the record's markers (a sandbox path, a token its test
    minted) as `(nodeid, path, row)`. A row with no marker is concurrent live use; an
    incomplete trailing line is not judged. An unreadable ledger line is itself returned (a
    record that cannot be judged is never dropped)."""
    out: list = []
    try:
        with open(ledger, "rb") as fh:
            fh.seek(since)
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except FileNotFoundError:
        return out
    for ln in lines:
        if not ln.strip():
            continue
        try:
            e = json.loads(ln)
            path, start, end = e["path"], int(e["start"]), int(e["end"])
            marks = [m for m in e.get("markers") or [] if m]
        except (ValueError, KeyError, TypeError):
            out.append(("?", ledger, f"unreadable growth record: {ln[:200]}"))
            continue
        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                data = fh.read(max(0, end - start))
        except OSError as exc:
            out.append((e.get("nodeid", "?"), path, f"growth not readable: {exc}"))
            continue
        rows = data.split(b"\n")
        complete = rows if data.endswith(b"\n") else rows[:-1]
        for r in complete:
            t = r.decode("utf-8", "replace")
            if t.strip() and any(m in t for m in marks):
                out.append((e.get("nodeid", "?"), path, t[:300]))
    return out


def check_logs(snap: dict, tag: str, touches: str, touches_size: int,
               growth: "str | None" = None, growth_size: int = 0) -> int:
    """Print one report line per log; return the number of offending rows (logs + touches +
    attributed growth recorded by per-test guards)."""
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
    for ln in touches_since(touches, touches_size):
        t = parse_touch(ln)
        if t is None or not t["probe"]:
            unexpected.append(ln)
    print(f"{touches}: unexpected_new_lines={len(unexpected)}")
    for ln in unexpected[:5]:
        print(f"  TOUCH {ln}")
    leaks = growth_leaks(growth, growth_size) if growth else []
    if growth:
        print(f"{growth}: attributed_growth_rows={len(leaks)}")
    for nodeid, path, row in leaks[:5]:
        print(f"  GROWTH-LEAK {nodeid} in {path}: {row}")
    return bad_total + len(unexpected) + len(leaks)


# ---- R6: no silent scope shrink ---------------------------------------------------------


class SkipGate:
    """A pytest plugin (ch-bsd r1 b2, 2026-10-15): the session FAILS when a test skipped that
    is not named in `allowed` (`nodeid -> why`). 18 pre-existing tests began to skip under the
    sandbox because each skip condition read a HOME-derived path; the baseline run skipped
    none, and nothing noticed. A skip is a test that stopped running, so each one is named.

    Per session (an instance per config), so an in-process `pytester` inner session's skips
    never reach the outer gate.

    bug-215 (T0.1' R1.2, 2026-11-15): a skip is pinned only when its nodeid is allowed AND its
    reason, after pytest's `Skipped: ` prefix, is EQUAL to the pinned value (the test's own
    `reason=`). Matching by nodeid alone let a pinned test that began skipping for a new reason
    pass unseen; a substring or case-folded match would do the same for a reworded one. A pinned
    nodeid that skips for any other reason is reported `SKIPPED-UNPINNED` with both reasons."""

    _PREFIX = "Skipped: "

    def __init__(self, allowed: dict):
        self.allowed = dict(allowed)
        self.skipped: dict = {}

    def _note(self, report) -> None:
        if report.skipped and not hasattr(report, "wasxfail"):
            lr = report.longrepr
            why = lr[2] if isinstance(lr, tuple) and len(lr) == 3 else str(lr)
            self.skipped[report.nodeid] = why

    def pytest_runtest_logreport(self, report):
        self._note(report)

    def pytest_collectreport(self, report):
        self._note(report)

    @classmethod
    def reason(cls, why: str) -> str:
        """The skip's own reason: `why` with the one `Skipped: ` prefix pytest adds removed."""
        return why[len(cls._PREFIX):] if why.startswith(cls._PREFIX) else why

    def unexpected(self) -> dict:
        """`nodeid -> report line` for every skip that is not pinned: an unknown nodeid, or a
        pinned nodeid whose reason is not exactly its pin (the line then names both)."""
        bad = {}
        for k, v in self.skipped.items():
            if k not in self.allowed:
                bad[k] = v
            elif self.reason(v) != self.allowed[k]:
                bad[k] = f"{v} (pinned reason: {self.allowed[k]!r}; actual: {self.reason(v)!r})"
        return bad

    def pytest_sessionfinish(self, session, exitstatus):
        bad = self.unexpected()
        if not bad:
            return
        tw = session.config.get_terminal_writer()
        tw.line(f"SkipGate: {len(bad)} skip(s) not pinned with their exact reason "
                f"(tests/conftest.py ALLOWED_SKIPS); a skip is a test that stopped running:",
                red=True)
        for k, v in sorted(bad.items()):
            tw.line(f"  SKIPPED-UNPINNED {k}: {v}", red=True)
        import pytest
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def _next_on_path(name: str) -> str:
    """The `name` the shim stands in front of: the first on `PATH` that is not in `BIN_DIR`
    (so an outer shim -- a decoy gate's -- still sees the call), else `/bin/<name>`."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or os.path.realpath(d) == os.path.realpath(str(BIN_DIR)):
            continue
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return os.path.join("/bin", name)


def shim_launchctl(args) -> int:
    """`tests/sandbox_site/bin/launchctl` (ch-bsd r1 s6): a read-only verb execs the real
    `launchctl`; anything else is refused through the same `spawn_violation()` the audit hook
    uses, with a touches-log line and `CHILD_EXIT`. Fail closed: no deny set, no launchctl."""
    root = os.environ.get("RMX_SANDBOX_ROOT")
    deny_file = Path(root) / DENY_FILE if root else None
    if deny_file is None or not deny_file.is_file():
        sys.stderr.write(f"SandboxViolation: launchctl shim has no deny set at {deny_file}\n")
        return CHILD_EXIT
    deny = json.loads(deny_file.read_text())
    _STATE["deny"], _STATE["mode"] = deny, "exit"
    argv = ["launchctl"] + list(args)
    target = spawn_violation(argv, None, deny)
    if target is not None:
        _refuse("launchctl", target, deny)          # exits CHILD_EXIT
    real = _next_on_path("launchctl")
    os.execv(real, [real] + list(args))
    return 0                                         # not reached


def _main(argv) -> int:
    """`python rmx_sandbox.py snapshot OUT LOG...` / `check SNAP TAG TOUCHES TOUCHES_SIZE` /
    `launchctl ARGS...` (the S6 shim). The shell wrappers (sandbox-proof.sh, the lane scripts,
    `bin/launchctl`) call these; the logic lives here once."""
    if argv and argv[0] == "launchctl":
        return shim_launchctl(argv[1:])
    if len(argv) >= 3 and argv[0] == "snapshot":
        Path(argv[1]).write_text(json.dumps(snapshot(argv[2:])))
        return 0
    if len(argv) in (5, 7) and argv[0] == "check":
        snap = json.loads(Path(argv[1]).read_text())
        growth = (argv[5], int(argv[6])) if len(argv) == 7 else (None, 0)
        n = check_logs(snap, argv[2], argv[3], int(argv[4]), *growth)
        print(f"sandbox-proof: {n} offending row(s)")
        return 1 if n else 0
    sys.stderr.write("usage: rmx_sandbox.py snapshot OUT LOG... | "
                     "check SNAP TAG TOUCHES TOUCHES_SIZE [GROWTH GROWTH_SIZE]\n")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
