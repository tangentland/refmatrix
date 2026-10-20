"""LaunchAgent for the session-index backfill ticker (Phase D).

One plist per refmatrix root, separate from `rmx daemon`'s LaunchAgent.
Periodically runs `rmx session ingest` to ingest any new Claude Code
session JSONLs into the `sessions-<project>` partition. Eventual
consistency, no hook dependency.

Shape differs from `launchctl.py`:
- Not a daemon: runs once per StartInterval, exits.
- No KeepAlive (would re-spawn the one-shot in a tight loop).
- No --watch flag — it's a periodic ingest, not a file watcher.

Same lifecycle as the daemon plist since task 4.6 (ch-bsd plan-4 r5 #s-3,
2026-10-19): the binary comes from `launchctl._rmx_path()` and is refused when
it is not verified (`_refuse_dev_tree`, unless `allow_dev`); a forced install
waits for an in-flight tick instead of booting it out under the old plist's
5 s ExitTimeOut; `check` / `reinstall` / `installed_flags` mirror the daemon's
so `rmx hub relaunch-fleet` can re-render drifted session plists on deploy.
"""
from __future__ import annotations

import plistlib
import re
import subprocess
import time
from pathlib import Path

from refmatrix import launchctl as _lc
from refmatrix.launchctl import (
    EXIT_TIMEOUT_S,
    LAUNCH_AGENTS_DIR,
    CheckReason,
    _bootout_cmd,
    _bootstrap_cmd,
    _domain,
    _identity_objection,
    _print_cmd,
    _refuse_dev_tree,
    _require_darwin,
    _rmx_path,
    launchd_path,
    plist_diff,
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
                 all_projects: bool = False, rmx: "str | None" = None) -> bytes:
    """Render the session-indexer plist for `root` as XML bytes.

    `all_projects=True` walks every project under ~/.claude/projects/ on
    each tick. Default (False) scopes to the project matching the active
    root's cwd — matches `rmx session ingest`'s default behaviour. `rmx` is
    the caller's binary, else `_rmx_path()`; like the daemon render this
    stays pure — the identity guard lives in `install` (task 4.6 S3)."""
    root = Path(root).resolve()
    label = label_for_root(root)
    rmx = rmx or _rmx_path()

    args: list[str] = [rmx, "session", "ingest"]
    if all_projects:
        args.append("--all-projects")

    env = {
        "REFMATRIX_ROOT": str(root),
        # Fixed, not the installing shell's PATH (see `launchctl.launchd_path`).
        "PATH": launchd_path(rmx),
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
        # launchd's SIGKILL deadline after SIGTERM. Without the key it is
        # launchd's 5 s default, the number every other refmatrix plist left
        # behind at plan-4 r3; an ingest tick mid-write deserves the same
        # grace as the daemon. ONE source — `launchctl.EXIT_TIMEOUT_S` — so the
        # two plists cannot drift (ch-bsd plan-4 r4 #m-6; task 4.5 R4,
        # 2026-10-19).
        "ExitTimeOut": int(EXIT_TIMEOUT_S),
    }
    return plistlib.dumps(plist)


def is_installed(root: Path) -> bool:
    return plist_path(root).exists()


def is_loaded(root: Path) -> bool:
    label = label_for_root(root)
    r = subprocess.run(_print_cmd(label), capture_output=True)
    return r.returncode == 0


def running_pid(root: Path) -> "int | None":
    """The pid of the in-flight ingest tick, from the `pid = N` line of
    `launchctl print`; None when the label is not loaded or no tick runs."""
    r = subprocess.run(_print_cmd(label_for_root(root)), capture_output=True, text=True)
    if r.returncode != 0:
        return None
    m = re.search(r"^\s*pid = (\d+)\s*$", r.stdout or "", re.M)
    return int(m.group(1)) if m else None


def _wait_loaded(root: Path, *, expected: bool, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if is_loaded(root) == expected:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _wait_tick_done(root: Path, grace: float) -> None:
    """Wait up to `grace` for an in-flight tick to finish; raise when it
    outlives it. The tick is a one-shot ingest that ends on its own, so the
    wait IS the graceful stop — it is never signalled (task 4.6 S3.3)."""
    deadline = time.monotonic() + grace
    pid = running_pid(root)
    while pid is not None:
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"session-indexer tick pid {pid} for {root} is still running after the "
                f"{grace:g}s grace; the plist was NOT rewritten and the label was not "
                f"booted out (a bootout would SIGTERM a mid-write ingest). Retry when "
                f"the tick has finished")
        time.sleep(0.1)
        pid = running_pid(root)


