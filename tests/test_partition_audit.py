"""ADR-0003: a store says whether its partition layout is canonical.

The 2026-09-20 fleet survey found four layouts, six zero-row orphan
registrations (one of them a TEST FIXTURE NAME in this project's live catalog),
~143MB of Lance vectors for partitions that no longer exist, session partitions
on four of eight stores, and one store never embedded at all. None of it came
from a decision; all of it was invisible because nothing reports shape.

The decision logic is a PURE FUNCTION over facts — partitions, row counts,
vector directories — so the audit cannot write, cannot open a catalog, and can
be tested against every fleet shape without building nine stores.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from refmatrix import partitions as pt


def _facts(**over):
    """A canonical project store, unless overridden."""
    base = dict(
        store_name="refmatrix",
        partitions=[{"id": 4, "name": "refmatrix", "kind": "repo"},
                    {"id": 68, "name": "sessions-refmatrix", "kind": "repo"}],
        active="refmatrix",
        row_counts={"refmatrix": {"code": 6147, "doc": 561, "memory": 368},
                    "sessions-refmatrix": {"memory": 66}},
        vector_dirs=["refmatrix"],
        is_global=False,
    )
    base.update(over)
    return base


def _kinds(result):
    return sorted(f["kind"] for f in result["findings"])


# ---- the canonical shapes -----------------------------------------------

def test_a_canonical_project_store_reports_no_drift():
    """`info` findings are allowed in a canonical shape — the sessions-embedding
    question is deliberately undecided, and reporting it must not make every
    store read as drifted."""
    out = pt.audit(**_facts())
    assert out["shape"] == "canonical", out
    assert [f for f in out["findings"] if f["severity"] != "info"] == []


def test_a_canonical_global_store_reports_no_findings():
    out = pt.audit(store_name="global", active="global",
                   partitions=[{"id": 3, "name": "global", "kind": "repo"}],
                   row_counts={"global": {"memory": 200}},
                   vector_dirs=["global"], is_global=True)
    assert out["shape"] == "canonical", out


# ---- the six orphans ------------------------------------------------------

def test_a_zero_row_registration_is_an_orphan():
    """`test_session_list_shows_ingest0` — a test registered a partition and
    wrote nothing. It is a leak, not a partition (ADR-0003 invariant 1)."""
    f = _facts()
    f["partitions"] = f["partitions"] + [
        {"id": 1, "name": "test_session_list_shows_ingest0", "kind": "repo"}]
    f["row_counts"]["test_session_list_shows_ingest0"] = {}
    out = pt.audit(**f)
    assert "orphan-partition" in _kinds(out)
    orphan = next(x for x in out["findings"] if x["kind"] == "orphan-partition")
    assert orphan["name"] == "test_session_list_shows_ingest0"
    assert out["shape"] == "drift"


def test_the_active_partition_is_never_called_an_orphan_when_empty():
    """A freshly `init`ed store has an empty active partition. That is a new
    store, not a leak — flagging it would train the signal away."""
    out = pt.audit(store_name="fresh", active="fresh",
                   partitions=[{"id": 1, "name": "fresh", "kind": "repo"}],
                   row_counts={"fresh": {}}, vector_dirs=[], is_global=False)
    assert "orphan-partition" not in _kinds(out)


def test_an_empty_NON_canonical_active_partition_is_not_an_orphan_either():
    """The case the previous test does NOT reach: `rmx -p scratch` makes a
    non-canonical partition active. It is still where writes are going, so it
    is not a leak — but it IS outside the canonical shape and must say so.

    Found by mutation: deleting the `name != active` guard killed no test,
    because a canonical active partition short-circuits on `name in expected`
    long before the orphan branch."""
    out = pt.audit(store_name="proj", active="scratch",
                   partitions=[{"id": 1, "name": "proj", "kind": "repo"},
                               {"id": 2, "name": "sessions-proj", "kind": "repo"},
                               {"id": 3, "name": "scratch", "kind": "repo"}],
                   row_counts={"proj": {"code": 5}, "sessions-proj": {"memory": 2},
                               "scratch": {}},
                   vector_dirs=["proj"], is_global=False)
    assert "orphan-partition" not in _kinds(out), out["findings"]
    assert "unexpected-partition" in _kinds(out)


def test_another_projects_partition_is_reported_as_foreign():
    """`memory-viascope` registered inside refmatrix's store."""
    f = _facts()
    f["partitions"] = f["partitions"] + [
        {"id": 7, "name": "memory-viascope", "kind": "repo"}]
    f["row_counts"]["memory-viascope"] = {}
    out = pt.audit(**f)
    assert "foreign-partition" in _kinds(out)


