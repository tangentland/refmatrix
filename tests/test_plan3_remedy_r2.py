"""ch-bsd plan-3 r2 remediation: #b-1 the hub boundary never swallows
ok:false or a timeout; #b-2 busy is not absent in the verb layer and no CLI
twin dispatches on an error string; #s-3 rmx_focus carries what the CLI
renders; #m-5 queues positive path."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import hub as hub_mod
from refmatrix import verbs
from refmatrix.cli import main as cli_main
from tests.test_plan2_remedy import _SilentDaemon
from tests.test_verbs_migrated import _MiniHub, home  # noqa: F401 (fixture)


# ---- #b-1 hub boundary -------------------------------------------------------

class _QueuesHub(_MiniHub):
    """The bus shim plus a `queues` op served from canned rows."""
    rows = [{"project": "p", "root": "/r", "daemon_up": True, "stale_files": 2}]

    def _gather_queues(self):
        return list(self.rows)

    def _serve(self):  # allow the queues op through the bus-only gate
        import json as _json, socket as _socket
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
                req = _json.loads(buf.decode()) if buf else {}
                op, args = req.get("op"), req.get("args") or {}
                if op == "ping":
                    resp = {"ok": True, "result": {"pid": os.getpid(), "port": 0}}
                elif op == "queues":
                    resp = {"ok": True, "result": self._hub.Hub._op_queues(self, args)}
                else:
                    h = getattr(self._hub.Hub, f"_op_{op}", None)
                    if h is None or not str(op).startswith("bus_"):
                        resp = {"ok": False, "error": f"unknown op {op}"}
                    else:
                        try:
                            resp = {"ok": True, "result": h(self, args)}
                        except Exception as e:  # noqa: BLE001
                            resp = {"ok": False, "error": str(e)}
                conn.sendall((_json.dumps(resp) + "\n").encode())
            finally:
                conn.close()


@pytest.fixture
def qhub(home):
    h = _QueuesHub()
    assert hub_mod.is_running()
    yield h
    h.close()


def test_hub_rpc_raises_on_ok_false_and_on_a_dead_socket(qhub, tmp_path, monkeypatch):
    with pytest.raises(verbs.VerbError, match="unknown op"):
        verbs._hub_rpc("no_such_op", {})
    def boom(op, args=None, **kw):
        raise TimeoutError("timed out")
    monkeypatch.setattr(hub_mod, "is_running", lambda: True)
    monkeypatch.setattr(hub_mod, "rpc", boom)
    with pytest.raises(verbs.VerbError, match="timed out"):
        verbs._hub_rpc("bus_channels")
    with pytest.raises(verbs.VerbError, match="timed out"):
        verbs.queues(tmp_path)


def test_queues_positive_path_on_a_real_socket(qhub, tmp_path):
    out = verbs.queues(tmp_path)
    assert out["queues"][0]["project"] == "p" and out["queues"][0]["stale_files"] == 2


def test_bus_pub_reports_a_hub_refusal_instead_of_a_keyerror(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr(hub_mod, "is_running", lambda: True)
    monkeypatch.setattr(hub_mod, "rpc", lambda op, args=None, **kw: {"ok": False, "error": "bus refused: boom"})
    r = CliRunner().invoke(cli_main, ["bus", "pub", "global:t", "hi"])
    assert r.exit_code != 0
    assert "boom" in r.output and "Traceback" not in r.output and "KeyError" not in r.output


# ---- #b-2 busy is not absent --------------------------------------------------

@pytest.fixture
def silent():
    d = _SilentDaemon()
    yield d
    d.close()


def test_verb_call_distinguishes_busy_from_absent(silent, tmp_path):
    with pytest.raises(verbs.VerbBusyError) as ei:
        verbs.ingest_status(silent.root)
    assert f"pid={os.getpid()}" in str(ei.value) and "busy" in str(ei.value)
    assert isinstance(ei.value, verbs.VerbError)
    absent = tmp_path / "none" / ".refmatrix"; absent.mkdir(parents=True)
    with pytest.raises(verbs.VerbAbsentError, match="not running"):
        verbs.ingest_status(absent)


def test_memory_add_bootstrap_fallback_never_fires_on_a_busy_daemon(silent, monkeypatch):
    """The in-process fallback exists for a store with NO daemon; on a busy
    one it would open the active slot under the writer."""
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    r = CliRunner().invoke(cli_main, ["memory", "add", "n", "-c", "body"])
    assert r.exit_code != 0
    assert "busy" in r.output and "not running" not in r.output
    assert not list(silent.root.glob("catalog*.duckdb")), "fallback opened the store"
    from refmatrix import mcp
    out = mcp._t_memory_add({"name": "n", "content": "c", "root": str(silent.root.parent)})
    assert "busy" in out.get("error", "")
    assert not list(silent.root.glob("catalog*.duckdb"))


def test_cli_twins_report_busy_by_type_not_by_string(silent, monkeypatch):
    monkeypatch.setattr(cli_mod, "_root", lambda: silent.root)
    for argv in (["ingest-status"], ["memory", "get", "x"], ["memory", "recall", "--recent", "--json"]):
        r = CliRunner().invoke(cli_main, argv)
        assert r.exit_code != 0, argv
        assert "busy" in (r.output + (r.stderr or "")), (argv, r.output)


def test_federated_search_names_a_busy_store_instead_of_dropping_it(silent, monkeypatch):
    monkeypatch.setattr("refmatrix.discovery.discover_roots", lambda: [silent.root])
    out = verbs.locate(silent.root, file="x.md")
    assert out["results"] == []
    assert out["skipped"] and "busy" in out["skipped"][0]["reason"]
    out2 = verbs.where(silent.root, "x")
    assert out2["skipped"] and "busy" in out2["skipped"][0]["reason"]


# ---- #s-3 rmx_focus carries what the CLI renders ---------------------------------

def test_focus_verb_returns_dialogue_milestones_and_line_refs(tmp_path):
    from refmatrix import stm as stm_mod
    root = tmp_path / ".refmatrix"; root.mkdir()
    s = stm_mod.Stm(root, "s9")
    s.record("input", "fix the parser in cli.py")
    s.record("git", "commit abc: fix parser")
    s.record("say", "done, parser fixed")
    out = verbs.focus(root, top=5, session="s9")
    assert [d["kind"] for d in out["dialogue"]] == ["input", "say"]
    assert out["dialogue"][0]["line"] == 1 and out["dialogue"][1]["line"] == 3
    assert out["milestones"] == [{"line": 2, "terse": "commit abc: fix parser"}]
    assert out["events_total"] == 3
    assert isinstance(out["last_line"], dict)
