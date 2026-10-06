"""Task 15.4: the passes that never stamp are NAMED, not assumed fresh.

`rmx reingest` runs five passes. Three stamped (`ingest`, `semantic`, `gmd`);
`sessions`, `embed` and `pagerank` never did. So on 2026-10-06 this project's
own `refmatrix` partition carried exactly ONE derive row (`gmd`), and
"the graph was derived by 0.75.0" was a claim about one pass out of five while
the other four were invisible rather than fresh — the same shape as bug-039,
one level down: a surface that reads complete because what is absent from it
has no name.

Two halves under test, and the second is the one that cannot be skipped:

1. The remaining passes stamp, at the END of a successful pass, so a crashed
   pass leaves the previous stamp standing.
2. `derive_status()` says which passes it EXPECTED and which of them have no
   stamp — per PARTITION KIND, because a sessions partition never runs `gmd`
   and a memory partition never runs `sessions`, and reporting a pass a
   partition can never run is a false positive with the same cost as the one
   task 15.1 removed.

An unstamped pass is NOT `behind_code` and MUST NOT reach the hub alert. On the
release that ships this, every store in the fleet is missing four of five
stamps; a gate that fired on that would alert all eight rows once and be turned
off forever (ch-bsd plan-12 #b-3, measured). Criterion 5 below is that gate's
only defence, which is why it asserts the hub's actual input and not a dict
this test built.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix import __version__ as RUNNING
from refmatrix.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / ".refmatrix")
    s.init()
    yield s
    s.close()


def _track(s: Store, tmp_path: Path, name: str = "a.md") -> Path:
    """Make the store look ingested-into: one tracked file."""
    f = tmp_path / name
    f.write_text(f"# {name}\n")
    s.mark_tracked(str(f.resolve()), f.stat().st_mtime)
    return f


# ---- the expected set is per partition KIND (criterion 4) ----------------

def test_partition_kind_reads_the_name_and_the_root():
    from refmatrix.store import partition_kind

    assert partition_kind("refmatrix") == "project"
    assert partition_kind("sessions-refmatrix") == "sessions"
    assert partition_kind("memory-refmatrix") == "memory"
    # The user-level global store holds memories ONLY and its partition is
    # named `global`, not `memory-*` — classifying it as a project partition
    # would report it missing `ingest`, a pass it is structurally forbidden to
    # run (`is_memory_only_root`).
    assert partition_kind("global") == "memory"


def test_a_memory_only_root_is_a_memory_partition_whatever_it_is_called():
    from refmatrix.store import partition_kind

    assert partition_kind("anything", root=Path.home() / ".refmatrix") == "memory"


def test_each_kind_expects_only_the_passes_it_can_run():
    from refmatrix.store import derive_expected_passes

    project = set(derive_expected_passes("refmatrix"))
    sessions = set(derive_expected_passes("sessions-refmatrix"))
    memory = set(derive_expected_passes("memory-refmatrix"))

    assert project == {"ingest", "semantic", "gmd", "embed", "pagerank"}
    # A sessions partition has no repo tree and no curated memory dir: its
    # cards come from the sessions pass.
    assert "gmd" not in sessions
    assert "ingest" not in sessions
    assert "sessions" in sessions
    # A memory partition is never walked by the sessions pass.
    assert "sessions" not in memory
    assert "gmd" in memory
    # Every kind embeds and ranks — those two walk whatever graph is there.
    for expected in (project, sessions, memory):
        assert {"embed", "pagerank"} <= expected


def test_the_expected_set_is_a_named_constant_not_a_literal_in_a_renderer():
    """A list inside the reporter is how coverage drifts without anyone
    noticing: a pass added to `reingest` and not to the renderer reads as
    complete."""
    from refmatrix import store as store_mod

    assert isinstance(store_mod._DERIVE_EXPECTED_PASSES, dict)
    assert set(store_mod._DERIVE_EXPECTED_PASSES) >= {
        "project", "sessions", "memory"}


# ---- derive_status names what is missing (criterion 3) -------------------

def test_one_stamp_out_of_five_lists_the_other_four_by_name(store, tmp_path):
    _track(store, tmp_path)
    store.stamp_derive("gmd")

    st = store.derive_status()

    assert st["partition_kind"] == "project"
    assert set(st["expected_passes"]) == {
        "ingest", "semantic", "gmd", "embed", "pagerank"}
    assert set(st["missing_passes"]) == {
        "ingest", "semantic", "embed", "pagerank"}


def test_a_fully_stamped_partition_is_missing_nothing(store, tmp_path):
    _track(store, tmp_path)
    for p in ("ingest", "semantic", "gmd", "embed", "pagerank"):
        store.stamp_derive(p)

    assert store.derive_status()["missing_passes"] == []


def test_a_sessions_partition_is_not_reported_as_missing_gmd(store, tmp_path):
    with store.with_partition("sessions-refmatrix"):
        _track(store, tmp_path, "s.md")
        store.stamp_derive("sessions")
        st = store.derive_status()

    assert st["partition_kind"] == "sessions"
    assert "gmd" not in st["missing_passes"]
    assert "ingest" not in st["missing_passes"]
    assert set(st["missing_passes"]) == {"embed", "pagerank"}


def test_a_memory_partition_is_not_reported_as_missing_sessions(store, tmp_path):
    with store.with_partition("memory-refmatrix"):
        _track(store, tmp_path, "m.md")
        store.stamp_derive("gmd")
        st = store.derive_status()

    assert st["partition_kind"] == "memory"
    assert "sessions" not in st["missing_passes"]
    assert set(st["missing_passes"]) == {"embed", "pagerank"}


def test_an_empty_partition_reports_no_missing_passes(store):
    """Nothing was derived because there is nothing to derive. Listing five
    missing passes for an empty partition is noise on every fresh store."""
    st = store.derive_status()

    assert st["missing_passes"] == []
    assert st["stale"] is False


# ---- criterion 5: missing must not reach the alert ----------------------

def test_a_missing_pass_is_not_behind_code_and_not_stale(store, tmp_path):
    _track(store, tmp_path)
    store.stamp_derive("gmd")       # current version, current code

    st = store.derive_status()

    assert st["missing_passes"], "precondition: four passes have no stamp"
    assert st["behind_code"] is False
    assert st["never_stamped"] is False
    assert st["stale"] is False, (
        "a pass that has never stamped is unknown, not stale — this is the "
        "assertion that keeps the fleet cold on release day")


def test_the_hub_alert_input_stays_cold_with_four_passes_missing(tmp_path):
    """The blast radius, asserted where it actually lands: `_store_health` is
    what the hub's alert tick reads, and `derive.stale` is the only gate it
    opens."""
    from refmatrix import daemon as dmod

    s = Store(tmp_path / ".refmatrix")
    s.init()
    _track(s, tmp_path)
    s.stamp_derive("gmd")

    class _D:
        root = tmp_path / ".refmatrix"

        def _st(self):
            return s

        def _read_active_slot(self):
            return None

    try:
        h = dmod._store_health(_D())
        assert h["derive"]["stale"] is False
        assert h["derive"]["behind_code"] is False
        assert h["derive"]["never_stamped"] is False
    finally:
        s.close()


def test_coverage_is_reported_even_though_it_is_not_an_alert(store, tmp_path):
    """Not hot is not the same as not said. The whole point of 15.4 is that the
    four unstamped passes are VISIBLE; a field nobody renders is the blind spot
    again."""
    from refmatrix.cli import render_derive_coverage

    _track(store, tmp_path)
    store.stamp_derive("gmd")
    line = render_derive_coverage(store.derive_status(), partition="refmatrix")

    assert "embed" in line and "pagerank" in line and "ingest" in line
    assert render_derive_coverage(
        {"missing_passes": [], "expected_passes": ["gmd"]}) == ""


# ---- criterion 2: a pass that RAISES leaves no stamp --------------------

def test_a_raising_pagerank_leaves_no_pagerank_stamp(tmp_path, monkeypatch):
    """The extractor is monkeypatched, never `stamp_derive` — patching the
    stamp would test the test."""
    import refmatrix.pagerank as pr_mod
    from refmatrix.daemon import Daemon, _op_pagerank

    s = Store(tmp_path / ".refmatrix")
    s.init()
    _track(s, tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("pagerank blew up")

    monkeypatch.setattr(pr_mod, "pagerank", _boom)

    d = Daemon(tmp_path / ".refmatrix")
    d.store = s
    try:
        with pytest.raises(Exception):
            _op_pagerank(d, {"partition": s._partition_name})
        names = [r["pass_name"] for r in s.derive_status()["passes"]]
        assert "pagerank" not in names
    finally:
        s.close()


def test_a_raising_pass_does_not_stop_the_others_from_stamping(tmp_path,
                                                              monkeypatch):
    """`reingest` continues past one bad pass by design; the stamps have to
    follow that, or one failure erases the record of four successes."""
    import refmatrix.pagerank as pr_mod
    from refmatrix.daemon import Daemon, _op_pagerank

    s = Store(tmp_path / ".refmatrix")
    s.init()
    _track(s, tmp_path)
    s.stamp_derive("ingest")
    s.stamp_derive("gmd")

    monkeypatch.setattr(pr_mod, "pagerank",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    d = Daemon(tmp_path / ".refmatrix")
    d.store = s
    try:
        with pytest.raises(Exception):
            _op_pagerank(d, {"partition": s._partition_name})
        names = {r["pass_name"] for r in s.derive_status()["passes"]}
        assert names == {"ingest", "gmd"}
    finally:
        s.close()


def test_a_successful_pagerank_stamps_itself(tmp_path):
    from refmatrix.daemon import Daemon, _op_pagerank

    s = Store(tmp_path / ".refmatrix")
    s.init()
    a = s.upsert_entity("concept", "alpha")
    b = s.upsert_entity("concept", "beta")
    s.link("related-to", a, b)
    s.link("related-to", b, a)

    d = Daemon(tmp_path / ".refmatrix")
    d.store = s
    try:
        _op_pagerank(d, {"partition": s._partition_name})
        rows = {r["pass_name"]: r for r in s.derive_status()["passes"]}
        assert "pagerank" in rows
        assert rows["pagerank"]["version"] == RUNNING
        # Criterion 1's other half: the history row, not just the stamp.
        hist = s.derive_history("pagerank")
        assert hist and hist[0]["pass_name"] == "pagerank"
    finally:
        s.close()


# ---- criterion 1: the real orchestrator stamps every pass that ran ------

def test_reingest_stamps_every_pass_that_ran(tmp_path, monkeypatch):
    """A real `rmx reingest` on a fresh store. `--no-embed` keeps the model out
    of the suite; the embed pass has its own test below, and its absence here
    is exactly criterion 6's case."""
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "m.py").write_text("def f():\n    return 1\n")
    (repo / "README.md").write_text("# proj\n\ntext about alpha.\n")
    root = repo / ".refmatrix"
    s = Store(root)
    s.init()
    s.close()

    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.chdir(repo)
    res = CliRunner().invoke(
        cli_mod.main,
        ["reingest", "--no-embed", "--no-sessions", "--memory-dir",
         str(tmp_path / "nope")],
    )
    assert res.exit_code == 0, res.output

    s = Store(root)
    try:
        stamped = {r["pass_name"] for r in s.derive_status()["passes"]}
        assert {"ingest", "semantic"} <= stamped
        assert "pagerank" in stamped, (
            "pagerank ran and did not record that it did")
        for p in stamped:
            assert s.derive_history(p), f"{p} stamped with no history row"
    finally:
        s.close()


