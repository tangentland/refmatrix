"""ch-bsd r6 #s-2: a reranker that cannot load is SURFACED on `rmx context`.

`_op_context` caught every `d._reranker()` failure into `rmxd.log` and served
the answer unreranked, so a ModelNotCached (an operator action: fetch the model)
became a log line nobody reads. The op now returns `warnings` beside `body`,
the CLI prints them to stderr, and the verb keeps them on the parsed bundle.

The model worker is the external boundary stubbed here (a daemon whose
`_reranker` raises); the store, the op, the CLI and the verb are real.
"""
from __future__ import annotations

import json
import threading

from click.testing import CliRunner

from refmatrix.models_local import ModelNotCached
from refmatrix.store import Store


class _D:
    def __init__(self, st):
        self.store = st
        self._store_lock = threading.RLock()
        self.logged: list[str] = []

    def _st(self):
        return self.store

    def _open_read_store(self, partition):
        return None   # writer fallback (ch-bsd r8 #s-2)

    def _request_snapshot(self):
        pass

    def _log(self, msg):
        self.logged.append(msg)

    def _maybe_rerank(self, args):
        return True

    def _reranker(self):
        raise ModelNotCached("model 'x/y' is not in the local Hugging Face cache")


def test_the_context_op_returns_the_rerank_failure_beside_the_body(tmp_path):
    from refmatrix.daemon import _op_context

    s = Store(tmp_path / ".refmatrix")
    s.init()
    cid = s.add_concept("Widget")
    s.link("defines", cid, s.upsert_entity(kind="code", name="w.py"))
    d = _D(s)

    resp = _op_context(d, {"ref": "Widget", "format": "json", "degree": 1,
                           "grep_backstop": False})

    assert json.loads(resp["body"])["anchor"]["name"] == "Widget"
    assert len(resp["warnings"]) == 1, resp
    assert "ModelNotCached" in resp["warnings"][0]
    assert "unreranked" in resp["warnings"][0]
    assert d.logged, "the log line stays too"
    s.close()


def test_the_cli_prints_the_warning_to_stderr(tmp_path, monkeypatch):
    from refmatrix import cli as cli_mod
    from refmatrix import daemon as daemon_mod

    monkeypatch.setattr(cli_mod, "_should_via_replica", lambda v: False)
    monkeypatch.setattr(cli_mod, "_root", lambda: tmp_path / ".refmatrix")
    monkeypatch.setattr(daemon_mod, "ping", lambda root, *a, **k: True)
    monkeypatch.setattr(daemon_mod, "call", lambda root, op, payload, **k: {
        "ok": True, "result": {"body": "BODY", "warnings": ["rerank unavailable (X)"]}})

    r = CliRunner().invoke(cli_mod.main, ["context", "Widget"])

    assert r.exit_code == 0, r.output
    assert "BODY" in r.stdout
    assert "rmx context: rerank unavailable (X)" in r.stderr
    assert "rerank unavailable" not in r.stdout


def test_the_verb_keeps_the_warnings_on_the_parsed_bundle(tmp_path, monkeypatch):
    from refmatrix import verbs

    monkeypatch.setattr(verbs, "_call", lambda root, op, payload, **k: {
        "body": json.dumps({"anchor": None, "groups": {}}),
        "warnings": ["rerank unavailable (X)"]})

    out = verbs.context(tmp_path, "Widget")

    assert out["warnings"] == ["rerank unavailable (X)"]
