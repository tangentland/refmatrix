"""refmatrix CLI."""
from __future__ import annotations

import atexit
import contextlib
import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.table import Table

from refmatrix import __version__
from refmatrix.handoff import (
    _SS_FOCUS_NOISE, _focus_digest, _ss_clean_focus, _ss_sh,
    compose_recall_state, compose_save_state,
)
from refmatrix.query import QueryEngine
from refmatrix.store import Store, default_partition_name
from refmatrix.telemetry import log_query

console = Console()


def _root() -> Path:
    """Resolve the active store root.

    REFMATRIX_ROOT env wins. Else walk up from cwd for a project `.refmatrix`.
    If none is found, fall back to the user-level GLOBAL store (`~/.refmatrix`)
    rather than auto-creating a junk `cwd/.refmatrix` — store creation is
    explicit (`rmx init`) only."""
    env = os.environ.get("REFMATRIX_ROOT")
    if env:
        return Path(env)
    cur = Path.cwd().resolve()
    # A `~/.claude/projects/<slug>/` cwd (e.g. a curated-memory dir) encodes the
    # project in its slug. Resolve THAT project's store FIRST — before the
    # generic ancestor walk, which would otherwise climb past it and hit the
    # home store's `~/.refmatrix` at `/Users/<user>`, mis-resolving every memory
    # op run from inside the projects dir to partition `global`.
    proj_root = _root_from_projects_slug(cur)
    if proj_root is not None:
        return proj_root
    for p in [cur, *cur.parents]:
        if (p / ".refmatrix").is_dir():
            return p / ".refmatrix"
    from refmatrix.taxonomy import user_home
    return user_home()  # global/home store; never auto-create cwd/.refmatrix


def _root_from_projects_slug(cwd: Path) -> "Path | None":
    """When `cwd` is inside `~/.claude/projects/<slug>/...`, resolve the project
    store whose slug matches `<slug>`. The slug is Claude Code's lossy cwd
    encoding (`/` and `_` → `-`) of the project dir — the same encoding
    `handoff.default_memory_dir` uses — so match it against the discovered
    roots' encoded parent dirs rather than trying to invert it (lossy)."""
    projects = Path.home() / ".claude" / "projects"
    try:
        rel = cwd.relative_to(projects)
    except ValueError:
        return None
    if not rel.parts:
        return None
    slug = rel.parts[0]
    from refmatrix import discovery
    for root in discovery.discover_roots():
        proj = root.parent
        encoded = str(proj.resolve()).replace("/", "-").replace("_", "-")
        if encoded == slug:
            return root
    return None


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


def _store_rw() -> Store:
    """Open the active rotation-slot catalog read-write (direct). The legacy
    `catalog.duckdb` is no longer touched by the daemon post-0.3.8: that file
    is FROZEN at bootstrap, and any code opening it from there sees stale data.

    Resolution:
      1. `<root>/catalog.<active>.duckdb` per the `active` marker — what
         the daemon writes to (or wrote to last). Source of truth.
      2. Legacy `<root>/catalog.duckdb` for ancient pre-rotation stores.

    With the daemon up, opening the active slot r/w from another process
    will fail (DuckDB exclusive lock). This is the DAEMON-DOWN writer path;
    when the daemon is up, `_store(write=True)` returns a `_DaemonWriter`
    that routes mutations through RPC instead."""
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


class _DaemonWriter:
    """The catalog writer returned by `_store(write=True)` when a daemon
    owns the store.

    Single control point for the lock: every mutation the CLI performs maps
    to a typed daemon RPC op, so the DuckDB write-lock stays single-owner and
    no command needs the daemon stopped. Read methods the CLI mixes in with
    writes (`get_entity_by_id`, `resolve_concept_ids`, `siblings_via_canon`,
    …) fall through `__getattr__` to a lock-free reader Store, so command
    bodies that interleave reads and writes on one object work unchanged.

    Mirrors the subset of the `Store` API the CLI calls. Each explicit method
    here MUTATES (signals write intent); anything not defined is a read and is
    delegated to the replica reader.
    """

    def __init__(self, root: Path, partition: str | None):
        self._root = root
        self._partition = partition
        self._reader: Store | None = None

    # -- routing core --------------------------------------------------------
    def _call(self, op: str, args: dict, timeout: float = 60.0):
        from refmatrix import daemon as daemon_mod
        a = dict(args)
        a.setdefault("partition", self._partition)
        resp = daemon_mod.call(self._root, op, a, timeout=timeout)
        if not isinstance(resp, dict) or not resp.get("ok"):
            msg = (resp or {}).get("error", f"daemon {op} failed")
            raise click.ClickException(msg)
        return resp.get("result") or {}

    def _get_reader(self) -> Store:
        if self._reader is None:
            rs = _reader_store()
            if rs is None:
                raise click.ClickException(
                    "daemon is up but no lock-free reader is available yet "
                    "(snapshot not built). Run `rmx replica refresh` and retry."
                )
            self._reader = rs
        return self._reader

    def __getattr__(self, name: str):
        # Only reached for attributes not defined on the class/instance —
        # i.e. read methods. Guard underscored names to avoid recursing on
        # internal attrs before __init__ has set them.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._get_reader(), name)

    def with_partition(self, partition: str | None):
        """Context manager mirroring Store.with_partition: scope subsequent
        op routing (and reader reads) to `partition`."""
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            prev = self._partition
            self._partition = partition
            prev_reader, self._reader = self._reader, None
            try:
                yield self
            finally:
                self._partition = prev
                try:
                    if self._reader is not None:
                        self._reader.close()
                except Exception:
                    pass
                self._reader = prev_reader

        return _ctx()

    def close(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None

    # -- mutations: each maps to a typed op ---------------------------------
    def link(self, linkage, concept_id, entity_id, weight=None, protect=False):
        return self._call("link", {
            "linkage": linkage, "concept_id": concept_id,
            "entity_id": entity_id, "weight": weight, "protect": protect,
        }).get("created", False)

    def unlink(self, linkage, concept_id, entity_id):
        return self._call("unlink", {
            "linkage": linkage, "concept_id": concept_id,
            "entity_id": entity_id,
        }).get("unlinked", False)

    def link_canon(self, local_concept_id, canon_partition, canon_concept_name):
        return self._call("link_canon", {
            "local_concept_id": local_concept_id,
            "canon_partition": canon_partition,
            "canon_concept_name": canon_concept_name,
        }).get("canon_id")

    def save_query(self, name, body):
        self._call("save_query", {"name": name, "body": body})

    def add_concept(self, name, description=None, protected=True):
        return self._call("add_concept", {
            "name": name, "description": description, "protected": protected,
        }).get("id")

    def add_linkage_type(self, name, directed=True, description=None):
        return self._call("add_linkage_type", {
            "name": name, "directed": directed, "description": description,
        }).get("id")

    def upsert_entity(self, kind, name, path=None, tldr=None, meta=None,
                      protected=True):
        return self._call("upsert_entity", {
            "kind": kind, "name": name, "path": path, "tldr": tldr,
            "meta": meta, "protected": protected,
        }).get("id")

    def add_memory(self, name, content, mtype="observation", tags=None,
                   metadata=None, protected=False):
        return self._call("memory_add", {
            "name": name, "content": content, "mtype": mtype,
            "tags": tags, "metadata": metadata, "protected": protected,
        }).get("id")

    def forget_memory(self, target):
        key = "id" if isinstance(target, int) else "name"
        return self._call("memory_forget", {key: target}).get("forgotten", False)

    def bulk_forget_memories(self, ids=None, names=None, mtypes=None,
                             dry_run=False):
        return self._call("memory_bulk_forget", {
            "ids": ids, "names": names, "mtypes": mtypes, "dry_run": dry_run,
        })

    def fold_concept_dups(self, *, dry_run=False):
        return self._call("memory_dedup", {"dry_run": dry_run})

    def vacuum(self):
        # Dropping orphaned concepts is a batched bulk-purge that can touch
        # thousands of rows on a big partition — give it the long timeout.
        return self._call("vacuum", {}, timeout=600.0)

    def prune_noise(self, namespaces=("keyword",), min_df=2,
                    max_df_ratio=0.25, drop=False):
        return self._call("prune_noise", {
            "namespaces": list(namespaces), "min_df": min_df,
            "max_df_ratio": max_df_ratio, "drop": drop,
        })

    def set_flag_by_selector(self, flag, value, **selectors):
        return self._call("set_flag", {"flag": flag, "value": value,
                                       **selectors})

    def forget_by_selector(self, *, dry_run=False, **selectors):
        # Batched bulk-purge can still touch thousands of rows + fragments on a
        # big partition — give it the same long timeout as bulk-forget/rebuild.
        return self._call("forget", {"dry_run": dry_run, **selectors},
                          timeout=600.0)

    def untrack_by_path(self, *, like=None, paths=None, dry_run=False):
        # Same long timeout as forget: a mis-ingested subtree can carry
        # thousands of entities across hundreds of files.
        return self._call("untrack",
                          {"like": like, "paths": list(paths) if paths else None,
                           "dry_run": dry_run},
                          timeout=600.0)

    def rebuild_index_from_log(self):
        return self._call("rebuild_index", {}, timeout=600.0).get("result", {})

    def ingest_path(self, path, source="auto", semantic=False):
        """Whole-path ingest as ONE op (not per-entity), so a big ingest is
        a single RPC, not thousands."""
        return self._call("ingest_path", {
            "path": str(path), "source": source, "semantic": semantic,
        }, timeout=24 * 3600.0).get("entities", 0)


def _store(write: bool = True) -> "Store | _DaemonWriter":
    """THE catalog accessor. The `write` flag signals intent at the call site.

    write=False -> a lock-free READER (replica/snapshot). Never opens the
        writer slot, so it can't collide with the daemon's write-lock.
    write=True  -> a WRITER. When a daemon owns the store, a `_DaemonWriter`
        proxy that routes every mutation through RPC; otherwise a direct
        read-write `Store` on the active slot.

    Default is `write=True` for back-compat with un-migrated call sites: with
    the daemon down (the common dev/test case) it returns the same direct
    `Store` as before, so behavior is unchanged until a daemon is present."""
    if not write:
        return _read_store()
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        return _DaemonWriter(root, _resolve_partition())
    return _store_rw()


@contextlib.contextmanager
def _stream_ingest_progress(root: Path):
    """Surface the daemon's per-pass `ingest-progress` live while a blocking
    ingest RPC runs, so the CLI isn't a black box during the long code+docs
    pass. Tails `rmxd.log` from EOF in a daemon thread; best-effort — if the
    log is unreadable nothing prints and the ingest is unaffected."""
    import threading
    import time as _t
    log_path = root / "rmxd.log"
    stop = threading.Event()

    def _tail():
        try:
            f = log_path.open("r")
        except OSError:
            return
        with f:
            f.seek(0, 2)  # only NEW lines from here
            while not stop.is_set():
                line = f.readline()
                if not line:
                    _t.sleep(0.2)
                    continue
                if "ingest-progress " in line:
                    msg = line.split("ingest-progress ", 1)[1]
                    msg = msg.split(" job=", 1)[0].strip()
                    console.print(f"[dim]  ⋯ {msg}[/]")

    t = threading.Thread(target=_tail, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=1.0)


def _ingest(writer: "Store | _DaemonWriter", path, *,
            source: str = "auto", semantic: bool = False) -> int:
    """Uniform whole-path ingest through the write control point.

    When `writer` is a `_DaemonWriter` the entire ingest runs as ONE daemon
    op (never per-entity RPC); otherwise it runs in-process against the
    direct Store. Returns the entity count. Lets `ingest` / `tldr-warm` /
    `graphify-warm` share one call shape regardless of daemon state."""
    if isinstance(writer, _DaemonWriter):
        # Blocking RPC — stream the daemon's per-pass progress so the user sees
        # movement instead of a frozen prompt for minutes.
        with _stream_ingest_progress(writer._root):
            return writer.ingest_path(path, source=source, semantic=semantic)
    from refmatrix.ingest import ingest_path as _ip
    return _ip(writer, Path(path), source=source, semantic=semantic)


def _replica_reader_path() -> Path:
    """Return the path to the current lock-free reader file.

    Resolution order (snapshot-first, symlink-last):
      1. `<root>/catalog.read.duckdb` — daemon-maintained snapshot
         (atomic tmp+rename file copy of the writer's catalog).
         Preferred — multi-process safe with no symlink indirection
         drift. The writer never holds this file open exclusively, so
         CLI processes can open it READ_ONLY without lock collision.
      2. `<root>/read_only.duckdb` — legacy symlink at the current
         inactive (reader) slot. Used only when the snapshot file is
         missing (pre-snapshot-tier stores, daemon cold-start before
         first write op).
      3. `<root>/active` marker + `catalog.{inactive}.duckdb` —
         fallback for pre-symlink stores that the daemon hasn't
         touched yet this run.
      4. Legacy `catalog.duckdb` for pre-rotation (pre-0.3.8) stores.

    Doesn't query the daemon — pure file-system lookup. Resolving the
    snapshot file directly (rather than the symlink) is what makes
    every read self-correcting: a stale symlink left over from a past
    daemon state can no longer route reads at the writer slot.
    """
    root = _root()
    snap = root / "catalog.read.duckdb"
    if snap.exists():
        return snap
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


def _maybe_learn_grep_backstop(root, daemon_mod, ref, bundle, grep_backstop):
    """When the grep backstop fired (index miss → grep hit), fold its hits into
    a protected `query/<ref>` concept via the daemon writer so the next lookup
    is indexed and survives `prune_noise`. The read path (replica) can't write,
    so the CLI brokers the learn through the daemon. Best-effort: a read command
    never fails on a learn miss, and with no daemon up nothing is learned."""
    if not grep_backstop or not ref:
        return
    grep_entries = bundle.groups.get("grep") or []
    if not grep_entries or not daemon_mod.ping(root):
        return
    hits: list[dict] = []
    for e in grep_entries:
        path = e.entity.path
        if not path:
            continue
        for ln in (e.lines or ([e.line] if e.line is not None else [])):
            hits.append({"file": path, "line": ln})
    if not hits:
        return
    try:
        daemon_mod.call(root, "learn_from_grep", {
            "pattern": ref, "hits": hits, "project_root": str(root.parent),
        }, timeout=30.0)
    except Exception:
        pass  # best-effort self-heal; never break the read


def _replica_store() -> Store:
    """Open the reader-slot catalog in read-only mode.

    Skips migrations / writes / repair. Used by `--via-replica` CLI ops
    so reads bypass the daemon's `_store_lock` entirely. The file is
    a snapshot (`catalog.read.duckdb`) the daemon regenerates shortly
    after each write op (snapshot-tier; writer rotation is dropped)."""
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


def _read_store() -> Store:
    """Snapshot-tier policy fix: return a Store usable for reads — prefers
    the daemon-maintained read-only reader slot (lock-free against the
    daemon's writer), falls back to the primary `_store()` only when the
    replica file isn't there yet (daemon down / fresh install).

    Use this in CLI read paths that previously did `s = _store();
    s._connect().execute(...)` and crashed with `Could not set lock on
    catalog.B.duckdb` when the daemon was up. Callers don't need to
    branch on daemon state — both shapes return a Store that supports
    read SQL through `._connect().execute(...)`."""
    rs = _reader_store()
    if rs is not None:
        return rs
    return _store()


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
        from refmatrix.init_agents import install_agents, install_commands
        for line in install_agents(project_root=project_root, force=force):
            console.print(line)
        # Slash commands (/stash, /stash-list, /stash-pop, /save-state,
        # /recall-state) — the standardized workflow rituals.
        for line in install_commands(project_root=project_root, force=force):
            console.print(line)


@main.command()
def info():
    """Print the active refmatrix version, root, and partition."""
    from refmatrix import __version__
    console.print(f"version:   {__version__}")
    console.print(f"root:      {_root()}")
    console.print(f"partition: {_resolve_partition()}")


@main.command()
@click.option("--from-dev", type=click.Path(path_type=Path), default=None,
              help="Promote a local dev tree's branch INTO this install instead "
                   "of pulling from GitHub (the dev->deploy ritual). "
                   "Fast-forward only.")
@click.option("--ref", default=None,
              help="Branch or tag to upgrade to (default: the install's current "
                   "branch; 'master' for --from-dev).")
@click.option("--check", is_flag=True,
              help="Dry-run: fetch and report current-vs-available version + "
                   "HEAD, mutating nothing.")
@click.option("--no-restart", is_flag=True,
              help="Skip the daemon restart after installing.")
def upgrade(from_dev, ref, check, no_restart):
    """Self-update this install: fast-forward its git tree, `pip install -e`,
    and restart the daemon, then report the version change.

    Default pulls from `origin/<branch>` (or `--ref`). `--from-dev <path>`
    promotes a local dev tree instead — the dev->deploy ritual, no GitHub
    round-trip. `--check` previews the change read-only. Merges are
    fast-forward only, so a divergent local tree is refused rather than
    rewritten."""
    from refmatrix import upgrade as _up
    try:
        _up.upgrade(from_dev=from_dev, ref=ref, check=check,
                    restart=not no_restart, log=console.print)
    except _up.UpgradeError as e:
        raise click.ClickException(str(e))


@main.command("ui")
@click.option("--port", type=int, default=None, help="HTTP port (default 7777).")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--no-browser", is_flag=True, help="Don't open a browser.")
def ui_cmd(port, host, no_browser):
    """Open the web UI (starts the hub if needed)."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        raise click.ClickException(
            "the web UI needs extra deps. Install with:\n"
            "    pip install 'refmatrix[ui]'"
        )
    from refmatrix import hub as hub_mod
    port = port or hub_mod.DEFAULT_PORT
    if not hub_mod.is_running():
        console.print("[dim]starting hub…[/]")
        hub_mod.spawn_hub(port=port, host=host)
    if not hub_mod.is_running():
        raise click.ClickException(f"hub failed to start (see {hub_mod.hub_log_path()})")
    url = f"http://{host}:{port}"
    console.print(f"[green]refmatrix hub UI[/] → {url}")
    if not no_browser:
        import webbrowser
        webbrowser.open(url)


@main.group()
def focus():
    """Short-term (working) memory — a per-project, isolated focus graph of
    what you're working on right now. Fixed-size ring + recency-weighted
    co-occurrence graph. Works with the daemon/hub stopped."""


def _resolve_stm_session(explicit: str | None = None, *, prefer_latest: bool = False) -> str:
    """Pick the STM session: an explicit --session wins, else $RMX_SESSION,
    else (for read surfaces) the most-recently-written session ring, else the
    bare "default". `prefer_latest` lets `focus tail/context/size` and the
    task read commands show the active Claude session a plain shell can't name."""
    from refmatrix import stm as stm_mod
    if explicit:
        return explicit
    env = os.environ.get("RMX_SESSION")
    if env:
        return env
    if prefer_latest:
        latest = stm_mod.latest_session(_root())
        if latest:
            return latest
    return stm_mod.session_id()


def _stm(session: str | None = None, *, prefer_latest: bool = False):
    from refmatrix import stm as stm_mod
    return stm_mod.Stm(_root(), _resolve_stm_session(session, prefer_latest=prefer_latest))


@focus.command("record")
@click.option("--kind", type=click.Choice(["input", "tool", "rmx", "result"]),
              default="tool")
@click.option("--terse", required=True, help="Terse one-line event text.")
@click.option("--ref", "refs", multiple=True, help="Explicit ref (repeatable).")
def focus_record(kind, terse, refs):
    """Append an event to short-term memory (used by hooks)."""
    ev = _stm().record(kind, terse, refs=list(refs) or None)
    console.print(f"[dim]stm[/] {ev['kind']}: {', '.join(ev['refs']) or '—'}")


@focus.command("tail")
@click.option("-n", type=int, default=20, show_default=True)
@click.option("-s", "--session", default=None,
              help="Session id to read. Default: active Claude session.")
def focus_tail(n, session):
    """Show recent short-term events (defaults to the active session)."""
    s = _stm(session, prefer_latest=True)
    rows = s.tail(n)
    if not rows:
        console.print(f"[yellow]no focus events[/] [dim](session {s.session})[/]")
        return
    console.print(f"[dim]session {s.session}[/]")
    for ev in rows:
        task = f" [dim]({ev['task']})[/]" if ev.get("task") else ""
        console.print(f"[dim]{ev['ts']}[/] [cyan]{ev['kind']}[/]{task}: {ev['terse']}")


@focus.command("context")
@click.option("--top", type=int, default=20, show_default=True)
@click.option("-s", "--session", default=None,
              help="Session id to read. Default: active Claude session.")
def focus_context(top, session):
    """Show the current focus mini-graph (recency-weighted)."""
    s = _stm(session, prefer_latest=True)
    # Pull a wider slice, then drop shell-token noise at render time so a graph
    # polluted by pre-noise-fix events (the ring isn't retroactively cleaned)
    # still displays the real symbols. _ss_clean_focus is the shared filter.
    g = s.focus_graph(top=max(top * 3, 30))
    nodes = _ss_clean_focus(g["nodes"], limit=top)
    if not nodes:
        console.print("[yellow]no focus yet[/]")
        return
    console.print(f"[bold]focus[/] · {g['events']} events · session {g['session']}")
    console.print("[dim]L<n> = line in the full log; `rmx focus show <n>` for "
                  "depth[/]")
    # Each event's 1-based line in the full on-disk log, so every row below can
    # cite L<n> and the reader can drill to the raw event via `focus show <n>`.
    events = s.all_events()
    last_line: dict[str, int] = {}
    for i, e in enumerate(events, 1):
        for r in (e.get("refs") or []):
            last_line[r] = i
    # Intent thread — the dialogue: user inputs (UserPromptSubmit) interleaved
    # with my replies (Stop → `say`). Short prompts ("deploy") extract no refs
    # so they're invisible in the ref-graph below; the dialogue gives the graph
    # its "why" and makes a bare "yes" legible against what I'd just proposed.
    dialogue = [(i, e) for i, e in enumerate(events, 1)
                if e.get("kind") in ("input", "say", "reason")]
    if dialogue:
        console.print("[bold]intent[/] [dim](dialogue + reasoning)[/]")
        _marks = {"input": "[magenta]▸[/]", "say": "[green]◂[/]",
                  "reason": "[blue]✎[/]"}
        for i, e in dialogue[-7:]:
            k = e["kind"]
            mark = _marks.get(k, " ")
            dim = "" if k == "input" else "[dim]"
            undim = "" if k == "input" else "[/]"
            console.print(f"  {mark} {dim}{e['terse'][:84]}{undim} [dim]L{i}[/]")
    # Milestones — git ops captured with their output (commit/push/merge/...).
    gits = [(i, e) for i, e in enumerate(events, 1) if e.get("kind") == "git"]
    if gits:
        console.print("[bold]milestones[/] [dim](git)[/]")
        for i, e in gits[-6:]:
            console.print(f"  [yellow]⎇[/] [dim]{e['terse'][:84]}[/] [dim]L{i}[/]")
    # Per-row +1 neighbors from the focus edges (co-occurrence within the
    # rolling window) — the graph structure, not just the ranked list. Noise
    # neighbors are dropped so a row points only at real symbols.
    nbr: dict[str, list[tuple[float, str]]] = {}
    for ed in g.get("edges", []):
        a, b, w = ed["source"], ed["target"], ed["weight"]
        if b.lower() not in _SS_FOCUS_NOISE:
            nbr.setdefault(a, []).append((w, b))
        if a.lower() not in _SS_FOCUS_NOISE:
            nbr.setdefault(b, []).append((w, a))
    console.print("[bold]graph[/]")
    for nd in nodes:
        tops = sorted(nbr.get(nd["name"], []), reverse=True)[:3]
        arrow = ("  [dim]→[/] " + ", ".join(n for _, n in tops)) if tops else ""
        ln = last_line.get(nd["name"])
        lref = f"  [dim]L{ln}[/]" if ln else ""
        console.print(f"  {nd['weight']:>5.2f}  [cyan]{nd['name']}[/] "
                      f"[dim]{nd['kind']} ×{nd['count']}[/]{arrow}{lref}")


@focus.command("export")
@click.option("-s", "--session", default=None,
              help="Session id to export. Default: active Claude session.")
@click.option("-o", "--out", type=click.Path(path_type=Path), default=None,
              help="Write to a file instead of stdout.")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSONL events.")
def focus_export(session, out, as_json):
    """Dump the FULL session focus log — every event, untrimmed. The ring file
    is never trimmed, so the complete context is always retrievable here."""
    s = _stm(session, prefer_latest=True)
    events = s.all_events()
    if as_json:
        text = "\n".join(json.dumps(e) for e in events)
    else:
        lines = [f"# focus log · session {s.session} · {len(events)} events", ""]
        # Line-numbered (1-based) so the L<n> refs in `focus context` resolve.
        for i, e in enumerate(events, 1):
            task = f" ({e['task']})" if e.get("task") else ""
            lines.append(f"{i:>5}: {e['ts']} [{e['kind']}]{task} {e.get('terse', '')}")
        text = "\n".join(lines)
    if out:
        Path(out).write_text(text + "\n")
        console.print(f"[green]exported[/] {len(events)} events → {out}")
    else:
        click.echo(text)


@focus.command("show")
@click.argument("line", type=int)
@click.option("-s", "--session", default=None,
              help="Session id. Default: active Claude session.")
@click.option("-C", "--context", "ctx", type=int, default=0,
              help="Also show ±N surrounding events.")
def focus_show(line, session, ctx):
    """Show the full event(s) at a log line (the L<n> refs in `focus context`)
    — untruncated terse + refs + task. -C N widens the window for depth."""
    s = _stm(session, prefer_latest=True)
    events = s.all_events()
    lo, hi = max(1, line - ctx), min(len(events), line + ctx)
    if line < 1 or line > len(events):
        console.print(f"[yellow]line {line} out of range[/] (1..{len(events)})")
        return
    for i in range(lo, hi + 1):
        e = events[i - 1]
        mark = "[bold]►[/]" if i == line else " "
        task = f" [dim]({e['task']})[/]" if e.get("task") else ""
        console.print(f"{mark} [dim]L{i}[/] [dim]{e['ts']}[/] [cyan]{e['kind']}[/]{task}")
        console.print(f"    {e.get('terse', '')}")
        if e.get("refs"):
            console.print(f"    [dim]refs: {', '.join(e['refs'])}[/]")


@focus.command("topics")
@click.option("--top", type=int, default=60, show_default=True,
              help="Graph nodes to cluster.")
@click.option("-s", "--session", default=None,
              help="Session id. Default: active Claude session.")
def focus_topics(top, session):
    """Cluster the session into topics — its distinct threads of work — as a
    timeline. Each topic shows its symbols + the L<n> range into the full log,
    so you can follow the session's evolution topically and drill via
    `focus show`."""
    from refmatrix import stm as stm_mod
    s = _stm(session, prefer_latest=True)
    g = s.focus_graph(top=top)
    # Cluster on the real symbols only (shell/path noise would merge topics).
    clean = {"nodes": [n for n in g["nodes"]
                       if n["name"].lower() not in _SS_FOCUS_NOISE],
             "edges": g["edges"]}
    clusters = stm_mod.cluster_focus(clean)
    if not clusters:
        console.print("[yellow]no topics yet[/]")
        return
    events = s.all_events()
    first_line: dict[str, int] = {}
    last_line: dict[str, int] = {}
    for i, e in enumerate(events, 1):
        for r in (e.get("refs") or []):
            first_line.setdefault(r, i)
            last_line[r] = i
    weight = {n["name"]: n["weight"] for n in g["nodes"]}
    # Order topics as a timeline by first appearance in the log.
    def span(c):
        ls = [first_line[n] for n in c if n in first_line]
        return min(ls) if ls else 10**9
    console.print(f"[bold]topics[/] · {g['events']} events · session {g['session']}")
    for c in sorted(clusters, key=span):
        members = sorted(c, key=lambda n: weight.get(n, 0), reverse=True)
        lines = [last_line[n] for n in c if n in last_line] + \
                [first_line[n] for n in c if n in first_line]
        rng = f"L{min(lines)}–L{max(lines)}" if lines else ""
        console.print(f"[bold]● {members[0]}[/] [dim]{rng}[/]")
        console.print(f"    [dim]{', '.join(members[:8])}[/]")


@focus.command("summarize")
@click.option("-s", "--session", default=None,
              help="Session id. Default: active Claude session.")
@click.option("--promote", is_flag=True,
              help="Write the digest to durable memory (the STM→LTM bridge).")
@click.option("--global", "is_global", is_flag=True,
              help="Promote to the shared cross-project global store.")
def focus_summarize(session, promote, is_global):
    """Condense the session's STM (topics + milestones + intent arc) into a
    compact digest. --promote writes it to durable memory so the transient
    focus graduates to LTM. Lighter than `save-state` (STM-only, no git/repo)."""
    s = _stm(session, prefer_latest=True)
    digest = _focus_digest(s)
    if not promote:
        click.echo(digest)
        return
    import re as _re
    slug = _re.sub(r"[^A-Za-z0-9]+", "", s.session)[:12] or "default"
    name = f"focus_summary_{slug}"
    args = {"name": name, "content": digest, "mtype": "session/digest",
            "tags": [f"session:{s.session}", "summary"],
            "metadata": {"title": f"Session summary {s.session[:8]}"},
            "protected": False}
    if is_global:
        from refmatrix import hub as hub_mod
        resp = hub_mod.global_call("memory_add", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        eid = resp["result"]["id"]
    else:
        from refmatrix import daemon as daemon_mod
        root = _root()
        if daemon_mod.ping(root):
            resp = _memory_daemon_call("memory_add", args)
            if not resp.get("ok"):
                raise click.ClickException(resp.get("error", "daemon error"))
            eid = resp["result"]["id"]
        else:
            eid = _store().add_memory(**args)
    console.print(f"[green]promoted[/] {name} (id={eid}) — recall with "
                  f"`rmx memory recall summary` or `rmx context {name}`")
    if not is_global:
        _file_under_active_subject(s, eid)


def _file_under_active_subject(s, leaf_eid: "int | None") -> None:
    """If the session has an active subject, file a just-promoted artifact
    under it (`part-of`) so the subject indexes it. Best-effort + quiet."""
    if not leaf_eid:
        return
    subj = s.get_subject()
    if not subj:
        return
    sid = _subject_upsert(subj.get("label") or subj.get("subject"))
    if sid:
        _subject_link(int(leaf_eid), int(sid))
        console.print(f"[dim]  filed under subject {subj.get('label')}[/]")


@focus.command("note")
@click.argument("text")
def focus_note(text):
    """Record a deliberate reasoning note into STM — the WHY behind a decision,
    a hypothesis, or a tradeoff. My extended-thinking blocks are redacted from
    the transcript, so this is the only reliable way the reasoning survives the
    session (see the briefing's 'Capture your reasoning' rule). Refs in the
    note enter the focus graph."""
    ev = _stm(prefer_latest=True).record("reason", text[:800])
    console.print(f"[blue]✎ noted[/]  [dim]{', '.join(ev['refs'][:6]) or '—'}[/]")


@focus.command("composite")
@click.option("--k", default=3, type=int, show_default=True,
              help="Max topic clusters to render.")
@click.option("--max-tokens", default=1200, type=int, show_default=True,
              help="Floor budget; autoscales up with session depth to a "
                   "ceiling unless --no-autoscale.")
@click.option("--no-expand", is_flag=True,
              help="STM focus only — skip long-term graph expansion.")
@click.option("--no-autoscale", is_flag=True,
              help="Fixed budget (disable session-depth autoscaling).")
def focus_composite(k, max_tokens, no_expand, no_autoscale):
    """Emit a GMD topic-composite subgraph of the current STM focus.

    Splits the session's focus graph — the running aggregate of every
    prompt+result — into its dominant topic threads and fuses each with its
    long-term graph neighborhood. This is the same block `scan-prompt` injects
    each turn; call it to pull the composite on demand."""
    from refmatrix.composite import build_topic_composite
    root = _root()

    def _run(s):
        return build_topic_composite(
            s, root, k=k, max_tokens=max_tokens,
            expand=not no_expand, autoscale=not no_autoscale)

    out = _replica_read(_run)
    if out:
        click.echo(out)
    else:
        console.print(
            "[dim]no STM topic composite "
            "(empty focus or no multi-node topic yet)[/]")


@focus.command("promote-edges")
@click.option("--min-weight", "min_w", type=float, default=None,
              help="Co-occurrence count a pair must reach to be promoted. "
                   "Default: RMX_PROMOTE_MIN_WEIGHT (3).")
@click.option("--max-edges", type=int, default=200, show_default=True,
              help="Cap per run. A focus graph of N nodes carries O(N^2) "
                   "edges; an unbounded run could bury the structural graph "
                   "in weak associations.")
@click.option("--session", default=None, help="Session id (default: latest).")
@click.option("--dry-run/--apply", "dry_run", default=True, show_default=True,
              help="Preview by default — this writes to the durable graph.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirm on --apply.")
def focus_promote_edges(min_w, max_edges, session, dry_run, yes):
    """Promote recurring STM co-occurrence into durable `co-occurs` edges.

    Every prompt's refs are already cliqued into the session's focus graph,
    with the pair weight bumped once per co-occurrence — so the working graph
    accumulates "these keep coming up together" and then throws it away when
    the session ends. This moves the pairs that recurred often enough into the
    long-term graph.

    `co-occurs` is deliberately its own verb, never `related-to`: that one is
    authored in GMD documents and carries editorial intent, and folding
    machine-derived co-occurrence into it would make a curated edge
    indistinguishable from an accident of phrasing. It is also purely
    associative, so it never touches the structural edges (`calls`, `defines`,
    `imports`) the symbolic retrieval floor is built on.

    Ranked by LIFT (`w / (freq_a * freq_b)`), not raw weight — raw weight
    crowns whatever file the workflow touches constantly (a version bump
    co-occurs with everything and means nothing).
    """
    args = {"dry_run": dry_run, "max_edges": max_edges, "sample": 20}
    if min_w is not None:
        args["threshold"] = min_w
    if session:
        args["session"] = session
    if not dry_run and not yes:
        click.confirm(
            "Write co-occurs edges into the durable graph?", abort=True)
    res = _memory_daemon_call("promote_edges", args, timeout=300.0)
    if not res.get("ok"):
        raise click.ClickException(res.get("error", "daemon error"))
    r = res["result"]
    n = r.get("promoted") or r.get("would_promote") or 0
    verb = "promoted" if not dry_run else "would promote"
    console.print(
        f"{verb} [bold]{n}[/] edge(s) "
        f"(threshold {r.get('threshold')}, "
        f"{r.get('skipped_below_threshold', 0)} below, "
        f"{r.get('skipped_ungated', 0)} unresolved/gated)"
    )
    for pair in r.get("pairs", [])[:20]:
        a, b, w = pair
        console.print(f"  [dim]w={w:>5}[/]  {a}  <->  {b}")


@focus.command("rebuild")
@click.option("--all", "all_rings", is_flag=True,
              help="Sweep every ring in the store's STM dir (not just the "
                   "active session).")
@click.option("--session", "session", default=None,
              help="Rebuild one ring by session/partition key (stem of its "
                   ".jsonl). Ignored when --all.")
@click.option("--root", "root_override", default=None,
              help="STM lives under <root>/stm. Defaults to this project's "
                   ".refmatrix. Pure file op — no daemon needed — so this can "
                   "target any store's rings.")
@click.option("--dry-run", is_flag=True,
              help="Report what WOULD be dropped without rewriting any graph.")
@click.option("--keep-ambient", is_flag=True,
              help="Do NOT drop ambient turns (hub/bus channel + notification "
                   "prompts). Default drops them.")
@click.option("--keep-junk", is_flag=True,
              help="Do NOT drop shape-junk refs (ids, hex, deep tmp paths). "
                   "Default drops them.")
def focus_rebuild(all_rings, session, root_override, dry_run,
                  keep_ambient, keep_junk):
    """Recompute focus graph(s) from the event ring, purging machine noise older
    ingests admitted — ambient turns (`<channel …>` hub/bus messages,
    system/task notifications recorded as `input`) and shape-junk refs. The ring
    is left intact (full provenance); only the maintained focus graph is
    rewritten. Use --all to remediate an entire store, --dry-run to preview."""
    from refmatrix import stm as stm_mod
    root = Path(root_override) if root_override else _root()
    d = stm_mod.stm_dir(root)
    if not d.is_dir():
        console.print(f"[dim]no STM at {d}[/]")
        return
    if all_rings:
        stems = sorted(
            p.stem for p in d.glob("*.jsonl") if not p.name.endswith(".tmp"))
    elif session:
        stems = [session]
    else:
        stems = [_resolve_stm_session(None, prefer_latest=True)]
    if not stems:
        console.print("[dim]no rings to rebuild[/]")
        return
    tag = "[yellow]DRY-RUN[/] " if dry_run else ""
    tot_ev = tot_amb = tot_ref = rewritten = 0
    for stem in stems:
        s = stm_mod.Stm(root, session=stem, subject="")
        st = s.rebuild_focus(
            drop_ambient=not keep_ambient, drop_junk=not keep_junk,
            dry_run=dry_run)
        tot_ev += st["events"]
        tot_amb += st["dropped_events"]
        tot_ref += st["dropped_refs"]
        if st["dropped_events"] or st["dropped_refs"]:
            rewritten += 1
            console.print(
                f"{tag}[cyan]{stem[:40]}[/]  events={st['events']} "
                f"[red]−{st['dropped_events']}amb[/] "
                f"[red]−{st['dropped_refs']}junk[/] "
                f"→ nodes={st['nodes']} edges={st['edges']}")
    verb = "would rewrite" if dry_run else "rewrote"
    console.print(
        f"{tag}[bold]{len(stems)} rings scanned[/] · {verb} {rewritten} · "
        f"events={tot_ev} dropped_ambient={tot_amb} dropped_junk={tot_ref}")


@focus.command("detour")
@click.argument("label", required=False)
def focus_detour(label):
    """Soft branch detour — bookmark the current focus before chasing a
    related-but-off-task tangent, so you can rewind to it with `focus return`.
    No git, no stash; just a focus return-point on the L-ref'd log."""
    m = _stm(prefer_latest=True).focus_mark(label or "")
    console.print(f"[magenta]⤴ detour[/] [bold]{m['label']}[/]  "
                  f"[dim]return-point at L{m['line']} · /return to rewind[/]")


@focus.command("detours")
@click.option("-s", "--session", default=None,
              help="Session id. Default: active Claude session.")
def focus_detours(session):
    """List open soft-detour return-points (most recent first)."""
    marks = _stm(session, prefer_latest=True).focus_marks()
    if not marks:
        console.print("[yellow]no open detours[/]")
        return
    for i, m in enumerate(reversed(marks), 1):
        console.print(f"[bold]{i}[/] {m['label']}  [dim]L{m.get('line')} · "
                      f"{m['ts']}[/]")


@focus.command("return")
@click.argument("selector", required=False)
def focus_return(selector):
    """Return from a soft detour — rewind focus to the bookmark. Default = most
    recent; SELECTOR (index from `focus detours` or label substring) returns
    from a specific detour. The tangent stays in the full log."""
    r = _stm(prefer_latest=True).focus_return(selector)
    if r["returned"] is None:
        console.print(f"[yellow]{r.get('error') or 'no open detours'}[/]")
        return
    console.print(f"[green]⤶ returned[/] from [bold]{r['returned']}[/] "
                  f"[dim](L{r.get('line')}, {r['remaining']} detour(s) left)[/]")
    if r.get("focus"):
        console.print(f"  [dim]focus: {', '.join(r['focus'][:8])}[/]")


@focus.command("clear")
def focus_clear():
    """Clear short-term memory + task stack for this session."""
    _stm().clear()
    console.print("[green]focus cleared[/]")


# ---- subjects (ADR-0002): a named STM partition + durable LTM container ----
def _subject_upsert(label: str) -> "int | None":
    """Upsert the durable subject node, daemon-or-inproc. Routes to the same
    partition as promoted digests so `part-of` edges resolve."""
    from refmatrix import daemon as daemon_mod
    if daemon_mod.ping(_root()):
        resp = _memory_daemon_call("subject_upsert", {"label": label})
        return resp.get("result", {}).get("id") if resp.get("ok") else None
    return _store().upsert_subject(label)["id"]


def _subject_link(leaf_id: int, subject_id: int) -> None:
    """File a leaf memory under a subject (part-of), daemon-or-inproc.
    Best-effort: a link failure never breaks the promote it rides on."""
    from refmatrix import daemon as daemon_mod
    try:
        if daemon_mod.ping(_root()):
            _memory_daemon_call(
                "subject_link", {"leaf_id": leaf_id, "subject_id": subject_id})
        else:
            _store().link_part_of(leaf_id, subject_id)
    except Exception:
        pass


@focus.command("change-subject")
@click.argument("label")
@click.option("-s", "--session", default=None,
              help="Session id. Default: active Claude session.")
def focus_change_subject(label, session):
    """Set the active SUBJECT — a named STM partition + durable LTM container
    for a thread of work. Focus events accrue to this subject; promoted
    digests / save-state handoffs file under it (`part-of`) so the thread is
    recallable across sessions. Idempotent for the same label."""
    s = _stm(session, prefer_latest=True)
    rec = s.set_subject(label)
    eid = _subject_upsert(label)
    console.print(
        f"[green]subject[/] {rec['label']} "
        f"[dim](slug={rec['subject']}, id={eid})[/] — focus scoped; "
        f"promotes file under it")


@focus.command("subject")
@click.option("-s", "--session", default=None,
              help="Session id. Default: active Claude session.")
def focus_subject(session):
    """Show the active subject for this session (or none)."""
    s = _stm(session, prefer_latest=True)
    cur = s.get_subject()
    if not cur:
        console.print("[yellow]no active subject[/] (bare session ring) — set one "
                      "with `rmx focus change-subject \"<label>\"`")
        return
    console.print(f"[bold]{cur.get('label')}[/]  [dim](slug={cur.get('subject')}, "
                  f"since {cur.get('ts')})[/]")


@focus.command("subjects")
def focus_subjects():
    """List durable subjects in this project (newest-active first) with leaf
    counts — the cross-session map of pursuits."""
    from refmatrix import daemon as daemon_mod
    if daemon_mod.ping(_root()):
        resp = _memory_daemon_call("subject_list", {})
        rows = resp.get("result", {}).get("rows", []) if resp.get("ok") else []
    else:
        rows = _store().list_subjects()
    if not rows:
        console.print("[yellow]no subjects yet[/] — `rmx focus change-subject "
                      "\"<label>\"`")
        return
    t = Table("subject", "leaves", "updated", "id")
    for r in rows:
        t.add_row(r.get("label") or r.get("name"), str(r.get("leaves", 0)),
                  str(r.get("updated_at") or ""), str(r.get("id")))
    console.print(t)


@focus.command("clear-subject")
@click.option("-s", "--session", default=None,
              help="Session id. Default: active Claude session.")
def focus_clear_subject(session):
    """Unset the active subject (revert to the bare session ring). The durable
    subject node + its filed leaves are untouched."""
    s = _stm(session, prefer_latest=True)
    had = s.clear_subject()
    console.print("[green]subject cleared[/]" if had
                  else "[yellow]no active subject[/]")


@focus.command("size")
@click.option("-s", "--session", default=None,
              help="Session id to read. Default: active Claude session.")
def focus_size(session):
    """Show the STM ring size + current event count."""
    s = _stm(session, prefer_latest=True)
    console.print(f"size={s.size}  events={len(s.all_events())}  "
                  f"session={s.session}  (set RMX_STM_SIZE to change)")


def _last_assistant_text(transcript_path: str) -> str:
    """Extract the most recent assistant message text from a Claude Code
    transcript JSONL. Each line is `{type, message:{role, content:[...]}}`;
    we want the last `type==assistant` with text blocks (tool-only turns are
    skipped). Returns collapsed whitespace, '' on any failure."""
    import re as _re
    try:
        lines = Path(transcript_path).read_text().splitlines()
    except OSError:
        return ""
    for ln in reversed(lines):
        try:
            d = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if d.get("type") != "assistant":
            continue
        msg = d.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
        else:
            text = ""
        text = _re.sub(r"\s+", " ", text).strip()
        if text:
            return text
    return ""


import re as _re_mod
# Mutating git ops are work milestones (commit/push/merge/...); read-only ones
# (status/log/diff/show) are noise and stay out.
_GIT_MILESTONE_RE = _re_mod.compile(
    r"(?:^|&&|\|\||;|\||\(|\n)\s*git\s+(?:-C\s+\S+\s+)?"
    r"(commit|push|merge|rebase|checkout|switch|tag|reset|revert|"
    r"cherry-pick|stash|pull|clone|init)\b")


def _git_milestone_subcmd(cmd: str) -> str | None:
    m = _GIT_MILESTONE_RE.search(cmd)
    return m.group(1) if m else None


def _tool_output_text(resp) -> str:
    """Flatten a PostToolUse tool_response to text (Bash → stdout+stderr)."""
    if isinstance(resp, dict):
        return ((resp.get("stdout") or "") + "\n"
                + (resp.get("stderr") or "")).strip()
    if isinstance(resp, str):
        return resp.strip()
    return ""


def _git_diff_summary(repo: str) -> "tuple[str, list[str]]":
    """(diffstat summary, changed files) for the just-created HEAD commit.
    Captured right after a milestone so the event carries WHAT changed; the
    changed files become refs so they enter the focus graph as real signal."""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "-C", repo, "show", "--stat", "--format=", "HEAD"],
            capture_output=True, text=True, timeout=5)
    except Exception:
        return "", []
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    summary = lines[-1].strip() if lines and "changed" in lines[-1] else ""
    files = [ln.split("|")[0].strip() for ln in lines if "|" in ln]
    return summary, files[:10]


