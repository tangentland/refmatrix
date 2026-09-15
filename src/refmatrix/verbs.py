"""Shared verb layer — ONE typed function per agent-facing capability.

Why this module exists (parity audit 2026-09-06): the CLI and the MCP server
each hand-built payloads for the same daemon ops, so argument names, defaults,
and knob coverage drifted — a dead rmx_query ({"dsl"} vs args["expr"]), a
semantic-less MCP ingest, a partition split-brain. The fix is structural, not
disciplinary:

- Every capability is one `@verb` function. Its SIGNATURE is the single
  source of truth for argument names and defaults.
- The MCP tool schema is GENERATED from that signature (`Verb.schema`); a new
  kwarg is automatically a new tool arg.
- Daemon-op payloads are built in exactly one place (the verb body), so an
  op-arg rename can only be wrong once and is covered by one test.
- The CI parity gate (tests/test_verb_parity.py) asserts the paired click
  command's defaults equal the verb's defaults for every shared parameter,
  so a CLI-side default change that skips the verb fails the build.

Verbs are daemon-routed (the single write/read control point). Surfaces with
richer routing (the CLI's replica-first context read) keep their routing but
MUST build op payloads via the verb's `payload_*` helpers.
"""
from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class VerbError(RuntimeError):
    """Raised when a verb cannot run (daemon down, bad args). MCP wrappers
    render it as {"error": str}; CLI wrappers as a ClickException."""


class VerbArgsError(VerbError, ValueError):
    """A required argument is missing — a caller bug, not a runtime condition.
    Also a ValueError so transport code that reports caller mistakes as
    exceptions (the MCP dispatcher's isError path) sees it as one."""


# ---- registry + schema generation -----------------------------------------


@dataclass
class Verb:
    name: str                    # MCP tool name (rmx_*)
    fn: Callable                 # fn(root: Path, **kwargs) -> dict
    description: str
    schema: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    aliases: dict = field(default_factory=dict)   # tool arg -> verb param

    def run(self, root: Path, args: dict) -> dict:
        """Invoke with an MCP-style args dict: unknown keys are ignored so
        transport-level extras (root/project/session already resolved by the
        caller) never crash a verb; known keys map to kwargs; declared aliases
        (`from` -> `sender`, `note` -> `text`) map onto their param."""
        params = set(self.defaults) | {
            p for p in inspect.signature(self.fn).parameters if p != "root"}
        kwargs: dict = {}
        for k, v in args.items():
            if v is None:
                continue
            k = self.aliases.get(k, k)
            if k in params and k not in kwargs:
                kwargs[k] = v
        missing = [p for p, prm in inspect.signature(self.fn).parameters.items()
                   if p != "root" and prm.default is inspect.Parameter.empty
                   and prm.kind not in (prm.VAR_POSITIONAL, prm.VAR_KEYWORD)
                   and p not in kwargs]
        if missing:
            raise VerbArgsError(
                f"{self.fn.__name__} requires "
                + ", ".join(f"'{m}'" for m in missing)
                + (f" (alias: {', '.join(repr(a) for a, t in self.aliases.items() if t in missing)})"
                   if any(t in missing for t in self.aliases.values()) else ""))
        return self.fn(root, **kwargs)


VERBS: dict[str, Verb] = {}

_PY_TO_JSON = {int: "integer", str: "string", bool: "boolean", float: "number"}


def _json_type(annot) -> dict:
    """Map a Python annotation to a JSON-schema fragment. Conservative: an
    unrecognized annotation becomes {} (any type), never a wrong constraint."""
    origin = typing.get_origin(annot)
    if origin is typing.Literal:
        vals = list(typing.get_args(annot))
        return {"type": "string", "enum": vals}
    if origin in (list, tuple):
        args = typing.get_args(annot)
        item = _json_type(args[0]) if args else {}
        return {"type": "array", "items": item}
    if origin is typing.Union or str(origin) == "types.UnionType":
        non_none = [a for a in typing.get_args(annot) if a is not type(None)]
        if len(non_none) == 1:
            return _json_type(non_none[0])
        return {}
    if annot in _PY_TO_JSON:
        return {"type": _PY_TO_JSON[annot]}
    return {}


def _schema_from_signature(fn: Callable) -> tuple[dict, dict]:
    """(json_schema, defaults) derived from fn's signature. `root` is the
    transport-resolved store root and is excluded; the registrar appends the
    transport extras (root/project/session) uniformly."""
    hints = typing.get_type_hints(fn)
    sig = inspect.signature(fn)
    props: dict = {}
    required: list = []
    defaults: dict = {}
    for pname, p in sig.parameters.items():
        if pname == "root" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        props[pname] = _json_type(hints.get(pname, Any))
        if p.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            defaults[pname] = p.default
    schema = {"type": "object", "properties": props, "required": required}
    return schema, defaults


_TRANSPORT_PROPS = {
    "root": {"type": "string"},
    "project": {"type": "string"},
    "session": {"type": "string"},
}


