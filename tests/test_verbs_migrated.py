"""plan-3 task 3.2's own test strategy, delivered (ch-bsd plan-3 r1 #bs-3,
#sk-6): every verb migrated from mcp.py exercised on a REAL tmp store behind a
REAL spawned daemon, the bus verbs against a REAL `Bus` on a tmp RMX_HOME
through the REAL `hub.rpc()` socket path. The only substitute is `_MiniHub`
(registered in workflow/test_mock_registry.md): a thread that binds the hub
socket and dispatches to `Hub._op_bus_*` — the hub PROCESS is replaced, not
the bus, not the op handlers, not the transport."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest

from refmatrix import daemon as dm
from refmatrix import discovery
from refmatrix import verbs
from refmatrix.store import Store


# ---- fixtures ---------------------------------------------------------------

def _spawn_project():
    """proj/ with a git repo, a doc + a python file, a .refmatrix store holding
    two memories, served by a spawned daemon."""
    base = Path(tempfile.mkdtemp(prefix="rmxm-"))
    proj = base / "proj"
    proj.mkdir()
    (proj / "notes.md").write_text("# Notes\n\nalpha_helper explains the alpha widget.\n")
    (proj / "alpha_tool.py").write_text("def alpha_helper():\n    '''alpha widget helper'''\n    return 1\n")
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=proj, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
                   cwd=proj, check=True)
    root = proj / ".refmatrix"
    s = Store(root); s.init()
    s.add_memory(name="alpha_decision", content="we chose alpha over beta", mtype="decision")
    s.add_memory(name="beta_note", content="beta was slower", mtype="note")
    s.close()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    return base, root


@pytest.fixture(scope="module")
def live():
    base, root = _spawn_project()
    yield root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def home(monkeypatch):
    """A tmp RMX_HOME: hub socket, bus.db and registry all land here, so no
    test can touch the real ~/.refmatrix."""
    d = Path(tempfile.mkdtemp(prefix="rmxh-", dir="/tmp"))
    monkeypatch.setenv("RMX_HOME", str(d))
    yield d
    # A test that reached the global store spawned a `-p global` daemon
    # under this home (`hub.ensure_global_daemon`); rmtree alone left 21 of
    # them alive on deleted roots, each holding a catalog and a socket
    # (found by ch-bsd plan-5 r3, 2026-09-15). Stop it before the dir goes.
    from refmatrix import hub as hub_mod
    groot = hub_mod.global_store_root()      # the home IS the global store (RMX_HOME still set)
    if groot.is_dir():
        # the spawn is asynchronous: give a just-launched daemon up to 3 s to
        # write its pid file, then stop it (a bare rmtree left one behind
        # even after this fixture learned to stop the daemon)
        import time as _time
        for _ in range(30):
            if (groot / "rmxd.pid").exists():
                break
            _time.sleep(0.1)
        dm.stop_daemon(groot)
    shutil.rmtree(d, ignore_errors=True)


class _MiniHub:
    """See module docstring. Binds `hub.hub_sock_path()` and serves the REAL
    `Hub._op_bus_*` handlers over a REAL `Bus()` (tmp RMX_HOME)."""

    def __init__(self):
        from refmatrix.bus import Bus
        from refmatrix import hub as hub_mod
        self.bus = Bus()
        self.port = 0
        self._hub = hub_mod
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sp = hub_mod.hub_sock_path()
        sp.parent.mkdir(parents=True, exist_ok=True)
        self._sock.bind(str(sp))
        self._sock.listen(8)
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            try:
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                req = json.loads(buf.decode()) if buf else {}
                op, args = req.get("op"), req.get("args") or {}
                if op == "ping":
                    resp = {"ok": True, "result": {"pid": os.getpid(), "port": 0}}
                else:
                    h = getattr(self._hub.Hub, f"_op_{op}", None)
                    if h is None or not op.startswith("bus_"):
                        resp = {"ok": False, "error": f"unknown op {op}"}
                    else:
                        try:
                            resp = {"ok": True, "result": h(self, args)}
                        except Exception as e:  # noqa: BLE001
                            resp = {"ok": False, "error": str(e)}
                conn.sendall((json.dumps(resp) + "\n").encode())
            finally:
                conn.close()

    def close(self):
        self._stop = True
        self._sock.close()


@pytest.fixture
def minihub(home):
    h = _MiniHub()
    from refmatrix import hub as hub_mod
    assert hub_mod.is_running()
    yield h
    h.close()


def _eventually(fn, pred, timeout=30.0):
    """Daemon reads are served from the mirror/snapshot slot, which trails the
    writer by a tick — the production read path's own semantics, so a test
    that writes then reads waits for the read to catch up."""
    deadline = time.monotonic() + timeout
    while True:
        out = fn()
        if pred(out) or time.monotonic() > deadline:
            return out
        time.sleep(0.2)


# ---- task -------------------------------------------------------------------

def test_task_verb_push_list_current_pop_swap(tmp_path):
    root = tmp_path / ".refmatrix"; root.mkdir()
    assert verbs.task(root, action="list", session="s1") == {"tasks": []}
    verbs.task(root, action="push", desc="first", session="s1")
    r = verbs.task(root, action="push", desc="second", session="s1")
    assert r["current"] == "second" and r["depth"] == 2
    assert [t["desc"] for t in verbs.task(root, action="list", session="s1")["tasks"]] == ["first", "second"]
    assert verbs.task(root, action="current", session="s1")["current"]["desc"] == "second"
    assert verbs.task(root, action="swap", session="s1")["current"] == "first"
    assert verbs.task(root, action="pop", session="s1")["popped"] == "first"
    with pytest.raises(verbs.VerbError):
        verbs.task(root, action="push", session="s1")


# ---- memory dispatcher ------------------------------------------------------

def test_memory_verb_get_list_search_retag_forget_on_a_live_daemon(live):
    got = verbs.memory(live, action="get", name="alpha_decision")["memory"]
    assert got["content"] == "we chose alpha over beta"
    assert verbs.memory(live, action="get", id=got["id"])["memory"]["name"] == "alpha_decision"
    names = {m["name"] for m in verbs.memory(live, action="list")["rows"]}
    assert {"alpha_decision", "beta_note"} <= names
    hits = verbs.memory(live, action="search", query="slower")["rows"]
    assert [m["name"] for m in hits] == ["beta_note"]
    verbs.memory(live, action="retag", name="beta_note", add=["perf"])
    got = _eventually(lambda: verbs.memory(live, action="get", name="beta_note")["memory"],
                      lambda m: "perf" in (m or {}).get("tags", []))
    assert "perf" in got["tags"]
    added = verbs.memory(live, action="add", name="gamma", content="g")
    assert added.get("id")
    _eventually(lambda: verbs.memory(live, action="get", name="gamma")["memory"], bool)
    verbs.memory(live, action="forget", name="gamma")
    gone = _eventually(lambda: verbs.memory(live, action="get", name="gamma")["memory"],
                       lambda m: m is None)
    assert gone is None


def test_memory_get_without_id_or_name_is_a_caller_error(live):
    with pytest.raises(verbs.VerbArgsError):
        verbs.memory(live, action="get")
    with pytest.raises(verbs.VerbArgsError):
        verbs.memory(live, action="forget")


def test_memory_recall_action_forwards_the_recall_knobs(live):
    """#meh-8: recall through the dispatcher honours recent/since/
    include_session like the dedicated verb (0.67 forwarded them)."""
    verbs.memory_add(live, "sess_card", "handoff", mtype="session/digest")
    shown = _eventually(
        lambda: verbs.memory(live, action="recall", recent=True, k=10, include_session=True),
        lambda r: "sess_card" in [m["name"] for m in r["memories"]])
    hidden = verbs.memory(live, action="recall", recent=True, k=10)
    assert "sess_card" not in [m["name"] for m in hidden["memories"]]
    assert "sess_card" in [m["name"] for m in shown["memories"]]
    windowed = verbs.memory(live, action="recall", recent=True, since="1s", k=10)
    assert windowed["since_seconds"] == 1.0


# ---- recall_state / ingest_status / federated ------------------------------

def test_recall_state_verb_reads_the_named_memory_dir(live, tmp_path):
    memdir = tmp_path / "mem"; memdir.mkdir()
    (memdir / "MEMORY.md").write_text("- [x](note_x.md) — x\n")
    (memdir / "note_x.md").write_text("---\ngmd: \"0.1\"\nid: note_x\ntitle: x\ntags: [project]\n---\n# x {#root}\nbody\n")
    out = verbs.recall_state(live, session="s-rs", memory_dir=str(memdir))
    assert isinstance(out, dict)
    assert "git" in out and "daemon" in out
    assert any("note_x" in json.dumps(v) for v in out.values())


def test_ingest_status_verb_lists_then_polls_a_real_job(live):
    assert "jobs" in verbs.ingest_status(live)
    started = verbs.ingest(live, path=str(live.parent), semantic=False)
    jid = started["job_id"]
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        st = verbs.ingest_status(live, job_id=jid)
        if st["job"].get("status") in ("done", "completed", "failed", "error"):
            break
        time.sleep(0.2)
    assert st["job"]["id"] == jid
    assert jid in {j["id"] for j in verbs.ingest_status(live)["jobs"]}


@pytest.fixture
def only_live(live, monkeypatch):
    """Federated verbs fan out over `discovery.discover_roots()` — an
    environment input (launchd + registry + cwd); pinned to the live tmp
    store so the test never touches real stores."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [live])
    return live


