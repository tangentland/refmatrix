"""Task 29.4c R3 (`task-29.4-suite-health#r3-census`, `#r3-kinds`, `#r3-scope`): the wall-clock
census, AC-4 and the wall-clock half of AC-11.

RED at `c4b44d0`: `tests/wallclock_census.py`, `tests/timing.py` and `tests/wallclock_allow.json`
do not exist. The tree-level nodes are the census proper; a census that passes at base is not a
RED test, so the must-fail cases on synthetic trees are what is RED (29.4 `#test-strategy`).

The contract these tests pin for GREEN (one module, `tests/wallclock_census.py`):

- `find_bounds(source, relpath) -> list` of objects with `.key`, `.function`, `.lineno`. A
  bound is an `assert` with an UPPER bound on a clock difference, on a name assigned from one, or
  on an elapsed-like name, whatever the limit is (literal, named constant, expression). `.key` is
  `relpath::test function::normalised assert source`, with no line number.
- `run_census(tests_root, *, allow_path, specs_root, legacy_baseline=None) -> result` with
  `.ok`, `.errors` (list of str), `.counts` (`{"legacy": n, "feature-bound": m}`) and
  `.report()` (text that prints the two counts apart). `legacy_baseline` is the set of keys that
  existed at the task's base; `None` means the committed baseline GREEN freezes.
- the allow file is `{"entries": [...]}`. Entry kinds: `legacy` (`key`, `class` in A/B/C/D),
  `feature-bound` (`key`, `ac` = `<spec id>#<anchor>`, `knob` = `env:NAME` | `const:mod.NAME` |
  `arg:param`, `max_s` <= 2.0, `clause` quoted from the AC's own text) and `budget-outcome`
  (`key` = `relpath::function`, `reason`; read by the budget-outcome census, ignored here).
- exempt by form: a lower bound, and `< HANG_GUARD_S` where the name is imported from
  `tests/timing.py`; the census checks that constant is >= 60. Exempt by path:
  `tests/fixtures/suite_health/` (its bounds are the fixture), and nothing else under
  `tests/fixtures/`.

Mutations this file kills (29.4 `#test-strategy`): 7 (numeric literals only:
`test_ac4_must_fail_*took_lt_LIMIT*`), 8 (stale entries ignored: `test_ac4_a_stale_entry_fails`),
18 (`test_ac11_a_new_legacy_entry_fails`), 19 (`test_ac11_feature_bound_*spec_id*`/`*anchor*`),
20 (`test_ac11_feature_bound_whose_test_never_sets_its_knob_fails`), 23
(`test_ac11_arg_knob_passed_as_a_variable_fails`).
"""
from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
ALLOW = TESTS / "wallclock_allow.json"
PLANS = REPO / "workflow" / "plans"
WEIGHTS = TESTS / "shard_weights.json"

# 29.4 #r3-scope with the R0 band (task-29.4-r0-durations#bands-d-order): tier (d) is 782.1 s
# serial against a 6-minute band, so the heaviest files' bounds are replaced in duration order
# until the band holds. These four take it to 348.8 s.
R3_SCOPE_FILES = ("test_task25_1_recall_budget.py", "test_plan3_remedy_r5.py",
                  "test_plan3_remedy_r4.py", "test_task3_6_r9_remedy.py")
TIER_D_BAND_S = 6 * 60
CLASS_NAMES = ("hang guard", "budget honoured", "did not block", "latency measurement")

TIMING_OK = "HANG_GUARD_S = 60.0\n"

SPEC = """\
---
gmd: "0.1"
id: task-fixture-deadlines
title: "fixture spec"
tags: [fixture]
---

# Fixture spec {#root}

- **AC-1.** The deadline fires: the call returns within 0.5 s of `RMX_FIX_DEADLINE_S`. {#ac-1}
- **AC-2.** The drain gives up within 1 s and the reaper within 2 s. {#ac-2}
- **AC-3.** Nothing here is about time. {#ac-3}
"""


def _census():
    from tests import wallclock_census
    return wallclock_census


def _tree(tmp_path: Path, files: dict, *, timing: str = TIMING_OK) -> Path:
    root = tmp_path / "tests"
    root.mkdir()
    (root / "timing.py").write_text(timing)
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src))
    return root


def _specs(tmp_path: Path) -> Path:
    d = tmp_path / "plans"
    d.mkdir()
    # The file name is NOT the id: the census resolves the frontmatter id (29.4 #r3-kinds).
    (d / "some-other-file-name.md").write_text(SPEC)
    return d


