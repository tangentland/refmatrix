"""T0.1' (plan-29 task 29.4 stage 1): bug-215 -- the skip gate follows each skip's own
condition and matches its own reason.

WHY. `tests/conftest.py` switched all 19 clone-only pins on one test,
`(_REPO / ".venv-eval").is_dir()`. A littlebig clone whose `.venv-eval` is a SYMLINK to the main
tree's passes that test, so every pin was dropped, and the one skip that still happens there
(the hooks belong to another checkout) failed every run: exit 1 on
`SKIPPED-UNPINNED tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated`
(workflow/review-output/t0.1/base-ac1.1-hooks-symlinked-clone.log). And `SkipGate` matched by
nodeid only, against pinned strings ("clone-only: …") that equal none of the reasons the tests
actually skip with, so a pinned test that started skipping for a NEW reason passed unseen.

What is pinned here (task-t0-suite-trust-sweep `#t0-1`):
- R1.1 / AC-1.2: `allowed_skips(checkout)` in `tests/conftest.py` builds the allowed set per
  entry: the 18 dev-venv pins only when `<checkout>/.venv-eval/bin/rmx` does not exist; the
  hooks pin only when the installed hooks belong to another checkout (`installed_root`, decided
  the way the test decides it). Layouts: no venv, a real venv, a half-built venv dir, a
  symlinked venv (with and without `bin/rmx` behind it), foreign hooks, no hooks file.
- R1.2: every pinned value is the test's own `reason=` string, verbatim.
- AC-1.1 in-session: this session's `ALLOWED_SKIPS` (and the registered gate's) is the builder
  applied to this checkout.
- AC-1.3: `SkipGate` treats a skip as pinned only when its nodeid is allowed AND its reason,
  after pytest's `Skipped: ` prefix, EQUALS the pinned value; anything else is
  `SKIPPED-UNPINNED` with both reasons.

The fixture checkouts are real directories (a real `bin/rmx` file, a real symlink, a real
`.claude/settings.json` read by the real `hooks.installed_root`); nothing is patched.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

import rmx_sandbox  # on sys.path via tests/conftest.py (tests/sandbox_site)
from refmatrix import hooks as hooks_mod

pytest_plugins = ["pytester"]

_REPO = Path(__file__).resolve().parents[1]

# The 18 dev-venv pins and the one hooks pin, each with the test's own `reason=` verbatim
# (task-t0-suite-trust-sweep `#t0-1-skip-reasons`, re-read at 9a5a98a).
_BRIEF = "tests/test_brief_real_daemon.py::"
_ARGV = "tests/test_grep_argv_order_e2e.py::"
_COUNT = "tests/test_grep_count_rows_e2e.py::"
VENV_PINS = {
    _BRIEF + "test_an_unknown_class_fails_loudly_through_the_daemon": "dev rmx not built",
    _BRIEF + "test_brief_runs_end_to_end_through_a_real_daemon": "dev rmx not built",
    _BRIEF + "test_saved_briefs_do_not_grow_the_corpus_on_rerun": "dev rmx not built",
    _BRIEF + "test_the_gmd_flag_does_not_crash_through_a_real_daemon": "dev rmx not built",
    _ARGV + "test_a_directory_walk_keeps_its_files_GROUPED": "dev venv rmx not built",
    _ARGV + "test_a_named_file_still_wins_its_argv_slot_against_a_walk":
        "dev venv rmx not built",
    _ARGV + "test_named_paths_come_back_in_argument_order_not_fanout_order":
        "dev venv rmx not built",
    _ARGV + "test_the_tool_itself_is_the_one_that_scrambles": "needs rmx + rg",
    _COUNT + "test_a_directory_with_no_match_gets_a_zero_row_per_file":
        "dev venv rmx or /usr/bin/grep missing",
    _COUNT + "test_a_directory_with_some_matches_keeps_its_zero_rows":
        "dev venv rmx or /usr/bin/grep missing",
    _COUNT + "test_a_missing_file_beside_a_directory_is_not_a_bare_zero":
        "dev venv rmx or /usr/bin/grep missing",
    _COUNT + "test_a_missing_file_beside_a_match_still_exits_2":
        "dev venv rmx or /usr/bin/grep missing",
    _COUNT + "test_a_missing_file_exits_2_and_says_so": "dev venv rmx or /usr/bin/grep missing",
    _COUNT + "test_two_spellings_keep_their_own_prefix_on_n":
        "dev venv rmx or /usr/bin/grep missing",
    _COUNT + "test_two_spellings_of_one_file_are_two_rows":
        "dev venv rmx or /usr/bin/grep missing",
    "tests/test_grep_evidence_verified.py::test_a_fully_filtered_answer_falls_through_to_the_floor":
        "dev venv rmx not built",
    "tests/test_grep_learning_replay.py::test_arm_a_learns_and_arm_b_learns_exactly_nothing":
        "needs the dev venv's rmx console script",
    "tests/test_grep_no_flag_bundle.py::test_the_documented_pipe_count_works_with_a_bare_flag":
        "dev venv rmx not built",
}
HOOKS_PINS = {
    "tests/test_repo_hooks_in_sync.py::test_installed_hooks_match_generated":
        "hooks belong to another checkout of this commit",
}


# ---- the conftest under test -----------------------------------------------------------------

def _conftest(config):
    """The `tests/conftest.py` module pytest registered for THIS session (not a re-import, which
    would run the sandbox entry a second time), so a mutation of the conftest is what runs."""
    want = (_REPO / "tests" / "conftest.py").resolve()
    for plugin in config.pluginmanager.get_plugins():
        f = getattr(plugin, "__file__", None)
        if f and Path(f).resolve() == want:
            return plugin
    raise AssertionError(f"{want} is not registered as a plugin in this session")


def _builder(config):
    build = getattr(_conftest(config), "allowed_skips", None)
    assert callable(build), (
        "tests/conftest.py defines no `allowed_skips(checkout)`: ALLOWED_SKIPS is still one "
        "`(_REPO / \".venv-eval\").is_dir()` switch over all 19 pins, so a symlinked .venv-eval "
        "drops every pin and a half-built venv keeps none (T0.1' R1.1, bug-215)")
    return build


# ---- fixture checkouts -----------------------------------------------------------------------

def _settings(checkout: Path, owner: "Path | None") -> None:
    """A `.claude/settings.json` whose hook command carries `<owner>/.refmatrix/…`, the marker
    `hooks.installed_root` reads; `owner=None` writes no settings file at all."""
    if owner is None:
        return
    (checkout / ".claude").mkdir(parents=True, exist_ok=True)
    cmd = f"rmx primer --out '{owner}/.refmatrix/PRIMER.md'"
    blob = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": cmd}]}]}}
    (checkout / ".claude" / "settings.json").write_text(json.dumps(blob))
    (checkout / ".claude" / "rmx-hooks.json").write_text("{}")


def _venv_with_rmx(where: Path) -> Path:
    (where / "bin").mkdir(parents=True)
    rmx = where / "bin" / "rmx"
    rmx.write_text("#!/bin/sh\nexit 0\n")
    rmx.chmod(0o755)
    return where


def _layout(tmp_path: Path, venv: str, hooks: str) -> Path:
    checkout = (tmp_path / "checkout").resolve()
    checkout.mkdir()
    if venv == "real":
        _venv_with_rmx(checkout / ".venv-eval")
    elif venv == "half-built":
        (checkout / ".venv-eval" / "bin").mkdir(parents=True)          # a dir, no bin/rmx
    elif venv == "symlink":
        (checkout / ".venv-eval").symlink_to(_venv_with_rmx(tmp_path / "main-tree-venv"),
                                             target_is_directory=True)
    elif venv == "symlink-empty":
        outside = tmp_path / "main-tree-venv"
        (outside / "bin").mkdir(parents=True)
        (checkout / ".venv-eval").symlink_to(outside, target_is_directory=True)
    else:
        assert venv == "none", venv
    owner = {"self": checkout, "foreign": (tmp_path / "main-tree").resolve(), "none": None}[hooks]
    _settings(checkout, owner)
    return checkout


_LAYOUTS = [
    # (id, venv, hooks, expected allowed set)
    ("no-venv", "none", "self", VENV_PINS),
    ("real-venv", "real", "self", {}),
    ("half-built-venv-dir", "half-built", "self", VENV_PINS),
    ("symlinked-venv-foreign-hooks", "symlink", "foreign", HOOKS_PINS),
    ("symlinked-venv-own-hooks", "symlink", "self", {}),
    ("symlinked-venv-without-rmx", "symlink-empty", "self", VENV_PINS),
    ("foreign-hooks-real-venv", "real", "foreign", HOOKS_PINS),
    ("foreign-hooks-no-venv", "none", "foreign", {**VENV_PINS, **HOOKS_PINS}),
    ("no-hooks-file-no-venv", "none", "none", VENV_PINS),
]


# ---- R1.1 / AC-1.2: the allowed-set builder --------------------------------------------------

@pytest.mark.parametrize("venv,hooks,expected", [l[1:] for l in _LAYOUTS],
                         ids=[l[0] for l in _LAYOUTS])
def test_the_allowed_set_follows_each_skips_own_condition(pytestconfig, tmp_path, venv, hooks,
                                                          expected):
    """AC-1.2: the exact allowed set for each checkout layout. A `.venv-eval` that is a symlink
    resolving outside the checkout satisfies neither condition by itself (mutation M1.1, the
    single `is_dir()` switch, fails the half-built, symlinked and foreign-hooks layouts)."""
    build = _builder(pytestconfig)
    checkout = _layout(tmp_path, venv, hooks)
    got = dict(build(checkout))
    assert got == dict(expected), (
        f"layout venv={venv} hooks={hooks}: allowed set differs.\n"
        f"  missing: {sorted(set(expected) - set(got))}\n"
        f"  extra:   {sorted(set(got) - set(expected))}\n"
        f"  wrong reason: "
        f"{ {k: (got[k], expected[k]) for k in set(got) & set(expected) if got[k] != expected[k]} }")


def test_the_hooks_pin_is_decided_the_way_the_hooks_test_decides_it(pytestconfig, tmp_path):
    """R1.1: the hooks pin is allowed exactly when `installed_root(checkout)` is not None and is
    not the checkout -- the condition `tests/test_repo_hooks_in_sync.py` skips on."""
    build = _builder(pytestconfig)
    checkout = _layout(tmp_path, "real", "foreign")
    owner = hooks_mod.installed_root(checkout)
    assert owner is not None and owner != checkout, owner
    assert set(build(checkout)) == set(HOOKS_PINS)


def test_every_pin_is_its_tests_own_reason_verbatim(pytestconfig, tmp_path):
    """R1.2: with every condition true, the builder pins exactly the 19 nodeids, and each value
    is a `reason="…"` string literal in that test's own file. A test whose reason changes must
    change its pin in the same commit; this goes red when only one of them moved."""
    build = _builder(pytestconfig)
    got = dict(build(_layout(tmp_path, "none", "foreign")))
    assert got == {**VENV_PINS, **HOOKS_PINS}, got
    stale = []
    for nodeid, reason in got.items():
        src = (_REPO / nodeid.split("::")[0]).read_text()
        if f'reason="{reason}"' not in src and f"reason='{reason}'" not in src:
            stale.append((nodeid, reason))
    assert not stale, f"pinned reasons that are not the test's own `reason=`: {stale!r}"


# ---- AC-1.1 in-session: this checkout's allowed set ------------------------------------------

def test_this_sessions_allowed_set_is_the_builder_on_this_checkout(pytestconfig):
    """AC-1.1, from inside the session: the pins this run allows are what each pin's own
    condition says about THIS checkout. In a littlebig clone with a symlinked `.venv-eval` that
    is exactly the hooks pin (the venv rmx exists through the symlink; the committed
    `.claude/settings.json` names the main tree), and at T0.1's base it was empty."""
    mod = _conftest(pytestconfig)
    expected = {}
    if not (_REPO / ".venv-eval" / "bin" / "rmx").exists():
        expected.update(VENV_PINS)
    owner = hooks_mod.installed_root(_REPO)
    if owner is not None and owner != _REPO:
        expected.update(HOOKS_PINS)
    assert dict(mod.ALLOWED_SKIPS) == expected, (
        f"ALLOWED_SKIPS for {_REPO} (venv rmx exists: "
        f"{(_REPO / '.venv-eval' / 'bin' / 'rmx').exists()}, hooks owner: {owner}) is "
        f"{dict(mod.ALLOWED_SKIPS)!r}; each pin's own condition gives {expected!r}")
    build = getattr(mod, "allowed_skips", None)
    assert callable(build) and dict(build(_REPO)) == expected
    gate = pytestconfig.pluginmanager.get_plugin("rmx_skip_gate")
    assert isinstance(gate, rmx_sandbox.SkipGate) and dict(gate.allowed) == expected, gate