def test_a_reversed_split_partition_is_named_as_such():
    """`memory-<project>` was merged away post-0.5.0; a live one is drift with
    a specific remedy, not a generic orphan."""
    f = _facts()
    f["partitions"] = f["partitions"] + [
        {"id": 9, "name": "memory-refmatrix", "kind": "repo"}]
    f["row_counts"]["memory-refmatrix"] = {"memory": 12}
    out = pt.audit(**f)
    finding = next(x for x in out["findings"] if x["kind"] == "reversed-split")
    assert "0.5.0" in finding["detail"]


# ---- vectors --------------------------------------------------------------

def test_vectors_without_a_partition_are_orphans():
    """143MB of Lance data for partitions that no longer exist."""
    f = _facts()
    f["vector_dirs"] = ["refmatrix", "memory-refmatrix", "memory-viascope"]
    out = pt.audit(**f)
    orphans = [x["name"] for x in out["findings"] if x["kind"] == "orphan-vectors"]
    assert sorted(orphans) == ["memory-refmatrix", "memory-viascope"]


def test_a_populated_active_partition_without_vectors_is_unembedded():
    """orderly: 27 code + 79 doc + 4721 concepts and no vectors at all, so
    every dense retrieval returns nothing while symbolic surfaces work."""
    f = _facts(vector_dirs=[])
    out = pt.audit(**f)
    assert "unembedded" in _kinds(out)


def test_an_unembedded_session_partition_is_reported_but_not_as_drift():
    """Whether sessions are embedded is deliberately UNDECIDED (ADR-0003
    #deferred-embed) — it is reported as information, and does not make a
    store non-canonical."""
    f = _facts()
    out = pt.audit(**f)
    note = next(x for x in out["findings"] if x["kind"] == "sessions-unembedded")
    assert note["severity"] == "info"
    assert out["shape"] == "canonical"


# ---- missing pieces -------------------------------------------------------

def test_a_project_store_with_no_session_partition_is_drift():
    """orderly, atldb, thiquet."""
    f = _facts()
    f["partitions"] = [p for p in f["partitions"] if p["name"] == "refmatrix"]
    f["row_counts"].pop("sessions-refmatrix")
    out = pt.audit(**f)
    assert "missing-sessions" in _kinds(out)
    assert out["shape"] == "drift"


def test_a_global_store_with_a_second_partition_is_drift():
    out = pt.audit(store_name="global", active="global",
                   partitions=[{"id": 3, "name": "global", "kind": "repo"},
                               {"id": 1, "name": "tholley", "kind": "repo"}],
                   row_counts={"global": {"memory": 200}, "tholley": {}},
                   vector_dirs=["global"], is_global=True)
    assert out["shape"] == "drift"


def test_a_global_store_holding_code_or_docs_violates_the_memory_only_guard():
    out = pt.audit(store_name="global", active="global",
                   partitions=[{"id": 3, "name": "global", "kind": "repo"}],
                   row_counts={"global": {"memory": 200, "doc": 120, "code": 14}},
                   vector_dirs=["global"], is_global=True)
    assert "global-not-memory-only" in _kinds(out)


