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
    dev_tree}`. `dev_tree` is True only when the venv belongs to a tree
    (pyproject above `sys.prefix`) and the imported code comes from a
    DIFFERENT tree; a system interpreter yields `venv_tree=None,
    dev_tree=False` rather than a false alarm. `prefix` / `import_file` are
    injectable so the check is testable on fake trees without patching the
    function itself."""
    import refmatrix
    imp = Path(import_file or refmatrix.__file__).resolve()
    code_root = _tree_root(imp)
    pfx = Path(prefix or sys.prefix).resolve()
    venv_tree = pfx.parent if (pfx.parent / "pyproject.toml").exists() else None
    target = editable_target(pfx)
    dev_tree = bool(venv_tree is not None and code_root is not None
                    and code_root.resolve() != venv_tree.resolve())
    return {
        "version": getattr(refmatrix, "__version__", None),
        "import_path": imp,
        "code_root": code_root,
        "venv_tree": venv_tree,
        "editable_target": target,
        "dev_tree": dev_tree,
    }


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
    log=print,
) -> UpgradeResult:
    """Run (or, with `check`, preview) an upgrade. See module docstring.

    `install_fn(root, log=...)` and `restart_fn(root, log=...) -> bool` are
    injectable for tests; the real ones are `_default_install` / `_default_restart`.
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
            f"this interpreter runs a DEV TREE: code {ident['import_path']} "
            f"but the venv belongs to {ident['venv_tree']} — reinstall the "
            f"deploy venv from its own tree "
            f"({ident['venv_tree'] / '.venv' / 'bin' / 'python'} -m pip "
            f"install -e {ident['venv_tree']}) before upgrading")
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
        res.restarted = bool((restart_fn or _default_restart)(root, log=log))

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
    """Restart the daemon so it runs the new code. Prefer launchd kickstart when
    supervised; else best-effort stop (next read auto-spawns a fresh daemon)."""
    try:
        from refmatrix import launchctl
        st = launchctl.status(root) or {}
        if st.get("supervised") or st.get("loaded"):
            launchctl.kickstart(root, restart=True)
            log("daemon kickstarted (launchd)")
            return True
    except Exception:
        pass
    try:
        from refmatrix import daemon as daemon_mod
        if hasattr(daemon_mod, "stop_daemon"):
            daemon_mod.stop_daemon(root)
            log("daemon stopped (next read spawns the upgraded daemon)")
            return True
    except Exception:
        pass
    log("could not auto-restart the daemon — restart it manually")
    return False
