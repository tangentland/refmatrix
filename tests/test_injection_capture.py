"""Task 31.5 S0 RED: the per-prompt injection capture (release A), and bug-256.

Spec: `workflow/plans/plan-31-pre-mod-loose-ends-tasks/task-31.5-scan-prompt-block-measure.md`,
`#s0` (R0.1-R0.7, AC-0.1 to AC-0.18), approved by ruling L140 at `606c0c8`.

Why: every prompt pays for `rmx scan-prompt` (up to 9,000 B) and the per-prompt recall pack, and
nothing measured so far can support a cut. The 2026-11-13 pilot saw only what reached the model;
what rmx rendered and then dropped (byte fit, token stop, unchanged composite, cadence) was never
logged, and nothing was split by block. S0 records, per call, every block with its kind and its
state, after the payload is printed, without changing the payload or any other log. bug-256: a
composite build that raises was indistinguishable from an absent composite.

How these tests run (spec `#s0-acceptance` preamble): each one runs the REAL `rmx scan-prompt` or
`rmx memory recall --pack` command, as a child process importing this checkout's `src/`, against
a throwaway store under a short `mkdtemp()` root (`/tmp/cap.XXXXXXXX`, every root the same
length so the rendered absolute paths, and with them the token costs, are the same in every
store). No daemon unless a test says so; the CLI reads the store in-process. "Capture off" is
`RMX_INJECTION_CAPTURE=0`, never `REFMATRIX_NO_TELEMETRY`, unless a test says so. Nothing in
`src/` is patched; no mock is used. The prompts are synthetic (no real prompt text,
`feedback_no_raw_prompts_in_public_repo`).

Contracts the spec leaves open, pinned here and listed in `workflow/review-output/31.5/
red-report.md`:
- the record file is `<store root>/injection-capture/capture-<UTC yyyymmdd>.jsonl` (R0.4);
- "the printed payload" is the command's stdout; the delivered and marker block texts, joined in
  order, equal it, allowing only the one newline `click.echo` appends after the text;
- `budget_bytes` is the channel's budget (`hook_budget.budget("scan_prompt")`), not cap - 1;
- the `capture:` line of `rmx telemetry --context` is ONE line starting `capture:`; its counts
  read as `N captured of M hook call(s)`, `<reason>=N` (or `<reason>: N`, `<reason> N`,
  `N <reason>`) for `errors.jsonl` reasons and `composite_error(s)`, and the words
  `invalid mode` for an unrecognised mode word;
- a "hook call" is a `query.log` row with `invocation` `hook`; control runs that must not count
  use `RMX_INVOCATION_SOURCE=internal`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from tests import task21_1_support as h

CAP_DIR = "injection-capture"
SESSION = "sess-cap315"
CANARY = "zqxcanary315"
COMP_MARK = "# STM topic composite"
NAMED = ["widget_registry", "ledger_codec"]
PLAIN = ["harbor", "lantern", "closet", "meadow"]
# Two identifiers and three plain words (AC-0.1).
PROMPT = "why does widget_registry call ledger_codec near the harbor lantern closet"
GROUNDED = ["parser.py", "lexer_table", "token_stream"]
MiB = 1024 * 1024

# R0.2: the record's keys, exactly (AC-0.8).
SCHEMA_KEYS = {
    "v", "ts", "rmx_version", "channel", "invocation", "session", "query_id",
    "prompt_sha256", "prompt_chars",
    "budget_bytes", "max_tokens", "payload_sha256", "payload_bytes",
    "capture_mode", "capture_ms", "capture_built", "pruned", "composite_error",
    # bug-268 (L152): the STM focus graph read raised or was wrong-shaped (class and
    # message), else null. Not in R0.2's list; named by this RED, see the report.
    "stm_error",
    "blocks",
}
BLOCK_KEYS = {"i", "kind", "state", "bytes", "sha256", "names", "dedup_rows"}
RECALL_HIT_KEYS = {"kind", "state", "name", "rank", "mtype", "scope", "hook_bytes",
                   "body_bytes", "body_sha256"}
KINDS = {"symbol_named", "content", "symbol_other", "composite", "recall_hit", "marker"}
STATES = {"delivered", "dropped_bytes", "dropped_tokens", "not_built", "suppressed_unchanged",
          "suppressed_cadence", "delivered_hook_only"}
RENDER_RANK = {"symbol_named": 0, "content": 1, "symbol_other": 2, "composite": 3}
EVENT_TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

h.mark_token(SESSION, CANARY, PROMPT)        # the live-log guard attributes these to the test


# ---- the fixture store ------------------------------------------------------------------------


def _doc(i: int, body: str) -> str:
    return (f'---\ngmd: "0.1"\nid: doc-{i}\ntitle: "D{i}"\ntags: [t]\n'
            f'metadata: {{node_type: memory, type: test/doc}}\n---\n\n# D{i} {{#root}}\n\n'
            f'{body}\n')


def _bodies() -> "list[str]":
    """Two identifiers (each in two docs) and four plain words, each with four docs of its
    own, so the content bundle (10 entities) cannot show every plain-word row and each tier-3
    bundle keeps rows of its own after the cross-section dedup."""
    out = ["The widget_registry keeps every widget; see widget_registry for the table.",
           "widget_registry is rebuilt nightly by the scheduler.",
           "ledger_codec encodes the ledger rows; ledger_codec owns the format.",
           "The ledger_codec decoder is strict about ledger rows."]
    for w in PLAIN:
        for j in range(4):
            out.append(f"{w.capitalize()} story {j}: the {w} keeps its own {w} notes, "
                       f"{w} entry {j}.")
    return out


def _new_base() -> Path:
    return Path(tempfile.mkdtemp(prefix="cap.", dir="/tmp")).resolve()


def _build(*, ring: bool = True, docs: bool = True, memories: int = 0) -> dict:
    """A throwaway project + store. `ring`: an STM ring for SESSION whose topic is grounded,
    so the composite is emitted. `memories`: that many recall fixture memories."""
    from refmatrix import stm as stm_mod
    from refmatrix.ingest_gmd import ingest_gmd_paths
    from refmatrix.store import Store

    base = _new_base()
    proj = base / "proj"
    proj.mkdir(parents=True)
    root = proj / ".refmatrix"
    s = Store(root, backend="duckdb")
    s.init()
    try:
        if docs:
            d = proj / "docs"
            d.mkdir()
            for i, b in enumerate(_bodies()):
                (d / f"doc-{i}.md").write_text(_doc(i, b), encoding="utf-8")
            ingest_gmd_paths(s, sorted(d.glob("*.md")), as_memory=True,
                             memory_mtype_default="test/doc")
            for name, idx in (("widget_registry", (0, 1)), ("ledger_codec", (2, 3))):
                cid = s.add_concept(name)
                for i in idx:
                    ent = s.get_entity("memory", f"doc-{i}")
                    assert ent is not None, f"fixture: no memory row doc-{i}"
                    s.link("mentions", cid, ent.id)
        for i in range(memories):
            s.add_memory(name=f"capmem_{i:02d}", content=f"Rule {i:02d}.\nBODYQ{i:02d}",
                         mtype="feedback", metadata={"title": f"capture fixture title {i:02d}"})
        s.flush_fragments()
    finally:
        s.close()
    if ring:
        r = stm_mod.Stm(root, SESSION)
        r.record("input", " ".join(GROUNDED), refs=GROUNDED)
        r.record("tool", "again " + " ".join(GROUNDED), refs=GROUNDED)
    return {"base": base, "proj": proj, "root": root}


def _teardown(c: dict) -> None:
    for p in sorted(c["base"].rglob("*"), reverse=True):
        try:
            if not p.is_symlink():
                os.chmod(p, 0o755 if p.is_dir() else 0o644)
        except OSError:
            pass
    shutil.rmtree(c["base"], ignore_errors=True)


@pytest.fixture
def store():
    c = _build()
    try:
        yield c
    finally:
        _teardown(c)


@pytest.fixture(autouse=True)
def _live_logs_untouched():
    snap = h.live_snapshot()
    yield
    h.assert_live_logs_unchanged(snap)


# ---- calibration (once per module; in-process, on its own store of the same path length) -----

_BUNDLE = re.compile(r"^=== context for `([^`]+)` ===$", re.M)
_SYM_HDR = re.compile(r"^# refmatrix context for prompt-mentioned symbols: (.*)$", re.M)
CONTENT_HDR = "# refmatrix content matches for prompt"
TOKEN_MARK = "# [truncated by --max-tokens]"


def _symbol_bundles(out: str) -> "list[str]":
    """Bundle anchors in render order; the content bundle (its ref is the prompt) excluded."""
    return [b for b in _BUNDLE.findall(out) if " " not in b]


def _tier3_names(out: str) -> "list[str]":
    """The names in the tier-3 header (the symbols header after the content matches)."""
    c = out.find(CONTENT_HDR)
    for m in _SYM_HDR.finditer(out):
        if c != -1 and m.start() > c:
            return [t.strip() for t in m.group(1).split(",")]
    return []


def _timed(time_mod, fn) -> float:
    t = time_mod.perf_counter()
    fn()
    return (time_mod.perf_counter() - t) * 1000.0


@pytest.fixture(scope="module")
def calib():
    """`t1`: a --max-tokens at which tier 1 trips at its SECOND bundle (widget_registry
    rendered, ledger_codec the tripping bundle, the content block never rendered).
    `t3`: one at which tier 1 and the content render and the FIRST tier-3 bundle trips.
    `tier3`: the tier-3 bundles an uncapped render shows (at least two)."""
    from refmatrix.scan import scan_prompt
    from refmatrix.store import Store

    c = _build(ring=False)
    s = Store(c["root"], backend="duckdb")
    try:
        def out_at(m: int) -> str:
            return scan_prompt(s, PROMPT, composite=False, max_tokens=m)

        full = out_at(100_000)
        assert TOKEN_MARK not in full, f"fixture: the uncapped render tripped the stop:\n{full}"
        bundles = _symbol_bundles(full)
        assert bundles[:2] == NAMED, f"fixture: tier 1 is not {NAMED}: {bundles}"
        tier3 = [b for b in bundles[2:]]
        assert len(tier3) >= 2, f"fixture: fewer than two tier-3 bundles: {bundles}\n{full}"

        def first_m(pred) -> int:
            lo, hi = 1, 100_000
            assert pred(out_at(hi)), "fixture: predicate false even uncapped"
            while lo < hi:
                mid = (lo + hi) // 2
                if pred(out_at(mid)):
                    hi = mid
                else:
                    lo = mid + 1
            return lo

        t1 = first_m(lambda o: "widget_registry" in _symbol_bundles(o))
        t3 = first_m(lambda o: "ledger_codec" in _symbol_bundles(o))
        o1, o3 = out_at(t1), out_at(t3)
        assert _symbol_bundles(o1) == ["widget_registry"] and TOKEN_MARK in o1 \
            and CONTENT_HDR not in o1, f"fixture: t1={t1} is not a tier-1 trip:\n{o1}"
        assert _symbol_bundles(o3) == NAMED and CONTENT_HDR in o3 and TOKEN_MARK in o3, (
            f"fixture: t3={t3} is not a tier-3 trip:\n{o3}")
        # M1 (L178): the fastest of three in-process builds of each tier-3 bundle, with the
        # hook's per-bundle arguments. A cold CLI child builds no faster, so it is a floor.
        import time as _time
        from refmatrix.context import build_context
        build_ms_min = min(
            min(_timed(_time, lambda n=n: build_context(s, n, max_tokens=600, max_entities=10,
                                                        degree=0)) for _ in range(3))
            for n in tier3)
        return {"t1": t1, "t3": t3, "tier3": tier3, "full": full, "build_ms_min": build_ms_min}
    finally:
        s.close()
        _teardown(c)


# ---- the command ------------------------------------------------------------------------------


def _rmx(c: dict, *args, input: str = "", **env) -> subprocess.CompletedProcess:
    env.setdefault("RMX_INVOCATION_SOURCE", "hook")
    env.setdefault("COLUMNS", "400")
    return h.run_rmx(list(args), root=c["root"], cwd=c["proj"], input=input, timeout=300, **env)


def _scan(c: dict, *extra, prompt: str = PROMPT, **env) -> subprocess.CompletedProcess:
    r = _rmx(c, "scan-prompt", "--text", prompt, "--composite-every", "1", *extra, **env)
    assert r.returncode == 0, f"scan-prompt exited {r.returncode}: {r.stderr[-1500:]}"
    return r


def _scan_bytes(c: dict, *extra, **env) -> subprocess.CompletedProcess:
    """`_scan` with stdout kept as bytes (the payload's unit)."""
    env.setdefault("RMX_INVOCATION_SOURCE", "hook")
    e = h.rmx_env(c["root"], **env)
    return subprocess.run([h.rmx_bin(), "scan-prompt", "--text", PROMPT, "--composite-every",
                           "1", *extra], input=b"", env=e, cwd=str(c["proj"]),
                          capture_output=True, timeout=300)


def _reset_composite_marker(c: dict) -> None:
    for m in (c["root"] / "stm").glob("*.composite.last"):
        m.unlink()


# ---- readers ----------------------------------------------------------------------------------


def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")


def _day(offset_days: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=offset_days)).strftime("%Y%m%d")