def test_a_global_store_is_not_asked_for_a_sessions_partition():
    out = pt.audit(store_name="global", active="global",
                   partitions=[{"id": 3, "name": "global", "kind": "repo"}],
                   row_counts={"global": {"memory": 200}},
                   vector_dirs=["global"], is_global=True)
    assert "missing-sessions" not in _kinds(out)


# ---- the contract ---------------------------------------------------------

def test_audit_is_pure_and_takes_no_store():
    """Read-only is a property of the signature, not a promise in a docstring:
    the function receives FACTS and can neither open nor write a catalog."""
    import inspect

    params = set(inspect.signature(pt.audit).parameters)
    assert params == {"store_name", "partitions", "active", "row_counts",
                      "vector_dirs", "is_global", "sessions_available"}
    assert not any(p in params for p in ("store", "root", "conn"))


def test_every_finding_carries_a_severity_and_a_remedy():
    f = _facts()
    f["partitions"] = f["partitions"] + [{"id": 1, "name": "leak", "kind": "repo"}]
    f["row_counts"]["leak"] = {}
    f["vector_dirs"] = ["refmatrix", "ghost"]
    out = pt.audit(**f)
    assert out["findings"]
    for finding in out["findings"]:
        assert finding["severity"] in ("info", "warn", "drift"), finding
        assert finding["remedy"], finding
        assert finding["name"] is not None, finding


def test_expected_shape_is_reported_so_a_reader_sees_the_target():
    out = pt.audit(**_facts())
    assert out["expected"] == ["refmatrix", "sessions-refmatrix"]


# ---- wiring: the op and the command, on a REAL store ----------------------
#
# `impression_bsd_tests_bypass_wiring`: a green test on an unwired helper is the
# exact shape this project keeps finding. The tests above prove the decision
# logic; these two prove the op gathers real catalog facts and the command
# reaches it.

def test_the_daemon_op_gathers_real_catalog_facts(tmp_path):
    from refmatrix import daemon as dm
    from refmatrix.store import Store

    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    d = dm.Daemon(root)
    d.store = s
    try:
        out = dm.OPS["partition_audit"](d, {})
    finally:
        s.close()

    assert out["store"] == "proj"
    assert out["expected"] == ["proj", "sessions-proj"]
    # A fresh store has no session partition and no vectors — both real
    # findings, produced from the catalog rather than from a fixture dict.
    kinds = {f["kind"] for f in out["findings"]}
    assert "missing-sessions" in kinds
    assert out["root"] == str(root)


def test_the_command_audits_a_store_with_no_daemon(tmp_path, monkeypatch):
    """The daemon-down path reads the catalog directly. Exercised end to end so
    `rmx partition audit` is proven to reach the audit, not merely to exist."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix.store import Store

    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()

    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["partition", "audit", "--json"])
    assert res.exit_code == 1, res.output          # drift: no sessions partition
    payload = json.loads(res.output)
    assert payload["store"] == "proj"
    assert any(f["kind"] == "missing-sessions" for f in payload["findings"])


def test_the_command_reports_a_canonical_store_and_exits_zero(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix.store import Store

    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    with s.with_partition("sessions-proj"):
        pass                      # registers it; the audit reads the catalog
    s.close()

    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["partition", "audit", "--json"])
    payload = json.loads(res.output)
    assert payload["shape"] == "canonical", payload
    assert res.exit_code == 0, res.output


def test_fleet_mode_audits_every_live_root_and_REPORTS_the_skipped(tmp_path, monkeypatch):
    """`search._live_roots()` returns `(roots, skipped)`. The first version of
    `--fleet` iterated the TUPLE and crashed on the live fleet with
    `TypeError: argument should be a str ... not 'list'` — no test covered the
    fleet path at all.

    Reporting `skipped` is not decoration: a busy store silently dropped from a
    fan-out is a filed finding (ch-bsd plan-3 r2 #b-2). An audit that quietly
    examines six of eight stores and prints a clean verdict is worse than no
    audit."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix.store import Store

    roots = []
    for name in ("alpha", "beta"):
        root = tmp_path / name / ".refmatrix"
        root.parent.mkdir()
        s = Store(root)
        s.init()
        s.close()
        roots.append(str(root))

    skipped = [{"project": "gamma", "root": "/x/gamma/.refmatrix",
                "reason": "daemon busy pid=1 (alive, not answering)"}]
    monkeypatch.setattr("refmatrix.search._live_roots", lambda: (roots, skipped))
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["partition", "audit", "--fleet", "--json"])
    payload = json.loads(res.output)
    audited = {row["store"] for row in payload
               if row.get("store") and not row.get("skipped")}
    assert audited == {"alpha", "beta"}, payload
    assert any(row.get("skipped") for row in payload), (
        "a store that could not be audited must appear in the output")
    assert any("gamma" in json.dumps(row) for row in payload)


