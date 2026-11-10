"""Task 26.6 r1 remedy (ch-bsd 26.6 r1, 2026-11-10) — RED for `#remedy-r1` items 1-5 and 7.

Spec: `workflow/plans/plan-26-memory-organisation-tasks/task-26.6-compile-subject-hygiene.md`
`#remedy-r1`; audit `workflow/bullshit/2026-11-10-1021-task26.6-r1-compile-hygiene-290348a.md`.
Item 5 (`#rm-real-fallback`) lives in tests/test_plan7_10_remedy_r4.py, where the mocked test
it replaces was; item 6 is docs-only; item 8 is no change.

Same production-path rules as tests/test_memory_compile_scope.py, whose seeds and harness are
reused (never redeclared): the REAL CLI, the REAL verb, a REAL spawned daemon over a throwaway
store under a short `mkdtemp()` root, or a real `Store` in-process where the item is about a
store-level computation. No mock of compile, `apply_plan`, the bridge or the index writer.

GREEN-at-HEAD by design, named so nobody reads them as broken RED: the `#rm-twin-tests` group
covers branches that WORK today and had no test (audit #s-2: deleting the twin or the error
capture survived the suite). Their proof is the mutation each one kills, not a red run.
"""
from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import refmatrix.store as store_mod
from refmatrix import brief, consolidate, discovery, handoff, verbs
from refmatrix import daemon as dm
from refmatrix.store import Store
from tests.test_memory_compile_scope import (  # noqa: F401 (spawn is a fixture)
    GMD, P, STATUS_FIX, STATUS_LINE, VP, _cli, _compile_verb, _memdir, _ok, _seed_scopes,
    _subjects, spawn,
)

PATTERN_PASS = "memory-compile:pattern"


def _tmp_store():
    """A seeded throwaway store under a SHORT mkdtemp root, no daemon. Returns (base, root,
    part, store) with the store OPEN; the caller closes it."""
    base = Path(tempfile.mkdtemp(prefix="r266r-"))
    root = base / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    return base, root, discovery.store_name(root), s


def _unstamped_memory_subject(s: Store, part: str) -> None:
    """The 2026-07-31 shape: a compiled memory-scope subject, no stamp."""
    with s.with_partition(part):
        s.upsert_subject("old junk", metadata={
            "compiled_by": "memory-compile", "compiled_scope": "memory", "compiled_at": 1.0})
        s.flush_fragments()


def _unstamped_pattern_subject(s: Store, part: str) -> None:
    with s.with_partition(part):
        s.upsert_subject("pattern old junk", metadata={
            "compiled_by": "memory-compile", "compiled_scope": "pattern", "compiled_at": 1.0})
        s.flush_fragments()


def _stamped_passes(root: Path) -> set:
    s = Store(root)
    try:
        return {r[0] for r in s._read().execute(
            "SELECT pass_name FROM derive_stamps").fetchall()}
    finally:
        s.close()


# =========================================== #rm-stamp-per-scope (r1 #s-1) ===

def test_stamp_per_scope_the_pattern_pass_is_registered_and_kept_out_of_the_verdict():
    """`memory-compile:pattern` hashes consolidate.py, is reported on its own line, and is
    never an EXPECTED pass (a store that never compiled patterns is not missing a derive)."""
    assert store_mod._DERIVE_PASS_MODULES.get(PATTERN_PASS) == ("consolidate.py",), \
        sorted(store_mod._DERIVE_PASS_MODULES)
    assert PATTERN_PASS in store_mod._DERIVE_VERDICT_EXCLUDED
    assert store_mod.MEMORY_COMPILE_PASS in store_mod._DERIVE_VERDICT_EXCLUDED
    for kind, passes in store_mod._DERIVE_EXPECTED_PASSES.items():
        assert PATTERN_PASS not in passes, (kind, passes)
        assert store_mod.MEMORY_COMPILE_PASS not in passes, (kind, passes)


