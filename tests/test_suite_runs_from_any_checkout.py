"""bug-054 (ch-bsd #m-5): the suite could not be run against a checkout of its
own commit.

`.claude/settings.json` is committed and its hook commands embed ABSOLUTE paths
of the tree they were rendered for. `test_installed_hooks_match_generated`
compares that file against a render for the CURRENT root, so a detached
`git worktree` at the very sha under test fails on a pure path rebase:

    - ... rmx primer --out '/Users/tholley/claude_tools/refmatrix/.refmatrix/PRIMER.md'
    + ... rmx primer --out '/private/tmp/rmxwt/.refmatrix/PRIMER.md'

Nothing is wrong with either tree. The cost is that once the working tree moves
on, a commit's suite result can no longer be reproduced from its sha — which is
why this ledger has filed "full-suite log != committed tree" three times.

So the identity check has to know whose identity it is checking.
"""
from __future__ import annotations

import json

from refmatrix import hooks as hooks_mod


def _settings(root_for: str) -> dict:
    return {
        "hooks": {
            "SessionStart": [{
                "matcher": "startup|resume",
                "hooks": [{
                    "type": "command",
                    "command": (
                        "export RMX_INVOCATION_SOURCE=hook; rmx primer --out "
                        f"'{root_for}/.refmatrix/PRIMER.md' >/dev/null 2>&1"
                    ),
                }],
            }],
        }
    }


def test_installed_root_reads_the_tree_the_hooks_were_rendered_for(tmp_path):
    canonical = "/Users/someone/claude_tools/refmatrix"
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps(_settings(canonical)))
    assert str(hooks_mod.installed_root(tmp_path)) == canonical


def test_installed_root_is_none_when_no_hook_names_a_tree(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"Stop": [{"matcher": "", "hooks": [
            {"type": "command", "command": "rmx focus summarize --promote"}]}]}}))
    assert hooks_mod.installed_root(tmp_path) is None


def test_installed_root_is_none_without_settings(tmp_path):
    assert hooks_mod.installed_root(tmp_path) is None


def test_installed_root_matches_this_checkout_when_it_is_the_managed_one(tmp_path):
    """The self-referential case: hooks rendered FOR tmp_path report tmp_path,
    so the identity check runs (rather than skipping) in a real checkout."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps(_settings(str(tmp_path))))
    assert hooks_mod.installed_root(tmp_path) == tmp_path


def test_check_says_the_hooks_belong_to_another_checkout(tmp_path):
    """`rmx install-hooks --check` in a relocated tree used to print a wall of
    path-rebased diff lines and call it drift. It has to say what happened."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps(_settings("/Users/someone/claude_tools/refmatrix")))
    (tmp_path / ".claude" / "rmx-hooks.json").write_text(
        json.dumps({"flags": {}}))
    ok, diff = hooks_mod.check(tmp_path)
    assert ok is False
    assert "another checkout" in diff, diff
    assert "/Users/someone/claude_tools/refmatrix" in diff, diff
