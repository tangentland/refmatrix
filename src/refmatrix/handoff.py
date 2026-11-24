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

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
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


def _ss_sh(args: list[str], cwd: Path, *, timeout: float = 20) -> str:
    """Best-effort subprocess capture; '' on any failure (never raises)."""
    try:
        r = subprocess.run(args, cwd=str(cwd), capture_output=True,
                           text=True, timeout=max(0.1, float(timeout)))
        return r.stdout.strip()
    except Exception:
        return ""


_SS_TRUNK_FALLBACK = ("origin/main", "origin/master", "main", "master")


def _ss_git_run(repo: Path, *args: str) -> tuple[int | None, str, str]:
    """(exit code, stdout, stderr) of one git call; exit None when git could not run
    (OSError, or the 20 s timeout). Unlike `_ss_sh` it lets the caller tell "not
    found" from "failed" -- the trunk reads need that (bug-225 r2, ruling L96)."""
    try:
        r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return None, "", f"{type(e).__name__}: {e}"
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _ss_git_failure(args: tuple[str, ...], rc: int | None, out: str, err: str) -> str:
    """One way to say a git call failed: the command, then how, in git's own words
    (bug-225 r3: "is corrupt" / "expected commit type" name the cause; a paraphrase
    would not). Multi-line stderr is joined with " / " so it stays one doc line."""
    cmd = f"`git {' '.join(args)}`"
    text = " / ".join(ln.strip() for ln in (err or out).splitlines() if ln.strip())
    if rc is None:
        return f"{cmd} could not run: {text}"
    return f"{cmd} exited {rc}: {text or '(no output)'}"


