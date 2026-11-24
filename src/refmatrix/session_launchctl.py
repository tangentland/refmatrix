"""LaunchAgent for the session-index backfill ticker (Phase D).

One plist per refmatrix root, separate from `rmx daemon`'s LaunchAgent.
Periodically runs `rmx session ingest` to ingest any new Claude Code
session JSONLs into the `sessions-<project>` partition. Eventual
consistency, no hook dependency.

Shape differs from `launchctl.py`:
- Not a daemon: runs once per calendar tick (`StartCalendarInterval`), exits.
- No KeepAlive (would re-spawn the one-shot in a tight loop).
- No --watch flag — it's a periodic ingest, not a file watcher.

Same lifecycle as the daemon plist since task 4.6 (ch-bsd plan-4 r5 #s-3,
2026-10-19): the binary comes from `launchctl._rmx_path()` and is refused when
it is not verified (`_refuse_dev_tree`, unless `allow_dev`); a forced install
waits for an in-flight tick instead of booting it out under the old plist's
5 s ExitTimeOut; `check` / `reinstall` / `installed_flags` mirror the daemon's
so `rmx hub relaunch-fleet` can re-render drifted session plists on deploy.

Staggered since L206 (2026-11-24): with `StartInterval` 600 every store's
indexer ran on its own clock, and under load seven `rmx session ingest` runs
overlapped and helped push the machine to load average ~200 (bug-309 note,
bug-310). Each store now fires on its own minutes inside the interval
(`_choose_offset`), and `rmx session ingest` runs one at a time across the
user (`session_ingest.indexer_lock`).
"""
from __future__ import annotations

import hashlib
import plistlib
import re
import subprocess
import sys
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
# The calendar steps that divide the hour: launchd's `StartCalendarInterval`
# repeats on the clock hour, so only these give an even cadence (L206).
_HOUR_DIVISORS = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60)


def label_for_root(root: Path) -> str:
    """`com.refmatrix.session-indexer.<slug>-<hash12>` — same shape as the
    daemon label but with a distinct prefix so the two coexist."""
    return f"{LABEL_PREFIX}.{_slug_for_root(root)}-{_short_hash(root)}"


def plist_path(root: Path) -> Path:
    return LAUNCH_AGENTS_DIR / f"{label_for_root(root)}.plist"


def calendar_step_minutes(interval_seconds: int) -> int:
    """The calendar step, in minutes, that stands for `interval_seconds` (L206, 2026-11-24).

    600 s is a 10-minute step. `StartCalendarInterval` fires on clock minutes and
    repeats every hour, so a step that does not divide 60 would leave a short gap
    across the hour (7 min: ...:49, :56, then :00 four minutes later). The step
    rounds DOWN to the nearest divisor of 60 (7 -> 6, 45 -> 30): the cadence stays
    even and a store never fires less often than asked. Under a minute, or over an
    hour, has no per-hour minute list, so it is refused (ValueError) rather than
    silently clamped."""
    seconds = int(interval_seconds)
    if seconds < 60 or seconds > 3600:
        raise ValueError(
            f"session-indexer interval {seconds}s cannot be a calendar schedule: it must be "
            f"60..3600 s (the indexer fires on clock minutes, every hour)")
    minutes = seconds // 60
    return max(d for d in _HOUR_DIVISORS if d <= minutes)


def _calendar_minutes(offset: int, step: int) -> "list[int]":
    return list(range(offset, 60, step))


def _preferred_offset(label: str, step: int) -> int:
    """The store's own slot in the step, from its label: sha256, never `hash()`,
    which is salted per process and would move the store on every install."""
    return int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big") % step


