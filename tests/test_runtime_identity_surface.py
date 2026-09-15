"""plan-1 task 1.1 — the runtime identity is visible where operators look:
`rmx version -v`, `rmx daemon status`, the daemon's ping, `rmx hub status`."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as daemon_mod
from refmatrix import upgrade as up


def _ident(dev_tree: bool) -> dict:
    return {"version": "9.9.9", "import_path": Path("/x/src/refmatrix/__init__.py"),
            "code_root": Path("/x"), "venv_tree": Path("/y") if dev_tree else Path("/x"),
            "editable_target": Path("/x/src"), "dev_tree": dev_tree}


def test_version_verbose_prints_code_path_and_dev_tree_flag(monkeypatch):
    monkeypatch.setattr(up, "runtime_identity", lambda **kw: _ident(True))
    out = CliRunner().invoke(cli_mod.main, ["version", "-v"]).output
    assert "code: /x/src/refmatrix/__init__.py" in out
    assert "DEV TREE" in out


def test_version_verbose_clean(monkeypatch):
    monkeypatch.setattr(up, "runtime_identity", lambda **kw: _ident(False))
    out = CliRunner().invoke(cli_mod.main, ["version", "-v"]).output
    assert "code:" in out and "DEV TREE" not in out


def test_daemon_ping_carries_code_path_and_dev_tree(tmp_path, monkeypatch):
    # identity is cached per process (a health probe must not glob
    # site-packages); reset the cache so the patched identity is what gets
    # computed for this test
    monkeypatch.setattr(daemon_mod, "_PROCESS_IDENTITY", None)
    monkeypatch.setattr(up, "runtime_identity", lambda **kw: _ident(True))

    class D:  # the ping op only touches root + store
        root = tmp_path
        store = None
    res = daemon_mod._op_ping(D(), {})
    assert res["code_path"] == "/x/src/refmatrix/__init__.py"
    assert res["dev_tree"] is True


def test_daemon_status_shows_the_daemons_code_path(tmp_path, monkeypatch):
    """Status reports what the DAEMON imported (its ping), not what the CLI
    imported — they are separate processes."""
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path)
    monkeypatch.setattr(daemon_mod, "read_pid", lambda root: 4242)
    monkeypatch.setattr(daemon_mod, "ping", lambda root, **kw: True)
    monkeypatch.setattr(daemon_mod, "call", lambda root, op, args=None, **kw: {
        "ok": True, "result": {"pid": 4242, "version": "9.9.9",
                                "code_path": "/dev/src/refmatrix/__init__.py", "dev_tree": True}})
    out = CliRunner().invoke(cli_mod.main, ["daemon", "status"]).output
    assert "code: /dev/src/refmatrix/__init__.py" in out
    assert "DEV TREE" in out


def test_hub_queue_rows_carry_dev_tree(monkeypatch):
    from refmatrix import hub as hub_mod
    monkeypatch.setattr(hub_mod, "_daemon_identity", lambda root: {"dev_tree": True, "code_path": "/dev/x"})
    rows = hub_mod._annotate_identity([{"project": "p", "root": "/r", "daemon_up": True, "stale_files": 0}])
    assert rows[0]["dev_tree"] is True and rows[0]["code_path"] == "/dev/x"
