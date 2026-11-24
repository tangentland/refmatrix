"""plan-29 task 29.4a (stage 4): four run tiers, assigned by one function (task-29.4 `#r1`).

WHY. The user asked on 2026-11-14 for the tests to run modularly. A run tier is decided per
FILE by `tests/tiering.py::tier_of`, an ordered rule (devtree, timing, daemon, unit; the first
match wins), so each file has exactly one tier by construction (plan-29 D11). conftest turns
the tier into a `tier_<name>` marker on every item, so `-m tier_unit` selects a tier while the
plain command still runs every test (`#r1-also`). Fixture suites are not part of the suite:
they are `case_*.py` under `tests/fixtures/suite_health/`, and `norecursedirs` keeps a stray
`test_*.py` there out of the plain collection (`#r1-fixtures`).

Found at this task's base (33825985, R0 of 29.4a): the plain command does not collect.
`tests/fixtures/suite_health/case_killed_mid_test.py` (29.4b) ends in `_test.py`, which is
pytest's OTHER default `python_files` pattern, so `pytest --collect-only -q` with no path
stops on `ModuleNotFoundError: No module named 'suite_health_support'` (1 error, 5370 tests
collected, "Interrupted"). Lane runs pass explicit files and never saw it. The collection test
below and the fixture-name guard pin it.

THE CONTRACT pinned here for GREEN (the spec leaves the names open):
- `tier_of(path) -> str`, one of `TIERS = ("unit", "daemon", "devtree", "timing")`; it raises
  `tiering.TierError` (a `ValueError`) for a `test_*.py` it cannot read or one that is not
  directly in a `tests/` directory.
- Everything `tier_of` reads besides the file comes from the file's own `tests/` directory:
  `conftest.py` (the skip pins: today `_FOREIGN_HOOKS_PINS`, keyed `tests/<file>::<test>`; the
  spec's `_CLONE_ONLY_SKIPS` no longer exists), `wallclock_allow.json` (entry keys
  `<file>::<test>::<assert source>`), and the helper modules a file imports from it
  (`from tests.x import …`, `from tests import x`, followed transitively).
- `DEVTREE_FILES`, `ALWAYS_FILES`, `SERIAL_GROUP`: dicts, repo-relative path -> reason.

Mutations this file kills (task-29.4 `#test-strategy`): 1 (`tier_of` ignores helper imports:
the helper and transitive-helper sources come back `unit`) and 2 (the marker hook skips files
in one tier: an item without its tier marker in the plain collection).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests import suite_health_tree as sht

REPO = sht.REPO
TESTS = REPO / "tests"
TIERS = ("unit", "daemon", "devtree", "timing")

# Hang guard (not a bound under test): collecting the whole suite took 67 s at load 6.8 at
# the base sha; a hang becomes a failure with the output.
_COLLECT_HANG_GUARD_S = 600.0


def _tiering():
    from tests import tiering
    return tiering


def _run(cmd: list, cwd: Path, **env) -> "subprocess.CompletedProcess":
    e = dict(os.environ)
    e.update(env)
    try:
        return subprocess.run(cmd, cwd=str(cwd), env=e, capture_output=True, text=True,
                              timeout=_COLLECT_HANG_GUARD_S)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) \
            else (exc.stdout or "")
        pytest.fail(f"{' '.join(cmd)} hung past {_COLLECT_HANG_GUARD_S} s:\n{out[-3000:]}")


# ---- tier_of on the real files ---------------------------------------------------------------

def test_tier_of_gives_every_test_file_exactly_one_known_tier():
    """task-29.4 #ac-1: one of the four names for every `tests/test_*.py`; the four per-tier
    lists are disjoint and their union is every test file."""
    tiering = _tiering()
    assert tuple(tiering.TIERS) == TIERS
    files = sorted(TESTS.glob("test_*.py"))
    by = {t: set() for t in TIERS}
    for f in files:
        t = tiering.tier_of(f)
        assert t in TIERS, f"{f.name}: {t!r}"
        by[t].add(f.name)
    for i, a in enumerate(TIERS):
        for b in TIERS[i + 1:]:
            assert not by[a] & by[b], (a, b, by[a] & by[b])
    assert set().union(*by.values()) == {f.name for f in files}
    assert all(by[t] for t in TIERS), f"an empty tier: { {t: len(v) for t, v in by.items()} }"


@pytest.mark.parametrize("name,tier", [
    ("test_kwic.py", "unit"),
    ("test_daemon_reaper.py", "daemon"),
    ("test_plan2_remedy.py", "timing"),
    ("test_repo_hooks_in_sync.py", "devtree"),
    ("test_bug230_repo_scope_gate.py", "devtree"),
], ids=lambda v: v)
def test_tier_of_on_real_files(name, tier):
    """One real file per tier, each for its rule: no signal; `subprocess` and a real daemon;
    eleven entries in `wallclock_allow.json`; a skip pin in conftest (`_FOREIGN_HOOKS_PINS`)
    and a real-home read; `DEVTREE_FILES` (bug-230)."""
    assert _tiering().tier_of(TESTS / name) == tier


def test_named_lists_exist_and_carry_their_reasons():
    """task-29.4 #ac-1: every name in `DEVTREE_FILES`, `ALWAYS_FILES`, the serial group and
    `SANDBOX_SELF_TESTS` (ruling L192 (1)) exists on disk, with a reason; `ALWAYS_FILES` holds
    #r6-parts' set and the census tests; `SANDBOX_SELF_TESTS` holds the five sandbox tests."""
    tiering = _tiering()
    for label in ("DEVTREE_FILES", "ALWAYS_FILES", "SERIAL_GROUP", "SANDBOX_SELF_TESTS"):
        d = getattr(tiering, label)
        assert isinstance(d, dict), f"{label} is a {type(d).__name__}, not path -> reason"
        for path, why in d.items():
            assert (REPO / path).is_file(), f"{label}: {path} is not a file under {REPO}"
            assert path.startswith("tests/test_"), f"{label}: {path} is not repo-relative"
            assert isinstance(why, str) and why.strip(), f"{label}: {path} has no reason"
    want = {"test_docs_generated.py", "test_verb_parity.py", "test_bug212_r4_red.py",
            "test_repo_hooks_in_sync.py", "test_gmd_lint_requires_version.py",
            "test_version_single_source.py", "test_wallclock_census.py",
            "test_budget_outcome_census.py", "test_tmp_root_census.py"}
    have = {Path(p).name for p in tiering.ALWAYS_FILES}
    assert want <= have, f"ALWAYS_FILES lacks {sorted(want - have)}"
    assert "tests/test_bug230_repo_scope_gate.py" in tiering.DEVTREE_FILES
    listed = {Path(k).name for k in tiering.SANDBOX_SELF_TESTS}
    assert set(_SANDBOX_SELF_TESTS) <= listed, \
        f"SANDBOX_SELF_TESTS lacks {sorted(set(_SANDBOX_SELF_TESTS) - listed)}"


