"""bug-065: an as-memory ingest IMPLIES memory vectors.

The bridge (`ingest-gmd --as-memory`) inserts `kind=memory` rows WITHOUT
vectors, and nothing drained them — `finalize_save_state` had zero occurrences
of `embed`. So every save-state produced durable, unreachable memories. Hit
twice on 2026-10-01: once by me (four new memories; `rmx memory search "verify
fix reachable from master"` returned NO matches while `memory get` found every
row) and once independently by a ch-bsd run whose distinctive phrase returned
five OTHER documents with scores identical to the pre-ingest run.

THE ACCEPTANCE IS A RECALL, NOT A `memory get`. That is the whole bug: both of
us confirmed "saved" with `memory get` and reported success on a half-save.

AND THE RULE BELONGS TO THE WRITE, NOT TO ONE CALLER. The first cut of this fix
put the drain in `finalize_save_state`, which made `rmx save-state` correct and
left `rmx ingest-gmd --as-memory` — the SessionStart catch-up hook, `rmx memory
sync-disk`, any by-hand run — still writing vectorless rows. The drain now
lives at the bridge's own completion point, so every route gets it
(`feedback_main_path_must_exercise_core_mechanisms`). Both routes are covered
below: the daemon op AND the in-process fallback, because a rule that holds
only when a daemon happens to be up is not a rule.
"""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import handoff, verbs
from refmatrix.ingest_gmd import (MEMORY_EMBED_DRAIN_BATCHES,
                                  drain_memory_vectors,
                                  render_memory_embed_line)
from refmatrix.store import Store

_HAS_DENSE = (
    importlib.util.find_spec("sentence_transformers") is not None
    and importlib.util.find_spec("lance") is not None
)

GMD = ('---\ngmd: "0.1"\nid: {id}\ntitle: "{id}"\ntags: [project]\n'
       'metadata:\n  type: feedback\n---\n# {id} {{#root}}\n\n{body}\n')


_READER = """
import json, sys
from pathlib import Path
from refmatrix.store import Store
root, part, what, arg = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
s = Store(root, read_only=True, partition=part)
try:
    if what == "pending":
        out = [list(r) for r in s.pending_embeddings(kinds=["memory"])]
    else:
        row = s._connect().execute("SELECT name FROM entities WHERE id = ?", (int(arg),)).fetchone()
        out = row[0] if row else None
finally:
    s.close()
print(json.dumps(out))
"""


def _read_snapshot(root: Path, part: str, what: str, arg: str = "") -> object:
    """Read the daemon's freshly forced snapshot from a SEPARATE process — what a CLI read does.

    bug-110: these tests opened `Store(root)` on the live writer slot while the fixture's daemon
    held it. That only worked because the snapshot's in-process copy had dropped the daemon's
    DuckDB lock, and it failed ~1 run in 5 on the WAL lock instead (bug-108). With the lock held
    the open is refused every time. A reader inside THIS process saw a stale snapshot even after
    a forced one (bug-112, mechanism not yet named), so the read runs in a child, as the CLI's
    does."""
    import json
    import os
    import subprocess
    import sys
    r = dm.call(root, "snapshot", {"force": True}, timeout=120)
    assert r.get("ok") and "snapshot_path" in (r.get("result") or {}), r
    proc = subprocess.run([sys.executable, "-c", _READER, str(root), part, what, arg],
                          capture_output=True, text=True, timeout=120, env=dict(os.environ))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])

