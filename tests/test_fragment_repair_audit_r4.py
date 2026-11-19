"""bug-105 hotfix round-4 audit regressions (ch-bsd `bsd-bug105-hotfix-r4-fb285cc`, 2026-10-14).

Round 4 found that a LIVE `partition merge` cannot be made safe inside this hotfix: moving the
home-binding rebind into a later hold of the FIFO writer lock hands every queued op a binding
that names the partition the merge just deleted (#b4-1, the bug-098 class), and a write naming
SRC between merge chunks orphans its entity (#s4-1). The user's decision d9ae: ship the REPAIR,
FENCE the live merge (the daemon refuses it; an offline merge with the daemon down has no
concurrent writer), and move the merge redesign to the helix plan, which owns merge (d9ac).

It also found four repair-path mutants alive for a third round (#b4-2): the daemon's periodic
flush guard (M1), the `links_skipped` count (M11), the fragment-file repair's delete list (M12)
and the canonical verb on the entity_links side (M14), plus unpinned operator output (M24, M25).
S1 (2026-11-19, one catalog backend) deleted M12's test and M24's CLI listing of unread
fragment dirs with the file-fragment layout.
"""
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner
from pyroaring import BitMap, BitMap64

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix.store import Store
import rmx_sandbox  # task-29.4 #r5: test roots live under the sandbox root (short_root)
from tests.test_bug212_hooks_in_worktrees import _base_env, _entry


@pytest.fixture
def s(tmp_path, monkeypatch):
    st = Store(tmp_path / ".refmatrix"); st.init()
    yield st
    st.close()


def _rows(s):
    con = s._connect()
    out = {}
    for pid, L, blob in con._duck.execute(
            "SELECT partition_id, linkage, blob FROM bitmap_fragments").fetchall():
        out[(pid, L)] = {int(b) for b in BitMap64.deserialize(bytes(blob))}
    return out


def _seed_two_partitions(root: Path) -> None:
    st = Store(root); st.init()
    with st.with_partition("src"):
        c = st.add_concept("k"); st.link("mentions", c, st.upsert_entity(kind="doc", name="o.md"))
    with st.with_partition("dst"):
        st.add_concept("k")
    st.flush_fragments(); st.close()


@pytest.fixture
def live(monkeypatch):
    base = Path(rmx_sandbox.short_root("r4f-"))
    home = base / "h"; home.mkdir()
    for k, v in {"HOME": str(home), "RMX_HOME": str(home / ".refmatrix"),
                 "RMX_SHARED_MODELS": "0", "RMX_MODEL_SOCK": str(base / "m.sock")}.items():
        monkeypatch.setenv(k, v)
    root = base / "p" / ".refmatrix"; root.parent.mkdir()
    _seed_two_partitions(root)
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    try:
        yield root
    finally:
        dm.stop_daemon(root); shutil.rmtree(base, ignore_errors=True)


# ---- the fence (d9ae) --------------------------------------------------------------------------

def test_daemon_refuses_a_live_merge_sync_and_async(live):
    for extra in ({}, {"async": True}):
        r = dm.call(live, "partition_merge", {"src": "src", "dst": "dst", "dry_run": False,
                                              **extra}, timeout=60.0)
        assert not r.get("ok"), r
        assert "offline" in r.get("error", ""), r
    res = dm.call(live, "partition_list", {}, timeout=30.0)["result"]
    rows = res.get("rows", res) if isinstance(res, dict) else res
    names = {p["name"] if isinstance(p, dict) else p for p in rows}
    assert {"src", "dst"} <= names, names          # nothing was merged


def test_daemon_still_answers_a_dry_run_merge(live):
    r = dm.call(live, "partition_merge", {"src": "src", "dst": "dst", "dry_run": True},
                timeout=60.0)
    assert r.get("ok") and r["result"]["dry_run"] is True, r


def test_cli_merge_with_the_daemon_up_is_refused(live, monkeypatch):
    monkeypatch.chdir(live.parent)
    monkeypatch.setenv("REFMATRIX_ROOT", str(live))
    r = CliRunner().invoke(cli_mod.main, ["partition", "merge", "src", "dst", "-y"])
    assert r.exit_code != 0, r.output
    assert "offline" in r.output, r.output


