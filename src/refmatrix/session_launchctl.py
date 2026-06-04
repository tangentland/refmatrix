"""LaunchAgent for the session-index backfill ticker (Phase D).

One plist per refmatrix root, separate from `rmx daemon`'s LaunchAgent.
Periodically runs `rmx session ingest` to ingest any new Claude Code
session JSONLs into the `sessions-<project>` partition. Eventual
consistency, no hook dependency.

Shape differs from `launchctl.py`:
- Not a daemon: runs once per StartInterval, exits.
- No KeepAlive (would re-spawn the one-shot in a tight loop).
- No --watch flag — it's a periodic ingest, not a file watcher.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from refmatrix.launchctl import (
    LAUNCH_AGENTS_DIR,
    _bootout_cmd,
    _bootstrap_cmd,
    _domain,
    _print_cmd,
    _require_darwin,
    _rmx_path,
    _short_hash,
    _slug_for_root,
)

LABEL_PREFIX = "com.refmatrix.session-indexer"
DEFAULT_INTERVAL_SECONDS = 600  # 10 min


def label_for_root(root: Path) -> str:
    """`com.refmatrix.session-indexer.<slug>-<hash12>` — same shape as the
    daemon label but with a distinct prefix so the two coexist."""
    return f"{LABEL_PREFIX}.{_slug_for_root(root)}-{_short_hash(root)}"


def plist_path(root: Path) -> Path:
    return LAUNCH_AGENTS_DIR / f"{label_for_root(root)}.plist"


def render_plist(root: Path, *, partition: str | None = None,
                 interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
                 all_projects: bool = False) -> bytes:
    """Render the session-indexer plist for `root` as XML bytes.

    `all_projects=True` walks every project under ~/.claude/projects/ on
    each tick. Default (False) scopes to the project matching the active
    root's cwd — matches `rmx session ingest`'s default behaviour."""
    root = Path(root).resolve()
    label = label_for_root(root)
    rmx = _rmx_path()

    args: list[str] = [rmx, "session", "ingest"]
    if all_projects:
        args.append("--all-projects")

    env = {
        "REFMATRIX_ROOT": str(root),
        "PATH": os.environ.get(
            "PATH", "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"
        ),
    }
    from refmatrix.store import default_partition_name
    if partition and partition != default_partition_name(root):
        env["RMX_PARTITION"] = partition

    plist: dict = {
        "Label": label,
        "ProgramArguments": args,
        "WorkingDirectory": str(root.parent),
        "EnvironmentVariables": env,
        "RunAtLoad": True,
        "StartInterval": int(interval_seconds),
        "StandardOutPath": str(root / "session-indexer.stdout.log"),
        "StandardErrorPath": str(root / "session-indexer.stderr.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(plist)


def is_installed(root: Path) -> bool:
    return plist_path(root).exists()


def is_loaded(root: Path) -> bool:
    label = label_for_root(root)
    r = subprocess.run(_print_cmd(label), capture_output=True)
    return r.returncode == 0


def install(root: Path, *, partition: str | None = None,
            interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
            all_projects: bool = False, force: bool = False) -> Path:
    """Write the plist + bootstrap it. Returns the plist path."""
    _require_darwin()
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = plist_path(root)
    label = label_for_root(root)

    if p.exists() and is_loaded(root) and not force:
        return p

    if is_loaded(root):
        subprocess.run(_bootout_cmd(label), capture_output=True)

    p.write_bytes(render_plist(
        root, partition=partition,
        interval_seconds=interval_seconds,
        all_projects=all_projects,
    ))
    p.chmod(0o644)

    r = subprocess.run(_bootstrap_cmd(p), capture_output=True, text=True)
    if r.returncode != 0 and not is_loaded(root):
        # Fall back to legacy `launchctl load`
        r2 = subprocess.run(
            ["launchctl", "load", str(p)], capture_output=True, text=True,
        )
        if r2.returncode != 0 and not is_loaded(root):
            err = (r.stderr or r.stdout or "").strip() or "(silent)"
            raise RuntimeError(
                f"failed to load session-indexer LaunchAgent: {err}"
            )
    return p


def uninstall(root: Path) -> bool:
    """Bootout + remove the plist. Returns True if anything was removed."""
    _require_darwin()
    p = plist_path(root)
    label = label_for_root(root)
    removed = False
    if is_loaded(root):
        r = subprocess.run(_bootout_cmd(label),
                           capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(
                ["launchctl", "unload", str(p)], capture_output=True,
            )
    if p.exists():
        p.unlink()
        removed = True
    return removed
