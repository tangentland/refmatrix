"""plan-2 task 2.3 — THIS repo's installed hooks equal what its own generator
renders. Drift (a hand-edited or hand-added hook) fails the suite, which is
the point: hooks are generated, never authored (constitution X)."""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix import hooks as hooks_mod

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not (REPO / ".claude" / "rmx-hooks.json").exists(),
                    reason="not an rmx-hooks-managed checkout")
def test_installed_hooks_match_generated():
    ok, diff = hooks_mod.check(REPO)
    assert ok, "hooks drift — run `rmx install-hooks --apply --force`:\n" + diff