def test_offline_cli_merge_runs_and_prints_the_repair(tmp_path, monkeypatch):
    """With no daemon there is no concurrent writer, so the offline merge stays available and
    still prints its fragment repair (pins the CLI print, M22/M23)."""
    root = tmp_path / "p" / ".refmatrix"; root.parent.mkdir()
    _seed_two_partitions(root)
    monkeypatch.chdir(root.parent)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    r = CliRunner().invoke(cli_mod.main, ["partition", "merge", "src", "dst", "-y"])
    assert r.exit_code == 0, r.output
    assert "fragments repair:" in r.output and "dropped_dead_concept=" in r.output, r.output
    assert "links_dead_concept=" in r.output and "links_dead_entity=" in r.output, r.output


# ---- M1: the daemon's periodic flush guard spans every binding ---------------------------------

def test_periodic_flush_persists_another_bindings_dirty_bits(s):
    with s.with_partition("p"):
        pid = s.partition_id
        c = s.add_concept("k"); e = s.upsert_entity(kind="doc", name="a.md")
        s.link("mentions", c, e)                 # dirty under ('p'), NOT flushed
    logs = []
    n = dm._periodic_flush(s, threading.Lock(), logs.append)
    assert n >= 1, logs
    assert s._pack(c, e) in _rows(s).get((pid, "mentions"), set())


# ---- M11: an entity_links row whose entity is gone is counted, not dropped silently ------------

def test_links_skipped_counts_a_link_to_a_missing_entity(s, tmp_path):
    c = s.add_concept("k"); e = s.upsert_entity(kind="doc", name="a.md")
    s.link("mentions", c, e); s.flush_fragments()
    con = s._connect()._duck
    lid = con.execute("SELECT id FROM linkage_types WHERE name='mentions'").fetchone()[0]
    con.execute("INSERT INTO entity_links (entity_id, linkage_id, concept_id) VALUES (?, ?, ?)",
                [987_654, lid, c])
    rep = s.repair_fragments(dry_run=True, manifest_dir=tmp_path / "m")
    assert rep["links_skipped"] == 1, rep


# ---- M14: a legacy non-canonical linkage name lands in the canonical fragment -------------------

def test_repair_files_a_legacy_snake_verb_link_under_the_canonical_kebab_name(s, tmp_path):
    c = s.add_concept("k"); e = s.upsert_entity(kind="doc", name="a.md")
    con = s._connect()._duck
    con.execute("INSERT INTO linkage_types (id, name) VALUES (9001, 'related_to')")
    con.execute("INSERT INTO entity_links (entity_id, linkage_id, concept_id) VALUES (?, 9001, ?)",
                [e, c])
    s._clear_fragment_caches()
    s.repair_fragments(dry_run=False, manifest_dir=tmp_path / "m")
    rows = _rows(s)
    assert s._pack(c, e) in rows.get((s.partition_id, "related-to"), set()), rows
    assert (s.partition_id, "related_to") not in rows, rows


# ---- M24 / M25: the operator sees every counter --------------------------------------------------

def _tree_digests(d: Path) -> dict:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file()}


def _named(planted: Path, store_root: Path, reported: "list[str]") -> bool:
    """`planted` is named: a reported entry is the planted dir itself or an ancestor of it
    strictly inside the store (`fragments/` / `bitmaps/` as a whole)."""
    for e in reported:
        ep = Path(e)
        if ep == planted or (ep in planted.parents and store_root in ep.parents):
            return True
    return False