def test_where_verb_finds_a_memory_across_live_stores(only_live, home):
    out = verbs.where(only_live, "alpha")
    mem = [r for r in out["results"] if r["kind"] == "memory"]
    assert any(r["name"] == "alpha_decision" for r in mem)


def test_search_verb_runs_the_dsl_on_every_live_store(only_live):
    out = verbs.search(only_live, "mentions:alpha")
    assert isinstance(out["projects"], list) and len(out["projects"]) == 1
    assert out["projects"][0]["project"] == discovery.store_name(only_live)
    assert out["projects"][0]["root"] == str(only_live)


def test_locate_verb_finds_an_ingested_file_by_basename(only_live):
    verbs.ingest(only_live, path=str(only_live.parent), semantic=False)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        out = verbs.locate(only_live, file="notes.md")
        if out["results"]:
            break
        time.sleep(0.3)
    assert any(Path(r["path"]).name == "notes.md" for r in out["results"]), out


# ---- queues / bus -----------------------------------------------------------

def test_queues_verb_refuses_without_a_hub(home, tmp_path):
    with pytest.raises(verbs.VerbError, match="hub not running"):
        verbs.queues(tmp_path)


def test_bus_verbs_round_trip_on_a_real_bus(minihub, tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_AGENT", raising=False)
    root = tmp_path / "alpha" / ".refmatrix"; root.mkdir(parents=True)
    m = verbs.bus_pub(root, "proj:alpha:topic", "hello", type="note")["message"]
    assert m["from"] == "alpha" and m["project"] == "alpha"
    m2 = verbs.bus_pub(root, "global:x", "reply", sender="agent-x", reply_to=m["id"])["message"]
    assert m2["from"] == "agent-x" and m2["reply_to"] == m["id"] and m2["project"] is None
    chans = {c["channel"] for c in verbs.bus_channels(root)["channels"]}
    assert {"proj:alpha:topic", "global:x"} <= chans
    assert [c["channel"] for c in verbs.bus_channels(root, glob="proj:*")["channels"]] == ["proj:alpha:topic"]
    hist = verbs.bus_history(root, "proj:alpha:topic")["messages"]
    assert [h["body"] for h in hist] == ["hello"]
    unread = verbs.bus_read(root, agent="reader")["messages"]
    assert [u["body"] for u in unread] == ["hello", "reply"]
    assert verbs.bus_read(root, agent="reader")["messages"] == []          # cursor advanced
    verbs.bus_pub(root, "global:x", "again")
    assert [u["body"] for u in verbs.bus_read(root, agent="reader", peek=True)["messages"]] == ["again"]
    verbs.bus_mark_read(root, "global:x", agent="reader")
    assert verbs.bus_read(root, agent="reader")["messages"] == []
    assert verbs.bus_delete(root, m2["id"])["deleted"]
    assert m2["id"] not in {h["id"] for h in verbs.bus_history(root, "global:x")["messages"]}
    assert verbs.bus_archive(root, channel="proj:alpha:topic")["archived"] == 1
    assert verbs.bus_history(root, "proj:alpha:topic", status="archived")[
        "messages"][0]["id"] == m["id"]
    assert verbs.bus_unarchive(root, m["id"])["restored"]
    st = verbs.bus_stats(root, agent="reader")
    assert st["totals"].get("deleted") == 1
    assert verbs.bus_purge(root)["purged"] == 1


def test_bus_sender_prefers_explicit_then_env_then_project_then_host(tmp_path, monkeypatch):
    root = tmp_path / "zeta" / ".refmatrix"; root.mkdir(parents=True)
    monkeypatch.delenv("RMX_AGENT", raising=False)
    assert verbs._bus_sender(root, "me") == "me"
    monkeypatch.setenv("RMX_AGENT", "env-a")
    assert verbs._bus_sender(root, None) == "env-a"
    monkeypatch.delenv("RMX_AGENT")
    assert verbs._bus_sender(root, None) == "zeta"
    assert verbs._bus_sender(tmp_path / "nope" / ".refmatrix", None) == socket.gethostname()


def test_bus_alias_from_loses_to_the_canonical_param(minihub, tmp_path):
    """#meh-9: canonical-first — `agent` wins over its alias `from` when a
    caller sends both."""
    root = tmp_path / "p" / ".refmatrix"; root.mkdir(parents=True)
    verbs.bus_pub(root, "global:a", "x")
    got = verbs.VERBS["rmx_bus_read"].run(root, {"agent": "canon", "from": "alias"})
    assert got["messages"] and verbs.VERBS["rmx_bus_read"].run(root, {"agent": "canon"})["messages"] == []
