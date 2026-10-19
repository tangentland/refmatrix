"""`rmx upgrade` — self-update the install, or promote a dev tree into it.

Two modes, one command:

* **git self-update** (default): fast-forward the install's git tree from
  `origin/<branch>` (or `--ref`), `pip install -e .` into its venv, restart the
  daemon, and verify the version moved. Works for any install / public users.
* **dev->deploy promote** (`--from-dev <path>`): fast-forward the install tree
  from a local dev tree's branch instead of GitHub — the day-to-day deploy
  ritual for the two-tree (dev `~/claude_tools/refmatrix` -> deploy `~/refmatrix`)
  setup, with no GitHub round-trip.

`--check` is a read-only dry-run: it fetches and reports current-vs-available
version + HEAD, mutating nothing. Both real mutations (pip, daemon restart) are
fast-forward-only and injectable, so the merge can never clobber local work and
the side effects are unit-testable.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


class UpgradeError(RuntimeError):
    """Any step of the upgrade failed; message is user-facing."""


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    if r.returncode != 0:
        detail = (r.stderr.strip() or r.stdout.strip() or "unknown error")
        raise UpgradeError(f"git {' '.join(args)}: {detail}")
    return r.stdout.strip()


def _read_version(text: str) -> "str | None":
    m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return m.group(1) if m else None


def package_root(start: "Path | None" = None) -> Path:
    """The git repo root of the INSTALLED refmatrix (the editable source tree).

    `rmx` runs whatever tree it was `pip install -e`'d from, so this is what
    `upgrade` updates — the deploy tree for the deploy binary, the dev tree for
    a dev binary."""
    if start is None:
        import refmatrix
        start = Path(refmatrix.__file__).resolve()
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists():
            return p
    raise UpgradeError("could not locate the install's pyproject.toml")


def _tree_root(start: "Path | None") -> "Path | None":
    """Nearest ancestor of `start` carrying pyproject.toml, else None."""
    if start is None:
        return None
    start = Path(start).resolve()
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists():
            return p
    return None


def venv_prefix(root: Path) -> "Path | None":
    """`<root>/.venv` when the tree carries its own venv, else None."""
    cand = Path(root) / ".venv"
    return cand if (cand / "bin").is_dir() or (cand / "lib").is_dir() else None


def editable_target(prefix: Path, *, strict: bool = False) -> "Path | None":
    """Where the interpreter at `prefix` imports refmatrix from, per pip's
    path-style editable marker (`__editable__.refmatrix-<v>.pth` = one line,
    the `src/` dir). None when no editable marker exists (wheel install).
    A marker that exists but yields no path (finder-style `import …` only)
    is None in reporting mode and an UpgradeError under `strict` — a verify
    step must not pass on "could not read" (ch-bsd bsd-plan1 #s-8)."""
    prefix = Path(prefix)
    seen_marker = None
    for sp in sorted(prefix.glob("lib/python*/site-packages")):
        for pth in sorted(sp.glob("__editable__.refmatrix*.pth")):
            seen_marker = pth
            for line in pth.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("import "):
                    return Path(line).resolve()
    if seen_marker is not None and strict:
        raise UpgradeError(
            f"editable marker present but target unreadable (finder-style "
            f"install?): {seen_marker} — reinstall with a path-style editable "
            f"or verify by hand")
    return None


def deploy_root() -> "Path | None":
    """The DEPLOY tree: `$RMX_DEPLOY_ROOT` (user-expanded, resolved), else
    `~/refmatrix`. Returned only when it holds a `pyproject.toml`; None when
    no deploy tree exists (ch-bsd plan-4 r5 #s-2; task 4.6 S2, 2026-10-19).

    The deploy tree is the one tree whose code may be rendered into a plist.
    `~/refmatrix` is the two-tree workstation's (dev `~/claude_tools/
    refmatrix` -> deploy `~/refmatrix`); a contributor running from another
    checkout names it with `RMX_DEPLOY_ROOT`."""
    env = os.environ.get("RMX_DEPLOY_ROOT")
    cand = Path(env).expanduser() if env else Path.home() / "refmatrix"
    try:
        cand = cand.resolve()
    except OSError:
        return None
    return cand if (cand / "pyproject.toml").is_file() else None


def runtime_identity(*, prefix: "Path | None" = None,
                     import_file: "Path | None" = None) -> dict:
    """Which tree does this interpreter actually run?

    2026-09-14: `~/refmatrix/.venv`'s editable marker pointed at the DEV
    checkout, so the deploy binary, every daemon and the hub executed
    uncommitted code while `git -C ~/refmatrix log` looked deployed. Nothing
    reported it. This is the one function that can: it derives the answer
    from the interpreter PREFIX (whose tree the venv belongs to) and the
    IMPORT PATH (whose tree the code came from), never from a package
    attribute alone.

    Returns `{version, import_path, code_root, venv_tree, editable_target,
    deploy_root, dev_tree, dev_reason}`. `dev_tree` is True when either rule
    holds:

    (a) `venv-mismatch` — the venv belongs to one tree (pyproject above the
        prefix) and the code comes from ANOTHER (the 2026-09-14 state);
    (b) the code comes from a SOURCE TREE (the import path is not under the
        prefix: an editable install or a PYTHONPATH checkout) and that tree
        is not the deploy tree — `no-deploy-tree` when `deploy_root()` is
        None (fail closed), `not-deploy-tree` when it is another tree.

    Rule (a) alone read the dev tree's OWN `.venv-eval` (editable -> its own
    `src/`) as "not a dev tree", so `.venv-eval/bin/rmx hub launchctl
    install` passed every guard and rendered uncommitted code into a plist
    (ch-bsd plan-4 r5 #s-2; task 4.6, 2026-10-19). A wheel install (import
    path under the prefix's site-packages, pipx) has no tree to confuse and
    is never a dev tree by rule (b). A system interpreter importing a wheel
    yields `dev_tree=False` rather than a false alarm. `prefix` /
    `import_file` are injectable so the check is testable on fake trees
    without patching the function itself."""
    import refmatrix
    imp = Path(import_file or refmatrix.__file__).resolve()
    code_root = _tree_root(imp)
    pfx = Path(prefix or sys.prefix).resolve()
    venv_tree = pfx.parent if (pfx.parent / "pyproject.toml").exists() else None
    target = editable_target(pfx)
    droot = deploy_root()
    reason: "str | None" = None
    if (venv_tree is not None and code_root is not None
            and code_root.resolve() != venv_tree.resolve()):
        reason = "venv-mismatch"
    elif code_root is not None and pfx not in imp.parents:
        # a source tree: is it THE deploy tree?
        if droot is None:
            reason = "no-deploy-tree"
        elif code_root.resolve() != droot:
            reason = "not-deploy-tree"
    return {
        "version": getattr(refmatrix, "__version__", None),
        "import_path": imp,
        "code_root": code_root,
        "venv_tree": venv_tree,
        "editable_target": target,
        "deploy_root": droot,
        "dev_tree": reason is not None,
        "dev_reason": reason,
    }


def dev_tree_message(ident: dict) -> str:
    """Why `ident` is a dev tree, in words an operator can act on. Reads the
    task-4.6 keys with `.get`: an older identity dict (an older daemon's
    ping, a test double) lacks them and is the venv-mismatch case."""
    reason = ident.get("dev_reason") or "venv-mismatch"
    if reason == "venv-mismatch":
        vt = ident.get("venv_tree")
        fix = (f"({Path(vt) / '.venv' / 'bin' / 'python'} -m pip install -e {vt})"
               if vt is not None else "")
        return (f"code {ident.get('import_path')} but the venv belongs to {vt} — "
                f"reinstall the deploy venv from its own tree {fix}").rstrip()
    droot = ident.get("deploy_root")
    if reason == "no-deploy-tree":
        where = (f"no deploy tree exists (RMX_DEPLOY_ROOT is unset or names no "
                 f"pyproject.toml, and ~/refmatrix is not a refmatrix tree)")
    else:
        where = f"the deploy tree is {droot}"
    return (f"code {ident.get('import_path')} comes from the source tree "
            f"{ident.get('code_root')}, and {where} (dev_reason={reason}, "
            f"deploy_root={droot}). Run the deployed rmx, or set RMX_DEPLOY_ROOT "
            f"to this tree if it IS your deploy tree")


def verify_editable(root: Path) -> "Path | None":
    """After `pip install -e <root>` into `<root>/.venv`, prove the venv's
    editable marker points INTO `root` (its `src/`). Raises UpgradeError with
    the actual target otherwise — the exact mistake of 2026-09-14 (an
    absolute `-e <other tree>` into the deploy venv). Returns the target, or
    None when the venv carries no editable marker (nothing to verify)."""
    root = Path(root).resolve()
    pfx = venv_prefix(root)
    if pfx is None:
        return None
    target = editable_target(pfx, strict=True)
    if target is None:
        return None
    if target != root and root not in target.parents:
        raise UpgradeError(
            f"editable target is {target}, expected a path under {root} — "
            f"the venv would run another tree; fix: "
            f"{pfx / 'bin' / 'python'} -m pip install -e {root}")
    return target


def venv_python(root: Path) -> Path:
    """The interpreter that should `pip install` — the tree's own `.venv` if it
    has one, else the running interpreter."""
    cand = root / ".venv" / "bin" / "python"
    return cand if cand.exists() else Path(sys.executable)


@dataclass
class UpgradeResult:
    root: Path
    source: str                       # "origin/<ref>" or "dev:<path>"
    old_head: str
    new_head: str
    old_version: "str | None"
    new_version: "str | None"
    checked: bool = False             # True = dry-run, nothing mutated
    installed: bool = False
    restarted: bool = False
    messages: list = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.old_head != self.new_head


def _fetch_target(root: Path, *, from_dev: "Path | None", ref: "str | None") -> str:
    """Fetch the upgrade source into FETCH_HEAD and return its sha."""
    if from_dev is not None:
        dev = Path(from_dev).resolve()
        if not (dev / "pyproject.toml").exists():
            raise UpgradeError(f"--from-dev is not a refmatrix tree: {dev}")
        _git(root, "fetch", str(dev), ref or "master")
    else:
        branch = ref or _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        _git(root, "fetch", "origin", branch)
    return _git(root, "rev-parse", "FETCH_HEAD")


def _target_version(root: Path, sha: str) -> "str | None":
    try:
        return _read_version(_git(root, "show", f"{sha}:pyproject.toml"))
    except UpgradeError:
        return None


def upgrade(
    *,
    root: "Path | str | None" = None,
    from_dev: "Path | str | None" = None,
    ref: "str | None" = None,
    check: bool = False,
    restart: bool = True,
    install_fn=None,
    restart_fn=None,
    store_root: "Path | str | None" = None,
    log=print,
) -> UpgradeResult:
    """Run (or, with `check`, preview) an upgrade. See module docstring.

    `install_fn(root, log=...)` and `restart_fn(store_root, log=...) -> bool`
    are injectable for tests; the real ones are `_default_install` /
    `_default_restart`. `store_root` is the STORE whose daemon is restarted —
    not `root`, the git tree being upgraded: `restart_fn(~/refmatrix)` named
    a label that is never loaded and a pid file that never exists, so the
    live `rmx upgrade` reported `restarted=True` having restarted nothing
    (task 4.6 #b1-root, 2026-10-19). None restarts nothing and says so.
    """
    # FIRST, on every path (--check, up to date, changed head): is this
    # interpreter running a dev tree? In the 2026-09-14 state the deploy tree
    # was at master's sha and the imported code came from elsewhere; the
    # previous guard looked at the imported tree's venv and passed
    # (ch-bsd bsd-plan1 #b-2). runtime_identity() is the only check that
    # sees prefix vs import path.
    ident = runtime_identity()
    if ident.get("dev_tree"):
        raise UpgradeError(
            f"this interpreter runs a DEV TREE: {dev_tree_message(ident)} — "
            f"refusing to upgrade from it")
    root = package_root() if root is None else Path(root)
    source = f"dev:{Path(from_dev).resolve()}" if from_dev else f"origin/{ref or 'HEAD'}"
    old_head = _git(root, "rev-parse", "HEAD")
    old_version = _read_version((root / "pyproject.toml").read_text())

    target_head = _fetch_target(root, from_dev=Path(from_dev) if from_dev else None, ref=ref)
    target_version = _target_version(root, target_head)

    if check:
        res = UpgradeResult(root, source, old_head, target_head, old_version,
                            target_version, checked=True)
        if not res.changed:
            log(f"up to date — {old_version} @ {old_head[:8]} ({source})")
        else:
            log(f"available — {old_version} @ {old_head[:8]} -> "
                f"{target_version} @ {target_head[:8]} ({source})")
        return res

    if target_head == old_head:
        # Up to date is not verified: the incident tree WAS at master's sha
        # with a wrong .pth. Check the venv on this path too.
        target = verify_editable(root)
        if target is not None:
            log(f"editable target verified: {target}")
        log(f"already up to date — {old_version} @ {old_head[:8]}")
        return UpgradeResult(root, source, old_head, old_head, old_version,
                             old_version)

    # Fast-forward only: refuse anything that would rewrite local history.
    _git(root, "merge", "--ff-only", target_head)
    new_head = _git(root, "rev-parse", "HEAD")
    new_version = _read_version((root / "pyproject.toml").read_text())
    res = UpgradeResult(root, source, old_head, new_head, old_version, new_version)
    res.messages.append(f"merged {source}: {old_head[:8]} -> {new_head[:8]}")
    log(res.messages[-1])

    (install_fn or _default_install)(root, log=log)
    # The install is injectable; the verification is not. Whatever wrote the
    # venv, it must import THIS tree afterwards.
    target = verify_editable(root)
    if target is not None:
        log(f"editable target verified: {target}")
    res.installed = True

    if restart:
        if store_root is None:
            log("no store root given — no daemon restarted; restart it manually: "
                "`rmx daemon restart --relaunch` (or `rmx hub relaunch-fleet` for "
                "every supervised store)")
        else:
            res.restarted = bool((restart_fn or _default_restart)(Path(store_root), log=log))

    log(f"upgraded {old_version} -> {new_version}"
        + (" (restart the daemon manually if needed)" if not res.restarted else ""))
    return res


def _default_install(root: Path, *, log=print) -> None:
    py = venv_python(root)
    log(f"pip install -e {root}  (via {py})")
    r = subprocess.run(
        [str(py), "-m", "pip", "install", "-e", str(root)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise UpgradeError(f"pip install failed: {(r.stderr or r.stdout)[-600:].strip()}")


def _default_restart(root: Path, *, log=print) -> bool:
    """Restart the daemon of the store at `root` so it runs the new code.
    Returns True only when the predecessor is gone.

    Under launchd: `launchctl.supervised_restart` — the ONE launchd restart
    sequence `rmx daemon restart` uses (watchdog pause, graceful stop with
    the grace, kick, resume). Standalone: `stop_daemon` with the grace; the
    next read spawns the upgraded daemon.

    This used to discard `stop_daemon`'s False, print "daemon stopped" and
    return True beside a live predecessor; its launchd branch was a bare
    `kickstart -k`; and two `except Exception: pass` let a failed probe or
    kick fall through to stopping a SUPERVISED daemon, which exits 0, is not
    respawned by KeepAlive, and leaves the next read to spawn an
    unsupervised daemon beside the label — bug-013 (ch-bsd plan-4 r5 #b-1;
    task 4.6, 2026-10-19). Every failure is now said and returns False."""
    from refmatrix import daemon as daemon_mod
    from refmatrix import launchctl
    manual = "restart it manually: `rmx daemon restart --relaunch`"
    if sys.platform == "darwin":
        try:
            st = launchctl.status(root) or {}
        except Exception as e:  # noqa: BLE001 — reported; never guessed unsupervised
            log(f"could not probe launchd for {root} ({type(e).__name__}: {e}); "
                f"not stopping a daemon that may be supervised — {manual}")
            return False
        if st.get("loaded"):
            try:
                label, stopped = launchctl.supervised_restart(root, log=log)
            except Exception as e:  # noqa: BLE001 — reported; never a standalone stop
                log(f"launchd restart of {root} failed ({type(e).__name__}: {e}); "
                    f"the supervised daemon was NOT stopped standalone — {manual}")
                return False
            log(f"daemon restarted (launchd kickstart{'' if stopped else ' -k'} "
                f"label={label})")
            return True
    # No launchd label for this store (or no launchd on this platform).
    grace = daemon_mod.stop_grace_s()
    rep: dict = {}
    try:
        ok = daemon_mod.stop_daemon(root, timeout=grace, report=rep)
    except Exception as e:  # noqa: BLE001 — reported, then False
        log(f"daemon stop failed ({type(e).__name__}: {e}) — {manual}")
        return False
    if not ok:
        pid = rep.get("pid") or daemon_mod.read_pid(root)
        log(f"daemon pid={pid} still alive after the {grace:g}s grace — not "
            f"restarted; {manual}")
        return False
    log("daemon stopped (next read spawns the upgraded daemon)")
    return True
