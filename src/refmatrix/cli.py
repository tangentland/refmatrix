"""refmatrix CLI."""
from __future__ import annotations

import atexit
import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from refmatrix import __version__
from refmatrix.query import QueryEngine
from refmatrix.store import Store, default_partition_name
from refmatrix.telemetry import log_query

console = Console()


def _root() -> Path:
    env = os.environ.get("REFMATRIX_ROOT")
    if env:
        return Path(env)
    cur = Path.cwd().resolve()
    for p in [cur, *cur.parents]:
        if (p / ".refmatrix").is_dir():
            return p / ".refmatrix"
    return cur / ".refmatrix"


# Set by main()'s --partition flag, consumed by _store() and init. None means
# "use the resolution chain below". A module-level variable keeps subcommand
# signatures untouched; click's group callback always runs before any command.
_partition_override: str | None = None


def _resolve_partition() -> str:
    """Resolution order (overrides first, then the default):
       1. --partition / -p flag on the rmx group
       2. RMX_PARTITION env var
       3. .refmatrix/partition file walked up from cwd (one-line partition
          name — drop one inside a project's existing .refmatrix/ to bind
          that tree to a named partition in a shared store)
       4. The project-scoped default (`default_partition_name`): basename of
          the .refmatrix root's parent dir, e.g. `viascope` for
          /path/to/viascope/.refmatrix/. This is the SAME default Store()
          uses, so lib and CLI always agree on an unconfigured root.

    Steps 1-3 are overrides; step 4 is the default. Note: the .refmatrix/
    that holds the `partition` file does NOT have to be the active store
    root — REFMATRIX_ROOT can still point at a central shared store while a
    per-project .refmatrix/partition file selects which partition this
    project's CLI invocations write into.
    """
    if _partition_override:
        return _partition_override
    env = os.environ.get("RMX_PARTITION")
    if env:
        return env
    cur = Path.cwd().resolve()
    for p in [cur, *cur.parents]:
        marker = p / ".refmatrix" / "partition"
        if marker.is_file():
            try:
                name = marker.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            except (OSError, IndexError):
                continue
            if name:
                return name
    return default_partition_name(_root())


def _active_slot_path() -> Path | None:
    """Resolve `<root>/catalog.<active>.duckdb` per the `active` marker, or
    None if no rotation has bootstrapped. Reading the marker is cheap and
    avoids opening a stale legacy `catalog.duckdb`."""
    root = _root()
    marker = root / "active"
    if not marker.exists():
        return None
    try:
        slot = marker.read_text().strip()
    except OSError:
        return None
    if slot not in ("A", "B"):
        return None
    p = root / f"catalog.{slot}.duckdb"
    return p if p.exists() else None


def _store() -> Store:
    """Open the active rotation-slot catalog. The legacy `catalog.duckdb`
    is no longer touched by the daemon post-0.3.8: that file is FROZEN at
    bootstrap, and any code opening it from there sees stale data.

    Resolution:
      1. `<root>/catalog.<active>.duckdb` per the `active` marker — what
         the daemon writes to (or wrote to last). Source of truth.
      2. Legacy `<root>/catalog.duckdb` for ancient pre-rotation stores.

    With the daemon up, opening the active slot r/w from another process
    will fail (DuckDB exclusive lock). Callers that want a read-only view
    while the daemon is running should use `_reader_store()` or route
    through the daemon's RPC."""
    s = Store(_root(), partition=_resolve_partition())
    slot_path = _active_slot_path()
    if slot_path is not None:
        s.db_path = slot_path
    if not s.db_path.exists():
        raise click.ClickException(
            f"no refmatrix at {s.root}. Run `rmx init` first or set REFMATRIX_ROOT."
        )
    # Register a flush-and-close on normal interpreter exit. CLI commands
    # mutate the in-memory fragment cache and rely on close() to persist;
    # without this, every command would lose its writes.
    atexit.register(s.close)
    return s


def _replica_reader_path() -> Path:
    """Return the path to the current reader-slot catalog file.

    Resolution order:
      1. `<root>/read_only.duckdb` — daemon-maintained symlink at the
         current inactive (reader) slot. Cheapest + most explicit; the
         daemon updates it atomically on every rotation swap.
      2. `<root>/active` marker + `catalog.{inactive}.duckdb` —
         fallback for pre-symlink stores that the daemon hasn't
         touched yet this run.
      3. Legacy `catalog.duckdb` for pre-rotation (pre-0.3.8) stores.

    Doesn't query the daemon — pure file-system lookup."""
    root = _root()
    link = root / "read_only.duckdb"
    if link.exists() or link.is_symlink():
        return link
    marker = root / "active"
    if marker.exists():
        try:
            active = marker.read_text().strip()
            if active in ("A", "B"):
                inactive = "B" if active == "A" else "A"
                return root / f"catalog.{inactive}.duckdb"
        except OSError:
            pass
    return root / "catalog.duckdb"


def _should_via_replica(explicit_flag: bool) -> bool:
    """CLI prioritization: the read replica is the default for every read
    so reads bypass the daemon's `_store_lock` entirely (zero contention
    with bg watch flushes / ingest / writers).

    Resolution:
      1. Explicit `--via-replica` flag wins.
      2. Otherwise use the replica whenever its reader file exists
         (post-rotation-bootstrap stores). Falls back to the daemon /
         direct path only when there is no replica file yet.

    No environment-variable knob: the replica read path is self-healing
    (`_replica_read` relinks + retries on a lock conflict), so there's no
    reason to globally opt out of it."""
    if explicit_flag:
        return True
    try:
        return _replica_reader_path().exists()
    except Exception:
        return False


def _replica_store() -> Store:
    """Open the reader-slot catalog in read-only mode.

    Skips migrations / writes / repair. Used by `--via-replica` CLI ops
    so reads bypass the daemon's `_store_lock` entirely. The file is
    refreshed by the daemon's rotation thread every
    RMX_REPLICA_REFRESH_S seconds (default 5)."""
    path = _replica_reader_path()
    if not path.exists():
        raise click.ClickException(
            f"no replica file at {path}. Has the daemon bootstrapped "
            f"rotation? Run `rmx daemon start` and wait one refresh "
            f"cycle, or use `rmx replica refresh`."
        )
    s = Store(_root(), partition=_resolve_partition(), read_only=True)
    s.db_path = path
    atexit.register(s.close)
    return s


def _reader_store() -> Store | None:
    """Return a replica-backed read-only Store, or None when no usable
    replica is available.

    Resolution: replica reader slot only. The earlier fallback that
    attached read-only against the active catalog was incorrect —
    DuckDB's read-only open still acquires a shared file lock that
    conflicts with the daemon's exclusive write lock, raising
    `IOException: Could not set lock on file catalog.A.duckdb`.

    If the replica symlink points at the same file the daemon currently
    holds (a state seen during the bootstrap window or after certain
    swap-failure paths), the read-only attach raises IOException too.
    We catch it and return None so callers fall back to daemon RPC.

    Callers route to the daemon RPC when this returns None. The
    daemon-side read ops (`_op_memory_get/iter/search/recent`) hold
    `_store_lock` to serialize against `_refresh_replica_now`'s swap,
    so even the fallback path is race-free."""
    try:
        s = _replica_store()
    except click.ClickException:
        return None
    try:
        s._connect()  # surface IOException now, not at first query
    except Exception:
        try:
            s.close()
        except Exception:
            pass
        return None
    return s


def _is_lock_conflict(e: BaseException) -> bool:
    """True if `e` is a DuckDB cross-process file-lock conflict — the
    error raised when a read-only attach lands on the slot the daemon
    holds open read-write. Matched on message text (the driver raises a
    bare `IOException` with no dedicated subclass)."""
    msg = str(e)
    return "Conflicting lock" in msg or "set lock on file" in msg


def _replica_read(fn):
    """Run `fn(replica_store)` against the lock-free reader slot, with a
    self-healing bounded retry.

    The daemon's rotation keeps `read_only.duckdb` pointed at a slot it is
    NOT writing, and during a refresh it moves readers onto the freed slot
    BEFORE locking the one it catches up — so in steady state a reader
    never lands on a write-locked file. This wrapper covers the residual
    edges: a transiently drifted symlink, or the sub-millisecond window
    around a swap.

    On a DuckDB lock conflict: ask the daemon to re-point the link
    (`replica_relink`, lock-free on the daemon side) on the first miss,
    then retry on a fresh reader store with a short backoff, re-reading the
    (possibly just-swapped) symlink each attempt.

    No daemon-RPC fallback: a conflict that survives every attempt is a
    genuine fault, surfaced as a clean ClickException rather than the raw
    driver traceback. `fn` must do all work that touches the store (connect
    + query + render) so a retry re-runs cleanly — the lock error always
    fires at first connect, before any output is produced."""
    import time as _time
    from refmatrix import daemon as daemon_mod

    attempts = 5
    last: Exception | None = None
    for i in range(attempts):
        s = _replica_store()
        try:
            return fn(s)
        except Exception as e:
            if not _is_lock_conflict(e):
                raise
            last = e
            try:
                s.close()
            except Exception:
                pass
        if i == 0:
            # First miss → most likely a drifted symlink. Have the daemon
            # re-point it (cheap, no _store_lock on the daemon side).
            root = _root()
            if daemon_mod.ping(root):
                try:
                    daemon_mod.call(root, "replica_relink", {}, timeout=10.0)
                except Exception:
                    pass
        else:
            # Subsequent misses → ride out a swap window (sub-second).
            _time.sleep(0.1 * i)
    raise click.ClickException(
        "replica read hit a lock conflict that persisted after relinking "
        "and retries — the rotation reader slot may be mis-pointed. "
        "Run `rmx replica refresh`."
    ) from last


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="refmatrix")
@click.option(
    "--partition", "-p", default=None,
    help="Active partition name (overrides RMX_PARTITION and .refmatrix/partition).",
)
def main(partition: str | None):
    """Roaring-bitmap reference matrix for docs, code, concepts."""
    global _partition_override
    _partition_override = partition


# ---- init / info ----------------------------------------------------------


@main.command()
@click.option("--path", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Where to create .refmatrix/ (defaults to ./.refmatrix)")
@click.option("--hooks/--no-hooks", default=True,
              help="Install git + Claude Code hooks so the index stays "
                   "fresh on every commit and Edit/Write call.")
@click.option("--memory-hooks/--no-memory-hooks", default=True,
              help="Also install ADR-0001 Phase C memory hooks: "
                   "SessionStart recall, UserPromptSubmit recall, "
                   "PreCompact recent-recall. Templates documented at "
                   "docs/hooks/intuition-style-hooks.md.")
@click.option("--agents/--no-agents", default=True,
              help="Place packaged subagent descriptions (e.g. gmd-curator) "
                   "into .claude/agents/ for project-local invocation.")
@click.option("--force", is_flag=True,
              help="Overwrite existing hook / agent / briefing files.")
def init(path: Path | None, hooks: bool, memory_hooks: bool, agents: bool,
         force: bool):
    """Initialize a refmatrix in the given directory (default: cwd).

    By default also installs hooks and packaged subagent descriptions so
    the project is fully wired on first run. Pass --no-hooks / --no-agents
    to opt out.
    """
    project_root = (path or Path.cwd()).resolve()
    target = project_root / ".refmatrix"
    s = Store(target, partition=_resolve_partition())
    # If a daemon already owns this catalog, skip Store.init() — it would
    # try to acquire the DuckDB write lock and crash. The store is already
    # initialized (the daemon proves it). We only need the Store object to
    # report root/partition; no _connect() call is required for that.
    from refmatrix import daemon as daemon_mod
    if daemon_mod.ping(s.root):
        console.print(
            f"[yellow]reusing[/] existing {s.root} (daemon pid present; "
            f"skipped catalog reinit)"
        )
    else:
        s.init()
        atexit.register(s.close)
        console.print(f"[green]initialized[/] {s.root} (partition={s.partition_name})")

    if hooks:
        from refmatrix.hooks import install
        for line in install(
            project_root=project_root, refmatrix_root=s.root,
            git=True, claude=True, briefing=True, scope="project",
            apply=True, force=force, memory_hooks=memory_hooks,
        ):
            console.print(line)

    if agents:
        from refmatrix.init_agents import install_agents
        for line in install_agents(project_root=project_root, force=force):
            console.print(line)


@main.command()
def info():
    """Print the active refmatrix root and partition."""
    console.print(f"root:      {_root()}")
    console.print(f"partition: {_resolve_partition()}")


@main.group()
def daemon():
    """Per-store background process that holds the catalog open and
    serializes writes — bypasses DuckDB's single-writer lock contention
    when many hooks fire concurrently."""


@daemon.command("start")
@click.option(
    "--watch/--no-watch", default=True,
    help="Spawn a watchdog thread that debounces fs events and syncs "
         "changed files automatically. Default on when watchdog is installed.",
)
@click.option(
    "--watch-root", "watch_roots",
    type=click.Path(path_type=Path), default=(), multiple=True,
    help="Directory to watch. Repeat for multiple paths (e.g. project "
         "tree plus the auto-memory dir). Defaults to the parent of the "
         "active `.refmatrix/` (the project root) when omitted.",
)
@click.option(
    "--debounce-ms", type=int, default=500,
    help="Quiet period before flushing a batch of fs events (ms).",
)
@click.option(
    "--semantic", is_flag=True,
    help="Also extract Python semantics on watcher-driven syncs (slow).",
)
@click.option(
    "--no-detach", is_flag=True,
    help="Run the daemon in the foreground (do not fork). Use this when "
         "launching under a supervisor like launchd / systemd that owns "
         "the process lifecycle. Required by `rmx daemon launchctl install`.",
)
def daemon_start(watch: bool, watch_roots: tuple[Path, ...], debounce_ms: int,
                 semantic: bool, no_detach: bool):
    """Start the rmx daemon for the active store. Idempotent: re-running
    while a daemon is already up is a fast no-op (returns its pid)."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not root.is_dir():
        raise click.ClickException(
            f"no refmatrix at {root}. Run `rmx init` first."
        )
    resolved_watch_roots: list[Path] = []
    if watch:
        if watch_roots:
            resolved_watch_roots = [Path(r).resolve() for r in watch_roots]
        else:
            resolved_watch_roots = [root.parent.resolve()]
    if no_detach:
        # Foreground mode for launchd / systemd. Blocks until SIGTERM.
        try:
            daemon_mod.serve_foreground(
                root,
                partition=_resolve_partition(),
                watch_root=resolved_watch_roots or None,
                watch_debounce_ms=debounce_ms,
                watch_semantic=semantic,
            )
        except RuntimeError as e:
            raise click.ClickException(str(e))
        return
    pid = daemon_mod.spawn_daemon(
        root,
        partition=_resolve_partition(),
        watch_root=resolved_watch_roots or None,
        watch_debounce_ms=debounce_ms,
        watch_semantic=semantic,
    )
    if resolved_watch_roots:
        roots_repr = (
            str(resolved_watch_roots[0])
            if len(resolved_watch_roots) == 1
            else "[" + ", ".join(str(r) for r in resolved_watch_roots) + "]"
        )
        extra = f" watching={roots_repr} (debounce={debounce_ms}ms)"
    else:
        extra = ""
    console.print(f"[green]daemon running[/] pid={pid} root={root}{extra}")


@daemon.command("stop")
def daemon_stop():
    """Stop the daemon for the active store, if any. Idempotent."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.stop_daemon(root):
        console.print("[green]daemon stopped[/]")
    else:
        raise click.ClickException("daemon did not stop within timeout")


@daemon.command("status")
def daemon_status():
    """Report whether the daemon is running for the active store."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    pid = daemon_mod.read_pid(root)
    healthy = daemon_mod.ping(root) if pid else False
    if pid and healthy:
        console.print(f"[green]running[/] pid={pid} root={root}")
    elif pid:
        console.print(f"[yellow]stale pid[/] {pid} (socket unreachable)")
    else:
        console.print("[dim]not running[/]")


@daemon.group("launchctl")
def daemon_launchctl():
    """Generate + manage a macOS launchd LaunchAgent for the active store.

    Installs a per-store plist in `~/Library/LaunchAgents/` that runs
    `rmx daemon start --no-detach` at login and restarts on crash.
    User-domain only — no sudo required.
    """


@daemon_launchctl.command("install")
@click.option("--watch/--no-watch", default=True,
              help="Embed --no-watch in the plist's ProgramArguments. "
                   "Default on.")
@click.option("--watch-root", "watch_roots",
              type=click.Path(path_type=Path), default=(), multiple=True,
              help="Directory the supervised daemon should watch. "
                   "Repeat for multiple. Defaults to the parent of the "
                   "active `.refmatrix/`.")
@click.option("--debounce-ms", type=int, default=500,
              help="Watcher debounce window passed to `daemon start`.")
@click.option("--semantic", is_flag=True,
              help="Pass --semantic to `daemon start` for Python "
                   "semantic extraction on watcher syncs.")
@click.option("--force", is_flag=True,
              help="Rewrite the plist and reload even if already "
                   "installed and loaded.")
def daemon_launchctl_install(watch: bool, watch_roots: tuple[Path, ...],
                             debounce_ms: int, semantic: bool, force: bool):
    """Install + bootstrap the LaunchAgent plist for the active store."""
    from refmatrix import launchctl as lc
    root = _root()
    if not root.is_dir():
        raise click.ClickException(
            f"no refmatrix at {root}. Run `rmx init` first."
        )
    roots_list = [Path(r).resolve() for r in watch_roots] or None
    try:
        p = lc.install(
            root, partition=_resolve_partition(),
            watch=watch, debounce_ms=debounce_ms,
            semantic=semantic, force=force,
            watch_roots=roots_list,
        )
    except (RuntimeError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    console.print(f"[green]installed[/] {p}")
    console.print(f"label: {lc.label_for_root(root)}")
    console.print(
        "logs:  "
        f"{root / 'daemon.stdout.log'} / {root / 'daemon.stderr.log'}"
    )


@daemon_launchctl.command("kickstart")
@click.option("-k", "--restart", is_flag=True,
              help="Force-restart the daemon if already running "
                   "(launchctl kickstart -k).")
def daemon_launchctl_kickstart(restart: bool):
    """Ensure the supervised daemon for the active store is running.

    Resolves the store's LaunchAgent label and `launchctl kickstart`s it —
    starts it if down, no-ops if already up, or restarts with -k. Intended
    for SessionStart hooks so a session always begins with a live,
    supervised daemon under the current label naming."""
    from refmatrix import launchctl as lc
    root = _root()
    try:
        label = lc.kickstart(root, restart=restart)
    except (RuntimeError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    console.print(f"[green]kickstarted[/] {label}")


@daemon_launchctl.command("uninstall")
def daemon_launchctl_uninstall():
    """Bootout the LaunchAgent and remove its plist file."""
    from refmatrix import launchctl as lc
    root = _root()
    try:
        removed = lc.uninstall(root)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    if removed:
        console.print(f"[green]uninstalled[/] {lc.plist_path(root)}")
    else:
        console.print("[dim]no plist to remove[/]")


@daemon_launchctl.command("status")
def daemon_launchctl_status():
    """Show plist path, label, and whether it is installed + loaded."""
    from refmatrix import launchctl as lc
    root = _root()
    st = lc.status(root)
    console.print(f"label:     {st['label']}")
    console.print(f"plist:     {st['plist_path']}")
    console.print(
        "installed: "
        f"{'[green]yes[/]' if st['installed'] else '[dim]no[/]'}"
    )
    console.print(
        "loaded:    "
        f"{'[green]yes[/]' if st['loaded'] else '[dim]no[/]'}"
    )


@daemon_launchctl.command("print")
@click.option("--watch/--no-watch", default=True)
@click.option("--watch-root", "watch_roots",
              type=click.Path(path_type=Path), default=(), multiple=True)
@click.option("--debounce-ms", type=int, default=500)
@click.option("--semantic", is_flag=True)
def daemon_launchctl_print(watch: bool, watch_roots: tuple[Path, ...],
                           debounce_ms: int, semantic: bool):
    """Render the plist to stdout without installing. Useful for review
    or piping into a different LaunchAgents directory."""
    from refmatrix import launchctl as lc
    root = _root()
    roots_list = [Path(r).resolve() for r in watch_roots] or None
    try:
        data = lc.render_plist(
            root, partition=_resolve_partition(),
            watch=watch, debounce_ms=debounce_ms,
            semantic=semantic, watch_roots=roots_list,
        )
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    click.echo(data.decode())


@main.command("migrate-to-duckdb")
@click.option(
    "--out", "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Destination DuckDB file (defaults to <root>/catalog.duckdb).",
)
@click.option(
    "--overwrite", is_flag=True,
    help="Replace the destination if it already exists.",
)
def migrate_to_duckdb(out_path: Path | None, overwrite: bool):
    """One-shot copy of the SQLite catalog into a native DuckDB catalog.

    Phase-2 of the DuckDB migration: makes a `.refmatrix/catalog.duckdb`
    alongside the existing `catalog.db`. The SQLite catalog is unchanged
    and remains the system of record until phase-2b flips writes over.
    """
    from refmatrix.migrate import migrate_catalog

    root = _root()
    src = root / "catalog.db"
    if not src.exists():
        raise click.ClickException(
            f"no SQLite catalog at {src}. Run `rmx init` first."
        )
    dst = out_path or (root / "catalog.duckdb")
    fragments_dir = root / "fragments"
    counts = migrate_catalog(
        src, dst,
        overwrite=overwrite,
        fragments_dir=fragments_dir if fragments_dir.is_dir() else None,
    )
    table = Table(show_header=True)
    table.add_column("table")
    table.add_column("rows", justify="right")
    for name, n in counts.items():
        table.add_row(name, str(n))
    console.print(table)
    console.print(f"[green]wrote[/] {dst}")


@main.group()
def partition():
    """Inspect and manage named partitions inside the active refmatrix."""


@partition.command("list")
def partition_list():
    """List all partitions in the active refmatrix, marking the active one."""
    s = _store()
    active = s.partition_name
    rows = s._connect().execute(
        "SELECT id, name, kind, root_path, created_at "
        "FROM partitions ORDER BY id"
    ).fetchall()
    table = Table(show_header=True)
    table.add_column("active")
    table.add_column("id", justify="right")
    table.add_column("name")
    table.add_column("kind")
    table.add_column("root_path")
    for r in rows:
        table.add_row(
            "*" if r["name"] == active else "",
            str(r["id"]), r["name"], r["kind"], r["root_path"] or "",
        )
    console.print(table)


@partition.command("add")
@click.argument("name")
@click.option("--kind", type=click.Choice(["repo", "canon", "agent-scratch"]),
              default="repo")
@click.option("--root-path", default=None, help="Optional source repo path.")
def partition_add(name: str, kind: str, root_path: str | None):
    """Register a partition explicitly. (Writes auto-create a partition by
    name too, so this is mostly for the 'canon' or 'agent-scratch' kinds.)"""
    import time as _time
    s = _store()
    con = s._connect()
    con.execute(
        "INSERT OR IGNORE INTO partitions(name, kind, root_path, created_at) "
        "VALUES (?, ?, ?, ?)",
        (name, kind, root_path, _time.time()),
    )
    con.commit()
    console.print(f"[green]registered[/] partition={name} kind={kind}")


@partition.command("rename")
@click.argument("old")
@click.argument("new")
def partition_rename(old: str, new: str):
    """Rename partition OLD to NEW.

    Updates the catalog row and moves the partition's fragment + vector
    directories. Entity rows reference the partition by id, so their data is
    untouched. Restart any daemon bound to OLD afterwards."""
    s = _store()
    try:
        s.rename_partition(old, new)
    except ValueError as e:
        raise click.ClickException(str(e))
    s.close()
    console.print(f"[green]renamed[/] partition {old} -> {new}")
    console.print(
        "[dim]restart the daemon if it was bound to the old name "
        "(`rmx daemon launchctl kickstart -k`).[/]"
    )


# ---- canon (cross-codebase concept matching) -----------------------------


@main.group()
def canon():
    """Wire concepts across partitions through a canonical hub.

    Each partition stores its own `parser` (or whatever) concept independently.
    Use `rmx canon link parser` to wire your active partition's concept to a
    canonical concept in a separate partition (default: 'canon'). Other
    partitions doing the same become siblings — `rmx canon siblings parser`
    surfaces them, so you can see which repos talk about the same thing.
    """


@canon.command("link")
@click.argument("concept")
@click.option(
    "--canon-name", default=None,
    help="Name for the canon concept (default: same as <concept>).",
)
@click.option(
    "--canon-partition", default="canon",
    help="Partition where the canon concept lives (default: 'canon').",
)
def canon_link(concept: str, canon_name: str | None, canon_partition: str):
    """Wire the active partition's CONCEPT to a canonical concept.

    Auto-creates the canon concept if it doesn't exist yet. Re-running is
    idempotent — a second invocation re-asserts the same_as edge."""
    s = _store()
    local = s.get_entity("concept", concept)
    if local is None:
        raise click.ClickException(
            f"no concept '{concept}' in partition '{s.partition_name}'. "
            f"Run `rmx add-concept {concept}` first."
        )
    name = canon_name or concept
    canon_id = s.link_canon(local.id, canon_partition, name)
    console.print(
        f"[green]linked[/] {s.partition_name}/{concept} "
        f"-> {canon_partition}/{name} (canon_id={canon_id})"
    )


@canon.command("siblings")
@click.argument("concept")
def canon_siblings(concept: str):
    """List concepts in other partitions that share a canon hub with CONCEPT."""
    s = _store()
    local = s.get_entity("concept", concept)
    if local is None:
        raise click.ClickException(
            f"no concept '{concept}' in partition '{s.partition_name}'."
        )
    rows = s.siblings_via_canon(local.id)
    if not rows:
        console.print(
            f"[yellow]no siblings[/] for {s.partition_name}/{concept} "
            f"(run `rmx canon link {concept}` here and in the other partition first)"
        )
        return
    table = Table(show_header=True, title=f"siblings of {s.partition_name}/{concept}")
    table.add_column("partition")
    table.add_column("concept")
    table.add_column("via canon")
    for r in rows:
        table.add_row(
            r["partition_name"],
            r["name"],
            f"{r['canon_partition']}/{r['canon_name']}",
        )
    console.print(table)


# ---- entities & concepts --------------------------------------------------


# ---- add / list subgroups -------------------------------------------------
#
# Flat hyphenated verbs (`rmx add-concept`, `rmx list-entities`, …) were
# adoption-blocking: no `rmx add <TAB>` discovery, history-search noise, and
# the hyphen forces composing the full verb. Subgroups give discoverability
# without breaking existing callers — the old hyphenated names stay as
# hidden aliases.


def _alias(src_cmd: click.Command, name: str) -> click.Command:
    """Return a hidden copy of `src_cmd` to register under `name` on the
    main group so old call sites (`rmx add-concept …`) keep working without
    cluttering `rmx --help` with both forms."""
    import copy
    cmd = copy.copy(src_cmd)
    cmd.hidden = True
    cmd.name = name
    return cmd


@main.group()
def add():
    """Add concepts, entities, and linkage types."""


@main.group("list")
def list_grp():
    """List entities, linkages, saved queries."""


@add.command("entity")
@click.option("--kind", required=True, type=click.Choice(["doc", "code", "concept"]))
@click.argument("name")
@click.option("--path", default=None, help="Optional filesystem path.")
@click.option("--tldr", default=None, help="Hyper-tldr summary blob.")
@click.option("--meta", default=None, help="JSON metadata.")
@click.option("--no-protect", is_flag=True,
              help="Don't pin this entity. By default manual adds are protected "
                   "from vacuum and prune-noise.")
def add_entity(kind, name, path, tldr, meta, no_protect):
    """Insert or update an entity. Manual adds are protected by default."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "upsert_entity", {
            "kind": kind, "name": name, "path": path, "tldr": tldr,
            "meta": meta, "protected": not no_protect,
        })
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        eid = resp["result"]["id"]
    else:
        s = _store()
        meta_d = json.loads(meta) if meta else None
        eid = s.upsert_entity(kind=kind, name=name, path=path, tldr=tldr,
                              meta=meta_d, protected=not no_protect)
    pinned = "" if no_protect else " (pinned)"
    console.print(f"[green]upserted[/] {kind}:{name} (id={eid}){pinned}")


