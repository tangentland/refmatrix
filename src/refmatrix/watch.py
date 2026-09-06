"""
Filesystem watcher daemon. Calls `sync_files` on debounced batches of changes.

This is the editor-driven freshness path. For Claude-driven flows, prefer the
PostToolUse hook (zero processes). For git-driven flows, prefer post-commit.
The watcher only earns its keep when files change outside of those routes —
e.g. a build step or another tool rewriting code.

Usage:
    rmx watch [--semantic] [--debounce 500] [path]

Stops on Ctrl-C / SIGTERM with a final flush.
"""
from __future__ import annotations

import signal
import threading
import time
from pathlib import Path
from typing import Callable

from refmatrix.ingest import CODE_EXTS, DOC_EXTS, load_ignore_spec
from refmatrix.store import Store
from refmatrix.sync import sync_files

IGNORE_DIRS = {
    "venv", "node_modules",
    "__pycache__", "dist", "build",
}
SUPPORTED_EXTS = CODE_EXTS | DOC_EXTS


def is_relevant(p: Path, root: Path | None = None) -> bool:
    """True if a path is worth syncing. Excludes hidden directories
    (any segment starting with `.` — covers .git, .venv, .tldr,
    .refmatrix, .wolf, .claude, .cursor, .idea, .mypy_cache, .pytest_cache,
    .ruff_cache, .tox, .nox, ...), the non-dot tooling dirs in IGNORE_DIRS,
    and — when `root` is given — anything matched by that repo's
    .refmatrix_ignore (e.g. a workflow/ dir of operational content)."""
    if p.suffix.lower() not in SUPPORTED_EXTS:
        return False
    parts = p.parts
    if any(part in IGNORE_DIRS for part in parts):
        return False
    if any(part.startswith(".") and part != "." for part in parts):
        return False
    if root is not None:
        spec = load_ignore_spec(root)
        if spec is not None:
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = Path(p.name)
            if spec.match(rel):
                return False
    return True


# Filename + path-segment patterns that signal "this change is curator-
# relevant" — i.e. it touches the documentation graph in a way the
# gmd-curator subagent should review (cross-link, surface drift,
# crystallize, contradict). Watcher routes matching paths to
# .refmatrix/curator.queue; a SessionStart hook surfaces the queue to
# Claude so the curator gets dispatched.
_CURATOR_FILENAME_PREFIXES = ("PLAN-", "SPEC-", "ISSUE-", "ROADMAP-",
                              "ADR-")
_CURATOR_PATH_SEGMENTS = {
    "plans", "plan", "specs", "spec", "issues", "issue", "roadmap",
    "adr", "decisions", "rfcs", "rfc",
}


def is_curator_relevant(p: Path) -> bool:
    """True if a change in this path should signal the gmd-curator.

    Matches: GMD docs (`.gmd` or `.md` under a `gmd:`-frontmatter path —
    cheaply approximated by extension here, content sniff happens at
    ingest time), plan/spec/issue/roadmap/ADR docs by filename prefix,
    and anything under a curator-relevant path segment.
    """
    name = p.name
    ext = p.suffix.lower()
    if ext == ".gmd":
        return True
    if ext == ".md":
        if any(name.startswith(pref) for pref in _CURATOR_FILENAME_PREFIXES):
            return True
        if any(seg in _CURATOR_PATH_SEGMENTS for seg in p.parts):
            return True
    return False


class Debouncer:
    """Coalesces fs events into batches; fires callback after a quiet period."""

    def __init__(self, delay_ms: int, callback: Callable[[list[str]], None]):
        self.delay = delay_ms / 1000.0
        self.callback = callback
        self._dirty: set[str] = set()
        self._lock = threading.Lock()
        self._deadline: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="rmx-debounce", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        with self._lock:
            paths = sorted(self._dirty)
            self._dirty.clear()
            self._deadline = None
        if paths:
            self._safe_fire(paths)

    def add(self, path: str) -> None:
        with self._lock:
            self._dirty.add(path)
            self._deadline = time.monotonic() + self.delay

    def _loop(self) -> None:
        # Tick faster than the smallest reasonable debounce window.
        tick = max(0.02, self.delay / 4)
        while not self._stop.is_set():
            time.sleep(tick)
            paths: list[str] = []
            with self._lock:
                if (self._deadline is not None
                        and time.monotonic() >= self._deadline
                        and self._dirty):
                    paths = sorted(self._dirty)
                    self._dirty.clear()
                    self._deadline = None
            if paths:
                self._safe_fire(paths)

    def _safe_fire(self, paths: list[str]) -> None:
        try:
            self.callback(paths)
        except Exception as e:
            print(f"[rmx watch] sync error: {e}")


def run_watcher(
    store: Store,
    project_root: Path,
    *,
    semantic: bool = False,
    debounce_ms: int = 500,
    on_batch: Callable[[list[str], dict], None] | None = None,
    stop_event: threading.Event | None = None,
    install_signal_handlers: bool = True,
) -> None:
    """Block until SIGINT/SIGTERM (or `stop_event` is set), syncing on changes."""
    try:
        from watchdog.events import FileSystemEventHandler  # pyright: ignore[reportMissingImports]
        from watchdog.observers import Observer  # pyright: ignore[reportMissingImports]
    except ImportError as e:
        raise RuntimeError(
            "watchdog not installed. `pip install 'refmatrix[watch]'` or `pip install watchdog`"
        ) from e

    project_root = project_root.resolve()

    def flush(paths: list[str]) -> None:
        report = sync_files(store, paths, project_root=project_root, semantic=semantic)
        if on_batch is not None:
            on_batch(paths, report)

    debouncer = Debouncer(debounce_ms, flush)

    class _Handler(FileSystemEventHandler):
        def _maybe(self, raw_path: str) -> None:
            p = Path(raw_path)
            if is_relevant(p, project_root):
                debouncer.add(str(p))

        def on_created(self, event) -> None:
            if not event.is_directory:
                self._maybe(event.src_path)

        def on_modified(self, event) -> None:
            if not event.is_directory:
                self._maybe(event.src_path)

        def on_deleted(self, event) -> None:
            if not event.is_directory:
                self._maybe(event.src_path)

        def on_moved(self, event) -> None:
            if event.is_directory:
                return
            self._maybe(event.src_path)
            self._maybe(event.dest_path)

    observer = Observer()
    observer.schedule(_Handler(), str(project_root), recursive=True)
    observer.start()
    debouncer.start()

    local_stop = stop_event or threading.Event()

    if install_signal_handlers:
        # signal handlers must be installed from the main thread
        try:
            signal.signal(signal.SIGINT, lambda *_: local_stop.set())
            signal.signal(signal.SIGTERM, lambda *_: local_stop.set())
        except ValueError:
            # not in main thread — caller will manage stop_event
            pass

    try:
        while not local_stop.is_set():
            local_stop.wait(1.0)
    finally:
        debouncer.stop()
        observer.stop()
        observer.join(timeout=2.0)
