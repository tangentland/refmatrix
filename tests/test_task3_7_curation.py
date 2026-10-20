"""Task 3.7 batch A — `rmx_curate` (RED).

Spec #fam-curation: `rmx_curate(action=protect|unprotect|noise|unnoise|forget,
names=…, like=…, namespace=…, kind=…)` over the existing `set_flag` / `forget`
daemon ops (C4 writes via `_call`, 60 s; forget 600 s; single attempt, #budgets).
  - at least one selector (`VerbArgsError`);
  - `forget` defaults to `dry_run=True` (returns what WOULD be forgotten);
  - a selector that is ONLY `kind` and/or `namespace` also needs `broad=True` for a
    destructive forget, else `VerbArgsError` naming the count it would remove;
  - C4a: no daemon ⇒ `local_write` in-process (reads inside the same handle);
  - C5: busy ⇒ `VerbBusyError` (never in-process), refusal ⇒ `VerbError` with the
    daemon's words, an undiallable path is neither;
  - C7: `partition` reaches every op.

Interpretation (named in the RED report): the `broad` guard applies to the
destructive call only; a kind-only DRY RUN is the preview that names the count.
"""
from __future__ import annotations

import pytest

from refmatrix import daemon as dm
from refmatrix import discovery, verbs
from tests.task3_7_helpers import (FakeDaemon, entity_names, init_store, make_snapshot, rm,
                                   short_root)
from tests.test_plan2_remedy import _SilentDaemon

_FLAGS = {"protect": ("protected", True), "unprotect": ("protected", False),
          "noise": ("noise", True), "unnoise": ("noise", False)}


