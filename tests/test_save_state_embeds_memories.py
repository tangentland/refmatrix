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
    s = Store(root)
    try:
        with s.with_partition(part):
            row = s._connect().execute(
                "SELECT name FROM entities WHERE id = ?",
                (int(hits[0]["id"]),)).fetchone()
    finally:
        s.close()
    assert row and row[0] == "savestate_recallme", (row, hits)


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
    s = Store(root)
    try:
        with s.with_partition(part):
            pending = s.pending_embeddings(kinds=["memory"])
    finally:
        s.close()
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
    s = Store(root)
    try:
        with s.with_partition(part):
            assert s.pending_embeddings(kinds=["memory"]) == []
    finally:
        s.close()


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