def test_stamp_per_scope_a_pattern_apply_leaves_the_memory_scope_needing_compile():
    """THE audit probe (#s-1): an unstamped memory-scope subject, then a pattern-only apply.
    At HEAD the one shared stamp clears `needs_compile` while the memory subjects stay
    un-recompiled."""
    base, root, part, s = _tmp_store()
    try:
        _seed_scopes(s, part)
        _unstamped_memory_subject(s, part)
        with s.with_partition(part):
            consolidate.run_compile(s, scope="pattern", dry_run=False, **VP)
            mc = s.derive_status()["memory_compile"]
    finally:
        s.close()
    scopes = mc.get("scopes")
    assert isinstance(scopes, dict) and set(scopes) == {"memory", "pattern"}, mc
    for name, st in scopes.items():
        for key in ("stamped", "behind_code", "compiled_subjects", "needs_compile"):
            assert key in st, (name, key, st)
    mem, pat = scopes["memory"], scopes["pattern"]
    assert mem["stamped"] is False, mem
    assert mem["compiled_subjects"] == 1, mem
    assert mem["needs_compile"] is True, (
        f"a pattern apply cleared the memory scope's warning: {mc}")
    assert pat["stamped"] is True and pat["needs_compile"] is False, pat
    assert pat["compiled_subjects"] >= 2, pat          # pattern_daemon_ops + pattern_store_lock
    passes = _stamped_passes(root)
    assert PATTERN_PASS in passes, passes
    assert store_mod.MEMORY_COMPILE_PASS not in passes, (
        f"a pattern apply stamped the MEMORY pass: {passes}")
    shutil.rmtree(base, ignore_errors=True)


def test_stamp_per_scope_a_memory_apply_stamps_only_the_memory_pass():
    """The reverse: a memory apply never stamps (so never clears) the pattern scope."""
    base, root, part, s = _tmp_store()
    try:
        _seed_scopes(s, part)
        _unstamped_pattern_subject(s, part)
        with s.with_partition(part):
            consolidate.run_compile(s, scope="memory", dry_run=False, **VP)
            mc = s.derive_status()["memory_compile"]
    finally:
        s.close()
    scopes = mc.get("scopes") or {}
    assert scopes.get("memory", {}).get("needs_compile") is False, mc
    assert scopes.get("pattern", {}).get("stamped") is False, mc
    assert scopes.get("pattern", {}).get("compiled_subjects") == 1, mc
    assert scopes.get("pattern", {}).get("needs_compile") is True, mc
    passes = _stamped_passes(root)
    assert store_mod.MEMORY_COMPILE_PASS in passes and PATTERN_PASS not in passes, passes
    shutil.rmtree(base, ignore_errors=True)


def _status_lines(out: str) -> list:
    return [ln for ln in out.splitlines() if STATUS_LINE in ln]


def test_stamp_per_scope_daemon_status_still_prints_the_memory_line_after_a_pattern_apply(
        spawn):
    """AC (#rm-stamp-per-scope): through the CLI a user runs — `memory compile --apply --scope
    pattern`, then `rmx daemon status` still says the memory scope is behind."""
    ctx = spawn(_seed_scopes, pre=_unstamped_memory_subject)
    assert _status_lines(_ok("daemon", "status")), "control: the unstamped subject must warn"
    _ok("memory", "compile", "--apply", "--scope", "pattern", *P)
    lines = _status_lines(_ok("daemon", "status"))
    mem = [ln for ln in lines if "--scope pattern" not in ln]
    assert mem, f"the memory-scope line vanished after a PATTERN apply: {lines}"
    assert STATUS_FIX in mem[0], mem
    assert not [ln for ln in lines if "--scope pattern" in ln], (
        f"the freshly stamped pattern scope still warns: {lines}")


def test_stamp_per_scope_a_stale_pattern_scope_prints_its_own_line(spawn):
    """One line PER stale scope, each naming its own remedy."""
    ctx = spawn(_seed_scopes, pre=_unstamped_pattern_subject)
    _ok("memory", "compile", "--apply", *P)                     # memory scope stamped
    lines = _status_lines(_ok("daemon", "status"))
    pat = [ln for ln in lines if "rmx memory compile --apply --scope pattern" in ln]
    assert len(pat) == 1, f"no pattern-scope line naming `--scope pattern`: {lines}"
    assert len(lines) == 1, f"the stamped memory scope printed too: {lines}"


# ============================================== #rm-twin-tests (r1 #s-2) ===
# GREEN at HEAD by design; each kills one mutation (twin deleted / error swallowed / skip
# silent). See the module docstring.

def _rows_named(root: Path, *names: str) -> set:
    s = Store(root)
    try:
        ph = ",".join("?" * len(names))
        return {r[0] for r in s._read().execute(
            f"SELECT name FROM entities WHERE kind='memory' AND name IN ({ph})",
            list(names)).fetchall()}
    finally:
        s.close()


