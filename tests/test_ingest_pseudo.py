"""`.pseudo` ingest is bulk-applied and mtime-gated.

The pass parses changed `.pseudo` files in parallel, applies them in one
`bulk_apply_records` batch (not per-row `apply_record`), and gates on a
dedicated `pssem:<abs>` marker so an unchanged re-ingest does no parse/apply
work. `.pseudo` is in CODE_EXTS (the tree pass also tracks it under its real
path), so the gate needs its own marker key — these tests lock that in.

Run against an in-process Store + `_ingest_path_inner` — no daemon.
"""
from __future__ import annotations

import os

import refmatrix.ingest as ing
from refmatrix.ingest import _ingest_path_inner
from refmatrix.store import Store

PSEUDO = """\
UserRecord:
    id: UUID
    name: string
    role: Role

create_user(name: string, role: Role) -> UserRecord:
    validate_name(name)
    return UserRecord
"""


def test_pseudo_ingests_then_gates_unchanged_and_reparses_on_touch(
    tmp_path, monkeypatch
):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.pseudo").write_text(PSEUDO)
    s = Store(tmp_path / ".refmatrix")
    s.init()
    with s.with_partition("pseudotest"):
        _ingest_path_inner(s, proj, source="tree")
        # The pseudo pass created entities (the UserRecord/Role/create_user
        # graph rides on the bulk apply).
        n = s._connect().execute("SELECT count(*) FROM entities").fetchone()[0]
        assert n > 0

        # Gate: an unchanged re-ingest must not re-parse the .pseudo file.
        calls = {"n": 0}
        orig = ing._build_pseudo_record

        def spy(fp, root):
            calls["n"] += 1
            return orig(fp, root)

        monkeypatch.setattr(ing, "_build_pseudo_record", spy)
        _ingest_path_inner(s, proj, source="tree")
        assert calls["n"] == 0, "unchanged .pseudo re-parsed (gate broken)"

        # Touch -> the gate sees a newer mtime and re-parses exactly once.
        st = (proj / "spec.pseudo").stat()
        os.utime(proj / "spec.pseudo", (st.st_atime + 5, st.st_mtime + 5))
        _ingest_path_inner(s, proj, source="tree")
        assert calls["n"] == 1, "touched .pseudo not re-parsed"
    s.close()