# ---- criterion 6: a SKIPPED pass is not a MISSING pass ------------------

def test_reingest_reports_a_skipped_pass_as_skipped_not_missing(tmp_path,
                                                                monkeypatch):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod

    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "README.md").write_text("# proj\n")
    root = repo / ".refmatrix"
    s = Store(root)
    s.init()
    s.close()

    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.chdir(repo)
    res = CliRunner().invoke(
        cli_mod.main,
        ["reingest", "--no-embed", "--no-sessions", "--no-semantic",
         "--memory-dir", str(tmp_path / "nope")],
    )
    assert res.exit_code == 0, res.output
    out = res.output

    assert "coverage" in out.lower(), (
        "reingest ran three of five passes and said nothing about the other "
        "two")
    # The PARTITION has to survive the renderer. The first run of this line
    # printed `derive coverage:` with the name gone, because rich read
    # `[proj]` as a style tag and dropped it — a coverage report that cannot
    # say WHICH partition is uncovered is the blind spot again, one layer out.
    #
    # Asserted on the BRACKETED label, not on the bare project name: `proj`
    # also appears in step 1's `ingested … from /…/proj` line, so a looser
    # assertion passes with the escape deleted (mutation M6 survived it).
    assert "derive coverage[proj]" in out, out
    # The operator asked for these to be skipped. Reporting them as missing
    # trains the reader to ignore the line.
    for pass_name in ("embed", "semantic", "sessions"):
        assert pass_name in out
    assert "skipped" in out.lower()


