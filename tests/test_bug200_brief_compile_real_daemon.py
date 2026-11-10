"""bug-200 m-2: `rmx memory brief --compile --scope pattern`, end to end, no fakes.

The bug-198 test this replaces (`test_cli_brief_compile_plans_the_same_scope`, ch-bsd
bug-197/198 r1 #m-2, 2026-11-10) faked `consolidate.compile_memories` with a plan that had NO
`scope` key, set `_read_store` to `object()` and recorded `verbs.memory`. The real op refuses
a plan compiled for a different scope (`compile_briefs` reads `plan.get("scope") or "memory"`),
so that test could not see a plan/brief scope disagreement -- the one thing it was named for.
Its two fakes had no `test_mock_registry` row.

Here everything is real: the CLI (`CliRunner` over `cli.main`), the in-process plan on the read
store, the verb, and a spawned daemon over a throwaway store under a SHORT mkdtemp root
(`spawn`, from `test_memory_compile_scope.py`). The corpus is `_seed_brief_corpus`: the memory
corpus has its own orphan `mem_only` (5 rows), the pattern corpus `imp_only` (4 rows), and a
`tag: pattern` doc's `pat_only` belongs to neither -- the auditor's probe shape.
"""
from __future__ import annotations

import json

from tests.test_memory_compile_remedy_r1 import _seed_brief_corpus
from tests.test_memory_compile_scope import _cli, spawn  # noqa: F401 (spawn is a fixture)


def _brief(*argv: str) -> dict:
    code, out = _cli("memory", "brief", *argv, "--json")
    assert code == 0, f"`rmx memory brief {' '.join(argv)} --json` exited {code}:\n{out}"
    try:
        return json.loads(out)
    except ValueError as exc:
        raise AssertionError(f"--json printed no JSON document ({exc}):\n{out}") from None


def _labels(res: dict, cls: str) -> set:
    return {b["label"] for b in res.get("briefs") or [] if b.get("class") == cls}


def test_cli_brief_compile_scope_pattern_plans_and_briefs_the_pattern_corpus(spawn):
    spawn(_seed_brief_corpus)
    res = _brief("--compile", "--scope", "pattern")
    stats = res.get("stats") or {}
    assert stats.get("scope") == "pattern", stats
    assert stats.get("memories") == 4, f"the pattern corpus is the 4 impressions: {stats}"
    assert _labels(res, "orphan-concept") == {"imp_only"}, res.get("briefs")
    # The plan-derived classes RAN (a --compile brief), on the same corpus: none of them may
    # name a row outside the pattern corpus.
    ran = stats.get("classes_run") or []
    assert "singleton" in ran and "corroborated" in ran, stats
    names = res.get("names") or {}
    seen = {names.get(str(e)) or names.get(e) for b in res.get("briefs") or []
            for e in b.get("evidence") or []}
    assert seen and all(n and n.startswith("obs_i") for n in seen), (
        f"every brief's evidence is a pattern-corpus row: {sorted(map(str, seen))}")


def test_cli_brief_compile_default_scope_is_the_memory_corpus(spawn):
    """Control in the same shape: without `--scope` the plan and the briefs are the memory
    corpus, so the pattern test above cannot pass on a scope-blind path."""
    spawn(_seed_brief_corpus)
    res = _brief("--compile")
    stats = res.get("stats") or {}
    assert stats.get("scope") == "memory", stats
    assert stats.get("memories") == 5, stats
    assert _labels(res, "orphan-concept") == {"mem_only"}, res.get("briefs")