# ---- AC-1.3: the reason must match exactly ---------------------------------------------------

_INNER = '''
import pytest

@pytest.mark.skipif(True, reason="the pinned reason")
def test_mark_exact():
    pass

def test_call_exact():
    pytest.skip("the pinned reason")

def test_other_reason():
    pytest.skip("a different reason")

@pytest.mark.skipif(True, reason="a new condition turned true")
def test_mark_other_reason():
    pass

def test_runs():
    assert True
'''


def _section(out: str, nodeid: str) -> str:
    """The `SKIPPED-UNPINNED <nodeid>` report, up to the next report line."""
    marker = f"SKIPPED-UNPINNED {nodeid}"
    assert marker in out, f"no `{marker}` line:\n{out[-3000:]}"
    tail = out[out.index(marker):]
    nxt = tail.find("SKIPPED-UNPINNED", len(marker))
    return tail if nxt < 0 else tail[:nxt]


def test_a_pinned_nodeid_skipping_for_another_reason_fails_the_session(pytester):
    """AC-1.3: a pinned nodeid that skips with a DIFFERENT reason fails the session, and the
    report names both reasons; a pinned nodeid that skips with its exact reason (pytest adds
    `Skipped: `) passes, in both the mark and the call form. Mutation M1.2 (nodeid only) passes
    the first half."""
    pytester.makepyfile(test_inner_reason=_INNER)
    pin = "the pinned reason"
    allowed = {f"test_inner_reason.py::{n}": pin
               for n in ("test_mark_exact", "test_call_exact", "test_other_reason",
                         "test_mark_other_reason")}
    gate = rmx_sandbox.SkipGate(allowed)
    result = pytester.runpytest("-p", "no:cacheprovider", plugins=[gate])
    out = result.stdout.str()
    assert result.ret == pytest.ExitCode.TESTS_FAILED, (
        "two pinned nodeids skipped for reasons that are not their pinned reason, and the "
        f"session passed (exit {result.ret}): the gate matched by nodeid only.\n" + out[-3000:])
    for name, actual in (("test_other_reason", "a different reason"),
                         ("test_mark_other_reason", "a new condition turned true")):
        sec = _section(out, f"test_inner_reason.py::{name}")
        assert pin in sec and actual in sec, (
            f"the report for {name} must name both the pinned and the actual reason: {sec!r}")
    tail = out.split("SkipGate:")[-1]
    assert "test_mark_exact" not in tail and "test_call_exact" not in tail, out[-3000:]

    exact = {f"test_inner_reason.py::{n}": pin for n in ("test_mark_exact", "test_call_exact")}
    exact["test_inner_reason.py::test_other_reason"] = "a different reason"
    exact["test_inner_reason.py::test_mark_other_reason"] = "a new condition turned true"
    ok = pytester.runpytest("-p", "no:cacheprovider", plugins=[rmx_sandbox.SkipGate(exact)])
    assert ok.ret == 0, ok.stdout.str()[-3000:]


