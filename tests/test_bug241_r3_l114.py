"""0.83.1 ch-bsd r2 fold (ruling L114): REDs for M1 and M2.

Report: `workflow/bullshit/2026-11-15-0152-bug241-bug240-r2-bba7313.md` (#m1 #m2); ruling L114
in `workflow/plan-review-2026-11-13.md#lead`.

M1 (#m1). L112's S1 threaded the daemon's yield hook into the markdown GMD pass, but with the
daemon's CODE-unit cadence: `_op_ingest_path` passes `RMX_INGEST_YIELD_EVERY_UNITS` (default
200, tuned for cheap per-file code units), while the daemon's own GMD op (`_run_ingest_gmd_body`)
yields every doc (`RMX_INGEST_YIELD_EVERY`, default 1). Measured on 211 docs: 200 -> 40 yields,
max lock hold 15.0 s, p95 9.9 s; 1 -> 460 yields, max 5.4 s, p95 1.3 s, same total time. Pinned:
a cooperative `ingest_path` called with `yield_every=200` (what `_op_ingest_path` passes) over N
GMD docs yields at least N times inside the GMD pass, on the cached route (phase
`code+docs: markdown/gmd`) and on the tree route (phase `code+docs: tldr/tree`).

M2 (#m2). L112's S2 made a failed GMD pass an `Error:` with a non-zero exit on both CLI routes;
the agent route (`rmx_ingest` verb -> daemon `ingest_path_start` -> `_run_detached_job`) still
ends the job `status: done` with `gmd_pass_failed` only inside `result`, so an agent polling
`rmx_ingest_status` reads success. Pinned, through a real daemon: the finished job's TOP-LEVEL
fields (everything but `result`) carry an `error` / `warning(s)` / `failure(s)` value naming the
GMD pass. That admits both fixes bsd names -- `status: error` with an `error` naming the GMD pass,
or `status: done` with a top-level `warning` -- and refuses the count buried in `result`. A
`status: error` whose error does not name the GMD pass also fails: the agent must be told which
pass failed. Guard: a clean tree's job ends `done` with no such field.

Real input for the failure, no patch: frontmatter `id: [a, b]` makes `ingest_gmd_paths` raise
(`test_bug241_r2_l112.BAD_MD`). Throwaway stores under SHORT `/tmp` roots; daemons spawned by the
dev `rmx` with this checkout's code. No mocks.
"""
from __future__ import annotations

import json
import time

import pytest

from test_bug241_r2_l112 import _init, _project, _rmx, _start, base  # noqa: F401 (fixture)

DAEMON_YIELD_EVERY = 200     # `_op_ingest_path`: RMX_INGEST_YIELD_EVERY_UNITS default
N_DOCS = 12
TOP_LEVEL = ("error", "warning", "warnings", "failure", "failures")


# ---- M1 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("cache,phase", [
    ("metadata", "code+docs: markdown/gmd"),
    ("none", "code+docs: tldr/tree"),
])
def test_m1_the_gmd_pass_yields_per_doc_under_the_daemons_code_cadence(base, cache, phase):
    from refmatrix.ingest import ingest_path
    from refmatrix.store import Store
    proj = _project(base, cache, n_md=N_DOCS)
    root = proj / ".refmatrix"
    root.mkdir()
    current = {"phase": None}
    yields: dict = {}

    def _progress(name: str, done: int = 0, total: int = 0) -> None:
        current["phase"] = name

    def _yield() -> None:
        yields[current["phase"]] = yields.get(current["phase"], 0) + 1

    s = Store(root)
    try:
        with s.with_partition("proj"):
            ingest_path(s, proj, yield_lock=_yield, yield_every=DAEMON_YIELD_EVERY,
                        progress_cb=_progress)
            gmd_docs = sum(1 for i in range(N_DOCS) if s.get_entity("doc", f"d{i:02d}"))
    finally:
        s.close()
    assert gmd_docs == N_DOCS, f"the GMD pass ingested {gmd_docs}/{N_DOCS} docs (fixture broken)"
    assert yields.get(phase, 0) >= N_DOCS, (
        f"the GMD pass yielded {yields.get(phase, 0)} times over {N_DOCS} docs with the "
        f"daemon's yield_every={DAEMON_YIELD_EVERY}: it inherits the code-unit cadence, not the "
        f"GMD op's per-doc one; yields by phase: {yields}")


# ---- M2 ---------------------------------------------------------------------------------


def _run_job(base, *, bad: bool) -> dict:
    """`rmx_ingest(path=<tree>)` through the verb on a real daemon; the finished job record."""
    from refmatrix.verbs import VERBS
    proj = _project(base, "metadata", bad=bad)
    root, env = _init(proj)
    _start(root, env)
    try:
        started = VERBS["rmx_ingest"].run(root, {"path": str(proj)})
        job_id = started["job_id"]
        job: dict = {}
        for _ in range(360):
            job = VERBS["rmx_ingest_status"].run(root, {"job_id": job_id}).get("job") or {}
            if job.get("status") != "running":
                break
            time.sleep(0.5)
        assert job.get("status") != "running", f"the job never finished: {job}"
        return job
    finally:
        _rmx(env, "daemon", "stop", timeout=120)


def _top_level_reports(job: dict) -> dict:
    return {k: job[k] for k in TOP_LEVEL if job.get(k)}


def test_m2_a_failed_gmd_pass_is_reported_at_the_top_of_the_job_record(base):
    job = _run_job(base, bad=True)
    reports = _top_level_reports(job)
    assert "gmd" in json.dumps(reports, default=str).lower(), (
        f"the agent route reports a failed GMD pass only inside `result`: status="
        f"{job.get('status')!r}, top-level reports={reports}, result={job.get('result')}")
    assert job.get("status") in ("error", "done"), job


def test_m2_guard_a_clean_trees_job_ends_done_with_no_report(base):
    job = _run_job(base, bad=False)
    assert job.get("status") == "done", job
    assert not _top_level_reports(job), f"a clean ingest carries a report: {job}"
