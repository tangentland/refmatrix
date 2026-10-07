"""ch-bsd r3 #b-2: `-i` must reach EVERY read path, and no flag means grep's
case-SENSITIVE match on every path, the floor included.

bug-073 threaded `ignore_case` into `Store.grep_evidence` and into the two
read paths that call it in-process (replica and direct). The third caller is
the daemon RPC in `_grep_run`, which sent `{pattern, regex, linkage, kind,
limit}` and no `ignore_case` — so the same `rmx grep -i error` answered from
the index on the direct path and fell to the floor on the daemon path. Two
mutations that dropped `-i` survived every grep test file, because the only
`-i` test was a store-level call.

The floor had the mirror defect, pre-existing: `ignore_case is None` (no
flag) mapped to `rg -S` (smart-case) and to `grep -i`, so `rmx grep error
e.txt` matched `ERROR here` and exited 0 where grep exits 1. That is the path
every rewritten bare `grep` with a named file takes.

The daemon path is driven through `_grep_run` with a TRANSPORT shim: `ping`
says up and `call` dispatches to the real `OPS` entry on a real `Daemon` over
a real `Store`. Only the socket is replaced (registered in
workflow/test_mock_registry.md).
"""
from __future__ import annotations

import types

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix.daemon import OPS, Daemon
from refmatrix.store import Store


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root, backend="duckdb")
    s.init()
    d = Daemon(root)
    d.store = s
    d._log = lambda m: None
    yield d
    s.close()


def _seed_upper(s: Store, proj):
    """One `keyword/error` row on a line that holds `ERROR`, never `error`."""
    f = proj / "a.py"
    f.write_text("ERROR raised here\n")
    cid = s.add_concept("keyword/error")
    eid = s.upsert_entity("code", "a.py", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=1)
    return f


def _rpc_shim(d: Daemon, sent: list):
    """`daemon_mod` as `_grep_run` sees it: up, and every call served by the
    REAL op on the real daemon."""
    def call(root, op, args, **kw):
        sent.append(dict(args))
        return {"ok": True, "result": OPS[op](d, args)}
    return types.SimpleNamespace(ping=lambda *a, **k: True, call=call)


def _tlog():
    return types.SimpleNamespace(cardinality=None, answered_by=None, learn=False)


def _run_daemon_path(d, flags: str, pattern: str, sent: list):
    gf = cli_mod._parse_grep_flags(flags)
    tlog = _tlog()
    try:
        cli_mod._grep_run(None, d.root, _rpc_shim(d, sent), pattern, pattern,
                          False, None, None, 100, False, False, gf, [], tlog)
    except SystemExit:
        pass
    return tlog


def test_the_daemon_rpc_carries_ignore_case(daemon, capsys):
    _seed_upper(daemon.store, daemon.root.parent)
    sent: list = []

    tlog = _run_daemon_path(daemon, "-i", "error", sent)

    assert sent and sent[0].get("ignore_case") is True, (
        f"the RPC dropped -i: {sent}")
    assert tlog.answered_by == "index", tlog
    assert "a.py:1" in capsys.readouterr().out


def test_the_daemon_rpc_without_i_is_case_sensitive(daemon, capsys):
    _seed_upper(daemon.store, daemon.root.parent)
    sent: list = []

    tlog = _run_daemon_path(daemon, "", "error", sent)

    assert sent and not sent[0].get("ignore_case"), sent
    assert tlog.answered_by != "index", tlog
    assert "a.py:1" not in capsys.readouterr().out


# ---- the floor: no flag is grep-case, not smart-case ----------------------

