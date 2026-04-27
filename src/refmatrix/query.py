"""
Query engine. Two surfaces:

1. DSL — infix set algebra over `linkage:concept` terms.
     mentions:parser AND defines:parser
     calls:foo OR (mentions:bar AND NOT imports:legacy)

2. PQL — Pilosa-style functional ops:
     Row(linkage, concept)             -> bitmap of entity ids
     Intersect(Row(...), Row(...))
     Union(Row(...), Row(...))
     Difference(A, B)                  -> A AND NOT B
     Xor(A, B)
     TopN(<bitmap-expr>, n)            -> top entities by co-occurrence weight
     Neighbors(concept, depth=1, linkages=[...])

Both surfaces compile to a tree of operations that produce a BitMap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from pyroaring import BitMap

from refmatrix.store import Store


# ----------------------------- DSL parser ----------------------------------

_TOKEN_RE = re.compile(
    r"\s*(?:"
    r"(?P<lparen>\()|"
    r"(?P<rparen>\))|"
    r"(?P<and>\bAND\b|&&)|"
    r"(?P<or>\bOR\b|\|\|)|"
    r"(?P<not>\bNOT\b|!)|"
    r"(?P<term>[A-Za-z_][\w\-./]*(?::[\w\-./@]+)?)"
    r")",
    re.IGNORECASE,
)


@dataclass
class Token:
    kind: str
    text: str


def _tokenize(s: str) -> list[Token]:
    pos = 0
    out: list[Token] = []
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            if s[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"unexpected char at {pos}: {s[pos]!r}")
        for kind, val in m.groupdict().items():
            if val is not None:
                out.append(Token(kind, val))
                break
        pos = m.end()
    return out


class _Parser:
    """Recursive-descent: expr := or; or := and (OR and)*; and := not (AND not)*; not := NOT? atom; atom := TERM | (expr)."""

    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0

    def _peek(self) -> Token | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _eat(self, kind: str) -> Token:
        t = self._peek()
        if t is None or t.kind != kind:
            raise ValueError(f"expected {kind}, got {t}")
        self.i += 1
        return t

    def parse(self) -> "Node":
        node = self._or()
        if self._peek() is not None:
            raise ValueError(f"trailing tokens: {self.toks[self.i:]}")
        return node

    def _or(self) -> "Node":
        left = self._and()
        while (t := self._peek()) and t.kind == "or":
            self.i += 1
            right = self._and()
            left = Op("or", [left, right])
        return left

    def _and(self) -> "Node":
        left = self._not()
        while (t := self._peek()) and t.kind == "and":
            self.i += 1
            right = self._not()
            left = Op("and", [left, right])
        return left

    def _not(self) -> "Node":
        if (t := self._peek()) and t.kind == "not":
            self.i += 1
            return Op("not", [self._atom()])
        return self._atom()

    def _atom(self) -> "Node":
        t = self._peek()
        if t is None:
            raise ValueError("unexpected end of input")
        if t.kind == "lparen":
            self.i += 1
            node = self._or()
            self._eat("rparen")
            return node
        if t.kind == "term":
            self.i += 1
            return Term(t.text)
        raise ValueError(f"unexpected token {t}")


# ----------------------------- AST ----------------------------------------


@dataclass
class Node:
    pass


@dataclass
class Term(Node):
    """A term is either `linkage:concept` or just `concept` (defaults to all linkages OR'd)."""
    text: str


@dataclass
class Op(Node):
    op: str  # 'and' | 'or' | 'not' | 'diff' | 'xor'
    args: list[Node]


# ----------------------------- engine -------------------------------------


class QueryEngine:
    def __init__(self, store: Store, include_noise: bool = False):
        self.s = store
        # When False (default), enumeration paths (neighbors, co_occurrence,
        # topn, density) skip concepts marked noise. Explicit name lookups via
        # _row() always resolve — typing the name is intent enough.
        self.include_noise = include_noise
        self._noise_cache: set[int] | None = None

    def _noise_ids(self) -> set[int]:
        if self.include_noise:
            return set()
        if self._noise_cache is None:
            self._noise_cache = self.s.noise_concept_ids()
        return self._noise_cache

    # --- DSL entry point ---
    def run(self, dsl: str) -> BitMap:
        ast = _Parser(_tokenize(dsl)).parse()
        return self._eval(ast)

    # --- PQL entry point ---
    def run_pql(self, pql: str) -> BitMap | list:
        return _PQLEvaluator(self).eval(pql.strip())

    # --- core ---
    def _eval(self, node: Node) -> BitMap:
        if isinstance(node, Term):
            return self._term_bitmap(node.text)
        if isinstance(node, Op):
            if node.op == "and":
                a, b = self._eval(node.args[0]), self._eval(node.args[1])
                return a & b
            if node.op == "or":
                a, b = self._eval(node.args[0]), self._eval(node.args[1])
                return a | b
            if node.op == "not":
                inner = self._eval(node.args[0])
                return self._universe() - inner
            if node.op == "diff":
                a, b = self._eval(node.args[0]), self._eval(node.args[1])
                return a - b
            if node.op == "xor":
                a, b = self._eval(node.args[0]), self._eval(node.args[1])
                return a ^ b
        raise ValueError(f"bad node: {node}")

    def _universe(self) -> BitMap:
        bm = BitMap()
        for r in self.s._connect().execute("SELECT id FROM entities"):
            bm.add(r[0])
        return bm

    def _term_bitmap(self, text: str) -> BitMap:
        if ":" in text:
            linkage, concept_name = text.split(":", 1)
            return self._row(linkage, concept_name)
        # bare concept => union of every linkage row for that concept
        c = self.s.resolve_entity(text)
        if c is None or c.kind != "concept":
            return BitMap()
        out = BitMap()
        for lk in self.s.list_linkages():
            out |= self.s.load_bitmap(lk["name"], c.id)
        return out

    def _row(self, linkage: str, concept_name: str) -> BitMap:
        c = self.s.resolve_entity(concept_name)
        if c is None or c.kind != "concept":
            # auto-create-on-read? no — return empty so queries don't surprise.
            return BitMap()
        return self.s.load_bitmap(linkage, c.id)

    # --- higher-level ops ---

    def neighbors(
        self,
        concept_name: str,
        depth: int = 1,
        linkages: list[str] | None = None,
    ) -> BitMap:
        c = self.s.resolve_entity(concept_name)
        if c is None or c.kind != "concept":
            return BitMap()
        link_names = linkages or [lk["name"] for lk in self.s.list_linkages()]
        noise = self._noise_ids()
        frontier = BitMap([c.id])
        seen = BitMap([c.id])
        for _ in range(depth):
            next_frontier = BitMap()
            for cid in frontier:
                for ln in link_names:
                    next_frontier |= self.s.load_bitmap(ln, cid)
            next_frontier -= seen
            if noise:
                next_frontier -= BitMap(noise)
            if len(next_frontier) == 0:
                break
            seen |= next_frontier
            frontier = next_frontier
        seen.discard(c.id)
        return seen

    def topn(self, bm: BitMap, n: int = 10) -> list[tuple[int, int]]:
        """Top-N entities in `bm` ranked by co-occurrence count across all linkages."""
        noise = self._noise_ids()
        weights: dict[int, int] = {}
        for lk in self.s.list_linkages():
            for cid in self.s.iter_concept_ids_for_linkage(lk["name"]):
                if cid in noise:
                    continue
                row = self.s.load_bitmap(lk["name"], cid)
                hit = row & bm
                for eid in hit:
                    weights[eid] = weights.get(eid, 0) + 1
        ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:n]

    def co_occurrence(self, concept_name: str, linkage: str = "mentions") -> list[tuple[str, int]]:
        """Concepts that share entities with `concept_name` under `linkage`."""
        c = self.s.resolve_entity(concept_name)
        if c is None:
            return []
        anchor = self.s.load_bitmap(linkage, c.id)
        if len(anchor) == 0:
            return []
        noise = self._noise_ids()
        out: list[tuple[str, int]] = []
        for cid in self.s.iter_concept_ids_for_linkage(linkage):
            if cid == c.id or cid in noise:
                continue
            other = self.s.load_bitmap(linkage, cid)
            overlap = len(anchor & other)
            if overlap > 0:
                e = self.s.get_entity_by_id(cid)
                if e:
                    out.append((e.name, overlap))
        out.sort(key=lambda kv: (-kv[1], kv[0]))
        return out