# Line comments the codebase actually uses. `--` would collide with diff
# metadata, so SQL comments are matched only with following whitespace.
_COMMENT_RE = _re_mod.compile(r"^\+\s*(#|//|\*|--\s)")
# Comment lines that carry no rationale: directives, noqa pragmas, shebangs,
# and section rules like `# ----------`.
_COMMENT_NOISE_RE = _re_mod.compile(
    r"^(#!|#\s*(type:|noqa|pragma|pylint|ruff|fmt:|isort:|-{3,}|={3,})"
    r"|//\s*(eslint|@ts-|prettier))"
)


def _git_commit_rationale(repo: str) -> str:
    """The commit message BODY (everything after the subject line).

    The densest rationale an agent produces, and structurally mandatory — it
    gets written to finish the task, not because someone asked for memory.
    `_git_diff_summary`'s sibling event kept only the subject (the first line
    of `git commit` output), discarding exactly the part that says WHY."""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "-C", repo, "log", "-1", "--format=%B", "HEAD"],
            capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    parts = (r.stdout or "").split("\n", 1)
    body = parts[1].strip() if len(parts) > 1 else ""
    # Drop trailers (Co-Authored-By, Signed-off-by, …) — provenance, not why.
    keep = [ln for ln in body.splitlines()
            if not _re_mod.match(r"^[A-Z][A-Za-z-]+-[Bb]y:\s", ln.strip())]
    return "\n".join(keep).strip()


def _git_added_comments(repo: str, limit: int = 12) -> "tuple[list[str], list[str]]":
    """(rendered `file: comment` lines, files that gained them) for HEAD.

    Where the LOCAL why lives: a comment sits next to the code it explains, and
    in this codebase writing one is near-mandatory by style. Mined from the
    diff rather than requested, so it costs no new discipline."""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "-C", repo, "show", "--unified=0", "--no-color",
             "--format=", "HEAD"],
            capture_output=True, text=True, timeout=5)
    except Exception:
        return [], []
    out: list[str] = []
    files: list[str] = []
    cur = ""
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("+++ b/"):
            cur = ln[6:].strip()
            continue
        if not _COMMENT_RE.match(ln):
            continue
        text = ln[1:].strip().lstrip("#/*- ").strip()
        if not text or _COMMENT_NOISE_RE.match(ln[1:].strip()):
            continue
        if len(text) < 12:      # `ok`, `TODO`, closing markers — no rationale
            continue
        out.append(f"{cur}: {text}" if cur else text)
        if cur and cur not in files:
            files.append(cur)
        if len(out) >= limit:
            break
    return out, files[:10]


def _is_ambient_prompt(text: str) -> bool:
    """True for machine-injected turns that are NOT user intent: hub/bus channel
    messages (`<channel …>`) and system/task notifications. Claude Code delivers
    these as 'user' prompts in the UserPromptSubmit envelope, but they carry no
    topical signal — recording them pollutes the STM focus graph (and every
    downstream topic composite), so the input hook skips them."""
    t = (text or "").lstrip()
    return (
        t.startswith("<channel")
        or t.startswith("<task-notification")
        or t.startswith("[SYSTEM NOTIFICATION")
    )


def _tool_call_key(d: dict) -> str:
    """Stable id pairing a PreToolUse with its PostToolUse. Prefers the
    harness-supplied tool_use_id; falls back to a hash of (tool, input) so the
    pairing still works on envelopes that omit it."""
    tid = d.get("tool_use_id") or d.get("toolUseId")
    if isinstance(tid, str) and tid:
        return tid
    import hashlib
    raw = json.dumps(
        [d.get("tool_name"), d.get("tool_input")], sort_keys=True, default=str)
    return "h:" + hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _tool_event_fields(d: dict) -> tuple[str, list[str], str | None]:
    """(terse, refs, detail) for one tool envelope — shared by the pre and post
    hooks so a parked call and its completion describe themselves identically.

    `refs` is the graph-facing token set (file paths only, explicitly passed so
    `record()` never ref-extracts a whole command line). `detail` is the
    verbatim action — the command string, the grep pattern — which `terse`
    drops as soon as any path ref is extractable."""
    tool = d.get("tool_name") or "tool"
    ti = d.get("tool_input") or {}
    refs: list[str] = []
    fp = ti.get("file_path")
    if isinstance(fp, str):
        refs.append(fp)
    for e in (ti.get("edits") or []):
        if isinstance(e, dict) and isinstance(e.get("file_path"), str):
            refs.append(e["file_path"])
    cmd = ti.get("command")
    if not refs and isinstance(cmd, str):
        from refmatrix import stm as _stm_mod
        refs = [m for m in _stm_mod._PATH_RE.findall(cmd)
                if ("/" in m or "." in m)][:8]
    if isinstance(cmd, str) and cmd.strip():
        detail = cmd.strip()
    elif isinstance(ti, dict) and ti:
        # Grep/Read/Glob and friends: keep the structured input, minus bulk
        # payloads that would swamp the ring.
        slim = {k: v for k, v in ti.items()
                if k not in ("content", "new_string", "old_string", "edits")}
        detail = json.dumps(slim, default=str) if slim else None
    else:
        detail = None
    terse = f"{tool} {' '.join(refs) or (cmd or '')}".strip()[:300]
    return terse, refs, detail


@focus.command("hook")
@click.option("--event",
              type=click.Choice(["input", "tool", "tool-pre", "say"]),
              required=True, help="Which Claude Code hook is firing.")
def focus_hook(event):
    """Record a short-term event from a Claude Code hook envelope on stdin.

    UserPromptSubmit → --event input; PreToolUse → --event tool-pre;
    PostToolUse → --event tool; Stop → --event say (records my last assistant
    message so STM holds the full dialogue, not just the user's half).

    `tool-pre` parks the call in a sidecar instead of appending to the ring —
    the matching `tool` clears it, and anything still parked at the next
    `input` is folded in as an `abandoned` event. That is the only way a tool
    call which hung, was denied, or killed the session reaches the timeline. The session id from the envelope
    groups STM per Claude session. Silent + best-effort: a malformed/empty
    envelope is a no-op exit 0 so the hook never blocks."""
    from refmatrix import stm as stm_mod
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    session = d.get("session_id") or stm_mod.session_id()
    s = stm_mod.Stm(_root(), session)
    if event == "tool-pre":
        terse, refs, detail = _tool_event_fields(d)
        s.inflight_begin(_tool_call_key(d), terse=terse, refs=refs,
                         detail=detail)
        return
    if event == "input":
        # Top of a turn: anything still parked from the previous one never
        # completed. Fold it in before recording the new prompt so the
        # abandoned call sits in front of it on the timeline.
        try:
            s.inflight_sweep()
        except Exception:
            pass
        prompt = (d.get("prompt") or "").strip()
        if prompt and not _is_ambient_prompt(prompt):
            s.record("input", prompt[:300])
    elif event == "say":
        # Stop hook: capture my reply from the transcript. refs=[] keeps it
        # text-only (visible in the intent thread) without admitting prose
        # tokens into the focus graph.
        text = _last_assistant_text(d.get("transcript_path") or "")
        if text:
            s.record("say", text[:300], refs=[])
    else:
        s.inflight_end(_tool_call_key(d))
        terse, refs, detail = _tool_event_fields(d)
        tool = d.get("tool_name") or "tool"
        ti = d.get("tool_input") or {}
        cmd = ti.get("command")
        # Git milestones: capture the op + its output line as a `git` event —
        # the work narrative's anchors (committed X, pushed Y, merged Z).
        sub = _git_milestone_subcmd(cmd) if isinstance(cmd, str) else None
        if sub:
            out = _tool_output_text(d.get("tool_response"))
            first = next((ln for ln in out.splitlines() if ln.strip()), "")
            terse = f"git {sub}: {first}".strip()
            diff_refs: list[str] = []
            # Capture the diffstat right after a content-changing milestone so
            # the event records WHAT changed; the changed files become refs.
            if sub in ("commit", "merge", "cherry-pick", "revert"):
                repo = d.get("cwd") or str(_root().parent)
                stat, diff_refs = _git_diff_summary(repo)
                if stat:
                    terse = f"{terse}  [{stat}]"
            # detail carries the verbatim git invocation — `terse` holds only
            # the subcommand + its first output line.
            s.record("git", terse[:300], refs=diff_refs, detail=detail)
            # Harvest the WHY from the two channels that are already mandatory,
            # rather than asking the agent to volunteer it (a `focus note` the
            # agent must remember to call is, empirically, not called). A merge
            # is skipped: its body is generated, not authored.
            if sub in ("commit", "cherry-pick", "revert"):
                repo = d.get("cwd") or str(_root().parent)
                body = _git_commit_rationale(repo)
                if body:
                    head = body.splitlines()[0].strip()
                    s.record("reason", f"why {sub}: {head}"[:300],
                             refs=diff_refs, detail=body)
                comments, cfiles = _git_added_comments(repo)
                if comments:
                    s.record(
                        "reason",
                        f"comments added ({len(comments)}): "
                        f"{comments[0]}"[:300],
                        refs=cfiles or diff_refs,
                        detail="\n".join(comments),
                    )
            return
        s.record("tool", terse, refs=refs, detail=detail)


@main.group()
def task():
    """Pushdown task stack — track interrupted work when tangents get
    explored. Push snapshots the current focus; pop restores it."""


@task.command("push")
@click.argument("desc")
def task_push(desc):
    """Push a task (snapshots current focus)."""
    # prefer_latest so a plain-shell push lands in the SAME session ring the
    # readers (`list`/`current`) resolve to — otherwise push writes the bare
    # "default" session while list reads the active Claude session and the
    # stack looks empty across invocations.
    r = _stm(prefer_latest=True).task_push(desc)
    console.print(f"[green]▸[/] {r['current']}  [dim]depth={r['depth']}[/]")


@task.command("pop")
@click.argument("selector", required=False)
def task_pop(selector):
    """Pop a stash and restore ITS focus (git-stash semantics). Default = top;
    SELECTOR (a 1-based index from `task list`, or a desc substring) pops out
    of order."""
    r = _stm(prefer_latest=True).task_pop(selector)
    if r["popped"] is None:
        msg = r.get("error") or "task stack empty"
        console.print(f"[yellow]{msg}[/]")
        return
    console.print(f"[green]✓[/] resumed: {r['popped']}  [dim]depth={r['depth']}[/]")
    if r.get("restored_focus"):
        console.print(f"  [dim]focus: {', '.join(r['restored_focus'][:8])}[/]")


@task.command("list")
@click.option("-s", "--session", default=None,
              help="Session id to read. Default: active Claude session.")
def task_list(session):
    """Show the stash stack with 1-based indices (top = 1 = most recent)."""
    stack = _stm(session, prefer_latest=True).task_list()
    if not stack:
        console.print("[yellow]no tasks[/]")
        return
    for i, t in enumerate(reversed(stack), 1):
        marker = "[green]▸[/]" if i == 1 else " "
        console.print(f"{marker} [bold]{i}[/] {t['desc']}  [dim]{t['ts']}[/]")


@task.command("current")
@click.option("-s", "--session", default=None,
              help="Session id to read. Default: active Claude session.")
def task_current(session):
    """Show the current (top) task."""
    t = _stm(session, prefer_latest=True).task_current()
    console.print(t["desc"] if t else "[yellow](none)[/]")


@task.command("swap")
def task_swap():
    """Swap the top two tasks."""
    r = _stm(prefer_latest=True).task_swap()
    console.print(f"[green]current:[/] {r['current']}" if r["swapped"]
                  else "[yellow]need ≥2 tasks to swap[/]")


@main.group()
def bus():
    """Agent message bus (hub-hosted). Intra-project (proj:<name>:<topic>) +
    inter-project (global:<topic>) pub/sub for live agent coordination."""


def _require_hub():
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        raise click.ClickException("hub not running — start it with `rmx hub start`")
    return hub_mod


@main.group("refine")
def refine_grp():
    """Review promotion candidates queued from the bus + the GMD curator.

    Candidates accumulate in the hub's refinement queue and are what the
    `global:queues` alert counts as `refinement_pending`. Accepting one writes
    the suggested memory into its scope's store (daemon-routed); rejecting
    drops it. Both are terminal — a candidate leaves `pending` either way.
    """


def _refine_rows(status: str) -> list[dict]:
    hub_mod = _require_hub()
    resp = hub_mod.rpc("refine_list", {"status": status})
    return resp.get("result", {}).get("candidates", [])


def _refine_pick(cand_id: str, rows: list[dict]) -> dict:
    """Resolve an id or unambiguous id-prefix to one candidate. Ids are 12-char
    hex, so typing the whole thing to reject a line noise entry is a chore —
    but a prefix that matches two candidates must NOT silently pick one, since
    accept writes a memory."""
    exact = [c for c in rows if c["id"] == cand_id]
    if exact:
        return exact[0]
    hits = [c for c in rows if c["id"].startswith(cand_id)]
    if not hits:
        raise click.ClickException(f"no candidate matching {cand_id!r}")
    if len(hits) > 1:
        ids = ", ".join(c["id"] for c in hits[:5])
        raise click.ClickException(
            f"{cand_id!r} matches {len(hits)} candidates: {ids}")
    return hits[0]


@refine_grp.command("list")
@click.option("--status", default="pending", show_default=True,
              type=click.Choice(["pending", "accepted", "rejected", "all"]))
@click.option("--scope", type=click.Choice(["global", "project"]), default=None,
              help="Only candidates targeting this scope.")
@click.option("--project", default=None, help="Only candidates for this project.")
@click.option("-n", "limit", type=int, default=20, show_default=True)
@click.option("--full", is_flag=True, help="Show the whole suggested body.")
@click.option("--json", "as_json", is_flag=True)
def refine_list(status, scope, project, limit, full, as_json):
    """List promotion candidates, oldest first."""
    rows = _refine_rows(status)
    if scope:
        rows = [c for c in rows if c.get("scope") == scope]
    if project:
        rows = [c for c in rows if c.get("project") == project]
    total = len(rows)
    shown = rows[:limit] if limit and limit > 0 else rows
    if as_json:
        console.print_json(json.dumps(
            {"candidates": shown, "total": total, "shown": len(shown)}))
        return
    if not rows:
        console.print(f"[dim]no {status} candidates[/]")
        return
    from rich.table import Column
    # The id must never be truncated — it is the argument you paste into
    # `refine accept`. Let the suggested-body column absorb the squeeze.
    t = Table(
        Column("id", no_wrap=True), Column("when", no_wrap=True),
        Column("scope", no_wrap=True), Column("mtype", no_wrap=True),
        # `suggested` stays wrappable: marking it no_wrap makes rich hand it
        # the whole width and squeeze the id down to an ellipsis.
        Column("suggested"),
    )
    for c in shown:
        sug = c.get("suggested") or {}
        body = (sug.get("content") or "").replace("\n", " ")
        if not full:
            body = body[:70] + ("…" if len(body) > 70 else "")
        t.add_row(
            c["id"], (c.get("ts") or "")[:16],
            c.get("project") or c.get("scope") or "?",
            sug.get("mtype") or "",
            f"{sug.get('name', '?')} — {body}",
        )
    console.print(t)
    if len(shown) < total:
        # Never let a -n cap read as "that is all there is".
        console.print(f"[dim]showing {len(shown)} of {total}; -n 0 for all[/]")


@refine_grp.command("show")
@click.argument("cand_id")
def refine_show(cand_id):
    """Show one candidate in full, including the body that would be written."""
    c = _refine_pick(cand_id, _refine_rows("all"))
    sug = c.get("suggested") or {}
    console.print(f"[bold]{c['id']}[/]  [dim]{c.get('ts', '')}[/]  "
                  f"status=[magenta]{c.get('status')}[/]")
    console.print(f"  scope={c.get('scope')} project={c.get('project')} "
                  f"channel={c.get('channel')} origin={c.get('origin')}")
    console.print(f"  → memory [bold]{sug.get('name')}[/] "
                  f"mtype={sug.get('mtype')} tags={sug.get('tags') or []}")
    if c.get("memory_id"):
        console.print(f"  written as entity {c['memory_id']}")
    console.print()
    console.print(sug.get("content") or "[dim](no body)[/]")


@refine_grp.command("accept")
@click.argument("cand_ids", nargs=-1, required=True)
def refine_accept(cand_ids):
    """Promote candidates into memories. Writes are daemon-routed."""
    rows = _refine_rows("all")
    ok = 0
    for raw in cand_ids:
        c = _refine_pick(raw, rows)
        hub_mod = _require_hub()
        resp = hub_mod.rpc("refine_accept", {"id": c["id"]})
        r = resp.get("result") or {}
        if r.get("ok"):
            ok += 1
            sug = c.get("suggested") or {}
            console.print(f"[green]accepted[/] {c['id']} → "
                          f"{sug.get('name')} (entity {r.get('memory_id')})")
        else:
            # Report per-candidate and keep going: a batch that dies on the
            # first already-accepted id would strand the rest.
            console.print(f"[red]failed[/] {c['id']}: "
                          f"{r.get('error', 'unknown error')}")
    console.print(f"[dim]{ok}/{len(cand_ids)} accepted[/]")


@refine_grp.command("reject")
@click.argument("cand_ids", nargs=-1, required=True)
def refine_reject(cand_ids):
    """Drop candidates without writing a memory."""
    rows = _refine_rows("all")
    ok = 0
    for raw in cand_ids:
        c = _refine_pick(raw, rows)
        hub_mod = _require_hub()
        resp = hub_mod.rpc("refine_reject", {"id": c["id"]})
        r = resp.get("result") or {}
        if r.get("ok"):
            ok += 1
            console.print(f"[yellow]rejected[/] {c['id']}")
        else:
            console.print(f"[red]failed[/] {c['id']}: "
                          f"{r.get('error', 'unknown error')}")
    console.print(f"[dim]{ok}/{len(cand_ids)} rejected[/]")


@bus.command("pub")
@click.argument("channel")
@click.argument("message")
@click.option("--type", "mtype", default="announce",
              type=click.Choice(["announce", "decision", "request", "reply", "note"]),
              help="Message type. announce/decision feed the refinement queue.")
