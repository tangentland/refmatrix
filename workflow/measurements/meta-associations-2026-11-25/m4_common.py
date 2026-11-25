"""M4 shared loaders: transcripts -> per-thread tool timelines, recall-events -> query units.

Why: the seven meta-association candidates (docs/architecture/explorations/meta-associations.md,
pre-registered 2026-11-25 at 82fb7997) all need the same join: what the retrieval returned for a
query, and what the agent touched next. Everything here reads COPIES under M4_ROOT (a short
mkdtemp root holding read-only clones); nothing here writes outside M4_ROOT/work, and nothing raw
(prompt text, query text, tool output) is ever written into the repo.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

M4_ROOT = Path(os.environ["M4_ROOT"])
WORK = M4_ROOT / "work"
WORK.mkdir(exist_ok=True)
REPO = Path(os.environ.get("M4_REPO", "/Volumes/littlebig/refmatrix-m4"))
HOME = str(Path.home())
MEM_PREFIX = f"{HOME}/.claude/projects/-{HOME[1:].replace('/', '-')}-claude-tools-refmatrix/memory/"
REPO_PREFIXES = (f"{HOME}/claude_tools/refmatrix/", f"{HOME}/refmatrix/")
LB = re.compile(r"^/Volumes/littlebig/[^/]+/")


def h(s: str) -> str:
    """Hashed id for anything that would otherwise be raw text in the doc."""
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def ts_of(s: str) -> float:
    s = s.replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def repo_files() -> set[str]:
    cache = WORK / "repo_files.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    out = subprocess.run(["git", "-C", str(REPO), "log", "--all", "--name-only", "--format="],
                         capture_output=True, text=True, check=True).stdout
    files = {l for l in out.splitlines() if l.strip()}
    cache.write_bytes(pickle.dumps(files))
    return files


def memory_stems() -> set[str]:
    stems = set()
    for p in (M4_ROOT / "memory").rglob("*.md"):
        if p.name != "MEMORY.md":
            stems.add(p.stem)
    return stems


_RF = None
_MS = None


def key_of_path(p: str) -> str | None:
    """Normalise a path to a file key, or None (pre-registration #defs)."""
    global _RF, _MS
    if _RF is None:
        _RF = repo_files()
        _MS = memory_stems()
    p = p.strip().strip("'\"`,;()[]")
    p = re.sub(r":\d+(?::\d+)?$", "", p)  # path:line
    if not p:
        return None
    if p.startswith(MEM_PREFIX) or "/memory/" in p and p.endswith(".md") and "claude-tools-refmatrix" in p:
        stem = Path(p).stem
        return f"memory/{stem}" if stem in _MS else None
    rel = None
    for pre in REPO_PREFIXES:
        if p.startswith(pre):
            rel = p[len(pre):]
            break
    if rel is None:
        m = LB.match(p)
        if m:
            rel = p[m.end():]
    if rel is None and not p.startswith("/"):
        rel = p[2:] if p.startswith("./") else p
    if rel is None:
        return None
    return rel if rel in _RF else None


HEREDOC = re.compile(r"<<-?\s*'?\"?(\w+)'?\"?.*", re.S)


def bash_keys(cmd: str) -> list[str]:
    """bash_path touches: path tokens resolving to a repo/memory file. Heredoc bodies and git
    commands are not tokenised (r12 pilot matcher change 4)."""
    cmd = HEREDOC.sub("", cmd)
    keys = []
    for part in re.split(r"&&|\|\||;|\|", cmd):
        part = part.strip()
        if not part or part.startswith("git ") or " git " in part[:12]:
            continue
        try:
            toks = shlex.split(part, posix=True)
        except ValueError:
            toks = part.split()
        for t in toks:
            if "/" not in t and not t.endswith((".py", ".md")):
                continue
            k = key_of_path(t)
            if k:
                keys.append(k)
    return keys


CTX = re.compile(r"(?:rmx|rmx-master)\s+(?:context|memory\s+recall|memory\s+search|search|query)\s+(.+?)(?:\s+--|\s*$|\s*\||\s*2>|\s*&&)")


def load_threads() -> dict:
    """{(session, thread): [call dicts]} plus prompts {session: [(ts, text)]} (main loop)."""
    cache = WORK / "threads.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    tx = M4_ROOT / "tx"
    threads: dict = defaultdict(list)
    prompts: dict = defaultdict(list)
    files = []
    for f in sorted(tx.glob("*.jsonl")):
        files.append((f.stem, "main", f))
    for d in sorted(p for p in tx.iterdir() if p.is_dir()):
        for f in sorted((d / "subagents").glob("agent-*.jsonl")):
            files.append((d.name, f.stem, f))
    for sess, thread, f in files:
        pending = {}
        for line in open(f, errors="replace"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            if t not in ("assistant", "user"):
                continue
            msg = d.get("message") or {}
            content = msg.get("content")
            ts = d.get("timestamp")
            if not ts:
                continue
            tsv = ts_of(ts)
            if t == "user" and thread == "main" and not d.get("isSidechain"):
                text = None
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    if any(c.get("type") == "tool_result" for c in content if isinstance(c, dict)):
                        text = None
                    else:
                        text = " ".join(c.get("text", "") for c in content
                                        if isinstance(c, dict) and c.get("type") == "text")
                if text and not d.get("isMeta") and not text.startswith(("<command-", "<local-command",
                                                                         "<task-notification",
                                                                         "<teammate-message")):
                    prompts[sess].append((tsv, text))
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use":
                    name = c.get("name", "")
                    inp = c.get("input") or {}
                    call = {"ts": tsv, "tool": name, "keys": [], "edit": False, "ctx": None,
                            "cmd": None, "offset": None, "limit": None, "path": None,
                            "err": None}
                    if name in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"):
                        fp = inp.get("file_path") or inp.get("notebook_path") or ""
                        k = key_of_path(fp)
                        call["path"] = fp
                        if k:
                            call["keys"] = [k]
                        call["edit"] = name != "Read"
                        call["offset"] = inp.get("offset")
                        call["limit"] = inp.get("limit")
                    elif name == "Bash":
                        cmd = inp.get("command", "") or ""
                        call["cmd"] = cmd
                        call["keys"] = bash_keys(cmd)
                        m = CTX.search(cmd)
                        if m:
                            arg = m.group(1).strip().strip("'\"")
                            call["ctx"] = arg
                            k = key_of_path(arg.split()[0]) if arg else None
                            if k:
                                call["keys"].append(k)
                    elif name.startswith("mcp__refmatrix__"):
                        call["ctx"] = str(inp.get("query") or inp.get("name") or inp.get("symbol")
                                          or inp.get("q") or "") or None
                    threads[(sess, thread)].append(call)
                    pending[c.get("id")] = call
                elif c.get("type") == "tool_result":
                    call = pending.get(c.get("tool_use_id"))
                    if call is None:
                        continue
                    is_err = c.get("is_error") in (True, "True", "true")
                    if is_err:
                        body = c.get("content")
                        if isinstance(body, list):
                            body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                        call["err"] = str(body or "")[:2000]
    for k in threads:
        threads[k].sort(key=lambda c: c["ts"])
        for i, c in enumerate(threads[k]):
            c["i"] = i
    for s in prompts:
        prompts[s].sort()
    out = {"threads": dict(threads), "prompts": dict(prompts)}
    cache.write_bytes(pickle.dumps(out))
    return out


def gmd_id_map() -> dict[str, str]:
    """GMD doc id -> file key, for concept rows named `doc-id#anchor`."""
    cache = WORK / "gmd_ids.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    m: dict[str, str] = {}
    idre = re.compile(r"^id:\s*\"?([^\"\n]+)\"?\s*$", re.M)
    for root, prefix in ((REPO, ""), (M4_ROOT / "memory", "memory/")):
        for p in root.rglob("*.md"):
            if ".git" in p.parts or ".venv" in str(p):
                continue
            try:
                head = p.read_text(errors="replace")[:1500]
            except OSError:
                continue
            mm = idre.search(head)
            if not mm:
                continue
            key = f"memory/{p.stem}" if prefix else str(p.relative_to(REPO))
            m[mm.group(1).strip()] = key
    cache.write_bytes(pickle.dumps(m))
    return m


def item_key(row: dict, gid: dict) -> str | None:
    kind, name = row.get("kind"), row.get("name") or ""
    global _MS
    if _MS is None:
        key_of_path("x")
    if kind == "memory":
        return f"memory/{name}" if name in _MS else None
    if kind == "code":
        return key_of_path(name.split("::")[0])
    if kind == "doc":
        return key_of_path(name) or gid.get(name)
    if kind == "concept" and "#" in name:
        return gid.get(name.split("#")[0])
    return None


def load_queries() -> dict:
    """{query_id: {session, ts, channel, invocation, keys:set, rows:[(rank,key,stage)]}}"""
    cache = WORK / "queries.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    gid = gmd_id_map()
    q: dict = {}
    for line in open(M4_ROOT / "recall-events.jsonl"):
        d = json.loads(line)
        if d["stage"] not in ("retrieved", "delivered"):
            continue
        qid = d["query_id"]
        e = q.setdefault(qid, {"session": d["session"], "ts": ts_of(d["ts"]),
                               "channel": d["channel"], "invocation": d["invocation"],
                               "keys": set(), "rows": [], "delivered": set()})
        k = item_key(d, gid)
        if k:
            e["keys"].add(k)
            e["rows"].append((d.get("rank") or 99, k, d["stage"]))
            if d["stage"] == "delivered":
                e["delivered"].add(k)
    cache.write_bytes(pickle.dumps(q))
    return q


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    w = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (c - w, c + w)


if __name__ == "__main__":
    t = load_threads()
    print("threads", len(t["threads"]), "calls", sum(len(v) for v in t["threads"].values()),
          "prompt sessions", len(t["prompts"]), file=sys.stderr)
    q = load_queries()
    print("queries", len(q), "with keys", sum(1 for v in q.values() if v["keys"]), file=sys.stderr)
