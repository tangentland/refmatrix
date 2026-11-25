#!/usr/bin/env python3
"""Render the P1 (b) table and totals from inventory.tsv plus the reviewer's verdicts.

WHY: the report's table must have exactly one row per inventoried file (the brief's done
line), so the table is generated, never typed. The verdicts below are the reviewer's
reading (2026-11-25, base 0c798f28); the counts beside them come from inventory.py.

Usage: python3 render.py   (prints the GMD table and the totals to stdout)
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE_MIN = 20       # 29.4's sharded-runner target, quoted by task-29.5 `#test-strategy-list`
SERIAL_MIN = 54      # tests/shard_weights.json total_s 3,255 s
MUT_MIN = 1          # one named test file (mean 9.1 s in shard_weights) plus apply and revert

L, R, T, C = "leave", "rewrite at entry", "trim", "covered by rule"
NONE = "none"
RULE = "none; the step-4 ruling replaces its process text"
# file -> (row, distance from the head, rounds written in the text, full-suite runs written
#          in the text, verdict, the cut, the reason, what the cut puts at risk)
V: dict[str, tuple] = {}


def put(names: str, row: str, dist: int, rounds: str, runs: int, verdict: str,
        cut: str, reason: str, risk: str) -> None:
    for n in names.split():
        V[n] = (row, dist, rounds, runs, verdict, cut, reason, risk)


NEW = "written in the L232 window in the L165 shape; one ch-bsd pass is the rule's own"
put("task-hook-writes-queue.md", "C2", 0, "1 (= L165)", 0, L, NONE,
    "101 lines, in build; " + NEW, "nothing")
put("task-b1-f4-f7.md", "B1", 1, "0", 0, L, NONE, NEW, "nothing")
put("plan-32-instruction-architecture.md plan-32-tasks/retriage-2026-11-24.md", "I1", 2, "0", 0,
    L, NONE, "a plan and its accepted task list (L214, L226); no ceremony in either", "nothing")
put("plan-32-tasks/task-I1.a-contradiction-edits.md plan-32-tasks/task-I1.b-substrate.md "
    "plan-32-tasks/task-I1.b0-probes.md plan-32-tasks/task-I1.b1-units-and-check.md "
    "plan-32-tasks/task-I1.b2-marker-and-ledger.md plan-32-tasks/task-I1.b3-dispatcher.md",
    "I1", 2, "1 each large (= L165)", 0, L, NONE, NEW + " (L234)", "nothing")
put("plan-32-tasks/task-I1.c-first-denies.md plan-32-tasks/task-I1.d-first-skills.md", "I1", 2,
    "0", 0, L, NONE, "drafted in the L165 shape, out of the window (`92ec1050`); Q67-Q69 open",
    "nothing")
put("plan-10-injection-dedup.md", "I1 (10.3)", 2, "0", 0, C, RULE,
    "only 10.3 is pre-mod; 50 history lines, 1 of 4 history anchors linked", "nothing")
put("plan-10-injection-dedup-tasks/task-10.3-plan-10-injection-dedup.md", "I1 (10.3)", 2, "0", 0,
    L, NONE, "its RED is inside the window: I1.b2 builds it and carries its R4 point as D1, D2",
    "nothing")
put("task-agent-start-context.md", "I1.g", 2, "1 spec round", 0, R,
    "at I1.g's entry: one page, and the line 'a ch-bsd spec round precedes approval' goes",
    "`drafting`, 82 lines; L226 pulled it in and L165 gives a spec no ch-bsd round", "nothing")
put("plan-32-tasks/task-H1.a-reconcile-shipped-files.md", "H1", 3, "0 (small path)", 0, L, NONE,
    "132 lines, building (L237)", "nothing")
put("task-t0.9-test-isolation.md", "T0.9", 5, "0", 0, L, NONE,
    "226 lines, no history, 'no ch-bsd round' in its own header; (a) is dispatchable (L235). "
    "(b) to (d) are revised at their entry (audit: `stale (revise)`)", "nothing")
put("task-t0-suite-trust-sweep.md", "4", 6, "1 per sub-task, repeated until CLEAN (R0.8)", 2,
    C, "none; the ruling replaces R0.8's 'until CLEAN', R7.7's and `#done`'s 'round is CLEAN'",
    "one sub-task (T0.7) is left and the file closes at stage 5; 9 of its 44 history anchors "
    "are linked, so a trim would rewrite live text",
    "plans 6, 7, 8 and 15 close on one pass plus a confirm-lite, not on a CLEAN round")
put("plan-29-code-quality.md", "4, 6-8", 6, "0", 0, L, NONE, "194 lines, no history section",
    "nothing")
put("plan-29-code-quality-tasks/task-29.4-suite-health.md", "4, 8 (29.4f)", 6,
    "1 per sub-task range (R10)", 0, C, "none; R10's round is L165's one pass under the ruling",
    "stage 5 and 29.4f are what is left; 80 history lines", "nothing")
put("plan-31-pre-mod-loose-ends.md", "5, 9, 14", 7, "0", 0, L, NONE,
    "231 lines, no history, no round, no band", "nothing")
GATE = ("its product is a gate script outside `src/`, so the ruling as worded would drop its "
        "mutation rows: question P1b-Q2")
put("plan-31-pre-mod-loose-ends-tasks/task-31.3-ledger-anchor-guard.md", "5", 7, "0", 0, C, RULE,
    "approved on 2026-11-15 (L140); 23 history lines; " + GATE,
    "under the ruling without Q2's clause, a guard nobody proved can fail")
put("plan-31-pre-mod-loose-ends-tasks/task-31.4-retire-standing-warnings.md", "5", 7, "0", 0, C,
    RULE, "approved L140; 20 history lines; " + GATE, "as 31.3")
put("plan-31-pre-mod-loose-ends-tasks/task-31.1-frontmatter-type-refusal.md "
    "plan-31-pre-mod-loose-ends-tasks/task-31.6-one-wikilink-resolver.md", "5", 7, "0", 0, C, RULE,
    "approved L149; its length is requirements and `src/` mutations, which are never a cut",
    "nothing")
put("plan-29-code-quality-tasks/task-29.1-registry-triage.md", "6", 8, "0", 0, C, RULE,
    "docs and a checker; 87 history lines, 2 of 14 history anchors linked", "nothing")
put("plan-29-code-quality-tasks/task-29.5-split-giant-modules.md", "7", 9, "0", 26, R,
    "at row 7's entry: one page on the tree as it then is; G5's per-commit full suite goes to "
    "the user first (question P1b-Q1)",
    "audit: `stale (revise)` (line counts, `migrate-to-duckdb`, ADR 0006 unwritten); its 115 "
    "history lines are the only large history block with no inbound link",
    "a requirement lost in the compression: the entry rewrite is diffed AC by AC")
put("plan-29-code-quality-tasks/task-29.3-converge-shapes.md", "8", 10, "0", 4, C,
    "none by rule; AC-c7's full suite before and after each module group is question P1b-Q1",
    "37 `src/` mutations and 10 ACs are the load, and they stay", "nothing")
put("plan-29-code-quality-tasks/task-29.2-mypy-gate.md", "8", 10,
    "2 (R7 and R8 'as their own RED, GREEN, ch-bsd round', then the rest)", 2, C,
    "none by edit; the ruling makes it one pass over 29.2's whole range; AC-14's before/after "
    "suite is question P1b-Q1",
    "118 history lines, 6 of 9 history anchors linked",
    "R7's derive-hash change is reviewed with the annotation edits, not ahead of them")
put("plan-29-code-quality-tasks/task-29.6-citation-and-pin-repoint.md", "8", 10,
    "1 confirm-lite per track on re-pointed specs (4 pre-mod tracks)", 0, C,
    "none by edit; the ruling replaces the per-track confirm-lite with the owner's sign-off "
    "the same line already requires; " + GATE,
    "L165: no ch-bsd round on a spec", "a location-bound spec change is read by its owner only")
put("plan-31-pre-mod-loose-ends-tasks/task-31.2-learned-evidence-agreement.md", "9", 11, "0", 0,
    C, RULE, "approved L149; 34 `src/` mutations and 16 ACs are the load", "nothing")
put("plan-22-audited-removal-and-repair-tasks/task-22.6-removal-entry-points.md", "9 (R4 only)",
    11, "0", 0, C, RULE,
    "only R4 is pre-mod and 31.2 builds it; 14 of 16 history anchors are linked", "nothing")
put("plan-30-materialisation.md plan-30-materialisation-tasks/task-30.0-disk-tier-probe.md "
    "plan-30-materialisation-tasks/task-30.5-load-bitmap-row-read.md "
    "plan-30-materialisation-tasks/task-30.1-adjacency-mapping-adapter.md "
    "plan-30-materialisation-tasks/task-30.2-vectorised-adjacency-build.md "
    "plan-30-materialisation-tasks/task-30.3-disk-tier-fate.md "
    "plan-30-materialisation-tasks/task-30.4-daemon-adjacency-ppr-op.md", "10", 12, "0", 0, C,
    RULE, "written 2026-11-14 with one revision note each (6 to 40 history lines); no round, "
    "no band", "nothing")
put("task-dq1-operational-content-out-of-graph.md", "10 (G22)", 12, "0", 0, C, RULE,
    "83 history lines, 5 of 6 history anchors linked; `#queue-stale` points are RED's", "nothing")
put("task-bug216-denotes-fold-evaluation.md", "10 (G30, in 30.6)", 12,
    "1 over the report (`#done`)", 0, C,
    "none by edit; under the ruling the report gets the lead's read, or one pass if question "
    "P1b-Q3 says so", "a measurement with no `src/`", "a wrong reading of the fold bands")
T2 = ("held revision `3a4d430` is not on `master` yet (L231 (2)); history anchors are linked "
      "from live text")
put("plan-26-memory-organisation.md plan-27-memory-fleet-rollout.md", "11", 13, "0", 0, C, RULE,
    "112 / 103 history lines, 6 of 7 and 5 of 8 history anchors linked", "nothing")
put("plan-26-memory-organisation-tasks/task-26.5-memory-organise-verb.md", "11", 13, "0", 0, R,
    "at row 11's entry: one page from `3a4d430` plus the six `#queue-stale` points; its 17 "
    "revision sections (268 lines) go then",
    "audit: `stale (revise)`; P7, P9 and the 26.5 split are open", "as 29.5")
put("plan-26-memory-organisation-tasks/task-26.7-memory-index-by-subject.md "
    "plan-26-memory-organisation-tasks/task-26.8-refmatrix-live-rollout.md", "11", 13, "0", 0, R,
    "at entry: L226's amendments (ADR 0007 `#memory-index`; AC-8's MEMORY-RULES text, L222) "
    "written in, history dropped", "audit: `stale (revise)`; " + T2, "as 29.5")
put("plan-26-memory-organisation-tasks/task-26.6-compile-subject-hygiene.md "
    "plan-26-memory-organisation-tasks/task-26.9-impression-patterns.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.0-organise-merge-from.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.1-fleet-inventory.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.2a-index-prose-to-memories.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.2-viascope2-fold-and-repoint.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.3-thiquet-store-repoint.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.4-quiet-dir-migrations.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.5-cliquedb-at-session-boundary.md "
    "plan-27-memory-fleet-rollout-tasks/task-27.6-per-store-compile-and-landing.md", "11", 13,
    "0", 0, C, RULE, "78 to 261 lines each; no round, no band; `#queue-stale` points are RED's",
    "nothing")
put("plan-25-cliquedb-field-report.md", "12", 14, "0 pre-mod (25.1b's round is post-mod)", 0, C,
    RULE, "133 history lines, 6 of 8 history anchors linked", "nothing")
put("plan-25-cliquedb-field-report-tasks/task-25.3-stm-ref-admission-and-helix-repeat.md", "12",
    14, "0", 0, C, RULE, "audit: stale at RED only (`stm.pre_prompt_state`)", "nothing")
put("plan-25-cliquedb-field-report-tasks/task-25.2-thin-prompt-gate.md", "12", 14, "0", 0, R,
    "at entry: R0 reports guardrail-memory uses apart from the rest (L226, re-triage `#r12`)",
    "audit: `stale (revise)`", "as 29.5")
put("plan-23-bounded-write-harness.md", "13", 15, "0", 0, C, RULE,
    "293 of 514 lines are history, but 12 of 13 history anchors are linked and 9 AC ids and 9 R "
    "ids appear only there", "nothing")
put("task-bug185-bulk-gmd-ingest.md", "13", 15, "0", 0, R,
    "at row 13's entry: one page with the L136 / L144 / L145 notes and bug-309's measured "
    "holder written in; 294 history lines go then",
    "audit: `stale (revise)`; its R9 STOP bands and the 5 + 5 timing runs are measured bands "
    "and stay", "as 29.5")
put("plan-23-bounded-write-harness-tasks/task-23.1-queue-and-drain.md", "13", 15, "0", 0, R,
    "at entry: three one-page specs (23.1b, 23.1a, 23.1c, as decided), L183 / L184 written "
    "in, R11 re-based on C2's spool; 252 history lines go then",
    "audit: `stale (revise)`; the largest file on the queue (2,103 lines), and 21 ACs with 53 "
    "mutations cannot fit one page unsplit", "as 29.5; the split is where a requirement is lost")
put("plan-23-bounded-write-harness-tasks/task-23.2-lock-hold-fixture.md "
    "plan-23-bounded-write-harness-tasks/task-23.3-sync-between-file-yield.md "
    "plan-23-bounded-write-harness-tasks/task-23.5-read-path-and-holder-bounds.md", "13", 15, "0",
    0, C, RULE, "history anchors linked (5 of 5, 7 of 8, 7 of 8); `#queue-stale` points are RED's",
    "nothing")
put("task-bug218-reinforcement-edge-direction.md", "13", 15, "0", 0, R,
    "at entry: the held revision `b2e2451` merged on the lead's read (L231 (2)), then one page",
    "audit: `stale (revise)`", "as 29.5")
put("plan-31-pre-mod-loose-ends-tasks/task-31.5-scan-prompt-block-measure.md", "14", 16, "0", 0,
    R, "at row 14's entry, S2 only: the recall-channel cut after I1.h and the regime marks at "
    "each I1 install window (L226). S0b, S1 and the capture size stay as written",
    "audit: `stale (revise)` for S2; the 400-prompt capture and the 200 runs per arm are "
    "bands the user set", "as 29.5")
put("plan-21-agent-context-usage.md", "14, 15", 16, "0", 0, C, RULE,
    "183 of 327 lines are history with no inbound link, but 15 AC ids appear only there", "nothing")
put("plan-21-agent-context-usage-tasks/task-21.2-precise-identifier-context.md", "14", 16, "0", 0,
    C, RULE, "183 lines; its gold files are re-frozen at RED (`#queue-stale`)", "nothing")
put("plan-21-agent-context-usage-tasks/task-21.4-surfaces-and-nl-ranking.md", "14", 16, "0", 0, R,
    "at entry: R4 leaves for I1.h (L226); R1 to R3 on one page", "audit: `stale (revise)`",
    "as 29.5")
put("plan-21-agent-context-usage-tasks/task-21.5-tool-used-signal.md", "15", 17,
    "1 over the measurement, until CLEAN or MEH-only (`#done-m`)", 0, C,
    "none by edit; one pass with no repeat under the ruling (question P1b-Q3)",
    "phase M has no `src/`; phase B (most of the 1,783 lines) is frozen and post-mod",
    "the band reading feeds the charter decision on one review")
put("plan-24-mod-transport.md plan-24-mod-transport-tasks/task-24.0-hook-cost-baseline.md "
    "plan-24-mod-transport-tasks/task-24.1-store-runtime-identity.md", "16, 17", 18, "0", 0, R,
    "row 16 is the rewrite: the freshness revision, with no ch-bsd round (L226)",
    "audit: `needs-approval`; `drafting`, r7 fold never confirmed", "nothing beyond row 16's own")


def main() -> int:
    rows = list(csv.DictReader((HERE / "inventory.tsv").open(), delimiter="\t"))
    missing = [r["file"] for r in rows if r["file"] not in V]
    extra = [f for f in V if f not in {r["file"] for r in rows}]
    if missing or extra:
        print(f"MISMATCH missing={missing} extra={extra}", file=sys.stderr)
        return 1
    print("| row | file | lines | ACs | history (sections / lines) | rounds written | "
          "full-suite runs written | mutation rows (`src/` / other) | cost if followed | "
          "verdict | the cut | reason | at risk |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    tot = defaultdict(lambda: defaultdict(int))
    for r in rows:
        row, dist, rounds, runs, verdict, cut, reason, risk = V[r["file"]]
        other = int(r["mut_non_src"])
        cost = []
        if runs:
            cost.append(f"{runs} runs = {runs * SUITE_MIN} min sharded ({runs * SERIAL_MIN} serial)")
        if other:
            cost.append(f"{other} non-`src/` mutations = ~{other * MUT_MIN} min")
        if not rounds.startswith("0"):
            cost.append("rounds as written")
        name = r["file"].split("/")[-1]
        print(f"| {row} (+{dist}) | `{name}` | {r['lines']} | {r['acs']} | "
              f"{r['history_sections']} / {r['history_lines']} | {rounds} | {runs or '0'} | "
              f"{r['mut_src']} / {other} | {'; '.join(cost) or 'nothing beyond L165'} | "
              f"**{verdict}** | {cut} | {reason} | {risk} |")
        t = tot[verdict]
        t["files"] += 1
        t["lines"] += int(r["lines"])
        t["hist"] += int(r["history_lines"])
        t["runs"] += runs
        t["mut_other"] += other
        t["mut_src"] += int(r["mut_src"])
        t["acs"] += int(r["acs"])
    print()
    print("| verdict | files | lines | history lines | ACs | `src/` mutation rows | "
          "other mutation rows | full-suite runs written |")
    print("|---|---|---|---|---|---|---|---|")
    keys = ("files", "lines", "hist", "acs", "mut_src", "mut_other", "runs")
    for v in (L, T, R, C):
        t = tot[v]
        print(f"| {v} | " + " | ".join(str(t[k]) for k in keys) + " |")
    print("| **all** | " + " | ".join(str(sum(tot[v][k] for v in tot)) for k in keys) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
