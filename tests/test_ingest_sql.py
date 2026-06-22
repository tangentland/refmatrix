"""`.sql` (SQL / PL/pgSQL) ingest is bulk-applied and mtime-gated.

The pass parses changed `.sql` files in parallel, applies them in one
`bulk_apply_records` batch, and gates on a dedicated `sqlsem:<abs>` marker so an
unchanged re-ingest does no parse/apply work. `.sql` is in CODE_EXTS (the tree
pass also tracks it under its real path), so the gate needs its own marker key —
these tests lock that in, plus the DDL/body extraction shape.

Run against an in-process Store + `_ingest_path_inner` — no daemon.
"""
from __future__ import annotations

import os
from pathlib import Path

import refmatrix.ingest as ing
from refmatrix.ingest import _build_sql_record, _ingest_path_inner
from refmatrix.store import Store

SQL = """\
-- a comment mentioning CREATE TABLE ghost (must be ignored)
CREATE SCHEMA app;

CREATE TABLE app.users (
    id serial PRIMARY KEY,
    email text NOT NULL
);

CREATE TYPE app.mood AS ENUM ('happy', 'sad');

CREATE OR REPLACE VIEW active_users AS
    SELECT * FROM app.users WHERE active;

CREATE OR REPLACE FUNCTION app.touch_user(uid int)
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE app.users SET seen = now() WHERE id = uid;
    PERFORM log_event(uid);
    INSERT INTO audit_log SELECT * FROM app.users;
END;
$$;

CREATE INDEX idx_users_email ON app.users (email);
"""


def test_sql_extracts_ddl_body_refs_and_calls(tmp_path):
    p = Path(tmp_path) / "spec.sql"
    p.write_text(SQL)
    rec = _build_sql_record(p, Path(tmp_path))
    assert rec is not None
    defined = {
        se["meta"]["kind"]: se["qname"].split("::")[-1]
        for se in rec.sub_entities
    }
    # one of each object kind, schema-qualification stripped to the leaf
    assert defined["table"] == "users"
    assert defined["view"] == "active_users"
    assert defined["type"] == "mood"
    assert defined["function"] == "touch_user"
    assert defined["index"] == "idx_users_email"
    assert defined["schema"] == "app"

    links = {(op["linkage"], op["src"], op["dst"])
             for op in rec.ops if op["op"] == "link"}
    fn = "@sub:code/spec.sql::touch_user"
    # body table references -> mentions (FROM/UPDATE/INTO), builtins skipped
    assert ("mentions", "@concept:users", fn) in links
    assert ("mentions", "@concept:audit_log", fn) in links
    # nested call -> calls; `now()`/`PERFORM` are stop-listed
    assert ("calls", "@concept:log_event", fn) in links
    assert not any(s == "@concept:now" for _, s, _ in links)
    # the commented-out ghost table never became a concept
    assert not any(d.endswith("::ghost") for _, _, d in links)


def test_sql_ingests_then_gates_unchanged_and_reparses_on_touch(
    tmp_path, monkeypatch
):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.sql").write_text(SQL)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    with s.with_partition("sqltest"):
        _ingest_path_inner(s, proj, source="tree")
        n = s._connect().execute("SELECT count(*) FROM entities").fetchone()[0]
        assert n > 0

        calls = {"n": 0}
        orig = ing._build_sql_record

        def spy(fp, root):
            calls["n"] += 1
            return orig(fp, root)

        monkeypatch.setattr(ing, "_build_sql_record", spy)
        _ingest_path_inner(s, proj, source="tree")
        assert calls["n"] == 0, "unchanged .sql re-parsed (gate broken)"

        st = (proj / "spec.sql").stat()
        os.utime(proj / "spec.sql", (st.st_atime + 5, st.st_mtime + 5))
        _ingest_path_inner(s, proj, source="tree")
        assert calls["n"] == 1, "touched .sql not re-parsed"
    s.close()
