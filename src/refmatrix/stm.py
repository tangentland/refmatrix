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
import typing
from contextlib import contextmanager
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


def _proc_info(pid: int) -> "tuple[int, str, str] | None":
    """`(ppid, executable path, start)` for `pid` with no subprocess, or None when the process is
    gone or the lookup is unavailable (bug-109 r2). macOS: libproc `proc_pidinfo` +
    `proc_pidpath` (~1 us; the `ps` it replaces cost ~60 ms per hook under load and could time
    out). Linux: /proc. `start` is the kernel start time, unique per process incarnation."""
    import sys
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if sys.platform == "darwin":
        lib = _libproc()
        if lib is None:
            return None
        import ctypes
        info = _BSDInfo()
        if lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != \
                ctypes.sizeof(info):
            return None
        buf = ctypes.create_string_buffer(4096)
        n = lib.proc_pidpath(pid, buf, 4096)
        path = buf.value.decode("utf-8", "replace") if n > 0 else \
            info.comm.decode("utf-8", "replace")
        return int(info.ppid), path, f"{info.start_sec}.{info.start_usec:06d}"
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rindex(")") + 2:].split()
        try:
            path = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            path = stat[stat.index("(") + 1:stat.rindex(")")]
        return int(fields[1]), path, fields[19]
    except (OSError, ValueError, IndexError):
        return None


_LIBPROC = None


def _libproc():
    global _LIBPROC, _BSDInfo
    if _LIBPROC is None:
        import ctypes

        class _Info(ctypes.Structure):   # struct proc_bsdinfo, 136 bytes
            _fields_ = [("_h", ctypes.c_uint32 * 4), ("ppid", ctypes.c_uint32),
                        ("_ids", ctypes.c_uint32 * 7), ("comm", ctypes.c_char * 16),
                        ("name", ctypes.c_char * 32), ("_m", ctypes.c_uint32 * 5),
                        ("nice", ctypes.c_int32), ("start_sec", ctypes.c_uint64),
                        ("start_usec", ctypes.c_uint64)]
        _BSDInfo = _Info
        try:
            _LIBPROC = ctypes.CDLL("/usr/lib/libproc.dylib")
        except OSError:
            _LIBPROC = False
    return _LIBPROC or None


_BSDInfo = None


def _is_claude(path: str) -> bool:
    """A Claude Code executable: `.../claude`, or the native installer's versioned binary
    `.../claude/versions/<x.y.z>` (whose kernel name is the version, not `claude`)."""
    p = Path(path)
    return p.name == "claude" or p.parent.name == "versions" and p.parent.parent.name == "claude"


def _proc_start(pid: int) -> str | None:
    """The start time of `pid`, or None when no such process exists. Two processes that held the
    same pid at different times have different start times, so a pid pointer is trusted only
    while this still matches what it recorded (bug-109)."""
    info = _proc_info(pid)
    return info[2] if info else None


def _ps_comm_chain() -> "list[tuple[int, str]] | None":
    """Fallback ancestor chain `[(pid, comm), ...]` from `ps`, whose `comm` is argv[0] (`claude`
    for an npm-installed CLI running under `node`). None when `ps` cannot run."""
    import subprocess
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True,
                             text=True, timeout=3.0).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    table: dict[int, tuple[int, str]] = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), Path(parts[2].strip()).name)
    if not table:
        return None
    chain, pid = [], os.getpid()
    for _ in range(16):
        if pid not in table:
            break
        chain.append((pid, table[pid][1]))
        if table[pid][0] <= 1 or table[pid][0] in [c[0] for c in chain]:
            break
        pid = table[pid][0]
    return chain


def owner_lookup() -> "tuple[int | None, str]":
    """`(owner_pid, status)`, status one of `found`, `none` (not under Claude Code: a plain
    terminal, a daemon) or `failed` (the process table could not be read, so the owner is
    UNKNOWN, not absent: r2 #b-1).

    `$CLAUDE_PID` wins only when it names a real ancestor (Claude Code sets it per child; an
    inherited one can name an OUTER Claude, r1 #s-1); else the nearest ancestor whose
    executable is Claude's; else, when the kernel lookup is unavailable, the `ps` argv[0]
    chain."""
    chain: list[int] = []
    paths: dict[int, str] = {}
    pid = os.getpid()
    for _ in range(16):
        info = _proc_info(pid)
        if info is None:
            break
        chain.append(pid)
        paths[pid] = info[1]
        if info[0] <= 1 or info[0] in chain:
            break
        pid = info[0]
    if len(chain) < 2:
        ps = _ps_comm_chain()
        if not ps:
            return None, "failed"
        chain = [c[0] for c in ps]
        env = os.environ.get("CLAUDE_PID")
        if env and env.isdigit() and int(env) in chain:
            return int(env), "found"
        for cpid, comm in ps[1:]:
            if comm == "claude":
                return cpid, "found"
        return None, "none"
    env = os.environ.get("CLAUDE_PID")
    if env and env.isdigit() and int(env) in chain:
        return int(env), "found"     # the common case under Claude: no subprocess at all
    # No usable $CLAUDE_PID (the rare path): the NEAREST ancestor that is Claude by executable
    # OR by argv[0] (an npm-installed CLI runs as `node`; a re-exec keeps argv[0]), so one `ps`
    # call supplies the argv[0] names.
    argv0 = dict(_ps_comm_chain() or [])
    for cpid in chain[1:]:
        if _is_claude(paths.get(cpid, "")) or argv0.get(cpid) == "claude":
            return cpid, "found"
    return None, "none"


def owner_claude_pid(*, long_lived: bool = False) -> int | None:
    """The Claude Code process this one runs under (bug-109). The long-lived MCP server is
    spawned BY the Claude process, so its owner is `os.getppid()` (19.0 R5) and nothing in its
    own environment is consulted. A per-call process: `owner_lookup()`."""
    if long_lived:
        return os.getppid()
    return owner_lookup()[0]


