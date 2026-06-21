"""FastAPI app served by the hub. Read spine + watchdog control + graph/
memory/query reads + streamed ops. The hub instance is injected via
`create_app(hub)`; all DuckDB reads route through the per-project daemon
(`daemon.call`) when one is up, else a best-effort read-only Store.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from refmatrix import daemon as daemon_mod
from refmatrix import discovery, telemetry

STATIC_DIR = Path(__file__).parent / "static"


# ---- read helpers ---------------------------------------------------------


def _daemon_read(root: Path, op: str, args: dict, *, timeout: float = 60.0) -> dict:
    """Route a read op through the daemon if up; else open a read-only Store
    and run the equivalent in-process. Returns {ok, result|error}."""
    root = Path(root)
    if daemon_mod.ping(root):
        try:
            return daemon_mod.call(root, op, args, timeout=timeout)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": False, "error": "daemon not running"}


def _partition(root: Path) -> str:
    return discovery.store_name(root)


def _drain(sub):
    """Block up to 1s for the next bus message; None on timeout (keepalive)."""
    import queue as _q
    try:
        return sub.q.get(timeout=1.0)
    except _q.Empty:
        return None


import threading as _threading

# Per-root read-only replica Store cache. Opening viascope's ~670MB snapshot
# cold costs seconds; reusing the open Store makes graph navigation snappy.
# DuckDB connections aren't safe for concurrent cursors, so each cached store
# is guarded by its own lock. Read-only, so a swapped snapshot just means the
# cached view is slightly stale until the process restarts.
_REPLICA_CACHE: "dict[str, tuple]" = {}
_REPLICA_CACHE_LOCK = _threading.Lock()


def _cached_replica(root: Path):
    """Return (store, lock) for a root, opening + caching on first use."""
    from refmatrix.store import Store
    key = str(Path(root).resolve())
    with _REPLICA_CACHE_LOCK:
        hit = _REPLICA_CACHE.get(key)
        if hit is not None:
            return hit
    part = _partition(root)
    s = Store(root, partition=part, read_only=True)
    entry = (s, _threading.Lock())
    with _REPLICA_CACHE_LOCK:
        # another thread may have opened it concurrently; keep the first
        existing = _REPLICA_CACHE.setdefault(key, entry)
    if existing is not entry:
        try:
            s.close()
        except Exception:
            pass
    return existing


def replica_context(root: Path, ref: str, *, degree: int = 0,
                    max_entities: int = 20, max_tokens: int = 4000) -> dict:
    """Build a context bundle via a CACHED in-process READ-ONLY replica store —
    the same path `rmx context --via-replica` uses. The daemon's `context` op
    reads the writer store and mis-resolves concepts on a multi-partition
    daemon; the snapshot replica is the consistent read source (snapshot-tier)
    and never contends with the writer lock. Returns the render_json dict, or
    {"error": ...}."""
    from refmatrix.context import build_context, render_json
    root = Path(root)
    part = _partition(root)
    try:
        s, lock = _cached_replica(root)
    except Exception as e:
        return {"error": f"replica unavailable: {e}"}
    try:
        with lock, s.with_partition(part):
            bundle = build_context(
                s, ref, degree=degree, max_entities=max_entities,
                max_tokens=max_tokens,
                _entities_explicit=False, _tokens_explicit=False,
            )
        return json.loads(render_json(bundle))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _context_to_graph(bundle: dict) -> dict:
    """Convert a context-bundle JSON into {nodes, edges} for force-graph.
    Anchor is the center; each grouped neighbor is a node + a typed edge."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node_id(name: str, kind: str) -> str:
        return f"{kind}:{name}"

    anchor = bundle.get("anchor")
    anchor_id = None
    if anchor:
        anchor_id = node_id(anchor["name"], anchor.get("kind", "concept"))
        nodes[anchor_id] = {
            "id": anchor_id, "name": anchor["name"],
            "kind": anchor.get("kind", "concept"),
            "path": anchor.get("path"), "tldr": anchor.get("tldr"),
            "anchor": True,
        }
    else:
        # content-only / unresolved ref: synthesize a center node
        anchor_id = node_id(bundle.get("ref", "?"), "query")
        nodes[anchor_id] = {"id": anchor_id, "name": bundle.get("ref", "?"),
                            "kind": "query", "anchor": True}

    for linkage, entries in (bundle.get("groups") or {}).items():
        for e in entries:
            nid = node_id(e["name"], e.get("kind", "concept"))
            if nid not in nodes:
                nodes[nid] = {
                    "id": nid, "name": e["name"], "kind": e.get("kind", "concept"),
                    "path": e.get("path"), "tldr": e.get("tldr"),
                    "snippet": e.get("snippet"),
                }
            edges.append({
                "source": anchor_id, "target": nid, "linkage": linkage,
                "weight": e.get("weight"),
            })
    return {"ref": bundle.get("ref"), "nodes": list(nodes.values()),
            "edges": edges, "truncated": bundle.get("truncated", False)}


