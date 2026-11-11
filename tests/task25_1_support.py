"""Shared harness for task 25.1's RED tests (recall hook byte budget; bug-164 + bug-181).

Not a test module (no `test_` prefix). Spec:
workflow/plans/plan-25-cliquedb-field-report-tasks/task-25.1-recall-hook-byte-budget.md.

Everything here runs INSIDE task 23.0's sandbox and reuses 21.1's subprocess harness
(`tests/task21_1_support.py`: the generated hook argv run by `/bin/bash -c` with the envelope on
stdin, a real foreground `rmx daemon start --no-detach --no-watch`, the real `rmx mcp` stdio
server). What this module adds:

- the frozen fixture (`tests/fixtures/plan25/`, committed; `make_fixture.py` regenerates it)
  copied into the SANDBOX memdir of a short-root store and brought in through the real bridge
  (`rmx ingest-gmd --as-memory`), plus the parts the spec seeds through store ops: 5 subject
  rows (one stale), an STM ring, a curator spool of 30 long paths, a corpus for scan-prompt,
  and a tmp GLOBAL store (`RMX_HOME`) served by its own sandbox daemon;
- a real `ModelServer` child on a short `RMX_MODEL_SOCK` (AC-4 b/e: "the test starts the real
  `modelsrv` worker on the sandbox `models.sock`"), never a stub worker;
- readers for the `--pack` text format (task 19.1 R3: header, `- <name> — <title> — <hook>
  (<fetch>)` lines, bodies, `+N more: <cmd>` trailer) and for `hook_budget` (R1). The ACs read
  the CONSTANTS, never the R0 probe (spec #r0, lead 2026-11-11): a missing module is reported
  with the measured byte count, so the RED line names the bytes the AC is about.

Nothing in `src/` is patched by this module.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests import task21_1_support as h

REPO = h.REPO
FIX = REPO / "tests" / "fixtures" / "plan25"
PROMPTS = json.loads((FIX / "prompts.json").read_text(encoding="utf-8"))
QUESTION = PROMPTS["question"]
ACK = PROMPTS["ack"]
SYMBOL = PROMPTS["symbol"]
GLOBAL_ROWS = json.loads((FIX / "global" / "memories.json").read_text(encoding="utf-8"))

N_MEM = 30
MEM_NAMES = [f"fx_mem_{i:02d}" for i in range(N_MEM)]
SUBJECTS = [f"subject_quasar_ledger_{i}" for i in range(5)]
STALE_SUBJECT = SUBJECTS[4]
LIVE_SUBJECTS = SUBJECTS[:4]
SAVESTATE = "savestate_fx01"
GLOBAL_NAMES = [r["name"] for r in GLOBAL_ROWS]
SESSION = "sess-p25-fx"

# The lead's 2026-11-11 transcript evidence (R0 runs in parallel and is NOT read here): the
# smallest UserPromptSubmit hook output persisted as a preview was 10,093 chars, the largest
# delivered whole 9,412 chars; a preview is ~2 KB. AC-3's "what the model receives" uses the
# conservative end until R0's table lands.
CAP_DELIVERED_WHOLE = 9412
PREVIEW_BYTES = 2048

# `hooks.HOOK_ENV` is the prefix of every generated command; the "no `$`" rule (AC-13) is about
# what FOLLOWS it (HOOK_ENV itself expands $HOME and $PATH by design).
from refmatrix.hooks import HOOK_ENV  # noqa: E402

h.mark_token(SESSION, QUESTION)


# ---- hook_budget (R1) -------------------------------------------------------------------------

def hook_budget_mod():
    try:
        from refmatrix import hook_budget
    except ImportError:
        return None
    return hook_budget


def budget_or_none(channel: str):
    hb = hook_budget_mod()
    return None if hb is None else hb.budget(channel)


def assert_within(n: int, channel: str, what: str) -> int:
    """`n` bytes ≤ `hook_budget.budget(channel)`; RED names the measured bytes."""
    b = budget_or_none(channel)
    assert b is not None, (f"{what}: printed {n} B; R1 `refmatrix.hook_budget` is not built, "
                           f"so budget({channel!r}) does not exist")
    assert n <= b, f"{what}: printed {n} B > budget({channel!r}) = {b} B"
    return b


def command_budget(command: str) -> int | None:
    """R0 outcome (A): a generated hook COMMAND's budget is the sum of the channels that
    share it (`HOOK_COMMAND_CHANNELS`, R1)."""
    hb = hook_budget_mod()
    if hb is None:
        return None
    return sum(hb.budget(c) for c in hb.HOOK_COMMAND_CHANNELS[command])


# ---- the --pack format (19.1 R3) ----------------------------------------------------------------

HOOK_LINE = re.compile(r"^- (?P<name>[^\s]+) — (?P<rest>.*)\((?P<fetch>rmx memory get [^()]*)\)\s*$")
TRAILER = re.compile(r"^\+(?P<n>\d+) more: (?P<cmd>.+)$")


class Pack:
    """A parsed `--pack` payload. `is_pack` is False for anything else (HEAD's `--json`)."""

    def __init__(self, raw: bytes):
        self.raw = raw
        self.text = raw.decode("utf-8", "replace")
        self.lines = self.text.splitlines()
        self.hook_lines = [m for m in (HOOK_LINE.match(ln) for ln in self.lines) if m]
        self.named = [m.group("name") for m in self.hook_lines]
        tr = [m for m in (TRAILER.match(ln) for ln in self.lines) if m]
        self.trailer = tr[-1] if tr else None
        self.more = int(self.trailer.group("n")) if self.trailer else 0
        self.header = self.lines[0] if self.lines else ""
        self.is_pack = bool(self.lines) and not self.text.lstrip().startswith(("[", "{"))
        self.bodied = sorted({n for n in re.findall(r"BODYMARK (\S+)", self.text)})

    def fetch_of(self, name: str) -> str | None:
        for m in self.hook_lines:
            if m.group("name") == name:
                return m.group("fetch")
        return None

    def hook_line_of(self, name: str) -> str | None:
        for m in self.hook_lines:
            if m.group("name") == name:
                return m.group(0)
        return None


def names_in_payload(raw: bytes) -> list[str]:
    """The memory names a payload carries, whatever its format: a `--json` list (HEAD) or a
    pack's hook lines. Used for the HEAD-vs-after records (AC-3, AC-6)."""
    text = raw.decode("utf-8", "replace")
    try:
        rows = json.loads(text)
        if isinstance(rows, list):
            return [r.get("name") for r in rows if isinstance(r, dict)]
    except ValueError:
        pass
    return Pack(raw).named


def received(raw: bytes) -> bytes:
    """What the model is handed (AC-3): the whole payload up to the cap, else the preview."""
    return raw if len(raw.decode("utf-8", "replace")) <= CAP_DELIVERED_WHOLE else raw[:PREVIEW_BYTES]


def distinct_memories_received(raw: bytes) -> set[str]:
    """AC-3's count: distinct non-subject, non-session fixture memories named in what the model
    receives. Name-matched against the fixture (a truncated preview cannot be parsed)."""
    got = received(raw).decode("utf-8", "replace")
    pool = set(MEM_NAMES) | set(GLOBAL_NAMES) | {"fx_dup_x"}
    return {n for n in pool if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", got)}


# ---- the generated argv -------------------------------------------------------------------------

def envelope(prompt: str, *, session: str = SESSION, event: str = "UserPromptSubmit",
             source: str | None = None) -> dict:
    env = {"session_id": session, "prompt": prompt, "hook_event_name": event, "cwd": "",
           "transcript_path": ""}
    if source:
        env["source"] = source
    return env


def recall_cmd(root: Path, event: str) -> str:
    needle = {"UserPromptSubmit": "memory recall --stdin-json",
              "SessionStart": "memory recall --session-start",
              "PreCompact": "memory recall --recent"}[event]
    return h.generated_cmd(root, event, needle)


def precompact_recall_cmds(root: Path) -> list[str]:
    return [c for ev, _m, c in h.hook_entries(root, "PreCompact") if "memory recall" in c]


def scan_prompt_part(root: Path) -> str:
    """The generated scan-prompt command WITHOUT its chained `curator status` (the same command
    text up to the ` ; ` that starts the curator leg)."""
    cmd = h.generated_cmd(root, "UserPromptSubmit", "scan-prompt")
    cut = cmd.find(" ; rmx curator status")
    assert cut > 0, f"the generated scan command chains no curator status: {cmd!r}"
    return cmd[:cut]


def after_env(cmd: str) -> str:
    assert cmd.startswith(HOOK_ENV), f"generated command lacks HOOK_ENV: {cmd!r}"
    return cmd[len(HOOK_ENV):]


def run_cmd(fx: "Fixture", cmd: str, *, env_in: dict | None = None, root: Path | None = None,
            timeout: float = 180, **extra) -> subprocess.CompletedProcess:
    """One generated command, as Claude Code runs it, against the fixture store and its tmp
    global store. stdout is BYTES (the budget unit)."""
    extra.setdefault("RMX_HOME", str(fx.home))
    return h.run_hook_bytes(cmd, root=root or fx.root, envelope=env_in, timeout=timeout,
                            **extra)


def rmx(fx: "Fixture", *args, root: Path | None = None, timeout: float = 180,
        **extra) -> subprocess.CompletedProcess:
    extra.setdefault("RMX_HOME", str(fx.home))
    return h.run_rmx(list(args), root=root or fx.root, timeout=timeout, **extra)


# ---- the fixture store ----------------------------------------------------------------------------

def short_base(tag: str) -> Path:
    """A short root under the sandbox (socket paths: macOS `sun_path` ~104 B)."""
    base = Path(tempfile.mkdtemp(prefix=f"{tag}-", dir=os.environ["RMX_SANDBOX_ROOT"]))
    return base


def _init_store(root: Path, *, partition: str | None = None) -> None:
    from refmatrix.store import Store
    root.mkdir(parents=True, exist_ok=True)
    s = Store(root, partition=partition) if partition else Store(root)
    try:
        s.init()
    finally:
        s.close()


def memdir_of(proj: Path) -> Path:
    from refmatrix.handoff import default_memory_dir
    return default_memory_dir(proj)


def copy_memdir(proj: Path, *, include: "set[str] | None" = None) -> Path:
    """Copy the committed fixture memdir into the SANDBOX memdir of `proj` (`HOME` is the
    sandbox's, so `default_memory_dir` lands under it -- never a live memory dir)."""
    md = memdir_of(proj)
    assert str(md).startswith(os.environ["HOME"]), md
    if md.exists():
        shutil.rmtree(md)
    shutil.copytree(FIX / "memory", md)
    if include is not None:
        for p in md.rglob("*.md"):
            if p.name != "MEMORY.md" and p.stem not in include:
                p.unlink()
    return md


def write_corpus(proj: Path) -> Path:
    """Docs + code dense in the question's terms and in `—`, so scan-prompt's bundles exceed its
    budget at HEAD (spec #fixture: "enough indexed docs that scan-prompt exceeds 10,000 B")."""
    c = proj / "corpus"
    c.mkdir(parents=True, exist_ok=True)
    words = ("quasar", "ledger", "reconcile", "flux", "batches", "zorbulate", "shards")
    for i in range(10):
        lines = [f"# Quasar ledger design {i} — reconcile flux batches → zorbulate shards\n"]
        for n in range(40):
            w = words[(i + n) % len(words)]
            lines.append(f"The {w} step {n} — quasar ledger reconcile → flux batches across "
                         f"zorbulate shards — {w} → {w}.\n")
        (c / f"quasar_design_{i}.md").write_text("".join(lines), encoding="utf-8")
    for i in range(6):
        (c / f"zorbulate_mod_{i}.py").write_text(
            f'"""zorbulate shard module {i} — quasar ledger → reconcile flux batches."""\n\n'
            f"def {SYMBOL}_{i}(batches):\n"
            f'    """Merge zorbulate shards {i} — reconcile → quasar ledger → flux."""\n'
            f"    return [b for b in batches]  # quasar ledger — reconcile → shard {i}\n\n"
            f"def quasar_ledger_reconcile_{i}(ledger):\n"
            f'    """Reconcile the quasar ledger {i} — flux batches → zorbulate shards."""\n'
            f"    return ledger\n", encoding="utf-8")
    (c / f"{SYMBOL}.py").write_text(
        f'"""The shard merge — zorbulate → quasar ledger."""\n\n'
        f"def {SYMBOL}(a, b):\n    return a + b  # zorbulate — merge → shard\n",
        encoding="utf-8")
    return c


LONG_DIR = "docs/" + "a_deliberately_long_directory_name_for_the_curator_queue_" * 2


def curator_paths(proj: Path) -> list[str]:
    """30 paths, each > 120 chars repo-relative (AC-12, AC-12b)."""
    out = [str(proj / LONG_DIR / f"curator_relevant_change_number_{i:02d}_quasar_ledger.md")
           for i in range(30)]
    for p in out:
        assert len(str(Path(p).relative_to(proj))) > 120, p
    return out


def seed_ring(root: Path, session: str = SESSION, n: int = 48) -> None:
    """A resumed session's STM ring sized so `rmx focus context --top 15` prints > 3,000 B at
    HEAD (AC-12b). Inputs with many distinct refs, plus tool and git milestone events."""
    from refmatrix import stm
    s = stm.Stm(root, session)
    for i in range(n):
        refs = [f"quasar_ledger_component_{i % 17}", f"zorbulate_shard_module_{i % 13}",
                f"corpus/quasar_design_{i % 10}.md", f"reconcile_pass_function_{i % 11}"]
        s.record("input", f"work on quasar_ledger_component_{i % 17} and "
                          f"zorbulate_shard_module_{i % 13} — reconcile pass {i}", refs=refs)
        s.record("tool", f"Edit corpus/quasar_design_{i % 10}.md — reconcile → shard {i}",
                 refs=refs[:3])
        if i % 6 == 0:
            s.record("git", f"git commit -m 'reconcile flux batches step {i} — quasar ledger'",
                     refs=refs[:2])


class Fixture:
    """Paths of one built fixture."""

    def __init__(self, base: Path, proj: Path, home: Path):
        self.base = base
        self.proj = proj
        self.root = proj / ".refmatrix"
        self.home = home                 # RMX_HOME: the tmp GLOBAL store + registry
        self.memdir = memdir_of(proj)
        self.daemon = None
        self.gdaemon = None

    @property
    def groot(self) -> Path:
        return self.home

    def partition(self) -> str:
        from refmatrix import discovery
        return discovery.store_name(self.root)


def build_global(home: Path) -> None:
    """The tmp global store: 10 global memories + AC-11's duplicate, partition `global`."""
    from refmatrix.store import Store
    _init_store(home, partition="global")
    s = Store(home, partition="global")
    try:
        with s.with_partition("global"):
            for r in GLOBAL_ROWS:
                s.add_memory(name=r["name"], content=r["content"], mtype=r["mtype"])
    finally:
        s.close()


def build_full(tag: str = "p25") -> Fixture:
    """THE AC fixture: project store (30 memories + dup + mis-typed save-state through the
    bridge; 5 subjects through the daemon op; docs for scan-prompt; STM ring; curator spool),
    a tmp global store, both served by real sandbox daemons. Caller stops them."""
    from refmatrix import daemon as dm, gmd_curator
    base = short_base(tag)
    proj = base / "fxproj"
    home = base / "g" / ".refmatrix"
    fx = Fixture(base, proj, home)
    _init_store(fx.root)
    build_global(home)
    r = rmx(fx, "ingest", str(write_corpus(proj)), timeout=600)
    assert r.returncode == 0, r.stderr
    copy_memdir(proj)
    r = rmx(fx, "ingest-gmd", "--as-memory", str(fx.memdir), timeout=600)
    assert r.returncode == 0, (r.stdout[-2000:], r.stderr[-2000:])
    seed_ring(fx.root)
    gmd_curator.write_spool(fx.root, curator_paths(proj))
    fx.gdaemon = h.SandboxDaemon(home, RMX_HOME=str(home), RMX_NO_EMBED_WARMUP="1")
    try:
        fx.daemon = h.SandboxDaemon(fx.root, RMX_HOME=str(home))
        fx.daemon.wait_models_warm()
        part = _verbs_partition(fx)
        for i, name in enumerate(SUBJECTS):
            meta = {"subject": True}
            if name == STALE_SUBJECT:
                meta.update({"stale": True, "stale_since": "2026-11-01T00:00:00Z"})
            res = dm.call(fx.root, "memory_add", {
                "name": name, "mtype": "subject", "metadata": meta, "partition": part,
                # Subjects 0-1 carry the question verbatim, so HEAD's per-prompt top 5 holds a
                # subject (AC-6's HEAD record, measured: none did with the weaker text).
                "content": (f"{QUESTION} — {QUESTION}" if i < 2 else
                            f"Subject {i}: {QUESTION} — subject group {i} → members")},
                timeout=120)
            assert res.get("ok"), res
        res = dm.call(fx.root, "embed", {"kinds": ["memory", "doc"], "partition": part},
                      timeout=900)
        assert res.get("ok"), res
        res = dm.call(fx.root, "snapshot", {"force": True}, timeout=300)
        assert res.get("ok"), res
    except BaseException:
        stop(fx)
        raise
    return fx


def _verbs_partition(fx: Fixture) -> str:
    """`verbs.memory_partition(root)` as the test process sees the fixture (R5's partition)."""
    from refmatrix import verbs
    return verbs.memory_partition(fx.root, timeout=30)


def stop(fx: Fixture) -> None:
    for d in (fx.daemon, fx.gdaemon):
        if d is not None:
            d.stop()


def build_offline(tag: str, name: str, names: "set[str]", *, home: Path) -> Fixture:
    """A store whose memories (a subset of the fixture, by name) are embedded and SNAPSHOTTED by
    a sandbox daemon that is then STOPPED: the replica + Lance vectors stay, no daemon answers
    (AC-4 b/c/e/g)."""
    from refmatrix import daemon as dm
    base = short_base(tag)
    proj = base / name
    fx = Fixture(base, proj, home)
    _init_store(fx.root)
    copy_memdir(proj, include=names)
    r = rmx(fx, "ingest-gmd", "--as-memory", str(fx.memdir), timeout=600)
    assert r.returncode == 0, (r.stdout[-2000:], r.stderr[-2000:])
    d = h.SandboxDaemon(fx.root, RMX_HOME=str(home))
    try:
        d.wait_models_warm()
        part = _verbs_partition(fx)
        res = dm.call(fx.root, "embed", {"kinds": ["memory"], "partition": part}, timeout=900)
        assert res.get("ok"), res
        res = dm.call(fx.root, "snapshot", {"force": True}, timeout=300)
        assert res.get("ok"), res
    finally:
        d.stop()
    assert not dm.ping(fx.root, timeout=0.5, retries=0)
    return fx


# ---- a REAL shared model worker -----------------------------------------------------------------

_MODELSRV = r"""
import sys, time
from refmatrix.modelsrv import ModelServer, SharedWorkerClient
from refmatrix.recall import remote_embedder
srv = ModelServer()
assert srv.start() is True, "ModelServer.start() refused"
c = SharedWorkerClient("embed")
e = remote_embedder(c)
e.embed_texts(["warm"])
c.close()
print("READY", flush=True)
while True:
    time.sleep(1)
"""


class SharedWorker:
    """`modelsrv.ModelServer` in its own process on a short `RMX_MODEL_SOCK`, its embed worker
    warmed (one real embed) before the test runs. The model is the real local one
    (`HF_HUB_OFFLINE=1`, the sandbox keeps the real cache)."""

    def __init__(self, base: Path, *, home: Path):
        self.sock = base / "m.sock"
        self.env = h.clean_env(HOME=os.environ["HOME"], RMX_HOME=str(home),
                               RMX_MODEL_SOCK=str(self.sock))
        self.log = open(base / "modelsrv.log", "w")
        self.proc = subprocess.Popen([sys.executable, "-c", _MODELSRV], env=self.env,
                                     stdout=subprocess.PIPE, stderr=self.log, text=True)
        deadline = time.monotonic() + 240
        line = ""
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline()
            if line.startswith("READY") or self.proc.poll() is not None:
                break
        if not line.startswith("READY"):
            self.stop()
            raise RuntimeError(f"model server never warmed: {(base / 'modelsrv.log').read_text()[-2000:]}")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=30)
        self.log.close()
        try:
            self.sock.unlink()
        except FileNotFoundError:
            pass


# ---- query.log rows ------------------------------------------------------------------------------

def recall_rows(root: Path) -> list[dict]:
    return [r for r in h.query_rows(root) if r.get("kind") == "recall"]


# ---- an MCP stdio child with a chosen env (REFMATRIX_ROOT may be UNSET) ------------------------

class McpChild(h.McpServer):
    """21.1's `McpServer`, but the env is the caller's: AC-4 (e) needs `REFMATRIX_ROOT` unset
    and the cwd inside store A, which `rmx_env` (it always sets REFMATRIX_ROOT) cannot give."""

    def __init__(self, *, cwd: Path, **env_extra):
        self.root = None
        self.env = h.clean_env(HOME=os.environ["HOME"], **env_extra)
        self.proc = subprocess.Popen(
            [h.rmx_bin(), "mcp"], env=self.env, cwd=str(cwd),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        self._id = 0
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "task25.1-test", "version": "0"}})
