"""bug-216 AC-4 (R3) — the GMD gate fails when a lint-scope GMD doc is excluded from ingest.

Spec: workflow/plans/task-bug216-rule-docs-in-graph.md (#r3, #ac-4).

WHY. `scripts/lint-gmd.sh` lints CLAUDE.md, docs/, workflow/, eval/ and the project profile, and
resolves `[[claude#…]]` / `[[project-profile#…]]`; the ingest scope excluded both rule docs, and
nothing compared the two scopes — "two parsers, never compared" again (bug-036, bug-179). R3
puts the comparison in `scripts/check-gmd-parity.py`, the step the gate already runs.

Each fixture is a throwaway ROOT under a short `/tmp` mkdtemp that holds REAL copies of the
gate's scripts (the bug-179 `_gate_root` layout): `scripts/check-gmd-parity.py`, `tools/gmd/
lint.py`, a `src` symlink to this checkout's `src`, a `.git` marker. So the project root the
script reads the ignore spec from is the fixture root however the implementation derives it (the
script's own repo, the cwd, or the scanned files' `.git` ancestor).

Must-fail first ([[feedback_clean_corpus_hides_a_dead_gate]]): every pass case below has a twin
that differs only in the ignore spec and must exit non-zero.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PARITY = REPO / "scripts" / "check-gmd-parity.py"
LINT = REPO / "tools" / "gmd" / "lint.py"
LINT_GMD_SH = REPO / "scripts" / "lint-gmd.sh"


def _gmd(doc_id: str, extra: str = "") -> str:
    return (f'---\ngmd: "0.1"\nid: {doc_id}\ntitle: "{doc_id}"\ntags: [t]\n---\n\n'
            f"# {doc_id} {{#root}}\n\nBody.\n{extra}")


PLAIN = "<!-- not-gmd: bug-216 fixture -->\n# Not GMD\n\nNo frontmatter, so neither lint nor the ingester treats it as GMD.\n"


def _root(prefix: str = "b216p") -> Path:
    root = Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp")).resolve()
    (root / ".git").mkdir()
    (root / "scripts").mkdir()
    shutil.copy2(PARITY, root / "scripts" / "check-gmd-parity.py")
    shutil.copy2(LINT_GMD_SH, root / "scripts" / "lint-gmd.sh")
    # T0.1' R1.4: lint-gmd.sh asks scripts/gmd_memdir.py for its memory dir; a gate root that
    # copies the script copies its resolver.
    shutil.copy2(REPO / "scripts" / "gmd_memdir.py", root / "scripts" / "gmd_memdir.py")
    (root / "tools" / "gmd").mkdir(parents=True)
    shutil.copy2(LINT, root / "tools" / "gmd" / "lint.py")
    (root / "src").symlink_to(REPO / "src")
    return root


def _spec(root: Path, lines: list[str]) -> None:
    d = root / ".refmatrix"
    d.mkdir(exist_ok=True)
    (d / ".refmatrix_ignore").write_text("\n".join(lines) + "\n")


def _small_repo(root: Path) -> None:
    """The lint scope of lint-gmd.sh, in miniature, plus one excluded doc of each shape."""
    files = {
        "CLAUDE.md": _gmd("claude"),
        ".claude/PROJECT_PROFILE.md": _gmd("project-profile"),
        "docs/index.md": _gmd("docs-index"),
        "docs/notes-private.md": _gmd("notes-private"),   # excluded by the glob below
        "docs/plain-private.md": PLAIN,                    # excluded too, but not GMD
        "workflow/w.md": _gmd("w"),
        "eval/e.md": _gmd("e"),
    }
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


SCOPE = ["CLAUDE.md", "docs/", "workflow/", "eval/", ".claude/PROJECT_PROFILE.md"]


def _run(root: Path, *extra: str) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    p = subprocess.run(
        [sys.executable, str(root / "scripts" / "check-gmd-parity.py"),
         *[str(root / a) for a in SCOPE], *extra],
        capture_output=True, text=True, cwd=root, env=env, timeout=600)
    return p.returncode, p.stdout + p.stderr


def _line_naming(out: str, rel: str) -> str:
    hits = [ln for ln in out.splitlines() if rel in ln]
    assert hits, f"no output line names {rel}:\n{out}"
    return "\n".join(hits)


@pytest.fixture
def roots():
    made: list[Path] = []
    yield made
    for r in made:
        shutil.rmtree(r)


# ---------------------------------------------------------------- must-fail


def test_ac4_fails_naming_the_file_and_the_spec_rule(roots):
    """A GMD doc in the lint scope that a spec pattern excludes: non-zero, and the line naming
    the file names the pattern that excluded it. The non-GMD file the same pattern excludes is
    NOT a finding (only GMD docs carry anchors other docs cite)."""
    root = _root()
    roots.append(root)
    _small_repo(root)
    _spec(root, ["*-private.md", "!.claude/PROJECT_PROFILE.md"])
    code, out = _run(root)
    assert code != 0, f"the gate passed a lint-scope GMD doc the ingest excludes:\n{out}"
    assert "*-private.md" in _line_naming(out, "docs/notes-private.md"), out
    assert "plain-private.md" not in out, f"a non-GMD file was reported:\n{out}"
    assert ".claude/PROJECT_PROFILE.md" not in out, f"the re-included profile was reported:\n{out}"


def test_ac4_fails_on_the_hidden_dir_rule_and_names_it(roots):
    """A scanned GMD doc that only the built-in hidden-dir rule excludes. The finding must say so
    — the rule is not in any file the user can grep. (Rev 4 R11: the PROFILE is now a built-in
    include, so the hidden-dir case is another `.claude/` doc passed to the script.)"""
    root = _root()
    roots.append(root)
    _small_repo(root)
    (root / ".claude" / "NOTES.md").write_text(_gmd("claude-notes"))
    _spec(root, ["!docs/notes-private.md"])
    code, out = _run(root, str(root / ".claude" / "NOTES.md"))
    assert code != 0, out
    assert "hidden" in _line_naming(out, ".claude/NOTES.md").lower(), out
    assert ".claude/PROJECT_PROFILE.md" not in out, (
        f"R11: the GMD profile is a built-in include, never a finding:\n{out}")


def test_ac4_fails_on_this_repos_head_config(roots):
    """The live store's ignore file as of 2026-11-13 (before R4): `.claude` and `CLAUDE.md`.
    Both rule docs are in the lint scope, both are excluded — exactly bug-216."""
    root = _root()
    roots.append(root)
    _small_repo(root)
    (root / "docs" / "notes-private.md").unlink()
    _spec(root, HEAD_CONFIG)
    code, out = _run(root)
    assert code != 0, out
    _line_naming(out, ".claude/PROJECT_PROFILE.md")
    assert "CLAUDE.md" in _line_naming(out, "CLAUDE.md"), out


# ---------------------------------------------------------------- pass


def test_ac4_exits_zero_when_reincluded(roots):
    root = _root()
    roots.append(root)
    _small_repo(root)
    _spec(root, [".claude", "!.claude/PROJECT_PROFILE.md",
                 "*-private.md", "!docs/notes-private.md"])
    code, out = _run(root)
    assert code == 0, out


def test_ac4_the_memory_dir_is_out_of_the_scope_check(roots):
    """R3: the memory dir reaches the store through the bridge, not the ignore-spec walk — and
    it always sits under `~/.claude/…`, a hidden dir. Passed with `--memory-dir`, it is never a
    scope finding. Green at HEAD (no scope check); guards the implementation."""
    root = _root()
    roots.append(root)
    _small_repo(root)
    _spec(root, [".claude", "!.claude/PROJECT_PROFILE.md",
                 "*-private.md", "!docs/notes-private.md"])
    mem = root / "home" / ".claude" / "projects" / "p" / "memory"
    mem.mkdir(parents=True)
    (mem / "feedback_x.md").write_text(_gmd("feedback_x"))
    code, out = _run(root, "--memory-dir", str(mem))
    assert code == 0, out


# ---------------------------------------------------------------- this repo, R4 mirrored

# The live `.refmatrix/.refmatrix_ignore` (runtime state, not committed), read 2026-11-13 and
# reproduced line for line — the test never reads the live file.
HEAD_CONFIG = [
    "eval/memaware/data/",
    ".claude",
    "CLAUDE.md",
    "src/refmatrix/templates",
]
# Spec #r4 applied to it: remove `CLAUDE.md`; keep `.claude`; add the profile re-include.
R4_CONFIG = [
    "eval/memaware/data/",
    ".claude",
    "!.claude/PROJECT_PROFILE.md",
    "src/refmatrix/templates",
]


def _mirror_this_repo(root: Path) -> None:
    """Copy this checkout's lint scope (every `.md` under it) and its `.gmd/config.yml`."""
    for rel in ("CLAUDE.md", ".claude/PROJECT_PROFILE.md", ".gmd/config.yml"):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, dst)
    for top in ("docs", "workflow", "eval"):
        for src in (REPO / top).rglob("*.md"):
            if not src.is_file():
                continue
            dst = root / src.relative_to(REPO)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def test_ac4_this_repo_passes_with_r4_config(roots):
    root = _root("b216r")
    roots.append(root)
    _mirror_this_repo(root)
    _spec(root, R4_CONFIG)
    code, out = _run(root)
    assert code == 0, out[-4000:]


