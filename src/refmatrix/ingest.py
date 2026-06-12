"""
Ingestion: turn a project directory into entities + linkages.

Sources, in order of preference:

1. **metadata** — `.tldr/cache/semantic/metadata.json` (llm-tldr's per-unit
   semantic dump). Strictly richer than call_graph.json: signature, unit_type
   (function/class/method/...), per-unit calls/called_by, dependencies, CFG
   and DFG summaries. Preferred when present.
2. **tldr** — `.tldr/cache/call_graph.json`. Just (from_file, from_func) ->
   (to_file, to_func) edges. Used when metadata.json isn't there.
3. **tree** — walk the directory, register every text file as a `doc` or
   `code`. No call graph; you still get a per-file entity to `link` against.
4. **semantic** (Python only, opt-in via --semantic) — stdlib ast pass that
   adds `imports` and docstring-keyword `mentions` linkages. Redundant when
   metadata.json is available, but harmless and cross-source-additive.
"""
from __future__ import annotations

import ast
import json
import os
import re
from collections import Counter
from pathlib import Path

from refmatrix.store import Store

CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".rb", ".php",
    ".cs", ".scala", ".sh", ".bash", ".zsh", ".sql", ".lua", ".pseudo",
}
DOC_EXTS = {".md", ".markdown", ".rst", ".txt", ".adoc"}

# Non-dot directory segments excluded from rglob walks. Dotfile dirs
# (anything starting with `.`) are excluded via _is_ignored() below —
# enumerating them was unsustainable and missed tooling dirs like
# .wolf / .claude / .cursor / .idea that get appended to repos all the
# time. Kept separate from watch.IGNORE_DIRS (broader, includes caches)
# to avoid a circular import: watch.py imports from this module.
#
# Per-repo extras live in `<project>/.refmatrix/.refmatrix_ignore`
# (gitignore-ish, loaded by load_ignore_spec) — e.g. a `workflow/` dir of
# Claude operational content that should stay out of the concept graph but
# remain reachable via `rmx session`/`rmx memory` recall.
INGEST_IGNORE_DIRS = ("node_modules", "venv")

# Name of the per-repo ignore file, read from the project-local .refmatrix dir.
IGNORE_FILE = ".refmatrix_ignore"
_IGNORE_CACHE: dict[str, tuple[float, "IgnoreSpec | None"]] = {}


class IgnoreSpec:
    """A tiny gitignore-ish matcher for `.refmatrix_ignore`. Supports three
    pattern shapes, one per line (blank lines and `#` comments skipped):

    - bare name  (`workflow`, `node_modules`) -> matches that path SEGMENT
      anywhere in the tree (a trailing `/` is allowed and stripped).
    - basename glob  (`*.md`, `*.log`)        -> fnmatch against the filename.
    - path with `/`  (`docs/bullshit`, `a/b`) -> anchored to the repo root:
      matches that relative path or anything beneath it (and fnmatch).

    Not full gitignore (no negation / `**`), but covers the dir- and
    glob-exclusion cases refmatrix needs."""

    def __init__(self, lines: list[str]):
        self.names: list[str] = []
        self.globs: list[str] = []
        self.anchored: list[str] = []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            line = line.rstrip("/")
            if not line:
                continue
            if "/" in line:
                self.anchored.append(line)
            elif any(ch in line for ch in "*?["):
                self.globs.append(line)
            else:
                self.names.append(line)

    def __bool__(self) -> bool:
        return bool(self.names or self.globs or self.anchored)

    def match(self, rel: Path) -> bool:
        from fnmatch import fnmatch
        segs = rel.parts
        if any(n in segs for n in self.names):
            return True
        name = rel.name
        if any(fnmatch(name, g) for g in self.globs):
            return True
        posix = rel.as_posix()
        for pat in self.anchored:
            if posix == pat or posix.startswith(pat + "/") or fnmatch(posix, pat):
                return True
        return False


def load_ignore_spec(project_root: Path) -> "IgnoreSpec | None":
    """Load `<project_root>/.refmatrix/.refmatrix_ignore` if present, cached by
    (path, mtime) so a walk reads it once. Returns None when absent/empty."""
    f = project_root / ".refmatrix" / IGNORE_FILE
    try:
        mtime = f.stat().st_mtime
    except OSError:
        _IGNORE_CACHE.pop(str(f), None)
        return None
    cached = _IGNORE_CACHE.get(str(f))
    if cached is not None and cached[0] == mtime:
        return cached[1]
    spec = IgnoreSpec(f.read_text().splitlines())
    spec = spec if spec else None
    _IGNORE_CACHE[str(f)] = (mtime, spec)
    return spec


def _is_ignored(parts: set[str]) -> bool:
    """True if any path segment is a non-dot ignore-listed dir
    (node_modules, venv) or a hidden directory (starts with `.`).
    The `seg != "."` guard keeps a leading `.` in relative paths
    (Path(".").parts == ('.',)) from excluding the cwd itself."""
    if any(seg in parts for seg in INGEST_IGNORE_DIRS):
        return True
    return any(seg.startswith(".") and seg != "." for seg in parts)


def should_ignore(p: Path, root: Path | None = None) -> bool:
    """Walk-filter predicate: the built-in `_is_ignored` segment rules PLUS the
    per-repo `.refmatrix_ignore` spec (matched against the path relative to
    `root`). `root` None falls back to the built-in rules only."""
    if _is_ignored(set(p.parts)):
        return True
    if root is not None:
        spec = load_ignore_spec(root)
        if spec is not None:
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = Path(p.name)
            if spec.match(rel):
                return True
    return False


def ingest_path(
    s: Store, path: Path, source: str = "auto", semantic: bool = False,
    *, yield_lock=None, yield_every: int = 200, progress_cb=None,
) -> int:
    """Run a full ingest.

    `progress_cb(phase: str, done: int, total: int)` is called at each pass
    boundary (and within the dominant per-file loops) so a caller — the daemon,
    which logs `ingest-progress` for the CLI to tail — has visibility into an
    otherwise-opaque blocking ingest. Optional; default no-op.

    Two modes:

    * Direct (``yield_lock is None``): wrap the entire body in one
      ``s.transaction()`` so every inner mutation's commit collapses into a
      single final commit — historically the single dominant cost
      (per-INSERT WAL fsync). This is the daemon-down / in-process fast path.

    * Cooperative (``yield_lock`` provided): used when the daemon runs the
      ingest, so a big warm doesn't hold the writer lock for minutes and
      stall latency-sensitive writes (memory hooks). No single mega-
      transaction; the dominant inner loops flush bitmap fragments and call
      ``yield_lock`` every ``yield_every`` units, releasing ``_store_lock``
      so queued writes interleave. Each yield lands on a consistent on-disk
      state (relational autocommitted + fragments flushed). Trades the
      single-commit batching for bounded lock-hold.
    """
    if yield_lock is None:
        with s.transaction():
            return _ingest_path_inner(s, path, source=source, semantic=semantic,
                                      progress_cb=progress_cb)
    # Cooperative path: drive windowed transactions so per-row WAL fsync
    # collapses to one fsync per yield window. The inner loops call their
    # yield hook (`_yield_flush`) every `yield_every` units; routing that hook
    # through `_CommitWindow.boundary` makes each boundary a COMMIT + lock
    # hand-off + fresh window. Without this the daemon ingest autocommits
    # every row (~28k fsyncs / ~20 min on a viascope warm) — the elevated-RSS
    # window that lets jetsam kill the daemon mid-warm.
    win = _CommitWindow(s, yield_lock)
    win.open()
    try:
        return _ingest_path_inner(
            s, path, source=source, semantic=semantic,
            yield_lock=win.boundary, yield_every=yield_every,
            progress_cb=progress_cb,
        )
    finally:
        win.close()


def _md_file_changed(pre_tracked: "dict[str, float]", p: Path) -> bool:
    """True if `p` should be (re)ingested by the markdown passes: not in the
    pre-ingest tracked snapshot, or its on-disk mtime differs. Gating against a
    snapshot captured BEFORE any pass writes is essential -- otherwise
    `_ingest_tree` (which tracks files earlier in the SAME ingest) would make
    every .md look 'already ingested' and the markdown passes would no-op."""
    try:
        cur = p.stat().st_mtime
    except OSError:
        return True
    prev = pre_tracked.get(str(p))
    return prev is None or abs(prev - cur) > 1e-6


