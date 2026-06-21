"""Short-term (working) memory — a per-project, isolated focus graph.

STM is two things, both under `<root>/stm/`:

  * an append-only **event ring** (`<session>.jsonl`) — raw provenance of what
    happened (input / tool / rmx / result), trimmed to a soft cap; and
  * a maintained **focus graph** (`<session>.focus.json`) — node-addressable,
    score-evicted, decayed. This is "an rmx of what I'm working on right now."

The focus graph is NOT a flat ring. Nodes are addressable by a stable key (the
ref name), refreshed in place (never duplicated). Each turn applies recency
decay; admission is gated + capped so one noisy turn can't churn the whole
graph; eviction is by a composite score (recency · frequency · graph centrality
· pin) so structurally-central hubs survive. Evicting a node that still has a
live neighbor leaves a cheap **frontier stub** — a breadcrumb to rehydrate from
long-term memory.

Per-project + file-based by design: project A's focus never bleeds into B, and
STM works whether or not the hub/daemon is running.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

# Event ring (raw provenance).
RING_SIZE = int(os.environ.get("RMX_STM_SIZE", "500"))
# Focus-graph node budget (scored eviction kicks in above this).
NODE_BUDGET = int(os.environ.get("RMX_STM_NODES", "200"))
# Cap on how many nodes one turn may admit (anti-churn).
MAX_ADMIT_PER_TURN = int(os.environ.get("RMX_STM_ADMIT", "12"))
# Per-turn recency decay factor.
DECAY = float(os.environ.get("RMX_STM_DECAY", "0.85"))
# Frontier stubs are cheap but bounded.
FRONTIER_BUDGET = max(8, NODE_BUDGET // 2)
COOCCUR_WINDOW = 4

# Score weights. Pin dominates so a pinned node is never evicted ahead of junk.
W_RECENCY, W_FREQ, W_CENTRALITY, W_PIN = 1.0, 0.5, 0.8, 10.0

EVENT_KINDS = ("input", "tool", "rmx", "result")

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}(?:\.[A-Za-z_][A-Za-z0-9_]+)*")
_PATH_RE = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}")
_STOP = {"the", "and", "for", "this", "that", "with", "from", "into", "rmx",
         "true", "false", "none", "null", "self", "args", "kwargs"}


def stm_dir(root: Path) -> Path:
    return Path(root) / "stm"


def session_id() -> str:
    return os.environ.get("RMX_SESSION") or "default"


def latest_session(root: Path) -> str | None:
    """The session id whose event ring was written most recently, or None if
    no STM exists yet. Lets read surfaces (`focus tail/context`, save-state)
    default to the active Claude session instead of the bare "default" ring —
    the hook keys STM by the Claude `session_id`, which a plain shell does not
    have in `$RMX_SESSION`."""
    d = stm_dir(root)
    if not d.is_dir():
        return None
    newest: tuple[float, str] | None = None
    for p in d.glob("*.jsonl"):
        if p.name.endswith(".tmp"):
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest[0]:
            newest = (mtime, p.stem)
    return newest[1] if newest else None


def _safe(session: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", session) or "default"


def _edge_key(a: str, b: str) -> str:
    return "\x00".join(sorted((a, b)))


class Stm:
    """File-backed short-term memory for one (root, session)."""

    def __init__(self, root: Path, session: str | None = None,
                 size: int = RING_SIZE, node_budget: int = NODE_BUDGET):
        self.root = Path(root)
        self.session = session or session_id()
        self.size = size
        self.node_budget = node_budget
        self._dir = stm_dir(self.root)
        self._path = self._dir / f"{_safe(self.session)}.jsonl"
        self._graph_path = self._dir / f"{_safe(self.session)}.focus.json"
        self._tasks_path = self._dir / f"{_safe(self.session)}.tasks.json"

    # ---- event ring (provenance) ----
    def record(self, kind: str, terse: str, *, refs: list[str] | None = None) -> dict:
        if kind not in EVENT_KINDS:
            kind = "tool"
        rlist = refs if refs is not None else _extract_refs(terse)
        ev = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session": self.session,
            "kind": kind,
            "terse": terse[:500],
            "refs": rlist,
            "task": self.current_task_desc(),
        }
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        self._trim_ring()
        # Maintain the focus graph. An `input` event opens a new turn (decay).
        self._ingest_into_graph(rlist, new_turn=(kind == "input"))
        return ev

    def _trim_ring(self) -> None:
        try:
            lines = self._path.read_text().splitlines()
        except OSError:
            return
        if len(lines) <= self.size + 64:
            return
        keep = lines[-self.size:]
        tmp = self._path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(keep) + "\n")
        tmp.replace(self._path)

    def tail(self, n: int = 50) -> list[dict]:
        if not self._path.exists():
            return []
        out = []
        for ln in self._path.read_text().splitlines()[-n:]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
        return out

    def all_events(self) -> list[dict]:
        return self.tail(self.size)

    def clear(self) -> None:
        for p in (self._path, self._graph_path, self._tasks_path):
            try:
                p.unlink()
            except OSError:
                pass

    # ---- focus graph (maintained, scored) ----
    def _load_graph(self) -> dict:
        if not self._graph_path.exists():
            return {"turn": 0, "nodes": {}, "edges": {}}
        try:
            g = json.loads(self._graph_path.read_text())
            g.setdefault("turn", 0); g.setdefault("nodes", {}); g.setdefault("edges", {})
            return g
        except (json.JSONDecodeError, OSError):
            return {"turn": 0, "nodes": {}, "edges": {}}

    def _save_graph(self, g: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._graph_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(g))
        tmp.replace(self._graph_path)

    def _ingest_into_graph(self, refs: list[str], *, new_turn: bool) -> None:
        if not refs and not new_turn:
            return
        g = self._load_graph()
        if new_turn:
            g["turn"] += 1
            for nd in g["nodes"].values():
                if not nd.get("frontier"):
                    nd["recency"] *= DECAY  # staleness falls out of scoring
        turn = g["turn"]
        admitted = self._admit(g, refs[:MAX_ADMIT_PER_TURN], turn)
        # co-occurrence edges among admitted refs (in-place weight bump)
        for i in range(len(admitted)):
            for j in range(i + 1, len(admitted)):
                k = _edge_key(admitted[i], admitted[j])
                g["edges"][k] = g["edges"].get(k, 0.0) + 1.0
        self._evict(g)
        self._save_graph(g)

    def _admit(self, g: dict, refs: list[str], turn: int) -> list[str]:
        """Create/refresh nodes in place (stable key = ref name). Rehydrates a
        frontier stub on re-touch. Returns the admitted names."""
        out = []
        for name in refs:
            if not name:
                continue
            nd = g["nodes"].get(name)
            if nd is None:
                g["nodes"][name] = {
                    "name": name, "kind": _ref_kind(name),
                    "recency": 1.0, "freq": 1, "pin": 0, "frontier": False,
                    "first_turn": turn, "last_turn": turn,
                    "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            else:
                nd["recency"] = 1.0          # touch resets recency
                nd["freq"] = nd.get("freq", 0) + 1
                nd["frontier"] = False       # rehydrate stub
                nd["last_turn"] = turn
                nd["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            out.append(name)
        return out

    def _degree(self, g: dict) -> dict[str, int]:
        deg: dict[str, int] = {}
        for k in g["edges"]:
            a, b = k.split("\x00")
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
        return deg

    def _score(self, nd: dict, maxfreq: int, deg: dict, maxdeg: int) -> float:
        freq = (nd.get("freq", 0) / maxfreq) if maxfreq else 0.0
        cen = (deg.get(nd["name"], 0) / maxdeg) if maxdeg else 0.0
        return (W_RECENCY * nd.get("recency", 0.0) + W_FREQ * freq
                + W_CENTRALITY * cen + W_PIN * nd.get("pin", 0))

    def _evict(self, g: dict) -> None:
        nodes = g["nodes"]
        real = [n for n, nd in nodes.items() if not nd.get("frontier")]
        if len(real) <= self.node_budget:
            self._evict_frontier(g)
            return
        deg = self._degree(g)
        maxdeg = max(deg.values()) if deg else 1
        while len(real) > self.node_budget:
            maxfreq = max((nodes[n].get("freq", 0) for n in real), default=1) or 1
            cand = [n for n in real if not nodes[n].get("pin")]
            if not cand:
                break  # everything pinned
            victim = min(cand, key=lambda n: self._score(nodes[n], maxfreq, deg, maxdeg))
            # surviving real neighbor? → leave a frontier breadcrumb, else delete
            has_live_neighbor = any(
                (other in nodes and not nodes[other].get("frontier") and other != victim)
                for other in _neighbors(g, victim)
            )
            if has_live_neighbor:
                nodes[victim]["frontier"] = True
                nodes[victim]["recency"] = 0.0
            else:
                _drop_node(g, victim)
            real = [n for n, nd in nodes.items() if not nd.get("frontier")]
            deg = self._degree(g)
            maxdeg = max(deg.values()) if deg else 1
        self._evict_frontier(g)

    def _evict_frontier(self, g: dict) -> None:
        nodes = g["nodes"]
        front = [n for n, nd in nodes.items() if nd.get("frontier")]
        if len(front) <= FRONTIER_BUDGET:
            return
        front.sort(key=lambda n: nodes[n].get("last_turn", 0))  # oldest first
        for victim in front[: len(front) - FRONTIER_BUDGET]:
            _drop_node(g, victim)

    def focus_graph(self, *, top: int = 30, include_frontier: bool = False) -> dict:
        """Ranked snapshot of the maintained focus graph (best-scoring first)."""
        g = self._load_graph()
        nodes = g["nodes"]
        deg = self._degree(g)
        maxdeg = max(deg.values()) if deg else 1
        real = [nd for nd in nodes.values() if not nd.get("frontier")]
        maxfreq = max((nd.get("freq", 0) for nd in real), default=1) or 1
        scored = sorted(
            real, key=lambda nd: self._score(nd, maxfreq, deg, maxdeg), reverse=True)
        keep = set(n["name"] for n in scored[:top])
        out_nodes = [{
            "name": nd["name"], "kind": nd["kind"],
            "weight": round(self._score(nd, maxfreq, deg, maxdeg), 3),
            "recency": round(nd.get("recency", 0), 3),
            "count": nd.get("freq", 0), "degree": deg.get(nd["name"], 0),
            "pin": nd.get("pin", 0), "last": nd.get("updated"),
        } for nd in scored[:top]]
        if include_frontier:
            for nd in nodes.values():
                if nd.get("frontier") and nd["name"] in {
                        x for e in g["edges"] for x in e.split("\x00") if x in keep}:
                    out_nodes.append({"name": nd["name"], "kind": nd["kind"],
                                      "weight": 0, "frontier": True})
                    keep.add(nd["name"])
        edges = []
        for k, w in g["edges"].items():
            a, b = k.split("\x00")
            if a in keep and b in keep:
                edges.append({"source": a, "target": b, "weight": round(w, 2)})
        return {"session": self.session, "turn": g.get("turn", 0),
                "events": len(self.all_events()), "nodes": out_nodes,
                "edges": edges, "focus": [n["name"] for n in out_nodes if not n.get("frontier")]}

    def pin(self, name: str, value: bool = True) -> bool:
        g = self._load_graph()
        nd = g["nodes"].get(name)
        if nd is None:
            return False
        nd["pin"] = 1 if value else 0
        if value:
            nd["frontier"] = False
        self._save_graph(g)
        return True

    # ---- task pushdown stack ----
    def _load_tasks(self) -> list[dict]:
        if not self._tasks_path.exists():
            return []
        try:
            return json.loads(self._tasks_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _save_tasks(self, stack: list[dict]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._tasks_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(stack, indent=2))
        tmp.replace(self._tasks_path)

    def current_task_desc(self) -> str | None:
        stack = self._load_tasks()
        return stack[-1]["desc"] if stack else None

    def task_push(self, desc: str) -> dict:
        stack = self._load_tasks()
        snap = self.focus_graph(top=12)["focus"]
        stack.append({"desc": desc, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "focus_snapshot": snap})
        self._save_tasks(stack)
        return {"depth": len(stack), "current": desc}

    def task_pop(self) -> dict:
        stack = self._load_tasks()
        if not stack:
            return {"popped": None, "depth": 0, "restored": None, "restored_focus": []}
        popped = stack.pop()
        self._save_tasks(stack)
        restored = stack[-1] if stack else None
        # Re-touch the restored task's focus so popping back actually re-warms it.
        if restored:
            self._ingest_into_graph(list(restored.get("focus_snapshot") or []),
                                    new_turn=False)
        return {"popped": popped["desc"], "depth": len(stack),
                "restored": restored["desc"] if restored else None,
                "restored_focus": restored["focus_snapshot"] if restored else []}

    def task_list(self) -> list[dict]:
        return self._load_tasks()

    def task_current(self) -> dict | None:
        stack = self._load_tasks()
        return stack[-1] if stack else None

    def task_swap(self) -> dict:
        stack = self._load_tasks()
        if len(stack) < 2:
            return {"swapped": False, "current": self.current_task_desc()}
        stack[-1], stack[-2] = stack[-2], stack[-1]
        self._save_tasks(stack)
        return {"swapped": True, "current": stack[-1]["desc"]}


def _neighbors(g: dict, name: str) -> list[str]:
    out = []
    for k in g["edges"]:
        a, b = k.split("\x00")
        if a == name:
            out.append(b)
        elif b == name:
            out.append(a)
    return out


def _drop_node(g: dict, name: str) -> None:
    g["nodes"].pop(name, None)
    for k in [k for k in g["edges"] if name in k.split("\x00")]:
        del g["edges"][k]


def _ref_kind(ref: str) -> str:
    if "/" in ref or re.search(r"\.[A-Za-z]{1,5}$", ref):
        return "code" if re.search(r"\.(py|js|ts|go|rs|java|c|cpp|h)$", ref) else "doc"
    return "concept"


def _extract_refs(text: str) -> list[str]:
    refs: list[str] = []
    for m in _PATH_RE.findall(text):
        if "/" in m or "." in m:
            refs.append(m)
    for m in _IDENT_RE.findall(text):
        if m.lower() not in _STOP and not m.isdigit():
            refs.append(m)
    seen: dict[str, None] = {}
    for r in refs:
        seen.setdefault(r, None)
    return list(seen)[:12]
