"""macOS launchd LaunchAgent generator + install/uninstall for `rmx daemon`.

One plist per refmatrix root, installed in `~/Library/LaunchAgents/`. Runs
`rmx daemon start --no-detach` so launchd owns the process lifecycle and
KeepAlive can restart on crash.
"""
from __future__ import annotations

import hashlib
import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path


LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_THROTTLE_SECONDS = 10
LABEL_PREFIX = "com.refmatrix.daemon"


def _short_hash(root: Path) -> str:
    return hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:12]


def _slug_for_root(root: Path) -> str:
    """Human-readable, reverse-DNS-safe project slug for `root`.

    The project name is the parent of `.refmatrix/` (where REFMATRIX_ROOT
    points). Non-alphanumerics collapse to single dashes so the slug is a
    legal launchd label segment; empty results fall back to ``store``.
    """
    root = Path(root).resolve()
    name = root.parent.name if root.name == ".refmatrix" else root.name
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return slug or "store"


def label_for_root(root: Path) -> str:
    """Readable, collision-free reverse-DNS label per refmatrix root.

    Shape: ``com.refmatrix.daemon.<slug>-<hash12>``. The slug makes the
    label greppable (``com.refmatrix.daemon.viascope-…``); the path hash
    suffix preserves the per-root uniqueness guarantee so two stores that
    share a basename never collide.
    """
    return f"{LABEL_PREFIX}.{_slug_for_root(root)}-{_short_hash(root)}"


def _legacy_label_for_root(root: Path) -> str:
    """Pre-slug label (hash only). Retained so `install`/`uninstall` can
    bootout + remove plists written by older refmatrix versions."""
    return f"{LABEL_PREFIX}.{_short_hash(root)}"


def plist_path(root: Path) -> Path:
    return LAUNCH_AGENTS_DIR / f"{label_for_root(root)}.plist"


def _legacy_plist_path(root: Path) -> Path:
    return LAUNCH_AGENTS_DIR / f"{_legacy_label_for_root(root)}.plist"


def _migrate_legacy(root: Path) -> bool:
    """Bootout + delete a legacy hash-only LaunchAgent for `root` if one
    exists, so reinstalling adopts the new slugged label without leaving a
    duplicate daemon running against the same store. Returns True if a
    legacy plist was removed."""
    legacy_label = _legacy_label_for_root(root)
    legacy_plist = _legacy_plist_path(root)
    if legacy_label == label_for_root(root):
        return False  # nothing to migrate (shouldn't happen with a slug)
    loaded = subprocess.run(
        _print_cmd(legacy_label), capture_output=True
    ).returncode == 0
    if loaded:
        subprocess.run(_bootout_cmd(legacy_label), capture_output=True)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if subprocess.run(
                _print_cmd(legacy_label), capture_output=True
            ).returncode != 0:
                break
            time.sleep(0.1)
    if legacy_plist.exists():
        legacy_plist.unlink()
        return True
    return False


# launchd's own stop budget. `launchctl kickstart -k` and a bootout SIGTERM
# the job and, after `ExitTimeOut` seconds, SIGKILL it. The default is 5 s;
# a daemon's drain is three pool drains × RMX_DAEMON_SHUTDOWN_TIMEOUT_S (10)
# plus the thread joins, the final flush and a bounded DuckDB close. Five
# daemons were SIGKILLed mid-drain on 2026-09-15 by a deploy that never put
# the two numbers side by side (ch-bsd plan-4 r3 #b-1). ONE number for every
# supervisor: the plist's ExitTimeOut, the hub's kill grace and the CLI's
# stop grace all read it — and since bug-051 the daemon reads it too:
# `daemon._StopDeadline` hands each shutdown stage a share of THIS number
# instead of its own constant, so the stages can no longer sum past it
# (they summed to 59 s when the flush budget went 5 -> 15).
EXIT_TIMEOUT_S = 45.0

_IDENTITY_CACHE: "dict[str, dict]" = {}


def binary_identity(rmx: str) -> dict:
    """What tree does the binary a plist would run actually import? Asks
    the binary itself (`rmx version -v --json`) — the plist renders THIS
    process's `rmx`, and from a dev shell that is the dev venv: `check`
    then reported drift on all eight plists and `reinstall` would have
    rewritten them to the dev tree before `_verify_relaunch` could object
    (ch-bsd plan-4 r3 #s-4). Cached per path for the life of the process
    (`relaunch-fleet` asks once, not once per store). An answer that is not
    the identity JSON (an older binary) is `{"dev_tree": None, "error": …}`:
    unknown, never "fine"."""
    key = str(rmx)
    hit = _IDENTITY_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        r = subprocess.run([key, "version", "-v", "--json"], capture_output=True,
                           text=True, timeout=30)
        import json as _json
        ident = _json.loads((r.stdout or "").strip().splitlines()[-1])
        if not isinstance(ident, dict) or "dev_tree" not in ident:
            raise ValueError("no dev_tree field")
    except Exception as e:  # noqa: BLE001 — unknown is said, not assumed fine
        ident = {"dev_tree": None, "error": f"{type(e).__name__}: {e}"}
    _IDENTITY_CACHE[key] = ident
    return ident