@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    monkeypatch.setenv("RMX_GREP_NOTE", "0")
    p = tmp_path / "proj"
    p.mkdir()
    s = Store(p / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    (p / "e.txt").write_text("ERROR here\n")
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(p)
    return p


def test_the_floor_without_i_does_not_match_another_case(proj):
    """`grep error e.txt` on `ERROR here` prints nothing and exits 1."""
    res = CliRunner().invoke(cli_mod.main, ["grep", "--no-learn", "error",
                                            "e.txt"])

    assert "ERROR here" not in res.stdout, res.stdout
    assert res.exit_code == 1, (res.exit_code, res.output)


def test_the_floor_count_without_i_is_zero(proj):
    """`grep -c error e.txt` prints `0` and exits 1."""
    res = CliRunner().invoke(cli_mod.main, ["grep", "--no-learn", "-c",
                                            "error", "e.txt"])

    assert res.stdout.strip() == "0", res.stdout
    assert res.exit_code == 1, (res.exit_code, res.output)


def test_the_floor_with_i_still_matches(proj):
    res = CliRunner().invoke(cli_mod.main, ["grep", "--no-learn", "-i",
                                            "error", "e.txt"])

    assert "ERROR here" in res.stdout, res.output
    assert res.exit_code == 0, res.output


def test_the_daemon_rpc_carries_word(daemon, capsys):
    """`-w` is the second matching flag the RPC must carry (ch-bsd r3 #s-7)."""
    f = daemon.root.parent / "w.py"
    f.write_text("an error here\n")
    s = daemon.store
    cid = s.add_concept("keyword/err")
    eid = s.upsert_entity("code", "w.py", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=1)
    sent: list = []

    tlog = _run_daemon_path(daemon, "-w", "err", sent)

    assert sent and sent[0].get("word") is True, sent
    assert tlog.answered_by != "index", tlog


# ---- ch-bsd r4 SKETCHY: paths that worked when run but had no test ---------

def test_the_daemon_rpc_cap_reaches_the_cli_note(daemon, capsys):
    """`capped` travels from `_op_grep_indexed` through the RPC result to
    `_grep_index_notes`. Survived mutation at r4 (the CLI ignoring it)."""
    f = daemon.root.parent / "c.py"
    f.write_text("error one\nerror two\nerror three\n")
    s = daemon.store
    cid = s.add_concept("keyword/error")
    eid = s.upsert_entity("code", "c.py", path=str(f))
    s.link("mentions", cid, eid)
    for ln in (1, 2, 3):
        s.add_evidence("mentions", cid, eid, file=str(f), line=ln)
    gf = cli_mod._parse_grep_flags("")
    try:
        cli_mod._grep_run(None, daemon.root, _rpc_shim(daemon, []), "error",
                          "error", False, None, None, 2, False, False, gf, [],
                          _tlog())
    except SystemExit:
        pass
    err = capsys.readouterr().err
    assert "capped at --limit 2" in err, err


@pytest.mark.parametrize("layout", ["replica", "direct"])
def test_word_reaches_the_in_process_read_paths(tmp_path, monkeypatch, layout):
    """`-w` on the replica (default) and direct paths, end to end. At r4 a
    mutation dropping `word=` from either in-process caller survived."""
    import shutil as _sh
    monkeypatch.delenv("RMX_BACKEND", raising=False)
    proj = tmp_path / "proj"
    proj.mkdir()
    s = Store(proj / ".refmatrix", backend="duckdb")
    s.init()
    f = proj / "w.py"
    f.write_text("an error here\n")
    cid = s.add_concept("keyword/err")
    eid = s.upsert_entity("code", "w.py", path=str(f))
    s.link("mentions", cid, eid)
    s.add_evidence("mentions", cid, eid, file=str(f), line=1)
    s.close()
    if layout == "direct":
        legacy = proj / ".refmatrix" / "catalog.duckdb"
        if legacy.exists():
            _sh.move(str(legacy), str(proj / ".refmatrix" / "catalog.A.duckdb"))
        (proj / ".refmatrix" / "active").write_text("A\n")
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)
    monkeypatch.chdir(proj)

    plain = CliRunner().invoke(cli_mod.main, ["grep", "--no-fallback", "--", "err"])
    word = CliRunner().invoke(cli_mod.main, ["grep", "--no-fallback", "-w", "--", "err"])

    assert plain.exit_code == 0 and "w.py:1" in plain.stdout, plain.output
    assert word.exit_code == 1, f"{layout}: -w kept a non-word hit: {word.output}"