@pytest.mark.timeout(120)
@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "applied"])
@pytest.mark.parametrize("entry", ["cli", "store"])
def test_the_repair_names_and_keeps_every_unread_file_layout_dir(entry, dry_run):
    """bsd-s1 r1 #b-1 (ruling L191, 2026-11-19): since S1 nothing reads the on-disk fragment
    layouts, `fragments/<partition>/*.rb64` and the older `bitmaps/<linkage>/<cid>.rb`. On a
    real DuckDB store holding both, `rmx repair-index --fragments` (and the store method it
    runs with no daemon) NAMES both dirs in the unread-dirs report, leaves both byte-identical,
    and leaves `bitmap_fragments` as it was. RED at GREEN be1c6b6c: the writer `_connect`'s kept
    `_migrate_legacy_bitmaps_if_needed` deletes the `.rb` files (no `bitmaps/` dir is ever
    named). Replaces the deleted `test_cli_repair_lists_unread_dirs`."""
    base = Path(rmx_sandbox.short_root("r4u-")).resolve()
    try:
        root = base / "p" / ".refmatrix"
        root.parent.mkdir()
        st = Store(root); st.init()
        c = st.add_concept("k")
        e = st.upsert_entity(kind="doc", name="a.md")
        st.link("mentions", c, e)
        st.flush_fragments()
        part = st.partition_name
        packed = st._pack(c, e)
        before_rows = _rows(st)
        st.close()
        assert before_rows, "fixture: no bitmap_fragments rows"
        frag_dir = root / "fragments" / part
        frag_dir.mkdir(parents=True)
        (frag_dir / "x.rb64").write_bytes(BitMap64([packed]).serialize())
        bm_dir = root / "bitmaps" / "mentions"
        bm_dir.mkdir(parents=True)
        (bm_dir / f"{c}.rb").write_bytes(BitMap([e]).serialize())
        planted = {"fragments": frag_dir, "bitmaps": bm_dir}
        before_files = {k: _tree_digests(d) for k, d in planted.items()}

        if entry == "cli":
            env = {**_base_env(), "REFMATRIX_ROOT": str(root), "COLUMNS": "1000"}
            argv = ["repair-index", "--fragments"] + (["--dry-run"] if dry_run else [])
            r = subprocess.run([sys.executable, str(_entry(base)), *argv], cwd=str(root.parent),
                               env=env, capture_output=True, text=True, timeout=90)
            text = f"exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
            assert r.returncode == 0, text
            prefix = "unread, left in place:"
            reported = [ln.split(prefix, 1)[1].strip() for ln in r.stdout.splitlines()
                        if prefix in ln]
            ro = Store(root, read_only=True)
            try:
                after_rows = _rows(ro)
            finally:
                ro.close()
        else:
            st = Store(root)
            try:
                rep = st.repair_fragments(dry_run=dry_run, manifest_dir=base / "m")
                after_rows = _rows(st)
            finally:
                st.close()
            reported = list(rep.get("unread_dirs") or [])
            text = f"repair_fragments returned {rep}"
        where = f"[{entry}, dry_run={dry_run}]"
        unnamed = [k for k, d in planted.items() if not _named(d, root, reported)]
        assert not unnamed, (f"{where} the unread-dirs report does not name the {unnamed} "
                             f"layout dir(s); reported {reported}\n{text}")
        moved = {k: (before_files[k], _tree_digests(d) if d.is_dir() else None)
                 for k, d in planted.items() if (_tree_digests(d) if d.is_dir() else None)
                 != before_files[k]}
        assert not moved, f"{where} changed or removed a planted unread dir: {moved}\n{text}"
        assert after_rows == before_rows, (
            f"{where} changed bitmap_fragments: {before_rows} -> {after_rows}\n{text}")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_daemon_repair_log_line_names_every_counter(live, monkeypatch):
    r = dm.call(live, "repair_fragments", {"dry_run": True}, timeout=120.0)
    assert r.get("ok"), r
    log = (live / "rmxd.log").read_text()
    lines = [l for l in log.splitlines() if "repair_fragments dry_run=" in l]
    assert lines, log[-2000:]
    for field in ("dropped_dead=", "dropped_dead_concept=", "links_skipped=", "unread_dirs=",
                  "manifest=", "links_dead_concept=", "links_dead_entity="):  # bug-111
        assert field in lines[-1], (field, lines[-1])


# ---- r5 (ch-bsd bsd-bug105-hotfix-r5-fccca72) ---------------------------------------------------

def _drop_link(s, eid, cid):
    s._connect()._duck.execute(
        "DELETE FROM entity_links WHERE entity_id=? AND concept_id=?", [eid, cid])


def _pid(s, name):
    r = s._connect().execute("SELECT id FROM partitions WHERE name=?", (name,)).fetchone()
    return None if r is None else int(r[0])


def test_r5_both_halves_collided_fragment_only_bit_follows_both_remaps(s):
    """#s5-2 (r4 probe Q1, adopted): kills N1 (remap the concept half only)."""
    with s.with_partition("src"):
        sk = s.add_concept("k"); se = s.upsert_entity(kind="doc", name="o.md")
        s.link("mentions", sk, se)
    with s.with_partition("dst"):
        dk = s.add_concept("k"); de = s.upsert_entity(kind="doc", name="o.md")
    s.flush_fragments()
    _drop_link(s, se, sk)
    rep = s.merge_partition("src", "dst")["fragments_repair"]
    assert s._pack(dk, de) in _rows(s).get((_pid(s, "dst"), "mentions"), set())
    assert rep["dropped_dead"] == 0 and rep["dropped_dead_concept"] == 0, rep
    assert rep["remapped"] >= 1, rep