# ----------------------------- PQL --------------------------------------


_PQL_TOK = re.compile(
    r"\s*(?:"
    r"(?P<name>[A-Za-z_][\w]*)|"
    r"(?P<num>-?\d+)|"
    r"(?P<str>\"[^\"]*\"|'[^']*')|"
    r"(?P<lp>\()|(?P<rp>\))|(?P<comma>,)"
    r")"
)


class _PQLEvaluator:
    def __init__(self, qe: QueryEngine):
        self.qe = qe

    def eval(self, src: str):
        toks = self._tokenize(src)
        result, end = self._parse(toks, 0)
        if end != len(toks):
            raise ValueError(f"trailing PQL tokens at {end}")
        return result

    @staticmethod
    def _tokenize(src: str) -> list[tuple[str, str]]:
        out, pos = [], 0
        while pos < len(src):
            m = _PQL_TOK.match(src, pos)
            if not m:
                if src[pos].isspace():
                    pos += 1
                    continue
                raise ValueError(f"PQL: bad char {src[pos]!r}")
            for k, v in m.groupdict().items():
                if v is not None:
                    out.append((k, v))
                    break
            pos = m.end()
        return out

    def _parse(self, toks, i):
        kind, val = toks[i]
        if kind != "name":
            raise ValueError(f"PQL: expected fn name at {i}, got {kind}:{val}")
        fn = val
        if i + 1 >= len(toks) or toks[i + 1][0] != "lp":
            # bare identifier — treat as concept name
            return fn, i + 1
        args = []
        j = i + 2
        if toks[j][0] == "rp":
            return self._call(fn, args), j + 1
        while True:
            kind2, val2 = toks[j]
            if kind2 == "name" and j + 1 < len(toks) and toks[j + 1][0] == "lp":
                a, j = self._parse(toks, j)
                args.append(a)
            elif kind2 == "name":
                args.append(val2)
                j += 1
            elif kind2 == "num":
                args.append(int(val2))
                j += 1
            elif kind2 == "str":
                args.append(val2[1:-1])
                j += 1
            else:
                raise ValueError(f"PQL: bad arg {kind2}:{val2}")
            if toks[j][0] == "comma":
                j += 1
                continue
            if toks[j][0] == "rp":
                return self._call(fn, args), j + 1
            raise ValueError(f"PQL: expected , or ) at {j}")

    def _call(self, fn: str, args: list):
        f = fn.lower()
        if f == "row":
            linkage, concept = args
            return self.qe._row(linkage, concept)
        if f in ("intersect", "and"):
            it = iter(args)
            res = next(it)
            for a in it:
                res = res & a
            return res
        if f in ("union", "or"):
            it = iter(args)
            res = next(it)
            for a in it:
                res = res | a
            return res
        if f in ("difference", "diff"):
            return args[0] - args[1]
        if f == "xor":
            return args[0] ^ args[1]
        if f == "topn":
            bm, n = args[0], (args[1] if len(args) > 1 else 10)
            return self.qe.topn(bm, n)
        if f == "neighbors":
            concept = args[0]
            depth = args[1] if len(args) > 1 else 1
            return self.qe.neighbors(concept, depth)
        if f == "count":
            return len(args[0])
        raise ValueError(f"PQL: unknown function {fn}")