@pytest.fixture
def root(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    base, r = short_root("r37c-")
    yield r
    rm(base)


def _flag_answer(args):
    return {"ok": True, "result": {"count": len(args.get("names") or []) or 3,
                                   "names": list(args.get("names") or ["a", "b", "c"])}}


def _forget_answer(args):
    names = list(args.get("names") or ["c1", "c2", "c3"])
    if args.get("dry_run"):
        return {"ok": True, "result": {"forgotten": 0, "names": names, "dry_run": True}}
    return {"ok": True, "result": {"forgotten": len(names), "names": names, "dry_run": False}}


@pytest.mark.parametrize("action", sorted(_FLAGS))
def test_flag_actions_send_set_flag_with_the_selector_and_partition(root, monkeypatch, action):
    fd = FakeDaemon({"set_flag": _flag_answer}).install(monkeypatch)
    out = verbs.curate(root, action=action, names=["a"], like="x%", partition="px")
    _op, args, timeout, retries = fd.last("set_flag")
    flag, value = _FLAGS[action]
    assert args["flag"] == flag and bool(args["value"]) is value, args
    assert args["names"] == ["a"] and args["like"] == "x%", args
    assert args["partition"] == "px", "C7: the CLI's -p partition must reach the op"
    assert timeout == 60.0 and retries == 0, (timeout, retries)
    assert out["count"] == 1 and out["names"] == ["a"], out


def test_flag_action_without_partition_uses_the_project_partition(root, monkeypatch):
    fd = FakeDaemon({"set_flag": _flag_answer}).install(monkeypatch)
    verbs.curate(root, action="protect", names=["a"])
    assert fd.last("set_flag")[1]["partition"] == discovery.store_name(root)


@pytest.mark.parametrize("action", ["protect", "unprotect", "noise", "unnoise", "forget"])
def test_a_selector_is_required(root, monkeypatch, action):
    fd = FakeDaemon({}).install(monkeypatch)
    with pytest.raises(verbs.VerbArgsError):
        verbs.curate(root, action=action)
    assert fd.calls == [], "a selector-less curate reached the daemon"


def test_forget_defaults_to_a_dry_run(root, monkeypatch):
    fd = FakeDaemon({"forget": _forget_answer}).install(monkeypatch)
    out = verbs.curate(root, action="forget", names=["n1", "n2"])
    assert [c[1].get("dry_run") for c in fd.calls if c[0] == "forget"] == [True], fd.calls
    assert out["names"] == ["n1", "n2"] and out["dry_run"] is True, out


@pytest.mark.parametrize("sel", [{"kind": "code"}, {"namespace": "query"},
                                 {"kind": "doc", "namespace": "query"}])
def test_a_broad_destructive_forget_needs_broad_and_names_the_count(root, monkeypatch, sel):
    fd = FakeDaemon({"forget": _forget_answer}).install(monkeypatch)
    with pytest.raises(verbs.VerbArgsError) as ei:
        verbs.curate(root, action="forget", dry_run=False, **sel)
    assert "3" in str(ei.value), ("the refusal names the count it would remove", str(ei.value))
    assert not [c for c in fd.calls if c[0] == "forget" and not c[1].get("dry_run")], (
        "a non-dry forget was sent without broad=True")


def test_a_broad_forget_with_broad_true_runs_with_the_600s_budget(root, monkeypatch):
    fd = FakeDaemon({"forget": _forget_answer}).install(monkeypatch)
    out = verbs.curate(root, action="forget", kind="code", dry_run=False, broad=True)
    real = [c for c in fd.calls if c[0] == "forget" and not c[1].get("dry_run")]
    assert len(real) == 1, fd.calls
    _op, args, timeout, retries = real[0]
    assert args["kind"] == "code" and timeout == 600.0 and retries == 0, real[0]
    assert out["forgotten"] == 3, out


def test_a_named_forget_needs_no_broad(root, monkeypatch):
    fd = FakeDaemon({"forget": _forget_answer}).install(monkeypatch)
    out = verbs.curate(root, action="forget", names=["n1"], dry_run=False)
    assert out["forgotten"] == 1
    assert fd.last("forget")[1]["dry_run"] is False


# ---- C5: busy / refused / undiallable ------------------------------------------


def test_a_write_timeout_is_busy_and_not_confirmed(root, monkeypatch):
    FakeDaemon({"set_flag": TimeoutError("timed out")}).install(monkeypatch)
    with pytest.raises(verbs.VerbBusyError) as ei:
        verbs.curate(root, action="protect", names=["a"])
    assert "not confirmed" in str(ei.value), str(ei.value)


def test_a_refusal_carries_the_daemons_words(root, monkeypatch):
    FakeDaemon({"set_flag": {"ok": False, "error": "CANARY-refused flag"}}).install(monkeypatch)
    with pytest.raises(verbs.VerbError) as ei:
        verbs.curate(root, action="protect", names=["a"])
    assert "CANARY-refused flag" in str(ei.value)
    assert not isinstance(ei.value, (verbs.VerbBusyError, verbs.VerbAbsentError))


def test_an_undiallable_socket_path_is_neither_absent_nor_in_process(root, monkeypatch):
    FakeDaemon({"set_flag": OSError("AF_UNIX path too long")}).install(monkeypatch)
    opened: list = []
    monkeypatch.setattr(verbs, "local_write", lambda *a, **k: opened.append(a) or {})
    with pytest.raises(verbs.VerbError) as ei:
        verbs.curate(root, action="protect", names=["a"])
    assert not isinstance(ei.value, verbs.VerbAbsentError)
    assert opened == [], "path-too-long licensed the in-process store"


@pytest.mark.timeout(60)
def test_a_real_busy_daemon_is_busy_and_never_opens_the_store(monkeypatch):
    monkeypatch.delenv("RMX_PARTITION", raising=False)
    d = _SilentDaemon(seeded=True)
    opened: list = []
    monkeypatch.setattr(verbs, "local_write", lambda *a, **k: opened.append(a) or {})
    try:
        with pytest.raises(verbs.VerbBusyError):
            verbs.curate(d.root, action="protect", names=["a"])
        assert opened == [], "a busy daemon was treated as absent"
    finally:
        d.close()


# ---- C4a: no daemon ⇒ in-process ------------------------------------------------


def test_no_daemon_protect_writes_in_process(root):
    init_store(root, [("concept", "keep_me")])
    assert not dm.ping(root)
    out = verbs.curate(root, action="protect", names=["keep_me"])
    assert out["count"] == 1 and out["source"] == "in-process", out
    from refmatrix.store import Store
    s = Store(root)
    try:
        with s.with_partition(discovery.store_name(root)):
            assert s.get_entity("concept", "keep_me").protected
    finally:
        s.close()


def test_no_daemon_forget_reads_then_writes_in_one_handle_over_a_stale_snapshot(root):
    """r3 M3 / C4a: the preview read and the purge share `local_write`'s writer
    handle; a `snapshot_read` in-process handle held across it is bug-135."""
    init_store(root, [("concept", "doomed"), ("concept", "spared")])
    make_snapshot(root)
    out = verbs.curate(root, action="forget", names=["doomed"], dry_run=False)
    assert out["forgotten"] == 1 and out["source"] == "in-process", out
    assert entity_names(root, "concept") == {"spared"}


def test_no_daemon_broad_forget_dry_run_names_the_count_and_deletes_nothing(root):
    init_store(root, [("code", "a.py"), ("code", "b.py"), ("concept", "c")])
    out = verbs.curate(root, action="forget", kind="code")
    assert sorted(out["names"]) == ["a.py", "b.py"] and out["dry_run"] is True, out
    with pytest.raises(verbs.VerbArgsError) as ei:
        verbs.curate(root, action="forget", kind="code", dry_run=False)
    assert "2" in str(ei.value)
    assert entity_names(root, "code") == {"a.py", "b.py"}