def test_ac4_this_repo_fails_with_its_head_config(roots):
    """The must-fail twin of the test above, on the real corpus."""
    root = _root("b216r")
    roots.append(root)
    _mirror_this_repo(root)
    _spec(root, HEAD_CONFIG)
    code, out = _run(root)
    assert code != 0, out[-4000:]
    _line_naming(out, ".claude/PROJECT_PROFILE.md")
    _line_naming(out, "CLAUDE.md")


# ---------------------------------------------------------------- the gate runs it


def test_ac4_lint_gmd_sh_fails_on_the_excluded_doc(roots):
    """The scope check runs where the anchor check runs: `scripts/lint-gmd.sh` exits non-zero
    on the must-fail fixture although lint itself is clean."""
    root = _root()
    roots.append(root)
    _small_repo(root)
    _spec(root, ["*-private.md", "!.claude/PROJECT_PROFILE.md"])
    prefix = Path(sys.prefix)
    assert (prefix / "bin" / "python").exists(), f"no venv python under {prefix}"
    (root / ".venv-eval").symlink_to(prefix)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    lint_alone = subprocess.run([sys.executable, str(root / "tools/gmd/lint.py"), *SCOPE],
                                capture_output=True, text=True, cwd=root, env=env)
    assert lint_alone.returncode == 0, f"precondition: lint passes alone\n{lint_alone.stdout}"
    p = subprocess.run(["bash", str(root / "scripts" / "lint-gmd.sh")], capture_output=True,
                       text=True, cwd=root, env=env, timeout=600)
    out = p.stdout + p.stderr
    assert p.returncode != 0, out
    assert "docs/notes-private.md" in out, out