# Ruling L192 (1): the real-home devtree rule over-matched. At 33825985, ten test files read the
# real home (`rmx_sandbox.real_home(` / `RMX_SANDBOX_REAL_HOME`). Five are the sandbox's own
# tests: they read the real home to aim their deny and decoy checks, and they must run in every
# clone and lane (tier (c) runs in neither), so `SANDBOX_SELF_TESTS` exempts them by name. The
# other five depend on the owning checkout and stay devtree.
_SANDBOX_SELF_TESTS = ("test_sandbox_children.py", "test_sandbox_refusal.py",
                       "test_sandbox_hardening.py", "test_sandbox_child_extensions.py",
                       "test_sandbox_redirect.py")
_REAL_HOME_DEVTREE = ("test_grep_learning_replay.py", "test_bug179_anchor_parity.py",
                      "test_lint_gmd_memdir_fallback.py", "test_gmd_lint_requires_version.py",
                      "test_repo_hooks_in_sync.py")


@pytest.mark.parametrize("name", _SANDBOX_SELF_TESTS + _REAL_HOME_DEVTREE, ids=lambda v: v)
def test_real_home_readers_are_devtree_except_the_sandbox_self_tests(name):
    """Ruling L192 (1). Every file here reads the real home (checked, so a file that stops
    reading it is noticed); the five sandbox self-tests are not devtree, the other five are.
    Must-fail: with the exemption dropped the five sandbox files come back devtree."""
    src = (TESTS / name).read_text()
    assert "real_home(" in src or "RMX_SANDBOX_REAL_HOME" in src, f"{name} no longer reads it"
    tier = _tiering().tier_of(TESTS / name)
    if name in _SANDBOX_SELF_TESTS:
        assert tier != "devtree", f"{name}: a sandbox self-test was put in tier (c)"
        assert tier in TIERS
    else:
        assert tier == "devtree", f"{name}: {tier}"


# ---- must-fail: synthetic sources fed to the rule --------------------------------------------

_ALLOW_KEY = "test_bound.py::test_waits::elapsed < 2.0"