def verb(name: str, description: str, *,
         aliases: "dict[str, str] | None" = None) -> Callable:
    """Register `fn` as the ONE implementation of tool `name`. `aliases` maps
    an extra tool-arg spelling onto a verb param (`{"from": "sender"}` —
    `from` is a Python keyword; `{"note": "text"}` — a documented convenience).
    The alias is part of the generated schema, and a param that has an alias
    is no longer `required` (either spelling satisfies it)."""
    aliases = dict(aliases or {})

    def _register(fn: Callable) -> Callable:
        schema, defaults = _schema_from_signature(fn)
        for alias, param in aliases.items():
            frag = dict(schema["properties"].get(param) or {})
            frag["description"] = f"alias for {param}"
            schema["properties"][alias] = frag
        aliased_params = set(aliases.values())
        schema["required"] = [r for r in schema.get("required", [])
                              if r not in aliased_params]
        schema["properties"] = {**schema["properties"], **_TRANSPORT_PROPS}
        VERBS[name] = Verb(name=name, fn=fn, description=description,
                           schema=schema, defaults=defaults, aliases=aliases)
        return fn
    return _register


# ---- shared plumbing -------------------------------------------------------


def _call(root: Path, op: str, payload: dict, *, timeout: float = 60.0) -> dict:
    from refmatrix import daemon as daemon_mod
    if not daemon_mod.ping(root):
        raise VerbError(f"daemon not running for {root}")
    r = daemon_mod.call(root, op, payload, timeout=timeout)
    if not r.get("ok"):
        raise VerbError(str(r.get("error")))
    return r.get("result", {})


def memory_partition(root: Path) -> str:
    """Legacy-aware memory partition (memory-<project> pre-merge, else the
    project partition). THE routing every memory verb must use — one handler
    skipping it caused the 0.21.1 / 0.25.x / 2026-09-06 split-brain family."""
    from refmatrix import daemon as daemon_mod, discovery
    project = discovery.store_name(root)
    legacy = f"memory-{project}"
    try:
        if daemon_mod.ping(root):
            r = daemon_mod.call(root, "partition_list", {}, timeout=10.0)
            if r.get("ok") and any(row.get("name") == legacy
                                   for row in r["result"].get("rows", [])):
                return legacy
    except Exception:
        pass
    return project


# ---- payload builders (shared by verbs AND bespoke CLI routing) ------------


def payload_context(ref: str, *, degree: int = 0, expand: int = 0,
                    hit_lines: str = "first", max_entities: int | None = None,
                    max_tokens: int | None = None, linkage: str | None = None,
                    fuse: bool = False, strict: bool = False,
                    include_sessions: bool = False,
                    grep_backstop: bool = True, fmt: str = "json") -> dict:
    """The daemon `context` op payload — the one place its arg names exist."""
    payload = {
        "ref": ref, "format": fmt, "degree": degree, "expand": expand,
        "hit_lines": hit_lines, "fuse": fuse, "strict": strict,
        "include_sessions": include_sessions, "grep_backstop": grep_backstop,
        "entities_explicit": max_entities is not None,
        "tokens_explicit": max_tokens is not None,
    }
    if max_entities is not None:
        payload["max_entities"] = max_entities
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if linkage:
        payload["linkages"] = [linkage]
    return payload


def payload_query(dsl: str) -> dict:
    """The daemon `query` op payload. The op reads `expr` — sending `dsl`
    was the parity audit's finding 1 (a dead tool from day one)."""
    return {"expr": dsl}


_DURATION_UNITS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0, "w": 604800.0}


def parse_duration(text: str) -> float:
    """`30m`, `1h`, `7d`, `2w` (or bare seconds) -> seconds. VerbError on junk."""
    t = str(text).strip().lower()
    if not t:
        raise VerbError("empty duration")
    if t[-1] in _DURATION_UNITS:
        try:
            return float(t[:-1]) * _DURATION_UNITS[t[-1]]
        except ValueError as e:
            raise VerbError(f"bad duration {text!r}") from e
    try:
        return float(t)
    except ValueError as e:
        raise VerbError(f"bad duration {text!r}; use 30m / 1h / 7d / bare seconds") from e


def mt_excluded(mtype: "str | None", patterns) -> bool:
    """True when `mtype` matches any glob in `patterns` (fnmatchcase, so
    `session/*` hides session/recall-state + session/digest)."""
    if not patterns:
        return False
    from fnmatch import fnmatchcase
    m = mtype or ""
    return any(fnmatchcase(m, pat) for pat in patterns)


def global_recall_rows(q: "str | None", *, k: int, recent: bool,
                       since_s: "float | None") -> list[dict]:
    """Rows from the hub-owned global behavior store, routed through ITS
    daemon (never a direct Store open). Lexical/recent only — no embedder —
    so the always-on hooks stay cheap."""
    from refmatrix import hub as hub_mod
    if not hub_mod.global_store_root().exists():
        return []
    if recent:
        op, args = "memory_recent", {"since_seconds": since_s, "limit": k}
    elif q:
        op, args = "memory_search", {"query": q, "limit": k}
    else:
        return []
    try:
        resp = hub_mod.global_call(op, args, timeout=30.0)
    except Exception:
        return []
    rows = resp.get("result", {}).get("rows", []) if resp.get("ok") else []
    for r in rows:
        r["scope"] = "global"
    return rows


