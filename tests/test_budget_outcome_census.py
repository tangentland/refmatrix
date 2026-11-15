"""Task 29.4c R3 (`task-29.4-suite-health#r3-budget-census`): the budget-outcome census, the
second half of AC-11.

"Does not assert an outcome that a real-time budget decides unless the test controls which side
of the budget the run falls on." A test function is a hit when it (a) uses a real daemon or runs
a real hook or CLI child through one (`SandboxDaemon`, `spawn_daemon_subprocess`, directly or
through a fixture) and (b) asserts a comparison of an `outcome` field with a string. A hit
passes only when, in the same function, it controls the budget: it builds the command it runs
with `tests.timing.with_budget(command, seconds)` (seconds a literal or `HANG_GUARD_S`), or sets
the budget's knob; otherwise it holds a `budget-outcome` entry with a reason in
`tests/wallclock_allow.json`.

RED at `c4b44d0`: `tests/budget_outcome_census.py` does not exist, and bug-228's test fails the
census as it stands (the frozen copy `tests/fixtures/suite_health/case_bug228_base.py`).

The contract these tests pin for GREEN (`tests/budget_outcome_census.py`):
- `violations(source, relpath) -> list[str]`: the `relpath::function` key of every hit that
  does not control its budget;
- `run_census(tests_root, *, allow_path) -> result` with `.ok` and `.errors`: violations under
  `tests_root` (`tests/fixtures/suite_health/` exempt by path) minus `budget-outcome` entries,
  each of which must carry a non-empty `reason`.

Mutation 21 (the census ignores fixtures) is killed by
`test_must_fail_a_daemon_reached_through_a_fixture`.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
ALLOW = TESTS / "wallclock_allow.json"
BASE_COPY = TESTS / "fixtures" / "suite_health" / "case_bug228_base.py"
REL = "test_task21_1_recall_skip.py"
LIVE = f"{REL}::test_ac2b_live_daemon_recall_writes_one_ok_recall_row"
SILENT_PEER = f"{REL}::test_ac2b_busy_daemon_skip_writes_one_skipped_budget_recall_row"
LIVE_CALL = ("h.run_hook(_recall_cmd(root), root=root, envelope=_envelope(), timeout=240)")


def _bc():
    from tests import budget_outcome_census
    return budget_outcome_census


def _base() -> str:
    return BASE_COPY.read_text()


def _with_import(src: str) -> str:
    return src.replace("from tests import task21_1_support as h",
                       "from tests import task21_1_support as h\n"
                       "from tests.timing import HANG_GUARD_S, with_budget", 1)


def test_bugs228_test_as_it_stands_at_base_fails_the_census():
    src = _base()
    assert src.count(LIVE_CALL) == 1, "the frozen copy no longer holds the live call"
    assert LIVE in _bc().violations(src, REL)


def test_the_silent_peer_skipped_budget_leg_passes():
    """The `skipped_budget` leg uses a silent peer, not a real daemon: not a hit."""
    assert SILENT_PEER not in _bc().violations(_base(), REL)


def test_the_live_test_with_its_budget_through_with_budget_passes():
    src = _with_import(_base()).replace(
        LIVE_CALL, "h.run_hook(with_budget(_recall_cmd(root), HANG_GUARD_S), root=root, "
                   "envelope=_envelope(), timeout=240)")
    assert LIVE not in _bc().violations(src, REL)


def test_with_budget_with_a_literal_passes():
    src = _with_import(_base()).replace(
        LIVE_CALL, "h.run_hook(with_budget(_recall_cmd(root), 60.0), root=root, "
                   "envelope=_envelope(), timeout=240)")
    assert LIVE not in _bc().violations(src, REL)


def test_must_fail_the_budget_swapped_by_a_bare_str_replace():
    src = _base().replace(
        LIVE_CALL, "h.run_hook(_recall_cmd(root).replace('--timeout 5', '--timeout 60'), "
                   "root=root, envelope=_envelope(), timeout=240)")
    assert LIVE in _bc().violations(src, REL)


def test_must_fail_with_budget_given_a_name_the_census_cannot_read():
    src = _with_import(_base()).replace(
        LIVE_CALL, "h.run_hook(with_budget(_recall_cmd(root), budget), root=root, "
                   "envelope=_envelope(), timeout=240)")
    assert LIVE in _bc().violations(src, REL)


SANDBOX_NO_KNOB = """\
from tests import task21_1_support as h

def test_ok_against_a_live_daemon(root):
    with h.SandboxDaemon(root):
        r = h.run_hook("rmx memory recall --timeout 5", root=root, envelope={}, timeout=60)
    row = h.query_rows(root)[-1]
    assert row["outcome"] == "ok", row
"""

SPAWNED_NO_KNOB = """\
from refmatrix import daemon as dm

def test_ok_against_a_spawned_daemon(root, run):
    dm.spawn_daemon_subprocess(root, watch_root=[])
    rows = run(root)
    assert rows[0]["outcome"] == "ok"
"""

THROUGH_A_FIXTURE = """\
import pytest
from tests import task21_1_support as h

@pytest.fixture
def live(root):
    with h.SandboxDaemon(root) as d:
        yield d

def test_ok_through_the_fixture(live, root):
    r = h.run_hook("rmx memory recall --timeout 5", root=root, envelope={}, timeout=60)
    assert h.query_rows(root)[-1]["outcome"] == "ok"
"""

PEER_ONLY = """\
def test_ok_against_a_test_owned_peer(peer, root):
    rows = peer.rows()
    assert rows[0]["outcome"] == "ok"
