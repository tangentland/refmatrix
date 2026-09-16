"""bug-038 — the version had two sources of truth and they disagreed.

`src/refmatrix/__init__.py` read 0.70.0 while `pyproject.toml` read 0.69.1.
The runtime uses `refmatrix.__version__` (`upgrade.runtime_identity`,
`hub._HUB_IDENTITY`), so the hub version handshake and every `rmx version`
reported one number while the installed dist-info recorded another — and
`reference_editable_venv_distinfo_lag` shows that gap is exactly where
"which code is actually running" arguments start.

Nothing asserted the two agreed, which is why they drifted a whole release.
"""

from __future__ import annotations

import re
from pathlib import Path

import refmatrix

REPO = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    for line in (REPO / "pyproject.toml").read_text().splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    raise AssertionError("pyproject.toml has no top-level version")


def test_pyproject_and_dunder_version_agree():
    assert refmatrix.__version__ == _pyproject_version(), (
        f"__version__={refmatrix.__version__} but pyproject says "
        f"{_pyproject_version()}; the hub handshake reads __version__ and "
        f"dist-info reads pyproject (bug-038)")
