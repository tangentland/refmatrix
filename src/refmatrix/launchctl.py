"""macOS launchd LaunchAgent generator + install/uninstall for `rmx daemon`.

One plist per refmatrix root, installed in `~/Library/LaunchAgents/`. Runs
`rmx daemon start --no-detach` so launchd owns the process lifecycle and
KeepAlive can restart on crash.
"""
from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path


LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_THROTTLE_SECONDS = 10


def label_for_root(root: Path) -> str:
    """Stable, collision-free reverse-DNS label per refmatrix root."""
    h = hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:12]
    return f"com.refmatrix.daemon.{h}"


def plist_path(root: Path) -> Path:
    return LAUNCH_AGENTS_DIR / f"{label_for_root(root)}.plist"


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
    }
    # launchd starts agents with a minimal environment. Capture the
    # caller's PYTHONPATH + PYTHONUSERBASE so the daemon's Python
    # sees the same site-packages dirs the interactive shell does
    # (some installs put big deps like torch / typing_extensions
    # in framework-shared paths, not the venv).
    pythonpath = os.environ.get("PYTHONPATH")
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    pythonuserbase = os.environ.get("PYTHONUSERBASE")
    if pythonuserbase:
        env["PYTHONUSERBASE"] = pythonuserbase
    if partition:
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
        return True
    return False


def status(root: Path) -> dict:
    """Snapshot status for the active store."""
    return {
        "label": label_for_root(root),
        "plist_path": str(plist_path(root)),
        "installed": is_installed(root),
        "loaded": is_loaded(root),
    }