@pytest.fixture
def downstore(monkeypatch):
    """A throwaway store with NO daemon: `ingest-gmd` takes the in-process twin
    (`_ingest_gmd_sync`)."""
    base = Path(tempfile.mkdtemp(prefix="r266t-"))
    root = base / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    s = Store(root)
    s.init()
    s.close()
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    ctx = SimpleNamespace(base=base, root=root)
    yield ctx
    memdir = handoff.default_memory_dir(root.parent)
    shutil.rmtree(memdir, ignore_errors=True)
    shutil.rmtree(base, ignore_errors=True)


def test_twin_daemon_down_bridge_regenerates_the_index_in_an_organised_dir(downstore):
    ctx = downstore
    assert not dm.ping(ctx.root, retries=0), "control: no daemon may serve this store"
    memdir = _memdir(ctx, organised=True)
    (memdir / "new_note.md").write_text(GMD.format(id="new_note", t="project", body="newest"))
    code, out = _cli("ingest-gmd", "--as-memory", str(memdir))
    assert code == 0, out
    idx = (memdir / "MEMORY.md").read_text()
    assert "](new_note.md)" in idx, f"the daemon-down twin wrote no index:\n{idx}\n---\n{out}"
    assert "](old_note.md)" in idx, idx
    assert "MEMORY.md regenerated in" in out, out


def _break_marker(memdir: Path) -> None:
    (memdir / ".memory-layout").write_text("{not json", encoding="utf-8")


def _assert_not_regenerated_but_saved(code: int, out: str, memdir: Path, before: bytes) -> None:
    assert code == 0, f"an unreadable marker failed an ingest whose rows are saved:\n{out}"
    assert "MEMORY.md NOT regenerated" in out, out
    assert "the memories are SAVED" in out, out
    assert (memdir / "MEMORY.md").read_bytes() == before, "an unreadable marker read as organised"


def test_twin_daemon_down_unreadable_marker_says_not_regenerated_and_saves(downstore):
    ctx = downstore
    memdir = _memdir(ctx, organised=True)
    _break_marker(memdir)
    before = (memdir / "MEMORY.md").read_bytes()
    (memdir / "third.md").write_text(GMD.format(id="third", t="project", body="3"))
    code, out = _cli("ingest-gmd", "--as-memory", str(memdir))
    _assert_not_regenerated_but_saved(code, out, memdir, before)
    assert "third" in _rows_named(ctx.root, "third"), "the memory was not saved"


def test_twin_daemon_up_unreadable_marker_says_not_regenerated_and_saves(spawn):
    ctx = spawn()
    memdir = _memdir(ctx, organised=True)
    _break_marker(memdir)
    before = (memdir / "MEMORY.md").read_bytes()
    (memdir / "third.md").write_text(GMD.format(id="third", t="project", body="3"))
    try:
        code, out = _cli("ingest-gmd", "--as-memory", str(memdir))
        _assert_not_regenerated_but_saved(code, out, memdir, before)
    finally:
        shutil.rmtree(handoff.default_memory_dir(ctx.root.parent), ignore_errors=True)
    dm.stop_daemon(ctx.root)
    assert "third" in _rows_named(ctx.root, "third"), "the memory was not saved"


def test_twin_the_global_store_says_it_skips_the_index(tmp_path, monkeypatch):
    """The global store has no project memory root: the skip is SAID, never silent."""
    home = Path(tempfile.mkdtemp(prefix="r266g-"))
    groot = home / ".refmatrix"
    groot.mkdir()
    s = Store(groot)
    s.init()
    s.close()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("REFMATRIX_ROOT", str(groot))
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    src = tmp_path / "gmem"
    src.mkdir()
    (src / "gnote.md").write_text(GMD.format(id="gnote", t="project", body="global"))
    try:
        assert not dm.ping(groot, retries=0), "control: no daemon may serve this store"
        code, out = _cli("ingest-gmd", "--as-memory", str(src))
        assert code == 0, out
        assert "MEMORY.md not regenerated: the global store has no project memory root" in out, \
            out
        assert "gnote" in _rows_named(groot, "gnote")
    finally:
        shutil.rmtree(home, ignore_errors=True)


# =============================================== #rm-one-corpus (r1 #s-3) ===

