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


# ---- registry + schema generation -----------------------------------------


@dataclass
class Verb:
    name: str                    # MCP tool name (rmx_*)
    fn: Callable                 # fn(root: Path, **kwargs) -> dict
    description: str
    schema: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)

    def run(self, root: Path, args: dict) -> dict:
        """Invoke with an MCP-style args dict: unknown keys are ignored so
        transport-level extras (root/project/session already resolved by the
        caller) never crash a verb; known keys map to kwargs."""
        params = set(self.defaults) | {
            p for p in inspect.signature(self.fn).parameters if p != "root"}
        kwargs = {k: v for k, v in args.items() if k in params and v is not None}
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


def verb(name: str, description: str) -> Callable:
    def _register(fn: Callable) -> Callable:
        schema, defaults = _schema_from_signature(fn)
        schema["properties"] = {**schema["properties"], **_TRANSPORT_PROPS}
        VERBS[name] = Verb(name=name, fn=fn, description=description,
                           schema=schema, defaults=defaults)
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


# ---- the verbs -------------------------------------------------------------


@verb("rmx_context",
      "Token-budgeted context bundle for a symbol/concept (anchor + typed "
      "neighbors + helix staleness notes). expand=N adds source lines per "
      "code hit; hit_lines=nums|text lists every hit line per file.")
def context(root: Path, ref: str, *, degree: int = 0, expand: int = 0,
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
      "Recall memories — project store by default (scope=project, matching "
      "the CLI); scope=both adds the global behavior store. session/* cards "
      "are excluded unless exclude_mtype=[].")
def memory_recall(root: Path, *, query: str = "", k: int = 8,
                  scope: typing.Literal["project", "global", "both"] = "project",
                  kinds: list[str] | None = None, fuse: bool = False,
                  rerank: bool | None = None,
                  since_seconds: float | None = None,
                  exclude_mtype: list[str] | None = None) -> dict:
    import fnmatch
    from refmatrix import daemon as daemon_mod, hub as hub_mod
    if exclude_mtype is None:
        exclude_mtype = ["session/*"]

    def _mt_ok(m: dict) -> bool:
        mt = str(m.get("mtype") or "")
        return not any(fnmatch.fnmatch(mt, pat) for pat in exclude_mtype)

    rows: list = []
    if scope in ("project", "both") and daemon_mod.ping(root):
        partition = memory_partition(root)
        if query:
            payload: dict = {"query": query, "k": k,
                             "kinds": kinds or ["memory"],
                             "fuse": fuse, "partition": partition}
            if rerank is not None:
                payload["rerank"] = rerank
            r = daemon_mod.call(root, "memory_recall", payload, timeout=180.0)
            hits = r["result"].get("hits", []) if r.get("ok") else []
            hits = sorted(hits, key=lambda h: (
                h["distance"] if h.get("distance") is not None
                else -(h.get("score") or 0.0)))
            for h in hits[:k]:
                eid = h.get("id") or h.get("entity_id")
                g = daemon_mod.call(root, "memory_get", {
                    "id": eid, "partition": partition}, timeout=30.0)
                if g.get("ok"):
                    m = g["result"].get("memory")
                    if m and _mt_ok(m):
                        m["scope"] = "project"; rows.append(m)
        else:
            r = daemon_mod.call(root, "memory_recent", {
                "since_seconds": since_seconds, "limit": k,
                "partition": partition})
            if r.get("ok"):
                for m in r["result"].get("rows", []):
                    if _mt_ok(m):
                        m["scope"] = "project"; rows.append(m)
    if scope in ("global", "both") and hub_mod.global_store_root().exists():
        g = hub_mod.global_call("memory_search", {"query": query, "limit": k})
        if g.get("ok"):
            for m in g["result"].get("rows", []):
                if _mt_ok(m):
                    m["scope"] = "global"; rows.append(m)
    return {"memories": rows[: k * 2]}


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
      "focus + tasks), promote the STM digest, lint, and file it under the "
      "active subject — identical post-steps to the CLI.")
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
      "alias for `text`.")
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
      "for `label`.")
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
