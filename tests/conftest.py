import pytest


@pytest.fixture(autouse=True)
def _isolate_agent_bashrc(tmp_path, monkeypatch):
    """Keep install() from touching the real ~/.claude/agent-bashrc.sh."""
    monkeypatch.setenv("RMX_AGENT_BASHRC", str(tmp_path / "agent-bashrc.sh"))
    # Never let a test write the real ~/.claude/hooks: an install(apply=True)
    # with search on rewrote the live rewriter with dev-tree paths every
    # full-suite run (found by `rmx install-hooks --check`, 2026-09-14).
    monkeypatch.setenv("RMX_CLAUDE_HOOKS_DIR", str(tmp_path / "claude-hooks"))


@pytest.fixture(autouse=True)
def _reset_cli_partition_override():
    """`cli._partition_override` is a module global the memory subcommands set
    for the life of ONE process (`rmx` is one invocation per process). In
    the suite every CliRunner call shares the process, so a memory command
    on one tmp store pinned the NEXT test's bridge to the wrong partition
    (found 2026-09-14: `test_sync_disk_alias_fails_loud…` → five `live`
    bridge tests looked up rows in a partition nothing wrote to)."""
    from refmatrix import cli as _cli
    yield
    _cli._partition_override = None
