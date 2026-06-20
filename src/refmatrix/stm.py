"""Short-term (working) memory — a per-project, isolated focus layer.

STM is a fixed-size ring of terse events (user input, tool use, rmx calls,
results) persisted under `<root>/stm/<session>.jsonl`. From the ring we compute,
on demand, a recency-weighted *focus graph* — "an rmx of what I'm working on
right now" — without paying a DuckDB write per event. A per-session pushdown
**task stack** frames the focus: pushing a task snapshots the current focus;
popping restores it, so returning from a tangent re-surfaces prior context.

Per-project + file-based by design: project A's focus never bleeds into B, and
STM works whether or not the hub/daemon is running.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_SIZE = int(os.environ.get("RMX_STM_SIZE", "500"))
EVENT_KINDS = ("input", "tool", "rmx", "result")
# Co-occurrence window: refs within this many adjacent events are linked.
COOCCUR_WINDOW = 4

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}(?:\.[A-Za-z_][A-Za-z0-9_]+)*")
_PATH_RE = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}")
_STOP = {"the", "and", "for", "this", "that", "with", "from", "into", "rmx",
         "true", "false", "none", "null", "self", "args", "kwargs"}


def stm_dir(root: Path) -> Path:
    return Path(root) / "stm"


def session_id() -> str:
    return os.environ.get("RMX_SESSION") or "default"


def _safe(session: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", session) or "default"


class Stm:
    """File-backed short-term memory for one (root, session)."""

    def __init__(self, root: Path, session: str | None = None,
                 size: int = DEFAULT_SIZE):
        self.root = Path(root)
        self.session = session or session_id()
        self.size = size
        self._dir = stm_dir(self.root)
        self._path = self._dir / f"{_safe(self.session)}.jsonl"
        self._tasks_path = self._dir / f"{_safe(self.session)}.tasks.json"

    # ---- ring ----
    def record(self, kind: str, terse: str, *, refs: list[str] | None = None) -> dict:
        if kind not in EVENT_KINDS:
            kind = "tool"
        ev = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session": self.session,
            "kind": kind,
            "terse": terse[:500],
            "refs": refs if refs is not None else _extract_refs(terse),
            "task": self.current_task_desc(),
        }
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        self._trim()
        return ev

    def _trim(self) -> None:
        """Keep only the last `size` events. Cheap: only rewrites when over by
        a margin so we don't rewrite on every append."""
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
        for p in (self._path, self._tasks_path):
            try:
                p.unlink()
            except OSError:
                pass

    # ---- focus graph (computed from the ring) ----
    def focus_graph(self, *, window: int | None = None, top: int = 30) -> dict:
        """Recency-weighted co-occurrence graph over the ring's refs. Newest
        events weigh most. Returns {nodes:[{name,kind,weight,count,last}],
        edges:[{source,target,weight}], focus:[name…ranked]}."""
        events = self.all_events()
        if window:
            events = events[-window:]
        n = len(events)
        weight: dict[str, float] = defaultdict(float)
        count: Counter[str] = Counter()
        last: dict[str, str] = {}
        kind_of: dict[str, str] = {}
        for i, ev in enumerate(events):
            # linear recency: oldest≈0.2, newest=1.0
            rec = 0.2 + 0.8 * ((i + 1) / n) if n else 1.0
            for ref in ev.get("refs") or []:
                weight[ref] += rec
                count[ref] += 1
                last[ref] = ev["ts"]
                kind_of[ref] = _ref_kind(ref)
        # co-occurrence edges within a sliding window
        edge_w: dict[tuple[str, str], float] = defaultdict(float)
        win = COOCCUR_WINDOW
        for i in range(n):
            bucket: list[str] = []
            for j in range(max(0, i - win + 1), i + 1):
                bucket += (events[j].get("refs") or [])
            uniq = list(dict.fromkeys(bucket))
            rec = 0.2 + 0.8 * ((i + 1) / n) if n else 1.0
            for a_i in range(len(uniq)):
                for b_i in range(a_i + 1, len(uniq)):
                    a, b = sorted((uniq[a_i], uniq[b_i]))
                    edge_w[(a, b)] += rec
        ranked = [r for r, _ in sorted(weight.items(), key=lambda kv: kv[1], reverse=True)]
        keep = set(ranked[:top])
        nodes = [{"name": r, "kind": kind_of.get(r, "concept"),
                  "weight": round(weight[r], 2), "count": count[r], "last": last[r]}
                 for r in ranked[:top]]
        edges = [{"source": a, "target": b, "weight": round(w, 2)}
                 for (a, b), w in edge_w.items()
                 if a in keep and b in keep and w > 0.4]
        return {"session": self.session, "events": n, "nodes": nodes,
                "edges": edges, "focus": ranked[:top]}

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
        """Push a task, snapshotting the current focus so a later pop can
        restore the context you were in."""
        stack = self._load_tasks()
        snap = self.focus_graph(top=12)["focus"]
        entry = {"desc": desc, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "focus_snapshot": snap}
        stack.append(entry)
        self._save_tasks(stack)
        return {"depth": len(stack), "current": desc}

    def task_pop(self) -> dict:
        stack = self._load_tasks()
        if not stack:
            return {"popped": None, "depth": 0, "restored": None}
        popped = stack.pop()
        self._save_tasks(stack)
        restored = stack[-1] if stack else None
        return {"popped": popped["desc"], "depth": len(stack),
                "restored": restored["desc"] if restored else None,
                "restored_focus": restored["focus_snapshot"] if restored else []}

    def task_list(self) -> list[dict]:
        return self._load_tasks()

    def task_current(self) -> dict | None:
        stack = self._load_tasks()
        return stack[-1] if stack else None

    def task_swap(self) -> dict:
        """Swap the top two tasks (jump back to the prior tangent)."""
        stack = self._load_tasks()
        if len(stack) < 2:
            return {"swapped": False, "current": self.current_task_desc()}
        stack[-1], stack[-2] = stack[-2], stack[-1]
        self._save_tasks(stack)
        return {"swapped": True, "current": stack[-1]["desc"]}


def _ref_kind(ref: str) -> str:
    if "/" in ref or re.search(r"\.[A-Za-z]{1,5}$", ref):
        return "code" if re.search(r"\.(py|js|ts|go|rs|java|c|cpp|h)$", ref) else "doc"
    return "concept"


def _extract_refs(text: str) -> list[str]:
    """Best-effort ref extraction when a caller doesn't supply refs: file
    paths + dotted identifiers, minus stopwords. Deduped, capped."""
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