def merge_scope(project_rows: list, global_rows: list, k: int, scope: str) -> list:
    """Combine project + global recall. `both` round-robins so global behavior
    memories are guaranteed representation, not truncated behind project hits."""
    for r in project_rows:
        r.setdefault("scope", "project")
    for r in global_rows:
        r.setdefault("scope", "global")
    if scope == "global":
        return global_rows[:k]
    if scope == "project":
        return project_rows[:k]
    out, seen = [], set()
    pi = gi = 0
    while len(out) < k and (pi < len(project_rows) or gi < len(global_rows)):
        if pi < len(project_rows):
            r = project_rows[pi]; pi += 1
            if r.get("name") not in seen:
                seen.add(r.get("name")); out.append(r)
        if len(out) >= k:
            break
        if gi < len(global_rows):
            r = global_rows[gi]; gi += 1
            if r.get("name") not in seen:
                seen.add(r.get("name")); out.append(r)
    return out


def attach_context(root: Path, rows: list[dict], degree: int,
                   partition: "str | None" = None) -> list[dict]:
    """degree>0: stash a rendered context bundle on each row (`row["context"]`)
    via the daemon `context` op — the same op `rmx context` uses. Best-effort
    per row; daemon down leaves `context` unset."""
    if degree <= 0:
        return rows
    from refmatrix import daemon as daemon_mod
    if not daemon_mod.ping(root):
        return rows
    for row in rows:
        try:
            payload = {"ref": row["name"], "format": "text", "degree": degree,
                       "entities_explicit": False, "tokens_explicit": False}
            if partition:
                payload["partition"] = partition
            resp = daemon_mod.call(root, "context", payload, timeout=120.0)
            row["context"] = resp.get("result", {}).get("body") if resp.get("ok") else None
        except Exception:
            row["context"] = None
    return rows


def payload_memory_recall(query: str, *, k: int, kinds: "list[str] | None",
                          fuse: bool, rerank: "bool | None",
                          partition: "str | None" = None) -> dict:
    """The daemon `memory_recall` op payload — one place for its arg names."""
    payload: dict = {"query": query, "k": k, "kinds": list(kinds or ["memory"]),
                     "fuse": bool(fuse)}
    if rerank is not None:
        payload["rerank"] = bool(rerank)
    if partition:
        payload["partition"] = partition
    return payload


def resolve_session(root: Path, session: "str | None") -> str:
    """Explicit session, else the most-recently-written STM ring (the active
    Claude session a spawned process cannot name), else the default id.
    Reads and writes MUST resolve identically."""
    from refmatrix import stm as stm_mod
    return session or stm_mod.latest_session(root) or stm_mod.session_id()


# ---- the verbs -------------------------------------------------------------


@verb("rmx_context",
      "Token-budgeted context bundle for a symbol/concept (anchor + typed "
      "neighbors + helix staleness notes). expand=N adds source lines per "
      "code hit; hit_lines=nums|text lists every hit line per file.")
def context(root: Path, ref: str, *, degree: int = 1, expand: int = 0,
            hit_lines: typing.Literal["first", "nums", "text"] = "first",
            max_entities: int | None = None, max_tokens: int | None = None,
            linkage: str | None = None, fuse: bool = False,
            strict: bool = False, include_sessions: bool = False,
            grep_backstop: bool = True) -> dict:
    import json as _json
    from refmatrix import discovery
    payload = payload_context(
        ref, degree=degree, expand=expand, hit_lines=hit_lines,
        max_entities=max_entities, max_tokens=max_tokens, linkage=linkage,
        fuse=fuse, strict=strict, include_sessions=include_sessions,
        grep_backstop=grep_backstop)
    payload["partition"] = discovery.store_name(root)
    result = _call(root, "context", payload, timeout=60.0)
    body = result.get("body")
    if isinstance(body, str):
        try:
            return _json.loads(body)
        except ValueError:
            pass
    return result


@verb("rmx_query",
      "Run a refmatrix DSL query in the current project "
      "(e.g. 'mentions:parser AND defines:parser').")
def query(root: Path, dsl: str) -> dict:
    from refmatrix import discovery
    payload = {**payload_query(dsl), "partition": discovery.store_name(root)}
    return _call(root, "query", payload, timeout=30.0)


@verb("rmx_memory_add",
      "Add or update a durable memory in the project memory store "
      "(daemon-routed write; legacy-aware partition).")
def memory_add(root: Path, name: str, content: str, *,
               mtype: str = "observation",
               tags: list[str] | None = None,
               protect: bool = False) -> dict:
    return _call(root, "memory_add", {
        "name": name, "content": content, "mtype": mtype, "tags": tags,
        "protected": protect, "partition": memory_partition(root),
    }, timeout=30.0)