def test_a_deliberate_skip_is_distinguishable_from_an_absence(store, tmp_path):
    """The rendering contract, at the unit the CLI calls: a pass the run chose
    not to run is labelled, and a pass nobody ran is listed as missing."""
    from refmatrix.cli import render_derive_coverage

    _track(store, tmp_path)
    store.stamp_derive("gmd")
    st = store.derive_status()

    line = render_derive_coverage(st, partition="refmatrix",
                                  skipped=("embed", "semantic"))

    assert "skipped" in line
    # `ingest` and `pagerank` were not skipped and have no stamp: still missing.
    assert "ingest" in line and "pagerank" in line
    # A skipped pass is NOT in the missing list.
    missing_part = line.split("skipped")[0]
    assert "embed" not in missing_part


# ---- the embed pass stamps where it COMPLETES ---------------------------

def test_embed_stamps_only_when_the_loop_runs_to_completion(tmp_path,
                                                            monkeypatch):
    """A `--max-batches` run is a PARTIAL derive. Stamping it would claim a
    complete pass, which is the exact lie 15.4 exists to remove — so the
    capped run must leave no stamp while the natural one leaves one.

    The model-bearing collaborator (`_op_embed`) is faked; the code under test
    is the orchestration that decides whether the pass finished.
    """
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix import daemon as dmod

    repo = tmp_path / "proj"
    repo.mkdir()
    root = repo / ".refmatrix"
    s = Store(root)
    s.init()
    s.upsert_entity("concept", "alpha")
    part = s._partition_name
    s.close()

    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setattr(dmod, "ping", lambda *a, **k: False)
    monkeypatch.chdir(repo)

    calls = {"n": 0}

    def _fake_embed(d, args):
        calls["n"] += 1
        # Always more work left: only --max-batches can stop this.
        return {"embedded": 1, "remaining": 5, "kinds": args.get("kinds")}

    monkeypatch.setattr(dmod, "_op_embed", _fake_embed)
    res = CliRunner().invoke(cli_mod.main,
                            ["embed", "-k", "concept", "--max-batches", "2"])
    assert res.exit_code == 0, res.output

    s = Store(root)
    try:
        names = {r["pass_name"] for r in s.derive_status()["passes"]}
        assert "embed" not in names, (
            "a capped embed run stamped a complete pass")
    finally:
        s.close()

    def _done_embed(d, args):
        return {"embedded": 2, "remaining": 0, "kinds": args.get("kinds")}

    monkeypatch.setattr(dmod, "_op_embed", _done_embed)
    res = CliRunner().invoke(cli_mod.main, ["embed", "-k", "concept"])
    assert res.exit_code == 0, res.output

    s = Store(root)
    try:
        rows = {r["pass_name"]: r for r in s.derive_status()["passes"]}
        assert "embed" in rows, "a completed embed pass did not stamp"
        assert rows["embed"]["version"] == RUNNING
        assert s.derive_history("embed")
    finally:
        s.close()


