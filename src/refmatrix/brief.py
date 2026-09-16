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
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from refmatrix.consolidate import DEFAULT_EXCLUDE_MTYPES, _OPERATIONAL_RE
from refmatrix.store import _CONCEPT_SHIFT, _ENTITY_MASK
from refmatrix.terms import STOPWORDS as _SHARED_STOPWORDS

if TYPE_CHECKING:
    from refmatrix.store import Store

# One definition, imported by identity. A test asserts the `is` relationship
# precisely so a future copy-paste shows up as a failure rather than as drift.
# `brief/*` excludes ITS OWN OUTPUT. `--save` writes one memory row per brief;
# without this the tool reports the rows it wrote 30 seconds earlier as a
# coverage gap, and `memory compile` folds derived prose back into subject
# clustering and thence into the scan-prompt hook (ch-bsd r1 #b-4).
EXCLUDE_MTYPES = tuple(DEFAULT_EXCLUDE_MTYPES) + ("brief", "brief/*")
OPERATIONAL_RE = _OPERATIONAL_RE

# ONE definition, imported. This module's docstring has always said so, and
# shipped without it anyway: the top `orphan-concept` brief on the live replica
# was the word `the` (ch-bsd r1 #b-3). That is the SIXTH site of the bug
# `feedback_reuse_shared_stoplist` records. Identity-asserted by test.
STOPWORDS = _SHARED_STOPWORDS

