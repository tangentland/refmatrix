"""Task 3.7 remedy round 2 — RED for the three MEH findings (spec #remedy-r2-meh-red; ch-bsd
`workflow/bullshit/2026-11-08-2256-task-3.7-remedy-r1-2a4096c.md` #m-1, #m-2, #m-3).

R2-M1  `curator status --drain` behind a head spool file holding more paths than `--limit`
       keeps that file (never fully shown) and cannot reach the newer ones — data-safe, but
       the skip was uncounted (CLAUDE.md#no-silent-failures). It must say on STDERR how many
       spool files it kept and why; exit code and the stdout line are unchanged.
R2-M2  the shipped gmd-curator template must not claim a hook drains the spool. The test
       reads the GENERATED hook commands (`hooks._claude_hook_block`), so it tracks what the
       hooks really do: if no hook runs `curator status --drain`, no template line may pair
       "hook" with draining.
R2-M3  the legacy raw-path parser took ANY non-JSON line as a path. Rule pinned here: a
       non-JSON line is a legacy path only when it has NO internal whitespace AND names a
       path shape (contains `/` or has a file suffix). Everything else is a counted bad
       line, warned, never an entry. The rule applies in every spool file: an adopted
       `curator.queue` keeps the spool name format, so file origin is not observable.

No doubles: real spool files on a short tmp root, the real click CLI, the real hook
generator, the shipped template file.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import gmd_curator, verbs
from refmatrix import hooks as hooks_mod
from tests.task3_7_helpers import rm, short_root

_REPO = Path(__file__).resolve().parent.parent
_TEMPLATE = _REPO / "src" / "refmatrix" / "templates" / "agents" / "gmd-curator.md"


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37m-")
    monkeypatch.setattr(cli_mod, "_root", lambda: r)
    yield r
    rm(base)


# ---- R2-M1: an oversized head file is a COUNTED keep ---------------------------------------


def test_drain_behind_an_oversized_head_file_reports_what_it_kept_on_stderr(root):
    head = gmd_curator.write_spool(root, [str(root.parent / f"BIG-{i}.md") for i in range(15)])
    newer = [gmd_curator.write_spool(root, [str(root.parent / f"N{i}{j}.md") for j in "ab"])
             for i in range(3)]
    before = sorted(p.name for p in gmd_curator.curator_spool_dir(root).glob("*.jsonl"))
    r = CliRunner().invoke(cli_mod.main, ["curator", "status", "--drain"])
    assert r.exit_code == 0, r.output
    after = sorted(p.name for p in gmd_curator.curator_spool_dir(root).glob("*.jsonl"))
    assert after == before == sorted([head, *newer]), "data safety (R-B1) regressed"
    assert "curator-queue: 15" in r.stdout and "+5 more" in r.stdout, r.stdout
    assert "kept" not in r.stdout, f"the keep notice belongs on stderr: {r.stdout!r}"
    err = r.stderr or ""
    assert re.search(r"\bkept 1 spool file", err) and "--limit" in err, (
        "status --drain kept the oversized head spool file without saying so "
        f"(uncounted skip); stderr={err!r}")
    # Control: once --limit covers the head file, everything shown is drained and the
    # keep notice is silent.
    r2 = CliRunner().invoke(cli_mod.main, ["curator", "status", "--drain", "--limit", "100"])
    assert r2.exit_code == 0, r2.output
    assert "kept" not in (r2.stderr or ""), r2.stderr


# ---- R2-M2: the template tells the truth about the hooks -----------------------------------


def _curator_hook_segments(tmp_path) -> list:
    block = hooks_mod._claude_hook_block(tmp_path / ".refmatrix")
    cmds = [h["command"] for evs in block["hooks"].values() for e in evs
            for h in e.get("hooks", []) if "command" in h]
    return [seg.strip() for c in cmds for seg in c.split(";") if "curator status" in seg]


_HOOK_DRAIN_CLAIM = re.compile(r"\bhooks?\b.*\bdrain|\bdrain\w*\b.*\bhooks?\b", re.I)


def test_the_shipped_curator_template_does_not_say_a_hook_drains_the_spool(tmp_path):
    segs = _curator_hook_segments(tmp_path)
    assert segs, "no generated hook runs `rmx curator status`"
    if any("--drain" in s for s in segs):
        pytest.fail(f"a generated hook drains again — R-B1 regressed: {segs}")
    claims = [f"{i}: {ln.strip()}" for i, ln in enumerate(_TEMPLATE.read_text().splitlines(), 1)
              if _HOOK_DRAIN_CLAIM.search(ln)]
    assert not claims, ("the generated hooks run `curator status` without --drain, but the "
                        "shipped template says a hook drains:\n" + "\n".join(claims))


# ---- R2-M3: only a path-shaped non-JSON line is a legacy entry ------------------------------


def test_a_non_path_legacy_line_is_counted_bad_not_an_entry(root):
    (root / "curator.queue").write_text(
        "docs/plan/a.md\nnot a path at all\nTraceback (most recent call last):\n/abs/ADR-1.md\n")
    out = verbs.curator(root, action="status")
    got = [(e["path"], e["reason"]) for e in out["entries"]]
    assert got == [("docs/plan/a.md", "legacy"), ("/abs/ADR-1.md", "legacy")], (
        "a non-path line became a file-change entry", got)
    assert any(w.startswith("2 unparseable line(s)") for w in out["warnings"]), out["warnings"]


def test_a_non_path_raw_line_in_a_watcher_spool_file_is_counted_bad(root):
    name = gmd_curator.write_spool(root, [str(root.parent / "GOOD.md")])
    with open(gmd_curator.curator_spool_dir(root) / name, "a") as fh:
        fh.write("not a path at all\n")
    out = verbs.curator(root, action="status")
    assert [e["path"] for e in out["entries"]] == [str(root.parent / "GOOD.md")], out["entries"]
    assert any(w.startswith("1 unparseable line(s)") and name in w
               for w in out["warnings"]), out["warnings"]