def _listing(root: Path) -> str:
    d = root / CAP_DIR
    if not d.is_dir():
        return f"{d} does not exist"
    return f"{d}: {sorted(p.name for p in d.iterdir())}"


def _records(root: Path) -> "list[dict]":
    d = root / CAP_DIR
    out: list[dict] = []
    if not d.is_dir():
        return out
    for f in sorted(d.glob("capture-*.jsonl")):
        if f.is_symlink() or f.stat().st_size > 4 * MiB:
            continue                     # a test's sparse filler or dangling link, not records
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                out.append(json.loads(ln))
    return out


def _query_rows(root: Path) -> "list[dict]":
    p = root / "query.log"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _last_qid(root: Path, kind: str = "scan") -> str:
    rows = [r for r in _query_rows(root) if r.get("kind") == kind]
    assert rows, f"fixture: no query.log row of kind {kind!r}"
    return rows[-1]["query_id"]


def _events(root: Path, qid: str) -> "list[dict]":
    p = root / "recall-events.jsonl"
    if not p.exists():
        return []
    evs = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [e for e in evs if e.get("query_id") == qid]


def _record_for(root: Path, qid: str) -> dict:
    recs = [r for r in _records(root) if r.get("query_id") == qid]
    assert recs, (f"no capture record for query_id {qid} (R0.2: one record per call, written "
                  f"after the payload is printed); {_listing(root)}")
    assert len(recs) == 1, f"{len(recs)} capture records for one call {qid}"
    return recs[0]


def _errors(root: Path) -> "list[dict]":
    p = root / CAP_DIR / "errors.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _sha(b: "bytes | str") -> str:
    return hashlib.sha256(b.encode("utf-8") if isinstance(b, str) else b).hexdigest()


def _joined_delivered(rec: dict) -> str:
    return "".join(b.get("text") or "" for b in rec["blocks"]
                   if b.get("state") == "delivered"
                   or (b.get("kind") == "marker" and b.get("state") in (None, "delivered")))


def _assert_is_payload(joined: str, stdout: str, what: str) -> None:
    assert joined in (stdout, stdout[:-1] if stdout.endswith("\n") else stdout), (
        f"{what}: the delivered and marker block texts joined in order are not the printed "
        f"payload ({len(joined)} vs {len(stdout)} chars)\n--- joined ---\n{joined[-800:]}\n"
        f"--- stdout ---\n{stdout[-800:]}")


def _blocks(rec: dict, *, kind: "str | None" = None, state: "str | None" = None) -> list:
    return [b for b in rec["blocks"] if (kind is None or b.get("kind") == kind)
            and (state is None or b.get("state") == state)]


def _anchors(block: dict) -> "list[str]":
    return _symbol_bundles(block.get("text") or "")


def _capture_line(c: dict) -> str:
    r = _rmx(c, "telemetry", "--context", RMX_INVOCATION_SOURCE="internal")
    assert r.returncode == 0, f"telemetry --context exited {r.returncode}: {r.stderr[-800:]}"
    lines = r.stdout.splitlines()
    idx = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("capture:")]
    assert len(idx) == 1, (f"R0.6: `rmx telemetry --context` prints {len(idx)} `capture:` "
                           f"line(s), not one:\n{r.stdout[-2000:]}")
    i = idx[0]
    out = [lines[i]]
    for ln in lines[i + 1:]:
        if ln.startswith((" ", "\t")) and ln.strip():
            out.append(ln.strip())       # a wrapped continuation
        else:
            break
    return " ".join(out)


def _count(line: str, key: str) -> "int | None":
    for pat in (rf"\b{key}\s*[=:]\s*(\d+)\b", rf"\b{key}\s+(\d+)\b", rf"\b(\d+)\s+{key}\b"):
        m = re.search(pat, line)
        if m:
            return int(m.group(1))
    return None


def _coverage(line: str) -> "tuple[int, int] | None":
    m = re.search(r"\b(\d+)\s+captured\s+of\s+(\d+)\s+hook\s+calls?\b", line)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _sparse(p: Path, size: int, *, days_old: int) -> None:
    with open(p, "wb") as f:
        f.truncate(size)
    t = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_old)).timestamp()
    os.utime(p, (t, t))


def _capture_dir_with_ignore(root: Path) -> Path:
    d = root / CAP_DIR
    d.mkdir()
    (d / ".gitignore").write_text("*\n", encoding="utf-8")
    return d


# ---- AC-0.1 -----------------------------------------------------------------------------------


def test_a_scan_call_writes_one_record_with_every_block(store):
    """AC-0.1 (RED at base): one record per call; every block labelled with its kind and state,
    in render order (tier 1, content, tier 3, composite), `capture_ms` and `capture_built`
    set; the record joins `query.log` by `query_id`."""
    from refmatrix import __version__, hook_budget
    r = _scan(store, "--max-tokens", "100000")
    assert COMP_MARK in r.stdout and "omitted by --max-bytes" not in r.stdout, (
        f"fixture: the call must deliver every section and the composite:\n{r.stdout[-600:]}")
    qid = _last_qid(store["root"])
    recs = _records(store["root"])
    assert len(recs) == 1, (f"R0.2: one capture record per call, found {len(recs)}; "
                            f"{_listing(store['root'])}")
    rec = recs[0]
    assert rec["query_id"] == qid, (rec["query_id"], qid)
    assert rec["v"] == 1 and EVENT_TS.match(rec["ts"]), (rec["v"], rec["ts"])
    assert rec["rmx_version"] == __version__, rec["rmx_version"]
    assert (rec["channel"], rec["invocation"]) == ("scan_prompt", "hook")
    assert rec["budget_bytes"] == hook_budget.budget("scan_prompt"), rec["budget_bytes"]
    assert rec["max_tokens"] == 100000, rec["max_tokens"]
    out_b = r.stdout.encode("utf-8")
    assert rec["payload_bytes"] == len(out_b) and rec["payload_sha256"] == _sha(out_b)
    assert rec["capture_mode"] in ("full", "names"), rec["capture_mode"]
    assert isinstance(rec["capture_ms"], (int, float)) and rec["capture_ms"] >= 0
    assert isinstance(rec["capture_built"], int) and rec["capture_built"] >= 0
    assert rec["pruned"] == [] and rec["composite_error"] is None and rec["stm_error"] is None
    blocks = rec["blocks"]
    assert [b["i"] for b in blocks] == sorted(b["i"] for b in blocks) and \
        len({b["i"] for b in blocks}) == len(blocks), [b.get("i") for b in blocks]
    for b in blocks:
        assert BLOCK_KEYS <= set(b), f"block lacks {BLOCK_KEYS - set(b)}: {b}"
        assert b["kind"] in KINDS and b["state"] in STATES, (b["kind"], b["state"])
        if b.get("text") is not None:
            assert b["bytes"] == len(b["text"].encode("utf-8")), b
            assert b["sha256"] == _sha(b["text"]), b
    kinds = [b["kind"] for b in blocks if b["kind"] in RENDER_RANK]
    assert [RENDER_RANK[k] for k in kinds] == sorted(RENDER_RANK[k] for k in kinds), (
        f"blocks are not in render order: {kinds}")
    named = _blocks(rec, kind="symbol_named")
    assert [a for b in named for a in _anchors(b)] == NAMED, [_anchors(b) for b in named]
    assert len(_blocks(rec, kind="content")) == 1, kinds
    assert _blocks(rec, kind="symbol_other"), kinds
    assert [b["state"] for b in _blocks(rec, kind="composite")] == ["delivered"], kinds


# ---- AC-0.2 -----------------------------------------------------------------------------------


@pytest.mark.parametrize("cap", [None, 1500], ids=["uncapped", "byte-capped"])
def test_delivered_blocks_concatenate_to_the_payload(store, cap):
    """AC-0.2 (RED): the delivered and marker texts, joined in order, are the printed payload;
    `payload_sha256` is the `block_sha` of the call's recall events."""
    extra = ["--max-tokens", "100000"] + ([] if cap is None else ["--max-bytes", str(cap)])
    r = _scan(store, *extra)
    if cap is not None:
        assert "omitted by --max-bytes" in r.stdout, f"fixture: nothing dropped:\n{r.stdout}"
    qid = _last_qid(store["root"])
    evs = _events(store["root"], qid)
    shas = {e["block_sha"] for e in evs}
    assert len(shas) == 1, f"fixture: the call's events carry {shas}"
    rec = _record_for(store["root"], qid)
    _assert_is_payload(_joined_delivered(rec), r.stdout, f"cap={cap}")
    assert rec["payload_sha256"] == shas.pop() == _sha(r.stdout), rec["payload_sha256"]


