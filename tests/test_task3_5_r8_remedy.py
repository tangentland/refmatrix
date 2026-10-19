"""Task 3.5 — the plan-3 r8 remedy (ch-bsd plan-3 r8, DIRTY 0B/4S/1M at d4bf001).

#s-1  Three r7 closures held in behaviour and in no test: mutants M4 (promote's
      global write at a fixed 30 s), M10 (locate's KEYWORD leg stops reading its
      errors) and M12 (the omnibox zero-hit branch back to a bare "no hits")
      survived the whole plan-3 set. M4 and M8 are pinned by tightening their r7
      tests in place (`test_plan3_remedy_r7.py`); M10 and M12 are pinned here.
      These tests PASS at HEAD by design — the behaviour is right, the guard was
      missing — so their RED proof is the r8 mutant, run in a scratch copy.

#s-2  Absent was still called busy on the global legs. `memory promote` against a
      global store with no daemon failed in 0.0 s with `[Errno 2] No such file or
      directory` (r8 probe P2) where `memory add --global` starts the daemon; and
      `federated_where` said "did not answer within 3s (FileNotFoundError)" for a
      socket that does not exist. Both commands converge on ONE global-write
      helper, `verbs.global_write`; the where leg words its reason from the
      exception type. RED at HEAD.

#s-3  r7 #s-4 asked for one `--degree` test against a REAL daemon, to graduate
      r6's `answering` fixture (a faked `daemon.call`). It was never written and
      never declared dropped. GREEN at HEAD (r7 verified the behaviour); its RED
      proof is a mutation of the `--degree` tail.

Every daemon here is real: `Store.init` + `spawn_daemon_subprocess` on a SHORT
`/tmp` root (macOS `sun_path` is ~104 bytes), and the global store is redirected
with `RMX_HOME`, never by patching `hub.global_store_root`.
"""
from __future__ import annotations

import shutil
import socket
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from refmatrix import cli as cli_mod
from refmatrix import daemon as dm
from refmatrix import discovery, search, verbs
from refmatrix import hub as hub_mod
from refmatrix.store import Store
from tests.test_plan2_remedy import _PingOnlyDaemon
from tests.test_plan3_remedy_r7 import up_without_replica  # noqa: F401 — fixture

BODY = "body of held_row"


def _short_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp"))


@pytest.fixture
def cold_global(monkeypatch):
    """A global store root with NO daemon: the state r8's probe P2 measured.
    `RMX_HOME` is the global store root (`hub.global_store_root` is
    `taxonomy.user_home()`), so the redirect is an env input, not a patch."""
    groot = _short_dir("rmxg-")
    monkeypatch.setenv("RMX_HOME", str(groot))
    assert hub_mod.global_store_root() == groot
    assert not dm.ping(groot)
    yield groot
    if dm.ping(groot):
        dm.stop_daemon(groot)
    shutil.rmtree(groot, ignore_errors=True)