def _ss_origin_head(repo: Path) -> tuple[str, str]:
    """(short ref origin/HEAD names, error) -- `("", "")` when origin/HEAD is unset.

    Why (bug-225, 2026-11-14): the trunk was guessed from a fixed name list, so in
    atlftpd, whose trunk is `develop`, the handoff reported 24 commits ahead of
    `origin/master` instead of 12 ahead of `origin/develop`. `refs/remotes/origin/HEAD`
    (set by `git clone`, changed per repo with `git remote set-head`) is the repo's own
    answer. `--quiet` makes "not a symbolic ref" exit 1 with no output: that is the
    unset case, and the list decides without a word. Any other result -- another
    exit, exit 1 WITH stderr, git failing to run -- is NOT unset: it is returned as
    an error the composers print (same rule as the candidate verify, bug-225 r3).
    The name is not verified here; `_ss_trunk` verifies it like every candidate.
    """
    args = ("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    rc, out, err = _ss_git_run(repo, *args)
    if rc == 0:
        return out, ""
    if rc == 1 and not err:
        return "", ""
    return "", _ss_git_failure(args, rc, out, err)


def _ss_trunk(repo: Path, facts: dict) -> None:
    """Pick the trunk and measure commits ahead of it, into `facts`.

    Candidates: the ref origin/HEAD names, then `_SS_TRUNK_FALLBACK`. Each is
    verified as `<name>^{commit}`, so a ref whose object is missing does not pass
    (bsd-225 r1 S1: plain `--verify` passed it, the ahead `git log` then failed
    inside `_ss_sh`, and the handoff said "0 commit(s) ahead -- in sync").

    "Does not resolve" is ONLY exit 1 with an empty stderr: under `--quiet`, git
    2.50.1 exits that way for a missing name or a ref to a missing sha, and the
    walk tries the next name. Everything else stops the walk and is said in git's
    own words: a corrupt object exits 128, an unreadable object, a broken ref or a
    ref to a tree exit 1 WITH stderr, and any other exit, an unrunnable git or a
    timeout is a failure too (bsd-225 r2 S1, ruling L100, 2026-11-14: reading 128
    as "not found" measured origin/master past a corrupt origin/main, silently).
    The ahead `git log` is read the same way: a failure is said and leaves
    `ahead_base` empty, so no surface can print a measured zero. When origin/HEAD
    names a ref that does not resolve, that is said too, with the trunk actually
    used (ruling L96).

    Problems land in `facts["trunk_errors"]` as (headline, detail) pairs; the
    composers render them (save-state doc line, recall-state anomaly). When
    nothing resolves and nothing failed (origin/HEAD unset, none of the list
    exists), `facts["trunk_info"]` says so: an info line in the save-state doc so
    "no trunk" reads differently from "measurement missing", but not a fault, so
    not a recall-state anomaly and not `trunk_error` (L100 M1)."""
    problems: list[tuple[str, str]] = facts["trunk_errors"]
    origin_head, oh_err = _ss_origin_head(repo)
    candidates = ([origin_head] if origin_head else []) + \
        [b for b in _SS_TRUNK_FALLBACK if b != origin_head]
    base, stopped_at = "", ""
    for cand in candidates:
        args = ("rev-parse", "--verify", "--quiet", f"{cand}^{{commit}}")
        rc, out, err = _ss_git_run(repo, *args)
        if rc == 0:
            base = cand
            break
        if rc == 1 and not err:
            continue
        stopped_at = cand
        what = ("origin/HEAD names `{0}`, which git could not verify" if cand == origin_head
                else "could not verify trunk candidate `{0}`").format(cand)
        problems.append((f"{what}; nothing measured", _ss_git_failure(args, rc, out, err)))
        break
    fallback = (f"measured against `{base}`" if base
                else "the fallback list was not verified" if stopped_at
                else "no fallback trunk resolves")
    if oh_err:
        problems.insert(0, ("origin/HEAD unreadable, " + (
            "measured by the fallback list" if base else fallback), oh_err))
    elif origin_head and base != origin_head and stopped_at != origin_head:
        problems.insert(0, (f"origin/HEAD names `{origin_head}`, which does not "
                            f"resolve; {fallback}", ""))
    if not base:
        if not (origin_head or oh_err or stopped_at):
            facts["trunk_info"] = ("none (origin/HEAD unset; no "
                                   + ", ".join(_SS_TRUNK_FALLBACK[:-1]) + " or "
                                   + _SS_TRUNK_FALLBACK[-1] + ")")
        return
    args = ("log", "--oneline", f"{base}..HEAD")
    rc, out, err = _ss_git_run(repo, *args)
    if rc == 0:
        facts["ahead_base"], facts["ahead"] = base, out
    else:
        problems.append((f"commits ahead of `{base}` not measured",
                         _ss_git_failure(args, rc, out, err)))


def _ss_trunk_lines(git: dict, *, sep: str, close: str) -> list[str]:
    """The trunk problems as `trunk: <headline><sep><detail><close>` lines."""
    return [f"trunk: {h}" + (f"{sep}{d}{close}" if d else "")
            for h, d in (git.get("trunk_errors") or [])]


def _ss_git_facts(repo: Path, since: str | None) -> dict:
    """Branch, HEAD, dirty tree, commits-ahead-of-trunk, and this-session
    commits (since the first STM event, if known).

    The trunk comes from `_ss_trunk` (origin/HEAD, then the fallback list, each
    verified as a commit; bug-225). `trunk_error` is every trunk problem in one
    string, the form the save-state verb result carries to CLI and MCP callers."""
    g = lambda *a: _ss_sh(["git", *a], repo)
    facts = {
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "head": g("log", "-1", "--format=%h %s"),
        "dirty": g("status", "--short"),
        "ahead_base": "", "ahead": "", "session_commits": "", "trunk_error": "",
        "trunk_errors": [], "trunk_info": "",
    }
    # No branch = not a work tree (or no commit yet): there is no trunk to measure
    # against, every git read above already came back empty, and no trunk git call
    # runs at all -- in a non-git dir each would fail "not a git repository".
    if facts["branch"]:
        _ss_trunk(repo, facts)
        facts["trunk_error"] = "; ".join(h + (f" — {d}" if d else "")
                                         for h, d in facts["trunk_errors"])
    if since:
        facts["session_commits"] = g("log", "--oneline", f"--since={since}")
    return facts


def _ss_recent_memories(memdir: Path, exclude: str, limit: int = 8) -> list[tuple[str, str]]:
    """(id, title) for the most-recently-touched memory files, newest first.

    Walks `memory_layout.iter_memory_files` -- THE walk of a memdir, so a memory
    in `feedback/` is a recent memory (task 26.3 AC-4, 2026-11-10). Save-states
    and impressions are not: a save-state is recalled through
    `_latest_savestate`, and at HEAD 8a867bc the top-level `*.md` glob here
    listed it as a "recent memory" while never seeing a type folder."""
    from refmatrix import memory_layout
    if not memdir.is_dir():
        return []
    files = []
    for p in memory_layout.iter_memory_files(memdir):
        rel = p.relative_to(memdir).parts
        if p.stem == exclude or memory_layout.is_savestate_path(memdir, p) or \
                (len(rel) > 1 and memory_layout.FOLDERS.get(rel[0]) == "impression"):
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


def _ss_updated_stamp(today: str) -> str:
    """`metadata.updated` for a save written now: `today` plus the wall clock's
    time of day and offset (`2026-11-09T14:03:22-08:00`; task 26.3 AC-1, ch-bsd
    plan-26 r2 s3). The date is the caller's `today`, so the stamp and the
    frozen `created:` of a first save agree on the day. The time of day is
    informational: ADR-0005 #newest orders by the DATE of `updated`, then mtime."""
    return today + datetime.now().astimezone().isoformat(timespec="seconds")[10:]


def _ss_render(*, mem_id: str, session: str, repo: Path, message: str | None,
               git: dict, focus: dict, tasks: list, recents: list,
               created: str, today: str, updated: str | None = None,
               goal: "dict | None" = None) -> str:
    """Render the handoff as a GMD memory doc (MEMORY-RULES shape). `updated`
    defaults to `_ss_updated_stamp(today)`; `created` stays a frozen date.

    `goal` (task-compaction-as-handoff R6, L198, 2026-11-24) is `read_active_goal`'s answer
    for the session's transcript; it is rendered as the `{#active-goal}` block, last before
    the `rel:` lines (recall-state renders it as its own block, so it never depends on the
    24-line excerpt). None = no transcript was known: no block, never a guessed one."""
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
    L.append(f"  updated: {updated or _ss_updated_stamp(today)}")
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
    L.extend(f"- {ln}" for ln in _ss_trunk_lines(git, sep=" — ", close=""))
    if git.get("trunk_info"):
        L.append(f"- trunk: {git['trunk_info']}")
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

    if goal is not None:
        L.extend(_goal_block_lines(goal))
        L.append("")

    L.append("rel: realizes -> [[feedback_save_state_means_handoff]]")
    L.append("rel: related-to -> [[feedback_recall_state_means_resume]]")
    L.append("")
    return "\n".join(L)


def _ss_update_index(memdir: Path, mem_id: str, title: str, hook: str) -> None:
    """Add/refresh the one-line MEMORY.md index entry for this save-state.

    In an organised dir (task 26.3 AC-5) the link is `](savestates/<id>.md)`,
    and the needle also matches the legacy `](<id>.md)` line so a moved
    save-state's old link is REPLACED, never left beside the new one; every
    matching line collapses into the one entry. An un-organised dir keeps
    HEAD's link, needle and per-line replacement byte for byte (ADR-0005
    #marker, 26.1 AC-9)."""
    from refmatrix import memory_layout
    idx = memdir / "MEMORY.md"
    legacy = f"]({mem_id}.md)"
    organised = memory_layout.is_organised(memdir)
    if organised:
        rel = f"{memory_layout.SAVESTATE_FOLDER}/{mem_id}.md"
        needles = (f"]({rel})", legacy)
    else:
        rel = f"{mem_id}.md"
        needles = (legacy,)
    line = f"- [{title}]({rel}) — {hook}"
    try:
        lines = idx.read_text().splitlines() if idx.exists() else []
    except OSError:
        lines = []
    out, replaced = [], False
    for ln in lines:
        if any(n in ln for n in needles):
            # Organised: the legacy line and the `savestates/` line are ONE
            # entry, so a second match is dropped, not duplicated.
            if not (organised and replaced):
                out.append(line)
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(line)
    idx.write_text("\n".join(out) + "\n")
    # Appending is what made the index unusable: it grew one line per memory,
    # past the 200-line cap `MEMORY-RULES.md` sets, and everything beyond that
    # is CUT when the file loads into a session — 234 lines / 34 KB on
    # 2026-09-16, with the last 34 entries unreachable through the surface whose
    # job is to reach them. Save-state is the write that grows it, so it is the
    # write that compacts it. Failure is said, never swallowed: an index that
    # silently stopped compacting would rebuild the same blind spot.
    from refmatrix import memory_index as _mi

    try:
        if not _mi.check(memdir):
            _mi.write(memdir)
    except Exception as exc:  # noqa: BLE001 — said, never mute
        import sys as _sys
        print(f"warning: MEMORY.md compaction failed: "
              f"{type(exc).__name__}: {exc}", file=_sys.stderr)


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


def _promote_digest(root: Path, s, *, timeout: float = 30.0) -> dict:
    """Condense the session STM and write it to the durable memory store
    (daemon-routed; in-proc Store fallback when the daemon is down). Returns
    {"name", "id"} on success or {"error"} — never raises.

    `timeout` bounds the daemon write (one attempt). PreCompact passes what is left of its
    overall budget (task-compaction-as-handoff s-2, L202/L203, 2026-11-24). A write that does
    not answer in time is NOT lost: measured 2026-11-24 on a held writer, the daemon applied
    the queued `memory_add` once the lock freed."""
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
        # Busy is not absent (ch-bsd plan-3 r3 #b-1): only a store with NO
        # daemon may be opened in-process; a busy one raises VerbBusyError,
        # which the outer except turns into the error dict the callers print.
        from refmatrix.verbs import VerbAbsentError, _call, require_daemon
        try:
            require_daemon(root)
            daemon_up = True
        except VerbAbsentError:
            daemon_up = False
        if daemon_up:
            # Typed, one attempt (bsd-plan3-r4 #s-3): the bare call retried a
            # 30 s timeout three times and reported "TimeoutError: timed out"
            # for a held writer; a busy daemon is now named as busy.
            r = _call(root, "memory_add", args, timeout=max(0.5, float(timeout)), retries=0)
            return {"name": name, "id": r.get("id")}
        # No daemon: through `verbs.local_write`, the checked opener (bug-212 r4, ruling
        # L72, 2026-11-13) -- a hand-rolled `Store(root)` here wrote a catalog git tracks.
        # Its refusal is a VerbError, returned below as {"error"}; `rmx save-state` prints
        # that on stderr and exits non-zero (L82).
        from refmatrix.verbs import local_write
        out = local_write(
            root, lambda st: {"id": st.add_memory(
                name=name, content=digest, mtype="session/digest",
                tags=[f"session:{s.session}", "summary"], protected=False)},
            partition=part, create=True)
        return {"name": name, "id": out["id"]}
    except Exception as e:  # noqa: BLE001 — promote is best-effort
        return {"error": f"{type(e).__name__}: {e}", "name": name}


# ---- save-state core -------------------------------------------------------


class SaveStateWriteError(OSError):
    """The handoff file could not be written (task 26.3 remedy-r1, 2026-11-10).

    Raised, never reported as a save: a save-state that returned a `target`
    it never wrote told the next session to resume from a file that does not
    hold this handoff. The message names the path and what was left in place,
    so the caller can say it; `verbs.save_state` turns it into a VerbError."""


def compose_save_state(s, root: Path, *, repo: Path, memdir: Path, today: str,
                       message: str | None = None, promote: bool = True,
                       dry_run: bool = False, transcript: "str | None" = None,
                       deadline: "float | None" = None) -> dict:
    """Compile + persist the session handoff memory. `s` is a live Stm.

    Returns a structured result the caller renders. Side effects (unless
    dry_run): writes the GMD handoff file, refreshes the MEMORY.md index, and
    (when promote) writes the condensed STM digest to durable memory.

    `transcript` (R6, L198, 2026-11-24): the session's Claude Code transcript, which the
    PreCompact hook passes from its envelope's `transcript_path`; without one, the transcript
    Claude Code keeps for this session id under `~/.claude/projects/<slug>/` is used when it
    exists (a `/save-state` then `/clear` keeps the goal too). Its active `/goal` becomes the
    `{#active-goal}` block; no transcript known = no block.

    ORDER (L203, the user 2026-11-24: "a timeout must never lose the commit"): the
    `savestate_*.md` file and the MEMORY.md index are written FIRST, to disk; only then does
    the store commit (the promote, a daemon write) start. `deadline` (a `time.monotonic()`
    value) bounds the commit with what is left; a commit that overruns leaves the file as the
    durable record and the caller says the commit was deferred.
    """
    events = s.all_events()
    focus = s.focus_graph(top=20)
    tasks = s.task_list()
    since = events[0]["ts"] if events else None
    git = _ss_git_facts(repo, since)

    sess_slug = re.sub(r"[^A-Za-z0-9]+", "", s.session)[:12] or "default"
    mem_id = f"savestate_{sess_slug}"
    # Task 26.3 AC-1/AC-2 (ADR-0005 #marker): an ORGANISED dir keeps its
    # save-states in `savestates/`; a dir without the marker is written exactly
    # as at HEAD 8a867bc, at the top level. `legacy` is the top-level path.
    from refmatrix import memory_layout
    legacy = memdir / f"{mem_id}.md"
    organised = memory_layout.is_organised(memdir)
    target = memory_layout.savestate_dir(memdir) / f"{mem_id}.md" if organised else legacy
    # The frozen `created:` comes from the copy the walk keeps: of a top-level
    # / `savestates/` pair, the NEWER one (`memory_layout.savestate_pair`,
    # #rm-newer-copy); else the `savestates/` file when it exists, else the
    # legacy file it replaces.
    pair = memory_layout.savestate_pair(memdir, legacy.name) if organised else None
    if pair:
        created_from = pair[0]
    else:
        created_from = target if target.exists() or not legacy.exists() else legacy
    created = _ss_frozen_created(created_from, today)
    recents = _ss_recent_memories(memdir, exclude=mem_id)
    goal_src = transcript or session_transcript_path(repo, s.session)
    goal = read_active_goal(goal_src) if goal_src else None

    doc = _ss_render(mem_id=mem_id, session=s.session, repo=repo,
                     message=message, git=git, focus=focus, tasks=tasks,
                     recents=recents, created=created, today=today,
                     updated=_ss_updated_stamp(today), goal=goal)

    head_sha = (git["head"].split() or ["?"])[0]
    result = {
        "mem_id": mem_id, "target": str(target), "session": s.session,
        "events": len(events), "doc": doc, "dry_run": dry_run,
        "branch": git["branch"], "head": git["head"],
        "dirty": bool(git["dirty"]), "promoted": None,
        # bug-225 r2 M1: the trunk problem rides back to every caller (CLI, MCP).
        "trunk_error": git.get("trunk_error") or "",
        "memdir": str(memdir),
        "moved_legacy": None,
        # #rm-newer-copy: the top-level copy of a pair this save removed, the
        # copy whose `created:` it kept, and a removal that failed (said).
        "removed_duplicate": None, "kept_copy": str(pair[0]) if pair else None,
        "remove_failed": None,
        "active_goal": goal,
    }
    if dry_run:
        return result

    try:
        memdir.mkdir(parents=True, exist_ok=True)
        if organised:
            target.parent.mkdir(parents=True, exist_ok=True)
            if legacy.exists() and not target.exists():
                # AC-2: MOVE the legacy file in (os.replace keeps its mtime)
                # BEFORE the write, so no instant holds two copies of one id
                # for 26.2's duplicate-id refusal to fire on.
                os.replace(legacy, target)
                result["moved_legacy"] = str(legacy)
        target.write_text(doc)
    except OSError as exc:
        kept = (f"; the top-level {legacy.name} is kept" if organised and legacy.exists()
                else "")
        raise SaveStateWriteError(
            f"save-state could not write {target} ({type(exc).__name__}: {exc})"
            f"{kept}; nothing was saved") from exc
    if organised and legacy.exists():
        # #rm-newer-copy: another writer left a top-level copy beside the
        # folder copy. Removed only NOW, after `savestates/` holds this save
        # (which carries the kept copy's `created:`), so a failed write above
        # never costs the only copy of the newest save.
        try:
            legacy.unlink()
            result["removed_duplicate"] = str(legacy)
        except OSError as exc:
            # The save landed; the stale copy stays and the walk keeps naming
            # it as skipped. Said, never mute.
            result["remove_failed"] = f"{legacy}: {type(exc).__name__}: {exc}"
    hook = (message or f"{repo.name} @ {head_sha}")[:90]
    title = f"Save-state {today}: {message or repo.name + ' @ ' + head_sha}"
    _ss_update_index(memdir, mem_id, title, hook)

    if promote:
        result["promoted"] = _promote_digest(
            root, s, **({"timeout": _remaining(deadline)} if deadline is not None else {}))
    return result


def _remaining(deadline: "float | None", floor: float = 0.5) -> float:
    """Seconds left before `deadline` (a `time.monotonic()` value), never under `floor`, so a
    spent budget still makes one short attempt that fails loudly rather than none."""
    return max(floor, deadline - time.monotonic()) if deadline is not None else floor


def finalize_save_state(s, root: Path, result: dict, *, repo: Path,
                        lint: bool = True, sync: bool = True,
                        deadline: "float | None" = None) -> dict:
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

    Since bug-065 it also DRAINS the memory embed queue after the bridge: the
    bridge inserts rows without vectors, so until then every save-state wrote
    memories that `memory get` could find and `memory recall` could not — and
    recall is the only way the next session reaches them.

    Returns {"lint": str | None, "filed_subject": str | None,
    "sync": dict | None, "embed": dict | None}; best-effort throughout — a
    lint, filing, bridge, or embed failure never breaks the handoff, but the
    bridge failure is returned in `sync["error"]` and the embed outcome in
    `embed` for the caller to surface, never swallowed."""
    out: dict = {"lint": None, "filed_subject": None, "sync": None,
                 "embed": None}
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
            # bug-065: the bridge writes memory rows, and since the fix it
            # also EMBEDS them — an as-memory ingest implies memory vectors,
            # because a row without one is durable and invisible to recall,
            # which is the only way the next session reaches it. The drain
            # lives in `ingest_gmd.drain_memory_vectors` so every bridge
            # caller gets it (this one, `rmx memory sync-disk`, and the
            # SessionStart `--detach` catch-up), not just save-state. Its
            # counts ride back here for the caller to print.
            out["embed"] = (out["sync"] or {}).get("embed")
    if lint:
        lint_py = Path.home() / "claude_tools" / "gmd" / "lint.py"
        target = result.get("target")
        if lint_py.exists() and target:
            out["lint"] = _ss_sh(["python3", str(lint_py), str(target)], repo,
                                 timeout=_remaining(deadline) if deadline is not None else 20)
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
                # Under a deadline (PreCompact, s-2): one attempt each, inside the budget;
                # `retries=2` on a 60 s default multiplied the worst case to ~6 min.
                bound = ({"timeout": _remaining(deadline), "retries": 0}
                         if deadline is not None else {})
                sid = _subject_upsert(label, **bound)
                if sid:
                    _subject_link(int(leaf), int(sid),
                                  **({"timeout": _remaining(deadline), "retries": 0}
                                     if deadline is not None else {}))
                    out["filed_subject"] = label
            except Exception as e:  # noqa: BLE001 — named in the result
                out["filed_subject_error"] = f"{label}: {e}"
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
    `rmx memory get <id>`.

    "Most recent" is `memory_layout.iter_savestates`' ONE ordering across
    `savestates/` and the legacy top level (task 26.3 AC-3, ADR-0005 #newest:
    `updated` date, then mtime, never `created`), the same answer the MEMORY.md
    pointer gives. At HEAD 8a867bc this globbed the top level only and took the
    newest MTIME, which in cliquedb was a file a later copy had touched, not
    its newest save (ch-bsd plan-26 r1 #s2)."""
    from refmatrix import memory_layout
    if not memdir.is_dir():
        return None
    cands = memory_layout.iter_savestates(memdir)
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
    # R6 (L198): the `{#active-goal}` block is read from the WHOLE file, not the capped body,
    # so a long handoff never hides the goal.
    return {"id": p.stem, "path": str(p), "body": body, "truncated": truncated,
            "active_goal": parse_active_goal_block(txt)}


def session_pointer_anomalies(root: Path, *, window_s: float = 86400.0) -> list[str]:
    """The reader of the user-level pointer-error log, SCOPED to `root` (bug-109 r2 #s-2;
    task 21.1 D6, round-7 #s-2: D3 made the log one file for every project, and an unscoped
    reader in project X counted project Y's rows). Up to three clauses, kept apart:
    (1) session-pointer failures — count per reason, and what each purpose did with the miss;
    (2) STM hook failures (`sweep-failed`, `composite-failed`, `enrichment-unresolved`) — no
        session wording, they are not session misses;
    (3) rows of this store dropped by the log's halving.
    Unreadable lines (r3 #m-2) and rows with no `root` (a writer defect) are counted apart,
    never attributed to this store silently. The path comes from `stm.errors_log_path()`, and
    the scope (`dropped_by_root`) is spelled by `stm.scope_key` (21.1 r1 #s3)."""
    import time as _t
    from collections import Counter
    from refmatrix import stm as stm_mod
    path = stm_mod.errors_log_path()
    rows = stm_mod.read_pointer_errors(root=root, since=_t.time() - window_s)
    bad = sum(1 for r in rows if r.get("reason") == "unreadable-line")
    unscoped = sum(1 for r in rows if r.get("reason") == "unscoped-row")
    trunc = sum(int((r.get("dropped_by_root") or {}).get(stm_mod.scope_key(root), 0))
                for r in rows if r.get("reason") == "errors-truncated")
    special = ("unreadable-line", "unscoped-row", "errors-truncated")
    hook_rows = [r for r in rows if r.get("reason") in stm_mod.STM_HOOK_REASONS]
    ptr_rows = [r for r in rows if r.get("reason") not in special
                and r.get("reason") not in stm_mod.STM_HOOK_REASONS]
    out: list[str] = []
    if ptr_rows or bad:
        by = Counter(str(r.get("reason")) for r in ptr_rows)
        parts = ", ".join(f"{k} x{v}" for k, v in by.most_common())
        if ptr_rows:
            msg = (f"{len(ptr_rows)} session-pointer failure(s) in 24h ({parts}): the session "
                   f"could not be resolved: reads used the labelled newest ring, writes were "
                   f"refused, events carry `session: null`")
            if bad:
                msg += f"; {bad} unreadable line(s) in the log"
        else:
            msg = f"session-pointer log has {bad} unreadable line(s)"
        out.append(f"{msg}; see {path}")
    if hook_rows:
        by = Counter(str(r.get("reason")) for r in hook_rows)
        parts = ", ".join(f"{k} x{v}" for k, v in by.most_common())
        # 21.1 r1 #m4 (2026-10-19): the path comes from `errors_log_path()` like every other
        # clause (round-9 #m9-2), never a hand-typed name.
        out.append(f"STM hook failures in 24h: {parts}; see {path}")
    if unscoped:
        out.append(f"pointer-error log rows with no store root (a writer defect, not "
                   f"attributed here): unscoped-row x{unscoped}; see {path}")
    if trunc:
        out.append(f"{trunc} pointer-error row(s) of this store were dropped when the log "
                   f"halved; see {path}")
    return out


def compose_recall_state(s, root: Path, *, repo: Path, memdir: Path,
                         pointer_anomalies: "list[str] | None" = None) -> dict:
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

    # Busy is not absent (bsd-plan3-r4 #b-1): a bare ping here turned every
    # busy daemon into "stale pid" on the resume report, and the render's
    # `busy` branch had no producer since 0.41.0.
    from refmatrix import discovery
    st = discovery.daemon_status(root, retries=0)
    pid = st.get("pid")
    daemon_info = {
        "running": bool(st.get("up")),
        "busy": bool(st.get("busy")),
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
    anomalies.extend(_ss_trunk_lines(git, sep=" (", close=")"))
    # A caller that resolved its own session AFTER reading the pointer-error log passes the
    # clauses it read first (task 21.1 D6): the report is about the rows that were there,
    # not about the miss this very call recorded while choosing which ring to show.
    anomalies.extend(pointer_anomalies if pointer_anomalies is not None
                     else session_pointer_anomalies(root))
    if pid and not daemon_info["running"]:
        if daemon_info["busy"]:
            anomalies.append(f"daemon pid {pid} alive but not answering (busy: "
                             f"starting, rebuilding an index, or holding the store lock)")
        else:
            anomalies.append(f"daemon pid {pid} present but the process is gone (stale)")

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


# ---- the recall-state text (task 25.1 R11) -------------------------------------------------

NEWEST_RING_LABEL = "(newest ring; not resolved)"


def recall_state_blocks(rep: dict, *, handoff_lines: int = 24,
                        recent_limit: int = 8) -> "list[str]":
    """`rmx recall-state`'s report as WHOLE text blocks, in the order a byte budget keeps them
    (task 25.1 R11, user 2026-11-11): the handoff head (the session line and which save-state
    is the handoff), the save-state's active goal (task-compaction-as-handoff R6, when its
    `{#active-goal}` block exists), the handoff's body head, anomalies, git, daemon, recent
    memories, the STM digest. Each block ends with a newline.

    ONE renderer for the CLI and the `recall_state` verb's `text` (`max_bytes`), so a hook's
    fitted output and an interactive run start with the same lines. Plain text: a hook's
    stdout is not a terminal, and rich markup in a payload is bytes the model pays for."""
    sess = rep.get("session") or "?"
    if rep.get("session_source") == "latest":
        sess = f"{sess} {NEWEST_RING_LABEL}"
    ss = rep.get("savestate")
    head = [f"recall-state · session {sess} ({rep.get('events', 0)} STM events)"]
    if ss:
        head.append(f"handoff {ss['id']} {ss['path']}")
    else:
        head.append("no prior save-state handoff found")
    blocks = ["\n".join(head) + "\n"]
    goal_text = active_goal_report_line(ss.get("active_goal"), ss["id"]) if ss else None
    if goal_text:
        # R6 (L198): second, right after the head, so a byte budget keeps it before the excerpt.
        blocks.append(goal_text + "\n")
    if ss and ss.get("body"):
        excerpt = "\n".join(str(ss["body"]).splitlines()[:handoff_lines])
        blocks.append(excerpt.rstrip("\n") + "\n")
    anomalies = rep.get("anomalies") or []
    if anomalies:
        blocks.append("anomalies\n" + "".join(f"  ! {a}\n" for a in anomalies))
    git = rep.get("git") or {}
    gl = [f"git branch {git.get('branch') or '?'} · HEAD {git.get('head') or '?'}"]
    if git.get("ahead_base"):
        n = len([x for x in str(git.get("ahead") or "").splitlines() if x.strip()])
        gl.append(f"     {n} commit(s) ahead of {git['ahead_base']}" + ("" if n else " — in sync"))
    gl.append("     working tree: " + ("dirty" if git.get("dirty") else "clean"))
    blocks.append("\n".join(gl) + "\n")
    d = rep.get("daemon") or {}
    state = (f"running pid={d.get('pid')}" if d.get("running")
             else (f"busy pid {d.get('pid')}" if d.get("busy")
                   else (f"stale pid {d.get('pid')}" if d.get("pid") else "not running")))
    blocks.append(f"daemon {state}\n")
    recents = rep.get("recent_memories") or []
    if recents:
        blocks.append("recent memories\n" + "".join(
            f"  {mid} — {title}\n" for mid, title in recents[:recent_limit]))
    if rep.get("stm_digest"):
        blocks.append("STM digest (live session)\n" + str(rep["stm_digest"]).rstrip("\n") + "\n")
    return blocks


def fit_recall_state(rep: dict, max_bytes: "int | None") -> "tuple[str, int]":
    """The report fitted to `max_bytes` UTF-8 bytes (None = everything): whole blocks in
    `recall_state_blocks` order, and a trailer naming `rmx recall-state` for the full output
    when any block was cut. Returns (text, dropped)."""
    from refmatrix import hook_budget
    blocks = recall_state_blocks(rep)
    if max_bytes is None:
        return "".join(blocks), 0
    f = hook_budget.fit_blocks(
        blocks, int(max_bytes),
        trailer=lambda n: f"+{n} block(s) omitted to fit {int(max_bytes)} B; "
                          f"full: rmx recall-state")
    return f.text, f.dropped


# ==== compaction and /clear as a handoff (task-compaction-as-handoff, L195, 2026-11-24) ========
#
# The user, 2026-11-14 (Q17 a, L91-L93): compaction should behave like save-state -> /clear ->
# recall-state. No hook can suppress the compaction summary or trigger /clear, so:
# - PreCompact saves state (with promote) and prints ONE instruction: summarise in one line, the
#   handoff is authoritative (`precompact_instruction`);
# - SessionStart(compact|clear) writes the FULL `rmx recall-state` report to a per-session file
#   here and injects only a pointer (`write_pulled_handoff`, `handoff_pointer`): the measured
#   45,870 B report (2026-11-14) is over the ~10 KB hook cap and the Bash tool's 30,000-char
#   output cap, and a Read carries neither;
# - a pointer alone is not trusted (session 37b7498f read none of the dozens of oversized hook
#   outputs Claude Code had saved to files), so until the file is Read every other tool call of
#   that session is denied (`gate_status`), the pointer is re-said on every prompt, and each
#   pull and stand-down is recorded for `rmx telemetry --context` (`handoff_events`);
# - the gate can never trap a session: a missing, unreadable or expired file stands it down in
#   one line.
# R6 (L198, the user 2026-11-24: "add the goal text to the C1 handoff"): the session's active
# `/goal`, read from its transcript, rides the save-state (`{#active-goal}`), the report and
# the pointer, because /clear removes it and only the user can re-issue it.

HANDOFFS_DIR = "handoffs"
# The handoff ledger (writes, pulls, stand-downs, reaps). Not `*events.jsonl`: that name family
# is reserved for recall items (21.1 AC-9's one-sink rule, `recall-events.jsonl`).
HANDOFF_LEDGER = "ledger.jsonl"
POINTER_MAX_BYTES = 1024        # the SessionStart pointer block (RED's contract)
PRECOMPACT_MAX_BYTES = 1000     # the PreCompact instruction (RED's contract; 3 lines at most)
FALLBACK_HEAD_MAX_BYTES = 500   # the "could not be written" line above the inline fallback
GATE_EXPIRY_S = 24 * 3600       # an unread handoff older than this stands its gate down
HANDOFF_KEEP_S = 7 * 24 * 3600  # handoff files and ledger rows older than this are reaped
# The clock every handoff age is read on: epoch seconds, `RMX_HANDOFF_NOW` when set (a test
# knob for the 24 h expiry and the 7-day reap, rule 6: no real waits), else the wall clock.
HANDOFF_NOW_ENV = "RMX_HANDOFF_NOW"

# Session ids the generated shell fast path can test without Python (`hooks._handoff_cmd`):
# the same character class there and here, so the shell and Python name the same file.
SESSION_SLUG_RE = re.compile(r"[A-Za-z0-9_-]+")


def _say(msg: str) -> None:
    print(msg, file=sys.stderr)


def _now() -> float:
    v = os.environ.get(HANDOFF_NOW_ENV)
    if v:
        try:
            return float(v)
        except ValueError:
            raise ValueError(f"{HANDOFF_NOW_ENV}={v!r} is not epoch seconds") from None
    return time.time()


def is_subagent(envelope: "dict | None") -> bool:
    """A subagent's or a teammate's hook input: Claude Code 2.1.331 gives it the PARENT's
    `session_id` plus `agent_id` / `agent_type` (bsd-cah r1 #b-1/#b-2, bug-307, 2026-11-24).
    The handoff, its gate and its pull are the session's MAIN thread's; a subagent's call
    never arms, trips or lifts them."""
    return bool((envelope or {}).get("agent_id"))


def handoff_slug(session: str) -> str:
    """The per-session file stem: the session id itself when it is `[A-Za-z0-9_-]+` (every
    Claude Code session id, a UUID), else a sanitised stem plus a hash, so two ids never
    share a file."""
    sid = str(session)
    if SESSION_SLUG_RE.fullmatch(sid):
        return sid
    import hashlib
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", sid).strip("_")[:64] or "session"
    return f"{clean}-{hashlib.sha256(sid.encode('utf-8')).hexdigest()[:10]}"


def handoffs_dir(root: Path) -> Path:
    return Path(root) / HANDOFFS_DIR


def handoff_file_path(root: Path, session: str) -> Path:
    """`<store>/handoffs/<session>.txt`: one file per session, the next write replaces it."""
    return handoffs_dir(root) / f"{handoff_slug(session)}.txt"


def _gate_path(root: Path, session: str) -> Path:
    return handoffs_dir(root) / f"{handoff_slug(session)}.gate"


def _marker_path(root: Path, session: str, kind: str) -> Path:
    return handoffs_dir(root) / f"{handoff_slug(session)}.{kind}"


def _now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(_now()))


def _record_event(root: Path, row: dict) -> bool:
    """Append one row to `<store>/handoffs/ledger.jsonl` (what `rmx telemetry --context`
    reads). A row that cannot be written is said on stderr, never dropped silently."""
    p = handoffs_dir(root) / HANDOFF_LEDGER
    row = {"ts": _now_ts(), "t": round(_now(), 3), **row}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
        return True
    except OSError as e:
        _say(f"rmx handoff: could not record the {row.get('event')} event in {p}: "
             f"{type(e).__name__}: {e}")
        return False


def _clip(text: str, max_bytes: int) -> str:
    from refmatrix import hook_budget
    return hook_budget.clip_utf8(text, max_bytes)


def _nbytes(text: str) -> int:
    return len(text.encode("utf-8"))


# ---- R6: the active /goal ------------------------------------------------------------------

# Claude Code's documented clearing forms (goal docs, read 2026-11-23): `/goal clear` and the
# aliases below. A bare `/goal` only SHOWS the goal and changes nothing.
GOAL_CLEAR_ALIASES = frozenset({"clear", "stop", "off", "reset", "none", "cancel"})
_GOAL_TAG = "<command-name>/goal</command-name>"
# The probed record shape (RED, 2026-11-23, shape + hashes only): a `type: user` record whose
# `message.content` is a STRING that is exactly this. A quote of it inside a tool result (list
# content) or an api-request blob is not a command.
_GOAL_CMD = re.compile(
    r"\A<command-name>/goal</command-name>\s*<command-message>goal</command-message>\s*"
    r"<command-args>(.*)</command-args>\s*\Z", re.S)
_JSONL_PROBE_LINES = 5


def _utc_second(ts) -> str:
    """An ISO timestamp as `YYYY-MM-DDTHH:MM:SSZ` (UTC, whole seconds)."""
    if not ts:
        return "an unknown time"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return f"an unparsed time ({str(ts)[:40]})"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_transcript_path(repo: Path, session: "str | None") -> "str | None":
    """The transcript Claude Code keeps for `session` in this project
    (`~/.claude/projects/<slug>/<session>.jsonl`, the slug `default_memory_dir` uses), when it
    exists; None otherwise. Lets a save-state with no hook envelope (`/save-state`, the MCP
    tool) still record the goal."""
    if not session:
        return None
    p = default_memory_dir(Path(repo)).parent / f"{session}.jsonl"
    return str(p) if p.is_file() else None


def read_active_goal(transcript: "str | Path") -> dict:
    """The session's active goal from its transcript: the NEWEST `/goal <text>` command not
    followed by a clearing `/goal` (`GOAL_CLEAR_ALIASES`).

    Returns `{"state": "set", "text", "set_at"}`, `{"state": "cleared", "by", "at"}`,
    `{"state": "none"}` or `{"state": "unknown", "note"}`; each also carries `transcript`.
    `text` is verbatim; `set_at` is the record's time to the UTC second. A transcript that
    cannot be read, or holds no JSON at all, is `unknown` with a one-line `note` naming it:
    never a guessed or an empty goal. Only lines that hold the command tag, plus the first few
    lines (to tell a JSONL file from garbage), are parsed, so a long transcript costs little;
    a tag line that is not JSON is counted (`skipped`) and said, never dropped silently."""
    p = Path(transcript)
    base = {"transcript": str(p)}
    try:
        raw = p.read_bytes()
    except OSError as e:
        why = e.strerror or str(e)
        return {**base, "state": "unknown",
                "note": f"the transcript {p} could not be read ({type(e).__name__}: {why})"}
    probed = parsed = bad = bad_tag = 0
    goal: "dict | None" = None
    cleared: "dict | None" = None
    for line in raw.decode("utf-8", "replace").splitlines():
        s = line.strip()
        if not s:
            continue
        tagged = _GOAL_TAG in s
        if not tagged:
            if probed >= _JSONL_PROBE_LINES:
                continue
            probed += 1
        try:
            rec = json.loads(s)
        except ValueError:
            bad += 1
            bad_tag += int(tagged)
            continue
        parsed += 1
        if not tagged or not isinstance(rec, dict):
            continue
        if rec.get("type") != "user" or rec.get("isSidechain") or rec.get("isMeta"):
            continue
        msg = rec.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, str):
            continue
        m = _GOAL_CMD.match(content)
        if not m:
            continue
        arg = m.group(1)
        word = arg.strip()
        if not word:
            continue                      # a bare `/goal` shows the goal; it sets nothing
        at = _utc_second(rec.get("timestamp"))
        if word.lower() in GOAL_CLEAR_ALIASES:
            goal, cleared = None, {"by": word, "at": at}
        else:
            goal, cleared = {"text": arg, "set_at": at}, None
    if parsed == 0 and bad:
        return {**base, "state": "unknown",
                "note": f"the transcript {p} could not be parsed ({bad} line(s) read, none "
                        f"of them JSON)"}
    extra = {"skipped": bad_tag} if bad_tag else {}
    if goal:
        return {**base, **extra, "state": "set", **goal}
    if cleared:
        return {**base, **extra, "state": "cleared", **cleared}
    return {**base, **extra, "state": "none"}