def _allow(tmp_path: Path, entries: list) -> Path:
    p = tmp_path / "wallclock_allow.json"
    p.write_text(json.dumps({"entries": entries}, indent=1))
    return p


def _run(tmp_path, files, entries, *, baseline=(), timing=TIMING_OK):
    wc = _census()
    root = _tree(tmp_path, files, timing=timing)
    return wc.run_census(root, allow_path=_allow(tmp_path, entries),
                         specs_root=_specs(tmp_path), legacy_baseline=set(baseline))


def _keys(source: str, relpath: str = "test_syn.py") -> list:
    return [b.key for b in _census().find_bounds(textwrap.dedent(source), relpath)]


def _text(result) -> str:
    return "\n".join(result.errors) + "\n" + result.report()


# ---- AC-4: what the census finds ------------------------------------------------------------

CLOCKDIFF = """\
import time
def test_a():
    t0 = time.monotonic()
    assert time.monotonic() - t0 < 2.0
"""
BOUND_NAME = """\
import time
def test_a():
    t0 = time.monotonic()
    x = time.monotonic() - t0
    assert x < 2.0
"""
ELAPSED_FROM_CLOCK = """\
import time
def test_a():
    t0 = time.perf_counter()
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0
"""
TOOK_LT_LIMIT = """\
LIMIT = 4.0
def test_a(run):
    took = run()
    assert took < LIMIT
"""
CHAINED_WALL = """\
def test_a(run):
    wall = run()
    assert 0.5 < wall < 3.0
"""


@pytest.mark.parametrize("source", [CLOCKDIFF, BOUND_NAME, ELAPSED_FROM_CLOCK, TOOK_LT_LIMIT,
                                    CHAINED_WALL],
                         ids=["clockdiff_lt_literal", "name_bound_from_clock",
                              "elapsed_from_clock_lt_literal", "took_lt_LIMIT",
                              "chained_0_5_lt_wall_lt_3"])
def test_ac4_must_fail_each_upper_bound_is_found(source):
    """AC-4's four synthetic sources (and the bound-name shape) each yield exactly one bound."""
    keys = _keys(source)
    assert len(keys) == 1, keys
    assert keys[0].startswith("test_syn.py::test_a::"), keys


@pytest.mark.parametrize("source", [CLOCKDIFF, TOOK_LT_LIMIT, CHAINED_WALL],
                         ids=["clockdiff_lt_literal", "took_lt_LIMIT", "chained_0_5_lt_wall_lt_3"])
def test_ac4_must_fail_an_unlisted_bound_fails_naming_file_test_and_classes(tmp_path, source):
    r = _run(tmp_path, {"test_syn.py": source}, [])
    assert not r.ok, _text(r)
    text = _text(r)
    assert "test_syn.py" in text and "test_a" in text, text
    for name in CLASS_NAMES:
        assert name in text.lower(), (name, text)


def test_ac4_a_lower_bound_is_not_a_bound(tmp_path):
    src = """\
    import time
    def test_a():
        t0 = time.monotonic()
        elapsed = time.monotonic() - t0
        assert elapsed >= 1.0
    """
    assert _keys(src) == []
    r = _run(tmp_path, {"test_syn.py": src}, [])
    assert r.ok, _text(r)


def test_ac4_hang_guard_imported_from_tests_timing_is_exempt(tmp_path):
    src = """\
    import time
    from tests.timing import HANG_GUARD_S
    def test_a():
        t0 = time.monotonic()
        assert time.monotonic() - t0 < HANG_GUARD_S
    """
    assert _keys(src) == []
    r = _run(tmp_path, {"test_syn.py": src}, [])
    assert r.ok, _text(r)


def test_ac4_must_fail_a_local_hang_guard_name_is_not_exempt(tmp_path):
    """The exemption is by import, not by spelling: a file that defines its own HANG_GUARD_S
    has an ordinary named-constant bound."""
    src = """\
    import time
    HANG_GUARD_S = 5.0
    def test_a():
        t0 = time.monotonic()
        assert time.monotonic() - t0 < HANG_GUARD_S
    """
    assert len(_keys(src)) == 1
    r = _run(tmp_path, {"test_syn.py": src}, [])
    assert not r.ok, _text(r)


def test_ac4_must_fail_a_hang_guard_below_60s_fails_the_census(tmp_path):
    src = """\
    import time
    from tests.timing import HANG_GUARD_S
    def test_a():
        t0 = time.monotonic()
        assert time.monotonic() - t0 < HANG_GUARD_S
    """
    r = _run(tmp_path, {"test_syn.py": src}, [], timing="HANG_GUARD_S = 30.0\n")
    assert not r.ok, _text(r)
    assert "HANG_GUARD_S" in _text(r), _text(r)