def _seed_brief_corpus(s: Store, part: str) -> dict:
    """Talk and disagreement that lives ONLY in rows scope `memory` must not see: impressions
    mention `imp_only` and contradict each other; a `tag: pattern` doc mentions `pat_only`.
    The memory corpus has its own orphan (`mem_only`) and its own contradiction, as controls.
    The two corpora DIFFER in size (5 memory rows, 4 pattern rows) so a brief that ignores its
    scope cannot match the compile's corpus by count alone (GREEN mutation M3 survived when
    both were 4)."""
    with s.with_partition(part):
        mem_c = s.add_concept("mem_only")
        imp_c = s.add_concept("imp_only")
        pat_c = s.add_concept("pat_only")
        ids = {}
        for n in ("note_m1", "note_m2", "note_m3", "note_m4", "note_m5"):
            ids[n] = s.add_memory(n, f"body of {n}", mtype="project")
            s.link("mentions", mem_c, ids[n])
        for n in ("obs_i1", "obs_i2", "obs_i3", "obs_i4"):
            ids[n] = s.add_memory(n, f"body of {n}", mtype="impression")
            s.link("mentions", imp_c, ids[n])
        for n in ("doc_p1", "doc_p2", "doc_p3", "doc_p4"):
            ids[n] = s.add_memory(n, f"body of {n}", mtype="project", tags=["pattern"])
            s.link("mentions", pat_c, ids[n])
        s.link("contradicts", ids["note_m1"], ids["note_m2"])
        s.link("contradicts", ids["obs_i1"], ids["obs_i2"])
        s.link("contradicts", ids["doc_p1"], ids["doc_p2"])
        s.flush_fragments()
    return ids


@pytest.fixture
def briefstore():
    base, root, part, s = _tmp_store()
    ids = _seed_brief_corpus(s, part)
    yield s, part, ids
    s.close()
    shutil.rmtree(base, ignore_errors=True)


def _labels(res: dict, cls: str) -> set:
    return {b.label for b in res["briefs"] if b.cls == cls}


def test_one_corpus_brief_detectors_exclude_impressions_and_pattern_docs_by_default(briefstore):
    """At HEAD `contradicted` and `orphan-concept` read `brief._memory_ids`, which still takes
    impressions and `tag: pattern` docs — the corpus scope `memory` compile excludes."""
    s, part, _ids = briefstore
    with s.with_partition(part):
        res = brief.compile_briefs(s, classes=["contradicted", "orphan-concept"])
    orphans = _labels(res, "orphan-concept")
    assert "mem_only" in orphans, f"control: the memory corpus' own orphan: {orphans}"
    assert "imp_only" not in orphans and "pat_only" not in orphans, orphans
    contra = _labels(res, "contradicted")
    assert "note_m1 vs note_m2" in contra, f"control: {contra}"
    assert not {c for c in contra if "obs_" in c or "doc_p" in c}, contra
    assert res["stats"]["memories"] == 5, res["stats"]


def test_one_corpus_brief_takes_an_explicit_scope(briefstore):
    """`brief` takes the compile's scope; scope `pattern` is exactly the impressions minus the
    `tag: pattern` docs, as in `consolidate`."""
    s, part, _ids = briefstore
    with s.with_partition(part):
        res = brief.compile_briefs(s, classes=["contradicted", "orphan-concept"],
                                   scope="pattern")
    orphans = _labels(res, "orphan-concept")
    assert orphans == {"imp_only"}, orphans
    assert _labels(res, "contradicted") == {"obs_i1 vs obs_i2"}, res["briefs"]
    assert res["stats"]["memories"] == 4, res["stats"]


@pytest.mark.parametrize("scope", ["memory", "pattern"])
def test_one_corpus_brief_and_compile_read_the_same_rows(briefstore, scope):
    """One predicate, two readers: brief's corpus IS the compile's corpus for the same scope
    (brief additionally drops its own `brief/*` rows, which `EXCLUDE_MTYPES` carries).

    Compared by row IDENTITY, not only by count: every orphan-concept brief's evidence must be
    a row of the compile's corpus for that scope, and the corpus must be non-trivially
    evidenced (the fixture's one orphan per corpus)."""
    s, part, _ids = briefstore
    with s.with_partition(part):
        want = {r["id"] for r in consolidate._memory_rows(
            s, exclude_mtypes=brief.EXCLUDE_MTYPES, scope=scope)}
        other = {r["id"] for r in consolidate._memory_rows(
            s, exclude_mtypes=brief.EXCLUDE_MTYPES,
            scope="pattern" if scope == "memory" else "memory")}
        res = brief.compile_briefs(s, classes=["orphan-concept"], scope=scope)
    assert len(want) != len(other), "control: the fixture corpora must differ in size"
    assert res["stats"]["memories"] == len(want), (scope, res["stats"], sorted(want))
    seen = {int(e) for b in res["briefs"] for e in b.evidence}
    assert seen, f"control: scope {scope} must yield an orphan with evidence: {res['briefs']}"
    assert seen <= want, (
        f"scope {scope}: brief evidence outside the compile's corpus: {sorted(seen - want)}")