def _goal_block_lines(g: dict) -> "list[str]":
    """The save-state's `{#active-goal}` block for `read_active_goal`'s answer. A set goal is
    `- goal: /goal <text>` (verbatim; a multi-line goal continues on lines indented two
    spaces) and `- set: <UTC second>`; anything else is ONE `- goal:` line saying why there is
    no goal. `parse_active_goal_block` reads it back."""
    L = ["## Active goal {#active-goal}", ""]
    st = g.get("state")
    if st == "set":
        first, *rest = str(g.get("text") or "").split("\n")
        L.append(f"- goal: /goal {first}")
        L.extend(f"  {ln}" for ln in rest)
        L.append(f"- set: {g.get('set_at') or 'an unknown time'}")
        L.append(f"- source: `{g.get('transcript')}`")
    elif st == "cleared":
        L.append(f"- goal: none (cleared by `/goal {g.get('by')}` at {g.get('at')})")
        L.append(f"- source: `{g.get('transcript')}`")
    elif st == "none":
        L.append("- goal: none (no `/goal` was set in this session's transcript)")
        L.append(f"- source: `{g.get('transcript')}`")
    else:
        L.append(f"- goal: unknown: {g.get('note') or 'no reason recorded'}")
    if g.get("skipped"):
        L.append(f"- note: {g['skipped']} `/goal` line(s) in the transcript are not JSON and "
                 f"were skipped")
    return L