# ---- session pointers + the pointer-error log (bug-109, task 21.1 R9 D3-D9) ----------------
#
# bug-109 (2026-10-14) kept one pointer per Claude pid under EACH store's `stm/by-pid/`. A
# pointer belongs to a Claude PROCESS, not a store: when the session's cwd moved into another
# tree the input hook wrote it into a store the MCP server never read (r1 #m-4). Task 21.1 D3
# moves pointers and their error log to ONE user-level directory, `<global store root>/by-pid/`,
# and D8 makes every mutation of that machine-wide log go through one locked writer.

_ERRORS_MAX_BYTES = 256 * 1024
_ERRORS_WINDOW_S = 86400.0

# The STM hook reasons (19.0) are reported apart from the session-pointer reasons (D6 (2)).
STM_HOOK_REASONS = frozenset({"sweep-failed", "composite-failed", "enrichment-unresolved"})


def pointer_dir() -> Path:
    """`<hub.global_store_root()>/by-pid/` (D3): ONE location for every store root. Creates
    only `by-pid/` itself, and only when the global store root already exists — no read ever
    creates a store (bug-109 r2 #s-1)."""
    from refmatrix import hub
    d = Path(hub.global_store_root()) / "by-pid"
    if d.parent.is_dir() and not d.is_dir():
        try:
            d.mkdir(exist_ok=True)
        except OSError as e:
            import sys
            print(f"rmx: session-pointer dir not created ({d}): {e}", file=sys.stderr)
    return d


def errors_log_path() -> Path:
    """The ONE name of the pointer-error log (round-9 #m9-2): every reader, writer and
    report text takes the path from here."""
    return pointer_dir() / "_errors.jsonl"


def pid_pointer_path(pid: int) -> Path:
    return pointer_dir() / f"{int(pid)}.json"


def proc_identity(pid: "int | None") -> "tuple[int, str] | None":
    """`(pid, start)` for a live process, or None when its start time cannot be read — the
    ONE accessor for a start value (round-10 #m10-2). It judges no liveness."""
    if pid is None:
        return None
    start = _proc_start(int(pid))
    return (int(pid), start) if start is not None else None


def liveness_available() -> bool:
    """Whether a process lookup works at all here (round-9 #m9-1): this process's own start
    time is readable. Called ONCE per SessionStart run before any liveness decision, so an
    unavailable lookup never reads every live owner as dead."""
    return _proc_start(os.getpid()) is not None


def start_token(start: "str | None") -> "str | None":
    """An 8-hex token of a process start time (the migration claim names carry it)."""
    import hashlib
    return hashlib.sha1(start.encode()).hexdigest()[:8] if start is not None else None


def owner_alive(pid: "int | None", pid_start: "str | None" = None, *,
                start_token: "str | None" = None) -> "bool | None":
    """THE liveness predicate (D6). None when the row is UNOWNED (no pid, or no start value
    to compare) — nothing else; True when `pid` is still the process that held `pid_start`
    (or whose start hashes to `start_token`); False otherwise. Callers check
    `liveness_available()` first: with no process lookup every pid reads as dead here."""
    if pid is None or (pid_start is None and start_token is None):
        return None
    cur = _proc_start(int(pid))
    if cur is None:
        return False
    if start_token is not None:
        return _start_token_of(cur) == start_token
    return cur == pid_start


_start_token_of = start_token


def _errors_lock_path() -> Path:
    return pointer_dir() / "_errors.lock"


@contextmanager
def _errors_locked():
    """`fcntl.flock(LOCK_EX)` on `<pointer_dir>/_errors.lock` (D8, round-8 #nm-2): the log is
    machine-wide, so bug-109's unlocked read-modify-write halving lost appends of other
    processes. Raises OSError when the global store root is absent."""
    import fcntl
    d = pointer_dir()
    if not d.is_dir():
        raise OSError(f"pointer dir absent (no global store root): {d}")
    fh = open(_errors_lock_path(), "a")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _parse_error_line(line: str) -> "dict | None":
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict):
        return None
    try:
        t = float(row["t"])
    except (KeyError, TypeError, ValueError):
        return None
    if t != t:                            # NaN
        return None
    return row


def _watermark_path(pid: int) -> Path:
    return pointer_dir() / f"_errors.seen.{int(pid)}"


def _root_watermark_path(root: Path) -> Path:
    import hashlib
    h = hashlib.sha1(str(root).encode()).hexdigest()[:12]
    return pointer_dir() / f"_errors.seen.root.{h}"


