#!/usr/bin/env python3
"""R0 PreCompact probe: does PreCompact hook stdout reach the agent?

Three headless invocations on ONE session id:
  1. a trivial prompt (creates the session; no probe hook fires on it);
  2. `/compact` on --resume (fires PreCompact with trigger=manual, then SessionStart
     source=compact);
  3. the marker question on --resume (what the post-compact agent can see).

Probe hooks (scratch project settings only):
  PreCompact   PC-small  500 chars  ascii
  PreCompact   PC-big    11000 chars ascii   (would show a preview if PreCompact were capped)
  SessionStart SS-postc  300 chars  ascii, matcher "compact" only (post-compaction delivery)

Evidence written to runs/<cell>.json: every hook attachment record, every api-request-blob
that contains a PC marker (which request — the summariser's or the agent's), the compact
boundary/summary records, and the model's reply to step 3.
"""
import json
import os
import secrets
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_cell as rc  # noqa: E402

HERE = rc.HERE


def blobs_with(tpath, needle):
    hits = []
    with open(tpath, encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            if needle not in line:
                continue
            r = json.loads(line)
            a = r.get("attachment") or {}
            hits.append({"line": n, "type": r.get("type"), "subtype": r.get("subtype"),
                         "attachment_type": a.get("type"), "hookEvent": a.get("hookEvent"),
                         "role": (r.get("message") or {}).get("role")
                         if isinstance(r.get("message"), dict) else None,
                         "len": len(line)})
    return hits


def main():
    cell = sys.argv[1] if len(sys.argv) > 1 else "p01-precompact"
    tag = secrets.token_hex(4)
    # argv[2:] = PreCompact hook specs LABEL:N:KIND (default: the p01 pair); "--instr" adds a
    # hook whose stdout asks the SUMMARISER to copy a token into the summary (tests whether
    # PreCompact stdout is fed to the compaction model, not only shown after it).
    specs = [a for a in sys.argv[2:] if a != "--instr"]
    instr = "--instr" in sys.argv[2:]
    hooks = [("PreCompact",) + (lambda l, n, k: (l, int(n), k))(*sp.split(":")) for sp in specs]
    if not hooks:
        hooks = [("PreCompact", "PC-small", 500, "ascii"), ("PreCompact", "PC-big", 11000, "ascii")]
    extra = []
    if instr:
        extra.append(("PreCompact", "echo 'Compaction instruction from a PreCompact hook: the summary "
                      f"MUST contain the literal token R0-SUMMARY-{tag} verbatim.'"))
    cfg = rc.settings_for(hooks, tag, extra)
    cfg["hooks"]["SessionStart"] = [{
        "matcher": "compact",
        "hooks": [{"type": "command",
                   "command": f"python3 {HERE}/payload.py SS-postc 300 ascii {tag}"}]}]
    with open(os.path.join(HERE, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=1)
    sid = str(uuid.uuid4())
    steps = []
    steps.append(("create", rc.run_claude("Reply with the single word: ready", sid)))
    steps.append(("compact", rc.run_claude("/compact", sid, resume=True)))
    steps.append(("ask", rc.run_claude(rc.PROMPT, sid, resume=True)))
    for name, run in steps:
        print(f"-- step {name}: rc={run['rc']} secs={run['secs']} stdout={run['stdout'][:300]!r} "
              f"stderr={run['stderr'][-300:]!r}")
    all_hooks = hooks + [("SessionStart", "SS-postc", 300, "ascii")]
    doc = rc.analyse(cell, all_hooks, tag, sid, steps[-1][1],
                     extra={"steps": [{"name": n, "rc": r["rc"], "secs": r["secs"],
                                       "argv": r["argv"], "stdout": r["stdout"][:4000],
                                       "stderr": r["stderr"][-2000:]} for n, r in steps]})
    tpath = doc["transcript"]
    marks = {}
    if tpath:
        for label in [h[1] for h in hooks] + ["SS-postc"]:
            for kind in ("START", "END"):
                m = f"R0-{kind}-{label}-{tag}"
                marks[m] = blobs_with(tpath, m)
        if instr:
            marks[f"R0-SUMMARY-{tag}"] = blobs_with(tpath, f"R0-SUMMARY-{tag}")
            with open(tpath, encoding="utf-8") as fh:
                summ = [json.loads(l) for l in fh if '"isCompactSummary":true' in l]
            doc["summary_has_instr_token"] = any(
                f"R0-SUMMARY-{tag}" in json.dumps(r) for r in summ)
            print("  summary record carries R0-SUMMARY token:", doc["summary_has_instr_token"])
    doc["marker_locations"] = marks
    with open(os.path.join(HERE, "runs", f"{cell}.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    rc.summarise(doc)
    for m, hits in marks.items():
        print("  marker", m, "->", [(h["type"], h["attachment_type"], h["hookEvent"]) for h in hits])


if __name__ == "__main__":
    main()