# ---- app ------------------------------------------------------------------


def create_app(hub) -> FastAPI:
    app = FastAPI(title="refmatrix hub", version="1")

    # ---- discovery / status ----
    @app.get("/api/projects")
    def projects(with_footprint: bool = True):
        return {"projects": discovery.all_projects(with_footprint=with_footprint)}

    @app.post("/api/projects/init")
    async def project_init(payload: dict):
        """Onboard a project: `rmx init` (+ optional install-hooks + launchd),
        then register it. Runs the CLI as a subprocess (daemon-routed writes)."""
        import os
        import subprocess
        import sys
        path = Path(payload["path"]).expanduser()
        if not path.is_dir():
            return {"ok": False, "error": f"not a directory: {path}"}
        steps: list[dict] = []

        def run(args, label):
            env = {**os.environ, "RMX_INVOCATION_SOURCE": "internal"}
            r = subprocess.run([sys.executable, "-m", "refmatrix.cli", *args],
                               cwd=str(path), env=env, capture_output=True, text=True)
            steps.append({"step": label, "ok": r.returncode == 0,
                          "out": (r.stdout or r.stderr)[-400:]})
            return r.returncode == 0

        run(["init"], "init")
        if payload.get("hooks", True):
            run(["install-hooks", "--apply"], "install-hooks")
        root = path / ".refmatrix"
        if payload.get("launchd") and sys.platform == "darwin":
            run(["daemon", "launchctl", "install"], "launchctl")
        if root.is_dir():
            discovery.register_root(root)
        return {"ok": True, "result": {"root": str(root), "steps": steps,
                                       "status": discovery.project_status(root)}}

    @app.post("/api/projects/register")
    async def project_register(payload: dict):
        root = Path(payload["root"])
        root = root if root.name == ".refmatrix" else root / ".refmatrix"
        if not root.is_dir():
            return {"ok": False, "error": f"no .refmatrix at {root}"}
        discovery.register_root(root)
        return {"ok": True, "result": {"root": str(root)}}

    @app.get("/api/stats")
    def stats(root: str):
        return _daemon_read(Path(root), "stats", {"include_stale": True})

    @app.get("/api/footprint")
    def footprint(root: str):
        return {"ok": True, "result": discovery.footprint(Path(root))}

    # ---- usage / adoption ----
    @app.get("/api/usage")
    def usage(since: str | None = None):
        roots = discovery.discover_roots()
        return {"ok": True, "result": telemetry.summarize_all(roots, since=since)}

    @app.get("/api/adoption")
    def adoption(since: str | None = None):
        return {"ok": True, "result": hub._op_adoption({"since": since})}

    # ---- hub / health ----
    @app.get("/api/hub")
    def hub_info():
        return {"ok": True, "result": hub._op_hub_info({})}

    @app.get("/api/health")
    def health():
        return {"ok": True, "result": {"health": hub.watchdog.health()}}

    @app.post("/api/watchdog")
    async def set_watchdog(payload: dict):
        hub.watchdog.set_policy(Path(payload["root"]), payload["policy"])
        return {"ok": True, "result": {"policy": payload["policy"]}}

    @app.post("/api/restart")
    async def restart(payload: dict):
        ok = hub.watchdog._restart(Path(payload["root"]))
        return {"ok": True, "result": {"restarted": ok}}

    @app.post("/api/daemon")
    async def daemon_ctl(payload: dict):
        """Start/stop a per-project daemon."""
        root = Path(payload["root"])
        action = payload.get("action")
        try:
            if action == "stop":
                daemon_mod.stop_daemon(root)
            else:
                daemon_mod.spawn_daemon(root)
            return {"ok": True, "result": {"up": daemon_mod.ping(root)}}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # ---- graph / reads ----
    @app.get("/api/context")
    def context(root: str, ref: str, degree: int = 0):
        bundle = replica_context(Path(root), ref, degree=degree)
        if bundle.get("error"):
            return {"ok": False, "error": bundle["error"]}
        return {"ok": True, "result": bundle}

    # ---- graph landing views ----
    @app.get("/api/top")
    def top(root: str, n: int = 30, exclude_ns: str = "keyword,kind,import"):
        """Density-ranked concept entry points for the Graph landing view.
        Excludes category/import namespaces by default so the entries are
        clickable symbols, not buckets like `kind/function`."""
        ns = [x for x in exclude_ns.split(",") if x]
        return _daemon_read(Path(root), "top_concepts",
                            {"n": n, "partition": _partition(Path(root)),
                             "exclude_ns": ns})

    @app.get("/api/tree")
    def tree(root: str, max_entries: int = 800):
        """Project file tree (code/doc files) for the Graph directory view.
        Walks the project root (parent of .refmatrix); skips hidden + heavy
        dirs. Returns a flat list of {path, rel, dir, depth} the client nests."""
        rootp = Path(root)
        base = rootp.parent
        SKIP = {".git", ".refmatrix", "node_modules", "__pycache__", ".venv",
                ".venv-eval", "dist", "build", ".tldr", "vectors"}
        KEEP = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
                ".c", ".cpp", ".h", ".md", ".gmd", ".rst", ".txt"}
        entries: list[dict] = []
        import os as _os
        for dirpath, dirnames, filenames in _os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP
                           and not d.startswith(".")]
            rel_dir = _os.path.relpath(dirpath, base)
            depth = 0 if rel_dir == "." else rel_dir.count(_os.sep) + 1
            for fn in sorted(filenames):
                if Path(fn).suffix not in KEEP:
                    continue
                rel = fn if rel_dir == "." else _os.path.join(rel_dir, fn)
                entries.append({"rel": rel, "name": fn, "depth": depth,
                                "dir": rel_dir if rel_dir != "." else ""})
                if len(entries) >= max_entries:
                    return {"ok": True, "result": {"base": str(base),
                            "entries": entries, "truncated": True}}
        entries.sort(key=lambda e: e["rel"])
        return {"ok": True, "result": {"base": str(base), "entries": entries,
                "truncated": False}}

    @app.get("/api/graph")
    def graph(root: str, seed: str, degree: int = 0):
        bundle = replica_context(Path(root), seed, degree=degree)
        if bundle.get("error"):
            return {"ok": False, "error": bundle["error"]}
        return {"ok": True, "result": _context_to_graph(bundle)}

    @app.post("/api/query")
    async def query(payload: dict):
        root = Path(payload["root"])
        body = payload.get("dsl") or payload.get("pql") or ""
        is_pql = bool(payload.get("pql"))
        # the daemon query op takes `expr` (+ pql flag), not `dsl`/`pql` keys
        return _daemon_read(root, "query", {
            "expr": body, "pql": is_pql, "partition": _partition(root),
        })

    @app.get("/api/memory")
    def memory(root: str, q: str = "", tag: str | None = None,
               mtype: str | None = None, limit: int = 30):
        rootp = Path(root)
        tags = [tag] if tag else None
        if q:
            args: dict[str, Any] = {"query": q, "limit": limit, "tags": tags,
                                    "partition": _partition(rootp)}
            return _daemon_read(rootp, "memory_search", args)
        args = {"mtype": mtype, "limit": limit, "tags": tags,
                "partition": _partition(rootp)}
        return _daemon_read(rootp, "memory_iter", args)

    @app.get("/api/taxonomy")
    def taxonomy_get():
        from refmatrix import taxonomy as tax
        return {"ok": True, "result": tax.load()}

    # ---- "where are my keys?" — federated retrieval (shared engine) ----
    @app.get("/api/where")
    def where(q: str, limit: int = 40):
        from refmatrix.search import federated_where
        return {"ok": True, "result": federated_where(q, limit=limit)}

    @app.get("/api/search")
    def search(dsl: str, limit: int = 50):
        from refmatrix.search import federated_query
        return {"ok": True, "result": federated_query(dsl, limit=limit)}

    @app.get("/api/canon")
    def canon(concept: str):
        from refmatrix.search import federated_concept
        return {"ok": True, "result": federated_concept(concept)}

    @app.get("/api/schedule")
    def schedule_get():
        from refmatrix import scheduler as sch
        return {"ok": True, "result": {"schedule": sch.load_schedule()}}

    @app.post("/api/schedule")
    async def schedule_set(payload: dict):
        from refmatrix import scheduler as sch
        root = Path(payload["root"])
        if payload.get("remove"):
            sch.remove_job(root, payload["op"])
        else:
            sch.add_job(root, payload["op"], int(payload["interval_s"]))
        return {"ok": True, "result": {"schedule": sch.load_schedule()}}

    # ---- bus + refinement ----
    @app.get("/api/bus/channels")
    def bus_channels():
        return {"ok": True, "result": {"channels": hub.bus.channels()}}

    @app.get("/api/bus/history")
    def bus_history(channel: str, n: int = 50):
        return {"ok": True, "result": {"messages": hub.bus.history(channel, n)}}

    @app.post("/api/bus/pub")
    async def bus_pub(payload: dict):
        msg = hub.bus.publish(
            payload["channel"], payload.get("body"),
            sender=payload.get("from", "ui"), project=payload.get("project"),
            mtype=payload.get("type", "announce"))
        return {"ok": True, "result": {"message": msg}}

    @app.get("/api/refine")
    def refine_list(status: str = "pending"):
        return {"ok": True, "result": {"candidates": hub.bus.refinement_queue(status)}}

    @app.post("/api/refine/accept")
    async def refine_accept(payload: dict):
        return hub.bus.accept_refinement(payload["id"])

    @app.post("/api/refine/reject")
    async def refine_reject(payload: dict):
        return hub.bus.reject_refinement(payload["id"])

    @app.get("/api/queues")
    def queues():
        return {"ok": True, "result": hub._op_queues({})}

    # ---- short-term focus ----
    @app.get("/api/focus")
    def focus(root: str, session: str = "default", top: int = 30):
        return {"ok": True, "result": hub._op_focus(
            {"root": root, "session": session, "top": top})}

    @app.get("/api/focus/sessions")
    def focus_sessions(root: str):
        return {"ok": True, "result": hub._op_focus_sessions({"root": root})}

    @app.websocket("/ws/bus")
    async def ws_bus(ws: WebSocket):
        await ws.accept()
        try:
            req = json.loads(await ws.receive_text())
        except Exception:
            await ws.close()
            return
        patterns = req.get("channels") or ["*"]
        if isinstance(patterns, str):
            patterns = [patterns]
        sub = hub.bus.subscribe(patterns)
        try:
            loop = asyncio.get_event_loop()
            while True:
                msg = await loop.run_in_executor(None, _drain, sub)
                if msg is None:
                    # keepalive / liveness probe
                    await ws.send_json({"keepalive": True})
                    continue
                await ws.send_json(msg)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.bus.unsubscribe(sub)
            try:
                await ws.close()
            except Exception:
                pass

    # ---- streamed ops ----
    @app.websocket("/ws/op")
    async def ws_op(ws: WebSocket):
        """Run `rmx <op>` in a project root and stream stdout line-by-line.
        Client sends {root, op, args:[...]} once; server streams {line} then
        {done, code}."""
        await ws.accept()
        try:
            req = json.loads(await ws.receive_text())
        except Exception:
            await ws.close()
            return
        root = Path(req["root"])
        op = req["op"]
        extra = req.get("args") or []
        allowed = {"ingest", "embed", "sync", "vacuum", "checkpoint", "reingest"}
        if op not in allowed:
            await ws.send_json({"error": f"op not allowed: {op}"})
            await ws.close()
            return
        import os
        import sys
        cmd = [sys.executable, "-m", "refmatrix.cli", op, *map(str, extra)]
        env = {**os.environ, "REFMATRIX_ROOT": str(root),
               "RMX_INVOCATION_SOURCE": "internal"}
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(root.parent),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                await ws.send_json({"line": raw.decode(errors="replace").rstrip()})
            code = await proc.wait()
            await ws.send_json({"done": True, "code": code})
        except WebSocketDisconnect:
            proc.kill()
        finally:
            if proc.returncode is None:
                proc.kill()
            try:
                await ws.close()
            except Exception:
                pass

    @app.websocket("/ws/logs")
    async def ws_logs(ws: WebSocket):
        """Tail a project's rmxd.log (or the hub log) live."""
        await ws.accept()
        try:
            req = json.loads(await ws.receive_text())
        except Exception:
            await ws.close()
            return
        root = req.get("root")
        from refmatrix.hub import hub_log_path
        path = (Path(root) / "rmxd.log") if root and root != "hub" else hub_log_path()
        try:
            with path.open() as f:
                f.seek(0, 2)  # tail
                while True:
                    line = f.readline()
                    if line:
                        await ws.send_json({"line": line.rstrip()})
                    else:
                        await asyncio.sleep(0.5)
        except (WebSocketDisconnect, FileNotFoundError, OSError):
            pass
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    # ---- static SPA ----
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index():
            idx = STATIC_DIR / "index.html"
            if idx.exists():
                return FileResponse(str(idx))
            return JSONResponse({"error": "UI not built"}, status_code=404)

    return app
