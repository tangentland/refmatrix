"""Tests for the append-only fact log (RMX_LOG=1) + dump/rebuild round-trip."""
from __future__ import annotations

import json
import os

import pytest

from refmatrix.store import Store


@pytest.fixture
def log_on(monkeypatch):
    monkeypatch.setenv("RMX_LOG", "1")
    yield


@pytest.fixture
def log_off(monkeypatch):
    monkeypatch.setenv("RMX_LOG", "0")
    yield


def _seed(s: Store) -> dict:
    parser = s.add_concept("parser", description="parses input", protected=True)
    tokenizer = s.add_concept("tokenizer")
    foo = s.upsert_entity(kind="code", name="src/foo.py", tldr="foo module")
    lex = s.upsert_entity(kind="code", name="src/lex.py")
    readme = s.upsert_entity(kind="doc", name="README.md")
    s.link("defines", parser, foo, weight=0.9)
    s.link("mentions", parser, readme)
    s.link("defines", tokenizer, lex)
    s.link_many("related_to", parser, [lex, foo])
    s.add_evidence("mentions", parser, readme, file="README.md", line=3)
    return {
        "parser": parser, "tokenizer": tokenizer,
        "foo": foo, "lex": lex, "readme": readme,
    }


def _snapshot(s: Store) -> dict:
    """Return a name-keyed view of catalog state for equality checks."""
    con = s._connect()
    entities = sorted(
        (r["kind"], r["name"], r["path"], r["tldr"], r["protected"], r["noise"])
        for r in con.execute(
            "SELECT kind, name, path, tldr, protected, noise FROM entities"
        )
    )
    links = sorted(
        (lt, c_name, e_kind, e_name, weight)
        for lt, c_name, e_kind, e_name, weight in con.execute(
            """
            SELECT lt.name, c.name, e.kind, e.name, el.weight
            FROM entity_links el
            JOIN linkage_types lt ON lt.id = el.linkage_id
            JOIN entities c ON c.id = el.concept_id
            JOIN entities e ON e.id = el.entity_id
            """
        )
    )
    evidence = sorted(
        (lt, c_name, e_kind, e_name, file, line)
        for lt, c_name, e_kind, e_name, file, line in con.execute(
            """
            SELECT lt.name, c.name, e.kind, e.name, ev.file, ev.line
            FROM linkage_evidence ev
            JOIN linkage_types lt ON lt.id = ev.linkage_id
            JOIN entities c ON c.id = ev.concept_id
            JOIN entities e ON e.id = ev.entity_id
            """
        )
    )
    return {"entities": entities, "links": links, "evidence": evidence}


def test_log_disabled_writes_nothing(tmp_path, log_off):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _seed(s)
    s.close()
    assert not (tmp_path / ".refmatrix" / "facts.log").exists()


def test_log_writes_link_events(tmp_path, log_on):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _seed(s)
    s.close()
    log = tmp_path / ".refmatrix" / "facts.log"
    assert log.exists()
    events = [json.loads(l) for l in log.read_text().splitlines() if l]
    ops = [e["op"] for e in events]
    assert "entity" in ops
    assert "link" in ops
    assert "evidence" in ops
    assert "protect" in ops  # parser is protected
    # Links carry name-keyed refs, not branch-local IDs.
    link_events = [e for e in events if e["op"] == "link"]
    assert any(
        e["linkage"] == "defines" and e["c"] == "parser" and e["e"] == "src/foo.py"
        for e in link_events
    )


def test_unlink_logs_tombstone(tmp_path, log_on):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    ids = _seed(s)
    s.unlink("mentions", ids["parser"], ids["readme"])
    s.close()
    log = tmp_path / ".refmatrix" / "facts.log"
    events = [json.loads(l) for l in log.read_text().splitlines() if l]
    assert any(
        e["op"] == "unlink" and e["c"] == "parser" and e["e"] == "README.md"
        for e in events
    )


def test_dump_rebuild_round_trip(tmp_path, log_off):
    """Build a catalog without logging, dump it to a log, wipe, replay, and
    confirm the rebuilt catalog is equivalent (name-keyed)."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    _seed(s)
    before = _snapshot(s)
    counts = s.dump_catalog_to_log()
    assert counts["entity"] == 5
    assert counts["link"] >= 4
    s.close()

    s2 = Store(tmp_path / ".refmatrix")
    s2.init()
    s2.rebuild_index_from_log()
    after = _snapshot(s2)
    s2.close()

    assert before == after


def test_purge_then_rebuild_drops_entity(tmp_path, log_on):
    """Purging an entity must produce a tombstone that survives replay."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    ids = _seed(s)
    s.purge_entity(ids["readme"])
    before = _snapshot(s)
    s.close()

    # Reuse the live log (already populated by mutations under RMX_LOG=1).
    s2 = Store(tmp_path / ".refmatrix")
    s2.init()
    s2.rebuild_index_from_log()
    after = _snapshot(s2)
    s2.close()

    assert before == after
    names = {(k, n) for k, n, *_ in after["entities"]}
    assert ("doc", "README.md") not in names


def test_protect_lww(tmp_path, log_on):
    """A later PROTECT=0 wins over an earlier PROTECT=1."""
    s = Store(tmp_path / ".refmatrix")
    s.init()
    s.add_concept("foo", protected=True)
    # Manually flip via SQL + log a later protect=0 event to simulate two
    # branches converging where the unprotect happens after the protect.
    s._connect().execute(
        "UPDATE entities SET protected=0 WHERE kind='concept' AND name='foo'"
    )
    s._connect().commit()
    s._log_event("protect", kind="concept", name="foo", value=0)
    s.close()

    s2 = Store(tmp_path / ".refmatrix")
    s2.init()
    s2.rebuild_index_from_log()
    row = s2._connect().execute(
        "SELECT protected FROM entities WHERE kind='concept' AND name='foo'"
    ).fetchone()
    s2.close()
    assert row["protected"] == 0