# ---- the sessions pass stamps where it COMPLETES ------------------------

def _session_jsonl(path: Path) -> None:
    """A settled two-turn transcript. Backdated past the active-skip window —
    a just-written JSONL reads as a live session and is skipped, which would
    make this test assert on a pass that never ran."""
    import json
    import os
    import time as _t

    path.write_text("\n".join([
        json.dumps({"type": "user",
                    "message": {"role": "user", "content": "about alpha"},
                    "timestamp": "2026-06-03T00:00:00Z",
                    "cwd": "/x/y/z", "gitBranch": "main"}),
        json.dumps({"type": "assistant",
                    "message": {"role": "assistant", "model": "claude-opus-5",
                                "content": [{"type": "text",
                                             "text": "alpha reply"}]},
                    "timestamp": "2026-06-03T00:00:01Z"}),
    ]) + "\n")
    old = _t.time() - 86400
    os.utime(path, (old, old))


def test_the_sessions_pass_stamps_its_own_partition(tmp_path, monkeypatch):
    """A real `rmx session ingest`, no daemon. The stamp has to land in
    `sessions-<project>` — the partition the cards went into — not in the
    project partition the CLI happens to be bound to."""
    from click.testing import CliRunner

    from refmatrix.cli import main

    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    src = tmp_path / "sess01.jsonl"
    _session_jsonl(src)
    runner = CliRunner()
    r0 = runner.invoke(main, ["init", "--path", str(tmp_path),
                             "--no-hooks", "--no-agents"])
    assert r0.exit_code == 0, r0.output
    r = runner.invoke(main, ["session", "ingest", str(src)])
    assert r.exit_code == 0, r.output

    s = Store(tmp_path / ".refmatrix")
    try:
        part = f"sessions-{tmp_path.name}"
        with s.with_partition(part):
            st = s.derive_status()
        names = {row["pass_name"] for row in st["passes"]}
        assert "sessions" in names, (
            f"the sessions pass indexed cards into {part} and recorded "
            f"nothing; stamped: {sorted(names)}")
        assert st["partition_kind"] == "sessions"
        assert "sessions" not in st["missing_passes"]
    finally:
        s.close()