main.add_command(_alias(add_entity, "add-entity"))


@add.command("concept")
@click.argument("name")
@click.option("--description", "-d", default=None)
@click.option("--no-protect", is_flag=True,
              help="Don't pin this concept. By default manual adds are protected.")
def add_concept(name, description, no_protect):
    """Add a concept (= entity of kind 'concept'). Pinned by default."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "add_concept", {
            "name": name, "description": description,
            "protected": not no_protect,
        })
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        cid = resp["result"]["id"]
    else:
        s = _store()
        cid = s.add_concept(name, description=description, protected=not no_protect)
    pinned = "" if no_protect else " (pinned)"
    console.print(f"[green]added concept[/] {name} (id={cid}){pinned}")


main.add_command(_alias(add_concept, "add-concept"))


@list_grp.command("entities")
@click.option("--kind", type=click.Choice(["doc", "code", "concept"]), default=None)
def list_entities(kind):
    """List entities."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    t = Table("id", "kind", "name", "path", "tldr")
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "iter_entities", {"kind": kind})
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        for r in resp["result"]["rows"]:
            t.add_row(str(r["id"]), r["kind"], r["name"], r["path"] or "",
                      (r["tldr"] or "")[:80])
    else:
        s = _store()
        for e in s.iter_entities(kind):
            t.add_row(str(e.id), e.kind, e.name, e.path or "",
                      (e.tldr or "")[:80])
    console.print(t)


main.add_command(_alias(list_entities, "list-entities"))


# ---- linkage types --------------------------------------------------------


@add.command("linkage-type")
@click.argument("name")
@click.option("--directed/--undirected", default=True)
@click.option("--description", "-d", default=None)
def add_linkage_type(name, directed, description):
    """Define a custom linkage type."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "add_linkage_type", {
            "name": name, "directed": directed, "description": description,
        })
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        lid = resp["result"]["id"]
    else:
        s = _store()
        lid = s.add_linkage_type(name=name, directed=directed,
                                 description=description)
    console.print(f"[green]linkage type[/] {name} (id={lid})")


main.add_command(_alias(add_linkage_type, "add-linkage-type"))


@list_grp.command("linkages")
def list_linkages():
    """List linkage types."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    t = Table("id", "name", "directed", "description")
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "list_linkages", {})
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        rows = _store().list_linkages()
    for lk in rows:
        t.add_row(str(lk["id"]), lk["name"],
                  "yes" if lk["directed"] else "no",
                  lk["description"] or "")
    console.print(t)


main.add_command(_alias(list_linkages, "list-linkages"))


# ---- linking --------------------------------------------------------------


def _resolve_concept(s: Store, ref: str) -> int:
    e = s.resolve_entity(ref)
    if e is None or e.kind != "concept":
        raise click.ClickException(f"no concept named {ref!r}. `rmx add-concept {ref}` first?")
    return e.id


def _resolve_entity_id(s: Store, ref: str) -> int:
    e = s.resolve_entity(ref)
    if e is None:
        raise click.ClickException(f"no entity named {ref!r}.")
    return e.id


@main.command()
@click.argument("concept")
@click.argument("entity")
@click.option("--type", "linkage", default="mentions",
              help="Linkage type (default: mentions).")
@click.option("--no-protect", is_flag=True,
              help="Don't pin the endpoints. By default a manual link protects "
                   "both the concept and entity from vacuum/prune-noise.")
def link(concept, entity, linkage, no_protect):
    """Set bit (linkage, concept, entity). Pins both endpoints by default."""
    s = _store()
    cid = _resolve_concept(s, concept)
    eid = _resolve_entity_id(s, entity)
    added = s.link(linkage, cid, eid, protect=not no_protect)
    msg = "linked" if added else "already linked"
    pinned = "" if no_protect else " (pinned)"
    console.print(f"[green]{msg}[/] {linkage}: {concept} -> {entity}{pinned}")


@main.command()
@click.argument("concept")
@click.argument("entity")
@click.option("--type", "linkage", default="mentions")
def unlink(concept, entity, linkage):
    """Clear bit (linkage, concept, entity)."""
    s = _store()
    cid = _resolve_concept(s, concept)
    eid = _resolve_entity_id(s, entity)
    removed = s.unlink(linkage, cid, eid)
    console.print(f"[yellow]{'unlinked' if removed else 'not linked'}[/] {linkage}: {concept} -> {entity}")


# ---- query ----------------------------------------------------------------


def _print_bitmap(s: Store, bm, limit: int = 50):
    t = Table("id", "kind", "name", "path")
    ids = list(bm)
    for eid in ids[:limit]:
        e = s.get_entity_by_id(eid)
        if e:
            t.add_row(str(e.id), e.kind, e.name, e.path or "")
    console.print(t)
    if len(ids) > limit:
        console.print(f"[dim]... {len(ids) - limit} more (cardinality={len(bm)})[/]")
    else:
        console.print(f"[dim]cardinality={len(bm)}[/]")


@main.command()
@click.argument("expr")
@click.option("--pql", "is_pql", is_flag=True, help="Treat expr as PQL not DSL.")
@click.option("--ids-only", is_flag=True)
@click.option("--limit", default=50, type=int)
@click.option("--explain", is_flag=True,
              help="For each result entity, show which (linkage, concept) memberships it has.")
@click.option("--full", "include_noise", is_flag=True,
              help="Include concepts marked noise by prune-noise. Default uses "
                   "the cleaned graph; --full restores the raw index for find/grep "
                   "replacement.")
@click.option("--filter", "name_filter", default=None,
              help="SQL LIKE pattern to filter result entities by name (e.g. '%.pseudo::%').")
@click.option("--strict", is_flag=True,
              help="Disable surface-form variant expansion for concept names. "
                   "By default `mentions:JSONParser` matches concepts canonicalized "
                   "to json_parser too (camelCase/PascalCase/dash/space variants); "
                   "--strict requires an exact name match.")
@click.option("--via-replica", is_flag=True,
              help="Read from the rotation reader slot instead of the daemon. "
                   "Bypasses _store_lock entirely; reads at native DuckDB speed "
                   "even during heavy bg ingest. Sees stale-by-N-seconds data "
                   "(N = RMX_REPLICA_REFRESH_S, default 5).")
def query(expr, is_pql, ids_only, limit, explain, include_noise, name_filter, strict, via_replica):
    """Run a query. DSL: `mentions:parser AND defines:parser`. PQL: `Row(calls,foo)`."""
    # --explain renders evidence via the daemon's writer-slot path; the
    # replica fast path doesn't (yet) carry the evidence join. Force the
    # daemon route when --explain is set so we don't silently drop the
    # explain output now that the replica is the default read path.
    if not explain:
        via_replica = _should_via_replica(via_replica)
    if via_replica:
        def _run(s):
            qe = QueryEngine(s, include_noise=include_noise, strict=strict)
            with log_query(s, kind="pql" if is_pql else "dsl",
                           body=expr, source="query-replica") as t:
                result = qe.run_pql(expr) if is_pql else qe.run(expr)
                try:
                    t.cardinality = len(result) if hasattr(result, "__len__") else None
                except TypeError:
                    t.cardinality = None
            if name_filter:
                from pyroaring import BitMap
                matching = BitMap(
                    r[0] for r in s._connect().execute(
                        "SELECT id FROM entities WHERE name LIKE ?", (name_filter,)
                    )
                )
                if isinstance(result, list):
                    result = [(eid, w) for eid, w in result if eid in matching]
                elif hasattr(result, '__iter__') and not isinstance(result, int):
                    result = result & matching
            if isinstance(result, list):
                t = Table("entity", "weight")
                for eid, w in result:
                    e = s.get_entity_by_id(eid)
                    t.add_row(e.name if e else str(eid), str(w))
                console.print(t)
                return
            if isinstance(result, int):
                console.print(str(result))
                return
            if ids_only:
                for eid in result:
                    print(eid)
                return
            _print_bitmap(s, result, limit=limit)
        _replica_read(_run)
        return

    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "query", {
            "expr": expr, "pql": is_pql, "include_noise": include_noise,
            "limit": limit, "name_filter": name_filter, "explain": explain,
            "strict": strict,
        }, timeout=120.0)
        if not resp.get("ok"):
            raise click.ClickException(f"daemon query failed: {resp.get('error')}")
        r = resp["result"]
        if r["shape"] == "int":
            console.print(str(r["value"]))
            return
        if r["shape"] == "weighted":
            t = Table("entity", "weight")
            for row in r["rows"]:
                t.add_row(row["name"] or str(row["id"]), str(row["weight"]))
            console.print(t)
            console.print(f"[dim]cardinality={r['cardinality']}[/]")
            return
        if ids_only:
            for row in r["rows"]:
                print(row["id"])
            return
        t = Table("id", "kind", "name", "path")
        for row in r["rows"]:
            t.add_row(str(row["id"]), row["kind"] or "", row["name"] or "",
                      row["path"] or "")
        console.print(t)
        console.print(f"[dim]cardinality={r['cardinality']}[/]")
        if explain and "evidence" in r:
            for eid_s, ev in r["evidence"].items():
                if not ev:
                    continue
                console.print(f"\n[bold]entity {eid_s}[/]")
                for x in ev:
                    loc = f" {x['file']}:{x['line']}" if x.get("line") else ""
                    console.print(
                        f"  {x['linkage']}:{x['concept']}{loc}"
                    )
        return

    s = _store()
    qe = QueryEngine(s, include_noise=include_noise, strict=strict)
    with log_query(s, kind="pql" if is_pql else "dsl", body=expr, source="query") as t:
        result = qe.run_pql(expr) if is_pql else qe.run(expr)
        try:
            t.cardinality = len(result) if hasattr(result, "__len__") else None
        except TypeError:
            t.cardinality = None
    if name_filter:
        from pyroaring import BitMap
        matching = BitMap(
            r[0] for r in s._connect().execute(
                "SELECT id FROM entities WHERE name LIKE ?", (name_filter,)
            )
        )
        if isinstance(result, list):
            result = [(eid, w) for eid, w in result if eid in matching]
        elif hasattr(result, '__iter__') and not isinstance(result, int):
            result = result & matching
    if isinstance(result, list):
        t = Table("entity", "weight")
        for eid, w in result:
            e = s.get_entity_by_id(eid)
            t.add_row(e.name if e else str(eid), str(w))
        console.print(t)
        return
    if isinstance(result, int):
        console.print(str(result))
        return
    if ids_only:
        for eid in result:
            print(eid)
        return
    _print_bitmap(s, result, limit=limit)
    if explain:
        ids = list(result)[:limit]
        for eid in ids:
            ent = s.get_entity_by_id(eid)
            if not ent:
                continue
            console.print(f"\n[bold]{ent.name}[/]  [{ent.kind}]")
            rows = s.explain_entity(eid)
            t = Table("linkage", "concept", "weight", "evidence")
            for r in rows:
                ev = "—"
                if r["evidence"]:
                    ev = "; ".join(
                        f"{e.get('file') or '?'}:{e.get('line') or '?'}"
                        for e in r["evidence"][:3]
                    )
                w = "" if r["weight"] is None else f"{r['weight']:g}"
                t.add_row(r["linkage"], r["concept_name"] or str(r["concept_id"]),
                          w, ev)
            console.print(t)


@main.command()
@click.argument("concept")
@click.option("--depth", default=1, type=int)
@click.option("--linkage", multiple=True, help="Restrict to these linkage types.")
@click.option("--limit", default=50, type=int)
@click.option("--full", "include_noise", is_flag=True,
              help="Include noise-marked concepts in the walk.")
@click.option("--strict", is_flag=True,
              help="Disable surface-form variant expansion for the seed concept.")
@click.option("--via-replica", is_flag=True,
              help="Read from the rotation reader slot instead of the daemon. "
                   "Lock-free; sees stale-by-N-seconds data.")
def neighbors(concept, depth, linkage, limit, include_noise, strict, via_replica):
    """Walk linkages from a concept (depth-N closure)."""
    via_replica = _should_via_replica(via_replica)

    def _run(s):
        qe = QueryEngine(s, include_noise=include_noise, strict=strict)
        with log_query(s, kind="neighbors", body=concept,
                       source="neighbors") as t:
            bm = qe.neighbors(concept, depth=depth,
                              linkages=list(linkage) or None)
            t.cardinality = len(bm)
        _print_bitmap(s, bm, limit=limit)

    if via_replica:
        _replica_read(_run)
    else:
        _run(_store())


@main.command()
@click.argument("symbol", required=False)
@click.option("--linkage", "-l", multiple=True,
              help="Restrict to these linkage types (repeatable).")
@click.option("--max-entities", default=20, type=int)
@click.option("--max-tokens", default=4000, type=int)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--since", default=None,
              help="Branch-scoped: bundle for concepts touched by `git diff --name-only <ref>`.")
@click.option("--fuse", is_flag=True,
              help="Reciprocal Rank Fusion across linkages. Avoids biasing truncation toward early linkage order.")
@click.option("--strict", is_flag=True,
              help="Disable surface-form variant expansion. By default `JSONParser`, "
                   "`json_parser`, `json-parser`, and `json parser` resolve to the "
                   "same canonical concept; --strict requires exact-name match.")
@click.option("--via-replica", is_flag=True,
              help="Read from the rotation reader slot instead of the daemon. "
                   "Lock-free; sees stale-by-N-seconds data.")