# ---- AC-0.3 -----------------------------------------------------------------------------------


def test_a_block_the_byte_fit_dropped_is_stored_as_dropped_bytes(store):
    """AC-0.3 (RED): every block the `--max-bytes` fit dropped is stored, with its text, as
    `dropped_bytes`; as many as the omission trailer counts."""
    r = _scan(store, "--max-tokens", "100000", "--max-bytes", "1500")
    m = re.search(r"# \[\+(\d+) block\(s\) omitted by --max-bytes", r.stdout)
    assert m, f"fixture: the fit dropped nothing:\n{r.stdout}"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    dropped = _blocks(rec, state="dropped_bytes")
    assert len(dropped) == int(m.group(1)), (
        f"the trailer says {m.group(1)} block(s) omitted; the record holds {len(dropped)} "
        f"dropped_bytes: {[(b['kind'], b['state']) for b in rec['blocks']]}")
    for b in dropped:
        assert b.get("text"), f"a dropped_bytes block without its text: {b}"
        assert b["text"].strip() not in r.stdout, f"a dropped block's text is in the payload: {b}"
        assert b["sha256"] == _sha(b["text"]) and b["bytes"] == len(b["text"].encode())
    assert {b["kind"] for b in dropped} >= {"composite"}, [b["kind"] for b in dropped]


def test_bundles_past_the_token_stop_are_built_and_stored_as_dropped_tokens(store, calib):
    """AC-0.3 (RED), mode `full`: the bundle that tripped the `--max-tokens` stop and every
    tier-3 bundle the stop prevented from being built are stored, with text, as
    `dropped_tokens`; the ones built only for the capture are counted in `capture_built`."""
    r = _scan(store, "--max-tokens", str(calib["t3"]), RMX_INJECTION_CAPTURE="full")
    assert TOKEN_MARK in r.stdout and CONTENT_HDR in r.stdout, f"fixture:\n{r.stdout}"
    assert _symbol_bundles(r.stdout) == NAMED, f"fixture: a tier-3 bundle was delivered"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    assert rec["capture_mode"] == "full", rec["capture_mode"]
    cut = _blocks(rec, kind="symbol_other", state="dropped_tokens")
    assert len(cut) >= 2, (f"tier-3 bundles past the stop: {len(cut)} stored as dropped_tokens; "
                           f"states {[(b['kind'], b['state']) for b in rec['blocks']]}")
    for b in cut:
        assert b.get("text") and _anchors(b), f"a dropped_tokens bundle without its text: {b}"
    seen = {a for b in cut for a in _anchors(b)}
    missing = [n for n in calib["tier3"] if n not in seen]
    assert not missing, f"tier-3 bundles the stop prevented, not stored: {missing} (have {seen})"
    assert rec["capture_built"] >= len(cut) - 1, (rec["capture_built"], len(cut))
    # M1 (L178, X-1): `capture_ms` is the wall time the capture added, the extra builds
    # included (R0.2); AC-0.17 reads it. A quarter of the fastest in-process build per built
    # bundle is a floor no honest record falls under (X-1's record read 0.5 ms).
    floor = 0.25 * rec["capture_built"] * calib["build_ms_min"]
    assert rec["capture_built"] >= 1 and rec["capture_ms"] >= floor, (
        f"capture_ms {rec['capture_ms']} does not cover {rec['capture_built']} built bundle(s) "
        f"(floor {floor:.1f} ms at {calib['build_ms_min']:.1f} ms per in-process build)")
    assert not _blocks(rec, state="not_built"), "mode full recorded a not_built block"
    assert [b["kind"] for b in _blocks(rec, kind="marker")], "the token-stop marker is unrecorded"


@pytest.mark.parametrize("mode", ["full", "names"])
def test_content_after_a_tier_1_token_stop_is_stored_with_text(store, calib, mode):
    """AC-0.3 (RED), R0.1 `#r0-1-content`: when tier 1 trips the stop, `scan_prompt` returns
    before rendering the (already built) content bundle; the capture renders it and stores it
    as `dropped_tokens` with its text, in mode `full` and mode `names` alike; the tripping
    tier-1 bundle is stored too."""
    r = _scan(store, "--max-tokens", str(calib["t1"]), RMX_INJECTION_CAPTURE=mode)
    assert TOKEN_MARK in r.stdout and CONTENT_HDR not in r.stdout, f"fixture:\n{r.stdout}"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    content = _blocks(rec, kind="content")
    assert [b["state"] for b in content] == ["dropped_tokens"], (
        f"mode {mode}: the content block after a tier-1 stop: "
        f"{[(b['kind'], b['state']) for b in rec['blocks']]}")
    assert CONTENT_HDR in (content[0].get("text") or ""), content[0]
    trip = _blocks(rec, kind="symbol_named", state="dropped_tokens")
    assert trip and _anchors(trip[0]) == ["ledger_codec"], (
        f"the tripping tier-1 bundle: {[(b['kind'], b['state'], _anchors(b)) for b in trip]}")


def test_names_mode_records_later_bundles_as_not_built(store, calib):
    """AC-0.3 (RED), R0.4 `#r0-4-mode`: mode `names` builds nothing extra: the bundle that
    tripped the stop (already built) and the content block are stored with text; later symbol
    bundles are `not_built`, with their names and no text; `capture_built` is 0."""
    r = _scan(store, "--max-tokens", str(calib["t3"]), RMX_INJECTION_CAPTURE="names")
    assert TOKEN_MARK in r.stdout and _symbol_bundles(r.stdout) == NAMED, f"fixture:\n{r.stdout}"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    assert rec["capture_mode"] == "names", rec["capture_mode"]
    assert rec["capture_built"] == 0, rec["capture_built"]
    assert all(b.get("text") for b in _blocks(rec, kind="content")) and \
        _blocks(rec, kind="content"), "the content block is not stored with its text"
    tripped = _blocks(rec, kind="symbol_other", state="dropped_tokens")
    assert len(tripped) == 1 and _anchors(tripped[0]), (
        f"mode names: the tripping bundle: {[(b['kind'], b['state']) for b in rec['blocks']]}")
    later = _blocks(rec, state="not_built")
    assert later, f"no not_built block: {[(b['kind'], b['state']) for b in rec['blocks']]}"
    tier3 = {n.lower() for n in _tier3_names(calib["full"])} | {n.lower() for n in calib["tier3"]}
    for b in later:
        assert not b.get("text"), f"a not_built block carries text: {b}"
        assert b.get("names") and {n.lower() for n in b["names"]} <= tier3, b


def test_an_unchanged_composite_is_recorded_as_suppressed_unchanged(store):
    """AC-0.3 (RED): the second call's composite, not rendered because its member-set
    signature equals the last delivered one, is a `suppressed_unchanged` block, no text."""
    first = _scan(store, "--max-tokens", "100000")
    assert COMP_MARK in first.stdout, "fixture: no composite on the first call"
    second = _scan(store, "--max-tokens", "100000")
    assert COMP_MARK not in second.stdout, "fixture: an unchanged composite was re-sent"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    comp = _blocks(rec, kind="composite")
    assert [b["state"] for b in comp] == ["suppressed_unchanged"], (
        [(b["kind"], b["state"]) for b in rec["blocks"]])
    assert not comp[0].get("text"), comp[0]


def test_a_composite_whose_printed_members_did_not_change_is_suppressed(store):
    """bug-277 (L178 S2; RED): the unchanged-composite signature is taken over the members
    the composite PRINTS (R2.0), not over every focus member. After the composite is delivered,
    `the` (stoplist) and `buigger` (names no concept) join the topic; the printed `Members:`
    line is the same, so the next call records `suppressed_unchanged` and prints no composite
    (bsd-315 r1 P2: it was re-sent, recorded `delivered`)."""
    from refmatrix import stm as stm_mod
    first = _scan(store, "--max-tokens", "100000")
    assert COMP_MARK in first.stdout, "fixture: no composite on the first call"
    stm_mod.Stm(store["root"], SESSION).record(
        "input", "the parser.py and the lexer_table buigger", refs=GROUNDED + ["the", "buigger"])
    topics = stm_mod.topic_composites(stm_mod.Stm(store["root"], SESSION).focus_graph(top=40))
    joined = {m for t in topics for m in t["members"]}
    assert {"the", "buigger"} & joined, f"fixture: the new words joined no topic: {topics}"
    second = _scan(store, "--max-tokens", "100000")
    rec = _record_for(store["root"], _last_qid(store["root"]))
    comp = _blocks(rec, kind="composite")
    assert [b["state"] for b in comp] == ["suppressed_unchanged"], (
        f"bug-277: a composite whose printed members did not change: "
        f"{[(b['kind'], b['state']) for b in rec['blocks']]}")
    assert COMP_MARK not in second.stdout, "the unchanged composite was re-sent"


def test_a_cadence_skip_is_recorded_as_suppressed_cadence(store):
    """AC-0.3 (RED): a composite skipped by `--composite-every` is `suppressed_cadence`, no
    text; the next call at every 1 delivers it (the composite exists)."""
    from refmatrix import stm as stm_mod
    turn = int(stm_mod.Stm(store["root"], SESSION).focus_graph().get("turn", 0))
    assert turn > 0, f"fixture: ring turn {turn}"
    every = str(turn + 1)                       # turn % (turn + 1) != 0: a skipped turn
    r = _rmx(store, "scan-prompt", "--text", PROMPT, "--max-tokens", "100000",
             "--composite-every", every)
    assert r.returncode == 0 and COMP_MARK not in r.stdout, f"fixture:\n{r.stdout[-400:]}"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    after = _scan(store, "--max-tokens", "100000")
    assert COMP_MARK in after.stdout, "fixture: no composite at --composite-every 1"
    comp = _blocks(rec, kind="composite")
    assert [b["state"] for b in comp] == ["suppressed_cadence"], (
        [(b["kind"], b["state"]) for b in rec["blocks"]])
    assert not comp[0].get("text"), comp[0]


# ---- AC-0.4 / AC-0.5 (guards) -----------------------------------------------------------------