@verb("rmx_memory_recall",
      "Recall memories. Modes: query (dense ANN), recent=true (newest-first, "
      "since=30m|1h|7d), session_start=true (recent, 7d window, widened to "
      "newest-k when empty), subject=<slug> (leaves filed under a subject). "
      "session/* cards (save-state handoffs, STM digests) are hidden unless "
      "include_session=true or exclude_mtype=[]. scope=both adds the global "
      "behavior store. Pass `project` (name) or `root` to target another store.")
def memory_recall(root: Path, *, query: str = "", k: int = 8,
                  scope: typing.Literal["project", "global", "both"] = "project",
                  kinds: list[str] | None = None, fuse: bool = False,
                  rerank: bool | None = None,
                  since_seconds: float | None = None,
                  since: str | None = None,
                  recent: bool = False, session_start: bool = False,
                  exclude_mtype: list[str] | None = None,
                  include_session: bool = False,
                  subject: str | None = None, degree: int = 0) -> dict:
    """ONE implementation of "which memories come back" for the CLI hook
    modes and the MCP tool (2026-09-14: the session-start default window,
    the widen-when-empty rule and the session/* exclusion lived only in
    cli.py, so agents calling the tool got different answers than the hook).

    Returns {"memories": rows, "mode": "session-start|recent|subject|dense",
    "widened": bool, "since_seconds": float|None}. Daemon-routed; raises
    VerbError when the project store's daemon is down (a surface with a
    lock-free replica may degrade on its own)."""
    from refmatrix import daemon as daemon_mod
    patterns = (list(exclude_mtype) if exclude_mtype is not None
                else ([] if include_session else ["session/*"]))
    widened = False
    since_defaulted = False
    if session_start:
        recent = True
        if since is None and since_seconds is None:
            since_seconds = 7 * 86400.0
            since_defaulted = True
    if since is not None and since_seconds is None:
        since_seconds = parse_duration(since)
    if not (recent or subject or query):
        # MCP contract since 0.21: an empty query means "what is recent".
        recent = True
        mode_hint = "recent"

    def _filt(rows: list[dict]) -> list[dict]:
        return [r for r in rows if not mt_excluded(r.get("mtype"), patterns)]

    want_project = scope in ("project", "both")
    partition = memory_partition(root) if want_project else None
    project_rows: list[dict] = []
    mode = "dense"

    if subject:
        mode = "subject"
        if want_project:
            r = _call(root, "subject_leaves", {"subject": subject, "partition": partition})
            project_rows = _filt(r.get("rows", []))[:k]
    elif recent:
        mode = "session-start" if session_start else "recent"
        if want_project:
            effective_k = k * 10 if patterns else k
            r = _call(root, "memory_recent", {"since_seconds": since_seconds,
                                              "limit": effective_k, "partition": partition})
            project_rows = _filt(r.get("rows", []))[:k]
            if not project_rows and since_defaulted:
                # An empty orient pass is worse than an older one: widen to
                # newest-k regardless of age. An explicit window is honored.
                widened = True
                since_seconds = None
                r = _call(root, "memory_recent", {"since_seconds": None,
                                                  "limit": effective_k, "partition": partition})
                project_rows = _filt(r.get("rows", []))[:k]
    else:
        if want_project:
            if not daemon_mod.ping(root):
                raise VerbError(f"daemon not running for {root}")
            ann_k = k * 3 if patterns else k
            r = _call(root, "memory_recall",
                      payload_memory_recall(query, k=ann_k, kinds=kinds, fuse=fuse,
                                            rerank=rerank, partition=partition),
                      timeout=180.0)
            hits = sorted(r.get("hits", []), key=lambda h: (
                h["distance"] if h.get("distance") is not None
                else -(h.get("score") or 0.0)))
            for h in hits:
                if len(project_rows) >= k:
                    break
                eid = h.get("id") or h.get("entity_id")
                if eid is None:
                    continue
                g = daemon_mod.call(root, "memory_get", {"id": eid, "partition": partition},
                                    timeout=30.0)
                m = g.get("result", {}).get("memory") if g.get("ok") else None
                if m and not mt_excluded(m.get("mtype"), patterns):
                    project_rows.append(m)
    for r in project_rows:
        r["scope"] = "project"

    rows = project_rows
    if scope != "project":
        gk = k * 10 if patterns else k
        grows = _filt(global_recall_rows(
            query or None, k=gk, recent=bool(recent) and not subject,
            since_s=since_seconds))
        rows = merge_scope(project_rows, grows, k, scope)
    rows = attach_context(root, rows, degree, partition)
    return {"memories": rows, "mode": mode, "widened": widened,
            "since_seconds": since_seconds}


@verb("rmx_ingest",
      "Fire-and-poll ingest/embed: enqueues on the daemon, returns a job_id "
      "immediately; poll rmx_ingest_status. mode=embed for dense vectors.")