def parse_active_goal_block(doc: str) -> "dict | None":
    """A save-state's `{#active-goal}` block as `{"state", "text"?, "set_at"?, "note"?}`, or
    None when the file has no block (written before R6, or with no transcript known)."""
    i = doc.find("{#active-goal}")
    if i < 0:
        return None
    nl = doc.find("\n", i)
    start = len(doc) if nl < 0 else nl + 1
    nxt = re.search(r"^(#{1,6} |rel: )", doc[start:], re.M)
    lines = (doc[start:start + nxt.start()] if nxt else doc[start:]).splitlines()
    out: dict = {"state": None}
    j = 0
    while j < len(lines):
        ln = lines[j]
        if ln.startswith("- goal: /goal "):
            text = [ln[len("- goal: /goal "):]]
            while j + 1 < len(lines) and lines[j + 1].startswith("  "):
                text.append(lines[j + 1][2:])
                j += 1
            out.update(state="set", text="\n".join(text))
        elif ln.startswith("- goal: unknown: "):
            out.update(state="unknown", note=ln[len("- goal: unknown: "):])
        elif ln.startswith("- goal: none"):
            out.update(state="none", note=ln[len("- goal: "):])
        elif ln.startswith("- set: "):
            out["set_at"] = ln[len("- set: "):].strip()
        j += 1
    if out["state"] is None:
        return {"state": "unknown", "note": "the {#active-goal} block holds no `- goal:` line"}
    return out