def context(symbol, linkage, max_entities, max_tokens, fmt, since, fuse, strict, via_replica):
    """Token-budgeted context bundle: anchor + neighbors + their tldr blobs."""
    from refmatrix.context import build_context, render_json, render_text
    from refmatrix import daemon as daemon_mod

    # `--since` requires a writer-slot connection (the diff lookup hits
    # path metadata that the replica may not cover yet); honor that case
    # below by leaving via_replica False. Same for the no-symbol path
    # which streams from the writer.
    if not since and symbol:
        via_replica = _should_via_replica(via_replica)

    if via_replica:
        if since:
            raise click.ClickException("--via-replica does not support --since")
        if not symbol:
            raise click.ClickException("--via-replica requires a symbol")
        def _run(s):
            with log_query(s, kind="context", body=symbol,
                           source="context-replica") as t:
                b = build_context(
                    s, symbol,
                    linkages=list(linkage) or None,
                    max_entities=max_entities,
                    max_tokens=max_tokens,
                    fuse=fuse,
                    strict=strict,
                )
                t.cardinality = b.total_entities() if b.anchor else 0
            return b
        bundle = _replica_read(_run)
        if fmt == "json":
            click.echo(render_json(bundle))
        else:
            click.echo(render_text(bundle))
        return

    # If a daemon is up, route the simple `context <symbol>` path through
    # the socket before trying to open the catalog ourselves — DuckDB
    # blocks cross-process reads while the daemon holds the write lock.
    if symbol and not since:
        root = _root()
        if daemon_mod.ping(root):
            resp = daemon_mod.call(root, "context", {
                "ref": symbol,
                "format": fmt,
                "linkages": list(linkage) or None,
                "max_entities": max_entities,
                "max_tokens": max_tokens,
                "fuse": fuse,
                "strict": strict,
            }, timeout=120.0)
            if not resp.get("ok"):
                raise click.ClickException(
                    f"daemon context failed: {resp.get('error')}"
                )
            click.echo(resp["result"]["body"])
            return

    s = _store()

    if since:
        import shutil
        import subprocess
        if not shutil.which("git"):
            raise click.ClickException("git not on PATH")
        proj = s.root.parent
        out = subprocess.run(
            ["git", "-C", str(proj), "diff", "--name-only", since],
            capture_output=True, text=True, check=True,
        )
        paths = [p for p in out.stdout.splitlines() if p.strip()]
        if not paths:
            console.print(f"[yellow]no files changed since {since}[/]")
            return
        # collect unique concepts that link to entities under those paths
        concept_ids: set[int] = set()
        for relp in paths:
            ap = (proj / relp).resolve()
            for eid in (
                r[0] for r in s._connect().execute(
                    "SELECT id FROM entities WHERE path=?", (str(ap),)
                )
            ):
                for r in s._connect().execute(
                    "SELECT DISTINCT concept_id FROM entity_links WHERE entity_id=?",
                    (eid,),
                ):
                    concept_ids.add(r[0])
        if not concept_ids:
            console.print(f"[yellow]no indexed concepts touch the {len(paths)} changed file(s)[/]")
            return
        # Render a small bundle per concept.
        concept_names = [s.get_entity_by_id(cid).name for cid in concept_ids
                         if s.get_entity_by_id(cid)]
        per = max(200, max_tokens // max(1, min(len(concept_names), 8)))
        rendered: list[str] = [
            f"# context for changes since {since} — {len(concept_names)} concepts"
        ]
        used = 0
        for name in sorted(concept_names)[:8]:
            b = build_context(s, name, max_tokens=per, max_entities=10,
                              linkages=list(linkage) or None, fuse=fuse,
                              strict=strict)
            if b.anchor is None or not b.groups:
                continue
            block = render_json(b) if fmt == "json" else render_text(b)
            cost = len(block) // 4
            if used + cost > max_tokens:
                rendered.append("# [truncated]")
                break
            rendered.append("")
            rendered.append(block)
            used += cost
        click.echo("\n".join(rendered))
        return

    if not symbol:
        raise click.ClickException("provide a symbol or use --since <git-ref>")
    with log_query(s, kind="context", body=symbol, source="context") as t:
        bundle = build_context(
            s, symbol,
            linkages=list(linkage) or None,
            max_entities=max_entities,
            max_tokens=max_tokens,
            fuse=fuse,
            strict=strict,
        )
        t.cardinality = bundle.total_entities() if bundle.anchor else 0
    if fmt == "json":
        click.echo(render_json(bundle))
    else:
        click.echo(render_text(bundle))


@main.command("co-occur")
@click.argument("concept")
@click.option("--type", "linkage", default="mentions")
@click.option("--limit", default=20, type=int)
@click.option("--full", "include_noise", is_flag=True,
              help="Include noise-marked concepts.")
def co_occur(concept, linkage, limit, include_noise):
    """Concepts that share entities with the given concept under a linkage."""
    s = _store()
    qe = QueryEngine(s, include_noise=include_noise)
    with log_query(s, kind="co-occur", body=concept, source="co-occur") as t:
        rows = qe.co_occurrence(concept, linkage=linkage)[:limit]
        t.cardinality = len(rows)
    t = Table("concept", "overlap")
    for name, n in rows:
        t.add_row(name, str(n))
    console.print(t)


_GREP_FLAGS_HELP = (
    "Grep-style flag bundle, quoted. Accepts spaces or bundled letters: "
    "`-f '-i -n -l'`, `-f '-inl'`, `-f -i`. Recognized: "
    "-i ignore-case (default ON; -I forces case-sensitive), "
    "-r recursive (no-op — always recursive over the index), "
    "-n line numbers (no-op — always shown), "
    "-l files only (one line per unique file, suppress per-hit detail), "
    "-c count matches per file, "
    "-v invert match (entities/files with NO match), "
    "-w word-boundary match, "
    "-F fixed-string (substring) — same as --substring, "
    "-E extended regex — same as --regex, "
    "-H print filename (no-op — always shown)."
)


def _parse_grep_flags(s: str | None) -> dict:
    """Parse a grep-style flag bundle string into a dict of bool flags.
    Accepts space-separated or bundled forms: '-il', '-i -l', '-inl', '-i'.
    Unknown letters raise click.UsageError."""
    f = {
        "ignore_case": None, "files_only": False, "count": False,
        "invert": False, "word": False, "force_substring": False,
        "force_regex": False, "files_without_match": False,
    }
    if not s:
        return f
    valid = "irIRnLlcvwFEH"
    for chunk in s.split():
        if not chunk.startswith("-") or len(chunk) < 2:
            raise click.UsageError(
                f"--flags: '{chunk}' is not a grep-style flag (need leading dash)"
            )
        for ch in chunk[1:]:
            if ch not in valid:
                raise click.UsageError(
                    f"--flags: unknown letter '-{ch}'. Recognized: {valid}"
                )
            if ch == "i":
                f["ignore_case"] = True
            elif ch == "I":
                f["ignore_case"] = False
            elif ch == "l":
                f["files_only"] = True
            elif ch == "L":
                f["files_without_match"] = True
            elif ch == "c":
                f["count"] = True
            elif ch == "v":
                f["invert"] = True
            elif ch == "w":
                f["word"] = True
            elif ch == "F":
                f["force_substring"] = True
            elif ch == "E":
                f["force_regex"] = True
            # r, n, H are accepted but no-op
    if f["force_substring"] and f["force_regex"]:
        raise click.UsageError("--flags: -F and -E are mutually exclusive")
    if f["files_only"] and f["files_without_match"]:
        raise click.UsageError("--flags: -l and -L are mutually exclusive")
    return f


def _render_grep_rows(rows, gf, limit, source_tag="idx"):
    """Render index-backed rows respecting the gf flag bundle:
      -l files-only          → one line per unique file path
      -L files-without-match → routed through fallback (needs file universe)
      -c count               → `path: N` per file
      -v invert              → printed in caller (needs a full entity
                               universe); for now we honor it as a no-op
                               on the indexed path
      default                → `path:line  [src linkage]  concept` per row
    """
    if gf["invert"] or gf["files_without_match"]:
        # Both -v and -L need a complete file universe to subtract matches
        # from. The indexed path only sees matched rows, so we can't
        # express either honestly. Punt to the rg/grep fallback.
        flag_name = "-L (files-without-match)" if gf["files_without_match"] else "-v (invert)"
        console.print(
            f"[yellow]{flag_name} is not implemented on the indexed path; "
            "drop --no-fallback to use rg's equivalent.[/]"
        )
        return
    if gf["files_only"]:
        seen: list[str] = []
        seen_set: set[str] = set()
        for r in rows:
            loc = r["path"] or r["entity"]
            if loc and loc not in seen_set:
                seen_set.add(loc)
                seen.append(loc)
                if len(seen) >= limit:
                    break
        for loc in seen:
            click.echo(loc)
        return
    if gf["count"]:
        from collections import Counter
        c: Counter = Counter()
        for r in rows:
            loc = r["path"] or r["entity"]
            if loc:
                c[loc] += 1
        for loc, n in c.most_common(limit):
            click.echo(f"{loc}: {n}")
        return
    # Default rendering — file:line  [src linkage]  concept
    for r in rows:
        loc = r["path"] or r["entity"]
        line = f":{r['line']}" if r["line"] is not None else ""
        click.echo(
            f"{loc}{line}  [{source_tag} {r['linkage']}]  {r['concept']}"
        )


def _is_stdin_piped() -> bool:
    """True if stdin has bytes ready (true pipe input). False for a
    tty, for a closed-or-empty pipe (Bash tool invocations), or for
    /dev/null. select() with timeout=0 peeks without blocking."""
    import sys as _sys
    if _sys.stdin.isatty():
        return False
    try:
        import select as _select
        ready, _, _ = _select.select([_sys.stdin], [], [], 0)
        if not ready:
            return False
        # On macOS, regular files always show ready in select(); check
        # the fstat to differentiate a fed-pipe from /dev/null.
        import os as _os
        import stat as _stat
        st = _os.fstat(_sys.stdin.fileno())
        if _stat.S_ISFIFO(st.st_mode):
            return True
        if _stat.S_ISREG(st.st_mode):
            return st.st_size > 0
        return False
    except Exception:
        return False


def _grep_stdin(pattern: str, regex: bool, gf: dict, limit: int) -> None:
    """Pipe-mode grep: search lines from sys.stdin, ignore the index.
    Honors -i / -I / -w / -l / -c / -v / -F / -E from the flag bundle."""
    import re as _re
    import sys as _sys
    if regex:
        rx_pattern = pattern
    else:
        rx_pattern = _re.escape(pattern)
    if gf["word"]:
        rx_pattern = rf"\b{rx_pattern}\b"
    flags_re = _re.IGNORECASE if gf["ignore_case"] is not False else 0
    try:
        rx = _re.compile(rx_pattern, flags_re)
    except _re.error as exc:
        raise click.ClickException(f"invalid regex: {exc}")
    matched = 0
    total = 0
    lines_out: list[tuple[int, str]] = []
    for n, raw in enumerate(_sys.stdin, start=1):
        line = raw.rstrip("\n")
        hit = bool(rx.search(line))
        if gf["invert"]:
            hit = not hit
        if not hit:
            continue
        total += 1
        if matched < limit:
            lines_out.append((n, line))
            matched += 1
    if gf["count"]:
        click.echo(str(total))
        return
    if gf["files_only"]:
        # `<stdin>` is the one file; emit once if any match.
        if lines_out:
            click.echo("<stdin>")
        return
    for n, line in lines_out:
        click.echo(f"<stdin>:{n}:{line}")


def _filter_rows_by_paths(rows: list[dict], paths: tuple) -> list[dict]:
    """Keep only index rows whose `path` lies under any of the given paths."""
    if not paths:
        return rows
    resolved = [Path(p).resolve() for p in paths]
    out: list[dict] = []
    for r in rows:
        rp = r.get("path")
        if not rp:
            continue
        try:
            rp_abs = Path(rp).resolve()
        except (OSError, ValueError):
            continue
        if any(rp_abs == base or rp_abs.is_relative_to(base) for base in resolved):
            out.append(r)
    return out


@main.command()
@click.argument("pattern")
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option("--regex/--substring", default=False,
              help="Treat PATTERN as a regex matched against concept names. "
                   "Default is case-insensitive substring.")
@click.option("--flags", "-f", "flags", default=None, help=_GREP_FLAGS_HELP)
@click.option("--linkage", default=None,
              help="Restrict to one linkage type (e.g. defines, mentions).")
@click.option("--kind", "-k", type=click.Choice(["doc", "code"]), default=None,
              help="Restrict to entities of this kind.")
@click.option("--limit", default=100, type=int,
              help="Cap the number of result rows (or files in -l mode).")
@click.option("--fallback/--no-fallback", default=True,
              help="Fall through to `rg` (then `grep -rn`) when the indexed "
                   "lookup returns zero matches.")
@click.option("--learn/--no-learn", default=True,
              help="When fallback finds hits, fold them into the index as a "
                   "`query/PATTERN` concept so future searches hit the index.")
@click.option("--via-replica", is_flag=True,
              help="Read from the rotation reader slot instead of the daemon. "
                   "Lock-free; default ON when the replica file exists. "
                   "Skips --learn (writes need the daemon).")
def grep(pattern, paths, regex, flags, linkage, kind, limit, fallback, learn, via_replica):
    """Index-backed grep: find concepts whose name matches PATTERN and
    print file:line for every recorded reference. Falls back to `rg` /
    `grep -rn` under the project root when the index has no hits.

    PATHS (optional, variadic) restrict both the indexed-row filter and the
    fall-through grep target. Pipe data into stdin to bypass the index
    entirely and grep the pipe.

        rmx grep "daemon" src/refmatrix/        # only entities under src/
        rmx grep "daemon" src/ tests/           # multiple targets
        rg -l TODO | rmx grep "FIXME"           # pipe mode (no index)

    Grep-style flags can be passed as a quoted bundle via --flags / -f:

        rmx grep -f '-i -l'   "daemon"      # case-insens, files only
        rmx grep -f '-inl'    "Daemon"      # same, bundled letters
        rmx grep -f '-c'      "linkage"     # count per file
        rmx grep -f '-v'      "noise"       # entities/files with NO match
    """
    import sys as _sys
    gf = _parse_grep_flags(flags)
    # --regex/--substring is the canonical control; -F / -E in --flags can
    # override it for convenience.
    if gf["force_substring"]:
        regex = False
    if gf["force_regex"]:
        regex = True

    # Stdin mode: data piped in → grep the pipe, ignore the index entirely.
    # isatty() alone is not enough -- subprocess invocations (Bash tool,
    # post-commit hooks) have a non-tty stdin even when no data is being
    # piped, which used to silently swallow the request. Peek with select
    # to confirm there is actually a byte ready before switching modes.
    if _is_stdin_piped():
        _grep_stdin(pattern, regex, gf, limit)
        return

    # Word-boundary wrapping when regex mode is on.
    effective_pattern = pattern
    if gf["word"] and regex:
        effective_pattern = rf"\b{pattern}\b"
    from refmatrix import daemon as daemon_mod
    root = _root()
    via_replica = _should_via_replica(via_replica)
    if via_replica:
        # Read-only replica path. Skip the daemon entirely so a busy
        # writer can't make us wait. `--learn` is implicitly disabled
        # because writes require the daemon's write connection.
        if learn:
            console.print("[dim]learn=off under --via-replica (read-only).[/]")
            learn = False

        def _run(s):
            with log_query(s, kind="grep", body=pattern,
                           source="grep-replica") as _tlog:
                _grep_run_direct(
                    s, pattern, effective_pattern, regex,
                    linkage, kind, limit, fallback, learn, gf, paths, _tlog,
                )
        _replica_read(_run)
        return
    # Read-only Store from the replica reader slot. A read-only attach
    # against the ACTIVE catalog is impossible while the daemon holds it:
    # DuckDB takes an exclusive cross-process lock, so even a read_only
    # open raises `IOException: Could not set lock on file`. So when the
    # daemon is up we use the replica (`_reader_store`, which returns None
    # on a lock conflict / missing replica); `_grep_run` then serves the
    # read over the daemon RPC (`grep_indexed`) and never touches `s`.
    # Only with no daemon do we open the catalog directly via `_store()`.
    s = _reader_store() if daemon_mod.ping(root) else _store()
    with log_query(s, kind="grep", body=pattern, source="grep") as _tlog:
        _grep_run(
            s, root, daemon_mod, pattern, effective_pattern, regex,
            linkage, kind, limit, fallback, learn, gf, paths, _tlog,
        )


def _grep_rg_fallback(*, pattern, regex, gf, limit, paths, _tlog, project_root):
    """Run `rg` then `grep -rn` as a fallback when the index returns
    zero rows. Extracted from `_grep_run` so the replica-read path can
    reuse it without re-implementing the rg/grep arg construction."""
    import shutil
    import subprocess

    targets = [str(p) for p in paths] if paths else [str(project_root)]
    tool = shutil.which("rg")
    if tool:
        case_flag = (
            "-i" if gf["ignore_case"] is True
            else ("-s" if gf["ignore_case"] is False else "-S")
        )
        cmd = ["rg", "-nH", case_flag, "--no-heading"]
        if gf["word"]:
            cmd.append("-w")
        if gf["invert"]:
            cmd.append("-v")
        if gf["count"]:
            cmd.append("-c")
        if gf["files_only"]:
            cmd.append("-l")
        if gf["files_without_match"]:
            cmd.append("--files-without-match")
        cmd += ["--regexp", pattern] + targets
    else:
        tool = shutil.which("grep")
        if not tool:
            raise click.ClickException(
                "no indexed match and neither rg nor grep on PATH"
            )
        g_letters = "rH"
        if not (gf["count"] or gf["files_only"] or gf["files_without_match"]):
            g_letters += "n"
        if gf["ignore_case"] is not False:
            g_letters += "i"
        if gf["word"]:
            g_letters += "w"
        if gf["invert"]:
            g_letters += "v"
        if gf["count"]:
            g_letters += "c"
        if gf["files_only"]:
            g_letters += "l"
        if gf["files_without_match"]:
            g_letters += "L"
        g_letters += "E" if regex else "F"
        cmd = [tool, f"-{g_letters}", pattern] + targets
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not res.stdout.strip():
        _tlog.cardinality = 0
        console.print("[dim]no matches[/]")
        return
    prefix = "[rg] " if tool.endswith("/rg") else "[grep] "
    shown = 0
    if gf["files_only"] or gf["files_without_match"] or gf["count"]:
        for raw in res.stdout.splitlines():
            if shown >= limit:
                break
            click.echo(prefix + raw)
            shown += 1
        _tlog.cardinality = shown
        return
    parsed = 0
    for raw in res.stdout.splitlines():
        if shown < limit:
            click.echo(prefix + raw)
            shown += 1
        parts = raw.split(":", 2)
        if len(parts) >= 2:
            try:
                int(parts[1])
                parsed += 1
            except ValueError:
                pass
    _tlog.cardinality = parsed


def _grep_run_direct(s, pattern, effective_pattern, regex,
                     linkage, kind, limit, fallback, learn, gf, paths, _tlog):
    """Read-only path: no daemon, no _store_lock. Mirrors the SQL the
    daemon's `_op_grep_indexed` runs but against the replica reader
    slot. `--learn` is no-op here (writes need the daemon)."""
    rows: list[dict] = []
    like = f"%{effective_pattern}%"
    sql = (
        "SELECT e.path, e.name, ev.line, lt.name, c.name "
        "FROM linkage_evidence ev "
        "JOIN entities e ON e.id = ev.entity_id "
        "JOIN entities c ON c.id = ev.concept_id "
        "JOIN linkage_types lt ON lt.id = ev.linkage_id "
        "WHERE c.name "
        + ("ILIKE" if not regex else "~") + " ? "
    )
    params: list = [effective_pattern if regex else like]
    if linkage:
        sql += "AND lt.name = ? "
        params.append(linkage)
    if kind:
        sql += "AND e.kind = ? "
        params.append(kind)
    sql += "ORDER BY e.path, ev.line LIMIT ?"
    params.append(limit)
    for r in s._connect().execute(sql, params).fetchall():
        rows.append({"path": r[0], "entity": r[1], "line": r[2],
                     "linkage": r[3], "concept": r[4]})

    if paths:
        rows = _filter_rows_by_paths(rows, paths)

    if rows:
        _tlog.cardinality = len(rows)
        _render_grep_rows(rows, gf, limit, source_tag="idx-replica")
        return

    if not fallback:
        _tlog.cardinality = 0
        console.print("[dim]no indexed matches[/]")
        return

    # Replica path: rg fallback without learn-on-miss (writes need
    # the daemon; user can re-run without --via-replica to learn).
    _grep_rg_fallback(
        pattern=pattern, regex=regex, gf=gf, limit=limit,
        paths=paths, _tlog=_tlog, project_root=Path.cwd(),
    )


def _grep_run(s, root, daemon_mod, pattern, effective_pattern, regex,
              linkage, kind, limit, fallback, learn, gf, paths, _tlog):
    rows: list[dict] = []
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "grep_indexed", {
            "pattern": effective_pattern, "regex": regex,
            "linkage": linkage, "kind": kind, "limit": limit,
        }, timeout=60.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        # Direct path: only used when daemon is down. Mirror the SQL.
        like = f"%{effective_pattern}%"
        sql = (
            "SELECT e.path, e.name, ev.line, lt.name, c.name "
            "FROM linkage_evidence ev "
            "JOIN entities e ON e.id = ev.entity_id "
            "JOIN entities c ON c.id = ev.concept_id "
            "JOIN linkage_types lt ON lt.id = ev.linkage_id "
            "WHERE c.name "
            + ("ILIKE" if not regex else "~") + " ? "
        )
        params: list = [effective_pattern if regex else like]
        if linkage:
            sql += "AND lt.name = ? "
            params.append(linkage)
        if kind:
            sql += "AND e.kind = ? "
            params.append(kind)
        sql += "ORDER BY e.path, ev.line LIMIT ?"
        params.append(limit)
        for r in s._connect().execute(sql, params).fetchall():
            rows.append({"path": r[0], "entity": r[1], "line": r[2],
                         "linkage": r[3], "concept": r[4]})

    # PATHS filter: drop rows whose entity path is outside the given targets.
    if paths:
        rows = _filter_rows_by_paths(rows, paths)

    if rows:
        _tlog.cardinality = len(rows)
        _render_grep_rows(rows, gf, limit, source_tag="idx")
        return

    if not fallback:
        _tlog.cardinality = 0
        console.print("[dim]no indexed matches[/]")
        return

    # Fall through to a real grep. Targets are the given PATHS if any,
    # otherwise the project root (existing behavior).
    import shutil
    import subprocess
    targets = [str(p) for p in paths] if paths else [str(root.parent)]
    tool = shutil.which("rg")
    if tool:
        # rg: -n line numbers, -H force filenames, --no-heading.
        # -S smart-case is overridden when --flags forces case.
        case_flag = (
            "-i" if gf["ignore_case"] is True
            else ("-s" if gf["ignore_case"] is False else "-S")
        )
        rg_cmd = ["rg", "-nH", case_flag, "--no-heading"]
        if gf["word"]:
            rg_cmd.append("-w")
        if gf["invert"]:
            rg_cmd.append("-v")
        if gf["count"]:
            rg_cmd.append("-c")
        if gf["files_only"]:
            rg_cmd.append("-l")
        if gf["files_without_match"]:
            # rg uses long form for files-without-match.
            rg_cmd.append("--files-without-match")
        rg_cmd += ["--regexp", pattern] + targets
        cmd = rg_cmd
    else:
        tool = shutil.which("grep")
        if not tool:
            raise click.ClickException("no indexed match and neither rg nor grep on PATH")
        # Build grep flags from gf bundle. Always recursive + filename.
        g_letters = "rH"
        if not (gf["count"] or gf["files_only"] or gf["files_without_match"]):
            g_letters += "n"
        if gf["ignore_case"] is not False:
            g_letters += "i"
        if gf["word"]:
            g_letters += "w"
        if gf["invert"]:
            g_letters += "v"
        if gf["count"]:
            g_letters += "c"
        if gf["files_only"]:
            g_letters += "l"
        if gf["files_without_match"]:
            g_letters += "L"
        g_letters += "E" if regex else "F"
        cmd = [tool, f"-{g_letters}", pattern] + targets
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not res.stdout.strip():
        _tlog.cardinality = 0
        console.print("[dim]no matches[/]")
        return
    prefix = "[rg] " if tool.endswith("/rg") else "[grep] "
    # In -l (files-only) / -L (files-without-match) mode tool emits bare
    # paths; in -c (count) mode it emits `path:N`. Skip the line-number
    # parsing for those.
    if gf["files_only"] or gf["files_without_match"] or gf["count"]:
        shown = 0
        for raw in res.stdout.splitlines():
            if shown >= limit:
                break
            click.echo(prefix + raw)
            shown += 1
        _tlog.cardinality = shown
        return
    # Default rendering: rg --no-heading / grep -H emit `path:line:rest`.
    parsed_hits: list[dict] = []
    shown = 0
    for raw in res.stdout.splitlines():
        if shown < limit:
            click.echo(prefix + raw)
            shown += 1
        parts = raw.split(":", 2)
        if len(parts) >= 2:
            try:
                line_no = int(parts[1])
            except ValueError:
                continue
            parsed_hits.append({"file": parts[0], "line": line_no})
    _tlog.cardinality = len(parsed_hits)

    if learn and parsed_hits and daemon_mod.ping(root):
        resp = daemon_mod.call(root, "learn_from_grep", {
            "pattern": pattern,
            "hits": parsed_hits,
            "project_root": str(root.parent),
        }, timeout=60.0)
        if resp.get("ok"):
            r = resp["result"]
            console.print(
                f"[dim]learned: concept '{r['concept']}' "
                f"with {r['added']} file(s) — future searches hit the index[/]"
            )


# ---- saved queries --------------------------------------------------------


@main.command("save-query")
@click.argument("name")
@click.argument("body")
def save_query(name, body):
    """Persist a named query."""
    s = _store()
    s.save_query(name, body)
    console.print(f"[green]saved[/] {name}")


@main.command()
@click.argument("name")
@click.option("--pql", "is_pql", is_flag=True)
@click.option("--ids-only", is_flag=True)
@click.option("--limit", default=50, type=int)
def run(name, is_pql, ids_only, limit):
    """Run a saved query by name."""
    s = _store()
    body = s.get_saved_query(name)
    if body is None:
        raise click.ClickException(f"no saved query: {name}")
    qe = QueryEngine(s)
    result = qe.run_pql(body) if is_pql else qe.run(body)
    if isinstance(result, list):
        for eid, w in result:
            e = s.get_entity_by_id(eid)
            print(f"{e.name if e else eid}\t{w}")
        return
    if ids_only:
        for eid in result:
            print(eid)
        return
    _print_bitmap(s, result, limit=limit)


@list_grp.command("queries")
def list_queries():
    """List saved queries."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    t = Table("name", "body")
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "list_saved_queries", {})
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        rows = list(_store().list_saved_queries())
    for n, b in rows:
        t.add_row(n, b)
    console.print(t)


main.add_command(_alias(list_queries, "list-queries"))


# ---- stats / export -------------------------------------------------------


@main.command()
@click.option("--stale", is_flag=True,
              help="Also list tracked files where on-disk mtime > last_synced.")
@click.option("--via-replica", is_flag=True,
              help="Read from the rotation reader slot instead of the daemon. "
                   "Lock-free; sees stale-by-N-seconds data. Incompatible with "
                   "--stale (tracked_files is not refreshed in the replica path).")
def stats(stale, via_replica):
    """Print catalog and bitmap stats."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if via_replica:
        if stale:
            raise click.ClickException("--via-replica and --stale are incompatible")
        s = None  # stale is False here, so the s.stale_files() branch is skipped
        out = _replica_read(lambda st: st.stats())
    elif daemon_mod.ping(root) and not stale:
        # Replica-first read: bypass daemon `_store_lock` so `stats`
        # doesn't queue 60s behind a long-running ingest. Falls back to
        # daemon RPC if replica isn't available.
        try:
            s = _reader_store()
            out = s.stats()
        except click.ClickException:
            resp = daemon_mod.call(root, "stats", {})
            if not resp.get("ok"):
                raise click.ClickException(
                    f"daemon stats failed: {resp.get('error')}"
                )
            out = resp["result"]
            s = None
    else:
        s = _store()
        out = s.stats()
    t1 = Table("kind", "count", title="entities")
    for k, v in out["entities"].items():
        t1.add_row(k, str(v))
    console.print(t1)
    t2 = Table("linkage", "concepts (rows)", "set bits", title="linkages")
    for name, d in out["linkages"].items():
        t2.add_row(name, str(d["concepts"]), str(d["bits"]))
    console.print(t2)
    if stale and s is not None:
        rows = s.stale_files()
        if not rows:
            console.print("[green]no stale files[/]")
            return
        t3 = Table("path", "status", "on-disk mtime", "last_synced",
                   title=f"stale ({len(rows)})")
        for r in rows:
            t3.add_row(r["path"], r["status"], f"{r['mtime']:.2f}",
                       f"{r['last_synced']:.2f}")
        console.print(t3)


@main.command()
@click.option("--since", default=None, help="Filter to records on or after ISO timestamp prefix.")
@click.option("--top-queried", is_flag=True, help="Just show top-queried concept names.")
@click.option("--zero-results", is_flag=True, help="Just show queries that returned 0.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def telemetry(since, top_queried, zero_results, fmt):
    """Summarize the query telemetry log."""
    from refmatrix.telemetry import (
        summarize, top_queried_concepts, zero_result_queries,
    )

    s = _store()

    if top_queried:
        rows = top_queried_concepts(s)
        if fmt == "json":
            click.echo(json.dumps(rows, indent=2))
        else:
            t = Table("concept", "queries")
            for name, n in rows:
                t.add_row(name, str(n))
            console.print(t)
        return
    if zero_results:
        rows = zero_result_queries(s)
        if fmt == "json":
            click.echo(json.dumps(rows, indent=2))
        else:
            t = Table("query", "count")
            for name, n in rows:
                t.add_row(name, str(n))
            console.print(t)
        return

    out = summarize(s, since=since)
    if fmt == "json":
        click.echo(json.dumps(out, indent=2))
        return

    if out["total"] == 0:
        console.print("[yellow]no telemetry records[/]")
        return

    console.print(f"[bold]total queries:[/] {out['total']}")
    console.print(
        f"[bold]latency p50/p95/p99:[/] "
        f"{out['latency_p50_ms']}ms / {out['latency_p95_ms']}ms / {out['latency_p99_ms']}ms"
    )
    console.print(
        f"[bold]zero-result:[/] {out['zero_result_count']} | "
        f"[bold]errors:[/] {out['error_count']}"
    )
    t = Table("kind", "count", title="by kind")
    for k, n in sorted(out["by_kind"].items(), key=lambda kv: -kv[1]):
        t.add_row(k, str(n))
    console.print(t)
    t = Table("body", "count", title="top queries")
    for body, n in out["top_queries"]:
        t.add_row(body[:80], str(n))
    console.print(t)
    if out["zero_result_examples"]:
        console.print("\n[bold]recent zero-result queries:[/]")
        for body in out["zero_result_examples"]:
            console.print(f"  {body}")


@main.command()
@click.option(
    "--keep-backup/--no-keep-backup", default=True,
    help="Keep the pre-compact catalog as <slot>.bloat for safety.",
)
def compact(keep_backup: bool):
    """Compact the writer-slot catalog via EXPORT/IMPORT round-trip.

    DuckDB doesn't reclaim space from deleted rows or churn — the data file
    keeps growing until you re-import. This stops the daemon, EXPORTs the
    writer-slot database as PARQUET, IMPORTs into a fresh file, swaps it
    in, and restarts the daemon. Typical reduction: 3-4x on a churn-heavy
    catalog.

    Rotation-aware (0.3.8+): operates on whichever slot is the current
    writer (catalog.A.duckdb or catalog.B.duckdb) per the `active`
    marker. Falls back to legacy catalog.duckdb if the rotation hasn't
    been bootstrapped. The inactive slot is left untouched and will be
    refreshed by the daemon on its next rotation cycle."""
    from refmatrix import daemon as daemon_mod
    import shutil
    import duckdb as _duckdb

    root = _root()
    # Determine the current writer slot. The daemon's `active` marker
    # is the authoritative pointer; if missing, fall back to the legacy
    # single-file path.
    marker = root / "active"
    if marker.exists():
        try:
            slot = marker.read_text().strip()
        except OSError:
            slot = "A"
        if slot not in ("A", "B"):
            slot = "A"
        src = root / f"catalog.{slot}.duckdb"
    else:
        slot = None
        src = root / "catalog.duckdb"
    if not src.exists():
        raise click.ClickException(f"no catalog at {src}")

    # Stop daemon so we can hold the write lock ourselves.
    daemon_was_up = daemon_mod.ping(root)
    if daemon_was_up:
        if not daemon_mod.stop_daemon(root):
            raise click.ClickException("daemon did not stop within timeout")

    export_dir = root / "catalog-export"
    new_path = src.with_suffix(".new.duckdb")
    backup = src.with_suffix(".duckdb.bloat")

    if export_dir.exists():
        shutil.rmtree(export_dir)
    if new_path.exists():
        new_path.unlink()

    try:
        before = src.stat().st_size
        console.print(f"[dim]exporting (was {before / 1024 / 1024:.1f} MB)…[/]")
        con = _duckdb.connect(str(src))
        con.execute(f"EXPORT DATABASE '{export_dir}' (FORMAT PARQUET)")
        con.close()

        console.print("[dim]importing into fresh catalog…[/]")
        ncon = _duckdb.connect(str(new_path))
        ncon.execute(f"IMPORT DATABASE '{export_dir}'")
        ncon.execute("CHECKPOINT")
        ncon.close()

        # Atomic-ish swap.
        if backup.exists():
            backup.unlink()
        src.rename(backup)
        new_path.rename(src)
        after = src.stat().st_size

        if not keep_backup:
            backup.unlink()
        shutil.rmtree(export_dir, ignore_errors=True)

        # Remove the legacy `catalog.duckdb` once rotation is in use.
        # Leaving it behind is dangerous: `_bootstrap_rotation_if_needed`
        # treats it as the source-of-truth seed if either slot is later
        # missing, and would overwrite the compacted writer with the
        # stale pre-rotation snapshot. The rotation slots are the new
        # source of truth.
        if slot is not None:
            legacy = root / "catalog.duckdb"
            if legacy.exists():
                if keep_backup:
                    legacy_backup = root / "catalog.duckdb.legacy-bloat"
                    if legacy_backup.exists():
                        legacy_backup.unlink()
                    legacy.rename(legacy_backup)
                    console.print(
                        f"  legacy pre-rotation catalog moved to "
                        f"{legacy_backup}"
                    )
                else:
                    legacy.unlink()

        console.print(
            f"[green]compacted[/] {before / 1024 / 1024:.1f} MB → "
            f"{after / 1024 / 1024:.1f} MB "
            f"({100 * (1 - after / before):.0f}% smaller)"
        )
        if keep_backup:
            console.print(f"  pre-compact backup: {backup}")
    finally:
        if daemon_was_up:
            daemon_mod.spawn_daemon(root, partition=_resolve_partition())


@main.command()
def checkpoint():
    """DuckDB CHECKPOINT: flush WAL and compact the catalog file. Run after
    big churn to shrink `.refmatrix/catalog.duckdb`."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "checkpoint requires a running daemon (only it holds the catalog open)"
        )
    resp = daemon_mod.call(root, "checkpoint", {}, timeout=120.0)
    if not resp.get("ok"):
        raise click.ClickException(f"daemon checkpoint failed: {resp.get('error')}")
    console.print("[green]checkpointed[/]")


@main.command()
def vacuum():
    """Drop empty concepts and tracked files that no longer exist."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "vacuum", {}, timeout=300.0)
        if not resp.get("ok"):
            raise click.ClickException(f"daemon vacuum failed: {resp.get('error')}")
        out = resp["result"]
    else:
        out = _store().vacuum()
    console.print(
        f"[green]vacuumed[/] dropped {out['concepts_dropped']} empty concepts, "
        f"purged {out['files_purged']} missing files"
    )


@main.command("prune-noise")
@click.option("--namespace", "-n", multiple=True, default=("keyword",),
              help="Namespaces to filter (default: keyword).")
@click.option("--min-df", default=2, type=int,
              help="Mark concepts with document-frequency below this.")
@click.option("--max-df-ratio", default=0.25, type=float,
              help="Mark concepts whose DF/total > this ratio.")
@click.option("--drop", is_flag=True,
              help="Actually delete marked concepts instead of just flagging "
                   "them. Default is non-destructive: queries hide noise but "
                   "--full restores the raw graph.")
def prune_noise(namespace, min_df, max_df_ratio, drop):
    """Mark (or with --drop, delete) noisy auto-generated concepts.

    Default behavior is non-destructive — concepts are flagged so queries can
    hide them by default, while `--full` on query/neighbors/co-occur/primer/
    scan-prompt restores the full graph for find/grep-style use. Protected
    concepts (added via add-entity/add-concept/link) are never touched.
    """
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "prune_noise", {
            "namespaces": list(namespace),
            "min_df": min_df,
            "max_df_ratio": max_df_ratio,
            "drop": drop,
        }, timeout=300.0)
        if not resp.get("ok"):
            raise click.ClickException(
                f"daemon prune_noise failed: {resp.get('error')}"
            )
        out = resp["result"]
    else:
        s = _store()
        out = s.prune_noise(
            namespaces=tuple(namespace), min_df=min_df,
            max_df_ratio=max_df_ratio, drop=drop,
        )
    if drop:
        console.print(
            f"[green]dropped[/] {out['dropped']} concepts "
            f"(kept {out['kept']} of {out['total_seen']} in "
            f"{','.join(namespace)} namespaces) | "
            f"min_df={out['min_df']} max_df={out['max_df']}"
        )
    else:
        console.print(
            f"[green]marked[/] {out['marked']} noise / "
            f"[yellow]unmarked[/] {out['unmarked']} "
            f"(kept {out['kept']} of {out['total_seen']} in "
            f"{','.join(namespace)} namespaces) | "
            f"min_df={out['min_df']} max_df={out['max_df']} | "
            f"queries hide these by default; pass --full to include"
        )


@main.command()
@click.option("--out", "-o", type=click.Path(path_type=Path), required=True)
def export(out):
    """Export the entire matrix as a single JSON file (entities, linkages, bitmaps)."""
    s = _store()
    payload: dict = {
        "version": __version__,
        "entities": [
            {"id": e.id, "kind": e.kind, "name": e.name, "path": e.path,
             "tldr": e.tldr, "meta": e.meta,
             "protected": e.protected, "noise": e.noise}
            for e in s.iter_entities()
        ],
        "linkage_types": s.list_linkages(),
        "bitmaps": {},
    }
    for lk in s.list_linkages():
        ln = lk["name"]
        payload["bitmaps"][ln] = {
            str(cid): list(s.load_bitmap(ln, cid))
            for cid in s.iter_concept_ids_for_linkage(ln)
        }
    Path(out).write_text(json.dumps(payload, indent=2))
    console.print(f"[green]exported[/] {out}")


@main.command("import")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--merge", is_flag=True, help="Merge into existing matrix instead of failing on conflicts.")
def import_(path, merge):
    """Import a JSON dump produced by `rmx export`."""
    s = _store()
    payload = json.loads(Path(path).read_text())
    id_remap: dict[int, int] = {}
    for e in payload["entities"]:
        new_id = s.upsert_entity(
            kind=e["kind"], name=e["name"], path=e.get("path"),
            tldr=e.get("tldr"), meta=e.get("meta"),
            protected=bool(e.get("protected", False)),
        )
        if e.get("noise"):
            s._connect().execute(
                "UPDATE entities SET noise=1 WHERE id=?", (new_id,)
            )
        id_remap[e["id"]] = new_id
    s._connect().commit()
    for lk in payload.get("linkage_types", []):
        s.add_linkage_type(name=lk["name"], directed=bool(lk["directed"]),
                           description=lk.get("description"))
    for ln, rows in payload.get("bitmaps", {}).items():
        for old_cid, eids in rows.items():
            new_cid = id_remap.get(int(old_cid))
            if new_cid is None:
                continue
            new_eids = [id_remap[e] for e in eids if e in id_remap]
            s.link_many(ln, new_cid, new_eids)
    console.print(f"[green]imported[/] {path}")


# ---- ingestion ------------------------------------------------------------


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--source",
              type=click.Choice(["auto", "metadata", "tldr", "tree", "graphify"]),
              default="auto",
              help="auto picks metadata > tldr > tree (with graphify layered "
                   "additively if graphify-out/graph.json exists). metadata "
                   "reads llm-tldr's per-unit semantic dump for the richest "
                   "graph; tldr falls back to call_graph.json; graphify forces "
                   "the knowledge-graph JSON to be the only ingest.")