@pytest.mark.parametrize("cut", ["token-stop", "byte-fit"])
def test_the_capture_never_changes_the_payload(store, calib, cut):
    """AC-0.4 (guard, green at base; M0-1): the same store and prompt give byte-identical
    stdout and exit status with the capture off and on (mode full), for a prompt that trips
    the token stop and one that trips the byte fit. The composite's sent marker is reset
    between the arms so both start from the same state."""
    extra = (["--max-tokens", str(calib["t3"])] if cut == "token-stop"
             else ["--max-tokens", "100000", "--max-bytes", "1500"])
    off = _scan_bytes(store, *extra, RMX_INJECTION_CAPTURE="0")
    _reset_composite_marker(store)
    on = _scan_bytes(store, *extra, RMX_INJECTION_CAPTURE="full")
    mark = b"truncated by --max-tokens" if cut == "token-stop" else b"omitted by --max-bytes"
    assert mark in off.stdout, f"fixture: {cut} did not trip:\n{off.stdout[-400:]!r}"
    assert (on.returncode, on.stdout) == (off.returncode, off.stdout), (
        f"{cut}: the capture changed the payload or exit: rc {off.returncode}->{on.returncode}, "
        f"{len(off.stdout)} B -> {len(on.stdout)} B")


_EVENT_VOLATILE = {"ts", "query_id", "cwd", "root"}
_ROW_VOLATILE = {"ts", "latency_ms", "query_id"}


def test_capture_only_bundles_emit_no_recall_events(store, calib):
    """AC-0.5 (guard; M0-2): with the capture on (mode full, so bundles past the token stop are
    built for it), the call's retrieved and delivered events and its query.log row, apart from
    ts and timing, are those of the same call with the capture off. Both arms write events:
    the capture switch leaves telemetry on."""
    extra = ["--max-tokens", str(calib["t3"])]
    _scan(store, *extra, RMX_INJECTION_CAPTURE="0")
    q_off = _last_qid(store["root"])
    _reset_composite_marker(store)
    _scan(store, *extra, RMX_INJECTION_CAPTURE="full")
    q_on = _last_qid(store["root"])
    assert q_on != q_off

    def norm_events(qid):
        return sorted(json.dumps({k: v for k, v in e.items() if k not in _EVENT_VOLATILE},
                                 sort_keys=True) for e in _events(store["root"], qid))

    ev_off, ev_on = norm_events(q_off), norm_events(q_on)
    assert ev_off, "fixture: the capture-off arm wrote no recall events"
    assert ev_on == ev_off, (
        f"the capture changed the call's recall events: off {len(ev_off)}, on {len(ev_on)}; "
        f"stages on {Counter(json.loads(e)['stage'] for e in ev_on)} vs off "
        f"{Counter(json.loads(e)['stage'] for e in ev_off)}")
    rows = {r["query_id"]: r for r in _query_rows(store["root"])}
    norm = [{k: v for k, v in rows[q].items() if k not in _ROW_VOLATILE} for q in (q_off, q_on)]
    assert norm[0] == norm[1], f"the capture changed the query.log row: {norm}"


# ---- AC-0.6 -----------------------------------------------------------------------------------


def test_a_composite_stored_as_dropped_is_sent_on_the_next_prompt(store):
    """AC-0.6 (guard of 0.84.0's S3 with the capture on; M0-3): a composite the byte fit
    dropped is stored as `dropped_bytes` with its text, its sent marker is NOT committed, and
    the next prompt with room delivers it. (RED at base only by the missing record.)"""
    sections = _scan(store, "--max-tokens", "100000", "--no-composite",
                     RMX_INJECTION_CAPTURE="0", RMX_INVOCATION_SOURCE="internal")
    cap = len(sections.stdout.encode("utf-8")) + 80
    capped = _scan(store, "--max-tokens", "100000", "--max-bytes", str(cap))
    assert COMP_MARK not in capped.stdout, f"fixture: the cap kept the composite"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    comp = _blocks(rec, kind="composite")
    assert [b["state"] for b in comp] == ["dropped_bytes"], (
        [(b["kind"], b["state"]) for b in rec["blocks"]])
    assert COMP_MARK in (comp[0].get("text") or ""), comp[0]
    again = _scan(store, "--max-tokens", "100000")
    assert COMP_MARK in again.stdout, (
        "a composite stored as dropped was marked sent and is suppressed on the next prompt "
        f"with room:\n{again.stdout[-800:]}")


# ---- AC-0.7 -----------------------------------------------------------------------------------


@pytest.fixture
def recall_store():
    c = _build(ring=False, docs=False, memories=12)
    try:
        yield c
    finally:
        _teardown(c)


_HOOK = re.compile(r"^- (capmem_\d\d) — .*\n", re.M)
_BODY = re.compile(r"^## (capmem_\d\d)\n(.*?\n)(?=## |\+\d+ more:|\Z)", re.M | re.S)


def _recall(c: dict, budget: int) -> subprocess.CompletedProcess:
    r = _rmx(c, "memory", "recall", "--session-start", "--pack", "--k", "12",
             "--max-bytes", str(budget))
    assert r.returncode == 0, f"recall exited {r.returncode}: {r.stderr[-800:]}"
    return r


def test_a_packed_recall_writes_one_block_per_hit(recall_store):
    """AC-0.7 (RED): 12 hits under a budget that names 8 and bodies 2 give 2 `delivered`,
    6 `delivered_hook_only` and 4 `dropped_bytes` `recall_hit` blocks, and no body text
    anywhere in the record. The SessionStart pack is used: the per-prompt pack carries no
    bodies (25.1 d3). The budget is derived from an uncapped pack of the same store."""
    from refmatrix import recall_pack
    c = recall_store
    full = _recall(c, 20000).stdout
    lines = {m.group(1): m.group(0) for m in _HOOK.finditer(full)}
    bodies = {m.group(1): f"## {m.group(1)}\n{m.group(2)}" for m in _BODY.finditer(full)}
    order = [m.group(1) for m in _HOOK.finditer(full)]
    assert len(order) == 12 and len(bodies) == 12, f"fixture: uncapped pack:\n{full}"
    small = _recall(c, 400).stdout
    tm = re.search(r"^\+\d+ more: (.+)$", small, re.M)
    assert tm, f"fixture: no trailer at 400 B:\n{small}"
    trailer4 = f"+4 more: {tm.group(1)}\n"
    fixed = (sum(len(lines[n].encode()) for n in order[:8])
             + sum(len(bodies[n].encode()) for n in order[:2]) + len(trailer4.encode()))
    budget = fixed + 60
    for _ in range(4):                          # the header names the budget: settle its digits
        budget = fixed + len(recall_pack.header_line(channel="session_start", hits=12,
                                                     max_bytes=budget).encode())
    r = _recall(c, budget)
    named = [m.group(1) for m in _HOOK.finditer(r.stdout)]
    bodied = [m.group(1) for m in _BODY.finditer(r.stdout)]
    assert named == order[:8] and bodied == order[:2] and "+4 more:" in r.stdout, (
        f"fixture: budget {budget} named {named}, bodied {bodied}:\n{r.stdout}")
    rec = _record_for(c["root"], _last_qid(c["root"], kind="recall"))
    assert rec["channel"] == "session_start", rec["channel"]
    assert rec["payload_sha256"] == _sha(r.stdout), "payload_sha256 is not the printed pack's"
    hits = sorted(_blocks(rec, kind="recall_hit"), key=lambda b: b["rank"])
    assert len(hits) == 12, f"{len(hits)} recall_hit blocks for 12 hits"
    for b in hits:
        assert RECALL_HIT_KEYS <= set(b), f"recall_hit block lacks {RECALL_HIT_KEYS - set(b)}"
        assert (b["scope"], b["mtype"]) == ("project", "feedback"), b
    assert [b["state"] for b in hits] == (["delivered"] * 2 + ["delivered_hook_only"] * 6
                                          + ["dropped_bytes"] * 4), [b["state"] for b in hits]
    assert [b["name"] for b in hits] == order, [b["name"] for b in hits]
    for b in hits[:8]:
        assert b["hook_bytes"] == len(lines[b["name"]].encode()), b
    for b in hits[:2]:
        content = f"Rule {b['name'][-2:]}.\nBODYQ{b['name'][-2:]}"
        assert b["body_bytes"] == len(content.encode()) and b["body_sha256"] == _sha(content), b
    assert "BODYQ" not in json.dumps(rec), "the record stores memory body text"


# ---- AC-0.8 -----------------------------------------------------------------------------------


def _canary_lines_outside_header(blk: dict) -> "list[str]":
    """Lines of a block's text that carry the canary where the render's header does not.

    The header is the `# refmatrix ...` section line and, for a block of kind `content` only,
    its FIRST `=== context for `<candidate bag>` ===` line: the content bundle's anchor is the
    prompt's candidate words, stored as rendered (R0.1). Ruling L155 (2026-11-15): the first
    reading allowed only the `# refmatrix` line and failed on green-315's faithful render."""
    bad: list[str] = []
    anchor_seen = False
    for ln in blk["text"].splitlines():
        is_anchor = ln.startswith("=== context for `")
        if CANARY in ln and not ln.startswith("# refmatrix ") and not (
                is_anchor and not anchor_seen and blk.get("kind") == "content"):
            bad.append(ln)
        anchor_seen = anchor_seen or is_anchor
    return bad


def test_prompt_text_appears_only_inside_block_text(store, calib):
    """AC-0.8 (RED): the record's keys are exactly the schema's; `prompt_sha256` is the
    prompt's hash; a canary prompt term appears in no field but `blocks[*].text`, there only
    where the printed payload carried it (a delivered block) or in a dropped block's header
    (the `# refmatrix` line, and for the content block its first `=== context for` anchor,
    which is the prompt's candidate words; L155); a prompt that produces nothing writes a
    record with no blocks and no canary.

    The canary is a prompt term the store does not hold, so the only block a render carries it
    in is the content block (its header's first eight terms and its candidate-bag anchor). Call 1 delivers that block; call 2
    (the same prompt, tier 1 tripping the token stop) drops it, so the canary is only in the
    uncapped render of a dropped block; call 3 is the canary alone, which produces nothing."""
    p_a = f"{CANARY} {PROMPT}"
    p_b = CANARY
    a = _scan(store, "--no-composite", "--max-tokens", "100000", prompt=p_a)
    assert CANARY in a.stdout, f"fixture: the payload does not carry the canary:\n{a.stdout}"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    a2 = _scan(store, "--no-composite", "--max-tokens", str(calib["t1"]), prompt=p_a)
    assert CANARY not in a2.stdout and TOKEN_MARK in a2.stdout, f"fixture:\n{a2.stdout}"
    rec2 = _record_for(store["root"], _last_qid(store["root"]))
    b = _scan(store, "--no-composite", prompt=p_b)
    assert b.stdout == "", f"fixture: the canary-only prompt produced a payload:\n{b.stdout}"
    rec_b = _record_for(store["root"], _last_qid(store["root"]))
    for r, p in ((rec, p_a), (rec2, p_a), (rec_b, p_b)):
        assert set(r) == SCHEMA_KEYS, (f"record keys differ from R0.2's: extra "
                                       f"{set(r) - SCHEMA_KEYS}, missing {SCHEMA_KEYS - set(r)}")
        assert r["prompt_sha256"] == _sha(p) and r["prompt_chars"] == len(p)
        outer = json.dumps({k: v for k, v in r.items() if k != "blocks"})
        assert CANARY not in outer, "the canary is in a record field outside blocks"
        for blk in r["blocks"]:
            assert CANARY not in json.dumps({k: v for k, v in blk.items() if k != "text"}), blk
    for r, out in ((rec, a.stdout), (rec2, a2.stdout)):
        delivered = _joined_delivered(r)
        _assert_is_payload(delivered, out, "canary prompt")
        assert delivered.count(CANARY) == out.count(CANARY)
        for blk in r["blocks"]:
            if blk.get("state") != "delivered" and blk.get("text"):
                bad = _canary_lines_outside_header(blk)
                assert not bad, f"the canary outside a dropped block's header: {bad}"
    held = [blk for blk in rec2["blocks"] if CANARY in (blk.get("text") or "")]
    assert [(blk["kind"], blk["state"]) for blk in held] == [("content", "dropped_tokens")], (
        f"the canary of the dropped content header: {[(x['kind'], x['state']) for x in held]}")
    assert rec_b["blocks"] == [], rec_b["blocks"]
    assert CANARY not in json.dumps(rec_b), "the empty call's record carries the canary"