def ingest(root: Path, *, path: str | None = None,
           mode: typing.Literal["ingest", "embed"] = "ingest",
           source: str = "auto", semantic: bool = True,
           kinds: list[str] | None = None, limit: int | None = None,
           rebuild: bool | None = None,
           partition: str | None = None) -> dict:
    from refmatrix import discovery
    part = partition or discovery.store_name(root)
    if mode == "embed":
        payload: dict = {"partition": part}
        for key, val in (("kinds", kinds), ("limit", limit),
                         ("rebuild", rebuild)):
            if val is not None:
                payload[key] = val
        return _call(root, "embed_start", payload, timeout=30.0)
    # semantic default True matches the CLI: a semantic-less ingest is the
    # 0.48.0 termless-corpus failure ("main path must exercise core
    # mechanisms").
    return _call(root, "ingest_path_start", {
        "path": path or str(Path(root).parent), "source": source,
        "semantic": semantic, "partition": part,
    }, timeout=30.0)


@verb("rmx_save_state",
      "Compile + persist the session handoff (GMD memory: git state + STM "
      "focus + tasks), promote the STM digest, lint, file it under the "
      "active subject, and run the memory bridge (ingest-gmd --as-memory "
      "over the memory dir so the next SessionStart recall sees every "
      "memory file) — identical post-steps to the CLI.")
def save_state(root: Path, *, message: str | None = None,
               promote: bool = True, dry_run: bool = False,
               session: str | None = None) -> dict:
    import time as _time
    from refmatrix import handoff, stm as stm_mod
    repo = Path(root).parent
    sess = session or stm_mod.latest_session(root) or stm_mod.session_id()
    s = stm_mod.Stm(root, sess)
    res = handoff.compose_save_state(
        s, root, repo=repo, memdir=handoff.default_memory_dir(repo),
        today=_time.strftime("%Y-%m-%d"), message=message,
        promote=promote, dry_run=dry_run)
    fin = handoff.finalize_save_state(s, root, res, repo=repo)
    res["lint"] = fin.get("lint")
    res["filed_subject"] = fin.get("filed_subject")
    # Memory bridge outcome — surfaced, not swallowed: an MCP caller sees
    # `sync.error` when the store did not take the handoff.
    res["sync"] = fin.get("sync")
    if not res.get("dry_run"):
        res.pop("doc", None)
    return res


@verb("rmx_focus",
      "Current short-term focus graph + task stack for the project (what is "
      "being worked on right now).")
def focus(root: Path, *, top: int = 20, session: str | None = None) -> dict:
    from refmatrix import stm as stm_mod
    sess = session or stm_mod.latest_session(root) or stm_mod.session_id()
    s = stm_mod.Stm(root, sess)
    return {"graph": s.focus_graph(top=top), "tasks": s.task_list()}


@verb("rmx_focus_note",
      "Record a deliberate reasoning note into the project's short-term "
      "memory — the WHY behind a decision/tradeoff. `note` is an accepted "
      "alias for `text`.", aliases={"note": "text"})
def focus_note(root: Path, text: str, *, session: str | None = None) -> dict:
    from refmatrix import stm as stm_mod
    sess = session or stm_mod.latest_session(root) or stm_mod.session_id()
    s = stm_mod.Stm(root, sess)
    ev = s.record("reason", str(text)[:800])
    return {"noted": True, "session": s.session,
            "refs": ev.get("refs", [])[:6]}


@verb("rmx_change_subject",
      "Set the active subject (named STM partition + durable LTM container) "
      "for this session's thread of work. `subject` is an accepted alias "
      "for `label`.", aliases={"subject": "label"})
def change_subject(root: Path, label: str, *,
                   session: str | None = None) -> dict:
    from refmatrix import daemon as daemon_mod, stm as stm_mod
    sess = session or stm_mod.latest_session(root) or stm_mod.session_id()
    s = stm_mod.Stm(root, sess)
    rec = s.set_subject(label)
    part = memory_partition(root)
    eid = None
    if daemon_mod.ping(root):
        r = daemon_mod.call(root, "subject_upsert",
                            {"label": label, "partition": part}, timeout=30.0)
        eid = r.get("result", {}).get("id") if r.get("ok") else None
    else:
        from refmatrix.store import Store
        s2 = Store(root)
        with s2.with_partition(part):
            eid = s2.upsert_subject(label)["id"]
    return {"subject": rec["subject"], "label": rec["label"], "id": eid,
            "session": s.session}


@verb("rmx_projects",
      "List all refmatrix projects on this machine: name, store root, "
      "daemon + supervision state; footprint=true adds disk usage "
      "(slower — stats every store).")
def projects(root: Path, *, footprint: bool = False) -> dict:
    # `root` is the transport convention; discovery is machine-wide.
    from refmatrix import discovery
    return {"projects": discovery.all_projects(with_footprint=footprint)}


# ---- verbs migrated from mcp.py (plan-3, 2026-09-14): every tool is a verb ----


