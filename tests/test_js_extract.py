"""JS extractor smoke tests for the eval-time per-language dispatcher.

Lives under tests/ (not eval/) so it runs in the main pytest sweep. The
extractor is regex-first cut; these tests lock in the basics it must get
right before we run the csn_javascript eval."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def js():
    eval_dir = Path(__file__).resolve().parents[1] / "eval"
    sys.path.insert(0, str(eval_dir))
    try:
        from retrievers.rmx_retriever import (
            extract_for_lang,
            js_extract,
        )
    finally:
        sys.path.pop(0)
    return js_extract, extract_for_lang


def test_classic_function(js):
    js_extract, _ = js
    out = js_extract("""
/**
 * Parses an integer.
 */
function parseIntSafe(text, radix) {
  return parseInt(text, radix);
}
""")
    assert out["defines"] == "parseIntSafe"
    assert out["params"] == "text radix"
    assert "parseInt" in out["calls"]
    assert "Parses an integer." in out["docstring"]


def test_arrow_function(js):
    js_extract, _ = js
    out = js_extract("/** sum */\nconst add = (a, b) => a + b;")
    assert out["defines"] == "add"
    assert out["params"] == "a b"


def test_class_name_captured(js):
    js_extract, _ = js
    out = js_extract("""
/** A point. */
class Point {
  constructor(x, y) { this.x = x; this.y = y; }
}
""")
    assert "Point" in out["defines"]
    assert "A point." in out["docstring"]


def test_object_literal_method(js):
    js_extract, _ = js
    out = js_extract("""
const api = {
  /** load */
  load: function(url, headers) { return fetch(url); }
};
""")
    assert "load" in out["defines"]
    assert "url" in out["params"] and "headers" in out["params"]


def test_async_function(js):
    js_extract, _ = js
    out = js_extract("""
/** read */
async function readFile(path) {
  return await fs.readFile(path, 'utf-8');
}
""")
    assert "readFile" in out["defines"]
    assert "path" in out["params"]


def test_no_jsdoc_keeps_full_body_as_code(js):
    js_extract, _ = js
    src = "function add(a, b) { return a + b; }"
    out = js_extract(src)
    assert out["docstring"] == ""
    assert out["code"] == src


def test_params_not_polluted_by_subsequent_if_paren(js):
    """The first-cut bug: param extractor saw `if (typeof ...)` as the param
    list. Lock in that we read the param list of the declared function."""
    js_extract, _ = js
    out = js_extract("""
function f(a, b) {
  if (typeof a === 'string') return b;
}
""")
    assert out["params"] == "a b"


def test_dispatcher_routes_by_lang(js):
    _, extract_for_lang = js
    py = extract_for_lang("def add(a, b):\n    '''d'''\n    return a + b\n", "python")
    js_out = extract_for_lang("/** d */\nfunction add(a, b) { return a + b; }", "javascript")
    assert "add" in py["defines"]
    assert "add" in js_out["defines"]