def _synthetic(tmp_path: Path) -> Path:
    """A `tests/` directory holding one file per rule, its helpers, a conftest with one skip
    pin, and a wall-clock allow list with one entry."""
    t = tmp_path / "tests"
    t.mkdir()
    files = {
        "test_plain.py": "def test_x():\n    assert 1 + 1 == 2\n",
        "test_subproc.py": "import subprocess\n\ndef test_x():\n"
                           "    subprocess.run(['true'], check=True)\n",
        "test_helper.py": "from tests.spawner import go\n\ndef test_x():\n    go()\n",
        "test_deep.py": "from tests import middle\n\ndef test_x():\n    middle.run()\n",
        "middle.py": "from tests.spawner import go\n\ndef run():\n    go()\n",
        "spawner.py": "from refmatrix import daemon\n\ndef go():\n"
                      "    return daemon.spawn_daemon_subprocess(None, watch_root=[])\n",
        "test_pinned.py": "def test_hooks():\n    assert True\n",
        "test_realhome.py": "import rmx_sandbox\n\ndef test_x():\n"
                            "    assert rmx_sandbox.real_home().is_dir()\n",
        "test_bound.py": "import time\n\ndef test_waits():\n    t0 = time.monotonic()\n"
                         "    elapsed = time.monotonic() - t0\n    assert elapsed < 2.0\n",
        "test_bound_and_proc.py": "import subprocess, time\n\ndef test_waits():\n"
                                  "    t0 = time.monotonic()\n    subprocess.run(['true'])\n"
                                  "    elapsed = time.monotonic() - t0\n"
                                  "    assert elapsed < 2.0\n",
        "test_broken.py": "def test_x(:\n    pass\n",
        "conftest.py": '_FOREIGN_HOOKS_PINS = {\n'
                       '    "tests/test_pinned.py::test_hooks": "pinned in this checkout",\n'
                       '}\n',
        "wallclock_allow.json": json.dumps({"entries": [
            {"key": _ALLOW_KEY, "kind": "legacy", "class": "A", "note": "fixture"},
            {"key": "test_bound_and_proc.py::test_waits::elapsed < 2.0", "kind": "legacy",
             "class": "A", "note": "fixture"}]}),
    }
    for name, src in files.items():
        (t / name).write_text(src)
    (t / "sub").mkdir()
    (t / "sub" / "test_nested.py").write_text("def test_x():\n    assert True\n")
    return t


@pytest.mark.parametrize("name,tier", [
    ("test_plain.py", "unit"),
    ("test_subproc.py", "daemon"),
    ("test_helper.py", "daemon"),
    ("test_deep.py", "daemon"),
    ("test_pinned.py", "devtree"),
    ("test_realhome.py", "devtree"),
    ("test_bound.py", "timing"),
    ("test_bound_and_proc.py", "timing"),
], ids=lambda v: v)
def test_tier_rule_on_synthetic_sources(tmp_path, name, tier):
    """task-29.4 #ac-1's must-fail cases: `subprocess.run(` is not unit; a helper (direct or
    transitive) that calls `spawn_daemon_subprocess` is not unit; a skip pin is devtree; a
    real-home read is devtree; an allow-listed bound is timing, and timing wins over a process
    signal (the rule is ordered). Kills mutation 1 (helper imports ignored)."""
    t = _synthetic(tmp_path)
    assert _tiering().tier_of(t / name) == tier


@pytest.mark.parametrize("rel", ["sub/test_nested.py", "test_missing.py", "test_broken.py"],
                         ids=["in-a-subdirectory", "missing", "unparseable"])
def test_tier_of_raises_rather_than_defaulting(tmp_path, rel):
    """task-29.4 #r1-also: a test file in a subdirectory of `tests/`, or one `tier_of` cannot
    read, is an error, not a default tier."""
    t = _synthetic(tmp_path)
    tiering = _tiering()
    with pytest.raises(tiering.TierError):
        tiering.tier_of(t / rel)
    assert issubclass(tiering.TierError, ValueError)


# ---- the markers, and the plain command ------------------------------------------------------

_DUMP_PLUGIN = textwrap.dedent('''
    """Writes every collected item's node id and its tier_* markers (test_suite_tiers.py)."""
    import json
    import os


    def pytest_collection_finish(session):
        with open(os.environ["RMX_294A_TIER_DUMP"], "w") as fh:
            for it in session.items:
                tiers = sorted({m.name for m in it.iter_markers() if m.name.startswith("tier_")})
                fh.write(json.dumps({"nodeid": it.nodeid, "tiers": tiers}) + "\\n")
''')


