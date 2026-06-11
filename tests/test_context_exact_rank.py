"""Focused tests for `_floor_exact_defs` — the content-rank fix that lifts an
exact-symbol DEFINITION above fuzzy body mentions.

Regression target: `rmx context "set_flag_by_selector"` surfaced the real
`def set_flag_by_selector` (store.py) at weight 0, ranked last under callers,
because the ref resolved to a learned `query/<ref>` concept whose `mentions`
edges carry tf=0 → BM25 score 0. The def — the most-relevant hit — landed in
the least-useful slot and rendered as `w=0`. These tests pin the floor without
any DB plumbing (pure list-of-entries logic)."""
from __future__ import annotations

from refmatrix.context import ContextEntry, _floor_exact_defs
from refmatrix.store import Entity


def _entry(name: str, snippet: str, weight: float) -> ContextEntry:
    ent = Entity(id=1, kind="code", name=name, path=name, tldr=None, meta={})
    e = ContextEntry(entity=ent, linkage="content", weight=weight)
    e.snippet = snippet
    return e


def test_exact_def_floored_above_fuzzy():
    """A zero-scored def must outrank a positively-scored fuzzy mention."""
    fuzzy = _entry("daemon.py", "    r = store.set_flag_by_selector(f, v)", 5.0)
    exact = _entry("store.py", "def set_flag_by_selector(self, flag, value):", 0.0)
    entries = [fuzzy, exact]
    _floor_exact_defs(entries, "set_flag_by_selector")
    assert entries[0] is exact                       # def leads
    assert (entries[0].weight or 0) > (fuzzy.weight or 0)   # above fuzzy


def test_exact_def_no_longer_renders_zero():
    """Even when every content hit scores 0, the def gets a non-zero weight."""
    caller = _entry("cli.py", "    store.set_flag_by_selector(f, v)", 0.0)
    exact = _entry("store.py", "def set_flag_by_selector(self):", 0.0)
    entries = [caller, exact]
    _floor_exact_defs(entries, "set_flag_by_selector")
    assert entries[0] is exact
    assert entries[0].weight and entries[0].weight > 0


def test_caller_line_is_not_treated_as_a_definition():
    """A call site (no def/class/etc. keyword) must NOT be boosted."""
    caller = _entry("cli.py", "    x = set_flag_by_selector(1)", 0.0)
    entries = [caller]
    _floor_exact_defs(entries, "set_flag_by_selector")
    assert caller.weight == 0.0                       # untouched


def test_class_and_arrow_defs_detected():
    """class <sym> and `const <sym> =` (JS/TS) count as definitions."""
    cls = _entry("m.py", "class FovWedge:  # impl", 0.0)
    entries = [_entry("o.py", "use(FovWedge())", 2.0), cls]
    _floor_exact_defs(entries, "FovWedge")
    assert entries[0] is cls

    arrow = _entry("a.ts", "const computeFov = (x) => x * 2", 0.0)
    entries2 = [_entry("b.ts", "computeFov(1)", 3.0), arrow]
    _floor_exact_defs(entries2, "computeFov")
    assert entries2[0] is arrow


def test_floor_is_noop_for_nl_phrase():
    """A multi-token NL phrase has no single symbol — order is preserved and
    no entry is boosted (so `context "fov wedge"` ranks exactly as content_rank
    returned it)."""
    a = _entry("a.py", "def get(self): ...", 3.0)
    b = _entry("b.py", "x = 1", 1.0)
    entries = [a, b]
    _floor_exact_defs(entries, "fov wedge")
    assert entries == [a, b]                           # untouched
    assert a.weight == 3.0 and b.weight == 1.0


def test_floor_is_noop_when_no_hit_defines_ref():
    """Single-identifier ref but no def present: nothing boosted; the
    pre-existing (content_rank) order is left intact."""
    a = _entry("a.py", "    foo()", 4.0)
    b = _entry("b.py", "    foo()", 2.0)
    entries = [a, b]
    _floor_exact_defs(entries, "foo")
    assert entries == [a, b]
    assert a.weight == 4.0 and b.weight == 2.0
