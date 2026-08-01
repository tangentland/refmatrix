"""cctree served by the hub, plus the offloaded-output rehydration.

cctree moved into refmatrix from ~/claude_tools/utilities. These cover the two
things that move introduced: HTTP routes over the renderers, and reading back
tool output that the transcript only kept a preview of.
"""
from __future__ import annotations

import json

import pytest

from refmatrix import cctree

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402

from refmatrix.hub import Hub  # noqa: E402
from refmatrix.ui import server as srv  # noqa: E402


# ------------------------------------------------------------- rehydration ---

def test_offloaded_output_is_read_back_from_disk(tmp_path):
    big = tmp_path / "hook-abc-stdout.txt"
    big.write_text("X" * 5000)
    stub = (f"Output too large (39.1KB). Full output saved to: {big}\n\n"
            f"Preview (first 2KB):\nXXX")
    out = cctree._rehydrate_offload(stub)
    assert "rehydrated" in out
    assert out.count("X") >= 5000


def test_rehydration_handles_the_persisted_output_wrapper(tmp_path):
    big = tmp_path / "hook-def-stdout.txt"
    big.write_text("payload-body")
    stub = (f"<persisted-output>\nOutput too large (15.7KB). "
            f"Full output saved to: {big}\n\nPreview (first 2KB):\npay")
    assert "payload-body" in cctree._rehydrate_offload(stub)


def test_missing_offload_file_says_so_instead_of_passing_off_the_preview(tmp_path):
    stub = (f"Output too large (1KB). Full output saved to: {tmp_path / 'gone.txt'}\n"
            f"Preview (first 2KB):\nonly-this")
    out = cctree._rehydrate_offload(stub)
    assert "unreadable" in out
    assert "only-this" in out          # the preview is kept, not discarded


def test_output_that_merely_quotes_the_marker_is_left_alone(tmp_path):
    """A grep over a transcript prints the marker. Rewriting that result would
    corrupt an innocent tool output, so the match is anchored at the head."""
    real = tmp_path / "hook-xyz-stdout.txt"
    real.write_text("SHOULD-NOT-APPEAR")
    quoting = (f"=== grep results ===\n"
               f"Output too large (39.1KB). Full output saved to: {real}\n")
    assert cctree._rehydrate_offload(quoting) == quoting


def test_decorations_rehydrate_too(tmp_path):
    """Hook stdout is the most commonly offloaded payload and arrives as a
    decoration, not a tool result."""
    big = tmp_path / "hook-ghi-stdout.txt"
    big.write_text("hook-full-body")
    att = {"type": "hook_success",
           "content": f"Output too large (9KB). Full output saved to: {big}\nPreview:"}
    assert "hook-full-body" in cctree.decoration_text(att)


# ------------------------------------------------------------- render args ---

def test_render_args_carries_every_cli_default():
    """The renderers read options the server never sets; taking the real
    parser's defaults is what keeps a new flag from raising AttributeError."""
    a = cctree.render_args(full=True, no_subagents=True)
    assert a.full is True and a.no_subagents is True
    for attr in ("no_decoration", "thinking", "turn", "tool", "out_limit",
                 "in_limit", "deco_limit", "resp_limit"):
        assert hasattr(a, attr), attr


# ------------------------------------------------------------------ routes ---

@pytest.fixture
def client():
    return TestClient(srv.create_app(Hub(port=0)))


@pytest.fixture
def a_session():
    projects = cctree.all_projects()
    if not projects:
        pytest.skip("no Claude Code transcripts on this host")
    for d in projects:
        s = cctree.sessions_in(d)
        if s:
            return s[0]
    pytest.skip("no sessions")


def test_index_lists_sessions(client, a_session):
    r = client.get("/cctree")
    assert r.status_code == 200
    assert "<details" in r.text
    assert f"/cctree/{a_session.stem}" in r.text


def test_session_page_renders(client, a_session):
    r = client.get(f"/cctree/{a_session.stem}")
    assert r.status_code == 200
    assert "<details" in r.text and "</html>" in r.text


def test_unknown_session_404s_and_escapes_the_id(client):
    # Slash-free on purpose: a payload containing `/` fails to match the route
    # at all and gets FastAPI's JSON 404, which would never exercise the HTML
    # error path this is here to check.
    r = client.get("/cctree/<img src=x onerror=alert(1)>")
    assert r.status_code == 404
    assert "<img src=x" not in r.text
    assert "&lt;img" in r.text


def test_sessions_api_groups_by_recorded_cwd(client, a_session):
    r = client.get("/api/cctree/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["sessions"])
    row = next(s for s in body["sessions"] if s["session"] == a_session.stem)
    # cwd comes from inside the transcript, not the lossy directory name.
    assert row["cwd"].startswith("/")
    assert row["url"] == f"/cctree/{a_session.stem}"


def test_session_json_route(client, a_session):
    r = client.get(f"/api/cctree/session/{a_session.stem}")
    assert r.status_code == 200
    assert isinstance(r.json(), (dict, list))


def test_session_json_404(client):
    assert client.get("/api/cctree/session/nope-nope").status_code == 404


def test_json_route_matches_the_module(a_session, client):
    turns, runs = cctree.parse_session(a_session)
    direct = json.loads(cctree.to_json(turns, a_session, runs))
    served = client.get(f"/api/cctree/session/{a_session.stem}").json()
    assert type(direct) is type(served)