def _sibling_minutes(root: Path) -> "set[int]":
    """The clock minutes the OTHER installed session-indexer plists fire on. A
    pre-L206 `StartInterval` plist claims none (it has no fixed minute). An
    unreadable plist is skipped and named on stderr: launchd cannot load it
    either, so it fires on no minute."""
    taken: set = set()
    if not LAUNCH_AGENTS_DIR.is_dir():
        return taken
    mine = plist_path(root).name
    skipped = 0
    for p in sorted(LAUNCH_AGENTS_DIR.glob(f"{LABEL_PREFIX}.*.plist")):
        if p.name == mine:
            continue
        try:
            entries = plistlib.loads(p.read_bytes()).get("StartCalendarInterval") or []
        except (OSError, ValueError, plistlib.InvalidFileException) as e:
            skipped += 1
            print(f"session-indexer stagger: skipped unreadable plist {p}: {e}",
                  file=sys.stderr)
            continue
        for e in entries if isinstance(entries, list) else [entries]:
            if isinstance(e, dict) and isinstance(e.get("Minute"), int):
                taken.add(e["Minute"])
    if skipped:
        print(f"session-indexer stagger: {skipped} unreadable session plist(s) skipped",
              file=sys.stderr)
    return taken


def _choose_offset(root: Path, step: int) -> int:
    """This store's minute offset inside the step (L206, 2026-11-24).

    A hash of the label picks the preferred slot, and a slot whose minutes another
    installed session plist already fires on is passed over, probing forward. Why
    not a slot from the hub registry order: that order changes when a store is
    added or pruned, which would move every later store and drift the whole fleet
    on each change, and it would make the render depend on hub state. The hash is
    stable per store; the probe only moves a store off a collision, and once
    installed the offset is read back from the plist (`installed_flags`) and kept,
    so it does not move when other stores come and go. With more stores than
    slots (over 10 at 600 s) sharing is unavoidable: the slot with the fewest
    shared minutes is taken."""
    taken = _sibling_minutes(root)
    start = _preferred_offset(label_for_root(root), step)
    best: "tuple[int, int] | None" = None
    for i in range(step):
        offset = (start + i) % step
        clash = len(taken.intersection(_calendar_minutes(offset, step)))
        if clash == 0:
            return offset
        if best is None or clash < best[0]:
            best = (clash, offset)
    assert best is not None
    return best[1]