def _owner_watermark_t(key: str) -> "float | None":
    """The `t` watermark of owner `<pid>:<start>`, or None when it has no watermark file (or
    the file belongs to an earlier process that held the pid)."""
    pid, _, start = key.partition(":")
    try:
        d = json.loads(_watermark_path(int(pid)).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("pid_start") != start:
        return None
    try:
        return float(d.get("t"))
    except (TypeError, ValueError):
        return None


def _owner_key(row: dict) -> "str | None":
    if row.get("owner") is None or row.get("owner_start") is None:
        return None
    return f"{row['owner']}:{row['owner_start']}"


def _truncation_row(removed: "list[str]", oldest_kept_t: "float | None") -> dict:
    """The `errors-truncated` row for a halving (D6). `dropped` and `dropped_by_root` roll up
    the removed truncation rows' counts (round-9 #m9-3), so non-truncation rows + Σ`dropped`
    = every row ever appended. `unseen_dropped` is a NEWS counter (round-10 #m10-3): per owner,
    removed rows above that owner's watermark at halving time (no file: all), and a removed
    truncation row's count only when that row's own `t` is above the watermark."""
    dropped = 0
    by_root: dict[str, int] = {}
    unseen: dict[str, int] = {}
    wm_cache: dict[str, "float | None"] = {}

    def _above(key: str, t: float) -> bool:
        if key not in wm_cache:
            wm_cache[key] = _owner_watermark_t(key)
        w = wm_cache[key]
        return w is None or t > w

    for line in removed:
        if not line.strip():
            continue
        row = _parse_error_line(line)
        if row is None:
            dropped += 1                      # an unreadable line was a row too
            continue
        if row.get("reason") == "errors-truncated":
            dropped += int(row.get("dropped") or 0)
            for k, v in (row.get("dropped_by_root") or {}).items():
                by_root[k] = by_root.get(k, 0) + int(v)
            for k, v in (row.get("unseen_dropped") or {}).items():
                if _above(k, float(row["t"])):
                    unseen[k] = unseen.get(k, 0) + int(v)
            continue
        dropped += 1
        if row.get("root"):
            by_root[str(row["root"])] = by_root.get(str(row["root"]), 0) + 1
        key = _owner_key(row)
        if key is not None and _above(key, float(row["t"])):
            unseen[key] = unseen.get(key, 0) + 1
    return {"t": time.time(), "reason": "errors-truncated", "dropped": dropped,
            "oldest_kept_t": oldest_kept_t, "dropped_by_root": by_root,
            "unseen_dropped": unseen, "owner": None, "owner_start": None}


def _append_error_rows(rows: "list[dict]", *, skip_existing_migrated: bool = False) -> bool:
    """The ONLY function that opens `_errors.jsonl` for writing (D8). Under ONE hold of
    `_errors_locked()`: when the file is over `_ERRORS_MAX_BYTES` it writes the newer half
    plus the `errors-truncated` row to a tmp file and `os.replace`s it, then appends `rows`,
    one `write()` each. `skip_existing_migrated` is the migration's idempotence check, made
    inside the same hold: a row whose `(t, reason, migrated_from)` is already in the log is
    not appended again. Returns False (never raises) when the lock or the write failed."""
    p = errors_log_path()
    try:
        with _errors_locked():
            try:
                size = p.stat().st_size
            except FileNotFoundError:
                size = 0
            if size > _ERRORS_MAX_BYTES:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                half = len(lines) // 2
                kept = lines[half:]
                oldest = None
                for ln in kept:
                    r = _parse_error_line(ln)
                    if r is not None:
                        oldest = float(r["t"])
                        break
                trow = _truncation_row(lines[:half], oldest)
                tmp = p.with_name(p.name + ".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write("".join(kept))
                    f.write(json.dumps(trow) + "\n")
                os.replace(tmp, p)
            if skip_existing_migrated and p.exists():
                have = set()
                for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    r = _parse_error_line(ln)
                    if r is not None and r.get("migrated_from"):
                        have.add((float(r["t"]), r.get("reason"), r.get("migrated_from")))
                rows = [r for r in rows
                        if (float(r["t"]), r.get("reason"), r.get("migrated_from")) not in have]
            if rows:
                fd = os.open(str(p), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
                try:
                    for r in rows:
                        os.write(fd, (json.dumps(r) + "\n").encode("utf-8"))
                finally:
                    os.close(fd)
        return True
    except (OSError, ValueError, TypeError):
        return False


def record_pointer_error(reason: str, *, root: Path, owner: "int | None", **fields) -> bool:
    """Append one SCOPED row to the user-level pointer-error log (D8). Every hook ends in
    `2>/dev/null || true`, so stderr is not a channel there: a pointer that was not written,
    a session that did not resolve, an STM hook step that failed, is recorded HERE, and
    `rmx recall-state`, `rmx focus topics` and the SessionStart writer report it.

    `root` is the row's SCOPE (the writer's store root), not the file's location; `owner` is
    the Claude pid the caller resolved (None when it found none), and `owner_start` is taken
    from `proc_identity(owner)`. Never raises; returns whether the row was written."""
    ident = proc_identity(owner) if owner is not None else None
    row = {"t": time.time(), "reason": reason, "root": os.path.abspath(str(root)),
           "owner": int(owner) if owner is not None else None,
           "owner_start": ident[1] if ident else None, **fields}
    return _append_error_rows([row])


def _row_in_scope(row: dict, root: "Path | None", owner: "tuple[int, str] | None") -> bool:
    if row.get("reason") == "errors-truncated":
        # The one global row: surfaced to a reader whose scope has a non-zero count in it.
        if root is not None and int((row.get("dropped_by_root") or {}).get(str(root), 0)) <= 0:
            return False
        if owner is not None and int(
                (row.get("unseen_dropped") or {}).get(f"{owner[0]}:{owner[1]}", 0)) <= 0:
            return False
        return True
    if root is not None and row.get("root") != str(root):
        return False
    if owner is not None and (row.get("owner") != owner[0]
                              or row.get("owner_start") != owner[1]):
        return False
    return True


def read_pointer_errors(*, root: "Path | None" = None,
                        owner: "tuple[int, str] | None" = None,
                        since: float = 0.0) -> "list[dict]":
    """Rows of the user-level log with `t >= since`, oldest first, filtered by scope (D6):
    `root=` keeps rows of that store root, `owner=(pid, pid_start)` rows of that owner; both
    keep rows matching both. A line that does not parse (bug-109 r3 #m-2) is returned as
    `{"reason": "unreadable-line", "line": n}` and a row with no `root` (a writer defect) as
    `{"reason": "unscoped-row", ...}` to every scoped reader — counted apart, never attributed
    to the reader's scope silently. No legacy `<root>/stm/by-pid/` file is read (round-7
    #s-3)."""
    out: list[dict] = []
    try:
        lines = errors_log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    scoped = root is not None or owner is not None
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        row = _parse_error_line(line)
        if row is None:
            out.append({"reason": "unreadable-line", "line": n})
            continue
        if float(row["t"]) < since:
            continue
        if scoped and "root" not in row and row.get("reason") != "errors-truncated":
            out.append({**row, "reason": "unscoped-row", "unscoped_reason": row.get("reason")})
            continue
        if not scoped or _row_in_scope(row, root, owner):
            out.append(row)
    return out


def write_pid_pointer(pid: int, session: str, *, root: Path, hook: str = "input") -> bool:
    """Record that Claude process `pid` is now running `session` (bug-109; D3: under the
    user-level `pointer_dir()`, D4: `hook` names the writer — `input` or
    `session-start:<source>`). The input hook calls this first on every envelope with a
    session id, and the SessionStart writer on start/resume/clear/compact, so after `/clear`
    the pointer names the new session before the first prompt. Returns True when the file was
    (re)written, False when it already named `session` AND this process incarnation, or when
    it was REFUSED: a pid whose start time cannot be read is recorded as `ps-failed` (r1 #b-1;
    its owner_start is null, so the row is UNOWNED, #nm-1). `root` only scopes the error row.
    Raises OSError when the pointer dir cannot be written (the hook records `write-failed`)."""
    p = pid_pointer_path(pid)
    ident = proc_identity(pid)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if ident is not None and isinstance(d, dict) and d.get("session") == session \
                and d.get("pid_start") == ident[1]:
            return False
    except (OSError, ValueError):
        pass
    if ident is None:
        record_pointer_error("ps-failed", root=root, owner=int(pid), session=session)
        return False
    if not p.parent.is_dir():
        raise OSError(f"pointer dir absent (no global store root): {p.parent}")
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"session": session, "pid": int(pid), "pid_start": ident[1],
                               "t": time.time(), "hook": hook}), encoding="utf-8")
    tmp.replace(p)
    return True