def test_ac4_the_key_carries_no_line_number():
    shifted = "\n\n\n# moved down three lines\n" + CLOCKDIFF
    assert _keys(CLOCKDIFF) == _keys(shifted)
    (b,) = _census().find_bounds(shifted, "test_syn.py")
    assert b.lineno == 8 and b.key == _keys(CLOCKDIFF)[0], (b.lineno, b.key)


def test_ac4_a_listed_bound_passes(tmp_path):
    (key,) = _keys(CLOCKDIFF)
    entry = {"key": key, "kind": "legacy", "class": "A"}
    ok = _run(tmp_path / "ok", {"test_syn.py": CLOCKDIFF}, [entry], baseline={key})
    assert ok.ok, _text(ok)


def test_ac4_a_stale_entry_fails(tmp_path):
    """An entry whose assert no longer exists fails: the list is exact and only shrinks
    (mutation 8)."""
    stale = {"key": "test_syn.py::test_gone::time.monotonic() - t0 < 2.0", "kind": "legacy",
             "class": "A"}
    r = _run(tmp_path, {"test_syn.py": "def test_a():\n    assert True\n"}, [stale],
             baseline={stale["key"]})
    assert not r.ok, _text(r)
    assert "test_gone" in _text(r), _text(r)


def test_ac4_fixture_suite_health_is_exempt_by_path_and_nothing_else_is(tmp_path):
    ok = _run(tmp_path / "a", {"fixtures/suite_health/case_slow.py": CLOCKDIFF}, [])
    assert ok.ok, _text(ok)
    bad = _run(tmp_path / "b", {"fixtures/other/case_slow.py": CLOCKDIFF}, [])
    assert not bad.ok, _text(bad)
    assert "case_slow.py" in _text(bad), _text(bad)


# ---- AC-11: the allow list cannot be used as a way round the census -------------------------

def _fb(key: str, **over) -> dict:
    e = {"key": key, "kind": "feature-bound", "ac": "task-fixture-deadlines#ac-1",
         "knob": "env:RMX_FIX_DEADLINE_S", "max_s": 1.0,
         "clause": "returns within 0.5 s of `RMX_FIX_DEADLINE_S`"}
    e.update(over)
    return e


ENV_KNOB = """\
import time
def test_deadline(monkeypatch, run):
    monkeypatch.setenv("RMX_FIX_DEADLINE_S", "{value}")
    t0 = time.monotonic()
    run()
    assert time.monotonic() - t0 < 1.5
"""
ENV_KNOB_NEVER_SET = """\
import time
def test_deadline(run):
    t0 = time.monotonic()
    run()
    assert time.monotonic() - t0 < 1.5
"""
CONST_KNOB = """\
import time
def test_deadline(monkeypatch, run):
    monkeypatch.setattr("refmatrix.daemon.FIX_DEADLINE_S", 0.2)
    t0 = time.monotonic()
    run()
    assert time.monotonic() - t0 < 1.5
"""
ARG_KNOB = """\
import time
def test_deadline(run):
    t = 0.2
    t0 = time.monotonic()
    run_git(["status"], {call})
    assert time.monotonic() - t0 < 1.5
"""


def _one(tmp_path, source, entry_over=None, *, entries=None):
    src = textwrap.dedent(source)
    (key,) = _keys(src)
    ents = entries(key) if entries else [_fb(key, **(entry_over or {}))]
    return _run(tmp_path, {"test_syn.py": src}, ents)


def test_ac11_a_new_legacy_entry_fails(tmp_path):
    """Mutation 18: a `legacy` entry whose key did not exist at the task's base gets in."""
    (key,) = _keys(CLOCKDIFF)
    entry = {"key": key, "kind": "legacy", "class": "A"}
    r = _run(tmp_path, {"test_syn.py": CLOCKDIFF}, [entry], baseline=set())
    assert not r.ok, _text(r)
    assert key in _text(r) or "test_a" in _text(r), _text(r)


def test_ac11_feature_bound_env_knob_passes(tmp_path):
    r = _one(tmp_path, ENV_KNOB.format(value="0.2"))
    assert r.ok, _text(r)
    assert r.counts == {"legacy": 0, "feature-bound": 1}, r.counts


def test_ac11_feature_bound_const_knob_passes(tmp_path):
    r = _one(tmp_path, CONST_KNOB, {"knob": "const:refmatrix.daemon.FIX_DEADLINE_S"})
    assert r.ok, _text(r)


