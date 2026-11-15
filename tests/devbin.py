"""The dev `rmx`, defined once (bug-253; task-t0-suite-trust-sweep `#t0-2-bug253`; rulings L121,
L122, L142).

WHY. The 29.4 stage-0 serial run in a no-venv littlebig clone (`/Volumes/littlebig/refmatrix-r0`,
2026-11-14) errored in 127 tests and failed 2 more on one E line, `AssertionError: dev rmx
missing at <clone>/…/bin/rmx` (the checkout's `.venv-eval`): eleven test files located the
subprocess `rmx` in the checkout's own venv, each its own way, and a clone has no venv of its own -- it
runs the dev tree's interpreter with `PYTHONPATH=<clone>/src` (workflow/ORCHESTRATION.md). Six
of those files SKIPPED instead, which is why 18 skip pins existed in tests/conftest.py at all.

The dev `rmx` is the console script beside the interpreter running the suite: in the main tree
that is the `rmx` in `.venv-eval`, in a clone the same file, found through `sys.executable` and
never through the clone's own `.venv-eval`. A child run through it gets this checkout's `src`
first on `PYTHONPATH` (`dev_env`), so in a clone it runs the clone's code and not the editable
install's tree.

`eval/production/grep_learning_replay.py` loads this file by path for the same answer (L142 (1)).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"


def dev_bin() -> Path:
    """The bin directory of the interpreter running the suite. Deliberately NOT resolved: a
    venv's `bin/python` is a symlink to the base interpreter, whose bin holds no `rmx`."""
    return Path(sys.executable).parent


def dev_rmx() -> Path:
    """The dev `rmx` console script: `dev_bin() / "rmx"`."""
    return dev_bin() / "rmx"


def dev_env(env: "dict | None" = None) -> dict:
    """A COPY of `env` (default `os.environ`) whose `PYTHONPATH` starts with this checkout's
    `src` and keeps every other entry in order (the sandbox's `tests/sandbox_site` rides there,
    task 23.0 R4). `os.environ` and `env` are never modified."""
    out = dict(os.environ if env is None else env)
    src = str(_SRC)
    rest = [p for p in str(out.get("PYTHONPATH", "")).split(os.pathsep) if p and p != src]
    out["PYTHONPATH"] = os.pathsep.join([src] + rest)
    return out