# ============================================ #rm-status-route (r1 #m-1) ===

class _Dispatcher:
    """The daemon's REAL dispatcher (`Daemon._handle`) behind a REAL unix socket at the
    store's `socket_path`, so the REAL `rmx_memory_compile` verb dials it. `serve_forever`
    cannot run off the main thread (it installs signal handlers), so this accept loop stands
    in for its socket half only; routing — the thing under test — is `_handle`'s own."""

    def __init__(self, d: dm.Daemon, cli_pool, bg_pool):
        self.d, self.cli, self.bg = d, cli_pool, bg_pool
        self.path = dm.socket_path(d.root)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(self.path))
        self.sock.listen(16)
        self.sock.settimeout(0.2)
        self.stop = threading.Event()
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                c, _ = self.sock.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            threading.Thread(target=self.d._handle, args=(c, self.cli, self.bg),
                             daemon=True).start()

    def close(self):
        self.stop.set()
        self.t.join(5)
        self.sock.close()
        self.path.unlink(missing_ok=True)


def test_status_route_answers_while_a_bg_job_holds_the_bg_pool():
    """`memory_compile status=True` must not queue behind bulk work: the bg pool has 12
    workers in production and a reingest or bridge can hold all of them. At HEAD the op is
    not in `CLI_OPS`, so the status call waits for the bg worker and the verb times out."""
    base, root, part, s = _tmp_store()
    d = dm.Daemon(root)
    d.store = s
    d._log = lambda m: None
    cli = ThreadPoolExecutor(max_workers=2, thread_name_prefix="t266-cli")
    bg = ThreadPoolExecutor(max_workers=1, thread_name_prefix="t266-bg")
    d._cli_pool, d._bg_pool = cli, bg
    gate = threading.Event()
    hold = bg.submit(gate.wait, 30)                 # the one bg worker is occupied
    srv = _Dispatcher(d, cli, bg)
    try:
        probe = bg.submit(lambda: None)
        time.sleep(0.3)
        assert not probe.done(), "control: the bg pool must be held"
        assert dm.ping(root), "control: the dispatcher must answer"
        box: dict = {}

        def _status():
            try:
                box["res"] = verbs.memory_compile(root, status=True, partition=part, timeout=3)
            except Exception as e:        # noqa: BLE001 — asserted below
                box["err"] = e

        t = threading.Thread(target=_status, daemon=True)
        t.start()
        t.join(6)
        assert not t.is_alive(), "the status verb hung past its own 3 s bound"
        assert "err" not in box, (
            f"`memory_compile status=True` queued behind the bg pool: {box.get('err')!r}")
        assert box["res"].get("running") is False, box
    finally:
        gate.set()
        hold.result(timeout=10)
        srv.close()
        cli.shutdown(wait=True)
        bg.shutdown(wait=True)
        s.close()
        shutil.rmtree(base, ignore_errors=True)


# ============================================ #rm-subjects-gmd (r1 #m-5) ===

def test_subjects_gmd_the_verb_carries_the_text_the_cli_writes(spawn, tmp_path):
    """MCP callers get the same subjects GMD the CLI writes to `--out`: the verb result
    carries it, the CLI only writes it."""
    ctx = spawn(_seed_scopes)
    dest = tmp_path / "subjects.md"
    _ok("memory", "compile", "--apply", "--out", str(dest), *P)
    written = dest.read_text()
    assert "rel: catalogs -> [[m_ops_a]]" in written, written   # control: a real render
    res = _compile_verb(ctx, apply=True)
    assert "subjects_gmd" in res, f"the verb result carries no subjects GMD: {sorted(res)}"
    assert res["subjects_gmd"] == written