def read_pid_pointer(pid: int, *, root: Path) -> "str | None":
    """The session Claude process `pid` is running, per its pointer, or None. A missing file
    is not an error by itself (the resolver's row covers it); a pointer that is present but
    not a JSON object is recorded as `pointer-unreadable`, and one whose `pid_start` no
    longer matches (pid reuse) as `pointer-stale` (D5) — never None silently. Liveness is
    judged by `owner_alive` only (round-9 #m9-1)."""
    p = pid_pointer_path(pid)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        record_pointer_error("pointer-unreadable", root=root, owner=int(pid), error=str(e))
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        d = None
    if not isinstance(d, dict) or not d.get("session"):
        record_pointer_error("pointer-unreadable", root=root, owner=int(pid))
        return None
    if owner_alive(int(pid), d.get("pid_start")) is not True:
        record_pointer_error("pointer-stale", root=root, owner=int(pid),
                             pointer_session=str(d.get("session")))
        return None
    return str(d["session"])


# ---- the SessionStart writer's surfacing, migration and prune (D4, D6, D7) ----------------

def _reason_counts(rows: "list[dict]") -> str:
    """`reason=n …` in first-seen order; `errors-truncated` rows print their counts."""
    counts: dict[str, int] = {}
    trunc: list[str] = []
    for r in rows:
        reason = str(r.get("reason"))
        if reason == "errors-truncated":
            trunc.append(f"errors-truncated(dropped={int(r.get('dropped') or 0)})")
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return " ".join([f"{k}={v}" for k, v in counts.items()] + trunc)


def advance_owner_watermark(owner: "tuple[int, str]") -> "list[dict]":
    """Set (1) of the SessionStart writer (D6): its OWNER's rows added since that owner's
    last surfacing, selected and the per-owner watermark `_errors.seen.<pid>` = `{pid_start,
    t}` advanced inside ONE hold of the lock. Keyed on `t`, never a byte offset: the halving
    moves every offset. A watermark file whose `pid_start` differs is an earlier process that
    held the pid, and is ignored. Unreadable lines carry no `t` and come back every time."""
    with _errors_locked():
        wp = _watermark_path(owner[0])
        w = None
        try:
            d = json.loads(wp.read_text())
            if isinstance(d, dict) and d.get("pid_start") == owner[1]:
                w = float(d["t"])
        except (OSError, ValueError, TypeError, KeyError):
            w = None
        rows = read_pointer_errors(owner=owner, since=w if w is not None else 0.0)
        rows = [r for r in rows if r.get("reason") == "unreadable-line"
                or w is None or float(r["t"]) > w]
        ts = [float(r["t"]) for r in rows if r.get("t") is not None]
        if ts:
            tmp = wp.with_name(wp.name + ".tmp")
            tmp.write_text(json.dumps({"pid_start": owner[1], "t": max(ts)}))
            os.replace(tmp, wp)
    return rows


def consumed_ended_sessions(root: Path) -> "tuple[list[dict], int, int]":
    """Set (2) of the SessionStart writer (D6, round-9 #s9-2): this root's rows of DEAD
    owners not yet shown, consumed BY OWNER — the per-root file `_errors.seen.root.<h>` =
    `{root, consumed: [[pid, pid_start, t_max], …]}` — inside one hold of the lock. A per-root
    `t` watermark lost an older live owner's rows once a younger dead owner's were printed.
    Rows of a live owner are neither printed nor consumed; unowned rows (null owner or null
    owner_start, #nm-1) are only counted. Entries older than the 24 h window are pruned in the
    same hold. Callers check `liveness_available()` first. Returns (rows, unowned, collision)."""
    now = time.time()
    since = now - _ERRORS_WINDOW_S
    collision = 0
    with _errors_locked():
        rf = _root_watermark_path(root)
        consumed: dict[tuple, float] = {}
        before = None
        try:
            d = json.loads(rf.read_text())
            before = d
            if isinstance(d, dict) and d.get("root") == str(root):
                for e in d.get("consumed") or []:
                    consumed[(int(e[0]), str(e[1]))] = float(e[2])
            else:
                collision = 1
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, IndexError):
            collision = 1
        picked: list[dict] = []
        unowned = 0
        for r in read_pointer_errors(root=root, since=since):
            if r.get("reason") in ("unreadable-line", "unscoped-row", "errors-truncated"):
                continue
            if r.get("owner") is None or r.get("owner_start") is None:
                unowned += 1
                continue
            key = (int(r["owner"]), str(r["owner_start"]))
            if owner_alive(key[0], key[1]) is not False:
                continue
            t_max = consumed.get(key)
            if t_max is not None and float(r["t"]) <= t_max:
                continue
            picked.append(r)
        for r in picked:
            key = (int(r["owner"]), str(r["owner_start"]))
            consumed[key] = max(consumed.get(key, float("-inf")), float(r["t"]))
        consumed = {k: v for k, v in consumed.items() if v >= since}
        after = {"root": str(root),
                 "consumed": [[k[0], k[1], v] for k, v in
                              sorted(consumed.items(), key=lambda kv: kv[1])]}
        if after != before:
            tmp = rf.with_name(rf.name + ".tmp")
            tmp.write_text(json.dumps(after))
            os.replace(tmp, rf)
    return picked, unowned, collision


