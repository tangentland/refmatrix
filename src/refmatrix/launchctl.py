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
                 semantic: bool = False) -> bytes:
    """Render the plist for `root` as bytes (XML)."""
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


def install(root: Path, *, partition: str | None = None,
            watch: bool = True, debounce_ms: int = 500,
            semantic: bool = False, force: bool = False) -> Path:
    """Write the plist + bootstrap it into the user's gui domain.
    Returns the plist path. Idempotent unless `force=True`."""
    _require_darwin()
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = plist_path(root)
    label = label_for_root(root)

    if p.exists() and is_loaded(root) and not force:
        return p

    if is_loaded(root):
        subprocess.run(_bootout_cmd(label), capture_output=True)

    p.write_bytes(render_plist(
        root, partition=partition, watch=watch,
        debounce_ms=debounce_ms, semantic=semantic,
    ))
    p.chmod(0o644)

    r = subprocess.run(_bootstrap_cmd(p), capture_output=True, text=True)
    if r.returncode != 0:
        r2 = subprocess.run(
            ["launchctl", "load", str(p)],
            capture_output=True, text=True,
        )
        if r2.returncode != 0:
            raise RuntimeError(
                f"launchctl bootstrap failed: {r.stderr.strip() or r.stdout.strip()}; "
                f"load fallback also failed: "
                f"{r2.stderr.strip() or r2.stdout.strip()}"
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