def test_r5_entity_half_only_collided_bit_is_remapped(s):
    """#s5-2 (r4 probe Q2, adopted)."""
    with s.with_partition("dst"):
        dc = s.add_concept("dst-only"); de = s.upsert_entity(kind="doc", name="o.md")
    with s.with_partition("src"):
        se = s.upsert_entity(kind="doc", name="o.md")
        s.link("mentions", dc, se)
    s.flush_fragments()
    _drop_link(s, se, dc)
    rep = s.merge_partition("src", "dst")["fragments_repair"]
    assert s._pack(dc, de) in _rows(s).get((_pid(s, "dst"), "mentions"), set())
    assert rep["dropped_dead"] == 0, rep


def test_r5_a_remap_only_change_in_an_unmoved_row_is_written(s):
    """#s5-2 (r4 probe Q3, adopted): kills N2 (changed set computed from the remapped rows)."""
    with s.with_partition("src"):
        sk = s.add_concept("k")
    with s.with_partition("dst"):
        dk = s.add_concept("k"); x = s.upsert_entity(kind="doc", name="x.md")
        s.link("mentions", sk, x)
    s.flush_fragments()
    dpid = _pid(s, "dst")
    rep = s.merge_partition("src", "dst")["fragments_repair"]
    got = _rows(s).get((dpid, "mentions"), set())
    assert s._pack(dk, x) in got and s._pack(sk, x) not in got, got
    assert rep["rows_changed"] >= 1 and rep["remapped"] >= 1, rep


def test_r5_offline_merge_prints_remapped_and_the_manifest(tmp_path, monkeypatch):
    """#s5-2 / F4: the offline merge's report names `remapped` and the manifest path."""
    root = tmp_path / "p" / ".refmatrix"; root.parent.mkdir()
    st = Store(root); st.init()
    with st.with_partition("src"):
        c = st.add_concept("k"); e = st.upsert_entity(kind="doc", name="o.md")
        st.link("mentions", c, e)
    with st.with_partition("dst"):
        st.add_concept("k")
    st.flush_fragments()
    hid = _pid(st, "src")
    con = st._connect()._duck
    blob = con.execute("SELECT blob FROM bitmap_fragments WHERE partition_id=? AND "
                       "linkage='mentions'", [hid]).fetchone()[0]
    bm = BitMap64.deserialize(bytes(blob)); bm.add(st._pack(888_888, e))     # a dead concept
    con.execute("UPDATE bitmap_fragments SET blob=? WHERE partition_id=? AND linkage='mentions'",
                [bm.serialize(), hid])
    st.close()
    monkeypatch.chdir(root.parent)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    r = CliRunner().invoke(cli_mod.main, ["partition", "merge", "src", "dst", "-y"])
    assert r.exit_code == 0, r.output
    assert "remapped=" in r.output and "manifest:" in r.output, r.output
    assert "hub resume" in r.output, r.output        # #m5-2: the restart hint, not kickstart -k


def test_r5_cli_fence_refuses_a_busy_daemon_too(tmp_path, monkeypatch):
    """#m5-1: `ping` cannot tell busy from absent; the fence asks require_daemon, so a busy
    daemon (alive, not answering) is refused, not treated as offline."""
    from refmatrix import verbs as verbs_mod
    root = tmp_path / "p" / ".refmatrix"; root.parent.mkdir()
    _seed_two_partitions(root)
    monkeypatch.chdir(root.parent)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))

    def busy(r, **kw):
        raise verbs_mod.VerbBusyError("daemon busy pid=1")
    monkeypatch.setattr(verbs_mod, "require_daemon", busy)
    r = CliRunner().invoke(cli_mod.main, ["partition", "merge", "src", "dst", "-y"])
    # A busy daemon is refused at the preview's store open, before the fence; the fence's busy
    # branch covers a daemon that turns busy between the preview and the merge. F5 (drop that
    # branch) is equivalent for this probe; recorded in bug105-r6-mutations.log.
    assert r.exit_code != 0 and "busy" in r.output, r.output