def unowned_in_root(root: Path) -> int:
    """Unowned rows (null owner or null owner_start) of `root` in the last 24 h."""
    n = 0
    for r in read_pointer_errors(root=root, since=time.time() - _ERRORS_WINDOW_S):
        if r.get("reason") in ("unreadable-line", "unscoped-row", "errors-truncated"):
            continue
        if r.get("owner") is None or r.get("owner_start") is None:
            n += 1
    return n


def prune_dead_pointer_files() -> int:
    """D7: remove each pointer file and each `_errors.seen.<pid>` watermark whose process is
    dead (`owner_alive(...) is False`), and each per-root watermark whose root path no longer
    exists. A pointer is only a cache of the process relation and a watermark only of what
    its process was shown, so nothing is lost. Callers check `liveness_available()` first:
    with no process lookup every live pointer would read as dead."""
    d = pointer_dir()
    if not d.is_dir():
        return 0
    n = 0
    with _errors_locked():
        for f in sorted(d.iterdir()):
            name = f.name
            try:
                if name.endswith(".json") and name[:-5].isdigit():
                    data = json.loads(f.read_text())
                    if isinstance(data, dict) and owner_alive(
                            int(name[:-5]), data.get("pid_start")) is False:
                        f.unlink()
                        n += 1
                elif name.startswith("_errors.seen.root."):
                    data = json.loads(f.read_text())
                    if isinstance(data, dict) and data.get("root") \
                            and not Path(data["root"]).exists():
                        f.unlink()
                        n += 1
                elif name.startswith("_errors.seen.") and name[13:].isdigit():
                    data = json.loads(f.read_text())
                    if isinstance(data, dict) and owner_alive(
                            int(name[13:]), data.get("pid_start")) is False:
                        f.unlink()
                        n += 1
            except (OSError, ValueError):
                continue                  # an unreadable file is not judged dead
    return n


def _legacy_dir(root: Path) -> Path:
    return stm_dir(root) / "by-pid"


def drop_legacy_pointers_migration(root: Path) -> int:
    """D3: bug-109's per-store pointer files `<root>/stm/by-pid/<pid>.json` are never read;
    the SessionStart writer deletes them, counted."""
    n = 0
    ld = _legacy_dir(root)
    if not ld.is_dir():
        return 0
    for f in ld.glob("*.json"):
        if f.stem.isdigit():
            try:
                f.unlink()
                n += 1
            except OSError:
                continue
    return n


def migrate_legacy_errors(root: Path, *, liveness: bool) -> "tuple[list[str], list[str]]":
    """D6's one-shot migration of bug-109's `<root>/stm/by-pid/_errors.jsonl` into the
    user-level log (round-7 #s-3; rounds 8-11). Returns (stdout lines, stderr lines).

    1. CLAIM by `os.rename` to `_errors.migrating.<pid>.<start_token>.jsonl` (own identity
       from `proc_identity`; none → skipped, the legacy file left for the next run). A run
       that loses the race gets FileNotFoundError and counts `migrate-claim-lost`. Before
       claiming, a claim whose claimant is DEAD (`owner_alive(pid, start_token=…) is False`)
       is adopted, so a crash leaves no orphan; a live or unknown claimant's claim is left.
    2. APPEND each parseable row with its ORIGINAL `t`, `root` and `migrated_from`, plus one
       `legacy-unreadable` row stamped with the legacy file's mtime, through the ONE writer
       with its `(t, reason, migrated_from)` idempotence check inside the lock.
    3. RENAME the claim to `_errors.migrated.jsonl` only when every append returned True;
       otherwise say `migration incomplete` and leave the claim for the next run."""
    out: list[str] = []
    err: list[str] = []
    ld = _legacy_dir(root)
    legacy = ld / "_errors.jsonl"
    claims = sorted(ld.glob("_errors.migrating.*.jsonl")) if ld.is_dir() else []
    if not legacy.exists() and not claims:
        out.append("migrated=0")
        return out, err
    ident = proc_identity(os.getpid())
    if ident is None:
        out.append("migration skipped: process lookup unavailable")
        return out, err
    own_claim = ld / f"_errors.migrating.{ident[0]}.{start_token(ident[1])}.jsonl"
    migrated_total = 0
    lost = 0
    todo: "list[tuple[Path, float | None]]" = []
    if liveness:
        for c in claims:
            parts = c.name.split(".")
            # _errors.migrating.<pid>.<token>.jsonl
            if len(parts) != 5 or not parts[2].isdigit() or c == own_claim:
                continue
            if owner_alive(int(parts[2]), start_token=parts[3]) is not False:
                continue
            try:
                mtime = c.stat().st_mtime
                os.rename(c, own_claim)
            except FileNotFoundError:
                lost += 1
                continue
            todo.append((own_claim, mtime))
            break                         # one claim at a time under our own name
    if not todo and legacy.exists():
        try:
            mtime = legacy.stat().st_mtime
            os.rename(legacy, own_claim)
            todo.append((own_claim, mtime))
        except FileNotFoundError:
            lost += 1
    for claim, mtime in todo:
        rows: list[dict] = []
        bad = 0
        try:
            text = claim.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            lost += 1
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            r = _parse_error_line(line)
            if r is None:
                bad += 1
                continue
            r = dict(r)
            r["root"] = os.path.abspath(str(root))
            r["migrated_from"] = str(legacy)
            r.setdefault("owner", None)
            r.setdefault("owner_start", None)
            rows.append(r)
        if bad:
            rows.append({"t": mtime, "reason": "legacy-unreadable", "n": bad,
                         "root": os.path.abspath(str(root)), "migrated_from": str(legacy),
                         "owner": None, "owner_start": None})
        before = _count_migrated(str(legacy), root)
        ok = _append_error_rows(rows, skip_existing_migrated=True)
        if not ok:
            err.append(f"migration incomplete: {len(rows)} rows not written (global store "
                       f"root absent or unwritable)")
            continue
        after = _count_migrated(str(legacy), root)
        migrated_total += max(0, after[0] - before[0])
        try:
            os.rename(claim, ld / "_errors.migrated.jsonl")
        except FileNotFoundError:
            lost += 1
            continue
    if lost:
        out.append(f"migrate-claim-lost={lost}")
    if not err and (todo or not lost):
        out.append(f"migrated={migrated_total}")
    return out, err


