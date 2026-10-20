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


def identity_binary(base: Path, *, dev_tree: bool, name: "str | None" = None,
                    import_path: str = "/x/src/refmatrix/__init__.py") -> Path:
    """A binary answering the identity JSON `rmx version -v --json` prints."""
    ident = ('{"dev_tree": %s, "import_path": "%s"}'
             % ("true" if dev_tree else "false", import_path))
    return script_binary(base, name or ("dev" if dev_tree else "deployed"), f"echo '{ident}'")


def deploy_tree(base: Path, name: str = "deploy", *, prefix: str = ".venv",
                editable_target: "Path | None" = None) -> Path:
    """A tmp tree shaped like a refmatrix checkout with its own venv (task 4.6, S2/M2):
    `<base>/<name>/{pyproject.toml, src/refmatrix/__init__.py}` plus `<prefix>/lib/python3.14/
    site-packages/__editable__.refmatrix-0.0.0.pth` naming `editable_target` (default: the
    tree's own `src/`). Never a real venv: `runtime_identity(prefix=, import_file=)` reads these
    paths and nothing else."""
    root = base / name
    (root / "src" / "refmatrix").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text('[project]\nname = "refmatrix"\nversion = "0.0.0"\n')
    (root / "src" / "refmatrix" / "__init__.py").write_text('__version__ = "0.0.0"\n')
    sp = root / prefix / "lib" / "python3.14" / "site-packages"
    sp.mkdir(parents=True, exist_ok=True)
    target = editable_target if editable_target is not None else root / "src"
    (sp / "__editable__.refmatrix-0.0.0.pth").write_text(str(target) + "\n")
    return root