def _identity_objection(rmx: str) -> "str | None":
    """Why a plist must NOT be rendered against `rmx`, or None when the
    binary itself said `dev_tree: false`. The ONE reading of
    `binary_identity` for every guard (`_refuse_dev_tree`, `check`,
    `check_hub`).

    Fail closed: anything but an explicit `False` objects. The three guards
    used to read `if ident.get("dev_tree"):` each, and `None` — the answer
    for a binary that is not readable (a pre-0.69 binary printing a version
    line, a venv mid-rebuild exiting non-zero, a mistyped path) — is falsy,
    so "unknown" passed as "not a dev tree" at all three sites at once
    (ch-bsd plan-4 r4 #s-2; task 4.5 R1, 2026-10-19). The identity `error`,
    which nobody read, is named here."""
    ident = binary_identity(rmx)
    dev = ident.get("dev_tree")
    if dev is False:
        return None
    if dev is True:
        return (f"{rmx} is a dev tree: it imports {ident.get('import_path')} "
                f"(a venv that belongs to another tree)")
    return (f"{rmx} identity unknown: `{rmx} version -v --json` did not answer "
            f"the identity JSON ({ident.get('error') or f'dev_tree={dev!r}'}); "
            f"an unreadable binary is never assumed to be the deployed one")


def _refuse_dev_tree(rmx: str) -> None:
    """Raise unless `rmx` says it is not a dev tree. The message names the
    CLI flag `--allow-dev` (`rmx daemon|hub launchctl install --allow-dev`),
    not the Python parameter no operator can type (r4 #m-5, task 4.5 R3)."""
    why = _identity_objection(rmx)
    if why is not None:
        raise RuntimeError(
            f"refusing to render a plist: {why}. Run this with the deployed rmx, "
            f"or pass --allow-dev to `rmx daemon launchctl install` / "
            f"`rmx hub launchctl install` / `rmx session launchctl install` to "
            f"install against it anyway")


def _rmx_path() -> str:
    """THE binary every plist-writing command renders: the one the operator
    actually ran.

    1. `$RMX_BIN` when set (the explicit operator override).
    2. Else `sys.argv[0]` made absolute with `os.path.abspath` — symlinks
       NOT resolved, because the plist bakes `~/bin/rmx` as written — when
       its basename is `rmx` / `refmatrix` and it is an executable file.
    3. Else FileNotFoundError naming `sys.argv[0]` and `RMX_BIN`.

    There is no `which rmx` fallback any more. From a dev shell `which rmx`
    is a binary nobody ran: the daemon plist commands resolved it while the
    hub resolved `sys.argv[0]`, so `rmx daemon launchctl install` refused
    the deployed binary the operator typed because the PATH found a dev one
    (ch-bsd plan-4 r5 #s-1, probe P1; task 4.6, 2026-10-19). bug-028 gave the
    hub the argv[0] semantics; this makes them the ONE resolver."""
    override = os.environ.get("RMX_BIN")
    if override:
        return override
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0:
        cand = os.path.abspath(argv0)
        if (os.path.basename(cand) in ("rmx", "refmatrix") and os.path.isfile(cand)
                and os.access(cand, os.X_OK)):
            return cand
    raise FileNotFoundError(
        f"cannot tell which rmx to render into a plist: this process was started "
        f"as {argv0!r} (sys.argv[0]), which is not an `rmx`/`refmatrix` executable, "
        f"and RMX_BIN is not set. Run the command with the rmx binary the plist "
        f"should run (e.g. ~/bin/rmx), or set RMX_BIN to its absolute path."
    )


class CheckReason(str):
    """Why a plist check failed, with what KIND of failure it is (ch-bsd
    plan-4 r5 #m-1; task 4.6 M1, 2026-10-19).

    `kind` is one of `identity` (the binary is not verified — never "fix" it
    by reinstalling), `drift` (the installed plist or the loaded job differs
    from the render), `missing` (no plist installed) or `unloaded` (current
    plist, label not loaded). The CLI used to print every failure as `plist
    DRIFT` and prescribe `install --force` / `relaunch-fleet` — both of which
    refuse an unverified binary. A `str` subclass so callers and fakes that
    return plain strings keep working; a plain string reads as drift
    (`reason_kind`)."""

    KINDS = ("identity", "drift", "missing", "unloaded")

    def __new__(cls, text: str = "", kind: str = "drift") -> "CheckReason":
        if kind not in cls.KINDS:
            raise ValueError(f"CheckReason kind {kind!r} not in {cls.KINDS}")
        obj = super().__new__(cls, text)
        obj.kind = kind
        return obj


def reason_kind(why: str) -> str:
    """`why.kind`, or `drift` for a plain string (a fake, an older caller)."""
    return getattr(why, "kind", "drift")


def plist_diff(have: dict, want: dict) -> "list[str]":
    """Every key on which an installed plist differs from its render, as
    `K: installed X != rendered Y` lines — the ONE diff for the daemon, hub
    and session-indexer checks (three copies of this loop existed or were
    about to; task 4.6 S3). A key missing from the installed plist reads
    `installed None`, so a label rendered before `ExitTimeOut` existed names
    it (r5 #s-3)."""
    why: list[str] = []
    he, we = have.get("EnvironmentVariables") or {}, want.get("EnvironmentVariables") or {}
    for k in sorted(set(he) | set(we)):
        if k not in he:
            why.append(f"env {k} missing")
        elif k not in we:
            why.append(f"env {k} extra")
        elif he[k] != we[k]:
            why.append(f"env {k}: installed {he[k]!r} != rendered {we[k]!r}")
    if have.get("ProgramArguments") != want.get("ProgramArguments"):
        why.append(f"ProgramArguments: installed {have.get('ProgramArguments')} "
                   f"!= rendered {want.get('ProgramArguments')}")
    for k in sorted(set(have) | set(want)):
        if k in ("EnvironmentVariables", "ProgramArguments"):
            continue
        if have.get(k) != want.get(k):
            why.append(f"{k}: installed {have.get(k)!r} != rendered {want.get(k)!r}")
    return why