def _ingest_path_inner(
    s: Store, path: Path, source: str = "auto", semantic: bool = False,
    *, yield_lock=None, yield_every: int = 200, progress_cb=None,
) -> int:
    path = path.resolve()

    def _phase(name: str, done: int = 0, total: int = 0) -> None:
        if progress_cb is not None:
            try:
                progress_cb(name, done, total)
            except Exception:
                pass  # progress is best-effort; never fail an ingest on it
    # Snapshot tracked mtimes up front: the markdown passes gate against PRIOR
    # ingests only, not files an earlier pass (e.g. _ingest_tree) tracks during
    # this same call.
    try:
        _pre_tracked = dict(s.list_tracked())
    except Exception:
        _pre_tracked = {}
    metadata_path = path / ".tldr" / "cache" / "semantic" / "metadata.json"
    call_graph_path = path / ".tldr" / "cache" / "call_graph.json"
    graphify_path = path / "graphify-out" / "graph.json"
    n = 0
    _phase("code+docs: tldr/tree")
    if source in ("auto", "metadata") and metadata_path.exists():
        n = _ingest_tldr_metadata(s, path, pre_tracked=_pre_tracked,
                                  yield_lock=yield_lock,
                                  yield_every=yield_every)
    if n == 0 and source in ("auto", "tldr") and call_graph_path.exists():
        n = _ingest_tldr(s, path, yield_lock=yield_lock, yield_every=yield_every)
    if source in ("auto", "tree") and n == 0:
        n = _ingest_tree(s, path)
    # Graphify is additive — when source=auto and the cache is present, layer
    # its cross-modal edges (rationale_for, semantically_similar_to, etc.) on
    # top of whatever the primary source produced. source=graphify forces it
    # to be the only ingest.
    if source == "graphify":
        _phase("code+docs: graphify")
        n = _ingest_graphify(s, path, pre_tracked=_pre_tracked)
    elif source == "auto" and graphify_path.exists():
        _phase("code+docs: graphify")
        _ingest_graphify(s, path, pre_tracked=_pre_tracked)
    if semantic:
        _phase("code+docs: python-semantic (scanning)")
        from concurrent.futures import ThreadPoolExecutor
        from refmatrix.ingest_records import bulk_apply_records
        # Gate on a DEDICATED `pysem:<abs>` marker key. .py files are ALSO
        # tracked by the tldr pass under their real path, so the shared
        # tracking key can't tell whether the *semantic* pass has seen a
        # file -- gating on it would skip files tldr tracked but --semantic
        # never processed (wrong on the FIRST --semantic run). Only this
        # pass writes pysem: markers, so a mismatch means "changed since the
        # last --semantic run, or never run". Snapshot is _pre_tracked,
        # captured before any pass writes (same rationale as the md gate).
        changed_py: list[tuple[Path, float]] = []
        for p in path.rglob("*.py"):
            if should_ignore(p, path):
                continue
            try:
                cur = p.stat().st_mtime
            except OSError:
                continue
            prev = _pre_tracked.get(f"pysem:{str(p)}")
            if prev is None or abs(prev - cur) > 1e-6:
                changed_py.append((p, cur))
        if changed_py:
            n_py = len(changed_py)
            _phase("code+docs: python-semantic", 0, n_py)
            sworkers = int(os.environ.get("RMX_INGEST_WORKERS", "8") or "8")
            sem_records = []
            with ThreadPoolExecutor(max_workers=sworkers,
                                    thread_name_prefix="rmx-pysem-parse") as ex:
                # ex.map yields in input order; count completions for per-file
                # progress (throttled) so a big --semantic tree shows movement.
                for _i, _rec in enumerate(ex.map(
                    lambda fp: _build_python_semantic_record(fp, path),
                    [p for p, _ in changed_py],
                ), 1):
                    sem_records.append(_rec)
                    if _i == n_py or _i % 25 == 0:
                        _phase("code+docs: python-semantic", _i, n_py)
            # One bulk apply across all changed .py files instead of ~1 upsert
            # per concept per file (the per-row cost that dominated
            # `rmx ingest . --semantic` on a large tree).
            bulk_apply_records(s, sem_records)
            # Write the gate markers in one batched statement. bulk_apply
            # already marked the real .py paths tracked (harmless, same value
            # tldr writes); the pysem: key is what this pass gates on.
            s.bulk_mark_tracked([
                (f"pysem:{str(p)}", mtime) for p, mtime in changed_py
            ])
            if yield_lock is not None:
                _yield_flush(s, yield_lock)
    # .pseudo pseudocode semantic enrichment. Gate on a DEDICATED
    # `pssem:<abs>` marker: .pseudo is in CODE_EXTS, so the tree pass ALSO
    # tracks these files under their real path -- gating on the shared key
    # would skip files tree tracked but the .pseudo pass never applied (wrong
    # on the FIRST run). Same rationale as the pysem: gate above. Snapshot is
    # _pre_tracked, captured before any pass writes.
    changed_pseudo: list[tuple[Path, float]] = []
    for p in path.rglob("*.pseudo"):
        if should_ignore(p, path):
            continue
        try:
            cur = p.stat().st_mtime
        except OSError:
            continue
        prev = _pre_tracked.get(f"pssem:{str(p)}")
        if prev is None or abs(prev - cur) > 1e-6:
            changed_pseudo.append((p, cur))
    if changed_pseudo:
        n_ps = len(changed_pseudo)
        _phase("code+docs: pseudo", 0, n_ps)
        from concurrent.futures import ThreadPoolExecutor
        from refmatrix.ingest_records import bulk_apply_records
        pworkers = int(os.environ.get("RMX_INGEST_WORKERS", "8") or "8")
        ps_records = []
        with ThreadPoolExecutor(max_workers=pworkers,
                                thread_name_prefix="rmx-ps-parse") as ex:
            for _i, _rec in enumerate(ex.map(
                lambda fp: _build_pseudo_record(fp, path),
                [p for p, _ in changed_pseudo],
            ), 1):
                ps_records.append(_rec)
                if _i == n_ps or _i % 25 == 0:
                    _phase("code+docs: pseudo", _i, n_ps)
        # One bulk apply across all changed .pseudo files instead of one
        # apply_record per file (the per-row cost the other passes already
        # shed). bulk_apply_records filters None records and marks the real
        # .pseudo paths tracked; the pssem: key is what this pass gates on.
        bulk_apply_records(s, ps_records)
        s.bulk_mark_tracked([
            (f"pssem:{str(p)}", mtime) for p, mtime in changed_pseudo
        ])
        if yield_lock is not None:
            _yield_flush(s, yield_lock)

    # ADR semantic extraction — two-pass so cross-references resolve.
    # Build adr_num_to_eid for EVERY ADR (so changed docs' @adr refs resolve),
    # but only parse + apply the ones whose mtime changed. bulk_apply marks the
    # changed ones tracked; unchanged ones stay tracked from the prior ingest.
    _phase("code+docs: markdown/adr")
    adr_files: list[tuple[Path, str]] = []
    adr_num_to_eid: dict[str, int] = {}
    for p in path.rglob("*.md"):
        if should_ignore(p, path):
            continue
        adr_num = _is_adr_file(p)
        if adr_num is None:
            continue
        rel = (
            p.relative_to(path).as_posix() if p.is_relative_to(path) else str(p)
        )
        changed = _md_file_changed(_pre_tracked, p)
        eid = s.upsert_entity(
            kind="doc", name=rel, path=str(p),
            meta={"adr_number": adr_num},
        )
        adr_num_to_eid[adr_num] = eid
        if changed:
            adr_files.append((p, adr_num))
    if adr_files:
        n_adr = len(adr_files)
        _phase("code+docs: adr", 0, n_adr)
        from concurrent.futures import ThreadPoolExecutor
        from refmatrix.ingest_records import bulk_apply_records
        adr_workers = int(os.environ.get("RMX_INGEST_WORKERS", "8") or "8")
        adr_records = []
        with ThreadPoolExecutor(max_workers=adr_workers,
                                thread_name_prefix="rmx-adr-parse") as ex:
            for _i, _rec in enumerate(ex.map(
                lambda fp: _build_adr_record(fp, path, adr_num_to_eid),
                [p for p, _ in adr_files],
            ), 1):
                adr_records.append(_rec)
                if _i == n_adr or _i % 25 == 0:
                    _phase("code+docs: adr", _i, n_adr)
        bulk_apply_records(s, adr_records, adr_num_to_eid=adr_num_to_eid)

    # General markdown semantic extraction (non-ADR). Runs after ADR pass so
    # ADR-NNNN cross-references from generic docs can resolve via
    # adr_num_to_eid. Parsed in parallel via ThreadPoolExecutor so the
    # regex+walk work no longer pins one CPU core; applied sequentially
    # against the daemon-owned Store under the active transaction.
    md_files: list[Path] = []
    for p in path.rglob("*.md"):
        if should_ignore(p, path):
            continue
        if _is_adr_file(p) is not None:
            continue
        # Skip files already ingested at their current mtime: a re-ingest over
        # an unchanged tree then does no markdown work. Their entities + links
        # persist from the prior ingest and cross-doc refs still resolve.
        if not _md_file_changed(_pre_tracked, p):
            continue
        md_files.append(p)
    if md_files:
        n_md = len(md_files)
        _phase("code+docs: markdown", 0, n_md)
        from concurrent.futures import ThreadPoolExecutor
        from refmatrix.ingest_records import bulk_apply_records
        workers = int(os.environ.get("RMX_INGEST_WORKERS", "8") or "8")
        records = []
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="rmx-md-parse") as ex:
            for _i, _rec in enumerate(ex.map(
                lambda fp: _build_markdown_record(fp, path, adr_num_to_eid),
                md_files,
            ), 1):
                records.append(_rec)
                if _i == n_md or _i % 25 == 0:
                    _phase("code+docs: markdown", _i, n_md)
        # One bulk apply across all changed docs instead of ~1 upsert per
        # concept per file (the per-row cost that dominated ingest on a large
        # tree). See ingest_records.bulk_apply_records.
        bulk_apply_records(s, records, adr_num_to_eid=adr_num_to_eid)
    # Inverse-linkage derivation: materialize `called_by` from `calls` once
    # every pass has written its call edges. Source-agnostic (operates on the
    # final entity_links) so it covers metadata / call-graph / graphify /
    # python-semantic at once; idempotent, and a no-op when there are no calls.
    _phase("code+docs: derive called_by")
    s.derive_called_by()
    return n


# --- tldr metadata.json (richest source) ------------------------------------


# Fields kept on each unit's `meta` blob. Anything bulky (code_preview, full
# docstring) is stored when present; querying paths can ignore it.
_UNIT_META_FIELDS = (
    "language", "unit_type", "name", "line",
    "cfg_summary", "dfg_summary", "docstring", "code_preview", "signature",
)

# What counts as a "trivial" callee. These would explode `calls`-bitmap
# cardinality without adding signal — every test has __init__, every async
# class has __aexit__, etc. Keep them out of the concept layer entirely.
_CALLEE_BLOCKLIST = frozenset({
    "__init__", "__new__", "__call__", "__enter__", "__exit__",
    "__aenter__", "__aexit__", "__repr__", "__str__", "__hash__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
})


def _yield_flush(s: Store, yield_lock) -> None:
    """Cooperative yield point. `yield_lock` here is `_CommitWindow.boundary`
    (the only cooperative caller, wired up in `ingest_path`): it COMMITs the
    current window — atomically flushing dirty bitmap fragments alongside the
    relational rows — then releases the writer lock briefly so queued writes
    interleave, then opens the next window.

    Fragments are deliberately NOT flushed here: a mid-window flush would push
    bitmaps to disk ahead of their still-uncommitted relational rows — the
    exact drift `Store.transaction()` guards against. The window COMMIT owns
    the flush instead."""
    yield_lock()