def active_goal_report_line(g: "dict | None", ss_id: str) -> "str | None":
    """The recall-state report's goal block (no trailing newline), or None with no block."""
    if not g:
        return None
    st = g.get("state")
    if st == "set":
        return (f"active goal: /goal {g.get('text')}\n"
                f"     set {g.get('set_at') or 'at an unknown time'} (from {ss_id})")
    if st == "none":
        return f"active goal: {g.get('note') or 'none'} (from {ss_id})"
    return f"active goal: unknown, {g.get('note')} (from {ss_id})"


def goal_pointer_lines(g: "dict | None", ss_id: str, *, max_bytes: int) -> "list[str]":
    """The pointer's goal lines (R6): `active goal: /goal <verbatim>` and what to do with it,
    within `max_bytes` (a goal too long for the pointer is clipped there and named whole in
    the handoff file). No goal, or a cleared one: no line."""
    if not g or g.get("state") in (None, "none"):
        return []
    if g.get("state") == "set":
        first, *rest = str(g.get("text") or "").split("\n")
        more = " (it continues in the handoff file)" if rest else ""
        line2 = (f"It was set {g.get('set_at') or 'at an unknown time'} ({ss_id}). Run a bare "
                 f"/goal to check that it is still active; if none is, ask the user to "
                 f"re-issue that exact command.")
        line1 = f"active goal: /goal {first}{more}"
        if _nbytes(line1) + _nbytes(line2) + 2 > max_bytes:
            tail = " … (clipped; the full text is in the handoff file)"
            room = max_bytes - _nbytes(line2) - 2 - _nbytes(tail)
            line1 = _clip(f"active goal: /goal {first}", max(room, 40)) + tail
        return [line1, line2]
    line = (f"active goal: unknown, {g.get('note')}; run a bare /goal to check whether one "
            f"is active.")
    return [_clip(line, max_bytes - 1)]