# The tool dirs a supervised daemon/hub needs, in lookup order: the user's own
# bins (`~/bin/tldr`, `~/.local/bin/graphify`), MacPorts (`rg`, `git`), Homebrew,
# then the system. `launchd_path` keeps the ones that exist on this machine.
_LAUNCHD_PATH_DIRS = ("~/bin", "~/.local/bin", "/opt/local/bin", "/opt/local/sbin",
                      "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
                      "/usr/sbin", "/sbin")


def launchd_path(rmx: str) -> str:
    """The PATH every refmatrix LaunchAgent exports — FIXED, not the caller's.

    The renderers baked `os.environ["PATH"]` of whichever shell ran the
    install (2026-10-07). From a Claude Code session that meant versioned
    plugin-cache bin dirs, which rot on every plugin update, plus `./` and an
    empty `::` entry (both are the cwd), and every drift check run from another
    shell reported PATH drift forever. The installed `rmx`'s own directory
    leads: the venv `bin` when `rmx` is the console script itself, or `~/bin`
    when it is reached through that symlink (this machine; r8 #m-1). Env
    values the HUB plist passes through on purpose (`RMX_WORKER_IDLE_S`,
    `RMX_HUB_QUEUE_ALERT_INTERVAL`) are operator settings, not the shell's
    PATH, and stay caller-supplied."""
    dirs = [str(Path(rmx).parent)] + [str(Path(d).expanduser()) for d in _LAUNCHD_PATH_DIRS]
    out: list[str] = []
    for d in dirs:
        if d not in out and Path(d).is_dir():
            out.append(d)
    return ":".join(out)


