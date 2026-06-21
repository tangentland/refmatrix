"""memory reclassify — bulk mtype change via selector."""
from __future__ import annotations

from refmatrix.store import Store


def _seed(s):
    s.add_memory("project_session1_save_state", "a", mtype="project")
    s.add_memory("project_session2_save_state", "b", mtype="project")
    s.add_memory("feedback_save_state_means_handoff", "c", mtype="feedback")
    s.add_memory("project_other", "d", mtype="project")


def test_reclassify_by_like_and_from(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        r = s.reclassify_memories(to_mtype="session-state",
                                  like="*save_state*", from_mtype="project")
        assert r["changed"] == 2
        got = {m["name"]: m["mtype"] for m in s.iter_memories()}
        assert got["project_session1_save_state"] == "session-state"
        assert got["project_session2_save_state"] == "session-state"
        # feedback save_state untouched (from_mtype filter), other untouched
        assert got["feedback_save_state_means_handoff"] == "feedback"
        assert got["project_other"] == "project"
    s.close()


def test_reclassify_dry_run(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        # no from_mtype → all 3 names containing save_state match
        r = s.reclassify_memories(to_mtype="x", like="*save_state*", dry_run=True)
        assert r["matched"] == 3 and r["changed"] == 0 and r["dry_run"] is True
        # nothing changed
        assert all(m["mtype"] != "x" for m in s.iter_memories())
    s.close()


def test_reclassify_by_names(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        r = s.reclassify_memories(to_mtype="session-state",
                                  names=["project_session1_save_state"])
        assert r["changed"] == 1
        got = {m["name"]: m["mtype"] for m in s.iter_memories()}
        assert got["project_session1_save_state"] == "session-state"
        assert got["project_session2_save_state"] == "project"
    s.close()


def test_memory_facets(tmp_path):
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        s.add_memory("a", "x", mtype="feedback", tags=["tone", "git-policy"])
        s.add_memory("b", "y", mtype="project", tags=["tone"])
        s.add_memory("c", "z", mtype="feedback")
        f = s.memory_facets()
        assert f["mtypes"] == {"feedback": 2, "project": 1}
        assert f["tags"]["tone"] == 2 and f["tags"]["git-policy"] == 1
        assert f["total"] == 3
    s.close()


def test_reclassify_re_logs_for_replay(tmp_path):
    """The mtype change must survive a rebuild-from-log."""
    s = Store(tmp_path / ".refmatrix"); s.init()
    with s.with_partition("p"):
        _seed(s)
        s.reclassify_memories(to_mtype="session-state", like="*save_state*",
                              from_mtype="project")
        # the log should carry the new mtype as the latest record
        import json
        lines = (s.root / "facts.log").read_text().splitlines()
        recs = [json.loads(ln) for ln in lines if ln.strip()]
        sess = [r for r in recs if r.get("op") == "memory_content"
                and r.get("name") == "project_session1_save_state"]
        assert sess and sess[-1]["mtype"] == "session-state"
    s.close()