def test_ac11_feature_bound_arg_knob_with_a_literal_passes(tmp_path):
    r = _one(tmp_path, ARG_KNOB.format(call="timeout=0.2"), {"knob": "arg:timeout"})
    assert r.ok, _text(r)


def test_ac11_feature_bound_with_no_ac_fails(tmp_path):
    def ents(key):
        e = _fb(key)
        del e["ac"]
        return [e]
    r = _one(tmp_path, ENV_KNOB.format(value="0.2"), entries=ents)
    assert not r.ok, _text(r)
    assert "test_deadline" in _text(r), _text(r)


def test_ac11_feature_bound_whose_spec_id_does_not_exist_fails(tmp_path):
    """Mutation 19: a made-up AC id gets in when the census does not resolve `ac`."""
    r = _one(tmp_path, ENV_KNOB.format(value="0.2"), {"ac": "task-no-such-spec#ac-1"})
    assert not r.ok, _text(r)
    assert "task-no-such-spec" in _text(r), _text(r)


def test_ac11_feature_bound_whose_spec_id_is_only_a_file_name_fails(tmp_path):
    """The census resolves the frontmatter `id`, not the file stem."""
    r = _one(tmp_path, ENV_KNOB.format(value="0.2"), {"ac": "some-other-file-name#ac-1"})
    assert not r.ok, _text(r)


def test_ac11_feature_bound_whose_anchor_does_not_exist_fails(tmp_path):
    r = _one(tmp_path, ENV_KNOB.format(value="0.2"), {"ac": "task-fixture-deadlines#ac-99"})
    assert not r.ok, _text(r)
    assert "ac-99" in _text(r), _text(r)


def test_ac11_feature_bound_whose_test_never_sets_its_knob_fails(tmp_path):
    """Mutation 20: a test that names a knob and never sets it would wait the production
    value."""
    r = _one(tmp_path, ENV_KNOB_NEVER_SET)
    assert not r.ok, _text(r)
    assert "RMX_FIX_DEADLINE_S" in _text(r), _text(r)


def test_ac11_feature_bound_value_over_max_s_fails(tmp_path):
    r = _one(tmp_path, ENV_KNOB.format(value="5.0"))
    assert not r.ok, _text(r)
    assert "test_deadline" in _text(r), _text(r)


def test_ac11_feature_bound_max_s_above_two_seconds_fails(tmp_path):
    r = _one(tmp_path, ENV_KNOB.format(value="0.2"), {"max_s": 3.0})
    assert not r.ok, _text(r)


def test_ac11_a_second_entry_for_an_ac_with_one_clause_fails(tmp_path):
    src_a = textwrap.dedent(ENV_KNOB.format(value="0.2"))
    src_b = src_a.replace("def test_deadline", "def test_deadline_again")
    (ka,) = _keys(src_a, "test_a_syn.py")
    (kb,) = _keys(src_b, "test_b_syn.py")
    r = _run(tmp_path, {"test_a_syn.py": src_a, "test_b_syn.py": src_b}, [_fb(ka), _fb(kb)])
    assert not r.ok, _text(r)
    assert "ac-1" in _text(r), _text(r)


def test_ac11_an_ac_with_two_clauses_may_own_two_entries(tmp_path):
    src_a = textwrap.dedent(ENV_KNOB.format(value="0.2"))
    src_b = src_a.replace("def test_deadline", "def test_deadline_again")
    (ka,) = _keys(src_a, "test_a_syn.py")
    (kb,) = _keys(src_b, "test_b_syn.py")
    ents = [_fb(ka, ac="task-fixture-deadlines#ac-2", clause="gives up within 1 s"),
            _fb(kb, ac="task-fixture-deadlines#ac-2", clause="the reaper within 2 s")]
    r = _run(tmp_path, {"test_a_syn.py": src_a, "test_b_syn.py": src_b}, ents)
    assert r.ok, _text(r)


def test_ac11_an_entry_whose_clause_is_not_in_its_ac_fails(tmp_path):
    r = _one(tmp_path, ENV_KNOB.format(value="0.2"),
             {"ac": "task-fixture-deadlines#ac-3", "clause": "returns within 0.5 s"})
    assert not r.ok, _text(r)


def test_ac11_arg_knob_whose_call_omits_the_parameter_fails(tmp_path):
    r = _one(tmp_path, ARG_KNOB.format(call="check=True"), {"knob": "arg:timeout"})
    assert not r.ok, _text(r)
    assert "timeout" in _text(r), _text(r)


