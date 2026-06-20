"""Hub-hosted agent message bus + refinement queue.

Pub/sub so live agents coordinate in real time — intra-project
(`proj:<name>:<topic>`) and inter-project (`global:<topic>`). Every message is
fanned out to in-memory subscribers and appended to a per-channel JSONL so late
joiners can replay backlog. Durable, high-signal messages (`announce` /
`decision`) are enqueued — NOT silently written — into a refinement queue an
agent/human approves to promote into memory.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from refmatrix.taxonomy import user_home

PROMOTE_TYPES = ("announce", "decision")


def bus_dir() -> Path:
    return user_home() / "bus"


def refine_path() -> Path:
    return user_home() / "refine" / "queue.jsonl"


def _safe_channel(channel: str) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "_", channel)


def _matches(pattern: str, channel: str) -> bool:
    if pattern in ("*", ""):
        return True
    if pattern.endswith("*"):
        return channel.startswith(pattern[:-1])
    if pattern.endswith(":"):
        return channel.startswith(pattern)
    return channel == pattern


class _Subscriber:
    def __init__(self, patterns: list[str]):
        self.patterns = patterns
        self.q: "queue.Queue[dict]" = queue.Queue(maxsize=1000)

    def wants(self, channel: str) -> bool:
        return any(_matches(p, channel) for p in self.patterns)


class Bus:
    def __init__(self):
        self._subs: list[_Subscriber] = []
        self._lock = threading.Lock()

    # ---- pub/sub ----
    def publish(self, channel: str, body: Any, *, sender: str = "?",
                project: str | None = None, mtype: str = "announce",
                reply_to: str | None = None) -> dict:
        msg = {
            "id": uuid.uuid4().hex[:12],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "channel": channel,
            "from": sender,
            "project": project,
            "type": mtype,
            "body": body,
            "reply_to": reply_to,
        }
        self._persist(channel, msg)
        with self._lock:
            subs = [s for s in self._subs if s.wants(channel)]
        for s in subs:
            try:
                s.q.put_nowait(msg)
            except queue.Full:
                pass
        if mtype in PROMOTE_TYPES:
            try:
                self._enqueue_refinement(msg)
            except OSError:
                pass
        return msg

    def subscribe(self, patterns: list[str]) -> _Subscriber:
        sub = _Subscriber(patterns)
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    # ---- persistence / history ----
    def _persist(self, channel: str, msg: dict) -> None:
        try:
            bus_dir().mkdir(parents=True, exist_ok=True)
            p = bus_dir() / f"{_safe_channel(channel)}.jsonl"
            with p.open("a") as f:
                f.write(json.dumps(msg) + "\n")
        except OSError:
            pass

    def history(self, channel: str, n: int = 50) -> list[dict]:
        p = bus_dir() / f"{_safe_channel(channel)}.jsonl"
        if not p.exists():
            return []
        lines = p.read_text().splitlines()[-n:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
        return out

    def channels(self) -> list[dict]:
        d = bus_dir()
        if not d.is_dir():
            return []
        out = []
        for p in sorted(d.glob("*.jsonl")):
            try:
                count = sum(1 for _ in p.open())
            except OSError:
                count = 0
            out.append({"channel": p.stem, "messages": count})
        return out

    # ---- refinement queue (no silent writes) ----
    def _enqueue_refinement(self, msg: dict) -> dict:
        """Turn a high-signal message into a *candidate* memory awaiting
        approval. Channel decides scope: global:* -> global store,
        proj:<name>:* -> that project."""
        scope = "global" if str(msg["channel"]).startswith("global:") else "project"
        tags = ["behavior"] if scope == "global" else []
        cand = {
            "id": msg["id"],
            "ts": msg["ts"],
            "origin": "bus",
            "scope": scope,
            "channel": msg["channel"],
            "project": msg.get("project"),
            "status": "pending",
            "suggested": {
                "name": f"{msg['type']}-{msg['id']}",
                "content": str(msg["body"]),
                "mtype": "feedback" if msg["type"] == "decision" else "observation",
                "tags": tags,
            },
        }
        p = refine_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(cand) + "\n")
        return cand

    def refinement_queue(self, status: str = "pending") -> list[dict]:
        p = refine_path()
        if not p.exists():
            return []
        out = []
        for ln in p.read_text().splitlines():
            try:
                c = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if status == "all" or c.get("status") == status:
                out.append(c)
        return out

    def _rewrite_refinement(self, items: list[dict]) -> None:
        p = refine_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(c) + "\n" for c in items))
        tmp.replace(p)

    def accept_refinement(self, cand_id: str) -> dict:
        """Promote a pending candidate into a memory (global or project store)
        and mark it accepted. Returns {ok, memory_id?} or {ok:False,error}."""
        items = self.refinement_queue(status="all")
        target = next((c for c in items if c["id"] == cand_id), None)
        if target is None:
            return {"ok": False, "error": "candidate not found"}
        if target["status"] != "pending":
            return {"ok": False, "error": f"already {target['status']}"}
        sug = target["suggested"]
        eid = self._write_memory(target, sug)
        target["status"] = "accepted"
        target["memory_id"] = eid
        self._rewrite_refinement(items)
        return {"ok": True, "memory_id": eid}

    def reject_refinement(self, cand_id: str) -> dict:
        items = self.refinement_queue(status="all")
        target = next((c for c in items if c["id"] == cand_id), None)
        if target is None:
            return {"ok": False, "error": "candidate not found"}
        target["status"] = "rejected"
        self._rewrite_refinement(items)
        return {"ok": True}

    def _write_memory(self, cand: dict, sug: dict) -> int:
        """Promote a candidate to a memory — routed through the owning daemon
        (single writer), never a direct Store() open. See the
        store-calls-via-daemon rule."""
        from refmatrix import daemon as daemon_mod
        args = {"name": sug["name"], "content": sug["content"],
                "mtype": sug["mtype"], "tags": sug["tags"] or None}
        if cand["scope"] == "global":
            from refmatrix.hub import global_call
            resp = global_call("memory_add", args)
        else:
            from refmatrix import discovery
            root = next((r for r in discovery.discover_roots()
                         if discovery.store_name(r) == cand.get("project")), None)
            if root is None:
                raise RuntimeError(f"no store for project {cand.get('project')!r}")
            daemon_mod.spawn_daemon(root)
            resp = daemon_mod.call(root, "memory_add",
                                   {**args, "partition": discovery.store_name(root)})
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "memory_add failed"))
        return resp["result"]["id"]