def _count_migrated(migrated_from: str, root: Path) -> "tuple[int, int]":
    """(parseable legacy rows, legacy-unreadable rows) already migrated from one file."""
    rows = [r for r in read_pointer_errors(root=root)
            if r.get("migrated_from") == migrated_from]
    return (sum(1 for r in rows if r.get("reason") != "legacy-unreadable"),
            sum(1 for r in rows if r.get("reason") == "legacy-unreadable"))


def session_start_surfacing(root: Path, owner: "int | None"
                            ) -> "tuple[list[str], list[str]]":
    """Everything the SessionStart writer (D4) does after its pointer write, as (stdout
    lines, stderr lines): the one-shot migration of this root's legacy files (D6, D3), set
    (1) — its owner's rows — and set (2) — this root's ended-session rows, consumed by owner
    — on STDOUT where SessionStart output reaches the agent (round-8 #ns-2), the unowned
    count, and the prune (D7). `liveness_available()` is read ONCE; with it False nothing is
    consumed, adopted or pruned and each step says so."""
    out: list[str] = []
    err: list[str] = []
    live = liveness_available()
    mig_out, mig_err = migrate_legacy_errors(root, liveness=live)
    err += mig_err
    dropped_ptrs = drop_legacy_pointers_migration(root)
    # (1) the owner's rows
    if owner is not None:
        ident = proc_identity(owner)
        if ident is None:
            out.append("own rows skipped: process lookup unavailable")
        else:
            try:
                own = advance_owner_watermark(ident)
            except OSError as e:
                err.append(f"rmx: session-pointer surfacing failed: {e}")
                own = []
            if own:
                out.append(f"rmx: pointer errors of this Claude process: "
                           f"{_reason_counts(own)} (see rmx recall-state)")
    # (2) this root's ended sessions
    if not live:
        out.append("ended_sessions skipped: process lookup unavailable")
        unowned = unowned_in_root(root)
    else:
        try:
            ended, unowned, collision = consumed_ended_sessions(root)
        except OSError as e:
            err.append(f"rmx: ended-session surfacing failed: {e}")
            ended, unowned, collision = [], unowned_in_root(root), 0
        if ended:
            out.append(f"ended_sessions: {_reason_counts(ended)} (see rmx recall-state)")
        if collision:
            out.append(f"watermark-collision={collision}")
    if unowned:
        out.append(f"unowned_in_root={unowned} (see rmx recall-state)")
    # D7 prune
    if not live:
        out.append("prune skipped: process lookup unavailable")
        pruned = None
    else:
        try:
            pruned = prune_dead_pointer_files()
        except OSError as e:
            err.append(f"rmx: by-pid prune failed: {e}")
            pruned = None
    status = list(mig_out) + [f"legacy_pointers_dropped={dropped_ptrs}"]
    if pruned is not None:
        status.append(f"pruned={pruned}")
    out.append("rmx session-pointer: " + " ".join(status))
    return out, err


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
        if kind == "input":
            # R9: an input event carries its prompt's sha256 and a sub-second epoch, so a
            # pre-prompt snapshot can be matched to it (the ring's `ts` is cut to the second).
            ev["t"] = time.time()
            ev["prompt_sha"] = prompt_sha(terse)
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

    # ---- the pre-prompt state (task 21.1 R9) --------------------------------
    #
    # The recall and scan hooks run IN PARALLEL with `focus hook --event input`
    # (Claude Code runs an event's hooks in parallel), and the input hook changes
    # the ring and the graph they read: its sweep folds parked calls in, then the
    # input record ingests the prompt. Live 2026-10-14: 17 of session db80475a's
    # 78 recorded prompts directly followed a sweep. No wall-clock margin on a
    # second-truncated `ts` separates this prompt from the last, so the input
    # hook writes ONE snapshot as its FIRST state change, and every prompt-time
    # reader resolves its phase inputs through `pre_prompt_state`.

    def _pre_path(self) -> Path:
        return self._dir / f"{self._key}.pre.json"

    def events_n(self) -> int:
        """R9's event count: complete ring lines whose `origin` is `parent` or
        absent (19.0 R2's field), so a background subagent's events landing in
        the parent ring do not move it. Until 19.0 R2 ships no event carries
        `origin` and every line counts (stated in the R7 usage report's footer)."""
        if not self._path.exists():
            return 0
        n = 0
        try:
            with self._path.open("rb") as f:
                for ln in f:
                    if not ln.endswith(b"\n"):
                        continue                  # a torn last line is not complete
                    if b'"origin"' not in ln:
                        n += 1
                        continue
                    try:
                        if json.loads(ln).get("origin") in (None, "parent"):
                            n += 1
                    except ValueError:
                        continue
        except OSError:
            return 0
        return n

    def snapshot_pre_prompt(self, prompt: str) -> None:
        """Write `<session>.pre.json` = `{prompt_sha, wall, turn, events_n, graph,
        topic_cache, topic_match}` by tmp + `os.replace`. The input hook calls it
        for EVERY non-empty prompt, ambient included (the sweep changes state on
        an ambient prompt too), BEFORE its sweep and its input record — so a
        reader that finds no matching snapshot after reading the live state read
        a state the input hook had not yet touched."""
        g = self._load_graph()
        rec = {"prompt_sha": prompt_sha(prompt), "wall": time.time(),
               "turn": int(g.get("turn", 0)), "events_n": self.events_n(),
               "graph": g, "topic_cache": {}, "topic_match": {}}
        self._dir.mkdir(parents=True, exist_ok=True)
        p = self._pre_path()
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec))
        os.replace(tmp, p)

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
        return _graph_degree(g)

    def _score(self, nd: dict, maxfreq: int, deg: dict, maxdeg: int) -> float:
        return _node_score(nd, maxfreq, deg, maxdeg)

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
        view = focus_view(self._load_graph(), top=top, include_frontier=include_frontier)
        return {"session": self.session, "turn": view["turn"],
                "events": self.event_count(), "nodes": view["nodes"],
                "edges": view["edges"], "focus": view["focus"]}

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


