"""Briefs — what the corpus knows solidly, and where it is thin.

`rmx memory compile` (consolidate.py) groups the corpus into subjects and says
what the store HAS. Nothing said what it LACKS, and that blind spot is the shape
of every coverage failure this project shipped: 43-83% of entities carrying no
terms at all (the main ingest path indexed nothing, 2026-09-03, which
invalidated eight experiments); 179 docs stranded by an mtime gate keyed on
input identity rather than on input-plus-code; a helix log so thoroughly
self-suppressed that a near-empty file was almost read as evidence of absent
demand. In every case the store answered queries. It just answered them thinly,
and nothing inside it could say so.

A **brief** is a derived `kind=memory` row in the `brief/<class>` namespace,
produced by a detector over signal THAT ALREADY EXISTS in the store — a compile
plan, a degree count, a typed edge. Three rules keep it a diagnostic instead of
a plausible-sentence generator:

  1. **Evidence or nothing.** Every brief carries entity ids a reader can
     resolve back to rows. `Brief.__post_init__` refuses an empty list, so a
     detector that cannot point at anything cannot emit.
  2. **No model.** Detectors are deterministic and their thresholds are named
     parameters. There is no LLM call anywhere in this module and no
     summarization step; the `finding` line states the measurement.
  3. **Counted skips.** A row that cannot be read is counted and returned, never
     quietly dropped — `feedback_no_silent_failures` governs anything between a
     memory and the store, and a detector is on that path.

Exclusions are IMPORTED from consolidate rather than redeclared. Operational
rows (`session/*`, `digest/*`) are per-session artifacts, not knowledge, and
they are numerous enough to dominate every class. The same junk-token bug
appeared at four separate call sites in this codebase because each one grew its
own copy of the list; one definition, imported, is the fix that stuck.
"""
from __future__ import annotations

import fnmatch
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from refmatrix.consolidate import DEFAULT_EXCLUDE_MTYPES, _OPERATIONAL_RE
from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK

if TYPE_CHECKING:
    from refmatrix.store import Store

# One definition, imported by identity. A test asserts the `is` relationship
# precisely so a future copy-paste shows up as a failure rather than as drift.
EXCLUDE_MTYPES = DEFAULT_EXCLUDE_MTYPES
OPERATIONAL_RE = _OPERATIONAL_RE

MTYPE_PREFIX = "brief"

# Defaults, stated once. Every detector takes them as parameters; none of them
# is buried as a literal in a comparison.
MIN_MEMBERS = 3          # corroborated: members in the subject
MIN_DATES = 3            # corroborated: distinct days those members were written
MIN_MENTIONS = 4         # orphan-concept: how much talk counts as "talked about"
MAX_EVIDENCE = 12        # evidence lists are for a reader, not an export


@dataclass
class Brief:
    """One derived observation about the corpus's own coverage.

    `evidence` is the whole contract. A brief that cannot name the rows it was
    derived from is indistinguishable from a guess, so construction fails
    rather than producing one.
    """
    cls: str
    label: str
    finding: str
    evidence: list[int] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.evidence = [int(e) for e in self.evidence]
        if not self.evidence:
            raise ValueError(
                f"brief {self.cls}/{self.label!r} has no evidence; a brief that "
                f"cannot point at a row is a guess, not a finding")

    @property
    def mtype(self) -> str:
        return f"{MTYPE_PREFIX}/{self.cls}"

    def as_dict(self) -> dict:
        return {"class": self.cls, "label": self.label, "finding": self.finding,
                "evidence": list(self.evidence), "detail": dict(self.detail),
                "mtype": self.mtype}


# ── helpers ────────────────────────────────────────────────────────────────

def _excluded_mtype(mtype: "str | None", patterns: Iterable[str] = ()) -> bool:
    pats = list(patterns) or list(EXCLUDE_MTYPES)
    m = mtype or ""
    return any(fnmatch.fnmatch(m, p) for p in pats)


def _memory_ids(store: "Store") -> dict[int, dict]:
    """Non-operational memory rows of the active partition, by id.

    Same filter as `consolidate._memory_rows` — mtype globs plus the
    operational name regex — because a brief over rows compile ignored would
    describe a corpus nobody else can see.
    """
    store._connect()
    rows = store._read().execute(
        "SELECT e.id, e.name, mc.mtype FROM entities e "
        "JOIN memory_content mc ON mc.entity_id = e.id "
        "WHERE e.partition_id=? AND e.kind='memory' ORDER BY e.id",
        (store._partition_id,),
    ).fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        name, mtype = str(r[1]), (r[2] or "")
        if _excluded_mtype(mtype) or OPERATIONAL_RE.match(name):
            continue
        out[int(r[0])] = {"id": int(r[0]), "name": name, "mtype": mtype}
    return out