_INNER_SUB = '''
import pytest

@pytest.mark.skipif(True, reason="dev venv rmx not built")
def test_pin_inside_the_reason():
    pass

@pytest.mark.skipif(True, reason="dev rmx not built")
def test_reason_inside_the_pin():
    pass

@pytest.mark.skipif(True, reason="Dev Rmx Not Built")
def test_case_differs():
    pass
'''


@pytest.mark.parametrize("name,pin", [
    ("test_pin_inside_the_reason", "rmx not built"),
    ("test_reason_inside_the_pin", "dev rmx not built yet"),
    ("test_case_differs", "dev rmx not built"),
])
def test_a_substring_or_near_match_is_not_a_pinned_reason(pytester, name, pin):
    """AC-1.3 / R1.2: the reason is EQUAL to the pin, not contained in it, not containing it,
    not equal ignoring case (mutation M1.2's substring form)."""
    pytester.makepyfile(test_inner_sub=_INNER_SUB)
    nodeid = f"test_inner_sub.py::{name}"
    others = {f"test_inner_sub.py::{n}": r for n, r in (
        ("test_pin_inside_the_reason", "dev venv rmx not built"),
        ("test_reason_inside_the_pin", "dev rmx not built"),
        ("test_case_differs", "Dev Rmx Not Built")) if n != name}
    gate = rmx_sandbox.SkipGate({nodeid: pin, **others})
    result = pytester.runpytest("-p", "no:cacheprovider", plugins=[gate])
    out = result.stdout.str()
    assert result.ret == pytest.ExitCode.TESTS_FAILED, (
        f"{nodeid} skipped with a reason that is not EQUAL to its pin {pin!r}, and the session "
        f"passed (exit {result.ret}).\n" + out[-3000:])
    sec = _section(out, nodeid)
    assert pin in sec, sec
    assert re.search(r"SKIPPED-UNPINNED", out.split("SkipGate:")[-1]), out[-3000:]