def _graph_degree(g: dict) -> dict[str, int]:
    deg: dict[str, int] = {}
    for k in g["edges"]:
        a, b = k.split("\x00")
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    return deg


def _node_score(nd: dict, maxfreq: int, deg: dict, maxdeg: int) -> float:
    freq = (nd.get("freq", 0) / maxfreq) if maxfreq else 0.0
    cen = (deg.get(nd["name"], 0) / maxdeg) if maxdeg else 0.0
    return (W_RECENCY * nd.get("recency", 0.0) + W_FREQ * freq
            + W_CENTRALITY * cen + W_PIN * nd.get("pin", 0))


def focus_view(g: dict, *, top: int = 30, include_frontier: bool = False) -> dict:
    """The ranked view of a RAW focus graph (`{turn, nodes, edges}`) that
    `Stm.focus_graph` returns — factored out (task 21.1 R9) so a snapshot graph
    from `<session>.pre.json` is clustered by exactly the code that clusters the
    live one."""
    nodes = g.get("nodes", {})
    deg = _graph_degree(g)
    maxdeg = max(deg.values()) if deg else 1
    real = [nd for nd in nodes.values() if not nd.get("frontier")]
    maxfreq = max((nd.get("freq", 0) for nd in real), default=1) or 1
    scored = sorted(
        real, key=lambda nd: _node_score(nd, maxfreq, deg, maxdeg), reverse=True)
    keep = set(n["name"] for n in scored[:top])
    out_nodes = [{
        "name": nd["name"], "kind": nd["kind"],
        "weight": round(_node_score(nd, maxfreq, deg, maxdeg), 3),
        "recency": round(nd.get("recency", 0), 3),
        "count": nd.get("freq", 0), "degree": deg.get(nd["name"], 0),
        "pin": nd.get("pin", 0), "last": nd.get("updated"),
    } for nd in scored[:top]]
    if include_frontier:
        for nd in nodes.values():
            if nd.get("frontier") and nd["name"] in {
                    x for e in g.get("edges", {}) for x in e.split("\x00") if x in keep}:
                out_nodes.append({"name": nd["name"], "kind": nd["kind"],
                                  "weight": 0, "frontier": True})
                keep.add(nd["name"])
    edges = []
    for k, w in g.get("edges", {}).items():
        a, b = k.split("\x00")
        if a in keep and b in keep:
            edges.append({"source": a, "target": b, "weight": round(w, 2)})
    return {"turn": g.get("turn", 0), "nodes": out_nodes, "edges": edges,
            "focus": [n["name"] for n in out_nodes if not n.get("frontier")]}


# ---- R9: the pre-prompt state, race-free --------------------------------------------------

# The match window between the input hook's snapshot `wall` and a parallel
# reader's entry `t0`. Interim value: 19.0 R0 measures the real |wall - t0| over
# >= 50 prompts and commits S = max(2 s, 3 x the largest measured skew) here.
# Until then 10 s bounds what was observed while building 21.1 (a sandbox hook
# child's full import + envelope + pointer write landed 1-3 s after a sibling
# reader started, 2026-10-16). Residual, stated: a prompt textually identical to
# the previous one and submitted within S of it reads that prompt's snapshot.
PRE_PROMPT_SKEW_S = 10.0


def prompt_sha(prompt: str) -> str:
    import hashlib
    return hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()


class PrePromptState(typing.NamedTuple):
    graph: dict
    topic_cache: dict
    turn: int
    events_n: int
    source: str                         # snapshot | live
    topic_match: "dict[str, str]"


def pre_prompt_state(root: Path, session: str, prompt: str, *, t0: float) -> PrePromptState:
    """THE prompt-time reader of STM state (R9). Reads the LIVE state first (focus graph,
    ring count), THEN `<session>.pre.json`: when the snapshot names this prompt (sha256) and
    its `wall` is within `PRE_PROMPT_SKEW_S` of the reader's process-entry `t0`, the
    snapshot's values (`source=snapshot`), else the live ones (`source=live`). Exact because
    the snapshot is written before the input hook's first change to the ring or the graph."""
    s = Stm(root, session)
    live_graph = s._load_graph()
    live_n = s.events_n()
    try:
        pre = json.loads(s._pre_path().read_text())
    except (OSError, ValueError):
        pre = None
    if isinstance(pre, dict) and pre.get("prompt_sha") == prompt_sha(prompt):
        try:
            close = abs(float(pre.get("wall")) - float(t0)) <= PRE_PROMPT_SKEW_S
        except (TypeError, ValueError):
            close = False
        if close and isinstance(pre.get("graph"), dict):
            return PrePromptState(graph=pre["graph"], topic_cache=pre.get("topic_cache") or {},
                                  turn=int(pre.get("turn") or 0),
                                  events_n=int(pre.get("events_n") or 0), source="snapshot",
                                  topic_match=pre.get("topic_match") or {})
    return PrePromptState(graph=live_graph, topic_cache={}, turn=int(live_graph.get("turn", 0)),
                          events_n=live_n, source="live", topic_match={})