def _pairs(store: "Store", linkage: str) -> set[tuple[int, int]]:
    """Decode a linkage fragment into (left, right) entity-id pairs.

    Cells are packed `left<<32 | right`, the same layout `pagerank` and
    `consolidate` decode. A missing fragment is an empty set, not an error: a
    store with no `contradicts` edges is the normal case, not a fault.
    """
    try:
        frag = store._load_fragment(linkage)
    except Exception:
        return set()
    if frag is None:
        return set()
    return {(int(p >> _CONCEPT_SHIFT), int(p & _ENTITY_MASK)) for p in frag}


def _day(ts: float) -> int:
    return int(float(ts) // 86400)


def memory_dates(store: "Store", ids: Iterable[int]) -> dict[int, float]:
    """`entities.created_at` for the given ids — the corroboration clock."""
    ids = list(ids)
    if not ids:
        return {}
    out: dict[int, float] = {}
    con = store._read()
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        ph = ",".join("?" * len(chunk))
        for r in con.execute(
            f"SELECT id, created_at FROM entities WHERE id IN ({ph})", chunk,
        ).fetchall():
            out[int(r[0])] = float(r[1] or 0.0)
    return out


# ── detectors ──────────────────────────────────────────────────────────────

def corroborated(plan: dict, *, dates: dict[int, float],
                 min_members: int = MIN_MEMBERS,
                 min_dates: int = MIN_DATES) -> list[Brief]:
    """Subjects the corpus arrived at more than once, on more than one day.

    Size alone is not corroboration. Four memories written in one sitting are
    one observation recorded four times — the writer's mood, not the corpus's
    agreement. Requiring distinct DAYS is what separates "this keeps coming
    back" from "this was on my mind that afternoon".
    """
    out: list[Brief] = []
    for cluster in plan.get("clusters") or []:
        members = [int(m["id"]) for m in cluster.get("members") or []]
        if len(members) < min_members:
            continue
        days = {_day(dates[m]) for m in members if m in dates}
        if len(days) < min_dates:
            continue
        out.append(Brief(
            cls="corroborated", label=str(cluster.get("label") or "unlabeled"),
            finding=(f"{len(members)} memories across {len(days)} distinct days "
                     f"converge on this subject"),
            evidence=members[:MAX_EVIDENCE],
            detail={"members": len(members), "days": len(days)}))
    return out


def singleton(plan: dict, *, name_to_id: dict[str, int],
              count_skips: bool = False):
    """Memories that joined no subject — a topic the corpus touched once.

    These are the compile plan's `unclustered` list, not clusters of size one:
    `compile_memories` enforces `min_size` and a lone memory never becomes a
    cluster at all. A singleton is not automatically a problem; it is a place
    the corpus has one data point and is about to be asked for a pattern.
    """
    out: list[Brief] = []
    skipped = 0
    for name in plan.get("unclustered") or []:
        eid = name_to_id.get(name)
        if eid is None:
            # Emitting here would mean a brief with no evidence. Count it.
            skipped += 1
            continue
        out.append(Brief(
            cls="singleton", label=str(name),
            finding="joined no subject; the corpus touched this once",
            evidence=[int(eid)]))
    return (out, skipped) if count_skips else out


def contradicted(store: "Store", *, rows: "dict[int, dict] | None" = None,
                 count_skips: bool = False):
    """`contradicts` edges where neither side was ever superseded.

    A contradiction someone already resolved is history — the `supersedes` edge
    IS the resolution, and re-reporting it would train a reader to ignore the
    class. What survives is a pair the corpus still disagrees with itself about.
    """
    rows = _memory_ids(store) if rows is None else rows
    contradicts = _pairs(store, "contradicts")
    supersedes = _pairs(store, "supersedes")
    out: list[Brief] = []
    skipped = 0
    seen: set[tuple[int, int]] = set()
    for a, b in sorted(contradicts):
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        seen.add(key)
        if a not in rows or b not in rows:
            # Either side operational, excluded, or from another partition.
            skipped += 1
            continue
        if (a, b) in supersedes or (b, a) in supersedes:
            continue
        out.append(Brief(
            cls="contradicted",
            label=f"{rows[a]['name']} vs {rows[b]['name']}",
            finding="two memories contradict and neither supersedes the other",
            evidence=[a, b]))
    return (out, skipped) if count_skips else out


def orphan_concept(store: "Store", *, min_mentions: int = MIN_MENTIONS,
                   rows: "dict[int, dict] | None" = None) -> list[Brief]:
    """Concepts the corpus talks about but never pins down.

    `mentions` degree high, `defines` and `lead` degree zero: a term that shows
    up everywhere and is anchored nowhere. This is the class that catches a
    vocabulary drifting — the point where two memories using the same word have
    no shared definition to disagree with.
    """
    rows = _memory_ids(store) if rows is None else rows
    df: Counter = Counter()
    mentioners: dict[int, list[int]] = defaultdict(list)
    for cid, eid in _pairs(store, "mentions"):
        if eid not in rows:
            continue
        df[cid] += 1
        mentioners[cid].append(eid)

    anchored = {cid for cid, _ in _pairs(store, "defines")}
    anchored |= {cid for cid, _ in _pairs(store, "lead")}

    candidates = sorted(c for c, n in df.items()
                        if n >= min_mentions and c not in anchored)
    if not candidates:
        return []

    names: dict[int, str] = {}
    con = store._read()
    for start in range(0, len(candidates), 500):
        chunk = candidates[start:start + 500]
        ph = ",".join("?" * len(chunk))
        for r in con.execute(
            f"SELECT id, name FROM entities WHERE id IN ({ph})", chunk,
        ).fetchall():
            names[int(r[0])] = str(r[1])

    out: list[Brief] = []
    for cid in candidates:
        name = names.get(cid)
        if not name or OPERATIONAL_RE.match(name):
            continue
        out.append(Brief(
            cls="orphan-concept", label=name,
            finding=(f"mentioned by {df[cid]} memories; nothing defines or "
                     f"leads with it"),
            evidence=sorted(mentioners[cid])[:MAX_EVIDENCE],
            detail={"mentions": df[cid]}))
    return out


# ── the run ────────────────────────────────────────────────────────────────

def compile_briefs(store: "Store", *, plan: "dict | None" = None,
                   min_members: int = MIN_MEMBERS,
                   min_dates: int = MIN_DATES,
                   min_mentions: int = MIN_MENTIONS,
                   classes: "Iterable[str] | None" = None) -> dict:
    """Run every detector over the active partition. Returns briefs + stats.

    `plan` is an already-computed `memory compile` plan; when absent the two
    plan-derived classes are skipped rather than silently recomputing a cluster
    pass that costs vectors and minutes. That is a deliberate asymmetry — the
    cheap classes should never be gated behind the expensive one.
    """
    wanted = set(classes) if classes else {
        "corroborated", "singleton", "contradicted", "orphan-concept"}
    rows = _memory_ids(store)
    briefs: list[Brief] = []
    skipped = 0
    ran: list[str] = []
    not_run: dict[str, str] = {}

    if "corroborated" in wanted or "singleton" in wanted:
        if plan is None:
            for c in ("corroborated", "singleton"):
                if c in wanted:
                    not_run[c] = ("needs a `memory compile` plan; pass plan= "
                                  "or run `rmx memory compile` first")
        else:
            if "corroborated" in wanted:
                dates = memory_dates(store, rows)
                briefs += corroborated(plan, dates=dates,
                                       min_members=min_members,
                                       min_dates=min_dates)
                ran.append("corroborated")
            if "singleton" in wanted:
                name_to_id = {r["name"]: r["id"] for r in rows.values()}
                got, sk = singleton(plan, name_to_id=name_to_id,
                                    count_skips=True)
                briefs += got
                skipped += sk
                ran.append("singleton")

    if "contradicted" in wanted:
        got, sk = contradicted(store, rows=rows, count_skips=True)
        briefs += got
        skipped += sk
        ran.append("contradicted")

    if "orphan-concept" in wanted:
        briefs += orphan_concept(store, min_mentions=min_mentions, rows=rows)
        ran.append("orphan-concept")

    return {
        "briefs": briefs,
        "stats": {
            "memories": len(rows),
            "briefs": len(briefs),
            "skipped": skipped,
            "by_class": dict(Counter(b.cls for b in briefs)),
            "classes_run": ran,
            "classes_not_run": not_run,
            "partition": store._partition_name,
        },
        "params": {"min_members": min_members, "min_dates": min_dates,
                   "min_mentions": min_mentions},
    }
