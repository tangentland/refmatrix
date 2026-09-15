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
import shutil
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
# plus the thread joins and a bounded DuckDB close — up to ~50 s. Five
# daemons were SIGKILLed mid-drain on 2026-09-15 by a deploy that never put
# the two numbers side by side (ch-bsd plan-4 r3 #b-1). ONE number for every
# supervisor: the plist's ExitTimeOut, the hub's kill grace and the CLI's
# stop grace all read it.
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


def _refuse_dev_tree(rmx: str) -> None:
    ident = binary_identity(rmx)
    if ident.get("dev_tree"):
        raise RuntimeError(
            f"refusing to render a plist against a dev tree: {rmx} imports "
            f"{ident.get('import_path')} (a venv that belongs to another tree). "
            f"Run this with the deployed rmx, or pass allow_dev to install")


def _rmx_path() -> str:
    override = os.environ.get("RMX_BIN")
    if override:
        return override
    p = shutil.which("rmx")
    if p:
        return p
    raise FileNotFoundError(
        "`rmx` not found on PATH. Install refmatrix system-wide "
        "(e.g. `pipx install refmatrix`) before generating a launchd "
        "plist, or set $RMX_BIN to the absolute path."
    )


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
    `$RMX_BIN` / `which rmx` (ch-bsd plan-4 r3 #s-4).
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
        "PATH": os.environ.get(
            "PATH", "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"
        ),
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


def render_hub_plist(*, port: int = 7777, host: str = "127.0.0.1") -> bytes:
    """Render the hub LaunchAgent. Runs `rmx hub start --no-detach` so launchd
    owns the process; KeepAlive restarts it on crash, RunAtLoad starts it at
    login."""
    rmx = _rmx_path()
    home = Path.home() / ".refmatrix"
    env: dict = {
        "PATH": os.environ.get(
            "PATH", "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"),
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
                force: bool = False) -> Path:
    """Write + bootstrap the hub LaunchAgent. Idempotent unless force."""
    _require_darwin()
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
        deadline = time.time() + 3.0
        while time.time() < deadline and hub_is_loaded():
            time.sleep(0.1)
    p.write_bytes(render_hub_plist(port=port, host=host))
    p.chmod(0o644)
    r = subprocess.run(_bootstrap_cmd(p), capture_output=True, text=True)
    deadline = time.time() + 3.0
    while time.time() < deadline and not hub_is_loaded():
        time.sleep(0.1)
    if not hub_is_loaded():
        subprocess.run(["launchctl", "load", str(p)], capture_output=True)
        deadline = time.time() + 3.0
        while time.time() < deadline and not hub_is_loaded():
            time.sleep(0.1)
    if not hub_is_loaded():
        raise RuntimeError(
            f"launchctl did not load the hub agent "
            f"(rc={r.returncode}, err={r.stderr.strip() or '(silent)'})")
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
        from refmatrix import daemon as _daemon
        _daemon.graceful_stop(root, grace=EXIT_TIMEOUT_S)
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
    (ch-bsd plan-4 r2 #b-1). Returns (True, "") or (False, why). The render
    bakes `rmx` — the caller's binary — and a dev-tree binary is named as
    drift that must NOT be "fixed" (r3 #s-4): from a dev shell every plist
    read as drifted and `reinstall` would have pointed all eight at the
    dev venv."""
    import plistlib
    rmx = rmx or _rmx_path()
    ident = binary_identity(rmx)
    if ident.get("dev_tree"):
        return False, (f"{rmx} is a dev tree ({ident.get('import_path')}); the plists "
                       f"are not rendered against it — run with the deployed rmx")
    p = plist_path(root)
    try:
        flags = installed_flags(root)
    except FileNotFoundError as e:
        return False, str(e)
    installed = p.read_bytes()
    rendered = render_plist(root, rmx=rmx, **flags)
    if installed == rendered:
        # The file is current; is the JOB? An installed-but-unloaded label
        # (bug-013) or a loaded job from an older definition is drift too.
        if not is_loaded(root):
            return False, (f"{p} is current but its label {label_for_root(root)} is "
                           f"not loaded — `rmx daemon launchctl install`")
        drift = _loaded_env_drift(root, rendered)
        if drift:
            return False, (f"{p} is current but the loaded job runs an older "
                           f"definition: " + "; ".join(drift)
                           + " — bootout/bootstrap needed (`rmx daemon launchctl install --force`)")
        return True, ""
    have = plistlib.loads(installed)
    want = plistlib.loads(rendered)
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
    return False, f"{p} drifted from its render: " + "; ".join(why or ["bytes differ"])


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


def status(root: Path) -> dict:
    """Snapshot status for the active store."""
    return {
        "label": label_for_root(root),
        "plist_path": str(plist_path(root)),
        "installed": is_installed(root),
        "loaded": is_loaded(root),
    }
