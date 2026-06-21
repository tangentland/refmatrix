"""Label-naming contract for the launchd LaunchAgent generator.

These are pure-function checks (no `launchctl` invocation) so they run on
any platform. They lock the slugged-label scheme and its legacy-hash
migration anchor.
"""
from pathlib import Path

from refmatrix import launchctl as lc


def test_label_is_slug_plus_hash():
    root = Path("/tmp/whatever/viascope/.refmatrix")
    label = lc.label_for_root(root)
    assert label.startswith("com.refmatrix.daemon.viascope-")
    # 12-hex path hash suffix preserves per-root uniqueness.
    suffix = label.rsplit("-", 1)[1]
    assert len(suffix) == 12
    assert all(c in "0123456789abcdef" for c in suffix)


def test_slug_taken_from_parent_of_dotrefmatrix():
    assert lc._slug_for_root(Path("/a/b/viascope/.refmatrix")) == "viascope"
    # No `.refmatrix` leaf -> slug from the dir itself.
    assert lc._slug_for_root(Path("/a/b/viascope")) == "viascope"


def test_slug_sanitizes_unsafe_chars():
    assert lc._slug_for_root(Path("/a/My Project!/.refmatrix")) \
        == "my-project"
    assert lc._slug_for_root(Path("/a/__weird..name__/.refmatrix")) \
        == "weird-name"


def test_legacy_label_is_hash_only_and_shares_suffix():
    root = Path("/a/b/viascope/.refmatrix")
    legacy = lc._legacy_label_for_root(root)
    assert legacy == f"com.refmatrix.daemon.{lc._short_hash(root)}"
    # New label's suffix == legacy label's hash, so migration maps 1:1.
    assert lc.label_for_root(root).endswith(legacy.rsplit(".", 1)[1])


def test_distinct_roots_same_basename_do_not_collide():
    a = lc.label_for_root(Path("/one/viascope/.refmatrix"))
    b = lc.label_for_root(Path("/two/viascope/.refmatrix"))
    assert a != b
    assert a.startswith("com.refmatrix.daemon.viascope-")
    assert b.startswith("com.refmatrix.daemon.viascope-")


def test_daemon_plist_disables_objc_fork_safety(tmp_path, monkeypatch):
    """The launchd-spawned daemon forks worker processes; libobjc reads
    OBJC_DISABLE_INITIALIZE_FORK_SAFETY once at image load, so it must be in
    the plist env or the daemon SIGABRTs on the initialize-after-fork check."""
    import plistlib
    fake_rmx = tmp_path / "bin" / "rmx"
    fake_rmx.parent.mkdir()
    fake_rmx.write_text("#!/bin/sh\nexit 0\n")
    fake_rmx.chmod(0o755)
    monkeypatch.setenv("RMX_BIN", str(fake_rmx))
    root = tmp_path / "proj" / ".refmatrix"
    root.mkdir(parents=True)
    env = plistlib.loads(lc.render_plist(root))["EnvironmentVariables"]
    assert env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] == "YES"
    assert env["TOKENIZERS_PARALLELISM"] == "false"


def test_hub_plist_disables_objc_fork_safety(tmp_path, monkeypatch):
    import plistlib
    fake_rmx = tmp_path / "bin" / "rmx"
    fake_rmx.parent.mkdir()
    fake_rmx.write_text("#!/bin/sh\nexit 0\n")
    fake_rmx.chmod(0o755)
    monkeypatch.setenv("RMX_BIN", str(fake_rmx))
    env = plistlib.loads(lc.render_hub_plist())["EnvironmentVariables"]
    assert env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] == "YES"
