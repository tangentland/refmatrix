"""`memory_brief` against a REAL spawned daemon — the test ch-bsd r1 #b-8 asked for.

Every other daemon-op test in this range monkeypatches `daemon._read_with_fallback`,
which is the exact function whose use IS the claim ("derivation runs on the read
path"). Per CLAUDE.md #no-mocks, a test that patches the thing under test is not
a test. This one spawns a daemon on a short tmp root and drives the op over the
socket.

Short root: macOS `sun_path` is ~104 bytes (CLAUDE.md #system-dependent-tests).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

RMX = Path(__file__).resolve().parents[1] / ".venv-eval" / "bin" / "rmx"
pytestmark = pytest.mark.skipif(not RMX.exists(), reason="dev rmx not built")


@pytest.fixture
def daemon_root():
    tmp = Path(tempfile.mkdtemp(prefix="/tmp/bd."))
    root = tmp / ".refmatrix"
    env = {**os.environ, "REFMATRIX_ROOT": str(root),
           "RMX_INVOCATION_SOURCE": "eval"}
    subprocess.run([str(RMX), "init", "--path", str(tmp), "--no-hooks",
                    "--no-agents", "--no-memory-hooks"],
                   env=env, capture_output=True, timeout=120)
    _seed(root, env)                      # edges BEFORE the daemon opens it
    subprocess.run([str(RMX), "daemon", "start", "--no-watch"],
                   env=env, capture_output=True, timeout=180)
    for _ in range(60):
        if list(root.glob("*.sock")):
            break
        time.sleep(1)
    yield root, env
    subprocess.run([str(RMX), "daemon", "stop"], env=env,
                   capture_output=True, timeout=120)
    shutil.rmtree(tmp, ignore_errors=True)


def _rmx(env, *args, timeout=180):
    return subprocess.run([str(RMX), *args], env=env, capture_output=True,
                          text=True, timeout=timeout)


def _seed(root: Path, env) -> None:
    """Give the store edges, not just rows.

    ch-bsd r2: this file passed with BOTH the #b-1 and #b-4 fixes REVERTED,
    because `rmx memory add` writes no linkage fragments — so every fixture
    yielded zero briefs, `--gmd` rendered the empty-document branch and never
    reached `_as_brief`, and `--save` saved nothing so nothing could re-enter.
    A real daemon with no data is not coverage. Seed through the store the
    daemon is serving, then let the daemon read it.
    """
    from refmatrix.store import Store
    s = Store(root)
    part = root.parent.name
    with s.with_partition(part):
        orphan = s.add_concept("orphanterm")
        for i in range(6):
            m = s.add_memory(f"seed{i}", f"body mentioning orphanterm {i}",
                             mtype="project")
            s.link("mentions", orphan, m)
        a = s.add_memory("claim-a", "the fix is X", mtype="project")
        b = s.add_memory("claim-b", "the fix is not X", mtype="project")
        s.link("contradicts", a, b)
        s.flush_fragments()
    s.close()


def test_brief_runs_end_to_end_through_a_real_daemon(daemon_root):
    root, env = daemon_root
    assert list(root.glob("*.sock")), "daemon never bound"

    _rmx(env, "memory", "add", "note-a", "the daemon owns the duckdb catalog")
    _rmx(env, "memory", "add", "note-b", "the catalog is owned by one writer")

    p = _rmx(env, "memory", "brief", "--json", "--min-mentions", "3")
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    # NOT just "the keys exist" — the seeded corpus must actually produce
    # briefs, or every assertion below is vacuous (ch-bsd r2).
    assert payload["briefs"], payload["stats"]
    classes = {b["class"] for b in payload["briefs"]}
    assert {"orphan-concept", "contradicted"} & classes, classes


def test_the_gmd_flag_does_not_crash_through_a_real_daemon(daemon_root):
    """#b-1 died here on every real invocation while a unit test passed."""
    root, env = daemon_root
    p = _rmx(env, "memory", "brief", "--gmd", "--min-mentions", "3")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "AttributeError" not in (p.stdout + p.stderr)
    # must reach _as_brief, i.e. render a real brief — not the empty branch
    assert "### " in p.stdout, p.stdout[:400]
    assert "no briefs" not in p.stdout.lower()
    # AND the edges must survive the renderer. `console.print` parsed
    # `[[name]]` as rich markup and emitted `[]`, deleting every wikilink and
    # every `rel:` target — while tools/gmd/lint.py reported 0 errors on the
    # wreckage, because `[[]]` is not a wikilink (ch-bsd r3 #b-1-r3).
    assert "rel: evidence-for -> [[" in p.stdout, p.stdout[:800]
    assert "-> []" not in p.stdout, "rich ate the wikilink"


def test_saved_briefs_do_not_grow_the_corpus_on_rerun(daemon_root):
    """#b-4 live, now that the replica lag is waited out rather than dodged."""
    root, env = daemon_root
    first = json.loads(_rmx(env, "memory", "brief", "--json",
                            "--min-mentions", "3", "--save").stdout)
    assert first.get("saved", 0) > 0, "nothing was saved; the test is vacuous"

    # Poll the DAEMON until the replica carries the saved rows. This is a
    # daemon read — nothing feedback_store_calls_via_daemon forbids — and it
    # closes the gap I previously documented as unclosable (ch-bsd r3).
    for _ in range(30):
        listing = _rmx(env, "memory", "list", "--type", "brief/orphan-concept")
        if "brief-" in listing.stdout:
            break
        time.sleep(1)
    else:
        pytest.fail("saved briefs never reached the replica; test is vacuous")

    second = json.loads(_rmx(env, "memory", "brief", "--json",
                             "--min-mentions", "3").stdout)
    assert second["stats"]["memories"] == first["stats"]["memories"], (
        "a saved brief re-entered its own corpus")


def test_an_unknown_class_fails_loudly_through_the_daemon(daemon_root):
    """#m-17: the MCP schema has no enum, so this path is reachable."""
    root, env = daemon_root
    # click.Choice already rejects this, so exit!=0 proved nothing about the
    # ValueError (ch-bsd r2). Assert the LIBRARY raises, where MCP reaches it.
    from refmatrix import brief as brief_mod
    from refmatrix.store import Store
    s = Store(root)
    with s.with_partition(root.parent.name):
        with pytest.raises(ValueError) as e:
            brief_mod.compile_briefs(s, classes=["bogus-class"])
    s.close()
    assert "bogus-class" in str(e.value)
    assert _rmx(env, "memory", "brief", "--class", "bogus-class").returncode != 0
