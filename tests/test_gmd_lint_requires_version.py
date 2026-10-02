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

def test_the_repo_scope_is_clean_under_the_stricter_gate():
    """The gate is only worth having if the tree it guards passes it. Runs the
    real `scripts/lint-gmd.sh`, which is what the commit gate invokes."""
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(["./scripts/lint-gmd.sh"], cwd=str(root),
                       capture_output=True, text=True)
    errors = [l for l in (r.stdout + r.stderr).splitlines() if ": error" in l]
    assert not errors, "in-scope GMD errors:\n" + "\n".join(errors[:20])
