"""Session handoff core — save-state (write) and recall-state (resume).

The shared, UI-free engine behind both `rmx save-state` / `rmx recall-state`
(CLI) and the `rmx_save_state` / `rmx_recall_state` MCP tools. Pure data in,
structured dict out — no `click`, no `console`, so the same logic serves a
terminal render and a JSON-RPC tool result without divergence.

What flows through here:

- **save-state** compiles ONE durable GMD handoff memory from the live session:
  git facts (branch / HEAD / commits-ahead / dirty tree), the short-term
  working-memory focus graph (top weighted symbols), the task stack, and links
  to recently-touched memories. It writes that file to the curated-memory dir,
  refreshes the MEMORY.md index, and (by default) PROMOTES a condensed STM
  digest into the durable memory store so the working memory graduates to LTM.

- **recall-state** is the mirror resume pass: it PULLS the latest save-state
  handoff memory, the live session's STM focus digest, the most-recent memories,
  the git state, and daemon health — everything the next instance needs to
  orient before acting.

This module imports only `stm` / `daemon` / `discovery` / `store` (all lazily),
never `cli`, so it is safe to import from the MCP process.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Shell/path tokens that pollute the STM focus graph (Bash hooks extract them
# from command lines). Dropped from the handoff Focus section so it surfaces
# real symbols, not `echo`/`grep`/the home-dir path.
_SS_FOCUS_NOISE = {
    "bash", "sh", "echo", "grep", "rg", "cat", "sed", "awk", "ls", "cd", "cp",
    "mv", "rm", "head", "tail", "git", "python", "python3", "pip", "rmx",
    "rtk", "def", "src", "tests", "true", "false", "null", "none", "self",
    "users", "tholley", "claude_tools", "tmp", "dev", "out", "tee", "sleep",
    "import", "from", "print", "the", "and", "for",
}


def default_memory_dir(repo: Path) -> Path:
    """The curated-memory dir for a project: `~/.claude/projects/<slug>/memory`,
    where the slug is Claude Code's lossy cwd encoding (`/` and `_` → `-`).
    `repo` is the .refmatrix root's parent."""
    slug = str(repo.resolve()).replace("/", "-").replace("_", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


# ---- low-level helpers (moved verbatim from cli.py) ------------------------


def _ss_clean_focus(nodes: list[dict], limit: int = 15) -> list[dict]:
    """Drop shell/path noise; keep code/doc refs and real concepts."""
    out = []
    for nd in nodes:
        name = nd.get("name", "")
        if nd.get("kind") in ("code", "doc"):
            out.append(nd); continue
        if name.lower() in _SS_FOCUS_NOISE:
            continue
        out.append(nd)
        if len(out) >= limit:
            break
    return out[:limit]


def _ss_sh(args: list[str], cwd: Path) -> str:
    """Best-effort subprocess capture; '' on any failure (never raises)."""
    try:
        r = subprocess.run(args, cwd=str(cwd), capture_output=True,
                           text=True, timeout=20)
        return r.stdout.strip()
    except Exception:
        return ""


def _ss_git_facts(repo: Path, since: str | None) -> dict:
    """Branch, HEAD, dirty tree, commits-ahead-of-trunk, and this-session
    commits (since the first STM event, if known)."""
    g = lambda *a: _ss_sh(["git", *a], repo)
    facts = {
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "head": g("log", "-1", "--format=%h %s"),
        "dirty": g("status", "--short"),
        "ahead_base": "", "ahead": "", "session_commits": "",
    }
    for base in ("origin/main", "origin/master", "main", "master"):
        if g("rev-parse", "--verify", "--quiet", base):
            facts["ahead_base"] = base
            facts["ahead"] = g("log", "--oneline", f"{base}..HEAD")
            break
    if since:
        facts["session_commits"] = g("log", "--oneline", f"--since={since}")
    return facts


def _ss_recent_memories(memdir: Path, exclude: str, limit: int = 8) -> list[tuple[str, str]]:
    """(id, title) for the most-recently-touched memory files, newest first."""
    if not memdir.is_dir():
        return []
    files = []
    for p in memdir.glob("*.md"):
        if p.name == "MEMORY.md" or p.stem == exclude:
            continue
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            continue
    files.sort(reverse=True)
    out = []
    for _, p in files[:limit]:
        title = p.stem
        try:
            m = re.search(r'^title:\s*"?(.+?)"?\s*$', p.read_text(), re.M)
            if m:
                title = m.group(1)
        except OSError:
            pass
        out.append((p.stem, title))
    return out


def _ss_frozen_created(path: Path, today: str) -> str:
    """Preserve `created:` across overwrites (MEMORY-RULES: created is frozen)."""
    if path.exists():
        try:
            m = re.search(r"^\s*created:\s*(\S+)", path.read_text(), re.M)
            if m:
                return m.group(1)
        except OSError:
            pass
    return today


def _ss_render(*, mem_id: str, session: str, repo: Path, message: str | None,
               git: dict, focus: dict, tasks: list, recents: list,
               created: str, today: str) -> str:
    """Render the handoff as a GMD memory doc (MEMORY-RULES shape)."""
    head_sha = (git["head"].split() or ["?"])[0]
    headline = message or f"{repo.name} @ {head_sha}"
    L: list[str] = []
    L.append("---")
    L.append('gmd: "0.1"')
    L.append(f"id: {mem_id}")
    L.append(f'title: "Save-state {today}: {headline}"')
    L.append(f'tags: ["session:{session}"]')
    L.append("metadata:")
    L.append("  node_type: memory")
    L.append("  type: session/recall-state")
    L.append(f"  originSessionId: {session}")
    L.append(f"  created: {created}")
    L.append(f"  updated: {today}")
    L.append("---")
    L.append("")
    L.append(f"# Save-state {today}: {headline} {{#root}}")
    L.append("")
    if message:
        L.append(message)
        L.append("")

    L.append("## Session {#session}")
    L.append("")
    L.append(f"- branch **{git['branch'] or '?'}** · HEAD `{git['head'] or '?'}`")
    if git["ahead_base"]:
        n = len([x for x in git["ahead"].splitlines() if x.strip()])
        L.append(f"- **{n}** commit(s) ahead of `{git['ahead_base']}`"
                 + ("" if n else " — in sync"))
    L.append(f"- working tree: {'**dirty**' if git['dirty'] else 'clean'}")
    L.append("")

    if git["session_commits"] or git["ahead"]:
        L.append("## Git activity {#git}")
        L.append("")
        body = git["session_commits"] or git["ahead"]
        label = "this session" if git["session_commits"] else f"ahead of {git['ahead_base']}"
        L.append(f"Commits ({label}):")
        L.append("")
        L.append("```")
        L.append(body or "(none)")
        L.append("```")
        if git["dirty"]:
            L.append("")
            L.append("Uncommitted:")
            L.append("")
            L.append("```")
            L.append(git["dirty"])
            L.append("```")
        L.append("")

    nodes = _ss_clean_focus(focus.get("nodes", []))
    if nodes:
        L.append("## Focus {#focus}")
        L.append("")
        L.append(f"Top of the working-memory graph ({focus.get('events', 0)} events):")
        L.append("")
        for nd in nodes:
            L.append(f"- `{nd['name']}` [{nd['kind']}] ×{nd.get('count', 0)} "
                     f"(w={nd['weight']})")
        L.append("")

    if tasks:
        L.append("## Tasks {#tasks}")
        L.append("")
        for i, t in enumerate(reversed(tasks)):
            mark = "▸" if i == 0 else " "
            L.append(f"- {mark} {t['desc']}  ({t.get('ts', '')})")
        L.append("")

    if recents:
        L.append("## Recent memories {#memories}")
        L.append("")
        for mid, title in recents:
            L.append(f"- [[{mid}]] — {title}")
        L.append("")

    L.append("rel: realizes -> [[feedback_save_state_means_handoff]]")
    L.append("rel: related-to -> [[feedback_recall_state_means_resume]]")
    L.append("")
    return "\n".join(L)


def _ss_update_index(memdir: Path, mem_id: str, title: str, hook: str) -> None:
    """Add/refresh the one-line MEMORY.md index entry for this memory."""
    idx = memdir / "MEMORY.md"
    line = f"- [{title}]({mem_id}.md) — {hook}"
    try:
        lines = idx.read_text().splitlines() if idx.exists() else []
    except OSError:
        lines = []
    out, replaced = [], False
    needle = f"]({mem_id}.md)"
    for ln in lines:
        if needle in ln:
            out.append(line); replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(line)
    idx.write_text("\n".join(out) + "\n")


def _focus_digest(s) -> str:
    """Condense a session's STM — topics, milestones, intent arc, touched
    files — into a compact markdown digest."""
    from refmatrix import stm as stm_mod
    g = s.focus_graph(top=60)
    events = s.all_events()
    weight = {n["name"]: n["weight"] for n in g["nodes"]}
    clean = {"nodes": [n for n in g["nodes"]
                       if n["name"].lower() not in _SS_FOCUS_NOISE],
             "edges": g["edges"]}
    clusters = stm_mod.cluster_focus(clean)
    inputs = [e for e in events if e.get("kind") == "input"]
    gits = [e for e in events if e.get("kind") == "git"]
    files = [n["name"] for n in clean["nodes"] if n["kind"] in ("code", "doc")][:10]
    span = f"{events[0]['ts']} → {events[-1]['ts']}" if events else ""
    L = [f"# Session summary — {s.session}", "",
         f"{len(events)} events · {span}", ""]
    # Top-N focus nodes in strength (weight) order — the session's heaviest
    # symbols, ranked. clean["nodes"] is already weight-sorted by focus_graph.
    topn = [{"name": n["name"], "kind": n["kind"], "weight": n["weight"]}
            for n in clean["nodes"][:10]]
    if topn:
        L.append("## Top (by strength)")
        for i, n in enumerate(topn, 1):
            L.append(f"{i}. `{n['name']}` [{n['kind']}] w={n['weight']}")
        L.append("")
    if clusters:
        L.append("## Topics worked on")
        for c in clusters:
            members = sorted(c, key=lambda n: weight.get(n, 0), reverse=True)
            L.append(f"- **{members[0]}** — {', '.join(members[:6])}")
        L.append("")
    if gits:
        L.append("## Milestones")
        for e in gits:
            L.append(f"- {e['terse']}")
        L.append("")
    if files:
        L.append("## Touched")
        L.append("- " + ", ".join(f"`{f}`" for f in files))
        L.append("")
    if inputs:
        L.append("## Arc")
        L.append(f"- first: {inputs[0]['terse'][:120]}")
        L.append(f"- last: {inputs[-1]['terse'][:120]}")
    return "\n".join(L)


# ---- promote: graduate the condensed STM digest to durable memory ----------


def _promote_digest(root: Path, s) -> dict:
    """Condense the session STM and write it to the durable memory store
    (daemon-routed; in-proc Store fallback when the daemon is down). Returns
    {"name", "id"} on success or {"error"} — never raises."""
    from refmatrix import daemon as daemon_mod, discovery
    slug = re.sub(r"[^A-Za-z0-9]+", "", s.session)[:12] or "default"
    name = f"focus_summary_{slug}"
    digest = _focus_digest(s)
    part = discovery.store_name(root)
    args = {"name": name, "content": digest, "mtype": "session/digest",
            "tags": [f"session:{s.session}", "summary"],
            "metadata": {"title": f"Session summary {s.session[:8]}"},
            "protected": False, "partition": part}
    try:
        if daemon_mod.ping(root):
            r = daemon_mod.call(root, "memory_add", args, timeout=30.0)
            if not r.get("ok"):
                return {"error": r.get("error", "daemon error"), "name": name}
            return {"name": name, "id": r.get("result", {}).get("id")}
        from refmatrix.store import Store
        st = Store(root)
        with st.with_partition(part):
            eid = st.add_memory(name=name, content=digest,
                                mtype="session/digest",
                                tags=[f"session:{s.session}", "summary"],
                                protected=False)
        return {"name": name, "id": eid}
    except Exception as e:  # noqa: BLE001 — promote is best-effort
        return {"error": f"{type(e).__name__}: {e}", "name": name}


# ---- save-state core -------------------------------------------------------


def compose_save_state(s, root: Path, *, repo: Path, memdir: Path, today: str,
                       message: str | None = None, promote: bool = True,
                       dry_run: bool = False) -> dict:
    """Compile + persist the session handoff memory. `s` is a live Stm.

    Returns a structured result the caller renders. Side effects (unless
    dry_run): writes the GMD handoff file, refreshes the MEMORY.md index, and
    (when promote) writes the condensed STM digest to durable memory.
    """
    events = s.all_events()
    focus = s.focus_graph(top=20)
    tasks = s.task_list()
    since = events[0]["ts"] if events else None
    git = _ss_git_facts(repo, since)

    sess_slug = re.sub(r"[^A-Za-z0-9]+", "", s.session)[:12] or "default"
    mem_id = f"savestate_{sess_slug}"
    target = memdir / f"{mem_id}.md"
    created = _ss_frozen_created(target, today)
    recents = _ss_recent_memories(memdir, exclude=mem_id)

    doc = _ss_render(mem_id=mem_id, session=s.session, repo=repo,
                     message=message, git=git, focus=focus, tasks=tasks,
                     recents=recents, created=created, today=today)

    head_sha = (git["head"].split() or ["?"])[0]
    result = {
        "mem_id": mem_id, "target": str(target), "session": s.session,
        "events": len(events), "doc": doc, "dry_run": dry_run,
        "branch": git["branch"], "head": git["head"],
        "dirty": bool(git["dirty"]), "promoted": None,
        "memdir": str(memdir),
    }
    if dry_run:
        return result

    memdir.mkdir(parents=True, exist_ok=True)
    target.write_text(doc)
    hook = (message or f"{repo.name} @ {head_sha}")[:90]
    title = f"Save-state {today}: {message or repo.name + ' @ ' + head_sha}"
    _ss_update_index(memdir, mem_id, title, hook)

    if promote:
        result["promoted"] = _promote_digest(root, s)
    return result


def finalize_save_state(s, root: Path, result: dict, *, repo: Path,
                        lint: bool = True, sync: bool = True) -> dict:
    """Post-compose steps EVERY save-state caller needs (CLI and MCP): GMD
    lint of the written handoff file, filing the promoted digest under the
    active subject (`part-of`) so the subject index reaches it, and — the
    memory bridge — `ingest-gmd --as-memory` over the whole curated-memory
    dir so the handoff and every memory file written this session are in
    the store before the next SessionStart recall. Before 2026-09-06 lint +
    filing lived only in the CLI command, so an MCP save-state promoted an
    orphaned digest (parity audit finding 7). Before 2026-09-14 NOTHING ran
    the bridge: memory files sat on disk for ten days while
    `memory recall --session-start` reported an empty window.

    Returns {"lint": str | None, "filed_subject": str | None,
    "sync": dict | None}; best-effort throughout — a lint, filing, or bridge
    failure never breaks the handoff, but the bridge failure is returned in
    `sync["error"]` for the caller to surface, never swallowed."""
    out: dict = {"lint": None, "filed_subject": None, "sync": None}
    if result.get("dry_run"):
        return out
    if sync:
        memdir = result.get("memdir")
        target = result.get("target")
        if not memdir and target:
            memdir = Path(target).parent
        if memdir:
            from refmatrix.cli import _sync_memory_dir  # lazy: cli->handoff cycle
            out["sync"] = _sync_memory_dir(Path(memdir))
    if lint:
        lint_py = Path.home() / "claude_tools" / "gmd" / "lint.py"
        target = result.get("target")
        if lint_py.exists() and target:
            out["lint"] = _ss_sh(["python3", str(lint_py), str(target)], repo)
    promoted = result.get("promoted") or {}
    leaf = promoted.get("id") if not promoted.get("error") else None
    if leaf:
        subj = None
        try:
            subj = s.get_subject()
        except Exception:
            subj = None
        if subj:
            label = subj.get("label") or subj.get("subject")
            try:
                # Lazy import breaks the cli->handoff import cycle; these
                # helpers carry the partition injection + daemon-or-inproc
                # routing that a bare daemon call here would get wrong.
                from refmatrix.cli import _subject_link, _subject_upsert
                sid = _subject_upsert(label)
                if sid:
                    _subject_link(int(leaf), int(sid))
                    out["filed_subject"] = label
            except Exception:
                pass
    return out


# ---- recall-state core -----------------------------------------------------


def _latest_savestate(memdir: Path, *, head_chars: int = 1800) -> dict | None:
    """The most-recent save-state handoff memory file (id + bounded body,
    frontmatter stripped). This is the prior session's durable handoff — the
    primary thing recall-state pulls.

    The body is capped to `head_chars` (the current-state header — arc, git,
    resume point — is front-loaded by `_ss_render`) with a pointer to the full
    file, so recall-state stays a thin resume signal instead of re-dumping a
    multi-KB (and growing) handoff inline every time (cliquedb UX report
    2026-07-09). `truncated` flags when the tail was elided; full via
    `rmx memory get <id>`."""
    if not memdir.is_dir():
        return None
    cands = sorted(memdir.glob("savestate_*.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        return None
    p = cands[0]
    try:
        txt = p.read_text()
    except OSError:
        return None
    body = re.sub(r"^---\n.*?\n---\n", "", txt, count=1, flags=re.S).strip()
    truncated = len(body) > head_chars
    if truncated:
        body = (body[:head_chars].rstrip() +
                f"\n\n… [truncated — full handoff: `rmx memory get {p.stem}`]")
    return {"id": p.stem, "path": str(p), "body": body, "truncated": truncated}


def compose_recall_state(s, root: Path, *, repo: Path, memdir: Path) -> dict:
    """Pull everything needed to resume: the latest save-state handoff, the
    live STM focus digest, recent memories, git state, and daemon health.

    `s` is a live Stm for the active session. Returns a structured dict; the
    caller renders the resume report. Read-only — writes nothing.
    """
    from refmatrix import daemon as daemon_mod

    events = s.all_events()
    since = events[0]["ts"] if events else None
    git = _ss_git_facts(repo, since)

    savestate = _latest_savestate(memdir)
    stm_digest = _focus_digest(s) if events else None
    recents = _ss_recent_memories(memdir, exclude="")

    pid = daemon_mod.read_pid(root)
    daemon_info = {
        "running": bool(pid) and daemon_mod.ping(root),
        "pid": pid,
    }

    anomalies: list[str] = []
    if git["dirty"]:
        anomalies.append("working tree is dirty (uncommitted changes)")
    if git["ahead_base"]:
        n = len([x for x in git["ahead"].splitlines() if x.strip()])
        if n:
            anomalies.append(f"{n} commit(s) ahead of {git['ahead_base']} "
                             f"(unmerged/undeployed?)")
    if pid and not daemon_info["running"]:
        anomalies.append(f"daemon pid {pid} present but socket unreachable (stale)")

    return {
        "session": s.session,
        "events": len(events),
        "git": git,
        "savestate": savestate,
        "stm_digest": stm_digest,
        "recent_memories": recents,
        "daemon": daemon_info,
        "anomalies": anomalies,
    }