@click.option("--semantic", is_flag=True,
              help="Also extract Python imports + docstring keywords (slow on big trees).")
def ingest(path, source, semantic):
    """Ingest a directory. Prefers .tldr/cache/semantic/metadata.json when present."""
    from refmatrix import daemon as daemon_mod
    from refmatrix.ingest import ingest_path

    root = _root()
    resolved = Path(path).resolve()
    if daemon_mod.ping(root):
        # Route through the daemon so the catalog write lock stays single-
        # owner. Long ingests can run minutes — give the socket headroom.
        resp = daemon_mod.call(root, "ingest_path", {
            "path": str(resolved),
            "source": source,
            "semantic": semantic,
        }, timeout=24 * 3600.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        n = resp["result"]["entities"]
    else:
        s = _store()
        n = ingest_path(s, resolved, source=source, semantic=semantic)
    console.print(f"[green]ingested[/] {n} entities from {path}")


@main.command("tldr-warm")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--tldr-bin", default=None, type=click.Path(path_type=Path),
              help="Path to llm-tldr's `tldr` binary. Default: search PATH "
                   "(env REFMATRIX_TLDR_BIN also honored).")
@click.option("--semantic", is_flag=True,
              help="Also run Python semantic enrichment after warm.")
@click.option("--lang", default=None,
              help="Restrict tldr warm to a language (e.g. python).")
def tldr_warm(path, tldr_bin, semantic, lang):
    """Run `tldr warm <path>`, then ingest the resulting call graph into rmx.

    Single-step UX so you don't have to remember both tools — the rmx ingest
    runs in tldr-mode against the freshly-built `.tldr/cache/call_graph.json`.
    """
    import shutil
    import subprocess

    from refmatrix.ingest import ingest_path

    s = _store()
    proj = Path(path).resolve()

    binpath = (
        str(tldr_bin)
        if tldr_bin
        else os.environ.get("REFMATRIX_TLDR_BIN")
        or shutil.which("tldr")
    )
    if not binpath:
        raise click.ClickException(
            "no `tldr` binary on PATH. Install llm-tldr (`pip install llm-tldr`) "
            "or pass --tldr-bin /path/to/tldr."
        )

    cmd: list[str] = [binpath, "warm", str(proj)]
    if lang:
        cmd += ["--lang", lang]
    console.print(f"[dim]$ {' '.join(cmd)}[/]")
    rv = subprocess.run(cmd)
    if rv.returncode != 0:
        raise click.ClickException(f"`tldr warm` failed (rc={rv.returncode})")

    cache = proj / ".tldr" / "cache" / "call_graph.json"
    if not cache.exists():
        console.print(
            f"[yellow]warning:[/] expected {cache} after warm; "
            "this may not be llm-tldr (the tldr-pages tool also ships as `tldr`). "
            "Pass --tldr-bin to point at llm-tldr."
        )

    n = ingest_path(s, proj, source="tldr", semantic=semantic)
    console.print(f"[green]ingested[/] {n} entities from {proj}")


@main.command("graphify-warm")
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--graphify-bin", default=None, type=click.Path(path_type=Path),
              help="Path to the `graphify` binary. Default: search PATH "
                   "(env REFMATRIX_GRAPHIFY_BIN also honored).")
@click.option("--mode", type=click.Choice(["fast", "deep"]), default=None,
              help="Pass --mode to graphify (deep = richer INFERRED edges).")
@click.option("--update", is_flag=True,
              help="Pass --update to graphify for incremental re-extract.")
def graphify_warm(path, graphify_bin, mode, update):
    """Run `graphify <path>`, then ingest the resulting graph.json into rmx.

    Mirrors `rmx tldr-warm` — single-step UX so you don't have to drive both
    tools. The rmx ingest runs against the freshly-built
    `graphify-out/graph.json`. Graphify edges (rationale_for,
    semantically_similar_to, conceptually_related_to, etc.) layer additively
    on top of any existing tldr-derived index.
    """
    import shutil
    import subprocess

    from refmatrix.ingest import ingest_path

    s = _store()
    proj = Path(path).resolve()

    binpath = (
        str(graphify_bin)
        if graphify_bin
        else os.environ.get("REFMATRIX_GRAPHIFY_BIN")
        or shutil.which("graphify")
    )
    if not binpath:
        raise click.ClickException(
            "no `graphify` binary on PATH. Install it or pass "
            "--graphify-bin /path/to/graphify."
        )

    cmd: list[str] = [binpath, str(proj)]
    if mode:
        cmd += ["--mode", mode]
    if update:
        cmd += ["--update"]
    console.print(f"[dim]$ {' '.join(cmd)}[/]")
    rv = subprocess.run(cmd)
    if rv.returncode != 0:
        raise click.ClickException(f"`graphify` failed (rc={rv.returncode})")

    cache = proj / "graphify-out" / "graph.json"
    if not cache.exists():
        raise click.ClickException(
            f"expected {cache} after graphify run; not found."
        )

    n = ingest_path(s, proj, source="graphify")
    console.print(f"[green]ingested[/] {n} graphify edges from {proj}")


# ---- incremental sync -----------------------------------------------------


@main.command()
@click.option("--files", "-f", multiple=True, type=click.Path(path_type=Path),
              help="Specific files to (re)ingest. Repeat or use shell glob.")
@click.option("--since", default=None, help="Sync paths changed since this git ref.")
@click.option("--flush-queue", is_flag=True,
              help="Drain .refmatrix/dirty.queue (populated by hooks).")
@click.option("--invalidate", "-i", multiple=True, type=click.Path(path_type=Path),
              help="Force-purge these paths regardless of existence.")
@click.option("--project-root", type=click.Path(path_type=Path), default=None,
              help="Project root for relative resolution (default: cwd).")
@click.option("--semantic", is_flag=True,
              help="Re-run Python semantic enrichment for touched files.")
@click.option("--enqueue-only", is_flag=True,
              help="Just append paths to dirty.queue and return; don't sync.")
@click.option("--async", "async_flag", is_flag=True,
              help="Fire-and-forget: hand the flush to the daemon and return "
                   "immediately. Hook-friendly. No-op without a running daemon.")
def sync(files, since, flush_queue, invalidate, project_root, semantic,
         enqueue_only, async_flag):
    """Incrementally update the matrix for given files / git changes / queued paths."""
    from refmatrix import sync as syncmod

    # --enqueue-only is the hottest hook path (fires on every Edit/Write).
    # Don't open the DuckDB catalog just to append to a text queue file —
    # that triggers a write-lock acquisition that contends with concurrent
    # rmx invocations from other hooks.
    if enqueue_only:
        if not files:
            raise click.ClickException("--enqueue-only requires --files")
        root = _root()
        if not root.is_dir():
            # No .refmatrix in this tree — nothing to enqueue against. Treat
            # as a silent no-op so hook callers don't fail when they fire on
            # edits outside any indexed project.
            return
        syncmod.enqueue(root, [str(p) for p in files])
        console.print(f"[green]enqueued[/] {len(files)} paths")
        return

    # Try the daemon for sync paths first — it holds the Store open across
    # many calls so we skip DuckDB lock acquisition. Falls back to
    # in-process when no daemon is running.
    if (flush_queue
            or (files and not since and not invalidate)
            or (since and not invalidate)):
        from refmatrix import daemon as daemon_mod
        root = _root()
        if daemon_mod.ping(root):
            proot = (project_root or Path.cwd()).resolve()
            args: dict = {"project_root": str(proot), "semantic": semantic}
            if async_flag and flush_queue:
                op = "flush_queue_async"
            elif flush_queue:
                op = "flush_queue"
            elif since:
                op = "sync_since"
                args["git_ref"] = since
            else:
                op = "sync_files"
                args["files"] = [str(p) for p in files]
            # `--since` over a big diff can take real time; bump the client
            # socket timeout to match. Async path stays sub-second.
            timeout = 60.0 if op == "flush_queue_async" else 600.0
            resp = daemon_mod.call(root, op, args, timeout=timeout)
            if not resp.get("ok"):
                raise click.ClickException(
                    f"daemon {op} failed: {resp.get('error')}"
                )
            r = resp["result"]
            if op == "flush_queue_async":
                tag = "queued" if r.get("queued") else "coalesced"
                console.print(f"[green]flush {tag}[/] [daemon]")
            else:
                console.print(
                    f"[green]synced[/] +{r['added']} ~{r['updated']} "
                    f"-{r['purged']} (touched={r['touched']}) [daemon]"
                )
            return
        # Daemon-managed store but the daemon isn't reachable (down or
        # restarting). Do NOT open the catalog directly — a direct write
        # grabs the exclusive lock and can block the daemon from starting
        # (the deadlock where a post-commit `rmx sync` raced a daemon
        # restart and held catalog.duckdb, crash-looping the daemon).
        # Enqueue the work instead; the daemon drains dirty.queue on its
        # next start / refresh tick.
        from refmatrix import launchctl as _lc
        if _lc.is_installed(root):
            if flush_queue:
                console.print(
                    "[yellow]daemon down[/] — queued paths will flush when "
                    "the daemon restarts"
                )
                return
            proot = (project_root or Path.cwd()).resolve()
            try:
                paths = ([str(p) for p in files] if files
                         else [str(p) for p in syncmod.changed_since(proot, since)])
            except RuntimeError as e:
                raise click.ClickException(str(e))
            if paths:
                syncmod.enqueue(root, paths)
            console.print(
                f"[yellow]daemon down[/] — enqueued {len(paths)} paths for "
                f"the daemon (no direct catalog write)"
            )
            return
        if async_flag and flush_queue:
            # --async only buys you the daemon's fire-and-forget. Without a
            # daemon (and not a daemon-managed store), fall through to the
            # in-process synchronous flush — at least the work gets done.
            pass

    s = _store()
    proot = (project_root or Path.cwd()).resolve()

    for p in invalidate:
        s.purge_path(str(Path(p).resolve()))
    if invalidate:
        console.print(f"[yellow]purged[/] {len(invalidate)} paths")

    if since:
        report = syncmod.sync_since(s, since, project_root=proot, semantic=semantic)
    elif flush_queue:
        # Single-flight: hook setups commonly fire `rmx sync --flush-queue`
        # from Stop, SubagentStop, SessionStart, etc. With the DuckDB
        # backend each invocation needs an exclusive write lock on
        # catalog.duckdb, so concurrent invocations pile up. The queue is
        # shared anyway — if another flush is already running it will drain
        # whatever this call would have. Skip the duplicate silently.
        import fcntl
        lock_path = s.root / "flush.lock"
        with lock_path.open("w") as lockf:
            try:
                fcntl.flock(lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                console.print("[dim]flush already running — skipping[/]")
                return
            report = syncmod.flush_queue(
                s, project_root=proot, semantic=semantic,
            )
    elif files:
        report = syncmod.sync_files(s, [str(p) for p in files],
                                    project_root=proot, semantic=semantic)
    else:
        if not invalidate:
            raise click.ClickException(
                "give one of --files / --since / --flush-queue / --invalidate")
        report = {"added": 0, "updated": 0, "purged": len(invalidate), "touched": 0}

    console.print(
        f"[green]synced[/] +{report['added']} ~{report['updated']} "
        f"-{report['purged']} (touched={report['touched']})"
    )


@main.command("queue")
def queue_cmd():
    """Show pending paths in the dirty queue."""
    s = _store()
    q = s.root / "dirty.queue"
    if not q.exists():
        console.print("[dim]queue is empty[/]")
        return
    for line in q.read_text().splitlines():
        if line.strip():
            console.print(line)


@main.group()
def replica():
    """Read-replica rotation management.

    The daemon maintains two persistent catalog files —
    catalog.A.duckdb + catalog.B.duckdb — and an `active` marker that
    names the current writer slot. Reads can be served by the frozen
    inactive slot without contending on the writer's lock. Every
    RMX_REPLICA_REFRESH_S seconds (default 5) the inactive slot is
    caught up to the writer's state and the marker swaps, demoting the
    old writer to reader. DuckDB backend only."""


@replica.command("status")
def replica_status():
    """Show rotation state: writer + reader slots, file sizes, freshness."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "daemon not running — replica is daemon-managed"
        )
    resp = daemon_mod.call(root, "replica_status", {}, timeout=10.0)
    if not resp.get("ok"):
        raise click.ClickException(resp.get("error", "daemon error"))
    r = resp["result"]
    if not r.get("enabled"):
        console.print("[yellow]replica disabled[/] (non-duckdb backend)")
        return
    console.print(f"[bold]writer slot:[/] {r['writer_slot']}  "
                  f"-> {r['writer_path']}")
    console.print(f"[bold]reader slot:[/] {r['reader_slot']}  "
                  f"-> {r['reader_path']}")
    console.print(
        f"[bold]A:[/] exists={r['a_exists']} "
        f"size={r['a_size']:,}    "
        f"[bold]B:[/] exists={r['b_exists']} "
        f"size={r['b_size']:,}"
    )
    console.print(
        f"[bold]refresh thread:[/] "
        f"{'[green]running[/]' if r['refresh_thread'] else '[red]stopped[/]'}"
    )
    last = r.get("last")
    if last:
        console.print(
            f"[bold]last refresh:[/] {last.get('refreshed_at', '?')} "
            f"({last.get('elapsed_ms', '?')} ms, "
            f"ok={last.get('ok', False)})"
        )
        if last.get("error"):
            console.print(f"[red]error:[/] {last['error']}")
    else:
        console.print("[dim]no refresh recorded yet[/]")


@replica.command("refresh")
def replica_refresh():
    """Force an immediate catch-up + slot swap. Returns size + latency."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "daemon not running — replica is daemon-managed"
        )
    resp = daemon_mod.call(root, "replica_refresh", {}, timeout=120.0)
    if not resp.get("ok"):
        raise click.ClickException(resp.get("error", "daemon error"))
    r = resp["result"]
    if not r.get("enabled"):
        console.print("[yellow]replica disabled[/] (non-duckdb backend)")
        return
    if not r.get("ok"):
        raise click.ClickException(f"replica refresh failed: {r.get('error')}")
    mode = r.get("mode", "delta")
    applied = r.get("applied", 0)
    size = r.get("size_bytes")
    size_str = f", size={size:,} bytes" if size else ""
    console.print(
        f"[green]swapped[/] writer -> slot {r['writer_slot']} "
        f"(mode={mode}, applied={applied}, {r['elapsed_ms']} ms{size_str})"
    )