@verb("rmx_where", "Find where something is across ALL your refmatrix projects + global memory — code, docs, concepts, memories. The 'where are my keys?' tool.")
def where(root: Path, query: str, *, limit: int = 40) -> dict:
    from refmatrix import search as search_mod
    return search_mod.federated_where(query, limit=int(limit))


@verb("rmx_search", "Run a refmatrix DSL query across all projects (e.g. 'mentions:parser AND defines:parser').")
def search(root: Path, dsl: str, *, limit: int = 50) -> dict:
    from refmatrix import search as search_mod
    return search_mod.federated_query(dsl, limit=int(limit))


@verb("rmx_locate", 'Locate full filesystem paths by filename (basename, no path) and/or keywords/concepts, across all live stores.')
def locate(root: Path, *, file: str | None = None,
           keywords: list[str] | None = None, n: int = 10) -> dict:
    from refmatrix import search as search_mod
    return search_mod.federated_locate(file, keywords or [], limit=int(n))


@verb("rmx_task", 'Task pushdown stack for the active session: push, pop, list, current, swap. Snapshots focus on push; restores it on pop (git-stash semantics).')
def task(root: Path, *, action: typing.Literal["push", "pop", "list", "current", "swap"] = "list",
         desc: str | None = None, selector: str | None = None,
         session: str | None = None) -> dict:
    from refmatrix import stm as stm_mod
    s = stm_mod.Stm(root, resolve_session(root, session))
    if action == "push":
        if not desc:
            raise VerbError("task push requires 'desc'")
        return s.task_push(desc)
    if action == "pop":
        return s.task_pop(selector)
    if action == "list":
        return {"tasks": s.task_list()}
    if action == "current":
        return {"current": s.task_current()}
    if action == "swap":
        return s.task_swap()
    raise VerbError(f"unknown task action {action!r}")


@verb("rmx_queues", 'Change-queue visibility: pending sync/stale work per project + refinement-queue depth.')
def queues(root: Path) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        raise VerbError("hub not running — change-queue visibility needs it")
    return hub_mod.rpc("queues").get("result", {})


@verb("rmx_ingest_status", 'Poll an ingest/embed job started by rmx_ingest. Omit job_id to list all jobs; since_seq streams new events.')
def ingest_status(root: Path, *, job_id: str | None = None,
                  since_seq: int | None = None, limit: int | None = None) -> dict:
    payload = {k: v for k, v in (("job_id", job_id), ("since_seq", since_seq),
                                 ("limit", limit)) if v is not None}
    return _call(root, "ingest_gmd_status", payload, timeout=15.0)


@verb("rmx_recall_state", "Recall session state — pull the prior handoff and orient (read-only). Returns: the latest save-state handoff (prior git/focus/tasks/recent-memory links), the live session's STM focus digest (top symbols, topics, milestones, intent arc), recent memories, current git state, daemon health, and anomalies (dirty tree, unmerged/undeployed commits, stale daemon). Mirror of rmx_save_state.")
def recall_state(root: Path, *, session: str | None = None) -> dict:
    from refmatrix import handoff, stm as stm_mod
    repo = Path(root).parent
    s = stm_mod.Stm(root, resolve_session(root, session))
    return handoff.compose_recall_state(s, root, repo=repo,
                                        memdir=handoff.default_memory_dir(repo))


_MEMORY_OPS = {
    "get": "memory_get", "list": "memory_iter", "search": "memory_search",
    "forget": "memory_forget", "reclassify": "memory_reclassify",
    "retag": "memory_retag", "link": "memory_link", "score": "memory_score",
    "bulk_forget": "memory_bulk_forget", "dedup": "memory_dedup",
}