def phase_inputs(pre: PrePromptState, prompt: "str | None") -> dict:
    """R10's raw phase inputs from ONE pre-prompt state: the topic count of the pre-prompt
    graph (`topic_composites` over its focus view) and the prompt-term ∩ composite-member
    overlap (null for a channel with no prompt)."""
    topics = topic_composites(focus_view(pre.graph))
    members: set[str] = set()
    for t in topics:
        members.update(t.get("members") or [])
    overlap = (len(set(_extract_refs(prompt)) & members) if prompt is not None else None)
    return {"stm_events_n": pre.events_n, "focus_topics_n": len(topics),
            "overlap": overlap, "stm_source": pre.source}


def phase_fields(root: Path, session: "str | None", prompt: "str | None", *, t0: float,
                 prompt_time: bool) -> dict:
    """R10's phase fields of one event set, from ONE state read. Prompt-time channels
    (`prompt_recall`, `scan_prompt`): `pre_prompt_state` — `turn` is the 0-based ordinal of
    this prompt among the session's recorded prompts. `session_start` / `precompact` have
    no prompt: the live state (`stm_source=live`, `overlap: null`) and `turn` = the live
    graph's `turn - 1`. No session: every field null (never another session's ring)."""
    empty = {"turn": None, "stm_session": None, "stm_source": None, "stm_events_n": None,
             "focus_topics_n": None, "overlap": None}
    if not session:
        return empty
    if prompt_time:
        pre = pre_prompt_state(root, session, prompt or "", t0=t0)
        return {"turn": pre.turn, "stm_session": session, **phase_inputs(pre, prompt or "")}
    s = Stm(root, session)
    g = s._load_graph()
    live = PrePromptState(graph=g, topic_cache={}, turn=int(g.get("turn", 0)),
                          events_n=s.events_n(), source="live", topic_match={})
    return {"turn": live_turn(root, session), "stm_session": session,
            **phase_inputs(live, None)}


def live_turn(root: Path, session: "str | None") -> "int | None":
    """The `turn` of a non-prompt-time event (R9): the live graph's `turn - 1`, the ordinal
    of the prompt being answered; null with no session or no ring."""
    if not session:
        return None
    s = Stm(root, session)
    if not s._path.exists() and not s._graph_path.exists():
        return None
    return int(s._load_graph().get("turn", 0)) - 1


# ---- D9: ONE hook-envelope reader -----------------------------------------------------------

# scan-prompt's four prompt keys, the ONE tuple (round-9 #s9-4).
HOOK_PROMPT_KEYS = ("prompt", "user_prompt", "text", "message")


class HookEnvelope(typing.NamedTuple):
    envelope: "dict | None"
    prose: "str | None"

    @property
    def prompt(self) -> str:
        """`prose` when set, else the first `HOOK_PROMPT_KEYS` value that is a string, else
        ''. (Behaviour change, recorded: `_resolve_query` read `prompt` only, and
        `scan.read_stdin_prompt` returned the raw JSON for an object with none of the keys.)"""
        if self.prose is not None:
            return self.prose
        for k in HOOK_PROMPT_KEYS:
            v = (self.envelope or {}).get(k)
            if isinstance(v, str):
                return v.strip()
        return ""


def read_hook_envelope(raw: str, *, root: Path, hook: str, require_session: bool,
                       prose_ok: bool) -> HookEnvelope:
    """Parse a Claude Code hook's stdin envelope — the ONE parser (D9, round-8 #nm-4; the
    user's converge rule: `focus hook`, `_resolve_query` and `scan.read_stdin_prompt` each
    had their own, each with its own silent fallback).

    `prose_ok=True` (scan-prompt; `_resolve_query` without `--stdin-json`): input that is
    not a JSON object is PROSE — `HookEnvelope(None, raw.strip())`, nothing recorded (`fix
    the {braces` is a prompt, not an error). `prose_ok=False` (the STM hooks,
    `--stdin-json`): it prints one stderr line, records `envelope-unreadable` and returns
    `HookEnvelope(None, None)`. `require_session=True` with a falsy `session_id` prints one
    line, records `envelope-no-session` and returns `HookEnvelope(None, None)`. Rows are
    scoped to `root` and the owner `owner_lookup()` finds (D8): the generated focus entries
    end `2>/dev/null || true`, so the row, not the stderr line, is the durable channel."""
    import sys
    text = raw or ""
    try:
        d = json.loads(text) if text.strip() else None
    except ValueError:
        d = None
    if not isinstance(d, dict):
        if prose_ok:
            return HookEnvelope(None, text.strip())
        print(f"rmx {hook}: hook envelope unreadable (not a JSON object, "
              f"{len(text)} bytes)", file=sys.stderr)
        owner, _ = owner_lookup()
        record_pointer_error("envelope-unreadable", root=root, owner=owner, hook=hook,
                             bytes=len(text))
        return HookEnvelope(None, None)
    if require_session and not d.get("session_id"):
        print(f"rmx {hook}: hook envelope carries no session_id", file=sys.stderr)
        owner, _ = owner_lookup()
        record_pointer_error("envelope-no-session", root=root, owner=owner, hook=hook)
        return HookEnvelope(None, None)
    return HookEnvelope(d, None)


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