@replica.command("path")
def replica_path():
    """Print the absolute path of the *reader* slot file. CLI tools that
    want a lock-free read can open this file in read-only DuckDB mode.

    The reader slot may change after the next refresh (every
    RMX_REPLICA_REFRESH_S seconds, default 5); re-call this command if
    you need the current path."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "replica_status", {}, timeout=5.0)
        if resp.get("ok") and resp["result"].get("enabled"):
            print(resp["result"]["reader_path"])
            return
    # Daemon down — fall back to inferring from the active marker.
    marker = root / "active"
    active = marker.read_text().strip() if marker.exists() else "A"
    inactive = "B" if active == "A" else "A"
    print(str(root / f"catalog.{inactive}.duckdb"))


@main.group()
def curator():
    """gmd-curator coordination — watcher-populated queue + dispatch
    signals. Wired into SessionStart so Claude knows when the
    documentation graph needs the curator's attention.
    """


@curator.command("status")
@click.option("--drain", is_flag=True,
              help="Empty the queue after reading it. Use from hooks "
                   "that only need to fire once per pending change.")
@click.option("--quiet-when-empty", is_flag=True, default=True,
              help="Print nothing if the queue is empty (default on). "
                   "Useful from SessionStart so the hook is silent on "
                   "fresh repos.")
@click.option("--limit", default=10, type=int,
              help="Cap the path list shown in the summary.")
def curator_status(drain: bool, quiet_when_empty: bool, limit: int):
    """Summarize the curator queue for hook injection.

    Prints a single short paragraph suitable for SessionStart /
    UserPromptSubmit hook stdout so Claude sees pending curator work
    without paging through full file lists.
    """
    import json as _json
    root = _root()
    qpath = root / "curator.queue"
    if not qpath.exists() or qpath.stat().st_size == 0:
        if not quiet_when_empty:
            console.print("curator queue: empty")
        return
    entries: list[dict] = []
    try:
        for line in qpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_json.loads(line))
            except _json.JSONDecodeError:
                continue
    except OSError:
        return
    if not entries:
        if drain:
            try:
                qpath.unlink()
            except OSError:
                pass
        return
    paths = sorted({e.get("path", "") for e in entries if e.get("path")})
    project_root = root.parent
    rels: list[str] = []
    for p in paths:
        try:
            rels.append(str(Path(p).resolve().relative_to(project_root)))
        except ValueError:
            rels.append(p)
    sample = rels[:limit]
    overflow = max(0, len(rels) - limit)
    # Plain stdout — hook surfaces this as additional Claude context.
    click.echo(
        f"curator-queue: {len(rels)} curator-relevant file change(s) since "
        f"last drain. Spawn `gmd-curator` (ingest mode) to cross-link, "
        f"surface drift, and crystallize. Paths: "
        + ", ".join(sample)
        + (f", +{overflow} more" if overflow else "")
    )
    if drain:
        try:
            qpath.unlink()
        except OSError:
            pass


@curator.command("drain")
def curator_drain():
    """Empty the curator queue without printing anything."""
    qpath = _root() / "curator.queue"
    if qpath.exists():
        try:
            qpath.unlink()
            console.print("[green]curator queue drained[/]")
        except OSError as exc:
            raise click.ClickException(f"drain failed: {exc}")
    else:
        console.print("[dim]curator queue already empty[/]")


# ---- weighted ranking -----------------------------------------------------


@main.command()
@click.option("--top", default=150, type=int, help="Number of concepts to include.")
@click.option("--symbol-like/--all", default=True,
              help="Filter to identifier-shaped names (default on).")
@click.option("--exclude-namespace", multiple=True, default=("keyword",),
              help="Drop concepts in these namespaces (default: keyword). "
                   "Note: import/ concepts are kept by default — they're useful "
                   "dependency signal for orientation.")
@click.option("--min-refs", default=2, type=int)
@click.option("--max-tokens", default=2000, type=int)
@click.option("--full", "include_noise", is_flag=True,
              help="Include noise-marked concepts.")
@click.option("--out", "-o", type=click.Path(path_type=Path), default=None,
              help="Write to file instead of stdout. Suggested: .refmatrix/PRIMER.md")
def primer(top, symbol_like, exclude_namespace, min_refs, max_tokens,
           include_noise, out):
    """Density-ranked map of the top-N reference-dense symbols. CLAUDE.md-friendly."""
    from refmatrix.primer import build_primer

    s = _store()
    text = build_primer(
        s,
        top_n=top,
        symbol_like_only=symbol_like,
        exclude_namespaces=tuple(exclude_namespace),
        min_refs=min_refs,
        max_tokens=max_tokens,
        include_noise=include_noise,
    )
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
        console.print(f"[green]wrote[/] {out}")
    else:
        click.echo(text)


@main.command("scan-prompt")
@click.option("--text", default=None, help="Prompt text (else read from stdin).")
@click.option("--max-tokens", default=2000, type=int)
@click.option("--per-concept-tokens", default=600, type=int)
@click.option("--max-concepts", default=5, type=int)
@click.option("--exclude-namespace", multiple=True, default=("keyword",),
              help="Drop noise namespaces (default: keyword). import/ is kept "
                   "so prompts mentioning module names get useful bundles.")
@click.option("--full", "include_noise", is_flag=True,
              help="Include noise-marked concepts when matching.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def scan_prompt_cmd(text, max_tokens, per_concept_tokens, max_concepts,
                    exclude_namespace, include_noise, fmt):
    """Read a prompt; emit context bundles for symbols it mentions.

    Designed for the Claude Code UserPromptSubmit hook. Output goes to stdout,
    which Claude Code injects as additional context for the turn.
    """
    from refmatrix.scan import read_stdin_prompt, scan_prompt

    s = _store()
    prompt = text if text is not None else read_stdin_prompt()
    if not prompt.strip():
        return
    with log_query(s, kind="scan", body=prompt[:200], source="scan-prompt") as tlog:
        out = scan_prompt(
            s, prompt,
            max_tokens=max_tokens,
            per_concept_tokens=per_concept_tokens,
            max_concepts=max_concepts,
            exclude_namespaces=tuple(exclude_namespace),
            include_noise=include_noise,
            fmt=fmt,
        )
        tlog.cardinality = out.count("=== context for") if out else 0
    if out:
        click.echo(out)


@main.command("top")
@click.argument("concept")
@click.option("--type", "linkage", default="mentions")
@click.option("-k", default=10, type=int)
def top(concept, linkage, k):
    """Top-K entities by weight under (linkage, concept)."""
    s = _store()
    e = s.resolve_entity(concept)
    if e is None or e.kind != "concept":
        raise click.ClickException(f"no concept: {concept}")
    with log_query(s, kind="top", body=concept, source="top") as tlog:
        rows = s.top_weighted(linkage, e.id, k=k)
        tlog.cardinality = len(rows)
    t = Table("entity", "kind", "weight")
    for eid, w in rows:
        ent = s.get_entity_by_id(eid)
        t.add_row(ent.name if ent else str(eid), ent.kind if ent else "", f"{w:g}")
    console.print(t)


# ---- hook installation ----------------------------------------------------


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--semantic", is_flag=True, help="Run Python semantic enrichment on each batch.")
@click.option("--debounce", default=500, type=int, help="Debounce window in ms (default 500).")
def watch(path, semantic, debounce):
    """Watch a directory and sync on debounced batches of changes. Ctrl-C to stop."""
    from refmatrix.watch import run_watcher

    s = _store()
    project_root = Path(path).resolve()
    console.print(
        f"[green]watching[/] {project_root} "
        f"(debounce={debounce}ms, semantic={semantic})"
    )
    console.print("[dim]Ctrl-C to stop[/]")

    def on_batch(paths, report):
        console.print(
            f"[cyan]synced[/] {len(paths)} path(s) "
            f"+{report['added']} ~{report['updated']} -{report['purged']}"
        )

    try:
        run_watcher(s, project_root, semantic=semantic,
                    debounce_ms=debounce, on_batch=on_batch)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    console.print("[yellow]watcher stopped[/]")


@main.command("install-hooks")
@click.option("--git/--no-git", default=True, help="Install git hooks.")
@click.option("--claude/--no-claude", default=True, help="Install Claude Code hook config.")
@click.option("--briefing/--no-briefing", default=True,
              help="Write .refmatrix/CLAUDE.md so Claude knows rmx is here.")
@click.option("--apply", is_flag=True,
              help="Actually write files. Without this flag, prints what would happen.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.option("--scope", type=click.Choice(["project", "user"]), default="project",
              help="For Claude hooks: write to .claude/settings.local.json (project) "
                   "or print snippet for ~/.claude/settings.json (user).")
def install_hooks(git, claude, briefing, apply, force, scope):
    """Install or preview hooks that keep refmatrix in sync."""
    from refmatrix.hooks import install

    s = _store()
    project_root = s.root.parent
    plan = install(project_root=project_root, refmatrix_root=s.root,
                   git=git, claude=claude, briefing=briefing, scope=scope,
                   apply=apply, force=force)
    for line in plan:
        console.print(line)


# ---- index repair ---------------------------------------------------------


@main.command("repair-index")
def repair_index():
    """Drop + recreate idx_entity_links_lk_concept to fix DuckDB secondary
    index drift. Daemon does this on every startup; this command is for
    triage when the index drifts mid-session ('Failed to delete all rows
    from index' fatals). Stops the daemon, repairs, restarts."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    daemon_was_up = daemon_mod.ping(root)
    if daemon_was_up:
        console.print("[yellow]stopping daemon...[/]")
        try:
            daemon_mod.call(root, "stop", {}, timeout=10.0)
        except Exception:
            pass
        # Best-effort wait for daemon to actually go down.
        import time as _time
        for _ in range(30):
            if not daemon_mod.ping(root):
                break
            _time.sleep(0.2)
    s = _store()
    r = s.repair_entity_links_index()
    s.close()
    console.print(
        f"[green]repaired[/] idx_entity_links_lk_concept "
        f"(rows={r.get('row_count', '?')})"
    )
    if daemon_was_up:
        console.print("[yellow]restarting daemon...[/]")
        pid = daemon_mod.spawn_daemon(root)
        console.print(f"[green]daemon up pid={pid}[/]")


# ---- cli invocation log ---------------------------------------------------


@main.command("cli-log")
@click.option("--tail", "-n", type=int, default=20,
              help="Show last N invocations (default 20). Ignored with --summary.")
@click.option("--grep", "-g", "pattern", default=None,
              help="Substring match against the joined argv.")
@click.option("--summary", "-s", is_flag=True,
              help="Print aggregate stats instead of records.")
@click.option("--since", default=None,
              help="ISO timestamp prefix filter, e.g. 2026-05-26 or 2026-05-26T10.")
@click.option("--errors", "errors_only", is_flag=True,
              help="Only show invocations with non-zero exit_code.")
@click.option("--json", "as_json", is_flag=True,
              help="Emit raw JSONL instead of formatted output.")
def cli_log(tail: int, pattern: str | None, summary: bool, since: str | None,
            errors_only: bool, as_json: bool):
    """Inspect the rmx CLI invocation log (.refmatrix/cli.log).

    Each line records: ts, argv, cwd, exit_code, latency_ms, error, pid.
    Disable logging with REFMATRIX_NO_TELEMETRY=1."""
    from refmatrix.telemetry import read_cli_log, summarize_cli_log

    root = _root()

    if summary:
        stats = summarize_cli_log(root, since=since)
        if as_json:
            console.print(json.dumps(stats, indent=2))
            return
        if stats.get("total", 0) == 0:
            console.print("[yellow]no cli.log entries[/]")
            return
        console.print(f"[bold]total:[/] {stats['total']}  "
                      f"[bold]errors:[/] {stats['error_count']} "
                      f"({stats['error_rate']*100:.1f}%)")
        console.print(f"[bold]latency ms:[/] p50={stats['latency_p50_ms']} "
                      f"p95={stats['latency_p95_ms']} "
                      f"p99={stats['latency_p99_ms']} "
                      f"max={stats['latency_max_ms']}")
        t = Table(title="by subcommand", show_header=True)
        t.add_column("subcommand"); t.add_column("count", justify="right")
        for sub, c in list(stats["by_subcommand"].items())[:20]:
            t.add_row(sub, str(c))
        console.print(t)
        t = Table(title="top invocations", show_header=True)
        t.add_column("argv"); t.add_column("count", justify="right")
        for argv_str, c in stats["top_invocations"]:
            t.add_row(argv_str, str(c))
        console.print(t)
        if stats["error_examples"]:
            t = Table(title="recent errors", show_header=True)
            t.add_column("ts"); t.add_column("argv"); t.add_column("error")
            for e in stats["error_examples"]:
                t.add_row(e.get("ts") or "", " ".join(e.get("argv") or []),
                          e.get("error") or "")
            console.print(t)
        return

    rows = read_cli_log(root, since=since)
    if pattern:
        rows = [r for r in rows if pattern in " ".join(r.get("argv") or [])]
    if errors_only:
        rows = [r for r in rows if r.get("exit_code", 0) != 0]
    rows = rows[-tail:] if tail > 0 else rows

    if as_json:
        for r in rows:
            console.print(json.dumps(r))
        return

    if not rows:
        console.print("[yellow]no matching entries[/]")
        return

    t = Table(show_header=True)
    t.add_column("ts"); t.add_column("argv"); t.add_column("exit", justify="right")
    t.add_column("ms", justify="right"); t.add_column("error")
    for r in rows:
        argv = " ".join(r.get("argv") or [])
        code = r.get("exit_code", 0)
        code_str = f"[red]{code}[/]" if code else str(code)
        t.add_row(
            r.get("ts") or "",
            argv,
            code_str,
            str(r.get("latency_ms") or 0),
            r.get("error") or "",
        )
    console.print(t)


# ---- merge-friendly fact log ---------------------------------------------


@main.command("dump-log")
def dump_log():
    """Snapshot the catalog into .refmatrix/facts.log (overwrites existing).

    The log is a name-keyed JSONL stream that's safe to commit and merge
    across branches. Run once to bootstrap an existing repo, then commit
    facts.log and gitignore catalog.db / fragments/."""
    s = _store()
    counts = s.dump_catalog_to_log()
    console.print(f"[green]wrote[/] {s.log_path}")
    for k, v in counts.items():
        console.print(f"  {k}: {v}")


@main.command("rebuild")
@click.option("--from-log", "from_log", is_flag=True,
              help="Replay facts.log into a fresh catalog. Wipes catalog.db "
                   "and fragments/ first.")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def rebuild(from_log: bool, yes: bool):
    """Rebuild derived state. Currently only --from-log is supported."""
    if not from_log:
        raise click.ClickException(
            "specify --from-log (the only supported source)"
        )
    s = _store()
    if not s.log_path.exists():
        raise click.ClickException(
            f"no log at {s.log_path}. Run `rmx dump-log` first."
        )
    if not yes:
        click.confirm(
            f"This will delete {s.db_path} and every fragment file, then "
            f"replay {s.log_path}. Proceed?",
            abort=True,
        )
    result = s.rebuild_index_from_log()
    console.print("[green]rebuilt[/]")
    for k, v in result.items():
        console.print(f"  {k}: {v}")


@main.command("ingest-gmd")
@click.argument("targets", nargs=-1, required=True,
                type=click.Path(exists=True, path_type=Path))
@click.option("--verbose", "-v", is_flag=True, help="Print per-file progress.")
@click.option("--as-memory", "as_memory", is_flag=True,
              help="Register each doc-level entity as kind=memory with a "
                   "memory_content sidecar populated from the body + "
                   "frontmatter. Required for the doc to surface in "
                   "`rmx memory recall` (which filters on kind=memory). "
                   "Use this when ingesting curated `.md` memory files "
                   "rather than reference docs.")
@click.option("--memory-mtype", "memory_mtype", default="curated",
              show_default=True,
              help="Default mtype assigned when --as-memory is set and "
                   "the frontmatter does not carry an explicit "
                   "`metadata.type`.")
@click.option("--prestage", is_flag=True,
              help="Backfill gmd_content_hash on entities for files whose "
                   "content already matches the live DB. Bootstraps the "
                   "auto-resume fast path so the next ingest skips both "
                   "passes for unchanged files. Does NOT ingest — pairs "
                   "with a regular `ingest-gmd` invocation afterwards.")
def ingest_gmd(targets: tuple[Path, ...], verbose: bool,
               as_memory: bool, memory_mtype: str, prestage: bool):
    """Ingest Graph Markdown (GMD) docs. Walks dirs for *.gmd/*.md files
    that carry `gmd:` frontmatter; non-GMD files are skipped."""
    from refmatrix import daemon as daemon_mod
    from refmatrix.ingest_gmd import (
        collect_gmd_files, ingest_gmd_paths, prestage_hashes,
    )

    root = _root()
    resolved = [Path(t).resolve() for t in targets]
    # Pin partition so --as-memory rows land where `rmx memory list/recall`
    # will see them. The daemon's bound partition is the code-sync target
    # and typically is NOT the caller's memory-<project> partition; without
    # this, ingested memories are orphaned. With --as-memory we mirror
    # `_apply_memory_partition_default`: explicit -p / RMX_PARTITION wins,
    # otherwise default to `memory-<project>`.
    if as_memory and not _partition_override \
            and not os.environ.get("RMX_PARTITION"):
        ingest_partition = _memory_partition_default()
    else:
        ingest_partition = _resolve_partition()
    # --prestage: walk files and stamp gmd_content_hash on existing
    # entities. Does not ingest. Useful to bootstrap auto-resume on a
    # store that was populated by older rmx versions (no hashes
    # recorded).
    if prestage:
        if daemon_mod.ping(root):
            resp = daemon_mod.call(root, "prestage_hashes", {
                "targets": [str(p) for p in resolved],
                "partition": ingest_partition,
            }, timeout=600.0)
            if not resp.get("ok"):
                raise click.ClickException(
                    resp.get("error", "daemon error")
                )
            report = resp["result"]
        else:
            s = _store()
            files = collect_gmd_files(resolved)
            with s.with_partition(ingest_partition):
                report = prestage_hashes(s, files)
        console.print(
            f"prestaged: considered={report['considered']} "
            f"written={report['written']} skipped={report['skipped']} "
            f"missing={report['missing']}"
        )
        return
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "ingest_gmd", {
            "targets": [str(p) for p in resolved],
            "verbose": verbose,
            "as_memory": as_memory,
            "memory_mtype": memory_mtype,
            "partition": ingest_partition,
        }, timeout=24 * 3600.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        console.print(resp["result"]["report"])
        return
    s = _store()
    files = collect_gmd_files(resolved)
    if not files:
        console.print("[yellow]no candidate files found[/]")
        return
    if verbose:
        for f in files:
            console.print(f"  scan {f}")
    # In-process path: mirror the daemon partition routing so the
    # no-daemon fallback also lands --as-memory rows in the right slot.
    with s.with_partition(ingest_partition):
        stats = ingest_gmd_paths(
            s, files, verbose=verbose,
            as_memory=as_memory, memory_mtype_default=memory_mtype,
        )
    console.print(stats.report())


# ---- dense / Lance --------------------------------------------------------


_DEFAULT_EMBED_KINDS = ("code", "doc", "concept", "memory")
_VALID_EMBED_KINDS = frozenset(_DEFAULT_EMBED_KINDS)


def _split_kinds(ctx, param, value):
    """Click callback: accepts either repeated `--kinds X --kinds Y` or
    comma-separated `--kinds X,Y` (or any mix). Strips whitespace, dedupes,
    validates each token against the known entity kinds."""
    if not value:
        return ()
    out: list[str] = []
    for v in value:
        for tok in str(v).split(","):
            tok = tok.strip()
            if not tok:
                continue
            if tok not in _VALID_EMBED_KINDS:
                raise click.BadParameter(
                    f"'{tok}' is not a valid kind; "
                    f"expected one of {sorted(_VALID_EMBED_KINDS)}"
                )
            if tok not in out:
                out.append(tok)
    return tuple(out)


@main.command("embed")
@click.option(
    "--kinds", "-k", multiple=True, callback=_split_kinds,
    help="Entity kinds to embed. Repeat the flag (`-k a -k b`) or pass "
         "a comma-separated list (`-k a,b`). Default: all four "
         "(code / doc / concept / memory).",
)
@click.option(
    "--batch", default=256, show_default=True,
    help="Rows per daemon round-trip; daemon stays responsive between batches.",
)
@click.option(
    "--rebuild", is_flag=True,
    help="Re-embed every row of the selected kinds, ignoring "
         "vectors_updated_at. Use after switching embedding models.",
)
@click.option(
    "--max-batches", default=0, show_default=True,
    help="Cap on iterations (0 = unlimited). Useful for partial runs.",
)
@click.option(
    "--gc", "gc_mode", is_flag=True,
    help="GC-only mode: drop lance vectors whose entity_id is absent "
         "from the catalog for the (partition, kind) pair. Pairs with "
         "prior `memory forget` / `purge` ops that left orphans behind "
         "in the dense layer (recall returns them with no resolvable "
         "name and JSON output silently filters to empty). Does not "
         "embed.",
)
@click.option(
    "--dry-run", is_flag=True,
    help="With --gc, report what would be dropped without writing.",
)
def embed_cmd(kinds, batch, rebuild, max_batches, gc_mode, dry_run):
    """Embed entities into Lance for dense ANN retrieval.

    Walks `entities.vectors_updated_at` for the active partition, runs
    per-kind text extractors, sends them through the sentence-
    transformers model, and upserts the float32 vectors into
    `.refmatrix/vectors/<partition>/<kind>.lance`.

    Incremental by default: rows whose `vectors_updated_at >=
    updated_at` are skipped. `--rebuild` forces full re-embed.

    Requires the [dense] extra (pylance + sentence-transformers).
    Operates through the daemon when one is up so the model stays
    loaded across calls; falls back to direct in-process work
    otherwise.
    """
    from refmatrix import daemon as daemon_mod

    root = _root()
    selected = list(kinds) if kinds else list(_DEFAULT_EMBED_KINDS)

    if gc_mode:
        args = {
            "kinds": selected if kinds else None,
            "dry_run": dry_run,
            "partition": _resolve_partition(),
        }
        if daemon_mod.ping(root):
            resp = daemon_mod.call(root, "embed_gc", args, timeout=300.0)
            if not resp.get("ok"):
                raise click.ClickException(resp.get("error", "daemon error"))
            result = resp["result"]
        else:
            from refmatrix.daemon import _op_embed_gc, Daemon
            d = Daemon(root)
            d.store = _store()
            result = _op_embed_gc(d, args)
            if result.get("ok") is False:
                raise click.ClickException(result.get("error", "gc failed"))
        by_kind = result.get("by_kind", {})
        if not by_kind:
            console.print("[yellow]no lance datasets found[/]")
            return
        total_orphans = sum(r["orphans"] for r in by_kind.values())
        tag = "would drop" if dry_run else "dropped"
        for kind, r in sorted(by_kind.items()):
            console.print(
                f"  {kind}: {tag}={r['orphans']} kept={r['kept']}"
            )
        console.print(
            f"[{'yellow' if dry_run else 'green'}]total {tag}: "
            f"{total_orphans}[/]"
        )
        return

    total_embedded = 0
    iters = 0
    if not daemon_mod.ping(root):
        console.print(
            "[yellow]no daemon up — embed runs faster through `rmx daemon start` "
            "so the model stays loaded between calls.[/]"
        )
    while True:
        iters += 1
        args = {
            "kinds": selected, "limit": batch,
            "rebuild": rebuild and iters == 1,
            # Daemon is bound to its startup partition; without this
            # the embed lands in `<root>/vectors/<daemon-partition>/...`
            # regardless of -p, so memory recall against memory-<project>
            # comes up empty even after a "successful" rebuild.
            "partition": _resolve_partition(),
        }
        if daemon_mod.ping(root):
            resp = daemon_mod.call(root, "embed", args, timeout=600.0)
            if not resp.get("ok"):
                raise click.ClickException(resp.get("error", "daemon error"))
            result = resp["result"]
        else:
            # Direct path: open the Store ourselves and run the same
            # logic the op handler runs. Worse latency (cold model
            # each call), but works without a daemon.
            from refmatrix.daemon import _op_embed, Daemon
            d = Daemon(root)
            d.store = _store()
            result = _op_embed(d, args)
        if result.get("ok") is False:
            raise click.ClickException(result.get("error", "embed failed"))
        embedded = int(result.get("embedded", 0))
        remaining = int(result.get("remaining", 0))
        total_embedded += embedded
        console.print(
            f"  batch {iters}: embedded={embedded} remaining={remaining}"
        )
        if embedded == 0 or remaining == 0:
            break
        if max_batches and iters >= max_batches:
            break

    console.print(
        f"[green]done[/] embedded={total_embedded} kinds={','.join(selected)}"
    )


@main.command("search-dense")
@click.argument("query")
@click.option("-k", "--k", default=10, show_default=True, help="Top-k hits.")
@click.option(
    "--kinds", "-K", multiple=True, callback=_split_kinds,
    help="Restrict to kinds. Repeat the flag or pass a comma-separated "
         "list (`-K memory,doc`). Default: all kinds with vectors.",
)
def search_dense_cmd(query, k, kinds):
    """Dense ANN search via Lance. Embeds QUERY with the same model
    used at index time, then returns top-k entities sorted by L2
    distance ascending."""
    from refmatrix import daemon as daemon_mod
    from rich.table import Table

    root = _root()
    args: dict = {"query": query, "k": k}
    if kinds:
        args["kinds"] = list(kinds)
    if daemon_mod.ping(root):
        # 180s covers embedder cold-start (sentence-transformers model
        # load can take 30-90s on a busy CPU). Steady-state ANN search
        # is sub-second.
        resp = daemon_mod.call(root, "ann_search", args, timeout=180.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        result = resp["result"]
    else:
        from refmatrix.daemon import _op_ann_search, Daemon
        d = Daemon(root)
        d.store = _store()
        result = _op_ann_search(d, args)
    if result.get("ok") is False:
        raise click.ClickException(result.get("error", "ann_search failed"))

    hits = result.get("hits", [])
    if not hits:
        console.print("[yellow]no hits[/]")
        return

    # Resolve ids to (kind, name) via the Store for a readable table.
    s = _store()
    con = s._connect()
    table = Table(show_header=True, header_style="bold")
    table.add_column("rank", justify="right")
    table.add_column("distance", justify="right")
    table.add_column("id", justify="right")
    table.add_column("kind")
    table.add_column("name")
    for rank, h in enumerate(hits, 1):
        eid = h["id"]
        dist = h["distance"]
        row = con.execute(
            "SELECT kind, name FROM entities WHERE id = ?", [eid]
        ).fetchone()
        kind = row["kind"] if row else "?"
        name = row["name"] if row else "?"
        table.add_row(str(rank), f"{dist:.3f}", str(eid), kind, name)
    console.print(table)


@main.command("recall")
@click.argument("query")
@click.option("-k", "--k", default=10, show_default=True, help="Top-k hits.")
@click.option(
    "--kinds", "-K", multiple=True, callback=_split_kinds,
    help="Restrict to kinds. Repeat the flag or pass a comma-separated "
         "list (`-K memory,doc`). Default: all kinds with vectors.",
)
@click.option(
    "--concept", "-c", multiple=True,
    help="Concept name(s) for bitmap pre-filter. Each concept's "
         "`mentions` bitmap is OR'd to narrow the ANN candidate set.",
)
@click.option(
    "--symbolic", "-s", multiple=True,
    help="Symbolic-side ranked ids (best-first). Repeat the flag in "
         "rank order. RRF-fuses with the dense side.",
)
@click.option(
    "--no-dense", is_flag=True,
    help="Skip the dense side entirely. Just returns the symbolic list "
         "(or empty if no --symbolic given). Use when [dense] isn't "
         "installed.",
)
def recall_cmd(query, k, kinds, concept, symbolic, no_dense):
    """Hybrid retrieval: bitmap-prefiltered Lance ANN + RRF fusion
    with an optional symbolic ranking.

    Common shapes:
        rmx recall "explain the parser"
            -- pure dense ANN over every kind that has vectors.
        rmx recall "parser entrypoint" -c parser -c lexer
            -- bitmap-narrow to entities that mention either concept,
               then ANN-rank within that subset.
        rmx recall "parser" -s 42 -s 17 -s 88
            -- fuse a symbolic top-3 with the dense side via RRF.

    Requires the [dense] extra unless --no-dense is set.
    """
    from refmatrix.recall import (
        bitmap_prefilter, dense_available, dense_recall, hybrid_recall,
    )
    from rich.table import Table

    s = _store()
    candidate_ids = None
    if concept:
        cids: list[int] = []
        for name in concept:
            e = s.get_entity("concept", name)
            if e is None:
                console.print(f"[yellow]unknown concept: {name}[/]")
                continue
            cids.append(e.id)
        if cids:
            candidate_ids = bitmap_prefilter(s, cids, linkage="mentions")
            if not candidate_ids:
                console.print(
                    "[yellow]concept pre-filter produced empty candidate set "
                    "— nothing matches the given concepts under 'mentions'.[/]"
                )
                return

    symbolic_hits = [int(x) for x in symbolic] if symbolic else None

    if no_dense or not dense_available():
        if symbolic_hits is None:
            console.print(
                "[yellow]dense not available and no --symbolic given — "
                "nothing to rank.[/]"
            )
            return
        # Symbolic-only short-circuit (the caller already ranked).
        ids = list(symbolic_hits)
        if candidate_ids is not None:
            allowed = set(candidate_ids)
            ids = [i for i in ids if i in allowed]
        ranked: list[tuple[int, float]] = [
            (eid, 1.0 - i / max(1, len(ids))) for i, eid in enumerate(ids[:k])
        ]
    else:
        from refmatrix.embedder import Embedder
        embedder = Embedder()
        if symbolic_hits is None and not query:
            console.print("[yellow]no query and no --symbolic given.[/]")
            return
        if symbolic_hits is None:
            ranked = dense_recall(
                s, embedder, query, k=k,
                kinds=list(kinds) if kinds else None,
                candidate_ids=candidate_ids,
            )
        else:
            ranked = hybrid_recall(
                s, embedder, query, k=k,
                kinds=list(kinds) if kinds else None,
                symbolic_hits=symbolic_hits,
                candidate_ids=candidate_ids,
            )

    if not ranked:
        console.print("[yellow]no hits[/]")
        return

    con = s._connect()
    table = Table(show_header=True, header_style="bold")
    table.add_column("rank", justify="right")
    table.add_column("score", justify="right")
    table.add_column("id", justify="right")
    table.add_column("kind")
    table.add_column("name")
    for rank, (eid, score) in enumerate(ranked, 1):
        row = con.execute(
            "SELECT kind, name FROM entities WHERE id = ?", [eid]
        ).fetchone()
        kind = row["kind"] if row else "?"
        name = row["name"] if row else "?"
        table.add_row(str(rank), f"{score:.4f}", str(eid), kind, name)
    console.print(table)


# ---------- intuition memory layer (ADR-0001, Phase B) -----------------------
#
# Every `rmx memory` subcommand persists a "phase: start" record to
# .refmatrix/cli.log BEFORE touching the daemon or the store. This survives
# a daemon SIGABRT mid-op so we can always reconstruct what was attempted.
# The existing cli_entry wrapper writes the matching end-of-run record in
# its finally block.

def _memory_intent(op: str) -> None:
    """First-line setup for every rmx memory subcommand:
    (1) Persist intent to cli.log BEFORE the store/daemon is touched so
        a crash leaves a recoverable record of what was attempted.
    (2) Pin the partition default to 'intuition' unless the user already
        chose one explicitly (-p flag or RMX_PARTITION env var).
    Order: intent first — _root() doesn't depend on partition, so the
    log always lands even if partition resolution explodes later."""
    from refmatrix.telemetry import log_cli_intent
    log_cli_intent(_root(), op=op, argv=list(sys.argv[1:]), pid=os.getpid())
    _apply_memory_partition_default()


# Memory commands default to a project-scoped partition
# `memory-<project>` so each project's observations stay isolated
# from other projects'. ADR-0001 originally landed everything in a
# shared `intuition` partition but per-project memory turned out to
# be the saner default — co-mingling 866 viascope memories with rmx
# work was already producing recall noise.
#
# Project name = the basename of the .refmatrix root's parent dir
# (so `<project>/.refmatrix/` -> partition `memory-<project>`).
# User-supplied -p / RMX_PARTITION / .refmatrix/partition still win,
# matching _resolve_partition's chain.
MEMORY_PARTITION_PREFIX = "memory-"


def _memory_partition_default() -> str:
    """Resolve `memory-<project_name>` for the active CLI invocation.
    Falls back to `memory-default` if the project name can't be
    inferred (e.g. .refmatrix lives at the filesystem root)."""
    try:
        project = _root().resolve().parent.name or "default"
    except Exception:
        project = "default"
    return f"{MEMORY_PARTITION_PREFIX}{project}"


def _memory_daemon_call(op: str, args: dict, *, timeout: float = 60.0):
    """Daemon call helper for memory ops. Auto-injects the active
    partition so memory commands don't have to know that the daemon
    might be bound to a different partition than the one we're
    writing/reading. Special-case callers can still override by
    setting `args['partition']` explicitly before the call."""
    from refmatrix import daemon as daemon_mod
    if "partition" not in args:
        args = {**args, "partition": _resolve_partition()}
    return daemon_mod.call(_root(), op, args, timeout=timeout)


def _apply_memory_partition_default() -> None:
    """If the user did not explicitly pick a partition (no -p on the rmx
    group, no RMX_PARTITION env var), pin this invocation to a project-
    scoped memory partition (`memory-<project>`) for the duration of
    the memory subcommand.

    Skips the .refmatrix/partition file check: that file binds the
    code/doc tree to its own partition, but memories deserve their own
    partition so they don't pollute the symbolic index. If a project
    wants memories in a different partition, pass
    `rmx -p <name> memory add ...` explicitly."""
    global _partition_override
    if _partition_override:
        return
    if os.environ.get("RMX_PARTITION"):
        return
    _partition_override = _memory_partition_default()


@main.group("memory")
def memory_grp():
    """Intuition memory layer (ADR-0001). add / get / search / recall /
    link / forget. All ops route through the daemon when one is up;
    in-process fallback otherwise."""


@memory_grp.command("add")
@click.argument("name")
@click.option("--content", "-c", required=True,
              help="Memory body. Use - to read from stdin.")
@click.option("--type", "mtype", default="observation", show_default=True,
              help="Memory subtype: observation / note / decision / feedback / ...")
@click.option("--tags", "-t", multiple=True, help="Repeatable.")
@click.option("--meta", default=None, help="JSON metadata.")
@click.option("--protect", is_flag=True,
              help="Pin against vacuum/prune-noise.")
def memory_add(name, content, mtype, tags, meta, protect):
    """Add or update a memory entity."""
    _memory_intent("memory_add")
    if content == "-":
        content = sys.stdin.read()
    meta_d = json.loads(meta) if meta else None
    tags_l = list(tags) if tags else None
    from refmatrix import daemon as daemon_mod
    root = _root()
    args = {
        "name": name, "content": content, "mtype": mtype,
        "tags": tags_l, "metadata": meta_d, "protected": protect,
    }
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_add", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        eid = resp["result"]["id"]
    else:
        s = _store()
        eid = s.add_memory(**args)
    console.print(f"[green]memory[/] {name} (id={eid}) {mtype}")


@memory_grp.command("get")
@click.argument("name_or_id")
def memory_get(name_or_id):
    """Fetch a memory by name (current partition) or id (any partition)."""
    _memory_intent("memory_get")
    from refmatrix import daemon as daemon_mod
    root = _root()
    target = int(name_or_id) if name_or_id.isdigit() else name_or_id
    args: dict = ({"id": target} if isinstance(target, int)
                  else {"name": target})
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_get", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        m = resp["result"]["memory"]
    else:
        s = _store()
        m = s.get_memory(target)
    if m is None:
        raise click.ClickException(f"no memory matching {name_or_id!r}")
    console.print(f"[bold]{m['name']}[/]  id={m['id']}  mtype={m['mtype']}")
    if m["tags"]:
        console.print(f"  tags: {', '.join(m['tags'])}")
    if m["metadata"]:
        console.print(f"  meta: {m['metadata']}")
    console.print()
    console.print(m["content"] or "")


@memory_grp.command("list")
@click.option("--type", "mtype", default=None,
              help="Filter by mtype.")
@click.option("--limit", "-n", type=int, default=20, show_default=True)
def memory_list(mtype, limit):
    """List memories in the active partition."""
    _memory_intent("memory_iter")
    from refmatrix import daemon as daemon_mod
    root = _root()
    args = {"mtype": mtype, "limit": limit}
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_iter", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        s = _store()
        rows = list(s.iter_memories(mtype=mtype, limit=limit))
    if not rows:
        console.print("[yellow]no memories[/]")
        return
    t = Table("id", "name", "mtype", "content", "tags")
    for m in rows:
        t.add_row(
            str(m["id"]), m["name"], m["mtype"] or "",
            (m["content"] or "")[:60],
            ", ".join(m["tags"]) if m["tags"] else "",
        )
    console.print(t)


@memory_grp.command("search")
@click.argument("query")
@click.option("--limit", "-n", type=int, default=20, show_default=True)
def memory_search(query, limit):
    """Case-insensitive substring search over memory name + content.
    Returns matching rows newest-first. For dense / hybrid retrieval,
    use `rmx memory recall`."""
    _memory_intent("memory_search")
    from refmatrix import daemon as daemon_mod
    root = _root()
    args = {"query": query, "limit": limit}
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_search", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        s = _store()
        rows = s.search_memories(query, limit=limit)
    if not rows:
        console.print("[yellow]no matches[/]")
        return
    t = Table("id", "name", "mtype", "content")
    for m in rows:
        t.add_row(
            str(m["id"]), m["name"], m["mtype"] or "",
            (m["content"] or "")[:80],
        )
    console.print(t)


_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _render_memory_gmd(rows, *, query: str | None = None,
                       mode: str | None = None,
                       partition: str | None = None) -> str:
    """Render memory recall hits as a single GMD document.

    Each row becomes an H2 node with `{#id}` anchor; the whole doc gets
    a `gmd: "0.1"` frontmatter envelope with a deterministic doc id.
    `rel:` edges are derived from row tags (session-id) and the
    partition. Content is rendered as a markdown blockquote so newlines
    inside the body don't break the GMD shape.
    """
    import hashlib as _h
    import time as _t

    ts_iso = _t.strftime("%Y-%m-%dT%H-%M-%S")
    seed = f"{query or ''}|{mode or ''}|{ts_iso}"
    doc_hash = _h.sha1(seed.encode()).hexdigest()[:8]
    doc_id = f"recall-{ts_iso}-{doc_hash}"

    title_q = (query or "").replace('"', "'")
    if len(title_q) > 60:
        title_q = title_q[:57] + "..."
    title = (
        f"recall: {title_q}" if query else f"recall: {mode or 'memory'}"
    )

    lines: list[str] = [
        "---",
        'gmd: "0.1"',
        f"id: {doc_id}",
        f'title: "{title}"',
    ]
    if query:
        lines.append(f'query: "{title_q}"')
    if mode:
        lines.append(f"mode: {mode}")
    if partition:
        lines.append(f"partition: {partition}")
    lines.append("tags: [recall, memory]")
    lines.append("---")
    lines.append("")
    lines.append("# recall {#root}")
    lines.append("")

    for m in rows:
        anchor = m.get("name") or f"memory-{m.get('id')}"
        score = m.get("score")
        mtype = m.get("mtype") or "memory"
        created = m.get("created_at")
        when = ""
        if created:
            try:
                when = " · when: " + _t.strftime(
                    "%Y-%m-%dT%H:%MZ", _t.gmtime(float(created))
                )
            except Exception:
                pass
        if isinstance(score, (int, float)):
            score_str = f" · score: {score:.3f}"
        else:
            score_str = ""

        lines.append(f"## {anchor} {{#{anchor}}}")
        lines.append(f"mtype: {mtype}{score_str}{when}")

        content = (m.get("content") or "").strip()
        if content:
            if len(content) > 2000:
                content = content[:2000].rstrip() + " …"
            for cl in content.splitlines():
                lines.append(f"> {cl}")

        # Provenance: session-derived memories point back via the
        # standard GMD `derives-from` verb. `part-of` ties every hit
        # to the synthesized root so a reader can enumerate the doc's
        # contents as a single subgraph.
        for t in (m.get("tags") or []):
            if isinstance(t, str) and t.startswith("session:"):
                sess = t[len("session:"):]
                short = sess[:8] if sess else "unknown"
                lines.append(
                    f"rel: derives-from -> [[session-{short}]]"
                )
                break
        lines.append("rel: part-of -> [[#root]]")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _parse_duration(text: str) -> float:
    """Parse `30m`, `1h`, `7d`, `2w` (or bare seconds) → seconds."""
    text = text.strip().lower()
    if not text:
        raise click.BadParameter("empty duration")
    if text[-1] in _DURATION_UNITS:
        try:
            n = float(text[:-1])
        except ValueError as e:
            raise click.BadParameter(f"bad duration {text!r}") from e
        return n * _DURATION_UNITS[text[-1]]
    try:
        return float(text)
    except ValueError as e:
        raise click.BadParameter(
            f"bad duration {text!r}; use 30m / 1h / 7d / bare seconds"
        ) from e


@memory_grp.command("recall")
@click.argument("query", required=False)
@click.option("--prompt", "prompt_query", default=None,
              help="Alias for the positional query. Convenience for "
                   "hook payloads that resolve the prompt themselves.")
@click.option("--stdin-json", "stdin_json", is_flag=True,
              help="Read a Claude Code UserPromptSubmit JSON envelope "
                   "from stdin and use its `.prompt` field as the "
                   "query. Drop-in for the UserPromptSubmit hook.")
@click.option("--k", "-k", type=int, default=10, show_default=True)
@click.option("--recent", is_flag=True,
              help="Phase C2: return the most recent memories by "
                   "entities.created_at DESC (no dense embedder needed). "
                   "Pair with --since to bound the window.")
@click.option("--since", default=None,
              help="With --recent, time window (e.g. 30m, 1h, 7d). "
                   "Default: all memories.")
@click.option("--session-start", "session_start", is_flag=True,
              help="Phase C2: shorthand for `--recent --since 7d` — "
                   "the top-k recent memories suitable for injecting "
                   "into a fresh session's context.")
@click.option("--json", "as_json", is_flag=True,
              help="Emit JSON instead of a Rich table — friendlier "
                   "for hook scripts piping the output into a prompt.")
@click.option("--gmd", "as_gmd", is_flag=True,
              help="Emit a GMD document (gmd:\"0.1\" frontmatter + one "
                   "H2 node per hit with rel: edges). Use as drop-in "
                   "graph-shaped context for prompt injection — readers "
                   "can `[[memory-id]]` cite hits without grepping. "
                   "Mutually exclusive with --json.")
@click.option("--kinds", "-K", "kinds", multiple=True, callback=_split_kinds,
              help="Entity kinds to recall from. Repeat the flag or pass "
                   "a comma-separated list (`-K memory,doc`). Use this to "
                   "include curated `.md` memory files ingested as kind=doc "
                   "alongside intuition observations (kind=memory). "
                   "Default: memory.")
def memory_recall(query, prompt_query, stdin_json, k, recent, since,
                  session_start, as_json, as_gmd, kinds):
    """Memory retrieval. Three modes:

    Hybrid (default): dense ANN over memory.lance fused with the
    symbolic graph. Requires the [dense] extra and embedded memories
    (rmx embed --kinds memory).

    Recent (--recent): newest-first ordering by created_at; no dense
    embedder needed. Pair with --since 1h / 7d to bound the window.

    Session-start (--session-start): shorthand for `--recent --since 7d`,
    the SessionStart hook's preferred mode per ADR-0001 Phase C."""
    _memory_intent("memory_recall")
    if as_json and as_gmd:
        raise click.ClickException(
            "--json and --gmd are mutually exclusive"
        )
    if session_start:
        recent = True
        if since is None:
            since = "7d"
    if stdin_json:
        # UserPromptSubmit hook envelope: {"prompt": "...", ...}.
        # An empty prompt is a normal case (slash commands, /clear,
        # /resume etc fire UserPromptSubmit with no user-typed text) —
        # exit 0 silently rather than erroring, so the hook stays
        # non-fatal for those events. A broken store still surfaces
        # via the daemon RPC path further down.
        import json as _json
        try:
            envelope = _json.load(sys.stdin)
        except Exception as e:
            raise click.ClickException(
                f"--stdin-json: invalid JSON on stdin: {e}"
            )
        prompt_query = (envelope.get("prompt") or "").strip()
        if not prompt_query:
            if as_json:
                click.echo("[]")
            elif as_gmd:
                # Empty-prompt path needs a parseable artifact so the
                # hook caller can detect "no recall" deterministically.
                click.echo(_render_memory_gmd(
                    [], query=None,
                    mode="empty", partition=_resolve_partition(),
                ))
            return
    q = prompt_query or query
    if not recent and not q:
        raise click.ClickException(
            "rmx memory recall needs a QUERY (or --prompt / --stdin-json), "
            "--recent, or --session-start"
        )

    if recent:
        since_s = _parse_duration(since) if since else None
        from refmatrix import daemon as daemon_mod
        if daemon_mod.ping(_root()):
            resp = _memory_daemon_call(
                "memory_recent",
                {"since_seconds": since_s, "limit": k},
            )
            if not resp.get("ok"):
                raise click.ClickException(resp.get("error", "daemon error"))
            rows = resp["result"]["rows"]
        else:
            s = _store()
            rows = s.recent_memories(since_seconds=since_s, limit=k)
        if as_json:
            import json as _json
            click.echo(_json.dumps(rows, indent=2))
            return
        if as_gmd:
            mode_tag = "session-start" if session_start else "recent"
            click.echo(_render_memory_gmd(
                rows, query=None, mode=mode_tag,
                partition=_resolve_partition(),
            ))
            return
        if not rows:
            console.print("[yellow]no memories in window[/]")
            return
        t = Table("rank", "id", "name", "mtype", "content")
        for i, m in enumerate(rows, 1):
            t.add_row(str(i), str(m["id"]), m["name"], m["mtype"] or "",
                      (m["content"] or "")[:80])
        console.print(t)
        return

    # Hybrid path. _memory_daemon_call injects the active partition so
    # the daemon (bound to whatever partition it was started on) can
    # still serve recall against the project's memory partition.
    from refmatrix import daemon as daemon_mod
    root = _root()
    kinds_list = list(kinds) if kinds else ["memory"]
    args = {"query": q, "k": k, "kinds": kinds_list}
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "rmx memory recall needs the daemon up (dense embedder lives there)"
        )
    # 180s covers worst-case embedder cold-start (sentence-transformers
    # model load on a busy CPU takes 30-90s). Steady-state recall is
    # sub-second once the daemon's _embedder cache warms.
    resp = _memory_daemon_call("ann_search", args, timeout=180.0)
    if not resp.get("ok"):
        raise click.ClickException(resp.get("error", "daemon error"))
    hits = resp["result"].get("hits", [])
    if not hits:
        if as_gmd:
            click.echo(_render_memory_gmd(
                [], query=q, mode="hybrid",
                partition=_resolve_partition(),
            ))
            return
        console.print("[yellow]no recall hits[/] (have memories been embedded? "
                      "rmx embed --kinds memory)")
        return
    # Route name/content lookup through the daemon so we read the live
    # rotation slot (catalog.A/B). _store() opens the legacy
    # `catalog.duckdb` file, which the daemon does NOT keep in sync after
    # rotation — looking ids up there returns None for valid memories and
    # silently produces `[]` from the JSON branch. The daemon's own slot
    # has the truth.
    def _fetch_memory(eid: int) -> dict | None:
        resp = _memory_daemon_call("memory_get", {"id": eid}, timeout=30.0)
        if not resp.get("ok"):
            return None
        return resp["result"].get("memory")

    if as_json or as_gmd:
        rows: list[dict] = []
        for h in hits:
            eid = h.get("entity_id") or h.get("id")
            score = h.get("score") or h.get("distance")
            m = _fetch_memory(eid)
            if m is None and "doc" in kinds_list:
                # Non-memory hit (kind=doc/code/concept). For these we
                # still need a direct entity row + file body. Use the
                # replica reader so the read bypasses the daemon's write
                # lock on the active slot; fall back to _store() only if
                # no replica is up yet.
                s = _reader_store() or _store()
                ent = s._read().execute(
                    "SELECT id, kind, name, path, tldr "
                    "FROM entities WHERE id=?", (eid,),
                ).fetchone()
                if ent is not None:
                    row_path = ent["path"] if "path" in ent.keys() else None
                    body = ""
                    if row_path:
                        try:
                            body = Path(row_path).read_text(
                                encoding="utf-8", errors="replace"
                            )
                            if len(body) > 4000:
                                body = body[:4000].rstrip() + " …"
                        except OSError:
                            body = ent["tldr"] or ""
                    m = {
                        "id": ent["id"],
                        "name": ent["name"],
                        "content": body or ent["tldr"] or "",
                        "mtype": ent["kind"],
                        "tags": [],
                        "metadata": {"source_path": row_path or None},
                        "partition_id": None,
                        "created_at": None,
                        "updated_at": None,
                    }
            if m:
                m["score"] = score
                rows.append(m)
        if as_gmd:
            click.echo(_render_memory_gmd(
                rows, query=q, mode="hybrid",
                partition=_resolve_partition(),
            ))
        else:
            import json as _json
            click.echo(_json.dumps(rows, indent=2))
        return
    t = Table("rank", "score", "id", "name")
    for r, h in enumerate(hits, 1):
        eid = h.get("entity_id") or h.get("id")
        score = h.get("score") or h.get("distance")
        m = _fetch_memory(eid)
        name = m["name"] if m else "?"
        t.add_row(str(r), f"{score:.4f}" if isinstance(score, float) else str(score),
                  str(eid), name)
    console.print(t)


@memory_grp.command("link")
@click.argument("src")
@click.argument("linkage")
@click.argument("concept")
@click.option("--weight", "-w", type=float, default=None,
              help="Signed weight. Positive for reinforces, negative "
                   "for contradicts; default None lets the linkage "
                   "convention pick the sign.")
def memory_link(src, linkage, concept, weight):
    """Link a memory to a concept. Auto-creates the concept if new.
    Valid linkages: reinforces, contradicts, recalls, informs, plus
    any DEFAULT_LINKAGES (mentions, defines, ...)."""
    _memory_intent("memory_link")
    from refmatrix import daemon as daemon_mod
    root = _root()
    src_arg = (
        {"src_id": int(src)} if src.isdigit() else {"src_name": src}
    )
    args = {**src_arg, "linkage": linkage, "concept": concept,
            "weight": weight}
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_link", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        result = resp["result"]
    else:
        s = _store()
        m = s.get_memory(int(src) if src.isdigit() else src)
        if m is None:
            raise click.ClickException(f"no memory matching {src!r}")
        cid = s.add_concept(concept)
        s.link(linkage, cid, m["id"], weight=weight)
        result = {"src_id": m["id"], "concept_id": cid}
    console.print(
        f"[green]linked[/] memory:{src} --{linkage}--> concept:{concept} "
        f"(memory_id={result['src_id']}, concept_id={result['concept_id']})"
    )


@memory_grp.command("score")
@click.argument("concept")
@click.option("--explain", is_flag=True,
              help="List the contributing memory rows (decayed weights, "
                   "ages) ordered by |contribution|.")
@click.option("--halflife-days", type=float, default=None,
              help="Override RMX_REINFORCE_HALFLIFE_DAYS for this call.")
@click.option("--cap", type=float, default=None,
              help="Override RMX_REINFORCE_CAP for this call.")
def memory_score(concept, explain, halflife_days, cap):
    """Phase B5: signed reinforcement score for a concept.

    Computes Σ +|w(m)|·decay over `reinforces` plus Σ -|w(m)|·decay
    over `contradicts`, clamped to ±CAP. Positive = the memory layer
    has reinforced this concept; negative = contradicted; ~0 = no
    signal yet.

    With --explain, also prints the per-memory breakdown so you can
    see which observations are driving the number."""
    _memory_intent("memory_score")
    from refmatrix import daemon as daemon_mod
    from refmatrix import reinforcement as rein
    root = _root()
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_score", {
            "concept": concept, "halflife_days": halflife_days,
            "cap": cap, "explain": explain,
        })
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        result = resp["result"]
        cids = result["concept_ids"]
        if not cids:
            raise click.ClickException(f"no concept matching {concept!r}")
        total = result["signal"]
        components_by_cid: dict[int, list[dict]] = {}
        for row in result.get("components") or []:
            components_by_cid.setdefault(row["concept_id"], []).append(row)
    else:
        s = _store()
        cids = s.resolve_concept_ids(concept, strict=False)
        if not cids:
            raise click.ClickException(f"no concept matching {concept!r}")
        scores = s.reinforcement_scores(
            cids, halflife_days=halflife_days, cap=cap,
        )
        total = sum(scores.values())
        components_by_cid = {}
        if explain:
            for cid in cids:
                components_by_cid[cid] = s.reinforcement_components(
                    cid, halflife_days=halflife_days,
                )
    halflife = halflife_days if halflife_days is not None else rein.get_halflife_days()
    cap_used = cap if cap is not None else rein.get_cap()
    console.print(
        f"[bold]{concept}[/]  signal={total:+.4f}  "
        f"(concepts={len(cids)}, halflife={halflife:g}d, cap=±{cap_used:g})"
    )
    if explain:
        s = _store()
        for cid in cids:
            rows = components_by_cid.get(cid, [])
            if not rows:
                continue
            ent = s.get_entity_by_id(cid)
            console.print(f"  [cyan]concept_id={cid}[/]  {ent.name if ent else '?'}")
            t = Table("entity", "linkage", "weight", "age_d",
                      "decay", "contrib")
            for r in rows:
                t.add_row(
                    f"{r['entity_kind']}:{r['entity_name']}",
                    r["linkage"],
                    f"{r['weight']:.3f}" if r["weight"] is not None else "-",
                    f"{r['age_days']:.1f}",
                    f"{r['decay']:.3f}",
                    f"{r['contribution']:+.4f}",
                )
            console.print(t)


