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
import json
import os
import plistlib
import pwd
import runpy
import shlex
import shutil
import socket
import sys
import tempfile
import threading
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
          "connect_log": None}
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


def build_deny(repo: Path, env=None) -> dict:
    """R3's ONE deny set, from the real paths. Read BEFORE the audit hook is installed (the
    registry and the plists name the stores the hook will then refuse). `pids` (S6): the live
    daemons and hubs those paths name, which `os.kill` / a spawned `kill` may not signal."""
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
            "pids": live_pids(sorted(roots), homes),
            "touches": str(repo / TOUCHES_REL)}


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
    for ln in touches_since(touches, touches_size):
        t = parse_touch(ln)
        if t is None or not t["probe"]:
            unexpected.append(ln)
    print(f"{touches}: unexpected_new_lines={len(unexpected)}")
    for ln in unexpected[:5]:
        print(f"  TOUCH {ln}")
    return bad_total + len(unexpected)


# ---- R6: no silent scope shrink ---------------------------------------------------------


class SkipGate:
    """A pytest plugin (ch-bsd r1 b2, 2026-10-15): the session FAILS when a test skipped that
    is not named in `allowed` (`nodeid -> why`). 18 pre-existing tests began to skip under the
    sandbox because each skip condition read a HOME-derived path; the baseline run skipped
    none, and nothing noticed. A skip is a test that stopped running, so each one is named.

    Per session (an instance per config), so an in-process `pytester` inner session's skips
    never reach the outer gate."""

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

    def unexpected(self) -> dict:
        return {k: v for k, v in self.skipped.items() if k not in self.allowed}

    def pytest_sessionfinish(self, session, exitstatus):
        bad = self.unexpected()
        if not bad:
            return
        tw = session.config.get_terminal_writer()
        tw.line(f"SkipGate: {len(bad)} skip(s) not in the pinned list (tests/conftest.py "
                f"ALLOWED_SKIPS); a skip is a test that stopped running:", red=True)
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
