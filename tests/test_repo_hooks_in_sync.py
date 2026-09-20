"""plan-2 task 2.3 — THIS repo's installed hooks equal what its own generator
renders. Drift (a hand-edited or hand-added hook) fails the suite, which is
the point: hooks are generated, never authored (constitution X)."""
from __future__ import annotations

from pathlib import Path

import pytest

from refmatrix import hooks as hooks_mod

REPO = Path(__file__).resolve().parents[1]

# `.claude/settings.json` is committed and its commands carry absolute paths,
# so a SECOND checkout of this commit (a detached `git worktree`, a clone)
# holds hooks belonging to the first. Comparing them there measures the path
# prefix, not drift — and failed the suite at the very sha under test
# (bug-054 / ch-bsd #m-5). The check runs where it means something.
_OWNER = hooks_mod.installed_root(REPO)


@pytest.mark.skipif(not (REPO / ".claude" / "rmx-hooks.json").exists(),
                    reason="not an rmx-hooks-managed checkout")
@pytest.mark.skipif(_OWNER is not None and _OWNER != REPO,
                    reason="hooks belong to another checkout of this commit")
def test_installed_hooks_match_generated(monkeypatch):
    # This test checks the REAL checkout against the REAL ~/.claude/hooks
    # (read-only); undo the conftest redirect that isolates every other test.
    monkeypatch.delenv("RMX_CLAUDE_HOOKS_DIR", raising=False)
    ok, diff = hooks_mod.check(REPO)
    assert ok, "hooks drift — run `rmx install-hooks --apply --force`:\n" + diff