"""


def test_must_fail_a_synthetic_sandbox_daemon_with_no_knob():
    assert _bc().violations(SANDBOX_NO_KNOB, "test_syn.py") == [
        "test_syn.py::test_ok_against_a_live_daemon"]


def test_must_fail_a_spawned_daemon_with_no_knob():
    assert _bc().violations(SPAWNED_NO_KNOB, "test_syn.py") == [
        "test_syn.py::test_ok_against_a_spawned_daemon"]


def test_must_fail_a_daemon_reached_through_a_fixture():
    """Mutation 21: a test that reaches the daemon through a fixture passes unseen."""
    assert _bc().violations(THROUGH_A_FIXTURE, "test_syn.py") == [
        "test_syn.py::test_ok_through_the_fixture"]


def test_a_test_owned_peer_is_not_a_hit():
    assert _bc().violations(PEER_ONLY, "test_syn.py") == []


# ---- ruling L159: readiness before the hook is a third control form ---------------------------
#
# `SandboxDaemon.wait_models_warm()` called in the SAME test function BEFORE the hook runs
# controls which side of the 5 s budget the run falls on (the budget is then spent on the recall,
# not on the models' cold load: T0.3 #base-sweep-bug228-legs). After the hook, or in another
# function, it controls nothing the census can see.

LIVE_WARM_BEFORE = ("with h.SandboxDaemon(root) as d:\n"
                    "        d.wait_models_warm()\n"
                    "        r = " + LIVE_CALL)
LIVE_WARM_AFTER = ("with h.SandboxDaemon(root) as d:\n"
                   "        r = " + LIVE_CALL + "\n"
                   "        d.wait_models_warm()")
LIVE_WITH = "with h.SandboxDaemon(root):\n        r = " + LIVE_CALL


def test_l159_the_live_test_warmed_before_its_hook_passes():
    src = _base()
    assert src.count(LIVE_WITH) == 1, "the frozen copy no longer holds the live with-block"
    assert LIVE not in _bc().violations(src.replace(LIVE_WITH, LIVE_WARM_BEFORE), REL)


def test_l159_must_fail_the_readiness_call_after_the_hook():
    src = _base().replace(LIVE_WITH, LIVE_WARM_AFTER)
    assert LIVE in _bc().violations(src, REL)


WARM_IN_ANOTHER_FUNCTION = """\
from tests import task21_1_support as h

def _ready(d):
    d.wait_models_warm()

def test_ok_warmed_by_a_helper(root):
    with h.SandboxDaemon(root) as d:
        _ready(d)
        r = h.run_hook("rmx memory recall --timeout 5", root=root, envelope={}, timeout=60)
    assert h.query_rows(root)[-1]["outcome"] == "ok"
"""

WARM_BEFORE_SYNTHETIC = """\
from tests import task21_1_support as h

def test_ok_warmed_first(root):
    with h.SandboxDaemon(root) as d:
        d.wait_models_warm()
        r = h.run_hook("rmx memory recall --timeout 5", root=root, envelope={}, timeout=60)
    assert h.query_rows(root)[-1]["outcome"] == "ok"
"""


def test_l159_must_fail_the_readiness_call_in_a_different_function():
    assert _bc().violations(WARM_IN_ANOTHER_FUNCTION, "test_syn.py") == [
        "test_syn.py::test_ok_warmed_by_a_helper"]


def test_l159_a_synthetic_test_warmed_before_its_hook_passes():
    assert _bc().violations(WARM_BEFORE_SYNTHETIC, "test_syn.py") == []


def _tree(tmp_path: Path, files: dict, entries: list):
    root = tmp_path / "tests"
    root.mkdir(parents=True)
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src))
    allow = tmp_path / "wallclock_allow.json"
    allow.write_text(json.dumps({"entries": entries}))
    return _bc().run_census(root, allow_path=allow)


def test_run_census_fails_on_a_hit_and_names_it(tmp_path):
    r = _tree(tmp_path, {"test_syn.py": SANDBOX_NO_KNOB}, [])
    assert not r.ok
    assert any("test_ok_against_a_live_daemon" in e for e in r.errors), r.errors


def test_run_census_passes_a_hit_with_a_reasoned_budget_outcome_entry(tmp_path):
    entry = {"key": "test_syn.py::test_ok_against_a_live_daemon", "kind": "budget-outcome",
             "reason": "fixture: the budget is the product question this test asks"}
    r = _tree(tmp_path, {"test_syn.py": SANDBOX_NO_KNOB}, [entry])
    assert r.ok, r.errors


def test_must_fail_a_budget_outcome_entry_with_no_reason(tmp_path):
    entry = {"key": "test_syn.py::test_ok_against_a_live_daemon", "kind": "budget-outcome",
             "reason": ""}
    r = _tree(tmp_path, {"test_syn.py": SANDBOX_NO_KNOB}, [entry])
    assert not r.ok


def test_fixture_suite_health_is_exempt_by_path(tmp_path):
    r = _tree(tmp_path, {"fixtures/suite_health/case_syn.py": SANDBOX_NO_KNOB}, [])
    assert r.ok, r.errors
    r2 = _tree(tmp_path / "b", {"fixtures/other/case_syn.py": SANDBOX_NO_KNOB}, [])
    assert not r2.ok


def test_the_tree_passes_the_budget_outcome_census():
    r = _bc().run_census(TESTS, allow_path=ALLOW)
    assert r.ok, r.errors
