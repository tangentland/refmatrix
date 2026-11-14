#!/usr/bin/env python3
"""Render the R0 per-cell table (markdown) from runs/*.json, plus session count and cost."""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def fmt_body(m):
    if not m:
        return ""
    return f"{m['utf16_units']:,} u16 / {m['utf8_bytes']:,} B"


def main():
    docs = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(f"{HERE}/runs/*.json"))]
    cost = 0.0
    sessions = 0
    invocations = 0
    print("| cell | event | hooks x size (kind) | this hook: code points / UTF-16 units / UTF-8 B "
          "| event total UTF-16 / B | transcript | API request | preview body | model saw END |")
    print("|---|---|---|---|---|---|---|---|---|")
    for d in docs:
        sessions += 1
        steps = (d.get("extra") or {}).get("steps")
        if steps:
            invocations += len(steps)
            for s in steps:
                try:
                    cost += json.loads(s["stdout"]).get("total_cost_usd") or 0
                except (json.JSONDecodeError, TypeError):
                    pass
        else:
            invocations += 1
            cost += (d.get("result") or {}).get("total_cost_usd") or 0
        by_ev = {}
        for r in d["rows"]:
            by_ev.setdefault(r["event"], []).append(r)
        for ev, rows in by_ev.items():
            tot16 = sum((r.get("emitted") or {}).get("utf16_units", 0) for r in rows)
            totb = sum((r.get("emitted") or {}).get("utf8_bytes", 0) for r in rows)
            sizes = {}
            for r in rows:
                sizes.setdefault((r["n_codepoints"], r["kind"]), 0)
                sizes[(r["n_codepoints"], r["kind"])] += 1
            shape = " + ".join(f"{c}x{n:,} ({k})" for (n, k), c in sizes.items())
            for r in rows:
                e = r.get("emitted") or {}
                if r.get("api_in_persisted_block"):
                    api = "PREVIEWED"
                elif r.get("api_start") and r.get("api_end"):
                    api = "whole"
                elif r.get("api_start"):
                    api = "CUT (head kept)"
                else:
                    api = "absent"
                if r.get("records"):
                    tr = "previewed" if r.get("previewed") else ("whole" if r.get("whole") else "?")
                elif r["event"] == "PreCompact":
                    tr = "in /compact stdout msg"
                else:
                    tr = "additionalContext rec"
                body = fmt_body(r.get("api_preview_body"))
                print(f"| {d['cell']} | {ev} | {shape} | {r['label']}: "
                      f"{e.get('codepoints', 0):,} / {e.get('utf16_units', 0):,} / "
                      f"{e.get('utf8_bytes', 0):,} | {tot16:,} / {totb:,} | {tr} | {api} | {body} "
                      f"| {r.get('model_end')} |")
    print(f"\nsessions={sessions} claude-invocations={invocations} total_cost_usd={cost:.4f}")


if __name__ == "__main__":
    main()