@click.option("--from", "sender", default=None, help="Agent id (default: $RMX_AGENT or host).")
@click.option("--reply-to", default=None, help="Message id this replies to.")
def bus_pub(channel, message, mtype, sender, reply_to):
    """Publish a message to a channel."""
    hub_mod = _require_hub()
    import socket as _s
    sender = sender or os.environ.get("RMX_AGENT") or _s.gethostname()
    project = None
    if channel.startswith("proj:"):
        parts = channel.split(":")
        project = parts[1] if len(parts) > 1 else None
    resp = hub_mod.rpc("bus_pub", {
        "channel": channel, "body": message, "type": mtype,
        "from": sender, "project": project, "reply_to": reply_to,
    })
    if not resp.get("ok"):
        raise click.ClickException(resp.get("error", "bus error"))
    console.print(f"[green]published[/] {resp['result']['message']['id']} → {channel}")


@bus.command("sub")
@click.argument("channels", nargs=-1, required=True)
@click.option("--history", "-H", type=int, default=0,
              help="Replay the last N messages before streaming (single exact channel).")
def bus_sub(channels, history):
    """Subscribe and stream messages (Ctrl-C to stop). Patterns: exact,
    `prefix:` or `prefix*`, or `*` for everything."""
    hub_mod = _require_hub()
    console.print(f"[dim]subscribed to {', '.join(channels)} — Ctrl-C to stop[/]")
    try:
        for m in hub_mod.subscribe_stream(list(channels), history=history):
            who = m.get("from", "?")
            proj = f" [{m['project']}]" if m.get("project") else ""
            console.print(f"[dim]{m['ts']}[/] [cyan]{m['channel']}[/] "
                          f"[bold]{who}[/]{proj} [magenta]{m['type']}[/]: {m['body']}")
    except KeyboardInterrupt:
        console.print("\n[dim]unsubscribed[/]")
    except (ConnectionError, OSError) as e:
        raise click.ClickException(f"bus connection lost: {e}")


@bus.command("channels")
def bus_channels():
    """List channels with message counts."""
    hub_mod = _require_hub()
    resp = hub_mod.rpc("bus_channels")
    chans = resp.get("result", {}).get("channels", [])
    if not chans:
        console.print("[yellow]no channels yet[/]")
        return
    t = Table("channel", "messages")
    for c in chans:
        t.add_row(c["channel"], str(c["messages"]))
    console.print(t)


@bus.command("history")
@click.argument("channel")
@click.option("-n", type=int, default=20, show_default=True)
@click.option("--status", default="active", show_default=True,
              type=click.Choice(["active", "archived", "deleted", "all"]),
              help="Which lifecycle state to show.")
def bus_history(channel, n, status):
    """Show the last N messages on a channel."""
    hub_mod = _require_hub()
    resp = hub_mod.rpc("bus_history", {"channel": channel, "n": n, "status": status})
    for m in resp.get("result", {}).get("messages", []):
        who = m.get("from", "?")
        console.print(f"[dim]{m['ts']}[/] [bold]{who}[/] [magenta]{m['type']}[/] "
                      f"[dim]#{m['id']}[/]: {m['body']}")


def _bus_agent(explicit):
    import socket as _s
    return explicit or os.environ.get("RMX_AGENT") or _s.gethostname()


@bus.command("read")
@click.argument("channels", nargs=-1)
@click.option("--from", "agent", default=None,
              help="Agent whose read-cursor to use (default: $RMX_AGENT or host).")
@click.option("--peek", is_flag=True, help="Show unread WITHOUT advancing the cursor.")
@click.option("-n", type=int, default=None, help="Cap messages returned (oldest-first).")
def bus_read(channels, agent, peek, n):
    """Show messages you haven't read yet across matching channels, advancing
    your cursor (unless --peek). Default pattern: * (all channels)."""
    hub_mod = _require_hub()
    agent = _bus_agent(agent)
    resp = hub_mod.rpc("bus_read", {"agent": agent, "channels": list(channels) or ["*"],
                                    "peek": peek, "n": n})
    msgs = resp.get("result", {}).get("messages", [])
    if not msgs:
        console.print("[dim]no unread messages[/]")
        return
    for m in msgs:
        who = m.get("from", "?")
        proj = f" [{m['project']}]" if m.get("project") else ""
        console.print(f"[dim]{m['ts']}[/] [cyan]{m['channel']}[/] [bold]{who}[/]{proj} "
                      f"[magenta]{m['type']}[/] [dim]#{m['id']}[/]: {m['body']}")
    tail = " (peek — cursor unchanged)" if peek else ""
    console.print(f"[dim]{len(msgs)} message(s){tail}[/]")


@bus.command("mark-read")
@click.argument("channel")
@click.option("--from", "agent", default=None, help="Agent whose cursor to set.")
@click.option("--upto-seq", type=int, default=None,
              help="Cursor position; default = channel max (mark everything read).")
def bus_mark_read(channel, agent, upto_seq):
    """Mark a channel read up to a point (default: everything)."""
    hub_mod = _require_hub()
    resp = hub_mod.rpc("bus_mark_read", {"agent": _bus_agent(agent),
                                         "channel": channel, "upto_seq": upto_seq})
    r = resp.get("result", {})
    console.print(f"[green]marked read[/] {channel} → seq {r.get('last_seq')}")


@bus.command("delete")
@click.argument("msg_id")
def bus_delete(msg_id):
    """Soft-delete a message by id (hidden from history/read, recoverable until purge)."""
    hub_mod = _require_hub()
    r = hub_mod.rpc("bus_delete", {"id": msg_id}).get("result", {})
    if r.get("deleted"):
        console.print(f"[green]deleted[/] {msg_id}")
    else:
        console.print(f"[yellow]not found or already deleted[/] {msg_id}")


@bus.command("archive")
@click.option("--id", "msg_id", default=None, help="Archive a single message by id.")
@click.option("--channel", default=None, help="Archive a whole channel.")
@click.option("--before", default=None,
              help="With --channel: only messages with ts < this ISO stamp.")
def bus_archive(msg_id, channel, before):
    """Move messages to the archive (still readable via `history --status archived`)."""
    hub_mod = _require_hub()
    r = hub_mod.rpc("bus_archive", {"id": msg_id, "channel": channel,
                                    "before_ts": before}).get("result", {})
    if not r.get("ok"):
        raise click.ClickException(r.get("error", "archive error"))
    console.print(f"[green]archived[/] {r.get('archived', 0)} message(s)")


@bus.command("unarchive")
@click.argument("msg_id")
def bus_unarchive(msg_id):
    """Restore an archived message to active."""
    hub_mod = _require_hub()
    r = hub_mod.rpc("bus_unarchive", {"id": msg_id}).get("result", {})
    console.print(f"[green]restored[/] {msg_id}" if r.get("restored")
                  else f"[yellow]not archived[/] {msg_id}")


@bus.command("purge")
@click.option("--status", default="deleted", show_default=True,
              type=click.Choice(["deleted", "archived", "all"]),
              help="Which rows to hard-remove.")
@click.option("--channel", default=None)
@click.option("--before", default=None, help="Only rows with ts < this ISO stamp.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation.")
def bus_purge(status, channel, before, yes):
    """Hard-remove messages — the only destructive path. Default reaps soft-deleted."""
    if not yes:
        scope = f"status={status}"
        if channel:
            scope += f" channel={channel}"
        if before:
            scope += f" before={before}"
        click.confirm(f"purge {scope}?", abort=True)
    hub_mod = _require_hub()
    r = hub_mod.rpc("bus_purge", {"status": status, "channel": channel,
                                  "before_ts": before}).get("result", {})
    console.print(f"[green]purged[/] {r.get('purged', 0)} row(s)")


@bus.command("stats")
@click.option("--from", "agent", default=None,
              help="Include unread counts for this agent (default: $RMX_AGENT or host).")
def bus_stats(agent):
    """Per-status totals + per-channel breakdown (+ unread counts)."""
    hub_mod = _require_hub()
    r = hub_mod.rpc("bus_stats", {"agent": _bus_agent(agent)}).get("result", {})
    totals = r.get("totals", {})
    console.print("[bold]totals[/] " +
                  (", ".join(f"{k}={v}" for k, v in totals.items()) or "empty"))
    unread = r.get("unread", {})
    t = Table("channel", "active", "archived", "deleted", "unread")
    for c in r.get("channels", []):
        t.add_row(c["channel"], str(c["messages"]), str(c.get("archived", 0)),
                  str(c.get("deleted", 0)), str(unread.get(c["channel"], 0)))
    console.print(t)


@main.command("mcp")
def mcp_cmd():
    """Run the refmatrix MCP server over stdio. Configure in Claude Code as an
    MCP server with command `rmx mcp` — Claude then calls where/context/
    memory_recall/query/bus/queues/focus as native tools."""
    from refmatrix.mcp import serve_stdio
    serve_stdio()


@main.group()
def schedule():
    """Per-project scheduled maintenance, run by the hub (sync/embed/vacuum/
    checkpoint/ingest on an interval). Config: ~/.refmatrix/schedule.json."""


@schedule.command("add")
@click.argument("op", type=click.Choice(["sync", "embed", "vacuum", "checkpoint", "ingest", "curator-scan"]))
@click.option("--every", "every", required=True,
              help="Interval, e.g. 30m / 2h / 1d.")
def schedule_add(op, every):
    """Schedule OP for the current project every <interval>."""
    from refmatrix import scheduler as sch
    secs = _parse_duration(every)
    if not secs:
        raise click.ClickException(f"bad interval: {every}")
    sch.add_job(_root(), op, int(secs))
    console.print(f"[green]scheduled[/] {op} every {every} for {_root().parent.name}")


@schedule.command("list")
def schedule_list():
    """Show all scheduled jobs across projects."""
    from refmatrix import scheduler as sch
    data = sch.load_schedule()
    if not data:
        console.print("[yellow]no scheduled jobs[/]")
        return
    t = Table("project", "op", "every (s)")
    for root, ops in data.items():
        for op, interval in ops.items():
            t.add_row(Path(root).parent.name, op, str(interval))
    console.print(t)


@schedule.command("remove")
@click.argument("op")
def schedule_remove(op):
    """Remove a scheduled OP for the current project."""
    from refmatrix import scheduler as sch
    if sch.remove_job(_root(), op):
        console.print(f"[green]removed[/] {op}")
    else:
        console.print(f"[yellow]no such job:[/] {op}")


@main.group()
def hub():
    """User-level control plane: supervises every per-project daemon
    (watchdog/restart), aggregates status + usage, owns the global memory
    store, and serves the web UI. One hub per machine."""


@hub.command("start")
@click.option("--port", type=int, default=None, help="HTTP port (default 7777).")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--no-detach", is_flag=True,
              help="Run in the foreground (for launchd / debugging).")
@click.option("--no-http", is_flag=True,
              help="Supervise headless; don't serve the web UI.")
def hub_start(port, host, no_detach, no_http):
    """Start the hub (idempotent)."""
    from refmatrix import hub as hub_mod
    port = port or hub_mod.DEFAULT_PORT
    if no_detach:
        hub_mod.Hub(port=port).run(host=host, serve_http=not no_http)
        return
    if hub_mod.is_running():
        console.print(f"[yellow]hub already running[/] pid={hub_mod.hub_pid()}")
        return
    # A foreign process on the port (orphaned uvicorn from a hub whose control
    # socket died) blocks startup — uvicorn can't bind, the hub self-stops, and
    # the user sees a confusing "started then gone". Catch it before spawning.
    orphan = hub_mod._pid_on_port(port)
    if orphan:
        console.print(f"[red]port {port} is held by pid {orphan}[/] but no live "
                      f"hub answers — run `rmx hub stop` to reap it, then retry")
        return
    pid = hub_mod.spawn_hub(port=port, host=host)
    if hub_mod.is_running():
        console.print(f"[green]hub started[/] pid={pid} http://{host}:{port}")
    else:
        console.print(f"[red]hub failed to start[/] (see {hub_mod.hub_log_path()})")


@hub.command("stop")
def hub_stop():
    """Stop the hub."""
    from refmatrix import hub as hub_mod
    if hub_mod.stop_hub():
        console.print("[green]hub stopped[/]")
    else:
        console.print("[yellow]hub did not stop cleanly[/]")


@hub.group("launchctl")
def hub_launchctl():
    """Supervise the hub itself via macOS launchd (com.refmatrix.hub).
    RunAtLoad + KeepAlive: auto-start at login, restart on crash."""


@hub_launchctl.command("install")
@click.option("--port", type=int, default=7777, show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--force", is_flag=True)
def hub_launchctl_install(port, host, force):
    """Install + load the hub LaunchAgent."""
    from refmatrix import launchctl
    try:
        p = launchctl.install_hub(port=port, host=host, force=force)
    except Exception as e:
        raise click.ClickException(str(e))
    console.print(f"[green]hub supervised[/] {launchctl.HUB_LABEL}\n[dim]{p}[/]")


@hub_launchctl.command("uninstall")
def hub_launchctl_uninstall():
    """Unload + remove the hub LaunchAgent."""
    from refmatrix import launchctl
    if launchctl.uninstall_hub():
        console.print("[green]hub LaunchAgent removed[/]")
    else:
        console.print("[yellow]no hub LaunchAgent to remove[/]")


@hub_launchctl.command("status")
def hub_launchctl_status():
    """Show hub LaunchAgent status."""
    from refmatrix import launchctl
    st = launchctl.hub_status()
    dot = "[green]●[/]" if st["loaded"] else "[red]●[/]"
    console.print(f"{dot} {st['label']}  installed={st['installed']} "
                  f"loaded={st['loaded']}")
    console.print(f"[dim]{st['plist_path']}[/]")


@hub.command("status")
def hub_status():
    """Show hub + supervised-store health."""
    from refmatrix import hub as hub_mod
    st = hub_mod.status()
    if not st["running"]:
        console.print("[yellow]hub not running[/]")
        console.print(f"[dim]start with `rmx hub start` ({st['sock']})[/]")
        return
    console.print(f"[green]hub running[/] pid={st.get('pid')} "
                  f"port={st.get('port')} registry={st.get('registry_size')}")
    resp = hub_mod.rpc("health")
    if resp.get("ok"):
        health = resp["result"]["health"]
        if not health:
            console.print("[dim]no health samples yet[/]")
        for root, h in health.items():
            last = h["history"][-1] if h["history"] else {}
            dot = "[green]●[/]" if last.get("up") else "[red]●[/]"
            console.print(f"  {dot} {root}  policy={h['policy']} "
                          f"restarts={h['restart_count']}")


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
@click.option(
    "--standalone", is_flag=True,
    help="Always fork a standalone daemon, even if a launchd LaunchAgent "
         "supervises this store. By default a supervised store defers to "
         "launchd (kickstart) so it doesn't spawn an unsupervised orphan.",
)
def daemon_start(watch: bool, watch_roots: tuple[Path, ...], debounce_ms: int,
                 semantic: bool, no_detach: bool, standalone: bool):
    """Start the rmx daemon for the active store. Idempotent: re-running
    while a daemon is already up is a fast no-op (returns its pid).

    Supervision-aware: if a launchd LaunchAgent is loaded for this store,
    a detached start defers to launchd (`launchctl kickstart`) instead of
    forking a standalone daemon, so it never spawns an unsupervised orphan
    that races the supervisor during a crash window. Pass --standalone to
    force a standalone fork anyway, or --no-detach for the foreground
    entrypoint launchd itself invokes."""
    import sys as _sys
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

    # Detached start. If launchd actively supervises this store, hand the
    # lifecycle to it rather than forking an orphan it doesn't own. macOS
    # only; --standalone forces the fork regardless.
    if not standalone and _sys.platform == "darwin":
        from refmatrix import launchctl as lc
        try:
            loaded = lc.is_loaded(root)
            installed = lc.is_installed(root)
        except Exception:  # noqa: BLE001 — supervision probe is best-effort
            loaded = installed = False
        if loaded:
            # A supervised daemon's watch config lives in the plist; flag
            # start-time watch options that would be silently ignored.
            if watch_roots or semantic or debounce_ms != 500 or not watch:
                console.print(
                    "[yellow]note:[/] store is launchd-supervised; "
                    "--watch/--watch-root/--debounce-ms/--semantic here are "
                    "ignored (the plist governs). Use `rmx daemon launchctl "
                    "install --force ...` to change supervised watch config."
                )
            try:
                label = lc.kickstart(root)
            except Exception as e:  # noqa: BLE001 — fall back to a fork
                console.print(
                    f"[yellow]kickstart failed ({e}); starting standalone[/]"
                )
            else:
                pid = daemon_mod.read_pid(root)
                pid_part = f" pid={pid}" if pid else ""
                console.print(
                    f"[green]daemon supervised[/] (launchd kickstart "
                    f"label={label}){pid_part} root={root}"
                )
                return
        elif installed:
            # Plist present but not loaded → half-configured supervision.
            # Fork standalone this run, but surface the gap.
            console.print(
                "[yellow]note:[/] a LaunchAgent plist exists for this store "
                "but isn't loaded; forking standalone. Run `rmx daemon "
                "launchctl install --force` to supervise it."
            )

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


@daemon.command("restart")
@click.option(
    "--watch/--no-watch", "watch", default=True,
    help="Watch the filesystem and auto-sync on change (standalone "
         "respawn only; ignored when launchd-supervised).",
)
@click.option(
    "--watch-root", "watch_roots",
    type=click.Path(path_type=Path), default=(), multiple=True,
    help="Directory to watch on the standalone respawn. Repeat for "
         "multiple. Defaults to the parent of the active `.refmatrix/`.",
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
    "--standalone", is_flag=True,
    help="Force a standalone stop+respawn even if a launchd LaunchAgent "
         "supervises this store (by default a supervised store is "
         "force-restarted via `launchctl kickstart -k`).",
)
def daemon_restart(watch: bool, watch_roots: tuple[Path, ...],
                   debounce_ms: int, semantic: bool, standalone: bool):
    """Restart the daemon for the active store.

    Supervision-aware: if a launchd LaunchAgent is loaded for this store,
    the running instance is force-restarted in place via
    `launchctl kickstart -k` (launchd keeps owning the lifecycle). Otherwise
    the standalone daemon is stopped and a fresh one is forked. Pass
    --standalone to force the stop+respawn path even under launchd."""
    import sys as _sys
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not root.is_dir():
        raise click.ClickException(
            f"no refmatrix at {root}. Run `rmx init` first."
        )

    # launchd-supervised store → force-restart in place, unless overridden.
    if not standalone and _sys.platform == "darwin":
        from refmatrix import launchctl as lc
        try:
            loaded = lc.is_loaded(root)
        except Exception:  # noqa: BLE001 — supervision probe is best-effort
            loaded = False
        if loaded:
            if watch_roots or semantic or debounce_ms != 500 or not watch:
                console.print(
                    "[yellow]note:[/] store is launchd-supervised; "
                    "--watch/--watch-root/--debounce-ms/--semantic here are "
                    "ignored (the plist governs). Use `rmx daemon launchctl "
                    "install --force ...` to change supervised watch config."
                )
            try:
                label = lc.kickstart(root, restart=True)
            except Exception as e:  # noqa: BLE001 — fall back to standalone
                console.print(
                    f"[yellow]kickstart -k failed ({e}); "
                    f"restarting standalone[/]"
                )
            else:
                pid = daemon_mod.read_pid(root)
                pid_part = f" pid={pid}" if pid else ""
                console.print(
                    f"[green]daemon restarted[/] (launchd kickstart -k "
                    f"label={label}){pid_part} root={root}"
                )
                return

    # Standalone path: stop the current daemon (idempotent), then respawn.
    daemon_mod.stop_daemon(root)
    resolved_watch_roots: list[Path] = []
    if watch:
        if watch_roots:
            resolved_watch_roots = [Path(r).resolve() for r in watch_roots]
        else:
            resolved_watch_roots = [root.parent.resolve()]
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
    console.print(f"[green]daemon restarted[/] pid={pid} root={root}{extra}")


@daemon.command("status")
def daemon_status():
    """Report whether the daemon is running for the active store, plus its
    launchd supervision state (one view over both the process and
    supervision layers)."""
    import sys as _sys
    from refmatrix import daemon as daemon_mod
    root = _root()
    pid = daemon_mod.read_pid(root)
    healthy = daemon_mod.ping(root) if pid else False
    if pid and healthy:
        console.print(f"[green]running[/] pid={pid} root={root}")
    elif pid:
        # A live process whose socket is still there is BUSY, not stale:
        # starting up, rebuilding an index, or holding the store lock for a
        # write. Saying "stale" invites a kill, which is the wrong move.
        alive = False
        try:
            os.kill(pid, 0)
            alive = daemon_mod.socket_path(root).exists()
        except (OSError, ProcessLookupError, PermissionError):
            alive = False
        if alive:
            console.print(
                f"[yellow]busy[/] pid={pid} root={root} "
                f"(alive, not answering yet — startup or a long write)")
        else:
            console.print(f"[yellow]stale pid[/] {pid} (process gone)")
    else:
        console.print("[dim]not running[/]")

    # Supervision layer — best-effort; never let it break process status.
    if _sys.platform != "darwin":
        console.print("supervised: [dim]n/a (macOS only)[/]")
        return
    try:
        from refmatrix import launchctl as lc
        st = lc.status(root)
    except Exception as e:  # noqa: BLE001 — diagnostic line, must not raise
        console.print(f"supervised: [dim]unknown ({e})[/]")
        return
    if not st["installed"]:
        console.print("supervised: [dim]no[/]")
    elif st["loaded"]:
        console.print(f"supervised: [green]yes[/] (loaded, label={st['label']})")
    else:
        console.print(
            f"supervised: [yellow]installed, not loaded[/] (label={st['label']})"
        )


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


@main.command("merge-verb-aliases")
def merge_verb_aliases():
    """Fold legacy snake_case linkage verbs into their kebab canonical.

    One-shot, idempotent maintenance: where the same relation accreted under
    two `linkage_types` ids (e.g. `related_to` from seeded defaults / code
    emitters vs `related-to` from GMD `rel:` edges), this re-points the
    relational forward index + per-partition bitmaps onto the canonical verb
    and drops the orphan type. Go-forward writes already canonicalize; this
    cleans up edges written before that landed.

    Routes through the daemon when one is running (no stop, no service
    interruption — safe on supervised stores); otherwise opens the writer
    directly. Either way refreshes the read snapshot so queries reflect the
    merge immediately.
    """
    import shutil
    from refmatrix import daemon as daemon_mod
    from refmatrix.store import _VERB_ALIASES

    root = _root()
    if daemon_mod.ping(root):
        # Daemon owns the writer — route the merge through it (no stop, no
        # service interruption; works on supervised stores). The op refreshes
        # the read snapshot itself.
        resp = daemon_mod.call(root, "merge_verb_aliases", {})
        if not resp.get("ok"):
            raise click.ClickException(
                f"daemon merge failed: {resp.get('error')}")
        results = resp["result"]["results"]
    else:
        # Daemon down: open the writer slot directly.
        s = _store_rw()
        results = []
        active = s.db_path
        is_duckdb = s._backend.kind == "duckdb"
        try:
            for legacy, canon in _VERB_ALIASES.items():
                results.append(s.merge_verb_alias(legacy, canon))
            # DuckDB only: flush WAL into the main file so the snapshot copy is
            # self-contained. SQLite has no CHECKPOINT statement (and no
            # snapshot tier — its WAL is the read path), so it's skipped.
            if is_duckdb:
                s._connect().execute("CHECKPOINT")
        finally:
            s.close()
        # DuckDB snapshot-tier refresh (mirrors the daemon's _snapshot_catalog)
        # so lock-free readers see the merged graph immediately. SQLite stores
        # have no catalog.read.duckdb; the in-method commit is enough.
        if is_duckdb:
            snap = root / "catalog.read.duckdb"
            if active.exists():
                tmp = snap.with_name(snap.name + ".merge.tmp")
                shutil.copy2(active, tmp)
                os.replace(tmp, snap)

    table = Table(show_header=True)
    table.add_column("legacy")
    table.add_column("canonical")
    table.add_column("merged", justify="right")
    table.add_column("edges", justify="right")
    table.add_column("evidence", justify="right")
    table.add_column("fragments", justify="right")
    for r in results:
        table.add_row(
            r["legacy"], r["canon"], "yes" if r["merged"] else "no",
            str(r["edges"]), str(r["evidence"]), str(r["fragments"]),
        )
    console.print(table)
    any_merged = any(r["merged"] for r in results)
    console.print(
        "[green]merged[/] — read snapshot refreshed"
        if any_merged else "[dim]nothing to merge (already canonical)[/]"
    )


@main.command("audit-same-as")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def audit_same_as(as_json: bool):
    """Health check on `same_as` identifier variant-unification.

    Reports edge count, the variants-per-canonical distribution (should stay
    ~2/concept — space + dash forms), and the over-merge tripwire: edges whose
    two endpoints have DIFFERENT canonical_names, meaning `canonicalize_name`
    fused distinct symbols. A clean store has zero. Read-only (lock-free via
    the replica). Exits non-zero when the tripwire fires, so it can gate a
    periodic/CI run.
    """
    out = _replica_read(lambda st: st.same_as_audit())
    if as_json:
        console.print_json(data=out)
    else:
        console.print(f"[bold]same_as edges:[/] {out['edges']}")
        dist = ", ".join(f"{k}→{v}" for k, v in sorted(out["distribution"].items()))
        console.print(f"variants-per-canonical (size→#canonicals): {dist or '(none)'}")
        if out["divergent_count"]:
            console.print(
                f"[red]⚠ over-merge tripwire: {out['divergent_count']} edge(s) "
                f"fuse different canonical_names[/]"
            )
            t = Table("variant", "variant_canon", "canonical", "canonical_canon")
            for d in out["divergent"]:
                t.add_row(d["variant"], d["variant_canon"],
                          d["canonical"], d["canonical_canon"])
            console.print(t)
            if out["divergent_count"] > len(out["divergent"]):
                console.print(
                    f"[dim]… {out['divergent_count'] - len(out['divergent'])} "
                    f"more not shown[/]"
                )
        else:
            console.print("[green]✓ no over-merge — every same_as edge unifies "
                          "one identifier[/]")
    if out["divergent_count"]:
        raise SystemExit(1)


@main.group()
def partition():
    """Inspect and manage named partitions inside the active refmatrix."""


@partition.command("list")
def partition_list():
    """List all partitions in the active refmatrix, marking the active one."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    active = _resolve_partition()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "partition_list", {})
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        s = _store()
        active = s.partition_name
        rows = [
            {
                "id": r["id"], "name": r["name"], "kind": r["kind"],
                "root_path": r["root_path"], "created_at": r["created_at"],
            }
            for r in s._connect().execute(
                "SELECT id, name, kind, root_path, created_at "
                "FROM partitions ORDER BY id"
            ).fetchall()
        ]
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
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "partition_add", {
            "name": name, "kind": kind, "root_path": root_path,
        }, timeout=30.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
    else:
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
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "partition_rename", {
            "old": old, "new": new,
        }, timeout=60.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
    else:
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


@partition.command("merge")
@click.argument("src")
@click.argument("dst")
@click.option("--dry-run", is_flag=True,
              help="Resolve the entity / saved-query / tracked-file "
                   "counts without mutating. Prints what would be "
                   "reparented + merged.")
@click.option("--yes", "-y", is_flag=True,
              help="Skip the confirmation prompt. Use after a --dry-run.")
def partition_merge(src: str, dst: str, dry_run: bool, yes: bool):
    """Merge SRC partition into DST. Drops SRC on success.

    Built for the `memory-<project>` → `<project>` consolidation: the
    memory partition split made cross-partition wikilinks fail to
    resolve and produced orphan rows. Collisions remap child rows to
    DST and prefer the longer memory_content body. Lance vectors +
    bitmap fragments move filesystem-side.

    Always run --dry-run first to see the impact.
    """
    from refmatrix import daemon as daemon_mod
    root = _root()
    args = {"src": src, "dst": dst, "dry_run": True}

    if daemon_mod.ping(root):
        preview = daemon_mod.call(
            root, "partition_merge", args, timeout=300.0,
        )
        if not preview.get("ok"):
            raise click.ClickException(
                preview.get("error", "daemon error")
            )
        result = preview["result"]
    else:
        s = _store()
        try:
            result = s.merge_partition(src, dst, dry_run=True)
        except ValueError as e:
            raise click.ClickException(str(e))

    console.print(
        f"[bold]partition merge preview:[/] {src} -> {dst}"
    )
    console.print(f"  entities to reparent: {result['entities_reparented']}")
    console.print(f"  entities to merge:    {result['entities_merged']}")
    console.print(f"  saved queries:        {result['saved_queries']}")
    console.print(f"  tracked files:        {result['tracked_files']}")
    if dry_run:
        return
    total = (
        result["entities_reparented"] + result["entities_merged"]
        + result["saved_queries"] + result["tracked_files"]
    )
    if total == 0:
        console.print(f"[yellow]nothing to merge[/]")
        return
    if not yes and not click.confirm(
        f"Merge {src} into {dst} and drop {src}?", default=False,
    ):
        console.print("[yellow]aborted[/]")
        return

    if daemon_mod.ping(root):
        resp = daemon_mod.call(
            root, "partition_merge",
            {"src": src, "dst": dst, "dry_run": False},
            timeout=3600.0,
        )
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        result = resp["result"]
    else:
        s = _store()
        try:
            result = s.merge_partition(src, dst, dry_run=False)
        except ValueError as e:
            raise click.ClickException(str(e))
    console.print(
        f"[green]merged[/] reparented={result['entities_reparented']} "
        f"merged={result['entities_merged']} "
        f"saved_queries={result['saved_queries']} "
        f"tracked_files={result['tracked_files']}"
    )
    console.print(
        "[dim]restart the daemon to drop any cached SRC partition "
        "binding (`rmx daemon launchctl kickstart -k`).[/]"
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


@canon.command("find")
@click.argument("concept")
def canon_find(concept: str):
    """Find which projects host CONCEPT (cross-project canon view)."""
    from refmatrix.search import federated_concept
    res = federated_concept(concept)
    projs = res["projects"]
    if not projs:
        console.print(f"[yellow]no live project hosts[/] {concept}")
        return
    t = Table("project", "kind", "neighbors")
    for p in projs:
        t.add_row(p["project"], p.get("kind") or "", str(p.get("neighbors", 0)))
    console.print(t)
    if len(projs) > 1:
        console.print(f"[dim]{concept} spans {len(projs)} projects — "
                      f"`rmx canon link {concept}` in each to unify[/]")


@canon.command("siblings")
@click.argument("concept")
def canon_siblings(concept: str):
    """List concepts in other partitions that share a canon hub with CONCEPT."""
    def _run(s):
        local = s.get_entity("concept", concept)
        if local is None:
            raise click.ClickException(
                f"no concept '{concept}' in partition '{s.partition_name}'."
            )
        return s.partition_name, s.siblings_via_canon(local.id)
    part, rows = _replica_read(_run)
    if not rows:
        console.print(
            f"[yellow]no siblings[/] for {part}/{concept} "
            f"(run `rmx canon link {concept}` here and in the other partition first)"
        )
        return
    table = Table(show_header=True, title=f"siblings of {part}/{concept}")
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
    s = _store(write=True)
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
    s = _store(write=True)
    cid = s.add_concept(name, description=description, protected=not no_protect)
    pinned = "" if no_protect else " (pinned)"
    console.print(f"[green]added concept[/] {name} (id={cid}){pinned}")


main.add_command(_alias(add_concept, "add-concept"))


# ---- protected / noise flag CRUD + forget ---------------------------------


def _entity_selectors(names, like, namespace, kind):
    """Build the selector dict shared by protect / unprotect / noise / forget,
    requiring at least one selector so a bare command can't touch everything."""
    sel = {"names": list(names) or None, "like": like,
           "namespace": namespace, "kind": kind}
    if not any(sel.values()):
        raise click.ClickException(
            "select targets: NAMES..., --like GLOB, --namespace NS, or --kind K")
    return sel


def _selector_opts(f):
    f = click.option("--kind", type=click.Choice(["doc", "code", "concept"]),
                     default=None, help="Restrict to this entity kind.")(f)
    f = click.option("--namespace", default=None,
                     help="Match a `NS/...` namespace (e.g. query, keyword).")(f)
    f = click.option("--like", default=None,
                     help="SQL LIKE glob over the entity name, e.g. 'query/%'.")(f)
    return f


def _report_flag(action, r):
    n = r.get("count", 0)
    console.print(f"[green]{action}[/] {n} entit{'y' if n == 1 else 'ies'}")
    for name in r.get("names", [])[:20]:
        console.print(f"  {name}")
    extra = len(r.get("names", [])) - 20
    if extra > 0:
        console.print(f"  … +{extra} more")


@main.command("protect")
@click.argument("names", nargs=-1)
@_selector_opts
def protect_cmd(names, like, namespace, kind):
    """Pin entities (protected=1) so prune-noise / vacuum never reap them.

        rmx protect MyConcept                 # by name
        rmx protect --namespace query         # every learned query/* concept
        rmx protect --like 'src/%' --kind code
    """
    s = _store(write=True)
    _report_flag("protected", s.set_flag_by_selector(
        "protected", True, **_entity_selectors(names, like, namespace, kind)))


@main.command("unprotect")
@click.argument("names", nargs=-1)
@_selector_opts
def unprotect_cmd(names, like, namespace, kind):
    """Clear protected so an entity can be pruned or forgotten."""
    s = _store(write=True)
    _report_flag("unprotected", s.set_flag_by_selector(
        "protected", False, **_entity_selectors(names, like, namespace, kind)))


@main.command("noise")
@click.argument("names", nargs=-1)
@_selector_opts
def noise_cmd(names, like, namespace, kind):
    """Flag entities as noise (hidden from default queries; reaped by
    prune-noise --drop unless also protected)."""
    s = _store(write=True)
    _report_flag("flagged noise", s.set_flag_by_selector(
        "noise", True, **_entity_selectors(names, like, namespace, kind)))


@main.command("unnoise")
@click.argument("names", nargs=-1)
@_selector_opts
def unnoise_cmd(names, like, namespace, kind):
    """Clear the noise flag."""
    s = _store(write=True)
    _report_flag("cleared noise", s.set_flag_by_selector(
        "noise", False, **_entity_selectors(names, like, namespace, kind)))


@main.command("forget")
@click.argument("names", nargs=-1)
@_selector_opts
@click.option("--dry-run", is_flag=True, help="Preview matches; delete nothing.")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirm prompt.")
def forget_cmd(names, like, namespace, kind, dry_run, yes):
    """Delete entities — row, bitmap memberships, linkage evidence, and dense
    vector. Irreversible (tombstone-logged). The one removal path for protected
    learned `query/*` concepts that prune-noise / vacuum spare.

        rmx forget --namespace query --dry-run     # preview learned concepts
        rmx forget 'query/oldsearch' -y
    """
    s = _store(write=True)
    sel = _entity_selectors(names, like, namespace, kind)
    preview = s.forget_by_selector(dry_run=True, **sel)
    matched = preview.get("names", [])
    if not matched:
        console.print("[dim]no matching entities[/]")
        return
    if dry_run:
        console.print(f"[yellow]would forget[/] {len(matched)}:")
        for name in matched[:50]:
            console.print(f"  {name}")
        if len(matched) > 50:
            console.print(f"  … +{len(matched) - 50} more")
        return
    if not yes:
        console.print(f"[red]forget {len(matched)} entit"
                      f"{'y' if len(matched) == 1 else 'ies'}?[/]")
        for name in matched[:20]:
            console.print(f"  {name}")
        if len(matched) > 20:
            console.print(f"  … +{len(matched) - 20} more")
        click.confirm("proceed", abort=True)
    r = s.forget_by_selector(dry_run=False, **sel)
    console.print(f"[red]forgot[/] {r.get('forgotten', 0)} entities")


@main.command("untrack")
@click.argument("paths", nargs=-1)
@click.option("--like", default=None,
              help="SQL LIKE glob over the absolute tracked path, e.g. "
                   "'/Users/me/Applications/PyCharm.app/%'.")
@click.option("--dry-run", is_flag=True, help="Preview matches; delete nothing.")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirm prompt.")
def untrack_cmd(paths, like, dry_run, yes):
    """Stop tracking files matching a path glob, purging their entities.

    The lever `vacuum` cannot pull: vacuum only reaps paths that are GONE from
    disk, so a subtree ingested by mistake but still present (an IDE bundle a
    wide crawl picked up, a vendored dependency tree) stays tracked forever and
    re-reports `stale` on every upstream touch.

        rmx untrack --like '/Users/me/Applications/PyCharm.app/%' --dry-run
        rmx untrack /abs/path/one.py /abs/path/two.py -y

    Irreversible (each path is untrack-logged). Re-ingesting the path brings it
    back.
    """
    if not paths and not like:
        raise click.UsageError("pass PATHS or --like — refusing to untrack "
                               "an entire partition")
    s = _store(write=True)
    preview = s.untrack_by_path(like=like, paths=list(paths) or None,
                                dry_run=True)
    matched = preview.get("paths", [])
    n_ent = preview.get("entities_purged", 0)
    if not matched:
        console.print("[dim]no tracked files match[/]")
        return
    summary = (f"{len(matched)} file{'' if len(matched) == 1 else 's'} "
               f"({n_ent} entit{'y' if n_ent == 1 else 'ies'})")
    if dry_run:
        console.print(f"[yellow]would untrack[/] {summary}:")
        _print_paths(matched, 50)
        return
    if not yes:
        console.print(f"[red]untrack {summary}?[/]")
        _print_paths(matched, 20)
        click.confirm("proceed", abort=True)
    r = s.untrack_by_path(like=like, paths=list(paths) or None, dry_run=False)
    console.print(f"[red]untracked[/] {r.get('files_untracked', 0)} files, "
                  f"purged {r.get('entities_purged', 0)} entities")


def _print_paths(paths, limit):
    for pth in paths[:limit]:
        console.print(f"  {pth}")
    if len(paths) > limit:
        console.print(f"  … +{len(paths) - limit} more")


@list_grp.command("entities")
@click.option("--kind", type=click.Choice(["doc", "code", "concept"]), default=None)
@click.option("--protected/--unprotected", "want_protected", default=None,
              help="Filter to protected (or explicitly unprotected) entities.")
@click.option("--noise/--no-noise", "want_noise", default=None,
              help="Filter to noise (or non-noise) entities.")
def list_entities(kind, want_protected, want_noise):
    """List entities. --protected / --noise filter by flag and show them."""
    s = _store(write=False)
    if want_protected is None and want_noise is None:
        t = Table("id", "kind", "name", "path", "tldr")
        for e in s.iter_entities(kind):
            t.add_row(str(e.id), e.kind, e.name, e.path or "",
                      (e.tldr or "")[:80])
        console.print(t)
        return
    t = Table("id", "kind", "name", "prot", "noise")
    for eid, name, ekind, prot, noise in s.find_entity_ids(
            kind=kind, protected=want_protected, noise=want_noise):
        t.add_row(str(eid), ekind, name, "✓" if prot else "", "✓" if noise else "")
    console.print(t)


main.add_command(_alias(list_entities, "list-entities"))


# ---- linkage types --------------------------------------------------------


@add.command("linkage-type")
@click.argument("name")
@click.option("--directed/--undirected", default=True)
@click.option("--description", "-d", default=None)
def add_linkage_type(name, directed, description):
    """Define a custom linkage type."""
    s = _store(write=True)
    lid = s.add_linkage_type(name=name, directed=directed,
                             description=description)
    console.print(f"[green]linkage type[/] {name} (id={lid})")


main.add_command(_alias(add_linkage_type, "add-linkage-type"))


@list_grp.command("linkages")
def list_linkages():
    """List linkage types."""
    t = Table("id", "name", "directed", "description")
    rows = _store(write=False).list_linkages()
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
                   "even during heavy bg ingest. Reads a snapshot the daemon "
                   "regenerates shortly after each write (snapshot-tier).")
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
        if len(bm) == 0:
            # An empty walk is ambiguous: unknown seed, no edges, or the
            # edges live on a sibling node. Say which, so the caller doesn't
            # conclude "this graph is unwalkable".
            if not s.resolve_concept_ids(concept, strict=strict):
                console.print(
                    f"[dim]no concept resolves to '{concept}'"
                    f"{' (try without --strict)' if strict else ''}[/]"
                )
            else:
                hint = f"'{concept}' has no edges at depth={depth}"
                if "#" not in concept and s.resolve_entity(f"{concept}#root"):
                    hint += (
                        f"; GMD rel: edges for this doc are on "
                        f"'{concept}#root'"
                    )
                console.print(f"[dim]{hint}[/]")

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
@click.option("--degree", default=0, type=int,
              help="Hop-depth ON TOP of the existing one-hop walk. 0 (default) "
                   "= current behavior with memory bodies attached for any "
                   "kind='memory' entry. Higher values reserve scope for "
                   "future multi-hop expansion; today they only auto-scale "
                   "the --max-entities / --max-tokens budgets.")