class _CommitWindow:
    """Windowed transactions for the cooperative (daemon) ingest path.

    The daemon can't wrap a whole warm in one transaction: it must yield the
    writer lock periodically so latency-sensitive writes (memory hooks)
    interleave. But autocommitting every mutation means one WAL fsync PER ROW
    — ~28k fsyncs on a viascope warm, which is both ~20 min of wall time and
    ~20 min of elevated daemon RSS, long enough for macOS jetsam to kill the
    daemon mid-warm. This batches commits to one per `yield_every` window:
    open a transaction, accumulate the window's writes, COMMIT (one fsync +
    atomic fragment flush) at the boundary, hand off the lock, reopen the next
    window. Collapses the fsync count by `yield_every`x while preserving the
    bounded lock-hold the cooperative path exists for."""

    def __init__(self, s: Store, real_yield) -> None:
        self.s = s
        self.real_yield = real_yield
        self._cm = None

    def open(self) -> None:
        self._cm = self.s.transaction()
        self._cm.__enter__()

    def boundary(self) -> None:
        # Close the window: COMMIT + atomic fragment flush (one fsync).
        if self._cm is not None:
            self._cm.__exit__(None, None, None)
            self._cm = None
        # Release the writer lock so queued writes interleave, then refresh
        # the read snapshot. (The daemon's `_yield` does
        # release -> sleep -> snapshot -> reacquire.)
        if self.real_yield is not None:
            self.real_yield()
        # Begin the next window under the reacquired lock.
        self.open()

    def close(self) -> None:
        if self._cm is not None:
            self._cm.__exit__(None, None, None)
            self._cm = None


def _ingest_tldr_metadata(s: Store, project: Path, *, pre_tracked=None,
                          yield_lock=None, yield_every: int = 200) -> int:
    """Ingest llm-tldr's per-unit semantic dump. Returns the number of units
    processed (not linkages). See the module docstring for source priority.

    Bulk path: one scan collects unique files / units / concepts (bare,
    `kind/<type>`, `import/<mod>`) and the planned links, then they're created
    in batched statements (`bulk_upsert_entity` + deferred `bulk_link`) instead
    of ~N single-row executes per unit. Same graph as the old per-row code;
    only creation order differs. Mirror of `_ingest_tldr`."""
    cache = project / ".tldr" / "cache" / "semantic" / "metadata.json"
    # Front-door no-op gate. `tldr` regenerates metadata.json only when source
    # actually changes, so an unchanged mtime guarantees this pass would
    # re-derive a byte-identical graph -- yet without a gate it still re-runs
    # every bulk upsert + link flush (thousands of DuckDB executes against the
    # big entity index: ~18s on a re-ingest of an unchanged tree). f3b7c9d
    # killed the *embed* re-stale tax via the updated_at predicate; this kills
    # the *write* tax. Gate on a dedicated `tldrmeta:<cache>` marker (the unit
    # paths are also tracked under their real names by the link flush, so the
    # shared key can't tell whether THIS pass has run). The recorded unit count
    # rides a sibling `tldrmeta_n:` marker so the no-op return keeps the
    # caller's `n == 0` source-chaining and the "ingested N" tally truthful.
    _gate_key = f"tldrmeta:{cache}"
    _count_key = f"tldrmeta_n:{cache}"
    try:
        _cache_mtime = cache.stat().st_mtime
    except OSError:
        _cache_mtime = None
    if pre_tracked is not None and _cache_mtime is not None:
        _prev = pre_tracked.get(_gate_key)
        if _prev is not None and abs(_prev - _cache_mtime) <= 1e-6:
            return int(pre_tracked.get(_count_key, 0))
    payload = json.loads(cache.read_text())
    units = payload.get("units") or []
    # The tldr cache indexes the whole tree; honor `.refmatrix_ignore` here too
    # (the tree-walk + semantic passes already filter, but this cache path
    # bypassed it and re-added ignored units — e.g. a vendored duplicate tree).
    units = [
        u for u in units
        if u.get("file") and not should_ignore(project / u["file"], project)
    ]
    if not units:
        return 0

    # ---- Pass 1: scan units -> unique entities/concepts + planned links ----
    # dicts-as-ordered-sets so bulk ids line up with insertion order.
    file_rels: dict[str, None] = {}
    for u in units:
        rel = u.get("file")
        if rel:
            file_rels.setdefault(rel)

    # unit entity rows keyed by qname (last value wins — every field is
    # non-null so this matches the old per-row COALESCE-on-conflict merge).
    unit_rows: dict[str, tuple[str, str, dict]] = {}
    # concept (name -> description); first description wins per distinct name.
    concept_desc: dict[str, str] = {}
    # planned unit links: (linkage, concept_name, qname).
    unit_links: list[tuple[str, str, str]] = []
    # planned file imports: rel -> set of `import/<mod>` concept names.
    file_imports: dict[str, set[str]] = {}

    def _concept(name: str, desc: str) -> None:
        if name and name not in concept_desc:
            concept_desc[name] = desc

    unit_count = 0
    for u in units:
        qname = u.get("qualified_name")
        rel = u.get("file")
        bare = u.get("name")
        if not qname or not rel or not bare:
            continue

        ap = project / rel
        meta = {k: u[k] for k in _UNIT_META_FIELDS if u.get(k)}
        signature = (u.get("signature")
                     or f"{u.get('unit_type', 'symbol')} {bare} in {rel}")
        unit_rows[qname] = (str(ap), signature, meta)
        unit_count += 1

        _concept(bare, f"symbol '{bare}'")
        unit_links.append(("defines", bare, qname))

        utype = u.get("unit_type")
        if utype:
            kn = f"kind/{utype}"
            _concept(kn, f"unit_type '{utype}'")
            unit_links.append(("is_a", kn, qname))

        for callee in u.get("calls") or ():
            if not callee or callee in _CALLEE_BLOCKLIST:
                continue
            _concept(callee, f"symbol '{callee}'")
            unit_links.append(("calls", callee, qname))

        for caller in u.get("called_by") or ():
            if not caller or caller in _CALLEE_BLOCKLIST:
                continue
            _concept(caller, f"symbol '{caller}'")
            unit_links.append(("called_by", caller, qname))

        # dependencies: comma-separated module list. Aggregate to file-level
        # so a 50-function file with 5 imports doesn't make 250 link rows.
        deps = u.get("dependencies") or ""
        if deps and rel in file_rels:
            bucket = file_imports.setdefault(rel, set())
            for raw in deps.split(","):
                mod = raw.strip().split(".")[0]
                if mod:
                    mn = f"import/{mod}"
                    _concept(mn, f"module '{mod}'")
                    bucket.add(mn)

    # ---- Pass 2: bulk-create files, units, concepts ----
    file_rows = [("code", rel, str(project / rel), None, None)
                 for rel in file_rels]
    file_id_list = _bulk_upsert_chunked(s, file_rows)
    file_ids = dict(zip(file_rels, file_id_list))
    for rel in file_ids:
        ap = project / rel
        try:
            s.mark_tracked(str(ap), ap.stat().st_mtime)
        except OSError:
            pass

    qnames = list(unit_rows)
    unit_entity_rows = [
        ("code", q, unit_rows[q][0], unit_rows[q][1], unit_rows[q][2])
        for q in qnames
    ]
    unit_id_list = _bulk_upsert_chunked(s, unit_entity_rows)
    qname_to_eid = dict(zip(qnames, unit_id_list))

    concept_ids = _bulk_add_concepts(s, concept_desc.items())

    # Hand off the writer lock once entities exist, before the link flush.
    if yield_lock is not None:
        _yield_flush(s, yield_lock)

    # ---- Pass 3: bulk-create links (one deferred Arrow batch) ----
    with s.deferred_links():
        for linkage, cname, qname in unit_links:
            s.link(linkage, concept_ids[cname], qname_to_eid[qname])
        for rel, mods in file_imports.items():
            fid = file_ids[rel]
            for mn in mods:
                s.link("imports", concept_ids[mn], fid)

    # Stamp the no-op gate: next ingest over an unchanged metadata.json mtime
    # short-circuits at the top. Count rides alongside so the skip path can
    # return the right `n` without re-parsing the cache.
    if _cache_mtime is not None:
        s.mark_tracked(_gate_key, _cache_mtime)
        s.mark_tracked(_count_key, float(unit_count))
    return unit_count


# --- tldr -------------------------------------------------------------------


def _bulk_upsert_chunked(s: Store, rows: list) -> list[int]:
    """Thin wrapper over `Store.bulk_upsert_entity`. (It historically chunked
    the id-lookup `IN`-list; bulk_upsert_entity now does a single Arrow-JOIN
    id-lookup that scales to any batch in one table scan, so chunking is no
    longer needed.) Returns ids in input order, [] for empty input."""
    return s.bulk_upsert_entity(rows) if rows else []


def _bulk_add_concepts(s: Store, named_descs) -> dict[str, int]:
    """Bulk equivalent of repeated `Store.add_concept` (and, since
    `add_namespaced_concept` is just `add_concept('ns/name', ...)`, of that
    too): upsert every canonical + variant concept in batched
    `bulk_upsert_entity` calls, wire the `same_as` variant links in one
    deferred-link flush, and return `{input_name: canonical_entity_id}`.

    `named_descs` is an iterable of `(name, description)` — first description
    wins per distinct name. Matches add_concept's per-row semantics exactly:
    the canonical row carries the supplied description; each variant row
    carries `alias of '<canonical>'`. Concept creation was the dominant cost
    in the tldr ingest profile (~56% of wall time via per-name upsert +
    variant expansion) — this collapses it to a handful of statements."""
    from refmatrix.store import _concept_variants
    seen: dict[str, str] = {}  # input name -> description (first wins)
    for nm, desc in named_descs:
        if nm and nm not in seen:
            seen[nm] = desc
    if not seen:
        return {}
    canon_of: dict[str, str] = {}
    variants_of: dict[str, list[str]] = {}
    desc_of: dict[str, str] = {}
    order: list[str] = []

    def _want(entity_name: str, desc: str) -> None:
        # First writer wins the description, mirroring upsert's COALESCE-on-
        # conflict when two source names canonicalize to the same entity.
        if entity_name not in desc_of:
            desc_of[entity_name] = desc
            order.append(entity_name)

    for name, desc in seen.items():
        canonical, variants = _concept_variants(name)
        canon_of[name] = canonical
        variants_of[name] = variants
        _want(canonical, desc)
        for v in variants:
            _want(v, f"alias of '{canonical}'")

    rows = [("concept", nm, None, None, {"description": desc_of[nm]})
            for nm in order]
    ids = _bulk_upsert_chunked(s, rows)
    id_by_name = {nm: i for nm, i in zip(order, ids)}

    with s.deferred_links():
        for name in seen:
            cid = id_by_name[canon_of[name]]
            for v in variants_of[name]:
                vid = id_by_name[v]
                if vid != cid:
                    s.link("same_as", vid, cid)
    return {name: id_by_name[canon_of[name]] for name in seen}


