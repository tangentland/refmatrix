"""A missing `gmd:` key is an ERROR, not a warning.

As a warning it was a gate that could not fail. A file without the key is never
recognized as GMD, so NONE of its anchors, wikilinks or `rel:` edges are
checked — and `scripts/lint-gmd.sh` reported success the whole time. Nine
in-scope docs had drifted out of the graph that way (seven under `eval/`, the
curator log, the bullshit ledger index), found 2026-10-02 by counting rather than
by any gate.

This is the same shape the ledger filed as "a linter which reports malformed
constructs cannot report ABSENT ones" (`impression_bsd_renderer_destroys_payload`,
where `tools/gmd/lint.py` gave 0 errors on a document whose entire edge set had
been deleted, because `[[]]` is not a wikilink). The fix is to make the file
declare itself.

Genuinely-flat files opt out IN THE FILE with a reason, so the exemption is
visible where a reader will be.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

LINTER = Path(__file__).resolve().parents[1] / "tools" / "gmd" / "lint.py"


def _lint(*paths: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(LINTER), *[str(p) for p in paths]],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


GOOD = '''---
gmd: "0.1"
id: fixture-good
title: "A GMD doc"
tags: [test]
---

# A GMD doc {#root}

Body.
'''


def test_a_gmd_doc_passes(tmp_path):
    rc, out = _lint(_write(tmp_path, "good.md", GOOD))
    assert rc == 0, out
    assert "no-gmd-version" not in out, out


def test_no_frontmatter_at_all_is_an_error(tmp_path):
    """The case that let seven `eval/` docs drift."""
    rc, out = _lint(_write(tmp_path, "plain.md", "# Just markdown\n\nBody.\n"))
    assert rc != 0, out
    assert "no-gmd-version" in out and "error" in out, out


def test_frontmatter_without_the_gmd_key_is_an_error(tmp_path):
    rc, out = _lint(_write(tmp_path, "fm.md", "---\nid: x\ntitle: \"X\"\n---\n\n# X\n"))
    assert rc != 0, out
    assert "no-gmd-version" in out and "error" in out, out


def test_the_error_says_what_is_lost_and_how_to_opt_out(tmp_path):
    """A gate that fires without saying why trades one silence for another."""
    rc, out = _lint(_write(tmp_path, "plain.md", "# X\n"))
    assert "not checked" in out.lower() or "not recognized" in out.lower(), out
    assert "not-gmd" in out, f"the opt-out is not discoverable from the error: {out!r}"


def test_a_reasoned_opt_out_passes(tmp_path):
    body = ("<!-- not-gmd: flat one-row-per-entry index -->\n"
            "# A flat index\n\n- a\n- b\n")
    rc, out = _lint(_write(tmp_path, "INDEXY.md", body))
    assert rc == 0, out
    assert "no-gmd-version" not in out, out


def test_an_opt_out_with_no_reason_is_an_error(tmp_path):
    """An unexplained exemption is how drift hides. The marker must say why."""
    rc, out = _lint(_write(tmp_path, "bare.md", "<!-- not-gmd: -->\n# X\n"))
    assert rc != 0, out
    assert "not-gmd-no-reason" in out, out


def test_the_opt_out_must_be_on_line_one(tmp_path):
    """Buried in the body it is neither visible to a reader nor to the gate."""
    body = "# X\n\n<!-- not-gmd: too late to count -->\n"
    rc, out = _lint(_write(tmp_path, "late.md", body))
    assert rc != 0, out
    assert "no-gmd-version" in out, out


def test_memory_index_keeps_its_by_name_exemption(tmp_path):
    """MEMORY.md is GENERATED (bug-042); the generator would have to learn to
    emit the marker, so its exemption stays by name."""
    rc, out = _lint(_write(tmp_path, "MEMORY.md", "- [A](a.md) — hook\n"))
    assert rc == 0, out
    assert "no-gmd-version" not in out, out


# ---- the repo's own tree must satisfy the gate it ships -------------------

GMD_MEMDIR = Path(__file__).resolve().parents[1] / "scripts" / "gmd_memdir.py"


def load_gmd_memdir():
    """`scripts/gmd_memdir.py`, the ONE resolver of the memory dir `scripts/lint-gmd.sh` scans
    (T0.1' R1.4, bug-155's residual). Loaded from the checkout under test by path, so the tests
    exercise this tree's copy. Interface the tests pin:

    - `resolve_memdir(root, home) -> (Path | None, str)`: the chosen memory dir (or None) and the
      one stderr line the script prints (falsy when the own-slug dir is the one used);
    - `slug(path) -> str`: the `~/.claude/projects/<slug>` name of a checkout path, so no test
      keeps a copy of the slug rule to build its decoy home (a third copy is what R1.4 removes).
    """
    assert GMD_MEMDIR.is_file(), (
        f"{GMD_MEMDIR} does not exist: there is no single memory-dir resolver; the slug and "
        "origin logic still lives in two copies, scripts/lint-gmd.sh and this test file "
        "(T0.1' R1.4)")
    import importlib.util
    spec = importlib.util.spec_from_file_location("gmd_memdir", GMD_MEMDIR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reason_text(line: str) -> str:
    """`line` with every absolute path removed, so a reason word (`empty`, `absent`, `cycle`, …)
    is read from the words the resolver wrote, never from a path that happens to hold it (a
    pytest tmp dir is named after its test: `test_an_empty_…0`, `test_a_cycle_…0`)."""
    import re
    return re.sub(r"/[^\s;,()'\"]+", " ", line)


def gate_note_lines(r: "subprocess.CompletedProcess", root: Path, slug: str) -> list:
    """The memory-dir lines of one `scripts/lint-gmd.sh` run: stderr lines that are not a lint
    finding and name this checkout (its path, or its slug inside its own memory-dir path) with
    one of R1.4's reason words. R1.4: whenever the own-slug dir is not the one used, the script
    prints ONE such line, naming every checkout tried, in order, each `absent` or `empty`."""
    out = []
    for line in r.stderr.splitlines():
        if ": error" in line or ": warning" in line:
            continue
        words = reason_text(line)
        if (str(root) in line or slug in line) and ("absent" in words or "empty" in words):
            out.append(line)
    return out


def dangling_summary(r: "subprocess.CompletedProcess") -> str:
    """Count and first lines of the run's `dangling-doc` errors, for a failure message (R0.2:
    a failure is quoted by its E lines, here by count and first lines)."""
    lines = [l for l in (r.stdout + r.stderr).splitlines() if "error: [dangling-doc]" in l]
    return (f"exit {r.returncode}; {len(lines)} dangling-doc error(s); first:\n"
            + "\n".join(lines[:5]))


def test_the_repo_scope_is_clean_under_the_stricter_gate(tmp_path):
    """The gate is only worth having if the tree it guards passes it. Runs the
    real `scripts/lint-gmd.sh`, which is what the commit gate invokes."""
    root = Path(__file__).resolve().parents[1]
    # 23.0 R6: the script adds a curated memory dir to its scope (the ledger cites memory ids).
    # The child gets a DECOY home holding a COPY of exactly that one memory dir -- never the real
    # `HOME` (ch-bsd r1 m3, 2026-10-15: handing the child the real home was a documented way out
    # of the sandbox).
    # T0.1' R1.4 (bug-155's residual): WHICH dir is decided by the one resolver the script also
    # calls, read in-process against the real home (a read-only existence check). This test kept
    # its own copy of the slug + one-hop origin logic, and so did the script; in a clone of a
    # clone both stopped at the first origin and every memory id dangled (1,235 dangling-doc,
    # workflow/review-output/t0.1/base-ac1.5-case1-script-clone-of-clone.log). The decoy gets the
    # chosen dir under the slug of the checkout that owns it; the child walks the same origins,
    # finds nothing at the slugs before it, and resolves the same content.
    import shutil
    gm = load_gmd_memdir()
    real_home = Path(os.environ["RMX_SANDBOX_REAL_HOME"])
    chosen, _note = gm.resolve_memdir(root, real_home)
    own = gm.slug(root)
    home = tmp_path / "home"
    home.mkdir()
    if chosen is not None:
        chosen = Path(chosen)
        shutil.copytree(chosen, home / ".claude" / "projects" / chosen.parent.name / "memory")
    env = dict(os.environ, HOME=str(home))
    assert Path(env["HOME"]).resolve() != Path(os.environ["RMX_SANDBOX_REAL_HOME"]).resolve()
    r = subprocess.run(["./scripts/lint-gmd.sh"], cwd=str(root),
                       capture_output=True, text=True, env=env)
    assert_gate_ran(r)
    if chosen is not None and chosen.parent.name != own:
        # The fallback was taken: the script says so on ONE line that names the chain -- this
        # checkout's direct origin, and the checkout whose dir was used (AC-1.5 case 1: "the
        # fallback line names both hops"; in a clone of a clone they differ).
        lines = gate_note_lines(r, root, own)
        assert len(lines) == 1, (
            f"the resolver chose {chosen} (not this checkout's own slug), so the script must "
            f"print exactly one memory-dir line naming the chain; got {lines!r}\n"
            + dangling_summary(r))
        line = lines[0]
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True).stdout.strip()
        if url.startswith("/"):
            direct = Path(url).resolve()
            assert str(direct) in line, (
                f"the memory-dir line does not name this checkout's origin {direct}: {line!r}")
        named = [t for t in _path_tokens(line)
                 if gm.slug(Path(t)) == chosen.parent.name
                 or Path(t).parent.name == chosen.parent.name]
        assert named, (f"the memory-dir line does not name the checkout whose dir was used "
                       f"(slug {chosen.parent.name}): {line!r}")
    assert_gate_ran_clean(r)


def _path_tokens(line: str) -> list:
    import re
    return [t.rstrip(".,;:)") for t in re.findall(r"/[^\s;,()'\"]+", line)]


def assert_gate_ran(r: "subprocess.CompletedProcess") -> None:
    """First clause of `assert_gate_ran_clean`, on its own: the gate RAN (it did not stop on a
    missing precondition with exit 2). T0.1' AC-1.5 (ch-bsd r1 M1): every test that runs the
    script asserts this BEFORE anything else, so a no-venv clone fails on this message (bug-253's
    E line) and never on a later, unlisted one."""
    out = r.stdout + r.stderr
    missing = [l for l in out.splitlines() if "not found at" in l]
    assert r.returncode != 2 and not missing, (
        f"scripts/lint-gmd.sh did not run its checks (exit {r.returncode}); a missing "
        "precondition is a failure, not a clean tree:\n" + out[-2000:])


def assert_gate_ran_clean(r: "subprocess.CompletedProcess") -> None:
    """The verdict of one `scripts/lint-gmd.sh` run on a tree that must be clean. Shared with
    tests/test_bug230_repo_scope_gate.py, which feeds it a gate whose parity step crashed.

    bug-179 audit s1 (2026-11-09): the gate exits 2 on a missing precondition (no linter, no
    parity script, no `.venv-eval` dev interpreter) BEFORE lint runs, printing no ": error"
    line -- so a test that only counted error lines passed in 0.13 s while nothing was linted.
    Exit 2 is the script's and lint's usage/precondition code, never a lint verdict (0/1), so it
    means the gate did not run. Assert that FIRST: a gate that did not run is a failure with its
    own message, never a clean tree.

    bug-230 (2026-11-14): exit 0 is the ONLY clean verdict. Rejecting exit 2 alone let a gate
    whose parity step was killed (the sandbox's exit 86, no `: error` line) pass as clean."""
    out = r.stdout + r.stderr
    assert_gate_ran(r)
    errors = [l for l in out.splitlines() if ": error" in l]
    assert not errors, "in-scope GMD errors:\n" + "\n".join(errors[:20])
    assert r.returncode == 0, (
        f"scripts/lint-gmd.sh exited {r.returncode} with no `: error` line: a step did not "
        "complete (crashed, killed, or a usage error), which is a failure, not a clean "
        "tree:\n" + out[-2000:])
