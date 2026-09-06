"""Helix phase 1: point-in-time STM snapshot annotation on stale retrievals.

The STM/LTM helix design (2026-08-25): an LTM core of timeless structural
edges, decorated by a time-decayed associative working graph. Phase 1 is the
cheapest experiment — when retrieval pulls a concept whose last STM touch
falls OUTSIDE the current working window, annotate the result with the
working-graph neighborhood AS OF that last touch, reconstructed from the
per-session STM rings (`.refmatrix/stm/*.jsonl`). No schema change; the
rings already carry `ts` per event and have been written-never-read since
June.

Phase 1 is deliberately the fork-decider for phase 2 (mutable edge-time
columns vs a versioned store): every emitted annotation is telemetry-logged,
so "does anybody read the snapshots" is a measurable question, not a debate.

Env:
  RMX_HELIX=0                 kill switch (annotation off)
  RMX_HELIX_WINDOW_DAYS=7     touches younger than this are "current" and
                              get no annotation (wall-clock, not turns —
                              work here is bursty; a turn window zeroes out)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Last N touches kept per concept in the index; the annotation only needs
# the most recent out-of-window touch, the tail is for future phases.
_TOUCHES_PER_CONCEPT = 8
# Events on either side of the touch considered "that moment" when
# reconstructing the neighborhood.
_MOMENT_EVENTS = 20
# Neighborhood refs shown in the annotation.
_NEIGHBOR_K = 8

_INDEX_NAME = "helix_index.json"

# Per-process memo: scan-prompt resolves up to max_concepts anchors in one
# short-lived CLI process, and the active session's ring mutates every
# prompt — without this each anchor would re-parse that ring.
_proc_cache: dict = {}


def _enabled() -> bool:
    return os.environ.get("RMX_HELIX", "1") not in ("0", "false", "False")


def _window_s() -> float:
    try:
        days = float(os.environ.get("RMX_HELIX_WINDOW_DAYS", "7") or "7")
    except ValueError:
        days = 7.0
    return days * 86400.0


def stm_dir(root: Path) -> Path:
    return Path(root) / "stm"


def _index_path(root: Path) -> Path:
    return stm_dir(root) / _INDEX_NAME


def _parse_ts(ts) -> float:
    """Ring `ts` is ISO-8601 seconds ('2026-06-20T21:39:14'); tolerate
    epoch floats from any future writer."""
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        return time.mktime(time.strptime(str(ts), "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return 0.0


def _norm(tok: str) -> str:
    return str(tok).strip().lower()


def _current_session(root: Path) -> str | None:
    """The session whose STM ring is 'now': the hook exports RMX_SESSION;
    a plain shell falls back to the most recently written ring. Used to
    exclude the current session's own touches from last_touch — the ring
    records the prompt being served, so without the exclusion every
    scan-prompt anchor looks seconds old and the stale gate never opens
    (the phase-1 confound, diagnosed 2026-09-06)."""
    sid = os.environ.get("RMX_SESSION")
    if sid:
        return sid
    try:
        from refmatrix import stm
        return stm.latest_session(Path(root))
    except Exception:
        return None


def _base_stem(ring_stem: str) -> str:
    """`<session>__<subject>` subject rings still belong to the session."""
    return str(ring_stem).split("__", 1)[0]


def _ring_files(root: Path) -> list[Path]:
    d = stm_dir(root)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.jsonl") if p.name != _INDEX_NAME)


def build_index(root: Path, *, force: bool = False) -> dict:
    """Reverse-index the STM rings by concept token.

    {token: [[ts, ring_stem, line_no], ...]} — last _TOUCHES_PER_CONCEPT
    per token, ascending ts. Incremental: rings whose mtime predates the
    stored stamp keep their cached entries; only changed/new rings re-parse.
    The scan is tiny (tens of rings, KB-hundreds each) but the always-on
    hook must not pay it per prompt, hence the stamp gate."""
    root = Path(root)
    ipath = _index_path(root)
    rings = _ring_files(root)
    key = (str(root), tuple((p.name, p.stat().st_mtime) for p in rings))
    if not force and _proc_cache.get("key") == key:
        return _proc_cache["value"]
    cached = {"stamp": {}, "touch": {}}
    if not force and ipath.exists():
        try:
            cached = json.loads(ipath.read_text(encoding="utf8"))
        except Exception:
            cached = {"stamp": {}, "touch": {}}
    stamp: dict = dict(cached.get("stamp") or {})
    touch: dict = {k: list(v) for k, v in (cached.get("touch") or {}).items()}

    changed = []
    for p in rings:
        m = p.stat().st_mtime
        if force or stamp.get(p.stem) != m:
            changed.append((p, m))
    if not changed:
        _proc_cache.update(key=key, value=cached)
        return cached

    # Drop entries from changed rings, then re-add from a fresh parse.
    if touch:
        dirty = {p.stem for p, _m in changed}
        for tok in list(touch):
            kept = [row for row in touch[tok] if row[1] not in dirty]
            if kept:
                touch[tok] = kept
            else:
                del touch[tok]
    for p, m in changed:
        stamp[p.stem] = m
        try:
            with open(p, encoding="utf8") as f:
                for i, line in enumerate(f):
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    ts = _parse_ts(ev.get("ts"))
                    if not ts:
                        continue
                    for ref in (ev.get("refs") or []):
                        tok = _norm(ref)
                        if not tok:
                            continue
                        touch.setdefault(tok, []).append([ts, p.stem, i])
        except OSError:
            continue
    for tok in touch:
        touch[tok].sort(key=lambda r: r[0])
        touch[tok] = touch[tok][-_TOUCHES_PER_CONCEPT:]

    out = {"stamp": stamp, "touch": touch}
    try:
        stm_dir(root).mkdir(parents=True, exist_ok=True)
        tmp = ipath.with_suffix(".tmp")
        tmp.write_text(json.dumps(out), encoding="utf8")
        tmp.replace(ipath)
    except OSError:
        pass
    _proc_cache.update(key=key, value=out)
    return out


def _stopwords() -> frozenset | set:
    """Shared prompt stoplist (feedback: reuse it, don't re-derive)."""
    try:
        from refmatrix.scan import _PROMPT_STOPWORDS
        return _PROMPT_STOPWORDS
    except Exception:
        return set()


def _display_ref(ref) -> str:
    """Ring refs arrive as raw focus tokens: absolute paths, and sometimes
    mid-word truncations (`s.repla`, `main..maste`, `.claud`). Compress a
    path to its basename and drop stopwords plus visibly truncated shapes —
    the annotation is for a human re-orienting, not a parser."""
    tok = _norm(ref)
    if "/" in tok:
        tok = tok.rstrip("/").rsplit("/", 1)[-1]
    if len(tok) < 3:
        return ""
    if tok in _stopwords():
        return ""
    # Visible truncation artifacts: doubled dots, leading/trailing dot.
    if ".." in tok or tok.startswith(".") or tok.endswith("."):
        return ""
    return tok


def _candidates(name: str) -> list[str]:
    """Tokens under which a graph anchor may appear in ring refs: the bare
    name, its leaf (`a.b::c` → c), and the canonical variant fold."""
    out = [_norm(name)]
    leaf = name.rsplit("/", 1)[-1].rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if _norm(leaf) not in out:
        out.append(_norm(leaf))
    try:
        from refmatrix.identifier import canonicalize_name
        c = _norm(canonicalize_name(name))
        if c and c not in out:
            out.append(c)
    except Exception:
        pass
    return out


def last_touch(root: Path, name: str, *, index: dict | None = None,
               exclude_session: str | None = None):
    """(ts, ring_stem, line_no) of the newest STM touch for `name`, else
    None. `index` lets a caller amortize one build over many anchors.
    `exclude_session` drops touches from that session's rings (subject
    rings included) so the current conversation can't mask staleness."""
    idx = index if index is not None else build_index(root)
    ex = _base_stem(exclude_session) if exclude_session else None
    best = None
    for tok in _candidates(name):
        rows = (idx.get("touch") or {}).get(tok)
        if not rows:
            continue
        for row in reversed(rows):
            if ex is not None and _base_stem(row[1]) == ex:
                continue
            if best is None or row[0] > best[0]:
                best = row
            break
    return best


def snapshot_at(root: Path, ring_stem: str, line_no: int, name: str) -> dict:
    """Reconstruct 'that moment': the touch event plus its co-occurring
    refs within ±_MOMENT_EVENTS ring events. Returns {ts, session, terse,
    neighbors: [(ref, count)]}."""
    p = stm_dir(Path(root)) / f"{ring_stem}.jsonl"
    events: list[tuple[int, dict]] = []
    try:
        with open(p, encoding="utf8") as f:
            for i, line in enumerate(f):
                if abs(i - line_no) > _MOMENT_EVENTS:
                    if i > line_no + _MOMENT_EVENTS:
                        break
                    continue
                try:
                    events.append((i, json.loads(line)))
                except ValueError:
                    continue
    except OSError:
        return {}
    self_toks = set(_candidates(name))
    counts: dict[str, int] = {}
    terse = ""
    ts = 0.0
    for i, ev in events:
        if i == line_no:
            terse = str(ev.get("terse") or "")[:100]
            ts = _parse_ts(ev.get("ts"))
        for ref in (ev.get("refs") or []):
            tok = _display_ref(ref)
            if tok and tok not in self_toks:
                counts[tok] = counts.get(tok, 0) + 1
    neighbors = sorted(counts.items(), key=lambda kv: -kv[1])[:_NEIGHBOR_K]
    return {"ts": ts, "session": ring_stem, "terse": terse,
            "neighbors": neighbors}


def annotate(root: Path, name: str, *, now: float | None = None,
             index: dict | None = None, label: str | None = None,
             exclude_current: bool = True) -> str | None:
    """The phase-1 product: a one-block annotation when `name`'s last STM
    touch predates the working window, else None. Telemetry-logged on every
    emission — the readership signal that decides the phase-2 storage fork.

    `exclude_current` (default on) ignores the CURRENT session's own ring
    when finding the last touch — the ring records the prompt being served,
    so without this the always-on hook can never see a stale anchor.
    `label` marks a non-anchor emission (a stale graph neighbor) and is
    prefixed to the header + logged as role=neighbor."""
    if not _enabled():
        return None
    root = Path(root)
    ex = _current_session(root) if exclude_current else None
    lt = last_touch(root, name, index=index, exclude_session=ex)
    if lt is None:
        return None
    ts, ring_stem, line_no = lt
    now_ts = time.time() if now is None else float(now)
    age = now_ts - float(ts)
    if age < _window_s():
        return None          # current work; the live STM composite covers it
    snap = snapshot_at(root, ring_stem, int(line_no), name)
    if not snap:
        return None
    days = int(age // 86400)
    when = time.strftime("%Y-%m-%d", time.localtime(float(ts)))
    nb = ", ".join(t for t, _c in snap.get("neighbors") or [])
    head = f"[helix] {label}: " if label else "[helix] "
    lines = [f"{head}last worked {when} ({days}d ago, "
             f"session {ring_stem[:8]})"]
    if snap.get("terse"):
        lines.append(f"  then: {snap['terse']}")
    if nb:
        lines.append(f"  neighborhood then: {nb}")
    note = "\n".join(lines)
    # Readership signal for the phase-2 storage fork: one JSONL row per
    # emitted annotation in .refmatrix/helix.log (same best-effort shape as
    # the cli.log trinity). If this file stays empty across real sessions,
    # take Option A and stop; if it fills, Option B earns its build.
    try:
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "concept": name,
               "age_days": days, "session": ring_stem,
               "role": "neighbor" if label else "anchor"}
        with open(Path(root) / "helix.log", "a", encoding="utf8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return note
