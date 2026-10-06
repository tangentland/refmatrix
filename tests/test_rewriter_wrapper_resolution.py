"""bug-066: the rewrite hook resolved the STALE wrapper copy.

Two copies of `rmxgrep` exist in a deploy tree and they are not the same file:

    ~/refmatrix/.venv/bin/rmxgrep   4,760 B  — whatever pip last installed
    ~/refmatrix/bin/rmxgrep         5,714 B  — the DEPLOYED wrapper

Wrappers deploy by COPY into `<tree>/bin`; `pip install` does not move them
(`project_grep_stdin_race_dialect_fix`). So the venv copy is a snapshot from
whenever the package was last installed, and `bin/` is current. The generated
rewriter resolved the venv sibling FIRST, so 954 bytes of fixes never reached
the path every rewritten grep in every agent session takes — including bug-005's
pipe short-circuit, and including the removal of the `RMXGREP_MODE=plain` bypass
the user ordered gone on 2026-09-15.

The irony that makes this worth a test rather than a one-line edit: bug-008's
durable fix made the rewriter resolve the wrapper AT RUNTIME from the tree that
owns the `rmx` on PATH, so that a dev-venv `install-hooks` could not bake its own
checkout into a user-global hook. That fix is right — and its resolution order
picked the stale COPY. One stale-path bug's fix selected another stale path.

NOT covered here: the `RMXGREP_MODE=rich` setting in the user's
`settings.json`, which is config and the user's call.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from refmatrix import search_hooks as sh


def _load_wrapper_resolver(monkeypatch, tmp_path):
    """Exec the GENERATED rewriter's `_wrapper` — the artifact that ships, not
    a copy of its logic in this test."""
    monkeypatch.setenv("RMX_CLAUDE_HOOKS_DIR", str(tmp_path / "hooks"))
    src = sh.render_scripts()[sh.REWRITER_NAME]
    start = src.index("def _wrapper(")
    end = src.index("def RMXGREP")
    ns: dict = {}
    exec(src[start:end], ns, ns)
    return ns["_wrapper"]


def _fake_deploy_tree(tmp_path: Path) -> Path:
    """A deploy tree shaped like the real one: an `rmx` console script inside
    `.venv/bin`, a STALE wrapper beside it, and the fresh wrapper in `bin/`."""
    tree = tmp_path / "refmatrix"
    venv_bin = tree / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (tree / "bin").mkdir()
    for p, body in ((venv_bin / "rmx", "#!/bin/sh\nexit 0\n"),
                    (venv_bin / "rmxgrep", "#!/bin/sh\n# STALE pip copy\n"),
                    (tree / "bin" / "rmxgrep", "#!/bin/sh\n# DEPLOYED copy\n")):
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return tree


def test_the_rewriter_prefers_the_deployed_wrapper_over_the_venv_copy(
        tmp_path, monkeypatch):
    tree = _fake_deploy_tree(tmp_path)
    monkeypatch.setenv("PATH", str(tree / ".venv" / "bin") + os.pathsep
                       + os.environ.get("PATH", ""))
    wrapper = _load_wrapper_resolver(monkeypatch, tmp_path)

    got = wrapper("rmxgrep")

    assert Path(got) == tree / "bin" / "rmxgrep", (
        f"resolved the stale pip copy: {got}\n"
        f"wrappers deploy by COPY into <tree>/bin and pip does not move them, "
        f"so the venv sibling is whatever was last installed")


def test_the_venv_copy_is_still_used_when_the_tree_has_no_bin(
        tmp_path, monkeypatch):
    """The venv sibling stays in the chain — an editable install without a
    `bin/` must still resolve rather than falling through to a bare name."""
    tree = tmp_path / "refmatrix"
    venv_bin = tree / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    for name in ("rmx", "rmxgrep"):
        p = venv_bin / name
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(venv_bin) + os.pathsep
                       + os.environ.get("PATH", ""))
    wrapper = _load_wrapper_resolver(monkeypatch, tmp_path)

    assert Path(wrapper("rmxgrep")) == venv_bin / "rmxgrep"


def test_the_rendered_bytes_still_name_no_checkout(tmp_path, monkeypatch):
    """bug-008's property, which this fix must not undo: the rewriter is
    USER-GLOBAL, so it must resolve at runtime and name no particular tree.
    Rendering from this checkout must not embed this checkout."""
    monkeypatch.setenv("RMX_CLAUDE_HOOKS_DIR", str(tmp_path / "hooks"))
    src = sh.render_scripts()[sh.REWRITER_NAME]

    assert "claude_tools/refmatrix" not in src
    assert str(Path.home() / "refmatrix") not in src


@pytest.mark.skipif(not (Path.home() / "refmatrix" / "bin" / "rmxgrep").exists(),
                    reason="no deploy tree on this machine")
def test_on_this_machine_it_resolves_the_deployed_copy(tmp_path, monkeypatch):
    """The live assertion, because the two tests above prove the ORDER and this
    one proves the order picks the right file HERE — where the two copies
    actually differ by 954 bytes."""
    wrapper = _load_wrapper_resolver(monkeypatch, tmp_path)

    got = Path(wrapper("rmxgrep"))

    assert got == Path.home() / "refmatrix" / "bin" / "rmxgrep", got
    # And the file it picked is the one WITHOUT the removed bypass. Checked on
    # the `case` arm, not on the text: the deployed wrapper mentions
    # `RMXGREP_MODE=plain` in the comment explaining its removal, so a
    # substring search over the prose fails on the fixed file — the same
    # mistake as grepping a docstring for a rule.
    body = got.read_text()
    import re
    assert not re.search(r"^\s*plain\)", body, re.M), (
        "the resolved wrapper still has a `plain)` arm, i.e. the bypass the "
        "user ordered removed on 2026-09-15 is live on the path every "
        "rewritten grep takes")
    # The stale sibling is the one that still honours it — if this ever fails,
    # the two copies have converged and bug-066 is closed at the deploy layer
    # too, not just in the resolver.
    stale = Path.home() / "refmatrix" / ".venv" / "bin" / "rmxgrep"
    if stale.exists():
        assert re.search(r"^\s*plain\)", stale.read_text(), re.M), (
            "the stale venv copy no longer carries the bypass — deploy now "
            "syncs both locations, so this assertion can be dropped")