def _memory_payload(action: str, a: dict) -> dict:
    """Daemon-op payload for a memory action; keys mirror the CLI memory
    subcommands (the proven callers) so the op contract stays single-sourced."""
    def keyed():
        return {"id": int(a["id"])} if a.get("id") is not None else {"name": a["name"]}
    if action in ("get", "forget"):
        return keyed()
    if action == "list":
        return {k: a[k] for k in ("mtype", "limit", "tags", "tags_match") if a.get(k) is not None}
    if action == "search":
        p = {"query": a["query"]}
        for k in ("limit", "tags", "tags_match"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "reclassify":
        p = {"to_mtype": a["to_mtype"]}
        for k in ("from_mtype", "like", "names", "dry_run"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "retag":
        p = keyed()
        for k in ("add", "remove", "replace"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "link":
        p = {"src_id": int(a["id"])} if a.get("id") is not None else {"src_name": a["name"]}
        p["linkage"] = a.get("linkage", "related-to")
        p["concept"] = a["concept"]
        if a.get("weight") is not None:
            p["weight"] = a["weight"]
        return p
    if action == "score":
        p = {"concept": a["concept"]}
        for k in ("halflife_days", "cap", "explain"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "bulk_forget":
        p = {"dry_run": bool(a.get("dry_run", False))}
        for k in ("ids", "names", "mtypes"):
            if a.get(k) is not None:
                p[k] = a[k]
        return p
    if action == "dedup":
        return {"dry_run": bool(a.get("dry_run", False))}
    return {}


@verb("rmx_memory", "Full access to the project memory store — parity with the CLI `rmx memory` group. `action` selects the op; pass that op's params alongside.")
def memory(root: Path, action: typing.Literal[
               "recall", "add", "get", "list", "search", "forget", "reclassify",
               "retag", "link", "score", "bulk_forget", "dedup", "promote"], *,
           name: str | None = None, id: int | None = None, content: str | None = None,
           mtype: str | None = None, to_mtype: str | None = None,
           from_mtype: str | None = None, query: str | None = None,
           scope: str | None = None, k: int | None = None, limit: int | None = None,
           tags: list[str] | None = None, tags_match: str | None = None,
           add: list[str] | None = None, remove: list[str] | None = None,
           replace: list[str] | None = None, names: list[str] | None = None,
           ids: list[int] | None = None, mtypes: list[str] | None = None,
           like: str | None = None, concept: str | None = None,
           linkage: str | None = None, weight: float | None = None,
           halflife_days: float | None = None, cap: float | None = None,
           explain: bool | None = None, protect: bool | None = None,
           dry_run: bool | None = None, partition: str | None = None) -> dict:
    """One dispatcher over the CLI `rmx memory` group. recall/add reuse the
    dedicated verbs; promote copies project→global; everything else routes to
    the daemon's memory_* op with the project partition injected."""
    from refmatrix import daemon as daemon_mod, hub as hub_mod
    a = {k: v for k, v in locals().items() if k not in ("root", "action", "daemon_mod", "hub_mod")}
    if action == "recall":
        kw = {k: v for k, v in a.items() if k in ("query", "k", "scope") and v is not None}
        return memory_recall(root, **kw)
    if action == "add":
        if not name or content is None:
            raise VerbError("memory add requires name and content")
        return memory_add(root, name, content, mtype=mtype or "observation",
                          tags=tags, protect=bool(protect))
    part = partition or memory_partition(root)
    if not daemon_mod.ping(root):
        raise VerbError(f"daemon not running for {root}")
    if action == "promote":
        key = {"id": int(id)} if id is not None else {"name": name}
        g0 = daemon_mod.call(root, "memory_get", {**key, "partition": part}, timeout=30.0)
        m = g0.get("result", {}).get("memory") if g0.get("ok") else None
        if not m:
            raise VerbError("no memory matching the id/name")
        tg = list(dict.fromkeys((m.get("tags") or []) + ["behavior"]))
        g = hub_mod.global_call("memory_add", {
            "name": m["name"], "content": m["content"],
            "mtype": m.get("mtype") or "feedback", "tags": tg,
            "metadata": m.get("metadata")})
        if not g.get("ok"):
            raise VerbError(str(g.get("error")))
        return g.get("result", {})
    op = _MEMORY_OPS.get(action)
    if op is None:
        raise VerbError(f"unknown memory action {action!r}")
    try:
        payload = {**_memory_payload(action, a), "partition": part}
    except KeyError as exc:
        raise VerbError(f"missing required arg for {action}: {exc}") from exc
    return _call(root, op, payload, timeout=120.0)


def _bus_sender(root: Path, explicit: "str | None") -> str:
    """explicit `from`/`agent` → $RMX_AGENT → this store's project name.
    Co-located agents share a hostname; the project is the only default that
    tells receivers WHO published."""
    import os
    from refmatrix import discovery
    return explicit or os.environ.get("RMX_AGENT") or discovery.store_name(root)


def _hub_rpc(op: str, args: "dict | None" = None) -> dict:
    from refmatrix import hub as hub_mod
    if not hub_mod.is_running():
        raise VerbError("hub not running")
    return hub_mod.rpc(op, args).get("result", {}) if args is not None else hub_mod.rpc(op).get("result", {})


@verb("rmx_bus_pub", "Publish a message to the agent bus (proj:<name>:<topic> or global:<topic>). `from` defaults to this server's project; pass `reply_to` (a prior message id) to thread a reply.", aliases={"from": "sender"})
def bus_pub(root: Path, channel: str, body: str, *, type: str = "announce",
            sender: str | None = None, project: str | None = None,
            reply_to: str | None = None) -> dict:
    if project is None and channel.startswith("proj:"):
        parts = channel.split(":")
        project = parts[1] if len(parts) > 1 else None
    return _hub_rpc("bus_pub", {"channel": channel, "body": body, "type": type,
                                "from": _bus_sender(root, sender), "project": project,
                                "reply_to": reply_to})


@verb("rmx_bus_history", 'Read recent messages on a bus channel.')
def bus_history(root: Path, channel: str, *, n: int = 20) -> dict:
    return _hub_rpc("bus_history", {"channel": channel, "n": int(n)})


@verb("rmx_bus_channels", 'List live bus channels (with message counts), optionally filtered by a glob like `proj:*` or `proj:cliquedb:*`. Channel discovery for the bus.')
def bus_channels(root: Path, *, glob: str | None = None) -> dict:
    import fnmatch
    chans = _hub_rpc("bus_channels").get("channels", [])
    if glob:
        chans = [c for c in chans if fnmatch.fnmatch(str(c.get("channel", "")), glob)]
    return {"channels": chans}


@verb("rmx_bus_read", 'Read bus messages you have NOT seen yet across matching channels, advancing your read-cursor (unless peek=true). `channels` is a list of patterns (`proj:*`, `global:`, exact); default `*`. Use this instead of bus_history to poll for new messages without re-reading old ones.', aliases={"from": "agent"})
def bus_read(root: Path, *, channels: list[str] | None = None, channel: str | None = None,
             agent: str | None = None, peek: bool = False, n: int | None = None) -> dict:
    chans = channels if channels is not None else ([channel] if channel else ["*"])
    if isinstance(chans, str):
        chans = [chans]
    return _hub_rpc("bus_read", {"agent": _bus_sender(root, agent), "channels": chans,
                                 "peek": bool(peek), "n": n})


@verb("rmx_bus_mark_read", 'Mark a channel read up to a point (default: everything) without returning the messages.', aliases={"from": "agent"})
def bus_mark_read(root: Path, channel: str, *, agent: str | None = None,
                  upto_seq: int | None = None) -> dict:
    return _hub_rpc("bus_mark_read", {"agent": _bus_sender(root, agent),
                                      "channel": channel, "upto_seq": upto_seq})


@verb("rmx_bus_delete", 'Soft-delete a bus message by id — hidden from history/read, recoverable until purge.')
def bus_delete(root: Path, id: str) -> dict:
    return _hub_rpc("bus_delete", {"id": id})


@verb("rmx_bus_archive", 'Archive bus messages (still readable via bus_history status=archived): by `id`, or a whole `channel` (optionally only those with ts < `before_ts`).')
def bus_archive(root: Path, *, id: str | None = None, channel: str | None = None,
                before_ts: float | None = None) -> dict:
    return _hub_rpc("bus_archive", {"id": id, "channel": channel, "before_ts": before_ts})


@verb("rmx_bus_unarchive", 'Restore an archived bus message to active.')
def bus_unarchive(root: Path, id: str) -> dict:
    return _hub_rpc("bus_unarchive", {"id": id})


@verb("rmx_bus_purge", 'Hard-remove bus messages — the only destructive path. Default reaps soft-deleted rows; status=archived reaps the archive; status=all + before_ts prunes old history.')
def bus_purge(root: Path, *, status: str = "deleted", channel: str | None = None,
              before_ts: float | None = None) -> dict:
    return _hub_rpc("bus_purge", {"status": status, "channel": channel, "before_ts": before_ts})


@verb("rmx_bus_stats", 'Bus overview: per-status totals + per-channel breakdown (active/archived/deleted) + your unread counts.', aliases={"from": "agent"})
def bus_stats(root: Path, *, agent: str | None = None) -> dict:
    return _hub_rpc("bus_stats", {"agent": _bus_sender(root, agent)})


# ---- CLI twins (asserted by tests/test_verb_parity.py) --------------------
# verb name -> click command path. None = MCP-only, with the reason in MCP_ONLY.
CLI_MAP: dict[str, "tuple[str, ...] | None"] = {
    "rmx_context": ("context",),
    "rmx_query": ("query",),
    "rmx_memory_add": ("memory", "add"),
    "rmx_memory_recall": ("memory", "recall"),
    "rmx_ingest": ("ingest",),
    "rmx_save_state": ("save-state",),
    "rmx_focus": ("focus", "context"),
    "rmx_focus_note": ("focus", "note"),
    "rmx_change_subject": ("focus", "change-subject"),
    "rmx_projects": ("projects",),
    "rmx_where": None,
    "rmx_search": None,
    "rmx_locate": ("locate",),
    "rmx_task": ("task", "list"),
    "rmx_queues": ("hub", "status"),
    "rmx_ingest_status": ("ingest-status",),
    "rmx_recall_state": ("recall-state",),
    "rmx_memory": ("memory", "get"),
    "rmx_bus_pub": ("bus", "pub"),
    "rmx_bus_history": ("bus", "history"),
    "rmx_bus_channels": ("bus", "channels"),
    "rmx_bus_read": ("bus", "read"),
    "rmx_bus_mark_read": ("bus", "mark-read"),
    "rmx_bus_delete": ("bus", "delete"),
    "rmx_bus_archive": ("bus", "archive"),
    "rmx_bus_unarchive": ("bus", "unarchive"),
    "rmx_bus_purge": ("bus", "purge"),
    "rmx_bus_stats": ("bus", "stats"),
}
MCP_ONLY: dict[str, str] = {
    "rmx_where": "federated cross-store lookup for agents; the CLI equivalent "
                 "is `rmx locate` (paths) + per-store `rmx context`",
    "rmx_search": "federated DSL over every live store; the CLI `query` is "
                  "single-store by design",
}
