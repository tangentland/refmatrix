"""Tests for the install-hooks agent-env surface: ~/.claude/agent-bashrc.sh
plus BASH_ENV wiring into the Claude settings env block."""
import json
import subprocess

from refmatrix.hooks import (
    AGENT_BASHRC_SECTION,
    _BASHRC_BEGIN,
    _BASHRC_END,
    install,
)


def _proj(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    rmx = proj / ".refmatrix"
    rmx.mkdir()
    return proj, rmx


def _bashrc(tmp_path):
    return tmp_path / "agent-bashrc.sh"  # matches conftest RMX_AGENT_BASHRC


def test_agent_env_apply_writes_bashrc_and_env(tmp_path):
    proj, rmx = _proj(tmp_path)
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    bashrc = _bashrc(tmp_path)
    assert bashrc.exists()
    text = bashrc.read_text()
    assert _BASHRC_BEGIN in text and _BASHRC_END in text
    assert "rmxc()" in text and "RMXGREP_MODE" in text
    data = json.loads((proj / ".claude" / "settings.local.json").read_text())
    assert data["env"]["BASH_ENV"] == str(bashrc)
    assert data["env"]["RMXGREP_MODE"] == "rich"


def test_agent_env_bashrc_sources_clean(tmp_path):
    proj, rmx = _proj(tmp_path)
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    r = subprocess.run(
        ["bash", "-c", 'type rmxc >/dev/null && echo "$RMXGREP_MODE"'],
        env={"BASH_ENV": str(_bashrc(tmp_path)), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "rich"


def test_agent_env_preserves_user_content_outside_markers(tmp_path):
    proj, rmx = _proj(tmp_path)
    bashrc = _bashrc(tmp_path)
    bashrc.write_text("export USER_THING=1\n")
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    text = bashrc.read_text()
    assert text.startswith("export USER_THING=1\n")
    assert _BASHRC_BEGIN in text


def test_agent_env_skips_existing_section_without_force(tmp_path):
    proj, rmx = _proj(tmp_path)
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    bashrc = _bashrc(tmp_path)
    mutated = bashrc.read_text().replace("rmxc()", "rmxOLD()")
    bashrc.write_text(mutated)
    out = install(project_root=proj, refmatrix_root=rmx, apply=True)
    assert "rmxOLD()" in bashrc.read_text()  # untouched
    assert any("skip" in line and "agent-bashrc" in line for line in out)


def test_agent_env_force_refreshes_section_only(tmp_path):
    proj, rmx = _proj(tmp_path)
    bashrc = _bashrc(tmp_path)
    bashrc.write_text("export BEFORE=1\n" + AGENT_BASHRC_SECTION + "export AFTER=1\n")
    mutated = bashrc.read_text().replace("rmxc()", "rmxOLD()")
    bashrc.write_text(mutated)
    install(project_root=proj, refmatrix_root=rmx, apply=True, force=True)
    text = bashrc.read_text()
    assert "rmxOLD()" not in text and "rmxc()" in text
    assert "export BEFORE=1" in text and "export AFTER=1" in text


def test_agent_env_keeps_existing_env_keys(tmp_path):
    proj, rmx = _proj(tmp_path)
    claude_dir = proj / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.local.json").write_text(json.dumps(
        {"env": {"BASH_ENV": "/custom/path.sh", "OTHER": "x"}}))
    install(project_root=proj, refmatrix_root=rmx, apply=True)
    data = json.loads((claude_dir / "settings.local.json").read_text())
    assert data["env"]["BASH_ENV"] == "/custom/path.sh"  # not clobbered
    assert data["env"]["OTHER"] == "x"
    assert data["env"]["RMXGREP_MODE"] == "rich"  # missing key added


def test_agent_env_user_scope_prints_snippet(tmp_path):
    proj, rmx = _proj(tmp_path)
    out = install(project_root=proj, refmatrix_root=rmx, apply=True,
                  scope="user", git=False, briefing=False)
    txt = "\n".join(out)
    assert "BASH_ENV" in txt and "RMXGREP_MODE" in txt
    assert not (proj / ".claude" / "settings.local.json").exists()


def test_agent_env_opt_out(tmp_path):
    proj, rmx = _proj(tmp_path)
    install(project_root=proj, refmatrix_root=rmx, apply=True,
            agent_env=False)
    assert not _bashrc(tmp_path).exists()
    data = json.loads((proj / ".claude" / "settings.local.json").read_text())
    assert "env" not in data
