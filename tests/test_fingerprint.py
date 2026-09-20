"""A measured number carries the conditions it was measured under, or it is not
comparable to another number.

Three proofs from one hour on 2026-09-20:

  * a stale `[UNVERIFIED]` daemon served a MemAware run and moved scan-prompt
    0.433 -> 0.444 — same code on disk, same corpus, same questions (bug-055);
  * `rmx context` measured 0.478/0.186 against a recorded 0.511/0.248 and the
    cause is still unattributed;
  * the 0.511 turned out to be a HELD-OUT question set, tabled beside numbers
    from a different one.

Plus the fleet survey: four partition layouts, one store with no vectors at all.
At least six axes move between runs and the harnesses record NONE of them. So a
fingerprint is not documentation — it is the precondition for the comparison,
and `require()` refuses to score without it.
"""
from __future__ import annotations

import json

import pytest

from refmatrix import fingerprint as fp


def _facts(**over):
    base = dict(
        cli_version="0.72.4",
        daemon_version="0.72.4",
        daemon_code="/Users/tholley/refmatrix/src/refmatrix/__init__.py",
        store_root="/tmp/x/.refmatrix",
        partition_shape="canonical",
        partitions={"x": 100, "sessions-x": 10},
        vector_partitions=["x"],
        derive_stale=False,
        derive_versions={"ingest": "0.72.4"},
        worker_topology="shared",
        corpus_encoding="project",
    )
    base.update(over)
    return base


# ---- trust: can this number be believed about the version it names? -------

def test_a_clean_run_is_trustworthy():
    out = fp.compose(**_facts())
    assert out["trustworthy"] is True
    assert out["reasons"] == []


def test_an_unverified_daemon_is_not_trustworthy():
    """bug-055: `code: unknown (ping carries no code path; pre-0.66.3 daemon?)`
    served a run that was reported as 0.72.4."""
    out = fp.compose(**_facts(daemon_code=None, daemon_version=None))
    assert out["trustworthy"] is False
    assert any("unverified" in r.lower() for r in out["reasons"]), out["reasons"]


def test_a_daemon_on_a_different_version_than_the_cli_is_not_trustworthy():
    out = fp.compose(**_facts(daemon_version="0.66.2"))
    assert out["trustworthy"] is False
    assert any("0.66.2" in r for r in out["reasons"])


def test_a_daemon_serving_the_dev_tree_is_not_trustworthy():
    """`rmx` is the DEPLOY build; a daemon importing the dev checkout means the
    number describes uncommitted code (feedback_deploy_tree_is_the_runtime)."""
    out = fp.compose(**_facts(
        daemon_code="/Users/tholley/claude_tools/refmatrix/src/refmatrix/__init__.py"))
    assert out["trustworthy"] is False
    assert any("dev" in r.lower() for r in out["reasons"])


def test_a_stale_derive_is_not_trustworthy():
    """bug-039: a store's derived graph decays while every health surface reads
    green, so the number describes a corpus nobody re-derived."""
    out = fp.compose(**_facts(derive_stale=True,
                              derive_versions={"ingest": "0.49.1"}))
    assert out["trustworthy"] is False
    assert any("derive" in r.lower() for r in out["reasons"])


def test_an_unembedded_store_is_not_trustworthy_for_a_dense_measurement():
    """orderly: rows but no vectors, so every dense retrieval returns nothing
    and the symbolic surfaces keep working — a silent floor."""
    out = fp.compose(**_facts(vector_partitions=[]))
    assert out["trustworthy"] is False
    assert any("vector" in r.lower() for r in out["reasons"])


def test_reasons_accumulate_rather_than_short_circuiting():
    out = fp.compose(**_facts(daemon_version="0.66.2", derive_stale=True,
                              vector_partitions=[]))
    assert len(out["reasons"]) >= 3, out["reasons"]


# ---- comparability: may these two numbers be put in one table? ------------

