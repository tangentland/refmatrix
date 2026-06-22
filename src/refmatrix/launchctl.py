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
                 watch_roots: "list[Path] | None" = None) -> bytes:
    """Render the plist for `root` as bytes (XML).

    `watch_roots` — optional list of dirs the daemon should watch. When
    omitted, the daemon defaults to watching the parent of `.refmatrix/`
    (the project root). Pass an explicit list to watch additional paths
    such as the auto-memory dir alongside the project tree.
    """
    root = Path(root).resolve()
    label = label_for_root(root)
    rmx = _rmx_path()

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
        "StandardOutPath": str(home / "hub.stdout.log"),
        "StandardErrorPath": str(home / "hub.stderr.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(plist)


def hub_is_loaded() -> bool:
    if sys.platform != "darwin":
        return False
    return subprocess.run(_print_cmd(HUB_LABEL), capture_output=True).returncode == 0


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


def is_installed(root: Path) -> bool:
    return plist_path(root).exists()


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
            watch_roots: "list[Path] | None" = None) -> Path:
    """Write the plist + bootstrap it into the user's gui domain.
    Returns the plist path. Idempotent unless `force=True`."""
    _require_darwin()
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = plist_path(root)
    label = label_for_root(root)

    # Adopt the slugged label over any legacy hash-only agent for this
    # root before deciding whether we're already installed.
    _migrate_legacy(root)

    if p.exists() and is_loaded(root) and not force:
        return p

    # If already loaded, bootout and wait for the domain to release the
    # label. Issuing bootstrap before the bootout settles silently no-ops
    # on some macOS versions — bootstrap returns 0 but the agent never
    # actually enters the domain.
    if is_loaded(root):
        subprocess.run(_bootout_cmd(label), capture_output=True)
        _wait_loaded(root, expected=False, timeout=3.0)

    p.write_bytes(render_plist(
        root, partition=partition, watch=watch,
        debounce_ms=debounce_ms, semantic=semantic,
        watch_roots=watch_roots,
    ))
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
