"""TS extractor smoke tests. Mirrors test_js_extract.py shape.

Locks in TS-specific surface: generics, type-annotation stripping on params,
decorators, interfaces, type aliases, enums, class methods captured as
defines (the gap the JS-only cut left open), and dispatcher routing for
typescript/tsx.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def ts():
    eval_dir = Path(__file__).resolve().parents[1] / "eval"
    sys.path.insert(0, str(eval_dir))
    try:
        from retrievers.rmx_retriever import (
            extract_for_lang,
            js_extract,
            ts_extract,
        )
    finally:
        sys.path.pop(0)
    return ts_extract, extract_for_lang, js_extract


def test_classic_function_with_types(ts):
    ts_extract, _, _ = ts
    out = ts_extract("""
/**
 * Parses an integer.
 */
function parseIntSafe(text: string, radix: number): number {
  return parseInt(text, radix);
}
""")
    assert "parseIntSafe" in out["defines"].split()
    assert out["params"].split() == ["text", "radix"]
    assert "parseInt" in out["calls"]
    assert "Parses an integer." in out["docstring"]


def test_generics_after_function_name(ts):
    ts_extract, _, _ = ts
    out = ts_extract("function map<T, U>(xs: T[], fn: (x: T) => U): U[] { return xs.map(fn); }")
    assert "map" in out["defines"].split()
    # `(x: T) => U` shows up as a nested paren block — the outer match
    # captures the params up to the first `)`; that yields `xs` and `fn`.
    assert "xs" in out["params"].split()
    assert "fn" in out["params"].split()


def test_arrow_function_with_return_type(ts):
    ts_extract, _, _ = ts
    out = ts_extract("/** sum */\nconst add = (a: number, b: number): number => a + b;")
    assert "add" in out["defines"].split()
    assert out["params"].split() == ["a", "b"]


def test_arrow_with_generic_prefix(ts):
    ts_extract, _, _ = ts
    out = ts_extract("const identity = <T>(x: T): T => x;")
    assert "identity" in out["defines"].split()
    assert "x" in out["params"].split()


def test_optional_default_rest_params(ts):
    ts_extract, _, _ = ts
    out = ts_extract(
        "function build(name: string, count: number = 3, kind?: string, ...tags: string[]) {}"
    )
    names = out["params"].split()
    assert names == ["name", "count", "kind", "tags"]


def test_interface_and_type_alias(ts):
    ts_extract, _, _ = ts
    out = ts_extract("""
/** Point in 2D. */
interface Point {
  x: number;
  y: number;
}
type Vec<T> = T[];
""")
    defs = out["defines"].split()
    assert "Point" in defs
    assert "Vec" in defs
    assert "Point in 2D." in out["docstring"]


def test_enum_captured(ts):
    ts_extract, _, _ = ts
    out = ts_extract("enum Color { Red, Green, Blue }")
    assert "Color" in out["defines"].split()


def test_decorator_does_not_shadow_class(ts):
    ts_extract, _, _ = ts
    out = ts_extract("""
@Component({ selector: 'x-foo' })
@Injectable()
export class XFoo {
  greet(name: string): string { return 'hi ' + name; }
}
""")
    defs = out["defines"].split()
    assert "XFoo" in defs
    assert "greet" in defs
    assert "name" in out["params"].split()


def test_class_method_captured_as_defines(ts):
    """The exact gap the JS-only cut left open: class methods landing in
    calls instead of defines. ts_extract must put them in defines."""
    ts_extract, _, _ = ts
    out = ts_extract("""
class Repo {
  find(id: string): Item | null { return null; }
  save(item: Item): void {}
}
""")
    defs = out["defines"].split()
    assert "Repo" in defs
    assert "find" in defs
    assert "save" in defs


def test_constructor_skipped_from_defines_but_params_kept(ts):
    ts_extract, _, _ = ts
    out = ts_extract("""
class User {
  constructor(public name: string, private age: number) {}
}
""")
    defs = out["defines"].split()
    assert "User" in defs
    assert "constructor" not in defs
    pms = out["params"].split()
    assert "name" in pms and "age" in pms


def test_destructured_params(ts):
    ts_extract, _, _ = ts
    out = ts_extract("function point({ x, y }: { x: number; y: number }) { return x + y; }")
    pms = out["params"].split()
    assert "x" in pms and "y" in pms


def test_no_jsdoc_keeps_full_body_as_code(ts):
    ts_extract, _, _ = ts
    src = "function add(a: number, b: number): number { return a + b; }"
    out = ts_extract(src)
    assert out["docstring"] == ""
    assert out["code"] == src


def test_dispatcher_routes_typescript_to_ts_extract(ts):
    ts_extract, extract_for_lang, js_extract = ts
    src = "function build<T>(x: T): T { return x; }"
    ts_out = extract_for_lang(src, "typescript")
    assert "build" in ts_out["defines"].split()
    # tsx routes the same way.
    tsx_out = extract_for_lang(src, "tsx")
    assert "build" in tsx_out["defines"].split()
    # Plain JS regex doesn't understand generics — confirms the TS path is
    # actually doing extra work and the dispatcher is picking the right one.
    js_out = extract_for_lang(src, "javascript")
    assert "build" not in js_out["defines"].split()


def test_js_class_method_now_in_defines(ts):
    """Verify the JS-side gap is also closed (shared method regex)."""
    _, _, js_extract = ts
    out = js_extract("""
class Repo {
  /** lookup */
  find(id) { return null; }
}
""")
    defs = out["defines"].split()
    assert "Repo" in defs
    assert "find" in defs