# ---- AC-0.9 -----------------------------------------------------------------------------------


def test_old_and_oversize_day_files_are_pruned_and_listed(store):
    """AC-0.9 (RED): before appending, the writer removes day files older than 42 days, then
    the oldest earlier day files while the total exceeds 64 MiB, never the current day's, and
    lists what it removed in the record's `pruned`. The clock is the real one; the day files'
    names and mtimes are set relative to it; the over-bound files are sparse."""
    d = _capture_dir_with_ignore(store["root"])
    old50 = d / f"capture-{_day(-50)}.jsonl"
    old50.write_text("{}\n", encoding="utf-8")
    _sparse(old50, old50.stat().st_size, days_old=50)
    d10 = d / f"capture-{_day(-10)}.jsonl"
    _sparse(d10, 40 * MiB, days_old=10)
    d5 = d / f"capture-{_day(-5)}.jsonl"
    _sparse(d5, 30 * MiB, days_old=5)
    day0 = _today()
    _scan(store, "--max-tokens", "100000")
    assert _today() == day0, "the run crossed UTC midnight; rerun"
    today = d / f"capture-{day0}.jsonl"
    assert today.exists(), f"no record appended today; {_listing(store['root'])}"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    assert not old50.exists(), "the 50-day file was kept (retention 42 days)"
    assert not d10.exists(), "70 MiB of day files is over the 64 MiB bound; the oldest stayed"
    assert d5.exists(), "a day file was pruned although the total was within the bound"
    assert sorted(Path(str(p)).name for p in rec["pruned"]) == sorted([old50.name, d10.name]), (
        rec["pruned"])


def test_a_day_file_over_the_bound_stops_appending(store):
    """AC-0.9 (RED): the current day's file is never pruned; when it alone is over the bound,
    no record is appended that day and the skipped call is one `over_bound` line in
    `errors.jsonl`."""
    d = _capture_dir_with_ignore(store["root"])
    day0 = _today()
    today = d / f"capture-{day0}.jsonl"
    _sparse(today, 65 * MiB, days_old=0)
    r = _scan(store, "--max-tokens", "100000")
    assert _today() == day0, "the run crossed UTC midnight; rerun"
    assert r.stdout, "fixture: empty payload"
    assert today.exists(), "the current day's file was pruned"
    assert today.stat().st_size == 65 * MiB, (
        f"a record was appended over the bound: {today.stat().st_size - 65 * MiB} B")
    errs = _errors(store["root"])
    assert [e.get("reason") for e in errs] == ["over_bound"], (
        f"errors.jsonl: {errs}; {_listing(store['root'])}")
    assert errs[0].get("channel") == "scan_prompt" and \
        errs[0].get("query_id") == _last_qid(store["root"]), errs[0]


def test_a_file_another_process_removed_is_not_an_error(store):
    """AC-0.9 (RED): two hook processes prune in parallel, so a day file that is listed and
    then gone is not an error. Modelled by a real input: an old day file whose entry resolves
    to nothing (a dangling link): listing finds it, stat says it does not exist. The call still
    appends its record and writes no `errors.jsonl` line."""
    d = _capture_dir_with_ignore(store["root"])
    gone = d / f"capture-{_day(-50)}.jsonl"
    os.symlink(d / "vanished-by-another-process.jsonl", gone)
    r = _scan(store, "--max-tokens", "100000")
    assert r.returncode == 0
    _record_for(store["root"], _last_qid(store["root"]))
    assert _errors(store["root"]) == [], f"a vanished day file was an error: {_errors(store['root'])}"


def test_a_day_file_the_pruner_cannot_remove_is_counted_and_kept(store):
    """AC-0.9 (L178 M2, X-3; bsd-315 r1 P4 as a test): a capture dir at 0o555 holding a 2020
    day file. The pruner cannot remove it: the call still exits 0 with its payload, the
    failure is one `prune_failed` line in errors.jsonl (naming PermissionError), the old file
    stays, and today's record is appended (today's file and errors.jsonl exist and are
    writable; only the directory is not)."""
    _scan(store, "--max-tokens", "100000")              # makes the dir, .gitignore, today's file
    d = store["root"] / CAP_DIR
    old = d / "capture-20200101.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    (d / "errors.jsonl").write_text("", encoding="utf-8")
    control = _scan_bytes(store, "--max-tokens", "100000", "--no-composite",
                          RMX_INJECTION_CAPTURE="0", RMX_INVOCATION_SOURCE="internal")
    os.chmod(d, 0o555)
    try:
        r = _scan_bytes(store, "--max-tokens", "100000", "--no-composite")
    finally:
        os.chmod(d, 0o755)
    assert (r.returncode, r.stdout) == (control.returncode, control.stdout), (
        f"rc {r.returncode}; stderr {r.stderr[-600:]!r}")
    errs = _errors(store["root"])
    assert [e.get("reason") for e in errs] == ["prune_failed"], f"errors.jsonl: {errs}"
    assert "PermissionError" in (errs[0].get("error") or ""), errs[0]
    assert old.exists(), "a file the pruner could not remove is gone"
    _record_for(store["root"], _last_qid(store["root"]))