def _ingest_tldr(s: Store, project: Path, *, yield_lock=None,
                 yield_every: int = 200) -> int:
    """Ingest llm-tldr's `call_graph.json` (edge list).

    Bulk path: one scan collects the unique files / functions / concepts and
    the planned links, then they're created in batched statements
    (`bulk_upsert_entity` + deferred `bulk_link`) instead of ~30 single-row
    DuckDB executes per edge. The per-edge path was the dominant ingest cost
    (profile: ~90% in `_duckdb.execute`, ~833k executes on a viascope warm) —
    the slow, RSS-elevated window that made the daemon a jetsam target. The
    produced graph is identical; only creation order differs (link existence
    is order-independent)."""
    cache = project / ".tldr" / "cache" / "call_graph.json"
    data = json.loads(cache.read_text())
    edges = data.get("edges", [])
    if not edges:
        return 0

    # ---- Pass 1: scan edges -> unique entities/concepts + planned links ----
    # dicts-as-ordered-sets so bulk ids line up with insertion order.
    file_rels: dict[str, None] = {}
    func_keys: dict[tuple[str, str], None] = {}
    concept_names: dict[str, None] = {}
    # (linkage, concept_name, (rel, fn)) — ids resolved after bulk create.
    link_plan: list[tuple[str, str, tuple[str, str]]] = []
    n = 0

    for e in edges:
        from_file = e.get("from_file") or ""
        from_func = e.get("from_func") or ""
        to_file = e.get("to_file") or ""
        to_func = e.get("to_func") or ""

        # Honor `.refmatrix_ignore` on the cache path too (see metadata ingest).
        if from_file and should_ignore(project / from_file, project):
            continue
        if to_file and should_ignore(project / to_file, project):
            continue

        if from_file:
            file_rels.setdefault(from_file)
        if to_file:
            file_rels.setdefault(to_file)

        if from_file and from_func:
            func_keys.setdefault((from_file, from_func))
            concept_names.setdefault(from_func)
            link_plan.append(("defines", from_func, (from_file, from_func)))
            n += 1

        if to_file and to_func:
            func_keys.setdefault((to_file, to_func))
            concept_names.setdefault(to_func)
            link_plan.append(("defines", to_func, (to_file, to_func)))
            n += 1

        if from_file and from_func and to_func:
            concept_names.setdefault(to_func)
            # function entity (from_file, from_func) 'calls' the to_func concept
            link_plan.append(("calls", to_func, (from_file, from_func)))
            if to_file and to_func:
                func_keys.setdefault((to_file, to_func))
                concept_names.setdefault(from_func)
                link_plan.append(
                    ("called_by", from_func, (to_file, to_func)))
            n += 1

    # ---- Pass 2: bulk-create file + function entities, then concepts ----
    file_rows = [("code", rel, str(project / rel), None, None)
                 for rel in file_rels]
    file_id_list = _bulk_upsert_chunked(s, file_rows)
    file_ids = dict(zip(file_rels, file_id_list))
    for rel in file_ids:
        ap = project / rel
        try:
            s.mark_tracked(str(ap), ap.stat().st_mtime)
        except OSError:
            pass

    func_rows = [
        ("code", f"{rel}::{fn}", str(project / rel),
         f"function {fn} in {rel}",
         {"file": rel, "func": fn, "kind": "function"})
        for (rel, fn) in func_keys
    ]
    func_id_list = _bulk_upsert_chunked(s, func_rows)
    func_ids = dict(zip(func_keys, func_id_list))

    concept_ids = _bulk_add_concepts(
        s, ((fn, f"function name '{fn}'") for fn in concept_names))

    # Hand off the writer lock once entities exist, before the link flush.
    if yield_lock is not None:
        _yield_flush(s, yield_lock)

    # ---- Pass 3: bulk-create links (one deferred Arrow batch) ----
    with s.deferred_links():
        for linkage, cname, fkey in link_plan:
            s.link(linkage, concept_ids[cname], func_ids[fkey])
    return n


# --- graphify (knowledge-graph JSON) ---------------------------------------


# Graphify edge `relation` → rmx linkage type. Verbs not listed here are
# auto-created via store.add_linkage_type() so custom graphify schemas still
# work — they just won't inherit any predefined inverse or weight semantics.
_GRAPHIFY_VERB_MAP = {
    "calls":                     "calls",
    "called_by":                 "called_by",
    "contains":                  "has-part",
    "inherits":                  "is_a",
    "implements":                "defines",
    "references":                "mentions",
    "uses":                      "depends-on",
    "cites":                     "related_to",
    "method":                    "has-part",
    "rationale_for":             "specifies",
    "conceptually_related_to":   "related_to",
    "semantically_similar_to":   "similar_to",
    "shares_data_with":          "shares_data_with",
}

# Graphify confidence labels → multiplier applied to edge weight. INFERRED
# and AMBIGUOUS edges are still ingested but down-weighted so the bitmap
# scorer can distinguish them from EXTRACTED ground-truth edges.
_GRAPHIFY_CONFIDENCE_W = {
    "EXTRACTED": 1.0,
    "INFERRED":  0.5,
    "AMBIGUOUS": 0.3,
}


def _graphify_kind(file_type: str | None) -> str:
    """Map graphify's file_type → rmx entity kind."""
    if file_type in ("doc", "web", "paper"):
        return "doc"
    return "code"


def _parse_source_line(loc: str | None) -> int | None:
    """Graphify writes line numbers as 'L<n>' or 'L<n>-<m>'. Pull the start."""
    if not loc or not loc.startswith("L"):
        return None
    try:
        return int(loc[1:].split("-", 1)[0])
    except ValueError:
        return None


def _ingest_graphify(s: Store, project: Path, *, pre_tracked=None) -> int:
    """Ingest a graphify knowledge graph (graphify-out/graph.json).

    Two-pass: nodes → entities + concept handles, then edges → linkages
    with file:line evidence. Returns the number of edges processed.
    """
    cache = project / "graphify-out" / "graph.json"
    if not cache.exists():
        return 0
    # Front-door no-op gate, same contract as `_ingest_tldr_metadata`: graph.json
    # is rewritten only when graphify re-runs, so an unchanged mtime means this
    # additive pass (per-row upsert_entity + add_concept + weighted_link +
    # add_evidence, ~18s on a re-ingest) would re-derive an identical subgraph.
    _gate_key = f"graphify:{cache}"
    _count_key = f"graphify_n:{cache}"
    try:
        _cache_mtime = cache.stat().st_mtime
    except OSError:
        _cache_mtime = None
    if pre_tracked is not None and _cache_mtime is not None:
        _prev = pre_tracked.get(_gate_key)
        if _prev is not None and abs(_prev - _cache_mtime) <= 1e-6:
            return int(pre_tracked.get(_count_key, 0))
    data = json.loads(cache.read_text())
    nodes = data.get("nodes") or []
    edges = data.get("links") or data.get("edges") or []
    if not nodes:
        return 0

    # Pass 1: register every node as both an entity (so it has a column id
    # for bitmap membership) and a concept (so it has a row id for the
    # source side of edges). Build id → (eid, cid) so pass 2 can resolve
    # both ends of each edge.
    nid_to_eid: dict[str, int] = {}
    nid_to_cid: dict[str, int] = {}
    for node in nodes:
        nid = node.get("id")
        if not nid:
            continue
        label = node.get("label") or nid
        src_file = node.get("source_file")
        meta: dict = {}
        for k in ("community", "file_type", "source_url",
                  "captured_at", "author", "contributor", "norm_label"):
            v = node.get(k)
            if v is not None:
                meta[k] = v
        eid = s.upsert_entity(
            kind=_graphify_kind(node.get("file_type")),
            name=f"graphify::{nid}",
            path=str(project / src_file) if src_file else None,
            tldr=label,
            meta=meta,
        )
        nid_to_eid[nid] = eid
        cid = s.add_concept(
            f"gf/{nid}",
            description=f"graphify node '{label}'",
        )
        nid_to_cid[nid] = cid

    # Track verbs we've already ensured to avoid per-edge linkage lookups.
    verbs_seen: set[str] = set()

    def ensure_verb(verb: str) -> None:
        if verb in verbs_seen:
            return
        try:
            s.get_linkage_id(verb)
        except KeyError:
            s.add_linkage_type(
                verb, directed=True,
                description=f"graphify relation '{verb}'",
            )
        verbs_seen.add(verb)

    # Pass 2: edges → linkages with weighted evidence.
    n = 0
    with s.deferred_links():
        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            relation = edge.get("relation")
            if not src or not tgt or not relation:
                continue
            if src not in nid_to_cid or tgt not in nid_to_eid:
                continue
            verb = _GRAPHIFY_VERB_MAP.get(relation, relation)
            ensure_verb(verb)
            confidence = edge.get("confidence") or "EXTRACTED"
            cw = _GRAPHIFY_CONFIDENCE_W.get(confidence, 1.0)
            weight = float(edge.get("weight") or 1.0) * cw * float(
                edge.get("confidence_score") or 1.0
            )
            src_cid = nid_to_cid[src]
            tgt_eid = nid_to_eid[tgt]
            s.weighted_link(verb, src_cid, tgt_eid, weight=weight)
            s.add_evidence(
                verb, src_cid, tgt_eid,
                file=edge.get("source_file"),
                line=_parse_source_line(edge.get("source_location")),
                detail=edge.get("context") or f"graphify:{confidence}",
            )
            n += 1
    if _cache_mtime is not None:
        s.mark_tracked(_gate_key, _cache_mtime)
        s.mark_tracked(_count_key, float(n))
    return n


# --- tree -------------------------------------------------------------------


def _ingest_tree(s: Store, root: Path) -> int:
    """Walk the tree, batching entity upserts.

    Per-row upsert_entity was O(N) cursor + (pre-transaction-wrap) commit
    calls. Batching via bulk_upsert_entity reduces it to a handful of
    executemany batches, which under the outer ingest transaction land
    in one final WAL flush.
    """
    BATCH = 1000
    batch: list[tuple[str, str, str | None, str | None, dict | None]] = []
    track_payload: list[tuple[str, float]] = []

    def _flush() -> None:
        if not batch:
            return
        s.bulk_upsert_entity(batch)
        for tpath, tmtime in track_payload:
            s.mark_tracked(tpath, tmtime)
        batch.clear()
        track_payload.clear()

    n = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if should_ignore(p, root):
            continue
        rel = p.relative_to(root).as_posix()
        ext = p.suffix.lower()
        if ext in DOC_EXTS:
            kind = "doc"
        elif ext in CODE_EXTS:
            kind = "code"
        else:
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        batch.append((kind, rel, str(p), None, None))
        track_payload.append((str(p), mtime))
        n += 1
        if len(batch) >= BATCH:
            _flush()
    _flush()
    return n