def test_one_unreachable_store_does_not_kill_the_fleet_audit(tmp_path, monkeypatch):
    """A daemon that times out (busy with an ingest, holding the store lock)
    raised straight out of the command and killed the whole fan-out on the live
    fleet. One store must not take the audit down: it is recorded as an error
    row and the others are still audited."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix.store import Store

    root = tmp_path / "alpha" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()
    dead = tmp_path / "busy" / ".refmatrix"
    dead.parent.mkdir(parents=True)

    monkeypatch.setattr("refmatrix.search._live_roots",
                        lambda: ([str(dead), str(root)], []))
    # `busy` answers ping and then times out; `alpha` has no daemon at all.
    monkeypatch.setattr("refmatrix.daemon.ping",
                        lambda r, *a, **k: str(r) == str(dead))

    def _boom(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr("refmatrix.daemon.call", _boom)

    res = CliRunner().invoke(cli_mod.main, ["partition", "audit", "--fleet", "--json"])
    payload = json.loads(res.output)
    errored = [r for r in payload if r.get("error")]
    audited = [r for r in payload if r.get("shape")]
    assert errored and "timed out" in errored[0]["error"].lower(), payload
    assert [r["store"] for r in audited] == ["alpha"], payload


# ---- dropping an orphan registration (ADR-0003 remediation) ---------------

def _store_with(tmp_path, extra=()):
    from refmatrix.store import Store

    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir(exist_ok=True)
    s = Store(root)
    s.init()
    for name in extra:
        with s.with_partition(name):
            pass
    s.close()
    return root


def test_dropping_an_empty_orphan_removes_the_registration(tmp_path, monkeypatch):
    """The audit's remedy for five of the fleet's six orphans. It must exist:
    an audit that prescribes a repair the product cannot perform sends the
    operator to hand-edit a live catalog."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    root = _store_with(tmp_path, extra=["leaked"])
    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["partition", "drop", "leaked", "-y"])
    assert res.exit_code == 0, res.output

    res = CliRunner().invoke(cli_mod.main, ["partition", "list"])
    assert "leaked" not in res.output, res.output


def test_dropping_a_partition_that_holds_rows_is_REFUSED(tmp_path, monkeypatch):
    """Data loss by audit remedy is the failure mode here. A partition with
    rows is a merge decision, never a drop."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix.store import Store

    root = _store_with(tmp_path, extra=["holds-data"])
    s = Store(root)
    with s.with_partition("holds-data"):
        s.upsert_entity(kind="doc", name="a-doc", path="/tmp/a-doc.md")
    s.close()

    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["partition", "drop", "holds-data", "-y"])
    assert res.exit_code != 0
    assert "row" in res.output.lower(), res.output
    res = CliRunner().invoke(cli_mod.main, ["partition", "list"])
    assert "holds-data" in res.output


def test_dropping_the_ACTIVE_partition_is_refused(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    root = _store_with(tmp_path)
    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["partition", "drop", "proj", "-y"])
    assert res.exit_code != 0
    assert "active" in res.output.lower(), res.output


def test_dropping_a_partition_with_vectors_on_disk_is_refused(tmp_path, monkeypatch):
    """Vectors are the second catalog. Dropping the registration while the
    Lance dataset stays would MANUFACTURE an orphan-vectors finding — the audit
    creating the drift it reports."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    root = _store_with(tmp_path, extra=["has-vectors"])
    (root / "vectors" / "has-vectors").mkdir(parents=True)
    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["partition", "drop", "has-vectors", "-y"])
    assert res.exit_code != 0
    assert "vector" in res.output.lower(), res.output