def _parse_memory_md_frontmatter(text: str) -> tuple[dict, str]:
    """Parse the auto-memory / GMD frontmatter shape used by curated
    `.md` memory files. Returns (frontmatter_dict, body_text).

    Handles the shapes the auto-memory writer and gmd-curator emit:
      - `key: value`
      - `key: "quoted value"`
      - `key: [a, b, c]`
      - block mapping `metadata:` followed by indented `  type: foo`
      - block list `tags:` followed by `- one` lines

    Tolerant of pre-GMD files that lack `gmd:` — the caller (sync-disk)
    treats any file with frontmatter + a usable name/id as a memory.
    Returns ({}, raw_text) if no frontmatter delimiter is present.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm: dict = {}
    i = 1
    cur_list_key: str | None = None
    cur_map_key: str | None = None
    while i < len(lines) and lines[i].strip() != "---":
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if raw.startswith("  ") and cur_map_key is not None:
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                fm[cur_map_key][k.strip()] = v.strip().strip("\"'")
            i += 1
            continue
        if stripped.startswith("- ") and cur_list_key is not None:
            fm[cur_list_key].append(stripped[2:].strip().strip("\"'"))
            i += 1
            continue
        cur_list_key = None
        cur_map_key = None
        if ":" not in stripped:
            i += 1
            continue
        key, _, val = stripped.partition(":")
        key, val = key.strip(), val.strip()
        if val == "":
            # Could be list (`tags:`) or map (`metadata:`); peek next
            # non-blank line.
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            peek = lines[j].strip() if j < len(lines) else ""
            if peek.startswith("- "):
                fm[key] = []
                cur_list_key = key
            else:
                fm[key] = {}
                cur_map_key = key
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = (
                [x.strip().strip("\"'")
                 for x in inner.split(",") if x.strip()]
                if inner else []
            )
        else:
            fm[key] = val.strip("\"'")
        i += 1
    body_start = i + 1 if i < len(lines) else i
    body = "\n".join(lines[body_start:]).lstrip("\n")
    return fm, body


@memory_grp.command("sync-disk")
@click.argument("paths", type=click.Path(exists=True, path_type=Path),
                nargs=-1, required=True)
@click.option("--mtype", "default_mtype", default="curated", show_default=True,
              help="mtype assigned to memories whose frontmatter does "
                   "not carry an explicit `metadata.type`.")
@click.option("--dry-run", is_flag=True,
              help="Walk and parse but don't upsert. Reports the set of "
                   "files that would be synced.")
def memory_sync_disk(paths: tuple[Path, ...], default_mtype: str,
                     dry_run: bool):
    """Ingest curated `.md` memory files into the rmx memory store.

    Walks each path (file or dir) for `*.md` files, parses frontmatter,
    and upserts each as a `kind=memory` entity using the frontmatter's
    `id` (or `name`, or filename stem) as the memory name. The body
    becomes the memory content. `metadata.type` -> mtype (default
    `curated` when absent). The original source path + mtime are
    stashed in metadata for round-trip diagnostics.

    Designed to bridge the auto-memory `.md` index at
    `~/.claude/projects/<project>/memory/` into rmx so SessionStart
    and UserPromptSubmit hooks see curated memories alongside the
    intuition observations imported from session JSONL.

    Reads:
      id | name | <filename-stem>   -> memory name
      title | description           -> stashed in metadata.title
      metadata.type                 -> mtype
      tags                          -> tags
    """
    _memory_intent("memory_sync_disk")
    from refmatrix import daemon as daemon_mod
    root = _root()
    daemon_up = daemon_mod.ping(root)

    candidates: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix == ".md":
            candidates.append(p.resolve())
        elif p.is_dir():
            for sub in sorted(p.rglob("*.md")):
                if sub.is_file():
                    candidates.append(sub.resolve())
    if not candidates:
        raise click.ClickException(
            "no .md files found under the given path(s)"
        )

    added = 0
    updated = 0
    skipped = 0
    skipped_reasons: list[tuple[str, str]] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            skipped += 1
            skipped_reasons.append((str(path), f"read: {exc}"))
            continue
        fm, body = _parse_memory_md_frontmatter(text)
        # The auto-memory index file (MEMORY.md) is a flat list, not a
        # memory node itself — skip it explicitly.
        if path.name == "MEMORY.md":
            skipped += 1
            skipped_reasons.append((str(path), "index file (MEMORY.md)"))
            continue
        name = (
            (fm.get("id") if isinstance(fm.get("id"), str) else None)
            or (fm.get("name") if isinstance(fm.get("name"), str) else None)
            or path.stem
        )
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        mtype = (
            meta.get("type") if isinstance(meta.get("type"), str) else None
        ) or default_mtype
        title = (
            (fm.get("title") if isinstance(fm.get("title"), str) else None)
            or (fm.get("description") if isinstance(fm.get("description"), str) else None)
        )
        tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        # Synthetic source-pointer metadata so a recall can locate the
        # backing file. Round-trip safe; the writer never reads it
        # back as truth, only the frontmatter on disk does.
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        metadata = {
            "source": "memory_sync_disk",
            "source_path": str(path),
            "source_mtime": mtime,
        }
        if title:
            metadata["title"] = title
        if meta:
            for k, v in meta.items():
                if k not in metadata:
                    metadata[k] = v

        if dry_run:
            added += 1
            continue
        existed: bool
        if daemon_up:
            get_resp = _memory_daemon_call("memory_get", {"name": name})
            existed = (
                get_resp.get("ok", False)
                and bool(get_resp.get("result", {}).get("memory"))
            )
            resp = _memory_daemon_call("memory_add", {
                "name": name,
                "content": body or text,
                "mtype": mtype,
                "tags": list(tags) if tags else None,
                "metadata": metadata,
            })
            if not resp.get("ok"):
                skipped += 1
                skipped_reasons.append(
                    (str(path), resp.get("error", "daemon error"))
                )
                continue
        else:
            s = _store()
            existed = s.get_memory(name) is not None
            s.add_memory(
                name=name, content=body or text,
                mtype=mtype, tags=list(tags) if tags else None,
                metadata=metadata,
            )
        if existed:
            updated += 1
        else:
            added += 1

    total = added + updated + skipped
    console.print(
        f"sync-disk: scanned={total} added={added} updated={updated} "
        f"skipped={skipped}{' (dry-run)' if dry_run else ''}"
    )
    if skipped_reasons:
        for p, reason in skipped_reasons[:10]:
            console.print(f"  [yellow]skipped[/] {p}  ({reason})")
        if len(skipped_reasons) > 10:
            console.print(f"  ... and {len(skipped_reasons) - 10} more")


@memory_grp.command("import-sqlite")
@click.argument("src", type=click.Path(exists=True, dir_okay=False,
                                       path_type=Path))
@click.option("--strict/--no-strict", default=False,
              help="--strict re-raises per-row failures; default collects "
                   "errors and continues so one bad row doesn't abort the "
                   "whole import.")
@click.option("--archive/--no-archive", default=True,
              help="On success, move the source .memory.db family into a "
                   "sibling .intuition-migrated/ directory so the original "
                   "intuition process can't reopen it. --no-archive leaves "
                   "the files in place (useful for dry-run / re-import).")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the stats dict as JSON instead of a table.")
def memory_import_sqlite(src, strict, archive, as_json):
    """Phase C1: import an intuition `.memory.db` into this rmx store.

    Maps observations -> memory entities, observation_concepts.score ->
    mentions weight, concept_relations -> typed linkages (auto-registered),
    concept_aliases -> same_as variants. Idempotent on the
    `imp-<dbname>-<orig_id>` memory naming scheme.

    Goes through the local Store directly (not the daemon) because the
    import is one big transaction and the daemon's RPC framing would
    serialize every row individually.

    By default, after a clean import (no errors), the source .memory.db
    plus its FAISS sidecars and the WAL/SHM files are moved into a
    sibling .intuition-migrated/ directory so the original intuition
    process can't keep writing to a now-shadowed catalog."""
    _memory_intent("memory_import_sqlite")
    from refmatrix.import_intuition import import_intuition_db, archive_source
    s = _store()
    with s.transaction():
        stats = import_intuition_db(s, src, strict=strict)
    archived: list[Path] = []
    if archive and not stats.errors:
        archived = archive_source(src)
    if as_json:
        import json as _json
        out = stats.as_dict()
        out["archived"] = [str(p) for p in archived]
        click.echo(_json.dumps(out, indent=2))
        return
    d = stats.as_dict()
    t = Table("metric", "count")
    for k, v in d.items():
        if k == "errors":
            continue
        t.add_row(k, str(v))
    console.print(t)
    if d["errors"]:
        console.print(f"[yellow]{len(d['errors'])} errors[/] "
                      "(non-strict mode; run with --strict to abort on first):")
        for line in d["errors"][:10]:
            console.print(f"  - {line}")
        if len(d["errors"]) > 10:
            console.print(f"  ... ({len(d['errors']) - 10} more)")
        console.print("[yellow]source files NOT archived[/] — fix and re-run.")
    elif archive:
        console.print(
            f"[green]archived[/] {len(archived)} source file(s) -> "
            f"{src.parent}/.intuition-migrated/"
        )