# A memory's own id is not a concept. `project_daemon_sigabrt_diagnosed`
# surfaced as an "orphan concept" on the live replica because it is a node the
# bridge created for the FILE, mentioned by the memories that cite it.
_MEMORY_ID_RE = re.compile(
    r"^(project|feedback|reference|impression|guardrail|savestate|task|plan|bsd|impl)[-_]")

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

    ENDPOINTS ARE NOT ALWAYS MEMORY ROWS. This shipped requiring both sides in
    `_memory_ids()` (`kind='memory'`), and on the live replica 54 of 59
    `contradicts` endpoints are CONCEPT nodes — GMD `rel:` edges land on the
    `#anchor` node, which `project_context_nl_ref_fixes` already recorded. The
    class scored 0 on 41 real pairs while the CLI blamed "unresolvable ids",
    which was the wrong diagnosis: they resolved fine, they were the wrong kind
    (ch-bsd r1 #b-2). Any endpoint that resolves to an entity now counts; only
    a genuinely unresolvable id is a skip.
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
        ra, rb = _endpoint(store, a, rows), _endpoint(store, b, rows)
        if ra is None or rb is None:
            # A genuinely unresolvable id — not merely a non-memory kind.
            skipped += 1
            continue
        if OPERATIONAL_RE.match(ra) or OPERATIONAL_RE.match(rb):
            skipped += 1
            continue
        if (a, b) in supersedes or (b, a) in supersedes:
            continue
        out.append(Brief(
            cls="contradicted",
            label=f"{ra} vs {rb}",
            finding="two memories contradict and neither supersedes the other",
            evidence=[a, b]))
    return (out, skipped) if count_skips else out


def _endpoint(store: "Store", eid: int,
              rows: dict[int, dict]) -> "str | None":
    """Name for a `contradicts` endpoint — memory row OR any other entity.

    Memory rows come from the pre-filtered map (so mtype exclusions still
    apply); anything else is looked up directly, because a GMD `rel:` edge
    lands on a concept `#anchor` node and that is the normal case here.
    """
    row = rows.get(eid)
    if row is not None:
        return row["name"]
    ent = store.get_entity_by_id(eid)
    return str(ent.name) if ent is not None else None


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
        # A function word is never an orphan concept; it is a stopword.
        if name.lower() in STOPWORDS:
            continue
        # Nor is a memory id, a filename fragment, or a GMD anchor.
        if _MEMORY_ID_RE.match(name) or name.startswith(".") or "#" in name:
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
    known = {"corroborated", "singleton", "contradicted", "orphan-concept"}
    wanted = set(classes) if classes else set(known)
    # Counted skips is rule 3 of this module; a class nobody implements must
    # not read as "ran and found nothing" (ch-bsd r1 #m-17). The CLI guards
    # with click.Choice; the generated MCP schema does not.
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError(
            f"unknown brief class(es): {', '.join(unknown)}; "
            f"known classes are {', '.join(sorted(known))}")
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


# ── the index on disk ──────────────────────────────────────────────────────

DOC_ID = "memory-briefs"
GENERATOR = "memory-brief"

_CLASS_ORDER = ("corroborated", "contradicted", "orphan-concept", "singleton")

_BRIEF_RE = re.compile(
    r"^### (?P<label>.+?) \{#(?P<anchor>[^}]+)\}\n\n(?P<finding>[^\n]+)\n"
    r"(?:.*?^Evidence \(\d+\): (?P<evidence>[^\n]+))?",
    re.M | re.S)

# Both rendered forms carry the id: `[[name]] `11`` and `` `99` (unresolved) ``.
_EV_ANY_RE = re.compile(r"`(\d+)`")


def _as_brief(b) -> "Brief":
    """Accept a `Brief` or the `as_dict()` shape that crosses the daemon wire."""
    if isinstance(b, Brief):
        return b
    return Brief(cls=b["class"], label=b["label"], finding=b["finding"],
                 evidence=list(b.get("evidence") or []),
                 detail=dict(b.get("detail") or {}))


def _anchor_safe(text: str) -> str:
    """A GMD anchor is an id, so it survives only what an id may contain."""
    out = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-").lower()
    return out or "brief"


def render_gmd(briefs: Iterable[Brief], *, names: "dict[int, str] | None" = None,
               doc_id: str = DOC_ID, partition: "str | None" = None,
               stats: "dict | None" = None) -> str:
    """Render briefs as a GMD index doc.

    The edge verb is `evidence-for`, pointed FROM the index at each cited
    memory, because the memory is what supports the finding. Direction is not
    cosmetic here: `consolidate.render_gmd` records the sibling mistake it had
    to avoid — emitting a container's own inverse verb would have claimed the
    subject is part of its own members.

    Output is sorted by (class, label) so two runs over the same store produce
    the same bytes. A derived file that churns on every run is a file nobody
    keeps in git.

    An evidence id with no known name cannot become a `[[wikilink]]` — that
    would be a dangling edge. It is written as a bare id and counted in the
    section text instead, because a silently shortened evidence list is the
    difference between "three memories agree" and "three memories, one of which
    I could not find".
    """
    names = names or {}
    # The daemon serialises briefs with `as_dict()` and the verb returns dicts
    # over the wire, so the CLI's `--gmd` path hands dicts in. Accepting only
    # `Brief` made the flag raise AttributeError on EVERY real invocation while
    # a unit test passed objects in-process (ch-bsd r1 #b-1).
    items = sorted((_as_brief(b) for b in briefs), key=lambda b: (b.cls, b.label))
    by_class: dict[str, list[Brief]] = defaultdict(list)
    for b in items:
        by_class[b.cls].append(b)

    st = stats or {}
    lines = [
        '---',
        'gmd: "0.1"',
        f'id: {doc_id}',
        'title: "Memory coverage briefs"',
        'tags: [memory, brief, derived]',
        'metadata:',
        '  node_type: index',
        f'  generator: {GENERATOR}',
        f'  partition: {partition or st.get("partition", "?")}',
        '---',
        '',
        '# Memory coverage briefs {#root}',
        '',
    ]
    if not items:
        lines += [
            'No briefs. Every detector ran and none fired — on this corpus, at '
            'these thresholds, nothing is thin enough to report.',
            '',
            'Derived, not authored — regenerate with `rmx memory brief`.',
            '',
        ]
        return "\n".join(lines).rstrip() + "\n"

    lines += [
        f'{len(items)} brief(s) over '
        f'{st.get("memories", "an unrecorded number of")} memories. '
        f'`memory compile` says what this corpus HAS; these say where it is '
        f'THIN.',
        '',
        'Derived, not authored — regenerate with `rmx memory brief`. Every '
        'brief names the rows it was derived from; there is no model in this '
        'path and nothing here is generated prose.',
        '',
    ]

    for cls in list(_CLASS_ORDER) + sorted(set(by_class) - set(_CLASS_ORDER)):
        group = by_class.get(cls)
        if not group:
            continue
        lines += [f'## {cls} {{#{cls}}}', '',
                  f'{len(group)} brief(s).', '']
        for b in group:
            anchor = f'{cls}-{_anchor_safe(b.label)}'
            resolved = [(e, names.get(e)) for e in b.evidence]
            unresolved = [e for e, n in resolved if not n]
            lines += [f'### {b.label} {{#{anchor}}}', '', b.finding, '']
            # The id travels WITH the link. Without it the doc names the rows
            # but cannot be read back into them, which is how the claimed round
            # trip came to be faked by a literal in its own test (r1 #b-5).
            ev = ", ".join(f'[[{n}]] `{e}`' if n else f'`{e}` (unresolved)'
                           for e, n in resolved)
            lines.append(f'Evidence ({len(resolved)}): {ev}.')
            if unresolved:
                lines.append(
                    f'{len(unresolved)} evidence id(s) could not be resolved '
                    f'to a memory name and are listed bare rather than '
                    f'dropped: {", ".join(str(e) for e in unresolved)}.')
            lines.append('')
            for e, n in resolved:
                if n:
                    lines.append(f'rel: evidence-for -> [[{n}]]')
            lines.append('')
    return "\n".join(lines).rstrip() + "\n"


def parse_gmd(doc: str, *, names: "dict[int, str] | None" = None) -> list[dict]:
    """Recover briefs from a rendered index — the other half of the trip.

    `memory compile` states the contract: the index is regenerable from the
    store and the store is rebuildable from the index. Without this half, a
    brief index is a report that happens to look like a node.
    """
    out: list[dict] = []
    # `render_gmd` writes `[[name]]`; invert the same map to get ids back. A
    # caller with no map still recovers the unresolved (bare-id) entries.
    ids_by_name = {v: k for k, v in (names or {}).items()}
    sections = re.split(r"^## ", doc, flags=re.M)[1:]
    for sec in sections:
        head = sec.splitlines()[0]
        m = re.match(r"^(\S+) \{#(\S+)\}", head)
        if not m:
            continue
        cls = m.group(1)
        if cls == "root":
            continue
        for bm in _BRIEF_RE.finditer(sec):
            out.append({"class": cls, "label": bm.group("label").strip(),
                        "finding": bm.group("finding").strip(),
                        "anchor": bm.group("anchor"),
                        "evidence": _parse_evidence(bm.group("evidence"),
                                                    ids_by_name)})
    return out


def _parse_evidence(line: "str | None",
                    ids_by_name: "dict[str, int]") -> list[int]:
    """Recover evidence ids from a rendered `Evidence (N): …` line.

    `evidence` is what `Brief.__post_init__` refuses to construct without and
    what the module docstring calls "the whole contract" — and it was written
    into the doc and never read back, so the round trip the plan claimed was
    faked by a literal in the test (ch-bsd r1 #b-5). Both rendered forms now
    carry the id, so no names map is needed to recover it.
    """
    if not line:
        return []
    return [int(x) for x in _EV_ANY_RE.findall(line)]

