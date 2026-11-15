"""Task T0.3: the load harness's pure logic (`scripts/t03_load_harness.py`), against the bands
as pre-registered in `task-t0-suite-trust-sweep#t0-3-bands`.

The harness decides whether a row has a reproducer and whether a fix held, so the arithmetic
that decides it is pinned here: the frozen load list, the placement, the cap, what a trial's
outcome is (the target's own, r3 m-1), void and hang, and the two bands.

RED: written before the harness; proven failing with the harness absent
(`workflow/review-output/t0.3/red-harness-absent.log`).
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
R0_SUMMARY = REPO / "workflow" / "implementation_summaries" / "task-29.4-r0-durations.md"


def _h():
    spec = importlib.util.spec_from_file_location(
        "t03_load_harness", REPO / "scripts" / "t03_load_harness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_load_list_is_stage_0s_top25_frozen():
    """`#t0-3-r0`: the 25 files of `task-29.4-r0-durations#top25`, in that order."""
    text = R0_SUMMARY.read_text()
    block = text.split("### The 25 heaviest files {#top25}", 1)[1].split("{#top25-table}", 1)[0]
    files = re.findall(r"^\| \d+ \| `([^`]+)` \|", block, re.M)
    assert len(files) == 25, files
    assert list(_h().TOP25) == [f"tests/{f}" for f in files]


def test_every_file_a_cap_needs_has_an_r0_weight():
    h = _h()
    w = h.load_weights()
    need = list(h.TOP25) + [h.file_of(n) for n in h.ROWS.values()]
    assert [f for f in need if f not in w] == []


def test_the_five_rows_name_tests_that_exist():
    h = _h()
    assert sorted(h.ROWS) == ["bug-091", "bug-130", "bug-190", "bug-228", "bug-231"]
    for node in h.ROWS.values():
        path, fn = node.split("::")
        tree = ast.parse((REPO / path).read_text())
        assert fn in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}, node


def test_the_band_constants_are_the_spec_s():
    h = _h()
    assert (h.LEVELS, h.BASE_TRIALS, h.REPRO_FAILS, h.FIX_PASSES, h.MAX_VOIDS) == (
        (3, 5, 8), 10, 3, 45, 3)
    assert (h.CAP_FACTOR, h.CAP_FLOOR_S) == (3.0, 300.0)


def test_split_load_is_heaviest_first_into_the_lightest():
    h = _h()
    w = {"a": 10.0, "b": 7.0, "c": 5.0, "d": 4.0, "e": 1.0}
    assert h.split_load(list(w), w, 2) == [["a", "d"], ["b", "c", "e"]]
    assert h.split_load(list(w), w, 3) == [["a"], ["b", "e"], ["c", "d"]]


def test_split_load_refuses_a_file_with_no_weight():
    with pytest.raises(KeyError):
        _h().split_load(["a", "zz"], {"a": 1.0}, 2)


def test_the_cap_is_three_times_T_with_a_300s_floor_and_counts_the_target_file():
    h = _h()
    w = {"tests/x.py": 100.0, "tests/y.py": 50.0, "tests/t.py": 20.0}
    cap, total = h.trial_cap([["tests/x.py"], ["tests/y.py"]], ["tests/t.py::test_a"], w)
    assert (cap, total) == (510.0, 170.0)
    cap, total = h.trial_cap([["tests/t.py"]], ["tests/t.py::test_a"], w)
    assert (cap, total) == (300.0, 40.0)


def test_the_level_3_trial_is_capped_by_the_stage_0_weights():
    h = _h()
    w = h.load_weights()
    load = h.split_load(list(h.TOP25), w, 3)
    assert sorted(f for p in load for f in p) == sorted(h.TOP25)
    cap, total = h.trial_cap(load, [h.ROWS["bug-091"]], w)
    top = sum(w[f] for f in h.TOP25)
    assert round(top, 1) == 1972.1                     # task-29.4-r0-durations#top25
    assert total == top + w["tests/test_watch.py"]
    assert cap == 3 * total


N = "tests/t.py::test_a"


def _start(node=N):
    return {"node": node, "event": "start"}


def _rep(phase, outcome, node=N, e=None):
    return {"node": node, "event": "report", "phase": phase, "outcome": outcome,
            "duration": 0.1, "e_lines": e or [], "crash": None}


def test_a_pass_is_setup_call_teardown_passed():
    recs = [_start(), _rep("setup", "passed"), _rep("call", "passed"), _rep("teardown", "passed")]
    assert _h().node_outcomes(recs, [N], target_exited=True)[N]["outcome"] == "pass"


def test_a_fail_carries_its_first_e_line_and_phase():
    recs = [_start(), _rep("setup", "passed"),
            _rep("call", "failed", e=["E   KeyError: 'rewrite_bytes_all'", "E   more"]),
            _rep("teardown", "passed")]
    o = _h().node_outcomes(recs, [N], target_exited=True)[N]
    assert o == {"outcome": "fail", "phase": "call", "e_line": "E   KeyError: 'rewrite_bytes_all'",
                 "call_s": 0.1}


def test_a_teardown_error_is_a_fail():
    recs = [_start(), _rep("setup", "passed"), _rep("call", "passed"),
            _rep("teardown", "failed", e=["E   OSError: busy"])]
    o = _h().node_outcomes(recs, [N], target_exited=True)[N]
    assert (o["outcome"], o["phase"]) == ("fail", "teardown")


def test_a_started_node_cut_off_by_the_cap_is_a_hang():
    recs = [_start(), _rep("setup", "passed")]
    assert _h().node_outcomes(recs, [N], target_exited=False)[N] == {"outcome": "hang"}


def test_a_node_that_never_started_is_not_run():
    assert _h().node_outcomes([], [N], target_exited=False)[N] == {"outcome": "not-run"}


def test_a_cap_hit_after_the_target_finished_is_void_and_before_it_is_counted():
    h = _h()
    assert h.trial_status({}, cap_hit=True, target_exited=True) == "void"
    assert h.trial_status({}, cap_hit=True, target_exited=False) == "counted"
    assert h.trial_status({}, cap_hit=False, target_exited=True) == "counted"


def test_base_band_three_failures_in_ten_is_the_reproducer_and_hangs_count():
    h = _h()
    seq = ["pass"] * 7 + ["fail", "hang", "fail"]
    assert h.base_band(seq) == {"trials": 10, "failures": 3, "reproducer": True,
                                "decided": True}
    assert h.base_band(["pass"] * 8 + ["fail", "fail"])["reproducer"] is False


def test_base_band_decides_early_once_the_rest_cannot_change_it():
    """Ruling L141: a level stops early once every row is decided."""
    h = _h()
    assert h.base_band(["fail"] * 3) == {"trials": 3, "failures": 3, "reproducer": True,
                                         "decided": True}
    assert h.base_band(["pass"] * 8)["decided"] is True           # 0 + 2 left < 3
    assert h.base_band(["pass"] * 7)["decided"] is False          # 0 + 3 left could reach 3
    assert h.base_band(["pass"] * 6 + ["fail"])["decided"] is False
    assert h.base_band(["pass"] * 8 + ["fail"])["decided"] is True  # 1 + 1 left < 3


def test_fix_band_needs_45_consecutive_passes_and_any_failure_ends_it():
    h = _h()
    assert h.fix_band(["pass"] * 45) == {"held": True, "passes": 45}
    assert h.fix_band(["pass"] * 44 + ["hang"]) == {
        "held": False, "passes_before_failure": 44, "failure": "hang"}
    assert h.fix_band(["pass"] * 10)["held"] is None
