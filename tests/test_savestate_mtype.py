"""Task 26.4: a save-state's type is `session/recall-state` wherever it came from
(`workflow/plans/plan-26-memory-organisation-tasks/task-26.4-savestate-mtype-normalisation.md`,
ADR-0005 #authority, #newest).

WHY. cliquedb's four hand-written save-states carry `metadata.type: project`. The bridge
(`ingest_gmd.ingest_gmd_paths`, as-memory pass 1) copies `metadata.type` verbatim into
`memory_content.mtype`, so hook-mode recall's `session/*` exclusion (`cli._memory_recall_impl`,
`hook_mode`) does not hide them and each one rides every prompt's recall payload -- bug-164's
symptom (its budget fix stays with plan-25; task 25.1 depends on AC-2 here). ADR-0005 #authority
makes `savestates/` (and a legacy top-level `savestate_*`) authoritative: the bridge stores
`session/recall-state` and counts the override; the FILE is corrected separately, preserving
mtime and `updated:` so the ADR #newest ordering (`(updated date, mtime, name)`) cannot move.

Real CLI (`rmx ingest-gmd --as-memory`, `rmx memory recall`, `rmx recall-state`) through
CliRunner, `cli._sync_memory_dir` (the save-state / SessionStart bridge), a throwaway store under
a short `mkdtemp()` root, a real spawned daemon + the real embed model for the daemon and recall
legs. Nothing in the bridge, recall, handoff or memory_layout is mocked. Rows are read back with
`Store` on the THROWAWAY store only, after its daemon is stopped. The fixtures are synthetic
copies of the cliquedb SHAPE (frontmatter only, made-up bodies; no session text).

Contracts this file pins (the spec names the terms; the shapes are chosen here, RED author):
- `IngestStats.mtype_normalised: list[(id, from, to)]`, in `as_dict()` as `[[id, from, to]]`,
  and in the bridge result (`cli._sync_memory_dir`: in-process leg, daemon leg, and the
  waited-job branch of `_bridge_wait_for_active_job`) as `out["mtype_normalised"]`.
- The bridge report prints `mtype_normalised: N` when N > 0 and names each overridden id.
- AC-3's file correction is a 26.4-owned primitive that 26.5's `rmx memory organise` calls:
  `memory_layout.normalise_savestate_types(memdir, *, apply: bool) -> list[dict]`, one entry
  `{"id", "path", "from", "to"}` per mis-typed save-state (apply=False is the preview list and
  writes nothing). It changes ONLY the `type:` line and restores the prior mtime.
- NOT here (26.5's, which depends on 26.4): `organise --apply`'s one-time forced re-bridge of
  every save-state (AC-3b organised half = 26.5 AC-5) and `organise --check`'s
  `folder/type mismatch` line (AC-4's report half = 26.5 AC-2).

Not pinned (spec/ADR disagree): a `savestate_*` id in a folder OTHER than the top level or
`savestates/`. AC-1 says "a file whose id starts with `savestate_`"; ADR-0005 #authority and
`memory_layout.is_savestate_path` say only a legacy TOP-LEVEL one. The fixtures here use only
the shapes both agree on.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import memory_layout, verbs
from refmatrix.store import Store

RS = "session/recall-state"


# ---- fixtures: a throwaway store, in-process or behind a real daemon ------------------------

def _new_store(spawn: bool):
    base = Path(tempfile.mkdtemp(prefix="rmx264-"))
    root = base / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()
    if spawn:
        pid = dm.spawn_daemon_subprocess(root, watch_root=[])
        assert pid and dm.ping(root)
    return base, root


@pytest.fixture
def inproc(monkeypatch):
    base, root = _new_store(spawn=False)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def daemon(monkeypatch):
    base, root = _new_store(spawn=True)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    yield base, root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


# ---- builders: the cliquedb shape, synthetic ------------------------------------------------

def at(y: int, mo: int, d: int, h: int = 12) -> float:
    """A local wall-clock time as a WHOLE-second epoch (so `os.utime` round-trips exactly)."""
    return float(int(time.mktime((y, mo, d, h, 0, 0, 0, 0, -1))))


def organise(memdir: Path) -> None:
    """The ADR-0005 #marker-encoding marker, as 26.5's writer will lay it down."""
    (memdir / ".memory-layout").write_text(json.dumps(
        {"layout": 1, "organised": "2026-11-09T10:00:00-08:00",
         "backup": str(memdir.parent / "backup.tar.gz")}), encoding="utf-8")


