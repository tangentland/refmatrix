"""plan-2 #b-3: the docs name the file install-hooks actually writes."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_docs_name_settings_json_and_the_check():
    readme = (REPO / "README.md").read_text()
    integ = (REPO / "docs" / "INTEGRATION.md").read_text()
    intuition = (REPO / "docs" / "hooks" / "intuition-style-hooks.md").read_text()
    for text, name in ((readme, "README.md"), (integ, "INTEGRATION.md"), (intuition, "intuition-style-hooks.md")):
        assert ".claude/settings.json" in text, name
        assert "install-hooks --check" in text, name
    # the old target may be mentioned only as legacy, never as the install target
    assert "writes a JSON block into `.claude/settings.local.json`" not in integ
    assert "| `.claude/settings.local.json` |" not in readme
    for ev in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop", "SubagentStop", "SessionStart", "PreCompact"):
        assert ev in readme, ev