# --- Python semantic enrichment --------------------------------------------

# crude stop-list to keep docstring-mined concepts useful
_DOCSTRING_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "is", "are",
    "be", "this", "that", "it", "as", "on", "from", "with", "by", "if",
    "into", "out", "not", "but", "so", "we", "you", "i", "me", "my", "our",
    "use", "used", "uses", "using", "see", "also", "can", "may", "must",
    "will", "should", "would", "could", "args", "arg", "kwargs", "kwarg",
    "param", "params", "return", "returns", "raise", "raises", "yields",
    "yield", "note", "notes", "example", "examples", "default", "true", "false",
    "none", "self", "cls", "type", "types", "value", "values", "object", "objects",
}
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _ingest_python_semantics(s: Store, file_path: Path, project_root: Path) -> int:
    """Emit namespaced concepts so noise is filterable:
    - import/<module>  for ImportNode targets
    - keyword/<word>   for docstring keywords
    Function-name concepts (from the call graph) stay bare so they collide
    naturally with user concepts (which is the desired join behavior).
    Records linkage_evidence with file:line for explainability.

    Direct path: parses + writes against a real Store in one call. The
    parallel-parse path (`_build_python_semantic_record`) shares the same
    AST-walk body via `_python_semantic_emit_body`.
    """
    try:
        src = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except (SyntaxError, OSError):
        return 0
    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    return _python_semantic_emit_body(s, tree, rel, file_path)


def _build_python_semantic_record(
    file_path: Path,
    project_root: Path,
) -> "IngestRecord | None":
    """Pure-parse builder for a .py file -- worker-thread safe. Runs the same
    AST walk as `_ingest_python_semantics` against a RecordingStore so the
    applier can replay it in one bulk batch. Mirrors `_build_pseudo_record`."""
    from refmatrix.ingest_records import RecordingStore
    try:
        src = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except (SyntaxError, OSError):
        return None
    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    try:
        mtime: float | None = file_path.stat().st_mtime
    except OSError:
        mtime = None
    rb = RecordingStore(
        rel=rel, file_path=str(file_path), mtime=mtime, doc_kind="code",
    )
    _python_semantic_emit_body(rb, tree, rel, file_path)
    return rb.record


def _python_semantic_emit_body(s, tree, rel: str, file_path: Path) -> int:
    """Shared AST-walk body. `s` is a real Store (direct path) or a
    RecordingStore (parallel-parse path); both expose the same mutation
    surface (upsert_entity / add_namespaced_concept / add_evidence /
    bulk_link), so the walk is identical for either."""
    file_id = s.upsert_entity(kind="code", name=rel, path=str(file_path))
    try:
        s.mark_tracked(str(file_path), file_path.stat().st_mtime)
    except OSError:
        pass
    n = 0
    # Buffer (linkage, concept_id, entity_id, weight) tuples so the entity_links
    # writes flush as one Arrow batch (DuckDB) or one executemany (SQLite).
    # Saves orders of magnitude on per-row binder overhead in large files.
    pending_links: list[tuple[str, int, int, float | None]] = []

    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                cid = s.add_namespaced_concept("import", mod,
                                               description=f"Python module '{mod}'")
                pending_links.append(("imports", cid, file_id, None))
                s.add_evidence("imports", cid, file_id, file=rel, line=line,
                               detail=f"import {alias.name}")
                n += 1
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod:
                cid = s.add_namespaced_concept("import", mod,
                                               description=f"Python module '{mod}'")
                pending_links.append(("imports", cid, file_id, None))
                s.add_evidence("imports", cid, file_id, file=rel, line=line,
                               detail=f"from {node.module} import ...")
                n += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if not doc:
                continue
            fname = f"{rel}::{node.name}"
            f_id = s.upsert_entity(
                kind="code", name=fname, path=str(file_path),
                meta={"file": rel, "func": node.name, "kind": "function"},
            )
            words = [
                w.lower() for w in _WORD_RE.findall(doc)
                if w.lower() not in _DOCSTRING_STOP and not w.isdigit()
            ]
            for word, count in Counter(words).items():
                cid = s.add_namespaced_concept("keyword", word,
                                               description=f"keyword '{word}'")
                pending_links.append(("mentions", cid, f_id, float(count)))
                s.add_evidence("mentions", cid, f_id, file=rel, line=line,
                               detail=f"docstring keyword (×{count})")
                n += 1
    if pending_links:
        s.bulk_link(pending_links)
    return n


# --- .pseudo pseudocode semantic enrichment --------------------------------

_PSEUDO_TYPE_RE = re.compile(r'^([A-Z][A-Za-z0-9]+):\s*(?:#.*)?$')
_PSEUDO_FUNC_RE = re.compile(
    r'^([a-z_][a-z0-9_]*)\s*\(([^)]*)\)(?:\s*->\s*(.+?))?\s*:\s*(?:#.*)?$'
)
_PSEUDO_FUNC_MULTILINE_RE = re.compile(r'^([a-z_][a-z0-9_]*)\s*\(')
_PSEUDO_FIELD_RE = re.compile(r'^\s+([a-z_][a-z0-9_]*)\s*:\s*(.+?)(?:\s*#.*)?$')
_PSEUDO_ENUM_VALUE_RE = re.compile(r'^\s+([A-Z][A-Z_0-9]+)(?:\s*=\s*.+)?\s*(?:#.*)?$')
_PSEUDO_IMPORT_RE = re.compile(r'^from\s+(\w+)\s+import\s+(.+)')
_PSEUDO_TYPE_REF_RE = re.compile(r'[A-Z][A-Za-z0-9]{2,}')
_PSEUDO_CALL_RE = re.compile(r'\b([a-z_][a-z0-9_]{2,})\s*\(')

_PSEUDO_BUILTIN_TYPES = frozenset({
    "None", "True", "False", "int", "int32", "int64", "uint32", "uint64",
    "float", "double", "string", "bool", "bytes", "UUID", "JSON",
    "list", "dict", "map", "set", "tuple", "optional",
})


def _build_pseudo_record(
    file_path: Path,
    project_root: Path,
) -> "IngestRecord | None":
    """Pure-parse builder for a .pseudo file -- worker-thread safe."""
    from refmatrix.ingest_records import RecordingStore
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    try:
        mtime: float | None = file_path.stat().st_mtime
    except OSError:
        mtime = None
    rb = RecordingStore(
        rel=rel, file_path=str(file_path), mtime=mtime, doc_kind="code",
    )
    _pseudo_emit_body(rb, lines, rel, file_path)
    return rb.record


def _ingest_pseudo_semantics(s: Store, file_path: Path, project_root: Path) -> int:
    """Extract types, enums, functions, and cross-references from .pseudo files.

    Delegates to _pseudo_emit_body so the same body runs against either a
    real Store (direct path) or a RecordingStore (parallel-parse path)."""
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0
    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    return _pseudo_emit_body(s, lines, rel, file_path)


def _pseudo_emit_body(
    s, lines: list[str], rel: str, file_path: Path,
) -> int:
    file_id = s.upsert_entity(kind="code", name=rel, path=str(file_path))
    try:
        s.mark_tracked(str(file_path), file_path.stat().st_mtime)
    except OSError:
        pass
    n = 0

    STATE_TOP, STATE_TYPE, STATE_ENUM, STATE_FUNC = range(4)
    state = STATE_TOP
    cur_eid: int | None = None
    cur_name: str | None = None

    concept_cache: dict[str, int] = {}

    def get_concept(name: str) -> int:
        if name in concept_cache:
            return concept_cache[name]
        cid = s.add_concept(name, description=f"pseudo symbol '{name}'")
        concept_cache[name] = cid
        return cid

    def extract_type_refs(annotation: str) -> list[str]:
        return [
            t for t in _PSEUDO_TYPE_REF_RE.findall(annotation)
            if t not in _PSEUDO_BUILTIN_TYPES
        ]

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('//'):
            continue

        indent = len(line) - len(line.lstrip())

        # Top-level definitions (col 0)
        if indent == 0:
            # Import statement
            m = _PSEUDO_IMPORT_RE.match(line)
            if m:
                mod = m.group(1)
                cid = s.add_namespaced_concept(
                    "import", mod, description=f"pseudo module '{mod}'")
                s.link("imports", cid, file_id)
                s.add_evidence("imports", cid, file_id, file=rel, line=lineno,
                               detail=f"from {mod} import {m.group(2).strip()}")
                n += 1
                state = STATE_TOP
                continue

            # Type/struct/enum definition
            m = _PSEUDO_TYPE_RE.match(line)
            if m:
                name = m.group(1)
                qname = f"{rel}::{name}"
                cur_eid = s.upsert_entity(
                    kind="code", name=qname, path=str(file_path),
                    meta={"file": rel, "func": name, "kind": "type", "line": lineno},
                )
                cur_name = name
                cid = get_concept(name)
                s.link("defines", cid, cur_eid)
                s.add_evidence("defines", cid, cur_eid, file=rel, line=lineno,
                               detail=f"type {name}")
                n += 1
                state = STATE_TYPE
                continue

            # Function definition
            m = _PSEUDO_FUNC_RE.match(line)
            if not m:
                m = _PSEUDO_FUNC_MULTILINE_RE.match(line)
            if m:
                name = m.group(1)
                qname = f"{rel}::{name}"
                cur_eid = s.upsert_entity(
                    kind="code", name=qname, path=str(file_path),
                    meta={"file": rel, "func": name, "kind": "function", "line": lineno},
                )
                cur_name = name
                cid = get_concept(name)
                s.link("defines", cid, cur_eid)
                s.add_evidence("defines", cid, cur_eid, file=rel, line=lineno,
                               detail=f"function {name}")
                n += 1
                # Extract type refs from params and return type
                if hasattr(m, 'group') and m.lastindex and m.lastindex >= 2:
                    params = m.group(2) or ""
                    ret = m.group(3) if m.lastindex >= 3 else None
                    for tref in extract_type_refs(params):
                        tc = get_concept(tref)
                        s.link("mentions", tc, cur_eid)
                        n += 1
                    if ret:
                        for tref in extract_type_refs(ret):
                            tc = get_concept(tref)
                            s.link("mentions", tc, cur_eid)
                            n += 1
                state = STATE_FUNC
                continue

            # Anything else at col 0 resets state
            state = STATE_TOP
            cur_eid = None
            continue

        # Indented lines — context-dependent
        if cur_eid is None:
            continue

        if state == STATE_TYPE:
            # Check if this is actually an enum
            if _PSEUDO_ENUM_VALUE_RE.match(line):
                state = STATE_ENUM
                continue
            # Field: extract type references
            m = _PSEUDO_FIELD_RE.match(line)
            if m:
                annotation = m.group(2)
                for tref in extract_type_refs(annotation):
                    tc = get_concept(tref)
                    s.link("mentions", tc, cur_eid)
                    s.add_evidence("mentions", tc, cur_eid, file=rel, line=lineno,
                                   detail=f"field type ref {tref}")
                    n += 1

        elif state == STATE_ENUM:
            pass  # enum values don't generate linkages

        elif state == STATE_FUNC:
            # Scan for function calls
            for call_match in _PSEUDO_CALL_RE.finditer(line):
                callee = call_match.group(1)
                if callee == cur_name:
                    continue
                cc = get_concept(callee)
                s.link("calls", cc, cur_eid)
                n += 1
            # Scan for type references
            for tref in extract_type_refs(line):
                tc = get_concept(tref)
                s.link("mentions", tc, cur_eid)
                n += 1

    return n


