"""Hub-hosted agent message bus + refinement queue.

Pub/sub so live agents coordinate in real time — intra-project
(`proj:<name>:<topic>`) and inter-project (`global:<topic>`). Every message is
fanned out to in-memory subscribers and persisted to a SQLite table
(`~/.refmatrix/bus/bus.db`) so late joiners can replay backlog AND messages are
maintainable: read-tracking (per-agent cursor), soft-delete, archive, and
purge. Durable, high-signal messages (`announce` / `decision`) are enqueued —
NOT silently written — into a refinement queue an agent/human approves to
promote into memory.

Message lifecycle (`status` column): `active` → `archived` (moved aside, still
readable) or `deleted` (soft-hidden). `purge` hard-removes archived/deleted
(or older-than) rows. `rowid` is the monotonic sequence used for ordering and
the per-agent read cursor (`bus_reads`).
"""
from __future__ import annotations

import json
import queue
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from refmatrix.taxonomy import user_home

PROMOTE_TYPES = ("announce", "decision")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bus_messages (
  seq      INTEGER PRIMARY KEY,   -- rowid alias: monotonic sequence + cursor
  id       TEXT UNIQUE NOT NULL,
  channel  TEXT NOT NULL,
  ts       TEXT NOT NULL,
  sender   TEXT,
  project  TEXT,
  mtype    TEXT,
  body     TEXT,
  reply_to TEXT,
  status   TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_bus_channel_seq ON bus_messages(channel, seq);
CREATE INDEX IF NOT EXISTS idx_bus_status ON bus_messages(status);
CREATE TABLE IF NOT EXISTS bus_reads (
  agent    TEXT NOT NULL,
  channel  TEXT NOT NULL,
  last_seq INTEGER NOT NULL,
  PRIMARY KEY (agent, channel)
);
"""


def bus_dir() -> Path:
    return user_home() / "bus"


def db_path() -> Path:
    return bus_dir() / "bus.db"


def refine_path() -> Path:
    return user_home() / "refine" / "queue.jsonl"


def _matches(pattern: str, channel: str) -> bool:
    if pattern in ("*", ""):
        return True
    if pattern.endswith("*"):
        return channel.startswith(pattern[:-1])
    if pattern.endswith(":"):
        return channel.startswith(pattern)
    return channel == pattern


def _row_to_msg(row: sqlite3.Row) -> dict:
    """DB row → the wire message dict. `body` is JSON-decoded (str and dict
    bodies both round-trip); `sender` surfaces as `from`; `rowid` as `seq`."""
    try:
        body = json.loads(row["body"]) if row["body"] is not None else None
    except (json.JSONDecodeError, TypeError):
        body = row["body"]
    return {
        "id": row["id"], "seq": row["seq"], "ts": row["ts"],
        "channel": row["channel"], "from": row["sender"],
        "project": row["project"], "type": row["mtype"], "body": body,
        "reply_to": row["reply_to"], "status": row["status"],
    }


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
        self._migrated = False

    # ---- SQLite plumbing ----
    def _connect(self) -> sqlite3.Connection:
        bus_dir().mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db_path(), timeout=5.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(_SCHEMA)
        if not self._migrated:
            self._migrate_jsonl(con)
            self._migrated = True
        return con

    def _migrate_jsonl(self, con: sqlite3.Connection) -> None:
        """One-time import of legacy per-channel `<channel>.jsonl` sidecars into
        the table, so history predating the SQLite bus survives. No-op once the
        table holds any row."""
        if con.execute("SELECT 1 FROM bus_messages LIMIT 1").fetchone():
            return
        for p in bus_dir().glob("*.jsonl"):
            try:
                lines = p.read_text().splitlines()
            except OSError:
                continue
            for ln in lines:
                try:
                    m = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                con.execute(
                    "INSERT OR IGNORE INTO bus_messages"
                    "(id,channel,ts,sender,project,mtype,body,reply_to,status) "
                    "VALUES (?,?,?,?,?,?,?,?,'active')",
                    (m.get("id") or uuid.uuid4().hex[:12],
                     m.get("channel") or p.stem, m.get("ts") or "",
                     m.get("from"), m.get("project"), m.get("type"),
                     json.dumps(m.get("body")), m.get("reply_to")),
                )
        con.commit()

    # ---- pub/sub ----
    def publish(self, channel: str, body: Any, *, sender: str = "?",
                project: str | None = None, mtype: str = "announce",
                reply_to: str | None = None) -> dict:
        mid = uuid.uuid4().hex[:12]
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        con = self._connect()
        try:
            with self._lock:
                cur = con.execute(
                    "INSERT INTO bus_messages"
                    "(id,channel,ts,sender,project,mtype,body,reply_to,status) "
                    "VALUES (?,?,?,?,?,?,?,?,'active')",
                    (mid, channel, ts, sender, project, mtype,
                     json.dumps(body), reply_to),
                )
                seq = cur.lastrowid
                con.commit()
        finally:
            con.close()
        msg = {
            "id": mid, "seq": seq, "ts": ts, "channel": channel,
            "from": sender, "project": project, "type": mtype,
            "body": body, "reply_to": reply_to, "status": "active",
        }
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

    # ---- read / history ----
    def history(self, channel: str, n: int = 50, *,
                status: str = "active") -> list[dict]:
        """Last `n` messages of a channel (chronological), filtered by status
        (`active` default, or `archived` / `deleted` / `all`)."""
        con = self._connect()
        try:
            if status == "all":
                rows = con.execute(
                    "SELECT * FROM bus_messages WHERE channel=? "
                    "ORDER BY seq DESC LIMIT ?", (channel, n)).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM bus_messages WHERE channel=? "
                    "AND status=? ORDER BY seq DESC LIMIT ?",
                    (channel, status, n)).fetchall()
        finally:
            con.close()
        return [_row_to_msg(r) for r in reversed(rows)]

    def read(self, agent: str, patterns: list[str], *, peek: bool = False,
             n: int | None = None) -> list[dict]:
        """Return `active` messages the agent has NOT seen — across every
        channel matching `patterns`, ordered globally by seq. Advances the
        agent's per-channel cursor to the last message returned unless `peek`.
        `n` caps the total returned (oldest-first)."""
        con = self._connect()
        try:
            chans = [r["channel"] for r in con.execute(
                "SELECT DISTINCT channel FROM bus_messages "
                "WHERE status='active'").fetchall()]
            want = [c for c in chans
                    if any(_matches(p, c) for p in patterns)]
            cursors = {r["channel"]: r["last_seq"] for r in con.execute(
                "SELECT channel, last_seq FROM bus_reads WHERE agent=?",
                (agent,)).fetchall()}
            out: list[dict] = []
            new_cursor: dict[str, int] = {}
            for c in want:
                last = cursors.get(c, 0)
                rows = con.execute(
                    "SELECT * FROM bus_messages WHERE channel=? "
                    "AND status='active' AND seq>? ORDER BY seq",
                    (c, last)).fetchall()
                if rows:
                    out.extend(_row_to_msg(r) for r in rows)
                    new_cursor[c] = rows[-1]["seq"]
            out.sort(key=lambda m: m["seq"])
            if n is not None:
                out = out[:n]
            if not peek and new_cursor:
                # advance only to the last seq actually returned (respects `n`)
                capped = out[-1]["seq"] if out else None
                with self._lock:
                    for c, seq in new_cursor.items():
                        adv = min(seq, capped) if capped is not None else seq
                        con.execute(
                            "INSERT INTO bus_reads(agent,channel,last_seq) "
                            "VALUES (?,?,?) ON CONFLICT(agent,channel) DO UPDATE "
                            "SET last_seq=excluded.last_seq "
                            "WHERE excluded.last_seq>bus_reads.last_seq",
                            (agent, c, adv))
                    con.commit()
        finally:
            con.close()
        return out

    def mark_read(self, agent: str, channel: str,
                  upto_seq: int | None = None) -> dict:
        """Set the agent's cursor for a channel to `upto_seq` (default: the
        channel's current max active seq — mark everything read)."""
        con = self._connect()
        try:
            if upto_seq is None:
                row = con.execute(
                    "SELECT MAX(seq) FROM bus_messages WHERE channel=? "
                    "AND status='active'", (channel,)).fetchone()
                upto_seq = row[0] or 0
            with self._lock:
                con.execute(
                    "INSERT INTO bus_reads(agent,channel,last_seq) VALUES (?,?,?) "
                    "ON CONFLICT(agent,channel) DO UPDATE SET last_seq=excluded.last_seq",
                    (agent, channel, upto_seq))
                con.commit()
        finally:
            con.close()
        return {"ok": True, "agent": agent, "channel": channel, "last_seq": upto_seq}

    def unread_count(self, agent: str, patterns: list[str] | None = None) -> dict:
        """Per-channel count of unseen active messages for `agent`."""
        con = self._connect()
        try:
            cursors = {r["channel"]: r["last_seq"] for r in con.execute(
                "SELECT channel, last_seq FROM bus_reads WHERE agent=?",
                (agent,)).fetchall()}
            rows = con.execute(
                "SELECT channel, seq FROM bus_messages "
                "WHERE status='active'").fetchall()
        finally:
            con.close()
        counts: dict[str, int] = {}
        pats = patterns or ["*"]
        for r in rows:
            c = r["channel"]
            if not any(_matches(p, c) for p in pats):
                continue
            if r["seq"] > cursors.get(c, 0):
                counts[c] = counts.get(c, 0) + 1
        return counts

    # ---- maintenance: delete / archive / purge ----
    def delete(self, msg_id: str) -> dict:
        """Soft-delete a message by id (`status='deleted'`): hidden from
        history/read, still recoverable until `purge`."""
        con = self._connect()
        try:
            with self._lock:
                cur = con.execute(
                    "UPDATE bus_messages SET status='deleted' "
                    "WHERE id=? AND status!='deleted'", (msg_id,))
                con.commit()
            n = cur.rowcount
        finally:
            con.close()
        return {"ok": n > 0, "deleted": n}

    def archive(self, *, msg_id: str | None = None, channel: str | None = None,
                before_ts: str | None = None) -> dict:
        """Move active messages to `status='archived'` — by id, or by channel
        (optionally only those with `ts < before_ts`). Keeps the active view
        lean; archived rows stay readable via `history(status='archived')`."""
        if not msg_id and not channel:
            return {"ok": False, "error": "need msg_id or channel"}
        clauses = ["status='active'"]
        params: list[Any] = []
        if msg_id:
            clauses.append("id=?"); params.append(msg_id)
        if channel:
            clauses.append("channel=?"); params.append(channel)
        if before_ts:
            clauses.append("ts<?"); params.append(before_ts)
        con = self._connect()
        try:
            with self._lock:
                cur = con.execute(
                    f"UPDATE bus_messages SET status='archived' "
                    f"WHERE {' AND '.join(clauses)}", params)
                con.commit()
            n = cur.rowcount
        finally:
            con.close()
        return {"ok": True, "archived": n}

    def unarchive(self, msg_id: str) -> dict:
        """Restore an archived message to `active`."""
        con = self._connect()
        try:
            with self._lock:
                cur = con.execute(
                    "UPDATE bus_messages SET status='active' "
                    "WHERE id=? AND status='archived'", (msg_id,))
                con.commit()
            n = cur.rowcount
        finally:
            con.close()
        return {"ok": n > 0, "restored": n}

    def purge(self, *, status: str = "deleted", channel: str | None = None,
              before_ts: str | None = None) -> dict:
        """Hard-DELETE rows — the only path that removes data. Defaults to
        reaping soft-deleted rows; pass `status='archived'` to reap the
        archive, or `status='all'` + `before_ts` to prune old history."""
        clauses: list[str] = []
        params: list[Any] = []
        if status != "all":
            clauses.append("status=?"); params.append(status)
        if channel:
            clauses.append("channel=?"); params.append(channel)
        if before_ts:
            clauses.append("ts<?"); params.append(before_ts)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        con = self._connect()
        try:
            with self._lock:
                cur = con.execute(f"DELETE FROM bus_messages{where}", params)
                con.commit()
            n = cur.rowcount
        finally:
            con.close()
        return {"ok": True, "purged": n}

    # ---- overview ----
    def channels(self) -> list[dict]:
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT channel, "
                "SUM(status='active') AS active, "
                "SUM(status='archived') AS archived, "
                "SUM(status='deleted') AS deleted "
                "FROM bus_messages GROUP BY channel ORDER BY channel").fetchall()
        finally:
            con.close()
        return [{"channel": r["channel"], "messages": r["active"] or 0,
                 "archived": r["archived"] or 0, "deleted": r["deleted"] or 0}
                for r in rows]

    def stats(self, agent: str | None = None) -> dict:
        """Bus overview: per-status totals + per-channel breakdown, plus unread
        counts for `agent` when given."""
        con = self._connect()
        try:
            totals = dict(con.execute(
                "SELECT status, COUNT(*) FROM bus_messages GROUP BY status"
            ).fetchall())
        finally:
            con.close()
        out: dict[str, Any] = {"totals": totals, "channels": self.channels()}
        if agent:
            out["unread"] = self.unread_count(agent)
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