@click.option("--include-sessions", is_flag=True,
              help="Include session-summary cards in the co-mention view. Off "
                   "by default: session cards are transient activity logs that "
                   "co-mention everything and drown out durable docs/code. Use "
                   "`rmx session recall <term>` to search sessions instead.")
@click.option("--expand", default=0, type=int,
              help="Context lines around each CONTENT MATCH snippet (grep -C "
                   "style). 0 (default) = the whole matched line only; N = ±N "
                   "surrounding source lines.")
@click.option("--hit-lines", "hit_lines",
              type=click.Choice(["first", "nums", "text"]), default="first",
              help="How many source lines to show per MENTIONED-IN entry. "
                   "first (default) = the first occurrence as a `file:line` "
                   "jump target; nums = every hit line number, compact "
                   "(`file:12,40,77`); text = every hit line WITH its source "
                   "(grep -n). Capped per entry with a `(+N more)` marker.")
@click.option("--grep/--no-grep", "grep_backstop", default=True,
              help="Grep backstop (default on): when the index returns no "
                   "CONTENT hit for the terms, literally `rg` the source tree "
                   "so context is never worse than a plain grep. Hits surface "
                   "in a GREP group; when the daemon is up they're learned into "
                   "the index as a protected `query/<ref>` concept (survives "
                   "prune). --no-grep disables both.")
@click.option("--text", "text", default=None,
              help="Query text — alias of the positional SYMBOL, for parity "
                   "with scan-prompt / memory recall.")
@click.option("--stdin-json", is_flag=True,
              help="Read the query from a UserPromptSubmit JSON envelope on "
                   "stdin ({\"prompt\": ...}) instead of an argument.")
def context(symbol, linkage, max_entities, max_tokens, fmt, since, fuse, strict,
            via_replica, degree, include_sessions, expand, hit_lines,
            grep_backstop, text, stdin_json):
    """Token-budgeted context bundle: anchor + neighbors + their tldr blobs."""
    from refmatrix.context import build_context, render_json, render_text
    from refmatrix import daemon as daemon_mod
    # Uniform query resolution: positional SYMBOL > --text > --stdin-json
    # envelope. Shared with scan-prompt / memory recall. read_stdin=False so a
    # bare `rmx context` in a pipeline doesn't silently consume stdin.
    symbol = _resolve_query(symbol, text, stdin_json=stdin_json,
                            read_stdin=False)
    # Detect whether the user actually passed --max-entities / --max-tokens
    # so the auto-scale (degree>0) knows whether to multiply or not. An
    # explicit override always wins, even if it happens to match the
    # default.
    ctx = click.get_current_context()
    entities_explicit = (
        ctx.get_parameter_source("max_entities")
        != click.core.ParameterSource.DEFAULT
    )
    tokens_explicit = (
        ctx.get_parameter_source("max_tokens")
        != click.core.ParameterSource.DEFAULT
    )

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
                    degree=degree,
                    include_sessions=include_sessions,
                    expand=expand,
                    hit_lines=hit_lines,
                    grep_backstop=grep_backstop,
                    _entities_explicit=entities_explicit,
                    _tokens_explicit=tokens_explicit,
                )
                t.cardinality = b.total_entities() if b.anchor else 0
            return b
        bundle = _replica_read(_run)
        if fmt == "json":
            click.echo(render_json(bundle))
        else:
            click.echo(render_text(bundle))
        # The replica read is read-only, so the grep backstop can only DISPLAY
        # the floor here. Fold its hits into a protected `query/<ref>` concept
        # via the daemon writer so the next lookup is indexed (and survives
        # prune). Best-effort; never fails the read.
        _maybe_learn_grep_backstop(_root(), daemon_mod, symbol, bundle,
                                   grep_backstop)
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
                "degree": degree,
                "include_sessions": include_sessions,
                "expand": expand,
                "hit_lines": hit_lines,
                "grep_backstop": grep_backstop,
                "entities_explicit": entities_explicit,
                "tokens_explicit": tokens_explicit,
            }, timeout=120.0)
            if not resp.get("ok"):
                raise click.ClickException(
                    f"daemon context failed: {resp.get('error')}"
                )
            click.echo(resp["result"]["body"])
            return

    # `--since` path + symbol fallback are read-only — entity / link
    # lookups + build_context rendering. Use the lock-free reader so the
    # command works while the daemon owns the writer slot.
    s = _read_store()

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
                              strict=strict, degree=degree)
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
            degree=degree,
            include_sessions=include_sessions,
            expand=expand,
            hit_lines=hit_lines,
            grep_backstop=grep_backstop,
            _entities_explicit=entities_explicit,
            _tokens_explicit=tokens_explicit,
        )
        t.cardinality = bundle.total_entities() if bundle.anchor else 0
    if fmt == "json":
        click.echo(render_json(bundle))
    else:
        click.echo(render_text(bundle))


def _render_describe(d: dict) -> None:
    """Human-readable rendering of a `describe_entity` payload."""
    import datetime as _dt

    def _ts(v):
        if not v:
            return "—"
        try:
            return _dt.datetime.fromtimestamp(float(v)).strftime(
                "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            return str(v)

    e = d["entity"]
    t = Table("field", "value", title=f"entity {e['id']}", show_lines=False)
    t.add_row("kind", str(e["kind"]))
    t.add_row("name", str(e["name"]))
    t.add_row("path", str(e["path"] or "—"))
    t.add_row("partition", f"{e.get('partition')} (id {e['partition_id']})")
    t.add_row("canonical_name", str(e.get("canonical_name") or "—"))
    t.add_row("protected / noise",
              f"{bool(e['protected'])} / {bool(e['noise'])}")
    t.add_row("created / updated", f"{_ts(e['created_at'])}  →  {_ts(e['updated_at'])}")
    t.add_row("tldr", (e.get("tldr") or "—")[:400])
    meta = e.get("meta")
    t.add_row("meta", json.dumps(meta, indent=2)[:1200] if meta else "—")
    console.print(t)

    v = d.get("vectors") or {}
    tf = d.get("tracked_file")
    pr = d.get("pagerank")
    t2 = Table("subsystem", "state", title="storage")
    t2.add_row("vectors (Lance)",
               (f"present={v.get('present')} dim={v.get('dim')} "
                f"dataset={v.get('dataset', '—')} embedded_at="
                f"{_ts(v.get('embedded_at'))}")
               + (f" error={v['error']}" if v.get("error") else ""))
    t2.add_row("tracked_file",
               (f"mtime={_ts(tf['mtime'])} last_synced={_ts(tf['last_synced'])} "
                f"stale={tf['stale']}") if tf else "— (not a tracked file)")
    t2.add_row("pagerank",
               f"{pr['score']:.6g} (computed {_ts(pr['computed_at'])})"
               if pr else "— (never computed)")
    console.print(t2)

    m = d.get("memory")
    if m:
        t3 = Table("field", "value", title="memory sidecar")
        t3.add_row("mtype", str(m["mtype"]))
        t3.add_row("tags", ", ".join(m["tags"]) if m["tags"] else "—")
        t3.add_row("metadata",
                   json.dumps(m["metadata"], indent=2)[:1200]
                   if m["metadata"] else "—")
        t3.add_row("created / updated",
                   f"{_ts(m['created_at'])}  →  {_ts(m['updated_at'])}")
        # Escape: rich would eat `[[wikilink]]` as console markup, so a GMD
        # body rendered here lost exactly the rel: targets you came to read.
        t3.add_row("content", rich_escape((m["content"] or "")[:2000]))
        console.print(t3)

    out = d["links_out"]
    # `store.link(linkage, concept_id, entity_id)` packs (source, target).
    # These rows match on entity_id, so THIS entity is the target and the
    # `concept` column is the source — the opposite of what a bare "outbound"
    # label suggests. Say so in the header: reading these as outbound is what
    # makes a correctly-stored `amends` edge look inverted.
    t4 = Table("linkage", "source → this", "weight", "evidence",
               title=f"edges INTO this entity — {out['total']} total, "
                     f"{len(out['shown'])} shown")
    for r in out["shown"]:
        ev = r.get("evidence") or []
        first = (f"{Path(ev[0]['file']).name}:{ev[0]['line']}"
                 if ev and ev[0].get("file") else "")
        t4.add_row(r["linkage"], str(r["concept"] or r["concept_id"]),
                   "—" if r["weight"] is None else f"{r['weight']:g}",
                   f"{r['evidence_count']}" + (f" ({first}…)" if first else ""))
    console.print(t4)

    inb = d["links_in"]
    if inb["total"]:
        # Matched on concept_id: this entity is the SOURCE of these edges.
        # A GMD doc's own `rel:` verbs live here.
        t5 = Table("linkage", "this → target", "kind", "weight",
                   title=f"edges FROM this entity — {inb['total']} total, "
                         f"{len(inb['shown'])} shown")
        for r in inb["shown"]:
            t5.add_row(r["linkage"], str(r["name"] or r["entity_id"]),
                       str(r["kind"] or "—"),
                       "—" if r["weight"] is None else f"{r['weight']:g}")
        console.print(t5)

    sib = d["siblings"]
    if sib["total"]:
        t6 = Table("id", "kind", "name",
                   title=f"same-path rows — {sib['total']} total, "
                         f"{len(sib['shown'])} shown")
        for r in sib["shown"]:
            t6.add_row(str(r["id"]), r["kind"], r["name"])
        console.print(t6)


@main.command()
@click.argument("ref")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]),
              default="text")
@click.option("--first", is_flag=True,
              help="On an ambiguous ref, describe the best match instead of "
                   "listing candidates.")
@click.option("--edge-limit", default=200, type=int,
              help="Max inbound / outbound edge rows shown (totals are exact).")
@click.option("--evidence-limit", default=20, type=int,
              help="Max evidence spans kept per outbound edge.")
@click.option("--sibling-limit", default=200, type=int,
              help="Max same-path sibling rows shown.")
@click.option("--no-vectors", is_flag=True,
              help="Skip the Lance probe (catalog-only, no dense import).")
@click.option("--via-replica", is_flag=True,
              help="Read from the rotation reader slot instead of the daemon.")
def describe(ref, fmt, first, edge_limit, evidence_limit, sibling_limit,
             no_vectors, via_replica):
    """Dump EVERY stored fact about one entity — the whole row plus the
    tables that hang off it.

    REF is an entity id, a file path (absolute, project-relative, or a
    suffix like `server.py`), or an entity/concept/memory name.

    Reports: the `entities` row (kind, path, tldr, meta, flags, timestamps,
    canonical_name), the partition it lives in, outbound `(linkage,
    concept)` memberships with evidence spans, inbound edges (what links TO
    it), same-path sibling rows (a doc's anchors, a file's symbols), the
    `tracked_files` sync record with on-disk staleness, the PageRank prior,
    the memory sidecar (content / mtype / tags / metadata), and Lance
    vector presence. `--format json` emits the whole payload verbatim.
    """
    from refmatrix import daemon as daemon_mod

    kwargs = {
        "evidence_limit": evidence_limit,
        "edge_limit": edge_limit,
        "sibling_limit": sibling_limit,
        "include_vectors": not no_vectors,
    }

    def _run(s):
        targets = s.find_describe_targets(str(ref))
        if not targets:
            return {"found": None, "candidates": []}
        if len(targets) > 1 and not first:
            return {"found": None, "candidates": targets}
        return {"found": s.describe_entity(targets[0]["id"], **kwargs),
                "candidates": targets}

    root = _root()
    if _should_via_replica(via_replica):
        payload = _replica_read(_run)
    elif daemon_mod.ping(root):
        resp = daemon_mod.call(root, "describe", {
            "ref": str(ref), "first": first,
            "partition": _resolve_partition(), **kwargs,
        }, timeout=60.0)
        if not resp.get("ok"):
            raise click.ClickException(
                f"daemon describe failed: {resp.get('error')}")
        payload = resp["result"]
    else:
        payload = _run(_read_store())

    if payload["found"] is None:
        cands = payload["candidates"]
        if not cands:
            raise click.ClickException(
                f"no entity matches {ref!r} in partition "
                f"{_resolve_partition()!r}. Try an id, a full path, or "
                f"`rmx locate {ref}`.")
        if fmt == "json":
            click.echo(json.dumps({"ambiguous": cands}, indent=2))
            return
        t = Table("id", "kind", "name", "path",
                  title=f"{len(cands)} matches for {ref!r} — re-run with an id "
                        f"or --first")
        for c in cands:
            t.add_row(str(c["id"]), c["kind"], c["name"], c["path"] or "—")
        console.print(t)
        return

    if fmt == "json":
        click.echo(json.dumps(payload["found"], indent=2, default=str))
    else:
        _render_describe(payload["found"])


@main.command("co-occur")
@click.argument("concept")
@click.option("--type", "linkage", default="mentions")
@click.option("--limit", default=20, type=int)
@click.option("--full", "include_noise", is_flag=True,
              help="Include noise-marked concepts.")
def co_occur(concept, linkage, limit, include_noise):
    """Concepts that share entities with the given concept under a linkage."""
    def _run(s):
        qe = QueryEngine(s, include_noise=include_noise)
        with log_query(s, kind="co-occur", body=concept, source="co-occur") as t:
            rows = qe.co_occurrence(concept, linkage=linkage)[:limit]
            t.cardinality = len(rows)
        return rows
    rows = _replica_read(_run)
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
        "whole_line": False,
        # Pipe-mode (stdin) rendering knobs. Ignored on the indexed path,
        # which always renders path:line over the whole index.
        "line_number": False, "with_filename": None, "quiet": False,
        "only_matching": False, "max_count": None, "after": 0, "before": 0,
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


# Bare grep/rg flag compatibility. `rmx grep -rn "pat" src/` should behave like
# a drop-in for grep/rg so a rewrite hook can route EVERY search through the
# learning grep. Three flag classes:
#   - ANSWER: changes which rows match → honored (or fail loud if unsupported).
#   - FORMAT: only changes rendering/recursion rmx already does → ignored + note.
#   - VALUE: consumes the next token (so it can't be mistaken for the pattern).
_GREP_VALUE_FLAGS = {"-e", "-A", "-B", "-C", "-m", "-g", "--glob", "-t",
                     "--max-count", "--after-context", "--before-context",
                     "--context"}
# FORMAT/recursion flags rmx grep ignores (its output is always path:line, it
# always searches the whole index): line numbers, filename toggles, only-match,
# recursion, binary/color/heading knobs.
_GREP_FORMAT_FLAGS = set("nHhroRasIbTup")
_GREP_FORMAT_LONG = {"--color", "--colour", "--no-heading", "--heading",
                     "--line-number", "--no-line-number", "--with-filename",
                     "--no-filename", "--only-matching", "--recursive",
                     "--no-messages", "--binary-files", "--null"}
# Rendering flags that are NOT formatting noise once rmx grep is filtering a
# pipe: there it stands in for grep byte-for-byte, so `-n` must number lines
# and `-h` must strip the filename. Honored only under stdin_mode.
_GREP_STDIN_SHORT = {
    "n": lambda gf: gf.__setitem__("line_number", True),
    "H": lambda gf: gf.__setitem__("with_filename", True),
    "h": lambda gf: gf.__setitem__("with_filename", False),
    "o": lambda gf: gf.__setitem__("only_matching", True),
}
_GREP_STDIN_LONG = {
    "--line-number": _GREP_STDIN_SHORT["n"],
    "--no-line-number": lambda gf: gf.__setitem__("line_number", False),
    "--with-filename": _GREP_STDIN_SHORT["H"],
    "--no-filename": _GREP_STDIN_SHORT["h"],
    "--only-matching": _GREP_STDIN_SHORT["o"],
}


def _split_grep_argv(tokens: list) -> tuple:
    """Split a raw grep-style argv into (flag_tokens, pattern, paths, warnings).

    Honors `--` (end of flags), `-e PAT` (explicit pattern), and value-taking
    flags (-A/-B/-C/-m/-g/-t) so their argument is never mistaken for the
    pattern. The first non-flag token (or the `-e` value) is the pattern; the
    rest are paths. A pattern beginning with `-` requires `--`."""
    flags: list = []
    pattern = None
    paths: list = []
    warnings: list = []
    i = 0
    n = len(tokens)
    end_of_flags = False
    while i < n:
        tok = str(tokens[i])
        if not end_of_flags and tok == "--":
            end_of_flags = True
            i += 1
            continue
        is_flag = (not end_of_flags) and tok.startswith("-") and tok != "-"
        if is_flag:
            # -e PAT: the value IS the pattern.
            base = tok.split("=", 1)[0]
            if base == "-e" or base == "--regexp":
                if "=" in tok:
                    pattern = tok.split("=", 1)[1]
                elif i + 1 < n:
                    pattern = str(tokens[i + 1]); i += 1
                i += 1
                continue
            flags.append(tok)
            # consume a value token for value-flags written separately (-C 3).
            if base in _GREP_VALUE_FLAGS and "=" not in tok and i + 1 < n:
                flags.append(str(tokens[i + 1])); i += 1
            i += 1
            continue
        # non-flag: pattern first, then paths.
        if pattern is None:
            pattern = tok
        else:
            paths.append(tok)
        i += 1
    return flags, pattern, paths, warnings


def _grep_bare_flags(flag_tokens: list, gf: dict, stdin_mode: bool = False) -> tuple:
    """Fold bare grep/rg flag tokens into `gf` (mutated in place) with grep
    semantics. Returns (ignored_note | None, error | None). ANSWER flags are
    honored; FORMAT flags are ignored (surfaced in the note); an unsupported
    flag that would CHANGE THE ANSWER (path filters -g/--glob/-t, unknown
    letters) errors loudly — a filter silently dropped from a READ is a wrong
    answer, not a formatting nicety.

    Under `stdin_mode` (pipe filtering, no index involved) rmx grep IS grep, so
    the rendering flags -n/-H/-h/-o/-q and the value flags -m/-A/-B/-C are
    honored rather than ignored."""
    ignored: list = []
    j = 0
    n = len(flag_tokens)
    while j < n:
        tok = str(flag_tokens[j]); j += 1
        base = tok.split("=", 1)[0]
        # value-flags: their consumed argument was appended right after them.
        if base in _GREP_VALUE_FLAGS:
            has_inline = "=" in tok
            val = None
            if has_inline:
                val = tok.split("=", 1)[1]
            elif j < n:
                val = flag_tokens[j]; j += 1
            if base in ("-A", "-B", "-C", "-m", "--after-context",
                        "--before-context", "--context", "--max-count"):
                if not stdin_mode:
                    ignored.append(tok)      # index output is always path:line
                    continue
                try:
                    num = int(str(val))
                except (TypeError, ValueError):
                    return None, (f"grep: '{base}' expects a number, got "
                                  f"{val!r}")
                if base in ("-m", "--max-count"):
                    gf["max_count"] = num
                elif base in ("-A", "--after-context"):
                    gf["after"] = num
                elif base in ("-B", "--before-context"):
                    gf["before"] = num
                else:
                    gf["after"] = gf["before"] = num
                continue
            # -g/--glob/-t narrow the file set → dropping them WIDENS the answer.
            return None, (f"grep: '{base}' (path filter) is not supported by "
                          f"rmx grep and would change the result set — pass an "
                          f"explicit PATH instead of {base} {val!r}")
        if base.startswith("--"):
            if base in _GREP_FORMAT_LONG:
                if stdin_mode and base in _GREP_STDIN_LONG:
                    _GREP_STDIN_LONG[base](gf); continue
                ignored.append(tok); continue
            if base in ("--quiet", "--silent"):
                if stdin_mode:
                    gf["quiet"] = True; continue
                return None, ("grep: -q/--quiet is only supported when rmx "
                              "grep filters a pipe; on the indexed path the "
                              "exit code would not mean what grep means")
            if base in ("--ignore-case",): gf["ignore_case"] = True; continue
            if base in ("--word-regexp",): gf["word"] = True; continue
            if base in ("--invert-match",): gf["invert"] = True; continue
            if base in ("--files-with-matches",): gf["files_only"] = True; continue
            if base in ("--files-without-match",):
                gf["files_without_match"] = True; continue
            if base in ("--count",): gf["count"] = True; continue
            if base in ("--fixed-strings",): gf["force_substring"] = True; continue
            if base in ("--extended-regexp", "--regexp-extended"):
                gf["force_regex"] = True; continue
            if base in ("--line-regexp",): gf["whole_line"] = True; continue
            return None, (f"grep: unsupported flag '{base}'. If it only affects "
                          f"formatting use -f to bundle known letters; "
                          f"answer-changing flags must be supported to be safe.")
        # short cluster, e.g. -inl. Value letters may carry their argument
        # attached (`-C1`, `-nA2`, `-m10`) and a bare `-3` means `-C 3`.
        body = tok[1:]
        if body.isdigit():
            # `-NUM` is GNU-only shorthand for -C NUM and BSD grep reads it
            # differently. Two grep dialects disagreeing about the answer is
            # exactly the case that must fail loud, not be guessed at.
            return None, (f"grep: '{tok}' (GNU -NUM context shorthand) is "
                          f"ambiguous across grep dialects — use -C {body}")
        k = 0
        while k < len(body):
            ch = body[k]; k += 1
            if ch in "ABCm" and body[k:].isdigit() and body[k:]:
                num = int(body[k:]); k = len(body)
                if not stdin_mode:
                    ignored.append(f"-{ch}{num}")
                elif ch == "m": gf["max_count"] = num
                elif ch == "A": gf["after"] = num
                elif ch == "B": gf["before"] = num
                else: gf["after"] = gf["before"] = num
                continue
            if ch == "i": gf["ignore_case"] = True
            elif ch == "w": gf["word"] = True
            elif ch == "v": gf["invert"] = True
            elif ch == "l": gf["files_only"] = True
            elif ch == "L": gf["files_without_match"] = True
            elif ch == "c": gf["count"] = True
            elif ch == "F": gf["force_substring"] = True
            elif ch == "E": gf["force_regex"] = True
            elif ch == "x": gf["whole_line"] = True
            elif ch == "q" and stdin_mode: gf["quiet"] = True
            elif stdin_mode and ch in _GREP_STDIN_SHORT:
                _GREP_STDIN_SHORT[ch](gf)
            elif ch in _GREP_FORMAT_FLAGS:
                ignored.append(f"-{ch}")
            else:
                return None, (f"grep: unsupported flag '-{ch}' (in {tok!r}). "
                              f"Answer-changing flags must be supported to be "
                              f"safe; formatting flags are ignored.")
    if gf["force_substring"] and gf["force_regex"]:
        return None, "grep: -F and -E are mutually exclusive"
    if gf["files_only"] and gf["files_without_match"]:
        return None, "grep: -l and -L are mutually exclusive"
    note = None
    if ignored:
        seen = []
        for x in ignored:
            if x not in seen: seen.append(x)
        note = ("rmx grep: ignoring formatting/recursion flags "
                + " ".join(seen) + " (output is always path:line over the "
                "whole index)")
    return note, None


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