@pytest.fixture
def live_project(monkeypatch):
    """A real project store behind a real spawned daemon, holding `held_row`."""
    base = _short_dir("rmxp-")
    root = base / "p" / ".refmatrix"
    root.parent.mkdir()
    Store(root).init()
    pid = dm.spawn_daemon_subprocess(root, watch_root=[])
    assert pid and dm.ping(root)
    monkeypatch.setattr(cli_mod, "_root", lambda: root)
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    # Seeded through the CLI twin, so the row lands in the partition the
    # `rmx memory` commands under test resolve (`memory-<project>`).
    r = CliRunner().invoke(cli_mod.main, ["memory", "add", "held_row", "-c", BODY,
                                          "--type", "project"])
    assert r.exit_code == 0, r.output
    # A daemon write lands on the writer slot; reads are served once the next
    # snapshot makes it visible (test_memory_bridge's `_get` waits the same way).
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        g = dm.call(root, "memory_get", {"name": "held_row",
                                         "partition": verbs.memory_partition(root)}, timeout=10)
        if g.get("ok") and (g.get("result") or {}).get("memory"):
            break
        time.sleep(0.2)
    else:
        pytest.fail("the seeded row never became readable")
    yield root
    dm.stop_daemon(root)
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def no_projects(monkeypatch):
    """Only the GLOBAL leg of `federated_where` runs."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [])
    monkeypatch.setattr(search, "_live_roots", lambda: ([], []))


def _global_reasons(out: dict) -> list[str]:
    return [s.get("reason", "") for s in out["skipped"] if s.get("project") == "global"]


# ---- #s-1 M10: the keyword leg reports on its own ---------------------------

def test_locate_reports_the_keyword_leg_on_its_own(up_without_replica, monkeypatch):  # noqa: F811
    """r8 M10 survived 125/125: the r7 test accepts "failed", and with a filename
    in the query the FILENAME leg supplies it. Keyword ONLY (r8 probe P4c's
    shape), and the reason must carry the keyword it was for."""
    monkeypatch.setattr(discovery, "discover_roots", lambda: [up_without_replica.root])
    monkeypatch.setattr(search, "_live_roots", lambda: ([up_without_replica.root], []))
    out = search.federated_locate(keywords=["held"])
    assert out["results"] == [], out
    reason = " ".join(s.get("reason", "") for s in out["skipped"])
    assert "(keyword 'held')" in reason, (
        f"the keyword leg dropped an unreadable store silently: {out['skipped']}")
    assert "replica" in reason.lower(), out["skipped"]


# ---- #s-1 M12: the omnibox zero-hit branch says which stores were skipped ---

def test_the_omnibox_zero_hit_branch_says_which_stores_were_skipped():
    """r8 M12 brought back r7 #s-3's exact symptom — every store skipped renders
    as "no hits" — and survived 125/125: the r1 #b-4 test checks only the
    GROUPED branch, and its `"skipNote" in body` is satisfied elsewhere.

    Source-level, like its sibling in `test_ui_server.py`: this repo runs no JS.
    It pins the zero-hit branch itself."""
    from refmatrix import ui

    js = (Path(ui.__file__).resolve().parent / "static" / "app.js").read_text()
    body = js[js.index("async function doWhere("):]
    body = body[:body.index("\n}\n")]
    start = body.index("if (!hits.length) {")
    branch = body[start:body.index("return;", start)]
    assert "skipNote" in branch, (
        "the zero-hit branch renders without the skipped-store note — a store "
        f"that could not be searched reads as 'no hits':\n{branch}")
    # "no hits" may only be the fallback when NOTHING was skipped.
    assert "skipNote ||" in branch, branch


# ---- #s-2: absent is not busy on the global legs ----------------------------

@pytest.mark.timeout(120)
def test_promote_starts_an_absent_global_daemon_and_the_row_lands(cold_global, live_project):
    """r8 probe P2: 0.0 s, exit 1, `global store memory_add failed: [Errno 2]
    No such file or directory`, ensure_global_daemon calls = 0. Before r8 this
    spawned the global daemon and wrote the row; `memory add --global` still
    does. Real project daemon, real cold global root — nothing faked."""
    r = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
    assert "Errno" not in r.output, r.output
    assert r.exit_code == 0, r.output
    assert "promoted to global" in r.output, r.output
    assert dm.ping(cold_global), "promote did not start the global daemon"
    # Visible once the global daemon's next snapshot lands (as in the fixture).
    deadline, g = time.monotonic() + 30, {}
    while time.monotonic() < deadline:
        g = hub_mod.global_call("memory_get", {"name": "held_row"}, timeout=10.0, retries=0)
        if g.get("ok") and (g.get("result") or {}).get("memory"):
            break
        time.sleep(0.2)
    assert g.get("ok"), g
    assert (g["result"].get("memory") or {}).get("content") == BODY, g


@pytest.mark.timeout(120)
def test_promote_and_add_global_share_one_global_write_helper(cold_global, live_project,
                                                              monkeypatch):
    """The anti-drift half of #s-2: the two global WRITE paths diverged (one
    ensured the daemon, one did not) because each called `hub.global_call`
    itself. One helper, `verbs.global_write`, and both commands go through it.
    The spy passes through to the real helper and the real daemons."""
    real = verbs.global_write
    seen: list = []

    def spy(*a, **kw):
        seen.append((a, kw))
        return real(*a, **kw)
    monkeypatch.setattr(verbs, "global_write", spy)

    r1 = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
    assert r1.exit_code == 0, r1.output
    n = len(seen)
    assert n >= 1, "memory promote wrote the global store without verbs.global_write"
    r2 = CliRunner().invoke(cli_mod.main, ["memory", "add", "other_row", "-c", "b", "--global"])
    assert r2.exit_code == 0, r2.output
    assert len(seen) > n, "memory add --global wrote the global store without verbs.global_write"


@pytest.mark.timeout(60)
def test_promote_says_not_running_when_the_global_daemon_cannot_start(cold_global, live_project,
                                                                       monkeypatch):
    """Absent and could not be started: the error names the state ("not
    running"), never the errno of a connect to a socket that is not there."""
    def refuse(*a, **kw):
        raise RuntimeError("daemon spawn refused (test)")
    monkeypatch.setattr(dm, "spawn_daemon_subprocess", refuse)
    t0 = time.monotonic()
    r = CliRunner().invoke(cli_mod.main, ["memory", "promote", "held_row"])
    elapsed = time.monotonic() - t0
    assert r.exit_code != 0, r.output
    assert "not running" in r.output.lower(), r.output
    assert "Errno" not in r.output, r.output
    assert elapsed < verbs.MEMORY_READ_BUDGET_S + 3.0, f"{elapsed:.1f}s"


def test_where_calls_an_absent_global_socket_not_running(cold_global, no_projects):
    """r8 probe P4b: `global memory_search did not answer within 3s
    (FileNotFoundError)` — a timeout claim for an op that failed instantly."""
    reasons = _global_reasons(search.federated_where("held"))
    assert reasons, "the absent global leg was dropped silently"
    assert "not running" in reasons[0], reasons
    assert "did not answer within" not in reasons[0], reasons


def test_where_calls_a_refused_global_socket_not_running(cold_global, no_projects):
    """A socket FILE with no listener (a daemon that died without unlinking it):
    `ConnectionRefusedError`, which is absent, not busy."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(dm.socket_path(cold_global)))
    s.close()
    reasons = _global_reasons(search.federated_where("held"))
    assert reasons, "the refused global leg was dropped silently"
    assert "not running" in reasons[0], reasons
    assert "did not answer within" not in reasons[0], reasons


@pytest.mark.timeout(60)
def test_where_still_calls_a_held_global_store_busy(no_projects, monkeypatch):
    """Busy stays busy: a global daemon that answers ping and stalls the op is
    "did not answer within", never "not running"."""
    g = _PingOnlyDaemon(seeded=True)
    try:
        monkeypatch.setenv("RMX_HOME", str(g.root))
        reasons = _global_reasons(search.federated_where("held"))
        assert reasons, "the held global leg was dropped silently"
        assert "did not answer within" in reasons[0], reasons
        assert "not running" not in reasons[0], reasons
    finally:
        g.close()


# ---- #s-3: the real-daemon --degree test r7 #s-4 asked for ------------------

@pytest.mark.timeout(120)
def test_memory_get_degree_renders_the_bundle_from_a_real_daemon(live_project):
    """Graduates r6's `answering` fixture (a faked `daemon.call`) for the
    healthy-path `--degree` evidence. bug-026's NameError lived on exactly the
    branch a HEALTHY daemon takes. No `# rmx:` line: the bundle came from the
    daemon's `context` op, not a degraded fallthrough."""
    r = CliRunner().invoke(cli_mod.main, ["memory", "get", "held_row", "--degree", "1"])
    assert r.exit_code == 0, r.output
    assert r.exception is None, repr(r.exception)
    assert BODY in r.output, r.output
    assert "--- context ---" in r.output, r.output
    tail = r.output.split("--- context ---", 1)[1]
    assert "held_row" in tail, f"no bundle under the context header: {tail!r}"
    assert "# rmx:" not in r.output, f"the bundle degraded: {r.output!r}"