def render_plist(root: Path, *, partition: str | None = None,
                 watch: bool = True, debounce_ms: int = 500,
                 semantic: bool = False,
                 watch_roots: "list[Path] | None" = None,
                 rmx: "str | None" = None) -> bytes:
    """Render the plist for `root` as bytes (XML).

    `watch_roots` — optional list of dirs the daemon should watch. When
    omitted, the daemon defaults to watching the parent of `.refmatrix/`
    (the project root). Pass an explicit list to watch additional paths
    such as the auto-memory dir alongside the project tree.
    `rmx` — the binary the job runs; the caller's resolved one, else
    `_rmx_path()` (`$RMX_BIN`, else the binary this process ran — never
    `which rmx`; r5 #s-1).
    """
    root = Path(root).resolve()
    label = label_for_root(root)
    rmx = rmx or _rmx_path()

    # The global store is memory-only and its root is `~/.refmatrix`, so the
    # default watch root is $HOME -- which tracked 12,448 files (10k of them
    # under ~/Applications, plus refmatrix's own dev and deploy trees) into
    # the behavior store and re-dirtied it on every deploy. `hub.
    # ensure_global_daemon` always spawned it with `watch_root=[]`; only this
    # plist disagreed, so a launchd start behaved differently from a hub
    # start. Force the two paths to agree.
    if root == (Path.home() / ".refmatrix").resolve():
        watch = False

    args: list[str] = [rmx, "daemon", "start", "--no-detach"]
    if not watch:
        args.append("--no-watch")
    if debounce_ms != 500:
        args += ["--debounce-ms", str(debounce_ms)]
    if semantic:
        args.append("--semantic")
    if watch_roots:
        for r in watch_roots:
            args += ["--watch-root", str(Path(r).resolve())]

    env = {
        "REFMATRIX_ROOT": str(root),
        "PATH": launchd_path(rmx),
        # libobjc reads this once at image load; providing it here means the
        # launchd-spawned daemon never hits the initialize-after-fork SIGABRT
        # and skips the cli_entry re-exec. See cli._reexec_for_fork_safety.
        "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
        "TOKENIZERS_PARALLELISM": "false",
        # The daemon under THIS plist is the supervisor's: it may adopt an
        # unsupervised predecessor (plan-4 4.4 / r1 #m-9).
        "RMX_SUPERVISED": "1",
    }
    # No PYTHONPATH / PYTHONUSERBASE capture: the daemon runs from a
    # standalone venv (`rmx` resolves to .venv/bin/rmx) that carries every
    # dependency itself. Bridging in framework/system site-packages was a
    # crutch for an incomplete venv and is deliberately not done here.
    #
    # Only bake RMX_PARTITION when it OVERRIDES the project-scoped default —
    # an env var that merely restates the default is noise (the daemon
    # resolves the same value from the root on its own).
    from refmatrix.store import default_partition_name
    if partition and partition != default_partition_name(root):
        env["RMX_PARTITION"] = partition

    plist: dict = {
        "Label": label,
        "ProgramArguments": args,
        "WorkingDirectory": str(root.parent),
        "EnvironmentVariables": env,
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": DEFAULT_THROTTLE_SECONDS,
        # SIGTERM → this many seconds → SIGKILL, on kickstart -k and bootout.
        # launchd's default (5 s) killed five draining daemons in one night.
        "ExitTimeOut": int(EXIT_TIMEOUT_S),
        "StandardOutPath": str(root / "daemon.stdout.log"),
        "StandardErrorPath": str(root / "daemon.stderr.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(plist)


# ---- hub (the user-level control plane, distinct from per-store daemons) ----

HUB_LABEL = "com.refmatrix.hub"


def hub_plist_path() -> Path:
    return LAUNCH_AGENTS_DIR / f"{HUB_LABEL}.plist"


def render_hub_plist(*, port: int = 7777, host: str = "127.0.0.1",
                     rmx: "str | None" = None, allow_dev: bool = False) -> bytes:
    """Render the hub LaunchAgent. Runs `rmx hub start --no-detach` so launchd
    owns the process; KeepAlive restarts it on crash, RunAtLoad starts it at
    login.

    `rmx` is the CALLER's binary, exactly as `render_plist` takes it. plan-4
    Q15 gave the eight daemon plists a dev-tree refusal and edited this
    function two lines below the untouched `_rmx_path()` call, so the hub
    plist kept baking whatever `which rmx` returned — with `RMX_BIN` aimed at
    a dev binary, `ProgramArguments[0]` became the dev tree and nothing
    objected (bug-028). The hub is the fleet's watchdog, the owner of the
    shared model workers and the version handshake, so it is the worst plist
    to leave unguarded."""
    rmx = rmx or _rmx_path()
    if not allow_dev:
        _refuse_dev_tree(rmx)
    home = Path.home() / ".refmatrix"
    env: dict = {
        "PATH": launchd_path(rmx),
        # The hub forks per-project daemons; same fork-safety guard.
        "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
        "TOKENIZERS_PARALLELISM": "false",
    }
    # Pass through the queue-alert interval if set; <=0 disables the alerts.
    # The hub owns the fleet's model workers, so the idle-evict knob has to
    # reach ITS process — a per-daemon `RMX_WORKER_IDLE_S` is a no-op under
    # sharing (each daemon holds a `SharedWorkerClient` that refuses to kill a
    # model six other projects are using).
    idle = os.environ.get("RMX_WORKER_IDLE_S")
    if idle:
        env["RMX_WORKER_IDLE_S"] = idle

    qa = os.environ.get("RMX_HUB_QUEUE_ALERT_INTERVAL")
    if qa:
        env["RMX_HUB_QUEUE_ALERT_INTERVAL"] = qa
    plist: dict = {
        "Label": HUB_LABEL,
        "ProgramArguments": [rmx, "hub", "start", "--no-detach",
                             "--port", str(port), "--host", host],
        "EnvironmentVariables": env,
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": DEFAULT_THROTTLE_SECONDS,
        # the hub closes its model workers and the bus on SIGTERM; launchd's
        # 5 s default SIGKILLed it mid-close on 2026-09-15 04:26 (bug-020)
        "ExitTimeOut": int(EXIT_TIMEOUT_S),
        "StandardOutPath": str(home / "hub.stdout.log"),
        "StandardErrorPath": str(home / "hub.stderr.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(plist)


def hub_is_loaded() -> bool:
    if sys.platform != "darwin":
        return False
    return subprocess.run(_print_cmd(HUB_LABEL), capture_output=True).returncode == 0


# After a bootstrap, how long to wait before re-checking that the label is
# still loaded (a late bootout completing removes it — bug-022).
HUB_SETTLE_S = float(os.environ.get("RMX_HUB_SETTLE_S", "2") or "2")


def _wait_hub_loaded(*, expected: bool, timeout: float) -> bool:
    """Poll `hub_is_loaded()` until it equals `expected` or `timeout` elapses."""
    deadline = time.time() + timeout
    while True:
        if hub_is_loaded() == expected:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.1)


def _stop_hub_before_bootout(grace: float = EXIT_TIMEOUT_S) -> bool:
    """Send the hub's `stop` op and wait until its control socket stops
    answering (it exits 0; KeepAlive SuccessfulExit:false does not respawn
    it). Returns True when the hub is gone within `grace`."""
    import sys as _sys
    import time as _time
    from refmatrix import hub as _hub
    try:
        _hub.rpc("stop", {}, timeout=5.0)
    except Exception as e:  # noqa: BLE001 — said; launchd's bootout signals it
        _sys.stderr.write(f"hub stop op not delivered ({type(e).__name__}: {e}); "
                          f"launchctl bootout will signal it\n")
        return False
    deadline = _time.monotonic() + grace
    while _time.monotonic() < deadline:
        try:
            _hub.rpc("ping", {}, timeout=1.0)
        except Exception:  # noqa: BLE001 — the socket is gone: the hub exited
            return True
        _time.sleep(0.2)
    _sys.stderr.write(f"hub still answering {grace:g}s after its stop op; "
                      f"launchctl bootout will signal it\n")
    return False


def install_hub(*, port: int = 7777, host: str = "127.0.0.1",
                force: bool = False, rmx: "str | None" = None,
                allow_dev: bool = False) -> Path:
    """Write + bootstrap the hub LaunchAgent. Idempotent unless force.

    The dev-tree refusal runs FIRST — before the stop order, before the
    bootout, before the write. A refusal that fired later would already have
    torn down a working hub to reject the binary that was going to replace it
    (bug-028, bug-023's shape)."""
    _require_darwin()
    rmx = rmx or _rmx_path()
    if not allow_dev:
        _refuse_dev_tree(rmx)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    (Path.home() / ".refmatrix").mkdir(parents=True, exist_ok=True)
    p = hub_plist_path()
    if p.exists() and hub_is_loaded() and not force:
        return p
    if hub_is_loaded():
        # A forced reinstall boots the job out = SIGTERM + a SIGKILL at the
        # OLD plist's ExitTimeOut (5 s before this key existed). Ask the hub
        # to stop first and wait for it to go (bounded by the grace); a hub
        # that does not answer is said and left to launchd's signal.
        _stop_hub_before_bootout()
    if hub_is_loaded():
        subprocess.run(_bootout_cmd(HUB_LABEL), capture_output=True)
        # WAIT for the domain to release the label — bug-013's shape, hub
        # twin (bug-022, live 2026-09-15 05:27: a 3 s wait let the bootstrap
        # land on a job still unloading; launchd then finished the bootout
        # and the hub label was simply gone). A bootout that does not
        # complete is an error, never a shrug.
        if not _wait_hub_loaded(expected=False, timeout=BOOTOUT_WAIT_S):
            raise RuntimeError(
                f"launchctl bootout did not unload {HUB_LABEL} within {BOOTOUT_WAIT_S:g}s "
                f"— the old job is still loaded (draining?); plist NOT rewritten. "
                f"Retry, or `launchctl bootout {_domain()}/{HUB_LABEL}` by hand")
    p.write_bytes(render_hub_plist(port=port, host=host, rmx=rmx,
                                   allow_dev=allow_dev))
    p.chmod(0o644)
    def _bootstrap_once() -> bool:
        subprocess.run(_bootstrap_cmd(p), capture_output=True, text=True)
        if _wait_hub_loaded(expected=True, timeout=10.0):
            return True
        # legacy fallback for a domain that refuses `bootstrap`
        subprocess.run(["launchctl", "load", str(p)], capture_output=True)
        return _wait_hub_loaded(expected=True, timeout=3.0)

    if not _bootstrap_once():
        raise RuntimeError(
            f"launchctl did not load the hub agent — `launchctl print {_domain()}/{HUB_LABEL}`")
    # A bootstrap that raced a late unload reads "loaded" for a moment and is
    # gone a second later (bug-022): settle, re-check, bootstrap once more.
    time.sleep(HUB_SETTLE_S)
    if not hub_is_loaded():
        if not _bootstrap_once():
            raise RuntimeError(
                f"{HUB_LABEL} unloaded itself after the bootstrap and a second bootstrap "
                f"did not load it — `launchctl print {_domain()}/{HUB_LABEL}`")
    return p


def uninstall_hub() -> bool:
    _require_darwin()
    p = hub_plist_path()
    if hub_is_loaded():
        subprocess.run(_bootout_cmd(HUB_LABEL), capture_output=True)
    if p.exists():
        p.unlink()
        return True
    return False


def hub_status() -> dict:
    return {
        "label": HUB_LABEL,
        "plist_path": str(hub_plist_path()),
        "installed": hub_plist_path().exists(),
        "loaded": hub_is_loaded(),
    }


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _bootstrap_cmd(plist: Path) -> list[str]:
    return ["launchctl", "bootstrap", _domain(), str(plist)]


def _bootout_cmd(label: str) -> list[str]:
    return ["launchctl", "bootout", f"{_domain()}/{label}"]


def _print_cmd(label: str) -> list[str]:
    return ["launchctl", "print", f"{_domain()}/{label}"]


# How long a forced reinstall waits for `launchctl bootout` to actually remove
# a RUNNING label from the domain. The daemon drains its pools first (up to
# RMX_DAEMON_SHUTDOWN_TIMEOUT_S per pool), so 3 s was never enough: install
# bootstrapped against the still-loaded label, both attempts failed silently,
# and a moment later NOTHING was loaded — two fleet daemons ran standalone
# after `relaunch-fleet` (bug-013, 2026-09-15).
BOOTOUT_WAIT_S = float(os.environ.get("RMX_LAUNCHCTL_BOOTOUT_WAIT_S", "45") or "45")


def is_installed(root: Path) -> bool:
    return plist_path(root).exists()


def loaded_env(root: Path) -> "dict[str, str] | None":
    """The `environment = { K => V }` block of `launchctl print` for the
    label — what launchd will actually export to the job, as opposed to what
    the plist file on disk says. None when the label is not loaded."""
    if sys.platform != "darwin":
        return None
    r = subprocess.run(_print_cmd(label_for_root(root)), capture_output=True, text=True)
    if r.returncode != 0:
        return None
    env: dict[str, str] = {}
    inside = False
    for line in r.stdout.splitlines():
        s = line.strip()
        if not inside:
            if s == "environment = {":
                inside = True
            continue
        if s == "}":
            break
        if " => " in s:
            k, v = s.split(" => ", 1)
            env[k.strip()] = v.strip()
    return env


def _loaded_env_drift(root: Path, rendered: bytes) -> "list[str]":
    """Keys/values the rendered plist exports that the LOADED job lacks."""
    import plistlib
    want = (plistlib.loads(rendered).get("EnvironmentVariables") or {})
    have = loaded_env(root)
    if have is None:
        return ["label not loaded"]
    out = []
    for k, v in want.items():
        if k not in have:
            out.append(f"loaded job env {k} missing")
        elif have[k] != v:
            out.append(f"loaded job env {k}: loaded {have[k]!r} != rendered {v!r}")
    return out


def is_loaded(root: Path) -> bool:
    """Return True if the label is currently bootstrapped into the
    user's gui domain. `launchctl print` exits 0 when found."""
    if sys.platform != "darwin":
        return False
    label = label_for_root(root)
    r = subprocess.run(_print_cmd(label), capture_output=True)
    return r.returncode == 0


def _require_darwin() -> None:
    if sys.platform != "darwin":
        raise RuntimeError(
            "launchctl integration is macOS-only. Linux supervisor "
            "support (systemd user unit) is not yet implemented."
        )


def _wait_loaded(root: Path, *, expected: bool, timeout: float = 3.0) -> bool:
    """Poll `is_loaded` until it matches `expected` or `timeout` elapses.
    launchctl bootout/bootstrap don't take effect synchronously — the
    label can take a few hundred ms to enter or leave the domain.
    Returns True if the expected state was observed within the window."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_loaded(root) == expected:
            return True
        time.sleep(0.1)
    return is_loaded(root) == expected


def check_hub(*, rmx: "str | None" = None, port: int = 7777,
              host: str = "127.0.0.1") -> "tuple[bool, str]":
    """Installed hub plist == its render. The twin of `check(root, rmx=)`.

    This did not exist. A drifted DAEMON plist is caught on every
    `relaunch-fleet`; nothing ever compared the hub's, so a hub plist aimed at
    a dev tree — or rendered before a key existed — survived every deploy
    silently (bug-028). A dev-tree or unknown binary is NOT drift: it is a
    `CheckReason(kind="identity")`, which the CLI reports as "binary not
    verified" and never prescribes a reinstall for (r5 #m-1, task 4.6)."""
    import plistlib
    rmx = rmx or _rmx_path()
    objection = _identity_objection(rmx)
    if objection is not None:
        # Not drift: `relaunch-fleet` "fixes" drift by reinstalling, and an
        # unknown or dev binary must never be the one it reinstalls (r4 #s-2).
        return False, CheckReason(
            f"{objection}; the hub plist is not rendered against it — "
            f"run with the deployed rmx", kind="identity")
    p = hub_plist_path()
    if not p.exists():
        return False, CheckReason(f"{p} does not exist — `rmx hub launchctl install`",
                                  kind="missing")
    installed = p.read_bytes()
    rendered = render_hub_plist(port=port, host=host, rmx=rmx)
    if installed == rendered:
        if not hub_is_loaded():
            return False, CheckReason(f"{p} is current but {HUB_LABEL} is not loaded — "
                                      f"`rmx hub launchctl install`", kind="unloaded")
        return True, ""
    why = plist_diff(plistlib.loads(installed), plistlib.loads(rendered))
    return False, CheckReason(f"{p} drifted from its render: "
                              + "; ".join(why or ["bytes differ"]), kind="drift")


def install(root: Path, *, partition: str | None = None,
            watch: bool = True, debounce_ms: int = 500,
            semantic: bool = False, force: bool = False,
            watch_roots: "list[Path] | None" = None,
            rmx: "str | None" = None, allow_dev: bool = False) -> Path:
    """Write the plist + bootstrap it into the user's gui domain.
    Returns the plist path. Idempotent unless `force=True`. Refuses a
    dev-tree `rmx` unless `allow_dev` (r3 #s-4) — BEFORE anything is
    booted out or written."""
    _require_darwin()
    rmx = rmx or _rmx_path()
    if not allow_dev:
        _refuse_dev_tree(rmx)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = plist_path(root)
    label = label_for_root(root)

    # Adopt the slugged label over any legacy hash-only agent for this
    # root before deciding whether we're already installed.
    _migrate_legacy(root)

    if p.exists() and is_loaded(root) and not force:
        return p

    # If already loaded, bootout and WAIT until the domain has released the
    # label — a running daemon drains its pools first, so this takes seconds.
    # Bootstrapping before the bootout settles silently no-ops (bootstrap
    # returns 0 or 37 but the OLD job stays, then leaves), which is how two
    # fleet daemons ended up standalone after `relaunch-fleet` (bug-013).
    # A bootout that does not complete is an error, never a shrug.
    if is_loaded(root):
        # A bootout is launchd's SIGTERM + a SIGKILL at ExitTimeOut — and on a
        # plist rendered before ExitTimeOut existed that is the 5 s default,
        # so the drift fixer itself would SIGKILL a draining daemon on its
        # first run (ch-bsd plan-4 r3 #b-1). Ask the daemon to stop FIRST
        # with the grace: a clean stop exits 0, which KeepAlive
        # (SuccessfulExit: false) does not respawn, so the bootout then
        # unloads an idle job. Lazy import: daemon imports this module.
        # The grace is `stop_grace_s()`, not the constant: reading
        # EXIT_TIMEOUT_S here bypassed the operator's RMX_STOP_GRACE_S, the
        # one override every other stop path honours (r4 #s-3, task 4.5 R2).
        from refmatrix import daemon as _daemon
        _daemon.graceful_stop(root, grace=_daemon.stop_grace_s())
        subprocess.run(_bootout_cmd(label), capture_output=True)
        if not _wait_loaded(root, expected=False, timeout=BOOTOUT_WAIT_S):
            raise RuntimeError(
                f"launchctl bootout did not unload {label} within {BOOTOUT_WAIT_S:g}s "
                f"— the old job is still loaded (draining?); plist NOT rewritten. "
                f"Retry, or `launchctl bootout {_domain()}/{label}` by hand")

    rendered = render_plist(
        root, partition=partition, watch=watch,
        debounce_ms=debounce_ms, semantic=semantic,
        watch_roots=watch_roots, rmx=rmx,
    )
    p.write_bytes(rendered)
    p.chmod(0o644)

    # Bootstrap, then verify the label actually registered. Some races
    # produce a zero exit code without loading the agent; the only
    # reliable signal is `launchctl print` succeeding afterward.
    r = subprocess.run(_bootstrap_cmd(p), capture_output=True, text=True)
    bootstrap_err = (r.stderr.strip() or r.stdout.strip()
                     if r.returncode != 0 else "")

    if not _wait_loaded(root, expected=True, timeout=3.0):
        r2 = subprocess.run(
            ["launchctl", "load", str(p)],
            capture_output=True, text=True,
        )
        if not _wait_loaded(root, expected=True, timeout=3.0):
            load_err = r2.stderr.strip() or r2.stdout.strip() or "(silent)"
            raise RuntimeError(
                f"launchctl bootstrap did not load the agent "
                f"(rc={r.returncode}, err={bootstrap_err!r}); "
                f"load fallback also failed: {load_err}"
            )
    # Loaded is not enough: the job launchd holds must export what the
    # rendered plist says (a stale definition survives a failed reload).
    drift = _loaded_env_drift(root, rendered)
    if drift:
        raise RuntimeError(
            f"{label} is loaded but not from the plist just written: "
            + "; ".join(drift) + " — `launchctl bootout` it and install again")
    return p


def installed_flags(root: Path) -> dict:
    """The install-time flags, recovered from the installed plist's
    ProgramArguments (watch / debounce_ms / semantic / watch_roots) and its
    RMX_PARTITION env — what `render_plist` needs to re-render the SAME
    plist. Raises FileNotFoundError when nothing is installed."""
    import plistlib
    p = plist_path(root)
    if not p.exists():
        raise FileNotFoundError(f"not installed: {p}")
    data = plistlib.loads(p.read_bytes())
    args = list(data.get("ProgramArguments") or [])
    flags: dict = {"watch": True, "debounce_ms": 500, "semantic": False,
                   "watch_roots": None, "partition": None}
    roots: list[Path] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--no-watch":
            flags["watch"] = False
        elif a == "--semantic":
            flags["semantic"] = True
        elif a == "--debounce-ms" and i + 1 < len(args):
            flags["debounce_ms"] = int(args[i + 1]); i += 1
        elif a == "--watch-root" and i + 1 < len(args):
            roots.append(Path(args[i + 1])); i += 1
        i += 1
    if roots:
        flags["watch_roots"] = roots
    env = data.get("EnvironmentVariables") or {}
    if env.get("RMX_PARTITION"):
        flags["partition"] = env["RMX_PARTITION"]
    return flags


def check(root: Path, *, rmx: "str | None" = None) -> "tuple[bool, str]":
    """Installed plist == its render (the `install-hooks --check` shape for
    plists). Until 2026-09-14 nothing compared the two: `relaunch-fleet`
    restarted two stores on plists rendered before `RMX_SUPERVISED` existed
    and the supervised start on them exited 1 into the KeepAlive loop
    (ch-bsd plan-4 r2 #b-1). Returns (True, "") or (False, CheckReason). The
    render bakes `rmx` — the caller's binary. A dev-tree or unknown binary is
    `kind="identity"`, not drift (r3 #s-4, r5 #m-1): from a dev shell every
    plist read as drifted and `reinstall` would have pointed all eight at the
    dev venv."""
    import plistlib
    rmx = rmx or _rmx_path()
    objection = _identity_objection(rmx)
    if objection is not None:
        # Not drift: `relaunch-fleet` -> `reinstall` would "fix" it by
        # rewriting the plist to this binary (r4 #s-2).
        return False, CheckReason(f"{objection}; the plists are not rendered against it — "
                                  f"run with the deployed rmx", kind="identity")
    p = plist_path(root)
    try:
        flags = installed_flags(root)
    except FileNotFoundError as e:
        return False, CheckReason(str(e), kind="missing")
    installed = p.read_bytes()
    rendered = render_plist(root, rmx=rmx, **flags)
    if installed == rendered:
        # The file is current; is the JOB? An installed-but-unloaded label
        # (bug-013) or a loaded job from an older definition is drift too.
        if not is_loaded(root):
            return False, CheckReason(
                f"{p} is current but its label {label_for_root(root)} is "
                f"not loaded — `rmx daemon launchctl install`", kind="unloaded")
        drift = _loaded_env_drift(root, rendered)
        if drift:
            return False, CheckReason(
                f"{p} is current but the loaded job runs an older definition: "
                + "; ".join(drift)
                + " — bootout/bootstrap needed (`rmx daemon launchctl install --force`)",
                kind="drift")
        return True, ""
    why = plist_diff(plistlib.loads(installed), plistlib.loads(rendered))
    return False, CheckReason(f"{p} drifted from its render: "
                              + "; ".join(why or ["bytes differ"]), kind="drift")


def reinstall(root: Path, *, rmx: "str | None" = None) -> Path:
    """Re-render + reload an installed plist with its own flags, then VERIFY
    the label is loaded — `install --force` has left a label unloaded
    (thiquet, 2026-09-14), so a plain install follows when it did. `rmx` is
    the caller's binary (r3 #s-4)."""
    flags = installed_flags(root)
    p = install(root, force=True, rmx=rmx, **flags)
    if not is_loaded(root):
        p = install(root, rmx=rmx, **flags)
    ok, why = check(root, rmx=rmx)
    if not ok:
        raise RuntimeError(f"reinstall did not converge: {why}")
    return p


def uninstall(root: Path) -> bool:
    """Bootout the agent (if loaded) and remove the plist file.
    Returns True if a plist was removed, False if there was nothing
    to remove."""
    _require_darwin()
    p = plist_path(root)
    label = label_for_root(root)

    # Clean up a legacy hash-only agent too, so uninstall fully removes a
    # store that was installed under either naming scheme.
    removed = _migrate_legacy(root)

    if is_loaded(root):
        r = subprocess.run(_bootout_cmd(label),
                           capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(
                ["launchctl", "unload", str(p)],
                capture_output=True,
            )

    if p.exists():
        p.unlink()
        removed = True
    return removed


def kickstart(root: Path, *, restart: bool = False) -> str:
    """Start (or restart, when `restart`) the supervised LaunchAgent for
    `root` via `launchctl kickstart`. Returns the label kicked.

    `kickstart` starts the service if it is down and no-ops if it is
    already running; `-k` (restart=True) force-restarts a running one.
    Raises RuntimeError if the agent isn't loaded — callers that want a
    best-effort path (e.g. a SessionStart hook) should fall back to
    `rmx daemon start` on failure."""
    _require_darwin()
    if not is_loaded(root):
        raise RuntimeError(
            f"LaunchAgent for {root} not loaded. "
            f"Run `rmx daemon launchctl install` first."
        )
    label = label_for_root(root)
    args = ["launchctl", "kickstart"]
    if restart:
        args.append("-k")
    args.append(f"{_domain()}/{label}")
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"launchctl kickstart failed (rc={r.returncode}): "
            f"{r.stderr.strip() or r.stdout.strip() or '(silent)'}"
        )
    return label


def _watchdog_pause(root: Path, seconds: float, log) -> None:
    """Tell the hub an operator is restarting `root` (a restart is not a
    wedge): the hub's no-process branch kicked five relaunching daemons
    inside launchd's ThrottleInterval on 2026-09-15 (ch-bsd plan-4 r3 #s-3).
    `refmatrix.hub.rpc` is looked up at call time. A hub that is down is
    said and the restart proceeds — never fatal, never silent."""
    from refmatrix import hub as _hub
    try:
        _hub.rpc("pause", {"root": str(root), "seconds": float(seconds)}, timeout=3.0)
    except Exception as e:  # noqa: BLE001 — said, then the restart proceeds
        log(f"hub watchdog not paused ({type(e).__name__}: {e}); restarting anyway")


def _watchdog_resume(root: Path, log) -> None:
    from refmatrix import hub as _hub
    try:
        _hub.rpc("resume", {"root": str(root)}, timeout=3.0)
    except Exception as e:  # noqa: BLE001 — said; the pause expires on its own
        log(f"hub watchdog not resumed ({type(e).__name__}: {e}); "
            f"the pause expires on its own")


def supervised_restart(root: Path, *, log=print) -> "tuple[str, bool]":
    """Restart a launchd-supervised daemon the ONE way: pause the hub
    watchdog for `root` (grace * 2 + 60 s), `daemon.graceful_stop` with
    `stop_grace_s()`, `kickstart` WITHOUT -k when it stopped (a clean stop
    exits 0, which KeepAlive SuccessfulExit:false does not respawn — the kick
    starts it) and -k only when it ignored the stop — said, because that -k
    is launchd's SIGTERM + SIGKILL at ExitTimeOut — then resume the watchdog
    in a `finally`. Returns `(label, stopped)`.

    Lifted unchanged out of `rmx daemon restart` (r3 #b-1) so `rmx upgrade`
    stops hand-rolling a bare `kickstart -k` that SIGKILLed draining daemons
    (ch-bsd plan-4 r5 #b-1; task 4.6, 2026-10-19). A `kickstart` failure
    PROPAGATES: both callers report it, and neither falls through to a
    standalone stop of a supervised daemon (bug-013's state)."""
    from refmatrix import daemon as _daemon
    grace = _daemon.stop_grace_s()
    _watchdog_pause(root, grace * 2 + 60.0, log)
    try:
        stopped = _daemon.graceful_stop(root, grace=grace)
        if not stopped:
            log(f"predecessor still alive after the {grace:g}s grace; launchd "
                f"kickstart -k will SIGTERM it and SIGKILL it at ExitTimeOut "
                f"({EXIT_TIMEOUT_S:g}s)")
        label = kickstart(root, restart=not stopped)
    finally:
        _watchdog_resume(root, log)
    return label, bool(stopped)


def status(root: Path) -> dict:
    """Snapshot status for the active store."""
    return {
        "label": label_for_root(root),
        "plist_path": str(plist_path(root)),
        "installed": is_installed(root),
        "loaded": is_loaded(root),
    }