_STDIN_LABEL = "(standard input)"
# Modes whose stdout is near-certainly parsed by the next stage of the
# pipeline (`| wc -l`, `&& …`, `$(…)`): the rmx addendum is suppressed so it
# can never be mistaken for data.
_STDIN_MACHINE_KEYS = ("quiet", "count", "files_only", "files_without_match",
                       "only_matching")


def _grep_stdin(pattern: str, regex: bool, gf: dict, limit: int | None) -> None:
    """Pipe-mode grep: search lines from sys.stdin, ignore the index.

    Output is byte-compatible with `grep` reading stdin — plain matching
    lines, `N:` only under -n, `(standard input):` only under -H — because a
    rewrite hook drops this into arbitrary pipelines where the next stage
    parses what grep would have produced. Honors -i/-I/-w/-v/-F/-E/-x plus
    the pipe-mode knobs -n/-H/-h/-o/-q/-c/-l/-L/-m/-A/-B/-C. Exits 1 when
    nothing matched (grep's contract for `&&` / `if` callers).

    Anything rmx has to add beyond grep is appended AFTER the grep output,
    never interleaved with it (see `_grep_stdin_addendum`)."""
    import re as _re
    import sys as _sys
    from collections import deque as _deque
    if regex:
        rx_pattern = pattern
    else:
        rx_pattern = _re.escape(pattern)
    if gf["word"]:
        rx_pattern = rf"\b{rx_pattern}\b"
    if gf["whole_line"]:
        rx_pattern = rf"^(?:{rx_pattern})$"
    flags_re = _re.IGNORECASE if gf["ignore_case"] is True else 0
    try:
        rx = _re.compile(rx_pattern, flags_re)
    except _re.error as exc:
        raise click.ClickException(f"invalid regex: {exc}")

    max_count = gf["max_count"]
    cap = limit if limit is not None else None
    before, after = gf["before"], gf["after"]
    show_num = gf["line_number"]
    show_name = bool(gf["with_filename"])

    def _fmt(n: int, line: str, sep: str = ":") -> str:
        head = f"{_STDIN_LABEL}{sep}" if show_name else ""
        if show_num:
            head += f"{n}{sep}"
        return head + line

    out: list[str] = []
    total = 0
    ctx_before = _deque(maxlen=before) if before else _deque(maxlen=0)
    after_left = 0
    last_emitted = 0        # line number of the last line pushed to `out`
    truncated = False
    for n, raw in enumerate(_sys.stdin, start=1):
        line = raw.rstrip("\n")
        hit = bool(rx.search(line))
        if gf["invert"]:
            hit = not hit
        if hit and max_count is not None and total >= max_count:
            hit = False
            after_left = 0
        if hit:
            total += 1
            if cap is not None and total > cap:
                truncated = True
            elif not gf["quiet"] and not gf["count"] and not gf["files_only"]:
                if (before or after) and last_emitted and out and \
                        n - len(ctx_before) > last_emitted + 1:
                    out.append("--")
                for cn, cline in ctx_before:
                    out.append(_fmt(cn, cline, "-"))
                if gf["only_matching"]:
                    for m in rx.finditer(line):
                        out.append(_fmt(n, m.group(0)))
                else:
                    out.append(_fmt(n, line))
                last_emitted = n
            ctx_before.clear()
            after_left = after
            if gf["quiet"] or (gf["files_only"] and not gf["count"]):
                # Nothing more to learn: -q/-l answer on the first match.
                break
        else:
            if after_left and not (gf["quiet"] or gf["count"]
                                   or gf["files_only"]):
                out.append(_fmt(n, line, "-"))
                last_emitted = n
                after_left -= 1
            elif before:
                ctx_before.append((n, line))

    # --- grep-expected output first, verbatim -------------------------------
    if gf["quiet"]:
        pass
    elif gf["count"]:
        click.echo(str(total))
    elif gf["files_only"]:
        if total:
            click.echo(_STDIN_LABEL)
    elif gf["files_without_match"]:
        if not total:
            click.echo(_STDIN_LABEL)
    else:
        for line in out:
            click.echo(line)

    # --- rmx-specific output strictly AFTER the grep output -----------------
    if truncated:
        click.echo(f"rmx grep: output capped at --limit {cap} "
                   f"({total} lines matched)", err=True)
    if not gf["quiet"] and not any(gf[k] for k in _STDIN_MACHINE_KEYS):
        _grep_stdin_addendum(pattern, total)

    raise SystemExit(0 if total else 1)


def _grep_stdin_addendum(pattern: str, total: int) -> None:
    """Append what rmx knows about PATTERN beneath the grep output.

    Best-effort and strictly additive: the grep-compatible lines are already
    on stdout, so this block starts with a `# rmx` marker and any failure
    (no index, no daemon, cold store) is swallowed — a pipe filter must never
    fail because the index was unavailable. Disable with RMX_GREP_NOTE=0."""
    import os as _os
    if _os.environ.get("RMX_GREP_NOTE", "1") in ("0", "false", "no"):
        return
    rows = []
    try:
        from refmatrix import daemon as daemon_mod
        root = _root()
        if not daemon_mod.ping(root):
            return          # no daemon: a pipe filter must not open the store
        resp = daemon_mod.call(root, "grep_indexed", {
            "pattern": pattern, "regex": False, "linkage": None,
            "kind": None, "limit": 5,
        }, timeout=3.0, retries=0)
        if resp.get("ok"):
            rows = (resp.get("result") or {}).get("rows") or []
    except Exception:
        return
    if not rows:
        return
    click.echo(f"# rmx: {pattern!r} in the index "
               f"({len(rows)} of the top references)")
    for r in rows[:5]:
        loc = r.get("path") or r.get("entity") or ""
        line = f":{r['line']}" if r.get("line") is not None else ""
        click.echo(f"#   {loc}{line}  [{r.get('linkage')}]  {r.get('concept')}")


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


@main.command(context_settings={"ignore_unknown_options": True})
@click.argument("argv", nargs=-1, type=click.UNPROCESSED)
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
def grep(argv, regex, flags, linkage, kind, limit, fallback, learn, via_replica):
    """Index-backed grep: find concepts whose name matches PATTERN and
    print file:line for every recorded reference. Falls back to `rg` /
    `grep -rn` under the project root when the index has no hits.

    Drop-in for grep/rg: bare grep-style flags work directly, so a rewrite hook
    can route every search through the learning grep.

        rmx grep -rn "daemon" src/           # bare flags, like grep
        rmx grep -i -l "daemon" src/         # case-insensitive, files only
        rmx grep -inl "Daemon"               # bundled short flags
        rmx grep -e "-x" -- src/             # -e gives the pattern
        rg -l TODO | rmx grep "FIXME"        # pipe mode (no index)

    Answer-changing flags (-i -w -v -l -L -c -F -E -x -e) are honored;
    formatting/recursion flags (-n -H -r -o --color …) are ignored with a note;
    an unsupported flag that would change the result set (path filters
    -g/--glob/-t, unknown letters) fails loudly rather than silently mangling
    the search. `--flags`/`-f` still accepts a quoted bundle for back-compat.
    """
    import sys as _sys
    flag_tokens, pattern, path_strs, _w = _split_grep_argv(list(argv))
    if pattern is None:
        raise click.UsageError("grep: no PATTERN given")
    paths = [Path(p) for p in path_strs]
    gf = _parse_grep_flags(flags)
    # Pipe mode is decided BEFORE flag folding: it changes which flags are
    # answer-changing (-n/-o/-m/-A… render output when we're standing in for
    # grep, but mean nothing against the index).
    piped = _is_stdin_piped()
    if flag_tokens:
        note, err = _grep_bare_flags(flag_tokens, gf, stdin_mode=piped)
        if err:
            raise click.UsageError(err)
        if note and not piped:
            click.echo(note, err=True)
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
    if piped:
        # --limit is an index-side guard; silently truncating a pipe would be
        # a wrong answer, so it only applies when the user asked for it.
        cap = limit
        try:
            ctx = click.get_current_context()
            if (ctx.get_parameter_source("limit")
                    == click.core.ParameterSource.DEFAULT):
                cap = None
        except Exception:
            cap = None
        _grep_stdin(pattern, regex, gf, cap)
        return

    # -x / --line-regexp: whole-line match. Forces regex and anchors the
    # pattern; an answer-changing flag, so it must be honored, not ignored.
    if gf["whole_line"]:
        regex = True
    # Word-boundary wrapping when regex mode is on.
    effective_pattern = pattern
    if gf["word"] and regex:
        effective_pattern = rf"\b{pattern}\b"
    if gf["whole_line"]:
        effective_pattern = rf"^{effective_pattern}$"
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
    # Try the replica FIRST regardless of ping: a saturated daemon fails the
    # 0.5s ping but the replica is still lock-free, so this avoids opening the
    # writer slot (which would raise "Conflicting lock"). s stays None when
    # there's no replica but a daemon is up -> `_grep_run` serves via RPC.
    s = _reader_store()
    if s is None and not daemon_mod.ping(root):
        s = _store()
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
    def _run(s):
        body = s.get_saved_query(name)
        if body is None:
            raise click.ClickException(f"no saved query: {name}")
        qe = QueryEngine(s)
        result = qe.run_pql(body) if is_pql else qe.run(body)
        if isinstance(result, list):
            return ("weighted", [(s.get_entity_by_id(eid), w) for eid, w in result])
        if ids_only:
            return ("ids", list(result))
        return ("bitmap", s, result)
    out = _replica_read(_run)
    kind = out[0]
    if kind == "weighted":
        for ent, w in out[1]:
            print(f"{ent.name if ent else '?'}\t{w}")
    elif kind == "ids":
        for eid in out[1]:
            print(eid)
    else:
        _print_bitmap(out[1], out[2], limit=limit)


@list_grp.command("queries")
def list_queries():
    """List saved queries."""
    t = Table("name", "body")
    rows = list(_store(write=False).list_saved_queries())
    for n, b in rows:
        t.add_row(n, b)
    console.print(t)


main.add_command(_alias(list_queries, "list-queries"))


# ---- stats / export -------------------------------------------------------


@main.command()
@click.option("--stale", is_flag=True,
              help="Also list tracked files where on-disk mtime > last_synced. "
                   "Reads the writer's tracked_files via the daemon — no need "
                   "to stop the daemon.")
@click.option("--via-replica", is_flag=True,
              help="Read counts from the rotation reader slot instead of the "
                   "daemon. Lock-free; sees stale-by-N-seconds data. Cannot be "
                   "combined with --stale (the replica's tracked_files isn't "
                   "refreshed).")
def stats(stale, via_replica):
    """Print catalog and bitmap stats."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if via_replica and stale:
        raise click.ClickException(
            "--via-replica and --stale are incompatible: the replica's "
            "tracked_files isn't refreshed. Use plain `--stale` (routes "
            "through the daemon's writer).")
    if via_replica or (not stale and _should_via_replica(False)):
        # Replica-first for plain counts, gated on the replica file EXISTING —
        # not on ping. The replica (catalog.read.duckdb) is never write-locked,
        # so this works even when the daemon is saturated and its ping times
        # out. (Gating on ping was the old bug: a busy daemon fails the 0.5s
        # ping, the caller then opened the writer slot r/w -> "Conflicting
        # lock".) --stale skips this branch — it needs the live writer.
        out = _replica_read(lambda st: st.stats())
    elif daemon_mod.ping(root):
        # Daemon owns the writer (+ tracked_files). Route through it so --stale
        # works WITHOUT stopping the daemon. Never open the writer slot directly
        # while the daemon owns it.
        resp = daemon_mod.call(root, "stats", {"include_stale": stale})
        if not resp.get("ok"):
            raise click.ClickException(f"daemon stats failed: {resp.get('error')}")
        out = resp["result"]
    else:
        # No daemon: safe to read the live catalog directly.
        s = _store_rw()
        out = s.stats()
        if stale:
            out["stale_files"] = s.stale_files()
    t1 = Table("kind", "count", title="entities")
    for k, v in out["entities"].items():
        t1.add_row(k, str(v))
    console.print(t1)
    t2 = Table("linkage", "concepts (rows)", "set bits", title="linkages")
    for name, d in out["linkages"].items():
        t2.add_row(name, str(d["concepts"]), str(d["bits"]))
    console.print(t2)
    if stale:
        rows = out.get("stale_files") or []
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

    def _run(s):
        if top_queried:
            return ("top_queried", top_queried_concepts(s))
        if zero_results:
            return ("zero_results", zero_result_queries(s))
        return ("summary", summarize(s, since=since))
    kind, data = _replica_read(_run)

    if kind == "top_queried":
        rows = data
        if fmt == "json":
            click.echo(json.dumps(rows, indent=2))
        else:
            t = Table("concept", "queries")
            for name, n in rows:
                t.add_row(name, str(n))
            console.print(t)
        return
    if kind == "zero_results":
        rows = data
        if fmt == "json":
            click.echo(json.dumps(rows, indent=2))
        else:
            t = Table("query", "count")
            for name, n in rows:
                t.add_row(name, str(n))
            console.print(t)
        return

    out = data
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
    out = _store(write=True).vacuum()
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
    out = _store(write=True).prune_noise(
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
    def _run(s):
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
        return payload
    payload = _replica_read(_run)
    Path(out).write_text(json.dumps(payload, indent=2))
    console.print(f"[green]exported[/] {out}")


@main.command("import")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--merge", is_flag=True, help="Merge into existing matrix instead of failing on conflicts.")
def import_(path, merge):
    """Import a JSON dump produced by `rmx export`."""
    # `import` does a large write (entities + linkages + bitmaps + commit)
    # straight against the catalog. Refuse to run while the daemon owns
    # the writer lock — would crash with "Could not set lock on
    # catalog.B.duckdb". Caller should stop the daemon, run the import,
    # and restart.
    from refmatrix import daemon as daemon_mod
    if daemon_mod.ping(_root()):
        raise click.ClickException(
            "daemon is running — stop it first (`rmx daemon stop`), run "
            "the import, then restart. The import bypasses the daemon's "
            "write path and would deadlock on the catalog lock."
        )
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
    resolved = Path(path).resolve()
    # Uniform write path: routes the whole ingest through the daemon (single
    # op) when one owns the store, else runs in-process. Single-owner lock.
    n = _ingest(_store(write=True), resolved, source=source, semantic=semantic)
    console.print(f"[green]ingested[/] {n} entities from {path}")


def _default_memory_dir(repo: Path) -> Path:
    """The curated-memory dir for this project:
    `~/.claude/projects/<encoded-cwd>/memory`, matching the slug Claude Code
    and `rmx session ingest` use. `repo` is the .refmatrix root's parent."""
    from refmatrix.handoff import default_memory_dir
    return default_memory_dir(repo)


def _reingest_embed(ctx, partition: str, *, rebuild: bool) -> None:
    """Run the embed pass with `partition` pinned (embed only walks the active
    partition, so the orchestrator embeds each layer's partition in turn)."""
    global _partition_override
    prev = _partition_override
    _partition_override = partition
    try:
        ctx.invoke(embed_cmd, kinds=(), rebuild=rebuild)
    finally:
        _partition_override = prev


@main.command("reingest")
@click.option("--semantic/--no-semantic", default=True, show_default=True,
              help="Run the slow Python/markdown semantic passes on the tree.")
@click.option("--sessions/--no-sessions", "do_sessions", default=True,
              show_default=True,
              help="Ingest this project's Claude Code session JSONLs.")
@click.option("--embed/--no-embed", "do_embed", default=True, show_default=True,
              help="Embed dense vectors after ingest (incremental).")
@click.option("--rebuild", is_flag=True,
              help="Pass --rebuild to the embed pass (re-embed every row).")
@click.option("--memory-dir", "memory_dir",
              type=click.Path(path_type=Path), default=None,
              help="Curated memory `.md` dir. "
                   "Default: ~/.claude/projects/<project-slug>/memory.")
@click.pass_context
def reingest(ctx, semantic, do_sessions, do_embed, rebuild, memory_dir):
    """Run every ingest pass over all sources in canonical order, then embed.

    Order (each gated/incremental — unchanged files are skipped):

    \b
      1. code + docs  — the repo tree (tldr/metadata/tree + markdown + pseudo
                        + python-semantic + graphify) into the project partition.
      2. memory       — curated `.md` memories as kind=memory WITH content and
                        the rel: graph (ingest-gmd --as-memory).
      3. sessions     — Claude Code session JSONLs into sessions-<project>.
      4. embed        — dense vectors for the project (+ memory) partition(s).
      5. pagerank     — global PageRank prior over each partition's graph,
                        so scan-prompt salience + `--rank ppr` use fresh
                        centrality (the graph just changed in steps 1-2).

    The single "make this store correct" command: picks the right pass per
    source in the right order so the read surfaces (context, scan-prompt,
    recall) see a consistent graph. Routes through the daemon when one is up.
    """
    root = _root()
    repo = root.parent
    results: list[tuple[str, bool, str]] = []

    def step(label: str, fn) -> None:
        console.print(f"[bold cyan]» {label}[/]")
        try:
            fn()
            results.append((label, True, ""))
        except click.ClickException as e:
            msg = e.format_message()
            console.print(f"[red]  {label} failed:[/] {msg}")
            results.append((label, False, msg))
        except Exception as e:  # noqa: BLE001 — orchestrator continues past one bad pass
            console.print(f"[red]  {label} error:[/] {e}")
            results.append((label, False, str(e)))

    # 1. code + docs
    step("1/5 code+docs", lambda: ctx.invoke(
        ingest, path=repo, source="auto", semantic=semantic))

    # 2. memory
    memdir = Path(memory_dir).resolve() if memory_dir else _default_memory_dir(repo)
    if memdir and memdir.is_dir():
        step(f"2/5 memory ({memdir})", lambda: ctx.invoke(
            ingest_gmd, targets=(memdir,), as_memory=True))
    else:
        console.print(f"[yellow]» 2/5 memory: no dir at {memdir}, skipped[/]")
        results.append(("2/5 memory", True, "skipped (no dir)"))

    # 3. sessions
    if do_sessions:
        step("3/5 sessions", lambda: ctx.invoke(session_ingest_cmd))
    else:
        console.print("[dim]» 3/5 sessions: skipped (--no-sessions)[/]")

    # Partitions touched by graph-bearing passes — embed + pagerank both walk
    # the active partition only, so iterate the project + memory partitions.
    graph_parts = list(dict.fromkeys([
        _resolve_partition(), _memory_partition_default(),
    ]))

    # 4. embed — per partition (embed only walks the active partition).
    if do_embed:
        for part in graph_parts:
            step(f"4/5 embed [{part}]",
                 lambda p=part: _reingest_embed(ctx, p, rebuild=rebuild))
    else:
        console.print("[dim]» 4/5 embed: skipped (--no-embed)[/]")

    # 5. pagerank — recompute the centrality prior now the graph changed.
    #    Cheap relative to embed; always run (no flag) since scan-prompt
    #    salience + --rank ppr read it on every prompt.
    for part in graph_parts:
        step(f"5/5 pagerank [{part}]",
             lambda p=part: _run_pagerank(root, p))

    ok = sum(1 for _, good, _ in results if good)
    console.print(f"\n[bold]reingest done[/] — {ok}/{len(results)} steps ok")
    for label, good, detail in results:
        mark = "[green]✓[/]" if good else "[red]✗[/]"
        console.print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))


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

    # Uniform write path — single daemon op when supervised, else in-process.
    n = _ingest(_store(write=True), proj, source="tldr", semantic=semantic)
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

    # Uniform write path — single daemon op when supervised, else in-process.
    n = _ingest(_store(write=True), proj, source="graphify")
    console.print(f"[green]ingested[/] {n} graphify edges from {proj}")


# ---- incremental sync -----------------------------------------------------