def test_a_capped_errors_file_is_named_on_the_capture_line(store):
    """AC-0.10 / R0.4 (L178 M2, X-2; RED): errors.jsonl stops growing at 1 MiB, and a capped
    file is said on the `capture:` line as `errors_capped`, so a count that stopped is not
    read as a count that is complete."""
    d = _capture_dir_with_ignore(store["root"])
    filler = (json.dumps({"ts": "2026-01-01T00:00:00.000Z", "query_id": "filler",
                          "channel": "scan_prompt", "reason": "append_failed",
                          "error": None}) + "\n")
    (d / "errors.jsonl").write_text(filler * (MiB // len(filler) + 1), encoding="utf-8")
    size = (d / "errors.jsonl").stat().st_size
    assert size >= MiB, size
    day = d / f"capture-{_today()}.jsonl"
    day.write_text("", encoding="utf-8")
    os.chmod(day, 0o444)
    _scan(store, "--max-tokens", "100000")              # its append fails; the line is capped
    assert (d / "errors.jsonl").stat().st_size == size, "errors.jsonl grew past its cap"
    line = _capture_line(store)
    assert "errors_capped" in line, f"a capped errors.jsonl is not named: {line!r}"


def test_the_coverage_window_starts_at_the_first_capture_record(store):
    """R0.6 (L178 M3; RED): with no `--since`, the coverage denominator counts the hook calls
    from the first capture record on, not every hook row `query.log` ever held. Three hook
    rows from before the capture existed are not uncaptured calls. (With no record at all
    every hook row counts, so a capture that never wrote reads 0 of N: AC-0.10.)"""
    with open(store["root"] / "query.log", "a", encoding="utf-8") as f:
        for i in range(3):
            f.write(json.dumps({"ts": f"2026-01-0{i + 1}T00:00:00", "kind": "scan",
                                "body": "old", "source": "scan-prompt", "invocation": "hook",
                                "outcome": "ok", "query_id": f"old{i}"}) + "\n")
    _scan(store, "--max-tokens", "100000")
    line = _capture_line(store)
    assert _coverage(line) == (1, 1), (
        f"the coverage counts hook calls from before the first capture record: {line!r}")


# ---- AC-0.10 ----------------------------------------------------------------------------------


def test_a_failed_append_keeps_the_payload_and_is_counted(store):
    """AC-0.10 (RED): with the day file unwritable, stdout and exit status are those of the
    same call with the capture off, `errors.jsonl` holds one `append_failed` line with no
    payload text, and `rmx telemetry --context` prints a `capture:` line with one error."""
    control = _scan_bytes(store, "--no-composite", RMX_INJECTION_CAPTURE="0",
                          RMX_INVOCATION_SOURCE="internal")
    d = _capture_dir_with_ignore(store["root"])
    day = d / f"capture-{_today()}.jsonl"
    day.write_text("", encoding="utf-8")
    os.chmod(day, 0o444)
    r = _scan_bytes(store, "--no-composite")
    assert (r.returncode, r.stdout) == (control.returncode, control.stdout), (
        f"a failed append changed the payload or exit: rc {r.returncode}; "
        f"stderr {r.stderr[-600:]!r}")
    errs = _errors(store["root"])
    assert [e.get("reason") for e in errs] == ["append_failed"], (
        f"errors.jsonl: {errs}; {_listing(store['root'])}")
    e = errs[0]
    assert {"ts", "query_id", "channel", "reason"} <= set(e), e
    assert (e["channel"], e["query_id"]) == ("scan_prompt", _last_qid(store["root"])), e
    assert not any(w in json.dumps(e) for w in ("widget_registry", "ledger_codec", "harbor")), (
        f"errors.jsonl carries payload text: {e}")
    line = _capture_line(store)
    assert _count(line, "append_failed") == 1, f"the capture: line: {line!r}"


def test_an_unwritable_capture_dir_shows_as_missing_coverage(store):
    """AC-0.10 (RED): when nothing can be written into the capture dir, stdout and exit status
    are unchanged and the `capture:` line reads 0 captured of 1 hook call."""
    control = _scan_bytes(store, "--no-composite", RMX_INJECTION_CAPTURE="0",
                          RMX_INVOCATION_SOURCE="internal")
    d = _capture_dir_with_ignore(store["root"])
    os.chmod(d, 0o555)
    try:
        r = _scan_bytes(store, "--no-composite")
    finally:
        os.chmod(d, 0o755)
    assert (r.returncode, r.stdout) == (control.returncode, control.stdout), (
        f"an unwritable capture dir changed the payload or exit: rc {r.returncode}; "
        f"stderr {r.stderr[-600:]!r}")
    line = _capture_line(store)
    assert _coverage(line) == (0, 1), f"the capture: line: {line!r}"


# bsd-315 r1 P5: a lone surrogate the JSON envelope can carry and click can still print.
SURROGATE_PROMPT_JSON = "widget_registry \\ud800 harbor lantern"


def _surrogate_envelope(c: dict) -> str:
    return ('{"session_id": "%s", "prompt": "%s", "hook_event_name": "UserPromptSubmit"}'
            % (SESSION, SURROGATE_PROMPT_JSON))


@pytest.mark.parametrize("route,fault", [
    ("scan_prompt", "surrogate"), ("scan_prompt", "dir-0o300"),
    ("prompt_recall", "surrogate"), ("session_start", "dir-0o300"),
])
def test_a_capture_failure_never_changes_the_exit_or_loses_the_capture_line(
        request, route, fault):
    """AC-0.10 (L178 S1, bug-276; RED): the capture never changes the exit status, whatever
    class its failure is. (a) A lone-surrogate prompt in the hook envelope (the writer's
    `prompt.encode` raised UnicodeEncodeError: capture-off exited 0, capture-on 1). (b) A
    capture dir at 0o300, writable but not listable (`os.listdir` raised PermissionError
    from the pruner and from the report). Each call prints what the same call prints with the
    capture off, exits 0 with no traceback, and `rmx telemetry --context` still exits 0 with
    its `capture:` line. The recall `--pack` hooks have no `|| true`, so a scan and a recall
    route are both covered."""
    c = request.getfixturevalue("store" if route == "scan_prompt" else "recall_store")
    if route == "scan_prompt":
        args = ["scan-prompt", "--stdin-json", "--composite-every", "1", "--max-tokens",
                "100000"]
    elif route == "prompt_recall":
        args = ["memory", "recall", "--stdin-json", "--recent", "--pack", "--k", "12"]
    else:
        args = ["memory", "recall", "--session-start", "--pack", "--k", "12"]
    stdin = (_surrogate_envelope(c) if fault == "surrogate" else
             (json.dumps({"session_id": SESSION, "prompt": PROMPT,
                          "hook_event_name": "UserPromptSubmit"}) if "--stdin-json" in args
              else ""))

    def call(**env):
        env.setdefault("RMX_INVOCATION_SOURCE", "hook")
        return subprocess.run([h.rmx_bin(), *args], input=stdin.encode("utf-8", "surrogatepass"),
                              env=h.rmx_env(c["root"], **env), cwd=str(c["proj"]),
                              capture_output=True, timeout=300)

    d = c["root"] / CAP_DIR
    if fault == "dir-0o300":
        _capture_dir_with_ignore(c["root"])
    control = call(RMX_INJECTION_CAPTURE="0", RMX_INVOCATION_SOURCE="internal")
    assert control.returncode == 0 and control.stdout, (
        f"fixture: the capture-off call: rc {control.returncode} {control.stderr[-400:]!r}")
    # The control arm delivers the composite and commits its sent marker; reset it so the
    # capture-on arm starts from the same state (as AC-0.4 does). `--no-composite` would hide
    # the composite path from this check (L178 GREEN verify, lead ruling).
    _reset_composite_marker(c)
    if fault == "dir-0o300":
        os.chmod(d, 0o300)
    try:
        r = call()
        line_err = None
        try:
            _capture_line(c)
        except AssertionError as e:
            line_err = str(e)
    finally:
        if d.exists():
            os.chmod(d, 0o755)
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0 and "Traceback" not in err, (
        f"bug-276: {route} with {fault} exited {r.returncode}: {err[-700:]}")
    assert r.stdout == control.stdout, f"bug-276: {route} with {fault} changed the payload"
    assert line_err is None, f"bug-276: the capture: line is lost: {line_err[:600]}"
    # Not merely survived: the capture still works. The surrogate prompt is hashed (no
    # `capture_failed`), and a dir it cannot list is counted `list_failed` while the record is
    # still appended (0o300 can create and append, not list).
    qid = _last_qid(c["root"], kind="scan" if route == "scan_prompt" else "recall")
    _record_for(c["root"], qid)
    reasons = [e.get("reason") for e in _errors(c["root"])]
    assert "capture_failed" not in reasons, f"the capture failed on {fault}: {_errors(c['root'])}"
    if fault == "dir-0o300":
        assert "list_failed" in reasons, f"an unlistable dir is not counted: {reasons}"


# A non-I/O failure inside the capture (L178 S1; SELF_AUDIT Q7 "force one non-I/O failure
# class too"). With the surrogate encode fixed no real input reaches the guard with a non-I/O
# class, so the guarded body `telemetry._write_capture` is replaced, IN A CHILD PROCESS ONLY,
# by one that raises ValueError; `write_capture`'s guard and the real `cli_entry` run.
# Registered in workflow/test_mock_registry.md.
_CAPTURE_RAISES_RUN = r"""
import sys
from refmatrix import telemetry
def _raise(*a, **kw):
    raise ValueError("injected non-I/O capture failure (bug-276)")
telemetry._write_capture = _raise
from refmatrix.cli import cli_entry
sys.argv = ["rmx", *sys.argv[1:]]
cli_entry()
"""


@pytest.mark.parametrize("route", ["scan_prompt", "session_start"])
def test_a_capture_failure_of_any_class_is_counted_and_keeps_the_exit(request, route):
    """bug-276 (L178 S1): ONE guard around the whole capture at both call sites. A capture
    that raises a non-I/O exception (ValueError here) leaves the payload and the exit status
    as they are with the capture off, writes no record, and is one `capture_failed` line in
    errors.jsonl naming the class."""
    import sys as _sys
    c = request.getfixturevalue("store" if route == "scan_prompt" else "recall_store")
    args = (["scan-prompt", "--text", PROMPT, "--composite-every", "1", "--max-tokens",
             "100000"] if route == "scan_prompt"
            else ["memory", "recall", "--session-start", "--pack", "--k", "12"])
    _capture_dir_with_ignore(c["root"])

    def call(patched: bool, **env):
        env.setdefault("RMX_INVOCATION_SOURCE", "hook")
        env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        argv = ([_sys.executable, "-c", _CAPTURE_RAISES_RUN, *args] if patched
                else [h.rmx_bin(), *args])
        return subprocess.run(argv, input=b"", env=h.rmx_env(c["root"], **env),
                              cwd=str(c["proj"]), capture_output=True, timeout=300)

    control = call(False, RMX_INJECTION_CAPTURE="0", RMX_INVOCATION_SOURCE="internal")
    assert control.returncode == 0 and control.stdout, f"fixture: {control.stderr[-400:]!r}"
    _reset_composite_marker(c)
    r = call(True)
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0 and "Traceback" not in err, (
        f"bug-276: a non-I/O capture failure exited {r.returncode}: {err[-700:]}")
    assert r.stdout == control.stdout, "a non-I/O capture failure changed the payload"
    errs = _errors(c["root"])
    assert [e.get("reason") for e in errs] == ["capture_failed"], f"errors.jsonl: {errs}"
    assert "ValueError" in (errs[0].get("error") or ""), errs[0]
    qid = _last_qid(c["root"], kind="scan" if route == "scan_prompt" else "recall")
    assert not [x for x in _records(c["root"]) if x.get("query_id") == qid], (
        "a record was written by a capture that failed")


# ---- AC-0.11 (characterization) ---------------------------------------------------------------


def test_json_format_writes_no_capture_record(store):
    """AC-0.11: `--format json` is an answer, not a hook payload: no capture record."""
    r = _rmx(store, "scan-prompt", "--text", PROMPT, "--format", "json")
    assert r.returncode == 0 and json.loads(r.stdout), f"fixture: {r.stdout[:300]}"
    assert not (store["root"] / CAP_DIR).exists(), _listing(store["root"])


def test_a_verb_recall_with_pack_writes_no_capture_record(recall_store):
    """AC-0.11 (M0-13): `verbs.memory_recall` called bare with `pack`, the way the MCP adapter
    calls it, writes no capture record. A sandbox daemon serves the store (the verb's recent
    leg is daemon-routed); the verb must really pack, or the test would prove nothing."""
    from refmatrix import verbs
    c = recall_store
    d = h.SandboxDaemon(c["root"], RMX_NO_EMBED_WARMUP="1", RMX_RERANK="0")
    try:
        res = verbs.memory_recall(c["root"], session_start=True, k=12, pack=True,
                                  max_bytes=4000, timeout=60)
    finally:
        d.stop()
    assert res.get("text") and res.get("named"), f"fixture: the verb did not pack: {res}"
    assert not (c["root"] / CAP_DIR).exists(), _listing(c["root"])


# ---- AC-0.15 ----------------------------------------------------------------------------------


def _git(proj: Path, *args) -> str:
    env = h.clean_env(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                      HOME=os.environ["HOME"])
    r = subprocess.run(["git", *args], cwd=str(proj), env=env, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


def _assert_git_never_sees_the_capture(proj: Path) -> None:
    status = _git(proj, "status", "--porcelain", "-uall")
    assert ".refmatrix/catalog" in status, (
        f"fixture: the store is ignored by some rule, so the test proves nothing:\n{status}")
    listed = [ln for ln in status.splitlines() if f"{CAP_DIR}/" in ln]
    assert not listed, f"`git status` lists the capture: {listed}"
    _git(proj, "add", "-A")
    staged = [ln for ln in _git(proj, "diff", "--cached", "--name-only").splitlines()
              if f"{CAP_DIR}/" in ln]
    assert not staged, f"`git add -A` staged the capture: {staged}"


@pytest.fixture
def git_store(store):
    _git(store["proj"], "init", "-q")
    assert not (store["proj"] / ".gitignore").exists()
    return store


def test_the_capture_dir_ignores_itself(git_store):
    """AC-0.15 (RED): in a git repository with no ignore rules, after one `scan-prompt`
    call, nothing under `injection-capture/` shows in `git status` or is staged by
    `git add -A` (bug-261: fleet repos that do not ignore `.refmatrix/`)."""
    _scan(git_store, "--max-tokens", "100000")
    days = list((git_store["root"] / CAP_DIR).glob("capture-*.jsonl")) \
        if (git_store["root"] / CAP_DIR).is_dir() else []
    assert days, f"no capture written; {_listing(git_store['root'])}"
    _assert_git_never_sees_the_capture(git_store["proj"])


def test_an_existing_capture_dir_without_gitignore_gets_one(git_store):
    """AC-0.15 (RED; M0-10 second step): a capture dir made by hand, with no `.gitignore`,
    before the call: the writer checks before EVERY write and creates it."""
    (git_store["root"] / CAP_DIR).mkdir()
    _scan(git_store, "--max-tokens", "100000")
    days = list((git_store["root"] / CAP_DIR).glob("capture-*.jsonl"))
    assert days, f"no capture written; {_listing(git_store['root'])}"
    _assert_git_never_sees_the_capture(git_store["proj"])


def test_an_errors_only_write_into_a_bare_capture_dir_is_ignored(git_store):
    """AC-0.15 (RED), the third case: the call's only write is a line of `errors.jsonl`
    (the day file is unwritable) into a hand-made dir with no `.gitignore`."""
    d = git_store["root"] / CAP_DIR
    d.mkdir()
    day = d / f"capture-{_today()}.jsonl"
    day.write_text("", encoding="utf-8")
    os.chmod(day, 0o444)
    _scan(git_store, "--max-tokens", "100000")
    assert (d / "errors.jsonl").exists(), f"no errors.jsonl line; {_listing(git_store['root'])}"
    _assert_git_never_sees_the_capture(git_store["proj"])


# ---- AC-0.16 (bug-256) ------------------------------------------------------------------------


# AC-0.16's raising input (L178 S4). The corrupt focus graph it used (`[]`) is no longer one:
# the loader reads a wrong shape as an empty graph for every reader (bug-268). No other real
# input raises inside the composite build: the graph is validated, the sent marker and the
# PageRank read fail open, and the store calls are the ones the payload's own sections make.
# So the composite's dependency `topic_composites` is replaced, IN A CHILD PROCESS ONLY, by one
# that raises; the real `cli_entry` runs everything else. Registered in test_mock_registry.md.
_COMPOSITE_RAISES_RUN = r"""
import sys
from refmatrix import composite
def _raise(*a, **kw):
    raise RuntimeError("injected composite failure (AC-0.16)")
composite.topic_composites = _raise
from refmatrix.cli import cli_entry
sys.argv = ["rmx", *sys.argv[1:]]
cli_entry()
"""


def _scan_composite_raises(c: dict, *extra, **env) -> subprocess.CompletedProcess:
    import sys as _sys
    env.setdefault("RMX_INVOCATION_SOURCE", "hook")
    # cli_entry re-execs `sys.argv` for fork safety unless this is set; under `-c` that argv
    # is not a script (the first lane run: "can't open file '.../rmx'").
    env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    return subprocess.run([_sys.executable, "-c", _COMPOSITE_RAISES_RUN, "scan-prompt",
                           "--text", PROMPT, "--composite-every", "1", *extra], input=b"",
                          env=h.rmx_env(c["root"], **env), cwd=str(c["proj"]),
                          capture_output=True, timeout=300)


def test_a_raising_composite_build_is_recorded_and_counted(store):
    """AC-0.16 (bug-256, M0-11): the composite build raises (its dependency
    `topic_composites`, replaced in the child: see `_COMPOSITE_RAISES_RUN`). stdout is
    byte-identical to the same call with the composite absent; stderr carries one line naming
    the exception; the record's `composite_error` names it; `rmx telemetry --context` counts
    one."""
    control = _scan_composite_raises(store, "--max-tokens", "100000", "--no-composite",
                                     RMX_INJECTION_CAPTURE="0", RMX_INVOCATION_SOURCE="internal")
    r = _scan_composite_raises(store, "--max-tokens", "100000")
    assert r.returncode == 0, f"rc {r.returncode}: {r.stderr[-1200:]!r}"
    assert r.stdout == control.stdout, "a failing composite changed the payload"
    err_new = [ln for ln in r.stderr.decode("utf-8", "replace").splitlines() if ln.strip()
               and ln not in control.stderr.decode("utf-8", "replace").splitlines()]
    assert len(err_new) == 1 and "RuntimeError" in err_new[0], (
        f"bug-256: the composite failure said on stderr: {err_new}")
    rec = _record_for(store["root"], _last_qid(store["root"]))
    ce = json.dumps(rec["composite_error"])
    assert "RuntimeError" in ce and "injected composite failure" in ce, (
        f"composite_error does not name the exception: {rec['composite_error']!r}")
    line = _capture_line(store)
    assert _count(line, "composite_errors?") == 1, f"the capture: line: {line!r}"


# ---- AC-0.18 ----------------------------------------------------------------------------------


def _assert_telemetry_written(c: dict) -> None:
    qid = _last_qid(c["root"])
    assert _events(c["root"], qid), "the capture switch also turned off the recall events"


@pytest.mark.parametrize("switch", ["env", "marker"])
def test_the_capture_switch_leaves_telemetry_on(store, switch):
    """AC-0.18 (RED; M0-12): `RMX_INJECTION_CAPTURE=0` or the marker file
    `<store root>/injection-capture.off` turns off the capture only: no capture dir is
    created, and the call's query.log row and recall events are written. With the switch
    cleared the same store captures (the switch is what stopped it)."""
    rows_before = len(_query_rows(store["root"]))
    if switch == "env":
        _scan(store, "--max-tokens", "100000", RMX_INJECTION_CAPTURE="0")
    else:
        (store["root"] / "injection-capture.off").write_text("", encoding="utf-8")
        _scan(store, "--max-tokens", "100000")
    assert not (store["root"] / CAP_DIR).exists(), f"switch {switch}: {_listing(store['root'])}"
    assert len(_query_rows(store["root"])) == rows_before + 1, "no query.log row"
    _assert_telemetry_written(store)
    (store["root"] / "injection-capture.off").unlink(missing_ok=True)
    _scan(store, "--max-tokens", "100000")
    _record_for(store["root"], _last_qid(store["root"]))


def test_no_telemetry_implies_no_capture(store):
    """AC-0.18 (RED): `REFMATRIX_NO_TELEMETRY` turns the capture off too; without it the same
    store captures."""
    _scan(store, "--max-tokens", "100000", REFMATRIX_NO_TELEMETRY="1")
    assert not (store["root"] / CAP_DIR).exists(), _listing(store["root"])
    _scan(store, "--max-tokens", "100000")
    _record_for(store["root"], _last_qid(store["root"]))


def test_the_mode_file_selects_the_path(store):
    """AC-0.18 (RED; M0-14 second step): the one word in `<store root>/injection-capture.mode`
    selects the mode (both words tried, so neither release default hides an ignored file);
    `RMX_INJECTION_CAPTURE` outranks the file; an unrecognised word writes no record and
    shows as an invalid mode on the `capture:` line."""
    mode_file = store["root"] / "injection-capture.mode"

    def mode_of(**env) -> str:
        _scan(store, "--no-composite", **env)
        return _record_for(store["root"], _last_qid(store["root"]))["capture_mode"]

    mode_file.write_text("names\n", encoding="utf-8")
    assert mode_of() == "names"
    mode_file.write_text("full\n", encoding="utf-8")
    assert mode_of() == "full"
    assert mode_of(RMX_INJECTION_CAPTURE="names") == "names", "the env did not outrank the file"
    mode_file.write_text("names\n", encoding="utf-8")
    assert mode_of(RMX_INJECTION_CAPTURE="full") == "full", "the env did not outrank the file"
    n = len(_records(store["root"]))
    mode_file.write_text("bogus\n", encoding="utf-8")
    _scan(store, "--no-composite")
    assert len(_records(store["root"])) == n, "an unrecognised mode word still captured"
    line = _capture_line(store)
    assert "invalid mode" in line.lower(), f"the capture: line: {line!r}"


# ---- R0.5 step 3 (the static half of the cost method's prompt set) ----------------------------

PROMPTS = Path(__file__).resolve().parent / "fixtures" / "injection_capture" / "prompts.txt"
HUB_WORDS = ("daemon", "memory", "partition", "session")


def test_the_cost_prompt_set_is_forty_synthetic_prompts():
    """R0.5 `#r0-5-method` step 3, the part checkable without the live catalog: 40 distinct
    synthetic prompts, one per line, at least 10 carrying a hub word as a plain word. Whether
    at least half trip the token stop on the copy of the live catalog is the measurement's
    (AC-0.13), recorded in the implementation summary."""
    assert PROMPTS.exists(), f"{PROMPTS} does not exist (spec #files: new in release A)"
    lines = [ln for ln in PROMPTS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 40 and len(set(lines)) == 40, (len(lines), len(set(lines)))
    hub = [ln for ln in lines
           if any(re.search(rf"(?<![\w./-]){w}(?![\w./-])", ln, re.I) for w in HUB_WORDS)]
    assert len(hub) >= 10, f"{len(hub)} prompts carry a hub word as a plain word"
    assert not [ln for ln in lines if "/Users/" in ln or "session_id" in ln], (
        "a prompt line looks copied from a transcript")


# ---- bug-268 (L152): a wrong-shaped focus graph never crashes a hook ---------------------------

# Valid JSON, wrong shape: `Stm._load_graph` catches only JSONDecodeError / OSError, so each one
# reached `stm.phase_fields` and raised AttributeError / KeyError after the payload was printed.
WRONG_SHAPES = {
    "list": "[]",
    "int-node": '{"turn": 2, "nodes": {"x": 1}, "edges": {}}',
    "nameless-node": '{"turn": 2, "nodes": {"a": {"freq": 1}}, "edges": {}}',
    # Python's json reads `Infinity`; a non-finite turn passes a "number" check and raises
    # at `int(turn)` (found writing the L178 fold).
    "nonfinite-turn": '{"turn": Infinity, "nodes": {}, "edges": {}}',
}


def _fault_lines(err: str) -> "list[str]":
    """stderr lines that say a corrupt focus graph (bug-268's wording: `STM focus graph of
    session <s> is corrupt (...)`)."""
    return [ln for ln in err.splitlines()
            if "focus graph" in ln.lower() and "corrupt" in ln.lower()]


def _corrupt(c: dict, shape: str) -> None:
    g = c["root"] / "stm" / f"{SESSION}.focus.json"
    assert g.exists(), f"fixture: no focus graph at {g}"
    g.write_text(WRONG_SHAPES[shape], encoding="utf-8")


def _assert_survived(r: subprocess.CompletedProcess, what: str) -> None:
    err = r.stderr if isinstance(r.stderr, str) else r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0 and "Traceback" not in err, (
        f"bug-268: {what} exited {r.returncode} on a wrong-shaped focus graph: {err[-700:]}")


def _assert_counted(c: dict, kind: str, what: str) -> None:
    qid = _last_qid(c["root"], kind=kind)
    assert _events(c["root"], qid), f"bug-268: {what} wrote no recall events"
    rec = _record_for(c["root"], qid)
    assert rec.get("stm_error"), (
        f"bug-268: the capture record does not count the corrupt focus graph: "
        f"stm_error={rec.get('stm_error')!r}")
    line = _capture_line(c)
    assert _count(line, "stm_errors?") == 1, f"the capture: line: {line!r}"


@pytest.mark.parametrize("shape", sorted(WRONG_SHAPES))
def test_a_wrong_shaped_focus_graph_never_crashes_scan_prompt(store, shape):
    """bug-268 (RED): `rmx scan-prompt` for the session whose focus graph is valid JSON of
    the wrong shape exits 0, prints the payload it prints with the composite absent, writes
    its recall events (the phase read at `cli.py:9872` no longer raises), and the corruption
    is counted on the capture record (`stm_error`) and the `capture:` line."""
    control = _scan_bytes(store, "--max-tokens", "100000", "--no-composite",
                          RMX_INJECTION_CAPTURE="0", RMX_INVOCATION_SOURCE="internal")
    _corrupt(store, shape)
    env = {"session_id": SESSION, "prompt": PROMPT, "hook_event_name": "UserPromptSubmit",
           "cwd": str(store["proj"]), "transcript_path": ""}
    e = h.rmx_env(store["root"], RMX_INVOCATION_SOURCE="hook", RMX_SESSION=SESSION)
    r = subprocess.run([h.rmx_bin(), "scan-prompt", "--stdin-json", "--composite-every", "1",
                        "--max-tokens", "100000"], input=json.dumps(env).encode(), env=e,
                       cwd=str(store["proj"]), capture_output=True, timeout=300)
    _assert_survived(r, "scan-prompt")
    assert r.stdout == control.stdout, "a wrong-shaped focus graph changed the payload"
    _assert_counted(store, "scan", "scan-prompt")
    # L178 S4: the composite reads the same graph. It is read as empty, not raised: the fault
    # is the corrupt graph, said once for the call, not a composite failure.
    rec = _record_for(store["root"], _last_qid(store["root"]))
    assert rec["composite_error"] is None, (
        f"bug-268: the composite raised on the corrupt graph: {rec['composite_error']!r}")
    said = _fault_lines(r.stderr.decode("utf-8", "replace"))
    assert len(said) == 1, f"bug-268: the corrupt graph is said {len(said)} times: {said}"


@pytest.fixture
def recall_ring_store():
    c = _build(ring=True, docs=False, memories=12)
    try:
        yield c
    finally:
        _teardown(c)


@pytest.mark.parametrize("route", ["prompt_recall", "session_start"])
@pytest.mark.parametrize("shape", sorted(WRONG_SHAPES))
def test_a_wrong_shaped_focus_graph_never_crashes_recall(recall_ring_store, shape, route):
    """bug-268 (RED), the recall routes: `_RecallCall.emit` reads the same phase fields at
    `cli.py:13344` (prompt_recall: `--stdin-json`, here on the recent leg, which needs no
    embedder) and `cli.py:13347` (session_start). Each exits 0 with its pack, writes its
    recall events, and counts the corruption."""
    c = recall_ring_store
    _corrupt(c, shape)
    args = ["memory", "recall", "--pack", "--k", "12"]
    if route == "prompt_recall":
        args += ["--stdin-json", "--recent"]
        stdin = json.dumps({"session_id": SESSION, "prompt": "which rule applies here",
                            "hook_event_name": "UserPromptSubmit", "cwd": str(c["proj"]),
                            "transcript_path": ""})
    else:
        args += ["--session-start"]
        stdin = ""
    r = _rmx(c, *args, input=stdin, RMX_SESSION=SESSION)
    _assert_survived(r, f"memory recall ({route})")
    assert r.stdout.startswith(f"# rmx recall · {route} ·") and "capmem_" in r.stdout, (
        f"no pack printed:\n{r.stdout[:600]}")
    rows = [q for q in _query_rows(c["root"]) if q.get("kind") == "recall"]
    assert rows and rows[-1].get("session") == SESSION, (
        f"fixture: the call did not resolve the corrupt ring's session: {rows[-1:]}")
    _assert_counted(c, "recall", f"memory recall ({route})")


@pytest.mark.parametrize("shape", sorted(WRONG_SHAPES))
@pytest.mark.parametrize("reader", ["focus-hook", "focus-context", "pin"])
def test_a_wrong_shaped_focus_graph_never_crashes_a_reader(store, reader, shape):
    """bug-268 (L178 S4; RED): every reader of the focus graph reads a wrong shape as an empty
    graph and says it once, not only the phase read. Through their entry points:
    `rmx focus hook --event input` (the UserPromptSubmit focus hook: `Stm.snapshot_pre_prompt`
    then `_ingest_into_graph`), `rmx focus context` (SessionStart resume: `focus_graph`) and
    `Stm.pin` (no CLI caller; called in-process). The focus hook then REWRITES the graph, so the
    corruption is not sticky: the next hook reads a good graph and says nothing."""
    from refmatrix import stm as stm_mod
    _corrupt(store, shape)
    g_path = store["root"] / "stm" / f"{SESSION}.focus.json"
    if reader == "pin":
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            try:
                pinned = stm_mod.Stm(store["root"], SESSION).pin("parser.py")
            except Exception as e:      # noqa: BLE001 -- the RED names it
                pytest.fail(f"bug-268: Stm.pin raised on a {shape} graph: "
                            f"{type(e).__name__}: {e}")
        assert pinned is False, "pin found a node in a graph read as empty"
        said = _fault_lines(buf.getvalue())
        assert len(said) == 1, f"bug-268: pin said the corrupt graph {len(said)} times: {said}"
        return
    if reader == "focus-context":
        r = _rmx(store, "focus", "context", "-s", SESSION, RMX_INVOCATION_SOURCE="hook")
        _assert_survived(r, "focus context")
        said = _fault_lines(r.stderr)
        assert len(said) == 1, f"bug-268: focus context said it {len(said)} times: {said}"
        return
    envelope = {"session_id": SESSION, "prompt": "check widget_registry and parser.py",
                "hook_event_name": "UserPromptSubmit", "cwd": str(store["proj"]),
                "transcript_path": ""}
    r = _rmx(store, "focus", "hook", "--event", "input", input=json.dumps(envelope))
    _assert_survived(r, "focus hook --event input")
    said = _fault_lines(r.stderr)
    assert len(said) == 1, f"bug-268: the focus hook said it {len(said)} times: {said}"
    g = json.loads(g_path.read_text(encoding="utf-8"))
    assert stm_mod.focus_graph_problem(g) is None, (
        f"bug-268: the focus hook left the graph corrupt: {g_path.read_text()[:200]}")
    again = _rmx(store, "focus", "hook", "--event", "input", input=json.dumps(envelope))
    _assert_survived(again, "the next focus hook")
    assert not _fault_lines(again.stderr), (
        f"the corruption is sticky: {_fault_lines(again.stderr)}")


def test_a_corrupt_snapshot_graph_falls_back_to_the_live_state(store):
    """bug-268 (L178, GREEN self-audit Q6: the guard it named as untested). A
    `<session>.pre.json` that names this prompt and is fresh, but whose `graph` is the wrong
    shape, is corrupt like a live graph: said once, counted as the call's `stm_error`, and the
    live state is read instead, so `scan-prompt` exits 0 with its payload."""
    from refmatrix import stm as stm_mod
    import time as _time
    s = stm_mod.Stm(store["root"], SESSION)
    good = json.loads((store["root"] / "stm" / f"{SESSION}.focus.json").read_text())
    assert stm_mod.focus_graph_problem(good) is None, "fixture: the live graph is not good"
    control = _scan_bytes(store, "--max-tokens", "100000", "--no-composite",
                          RMX_INJECTION_CAPTURE="0", RMX_INVOCATION_SOURCE="internal")
    s._pre_path().write_text(json.dumps({
        "prompt_sha": stm_mod.prompt_sha(PROMPT), "wall": _time.time(), "turn": 2,
        "events_n": 2, "graph": {"turn": 2, "nodes": {"x": 1}, "edges": {}},
        "topic_cache": {}, "topic_match": {}}), encoding="utf-8")
    envl = {"session_id": SESSION, "prompt": PROMPT, "hook_event_name": "UserPromptSubmit",
            "cwd": str(store["proj"]), "transcript_path": ""}
    r = subprocess.run([h.rmx_bin(), "scan-prompt", "--stdin-json", "--max-tokens", "100000",
                        "--no-composite"], input=json.dumps(envl).encode(),
                       env=h.rmx_env(store["root"], RMX_INVOCATION_SOURCE="hook",
                                     RMX_SESSION=SESSION),
                       cwd=str(store["proj"]), capture_output=True, timeout=300)
    _assert_survived(r, "scan-prompt with a corrupt pre.json graph")
    assert r.stdout == control.stdout, "a corrupt snapshot graph changed the payload"
    said = _fault_lines(r.stderr.decode("utf-8", "replace"))
    assert len(said) == 1 and ".pre.json" in said[0], f"the corrupt snapshot said: {said}"
    rec = _record_for(store["root"], _last_qid(store["root"]))
    assert ".pre.json" in (rec.get("stm_error") or ""), (
        f"the corrupt snapshot is not the call's stm_error: {rec.get('stm_error')!r}")


def test_a_surrogate_prompt_never_crashes_the_prompt_hooks_with_the_capture_off(store):
    """bug-276's class outside the capture (L178 GREEN's real run): `stm.prompt_sha` encoded
    the prompt strictly. A lone surrogate in the envelope made the UserPromptSubmit focus hook
    (`snapshot_pre_prompt`) exit 1, and with a `<session>.pre.json` present made
    `scan-prompt` exit 1, with the capture OFF. Both exit 0 now; the hook writes its
    snapshot, and the scan prints what it prints for any prompt."""
    envl = _surrogate_envelope(store).encode("utf-8")
    off = h.rmx_env(store["root"], RMX_INVOCATION_SOURCE="hook", RMX_INJECTION_CAPTURE="0")
    hook = subprocess.run([h.rmx_bin(), "focus", "hook", "--event", "input"], input=envl,
                          env=off, cwd=str(store["proj"]), capture_output=True, timeout=300)
    _assert_survived(hook, "focus hook --event input with a surrogate prompt")
    pre = store["root"] / "stm" / f"{SESSION}.pre.json"
    assert pre.exists(), "the focus hook wrote no pre-prompt snapshot"
    r = subprocess.run([h.rmx_bin(), "scan-prompt", "--stdin-json", "--max-tokens", "100000"],
                       input=envl, env=off, cwd=str(store["proj"]), capture_output=True,
                       timeout=300)
    _assert_survived(r, "scan-prompt with a surrogate prompt and a pre.json, capture off")
    assert r.stdout, "scan-prompt printed nothing"
