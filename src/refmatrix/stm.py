"""Short-term (working) memory — a per-project, isolated focus graph.

STM is two things, both under `<root>/stm/`:

  * an append-only **event ring** (`<session>.jsonl`) — raw provenance of what
    happened (input / tool / rmx / result), trimmed to a soft cap; and
  * a maintained **focus graph** (`<session>.focus.json`) — node-addressable,
    score-evicted, decayed. This is "an rmx of what I'm working on right now."

The focus graph is NOT a flat ring. Nodes are addressable by a stable key (the
ref name), refreshed in place (never duplicated). Each turn applies recency
decay; admission is gated + capped so one noisy turn can't churn the whole
graph; eviction is by a composite score (recency · frequency · graph centrality
· pin) so structurally-central hubs survive. Evicting a node that still has a
live neighbor leaves a cheap **frontier stub** — a breadcrumb to rehydrate from
long-term memory.

Per-project + file-based by design: project A's focus never bleeds into B, and
STM works whether or not the hub/daemon is running.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .scan import _PROMPT_STOPWORDS

# Event ring (raw provenance).
RING_SIZE = int(os.environ.get("RMX_STM_SIZE", "500"))
# Focus-graph node budget (scored eviction kicks in above this).
NODE_BUDGET = int(os.environ.get("RMX_STM_NODES", "200"))
# Cap on how many nodes one turn may admit (anti-churn).
MAX_ADMIT_PER_TURN = int(os.environ.get("RMX_STM_ADMIT", "12"))
# Per-turn recency decay factor.
DECAY = float(os.environ.get("RMX_STM_DECAY", "0.85"))
# Frontier stubs are cheap but bounded.
FRONTIER_BUDGET = max(8, NODE_BUDGET // 2)
COOCCUR_WINDOW = 4
# Verbatim surface action retained on the timeline (never graph-ingested).
DETAIL_MAX = int(os.environ.get("RMX_STM_DETAIL_MAX", "600"))
# Cap on parked (started-but-unfinished) tool calls.
INFLIGHT_BUDGET = 64

# Score weights. Pin dominates so a pinned node is never evicted ahead of junk.
W_RECENCY, W_FREQ, W_CENTRALITY, W_PIN = 1.0, 0.5, 0.8, 10.0

EVENT_KINDS = ("input", "tool", "rmx", "result", "say", "git", "mark", "reason")

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}(?:\.[A-Za-z_][A-Za-z0-9_]+)*")
_PATH_RE = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}")
# Reuse the maintained NL function-word stoplist from the prompt scanner
# (articles/pronouns/prepositions/conjunctions/auxiliaries) — a focus note is
# prose, same problem as a prompt. Union with the shell/path/domain noise that
# is specific to ref-extraction over command lines and absolute paths.
_STOP = _PROMPT_STOPWORDS | {
    "rmx", "true", "false", "none", "null", "self", "args", "kwargs",
    # common adverbs / fillers the prompt list omits (prose-only noise)
    "here", "there", "now", "also", "because", "just", "very", "much",
    "more", "most", "some", "any", "all", "each", "every", "both", "either",
    "neither", "only", "even", "still", "again", "back", "over", "out", "up",
    "down", "too", "use", "used", "using", "uses", "try", "tried", "trying",
    "get", "got", "make", "made", "note", "noted", "like", "want", "need",
    "see", "seen", "test", "testing", "tested",
    # shell commands + tool names: noise when a Bash command line or a
    # tool envelope is ref-extracted. The signal in a command is its file
    # paths, not `echo`/`grep`/`Bash`.
    "bash", "sh", "zsh", "echo", "grep", "rg", "cat", "sed", "awk", "ls",
    "cd", "cp", "mv", "head", "tail", "git", "python", "python3", "pip",
    "rtk", "tee", "xargs", "find", "sleep", "export", "sudo", "chmod",
    "mkdir", "touch", "curl", "wget", "tool", "read", "edit",
    "write", "glob", "bash_tool",
    # home-dir path segments that appear in every absolute path
    "users", "home", "tmp", "var", "usr", "opt", "bin", "dev",
    "tholley", "claude_tools", "claude",
}


# Machine-noise gates, shared by the input hook (skip at ingest), the topic
# composite (skip at render), and `rebuild_focus` (skip on replay).
_JUNK_PREFIX = ("toolu_", "msg_", "call_", "run_", "req_", "wf_")
# Hex-ish id: >=4 hex chars AND >=1 digit, so real all-letter words like
# "face"/"cafe" survive but "a22a"/"e8fb2e" are gated.
_HEXISH = re.compile(r"^(?=.*[0-9])[0-9a-f]{4,}$", re.I)
_UUIDISH = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", re.I)


def is_junk_ref(name: str) -> bool:
    """Shape-based junk gate for a ref/node name: tool/message/run ids, bare hex
    blobs, uuids, and deep absolute-path tails (tmp/scratchpad blobs). These
    carry no topical signal and must never enter the focus graph or composite."""
    n = (name or "").strip()
    if not n:
        return True
    if n.startswith(_JUNK_PREFIX):
        return True
    if _HEXISH.match(n) or _UUIDISH.search(n):
        return True
    if n.startswith("/") and n.count("/") >= 4:
        return True
    return False


def is_ambient_text(text: str) -> bool:
    """True for machine-injected turns that are NOT user intent: hub/bus channel
    messages (`<channel …>`) and system/task notifications. Claude Code delivers
    these as 'user' prompts, but they carry no topical signal — recording them
    pollutes the focus graph and every downstream composite."""
    t = (text or "").lstrip()
    return (
        t.startswith("<channel")
        or t.startswith("<task-notification")
        or t.startswith("[SYSTEM NOTIFICATION")
    )


def stm_dir(root: Path) -> Path:
    return Path(root) / "stm"


def session_id() -> str:
    return os.environ.get("RMX_SESSION") or "default"


def latest_session(root: Path) -> str | None:
    """The session id whose event ring was written most recently, or None if
    no STM exists yet. Lets read surfaces (`focus tail/context`, save-state)
    default to the active Claude session instead of the bare "default" ring —
    the hook keys STM by the Claude `session_id`, which a plain shell does not
    have in `$RMX_SESSION`."""
    d = stm_dir(root)
    if not d.is_dir():
        return None
    newest: tuple[float, str] | None = None
    for p in d.glob("*.jsonl"):
        if p.name.endswith(".tmp"):
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        # A subject ring is named `<session>__<subject>.jsonl`; the resumable
        # unit is still the Claude session, so strip the subject suffix.
        stem = p.stem.split("__", 1)[0]
        if newest is None or mtime > newest[0]:
            newest = (mtime, stem)
    return newest[1] if newest else None


def _safe(session: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", session) or "default"


def subject_slug(label: str) -> str:
    """Slug a subject label into a stable partition-key fragment. Lowercase,
    non-alphanumerics → `_`, collapsed, capped. Empty → 'subject'."""
    s = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    return s[:48] or "subject"


def _partition_key(session: str, subject: "str | None") -> str:
    """The on-disk key for an STM partition. Bare session when no subject is
    active; `<session>__<subject-slug>` when one is. The `__` separator never
    collides with a Claude session id (a hyphenated uuid)."""
    base = _safe(session)
    return f"{base}__{subject}" if subject else base


def _edge_key(a: str, b: str) -> str:
    return "\x00".join(sorted((a, b)))


class Stm:
    """File-backed short-term memory for one (root, session)."""

    def __init__(self, root: Path, session: str | None = None,
                 size: int = RING_SIZE, node_budget: int = NODE_BUDGET,
                 subject: "str | None" = None):
        self.root = Path(root)
        self.session = session or session_id()
        self.size = size
        self.node_budget = node_budget
        self._dir = stm_dir(self.root)
        # The active-subject pointer is keyed by the RAW session, so every
        # subject of a session shares one pointer. An explicit `subject` arg
        # overrides it (None = inherit the active subject, "" = force bare).
        self._subject_path = self._dir / f"{_safe(self.session)}.subject.json"
        self.subject = subject if subject is not None else self._read_subject()
        self.subject = self.subject or None
        self._rebind()

    def _rebind(self) -> None:
        """(Re)point the ring/graph/tasks/marks files at the active partition
        key — `<session>` or `<session>__<subject>`."""
        key = _partition_key(self.session, self.subject)
        self._key = key
        self._path = self._dir / f"{key}.jsonl"
        self._graph_path = self._dir / f"{key}.focus.json"
        self._tasks_path = self._dir / f"{key}.tasks.json"
        self._marks_path = self._dir / f"{key}.marks.json"
        self._inflight_path = self._dir / f"{key}.inflight.json"

    # ---- subject (named STM partition; durable face lives in the memory store) ----
    def _read_subject(self) -> "str | None":
        try:
            d = json.loads(self._subject_path.read_text())
            return d.get("subject") or None
        except (OSError, json.JSONDecodeError):
            return None

    def set_subject(self, label: str) -> dict:
        """Set the active subject for this session and rebind to its partition.
        Returns the pointer record. Idempotent for the same label."""
        slug = subject_slug(label)
        self._dir.mkdir(parents=True, exist_ok=True)
        rec = {"subject": slug, "label": label,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        tmp = self._subject_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec))
        tmp.replace(self._subject_path)
        self.subject = slug
        self._rebind()
        return rec

    def get_subject(self) -> "dict | None":
        try:
            return json.loads(self._subject_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def clear_subject(self) -> bool:
        """Unset the active subject (revert to the bare session ring). Returns
        True if one was set."""
        existed = self._subject_path.exists()
        try:
            self._subject_path.unlink()
        except OSError:
            pass
        self.subject = None
        self._rebind()
        return existed

    # ---- event ring (provenance) ----
    def record(self, kind: str, terse: str, *, refs: list[str] | None = None,
               detail: str | None = None, extra: dict | None = None) -> dict:
        """Append one event to the ring.

        `detail` is the verbatim surface action — the shell command, the grep
        pattern, the tool_input — kept on the TIMELINE only. It never reaches
        `_extract_refs` and never enters the focus graph, so it cannot admit
        `Bash`/`echo`/path-segment noise as concept nodes. `terse` stays the
        graph-facing summary; `detail` answers "what was actually run", which
        `terse` deliberately drops once path refs are extractable."""
        if kind not in EVENT_KINDS:
            kind = "tool"
        rlist = refs if refs is not None else _extract_refs(terse)
        ev = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session": self.session,
            "kind": kind,
            "terse": terse[:500],
            "refs": rlist,
            "task": self.current_task_desc(),
        }
        if detail:
            ev["detail"] = detail[:DETAIL_MAX]
        if extra:
            ev.update(extra)
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        # The jsonl is the FULL, append-only session log — never trimmed, so the
        # complete context is always retrievable from disk (`focus export`). The
        # live focus GRAPH stays bounded independently via node-budget eviction,
        # so an unbounded log doesn't grow the working set.
        self._ingest_into_graph(rlist, new_turn=(kind == "input"))
        return ev

    # ---- in-flight tool calls (PreToolUse) --------------------------------
    #
    # PostToolUse only fires for calls that COMPLETE. A tool that hangs, is
    # denied, or takes the session down leaves no trace at all — precisely the
    # moment a post-mortem wants. PreToolUse writes the call here first; the
    # matching PostToolUse clears it. Whatever is still parked when the next
    # turn starts never finished, and gets folded into the ring as an
    # `abandoned` event.
    #
    # A sidecar rather than a ring entry: the ring is append-only, so a
    # pre/post pair would either double every tool event or need a rewrite.

    def _read_inflight(self) -> dict:
        try:
            d = json.loads(self._inflight_path.read_text())
            return d if isinstance(d, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_inflight(self, d: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._inflight_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(d))
            tmp.replace(self._inflight_path)
        except OSError:
            pass

    def inflight_begin(self, key: str, *, terse: str, refs: list[str],
                       detail: str | None = None) -> dict:
        """Park a tool call as started. Bounded so a runaway session can't grow
        the sidecar without limit."""
        d = self._read_inflight()
        if len(d) > INFLIGHT_BUDGET:
            for k in sorted(d, key=lambda k: d[k].get("t", 0))[:len(d) // 2]:
                d.pop(k, None)
        rec = {"t": time.time(), "terse": terse[:500], "refs": refs,
               "detail": (detail or "")[:DETAIL_MAX] or None}
        d[key] = rec
        self._write_inflight(d)
        return rec

    def inflight_end(self, key: str) -> dict | None:
        """Clear a completed call. Returns the parked record if there was one."""
        d = self._read_inflight()
        rec = d.pop(key, None)
        if rec is not None:
            self._write_inflight(d)
        return rec

    def inflight_sweep(self, *, max_age_s: float = 90.0) -> list[dict]:
        """Fold calls that never completed into the ring as `abandoned` tool
        events. Called at the top of each turn (the `input` hook), so a hang or
        a denial shows up on the timeline by the next prompt."""
        d = self._read_inflight()
        if not d:
            return []
        now = time.time()
        stale = {k: v for k, v in d.items()
                 if now - float(v.get("t") or 0) > max_age_s}
        if not stale:
            return []
        out = []
        for k, v in stale.items():
            out.append(self.record(
                "tool", v.get("terse") or "tool",
                refs=list(v.get("refs") or []),
                detail=v.get("detail"),
                extra={"abandoned": True},
            ))
            d.pop(k, None)
        self._write_inflight(d)
        return out

    def tail(self, n: int = 50) -> list[dict]:
        """Last n events. Reads the full log but keeps only the last n in
        memory (deque) so it stays cheap as the log grows."""
        if not self._path.exists():
            return []
        from collections import deque
        out = []
        try:
            with self._path.open() as f:
                for ln in deque(f, maxlen=n):
                    try:
                        out.append(json.loads(ln))
                    except json.JSONDecodeError:
                        pass
        except OSError:
            return []
        return out

    def all_events(self) -> list[dict]:
        """The ENTIRE session log (full context), not just a recent window."""
        if not self._path.exists():
            return []
        out = []
        try:
            for ln in self._path.read_text().splitlines():
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
        except OSError:
            return []
        return out

    def event_count(self) -> int:
        """Cheap total event count (line count, no parse)."""
        if not self._path.exists():
            return 0
        try:
            with self._path.open() as f:
                return sum(1 for _ in f)
        except OSError:
            return 0

    def clear(self) -> None:
        for p in (self._path, self._graph_path, self._tasks_path, self._marks_path):
            try:
                p.unlink()
            except OSError:
                pass

    # ---- focus graph (maintained, scored) ----
    def _load_graph(self) -> dict:
        if not self._graph_path.exists():
            return {"turn": 0, "nodes": {}, "edges": {}}
        try:
            g = json.loads(self._graph_path.read_text())
            g.setdefault("turn", 0); g.setdefault("nodes", {}); g.setdefault("edges", {})
            return g
        except (json.JSONDecodeError, OSError):
            return {"turn": 0, "nodes": {}, "edges": {}}

    def _save_graph(self, g: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._graph_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(g))
        tmp.replace(self._graph_path)

    def _apply_turn(self, g: dict, refs: list[str], *, new_turn: bool) -> None:
        """Fold one event's refs into graph `g` in place — the pure ingest step,
        shared by the live `record` path and the offline `rebuild_focus` replay.
        Does NOT load or save; the caller owns persistence."""
        if new_turn:
            g["turn"] += 1
            for nd in g["nodes"].values():
                if not nd.get("frontier"):
                    nd["recency"] *= DECAY  # staleness falls out of scoring
        turn = g["turn"]
        admitted = self._admit(g, refs[:MAX_ADMIT_PER_TURN], turn)
        # co-occurrence edges among admitted refs (in-place weight bump)
        for i in range(len(admitted)):
            for j in range(i + 1, len(admitted)):
                k = _edge_key(admitted[i], admitted[j])
                g["edges"][k] = g["edges"].get(k, 0.0) + 1.0
        self._evict(g)

    def _ingest_into_graph(self, refs: list[str], *, new_turn: bool) -> None:
        if not refs and not new_turn:
            return
        g = self._load_graph()
        self._apply_turn(g, refs, new_turn=new_turn)
        self._save_graph(g)

    def rebuild_focus(self, *, drop_ambient: bool = True,
                      drop_junk: bool = True, dry_run: bool = False) -> dict:
        """Recompute the focus graph from the event ring, dropping machine noise
        that older ingests admitted: ambient turns (hub/bus channel messages,
        system/task notifications recorded as `input`) and shape-junk refs
        (tool/message ids, hex blobs, deep tmp paths). Replays the SAME ingest
        math over the surviving events into a fresh graph and swaps it in.

        The ring is left intact (full provenance); only the maintained graph is
        rewritten. When `dry_run`, the fresh graph is computed and measured but
        NOT swapped in — the on-disk graph is untouched. Returns a stats dict for
        reporting / dry-run callers; `dry_run` is echoed back in it."""
        events = self.all_events()
        g = {"turn": 0, "nodes": {}, "edges": {}}
        dropped_events = 0
        dropped_refs = 0
        for ev in events:
            kind = ev.get("kind", "tool")
            terse = ev.get("terse", "")
            if drop_ambient and kind == "input" and is_ambient_text(terse):
                dropped_events += 1
                continue
            refs = ev.get("refs") or []
            if drop_junk:
                kept = [r for r in refs if not is_junk_ref(r)]
                dropped_refs += len(refs) - len(kept)
                refs = kept
            self._apply_turn(g, refs, new_turn=(kind == "input"))
        if not dry_run:
            self._save_graph(g)
        return {"session": self._key, "events": len(events),
                "dropped_events": dropped_events, "dropped_refs": dropped_refs,
                "nodes": len(g["nodes"]), "edges": len(g["edges"]),
                "dry_run": dry_run}

    def _admit(self, g: dict, refs: list[str], turn: int) -> list[str]:
        """Create/refresh nodes in place (stable key = ref name). Rehydrates a
        frontier stub on re-touch. Returns the admitted names."""
        out = []
        for name in refs:
            if not name:
                continue
            nd = g["nodes"].get(name)
            if nd is None:
                g["nodes"][name] = {
                    "name": name, "kind": _ref_kind(name),
                    "recency": 1.0, "freq": 1, "pin": 0, "frontier": False,
                    "first_turn": turn, "last_turn": turn,
                    "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            else:
                nd["recency"] = 1.0          # touch resets recency
                nd["freq"] = nd.get("freq", 0) + 1
                nd["frontier"] = False       # rehydrate stub
                nd["last_turn"] = turn
                nd["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            out.append(name)
        return out

    def _degree(self, g: dict) -> dict[str, int]:
        deg: dict[str, int] = {}
        for k in g["edges"]:
            a, b = k.split("\x00")
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
        return deg

    def _score(self, nd: dict, maxfreq: int, deg: dict, maxdeg: int) -> float:
        freq = (nd.get("freq", 0) / maxfreq) if maxfreq else 0.0
        cen = (deg.get(nd["name"], 0) / maxdeg) if maxdeg else 0.0
        return (W_RECENCY * nd.get("recency", 0.0) + W_FREQ * freq
                + W_CENTRALITY * cen + W_PIN * nd.get("pin", 0))

    def _evict(self, g: dict) -> None:
        nodes = g["nodes"]
        real = [n for n, nd in nodes.items() if not nd.get("frontier")]
        if len(real) <= self.node_budget:
            self._evict_frontier(g)
            return
        deg = self._degree(g)
        maxdeg = max(deg.values()) if deg else 1
        while len(real) > self.node_budget:
            maxfreq = max((nodes[n].get("freq", 0) for n in real), default=1) or 1
            cand = [n for n in real if not nodes[n].get("pin")]
            if not cand:
                break  # everything pinned
            victim = min(cand, key=lambda n: self._score(nodes[n], maxfreq, deg, maxdeg))
            # surviving real neighbor? → leave a frontier breadcrumb, else delete
            has_live_neighbor = any(
                (other in nodes and not nodes[other].get("frontier") and other != victim)
                for other in _neighbors(g, victim)
            )
            if has_live_neighbor:
                nodes[victim]["frontier"] = True
                nodes[victim]["recency"] = 0.0
            else:
                _drop_node(g, victim)
            real = [n for n, nd in nodes.items() if not nd.get("frontier")]
            deg = self._degree(g)
            maxdeg = max(deg.values()) if deg else 1
        self._evict_frontier(g)

    def _evict_frontier(self, g: dict) -> None:
        nodes = g["nodes"]
        front = [n for n, nd in nodes.items() if nd.get("frontier")]
        if len(front) <= FRONTIER_BUDGET:
            return
        front.sort(key=lambda n: nodes[n].get("last_turn", 0))  # oldest first
        for victim in front[: len(front) - FRONTIER_BUDGET]:
            _drop_node(g, victim)

    def focus_graph(self, *, top: int = 30, include_frontier: bool = False) -> dict:
        """Ranked snapshot of the maintained focus graph (best-scoring first)."""
        g = self._load_graph()
        nodes = g["nodes"]
        deg = self._degree(g)
        maxdeg = max(deg.values()) if deg else 1
        real = [nd for nd in nodes.values() if not nd.get("frontier")]
        maxfreq = max((nd.get("freq", 0) for nd in real), default=1) or 1
        scored = sorted(
            real, key=lambda nd: self._score(nd, maxfreq, deg, maxdeg), reverse=True)
        keep = set(n["name"] for n in scored[:top])
        out_nodes = [{
            "name": nd["name"], "kind": nd["kind"],
            "weight": round(self._score(nd, maxfreq, deg, maxdeg), 3),
            "recency": round(nd.get("recency", 0), 3),
            "count": nd.get("freq", 0), "degree": deg.get(nd["name"], 0),
            "pin": nd.get("pin", 0), "last": nd.get("updated"),
        } for nd in scored[:top]]
        if include_frontier:
            for nd in nodes.values():
                if nd.get("frontier") and nd["name"] in {
                        x for e in g["edges"] for x in e.split("\x00") if x in keep}:
                    out_nodes.append({"name": nd["name"], "kind": nd["kind"],
                                      "weight": 0, "frontier": True})
                    keep.add(nd["name"])
        edges = []
        for k, w in g["edges"].items():
            a, b = k.split("\x00")
            if a in keep and b in keep:
                edges.append({"source": a, "target": b, "weight": round(w, 2)})
        return {"session": self.session, "turn": g.get("turn", 0),
                "events": self.event_count(), "nodes": out_nodes,
                "edges": edges, "focus": [n["name"] for n in out_nodes if not n.get("frontier")]}

    def pin(self, name: str, value: bool = True) -> bool:
        g = self._load_graph()
        nd = g["nodes"].get(name)
        if nd is None:
            return False
        nd["pin"] = 1 if value else 0
        if value:
            nd["frontier"] = False
        self._save_graph(g)
        return True

    # ---- task pushdown stack ----
    def _load_tasks(self) -> list[dict]:
        if not self._tasks_path.exists():
            return []
        try:
            return json.loads(self._tasks_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _save_tasks(self, stack: list[dict]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._tasks_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(stack, indent=2))
        tmp.replace(self._tasks_path)

    def current_task_desc(self) -> str | None:
        stack = self._load_tasks()
        return stack[-1]["desc"] if stack else None

    def task_push(self, desc: str) -> dict:
        stack = self._load_tasks()
        snap = self.focus_graph(top=12)["focus"]
        stack.append({"desc": desc, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "focus_snapshot": snap})
        self._save_tasks(stack)
        return {"depth": len(stack), "current": desc}

    def _find_task(self, stack: list[dict], selector: str) -> "int | None":
        """Resolve a stack index from a selector: a 1-based index as shown by
        `stash-list` (top = 1), or a case-insensitive desc substring (most
        recent match wins). Enables out-of-order pop."""
        s = str(selector).strip()
        if not s:
            return len(stack) - 1 if stack else None
        if s.lstrip("+").isdigit():
            i = len(stack) - int(s)   # display 1 == top == stack[-1]
            return i if 0 <= i < len(stack) else None
        for i in range(len(stack) - 1, -1, -1):
            if s.lower() in stack[i]["desc"].lower():
                return i
        return None

    def task_pop(self, selector: str | None = None) -> dict:
        """Pop a stash and restore ITS focus snapshot (git-stash semantics: you
        resume exactly where you stashed). Default = top; `selector` (index or
        desc substring) pops out of order."""
        stack = self._load_tasks()
        if not stack:
            return {"popped": None, "depth": 0, "restored": None,
                    "restored_focus": []}
        idx = (len(stack) - 1) if selector is None \
            else self._find_task(stack, selector)
        if idx is None:
            return {"popped": None, "depth": len(stack), "restored": None,
                    "restored_focus": [],
                    "error": f"no stash matching {selector!r}"}
        popped = stack.pop(idx)
        self._save_tasks(stack)
        snap = popped.get("focus_snapshot") or []
        # Re-warm the resumed work's focus.
        self._ingest_into_graph(list(snap), new_turn=False)
        return {"popped": popped["desc"], "depth": len(stack),
                "restored": popped["desc"], "restored_focus": snap}

    def task_list(self) -> list[dict]:
        return self._load_tasks()

    def task_current(self) -> dict | None:
        stack = self._load_tasks()
        return stack[-1] if stack else None

    def task_swap(self) -> dict:
        stack = self._load_tasks()
        if len(stack) < 2:
            return {"swapped": False, "current": self.current_task_desc()}
        stack[-1], stack[-2] = stack[-2], stack[-1]
        self._save_tasks(stack)
        return {"swapped": True, "current": stack[-1]["desc"]}

    # ---- soft branch detours (lightweight focus rewind points) ----
    # A detour is NOT a stash: no git, no stack discipline — just a focus
    # return-point you bookmark before chasing a related-but-off-task tangent,
    # then rewind to. The tangent stays in the full log (clusters as its own
    # topic); `return` re-warms the pre-detour focus.
    def _load_marks(self) -> list[dict]:
        p = self._marks_path
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _save_marks(self, marks: list[dict]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        p = self._marks_path
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(marks, indent=2))
        tmp.replace(p)

    def _find_mark(self, marks: list[dict], selector: str) -> "int | None":
        s = str(selector).strip()
        if not s:
            return len(marks) - 1 if marks else None
        if s.lstrip("+").isdigit():
            i = len(marks) - int(s)   # display 1 == most recent == marks[-1]
            return i if 0 <= i < len(marks) else None
        for i in range(len(marks) - 1, -1, -1):
            if s.lower() in marks[i]["label"].lower():
                return i
        return None

    def focus_mark(self, label: str = "") -> dict:
        """Drop a soft-detour return-point: the current focus snapshot + log
        line. Also logs a `mark` event so the detour shows on the timeline."""
        marks = self._load_marks()
        snap = self.focus_graph(top=12)["focus"]
        mark = {"label": label or f"detour-{len(marks) + 1}",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "line": self.event_count() + 1, "focus_snapshot": snap}
        marks.append(mark)
        self._save_marks(marks)
        self.record("mark", f"⤴ detour: {mark['label']}", refs=[])
        return mark

    def focus_marks(self) -> list[dict]:
        return self._load_marks()

    def focus_return(self, selector: str | None = None) -> dict:
        """Rewind focus to a detour return-point (re-warm its snapshot). The
        tangent's events stay in the log. Default = most recent; `selector`
        (index or label substring) returns from a specific detour."""
        marks = self._load_marks()
        if not marks:
            return {"returned": None, "focus": [], "remaining": 0}
        idx = (len(marks) - 1) if selector is None \
            else self._find_mark(marks, selector)
        if idx is None:
            return {"returned": None, "focus": [], "remaining": len(marks),
                    "error": f"no detour matching {selector!r}"}
        mark = marks.pop(idx)
        self._save_marks(marks)
        snap = mark.get("focus_snapshot") or []
        self._ingest_into_graph(list(snap), new_turn=False)
        self.record("mark", f"⤶ return: {mark['label']}", refs=list(snap)[:6])
        return {"returned": mark["label"], "line": mark.get("line"),
                "focus": snap, "remaining": len(marks)}


def cluster_focus(graph: dict, *, min_size: int = 2) -> list[list[str]]:
    """Partition a `focus_graph()` snapshot into topic clusters by label
    propagation over the co-occurrence edges. Each cluster is a thread of work
    (symbols that co-occurred). Returns node-name lists, largest first.

    Deterministic: node iteration follows the graph's score order and labels
    break ties by lowest id, so the same graph always yields the same topics
    (no Math.random / dict-order dependence)."""
    import collections
    nodes = [n["name"] for n in graph.get("nodes", [])]
    adj: dict[str, dict[str, float]] = {n: {} for n in nodes}
    for e in graph.get("edges", []):
        a, b, w = e.get("source"), e.get("target"), e.get("weight", 1.0)
        if a in adj and b in adj:
            adj[a][b] = adj[a].get(b, 0.0) + w
            adj[b][a] = adj[b].get(a, 0.0) + w
    label = {n: i for i, n in enumerate(nodes)}
    for _ in range(30):
        changed = False
        for n in nodes:  # graph order = score order → deterministic
            if not adj[n]:
                continue
            tally: dict[int, float] = collections.defaultdict(float)
            for m, w in adj[n].items():
                tally[label[m]] += w
            best = max(tally.items(), key=lambda kv: (kv[1], -kv[0]))[0]
            if label[n] != best:
                label[n] = best
                changed = True
        if not changed:
            break
    clusters: dict[int, list[str]] = collections.defaultdict(list)
    for n in nodes:
        clusters[label[n]].append(n)
    return sorted((c for c in clusters.values() if len(c) >= min_size),
                  key=len, reverse=True)


def topic_composites(graph: dict, *, k: int = 3, min_size: int = 2) -> list[dict]:
    """Top-`k` topic clusters of a `focus_graph()` snapshot, each rendered as an
    induced subgraph: the cluster's nodes plus every co-occurrence edge whose
    endpoints are BOTH in the cluster. Largest cluster first; members sorted by
    focus weight (strongest head first). Deterministic — inherits
    `cluster_focus`'s label-propagation determinism.

    This is the aggregation surface for "the current topic": the focus graph
    already fuses every prompt+result (their extracted refs) into a scored,
    decayed co-occurrence graph; this splits it into the k dominant threads and
    hands back each thread's self-contained subgraph for rendering/expansion."""
    nmap = {n["name"]: n for n in graph.get("nodes", [])}
    out: list[dict] = []
    for members in cluster_focus(graph, min_size=min_size)[:k]:
        keep = set(members)
        nodes = sorted(
            (nmap[n] for n in members if n in nmap),
            key=lambda nd: nd.get("weight", 0.0), reverse=True)
        if not nodes:
            continue
        edges = [e for e in graph.get("edges", [])
                 if e.get("source") in keep and e.get("target") in keep]
        out.append({"members": [nd["name"] for nd in nodes],
                    "nodes": nodes, "edges": edges})
    return out


def _neighbors(g: dict, name: str) -> list[str]:
    out = []
    for k in g["edges"]:
        a, b = k.split("\x00")
        if a == name:
            out.append(b)
        elif b == name:
            out.append(a)
    return out


def _drop_node(g: dict, name: str) -> None:
    g["nodes"].pop(name, None)
    for k in [k for k in g["edges"] if name in k.split("\x00")]:
        del g["edges"][k]


def _ref_kind(ref: str) -> str:
    if "/" in ref or re.search(r"\.[A-Za-z]{1,5}$", ref):
        return "code" if re.search(r"\.(py|js|ts|go|rs|java|c|cpp|h)$", ref) else "doc"
    return "concept"


def _extract_refs(text: str) -> list[str]:
    refs: list[str] = []
    for m in _PATH_RE.findall(text):
        if "/" in m or "." in m:
            refs.append(m)
    for m in _IDENT_RE.findall(text):
        if m.lower() not in _STOP and not m.isdigit():
            refs.append(m)
    seen: dict[str, None] = {}
    for r in refs:
        seen.setdefault(r, None)
    return list(seen)[:12]