def _sync_stale(project_root, semantic, *, batch: int) -> None:
    """Re-sync every `status=stale` file the daemon reports (mtime ahead of
    last_synced), in jetsam-safe batches. The incremental hook/queue path only
    re-syncs files it was told about; edits that bypass it (git ops, external
    tools) sit stale forever with no lever to drain them. This is that lever:
    the counterpart to `vacuum` (which handles `missing`), not a duplicate."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "--stale needs the daemon (it serves the authoritative stale list "
            "and holds the Store open); start it and retry.")
    r = daemon_mod.call(root, "stats", {"include_stale": True}, timeout=60.0)
    if not r.get("ok"):
        raise click.ClickException(f"stats failed: {r.get('error')}")
    sf = r["result"].get("stale_files") or []
    paths = [e["path"] for e in sf if e.get("status") == "stale"]
    missing = sum(1 for e in sf if e.get("status") == "missing")
    if missing:
        console.print(f"[dim]{missing} missing file(s) — run `rmx vacuum` "
                      f"for those (this only re-syncs stale)[/]")
    if not paths:
        console.print("[green]no stale files to sync[/]")
        return
    proot = str((project_root or Path.cwd()).resolve())
    total = len(paths)
    added = updated = purged = done = 0
    def _bail(i, why):
        # Daemon died (jetsam is the usual cause — inline embed spikes RSS) or
        # errored mid-run. Enqueue the remainder so a later flush drains it, and
        # report honestly rather than crashing with a socket traceback.
        from refmatrix import sync as syncmod
        remaining = paths[i:]
        try:
            syncmod.enqueue(root, remaining)
        except Exception:
            pass
        console.print(
            f"[yellow]daemon stopped at {done}/{total}[/] ({why}) — enqueued "
            f"{len(remaining)} remaining to dirty.queue "
            f"(recover with `rmx sync --flush-queue`; if it keeps dying on "
            f"embed, drain in a lean process per the jetsam recipe)")

    for i in range(0, total, batch):
        chunk = paths[i:i + batch]
        try:
            resp = daemon_mod.call(root, "sync_files", {
                "project_root": proot, "semantic": semantic,
                "files": chunk}, timeout=600.0)
        except (ConnectionError, OSError) as e:
            _bail(i, type(e).__name__)
            return
        if not resp.get("ok"):
            _bail(i, resp.get("error") or "op failed")
            return
        res = resp["result"]
        added += res.get("added", 0); updated += res.get("updated", 0)
        purged += res.get("purged", 0); done += len(chunk)
        console.print(
            f"[dim]{done}/{total}[/] +{res.get('added',0)} "
            f"~{res.get('updated',0)} -{res.get('purged',0)}")
    console.print(
        f"[green]stale-sync done[/] {done} files · "
        f"+{added} ~{updated} -{purged}")


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
@click.option("--stale", "stale_flag", is_flag=True,
              help="Re-sync every file `stats --stale` reports (on-disk mtime "
                   "ahead of last_synced) — drains a stuck stale count without "
                   "naming paths. Batched jetsam-safe; enqueues the remainder "
                   "if the daemon dies mid-run.")
@click.option("--stale-batch", default=25, type=int, show_default=True,
              help="Files per batch for --stale (small keeps a fat daemon "
                   "under the jetsam ceiling).")
def sync(files, since, flush_queue, invalidate, project_root, semantic,
         enqueue_only, async_flag, stale_flag, stale_batch):
    """Incrementally update the matrix for given files / git changes / queued paths."""
    from refmatrix import sync as syncmod

    if stale_flag:
        _sync_stale(project_root, semantic, batch=max(1, stale_batch))
        return

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


@main.group("queue", invoke_without_command=True)
@click.pass_context
def queue_cmd(ctx):
    """Show or manage the dirty (change) queue.

    Bare `rmx queue` lists pending paths; `rmx queue clear` empties it."""
    if ctx.invoked_subcommand is not None:
        return
    from refmatrix import sync as syncmod
    q = _root() / syncmod.QUEUE_FILE
    if not q.exists():
        console.print("[dim]queue is empty[/]")
        return
    for line in q.read_text().splitlines():
        if line.strip():
            console.print(line)


@queue_cmd.command("clear")
@click.option("--flush", is_flag=True,
              help="Drain AND process the queued paths (like `sync "
                   "--flush-queue`) instead of discarding them.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def queue_clear(flush, yes):
    """Empty the dirty queue.

    Default DISCARDS the pending paths without ingesting them — just drops
    `dirty.queue`. Use this to abandon a stale backlog the daemon keeps
    re-attempting. `--flush` instead drains and syncs the paths (identical to
    `rmx sync --flush-queue`), so no pending work is lost.

    Note: this only touches the hook-populated change queue. It does NOT clear
    `stale_files` (tracked rows whose on-disk mtime drifted, or whose path
    vanished) — resolve those with `rmx sync` / `rmx vacuum`."""
    from refmatrix import sync as syncmod
    root = _root()
    q = root / syncmod.QUEUE_FILE

    if flush:
        # Reuse the daemon-routed flush the `sync` command already implements.
        ctx = click.get_current_context()
        ctx.invoke(sync, flush_queue=True)
        return

    # Discard path: dirty.queue is a plain hook-appended text file, never the
    # catalog — safe to unlink directly whether the daemon is up or down. The
    # daemon's next drain simply finds no file. No lock needed.
    if not q.exists():
        console.print("[dim]queue is empty[/]")
        return
    pending = [ln for ln in q.read_text().splitlines() if ln.strip()]
    if not pending:
        q.unlink()
        console.print("[dim]queue is empty[/]")
        return
    if not yes:
        click.confirm(
            f"Discard {len(pending)} pending path(s) without ingesting?",
            abort=True,
        )
    q.unlink()
    console.print(f"[green]cleared[/] {len(pending)} pending path(s) (discarded)")


@main.group()
def replica():
    """Read-replica (snapshot-tier) management.

    The writer stays pinned to one catalog slot (the `active` marker
    names it); writer rotation is dropped. Reads are served from a
    snapshot file (`catalog.read.duckdb`) the daemon regenerates shortly
    after each write op, so readers never contend on the writer's lock.
    `refresh` is now a no-op. DuckDB backend only."""


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


@replica.command("audit")
@click.option("--json", "as_json", is_flag=True,
              help="Print the raw report as JSON instead of a table.")
def replica_audit(as_json):
    """Detect drift between rotation slots: per-table row diffs + entity
    (partition,kind,name) collisions across slots A and B. Read-only;
    safe to run with or without the daemon up. Run periodically to catch
    drift before it accumulates."""
    import json as _json
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "replica_audit", {}, timeout=30.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        report = resp["result"]
    else:
        # Daemon down — audit catalog files directly. Pure read-only ATTACH
        # is safe even when nobody owns the file lock.
        from refmatrix import replica_merge as rm
        a_path = root / "catalog.A.duckdb"
        b_path = root / "catalog.B.duckdb"
        if not (a_path.exists() and b_path.exists()):
            raise click.ClickException(
                f"missing slot file: a_exists={a_path.exists()} "
                f"b_exists={b_path.exists()}"
            )
        report = rm.audit_slots(a_path, b_path)
        report["enabled"] = True
        report["ok"] = True

    if as_json:
        click.echo(_json.dumps(report, indent=2))
        return
    if not report.get("enabled"):
        console.print("[yellow]replica disabled[/] (non-duckdb backend)")
        return
    drift = report.get("drift_detected")
    color = "red" if drift else "green"
    console.print(f"[{color}]drift_detected:[/] {drift}")
    a = report["a_counts"]
    b = report["b_counts"]
    console.print("\n[bold]Per-table row counts:[/]")
    for t in a:
        delta = b[t] - a[t]
        marker = "" if delta == 0 else f"  [yellow]Δ {delta:+d}[/]"
        console.print(f"  {t:18s}  A={a[t]:>8}  B={b[t]:>8}{marker}")
    e = report["entities"]
    console.print("\n[bold]Entity drift:[/]")
    console.print(f"  A-only ids:                  {e['a_only_ids']}")
    console.print(f"  B-only ids:                  {e['b_only_ids']}")
    console.print(f"  same-id, payload differs:    {e['same_id_diff_payload']}")
    console.print(f"  (p,k,n) collisions (id≠):    {e['pkn_collisions_different_ids']}")
    mc = report["memory_content"]
    console.print("\n[bold]memory_content drift:[/]")
    console.print(f"  A-only entity_ids:           {mc['a_only_entity_ids']}")
    console.print(f"  B-only entity_ids:           {mc['b_only_entity_ids']}")
    if drift:
        console.print("\n[dim]Run `rmx replica merge --dry-run` to preview "
                      "the recovery plan.[/]")


@replica.command("merge")
@click.option("--dry-run", is_flag=True,
              help="Build the merge plan and report counts WITHOUT writing "
                   "the merged catalog or touching the rotation.")
@click.option("--json", "as_json", is_flag=True,
              help="Print the raw report as JSON instead of a table.")
@click.option("--yes", is_flag=True,
              help="Skip the confirmation prompt. Required for non-dry-run "
                   "from non-interactive contexts.")
def replica_merge(dry_run, as_json, yes):
    """Drift recovery: merge rotation slots A and B into one canonical
    catalog and atomically install on both slots.

    Use when `rmx replica audit` reports drift that the daemon's facts.log
    replay can't heal — typically unlogged writes that landed only on the
    writer slot at the time. The merge:

      1. Drains in-flight read-replica connections.
      2. Locks the writer; CHECKPOINT + flush.
      3. Builds a merged catalog out-of-band.
      4. os.replace's both slots with the merged file.
      5. Resets both offset files to the post-merge log position.
      6. Reopens the writer on slot A; points the read symlink at B.

    Heavy operation: takes a few seconds for a multi-100-MB store. Block
    on the daemon for the duration."""
    import json as _json
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "daemon not running — merge requires exclusive control of the "
            "catalog files. Start the daemon first."
        )

    if not dry_run and not yes:
        # Show a quick audit so the user has the drift in front of them.
        resp = daemon_mod.call(root, "replica_audit", {}, timeout=30.0)
        if resp.get("ok"):
            r = resp["result"]
            click.echo("About to merge slots. Current drift:")
            click.echo(f"  entities: A={r['a_counts']['entities']:,} "
                       f"B={r['b_counts']['entities']:,}")
            click.echo(f"  memory_content: A={r['a_counts']['memory_content']:,} "
                       f"B={r['b_counts']['memory_content']:,}")
            click.echo(f"  (p,k,n) collisions: "
                       f"{r['entities']['pkn_collisions_different_ids']}")
        if not click.confirm("Proceed with merge?", default=False):
            click.echo("aborted")
            return

    resp = daemon_mod.call(
        root, "replica_merge", {"dry_run": dry_run}, timeout=600.0,
    )
    if not resp.get("ok"):
        raise click.ClickException(resp.get("error", "daemon error"))
    report = resp["result"]
    if not report.get("enabled"):
        console.print("[yellow]replica disabled[/] (non-duckdb backend)")
        return
    if not report.get("ok"):
        raise click.ClickException(f"merge failed: {report.get('error')}")

    if as_json:
        click.echo(_json.dumps(report, indent=2))
        return

    elapsed = report.get("elapsed_ms_total", report.get("elapsed_ms", 0))
    head = "DRY-RUN" if report.get("dry_run") else "MERGED"
    console.print(f"\n[bold green]{head}[/] in {elapsed} ms")

    a, b, m = report["a_counts"], report["b_counts"], report["merged_counts"]
    console.print("\n[bold]Per-table counts (A / B → merged):[/]")
    for t in a:
        delta_a = m[t] - a[t]
        delta_b = m[t] - b[t]
        console.print(
            f"  {t:18s}  {a[t]:>8} / {b[t]:>8} → {m[t]:>8}  "
            f"(Δa {delta_a:+d}, Δb {delta_b:+d})"
        )
    rm = report["remap"]
    console.print(
        f"\n[bold]Remap:[/] A-loser={rm['a_loser_count']} "
        f"B-loser={rm['b_loser_count']} "
        f"edge_cases={rm['fresh_alloc_edge_cases']}"
    )
    if not report.get("dry_run"):
        console.print(
            f"\n[bold]writer:[/] slot {report['writer_slot']}, "
            f"log_end_offset={report['log_end_offset']:,}"
        )
        if report.get("target_size_bytes"):
            console.print(
                f"[bold]merged size:[/] "
                f"{report['target_size_bytes']:,} bytes"
            )


@replica.command("path")
def replica_path():
    """Print the absolute path of the *reader* slot file. CLI tools that
    want a lock-free read can open this file in read-only DuckDB mode.

    The reader path is the snapshot file (`catalog.read.duckdb`), which
    the daemon regenerates in place after each write — stable across
    writes, so the path does not change."""
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


@curator.command("scan")
@click.option("--no-drain", is_flag=True,
              help="Leave the curator queue in place after scanning.")
@click.option("--dry-run", is_flag=True,
              help="Show candidates without enqueueing them.")
def curator_scan(no_drain, dry_run):
    """Lint queued GMD docs → file curation candidates into the refinement
    queue (no silent writes). The gmd-curator subagent drains + fixes them.
    Intended to run on the scheduler or on demand."""
    from refmatrix import gmd_curator
    root = _root()
    if dry_run:
        cands = gmd_curator.scan(root)
        if not cands:
            console.print("[dim]no curation candidates[/]")
            return
        for c in cands:
            console.print(f"[yellow]{c['kind']}[/] {c['path']}")
            console.print(f"  [dim]{c['detail'].strip()[:200]}[/]")
        console.print(f"\n[dim]{len(cands)} candidate(s) — run without --dry-run "
                      f"to enqueue[/]")
        return
    res = gmd_curator.scan_and_enqueue(root, drain=not no_drain)
    console.print(f"[green]curator scan:[/] {res['candidates']} candidate(s) "
                  f"queued for review"
                  + (" · queue drained" if res["drained"] else ""))
    if res["candidates"]:
        console.print("[dim]review/accept in the UI Bus tab or `rmx bus` "
                      "refinement queue; dispatch the gmd-curator subagent to fix[/]")


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

    def _run(s):
        return build_primer(
            s,
            top_n=top,
            symbol_like_only=symbol_like,
            exclude_namespaces=tuple(exclude_namespace),
            min_refs=min_refs,
            max_tokens=max_tokens,
            include_noise=include_noise,
        )

    text = _replica_read(_run)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
        console.print(f"[green]wrote[/] {out}")
    else:
        click.echo(text)


def _read_stdin_text() -> str:
    """Read all of stdin, returning '' on any error / no data."""
    try:
        return sys.stdin.read()
    except Exception:
        return ""


def _resolve_query(
    positional: "str | None",
    text: "str | None" = None,
    prompt: "str | None" = None,
    *,
    stdin_json: bool = False,
    read_stdin: bool = True,
) -> str:
    """Uniform query resolution for the read surfaces — `context`,
    `scan-prompt`, and `memory recall` — so they stop disagreeing on how a
    query is passed.

    Precedence: positional arg > --text > --prompt > stdin. For stdin, an
    explicit --stdin-json (or a payload that merely looks like a JSON object)
    is parsed as the UserPromptSubmit envelope and its `.prompt` is used;
    anything else is taken as raw prose. Auto-detecting the JSON object closes
    the scan-prompt footgun where a hook piping `{"prompt": "..."}` got the
    braces indexed as the query.

    `read_stdin=False` suppresses the implicit non-tty stdin read (so
    `context` / `memory recall` don't consume a pipe unless --stdin-json is
    explicit); an explicit --stdin-json still reads. Returns the resolved
    query (stripped); '' when nothing resolves."""
    import json
    for cand in (positional, text, prompt):
        if cand and cand.strip():
            return cand.strip()
    if not (stdin_json or (read_stdin and not sys.stdin.isatty())):
        return ""
    raw = _read_stdin_text()
    if not raw.strip():
        return ""
    if stdin_json or raw.lstrip().startswith("{"):
        try:
            env = json.loads(raw)
        except Exception:
            if stdin_json:
                raise click.ClickException(
                    "--stdin-json: invalid JSON on stdin"
                )
            return raw.strip()   # looked like JSON but isn't — treat as prose
        if isinstance(env, dict):
            return (env.get("prompt") or "").strip()
        return raw.strip()
    return raw.strip()


@main.command("scan-prompt")
@click.argument("query", required=False)
@click.option("--text", default=None,
              help="Prompt text — alias of the positional QUERY; else read "
                   "from stdin.")
@click.option("--stdin-json", is_flag=True,
              help="Force-parse stdin as a UserPromptSubmit JSON envelope "
                   "({\"prompt\": ...}). A raw piped envelope is auto-detected "
                   "as JSON too, so the braces are no longer indexed as prose.")
@click.option("--max-tokens", default=2000, type=int)
@click.option("--per-concept-tokens", default=600, type=int)
@click.option("--max-concepts", default=5, type=int)
@click.option("--exclude-namespace", multiple=True, default=("keyword",),
              help="Drop noise namespaces (default: keyword). import/ is kept "
                   "so prompts mentioning module names get useful bundles.")
@click.option("--full", "include_noise", is_flag=True,
              help="Include noise-marked concepts when matching.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--rank",
              type=click.Choice(["salience", "ppr", "enrich", "net"]),
              default="ppr", show_default=True,
              help="Concept selection. 'ppr' (default) seeds local-push "
                   "personalized PageRank on the matched concepts and also "
                   "surfaces strongly-related concepts the prompt never named; "
                   "'enrich' walks the seeds (plus the session's STM focus) to "
                   "degree 2 and ranks by how many seeds independently reach "
                   "each node, rather than by diffused mass; 'net' links the "
                   "prompt's concepts (plus STM focus) into a core clique, "
                   "expands via graph edges AND tldr bodies, then keeps only "
                   "nodes more than one core member reached; "
                   "falls back to 'salience' if the walk can't seed. "
                   "'salience' ranks only the prompt's own matched concepts "
                   "(shape+idf+PageRank prior).")
@click.option("--content/--no-content", default=True, show_default=True,
              help="Prepend a content-ranked (BM25 idf + coverage) bundle over "
                   "ALL the prompt's terms, ahead of the per-concept graph "
                   "bundles. The per-concept view ranks by raw term frequency "
                   "within one term at a time, so it cannot prefer a document "
                   "covering several of the prompt's terms — on prose that "
                   "costs more than half the recall.")
@click.option("--content-tokens", default=600, type=int, show_default=True,
              help="Token budget for the content-ranked bundle. Counts against "
                   "--max-tokens, so the graph bundles get what is left.")
@click.option("--composite/--no-composite", default=True, show_default=True,
              help="Append a GMD topic-composite subgraph of the session's "
                   "current STM focus (the running aggregate of every "
                   "prompt+result), budgeted SEPARATELY from --max-tokens.")
@click.option("--composite-max-tokens", default=1200, type=int, show_default=True,
              help="Floor budget for the composite; autoscales up with session "
                   "depth to a ceiling (RMX_STM_COMPOSITE_TOKENS_MAX). "
                   "Independent of --max-tokens.")
@click.option("--composite-k", default=3, type=int, show_default=True,
              help="Max topic clusters rendered in the composite.")
@click.option("--no-composite-expand", "composite_no_expand", is_flag=True,
              help="Build the composite from STM focus only — skip long-term "
                   "graph expansion (no build_context calls).")
@click.option("--composite-every", default=1, type=int, show_default=True,
              help="Inject the composite only every Nth turn (env "
                   "RMX_STM_COMPOSITE_EVERY). 1 = every turn; higher throttles "
                   "the per-prompt injection. Focus graph still updates each "
                   "turn — only the emitted block is suppressed on skips.")
@click.option("--composite-intra-edges", default=3, type=int, show_default=True,
              help="Per-topic cap on GROUNDED intra-cluster edges (env "
                   "RMX_STM_COMPOSITE_INTRA_EDGES). Real typed graph verbs "
                   "(calls/defines/depends-on…) between focus members, replacing "
                   "the old weak co-occurs dump. 0 = drop the block.")
def scan_prompt_cmd(query, text, max_tokens, per_concept_tokens, max_concepts,
                    exclude_namespace, include_noise, fmt, stdin_json, rank,
                    composite, composite_max_tokens, composite_k,
                    composite_no_expand, composite_every,
                    composite_intra_edges, content, content_tokens):
    """Read a prompt; emit context bundles for symbols it mentions.

    Designed for the Claude Code UserPromptSubmit hook. Output goes to stdout,
    which Claude Code injects as additional context for the turn. Accepts the
    prompt as a positional QUERY, --text, or stdin (raw prose or a JSON
    envelope — auto-detected).

    Also appends (default on) a GMD topic-composite subgraph of the session's
    current focus — a running aggregate of every prompt+result — with its own
    autoscaling token budget, so it never robs the prompt-symbol context.
    """
    from refmatrix.scan import scan_prompt

    # Positional QUERY > --text > stdin (JSON envelope auto-detected).
    prompt = _resolve_query(query, text, stdin_json=stdin_json, read_stdin=True)
    if not prompt.strip():
        return
    composite_root = _root() if composite else None

    def _run(s):
        with log_query(s, kind="scan", body=prompt[:200], source="scan-prompt") as tlog:
            result = scan_prompt(
                s, prompt,
                max_tokens=max_tokens,
                per_concept_tokens=per_concept_tokens,
                max_concepts=max_concepts,
                rank=rank,
                exclude_namespaces=tuple(exclude_namespace),
                include_noise=include_noise,
                fmt=fmt,
                composite=composite,
                composite_root=composite_root,
                composite_k=composite_k,
                composite_expand=not composite_no_expand,
                composite_max_tokens=composite_max_tokens,
                content=content,
                content_tokens=content_tokens,
                composite_every=composite_every,
                composite_intra_edges=composite_intra_edges,
            )
            tlog.cardinality = result.count("=== context for") if result else 0
        return result

    out = _replica_read(_run)
    if out:
        click.echo(out)


@main.command("top")
@click.argument("concept")
@click.option("--type", "linkage", default="mentions")
@click.option("-k", default=10, type=int)
def top(concept, linkage, k):
    """Top-K entities by weight under (linkage, concept)."""
    def _run(s):
        e = s.resolve_entity(concept)
        if e is None or e.kind != "concept":
            raise click.ClickException(f"no concept: {concept}")
        with log_query(s, kind="top", body=concept, source="top") as tlog:
            rows = s.top_weighted(linkage, e.id, k=k)
            tlog.cardinality = len(rows)
        return [(s.get_entity_by_id(eid), w) for eid, w in rows]
    pairs = _replica_read(_run)
    t = Table("entity", "kind", "weight")
    for ent, w in pairs:
        t.add_row(ent.name if ent else "?", ent.kind if ent else "", f"{w:g}")
    console.print(t)


@main.command("locate")
@click.argument("terms", nargs=-1)
@click.option("-f", "--file", "filename", default=None,
              help="Filename to locate (basename only; a path is reduced to "
                   "its basename).")
@click.option("-n", "limit", default=10, type=int, show_default=True,
              help="Max number of full paths to return.")
@click.option("--json", "as_json", is_flag=True,
              help="JSON output (paths + scores + why).")
def locate(terms, filename, limit, as_json):
    """Locate full filesystem paths by FILENAME and/or keywords/concepts.

    Searches every live store. A positional token that looks like a filename
    (has an extension, no slash) becomes the filename filter; the remaining
    tokens are keywords/concepts that rank the results by relevance. `-f` sets
    the filename explicitly.

    \b
    Examples:
      rmx locate cli.py                 # where is cli.py
      rmx locate ingest semantic        # files most about these concepts
      rmx locate store.py partition     # store.py ranked by 'partition' relevance
    """
    import re as _re
    from refmatrix.search import federated_locate

    keywords: list[str] = []
    fname = filename
    for t in terms:
        looks_file = "/" not in t and bool(_re.match(r'^[\w.\-]+\.\w+$', t))
        if looks_file and fname is None:
            fname = t
        else:
            keywords.append(t)
    if fname and "/" in fname:
        fname = Path(fname).name
    if not fname and not keywords:
        raise click.ClickException("give a filename and/or keywords to locate")

    res = federated_locate(fname, keywords, limit=limit)
    rows = res["results"]
    if as_json:
        console.print_json(data=res)
        return
    if not rows:
        console.print("[yellow]no matches[/]")
        return
    for r in rows:
        click.echo(r["path"])


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


# ---- unified log access --------------------------------------------------

# name -> (filename, one-line description). Order = display order.
_LOG_REGISTRY: "dict[str, tuple[str, str]]" = {
    "cli":         ("cli.log", "CLI invocations (argv, exit, latency)"),
    "query":       ("query.log", "query strings + result counts"),
    "facts":       ("facts.log", "every mutation (entities/links) — append log, can be huge"),
    "daemon":      ("daemon.stderr.log", "daemon stderr (crashes, tracebacks)"),
    "daemon-out":  ("daemon.stdout.log", "daemon stdout"),
    "rmxd":        ("rmxd.log", "daemon internal log (ingest progress, ops)"),
    "sync":        ("sync.log", "sync / watcher activity"),
    "session":     ("session-indexer.stderr.log", "session-indexer stderr"),
    "session-out": ("session-indexer.stdout.log", "session-indexer stdout"),
    "compact":     ("compact.log", "catalog compaction"),
}


def _fmt_bytes(n: int) -> str:
    f = float(n)
    for unit in ("B", "K", "M", "G"):
        if f < 1024 or unit == "G":
            return f"{f:.0f}{unit}" if unit == "B" else f"{f:.1f}{unit}"
        f /= 1024
    return f"{f:.1f}T"


def _read_log_tail(path: Path, n: int, pattern: str | None,
                   cap: int = 4_000_000) -> "list[str]":
    """Last `n` lines of `path`, optionally filtered by substring `pattern`,
    reading at most the trailing `cap` bytes so a multi-GB log is never loaded
    whole. The filter therefore applies to the recent window, not the whole
    file (use `--path` + your own tools for a full scan)."""
    size = path.stat().st_size
    with open(path, "rb") as f:
        if size > cap:
            f.seek(size - cap)
            f.readline()  # drop the partial first line
        raw = f.read()
    lines = raw.decode("utf-8", "replace").splitlines()
    if pattern:
        lines = [ln for ln in lines if pattern in ln]
    return lines[-n:] if n > 0 else lines


@main.command("log")
@click.argument("name", required=False)
@click.argument("pattern", required=False)
@click.option("--tail", "-n", type=int, default=40,
              help="Show last N lines (default 40). 0 = whole read window.")
@click.option("--follow", "-f", is_flag=True, help="Follow the log (tail -f).")
@click.option("--path", "show_path", is_flag=True,
              help="Print the log's file path and exit.")
def log_cmd(name: "str | None", pattern: "str | None", tail: int,
            follow: bool, show_path: bool):
    """List or tail refmatrix's logs under .refmatrix/.

    \b
    rmx log                 list available logs with sizes
    rmx log daemon          tail the daemon stderr log
    rmx log cli foo         tail cli.log, only lines containing 'foo'
    rmx log facts -n 100    last 100 facts.log lines
    rmx log rmxd -f         follow the daemon log

    Tailing reads only the end of the file, so the (potentially multi-GB)
    facts.log is never loaded whole."""
    root = _root()

    if not name:
        t = Table(title=f"logs under {root}", show_header=True)
        t.add_column("name", style="bold")
        t.add_column("file")
        t.add_column("size", justify="right")
        t.add_column("what")
        for lname, (fn, desc) in _LOG_REGISTRY.items():
            p = root / fn
            size = _fmt_bytes(p.stat().st_size) if p.exists() else "[dim]-[/]"
            t.add_row(lname, fn, size, desc)
        console.print(t)
        console.print("[dim]rmx log <name> [pattern] [-n N] [-f][/]")
        return

    if name not in _LOG_REGISTRY:
        raise click.ClickException(
            f"unknown log '{name}'. Known: {', '.join(_LOG_REGISTRY)}"
        )
    p = root / _LOG_REGISTRY[name][0]
    if show_path:
        console.print(str(p))
        return
    if not p.exists():
        console.print(f"[yellow]{p} does not exist yet[/]")
        return

    if follow:
        import shlex
        import subprocess
        cmd = f"tail -n {max(tail, 0)} -f {shlex.quote(str(p))}"
        if pattern:
            cmd += f" | grep --line-buffered -F -- {shlex.quote(pattern)}"
        try:
            subprocess.run(cmd, shell=True)
        except KeyboardInterrupt:
            pass
        return

    lines = _read_log_tail(p, tail, pattern)
    if not lines:
        console.print("[yellow]no matching lines in the read window[/]")
        return
    for ln in lines:
        console.print(ln, markup=False, highlight=False)


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


@main.command("compact-log")
@click.option("--force", is_flag=True,
              help="Compact even if the log is under the size threshold.")
def compact_log(force: bool):
    """Compact .refmatrix/facts.log, reclaiming its unbounded growth.

    facts.log is the append-only mutation log; every re-ingest appends
    duplicate events the catalog already folds by name, so it grows without
    bound (a churned store reached 2.4GB). This rewrites it from the
    authoritative catalog as a minimal, replay-faithful current-state snapshot
    (partitions + memory bodies preserved).

    Routes through the daemon writer when one is up (no daemon-stop needed);
    otherwise compacts in-process. Size-gated unless --force; the daemon also
    auto-compacts on a tick (RMX_FACTSLOG_MAX_BYTES, default 256MiB)."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if daemon_mod.ping(root):
        r = daemon_mod.call(root, "compact_factslog", {"force": force},
                            timeout=180.0)
        if not r.get("ok"):
            raise click.ClickException(r.get("error", "compact failed"))
        res = r["result"]
    else:
        s = _store()
        log_path = s.log_path
        size = log_path.stat().st_size if log_path.exists() else 0
        threshold = int(
            os.environ.get("RMX_FACTSLOG_MAX_BYTES", str(256 * 1024 * 1024))
            or 0
        )
        if not force and (threshold <= 0 or size < threshold):
            res = {"skipped": "under-threshold", "size": size,
                   "threshold": threshold}
        else:
            counts = s.dump_catalog_to_log()
            new_size = log_path.stat().st_size if log_path.exists() else 0
            res = {"compacted": True, "old_size": size, "new_size": new_size,
                   "counts": counts}
    if res.get("compacted"):
        old, new = res["old_size"], res["new_size"]
        pct = (1 - new / old) * 100 if old else 0
        console.print(
            f"[green]compacted[/] facts.log "
            f"{old/1024/1024:.1f}MB -> {new/1024/1024:.1f}MB ([cyan]{pct:.0f}%[/] smaller)"
        )
    else:
        console.print(
            f"[yellow]skipped[/] ({res.get('skipped')}): "
            f"size={res.get('size', 0)/1024/1024:.1f}MB "
            f"threshold={res.get('threshold', 0)/1024/1024:.0f}MB "
            f"— use --force to compact anyway"
        )


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


def _tail_ingest_progress(root: Path, job_id: str, files_total: int) -> None:
    """Poll `ingest_gmd_status` and print one line per file event until
    the job's status flips off `running`. Used by `ingest-gmd --progress`
    and `ingest-status --follow`.
    """
    from refmatrix import daemon as daemon_mod
    import time as _time
    cursor = 0
    poll_s = float(os.environ.get("RMX_INGEST_POLL_S", "0.25") or "0.25")
    last_status = "running"
    final_job: dict | None = None
    while True:
        resp = daemon_mod.call(
            root, "ingest_gmd_status",
            {"job_id": job_id, "since_seq": cursor, "limit": 500},
            timeout=30.0,
        )
        if not resp.get("ok"):
            raise click.ClickException(
                resp.get("error", "daemon error")
            )
        job = resp["result"]["job"]
        events = resp["result"].get("events") or []
        for ev in events:
            cursor = max(cursor, ev["seq"])
            n = ev.get("n") or files_total or 0
            click.echo(f"[{ev['phase']} {ev['i']}/{n}] {ev['path']}")
        last_status = job.get("status", "running")
        if last_status != "running":
            final_job = job
            break
        _time.sleep(poll_s)
    if final_job is None:
        return
    if last_status == "error":
        raise click.ClickException(
            f"ingest job {job_id} failed: {final_job.get('error')!r}"
        )
    result = final_job.get("result") or {}
    if "report" in result:
        console.print(result["report"])
    else:
        console.print(f"ingest job {job_id} completed")


@main.command("ingest-status")
@click.argument("job_id", required=False)
@click.option("--follow", "-f", is_flag=True,
              help="Tail per-file progress for a still-running job, "
                   "same as `ingest-gmd --progress`.")