# --- ADR markdown semantic enrichment --------------------------------------

_ADR_FILENAME_RE = re.compile(r'^(\d{4})-.*\.md$')
_ADR_HEADER_FIELD_RE = re.compile(
    r'^\*{0,2}([A-Z][A-Za-z-]+):\*{0,2}\s*(.+?)\s*$'
)
_ADR_REF_RE = re.compile(r'\bADR-(\d{4})\b')
_ADR_CLASS_RE = re.compile(
    r'^(?:(?:class|enum|struct|interface)\s+)?([A-Z][A-Za-z0-9_]+)\s*(?:(?:\(|extends\s+)([A-Za-z0-9_,\s]+)\)?)?\s*:\s*(?:#.*)?$'
)
_ADR_TREE_CHILD_RE = re.compile(
    r'^\s*[+\-|]+--\s*([A-Z][A-Za-z0-9_]+)'
    r'(?:\s*\(([A-Za-z0-9_,\s]+)\))?'
)
_ADR_METHOD_RE = re.compile(
    r'^\s+([a-z_][a-z0-9_]*)\s*\(([^)]*)\)\s*(?:->\s*([^#]+?))?\s*(?:#.*)?$'
)
_ADR_GOVERNS_TOKEN_RE = re.compile(r'\b([A-Z][A-Za-z0-9_]{2,})\b')

_ADR_STATUS_WEIGHT = {
    "Accepted": 1.0,
    "Proposed": 0.3,
    "Draft": 0.2,
    "Superseded": 0.0,
    "Deprecated": 0.0,
    "Rejected": 0.0,
}


def _is_adr_file(p: Path) -> str | None:
    """Return zero-padded ADR number if p looks like an ADR markdown, else None."""
    if p.suffix.lower() != ".md":
        return None
    if not any(part.lower() == "adr" for part in p.parts):
        return None
    m = _ADR_FILENAME_RE.match(p.name)
    return m.group(1) if m else None


def _parse_adr_header(lines: list[str]) -> dict[str, str]:
    """Pull YAML-ish header fields from the top of an ADR.

    Stops at the first ## section heading. Tolerates a leading '# Title' line
    and blank lines. Continuation lines (indented under a field) are joined
    with a space so multi-line Governs/Cross-references survive.
    """
    header: dict[str, str] = {}
    last_key: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if not stripped:
            last_key = None
            continue
        if stripped.startswith("# ") and last_key is None:
            continue
        m = _ADR_HEADER_FIELD_RE.match(stripped)
        if m:
            last_key = m.group(1)
            header[last_key] = m.group(2).strip()
        elif last_key and (line.startswith(" ") or line.startswith("\t")):
            header[last_key] = (header[last_key] + " " + stripped).strip()
        else:
            last_key = None
    return header


def _build_adr_record(
    file_path: Path,
    project_root: Path,
    adr_num_to_eid: dict[str, int],
) -> "IngestRecord | None":
    """Pure-parse builder for an ADR markdown file. Returns a record that
    apply_record materializes against the real Store. Mirrors the legacy
    _ingest_adr_semantics logic but writes through a RecordingStore so
    workers can parse in parallel without touching the catalog.
    """
    from refmatrix.ingest_records import RecordingStore
    adr_num = _is_adr_file(file_path)
    if adr_num is None or adr_num not in adr_num_to_eid:
        return None
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    lines = text.splitlines()
    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    try:
        mtime: float | None = file_path.stat().st_mtime
    except OSError:
        mtime = None
    header = _parse_adr_header(lines)
    status_raw = header.get("Status", "Proposed")
    status = status_raw.split()[0] if status_raw else "Proposed"
    weight = _ADR_STATUS_WEIGHT.get(status, 0.3)
    if weight == 0.0:
        return None

    rb = RecordingStore(
        rel=rel, file_path=str(file_path), mtime=mtime,
        doc_kind="doc", doc_meta={"adr_number": adr_num},
    )
    adr_eid = rb.upsert_entity(
        kind="doc", name=rel, path=str(file_path),
        meta={"adr_number": adr_num},
    )

    concept_cache: dict[str, str] = {}

    def get_concept(name: str) -> str:
        if name in concept_cache:
            return concept_cache[name]
        cid = rb.add_concept(name, description=f"symbol '{name}'")
        concept_cache[name] = cid
        return cid

    _adr_emit_body(
        rb, lines, text, rel, file_path, adr_num, adr_eid,
        adr_num_to_eid, weight, get_concept,
    )
    return rb.record


def _ingest_adr_semantics(
    s: Store,
    file_path: Path,
    project_root: Path,
    adr_num_to_eid: dict[str, int],
) -> int:
    """Compatibility wrapper around _build_adr_record + apply_record so
    direct callers (sync.py, tests) keep working. The parallel ingest
    path bypasses this and calls the builder directly."""
    from refmatrix.ingest_records import apply_record
    rec = _build_adr_record(file_path, project_root, adr_num_to_eid)
    if rec is None:
        return 0
    return apply_record(s, rec, adr_num_to_eid=adr_num_to_eid)


def _adr_emit_body(
    s,
    lines: list[str],
    text: str,
    rel: str,
    file_path: Path,
    adr_num: str,
    adr_eid,
    adr_num_to_eid: dict[str, int],
    weight: float,
    get_concept,
) -> int:
    """Body extraction shared between the legacy single-call path and the
    record-builder. `s` is either a real Store or a RecordingStore; this
    fn never branches on the type."""
    header = _parse_adr_header(lines)
    n = 0

    # Governs line → mentions linkage on CamelCase tokens
    governs = header.get("Governs", "")
    for tok in _ADR_GOVERNS_TOKEN_RE.findall(governs):
        if tok in _PSEUDO_BUILTIN_TYPES:
            continue
        cid = get_concept(tok)
        s.weighted_link("mentions", cid, adr_eid, weight=weight)
        s.add_evidence("mentions", cid, adr_eid, file=rel, line=1,
                       detail=f"Governs: {tok}")
        n += 1

    # Cross-references → related_to via adr/NNNN namespaced concept hub
    seen_refs: set[str] = set()
    for m in _ADR_REF_RE.finditer(text):
        ref_num = m.group(1)
        if ref_num == adr_num or ref_num in seen_refs:
            continue
        seen_refs.add(ref_num)
        if hasattr(s, "register_ref_resolve"):
            if ref_num not in adr_num_to_eid:
                continue
            target_eid = f"@adr:{ref_num}"
        else:
            target_eid = adr_num_to_eid.get(ref_num)
            if target_eid is None:
                continue
        ref_concept = s.add_namespaced_concept(
            "adr", ref_num, description=f"ADR-{ref_num}"
        )
        s.link("related_to", ref_concept, adr_eid)
        s.link("related_to", ref_concept, target_eid)
        s.add_evidence("related_to", ref_concept, adr_eid,
                       file=rel, detail=f"references ADR-{ref_num}")
        n += 1

    # Class / struct specs + subclass trees
    in_fence = False
    cur_class_eid: int | None = None
    cur_class_name: str | None = None
    class_block_indent: int = -1

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1
            continue

        if not stripped:
            continue

        if not in_fence and stripped.startswith("#"):
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1
            continue

        indent = len(line) - len(line.lstrip())

        # Subclass tree line e.g. "+-- AnnotatedZone(Zone)"
        tm = _ADR_TREE_CHILD_RE.match(line)
        if tm:
            child = tm.group(1)
            parents_str = tm.group(2) or ""
            child_qname = f"{rel}::{child}"
            child_eid = s.upsert_entity(
                kind="doc", name=child_qname, path=str(file_path),
                meta={"file": rel, "func": child, "kind": "class",
                      "adr": adr_num, "line": lineno},
            )
            cc = get_concept(child)
            s.weighted_link("defines", cc, child_eid, weight=weight)
            s.add_evidence("defines", cc, child_eid, file=rel, line=lineno,
                           detail=f"ADR-{adr_num} subclass {child}")
            n += 1
            for parent in (p.strip() for p in parents_str.split(",")):
                if not parent or parent in _PSEUDO_BUILTIN_TYPES:
                    continue
                pc = get_concept(parent)
                s.weighted_link("is_a", pc, child_eid, weight=weight)
                s.add_evidence("is_a", pc, child_eid, file=rel, line=lineno,
                               detail=f"{child} subclass of {parent}")
                n += 1
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1
            continue

        # Class definition: CamelCase at col 0 inside fence, OR CamelCase at
        # col 0 outside fence (indented pseudocode block under a heading)
        cm = _ADR_CLASS_RE.match(line) if indent == 0 else None
        if cm and (in_fence or _looks_like_class_block(lines, lineno)):
            name = cm.group(1)
            parents_str = cm.group(2) or ""
            qname = f"{rel}::{name}"
            cur_class_eid = s.upsert_entity(
                kind="doc", name=qname, path=str(file_path),
                meta={"file": rel, "func": name, "kind": "class",
                      "adr": adr_num, "line": lineno},
            )
            cur_class_name = name
            class_block_indent = 0
            cid = get_concept(name)
            s.weighted_link("defines", cid, cur_class_eid, weight=weight)
            s.add_evidence("defines", cid, cur_class_eid, file=rel, line=lineno,
                           detail=f"ADR-{adr_num} class {name}")
            n += 1
            for parent in (p.strip() for p in parents_str.split(",")):
                if not parent or parent in _PSEUDO_BUILTIN_TYPES:
                    continue
                pc = get_concept(parent)
                s.weighted_link("is_a", pc, cur_class_eid, weight=weight)
                s.add_evidence("is_a", pc, cur_class_eid, file=rel, line=lineno,
                               detail=f"{name} subclass of {parent}")
                n += 1
            continue

        # Body of an open class block: methods + type refs
        if cur_class_eid is not None and indent > class_block_indent:
            mm = _ADR_METHOD_RE.match(line)
            if mm:
                method = mm.group(1)
                mc = get_concept(method)
                s.weighted_link("mentions", mc, cur_class_eid, weight=weight)
                n += 1
                # Type refs in params + return
                for blob in (mm.group(2) or "", mm.group(3) or ""):
                    for tref in _PSEUDO_TYPE_REF_RE.findall(blob):
                        if tref in _PSEUDO_BUILTIN_TYPES or tref == cur_class_name:
                            continue
                        tc = get_concept(tref)
                        s.weighted_link("mentions", tc, cur_class_eid, weight=weight)
                        n += 1
            else:
                for tref in _PSEUDO_TYPE_REF_RE.findall(line):
                    if tref in _PSEUDO_BUILTIN_TYPES or tref == cur_class_name:
                        continue
                    tc = get_concept(tref)
                    s.weighted_link("mentions", tc, cur_class_eid, weight=weight)
                    n += 1
        elif cur_class_eid is not None and indent <= class_block_indent:
            # Dedent back to col 0 with non-class content closes the block
            cur_class_eid = None
            cur_class_name = None
            class_block_indent = -1

    return n


