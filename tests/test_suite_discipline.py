"""Guard for CLAUDE.md test-discipline rule 1: no new round, remedy, bug or RED test files.

The allowlist (tests/round_named_allow.json) holds the files that already carried such a name
when the guard was added. It only shrinks: a new matching file fails, and so does an entry
whose file is gone (remove it when the file is consolidated).
"""
import json
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ALLOW = TESTS / "round_named_allow.json"
# `_r<digits>` or `_red` as a name component, `remedy` anywhere, `test_bug<digits>` prefix.
PATTERN = re.compile(r"(^|_)r\d+(_|$)|remedy|^test_bug\d|(^|_)red(_|$)")


def round_named_files(root: Path) -> list[str]:
    """Sorted posix paths (relative to root) of test files whose name breaks rule 1."""
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if PATTERN.search(p.stem)
    )


def check(root: Path, allowed: set[str]) -> list[str]:
    found = set(round_named_files(root))
    problems = [f"new round/bug/remedy/RED-named test file: {f}" for f in sorted(found - allowed)]
    problems += [f"allowlist entry has no file (remove it): {f}" for f in sorted(allowed - found)]
    return problems


def test_no_new_round_named_test_files():
    allowed = set(json.loads(ALLOW.read_text()))
    assert check(TESTS, allowed) == []


def test_allowlist_is_sorted_and_unique():
    entries = json.loads(ALLOW.read_text())
    assert entries == sorted(set(entries))


def test_guard_reports_a_new_round_file_and_a_stale_entry(tmp_path):
    # Must-fail case (rule 5): the same check over a tmp tree, no patching.
    (tmp_path / "test_feature.py").write_text("")
    (tmp_path / "test_feature_r7.py").write_text("")
    (tmp_path / "test_other_remedy.py").write_text("")
    (tmp_path / "test_bug123_thing.py").write_text("")
    (tmp_path / "test_x_red.py").write_text("")
    problems = check(tmp_path, {"test_gone_r1.py"})
    for name in ("test_feature_r7.py", "test_other_remedy.py", "test_bug123_thing.py", "test_x_red.py"):
        assert any(name in p and p.startswith("new") for p in problems), name
    assert not any("test_feature.py" in p for p in problems)
    assert any("test_gone_r1.py" in p and "no file" in p for p in problems)
