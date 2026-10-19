"""ONE fake `rmx` binary for every test that renders or installs a plist (task 4.5 follow-up).

Since r4 #s-2 was fixed, `launchctl._refuse_dev_tree` / `check` / `check_hub` refuse any binary
that does not answer `rmx version -v --json` with `dev_tree: false`. Six older tests rendered the
hub plist against `RMX_BIN=/usr/local/bin/rmx` (nonexistent) or a script that printed nothing,
and passed only because "unknown" read as "not a dev tree". They now take the `deployed_rmx`
fixture (tests/conftest.py), which keeps the guard exercised on a binary that really answers.
"""
from __future__ import annotations

from pathlib import Path


def script_binary(base: Path, name: str, body: str) -> Path:
    """A real shell script named `rmx` under `base/bins/<name>/`."""
    b = base / "bins" / name / "rmx"
    b.parent.mkdir(parents=True)
    b.write_text("#!/bin/sh\n" + body + "\n")
    b.chmod(0o755)
    return b


def identity_binary(base: Path, *, dev_tree: bool, name: "str | None" = None) -> Path:
    """A binary answering the identity JSON `rmx version -v --json` prints."""
    ident = ('{"dev_tree": %s, "import_path": "/x/src/refmatrix/__init__.py"}'
             % ("true" if dev_tree else "false"))
    return script_binary(base, name or ("dev" if dev_tree else "deployed"), f"echo '{ident}'")
