"""ch-bsd r1 #b-2, the ORDER half: a gate with measured power.

`rmx grep`'s floor inherits `rg`'s PARALLEL fan-out order verbatim, because
`produced = res.stdout.splitlines()` was never reordered — while grep's
contract for named paths is argument order. The defect is NONDETERMINISTIC,
which is why a first attempt to confirm it looked clean and nearly got the fix
deleted as unproven.

GATE POWER, measured by the audit over 40 runs per size — how often the
UNFIXED build happens to hold argv order by luck:

    2 files: 18/40 held  -> an argv-order assertion fails unfixed code ~55%
    3 files:  1/40 held  ->                                           97.5%
    4 files:  0/40 held  ->                                            100%
    8 files:  0/40 held  ->                                            100%

So this file uses SIX files of 400 matching lines. At two files the assertion
is a coin flip and would have read as "no defect"; at 4+ the unfixed build
fails every run.

Three traps, all of which a plausible version of this test falls into:

  * **A shell control is not a control.** The PreToolUse rewrite hook replaces
    even an absolute-path `/usr/bin/grep`, and survives a `;` separator. With
    `RMXGREP_MODE=rich` set (this machine's config) BOTH sides of such a probe
    are `rmx` and agree by construction. Every exec here is `shell=False` with
    a list argv, and the `# rmx grep fallback via rg` banner on stderr is the
    discriminator — the control asserts it is ABSENT.
  * **Argv rank, not `sorted()`.** The fixture is deliberately REVERSE
    alphabetical, so an alphabetical sort would pass an alphabetical fixture
    and still be wrong.
  * **`-c` is not evidence for the sort.** Seeding the zero counts in argv
    order already fixes `-c`'s order, because dicts preserve insertion order.
    A green `-c` test says nothing about `triples`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RMX = Path(__file__).resolve().parents[1] / ".venv-eval" / "bin" / "rmx"
HAS_RG = shutil.which("rg") is not None
N_FILES = 6
N_LINES = 400


@pytest.fixture
def many_files(tmp_path):
    """Six files, 400 matching lines each, named so argv order is the REVERSE
    of alphabetical order."""
    names = [f"f{i}.txt" for i in range(N_FILES)]
    for n in names:
        (tmp_path / n).write_text("alpha\n" * N_LINES)
    from refmatrix.store import Store
    s = Store(tmp_path / ".refmatrix", backend="duckdb")
    s.init()
    s.close()
    return tmp_path, list(reversed(names))


def _first_appearance(stdout: str) -> list:
    """File order by first appearance, which is what fan-out scrambles."""
    seen: list = []
    for line in stdout.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = Path(line.split(":", 1)[0]).name
        if f not in seen:
            seen.append(f)
    return seen


def _run(argv: list, cwd: Path) -> "tuple[str, str, int]":
    r = subprocess.run(argv, capture_output=True, text=True, cwd=str(cwd),
                       timeout=120)
    return r.stdout, r.stderr, r.returncode


@pytest.mark.skipif(not RMX.exists(), reason="dev venv rmx not built")
def test_named_paths_come_back_in_argument_order_not_fanout_order(many_files):
    """THE gate. Deleting the argv sort fails this 40/40 at six files."""
    cwd, argv_names = many_files

    out, err, code = _run([str(RMX), "grep", "-n", "alpha", *argv_names], cwd)

    assert code == 0, (code, err)
    assert _first_appearance(out) == argv_names, (
        f"fan-out order leaked: {_first_appearance(out)} != {argv_names}")


@pytest.mark.skipif(not shutil.which("grep"), reason="no grep")
def test_the_control_is_real_grep_and_it_holds_argument_order(many_files):
    """The control, asserted to BE the control. `/usr/bin/grep` through a shell
    is rewritten to the shim; this is a direct exec and the absence of the
    fallback banner proves nothing rewrote it."""
    cwd, argv_names = many_files
    grep = shutil.which("grep") or "/usr/bin/grep"

    out, err, code = _run([grep, "-nH", "alpha", *argv_names], cwd)

    assert code == 0, (code, err)
    assert "rmx grep fallback" not in err, (
        "the control was rewritten to rmx — this measures rmx against itself")
    assert _first_appearance(out) == argv_names


@pytest.mark.skipif(not (RMX.exists() and HAS_RG), reason="needs rmx + rg")
def test_the_tool_itself_is_the_one_that_scrambles(many_files):
    """Attribution, not just symptom: rg's own output is NOT argv order at this
    size, which is why the renderer has to impose it. If this ever starts
    holding argv order, the gate above has lost its power and the comment at
    the top of this file is stale."""
    cwd, argv_names = many_files
    rg = shutil.which("rg")

    orders = set()
    for _ in range(3):
        out, _err, _code = _run([rg, "-nH", "--no-heading", "-e", "alpha",
                                 *argv_names], cwd)
        orders.add(tuple(_first_appearance(out)))

    assert orders, "rg produced nothing"
    scrambled = any(list(o) != argv_names for o in orders)
    assert scrambled, (
        "rg held argv order on every run at this size — the gate above can no "
        "longer distinguish the fix from its absence; raise N_FILES/N_LINES "
        "or re-measure the power table in this docstring")


@pytest.mark.skipif(not RMX.exists(), reason="dev venv rmx not built")
def test_a_directory_walk_is_not_reordered(many_files):
    """The carve-out: argv order applies to NAMED paths. A walk keeps the
    tool's own order, because re-sorting it invents an order grep does not
    promise either."""
    cwd, _argv_names = many_files

    out, err, code = _run([str(RMX), "grep", "-rn", "alpha", "."], cwd)

    assert code == 0, (code, err)
    assert len(_first_appearance(out)) == N_FILES, out[:400]
