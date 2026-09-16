"""LongMemEval store build — the passes, in order, on the production path.

RED first for task 7.2 (plan-7-longmemeval). No store is opened here: the point
of these assertions is the SHAPE of the command sequence, which is where this
harness can quietly stop measuring the product.

The two failures being guarded:

  * **Plain `rmx ingest` instead of `ingest-gmd --as-memory`.** Measured on the
    MemAware corpus: the general markdown pass over chat prose produced 1309
    doc entities, 0 `mentions` rows and 3 concepts. Every symbolic surface then
    degrades to the grep backstop and the benchmark reports a number for an
    index that was never built. The argv is the only place this is visible.

  * **A pass that fails and the build continues.** A failed embed leaves the
    dense conditions scoring an empty vector table, which reads as "rmx is bad
    at this" rather than "the build broke". `feedback_no_silent_failures`
    applies to a benchmark build as much as to a memory path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval" / "production" / "longmemeval"))

import ingest  # noqa: E402


class Recorder:
    """Stands in for subprocess.run; records argv, returns a scripted code."""

    def __init__(self, fail_on: "str | None" = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, argv: list[str], env: dict) -> int:
        self.calls.append(list(argv))
        if self.fail_on and self.fail_on in " ".join(argv):
            return 3
        return 0

    def argv_for(self, token: str) -> "list[str] | None":
        for c in self.calls:
            if token in c:
                return c
        return None


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    c = tmp_path / "corpus"
    c.mkdir()
    (c / "s1.md").write_text("---\ngmd: \"0.1\"\nid: s1\n---\n\n# s1 {#root}\n")
    return c


# ── the passes ─────────────────────────────────────────────────────────────

def test_ingest_uses_ingest_gmd_as_memory_never_plain_ingest(corpus, tmp_path):
    """The whole benchmark rests on this one argument."""
    rec = Recorder()
    ingest.build(rmx="rmx", corpus=corpus, root=tmp_path / ".refmatrix",
                 runner=rec)
    argv = rec.argv_for("ingest-gmd")
    assert argv is not None, "no ingest-gmd pass was run"
    assert "--as-memory" in argv
    assert "--memory-mtype" in argv
    assert argv[argv.index("--memory-mtype") + 1] == "longmemeval/session"
    # plain `rmx ingest` must never appear as its own subcommand
    assert not any(c[1:2] == ["ingest"] for c in rec.calls), rec.calls


def test_passes_run_in_order_ingest_then_embed_then_compile(corpus, tmp_path):
    rec = Recorder()
    ingest.build(rmx="rmx", corpus=corpus, root=tmp_path / ".refmatrix",
                 runner=rec)
    flat = [" ".join(c) for c in rec.calls]
    order = [i for i, f in enumerate(flat)
             if "ingest-gmd" in f or "embed" in f or "compile" in f]
    labels = [flat[i] for i in order]
    assert "ingest-gmd" in labels[0]
    assert "embed" in labels[1]
    assert "compile" in labels[2]


def test_embed_targets_the_memory_kind(corpus, tmp_path):
    """`--kinds memory`: these rows are ingested as memories, and an embed that
    defaults to code leaves every dense condition scoring an empty table."""
    rec = Recorder()
    ingest.build(rmx="rmx", corpus=corpus, root=tmp_path / ".refmatrix",
                 runner=rec)
    argv = rec.argv_for("embed")
    assert argv[argv.index("--kinds") + 1] == "memory"


def test_init_disables_hooks_agents_and_memory_hooks(corpus, tmp_path):
    """A benchmark store must not install itself into the user's session."""
    rec = Recorder()
    ingest.build(rmx="rmx", corpus=corpus, root=tmp_path / ".refmatrix",
                 runner=rec)
    argv = rec.argv_for("init")
    assert "--no-hooks" in argv and "--no-agents" in argv and "--no-memory-hooks" in argv


def test_each_pass_is_skippable(corpus, tmp_path):
    rec = Recorder()
    ingest.build(rmx="rmx", corpus=corpus, root=tmp_path / ".refmatrix",
                 runner=rec, skip=("embed", "compile"))
    assert rec.argv_for("ingest-gmd") is not None
    assert rec.argv_for("embed") is None
    assert rec.argv_for("compile") is None


# ── the loud failure ───────────────────────────────────────────────────────

def test_a_failing_pass_aborts_and_names_itself(corpus, tmp_path):
    rec = Recorder(fail_on="embed")
    with pytest.raises(ingest.PassFailed) as e:
        ingest.build(rmx="rmx", corpus=corpus, root=tmp_path / ".refmatrix",
                     runner=rec)
    assert "embed" in str(e.value)
    assert "3" in str(e.value)          # the exit code is reported


def test_a_failing_pass_does_not_run_the_next_one(corpus, tmp_path):
    rec = Recorder(fail_on="ingest-gmd")
    with pytest.raises(ingest.PassFailed):
        ingest.build(rmx="rmx", corpus=corpus, root=tmp_path / ".refmatrix",
                     runner=rec)
    assert rec.argv_for("embed") is None


def test_an_empty_corpus_is_refused_before_any_pass_runs(tmp_path):
    rec = Recorder()
    empty = tmp_path / "corpus"
    empty.mkdir()
    with pytest.raises(ingest.PassFailed) as e:
        ingest.build(rmx="rmx", corpus=empty, root=tmp_path / ".refmatrix",
                     runner=rec)
    assert "corpus" in str(e.value).lower()
    assert rec.calls == []


# ── the environment ────────────────────────────────────────────────────────

def test_the_build_is_pinned_to_the_benchmark_store_and_partition(corpus, tmp_path):
    """Never the project store, never the global one — the corpus is 19,829
    transcripts about synthetic people and has no business in either."""
    seen: list[dict] = []

    def rec(argv, env):
        seen.append(env)
        return 0

    root = tmp_path / ".refmatrix"
    ingest.build(rmx="rmx", corpus=corpus, root=root, runner=rec)
    for env in seen:
        assert env["REFMATRIX_ROOT"] == str(root)
        assert env["RMX_PARTITION"] == "longmemeval"
        assert env["RMX_INVOCATION_SOURCE"] == "eval"