def _looks_like_class_block(lines: list[str], lineno_1based: int) -> bool:
    """Heuristic: a 'Name:' line outside a fence opens a class block only if
    the next non-blank line is indented. Avoids treating markdown labels like
    'Status:' or 'Decision:' as class definitions (they're caught by header
    parser, but also appear in prose)."""
    idx = lineno_1based  # next line index in 0-based
    while idx < len(lines):
        nxt = lines[idx]
        if not nxt.strip():
            idx += 1
            continue
        return nxt.startswith(" ") or nxt.startswith("\t")
    return False


# --- General markdown semantic enrichment ----------------------------------

# Concept-doc detection: a markdown file is a concept doc if any of these dir
# names appears in its path. Concept docs get H1 + H3 extraction.
_CONCEPT_DOC_DIRS = frozenset({"concepts", "concept", "glossary"})

# Plan-doc detection: a markdown file is a plan/spec/issue if filename or any
# path segment matches. Plan docs get the same H1+H3 extraction as concept
# docs but emit `specifies` (not `defines`) so provenance back to the spec
# survives queries on the produced concept.
_PLAN_DOC_DIRS = frozenset({
    "plans", "plan", "specs", "spec", "issues", "issue", "roadmap",
})
_PLAN_FILENAME_RE = re.compile(
    r"^(?:PLAN|ISSUE|SPEC|ROADMAP)(?:[-_][\w.\-]+)?\.md$",
    re.IGNORECASE,
)

# Bold-labeled metadata refs in design-doc headers.
# Matches: **Source:** path.md  /  **Referenced by:** a.md, b.md
_MD_BOLD_LABEL_RE = re.compile(
    r'^\*\*([A-Za-z][A-Za-z \-]*?):\*\*\s*(.+?)\s*$'
)

# Labels that point at other docs/ADRs. Other bold labels (Created, Authors,
# Date, Tags) are ignored — they're metadata about this doc, not refs.
_MD_REF_LABELS = frozenset({
    "Source", "Referenced by", "Companion", "Implements",
    "Supersedes", "Replaces", "See also", "Related", "Related to",
    "Depends on", "Extends", "Builds on",
})

# H3 with a single CamelCase token (optionally followed by parenthetical or
# em-dash continuation). The captured group is the concept name.
_MD_H3_CONCEPT_RE = re.compile(
    r'^###\s+([A-Z][A-Za-z0-9]+)(?:\s*[\(\-—–:].*)?$'
)
_MD_H1_RE = re.compile(r'^#\s+(.+?)\s*$')
_MD_FIRST_CAMEL_RE = re.compile(r'\b([A-Z][A-Za-z0-9]{2,})\b')

# Inheritance prose inside an H3 body. Two forms:
#   "X subclasses Y"  /  "X extends Y"            (both CamelCase)
#   "...subclasses Y" / "...extends Y"            (use H3 title as child)
_MD_SUBCLASS_RE = re.compile(
    r'\b(?:subclasses|extends)\s+([A-Z][A-Za-z0-9]+)\b'
)
_MD_SUBCLASS_BOTH_RE = re.compile(
    r'\b([A-Z][A-Za-z0-9]+)\s+(?:subclasses|extends)\s+([A-Z][A-Za-z0-9]+)\b'
)


def _is_concept_doc(file_path: Path) -> bool:
    return any(part.lower() in _CONCEPT_DOC_DIRS for part in file_path.parts)


def _is_plan_file(file_path: Path) -> bool:
    if file_path.suffix.lower() != ".md":
        return False
    if _PLAN_FILENAME_RE.match(file_path.name):
        return True
    return any(part.lower() in _PLAN_DOC_DIRS for part in file_path.parts)


def _kebab_to_pascal(stem: str) -> str:
    """Convert kebab-case filename stem to PascalCase concept name."""
    parts = re.split(r'[-_]', stem)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _resolve_ref_target(
    s,
    raw: str,
    project_root: Path,
    source_dir: Path,
):
    """Resolve a bold-metadata value to a doc/code entity.

    Tries the value as project-relative path, source-relative path, and
    bare basename. Returns the entity id (real Store mode) or a symbolic
    @ref handle (RecordingStore mode -- resolved by the applier later)
    or None if no candidate could be built.
    """
    raw = raw.strip().strip("`").strip()
    if not raw:
        return None
    candidate_names: list[str] = []
    candidate_names.append(raw)
    try:
        sr = (source_dir / raw).resolve().relative_to(project_root).as_posix()
        candidate_names.append(sr)
    except (ValueError, OSError):
        pass
    try:
        pr = (project_root / raw).resolve().relative_to(project_root).as_posix()
        candidate_names.append(pr)
    except (ValueError, OSError):
        pass
    if not candidate_names:
        return None
    # RecordingStore mode -- defer resolution to apply phase
    if hasattr(s, "register_ref_resolve"):
        candidates = [
            (kind, name)
            for name in candidate_names
            for kind in ("doc", "code")
        ]
        return s.register_ref_resolve(candidates)
    # Real Store -- resolve immediately
    for cand in candidate_names:
        for kind in ("doc", "code"):
            ent = s.get_entity(kind, cand)
            if ent is not None:
                return ent.id
    return None


def _build_markdown_record(
    file_path: Path,
    project_root: Path,
    adr_num_to_eid: dict[str, int],
) -> "IngestRecord | None":
    """Pure-parse build of an IngestRecord for a non-ADR markdown file.

    No Store access. Safe to call from worker threads in parallel; the
    returned record is replayed sequentially against the real Store via
    ingest_records.apply_record. Mirrors the semantics of the old
    _ingest_markdown_semantics path -- helpers below accept a
    RecordingStore in place of a real Store and emit the same calls.
    """
    from refmatrix.ingest_records import RecordingStore
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    lines = text.splitlines()

    rel = (
        file_path.relative_to(project_root).as_posix()
        if file_path.is_relative_to(project_root)
        else str(file_path)
    )
    try:
        mtime: float | None = file_path.stat().st_mtime
    except OSError:
        mtime = None

    rb = RecordingStore(
        rel=rel, file_path=str(file_path), mtime=mtime, doc_kind="doc",
    )
    doc_eid = rb.upsert_entity(kind="doc", name=rel, path=str(file_path))

    concept_cache: dict[str, str] = {}

    def get_concept(name: str) -> str:
        if name in concept_cache:
            return concept_cache[name]
        cid = rb.add_concept(name, description=f"symbol '{name}'")
        concept_cache[name] = cid
        return cid

    _emit_bold_metadata_refs(
        rb, lines, rel, doc_eid, file_path, project_root,
        adr_num_to_eid, get_concept,
    )

    seen_adr_refs: set[str] = set()
    for m in _ADR_REF_RE.finditer(text):
        ref_num = m.group(1)
        if ref_num in seen_adr_refs:
            continue
        seen_adr_refs.add(ref_num)
        if ref_num not in adr_num_to_eid:
            continue
        ref_concept = rb.add_namespaced_concept(
            "adr", ref_num, description=f"ADR-{ref_num}"
        )
        rb.link("related_to", ref_concept, doc_eid)
        rb.link("related_to", ref_concept, f"@adr:{ref_num}")
        rb.add_evidence("related_to", ref_concept, doc_eid,
                        file=rel, detail=f"references ADR-{ref_num}")

    is_plan = _is_plan_file(file_path)
    if _is_concept_doc(file_path):
        _emit_concept_doc_linkages(
            rb, lines, rel, doc_eid, file_path, get_concept,
        )
    elif is_plan:
        _emit_concept_doc_linkages(
            rb, lines, rel, doc_eid, file_path, get_concept,
            verb="specifies",
        )

    _emit_md_fenced_class_specs(
        rb, lines, rel, doc_eid, file_path, get_concept, weight=0.5,
        verb="specifies" if is_plan else "defines",
    )

    return rb.record


def _ingest_markdown_semantics(
    s: Store,
    file_path: Path,
    project_root: Path,
    adr_num_to_eid: dict[str, int],
) -> int:
    """Compatibility wrapper: build a record, apply it. Preserves the
    old single-call entry point for any direct callers (sync.py, tests).
    The parallel ingest path bypasses this and calls
    _build_markdown_record + apply_record directly."""
    from refmatrix.ingest_records import apply_record
    rec = _build_markdown_record(file_path, project_root, adr_num_to_eid)
    if rec is None:
        return 0
    return apply_record(s, rec, adr_num_to_eid=adr_num_to_eid)