def install(root: Path, *, partition: str | None = None,
            interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
            all_projects: bool = False, force: bool = False,
            rmx: "str | None" = None, allow_dev: bool = False) -> Path:
    """Write the plist + bootstrap it. Returns the plist path.

    The identity guard runs FIRST — before any bootout, write or bootstrap —
    exactly as the daemon and hub installs: this one had none, so a dev or
    unreadable binary was baked into the session plist unchallenged (ch-bsd
    plan-4 r5 #s-3; task 4.6, 2026-10-19). A forced reinstall on a loaded
    label waits for the in-flight tick (up to `daemon.stop_grace_s()`)
    before the bootout, then waits for the domain to release the label
    (bug-013's shape)."""
    _require_darwin()
    rmx = rmx or _rmx_path()
    if not allow_dev:
        _refuse_dev_tree(rmx)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = plist_path(root)
    label = label_for_root(root)

    if p.exists() and is_loaded(root) and not force:
        return p

    if is_loaded(root):
        from refmatrix import daemon as _daemon   # lazy: daemon imports launchctl
        _wait_tick_done(root, _daemon.stop_grace_s())
        subprocess.run(_bootout_cmd(label), capture_output=True)
        wait = _lc.BOOTOUT_WAIT_S
        if not _wait_loaded(root, expected=False, timeout=wait):
            raise RuntimeError(
                f"launchctl bootout did not unload {label} within {wait:g}s; plist NOT "
                f"rewritten. Retry, or `launchctl bootout {_domain()}/{label}` by hand")

    p.write_bytes(render_plist(
        root, partition=partition,
        interval_seconds=interval_seconds,
        all_projects=all_projects, rmx=rmx,
    ))
    p.chmod(0o644)

    r = subprocess.run(_bootstrap_cmd(p), capture_output=True, text=True)
    if not _wait_loaded(root, expected=True, timeout=3.0):
        # Fall back to legacy `launchctl load`
        r2 = subprocess.run(
            ["launchctl", "load", str(p)], capture_output=True, text=True,
        )
        if not _wait_loaded(root, expected=True, timeout=3.0):
            err = (r.stderr or r.stdout or r2.stderr or r2.stdout or "").strip() or "(silent)"
            raise RuntimeError(
                f"failed to load session-indexer LaunchAgent: {err}"
            )
    return p


def installed_flags(root: Path) -> dict:
    """The install-time flags recovered from the installed plist —
    `interval_seconds` (StartInterval), `all_projects` (`--all-projects`),
    `partition` (RMX_PARTITION) — so a re-render keeps them. Raises
    FileNotFoundError when nothing is installed."""
    p = plist_path(root)
    if not p.exists():
        raise FileNotFoundError(f"not installed: {p}")
    data = plistlib.loads(p.read_bytes())
    env = data.get("EnvironmentVariables") or {}
    return {
        "interval_seconds": int(data.get("StartInterval") or DEFAULT_INTERVAL_SECONDS),
        "all_projects": "--all-projects" in (data.get("ProgramArguments") or []),
        "partition": env.get("RMX_PARTITION") or None,
    }


def check(root: Path, *, rmx: "str | None" = None) -> "tuple[bool, str]":
    """Installed session plist == its render from the installed flags, and
    loaded. The daemon `check`'s shape: identity objection first
    (`kind="identity"`), then a missing plist, the byte comparison (a drift
    reason names every differing key — a plist without ExitTimeOut reads
    `ExitTimeOut: installed None != rendered 45`), then an unloaded label.
    Nothing compared these before task 4.6: 0/6 installed session labels
    carried ExitTimeOut and no command could say so (r5 #s-3)."""
    rmx = rmx or _rmx_path()
    objection = _identity_objection(rmx)
    if objection is not None:
        return False, CheckReason(f"{objection}; the session plist is not rendered "
                                  f"against it — run with the deployed rmx", kind="identity")
    p = plist_path(root)
    try:
        flags = installed_flags(root)
    except FileNotFoundError as e:
        return False, CheckReason(f"{e} — `rmx session launchctl install`", kind="missing")
    installed = p.read_bytes()
    rendered = render_plist(root, rmx=rmx, **flags)
    if installed != rendered:
        why = plist_diff(plistlib.loads(installed), plistlib.loads(rendered))
        return False, CheckReason(f"{p} drifted from its render: "
                                  + "; ".join(why or ["bytes differ"]), kind="drift")
    if not is_loaded(root):
        return False, CheckReason(f"{p} is current but its label {label_for_root(root)} "
                                  f"is not loaded — `rmx session launchctl install`",
                                  kind="unloaded")
    return True, ""


def reinstall(root: Path, *, rmx: "str | None" = None) -> Path:
    """Re-render + reload an installed session plist with its own flags,
    then verify with `check`; raises when it does not converge. The daemon
    `reinstall`'s shape (task 4.6 S3.6)."""
    flags = installed_flags(root)
    p = install(root, force=True, rmx=rmx, **flags)
    if not is_loaded(root):
        p = install(root, rmx=rmx, **flags)
    ok, why = check(root, rmx=rmx)
    if not ok:
        raise RuntimeError(f"session-indexer reinstall did not converge: {why}")
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