# ---- missing-sessions severity depends on whether transcripts EXIST -------
#
# Found by remediating: orderly and atldb read `drift` for a condition they
# cannot fix — their ~/.claude/projects/<slug>/ directories hold a `memory/`
# subdir and ZERO .jsonl files, so there is no session history to ingest. A
# store that reads drift forever for an unfixable condition trains the signal
# away, which is the same argument ADR-0003 uses for `sessions-unembedded`.

def test_missing_sessions_is_drift_when_transcripts_exist():
    """The remediable case: history exists and was never ingested."""
    f = _facts()
    f["partitions"] = [p for p in f["partitions"] if p["name"] == "refmatrix"]
    f["row_counts"].pop("sessions-refmatrix")
    f["sessions_available"] = True
    out = pt.audit(**f)
    finding = next(x for x in out["findings"] if x["kind"] == "missing-sessions")
    assert finding["severity"] == "drift"
    assert "rmx session ingest" in finding["remedy"]
    assert out["shape"] == "drift"


def test_missing_sessions_is_info_when_the_project_has_no_transcripts():
    """orderly / atldb: nothing to ingest, so nothing to repair — and a store
    in that state is CANONICAL, not drifted."""
    f = _facts()
    f["partitions"] = [p for p in f["partitions"] if p["name"] == "refmatrix"]
    f["row_counts"].pop("sessions-refmatrix")
    f["sessions_available"] = False
    out = pt.audit(**f)
    finding = next(x for x in out["findings"] if x["kind"] == "missing-sessions")
    assert finding["severity"] == "info"
    assert "no session transcripts" in finding["detail"].lower()
    assert out["shape"] == "canonical", out["findings"]


def test_sessions_available_defaults_to_true_so_a_caller_that_cannot_tell_reports_drift():
    """A gather path that cannot determine the fact must NOT silently downgrade
    a real drift to info — the conservative default is the remediable one."""
    f = _facts()
    f["partitions"] = [p for p in f["partitions"] if p["name"] == "refmatrix"]
    f["row_counts"].pop("sessions-refmatrix")
    f.pop("sessions_available", None)
    out = pt.audit(**f)
    finding = next(x for x in out["findings"] if x["kind"] == "missing-sessions")
    assert finding["severity"] == "drift"


def test_the_op_reports_whether_transcripts_exist(tmp_path, monkeypatch):
    """The gather side must supply the fact, using the SAME slug encoding
    `rmx session ingest` uses — otherwise the audit and its own remedy disagree
    about where transcripts live."""
    from refmatrix import daemon as dm
    from refmatrix.store import Store

    home = tmp_path / "home"
    proj = tmp_path / "proj"
    root = proj / ".refmatrix"
    proj.mkdir()
    (home / ".claude" / "projects").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    s = Store(root)
    s.init()
    d = dm.Daemon(root)
    d.store = s
    try:
        out = dm.OPS["partition_audit"](d, {})
        assert out["sessions_available"] is False
        finding = next(f for f in out["findings"] if f["kind"] == "missing-sessions")
        assert finding["severity"] == "info"

        slug = str(proj).replace("/", "-").replace("_", "-")
        tdir = home / ".claude" / "projects" / slug
        tdir.mkdir(parents=True)
        (tdir / "a-session.jsonl").write_text("{}\n")

        out = dm.OPS["partition_audit"](d, {})
        assert out["sessions_available"] is True
        finding = next(f for f in out["findings"] if f["kind"] == "missing-sessions")
        assert finding["severity"] == "drift"
    finally:
        s.close()