@pytest.fixture
def live(monkeypatch):
    """A REAL spawned daemon: the route `rmx save-state` and the SessionStart
    hook actually take."""
    base = Path(tempfile.mkdtemp(prefix="rmx065-"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def quiet(monkeypatch):
    """A store with NO daemon — the in-process fallback branch. `dm.ping` is
    not patched: there is genuinely nothing listening, so the code takes the
    in-proc path for the real reason rather than a faked one."""
    base = Path(tempfile.mkdtemp(prefix="rmx065q-"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    Store(root).init()
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    shutil.rmtree(base, ignore_errors=True)


def _memdir(base: Path, **files: str) -> Path:
    memdir = base / "memory"
    memdir.mkdir(exist_ok=True)
    for name, body in files.items():
        (memdir / f"{name}.md").write_text(GMD.format(id=name, body=body))
    return memdir


def _finalize(base: Path, root: Path, memdir: Path, target: str) -> dict:
    res = {"target": str(memdir / f"{target}.md"), "memdir": str(memdir),
           "dry_run": False, "promoted": None}
    return handoff.finalize_save_state(None, root, res, repo=base / "proj",
                                       lint=False)


# ---- the acceptance: a RECALL, on a real daemon with the real model -------

@pytest.mark.skipif(not _HAS_DENSE, reason="needs the [dense] extra")
@pytest.mark.timeout(900)
def test_a_memory_save_state_wrote_is_found_by_recall(live):
    """The standing verification rule this bug implies: write a memory holding
    a phrase unique to it, save state, and require recall to RANK IT FIRST.
    `memory get` would have passed throughout the bug."""
    base, root = live
    phrase = "sandblasted ferrocement bellwether"
    memdir = _memdir(base, savestate_recallme=(
        f"The resume point is a {phrase} with nothing else like it."))

    fin = _finalize(base, root, memdir, "savestate_recallme")
    assert fin["sync"]["error"] is None, fin["sync"]
    assert fin["embed"] is not None, "the bridge ran no embed at all"
    assert fin["embed"]["error"] is None, fin["embed"]
    assert fin["embed"]["embedded"] >= 1, fin["embed"]

    part = verbs.memory_partition(root)
    r = dm.call(root, "memory_recall",
                {"query": phrase, "k": 5, "partition": part}, timeout=300)
    assert r.get("ok"), r
    hits = (r.get("result") or {}).get("hits") or []
    assert hits, f"recall found nothing for a phrase unique to the memory: {r}"

    # Resolve the top hit's id to a name — the id alone cannot fail this test
    # for the right reason.
    name = _read_snapshot(root, part, "name", str(int(hits[0]["id"])))
    assert name == "savestate_recallme", (name, hits)


@pytest.mark.skipif(not _HAS_DENSE, reason="needs the [dense] extra")
@pytest.mark.timeout(900)
def test_no_memory_row_is_left_without_a_vector(live):
    """The structural property behind the recall: after the bridge, the memory
    embed queue for that partition is EMPTY. A row still pending is a memory
    recall cannot reach."""
    base, root = live
    memdir = _memdir(base, savestate_a="alpha body", other_note="beta body")

    fin = _finalize(base, root, memdir, "savestate_a")
    assert fin["embed"]["error"] is None, fin["embed"]

    part = verbs.memory_partition(root)
    pending = _read_snapshot(root, part, "pending")
    assert pending == [], f"{len(pending)} memory row(s) have no vector"


# ---- EVERY as-memory route, not just save-state --------------------------

@pytest.mark.skipif(not _HAS_DENSE, reason="needs the [dense] extra")
@pytest.mark.timeout(900)
def test_a_bare_ingest_gmd_as_memory_embeds_too(live):
    """The route the SessionStart catch-up hook and `rmx memory sync-disk`
    take. The first cut of this fix covered save-state ONLY, so this command
    kept writing vectorless rows — the whole reason the drain moved down to
    the bridge."""
    base, root = live
    memdir = _memdir(base, hook_written_note="a note the hook bridged")
    monkeypatch_free = CliRunner().invoke(
        cli_mod.main, ["ingest-gmd", "--as-memory", str(memdir)])
    assert monkeypatch_free.exit_code == 0, monkeypatch_free.output
    assert "memory embed" in monkeypatch_free.output, monkeypatch_free.output

    part = verbs.memory_partition(root)
    assert _read_snapshot(root, part, "pending") == []


def test_a_non_memory_ingest_gmd_does_not_embed(quiet, monkeypatch):
    """`--as-memory` implies the drain; a plain GMD doc ingest must not pay
    for it. The gate is `as_memory`, not "ingest-gmd ran"."""
    base, root = quiet
    docs = base / "docs"
    docs.mkdir()
    (docs / "d.md").write_text(GMD.format(id="plain_doc", body="text"))
    seen: list = []
    monkeypatch.setattr(dm, "_op_embed",
                        lambda d, a: seen.append(a) or {"embedded": 0,
                                                        "remaining": 0})
    rep = cli_mod._ingest_gmd_sync([docs], as_memory=False)
    assert seen == [], seen
    assert "memory embed" not in rep


def test_the_in_process_route_embeds_as_well(quiet, monkeypatch):
    """Daemon down. The same drain, through `_ingest_gmd_sync`'s in-proc
    branch — a rule that holds only when a daemon is up is not a rule."""
    base, root = quiet
    memdir = _memdir(base, inproc_note="body")
    seen: list = []

    def _record(d, args):
        seen.append(args)
        return {"embedded": 1, "remaining": 0, "kinds": args.get("kinds")}

    monkeypatch.setattr(dm, "_op_embed", _record)
    rep, st = cli_mod._ingest_gmd_sync([memdir], as_memory=True,
                                        with_stats=True)
    assert seen, "the in-process branch wrote memory rows and embedded nothing"
    assert seen[0]["kinds"] == ["memory"], seen[0]
    assert st["embed"]["embedded"] == 1, st
    assert "memory embed" in rep, rep


# ---- bounded, counted, said (no model needed) ----------------------------

def test_the_drain_is_bounded_and_says_what_it_left():
    """A store thousands of vectors behind must not be silently re-embedded
    inside a bridge call. The cap is hit, the remainder is reported, and the
    line names the command that finishes the job."""
    calls = {"n": 0}

    def _never_done(args):
        calls["n"] += 1
        return {"embedded": 1, "remaining": 9999}

    out = drain_memory_vectors(_never_done, partition="p")
    assert out["capped"] is True, out
    assert calls["n"] == MEMORY_EMBED_DRAIN_BATCHES
    assert out["remaining"] == 9999
    assert out["error"] is None
    line = render_memory_embed_line(out)
    assert "capped" in line and "rmx embed --kinds memory" in line


def test_the_remaining_count_is_one_the_real_producer_can_emit(tmp_path):
    """ch-bsd r1 #b-1: the test above feeds `remaining: 9999`, and the REAL
    producer could only ever return 0 or 1 — `_op_embed` reported
    `len(pending_embeddings(limit=1))`. The fake was the blindfold, so the
    capped line told operators "1 still without vectors" with thousands
    outstanding. Driven against the real store method, no fake."""
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    try:
        for i in range(5):
            s.upsert_entity("memory", f"m{i}")
        pend = s.pending_embeddings(kinds=["memory"])
        assert len(pend) == 5, pend
        # The bug, pinned: a capped LIST is not a count.
        assert len(s.pending_embeddings(kinds=["memory"], limit=1)) == 1
        # The fix: the count is the count.
        assert s.pending_embeddings_count(kinds=["memory"]) == 5
        # And it respects the same predicate as the list it counts.
        assert s.pending_embeddings_count() >= 5
        assert s.pending_embeddings_count(kinds=["code"]) == 0
    finally:
        s.close()


def test_op_embed_reports_a_real_remaining_count(tmp_path, monkeypatch):
    """The producer, not the helper: `_op_embed`'s `remaining` has to be the
    number the renderer spends. Asserted over a store with more pending rows
    than one batch, so a 0-or-1 answer is visibly wrong."""
    from refmatrix.daemon import Daemon, _op_embed
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    for i in range(7):
        s.upsert_entity("memory", f"m{i}")

    class _FakeEmb:
        """Only the model is faked. `_op_embed`'s own arithmetic — the
        `remaining` under test — runs for real."""
        dim = 3
        model_name = "fake"

        def embed_texts(self, texts):
            import numpy as _np
            return _np.zeros((len(texts), 3), dtype="float32")

    d = Daemon(tmp_path / ".refmatrix")
    d.store = s
    monkeypatch.setattr(d, "_embedder", lambda: _FakeEmb(), raising=False)
    # NO `upsert_vector` stub (ch-bsd r3 #s-2, the twin of r2 #s-1). The stub
    # pinned `remaining` at 7 so `> 1` could not tell a count measured AFTER
    # the write from one sampled before it. Unstubbed, the two vectors land
    # and the count must move to exactly 5.
    try:
        res = _op_embed(d, {"kinds": ["memory"], "limit": 2})
        assert res.get("ok") is not False, res
        assert res["embedded"] == 2, res
        assert res["remaining"] == 5, (
            f"remaining={res['remaining']} — not re-measured after the write, "
            f"or a 0-or-1 boolean wearing a count's clothes (#b-1)")
        assert res["remaining"] == s.pending_embeddings_count(kinds=["memory"])
    finally:
        s.close()


def test_a_pass_that_makes_no_progress_stops_instead_of_spinning():
    """`embedded == 0` with rows still pending is a pass that cannot advance;
    burning the whole budget on it would turn a stuck embedder into eight
    timeouts inside a handoff."""
    calls = {"n": 0}

    def _stuck(args):
        calls["n"] += 1
        return {"embedded": 0, "remaining": 5}

    out = drain_memory_vectors(_stuck, partition="p")
    assert calls["n"] == 1, calls
    assert out["capped"] is False
    assert out["remaining"] == 5


def test_an_embed_failure_is_returned_never_swallowed():
    out = drain_memory_vectors(lambda args: {"ok": False, "error": "no model"},
                               partition="p")
    assert out["error"] == "no model", out
    assert out["embedded"] == 0
    assert "FAILED" in render_memory_embed_line(out)
    assert "rmx embed --kinds memory" in render_memory_embed_line(out)


def test_a_raising_embed_is_reported_as_an_error():
    def _boom(args):
        raise RuntimeError("lance exploded")

    out = drain_memory_vectors(_boom, partition="p")
    assert "RuntimeError" in (out["error"] or ""), out
    assert "lance exploded" in (out["error"] or "")


def test_a_clean_run_with_nothing_to_do_says_nothing():
    """Every unchanged bridge call would otherwise add a line that means
    nothing, and a report people skim is a report people stop reading."""
    out = drain_memory_vectors(lambda args: {"embedded": 0, "remaining": 0},
                               partition="p")
    assert out["error"] is None and out["embedded"] == 0
    assert render_memory_embed_line(out) == ""
    assert render_memory_embed_line(None) == ""


def test_the_drain_targets_the_partition_the_bridge_wrote_to(quiet, monkeypatch):
    """`_sync_memory_dir` resolves the memory partition by three different
    rules; embedding a DIFFERENT one is `project_embed_partition_routing_fix`'s
    old defect — a successful-looking run with zero vectors where recall
    reads."""
    base, root = quiet
    memdir = _memdir(base, savestate_part="body here")
    seen: list = []

    def _record(d, args):
        seen.append(args.get("partition"))
        return {"embedded": 0, "remaining": 0, "kinds": args.get("kinds")}

    monkeypatch.setattr(dm, "_op_embed", _record)
    fin = _finalize(base, root, memdir, "savestate_part")

    assert fin["sync"]["partition"], fin["sync"]
    assert seen and seen[0] == fin["sync"]["partition"], (seen, fin["sync"])
    assert fin["embed"]["partition"] == fin["sync"]["partition"]


def test_a_dry_run_and_sync_false_embed_nothing(quiet, monkeypatch):
    base, root = quiet
    memdir = _memdir(base, savestate_dry="body")
    called = {"n": 0}
    monkeypatch.setattr(dm, "_op_embed",
                        lambda d, a: called.__setitem__("n", called["n"] + 1))

    res = {"target": str(memdir / "savestate_dry.md"), "memdir": str(memdir),
           "dry_run": False, "promoted": None}
    fin = handoff.finalize_save_state(None, root, res, repo=base / "proj",
                                      lint=False, sync=False)
    assert fin["embed"] is None and called["n"] == 0
    fin = handoff.finalize_save_state(None, root, dict(res, dry_run=True),
                                      repo=base / "proj", lint=False)
    assert fin["embed"] is None and called["n"] == 0


# ---- the outcome reaches every caller ------------------------------------

def test_the_save_state_verb_carries_the_embed_result(quiet, monkeypatch):
    """MCP and the CLI read the same dict. A count computed and not returned
    is the shape bsd-plan2-r4 #s-2 found on `filed_subject_error`."""
    base, root = quiet
    monkeypatch.setattr(dm, "_op_embed",
                        lambda d, args: {"embedded": 2, "remaining": 0,
                                         "kinds": args.get("kinds")})
    memdir = _memdir(base, savestate_verb="body")
    res = verbs.save_state(root, memory_dir=str(memdir), lint=False,
                           promote=False)
    assert res.get("embed") is not None, sorted(res)
    assert res["embed"]["embedded"] == 2, res["embed"]


def test_the_command_says_so_when_the_embed_FAILED(quiet, monkeypatch):
    """A memory that is SAVED and unreachable must not pass quietly, and the
    line has to name the command that fixes it. Driven through the real `rmx
    save-state`, not by re-running its branch."""
    base, root = quiet
    monkeypatch.setattr(dm, "_op_embed",
                        lambda d, args: {"ok": False, "error": "no model"})
    memdir = _memdir(base, savestate_failrender="body")
    monkeypatch.chdir(base / "proj")
    r = CliRunner().invoke(cli_mod.main, [
        "save-state", "--memory-dir", str(memdir), "--no-lint",
        "--no-promote"])
    assert r.exit_code == 0, r.output
    assert "memory embed FAILED" in r.output, r.output
    assert "rmx embed --kinds memory" in r.output, r.output


def test_save_state_command_renders_the_embed_line(quiet, monkeypatch):
    base, root = quiet
    monkeypatch.setattr(dm, "_op_embed",
                        lambda d, args: {"embedded": 3, "remaining": 0,
                                         "kinds": args.get("kinds")})
    memdir = _memdir(base, savestate_render="body")
    monkeypatch.chdir(base / "proj")
    r = CliRunner().invoke(cli_mod.main, [
        "save-state", "--memory-dir", str(memdir), "--no-lint",
        "--no-promote"])
    assert r.exit_code == 0, r.output
    assert "3 row(s) now reachable by recall" in r.output, r.output
    # EXACTLY once. The first cut printed it twice — the bridge appends the
    # line to the report that save-state echoes, and the renderer printed it
    # again from `fin["embed"]`. This assertion said only "appears", so it
    # passed straight through the duplication; I saw it in this session's own
    # save-state output, not in a test.
    assert r.output.count("memory embed") == 1, (
        f"{r.output.count('memory embed')} embed lines:\n{r.output}")


def test_the_capped_branch_reports_a_real_count_from_the_real_producer(tmp_path,
                                                                       monkeypatch):
    """The branch whose number was WRONG, driven end to end with no fake count.

    ch-bsd r1 #b-1 lived specifically in the CAPPED path: `remaining` came from
    `len(pending_embeddings(limit=1))`, so the one line an operator acts on
    ("N still without vectors") could only say 0 or 1. Every other test here
    either does not reach the cap or reaches it through a fake. This one drives
    `drain_memory_vectors` with the REAL `_op_embed` and a deliberately tiny
    budget (`batches=2, limit=1`) so the cap is hit on a small store, and then
    asserts the reported remainder equals what the store actually owes.

    Only the MODEL is faked. The count, the loop, the cap and the rendered line
    are all real.
    """
    from refmatrix.daemon import Daemon, _op_embed
    from refmatrix.ingest_gmd import drain_memory_vectors, render_memory_embed_line
    from refmatrix.store import Store

    s = Store(tmp_path / ".refmatrix")
    s.init()
    for i in range(9):
        s.upsert_entity("memory", f"m{i}")

    class _FakeEmb:
        dim = 3
        model_name = "fake"

        def embed_texts(self, texts):
            import numpy as _np
            return _np.zeros((len(texts), 3), dtype="float32")

    d = Daemon(tmp_path / ".refmatrix")
    d.store = s
    monkeypatch.setattr(d, "_embedder", lambda: _FakeEmb(), raising=False)
    # NO `upsert_vector` stub (ch-bsd r2 #s-1). Stubbing the write pinned
    # `remaining` at 9, so the assertion could not tell a RE-MEASURED count
    # from one sampled before the loop — the exact confusion #b-1 was about.
    # Unstubbed, the vectors really land and `remaining` tracks real progress,
    # which is strictly stronger and one fewer double.
    try:
        out = drain_memory_vectors(lambda a: _op_embed(d, a),
                                   partition=s._partition_name,
                                   batches=2, limit=1)
        assert out["capped"] is True, out
        assert out["error"] is None, out
        assert out["embedded"] == 2, out
        # 9 owed, 2 embedded under a 2-batch cap: the remainder is MEASURED
        # after the loop, not sampled before it.
        assert out["remaining"] == 7, out
        assert out["remaining"] == s.pending_embeddings_count(kinds=["memory"])
        line = render_memory_embed_line(out)
        assert "7 still without vectors" in line, line
        assert "rmx embed --kinds memory" in line
    finally:
        s.close()