# ---- R3: the per-session handoff file and its pointer ---------------------------------------


def write_pulled_handoff(root: Path, session: str, text: str, *, source: str) -> dict:
    """Write the FULL recall-state report to `handoff_file_path` (atomically: a temp file then
    `os.replace`, so a reader never sees half of it) and arm the session's read gate.

    Raises OSError when the FILE cannot be written (the caller then falls back to the inline
    report, R3). A gate that cannot be armed after the file landed is returned in
    `gate_error` for the pointer to say: the file is still the handoff."""
    path = handoff_file_path(root, session)
    data = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    now = _now()
    try:
        tmp.write_bytes(data)
        os.utime(tmp, (now, now))         # the file's age is read on the handoff clock (reap)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    state = {"session": str(session), "path": str(path), "bytes": len(data),
             "written_at": now, "source": source or "unknown"}
    gate_error = None
    try:
        for kind in ("pulled", "stood-down"):
            _marker_path(root, session, kind).unlink(missing_ok=True)
        _gate_path(root, session).write_text(json.dumps(state), encoding="utf-8")
    except OSError as e:
        gate_error = f"{type(e).__name__}: {e}"
        _say(f"rmx recall-state --handoff: the read gate for {path} could not be armed: "
             f"{gate_error}")
    _record_event(root, {"event": "write", "session": str(session), "path": str(path),
                         "bytes": len(data), "source": state["source"],
                         **({"gate_error": gate_error} if gate_error else {})})
    reap_handoffs(root, keep=path)
    return {**state, "gate_error": gate_error}