def test_two_identical_conditions_share_a_key():
    assert fp.compose(**_facts())["key"] == fp.compose(**_facts())["key"]


@pytest.mark.parametrize("field,value", [
    ("daemon_version", "0.71.0"),
    ("partition_shape", "drift"),
    ("vector_partitions", ["x", "sessions-x"]),
    ("derive_versions", {"ingest": "0.49.1"}),
    ("worker_topology", "private"),
    ("corpus_encoding", "sessions"),
])
def test_any_moved_axis_changes_the_key(field, value):
    """Each of these moved on the fleet today. A table that mixes two keys is
    comparing across an axis nobody recorded."""
    assert fp.compose(**_facts())["key"] != fp.compose(**_facts(**{field: value}))["key"]


def test_row_counts_do_not_change_the_key():
    """A corpus that grew is still the same CONDITION; the question set and the
    encoding are what must match. Otherwise no two runs are ever comparable and
    the key is useless."""
    a = fp.compose(**_facts())
    b = fp.compose(**_facts(partitions={"x": 101, "sessions-x": 10}))
    assert a["key"] == b["key"]


def test_same_conditions_answers_the_question_directly():
    a = fp.compose(**_facts())
    b = fp.compose(**_facts(worker_topology="private"))
    assert fp.same_conditions(a, a) is True
    assert fp.same_conditions(a, b) is False


# ---- the gate a harness calls --------------------------------------------

def test_require_refuses_an_untrustworthy_fingerprint():
    bad = fp.compose(**_facts(daemon_code=None, daemon_version=None))
    with pytest.raises(fp.UntrustworthyMeasurement) as e:
        fp.require(bad)
    assert "unverified" in str(e.value).lower()


def test_require_returns_the_fingerprint_when_clean():
    good = fp.compose(**_facts())
    assert fp.require(good) is good


def test_require_can_be_overridden_but_says_so_loudly():
    """A deliberate measurement of a known-bad condition is legitimate — the
    D-vs-P arms of plan-13 measure a drifted encoding ON PURPOSE. It must be
    recorded in the fingerprint, not waved through."""
    bad = fp.compose(**_facts(derive_stale=True))
    out = fp.require(bad, accept_reasons=["derive"])
    assert out["accepted_despite"] == [r for r in bad["reasons"] if "derive" in r.lower()]
    assert out["trustworthy"] is False        # the override does not launder it


def test_an_override_that_does_not_match_a_reason_still_raises():
    bad = fp.compose(**_facts(derive_stale=True))
    with pytest.raises(fp.UntrustworthyMeasurement):
        fp.require(bad, accept_reasons=["worker"])


# ---- wiring: gather() reads the surfaces that already report these facts ---

def test_gather_on_a_daemonless_store_is_untrustworthy_and_says_why(tmp_path):
    """No daemon answering means nothing can vouch for the serving code, which
    is the bug-055 condition. It must refuse rather than assume the CLI's own
    version describes the run."""
    from refmatrix.store import Store

    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()

    out = fp.gather(root)
    assert out["trustworthy"] is False
    assert any("unverified" in r.lower() for r in out["reasons"])
    assert out["store_root"] == str(root)
    assert out["key"]


def test_the_command_prints_a_key_and_exits_nonzero_when_untrustworthy(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from refmatrix import cli as cli_mod
    from refmatrix.store import Store

    root = tmp_path / "proj" / ".refmatrix"
    root.parent.mkdir()
    s = Store(root)
    s.init()
    s.close()

    monkeypatch.setattr(cli_mod, "_root", lambda *a, **k: root)
    monkeypatch.setattr("refmatrix.daemon.ping", lambda *a, **k: False)

    res = CliRunner().invoke(cli_mod.main, ["fingerprint", "--json"])
    assert res.exit_code == 1, res.output
    payload = json.loads(res.output)
    assert payload["key"]
    assert payload["trustworthy"] is False