def render_plist(root: Path, *, partition: str | None = None,
                 interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
                 all_projects: bool = False, rmx: "str | None" = None,
                 offset_minutes: "int | None" = None) -> bytes:
    """Render the session-indexer plist for `root` as XML bytes.

    `all_projects=True` walks every project under ~/.claude/projects/ on
    each tick. Default (False) scopes to the project matching the active
    root's cwd — matches `rmx session ingest`'s default behaviour. `rmx` is
    the caller's binary, else `_rmx_path()`; like the daemon render this
    stays pure — the identity guard lives in `install` (task 4.6 S3).

    The schedule is `StartCalendarInterval` minutes `offset, offset+step, …`
    (L206): `offset_minutes` is the installed one when re-rendering, else
    `_choose_offset` picks it against the other installed session plists."""
    root = Path(root).resolve()
    label = label_for_root(root)
    rmx = rmx or _rmx_path()
    step = calendar_step_minutes(interval_seconds)
    if offset_minutes is None:
        offset_minutes = _choose_offset(root, step)
    elif not 0 <= int(offset_minutes) < step:
        raise ValueError(f"session-indexer offset {offset_minutes} is outside the "
                         f"{step}-minute step")

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
        # Not `StartInterval` (L206): each store fires on its own clock minutes.
        # A tick missed in sleep fires once on wake, for every store at once;
        # `session_ingest.indexer_lock` is what serialises that burst.
        "StartCalendarInterval": [{"Minute": m}
                                  for m in _calendar_minutes(int(offset_minutes), step)],
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
            rmx: "str | None" = None, allow_dev: bool = False,
            offset_minutes: "int | None" = None) -> Path:
    """Write the plist + bootstrap it. Returns the plist path.

    The identity guard runs FIRST — before any bootout, write or bootstrap —
    exactly as the daemon and hub installs: this one had none, so a dev or
    unreadable binary was baked into the session plist unchallenged (ch-bsd
    plan-4 r5 #s-3; task 4.6, 2026-10-19). A forced reinstall on a loaded
    label waits for the in-flight tick (up to `daemon.stop_grace_s()`)
    before the bootout, then waits for the domain to release the label
    (bug-013's shape).

    The interval is checked before anything is touched (a refused interval
    after the bootout would leave the label unloaded), and a store already
    installed on a calendar schedule with the same step keeps its offset
    (L206: the same store fires on the same minutes on every install)."""
    _require_darwin()
    step = calendar_step_minutes(interval_seconds)
    rmx = rmx or _rmx_path()
    if not allow_dev:
        _refuse_dev_tree(rmx)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = plist_path(root)
    label = label_for_root(root)
    if offset_minutes is None and p.exists():
        try:
            have = installed_flags(root)
        except ValueError as e:
            print(f"session-indexer: installed {p} unreadable ({e}); choosing a new offset",
                  file=sys.stderr)
            have = {}
        if (have.get("offset_minutes") is not None
                and have.get("interval_seconds") == step * 60):
            offset_minutes = have["offset_minutes"]

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
        offset_minutes=offset_minutes,
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
    `interval_seconds` and `offset_minutes` (the schedule), `all_projects`
    (`--all-projects`), `partition` (RMX_PARTITION) — so a re-render keeps
    them. Raises FileNotFoundError when nothing is installed.

    Both schedule forms read back (L206, 2026-11-24): a calendar plist gives
    its step (the gap between its minutes; 60 for one minute) and its first
    minute as the offset; a pre-L206 `StartInterval` plist gives that interval
    and `offset_minutes=None`, so its re-render picks an offset and `check`
    reports it as drift. A calendar list that is not one even step raises
    ValueError naming the plist."""
    p = plist_path(root)
    if not p.exists():
        raise FileNotFoundError(f"not installed: {p}")
    data = plistlib.loads(p.read_bytes())
    env = data.get("EnvironmentVariables") or {}
    cal = data.get("StartCalendarInterval")
    if cal is not None:
        entries = cal if isinstance(cal, list) else [cal]
        try:
            mins = sorted(int(e["Minute"]) for e in entries)
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"{p}: StartCalendarInterval {cal!r} is not a minute list") from e
        step = mins[1] - mins[0] if len(mins) > 1 else 60
        if not mins or mins != _calendar_minutes(mins[0], step) or mins[0] >= step:
            raise ValueError(f"{p}: StartCalendarInterval minutes {mins} are not one "
                             f"even step through the hour")
        interval, offset = step * 60, mins[0]
    else:
        interval = int(data.get("StartInterval") or DEFAULT_INTERVAL_SECONDS)
        offset = None
    return {
        "interval_seconds": interval,
        "offset_minutes": offset,
        "all_projects": "--all-projects" in (data.get("ProgramArguments") or []),
        "partition": env.get("RMX_PARTITION") or None,
    }


def check(root: Path, *, rmx: "str | None" = None) -> "tuple[bool, str]":
    """Installed session plist == its render from the installed flags, and
    loaded. The daemon `check`'s shape: identity objection first
    (`kind="identity"`), then a missing plist, the byte comparison (a drift
    reason names every differing key — a plist without ExitTimeOut reads
    `ExitTimeOut: installed None != rendered 45`, a pre-L206 one reads
    `StartCalendarInterval: installed None != …; StartInterval: installed 600
    != rendered None`), then an unloaded label.
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
    except ValueError as e:
        return False, CheckReason(f"{e}; re-render with `rmx session launchctl install "
                                  f"--force`", kind="drift")
    installed = p.read_bytes()
    try:
        rendered = render_plist(root, rmx=rmx, **flags)
    except ValueError as e:
        # A pre-L206 `StartInterval` no calendar can express (L206).
        return False, CheckReason(f"{p} cannot be re-rendered: {e}", kind="drift")
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