def test_r5_the_dead_job_api_is_gone():
    """#b5-1: the fence removed the async merge, the only writer of the daemon's job table, so
    its reader (`job_status`, `rmx daemon job`) goes too."""
    assert "job_status" not in dm.OPS
    assert "job" not in cli_mod.daemon.commands


# ---- r6 (ch-bsd bsd-bug105-hotfix-r6-fe7abea): the auditor's probes P1-P4, adopted ------------

def _seq_require(monkeypatch, seq):
    """require_daemon answers from `seq` in order: 'absent' | 'busy' | 'up'."""
    from refmatrix import verbs as verbs_mod
    calls = []

    def fake(root, **kw):
        state = seq[min(len(calls), len(seq) - 1)]
        calls.append(state)
        if state == "absent":
            raise verbs_mod.VerbAbsentError("daemon not running")
        if state == "busy":
            raise verbs_mod.VerbBusyError("daemon busy pid=1")
        return {"up": True}
    monkeypatch.setattr(verbs_mod, "require_daemon", fake)
    return calls


def _offline_root(tmp_path, monkeypatch):
    root = tmp_path / "p" / ".refmatrix"; root.parent.mkdir()
    _seed_two_partitions(root)
    monkeypatch.chdir(root.parent)
    monkeypatch.setenv("REFMATRIX_ROOT", str(root))
    return root


def test_p1_fence_refuses_a_daemon_that_turned_busy_after_the_preview(tmp_path, monkeypatch):
    """Kills F5: preview offline (absent), the FENCE sees busy -> its own refusal."""
    root = _offline_root(tmp_path, monkeypatch)
    calls = _seq_require(monkeypatch, ["absent", "busy"])
    r = CliRunner().invoke(cli_mod.main, ["partition", "merge", "src", "dst", "-y"])
    assert r.exit_code != 0, r.output
    assert "live partition merge is disabled" in r.output and "busy" in r.output, (calls, r.output)
    st = Store(root)
    names = {n for (n,) in st._connect().execute("SELECT name FROM partitions").fetchall()}
    st.close()
    assert {"src", "dst"} <= names, names


def test_p2_fence_refusal_names_hub_pause(tmp_path, monkeypatch):
    """Pins #m5-2's refusal text: preview offline, the fence sees an up daemon."""
    _offline_root(tmp_path, monkeypatch)
    _seq_require(monkeypatch, ["absent", "up"])
    r = CliRunner().invoke(cli_mod.main, ["partition", "merge", "src", "dst", "-y"])
    assert r.exit_code != 0, r.output
    assert "hub pause" in r.output and "hub resume" in r.output, r.output


def test_p3_remapped_counts_exactly_the_rewritten_bits(s):
    """`remapped` == number of fragment bits whose (concept, entity) pack changed: one
    collided bit with both halves remapped -> exactly 1; an untouched DST bit -> 0."""
    with s.with_partition("src"):
        sk = s.add_concept("k"); se = s.upsert_entity(kind="doc", name="o.md")
        s.link("mentions", sk, se)
    with s.with_partition("dst"):
        dk = s.add_concept("k"); de = s.upsert_entity(kind="doc", name="o.md")
        other = s.add_concept("other"); y = s.upsert_entity(kind="doc", name="y.md")
        s.link("mentions", other, y)
    s.flush_fragments()
    before = _rows(s)
    expect = 0
    idmap = {sk: dk, se: de}
    mask = (1 << 32) - 1
    for _k, bits in before.items():
        for b in bits:
            c, e = b >> 32, b & mask
            if c in idmap or e in idmap:
                expect += 1
    rep = s.merge_partition("src", "dst")["fragments_repair"]
    assert rep["remapped"] == expect and expect >= 1, (rep, expect, before)


def test_p4_offline_merge_cli_prints_the_true_remapped_count(tmp_path, monkeypatch):
    """Kills R5 (CLI prints a constant): the seed's one collided bit prints remapped=1+."""
    root = _offline_root(tmp_path, monkeypatch)
    r = CliRunner().invoke(cli_mod.main, ["partition", "merge", "src", "dst", "-y"])
    assert r.exit_code == 0, r.output
    m = re.search(r"remapped=(\d+)", r.output)
    assert m and int(m.group(1)) >= 1, r.output