def test_ac11_arg_knob_passed_as_a_variable_fails(tmp_path):
    """Mutation 23: the census accepts any call that names the parameter, literal or not."""
    r = _one(tmp_path, ARG_KNOB.format(call="timeout=t"), {"knob": "arg:timeout"})
    assert not r.ok, _text(r)
    assert "timeout" in _text(r), _text(r)


def test_ac11_arg_knob_literal_over_max_s_fails(tmp_path):
    r = _one(tmp_path, ARG_KNOB.format(call="timeout=5.0"), {"knob": "arg:timeout"})
    assert not r.ok, _text(r)


def test_ac11_the_census_prints_the_two_counts_apart(tmp_path):
    fb_src = textwrap.dedent(ENV_KNOB.format(value="0.2"))
    (kf,) = _keys(fb_src, "test_fb.py")
    (kl,) = _keys(CLOCKDIFF, "test_legacy.py")
    r = _run(tmp_path, {"test_fb.py": fb_src, "test_legacy.py": CLOCKDIFF},
             [_fb(kf), {"key": kl, "kind": "legacy", "class": "A"}], baseline={kl})
    assert r.ok, _text(r)
    assert r.counts == {"legacy": 1, "feature-bound": 1}, r.counts
    rep = r.report()
    assert re.search(r"legacy\D{0,20}1\b", rep) and re.search(r"feature-bound\D{0,20}1\b", rep), rep


def test_ac11_budget_outcome_entries_are_not_wallclock_entries(tmp_path):
    """The two censuses share the allow file; a `budget-outcome` entry is never stale here."""
    entry = {"key": "test_syn.py::test_a", "kind": "budget-outcome", "reason": "fixture"}
    r = _run(tmp_path, {"test_syn.py": "def test_a():\n    assert True\n"}, [entry])
    assert r.ok, _text(r)


# ---- the tree -------------------------------------------------------------------------------

def _entries() -> list:
    return json.loads(ALLOW.read_text())["entries"]


def _wallclock_entries() -> list:
    return [e for e in _entries() if e.get("kind") in ("legacy", "feature-bound")]


def test_the_tree_passes_the_wallclock_census(capsys):
    r = _census().run_census(TESTS, allow_path=ALLOW, specs_root=PLANS)
    print(r.report())
    assert r.ok, _text(r)


def test_the_legacy_list_starts_at_the_r0_count_and_only_shrinks():
    """77 at `f3709d2` once `HANG_BOUND_S` is renamed (29.4 #r3-census); unchanged at
    `4c6a0c6` (task-29.4-r0-durations#baseline-restated-table) and at `c4b44d0`."""
    r = _census().run_census(TESTS, allow_path=ALLOW, specs_root=PLANS)
    assert r.counts["legacy"] <= 77, r.counts


def test_bug228_and_bug231_tests_hold_no_entry():
    """AC-4 / AC-6: the two rows are replaced, not allow-listed, in either kind."""
    hits = [e["key"] for e in _entries()
            if (e["key"].startswith("test_plan4_remedy.py::") and "graceful_stop" in e["key"])
            or (e["key"].startswith("test_task21_1_recall_skip.py::")
                and "live_daemon_recall" in e["key"])]
    assert hits == [], hits


def test_r3_scope_the_four_heaviest_tier_d_files_hold_no_entry():
    hits = [e["key"] for e in _wallclock_entries() if e["key"].split("::")[0] in R3_SCOPE_FILES]
    assert hits == [], hits


def test_r3_scope_no_class_c_or_d_legacy_entry_remains():
    """Class C and D sites are replaced everywhere (29.4 #r3-scope); what stays records its
    class, and it is A or B."""
    bad = [(e["key"], e.get("class")) for e in _wallclock_entries()
           if e["kind"] == "legacy" and e.get("class") not in ("A", "B")]
    assert bad == [], bad


def test_r3_scope_tier_d_projected_within_its_band():
    """Tier (d) is the files that still hold an allow entry (29.4 #r1, rule 2). Their R0
    weights must sum to the 6-minute band (task-29.4-r0-durations#bands)."""
    weights = json.loads(WEIGHTS.read_text())["files"]
    files = sorted({e["key"].split("::")[0] for e in _wallclock_entries()})
    missing = [f for f in files if f"tests/{f}" not in weights]
    assert missing == [], missing
    total = sum(weights[f"tests/{f}"] for f in files)
    assert total <= TIER_D_BAND_S, (round(total, 2), files)
