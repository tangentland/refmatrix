"""Cross-store discovery + per-store status/footprint.

There is no global registry of refmatrix stores — each `.refmatrix/` is
independent. This module reconstructs the machine-wide view from three sources
(launchd plists, a UI-written registry cache, and the cwd), and reports each
store's daemon liveness, supervision state, and disk footprint. Read-only:
nothing here mutates a catalog. Used by the hub + web UI.
"""
from __future__ import annotations

import json
import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any

from refmatrix import launchctl
from refmatrix.taxonomy import user_home


REGISTRY_FILE = "registry.json"


# ---- registry cache -------------------------------------------------------


def registry_path() -> Path:
    return user_home() / REGISTRY_FILE


def load_registry() -> list[str]:
    p = registry_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        roots = data.get("roots", data) if isinstance(data, dict) else data
        return [str(r) for r in roots] if isinstance(roots, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_registry(roots: list[str]) -> None:
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"roots": sorted(set(roots))}, indent=2))
    tmp.replace(p)


def register_root(root: Path) -> None:
    """Add a `.refmatrix` root to the registry cache (idempotent)."""
    key = str(Path(root).resolve())
    roots = load_registry()
    if key not in roots:
        roots.append(key)
        save_registry(roots)


def unregister_root(root: Path) -> None:
    key = str(Path(root).resolve())
    roots = [r for r in load_registry() if r != key]
    save_registry(roots)


# ---- discovery ------------------------------------------------------------


def _roots_from_launchd() -> list[Path]:
    out: list[Path] = []
    d = launchctl.LAUNCH_AGENTS_DIR
    if not d.is_dir():
        return out
    for plist in d.glob(f"{launchctl.LABEL_PREFIX}*.plist"):
        try:
            data = plistlib.loads(plist.read_bytes())
            r = (data.get("EnvironmentVariables") or {}).get("REFMATRIX_ROOT")
            if r:
                out.append(Path(r))
        except (OSError, plistlib.InvalidFileException):
            continue
    return out


def _cwd_root() -> Path | None:
    env = os.environ.get("REFMATRIX_ROOT")
    if env:
        return Path(env)
    cur = Path.cwd()
    for d in (cur, *cur.parents):
        if (d / ".refmatrix").is_dir():
            return d / ".refmatrix"
    return None


def discover_roots() -> list[Path]:
    """Union of launchd-supervised roots, the registry cache, and the cwd.
    Returns existing `.refmatrix` dirs, deduped + sorted."""
    seen: dict[str, Path] = {}
    candidates = list(_roots_from_launchd())
    candidates += [Path(r) for r in load_registry()]
    cwd = _cwd_root()
    if cwd is not None:
        candidates.append(cwd)
    for c in candidates:
        try:
            rc = c.resolve()
        except OSError:
            rc = c
        if rc.is_dir():
            seen[str(rc)] = rc
    return [seen[k] for k in sorted(seen)]


# ---- per-store status -----------------------------------------------------


def _rss_mb(pid: int) -> float | None:
    """Resident set size of a pid in MB via `ps` (no psutil dependency)."""
    try:
        r = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True, timeout=2,
        )
        kb = r.stdout.strip()
        return round(int(kb) / 1024, 1) if kb else None
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def _read_pid(root: Path) -> int | None:
    p = root / "rmxd.pid"
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


def daemon_status(root: Path) -> dict:
    from refmatrix import daemon as daemon_mod
    up = False
    try:
        up = bool(daemon_mod.ping(root))
    except Exception:
        up = False
    pid = _read_pid(root)
    return {
        "up": up,
        "pid": pid,
        "rss_mb": _rss_mb(pid) if (up and pid) else None,
    }


def _dir_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for fn in filenames:
            try:
                total += (Path(dirpath) / fn).stat().st_size
            except OSError:
                pass
    return total


def footprint(root: Path) -> dict:
    """Disk footprint of a store, broken out by tier. Bytes."""
    root = Path(root)
    catalog = sum(
        _dir_bytes(p) for p in root.glob("catalog*.duckdb")
    )
    vectors = _dir_bytes(root / "vectors")
    logs = sum(_dir_bytes(p) for p in root.glob("*.log"))
    total = _dir_bytes(root)
    return {
        "catalog_bytes": catalog,
        "vectors_bytes": vectors,
        "logs_bytes": logs,
        "total_bytes": total,
    }


def store_name(root: Path) -> str:
    from refmatrix.store import default_partition_name
    try:
        return default_partition_name(root)
    except Exception:
        r = Path(root).resolve()
        return r.parent.name if r.name == ".refmatrix" else r.name


def launchd_state(root: Path) -> dict:
    try:
        return {
            "installed": launchctl.is_installed(root),
            "loaded": launchctl.is_loaded(root),
            "label": launchctl.label_for_root(root),
        }
    except Exception:
        return {"installed": False, "loaded": False, "label": None}


def project_status(root: Path, *, with_footprint: bool = True) -> dict:
    """Full status card for one store: identity, daemon, supervision, disk."""
    root = Path(root)
    status: dict[str, Any] = {
        "root": str(root),
        "name": store_name(root),
        "daemon": daemon_status(root),
        "launchd": launchd_state(root),
    }
    if with_footprint:
        status["footprint"] = footprint(root)
    return status


def all_projects(*, with_footprint: bool = True) -> list[dict]:
    return [
        project_status(r, with_footprint=with_footprint)
        for r in discover_roots()
    ]