@memory_grp.command("forget")
@click.argument("name_or_id")
@click.confirmation_option(prompt="Delete this memory and all its linkages?")
def memory_forget(name_or_id):
    """Drop a memory: its entity row, sidecar, and every entity_link."""
    _memory_intent("memory_forget")
    from refmatrix import daemon as daemon_mod
    root = _root()
    args: dict = (
        {"id": int(name_or_id)} if name_or_id.isdigit()
        else {"name": name_or_id}
    )
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_forget", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        ok = resp["result"]["forgotten"]
    else:
        s = _store()
        ok = s.forget_memory(int(name_or_id) if name_or_id.isdigit() else name_or_id)
    if ok:
        console.print(f"[green]forgot[/] {name_or_id}")
    else:
        console.print(f"[yellow]no memory matching[/] {name_or_id}")


# --- session-index group (Phase B) ----------------------------------------
#
# Sessions live in a dedicated `sessions-<project>` partition so the
# conversational, high-volume index doesn't pollute code/memory recall.
# Reuses the existing `as_memory` ingest path entirely — sessions are
# stored as kind=memory rows in the sessions partition, with mtype="session"
# for cross-partition disambiguation.

SESSIONS_PARTITION_PREFIX = "sessions-"


def _sessions_partition_default() -> str:
    """Resolve `sessions-<project_name>` for the active CLI invocation.
    Parallels `_memory_partition_default()`."""
    try:
        project = _root().resolve().parent.name or "default"
    except Exception:
        project = "default"
    return f"{SESSIONS_PARTITION_PREFIX}{project}"


def _encode_claude_project_dir(cwd: Path) -> str:
    """Replicate Claude Code's project-dir slug encoder. Used to find the
    `~/.claude/projects/<slug>/` directory matching the current cwd.

    Claude Code maps both `/` and `_` to `-` in the directory name, so the
    encoding is lossy in reverse — but for lookups (cwd known) it's exact."""
    return str(cwd).replace("/", "-").replace("_", "-")


@main.group("session")
def session_grp():
    """Past Claude Code session index. ingest / (recall, show, list — Phase C).

    Ingests session JSONLs from ~/.claude/projects/ into a dedicated
    sessions-<project> partition. Cards are compressed (~2% of source) GMD
    docs holding user prompts, assistant decisions, files touched, commits,
    and tool counts. Raw JSONLs stay on disk; cards reference them by path."""


@session_grp.command("ingest")
@click.argument("targets", nargs=-1,
                type=click.Path(exists=True, path_type=Path))
@click.option("--all-projects", is_flag=True,
              help="Walk every project under ~/.claude/projects/. Default "
                   "(no targets, no flag) scopes to the project matching "
                   "the current cwd.")
@click.option("--force", is_flag=True,
              help="Rebuild cards even if content_hash matches the existing "
                   "card on disk. Default skips unchanged sessions.")
@click.option("--verbose", "-v", is_flag=True,
              help="Print per-session progress.")
@click.option("--no-index", is_flag=True,
              help="Build cards on disk but skip the ingest-gmd step. "
                   "Useful for previewing card output without touching the "
                   "store.")
def session_ingest_cmd(targets, all_projects, force, verbose, no_index):
    """Parse Claude Code session JSONLs into GMD cards + index them.

    Default scope (no args): the ~/.claude/projects/ directory matching the
    current rmx project's cwd. Pass explicit paths (file or dir) to override.
    `--all-projects` walks every project under ~/.claude/projects/."""
    from refmatrix import daemon as daemon_mod
    from refmatrix.ingest_gmd import collect_gmd_files, ingest_gmd_paths
    from refmatrix.session_ingest import ingest_session, parse_session_jsonl

    root = _root()
    cards_dir = root / "sessions"
    claude_projects = Path.home() / ".claude" / "projects"

    # Resolve which JSONL files to parse.
    jsonls: list[Path] = []
    if targets:
        for t in targets:
            tp = Path(t).resolve()
            if tp.is_file() and tp.suffix == ".jsonl":
                jsonls.append(tp)
            elif tp.is_dir():
                jsonls.extend(sorted(tp.glob("*.jsonl")))
                jsonls.extend(sorted(tp.glob("**/*.jsonl")))
    elif all_projects:
        if not claude_projects.is_dir():
            raise click.ClickException(f"no such dir: {claude_projects}")
        jsonls.extend(sorted(claude_projects.glob("**/*.jsonl")))
    else:
        # Default: project matching current rmx root's cwd.
        project_cwd = root.resolve().parent
        slug = _encode_claude_project_dir(project_cwd)
        proj_dir = claude_projects / slug
        if not proj_dir.is_dir():
            raise click.ClickException(
                f"no Claude Code project dir for {project_cwd} "
                f"(expected {proj_dir}). Pass an explicit path or "
                f"use --all-projects."
            )
        jsonls.extend(sorted(proj_dir.glob("*.jsonl")))

    # Dedup while preserving order.
    seen: set[Path] = set()
    jsonls = [p for p in jsonls if not (p in seen or seen.add(p))]

    if not jsonls:
        console.print("[yellow]no session JSONLs found[/]")
        return

    cards_dir.mkdir(parents=True, exist_ok=True)
    built: list[Path] = []
    skipped = 0
    for jp in jsonls:
        session_id = jp.stem
        card_path = cards_dir / f"{session_id}.md"
        if card_path.exists() and not force:
            try:
                existing = card_path.read_text(encoding="utf-8")
                new_data = parse_session_jsonl(jp)
                if f"content_hash: {new_data.content_hash}" in existing:
                    skipped += 1
                    if verbose:
                        console.print(f"  skip {session_id} (hash match)")
                    continue
            except Exception:
                pass
        out, data = ingest_session(jp, cards_dir)
        built.append(out)
        if verbose:
            console.print(
                f"  card {session_id}: {data.turn_count} turns, "
                f"{data.user_prompt_count} prompts, "
                f"{len(data.files_touched)} files"
            )

    console.print(
        f"cards: built={len(built)} skipped={skipped} total_jsonl={len(jsonls)}"
    )

    if no_index or not built:
        return

    # Route through ingest_gmd with as_memory=True + sessions partition.
    partition = (
        _partition_override
        or os.environ.get("RMX_PARTITION")
        or _sessions_partition_default()
    )
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "ingest_gmd", {
            "targets": [str(p) for p in built],
            "verbose": verbose,
            "as_memory": True,
            "memory_mtype": "session",
            "partition": partition,
        }, timeout=24 * 3600.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        console.print(resp["result"]["report"])
        return

    s = _store()
    files = collect_gmd_files([cards_dir])
    if not files:
        console.print("[yellow]no cards to index[/]")
        return
    with s.with_partition(partition):
        stats = ingest_gmd_paths(
            s, files, verbose=verbose,
            as_memory=True, memory_mtype_default="session",
        )
    console.print(stats.report())


