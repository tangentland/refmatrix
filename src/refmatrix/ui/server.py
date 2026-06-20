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
        return _daemon_read(Path(root), "context", {
            "ref": ref, "format": "json", "degree": degree,
            "entities_explicit": False, "tokens_explicit": False,
            "partition": _partition(Path(root)),
        }, timeout=120.0)

    @app.get("/api/graph")
    def graph(root: str, seed: str, degree: int = 0):
        resp = _daemon_read(Path(root), "context", {
            "ref": seed, "format": "json", "degree": degree,
            "entities_explicit": False, "tokens_explicit": False,
            "partition": _partition(Path(root)),
        }, timeout=120.0)
        if not resp.get("ok"):
            return resp
        return {"ok": True, "result": _context_to_graph(resp["result"])}

    @app.post("/api/query")
    async def query(payload: dict):
        root = Path(payload["root"])
        body = payload.get("dsl") or payload.get("pql") or ""
        mode = "pql" if payload.get("pql") else "dsl"
        return _daemon_read(root, "query", {
            mode: body, "partition": _partition(root),
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

    # ---- "where are my keys?" — federated retrieval ----
    @app.get("/api/where")
    def where(q: str, limit: int = 40):
        """Fan a query across every live store: code/doc/concept hits from
        context + memory hits. Merge-ranked-ish (grouped by source)."""
        results: list[dict] = []
        for root in discovery.discover_roots():
            if not daemon_mod.ping(root):
                continue
            proj = discovery.store_name(root)
            try:
                ctx = daemon_mod.call(root, "context", {
                    "ref": q, "format": "json", "degree": 0,
                    "entities_explicit": False, "tokens_explicit": False,
                    "partition": proj,
                }, timeout=20.0)
                if ctx.get("ok"):
                    b = ctx["result"]
                    anchor = b.get("anchor")
                    if anchor:
                        results.append({
                            "source": anchor.get("kind", "concept"),
                            "project": proj, "root": str(root),
                            "name": anchor["name"], "kind": anchor.get("kind", "concept"),
                            "path": anchor.get("path"), "line": None,
                        })
                    for entries in (b.get("groups") or {}).values():
                        for e in entries[:6]:
                            results.append({
                                "source": e.get("kind", "concept"),
                                "project": proj, "root": str(root),
                                "name": e["name"], "kind": e.get("kind", "concept"),
                                "path": e.get("path"), "line": e.get("line"),
                                "snippet": e.get("snippet"),
                            })
            except Exception:
                pass
            try:
                mem = daemon_mod.call(root, "memory_search", {
                    "query": q, "limit": 4, "partition": proj,
                }, timeout=10.0)
                if mem.get("ok"):
                    for m in mem["result"].get("rows", []):
                        results.append({
                            "source": "memory", "project": proj, "root": str(root),
                            "name": m["name"], "kind": "memory", "path": None,
                            "snippet": (m.get("content") or "")[:120],
                        })
            except Exception:
                pass
        # de-dup by (kind,name,project); cap.
        seen = set(); deduped = []
        for r in results:
            k = (r["kind"], r["name"], r["project"])
            if k in seen:
                continue
            seen.add(k); deduped.append(r)
        return {"ok": True, "result": {"results": deduped[:limit]}}

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
