"""Throwaway checkouts for the task-29.4a tests (run tiers, the sharded runner, the merge gate).

WHY. The runner (`scripts/ptest.sh` -> `scripts/ptest.py`) and `tier_of` act on a CHECKOUT: its
`tests/`, its `scripts/`, its `workflow/review-output/`, and whether it is the owning one (its
own `.refmatrix/`, a `.venv-eval` inside it). The fixture suites that prove them must fail,
error at teardown, skip unpinned and touch a live path on purpose, so they cannot be part of
the real suite (task-29.4 `#r1-fixtures`): they live as `case_*.py` under
`tests/fixtures/suite_health/`, and a test copies the ones it needs into a tree built here,
under the name `tests/test_*.py`, beside this checkout's own test support (conftest, sandbox
site, helpers, `tiering.py` once it exists) and runner scripts. `src` is a symlink to this
checkout's `src`, so the code under test is the checkout's.

Two shapes, as task-29.4 `#r7` defines "owning":
- `owning=False` (a littlebig clone): no `.refmatrix/`, and `.venv-eval` a symlink that
  resolves OUTSIDE the tree (the clone's `.venv-eval` links to the dev tree's);
- `owning=True`: a `.refmatrix/` directory and a real `.venv-eval/` directory inside the tree.
  The shards' interpreter is never read from it: the tests set `RMX_PYTEST_PY`.

Only file operations live here (no process is started), so this module carries no run-tier
signal of its own.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
CASES = TESTS / "fixtures" / "suite_health"
SCRIPTS = ("ptest.sh", "ptest.py")


def build(root: Path, cases: dict, *, owning: bool = False, weights: "dict | None" = None,
          tiering_extra: str = "", lint_exit: "int | None" = None) -> Path:
    """A checkout at `root/co`. `cases` maps a `tests/test_*.py` name to a `case_*.py` stem.

    `weights` (repo-relative path -> seconds) replaces `tests/shard_weights.json`'s `files`.
    `tiering_extra` is appended to the copied `tests/tiering.py` (a fixture's own entries in
    `DEVTREE_FILES`, `ALWAYS_FILES` or `SERIAL_GROUP`; those are dicts, path -> reason).
    `lint_exit` writes a `scripts/lint-gmd.sh` that exits with that code (the merge gate runs
    the lint gate; the fixture checkout holds no docs to lint)."""
    tree = (Path(root) / "co").resolve()
    tests = tree / "tests"
    tests.mkdir(parents=True)
    for p in TESTS.iterdir():
        if p.name in ("__pycache__", "fixtures") or p.name.startswith("test_"):
            continue
        if p.is_dir():
            shutil.copytree(p, tests / p.name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(p, tests / p.name)
    shutil.copy2(CASES / "support.py", tests / "suite_health_support.py")
    for name, case in cases.items():
        assert name.startswith("test_") and name.endswith(".py"), name
        shutil.copy2(CASES / f"{case}.py", tests / name)
    if weights is not None:
        (tests / "shard_weights.json").write_text(json.dumps({"files": weights}, indent=1))
    if tiering_extra:
        tiering = tests / "tiering.py"
        text = tiering.read_text() if tiering.is_file() else ""
        tiering.write_text(text + "\n\n# ---- fixture entries (tests/suite_health_tree.py) ----\n"
                           + tiering_extra + "\n")
    (tree / "tools").mkdir()
    shutil.copy2(REPO / "tools" / "pyc_guard.py", tree / "tools" / "pyc_guard.py")
    if (REPO / "pyproject.toml").is_file():
        shutil.copy2(REPO / "pyproject.toml", tree / "pyproject.toml")
    (tree / "scripts").mkdir()
    for name in SCRIPTS:
        if (REPO / "scripts" / name).is_file():
            shutil.copy2(REPO / "scripts" / name, tree / "scripts" / name)
    if lint_exit is not None:
        lint = tree / "scripts" / "lint-gmd.sh"
        lint.write_text(f"#!/bin/bash\necho 'fixture lint gate: exit {lint_exit}'\n"
                        f"exit {lint_exit}\n")
        lint.chmod(0o755)
    (tree / "src").symlink_to(REPO / "src")
    (tree / "workflow" / "review-output").mkdir(parents=True)
    if owning:
        (tree / ".refmatrix").mkdir()
        (tree / ".venv-eval").mkdir()
    else:
        (tree / ".venv-eval").symlink_to(Path(sys.prefix).resolve())
    return tree


def run_dir(tree: Path, name: str) -> Path:
    """Where the runner writes run `name` (task-29.4 `#r2`)."""
    return tree / "workflow" / "review-output" / name