# --- session-index retrieval (Phase C) ------------------------------------

def _session_partition() -> str:
    """Resolve the partition for session ops. Explicit -p / RMX_PARTITION
    wins; otherwise default to sessions-<project>."""
    return (
        _partition_override
        or os.environ.get("RMX_PARTITION")
        or _sessions_partition_default()
    )


def _session_call(op: str, args: dict, *, timeout: float = 60.0):
    """Daemon call helper for session ops. Auto-pins the sessions partition."""
    from refmatrix import daemon as daemon_mod
    if "partition" not in args:
        args = {**args, "partition": _session_partition()}
    return daemon_mod.call(_root(), op, args, timeout=timeout)


def _iter_session_memories() -> list[dict]:
    """Return all memory rows in the active sessions partition. Routes
    through daemon when available; falls back to direct store read."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = _session_call(
            "memory_iter", {"mtype": "session", "limit": 100000},
        )
        if resp.get("ok"):
            return resp["result"]["memories"]
    s = Store(root, partition=_session_partition())
    return list(s.iter_memories(mtype="session", limit=100000))


def _session_meta_get(mem: dict, key: str, default=None):
    """Reach into memory_content.metadata; handle daemon (already-parsed)
    vs. direct-store (may be a JSON str) shapes."""
    meta = mem.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    return meta.get(key, default) if isinstance(meta, dict) else default


def _session_meta_list(mem: dict, key: str) -> list[str]:
    """List-valued metadata accessor. Frontmatter list values like
    `files_touched: ["a", "b"]` survive ingest as JSON-encoded strings
    (the YAML parser used by ingest-gmd's --as-memory path doesn't unwrap
    nested metadata). Parse on read."""
    v = _session_meta_get(mem, key)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except json.JSONDecodeError:
                pass
            # Fallback: split on commas, strip quotes
            inner = s[1:-1].strip()
            if not inner:
                return []
            return [
                item.strip().strip("'\"") for item in inner.split(",")
                if item.strip()
            ]
        return [s] if s else []
    return []


def _session_passes_filters(
    mem: dict,
    *,
    project: str | None = None,
    branch: str | None = None,
    commit: str | None = None,
    touched: str | None = None,
    since_iso: str | None = None,
    until_iso: str | None = None,
) -> bool:
    if project and project not in (_session_meta_get(mem, "project") or ""):
        return False
    if branch and _session_meta_get(mem, "branch") != branch:
        return False
    if commit:
        commits = _session_meta_list(mem, "commits")
        if not any(commit in c for c in commits):
            return False
    if touched:
        files = _session_meta_list(mem, "files_touched")
        if not any(touched in f for f in files):
            return False
    ended = _session_meta_get(mem, "ended") or ""
    if since_iso and ended and ended < since_iso:
        return False
    if until_iso and ended and ended > until_iso:
        return False
    return True


def _since_to_iso(since: str | None) -> str | None:
    """Convert `7d`/`1h`/ISO-prefix to ISO timestamp string for comparison."""
    if not since:
        return None
    # If looks like ISO date, pass through.
    if since and (since[0:4].isdigit() and "-" in since):
        return since
    try:
        secs = _parse_duration(since)
    except click.BadParameter:
        return since
    import time
    return (
        __import__("datetime").datetime.fromtimestamp(
            time.time() - secs, tz=__import__("datetime").timezone.utc,
        ).isoformat().replace("+00:00", "Z")
    )


@session_grp.command("recall")
@click.argument("query", required=False)
@click.option("--project", default=None,
              help="Filter to sessions whose metadata.project contains this "
                   "substring.")
@click.option("--branch", default=None,
              help="Filter to sessions ended on this git branch.")
@click.option("--commit", default=None,
              help="Filter to sessions where this commit sha was authored.")
@click.option("--touched", default=None,
              help="Filter to sessions that edited a file containing this "
                   "path substring.")
@click.option("--since", default=None,
              help="Only sessions ended on/after this point. Accepts `7d`, "
                   "`1h`, `30m`, bare seconds, or ISO date prefix.")
@click.option("--until", default=None,
              help="Only sessions ended on/before this point. Same formats "
                   "as --since.")
@click.option("--k", default=20, type=int, show_default=True,
              help="Result count.")
@click.option("--json", "as_json", is_flag=True,
              help="Emit JSON instead of a table.")
def session_recall_cmd(query, project, branch, commit, touched,
                       since, until, k, as_json):
    """BM25-style search over session cards with metadata filters.

    Symbolic-only: no dense vectors. Score = body match (when QUERY given) +
    recency tiebreak on metadata.ended. Without QUERY, lists most-recent
    sessions matching the filters."""
    from refmatrix import daemon as daemon_mod
    root = _root()

    since_iso = _since_to_iso(since)
    until_iso = _since_to_iso(until)

    # Phase 1: get candidate rows. If query given, use search_memories;
    # else iter the partition.
    if query:
        if daemon_mod.ping(root):
            resp = _session_call(
                "memory_search", {"query": query, "limit": max(k * 4, 100)},
            )
            if not resp.get("ok"):
                raise click.ClickException(resp.get("error", "daemon error"))
            mems = resp["result"]["memories"]
        else:
            s = Store(root, partition=_session_partition())
            mems = list(s.search_memories(query, limit=max(k * 4, 100)))
        # Only sessions
        mems = [m for m in mems if m.get("mtype") == "session"]
    else:
        mems = _iter_session_memories()

    # Phase 2: post-filter on metadata.
    filtered = [
        m for m in mems
        if _session_passes_filters(
            m, project=project, branch=branch, commit=commit,
            touched=touched, since_iso=since_iso, until_iso=until_iso,
        )
    ]

    # Phase 3: sort. With query, preserve search order (already relevance);
    # without, sort by ended DESC.
    if not query:
        filtered.sort(
            key=lambda m: _session_meta_get(m, "ended") or "",
            reverse=True,
        )
    filtered = filtered[:k]

    if as_json:
        click.echo(json.dumps([
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "session_id": _session_meta_get(m, "session_id"),
                "project": _session_meta_get(m, "project"),
                "branch": _session_meta_get(m, "branch"),
                "started": _session_meta_get(m, "started"),
                "ended": _session_meta_get(m, "ended"),
                "turn_count": _session_meta_get(m, "turn_count"),
                "title": (m.get("content") or "").split("\n", 2)[0].lstrip("# ").strip(),
            }
            for m in filtered
        ], indent=2, default=str))
        return

    if not filtered:
        console.print("[yellow]no matching sessions[/]")
        return

    from rich.table import Table
    t = Table(show_lines=False)
    t.add_column("session", style="cyan")
    t.add_column("ended", style="dim")
    t.add_column("branch")
    t.add_column("project", style="dim")
    t.add_column("title")
    for m in filtered:
        sid = _session_meta_get(m, "session_id") or m.get("name", "")
        sid_short = sid[:8] if sid else "?"
        title = (m.get("content") or "").split("\n", 2)[0].lstrip("# ").strip()
        # strip {#root} suffix from title
        title = title.split(" {#")[0]
        ended = (_session_meta_get(m, "ended") or "")[:19]
        branch_s = _session_meta_get(m, "branch") or ""
        project_s = (_session_meta_get(m, "project") or "").split("/")[-1]
        t.add_row(sid_short, ended, branch_s, project_s, title[:60])
    console.print(t)


def _resolve_session(prefix: str) -> dict | None:
    """Resolve a session by id, short prefix, or full memory name."""
    # Direct hit by memory name
    from refmatrix import daemon as daemon_mod
    root = _root()
    candidate_names = [prefix]
    if not prefix.startswith("session-"):
        candidate_names.append(f"session-{prefix[:8]}")
    for nm in candidate_names:
        if daemon_mod.ping(root):
            resp = _session_call("memory_get", {"name": nm})
            if resp.get("ok") and resp["result"].get("memory"):
                return resp["result"]["memory"]
        else:
            s = Store(root, partition=_session_partition())
            row = s.get_memory(nm)
            if row:
                return row
    # Prefix scan over session_id
    for m in _iter_session_memories():
        sid = _session_meta_get(m, "session_id") or ""
        if sid.startswith(prefix) or m.get("name", "").endswith(prefix):
            return m
    return None


@session_grp.command("show")
@click.argument("session_id")
@click.option("--card", "mode", flag_value="card", default=True,
              help="Print the rendered card markdown (default).")
@click.option("--raw", "mode", flag_value="raw",
              help="Print the path to the source JSONL.")
@click.option("--turns", "mode", flag_value="turns",
              help="Re-parse the source JSONL and pretty-print filtered "
                   "user prompts + assistant decisions.")
def session_show_cmd(session_id, mode):
    """Load a session by id (full uuid or 8-char prefix)."""
    mem = _resolve_session(session_id)
    if not mem:
        raise click.ClickException(f"no session matching {session_id!r}")

    if mode == "card":
        click.echo(mem.get("content") or "")
        return
    if mode == "raw":
        src = _session_meta_get(mem, "jsonl_path")
        if not src:
            raise click.ClickException("no jsonl_path in card metadata")
        click.echo(src)
        return
    if mode == "turns":
        from refmatrix.session_ingest import parse_session_jsonl
        src = _session_meta_get(mem, "jsonl_path")
        if not src or not Path(src).exists():
            raise click.ClickException(f"source JSONL missing: {src}")
        data = parse_session_jsonl(Path(src))
        console.print(f"[bold cyan]Session {data.session_id}[/]")
        console.print(
            f"[dim]{data.started} → {data.ended}  "
            f"branch={data.branch}  turns={data.turn_count}[/]"
        )
        console.print()
        console.print("[bold]User prompts:[/]")
        for p in data.user_prompts:
            console.print(f"  • {p}")
        console.print()
        console.print("[bold]Assistant decisions:[/]")
        for d in data.assistant_decisions:
            console.print(d)
            console.print()


@session_grp.command("list")
@click.option("--project", default=None,
              help="Filter to sessions whose project metadata contains this "
                   "substring.")
@click.option("--branch", default=None)
@click.option("--since", default=None,
              help="Only sessions ended on/after this point. Same formats "
                   "as recall --since.")
@click.option("--limit", default=50, type=int, show_default=True)
@click.option("--offset", default=0, type=int)
@click.option("--json", "as_json", is_flag=True)
def session_list_cmd(project, branch, since, limit, offset, as_json):
    """Paginated index of sessions, sorted by ended DESC."""
    since_iso = _since_to_iso(since)
    mems = _iter_session_memories()
    filtered = [
        m for m in mems
        if _session_passes_filters(
            m, project=project, branch=branch, since_iso=since_iso,
        )
    ]
    filtered.sort(
        key=lambda m: _session_meta_get(m, "ended") or "", reverse=True,
    )
    page = filtered[offset : offset + limit]

    if as_json:
        click.echo(json.dumps([
            {
                "session_id": _session_meta_get(m, "session_id"),
                "project": _session_meta_get(m, "project"),
                "branch": _session_meta_get(m, "branch"),
                "ended": _session_meta_get(m, "ended"),
                "turn_count": _session_meta_get(m, "turn_count"),
            }
            for m in page
        ], indent=2, default=str))
        return

    if not page:
        console.print("[yellow]no sessions matching[/]")
        return

    from rich.table import Table
    t = Table()
    t.add_column("session", style="cyan")
    t.add_column("ended", style="dim")
    t.add_column("branch")
    t.add_column("turns", justify="right")
    t.add_column("title")
    for m in page:
        sid = _session_meta_get(m, "session_id") or m.get("name", "")
        title = (m.get("content") or "").split("\n", 2)[0].lstrip("# ").strip()
        title = title.split(" {#")[0]
        ended = (_session_meta_get(m, "ended") or "")[:19]
        branch_s = _session_meta_get(m, "branch") or ""
        turns = str(_session_meta_get(m, "turn_count") or "")
        t.add_row(sid[:8], ended, branch_s, turns, title[:60])
    console.print(t)
    console.print(
        f"[dim]showing {offset + 1}-{offset + len(page)} of "
        f"{len(filtered)} (limit={limit})[/]"
    )


@session_grp.command("stats")
@click.option("--project", default=None,
              help="Restrict aggregation to matching sessions.")
@click.option("--since", default=None)
def session_stats_cmd(project, since):
    """Aggregate stats: session count, turns, tool usage, top files."""
    from collections import Counter
    since_iso = _since_to_iso(since)
    mems = _iter_session_memories()
    filtered = [
        m for m in mems
        if _session_passes_filters(m, project=project, since_iso=since_iso)
    ]
    if not filtered:
        console.print("[yellow]no sessions matching[/]")
        return
    total_turns = 0
    total_prompts = 0
    files_counter: Counter = Counter()
    branch_counter: Counter = Counter()
    project_counter: Counter = Counter()
    model_counter: Counter = Counter()
    for m in filtered:
        total_turns += int(_session_meta_get(m, "turn_count") or 0)
        total_prompts += int(_session_meta_get(m, "user_prompt_count") or 0)
        for f in _session_meta_list(m, "files_touched"):
            files_counter[f] += 1
        b = _session_meta_get(m, "branch")
        if b:
            branch_counter[b] += 1
        p = _session_meta_get(m, "project")
        if p:
            project_counter[p] += 1
        for md in _session_meta_list(m, "models_used"):
            model_counter[md] += 1

    console.print(f"[bold]sessions:[/] {len(filtered)}")
    console.print(f"[bold]total turns:[/] {total_turns}")
    console.print(f"[bold]total user prompts:[/] {total_prompts}")
    if branch_counter:
        console.print(
            "[bold]branches:[/] "
            + ", ".join(f"{b}({n})" for b, n in branch_counter.most_common(5))
        )
    if project_counter:
        console.print(
            "[bold]projects:[/] "
            + ", ".join(
                f"{p.split('/')[-1]}({n})"
                for p, n in project_counter.most_common(5)
            )
        )
    if model_counter:
        console.print(
            "[bold]models:[/] "
            + ", ".join(f"{m}({n})" for m, n in model_counter.most_common())
        )
    if files_counter:
        console.print("[bold]top files touched:[/]")
        for f, n in files_counter.most_common(10):
            console.print(f"  {n:>3} × {f}")


# --- session-index launchd backfill (Phase D) -----------------------------

@session_grp.group("launchctl")
def session_launchctl_grp():
    """macOS launchd integration for the session-index backfill ticker.

    Installs a per-store LaunchAgent that periodically runs
    `rmx session ingest`, keeping the sessions partition in sync with
    ~/.claude/projects/ without any hook dependency."""


@session_launchctl_grp.command("install")
@click.option("--interval", "interval_seconds", default=600, type=int,
              show_default=True,
              help="Seconds between ingest runs.")
@click.option("--all-projects", is_flag=True,
              help="Walk every project under ~/.claude/projects/ on each "
                   "tick (instead of the current project's matching dir).")
@click.option("--force", is_flag=True,
              help="Rewrite the plist + reload even if already installed.")
def session_launchctl_install(interval_seconds, all_projects, force):
    """Install + bootstrap the session-indexer LaunchAgent."""
    from refmatrix import session_launchctl as sl
    root = _root()
    try:
        p = sl.install(
            root, partition=_session_partition(),
            interval_seconds=interval_seconds,
            all_projects=all_projects, force=force,
        )
    except (RuntimeError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    console.print(f"[green]installed[/] {p}")
    console.print(
        f"label: {sl.label_for_root(root)}  "
        f"interval: {interval_seconds}s  "
        f"all_projects: {all_projects}"
    )


@session_launchctl_grp.command("uninstall")
def session_launchctl_uninstall():
    """Bootout + remove the session-indexer LaunchAgent."""
    from refmatrix import session_launchctl as sl
    root = _root()
    try:
        removed = sl.uninstall(root)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    if removed:
        console.print(f"[yellow]uninstalled[/] {sl.plist_path(root)}")
    else:
        console.print("[dim]no session-indexer agent to remove[/]")


@session_launchctl_grp.command("status")
def session_launchctl_status():
    """Report whether the session-indexer agent is installed + loaded."""
    from refmatrix import session_launchctl as sl
    root = _root()
    p = sl.plist_path(root)
    inst = sl.is_installed(root)
    loaded = sl.is_loaded(root) if inst else False
    console.print(f"plist:     {p}")
    console.print(f"label:     {sl.label_for_root(root)}")
    console.print(f"installed: {'[green]yes[/]' if inst else '[red]no[/]'}")
    console.print(f"loaded:    {'[green]yes[/]' if loaded else '[red]no[/]'}")


@main.command("tools-primer")
@click.option("--json", "as_json", is_flag=True,
              help="Emit JSON instead of markdown.")
@click.option("--group", "scope_group", default=None,
              help="Restrict to one subgroup (e.g. 'memory').")
@click.option("--include-options/--no-options", default=True,
              help="Include per-command options + arguments.")
def tools_primer(as_json, scope_group, as_options=None, include_options=True):
    """Produce an agent-consumable primer describing the rmx CLI surface.

    Same role an MCP `tools/list` response plays for an MCP-enabled agent:
    one record per command with name, summary, arguments, options, and
    when-to-use guidance, structured so an agent can plan invocations
    without trial-and-error.

    Markdown by default (CLAUDE.md-friendly). Pass --json for a machine-
    readable structure suitable for piping into another tool.

    Examples:
        rmx tools-primer                       # all commands, markdown
        rmx tools-primer --group memory        # just the memory subgroup
        rmx tools-primer --json                # JSON for programmatic use
        rmx tools-primer --no-options          # compact: names + summaries
    """
    import click as _click

    def _summarize_command(cmd, full_name: str) -> dict:
        # Help text: short_help when set, else first paragraph of the
        # docstring, else the click-rendered help.
        short = cmd.short_help or ""
        long_help = (cmd.help or "").strip()
        summary = short.strip() or long_help.split("\n\n", 1)[0].replace("\n", " ").strip()
        details: list[str] = []
        if long_help and long_help != summary:
            for para in long_help.split("\n\n")[1:]:
                clean = " ".join(p.strip() for p in para.splitlines() if p.strip())
                if clean:
                    details.append(clean)
        args: list[dict] = []
        opts: list[dict] = []
        for p in cmd.params:
            entry = {
                "name": p.name,
                "required": getattr(p, "required", False),
                "help": getattr(p, "help", None),
            }
            ptype = getattr(p, "type", None)
            choices = getattr(ptype, "choices", None)
            if choices:
                entry["choices"] = list(choices)
            default = getattr(p, "default", None)
            # Skip click's internal sentinel and other non-renderables.
            if (
                default not in (None, (), [], False)
                and not callable(default)
                and type(default).__name__ != "Sentinel"
            ):
                entry["default"] = default
            if isinstance(p, _click.Argument):
                args.append(entry)
            elif isinstance(p, _click.Option):
                opts.append({
                    **entry,
                    "flags": list(p.opts) + list(p.secondary_opts),
                    "is_flag": bool(p.is_flag),
                })
        return {
            "name": full_name,
            "summary": summary,
            "details": details,
            "arguments": args,
            "options": opts,
        }

    def _walk(group, prefix: str) -> list[dict]:
        records: list[dict] = []
        for sub_name, sub_cmd in sorted(group.commands.items()):
            full = f"{prefix} {sub_name}".strip()
            if isinstance(sub_cmd, _click.Group):
                # Group header so agents can see the grouping shape.
                records.append({
                    "name": full,
                    "kind": "group",
                    "summary":
                        (sub_cmd.short_help or "").strip()
                        or (sub_cmd.help or "").strip().split("\n\n", 1)[0]
                            .replace("\n", " "),
                    "details": [],
                    "arguments": [],
                    "options": [],
                })
                records.extend(_walk(sub_cmd, full))
            else:
                rec = _summarize_command(sub_cmd, full)
                rec["kind"] = "command"
                records.append(rec)
        return records

    if scope_group is not None:
        if scope_group not in main.commands:
            raise click.ClickException(f"unknown group: {scope_group!r}")
        target = main.commands[scope_group]
        if not isinstance(target, _click.Group):
            raise click.ClickException(
                f"{scope_group!r} is a command, not a group; try without --group"
            )
        records = _walk(target, f"rmx {scope_group}")
    else:
        records = _walk(main, "rmx")

    if as_json:
        click.echo(json.dumps({"tool": "rmx", "commands": records}, indent=2))
        return

    # Markdown rendering, MCP-tools-list-shaped.
    lines: list[str] = []
    lines.append("# rmx CLI tools primer")
    lines.append("")
    lines.append(
        "Agent-consumable description of the `rmx` CLI surface. Each entry "
        "below mirrors the role an MCP `tools/list` record plays: name, "
        "summary, arguments, options, when-to-use detail. Plan invocations "
        "from this primer instead of `rmx <cmd> --help` trial-and-error."
    )
    lines.append("")
    for rec in records:
        if rec.get("kind") == "group":
            lines.append(f"## `{rec['name']}` (group)")
            if rec["summary"]:
                lines.append("")
                lines.append(rec["summary"])
            lines.append("")
            continue
        lines.append(f"### `{rec['name']}`")
        lines.append("")
        if rec["summary"]:
            lines.append(rec["summary"])
            lines.append("")
        for para in rec["details"]:
            lines.append(para)
            lines.append("")
        if include_options and rec["arguments"]:
            lines.append("**Arguments:**")
            for a in rec["arguments"]:
                req = " (required)" if a["required"] else ""
                hlp = f" — {a['help']}" if a.get("help") else ""
                lines.append(f"- `{a['name'].upper()}`{req}{hlp}")
            lines.append("")
        if include_options and rec["options"]:
            lines.append("**Options:**")
            for o in rec["options"]:
                flags = ", ".join(f"`{f}`" for f in o["flags"])
                hlp = f" — {o['help']}" if o.get("help") else ""
                ch = (
                    f" choices: {o['choices']}"
                    if o.get("choices") else ""
                )
                dv = (
                    f" default: `{o['default']}`"
                    if "default" in o else ""
                )
                lines.append(f"- {flags}{hlp}{ch}{dv}")
            lines.append("")
    click.echo("\n".join(lines))


def cli_entry() -> None:
    """Console-script entrypoint. Wraps `main()` with invocation logging.

    Captures argv, cwd, exit code, latency, and any exception, then appends
    one JSONL record to .refmatrix/cli.log via telemetry. Preserves Click's
    exit semantics by re-raising SystemExit.
    """
    import time as _time
    from refmatrix.telemetry import log_cli_invocation

    t0 = _time.monotonic()
    argv = list(sys.argv[1:])
    cwd = str(Path.cwd())
    pid = os.getpid()
    exit_code = 0
    error: str | None = None
    try:
        main()
    except SystemExit as e:
        code = e.code
        exit_code = int(code) if isinstance(code, int) else (0 if code is None else 1)
        raise
    except BaseException as e:
        exit_code = 1
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        try:
            log_cli_invocation(
                _root(),
                argv=argv,
                cwd=cwd,
                exit_code=exit_code,
                latency_ms=latency_ms,
                error=error,
                pid=pid,
            )
        except Exception:
            pass


if __name__ == "__main__":
    cli_entry()