def ingest_status(job_id: str | None, follow: bool):
    """Inspect ingest job state. With no JOB_ID, lists all known jobs.
    With a JOB_ID, prints the job summary; pass --follow to tail
    per-file events until the job finishes."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "daemon not running — ingest jobs are daemon-resident"
        )
    if follow:
        if not job_id:
            raise click.ClickException("--follow requires a JOB_ID")
        # Probe once to learn files_total for the header line.
        resp = daemon_mod.call(
            root, "ingest_gmd_status", {"job_id": job_id}, timeout=30.0,
        )
        if not resp.get("ok"):
            raise click.ClickException(
                resp.get("error", "daemon error")
            )
        job = resp["result"]["job"]
        _tail_ingest_progress(root, job_id, job.get("files_total", 0))
        return
    resp = daemon_mod.call(
        root, "ingest_gmd_status",
        {"job_id": job_id} if job_id else {},
        timeout=30.0,
    )
    if not resp.get("ok"):
        raise click.ClickException(resp.get("error", "daemon error"))
    result = resp["result"]
    if "jobs" in result:
        jobs = result["jobs"]
        if not jobs:
            console.print("[yellow]no ingest jobs known[/]")
            return
        t = Table("job", "status", "progress", "started", "ended")
        for j in jobs:
            t.add_row(
                j["id"], j["status"],
                f"{j['files_done']}/{j['files_total']}",
                _ts_short(j.get("started_at")),
                _ts_short(j.get("ended_at")),
            )
        console.print(t)
        return
    job = result["job"]
    console.print(
        f"job {job['id']}  status={job['status']}  "
        f"progress={job['files_done']}/{job['files_total']}"
    )
    if job.get("current_file"):
        console.print(f"  current: {job['current_file']}")
    if job.get("error"):
        console.print(f"  error:   {job['error']}")
    if job.get("result", {}).get("report"):
        console.print(job["result"]["report"])


def _ts_short(ts: float | None) -> str:
    import datetime as _dt
    if not ts:
        return "-"
    return _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


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
@click.option("--detach", is_flag=True,
              help="Start the ingest as a background job and return the "
                   "job id immediately. Use `rmx ingest-status <job_id>` "
                   "to poll. Mutually exclusive with --progress.")
@click.option("--progress", is_flag=True,
              help="Run as a detached job but tail per-file progress in "
                   "the foreground (one line per file: `[i/n] path`). "
                   "Exits when the job finishes. Mutually exclusive with "
                   "--detach.")
def ingest_gmd(targets: tuple[Path, ...], verbose: bool,
               as_memory: bool, memory_mtype: str, prestage: bool,
               detach: bool, progress: bool):
    """Ingest Graph Markdown (GMD) docs. Walks dirs for *.gmd/*.md files
    that carry `gmd:` frontmatter; non-GMD files are skipped.

    Single-active-ingest: a second `ingest-gmd` against the same daemon
    while one is in flight errors out — the two would fight over the
    write lock and interleave their two-pass parse/resolve state.
    """
    if detach and progress:
        raise click.ClickException(
            "--detach and --progress are mutually exclusive"
        )
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
        op_args = {
            "targets": [str(p) for p in resolved],
            "verbose": verbose,
            "as_memory": as_memory,
            "memory_mtype": memory_mtype,
            "partition": ingest_partition,
        }
        if detach or progress:
            resp = daemon_mod.call(
                root, "ingest_gmd_start", op_args, timeout=60.0,
            )
            if not resp.get("ok"):
                raise click.ClickException(
                    resp.get("error", "daemon error")
                )
            job = resp["result"]
            job_id = job["job_id"]
            files_total = job.get("files_total", 0)
            if detach:
                console.print(
                    f"ingest job {job_id} started "
                    f"({files_total} files). "
                    f"poll with: rmx ingest-status {job_id}"
                )
                return
            # --progress: foreground poll loop. Tail events + print one
            # line per file. Exit when job status flips off "running".
            _tail_ingest_progress(root, job_id, files_total)
            return
        # Synchronous path (default). Daemon errors immediately if
        # another ingest is already active.
        resp = daemon_mod.call(root, "ingest_gmd", op_args,
                               timeout=24 * 3600.0)
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


def _split_csv(ctx, param, value):
    """Click callback: accepts either repeated `--flag X --flag Y` or
    comma-separated `--flag X,Y` (or any mix). Strips whitespace + dedupes.
    Does NOT validate token values — use this for free-form lists like
    mtype filters; `_split_kinds` is the validated form."""
    if not value:
        return ()
    out: list[str] = []
    for v in value:
        for tok in str(v).split(","):
            tok = tok.strip()
            if not tok:
                continue
            if tok not in out:
                out.append(tok)
    return tuple(out)


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


@main.command("pagerank")
@click.option("--damping", default=0.85, show_default=True,
              help="PageRank damping factor (restart probability = 1-damping).")
@click.option("--link-weight", default=2.0, show_default=True,
              help="Transition-weight multiplier for typed linkage edges "
                   "(defines/calls/...) relative to bare co-mention edges.")
@click.option("--max-iter", default=100, show_default=True,
              help="Power-iteration cap (stops early on L1 convergence).")
@click.option("--top", default=10, show_default=True,
              help="Print the N most central nodes after computing.")
def pagerank_cmd(damping, link_weight, max_iter, top):
    """Recompute the global PageRank prior over the concept⇄entity graph.

    Stores a centrality ratio (`pr * N`; an average node ≈ 1.0, hubs > 1)
    per node in the `pagerank` sidecar for the active partition. The
    scan-prompt salience ranker reads it as a query-agnostic prior so
    central concepts outrank incidental ones. Run after a large ingest.

    Graph: bipartite concept⇄entity, undirected — mention edges from the
    `mentions` fragment plus typed `entity_links` edges (weighted heavier
    via --link-weight). Daemon-routed when up; in-proc fallback otherwise.
    """
    root = _root()
    result = _run_pagerank(
        root, _resolve_partition(), damping=damping, link_weight=link_weight,
        max_iter=max_iter, top=top)
    console.print(
        f"[green]pagerank[/] partition={result.get('partition')} "
        f"nodes={result.get('nodes')}")
    for row in result.get("top", []):
        console.print(
            f"  {row['ratio']:6.2f}  [{row['kind']}] {row['name']}")


def _run_pagerank(root: Path, partition: str, *, damping: float = 0.85,
                  link_weight: float = 2.0, max_iter: int = 100,
                  top: int = 10) -> dict:
    """Compute + persist the PageRank prior for one partition. Daemon-routed
    when up, in-proc otherwise. Shared by `rmx pagerank` and `rmx reingest`."""
    from refmatrix import daemon as daemon_mod
    args = {
        "partition": partition, "damping": damping,
        "link_weight": link_weight, "max_iter": max_iter, "top": top,
    }
    if daemon_mod.ping(root):
        resp = daemon_mod.call(root, "pagerank_compute", args, timeout=600.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        return resp["result"]
    from refmatrix.daemon import _op_pagerank, Daemon
    d = Daemon(root)
    d.store = _store()
    return _op_pagerank(d, args)


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
        total_missing = sum(r.get("missing", 0) for r in by_kind.values())
        tag = "would drop" if dry_run else "dropped"
        for kind, r in sorted(by_kind.items()):
            console.print(
                f"  {kind}: {tag}={r['orphans']} kept={r['kept']} "
                f"re-queued={r.get('missing', 0)}"
            )
        console.print(
            f"[{'yellow' if dry_run else 'green'}]total {tag}: "
            f"{total_orphans}[/]"
        )
        if total_missing:
            # The inverse leak: rows claiming a vector Lance never had. They
            # are invisible to `embed` until the stamp is cleared, so say it
            # out loud and name the follow-up rather than fixing it silently.
            console.print(
                f"[{'yellow' if dry_run else 'green'}]{total_missing} row(s) "
                f"claimed a vector that is absent from lance"
                f"{' — would be' if dry_run else ''} re-queued; "
                f"run `rmx embed` to fill them[/]"
            )
        return

    # Memory nodes live in the memory partition (`memory-<project>` pre-merge,
    # else the project partition); every other kind lives in the project
    # partition. embed used to send ALL kinds to `_resolve_partition()`, so
    # `rmx embed --kinds memory` scanned the *code* partition and never built
    # the memory vectors — dense recall came up empty on every prompt and the
    # recall hook nagged "rmx embed --kinds memory" (the command that didn't
    # work). Route per kind, matching `reingest`'s graph_parts loop and the
    # partition recall actually reads.
    mem_kinds = [k for k in selected if k == "memory"]
    other_kinds = [k for k in selected if k != "memory"]
    plan: list[tuple[str, list[str]]] = []
    if other_kinds:
        plan.append((_resolve_partition(), other_kinds))
    if mem_kinds:
        mp = _memory_partition_default()
        # On a post-merge host the memory partition IS the project partition;
        # fold rather than embed the same partition twice.
        folded = next((i for i, (p, _) in enumerate(plan) if p == mp), None)
        if folded is not None:
            plan[folded] = (mp, plan[folded][1] + mem_kinds)
        else:
            plan.append((mp, mem_kinds))

    if not daemon_mod.ping(root):
        console.print(
            "[yellow]no daemon up — embed runs faster through `rmx daemon start` "
            "so the model stays loaded between calls.[/]"
        )

    total_embedded = 0
    for part, part_kinds in plan:
        console.print(
            f"[dim]embedding kinds={','.join(part_kinds)} partition={part} "
            f"(batch={batch}); the first batch warms the model (~134MB)…[/]"
        )
        iters = 0
        while True:
            iters += 1
            args = {
                "kinds": part_kinds, "limit": batch,
                "rebuild": rebuild and iters == 1,
                # Daemon is bound to its startup partition; without this
                # the embed lands in `<root>/vectors/<daemon-partition>/...`
                # regardless of -p, so memory recall against memory-<project>
                # comes up empty even after a "successful" rebuild.
                "partition": part,
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
                f"[dim]  ⋯ embed batch {iters}: +{embedded} "
                f"({total_embedded} done, {remaining} left)[/]"
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
        d.store = _read_store()  # replica-first; never the writer slot
        result = _op_ann_search(d, args)
    if result.get("ok") is False:
        raise click.ClickException(result.get("error", "ann_search failed"))

    hits = result.get("hits", [])
    if not hits:
        console.print("[yellow]no hits[/]")
        return

    # Resolve ids to (kind, name) via a read-only Store for a readable
    # table. Lock-free against the daemon's writer.
    s = _read_store()
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
    "--json", "as_json", is_flag=True,
    help="Emit ranked hits as JSON (rank/id/score/kind/name/path). Parity "
         "with context / memory recall / scan-prompt.",
)
@click.option(
    "--no-dense", is_flag=True,
    help="Skip the dense side entirely. Just returns the symbolic list "
         "(or empty if no --symbolic given). Use when [dense] isn't "
         "installed.",
)
def recall_cmd(query, k, kinds, concept, symbolic, as_json, no_dense):
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

    # Recall is read-only: bitmap prefilter, ANN ranking, then name
    # lookup. Use the lock-free reader so we don't race the daemon's
    # writer.
    s = _read_store()
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

    con = s._connect()
    if as_json:
        # Every other read surface (`context`, `memory recall`, `scan-prompt`,
        # `query`) speaks JSON; this one only ever rendered a rich table, so a
        # programmatic caller had to scrape it. Emitted before the empty check
        # so "no hits" is a parseable [] rather than prose on stdout.
        out = []
        for rank, (eid, score) in enumerate(ranked, 1):
            row = con.execute(
                "SELECT kind, name, path FROM entities WHERE id = ?", [eid],
            ).fetchone()
            out.append({
                "rank": rank, "id": eid, "score": float(score),
                "kind": row[0] if row else None,
                "name": row[1] if row else None,
                "path": row[2] if row else None,
            })
        click.echo(json.dumps(out))
        return

    if not ranked:
        console.print("[yellow]no hits[/]")
        return

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
    """Resolve the memory partition for the active CLI invocation.

    Post-0.5.0 default: project partition (`default_partition_name`),
    NOT `memory-<project>`. The split that existed for ADR-0001 Phase
    B → Phase C made cross-partition wikilinks unresolvable so
    memory→memory rel: edges from sync-disk silently dropped. Recall's
    existing kind=memory filter already separates memory results at
    query time, so the noise concern the split addressed is handled
    without the split.

    Migration auto-detect: if the legacy `memory-<project>` partition
    still exists (a host that hasn't run `rmx partition merge`), keep
    routing to it so existing data stays reachable. After the operator
    runs the merge (drops the legacy partition row), the default flips
    to the project partition automatically.
    """
    from refmatrix.store import default_partition_name
    try:
        root = _root()
        project = root.resolve().parent.name or "default"
        legacy = f"{MEMORY_PARTITION_PREFIX}{project}"
        # Best-effort legacy detection: peek at partitions table without
        # holding the writer lock. Daemon-up call is preferred so a CLI
        # invocation while the daemon owns the lock doesn't crash on
        # the read; daemon-down falls back to a lock-free reader.
        if _legacy_memory_partition_exists(root, legacy):
            return legacy
        return default_partition_name(root)
    except Exception:
        return f"{MEMORY_PARTITION_PREFIX}default"


def _legacy_memory_partition_exists(root: Path, legacy: str) -> bool:
    """True when the `memory-<project>` partition row is still present
    (pre-merge state). Caches per process so repeated `rmx memory`
    invocations don't re-query.

    Read paths (in order of preference, all lock-free):
      1. Daemon RPC `partition_list` when the daemon is up. The daemon
         owns the writer slot; this is the safest read.
      2. `Store(read_only=True)` opened against the snapshot symlink
         (`read_only.duckdb`). Lock-free because the writer never
         attaches to the snapshot file.
      3. Snapshot/replica absent (bootstrap window) → return False.
         A fresh tree has no legacy partition by definition; routing
         to the project partition is the correct default.

    NEVER opens the active rotation slot directly — that would crash
    with `Could not set lock on catalog.B.duckdb` whenever the daemon
    is alive but `ping()` momentarily failed (restart window, socket
    hiccup), exactly the path that produced the 0.5.1 regression."""
    cache_key = (str(root), legacy)
    cached = getattr(_legacy_memory_partition_exists, "_cache", {})
    if cache_key in cached:
        return cached[cache_key]
    found = False
    try:
        from refmatrix import daemon as daemon_mod
        if daemon_mod.ping(root):
            resp = daemon_mod.call(
                root, "partition_list", {}, timeout=10.0,
            )
            if resp.get("ok"):
                rows = resp["result"].get("rows", [])
                found = any(r.get("name") == legacy for r in rows)
        else:
            rs = _reader_store()
            if rs is not None:
                try:
                    row = rs._connect().execute(
                        "SELECT 1 FROM partitions WHERE name=?", (legacy,),
                    ).fetchone()
                    found = row is not None
                finally:
                    try:
                        rs.close()
                    except Exception:
                        pass
            # else: no snapshot yet → fresh tree → no legacy partition.
    except Exception:
        found = False
    cached[cache_key] = found
    _legacy_memory_partition_exists._cache = cached  # type: ignore[attr-defined]
    return found


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


@main.group("taxonomy")
def taxonomy_grp():
    """Shared memory-tag vocabulary (~/.refmatrix/taxonomy.json). Validation is
    soft — off-vocabulary tags warn, never block."""


@taxonomy_grp.command("list")
def taxonomy_list():
    """Show the tag vocabulary grouped by category."""
    from refmatrix import taxonomy as _tax
    data = _tax.load()
    cats = data.get("categories", {})
    if not cats:
        console.print("[yellow]empty taxonomy[/]")
        return
    for cat_name, cat in cats.items():
        console.print(f"[bold]{cat_name}[/]  [dim]{cat.get('description','')}[/]")
        for tag, meta in (cat.get("tags") or {}).items():
            console.print(f"  • {tag}  [dim]{meta.get('description','')}[/]")
    console.print(f"\n[dim]{_tax.taxonomy_path()}[/]")


@taxonomy_grp.command("add")
@click.argument("category")
@click.argument("tag")
@click.option("--desc", default="", help="Tag description.")
@click.option("--color", default="#64748b", help="Hex color for the UI.")
def taxonomy_add(category, tag, desc, color):
    """Add (or update) a tag under a category."""
    from refmatrix import taxonomy as _tax
    _tax.add_tag(category, tag, description=desc, color=color)
    console.print(f"[green]added[/] {tag} → {category}")


@taxonomy_grp.command("remove")
@click.argument("tag")
def taxonomy_remove(tag):
    """Remove a tag from the vocabulary."""
    from refmatrix import taxonomy as _tax
    if _tax.remove_tag(tag):
        console.print(f"[green]removed[/] {tag}")
    else:
        console.print(f"[yellow]not in taxonomy:[/] {tag}")


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
@click.option("--global", "is_global", is_flag=True,
              help="Write to the shared cross-project global behavior store "
                   "(~/.refmatrix/global) instead of this project.")
def memory_add(name, content, mtype, tags, meta, protect, is_global):
    """Add or update a memory entity."""
    _memory_intent("memory_add")
    if content == "-":
        content = sys.stdin.read()
    meta_d = json.loads(meta) if meta else None
    tags_l = list(tags) if tags else None
    if tags_l:
        from refmatrix import taxonomy as _tax
        _, unknown = _tax.validate(tags_l)
        if unknown:
            console.print(
                f"[yellow]note:[/] off-vocabulary tag(s): {', '.join(unknown)} "
                f"(add via `rmx taxonomy add <category> <tag>`)"
            )
    if is_global:
        from refmatrix import hub as hub_mod
        resp = hub_mod.global_call("memory_add", {
            "name": name, "content": content, "mtype": mtype,
            "tags": tags_l, "metadata": meta_d, "protected": protect})
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        console.print(f"[green]global memory[/] {name} "
                      f"(id={resp['result']['id']}) {mtype}")
        return
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
@click.option("--degree", default=0, type=int,
              help="When >0, ALSO render the context bundle for this memory "
                   "(anchor + one-hop neighbors + their bodies). Same shape "
                   "as `rmx context`. Lets a single `memory get` call return "
                   "body + graph instead of forcing two commands.")
def memory_get(name_or_id, degree):
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
        s = _read_store()
        m = s.get_memory(target)
    if m is None:
        raise click.ClickException(f"no memory matching {name_or_id!r}")
    console.print(f"[bold]{m['name']}[/]  id={m['id']}  mtype={m['mtype']}")
    if m["tags"]:
        console.print(f"  tags: {', '.join(m['tags'])}")
    if m["metadata"]:
        console.print(f"  meta: {m['metadata']}")
    console.print()
    # `click.echo` here, NOT `console.print`: Rich's markup parser
    # consumes `[[name]]` patterns (interpreting `[name]` as a tag)
    # and strips them to `[]`, mangling every GMD `rel:` wikilink in
    # the body. `click.echo` writes the raw bytes verbatim.
    click.echo(m["content"] or "")
    if degree > 0:
        # Render the context bundle alongside the body so a `memory get
        # --degree 1` call covers both surfaces in one shot. Route
        # through the same daemon path the `rmx context` CLI uses so
        # callers see identical output.
        from refmatrix.context import build_context, render_text
        console.print()
        console.print("[bold]--- context ---[/]")
        if daemon_mod.ping(root):
            ctx_args = {
                "ref": m["name"], "format": "text",
                "degree": degree,
                "entities_explicit": False, "tokens_explicit": False,
                "partition": _resolve_partition(),
            }
            ctx_resp = daemon_mod.call(
                root, "context", ctx_args, timeout=120.0,
            )
            if ctx_resp.get("ok"):
                click.echo(ctx_resp["result"]["body"])
            else:
                console.print(
                    f"[yellow]context unavailable: "
                    f"{ctx_resp.get('error')}[/]"
                )
        else:
            s = _read_store()
            click.echo(render_text(
                build_context(
                    s, m["name"], degree=degree,
                    _entities_explicit=False, _tokens_explicit=False,
                )
            ))


@memory_grp.command("promote")
@click.argument("name_or_id")
def memory_promote(name_or_id):
    """Copy a project memory into the shared global behavior store. Both reads
    and the write route through daemons (no direct Store opens)."""
    _memory_intent("memory_get")
    from refmatrix import daemon as daemon_mod, hub as hub_mod
    root = _root()
    target = int(name_or_id) if name_or_id.isdigit() else name_or_id
    args = {"id": target} if isinstance(target, int) else {"name": target}
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_get", args)
        m = resp.get("result", {}).get("memory") if resp.get("ok") else None
    else:
        raise click.ClickException("daemon not running for this project")
    if m is None:
        raise click.ClickException(f"no memory matching {name_or_id!r}")
    tags = list(dict.fromkeys((m.get("tags") or []) + ["behavior"]))
    g = hub_mod.global_call("memory_add", {
        "name": m["name"], "content": m["content"],
        "mtype": m.get("mtype") or "feedback", "tags": tags,
        "metadata": m.get("metadata")})
    if not g.get("ok"):
        raise click.ClickException(g.get("error", "global write failed"))
    console.print(f"[green]promoted to global[/] {m['name']} "
                  f"(global id={g['result']['id']})")


@memory_grp.command("reclassify")
@click.option("--to", "to_mtype", required=True, help="New mtype to set.")
@click.option("--like", default=None,
              help="Glob on memory name (e.g. '*save_state*'). * → SQL %.")
@click.option("--from", "from_mtype", default=None,
              help="Only reclassify memories currently of this mtype.")
@click.option("--name", "names", multiple=True, help="Explicit name (repeatable).")
@click.option("--dry-run", is_flag=True, help="Show matches without changing.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation.")
def memory_reclassify(to_mtype, like, from_mtype, names, dry_run, yes):
    """Bulk-change the mtype of memories (selector: --like / --from / --name).

    e.g. `rmx memory reclassify --like '*save_state*' --from project --to session-state`"""
    _memory_intent("memory_reclassify")
    if not (like or names):
        raise click.ClickException("need --like or --name to select memories")
    from refmatrix import daemon as daemon_mod
    args = {"to_mtype": to_mtype, "like": like, "from_mtype": from_mtype,
            "names": list(names) or None, "dry_run": True}
    root = _root()
    daemon_up = daemon_mod.ping(root)
    # preview first
    if daemon_up:
        resp = _memory_daemon_call("memory_reclassify", args)
        prev = resp.get("result", {}) if resp.get("ok") else None
        if prev is None:
            raise click.ClickException(resp.get("error", "daemon error"))
    else:
        s = _store()
        prev = s.reclassify_memories(to_mtype=to_mtype, like=like,
                                     from_mtype=from_mtype,
                                     names=list(names) or None, dry_run=True)
    n = prev["matched"]
    if n == 0:
        console.print("[yellow]no memories matched[/]")
        return
    console.print(f"[bold]{n}[/] memories → mtype [cyan]{to_mtype}[/]")
    for nm in prev["names"][:10]:
        console.print(f"  {nm}")
    if n > 10:
        console.print(f"  … +{n - 10} more")
    if dry_run:
        return
    if not yes and not click.confirm(f"reclassify {n} memories?"):
        return
    args["dry_run"] = False
    if daemon_up:
        resp = _memory_daemon_call("memory_reclassify", args)
        res = resp.get("result", {}) if resp.get("ok") else None
        if res is None:
            raise click.ClickException(resp.get("error", "daemon error"))
    else:
        res = s.reclassify_memories(to_mtype=to_mtype, like=like,
                                    from_mtype=from_mtype,
                                    names=list(names) or None, dry_run=False)
    console.print(f"[green]reclassified[/] {res['changed']} → {to_mtype}")


@memory_grp.command("retag")
@click.argument("name_or_id")
@click.option("--add", "add_tags", multiple=True, help="Tag to add (repeatable).")
@click.option("--remove", "rm_tags", multiple=True, help="Tag to remove (repeatable).")
@click.option("--set", "set_tags", multiple=True,
              help="Replace ALL tags with these (overrides --add/--remove).")
def memory_retag(name_or_id, add_tags, rm_tags, set_tags):
    """Add/remove/replace a memory's tags."""
    _memory_intent("memory_retag")
    add_l = list(add_tags) or None
    rm_l = list(rm_tags) or None
    set_l = list(set_tags) if set_tags else None
    check = set_l if set_l is not None else (add_l or [])
    if check:
        from refmatrix import taxonomy as _tax
        _, unknown = _tax.validate(check)
        if unknown:
            console.print(
                f"[yellow]note:[/] off-vocabulary tag(s): {', '.join(unknown)}"
            )
    from refmatrix import daemon as daemon_mod
    root = _root()
    target = int(name_or_id) if name_or_id.isdigit() else name_or_id
    args: dict = {"add": add_l, "remove": rm_l, "replace": set_l}
    args["id" if isinstance(target, int) else "name"] = target
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_retag", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        new = resp["result"]["tags"]
    else:
        s = _store()
        new = s.retag_memory(target, add=add_l, remove=rm_l, replace=set_l)
    if new is None:
        raise click.ClickException(f"no memory matching {name_or_id!r}")
    console.print(f"[green]retagged[/] {name_or_id}: {', '.join(new) if new else '(none)'}")


@memory_grp.command("list")
@click.option("--type", "mtype", default=None,
              help="Filter by mtype.")
@click.option("--tag", "tags", multiple=True,
              help="Filter by tag (repeatable). AND by default; --tag-any for OR.")
@click.option("--tag-any", "tag_any", is_flag=True, default=False,
              help="Match ANY of --tag instead of ALL.")
@click.option("--limit", "-n", type=int, default=20, show_default=True)
def memory_list(mtype, tags, tag_any, limit):
    """List memories in the active partition."""
    _memory_intent("memory_iter")
    from refmatrix import daemon as daemon_mod
    root = _root()
    tags = list(tags) or None
    tags_match = "any" if tag_any else "all"
    args = {"mtype": mtype, "limit": limit, "tags": tags, "tags_match": tags_match}
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_iter", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        s = _read_store()
        rows = list(s.iter_memories(
            mtype=mtype, limit=limit, tags=tags, tags_match=tags_match))
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
@click.option("--tag", "tags", multiple=True,
              help="Filter by tag (repeatable). AND by default; --tag-any for OR.")
@click.option("--tag-any", "tag_any", is_flag=True, default=False,
              help="Match ANY of --tag instead of ALL.")
@click.option("--limit", "-n", type=int, default=20, show_default=True)
def memory_search(query, tags, tag_any, limit):
    """Case-insensitive substring search over memory name + content.
    Returns matching rows newest-first. For dense / hybrid retrieval,
    use `rmx memory recall`."""
    _memory_intent("memory_search")
    from refmatrix import daemon as daemon_mod
    root = _root()
    tags = list(tags) or None
    tags_match = "any" if tag_any else "all"
    args = {"query": query, "limit": limit, "tags": tags, "tags_match": tags_match}
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_search", args)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        rows = resp["result"]["rows"]
    else:
        s = _read_store()
        rows = s.search_memories(query, limit=limit, tags=tags, tags_match=tags_match)
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


def _ann_similarity(distance: float) -> float:
    """Cosine similarity (higher = closer) from a Lance L2 distance over
    L2-normalized embedding vectors. For unit vectors ‖a−b‖² = 2(1 − cos), so
    cos = 1 − d²/2. The daemon's ANN op returns the raw L2 *distance*
    (ascending = best); converting here lets `memory recall` show a `score`
    that rises with rank instead of a distance mislabeled "score"."""
    return 1.0 - (distance * distance) / 2.0


def _recall_display_score(h: dict) -> "float | None":
    """Display score (higher = better, agrees with rank order) for a recall
    hit. A fused hit carries an RRF `score` — use it directly. A pure-dense
    hit carries an L2 `distance` — convert to cosine similarity."""
    if h.get("fused"):
        s = h.get("score")
        return float(s) if isinstance(s, (int, float)) else None
    d = h.get("distance")
    if d is None:
        d = h.get("score")  # pure-dense legacy hit shape
    return _ann_similarity(float(d)) if isinstance(d, (int, float)) else None


def _global_recall_rows(q, *, k, recent, since_s):
    """Recall from the hub-owned global behavior store — routed through ITS
    daemon (global_call ensures it's up), never a direct Store() open, so we
    don't reintroduce catalog lock contention. Lexical/recent only (no embedder
    needed), keeping the UserPromptSubmit/SessionStart hooks cheap."""
    from refmatrix import hub as hub_mod
    if not hub_mod.global_store_root().exists():
        return []
    if recent:
        op, args = "memory_recent", {"since_seconds": since_s, "limit": k}
    elif q:
        op, args = "memory_search", {"query": q, "limit": k}
    else:
        return []
    try:
        resp = hub_mod.global_call(op, args, timeout=30.0)
    except Exception:
        return []
    rows = resp.get("result", {}).get("rows", []) if resp.get("ok") else []
    for r in rows:
        r["scope"] = "global"
    return rows


def _merge_scope(project_rows, global_rows, k, scope):
    """Combine project + global recall. `both` round-robins so global behavior
    memories are guaranteed representation, not truncated behind project hits."""
    for r in project_rows:
        r.setdefault("scope", "project")
    for r in global_rows:
        r.setdefault("scope", "global")
    if scope == "global":
        return global_rows[:k]
    if scope == "project":
        return project_rows[:k]
    out, seen = [], set()
    pi = gi = 0
    while len(out) < k and (pi < len(project_rows) or gi < len(global_rows)):
        if pi < len(project_rows):
            r = project_rows[pi]; pi += 1
            if r.get("name") not in seen:
                seen.add(r.get("name")); out.append(r)
        if len(out) >= k:
            break
        if gi < len(global_rows):
            r = global_rows[gi]; gi += 1
            if r.get("name") not in seen:
                seen.add(r.get("name")); out.append(r)
    return out


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

        # When --degree>0 attached a context bundle to this row, fold
        # it into the GMD as a fenced block so prompt-injection
        # consumers see graph + body inline instead of having to
        # re-fetch.
        ctx = (m.get("context") or "").strip()
        if ctx:
            lines.append("")
            lines.append("```")
            for cl in ctx.splitlines():
                lines.append(cl)
            lines.append("```")

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
@click.option("--text", "text", default=None,
              help="Alias of the positional query / --prompt, for parity "
                   "with context / scan-prompt.")
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
@click.option("--exclude-mtype", "exclude_mtype", multiple=True,
              callback=_split_csv,
              help="Filter out memories whose mtype matches any of the "
                   "given values. Repeat the flag or pass a comma-separated "
                   "list (`--exclude-mtype session-request,session-milestone`). "
                   "Glob patterns supported (fnmatch), so namespaced mtypes "
                   "filter by prefix: `--exclude-mtype 'session/*'` hides "
                   "session/recall-state + session/digest in one value. "
                   "Filter is applied client-side after the recall RPC "
                   "returns.")
@click.option("--include-session", is_flag=True, default=False,
              help="Opt back into session/* memories (save-state handoffs, "
                   "STM digests) in the always-on hook modes (--session-start / "
                   "--stdin-json), which exclude them by default. Their multi-KB "
                   "bodies otherwise dominate the per-prompt injection budget; "
                   "`rmx recall-state` surfaces the latest handoff on demand.")
@click.option("--degree", default=0, type=int,
              help="When >0, attach a context bundle (body + one-hop "
                   "neighbors with their bodies) to each hit. JSON output "
                   "gains a `context` field per row; table output appends "
                   "the rendered context block under each row. Cost is N "
                   "extra daemon context calls; keep low for hook latency.")
@click.option("--rerank/--no-rerank", "rerank", default=None,
              help="Cross-encoder rerank of the dense/fused shortlist "
                   "(daemon-side, subprocess model). Default: RMX_RERANK. "
                   "Reorders only \u2014 it cannot surface a memory retrieval "
                   "missed, so raise -k if recall is the problem. Note the "
                   "score column then shows cross-encoder logits, not cosine "
                   "similarity: comparable within one result set, not across.")
@click.option("--fuse/--no-fuse", "fuse", default=False, show_default=True,
              help="--fuse (opt-in): RRF-fuse dense ANN with symbolic "
                   "content_rank (BM25), so rare-keyword queries surface the "
                   "lexically-exact memory dense alone misses. The lexical win "
                   "is a scale effect; on small memory sets it is muted/mixed, "
                   "so it stays opt-in until a labeled memory-recall eval tunes "
                   "rrf_k. Default = pure dense ANN.")
@click.option("--scope", type=click.Choice(["project", "global", "both"]),
              default="project", show_default=True,
              help="project: this store only. global: the shared cross-project "
                   "behavior store only. both: round-robin merge so global "
                   "behavior memories surface alongside project hits (what the "
                   "recall hook uses).")
@click.option("--subject", default=None,
              help="Recall the memories filed under a SUBJECT (ADR-0002): walk "
                   "the `part-of` index for this subject (id, `subject_<slug>` "
                   "name, or bare label), newest first. Composes with "
                   "--exclude-mtype / -k. The cross-session 'everything on X'.")
def memory_recall(query, prompt_query, text, stdin_json, k, recent, since,
                  session_start, as_json, as_gmd, kinds, exclude_mtype,
                  include_session, degree, fuse, scope, subject, rerank):
    """Memory retrieval. Three modes:

    Dense (default): pure dense ANN (cosine over bge-small vectors) on the
    memory partition. Requires the [dense] extra + embedded memories
    (rmx embed --kinds memory).

    Hybrid (--fuse, opt-in): RRF fusion of dense ANN with symbolic
    content_rank (BM25 over the mentions index). content_rank rewards rare
    exact query terms that a 384-dim dense vector dilutes into topical space,
    so a rare-keyword query surfaces the lexically-exact memory dense alone
    ranks far down. The win is a scale effect — muted/mixed on small memory
    sets — so it is opt-in until a labeled memory-recall eval tunes rrf_k.

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
    # Uniform resolution: positional query > --text > --prompt > --stdin-json
    # envelope. read_stdin=False so --recent doesn't consume an unrelated pipe;
    # an explicit --stdin-json still reads + parses (raising on bad JSON).
    q = _resolve_query(query, text, prompt_query, stdin_json=stdin_json,
                       read_stdin=False)
    if stdin_json and not q:
        # UserPromptSubmit hook fired with an empty prompt (slash command,
        # /clear, /resume etc): non-fatal — emit a parseable empty artifact so
        # the hook can detect "no recall" deterministically, and exit 0.
        if as_json:
            click.echo("[]")
        elif as_gmd:
            click.echo(_render_memory_gmd(
                [], query=None, mode="empty",
                partition=_resolve_partition(),
            ))
        return
    if not recent and not q and not subject:
        raise click.ClickException(
            "rmx memory recall needs a QUERY (or --text / --prompt / "
            "--stdin-json), --recent, --session-start, or --subject"
        )

    exclude_mtypes = set(exclude_mtype) if exclude_mtype else set()
    # Always-on injection hooks (SessionStart --session-start, UserPromptSubmit
    # --stdin-json) must NOT re-dump save-state / STM-digest bodies every prompt:
    # they're multi-KB each and at -k 5 blow the injection budget → "Output too
    # large" truncation (cliquedb UX report 2026-07-09). Exclude the session/*
    # mtype family by default in these modes; --include-session opts back in.
    # The latest handoff still surfaces on demand via `rmx recall-state`
    # (handoff.compose_recall_state — a different path from this recall).
    if (session_start or stdin_json) and not include_session:
        exclude_mtypes.add("session/*")

    def _mt_excluded(mtype: "str | None") -> bool:
        """True if mtype matches any --exclude-mtype value. Patterns glob
        (fnmatchcase) so namespaced mtypes filter by prefix —
        `--exclude-mtype 'session/*'` hides session/recall-state +
        session/digest. Plain values without glob chars still match
        exactly."""
        if not exclude_mtypes:
            return False
        from fnmatch import fnmatchcase
        m = mtype or ""
        return any(fnmatchcase(m, pat) for pat in exclude_mtypes)

    def _global_rows(qq, *, recent_flag, since):
        """Global-store rows for the --scope both/global merge, with the SAME
        `--exclude-mtype` filter applied as the project side. Without this the
        session/* exclusion (and any explicit --exclude-mtype) leaked global
        save-state / digest rows straight past the filter (cliquedb UX report
        2026-07-09). Over-fetch when filtering so the merge still has k."""
        gk = k * 10 if exclude_mtypes else k
        grows = _global_recall_rows(qq, k=gk, recent=recent_flag, since_s=since)
        if exclude_mtypes:
            grows = [r for r in grows if not _mt_excluded(r.get("mtype"))]
        return grows

    def _attach_context(rows: list[dict]) -> list[dict]:
        """When --degree > 0, fetch a context bundle per row and stash
        the rendered text on `row['context']`. Daemon-side: routes
        through the same `_op_context` the `rmx context` CLI uses, so
        the output shape matches. No-op for degree=0.
        Best-effort: a per-row failure leaves `context` unset rather
        than breaking the whole recall response."""
        if degree <= 0:
            return rows
        from refmatrix import daemon as daemon_mod
        root = _root()
        if not daemon_mod.ping(root):
            # Degraded mode: in-process build, no daemon.
            from refmatrix.context import build_context, render_text
            s = _read_store()
            for row in rows:
                try:
                    b = build_context(
                        s, row["name"], degree=degree,
                        _entities_explicit=False, _tokens_explicit=False,
                    )
                    row["context"] = render_text(b)
                except Exception:
                    row["context"] = None
            return rows
        for row in rows:
            try:
                ctx_resp = daemon_mod.call(
                    root, "context",
                    {"ref": row["name"], "format": "text",
                     "degree": degree,
                     "entities_explicit": False,
                     "tokens_explicit": False,
                     "partition": _resolve_partition()},
                    timeout=120.0,
                )
                row["context"] = (
                    ctx_resp.get("result", {}).get("body")
                    if ctx_resp.get("ok") else None
                )
            except Exception:
                row["context"] = None
        return rows

    if subject:
        # ADR-0002: recall the leaves filed under a subject (walk part-of),
        # newest first. Composes with --exclude-mtype / -k. daemon-or-inproc.
        from refmatrix import daemon as daemon_mod
        if daemon_mod.ping(_root()):
            resp = _memory_daemon_call("subject_leaves", {"subject": subject})
            rows = resp.get("result", {}).get("rows", []) if resp.get("ok") else []
        else:
            rows = _store().subject_leaves(subject)
        rows = [r for r in rows if not _mt_excluded(r.get("mtype"))][:k]
        rows = _attach_context(rows)
        if as_json:
            import json as _json
            click.echo(_json.dumps(rows, indent=2))
            return
        if as_gmd:
            click.echo(_render_memory_gmd(
                rows, query=None, mode="subject",
                partition=_resolve_partition()))
            return
        if not rows:
            console.print(f"[yellow]no memories filed under subject[/] {subject!r}")
            return
        t = Table("rank", "id", "name", "mtype", "content")
        for i, m in enumerate(rows, 1):
            t.add_row(str(i), str(m["id"]), m["name"], m.get("mtype") or "",
                      (m.get("content") or "")[:80])
        console.print(t)
        return

    if recent:
        since_s = _parse_duration(since) if since else None
        from refmatrix import daemon as daemon_mod
        # Over-fetch when filtering so the final list still has k rows.
        # Cap at 10× to avoid pathological cases on heavily-polluted
        # partitions.
        effective_k = k * 10 if exclude_mtypes else k
        if daemon_mod.ping(_root()):
            resp = _memory_daemon_call(
                "memory_recent",
                {"since_seconds": since_s, "limit": effective_k},
            )
            if not resp.get("ok"):
                raise click.ClickException(resp.get("error", "daemon error"))
            rows = resp["result"]["rows"]
        else:
            s = _store()
            rows = s.recent_memories(since_seconds=since_s, limit=effective_k)
        if exclude_mtypes:
            rows = [r for r in rows if not _mt_excluded(r.get("mtype"))][:k]
        if scope != "project":
            rows = _merge_scope(
                rows, _global_rows(None, recent_flag=True, since=since_s),
                k, scope)
        rows = _attach_context(rows)
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
        if degree > 0:
            # Table mode: append the per-row context block under the
            # table so the operator sees graph + body alongside the
            # ranked list. JSON/GMD modes carry it inline via the
            # `context` field set by `_attach_context`.
            for i, m in enumerate(rows, 1):
                ctx = m.get("context")
                if ctx:
                    console.print()
                    console.print(f"[bold]#{i} {m['name']} — context[/]")
                    click.echo(ctx)
        return

    # Hybrid path. _memory_daemon_call injects the active partition so
    # the daemon (bound to whatever partition it was started on) can
    # still serve recall against the project's memory partition.
    from refmatrix import daemon as daemon_mod
    root = _root()
    kinds_list = list(kinds) if kinds else ["memory"]
    # Over-fetch when mtype filter is active so the surviving list still
    # has k rows after exclusion. 3× covers most pollution levels; user
    # can raise -k for partitions with denser noise.
    ann_k = k * 3 if exclude_mtypes else k
    args = {"query": q, "k": ann_k, "kinds": kinds_list, "fuse": fuse}
    # None = let the daemon apply its RMX_RERANK default; explicit
    # --rerank/--no-rerank overrides it for this call only.
    if rerank is not None:
        args["rerank"] = bool(rerank)
    if not daemon_mod.ping(root):
        raise click.ClickException(
            "rmx memory recall needs the daemon up (dense embedder lives there)"
        )
    # 180s covers worst-case embedder cold-start (sentence-transformers
    # model load on a busy CPU takes 30-90s). Steady-state recall is
    # sub-second once the daemon's _embedder cache warms.
    resp = _memory_daemon_call("memory_recall", args, timeout=180.0)
    if not resp.get("ok"):
        raise click.ClickException(resp.get("error", "daemon error"))
    hits = resp["result"].get("hits", [])
    # Best-first by ascending L2 distance so the displayed `score` (cosine
    # similarity, higher = better) decreases monotonically with rank — the
    # column and the row order cannot disagree. The daemon already sorts
    # ascending; this makes the invariant explicit and robust to hit shape.
    hits = sorted(
        hits,
        key=lambda h: (
            h["distance"] if h.get("distance") is not None
            else -(h.get("score") or 0.0)
        ),
    )
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
            if len(rows) >= k:
                break
            eid = h.get("entity_id") or h.get("id")
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
                if _mt_excluded(m.get("mtype")):
                    continue
                # Honest fields, higher = better, agreeing with rank order.
                # Fused hits carry an RRF `score`; pure-dense hits a cosine
                # similarity derived from the raw L2 `distance` (kept too).
                m["score"] = _recall_display_score(h)
                m["distance"] = h.get("distance")
                m["fused"] = bool(h.get("fused"))
                rows.append(m)
        if scope != "project":
            rows = _merge_scope(
                rows, _global_rows(q, recent_flag=False, since=None),
                k, scope)
        rows = _attach_context(rows)
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
    table_rows: list[dict] = []
    shown = 0
    for h in hits:
        if shown >= k:
            break
        eid = h.get("entity_id") or h.get("id")
        score = _recall_display_score(h)
        m = _fetch_memory(eid)
        if m and _mt_excluded(m.get("mtype")):
            continue
        name = m["name"] if m else "?"
        shown += 1
        t.add_row(
            str(shown),
            f"{score:.4f}" if isinstance(score, float) else str(score),
            str(eid), name,
        )
        if m is not None:
            table_rows.append(m)
    if scope != "project":
        seen_names = {m.get("name") for m in table_rows}
        for gr in _global_rows(q, recent_flag=False, since=None):
            if shown >= k:
                break
            if gr.get("name") in seen_names:
                continue
            shown += 1
            t.add_row(str(shown), "—", str(gr.get("id")),
                      f"{gr['name']} [global]")
            table_rows.append(gr)
    console.print(t)
    if degree > 0 and table_rows:
        # Mirror the recent-mode behavior: render per-hit context blocks
        # under the ranked table for table mode.
        ctx_rows = _attach_context(table_rows)
        for i, m in enumerate(ctx_rows, 1):
            ctx = m.get("context")
            if ctx:
                console.print()
                console.print(f"[bold]#{i} {m['name']} — context[/]")
                click.echo(ctx)


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
                nargs=-1, required=False)
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

    if not paths:
        # No-arg → sync the whole curated-memory dir for this project, matching
        # the save-state skill's "sync the memory tree" contract.
        default_dir = _default_memory_dir(root.parent)
        if not default_dir.is_dir():
            raise click.ClickException(
                f"no PATHS given and default memory dir does not exist: "
                f"{default_dir}")
        paths = (default_dir,)
        click.echo(f"# no PATHS given — syncing default memory dir: "
                   f"{default_dir}", err=True)

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


@memory_grp.command("dedup")
@click.option("--dry-run", is_flag=True,
              help="Report the dup count without folding.")
def memory_dedup(dry_run):
    """Fold concept↔memory duplicate nodes into the memory (pre-0.7.6 debt).

    The GMD `__root__` node used to mint a concept twinning each doc-level
    memory, splitting a subject's edges across two nodes. New ingests no
    longer create them (the ingest_gmd fix); this migrates any lingering
    concept's edges onto the same-named memory and drops the concept.
    Operates on the active partition. Routes through the daemon when one is up.
    """
    _memory_intent("memory_dedup")
    s = _store(write=True)
    res = s.fold_concept_dups(dry_run=dry_run)
    verb = "would fold" if res.get("dry_run") else "folded"
    console.print(
        f"[green]{verb}[/] {res.get('folded', 0)} concept↔memory dup(s), "
        f"{res.get('edges_migrated', 0)} edge(s) migrated"
    )


@memory_grp.command("compile")
@click.option("--k", type=int, default=8, show_default=True,
              help="Dense neighbours considered per memory.")
@click.option("--threshold", type=float, default=None,
              help="Absolute cosine floor. Default is adaptive — see "
                   "--threshold-pct — because an absolute cosine means "
                   "nothing across corpora of different breadth.")
@click.option("--threshold-pct", type=float, default=95.0, show_default=True,
              help="Percentile of this corpus's own pair-similarity "
                   "distribution to use as the floor.")
@click.option("--mutual/--no-mutual", default=True, show_default=True,
              help="Require reciprocal kNN membership. Without it a single "
                   "generic memory welds unrelated groups into one blob.")
@click.option("--beta", type=float, default=1.0, show_default=True,
              help="How hard shared concepts strengthen a dense edge.")
@click.option("--gamma", type=float, default=0.5, show_default=True,
              help="Weight multiplier for concept-only bridge edges.")
@click.option("--bridge-min", type=float, default=0.35, show_default=True,
              help="Concept similarity a NON-dense pair must clear to bridge.")
@click.option("--hub-df-frac", type=float, default=0.10, show_default=True,
              help="Concepts in more than this fraction of the corpus are "
                   "hubs and leave the concept space entirely.")
@click.option("--min-size", type=int, default=2, show_default=True,
              help="Smallest cluster that becomes a subject.")
@click.option("--signal", type=click.Choice(["fused", "dense", "concept"]),
              default="fused", show_default=True,
              help="Edge weighting. Ablation: run all three and compare "
                   "against the hand-declared part-of/amends edges.")
@click.option("--exclude-mtype", "exclude_mtypes", multiple=True,
              help="mtype glob to keep out of clustering (repeatable). "
                   "Defaults to session*/digest*/subject.")