def test_plain_collection_is_clean_and_every_item_carries_its_files_tier_marker(tmp_path):
    """task-29.4 #ac-1 / #ac-10 on the real suite: the PLAIN command (no path, no `-m`)
    collects with exit 0; every item carries exactly one `tier_<name>` marker, the one
    `tier_of` gives its file; so the four tiers' item counts sum to the plain count. Every
    collected item is in a top-level `tests/test_*.py` (no fixture leaks in).

    Kills mutation 2 (the marker hook skips one tier's files). RED at the base sha for two
    reasons: the collection error (module docstring) and no markers."""
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "rmx294a_tier_dump.py").write_text(_DUMP_PLUGIN)
    dump = tmp_path / "items.jsonl"
    pp = os.pathsep.join([str(plugin_dir)] + [p for p in os.environ.get("PYTHONPATH", "")
                                              .split(os.pathsep) if p])
    r = _run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
              "-p", "rmx294a_tier_dump"], REPO, PYTHONPATH=pp, RMX_294A_TIER_DUMP=str(dump))
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"the plain collection exited {r.returncode}:\n{out[-3000:]}"
    items = [json.loads(ln) for ln in dump.read_text().splitlines() if ln.strip()]
    assert items, "nothing collected"
    tiering = _tiering()
    want_by_file: dict = {}
    counts = {t: 0 for t in TIERS}
    bad = []
    for it in items:
        rel = it["nodeid"].split("::", 1)[0]
        assert rel.startswith("tests/test_") and rel.count("/") == 1, f"collected {rel}"
        if rel not in want_by_file:
            want_by_file[rel] = "tier_" + tiering.tier_of(REPO / rel)
        if it["tiers"] != [want_by_file[rel]]:
            bad.append((it["nodeid"], it["tiers"], want_by_file[rel]))
        else:
            counts[want_by_file[rel][len("tier_"):]] += 1
    assert not bad, f"{len(bad)} items without exactly their file's tier marker; first: {bad[:5]}"
    assert sum(counts.values()) == len(items), counts


def test_dash_m_selects_one_tier_and_the_markers_are_registered(tmp_path):
    """task-29.4 #r1-also: `-m tier_<name>` selects that tier's files, `--strict-markers`
    accepts the four markers (registered in `pytest_configure`), and with no `-m` every tier
    is collected. On a fixture checkout of one unit and one daemon file."""
    tree = sht.build(tmp_path, {"test_plain.py": "case_trivial", "test_proc.py": "case_pass_child"})
    base = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
            "--strict-markers"]

    def nodes(*extra):
        r = _run(base + list(extra), tree)
        ids = [ln for ln in r.stdout.splitlines() if "::" in ln]
        return r, ids

    r, unit = nodes("-m", "tier_unit")
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    assert unit == ["tests/test_plain.py::test_nothing"], unit
    r, daemon = nodes("-m", "tier_daemon")
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    assert daemon == ["tests/test_proc.py::test_passes_with_a_child"], daemon
    r, both = nodes()
    assert r.returncode == 0 and sorted(both) == sorted(unit + daemon), both


# ---- fixture suites are not part of the suite --------------------------------------------------

def test_no_fixture_file_matches_pytests_default_test_patterns():
    """task-29.4 #r1-fixtures: fixtures are `case_*.py`; nothing under `tests/fixtures/` may be
    named as pytest collects by default (`test_*.py` OR `*_test.py`). At the base sha
    `case_killed_mid_test.py` matches the second and broke the plain collection."""
    hits = sorted(p.relative_to(REPO).as_posix() for p in (TESTS / "fixtures").rglob("*.py")
                  if p.name.startswith("test_") or p.stem.endswith("_test"))
    assert hits == [], f"fixture files pytest would collect: {hits}"


def test_norecursedirs_keeps_a_planted_test_file_out_of_the_plain_collection(tmp_path):
    """task-29.4 #r1-fixtures: `[tool.pytest.ini_options]` `norecursedirs` holds `fixtures` and
    `sandbox_site`, so a `test_*.py` dropped under either is not collected by the plain
    command. Behaviour, on a copy of this checkout's `pyproject.toml` and a planted file in
    each directory (the must-fail case: at the base sha both are collected)."""
    co = tmp_path / "co"
    (co / "tests" / "fixtures" / "x").mkdir(parents=True)
    (co / "tests" / "sandbox_site").mkdir(parents=True)
    (co / "pyproject.toml").write_text((REPO / "pyproject.toml").read_text())
    (co / "tests" / "test_real.py").write_text("def test_real():\n    assert True\n")
    planted = "def test_planted():\n    assert True\n"
    (co / "tests" / "fixtures" / "x" / "test_planted.py").write_text(planted)
    (co / "tests" / "sandbox_site" / "test_planted.py").write_text(planted)
    r = _run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
             co)
    ids = [ln for ln in r.stdout.splitlines() if "::" in ln]
    assert ids == ["tests/test_real.py::test_real"], (ids, (r.stdout + r.stderr)[-2000:])