def test_no_index_builds_cards_and_stamps_nothing(tmp_path, monkeypatch):
    """`--no-index` writes cards to disk and leaves the store alone. A stamp
    would claim a sessions graph this run deliberately did not build."""
    from click.testing import CliRunner

    from refmatrix.cli import main

    monkeypatch.setenv("REFMATRIX_ROOT", str(tmp_path / ".refmatrix"))
    src = tmp_path / "sess02.jsonl"
    _session_jsonl(src)
    runner = CliRunner()
    assert runner.invoke(main, ["init", "--path", str(tmp_path),
                                "--no-hooks", "--no-agents"]).exit_code == 0
    r = runner.invoke(main, ["session", "ingest", "--no-index", str(src)])
    assert r.exit_code == 0, r.output

    s = Store(tmp_path / ".refmatrix")
    try:
        with s.with_partition(f"sessions-{tmp_path.name}"):
            names = {row["pass_name"] for row in s.derive_status()["passes"]}
        assert "sessions" not in names
    finally:
        s.close()


# ---- the new passes are mapped, so staleness stays attributable ---------

def test_the_new_passes_have_their_own_module_sets(tmp_path, monkeypatch):
    """An UNMAPPED pass falls through to the union of three modules, which
    means an edit to `ingest.py` would read as pagerank staleness. 15.1 removed
    that for the passes that existed; adding three passes without mapping them
    puts it straight back."""
    from refmatrix import store as store_mod

    for p in ("sessions", "embed", "pagerank"):
        mods = store_mod.derive_pass_modules(p)
        assert mods != store_mod._DERIVE_CODE_MODULES, (
            f"{p} is unmapped and inherits the union")
        assert mods, f"{p} maps to nothing, so its gate can never fire"
    assert (store_mod.derive_pass_modules("pagerank")
            != store_mod.derive_pass_modules("embed"))