@click.option("--max-subjects", type=int, default=None,
              help="Keep only the N largest clusters (drops are reported).")
@click.option("--apply", "do_apply", is_flag=True,
              help="Write subject nodes + part-of edges and emit the index. "
                   "Without it this is a preview.")
@click.option("--no-prune", is_flag=True,
              help="Keep previously-compiled part-of edges instead of "
                   "re-filing. Accretes; use only to inspect drift.")
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help="Where to write the GMD index ('-' for stdout). Default "
                   "is <root>/compiled/subjects.md — deliberately NOT the "
                   "memory dir, which would re-ingest it as a memory.")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw plan.")
def memory_compile(k, threshold, threshold_pct, mutual, beta, gamma,
                   bridge_min, hub_df_frac, min_size, signal, exclude_mtypes,
                   max_subjects, do_apply, no_prune, out, as_json):
    """Group memories into subjects and link crosscutting concepts.

    Clusters the partition's memories on a FUSED signal — dense cosine over
    the memory vectors sets the topology, idf-weighted concept overlap
    strengthens confirmed pairs and adds sparse bridges dense missed — then
    names each cluster by its highest-lift shared concept.

    Preview by default; `--apply` writes subject nodes + `part-of` edges
    (daemon-routed) and emits the GMD index.
    """
    from refmatrix import consolidate
    from refmatrix import daemon as daemon_mod

    _memory_intent("memory_compile")
    plan = consolidate.compile_memories(
        _read_store(), k=k, threshold=threshold, threshold_pct=threshold_pct,
        mutual=mutual, beta=beta, gamma=gamma, bridge_min=bridge_min,
        hub_df_frac=hub_df_frac, min_size=min_size, signal=signal,
        max_subjects=max_subjects,
        exclude_mtypes=list(exclude_mtypes) or None,
    )
    if as_json:
        console.print_json(json.dumps(plan))
        if not do_apply:
            return

    st, clusters = plan["stats"], plan["clusters"]
    if not as_json:
        if st.get("unembedded"):
            # Loud, not swallowed: an unembedded memory is INVISIBLE to
            # clustering, so a quiet run would under-report coverage.
            console.print(
                f"[yellow]{st['unembedded']} memory(ies) have no vector[/] — "
                f"excluded from clustering; run `rmx embed` first."
            )
        console.print(
            f"[dim]{st['candidates']} candidates · {st['embedded']} embedded · "
            f"{st.get('concept_space', 0)} informative concepts · "
            f"{st.get('edges', 0)} edges "
            f"({st.get('confirmed', 0)} concept-confirmed, "
            f"{st.get('bridges', 0)} bridges)[/]"
        )
        if not clusters:
            console.print("[yellow]no clusters[/] — loosen --threshold or "
                          "lower --min-size")
            return
        t = Table("subject", "size", "evidence (concept, lift)")
        for c in clusters:
            t.add_row(
                c["label"], str(c["size"]),
                ", ".join(f'{e["concept"]}×{e["lift"]}'
                          for e in c["evidence"][:3]) or "—",
            )
        console.print(t)
        if plan["crosscutting"]:
            console.print(
                "\n[bold]crosscutting[/] (bridge score = df × idf ÷ spread):")
            for x in plan["crosscutting"]:
                console.print(f"  {x['concept']} — {x['spread']} subjects, "
                              f"{x.get('df', 0)} memories "
                              f"(score {x['score']})")
        if plan["unclustered"]:
            console.print(
                f"\n[dim]{len(plan['unclustered'])} memory(ies) unclustered[/]")
        if st.get("dropped_clusters"):
            console.print(
                f"[yellow]--max-subjects dropped {st['dropped_clusters']} "
                f"cluster(s) / {st['dropped_members']} member(s)[/]")

    if not do_apply:
        if not as_json:
            console.print("\n[dim]preview only — re-run with --apply to "
                          "write subjects + part-of edges[/]")
        return

    root = _root()
    args = {"plan": plan, "prune": not no_prune}
    if daemon_mod.ping(root):
        resp = _memory_daemon_call("memory_compile_apply", args, timeout=180.0)
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        res = resp["result"]
    else:
        res = consolidate.apply_plan(
            _store(write=True), plan, prune=not no_prune)
    console.print(
        f"[green]applied[/] {len(res['subjects'])} subject(s), "
        f"{res['linked']} part-of edge(s) linked, "
        f"{res['unlinked']} stale edge(s) unlinked"
    )

    gmd = consolidate.render_gmd(
        plan, partition=plan["stats"].get("partition"))
    if str(out) == "-":
        console.print(gmd)
        return
    dest = Path(out) if out else consolidate.default_out_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(gmd)
    console.print(f"[green]index[/] {dest}")


@memory_grp.command("bulk-forget")
@click.option("--id", "ids", type=int, multiple=True,
              help="Entity id to forget (repeatable).")
@click.option("--name", "names", multiple=True,
              help="Memory name to forget within the active partition (repeatable).")
@click.option("--mtype", "mtypes", multiple=True,
              help="Forget every memory whose mtype matches (repeatable).")
@click.option("--dry-run", is_flag=True,
              help="Resolve the id set + per-mtype counts without deleting.")
@click.option("--yes", "-y", is_flag=True,
              help="Skip confirmation prompt (use after a --dry-run).")
def memory_bulk_forget(ids, names, mtypes, dry_run, yes):
    """Bulk-delete memories by id / name / mtype.

    Selection is the union of the supplied filters. The 271-card
    viascope session-card cleanup runs as:

        rmx memory bulk-forget \\
            --mtype session-request --mtype session-milestone --dry-run

    Then, after reviewing the count, repeat without --dry-run and
    confirm.
    """
    _memory_intent("memory_bulk_forget")
    if not ids and not names and not mtypes:
        raise click.ClickException(
            "at least one of --id, --name, --mtype is required"
        )
    from refmatrix import daemon as daemon_mod
    root = _root()
    args: dict = {"dry_run": dry_run}
    if ids:
        args["ids"] = list(ids)
    if names:
        args["names"] = list(names)
    if mtypes:
        args["mtypes"] = list(mtypes)

    if daemon_mod.ping(root):
        # Always run a dry-run first to drive the confirmation prompt;
        # this both gives the user a real count and short-circuits the
        # confirm when the filter matches nothing.
        preview = _memory_daemon_call(
            "memory_bulk_forget", {**args, "dry_run": True}, timeout=120.0,
        )
        if not preview.get("ok"):
            raise click.ClickException(preview.get("error", "daemon error"))
        result = preview["result"]
    else:
        s = _store()
        result = s.bulk_forget_memories(
            ids=args.get("ids"), names=args.get("names"),
            mtypes=args.get("mtypes"), dry_run=True,
        )

    count = len(result.get("ids", []))
    by_mtype = result.get("by_mtype", {})
    console.print(
        f"[bold]bulk-forget preview:[/] {count} memories selected"
    )
    for mt, n in sorted(by_mtype.items()):
        console.print(f"  {mt}: {n}")

    if count == 0 or dry_run:
        return

    if not yes and not click.confirm(
        f"Delete {count} memories and all their linkages?", default=False,
    ):
        console.print("[yellow]aborted[/]")
        return

    if daemon_mod.ping(root):
        resp = _memory_daemon_call(
            "memory_bulk_forget", args, timeout=600.0,
        )
        if not resp.get("ok"):
            raise click.ClickException(resp.get("error", "daemon error"))
        result = resp["result"]
    else:
        s = _store()
        result = s.bulk_forget_memories(
            ids=args.get("ids"), names=args.get("names"),
            mtypes=args.get("mtypes"), dry_run=False,
        )
    console.print(
        f"[green]forgot[/] {result.get('forgotten', 0)} memories"
    )


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


# ---- save-state / recall-state: session handoff (core in handoff.py) -------


@main.command("save-state")
@click.option("-m", "--message", default=None,
              help="Headline / notes to weave into the handoff.")
@click.option("--commit", is_flag=True,
              help="Also `git add -A && git commit` the repo (code only).")
@click.option("-s", "--session", default=None,
              help="STM session to compile. Default: active Claude session.")
@click.option("--memory-dir", "memory_dir", type=click.Path(path_type=Path),
              default=None, help="Override the curated-memory dir.")
@click.option("--dry-run", is_flag=True, help="Render to stdout; write nothing.")
@click.option("--no-lint", is_flag=True, help="Skip the GMD lint pass.")
@click.option("--promote/--no-promote", default=True, show_default=True,
              help="Also promote the condensed STM digest to durable memory.")
def save_state(message, commit, session, memory_dir, dry_run, no_lint, promote):
    """Compile + persist a session handoff — the resume point for the next instance.

    SAVES, into ONE durable GMD memory (`savestate_<session>`) in the curated-
    memory dir (overwritten each call: `created:` frozen, `updated:` refreshed):

    \b
      • git state — branch, HEAD sha + subject, commits-ahead-of-trunk,
        dirty-tree / uncommitted file list, and this-session's commits
      • Focus — top of the short-term working-memory graph (heaviest symbols
        by recency-weight: files, concepts), with event count
      • Tasks — the session's task stack (active item marked)
      • Recent memories — links to the most-recently-touched memory files
      • the headline / notes passed via `-m`

    Then (unless `--no-promote`) it PROMOTES a condensed STM digest
    (`focus_summary_<session>`, mtype `session/digest`) into the durable memory
    store — topics, milestones, intent arc, touched files — so the working
    memory graduates to LTM and `recall-state` / `memory recall` find it. If a
    subject is active, the digest is filed under it (`part-of`).

    The handoff file lands OUTSIDE the repo; the SessionStart bridge ingests it
    into rmx. `--commit` commits repo CODE only. `--dry-run` renders the file to
    stdout and writes nothing. Mirror of `recall-state`.
    """
    import time as _time

    root = _root()
    repo = root.parent
    sess = _resolve_stm_session(session, prefer_latest=True)
    today = _time.strftime("%Y-%m-%d")
    memdir = Path(memory_dir).resolve() if memory_dir else _default_memory_dir(repo)

    from refmatrix import stm as stm_mod
    s = stm_mod.Stm(root, sess)

    res = compose_save_state(s, root, repo=repo, memdir=memdir, today=today,
                             message=message, promote=promote, dry_run=dry_run)

    if dry_run:
        console.print(f"[dim]# would write {res['target']}[/]")
        click.echo(res["doc"])
        return

    console.print(f"[green]save-state[/] {res['target']}  "
                  f"[dim]({res['events']} events, session {sess})[/]")

    if not no_lint:
        lint = Path.home() / "claude_tools" / "gmd" / "lint.py"
        if lint.exists():
            out = _ss_sh(["python3", str(lint), res["target"]], repo)
            tag = "[green]lint ok[/]" if "0 error" in out.lower() or not out \
                else "[yellow]lint[/]"
            if out:
                console.print(f"{tag} {out.splitlines()[-1] if out else ''}")

    promoted = res.get("promoted")
    if promoted:
        if promoted.get("error"):
            console.print(f"[yellow]promote skipped:[/] {promoted['error']}")
        else:
            console.print(f"[green]promoted[/] {promoted['name']} "
                          f"(id={promoted.get('id')}) → durable memory")
            _file_under_active_subject(s, promoted.get("id"))

    subj = s.get_subject()
    if subj:
        console.print(f"[dim]subject:[/] {subj.get('label')} "
                      f"(slug={subj.get('subject')})")

    if commit:
        _ss_sh(["git", "add", "-A"], repo)
        msg = f"chore(save-state): {today} {message or 'session handoff'}"
        out = _ss_sh(["git", "commit", "-m", msg], repo)
        console.print(f"[green]committed[/] {out.splitlines()[0] if out else '(nothing to commit)'}")


@main.command("recall-state")
@click.option("-s", "--session", default=None,
              help="STM session to resume. Default: active Claude session.")
@click.option("--memory-dir", "memory_dir", type=click.Path(path_type=Path),
              default=None, help="Override the curated-memory dir.")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the structured resume payload as JSON.")
def recall_state(session, memory_dir, as_json):
    """Pull the prior session's handoff and orient — the mirror of save-state.

    Read-only. PULLS and reports, so the next instance starts warm instead of
    cold:

    \b
      • Latest save-state handoff (`savestate_<session>`) — the durable
        resume point: prior git state, focus, tasks, recent-memory links
      • STM focus digest — the live session's short-term working memory
        condensed (top symbols, topics, milestones, intent arc). Cold at a
        fresh session start; populated when recalled mid-session.
      • Recent memories — the most-recently-touched memory files
      • git state — branch, HEAD, commits-ahead-of-trunk, dirty tree
      • daemon health — running / pid for the active store
      • Anomalies — dirty tree, unmerged/undeployed commits, a stale daemon

    `--json` emits the raw payload (what the `rmx_recall_state` MCP tool
    returns). After this, decide the next action — recall-state does not start
    work on its own.
    """
    root = _root()
    repo = root.parent
    sess = _resolve_stm_session(session, prefer_latest=True)
    memdir = Path(memory_dir).resolve() if memory_dir else _default_memory_dir(repo)

    from refmatrix import stm as stm_mod
    s = stm_mod.Stm(root, sess)
    rep = compose_recall_state(s, root, repo=repo, memdir=memdir)

    if as_json:
        import json as _json
        click.echo(_json.dumps(rep, default=str, indent=2))
        return

    git = rep["git"]
    console.print(f"[bold]recall-state[/] · session {sess} "
                  f"[dim]({rep['events']} STM events)[/]")
    console.print(f"[bold]git[/] branch [cyan]{git['branch'] or '?'}[/] · "
                  f"HEAD {git['head'] or '?'}")
    if git["ahead_base"]:
        n = len([x for x in git["ahead"].splitlines() if x.strip()])
        console.print(f"     {n} commit(s) ahead of {git['ahead_base']}"
                      + ("" if n else " — in sync"))
    console.print(f"     working tree: "
                  + ("[yellow]dirty[/]" if git["dirty"] else "clean"))

    d = rep["daemon"]
    state = (f"[green]running[/] pid={d['pid']}" if d["running"]
             else (f"[yellow]busy pid {d['pid']}[/]" if d.get("busy")
                   else (f"[yellow]stale pid {d['pid']}[/]" if d["pid"]
                         else "[dim]not running[/]")))
    console.print(f"[bold]daemon[/] {state}")

    ss = rep["savestate"]
    if ss:
        console.print(f"[bold]handoff[/] [cyan]{ss['id']}[/] [dim]{ss['path']}[/]")
        body = ss["body"]
        excerpt = "\n".join(body.splitlines()[:24])
        console.print(excerpt)
    else:
        console.print("[yellow]no prior save-state handoff found[/]")

    if rep["recent_memories"]:
        console.print("[bold]recent memories[/]")
        for mid, title in rep["recent_memories"][:8]:
            console.print(f"  [cyan]{mid}[/] — {title}")

    if rep["stm_digest"]:
        console.print("[bold]STM digest (live session)[/]")
        console.print(rep["stm_digest"])

    if rep["anomalies"]:
        console.print("[bold yellow]anomalies[/]")
        for a in rep["anomalies"]:
            console.print(f"  [yellow]![/] {a}")


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
    # Skip sessions still being actively written. The live session's JSONL
    # changes every turn, so its content_hash never matches — without this it
    # gets fully re-parsed + re-ingested on every indexer tick, and a long
    # session's card grows until each GMD ingest holds the daemon's writer
    # lock for minutes (the wedge that times out `rmx stats`). A session
    # quiet for RMX_SESSION_INGEST_QUIET_S (default 300s) is treated as
    # settled and ingested once; --force overrides.
    import time as _time
    quiet_s = float(os.environ.get("RMX_SESSION_INGEST_QUIET_S", "300") or "300")
    now = _time.time()
    built: list[Path] = []
    skipped = 0
    active_skipped = 0
    for jp in jsonls:
        session_id = jp.stem
        if not force:
            try:
                age = now - jp.stat().st_mtime
            except OSError:
                age = quiet_s + 1.0
            if age < quiet_s:
                active_skipped += 1
                if verbose:
                    console.print(
                        f"  skip {session_id} (active — modified {age:.0f}s ago)"
                    )
                continue
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
        f"cards: built={len(built)} skipped={skipped} "
        f"active-skipped={active_skipped} total_jsonl={len(jsonls)}"
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
            return resp["result"]["rows"]
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
    from refmatrix.kwic import kwic_one
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
            mems = resp["result"]["rows"]
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
                "snippet": (
                    kwic_one(m.get("content") or "", query, width=160) or None
                    if query else None
                ),
            }
            for m in filtered
        ], indent=2, default=str))
        return

    if not filtered:
        console.print("[yellow]no matching sessions[/]")
        return

    from rich.table import Table
    from rich.text import Text
    # When the user gave a query, show the line where it actually matched —
    # otherwise the title alone (often "Recall state") says nothing about why
    # the session ranked. Match column off for the bare-list path.
    show_match = bool(query)
    t = Table(show_lines=show_match)
    t.add_column("session", style="cyan")
    t.add_column("ended", style="dim")
    t.add_column("branch")
    t.add_column("project", style="dim")
    t.add_column("title")
    if show_match:
        t.add_column("match")
    for m in filtered:
        sid = _session_meta_get(m, "session_id") or m.get("name", "")
        sid_short = sid[:8] if sid else "?"
        title = (m.get("content") or "").split("\n", 2)[0].lstrip("# ").strip()
        # strip {#root} suffix from title
        title = title.split(" {#")[0]
        ended = (_session_meta_get(m, "ended") or "")[:19]
        branch_s = _session_meta_get(m, "branch") or ""
        project_s = (_session_meta_get(m, "project") or "").split("/")[-1]
        row = [sid_short, ended, branch_s, project_s, title[:60]]
        if show_match:
            snip = kwic_one(m.get("content") or "", query, width=90)
            # Wrap as literal Text so body markup like `[link]` is not parsed
            # by rich; the «…» sentinels mark the matched term.
            row.append(Text(snip) if snip else Text("—", style="dim"))
        t.add_row(*row)
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


@main.command("cctree", context_settings={
    "ignore_unknown_options": True, "allow_extra_args": True,
    "help_option_names": [],
})
@click.pass_context
def cctree_cmd(ctx):
    """Prompt -> action tree for Claude Code sessions.

    Every flag is passed through to cctree unchanged (`rmx cctree --help` for
    the full set): --list, --session <id>, --json, --html OUT, --html-site DIR,
    --summary --all-projects, --follow, --full.

    The hub serves the same renderers at /cctree, so the tree is browsable
    without generating files.
    """
    import sys as _sys
    from refmatrix import cctree

    argv = _sys.argv
    try:
        # cctree parses sys.argv itself; hand it just the post-subcommand args
        # so `rmx cctree --list` and `cctree.py --list` behave identically.
        _sys.argv = ["cctree"] + list(ctx.args)
        cctree.main()
    finally:
        _sys.argv = argv


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


@main.group("concept")
def concept_grp():
    """Concept-scoped cross-index queries.

    Where `context` answers the spatial question (what defines / uses a
    concept), this group answers temporal ones by JOINING the context graph
    (concept -> its files) with the session index (files/commits -> when they
    were worked on) and git (authoritative code-introduction commit)."""


# Structural linkages whose neighbors carry the concept's file footprint.
_TIMELINE_LINKAGES = [
    "defines", "implements", "calls", "called_by", "imports", "mentions",
]


def _concept_files(s, cids, *, hops, cap=200):
    """Resolve concept ids -> {abspath: relpath} for the code/doc files in the
    concept's structural footprint, expanding `hops` concept-hops out. Also
    returns the set of concept names visited (for the header)."""
    from refmatrix.context import _concept_rows
    # Only walk linkages that actually exist — top_weighted/load_bitmap raise
    # on an unregistered linkage type (a fresh store has only what's linked).
    existing = {lk["name"] for lk in s.list_linkages()}
    linkages = [ln for ln in _TIMELINE_LINKAGES if ln in existing]
    files: dict[str, str] = {}
    seen: set[int] = set(cids)
    names: dict[int, str] = {}
    for cid in cids:
        ent = s.get_entity_by_id(cid)
        if ent is not None:
            names[cid] = ent.name
    frontier = list(cids)
    depth = 0
    while frontier and depth <= hops and len(files) < cap:
        nxt: list[int] = []
        for cid in frontier:
            for _ln, eid, _w in _concept_rows(s, cid, linkages, cap):
                e = s.get_entity_by_id(eid)
                if e is None:
                    continue
                if e.kind in ("code", "doc") and e.path:
                    files.setdefault(e.path, e.name or e.path)
                elif e.kind == "concept" and depth < hops and e.id not in seen:
                    seen.add(e.id)
                    names[e.id] = e.name
                    nxt.append(e.id)
        frontier = nxt
        depth += 1
    return files, names


@concept_grp.command("timeline")
@click.argument("concept")
@click.option("--hops", default=0, type=int, show_default=True,
              help="Concept-hops out when collecting files. 0 = files that "
                   "directly define/use/mention the concept; higher pulls in "
                   "neighbor concepts' files (wider indirect footprint).")
@click.option("--since", default=None,
              help="Only events on/after this point (7d, 1h, ISO date).")
@click.option("--until", default=None, help="Only events on/before this point.")
@click.option("--k", default=40, type=int, show_default=True,
              help="Max session rows to render.")
@click.option("--no-git", is_flag=True,
              help="Skip the git pickaxe for the code-introduction commit.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def concept_timeline_cmd(concept, hops, since, until, k, no_git, as_json):
    """When was CONCEPT introduced / worked on, directly or indirectly.

    Joins the context graph (concept -> its files) with the session index
    (files/commits -> when touched) plus a git pickaxe for the authoritative
    code-introduction commit. Direct = a session names the concept; indirect =
    a session edited one of its files without naming it."""
    import shutil
    import subprocess
    from refmatrix import daemon as daemon_mod

    since_iso = _since_to_iso(since)
    until_iso = _since_to_iso(until)

    # 1. Graph: resolve concept -> its files.
    s = _read_store()
    cids = s.resolve_concept_ids(concept, strict=False)
    if not cids:
        e = s.resolve_entity(concept)
        if e is not None and e.kind == "concept":
            cids = [e.id]
    if not cids:
        raise click.ClickException(f"unknown concept: {concept!r}")
    files, cnames = _concept_files(s, cids, hops=hops)
    rel_keys = list(files.values())
    proj = s.root.parent

    events: list[dict] = []  # {date, type, ref, detail}

    # 2. Git: first commit that introduced the concept string (pickaxe),
    #    scoped to the resolved files when we have them.
    if not no_git and shutil.which("git"):
        pathspec = rel_keys or ["."]
        try:
            out = subprocess.run(
                ["git", "-C", str(proj), "log", "--reverse", "-i",
                 "-S", concept, "--pretty=%h%x09%aI%x09%s", "--", *pathspec],
                capture_output=True, text=True, timeout=30,
            )
            first = next((ln for ln in out.stdout.splitlines() if ln.strip()),
                         None)
            if first:
                parts = (first.split("\t") + ["", "", ""])[:3]
                h, aiso, subj = parts
                events.append({"date": aiso, "type": "git", "ref": h,
                               "detail": f"introduced `{concept}` — {subj[:60]}"})
        except Exception:
            pass

    # 3. Sessions: direct (names the concept) + indirect (touched a file).
    sessions: dict[str, dict] = {}

    def _record(m, how, via=None):
        sid = _session_meta_get(m, "session_id") or m.get("name", "")
        ended = _session_meta_get(m, "ended") or ""
        if since_iso and ended and ended < since_iso:
            return
        if until_iso and ended and ended > until_iso:
            return
        title = (m.get("content") or "").split("\n", 2)[0].lstrip("# ").strip()
        title = title.split(" {#")[0]
        cur = sessions.get(sid)
        if cur is None:
            sessions[sid] = {"date": ended, "title": title[:56],
                             "how": how, "via": via}
        elif how == "direct" and cur["how"] != "direct":
            cur["how"] = "direct"  # naming the concept outranks a file touch
            cur["via"] = None

    # Session collection is best-effort — a project with no session index
    # still gets a useful git-only timeline.
    try:
        direct_rows: list[dict] = []
        if daemon_mod.ping(_root()):
            resp = _session_call("memory_search",
                                 {"query": concept, "limit": max(k * 4, 100)})
            if resp.get("ok"):
                direct_rows = [r for r in resp["result"]["rows"]
                               if r.get("mtype") == "session"]
        else:
            direct_rows = [m for m in _iter_session_memories()
                           if concept.lower() in (m.get("content") or "").lower()]
        for m in direct_rows:
            _record(m, "direct")

        if rel_keys:
            for m in _iter_session_memories():
                touched = _session_meta_list(m, "files_touched")
                hit = next((rel for rel in rel_keys
                            if any(rel in f for f in touched)), None)
                if hit:
                    _record(m, "indirect", via=hit)
    except Exception:
        pass

    for sid, d in sessions.items():
        via = f" via {d['via']}" if d.get("via") else ""
        events.append({"date": d["date"], "type": "session", "ref": sid[:8],
                       "detail": f"[{d['how']}{via}] {d['title']}"})

    events = [e for e in events if e["date"]]
    events.sort(key=lambda e: e["date"])
    session_events = [e for e in events if e["type"] == "session"]
    truncated = len(session_events) > k
    if truncated:
        # Keep the earliest k session rows; introduction is the point.
        keep = set(id(e) for e in session_events[:k])
        events = [e for e in events
                  if e["type"] != "session" or id(e) in keep]

    if as_json:
        click.echo(json.dumps({
            "concept": concept,
            "resolved_files": len(files),
            "resolved_concepts": len(cnames),
            "hops": hops,
            "events": events,
            "session_count": len(session_events),
            "truncated": truncated,
        }, indent=2, default=str))
        return

    click.echo(f"=== timeline for `{concept}` ===")
    click.echo(f"graph: {len(files)} files, {len(cnames)} concepts (hops={hops})")
    if not events:
        click.echo("(no events — concept resolved but no git/session hits)")
        return
    from rich.table import Table
    from rich.text import Text
    t = Table(show_lines=False)
    t.add_column("date", style="dim")
    t.add_column("type", style="cyan")
    t.add_column("ref")
    t.add_column("detail")
    for e in events:
        t.add_row((e["date"] or "")[:10], e["type"], e["ref"],
                  Text(e["detail"]))
    console.print(t)
    if truncated:
        console.print(f"[dim](+{len(session_events) - k} more sessions; "
                      f"raise --k)[/]")
    first = events[0]
    click.echo(f"\nfirst seen: {(first['date'] or '')[:10]}  "
               f"({first['type']} {first['ref']})")
    if session_events:
        lo = session_events[0]["date"][:10]
        hi = session_events[-1]["date"][:10]
        click.echo(f"worked on: {len(session_events)} sessions, {lo} → {hi}")


def _reexec_for_fork_safety() -> None:
    """macOS only: re-exec once so a fresh libobjc loads with the
    initialize-after-fork check DISABLED.

    `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` is read by libobjc ONCE at image
    load (`environ_init`) and cached — setting it from Python afterwards is
    too late for the daemon's plain `os.fork()` (double-fork, no exec): the
    cached "safety ON" state is copied into the forked daemon child, which
    then SIGABRTs the moment it touches objc:

        objc[...]: +[NSMutableString initialize] may have been in progress
        in another thread when fork() was called. ... Crashing instead.

    Re-execing a fresh interpreter with the var already present means its
    libobjc loads with the check off; the daemon we later fork inherits that
    cleared state, and loky's fork+exec workers inherit the env directly.
    `_harden_fork_safety()` (env-only, in spawn_daemon) remains a fallback
    that covers the fork+exec paths but cannot fix the no-exec daemon fork —
    this does.

    Idempotent: once the var is set we return without re-execing, so there
    is no exec loop. A launchd plist that already provides the var (see
    `launchctl.render_plist`) short-circuits here too, paying no exec cost.
    """
    if sys.platform != "darwin":
        return
    if os.environ.get("OBJC_DISABLE_INITIALIZE_FORK_SAFETY") == "YES":
        return
    os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    try:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except OSError:
        # exec failed (e.g. ENOMEM) — proceed in-process; the env var still
        # helps fork+exec children even if the no-exec daemon fork can't be
        # rescued. Never block startup on this.
        pass


def cli_entry() -> None:
    """Console-script entrypoint. Wraps `main()` with invocation logging.

    Captures argv, cwd, exit code, latency, and any exception, then appends
    one JSONL record to .refmatrix/cli.log via telemetry. Preserves Click's
    exit semantics by re-raising SystemExit.
    """
    _reexec_for_fork_safety()
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
