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
from refmatrix.store import Store
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
    """Resolution order:
       1. --partition / -p flag on the rmx group
       2. RMX_PARTITION env var
       3. .refmatrix/partition file walked up from cwd (one-line partition
          name — drop one inside a project's existing .refmatrix/ to bind
          that tree to a named partition in a shared store)
       4. 'local' (matches the default partition created at init)

    Note: the .refmatrix/ that holds the `partition` file does NOT have to
    be the active store root — REFMATRIX_ROOT can still point at a central
    shared store while a per-project .refmatrix/partition file selects which
    partition this project's CLI invocations write into.
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
    return "local"


def _store() -> Store:
    s = Store(_root(), partition=_resolve_partition())
    if not s.db_path.exists():
        raise click.ClickException(
            f"no refmatrix at {s.root}. Run `rmx init` first or set REFMATRIX_ROOT."
        )
    # Register a flush-and-close on normal interpreter exit. CLI commands
    # mutate the in-memory fragment cache and rely on close() to persist;
    # without this, every command would lose its writes.
    atexit.register(s.close)
    return s


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
def init(path: Path | None):
    """Initialize a refmatrix in the given directory (default: cwd)."""
    target = (path or Path.cwd()) / ".refmatrix"
    s = Store(target, partition=_resolve_partition())
    s.init()
    atexit.register(s.close)
    console.print(f"[green]initialized[/] {s.root} (partition={s.partition_name})")


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
def daemon_start():
    """Start the rmx daemon for the active store. Idempotent: re-running
    while a daemon is already up is a fast no-op (returns its pid)."""
    from refmatrix import daemon as daemon_mod
    root = _root()
    if not root.is_dir():
        raise click.ClickException(
            f"no refmatrix at {root}. Run `rmx init` first."
        )
    pid = daemon_mod.spawn_daemon(root, partition=_resolve_partition())
    console.print(f"[green]daemon running[/] pid={pid} root={root}")


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


@main.command("add-entity")
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
    s = _store()
    meta_d = json.loads(meta) if meta else None
    eid = s.upsert_entity(kind=kind, name=name, path=path, tldr=tldr,
                          meta=meta_d, protected=not no_protect)
    pinned = "" if no_protect else " (pinned)"
    console.print(f"[green]upserted[/] {kind}:{name} (id={eid}){pinned}")


@main.command("add-concept")
@click.argument("name")
@click.option("--description", "-d", default=None)
@click.option("--no-protect", is_flag=True,
              help="Don't pin this concept. By default manual adds are protected.")
def add_concept(name, description, no_protect):
    """Add a concept (= entity of kind 'concept'). Pinned by default."""
    s = _store()
    cid = s.add_concept(name, description=description, protected=not no_protect)
    pinned = "" if no_protect else " (pinned)"
    console.print(f"[green]added concept[/] {name} (id={cid}){pinned}")


@main.command("list-entities")
@click.option("--kind", type=click.Choice(["doc", "code", "concept"]), default=None)
def list_entities(kind):
    """List entities."""
    s = _store()
    t = Table("id", "kind", "name", "path", "tldr")
    for e in s.iter_entities(kind):
        t.add_row(str(e.id), e.kind, e.name, e.path or "", (e.tldr or "")[:80])
    console.print(t)


# ---- linkage types --------------------------------------------------------


@main.command("add-linkage-type")
@click.argument("name")
@click.option("--directed/--undirected", default=True)
@click.option("--description", "-d", default=None)
def add_linkage_type(name, directed, description):
    """Define a custom linkage type."""
    s = _store()
    lid = s.add_linkage_type(name=name, directed=directed, description=description)
    console.print(f"[green]linkage type[/] {name} (id={lid})")


@main.command("list-linkages")
def list_linkages():
    """List linkage types."""
    s = _store()
    t = Table("id", "name", "directed", "description")
    for lk in s.list_linkages():
        t.add_row(str(lk["id"]), lk["name"], "yes" if lk["directed"] else "no", lk["description"] or "")
    console.print(t)


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
def query(expr, is_pql, ids_only, limit, explain, include_noise, name_filter):
    """Run a query. DSL: `mentions:parser AND defines:parser`. PQL: `Row(calls,foo)`."""
    s = _store()
    qe = QueryEngine(s, include_noise=include_noise)
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
def neighbors(concept, depth, linkage, limit, include_noise):
    """Walk linkages from a concept (depth-N closure)."""
    s = _store()
    qe = QueryEngine(s, include_noise=include_noise)
    with log_query(s, kind="neighbors", body=concept, source="neighbors") as t:
        bm = qe.neighbors(concept, depth=depth, linkages=list(linkage) or None)
        t.cardinality = len(bm)
    _print_bitmap(s, bm, limit=limit)


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
def context(symbol, linkage, max_entities, max_tokens, fmt, since, fuse):
    """Token-budgeted context bundle: anchor + neighbors + their tldr blobs."""
    from refmatrix.context import build_context, render_json, render_text

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
                              linkages=list(linkage) or None, fuse=fuse)
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


@main.command("list-queries")
def list_queries():
    """List saved queries."""
    s = _store()
    t = Table("name", "body")
    for n, b in s.list_saved_queries():
        t.add_row(n, b)
    console.print(t)


# ---- stats / export -------------------------------------------------------


@main.command()
@click.option("--stale", is_flag=True,
              help="Also list tracked files where on-disk mtime > last_synced.")
def stats(stale):
    """Print catalog and bitmap stats."""
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
    if stale:
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
def vacuum():
    """Drop empty concepts and tracked files that no longer exist."""
    s = _store()
    out = s.vacuum()
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
              type=click.Choice(["auto", "metadata", "tldr", "tree"]),
              default="auto",
              help="auto picks metadata > tldr > tree. metadata reads "
                   "llm-tldr's per-unit semantic dump for the richest graph; "
                   "tldr falls back to call_graph.json.")
@click.option("--semantic", is_flag=True,
              help="Also extract Python imports + docstring keywords (slow on big trees).")
def ingest(path, source, semantic):
    """Ingest a directory. Prefers .tldr/cache/semantic/metadata.json when present."""
    from refmatrix.ingest import ingest_path

    s = _store()
    n = ingest_path(s, Path(path), source=source, semantic=semantic)
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
def sync(files, since, flush_queue, invalidate, project_root, semantic,
         enqueue_only):
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

    # Try the daemon for flush-queue / sync_files paths first — it holds
    # the Store open across many calls so we skip DuckDB lock acquisition.
    # Falls back to in-process when no daemon is running.
    if flush_queue or (files and not since and not invalidate):
        from refmatrix import daemon as daemon_mod
        root = _root()
        if daemon_mod.ping(root):
            proot = (project_root or Path.cwd()).resolve()
            op = "flush_queue" if flush_queue else "sync_files"
            args: dict = {"project_root": str(proot), "semantic": semantic}
            if not flush_queue:
                args["files"] = [str(p) for p in files]
            resp = daemon_mod.call(root, op, args)
            if not resp.get("ok"):
                raise click.ClickException(
                    f"daemon {op} failed: {resp.get('error')}"
                )
            r = resp["result"]
            console.print(
                f"[green]synced[/] +{r['added']} ~{r['updated']} "
                f"-{r['purged']} (touched={r['touched']}) [daemon]"
            )
            return

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
def ingest_gmd(targets: tuple[Path, ...], verbose: bool):
    """Ingest Graph Markdown (GMD) docs. Walks dirs for *.gmd/*.md files
    that carry `gmd:` frontmatter; non-GMD files are skipped."""
    from refmatrix.ingest_gmd import collect_gmd_files, ingest_gmd_paths
    s = _store()
    files = collect_gmd_files(list(targets))
    if not files:
        console.print("[yellow]no candidate files found[/]")
        return
    if verbose:
        for f in files:
            console.print(f"  scan {f}")
    stats = ingest_gmd_paths(s, files, verbose=verbose)
    console.print(stats.report())


if __name__ == "__main__":
    main()
