"""memory_content is logged + replayed, and the writer-rotation swap is
retired by default.

Two coupled fixes for the body-loss-on-rotation class:

(a) `add_memory` writes the body sidecar AND a `memory_content` log event, so
    `apply_log_delta` / `rebuild_index_from_log` reconstruct bodies (previously
    only the entity row was logged — rebuilds produced content-less memories).

(b) The A/B replica swap (`_refresh_replica_now`) is a no-op by default. It
    used to promote a log-replayed inactive slot to writer; any under-logged
    state would vanish on the swap. Snapshot-tier is the read path, so pinning
    the writer to the last-known slot is safe. RMX_REPLICA_ROTATE=1 re-enables.
"""
from __future__ import annotations

import pytest

from refmatrix.store import Store


def test_memory_content_event_is_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(name="m1", content="the body", mtype="project")
    log = s.log_path.read_text(encoding="utf-8")
    assert '"op": "memory_content"' in log
    assert '"the body"' in log
    s.close()


def test_memory_content_survives_rebuild_from_log(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(
        name="m1", content="durable body text",
        mtype="project", tags=["t1", "t2"], metadata={"k": "v"},
    )
    assert s.get_memory("m1")["content"] == "durable body text"

    res = s.rebuild_index_from_log()
    assert res.get("memory_content", 0) >= 1

    got = s.get_memory("m1")
    assert got is not None
    assert got["content"] == "durable body text"
    assert got["mtype"] == "project"
    assert got["tags"] == ["t1", "t2"]
    assert got["metadata"] == {"k": "v"}
    s.close()


def test_memory_content_latest_write_wins_on_rebuild(tmp_path, monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_memory(name="m1", content="first", mtype="project")
    s.add_memory(name="m1", content="second", mtype="project")
    s.rebuild_index_from_log()
    assert s.get_memory("m1")["content"] == "second"
    s.close()


def test_writer_rotation_swap_is_dropped(tmp_path):
    from refmatrix.daemon import Daemon

    s = Store(tmp_path / ".refmatrix")
    s.init()
    d = Daemon(tmp_path / ".refmatrix")
    d.store = s
    d._active_slot = "A"
    res = d._refresh_replica_now()
    # No swap: the writer stays on its slot.
    assert res.get("enabled") is False
    assert "dropped" in (res.get("reason") or "")
    assert d._active_slot == "A"
    s.close()


# ---- task-hook-writes-queue (L212, 2026-11-24): the authoring time (23.1 R11.3) ------------------

def _mc_events(s: Store, name: str) -> list:
    import json
    out = []
    for line in s.log_path.read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("op") == "memory_content" and ev.get("name") == name:
            out.append(ev)
    return out


def test_add_memory_with_an_authoring_time_never_overwrites_a_newer_row(tmp_path, monkeypatch):
    """R11.3 item 1, the ONE guard both writers obey (the timed-out dial and the queued apply):
    `add_memory(..., updated_at=T)` writes nothing, logs no event and returns the existing id
    when the stored `memory_content.updated_at >= T`; otherwise it upserts with
    `updated_at = T` (and `created_at = T` on an INSERT) and the `memory_content` event carries
    `updated_at`. `updated_at=None` (every existing caller) is today's behaviour exactly."""
    import time
    monkeypatch.setenv("RMX_LOG", "1")
    s = Store(tmp_path / ".refmatrix")
    s.init()
    try:
        t = time.time() - 1000.0
        eid = s.add_memory(name="d1", content="v1", mtype="session/digest", updated_at=t)
        m = s.get_memory("d1")
        assert (m["content"], m["created_at"], m["updated_at"]) == ("v1", t, t), m
        assert [ev.get("updated_at") for ev in _mc_events(s, "d1")] == [t]
        for older, content in ((t - 1.0, "v-older"), (t, "v-same")):
            assert s.add_memory(name="d1", content=content, mtype="session/digest",
                                updated_at=older) == eid
            assert s.get_memory("d1")["content"] == "v1", f"{content} overwrote a newer row"
        assert len(_mc_events(s, "d1")) == 1, "a skipped write logged an event"
        assert s.add_memory(name="d1", content="v2", mtype="session/digest",
                            updated_at=t + 1.0) == eid
        m = s.get_memory("d1")
        assert (m["content"], m["created_at"], m["updated_at"]) == ("v2", t, t + 1.0), m
        before = time.time()
        s.add_memory(name="d1", content="v3", mtype="session/digest")
        m = s.get_memory("d1")
        assert m["content"] == "v3" and m["updated_at"] >= before, m
        assert _mc_events(s, "d1")[-1].get("updated_at") == m["updated_at"]
    finally:
        s.close()


def test_a_queued_entry_authored_before_a_rebuild_still_applies():
    """task-hook-writes-queue AC-7 (R11.3 item 3). A guarded write at T through the daemon's
    `memory_add` op; `rmx rebuild --from-log --yes` (the real CLI) replays facts.log into a
    fresh catalog; the replayed row keeps `updated_at == T` exactly, not the replay's wall time.
    Then, drained by the daemon one at a time, a queued entry authored at T - 1 is skipped
    (`superseded`) and one authored at T + 1 applies. Without the field in the event the
    rebuilt row carries the replay time and the T + 1 entry is skipped for good: a digest queued
    before a repair would be lost. Mutation: drop `updated_at` from the event."""
    import os
    import time
    from pathlib import Path

    from refmatrix import daemon as dm
    from refmatrix import discovery
    from tests.task21_1_support import run_rmx

    root = Path(os.environ["REFMATRIX_ROOT"])
    part = discovery.resolve_partition(root, cwd=root.parent)
    name = "focus_summary_hwqac7"
    t = time.time() - 1000.0

    def _payload(content, ts):
        return {"name": name, "content": content, "mtype": "session/digest",
                "tags": ["summary"], "metadata": {"title": "hwq"}, "protected": False,
                "updated_at": ts}

    def _daemon():
        d = dm.Daemon(root)
        st = Store(root)
        st.init()
        d.store = st
        d._log = lambda m: None
        return d

    d = _daemon()
    try:
        dm.OPS["memory_add"](d, {**_payload("v1", t), "partition": part})
        assert [ev.get("updated_at") for ev in _mc_events(d.store, name)] == [t], (
            "the memory_content event must carry the authoring time it stored")
    finally:
        d.store.close()
    r = run_rmx(["rebuild", "--from-log", "--yes"], root=root)
    assert r.returncode == 0, r.stdout + r.stderr
    d = _daemon()
    try:
        with d.store.with_partition(part):
            m = d.store.get_memory(name)
        assert m is not None and (m["content"], m["updated_at"]) == ("v1", t), m
        from refmatrix import hook_writes as hw
        for content, ts, applied in (("v0", t - 1.0, False), ("v2", t + 1.0, True)):
            hw.enqueue(root, {"op": "memory_add", "partition": part, "name": name,
                              "args": _payload(content, ts), "subject": None,
                              "origin": "stop-hook", "ts": ts})
            res = d._drain_hook_writes()
            assert (res["applied"], res["superseded"]) == ((1, 0) if applied else (0, 1)), (
                content, res)
        with d.store.with_partition(part):
            m = d.store.get_memory(name)
        assert (m["content"], m["updated_at"]) == ("v2", t + 1.0), m
    finally:
        d.store.close()


@pytest.mark.parametrize("route", ["rebuild", "apply_log_delta", "dump_then_rebuild"])
def test_replay_orders_by_and_keeps_the_authoring_time(tmp_path, monkeypatch, route):
    """R11.3 item 3 (b)(c) and the compaction emit. facts.log holding two `memory_content`
    events for one name whose APPEND order is the opposite of their `updated_at` order (`v-new`
    at T + 5 first, then `v-old` at T: a held dial that lands late) replays to `v-new` through
    BOTH replay paths (`rebuild_index_from_log` orders its per-name winner by
    `ev.get("updated_at", ts)`; `apply_log_delta` -> `_apply_one_event` passes it to
    `add_memory`'s guard). A log written by `dump_catalog_to_log` (compaction) carries
    `updated_at` and its rebuild keeps T. Mutations: the rebuild's first pass ordering by `ts`
    alone; a replay path not passing `ev.get("updated_at")`; the dump not emitting it."""
    import json
    import shutil
    import time
    monkeypatch.setenv("RMX_LOG", "1")
    t = time.time() - 1000.0
    s = Store(tmp_path / "a" / ".refmatrix")
    s.init()
    try:
        if route == "dump_then_rebuild":
            s.add_memory(name="d1", content="v1", mtype="note", updated_at=t)
            s.dump_catalog_to_log()
            assert [ev.get("updated_at") for ev in _mc_events(s, "d1")] == [t], (
                "the compacted log's memory_content event lost the authoring time")
            s.rebuild_index_from_log()
            m = s.get_memory("d1")
            assert (m["content"], m["updated_at"]) == ("v1", t), m
            return
        s.add_memory(name="d1", content="v-new", mtype="note", updated_at=t + 5.0)
        new_ev = _mc_events(s, "d1")[-1]
        old_ev = {**new_ev, "content": "v-old", "updated_at": t, "ts": new_ev["ts"] + 1.0}
        with s.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(old_ev, sort_keys=True) + "\n")
        if route == "rebuild":
            s.rebuild_index_from_log()
            m = s.get_memory("d1")
        else:
            s2 = Store(tmp_path / "b" / ".refmatrix")
            s2.init()
            try:
                shutil.copyfile(s.log_path, s2.log_path)
                s2.apply_log_delta(0)
                m = s2.get_memory("d1")
            finally:
                s2.close()
        assert m is not None and (m["content"], m["updated_at"]) == ("v-new", t + 5.0), m
    finally:
        s.close()