def _row_epoch(row: dict) -> "float | None":
    t = row.get("t")
    if isinstance(t, (int, float)):
        return float(t)
    try:
        return time.mktime(time.strptime(str(row.get("ts"))[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None


def reap_handoffs(root: Path, *, keep: "Path | None" = None) -> dict:
    """What no session will consult again, reaped when a handoff is written (bsd-cah r1 #m-3,
    2026-11-24): an unread gate past `GATE_EXPIRY_S` stands down (recorded, as its own session
    would have on its next call); a handoff file older than `HANDOFF_KEEP_S`, with its
    markers, is removed; ledger rows older than that are dropped. Without this a session that
    ended unread left its `.gate` forever (every Read in every session then started Python)
    and the files grew one per session. `keep` (the file just written) is never reaped.
    Counts ride back and are recorded as one `reap` row; a failure is said, never silent."""
    d = handoffs_dir(root)
    now = _now()
    out = {"gates": 0, "files": 0, "rows": 0, "errors": 0}
    if not d.is_dir():
        return out
    for gp in sorted(d.glob("*.gate")):
        try:
            st = json.loads(gp.read_text(encoding="utf-8"))
            age = now - float(st.get("written_at") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            continue                          # its own session's gate_status says so
        if age > GATE_EXPIRY_S:
            sess = str(st.get("session") or gp.stem)
            _stand_down(root, sess, st, f"was never read; reaped {age / 3600:.0f} h after it "
                                        f"was written (past the {GATE_EXPIRY_S // 3600} h expiry)")
            out["gates"] += 1
    keep_s = str(keep) if keep else None
    for f in sorted(d.glob("*.txt")):
        if keep_s and str(f) == keep_s:
            continue
        try:
            if now - f.stat().st_mtime <= HANDOFF_KEEP_S:
                continue
            f.unlink()
            for kind in ("gate", "pulled", "stood-down"):
                f.with_suffix(f".{kind}").unlink(missing_ok=True)
            out["files"] += 1
        except OSError as e:
            out["errors"] += 1
            _say(f"rmx handoff: could not reap {f}: {type(e).__name__}: {e}")
    led = d / HANDOFF_LEDGER
    if led.is_file():
        try:
            lines = led.read_text(encoding="utf-8").splitlines()
            kept = []
            for ln in lines:
                try:
                    t = _row_epoch(json.loads(ln))
                except ValueError:
                    t = None                  # an unreadable line stays: telemetry counts it
                if t is not None and now - t > HANDOFF_KEEP_S:
                    out["rows"] += 1
                else:
                    kept.append(ln)
            if out["rows"]:
                tmp = led.with_name(f".{led.name}.{os.getpid()}.tmp")
                tmp.write_text("".join(x + "\n" for x in kept), encoding="utf-8")
                os.replace(tmp, led)
        except OSError as e:
            out["errors"] += 1
            _say(f"rmx handoff: could not reap old rows of {led}: {type(e).__name__}: {e}")
    if out["gates"] or out["files"] or out["rows"]:
        _record_event(root, {"event": "reap", **out})
    return out


def handoff_pointer(written: dict, *, source: str, savestate: "dict | None") -> str:
    """The block SessionStart(compact|clear) injects instead of the report: the file's
    absolute path, its byte count, "read it before any other action; it is the authoritative
    state", and the R6 goal lines; at most `POINTER_MAX_BYTES`."""
    when = {"compact": "compaction", "clear": "/clear"}.get(source, source or "session start")
    path, n = written["path"], written["bytes"]
    lines = [f"Handoff after {when}: the full recall-state report is in {path} ({n} B)."]
    if written.get("gate_error"):
        lines.append(_clip(f"Read {path} before any other action: it is the authoritative "
                           f"state (the read gate could not be armed: "
                           f"{written['gate_error']}).", 600))
    else:
        lines.append(f"Read {path} before any other action: it is the authoritative state; "
                     f"every other tool call is denied until it is read.")
    room = POINTER_MAX_BYTES - _nbytes("\n".join(lines) + "\n") - 1
    if savestate:
        lines.extend(goal_pointer_lines(savestate.get("active_goal"), savestate.get("id") or "?",
                                        max_bytes=room))
    return _clip("\n".join(lines) + "\n", POINTER_MAX_BYTES)


def handoff_fallback(reason: str, fitted: str) -> str:
    """R3's fallback: one line saying the handoff file could not be written, then 25.1's
    budgeted inline report. Nothing is gated (no file was written)."""
    head = _clip(" ".join(f"handoff file could not be written ({reason}); the budgeted "
                          f"recall-state report follows inline and nothing is gated.".split()),
                 FALLBACK_HEAD_MAX_BYTES)
    return head + "\n" + fitted


# ---- R3b: the read gate, the pull marker and the re-injection --------------------------------


def _same_file(a, b: str) -> bool:
    if not isinstance(a, str) or not a:
        return False
    return os.path.realpath(a) == os.path.realpath(b)


def _load_gate(root: Path, session: str) -> "tuple[dict | None, str | None]":
    """(gate state, problem). (None, None) = this session is not gated."""
    gp = _gate_path(root, session)
    try:
        raw = gp.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None
    except OSError as e:
        return {"path": str(gp)}, f"its gate state {gp} is unreadable ({type(e).__name__}: {e})"
    try:
        st = json.loads(raw)
    except ValueError:
        st = None
    if not isinstance(st, dict) or not isinstance(st.get("path"), str):
        return {"path": str(gp)}, f"its gate state {gp} is not a JSON object with a path"
    return st, None


def _stand_down(root: Path, session: str, state: dict, reason: str) -> str:
    """Lift a gate that cannot be satisfied, record it, and return the ONE line that says so."""
    path = state.get("path") or "?"
    try:
        _marker_path(root, session, "stood-down").write_text(
            json.dumps({"session": session, "path": path, "reason": reason, "ts": _now_ts()}),
            encoding="utf-8")
        _gate_path(root, session).unlink(missing_ok=True)
    except OSError as e:
        reason += f"; the gate could not be cleared ({type(e).__name__}: {e})"
    _record_event(root, {"event": "stand_down", "session": session, "path": path,
                         "reason": reason})
    return f"rmx handoff gate stood down: {path} {reason}; nothing is gated."


def _unwritable_marker(root: Path, session: str) -> Path:
    """Where a stand-down is remembered when `handoffs/` itself cannot be written (b-3): beside
    it, in the store root, so the stand-down line is said once, not on every call."""
    return Path(root) / f".handoff-stood-down.{handoff_slug(session)}"


def gate_status(root: Path, session: "str | None") -> "tuple[str, dict | None, str]":
    """`("none" | "armed" | "stood_down", state, line)` for `session`. A gate whose file is
    missing, unreadable or past `GATE_EXPIRY_S` stands down here, once, with its line.

    A gate that could not be LIFTED stands down too (bsd-cah r1 #b-3, bug-308, 2026-11-24):
    when `handoffs/` is not writable, neither the pull marker nor the stand-down can persist
    there, and at cbbe9e3f the session stayed denied until the 24 h expiry. Now the gate
    stands down, remembered beside the dir so its one line is said once."""
    if not session:
        return "none", None, ""
    session = str(session)
    hd = handoffs_dir(root)
    um = _unwritable_marker(root, session)
    if um.exists():
        if os.access(hd, os.W_OK):
            _gate_path(root, session).unlink(missing_ok=True)
            um.unlink(missing_ok=True)
        return "none", None, ""
    if _marker_path(root, session, "pulled").exists():
        # A pull whose gate file could not be removed must not keep the session trapped.
        try:
            _gate_path(root, session).unlink(missing_ok=True)
        except OSError:
            pass                              # unwritable dir: handled below if still armed
        if not _gate_path(root, session).exists():
            return "none", None, ""
    state, problem = _load_gate(root, session)
    if state is None:
        return "none", None, ""
    if not os.access(hd, os.W_OK):
        path = state.get("path") or "?"
        line = (f"rmx handoff gate stood down: {path} cannot be marked read ({hd} is not "
                f"writable); nothing is gated.")
        try:
            um.write_text(json.dumps({"session": session, "path": path, "ts": _now_ts()}),
                          encoding="utf-8")
        except OSError as e:
            line += f" (the stand-down could not be remembered: {type(e).__name__}: {e})"
        _record_event(root, {"event": "stand_down", "session": session, "path": path,
                             "reason": f"{hd} is not writable"})
        return "stood_down", state, line
    if problem:
        return "stood_down", state, _stand_down(root, session, state, problem)
    path = state["path"]
    age = _now() - float(state.get("written_at") or 0)
    if age > GATE_EXPIRY_S:
        why = f"was written {age / 3600:.0f} h ago, past the {GATE_EXPIRY_S // 3600} h expiry"
        return "stood_down", state, _stand_down(root, session, state, why)
    if not os.path.isfile(path):
        return "stood_down", state, _stand_down(root, session, state, "is missing")
    if not os.access(path, os.R_OK):
        return "stood_down", state, _stand_down(root, session, state, "is not readable")
    return "armed", state, ""


def gate_decision(root: Path, envelope: dict) -> "tuple[str, str]":
    """PreToolUse: `("allow", "")`, `("deny", reason)` or `("stand_down", line)`. While the
    session's handoff is unread, every tool call but a Read of that exact file is denied."""
    if is_subagent(envelope):
        return "allow", ""
    status, state, line = gate_status(root, envelope.get("session_id"))
    if status != "armed":
        return ("stand_down", line) if status == "stood_down" else ("allow", "")
    path = state["path"]
    ti = envelope.get("tool_input") or {}
    if envelope.get("tool_name") == "Read" and isinstance(ti, dict) \
            and _same_file(ti.get("file_path"), path):
        return "allow", ""
    return "deny", (f"read {path} first: it is the authoritative state (the "
                    f"{state.get('source')} handoff, {state.get('bytes')} B); every other tool "
                    f"call is denied until that Read.")


def _offset_ok(ti: dict) -> bool:
    off = ti.get("offset")
    if off in (None, ""):
        return True
    try:
        return int(off) <= 1
    except (TypeError, ValueError):
        return False


def record_pull(root: Path, envelope: dict) -> "dict | None":
    """PostToolUse(Read): a successful Read of the session's handoff, from its start (no
    offset, or offset <= 1; lead ruling L200), lifts the gate, writes the `.pulled` marker and
    records the pull (path, bytes, seconds since the file was written). A subagent's Read is
    not the session's pull (b-1). A gate that cannot be lifted stands down (b-3): the result
    is then `{"stood_down": line}`. Anything else: None."""
    if is_subagent(envelope) or envelope.get("tool_name") != "Read":
        return None
    session = envelope.get("session_id")
    status, state, line = gate_status(root, session)
    if status == "stood_down":
        return {"stood_down": line}
    if status != "armed":
        return None
    ti = envelope.get("tool_input") or {}
    if not isinstance(ti, dict) or not _same_file(ti.get("file_path"), state["path"]) \
            or not _offset_ok(ti):
        return None
    resp = envelope.get("tool_response")
    if isinstance(resp, dict) and (resp.get("is_error") or resp.get("error")):
        return None
    session = str(session)
    path = state["path"]
    try:
        nbytes = os.stat(path).st_size
    except OSError:
        nbytes = int(state.get("bytes") or 0)
    seconds = round(max(0.0, _now() - float(state.get("written_at") or _now())), 3)
    row = {"session": session, "path": path, "bytes": nbytes, "seconds": seconds}
    # Lift FIRST, then mark (b-3): a marker that cannot be written must not leave the gate.
    try:
        _gate_path(root, session).unlink(missing_ok=True)
    except OSError as e:
        return {"stood_down": _stand_down(root, session, state,
                                          f"was read but its gate could not be lifted "
                                          f"({type(e).__name__}: {e})")}
    try:
        _marker_path(root, session, "pulled").write_text(
            json.dumps({**row, "ts": _now_ts()}), encoding="utf-8")
    except OSError as e:
        _say(f"rmx handoff pulled: the gate is lifted but the read marker for {session} could "
             f"not be written: {type(e).__name__}: {e}")
    _record_event(root, {"event": "pull", **row})
    return row


def remind_line(root: Path, session: "str | None", *, agent: bool = False) -> str:
    """UserPromptSubmit: the one-line pointer while the session's handoff is unread (so a
    tool-less reply cannot skip it for more than one turn), the stand-down line when the gate
    just stood down, else ''. Never for a subagent's prompt (b-1). At most the
    `handoff_remind` channel's bytes (hook_budget)."""
    if agent:
        return ""
    status, state, line = gate_status(root, session)
    if status == "stood_down":
        return line
    if status != "armed":
        return ""
    from refmatrix import hook_budget
    return _clip(f"Handoff pending: read {state['path']} before any other action; it is the "
                 f"authoritative state ({state.get('bytes')} B, written after "
                 f"{state.get('source')}).", hook_budget.resolve("handoff_remind", None) - 1)


def handoff_events(root: Path, *, since: "str | None" = None) -> dict:
    """`rmx telemetry --context`'s `handoff` view: every handoff written, pulled and stood
    down, from `<store>/handoffs/events.jsonl`. Compliance is `len(pulls) / len(written)`;
    `seconds` is from the write (the session's start) to the Read. Unreadable lines are
    counted, never skipped silently."""
    out: dict = {"written": [], "pulls": [], "stand_downs": [], "reaps": [],
                 "unreadable_lines": 0}
    p = handoffs_dir(root) / HANDOFF_LEDGER
    if not p.is_file():
        return out
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        out["error"] = f"{p}: {type(e).__name__}: {e}"
        return out
    keys = {"write": ("written", ("session", "path", "bytes", "source", "gate_error")),
            "pull": ("pulls", ("session", "path", "bytes", "seconds")),
            "stand_down": ("stand_downs", ("session", "path", "reason")),
            "reap": ("reaps", ("gates", "files", "rows", "errors"))}
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            out["unreadable_lines"] += 1
            continue
        if not isinstance(row, dict) or row.get("event") not in keys:
            out["unreadable_lines"] += 1
            continue
        if since and str(row.get("ts") or "") < since:
            continue
        bucket, fields = keys[row["event"]]
        out[bucket].append({"ts": row.get("ts"),
                            **{k: row[k] for k in fields if k in row}})
    return out


# ---- R1 / R2: the PreCompact instruction ----------------------------------------------------


def precompact_instruction(root: Path, session: "str | None", *, memdir: Path,
                           saved: "dict | None", save_failed: bool,
                           checkpoint: bool = True) -> str:
    """PreCompact's whole stdout (R2): at most one summary line naming the task in progress,
    the handoff is authoritative, do not restate files, decisions or plans; it names the
    save-state (R1: the one just written, else the last good one) and the handoff file the
    SessionStart(compact) entry will write (R3: "names the same first action"). Two lines,
    at most `PRECOMPACT_MAX_BYTES`."""
    from refmatrix import memory_layout
    hfile = (str(handoff_file_path(root, session)) if session
             else f"{handoffs_dir(root)}/<this session>.txt")
    after = f"after compaction its full report is written to {hfile} and read before any other action."
    line1 = ("Compaction summary: write at most one line, naming the task in progress. "
             "Do not restate files, decisions or plans.")

    def compose(with_paths: bool) -> str:
        if saved and not save_failed:
            ref = saved["mem_id"] + (f" ({saved['target']})" if with_paths else "")
            line2 = f"The handoff is authoritative: save-state {ref}; {after}"
        else:
            lead = ("This session's save-state could not be written (the cause is on stderr)"
                    if save_failed else
                    "No checkpoint was saved (precompact_checkpoint is off)")
            try:
                cands = memory_layout.iter_savestates(memdir) if memdir.is_dir() else []
            except OSError as e:
                _say(f"rmx precompact: could not list the save-states in {memdir}: "
                     f"{type(e).__name__}: {e}")
                cands = []
            if cands:
                last = Path(cands[0])
                ref = last.stem + (f" ({last})" if with_paths else "")
                line2 = f"{lead}; the last good handoff, {ref}, is authoritative; {after}"
            else:
                line2 = (f"{lead}, and no earlier save-state exists; the report written after "
                         f"compaction to {hfile} is authoritative and is read before any "
                         f"other action.")
        return line1 + "\n" + line2 + "\n"

    text = compose(True)
    if _nbytes(text) > PRECOMPACT_MAX_BYTES:
        text = compose(False)
    return _clip(text, PRECOMPACT_MAX_BYTES)