def savestate(memdir: Path, rel: str, *, mtype: "str | None", created: str,
              updated: "str | None", mtime: float, body: str = "made-up handoff") -> Path:
    """A hand-written save-state in cliquedb's shape: GMD frontmatter, `metadata.type` as the
    writer typed it (`project` for the four), `originSessionId`, `created`, maybe `updated`."""
    p = memdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    meta = "metadata:\n  node_type: memory\n"
    if mtype is not None:
        meta += f"  type: {mtype}\n"
    meta += f"  originSessionId: 0000aaaa-{p.stem[-4:]}-4000-8000-000000000000\n"
    meta += f"  created: {created}\n"
    if updated is not None:
        meta += f"  updated: {updated}\n"
    p.write_text('---\ngmd: "0.1"\n'
                 f"id: {p.stem}\n"
                 f'title: "Save state {p.stem}"\n'
                 "tags: [project, savestate]\n" + meta + "---\n\n"
                 f"# Save state {p.stem} {{#root}}\n\n{body} of {p.stem}.\n", encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def note(memdir: Path, rel: str, *, mtype: str, body: str = "a curated note") -> Path:
    p = memdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('---\ngmd: "0.1"\n'
                 f"id: {p.stem}\n"
                 f'title: "Note {p.stem}"\n'
                 f"tags: [{mtype.split('/')[0]}]\n"
                 f"metadata:\n  node_type: memory\n  type: {mtype}\n  created: 2026-11-01\n"
                 "---\n\n"
                 f"# Note {p.stem} {{#root}}\n\n{body} ({p.stem}).\n", encoding="utf-8")
    return p


def cliquedb_four(memdir: Path, prefix: str = "") -> dict:
    """AC-3's fixture: four `type: project` save-states from June/July, plus a correctly typed
    August one that is THE newest. One July file has no `updated:`, so its mtime's date is its
    ordering key (ADR-0005 #newest step 1): a rewrite that bumps mtime makes IT newest, one that
    bumps `updated:` makes any rewritten file newest -- both resume from July, not August."""
    rel = (lambda n: f"{prefix}{n}.md")
    return {
        "jun_a": savestate(memdir, rel("savestate_cq_0603"), mtype="project",
                           created="2026-06-03", updated="2026-06-03", mtime=at(2026, 6, 3)),
        "jun_b": savestate(memdir, rel("savestate_cq_0619"), mtype="project",
                           created="2026-06-19", updated="2026-06-20", mtime=at(2026, 6, 20)),
        "jul_a": savestate(memdir, rel("savestate_cq_0707"), mtype="project",
                           created="2026-07-07", updated="2026-07-08", mtime=at(2026, 7, 8)),
        "jul_b": savestate(memdir, rel("savestate_cq_0722"), mtype="project",
                           created="2026-07-22", updated=None, mtime=at(2026, 7, 22)),
        "aug": savestate(memdir, rel("savestate_cq_0814"), mtype=RS,
                         created="2026-08-14", updated="2026-08-14", mtime=at(2026, 8, 14)),
    }


MISTYPED = ("savestate_cq_0603", "savestate_cq_0619", "savestate_cq_0707", "savestate_cq_0722")


# ---- readers / drivers ---------------------------------------------------------------------

def _invoke(args, *, ok: bool = True, input: "str | None" = None, env=None):
    r = CliRunner().invoke(cli_mod.main, args, input=input, env=env)
    if ok:
        assert r.exit_code == 0, f"rmx {' '.join(map(str, args))}: exit {r.exit_code}\n" \
                                 f"{r.output}\n{r.exception!r}"
    return r


def _bridge_cli(memdir: Path) -> str:
    return _invoke(["ingest-gmd", "--as-memory", str(memdir)]).output


def _mtypes(root: Path) -> dict:
    """{name: mtype} of every memory row, read on the THROWAWAY store (daemon stopped)."""
    s = Store(root)
    try:
        con = s._connect()
        return {n: m for n, m in con.execute(
            "SELECT e.name, mc.mtype FROM entities e "
            "JOIN memory_content mc ON mc.entity_id = e.id WHERE e.kind = 'memory'").fetchall()}
    finally:
        s.close()


def _set_mtype(root: Path, name: str, mtype: str) -> None:
    """Rewind one row to the PRE-26.4 shape (what every deployed store holds today: the file's
    `project` copied verbatim). THROWAWAY store only."""
    s = Store(root)
    try:
        con = s._connect()
        ids = [r[0] for r in con.execute(
            "SELECT id FROM entities WHERE kind = 'memory' AND name = ?", (name,)).fetchall()]
        for eid in ids:
            con.execute("UPDATE memory_content SET mtype = ? WHERE entity_id = ?", (mtype, eid))
        con.commit()
        n = len(ids)
    finally:
        s.close()
    assert n != 0, f"no memory row named {name!r} to rewind"


def _norm(seq) -> list:
    return sorted(tuple(x) for x in (seq or []))


def _latest(memdir: Path) -> "str | None":
    from refmatrix import handoff
    r = handoff._latest_savestate(memdir)
    return r["id"] if r else None


# =============================================================================================
# AC-1: the bridge rule -- a save-state is stored as session/recall-state, counted
# =============================================================================================

def test_ac1_top_level_hand_typed_savestate_is_stored_as_recall_state(inproc):
    """Un-organised (flat) dir, cliquedb's shape: legacy top-level `savestate_*` typed `project`.
    RED: `memory_content.mtype` reads `project` (the frontmatter copied verbatim)."""
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    savestate(memdir, "savestate_cq_0603.md", mtype="project", created="2026-06-03",
              updated="2026-06-03", mtime=at(2026, 6, 3))
    note(memdir, "project_plain.md", mtype="project")
    _bridge_cli(memdir)
    got = _mtypes(root)
    assert got.get("savestate_cq_0603") == RS, \
        f"hand-typed top-level save-state stored as {got.get('savestate_cq_0603')!r}, not {RS!r}"
    assert got.get("project_plain") == "project", got


@pytest.mark.parametrize("ftype", ["project", "feedback", None])
def test_ac1_savestates_folder_file_ignores_its_frontmatter_type(inproc, ftype):
    """Organised dir: ANY file under `savestates/` is a recall-state whatever its frontmatter
    says, including no `type` at all (the bridge's `memory_mtype_default`, `curated`, is not a
    save-state's type either). RED: the row reads `project` / `feedback` / `curated`."""
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    organise(memdir)
    savestate(memdir, "savestates/savestate_cq_0707.md", mtype=ftype, created="2026-07-07",
              updated="2026-07-08", mtime=at(2026, 7, 8))
    _bridge_cli(memdir)
    got = _mtypes(root).get("savestate_cq_0707")
    assert got == RS, f"savestates/ file typed {ftype!r} stored as {got!r}, not {RS!r}"


def test_ac1_ingest_stats_count_every_override_and_only_overrides(inproc):
    """`stats.mtype_normalised: [(id, from, to)]` names each override; a correctly typed
    save-state and a `project` note outside the save-state shapes are not in it.
    RED: `IngestStats` has no `mtype_normalised` (AttributeError)."""
    from refmatrix.ingest_gmd import collect_gmd_files, ingest_gmd_paths
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    cliquedb_four(memdir)
    note(memdir, "project_plain.md", mtype="project")
    note(memdir, "feedback/feedback_typed_project.md", mtype="project")
    s = Store(root)
    try:
        st = ingest_gmd_paths(s, collect_gmd_files([memdir.resolve()], as_memory=True),
                              as_memory=True)
    finally:
        s.close()
    want = sorted((i, "project", RS) for i in MISTYPED)
    assert _norm(st.mtype_normalised) == want, st.mtype_normalised
    assert _norm(st.as_dict()["mtype_normalised"]) == want, st.as_dict().get("mtype_normalised")
    got = _mtypes(root)
    assert all(got[i] == RS for i in (*MISTYPED, "savestate_cq_0814")), got
    assert got["project_plain"] == "project" and got["feedback_typed_project"] == "project", got


def test_ac1_bridge_report_prints_the_count_and_names_each_id(inproc):
    """RED: the report has no `mtype_normalised:` line."""
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    cliquedb_four(memdir)
    out = _bridge_cli(memdir)
    m = re.search(r"^\s*mtype_normalised: (\d+)\b", out, re.M)
    assert m and int(m.group(1)) == 4, f"no `mtype_normalised: 4` line in the report:\n{out}"
    missing = [i for i in MISTYPED if i not in out]
    assert not missing, f"report does not name {missing}:\n{out}"


def test_ac1_in_process_bridge_result_carries_mtype_normalised(inproc):
    """`cli._sync_memory_dir` (save-state's and SessionStart's bridge), daemon down: the result
    carries the overrides through `_bridge_stats`. RED: KeyError `mtype_normalised`."""
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    cliquedb_four(memdir)
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _norm(out["mtype_normalised"]) == sorted((i, "project", RS) for i in MISTYPED), out


def test_ac1_daemon_bridge_result_carries_mtype_normalised(daemon):
    """The daemon leg: the count crosses the daemon result (`stats` = `as_dict()`) into
    `_bridge_stats`, and the row the DAEMON wrote reads recall-state. RED: the result has no
    `mtype_normalised` (None)."""
    base, root = daemon
    memdir = base / "memory"
    memdir.mkdir()
    cliquedb_four(memdir)
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None and out["waited"] is False, out
    assert _norm(out.get("mtype_normalised")) == sorted((i, "project", RS) for i in MISTYPED), \
        f"daemon-leg bridge result: mtype_normalised={out.get('mtype_normalised')!r}"
    dm.stop_daemon(root)
    got = _mtypes(root)
    assert all(got[i] == RS for i in MISTYPED), got


PLAIN = ('---\ngmd: "0.1"\nid: {id}\ntitle: "{id}"\ntags: [project]\nmetadata:\n'
         '  type: feedback\n---\n# {id} {{#root}}\n\n{body}\n')


@pytest.mark.timeout(900)
def test_ac1_waited_job_result_carries_mtype_normalised(daemon, monkeypatch):
    """ch-bsd r1 #m5: the overlap path (`_bridge_wait_for_active_job`) takes the covering job's
    result; it must carry the field too. RED: the result has no `mtype_normalised` (None)."""
    base, root = daemon
    memdir = base / "memory"
    memdir.mkdir()
    cliquedb_four(memdir)
    for i in range(350):                      # long enough that the bridge meets it running
        (memdir / f"doc{i:04d}.md").write_text(
            PLAIN.format(id=f"w_doc{i:04d}", body="x " * 400), encoding="utf-8")
    part = verbs.memory_partition(root)
    resp = dm.call(root, "ingest_gmd_start", {"targets": [str(memdir.resolve())],
                                              "as_memory": True, "memory_mtype": "curated",
                                              "partition": part}, timeout=30)
    assert resp.get("ok"), resp
    monkeypatch.setenv("RMX_BRIDGE_WAIT_S", "600")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["waited"] is True and out["waited_job"] == resp["result"]["job_id"], out
    assert out["error"] is None, out
    assert _norm(out.get("mtype_normalised")) == sorted((i, "project", RS) for i in MISTYPED), \
        f"waited-job bridge result: mtype_normalised={out.get('mtype_normalised')!r}"


# =============================================================================================
# AC-2: the recall consequence, on the REAL hook-mode path (task 25.1 depends on it)
# =============================================================================================

def _hook_recall_argv(root: Path, timeout_s: str) -> list:
    """The UserPromptSubmit recall EXACTLY as `rmx install-hooks` generates it (never a
    hand-written copy), minus the `rmx` launcher. The `--timeout` value alone is replaced: a
    fresh daemon's first dense recall loads the embed + rerank models, which the hook's 5 s
    budget does not cover, and the budget is not what AC-2 tests."""
    from refmatrix.hooks import _claude_hook_block
    from tests.test_hooks_reproducible import _cmds
    block = _claude_hook_block(root)
    cmds = [c for _, _, c in _cmds(block, "UserPromptSubmit")
            if "memory recall --stdin-json" in c]
    assert len(cmds) == 1, cmds
    assert "RMX_INVOCATION_SOURCE=hook" in cmds[0], cmds[0]
    argv = shlex.split(cmds[0].split("rmx memory recall", 1)[1])
    argv = ["memory", "recall", *argv]
    i = argv.index("--timeout")
    argv[i + 1] = timeout_s
    return argv


@pytest.mark.timeout(900)
def test_ac2_hook_mode_recall_hides_the_hand_typed_savestate_and_include_session_keeps_it(
        daemon):
    """After AC-1 the per-prompt hook's recall (`--stdin-json`, `RMX_INVOCATION_SOURCE=hook`)
    no longer returns the hand-typed save-state; `--include-session` still does. A curated
    note answering the same prompt is the control: the recall worked and was not a degraded
    `[]`. RED: the save-state is in the hook-mode answer (its row reads `project`)."""
    base, root = daemon
    memdir = base / "memory"
    memdir.mkdir()
    phrase = "quillwort barometer tessellation"
    savestate(memdir, "savestate_cq_0707.md", mtype="project", created="2026-07-07",
              updated="2026-07-08", mtime=at(2026, 7, 8),
              body=f"resume the {phrase} handoff")
    note(memdir, "feedback_control.md", mtype="feedback", body=f"the {phrase} control note")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert out["embed"] and out["embed"].get("error") is None, out["embed"]
    # warm the models through the daemon's own recall op (the same one the CLI dials)
    warm = dm.call(root, "memory_recall", {"query": phrase, "k": 5,
                                           "partition": verbs.memory_partition(root)},
                   timeout=300)
    assert warm.get("ok"), warm
    argv = _hook_recall_argv(root, "120")
    env = {"RMX_INVOCATION_SOURCE": "hook"}
    envelope = json.dumps({"prompt": f"where were we on the {phrase}?",
                           "session_id": "sess-264", "hook_event_name": "UserPromptSubmit"})

    def names(extra):
        r = _invoke(argv + extra, input=envelope, env=env)
        assert "recall skipped" not in (r.stderr or ""), r.stderr
        return [row.get("name") for row in json.loads(r.stdout)]

    hooked = names([])
    assert "feedback_control" in hooked, f"control note missing: the recall did not run {hooked}"
    assert "savestate_cq_0707" not in hooked, \
        f"hook-mode recall returned the hand-typed save-state: {hooked}"
    opted = names(["--include-session"])
    assert "savestate_cq_0707" in opted, f"--include-session lost the save-state: {opted}"


# =============================================================================================
# AC-3: the file is corrected; "newest" stays where it was
# =============================================================================================

def _snapshot(paths) -> dict:
    return {p: (p.read_text(encoding="utf-8"), p.stat().st_mtime_ns) for p in paths}


def test_ac3_apply_rewrites_only_the_type_line_and_restores_mtime(tmp_path):
    """The rewrite is a metadata correction, not a content update: exactly one line changes
    (`type: project` -> `type: session/recall-state`); `updated`, `created`, `originSessionId`
    and the body are byte-identical; mtime is its prior value. The correctly typed August file
    is untouched. RED: `memory_layout.normalise_savestate_types` does not exist."""
    memdir = tmp_path / "memory"
    memdir.mkdir()
    fx = cliquedb_four(memdir)
    before = _snapshot(fx.values())
    res = memory_layout.normalise_savestate_types(memdir, apply=True)
    assert sorted((e["id"], e["from"], e["to"]) for e in res) == \
        sorted((i, "project", RS) for i in MISTYPED), res
    assert sorted(Path(e["path"]).resolve() for e in res) == \
        sorted(fx[k].resolve() for k in ("jun_a", "jun_b", "jul_a", "jul_b")), res
    for k, p in fx.items():
        text0, mt0 = before[p]
        text1, mt1 = p.read_text(encoding="utf-8"), p.stat().st_mtime_ns
        assert mt1 == mt0, f"{p.name}: mtime {mt0} -> {mt1} (the rewrite must restore it)"
        if k == "aug":
            assert text1 == text0, f"{p.name} was already {RS} and was rewritten"
            continue
        l0, l1 = text0.splitlines(), text1.splitlines()
        assert len(l0) == len(l1), (p.name, l0, l1)
        changed = [(a, b) for a, b in zip(l0, l1) if a != b]
        assert changed == [("  type: project", f"  type: {RS}")], (p.name, changed)


def test_ac3_preview_lists_the_corrections_and_writes_nothing(tmp_path):
    """apply=False is the list 26.5's preview prints (spec: "the correction is listed in the
    organise report"), and touches no byte and no mtime. RED: no such function."""
    memdir = tmp_path / "memory"
    memdir.mkdir()
    fx = cliquedb_four(memdir)
    before = _snapshot(fx.values())
    res = memory_layout.normalise_savestate_types(memdir, apply=False)
    assert sorted((e["id"], e["from"], e["to"]) for e in res) == \
        sorted((i, "project", RS) for i in MISTYPED), res
    assert _snapshot(fx.values()) == before, "the preview changed a file"


def test_ac3_fixture_discriminates_both_mutations(tmp_path):
    """Fixture proof (passes at HEAD by design; it is not one of the RED tests): the AC-3
    fixture CAN fail. A naive rewrite of the type line that lets mtime move resumes from
    July's `updated`-less file; one that also stamps `updated:` today resumes from whichever
    rewritten file -- never August. Without this, a preservation test over a fixture whose
    newest no rewrite could move would pass on a broken rewrite (feedback: a check whose corpus
    is clean cannot tell you it stopped checking)."""
    for bump_updated in (False, True):
        memdir = tmp_path / f"m{int(bump_updated)}"
        memdir.mkdir()
        fx = cliquedb_four(memdir)
        assert _latest(memdir) == "savestate_cq_0814", "fixture: August is not the newest"
        for k in ("jun_a", "jun_b", "jul_a", "jul_b"):
            t = fx[k].read_text(encoding="utf-8").replace("type: project", f"type: {RS}")
            if bump_updated:
                t = re.sub(r"^  updated: .*$", "  updated: 2026-11-11", t, flags=re.M)
            fx[k].write_text(t, encoding="utf-8")       # mtime = now
        assert _latest(memdir) != "savestate_cq_0814", \
            f"a rewrite that moved mtime (bump_updated={bump_updated}) left August newest: " \
            f"the fixture cannot see the mutation"


@pytest.mark.parametrize("organised", [False, True])
def test_ac3_recall_state_still_resumes_from_august_after_the_rewrite(tmp_path, organised):
    """`rmx recall-state` resumes from the August save-state before AND after the correction.
    If the rewrite bumped mtime or `updated:` it would resume from July (the fixture-proof test
    shows both). RED: no `normalise_savestate_types`."""
    memdir = tmp_path / "memory"
    memdir.mkdir()
    if organised:
        organise(memdir)
    cliquedb_four(memdir, prefix="savestates/" if organised else "")

    def resumes() -> str:
        r = _invoke(["recall-state", "--json", "-s", "sess-264", "--memory-dir", str(memdir)])
        rep = json.loads(r.stdout)
        return (rep.get("savestate") or {}).get("id")

    assert resumes() == "savestate_cq_0814", "fixture: recall-state did not resume from August"
    res = memory_layout.normalise_savestate_types(memdir, apply=True)
    assert len(res) == 4, res
    assert resumes() == "savestate_cq_0814", "the type correction moved the resume point"


def test_ac3_after_the_rewrite_disk_and_store_agree_and_the_next_bridge_counts_zero(inproc):
    """Bridge (four overrides) -> correct the files -> bridge again: the rewritten files are
    re-ingested (their hash changed), every row reads recall-state, and nothing is overridden
    because disk already says so. RED: no `mtype_normalised` in the bridge result."""
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    cliquedb_four(memdir)
    first = cli_mod._sync_memory_dir(memdir)
    assert first["error"] is None, first
    assert len(first["mtype_normalised"]) == 4, first["mtype_normalised"]
    memory_layout.normalise_savestate_types(memdir, apply=True)
    second = cli_mod._sync_memory_dir(memdir)
    assert second["error"] is None, second
    assert second["mtype_normalised"] == [], second["mtype_normalised"]
    got = _mtypes(root)
    assert all(got[i] == RS for i in (*MISTYPED, "savestate_cq_0814")), got
    assert memory_layout.normalise_savestate_types(memdir, apply=False) == [], \
        "disk still holds a mis-typed save-state after apply"


# =============================================================================================
# AC-3b: scope -- the store rule reaches a file only when the bridge re-ingests it
# =============================================================================================

def test_ac3b_unorganised_unchanged_file_keeps_its_row_until_its_next_touch(inproc):
    """Un-organised dir, a store already holding the pre-26.4 row (`project`): an UNCHANGED file
    is skipped by the hash gate and keeps `project` (accepted and stated: cliquedb's four keep it
    until 27.5); the file's next touch re-ingests it and the rule lands, counted. No file is
    written by the bridge. RED: after the touch the row still reads `project`."""
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    p = savestate(memdir, "savestate_cq_0707.md", mtype="project", created="2026-07-07",
                  updated="2026-07-08", mtime=at(2026, 7, 8))
    cli_mod._sync_memory_dir(memdir)
    _set_mtype(root, "savestate_cq_0707", "project")         # the deployed stores' row today
    text0 = p.read_text(encoding="utf-8")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None and out["skipped_unchanged"] == 1, out
    assert _mtypes(root)["savestate_cq_0707"] == "project", \
        "an unchanged file was re-typed: the gate did not skip it"
    assert p.read_text(encoding="utf-8") == text0, "the bridge wrote the file"
    p.write_text(text0.replace("made-up handoff", "made-up handoff, edited"), encoding="utf-8")
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _mtypes(root)["savestate_cq_0707"] == RS, \
        "the next touch re-ingested the save-state and still stored the frontmatter type"
    assert _norm(out["mtype_normalised"]) == [("savestate_cq_0707", "project", RS)], out
    assert "type: project" in p.read_text(encoding="utf-8"), "the bridge rewrote the file"


# =============================================================================================
# AC-4: other folders are report-only
# =============================================================================================

def test_ac4_a_project_file_in_feedback_is_not_retyped_by_bridge_or_correction(inproc):
    """A `project`-typed file in `feedback/` keeps `project` in the store, is not counted, and
    `normalise_savestate_types` neither lists nor rewrites it (its `folder/type mismatch` line is
    26.5's `organise --check`). RED: no `mtype_normalised` / no `normalise_savestate_types`."""
    base, root = inproc
    memdir = base / "memory"
    memdir.mkdir()
    organise(memdir)
    fb = note(memdir, "feedback/feedback_typed_project.md", mtype="project")
    savestate(memdir, "savestates/savestate_cq_0707.md", mtype="project", created="2026-07-07",
              updated="2026-07-08", mtime=at(2026, 7, 8))
    os.utime(fb, (at(2026, 9, 1), at(2026, 9, 1)))
    fb0 = (fb.read_text(encoding="utf-8"), fb.stat().st_mtime_ns)
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _norm(out["mtype_normalised"]) == [("savestate_cq_0707", "project", RS)], out
    assert _mtypes(root)["feedback_typed_project"] == "project"
    res = memory_layout.normalise_savestate_types(memdir, apply=True)
    assert [e["id"] for e in res] == ["savestate_cq_0707"], res
    assert (fb.read_text(encoding="utf-8"), fb.stat().st_mtime_ns) == fb0, \
        "a feedback/ file was rewritten"


# =============================================================================================
# AC-1 clarified (team-lead decision 2026-11-11, ADR-0005 #authority): a `savestate_*` stem in
# any folder other than the top level and `savestates/` is MISFILED, not a save-state
# =============================================================================================

@pytest.mark.parametrize("leg", ["inproc", "daemon"])
@pytest.mark.parametrize("marker", [True, False])
def test_ac1_a_savestate_stem_in_another_folder_is_not_retyped_counted_or_rewritten(
        request, leg, marker):
    """`feedback/savestate_misfiled.md` typed `project` stays `project` in the store, is not in
    `mtype_normalised`, and `normalise_savestate_types` neither lists nor rewrites it (26.5's
    `organise --check` reports it as misfiled). A real `savestates/` save-state in the same dir
    is the positive control: the rule ran, on the right file only. Through the save-state /
    SessionStart bridge (`cli._sync_memory_dir`), both legs, the memdir as its target.

    Kills ch-bsd 26.4 mutation f1 (the override widened to any `savestate_*` id): the misfiled
    file is counted and stored as `session/recall-state`."""
    base, root = request.getfixturevalue(leg)
    memdir = base / "memory"
    memdir.mkdir()
    if marker:
        organise(memdir)
    mis = savestate(memdir, "feedback/savestate_misfiled.md", mtype="project",
                    created="2026-07-07", updated="2026-07-08", mtime=at(2026, 7, 8))
    real = "savestates/savestate_cq_0707.md" if marker else "savestate_cq_0707.md"
    savestate(memdir, real, mtype="project", created="2026-07-07", updated="2026-07-08",
              mtime=at(2026, 7, 8))
    mis0 = (mis.read_bytes(), mis.stat().st_mtime_ns)
    out = cli_mod._sync_memory_dir(memdir)
    assert out["error"] is None, out
    assert _norm(out["mtype_normalised"]) == [("savestate_cq_0707", "project", RS)], \
        f"{leg} bridge counted a misfiled savestate_* stem: {out['mtype_normalised']}"
    assert "savestate_misfiled" not in (out["report"] or ""), out["report"]
    if leg == "daemon":
        dm.stop_daemon(root)
    got = _mtypes(root)
    assert got["savestate_misfiled"] == "project", \
        f"misfiled feedback/savestate_misfiled.md stored as {got['savestate_misfiled']!r}"
    assert got["savestate_cq_0707"] == RS, got
    res = memory_layout.normalise_savestate_types(memdir, apply=True)
    assert [e["id"] for e in res] == ["savestate_cq_0707"], res
    assert (mis.read_bytes(), mis.stat().st_mtime_ns) == mis0, "the misfiled file was rewritten"


def test_every_production_memory_bridge_call_names_its_marker_roots():
    """The predicate's memdir is the bridge's DIR target (`_OrganisedDirs.is_savestate`); a
    direct `ingest_gmd_paths(..., as_memory=...)` caller that names no `marker_roots` bounds
    each file by its own folder, so `feedback/savestate_x.md` would read as a top-level
    save-state (green-264's flag). Pins that every such call in `src/` passes `marker_roots`
    -- the three today: the in-process CLI leg, the daemon's ingest op, `sessions index`."""
    import ast
    src = Path(__file__).resolve().parent.parent / "src" / "refmatrix"
    calls, bare = [], []
    for f in sorted(src.rglob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None)
                    == "ingest_gmd_paths"):
                continue
            kw = {k.arg for k in node.keywords}
            if "as_memory" not in kw:
                continue                     # a doc ingest: no memory rows, no save-state rule
            calls.append(f"{f.name}:{node.lineno}")
            if "marker_roots" not in kw:
                bare.append(f"{f.name}:{node.lineno}")
    assert len(calls) >= 3, f"expected the CLI, daemon and sessions callers, found {calls}"
    assert not bare, f"as-memory ingest_gmd_paths calls with no marker_roots: {bare}"