def _emit_bold_metadata_refs(
    s: Store,
    lines: list[str],
    rel: str,
    doc_eid: int,
    file_path: Path,
    project_root: Path,
    adr_num_to_eid: dict[str, int],
    get_concept,
) -> int:
    """Scan first 50 non-blank lines for **Label:** value refs."""
    n = 0
    scanned = 0
    source_dir = file_path.parent
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            break
        scanned += 1
        if scanned > 50:
            break
        m = _MD_BOLD_LABEL_RE.match(stripped)
        if not m:
            continue
        label = m.group(1).strip()
        value = m.group(2).strip()
        if label not in _MD_REF_LABELS:
            continue
        # Split on commas; values may be paths or ADR-NNNN refs
        for raw in value.split(","):
            tok = raw.strip().strip("`").strip()
            if not tok:
                continue
            # ADR ref?
            adr_m = _ADR_REF_RE.search(tok)
            if adr_m:
                ref_num = adr_m.group(1)
                # In record-build mode we can't reference the real id by
                # int; use the symbolic @adr:NNNN handle so the applier
                # binds it via adr_num_to_eid at apply time. In direct
                # mode the dict carries real ids, so look it up.
                if hasattr(s, "register_ref_resolve"):
                    if ref_num not in adr_num_to_eid:
                        continue
                    target_eid = f"@adr:{ref_num}"
                else:
                    target_eid = adr_num_to_eid.get(ref_num)
                    if target_eid is None:
                        continue
                ref_concept = s.add_namespaced_concept(
                    "adr", ref_num, description=f"ADR-{ref_num}"
                )
                s.link("related_to", ref_concept, doc_eid)
                s.link("related_to", ref_concept, target_eid)
                s.add_evidence("related_to", ref_concept, doc_eid,
                               file=rel, line=lineno,
                               detail=f"{label}: ADR-{ref_num}")
                n += 1
                continue
            # Path ref?
            target_eid = _resolve_ref_target(s, tok, project_root, source_dir)
            if target_eid is not None and target_eid != doc_eid:
                path_concept = s.add_namespaced_concept(
                    "ref", tok, description=f"reference to {tok}"
                )
                s.link("related_to", path_concept, doc_eid)
                s.link("related_to", path_concept, target_eid)
                s.add_evidence("related_to", path_concept, doc_eid,
                               file=rel, line=lineno,
                               detail=f"{label}: {tok}")
                n += 1
    return n


def _emit_concept_doc_linkages(
    s: Store,
    lines: list[str],
    rel: str,
    doc_eid: int,
    file_path: Path,
    get_concept,
    verb: str = "defines",
) -> int:
    """Concept-doc shape: filename + H1 → <verb> this doc; H3 PascalCase →
    sub-entity with <verb> + is_a-from-prose. `verb` is "defines" for concept
    docs / glossary entries, "specifies" for plan / issue / spec files (where
    the doc declares intent for code that should exist)."""
    n = 0

    # Filename stem → PascalCase concept linked to this doc
    stem = file_path.stem
    fname_concept = _kebab_to_pascal(stem)
    if fname_concept:
        cid = get_concept(fname_concept)
        s.link(verb, cid, doc_eid)
        s.add_evidence(verb, cid, doc_eid, file=rel,
                       detail=f"concept doc filename: {stem}")
        n += 1

    # H1 first CamelCase token linked to this doc
    for line in lines:
        h1 = _MD_H1_RE.match(line)
        if h1:
            first = _MD_FIRST_CAMEL_RE.search(h1.group(1))
            if first:
                cid = get_concept(first.group(1))
                s.link(verb, cid, doc_eid)
                s.add_evidence(verb, cid, doc_eid, file=rel, line=1,
                               detail=f"H1 concept: {first.group(1)}")
                n += 1
            break

    # H3 sections: each single-CamelCase H3 defines a sub-concept entity.
    # Collect H3 ranges so we can scan body for subclass/extends.
    h3_ranges: list[tuple[str, int, int]] = []  # (concept_name, start, end)
    cur_h3: str | None = None
    cur_start: int = -1
    for i, line in enumerate(lines):
        if line.startswith("###"):
            if cur_h3 is not None:
                h3_ranges.append((cur_h3, cur_start, i))
            m = _MD_H3_CONCEPT_RE.match(line)
            if m:
                cur_h3 = m.group(1)
                cur_start = i + 1
            else:
                cur_h3 = None
        elif line.startswith("## ") or line.startswith("# "):
            if cur_h3 is not None:
                h3_ranges.append((cur_h3, cur_start, i))
            cur_h3 = None
    if cur_h3 is not None:
        h3_ranges.append((cur_h3, cur_start, len(lines)))

    for name, start, end in h3_ranges:
        qname = f"{rel}::{name}"
        sub_eid = s.upsert_entity(
            kind="doc", name=qname, path=str(file_path),
            meta={"file": rel, "func": name, "kind": "concept",
                  "line": start},
        )
        cc = get_concept(name)
        s.link(verb, cc, sub_eid)
        s.add_evidence(verb, cc, sub_eid, file=rel, line=start,
                       detail=f"H3 concept: {name}")
        n += 1

        # Subclass/extends prose in this H3's body
        body = "\n".join(lines[start:end])
        seen_parents: set[str] = set()
        # Form 1: "X subclasses Y" (both CamelCase) — emit both directions
        for cm in _MD_SUBCLASS_BOTH_RE.finditer(body):
            child = cm.group(1)
            parent = cm.group(2)
            if parent in _PSEUDO_BUILTIN_TYPES or parent == child:
                continue
            key = f"{child}<{parent}"
            if key in seen_parents:
                continue
            seen_parents.add(key)
            # If the child matches the H3 name, link to sub_eid; else create child sub-entity
            if child == name:
                target_eid = sub_eid
            else:
                child_qname = f"{rel}::{child}"
                target_eid = s.upsert_entity(
                    kind="doc", name=child_qname, path=str(file_path),
                    meta={"file": rel, "func": child, "kind": "concept",
                          "line": start},
                )
                cc2 = get_concept(child)
                s.link(verb, cc2, target_eid)
                n += 1
            pc = get_concept(parent)
            s.link("is_a", pc, target_eid)
            s.add_evidence("is_a", pc, target_eid, file=rel, line=start,
                           detail=f"{child} subclasses {parent}")
            n += 1
        # Form 2: bare "subclasses Y" / "extends Y" — child is the H3 concept
        for cm in _MD_SUBCLASS_RE.finditer(body):
            parent = cm.group(1)
            if parent in _PSEUDO_BUILTIN_TYPES or parent == name:
                continue
            key = f"{name}<{parent}"
            if key in seen_parents:
                continue
            seen_parents.add(key)
            pc = get_concept(parent)
            s.link("is_a", pc, sub_eid)
            s.add_evidence("is_a", pc, sub_eid, file=rel, line=start,
                           detail=f"{name} subclasses {parent}")
            n += 1
    return n


def _emit_md_fenced_class_specs(
    s: Store,
    lines: list[str],
    rel: str,
    doc_eid: int,
    file_path: Path,
    get_concept,
    weight: float,
    verb: str = "defines",
) -> int:
    """Universal: parse fenced code blocks for class specs (Name: + indented
    body). Mirrors the ADR class-spec parser but only handles fenced blocks
    (no indented-pseudocode case — that's too noisy outside ADRs). `verb` is
    "defines" by default; plan/spec files pass "specifies".
    """
    n = 0
    in_fence = False
    cur_class_eid: int | None = None
    cur_class_name: str | None = None

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            cur_class_eid = None
            cur_class_name = None
            continue
        if not in_fence:
            continue
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue

        indent = len(line) - len(line.lstrip())

        # Subclass tree line e.g. "+-- Child(Parent)"
        tm = _ADR_TREE_CHILD_RE.match(line)
        if tm:
            child = tm.group(1)
            parents_str = tm.group(2) or ""
            child_qname = f"{rel}::{child}"
            child_eid = s.upsert_entity(
                kind="doc", name=child_qname, path=str(file_path),
                meta={"file": rel, "func": child, "kind": "class",
                      "line": lineno},
            )
            cc = get_concept(child)
            s.weighted_link(verb, cc, child_eid, weight=weight)
            s.add_evidence(verb, cc, child_eid, file=rel, line=lineno,
                           detail=f"subclass tree {child}")
            n += 1
            for parent in (p.strip() for p in parents_str.split(",")):
                if not parent or parent in _PSEUDO_BUILTIN_TYPES:
                    continue
                pc = get_concept(parent)
                s.weighted_link("is_a", pc, child_eid, weight=weight)
                n += 1
            cur_class_eid = None
            cur_class_name = None
            continue

        # Class header at col 0
        cm = _ADR_CLASS_RE.match(line) if indent == 0 else None
        if cm:
            name = cm.group(1)
            parents_str = cm.group(2) or ""
            qname = f"{rel}::{name}"
            cur_class_eid = s.upsert_entity(
                kind="doc", name=qname, path=str(file_path),
                meta={"file": rel, "func": name, "kind": "class",
                      "line": lineno},
            )
            cur_class_name = name
            cid = get_concept(name)
            s.weighted_link(verb, cid, cur_class_eid, weight=weight)
            s.add_evidence(verb, cid, cur_class_eid, file=rel, line=lineno,
                           detail=f"fenced class spec {name}")
            n += 1
            for parent in (p.strip() for p in parents_str.split(",")):
                if not parent or parent in _PSEUDO_BUILTIN_TYPES:
                    continue
                pc = get_concept(parent)
                s.weighted_link("is_a", pc, cur_class_eid, weight=weight)
                n += 1
            continue

        # Body: methods + type refs
        if cur_class_eid is not None and indent > 0:
            mm = _ADR_METHOD_RE.match(line)
            if mm:
                method = mm.group(1)
                mc = get_concept(method)
                s.weighted_link("mentions", mc, cur_class_eid, weight=weight)
                n += 1
                for blob in (mm.group(2) or "", mm.group(3) or ""):
                    for tref in _PSEUDO_TYPE_REF_RE.findall(blob):
                        if tref in _PSEUDO_BUILTIN_TYPES or tref == cur_class_name:
                            continue
                        tc = get_concept(tref)
                        s.weighted_link("mentions", tc, cur_class_eid, weight=weight)
                        n += 1
            else:
                for tref in _PSEUDO_TYPE_REF_RE.findall(line):
                    if tref in _PSEUDO_BUILTIN_TYPES or tref == cur_class_name:
                        continue
                    tc = get_concept(tref)
                    s.weighted_link("mentions", tc, cur_class_eid, weight=weight)
                    n += 1
    return n
