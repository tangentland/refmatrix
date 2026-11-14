#!/usr/bin/env python3
"""R0 probe runner: one headless Claude Code session per cell.

Usage:
    python3 run_cell.py <cell-name> <hookspec> [<hookspec> ...]
    hookspec = EVENT:LABEL:N:KIND     e.g. UserPromptSubmit:UPS-a9000:9000:ascii

For the cell it (1) writes .claude/settings.json in this scratch project with one matcher group
per probe hook (production shape: rmx generates one group per command), (2) runs
`claude -p` with ONLY project settings (`--setting-sources project`), no tools, haiku, a fixed
--session-id, and the parent session's CLAUDE*/messaging env stripped, (3) reads the session
transcript JSONL (read-only) for the hook attachment records, (4) parses the model's JSON reply,
and (5) writes runs/<cell>.json and appends one row per probe hook to runs/results.jsonl.

Transcript evidence is primary: an attachment whose `content` starts with `<persisted-output>`
was previewed; one whose `content` equals the emitted stdout was delivered whole.
"""
import glob
import json
import os
import re
import secrets
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
STRIP_ENV = [
    "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID",
    "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_EXECPATH",
    "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_EFFORT", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    "CLAUDE_CODE_ENTRYPOINT",
]
PROMPT = (
    "Do not use any tools. Before this message, hooks injected text into your context. Some "
    "injected lines begin with the prefix R0-START- or R0-END-. Reply with ONLY one JSON object, "
    "no prose and no code fence: {\"start_lines\": [each line in your context that begins with "
    "R0-START-, copied exactly], \"end_lines\": [each line that begins with R0-END-, copied "
    "exactly], \"saved_to\": [every file path that any injected text says output was saved to; "
    "an empty list if none]}. This message itself does not count."
)


def settings_for(hooks, tag, extra_cmds=None):
    cfg = {}
    for ev, label, n, kind in hooks:
        k = kind.split("+")[0]
        cmd = f"python3 {HERE}/payload.py {label} {n} {k} {tag}"
        cmd += " 1" if "+nl" in kind else ""
        cmd += " --json" if "+json" in kind else ""
        group = {"hooks": [{"type": "command", "command": cmd, "timeout": 30}]}
        if ev == "SessionStart":
            group["matcher"] = "startup|resume|clear|compact"
        cfg.setdefault(ev, []).append(group)
    for ev, cmd in (extra_cmds or []):
        cfg.setdefault(ev, []).append({"hooks": [{"type": "command", "command": cmd}]})
    return {"hooks": cfg}


def run_claude(prompt, session_id, resume=False, extra_args=()):
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
    argv = ["claude", "-p", prompt, "--model", "haiku", "--setting-sources", "project",
            "--tools", "", "--output-format", "json", "--strict-mcp-config",
            "--effort", "low", "--max-budget-usd", "0.50"]
    argv += (["--resume", session_id] if resume else ["--session-id", session_id])
    argv += list(extra_args)
    t0 = time.time()
    p = subprocess.run(argv, cwd=HERE, env=env, capture_output=True, text=True, timeout=300,
                       stdin=subprocess.DEVNULL)
    return {"argv": argv, "rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
            "secs": round(time.time() - t0, 1)}


def transcript_path(session_id):
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    return hits[0] if hits else None


def preview_parts(content):
    """Split a <persisted-output> block into header size text and preview body."""
    m = re.search(r"Output too large \(([^)]*)\)", content)
    body = None
    if "Preview (first 2KB):\n" in content:
        body = content.split("Preview (first 2KB):\n", 1)[1]
        body = re.sub(r"\n\.\.\.\n</persisted-output>\s*$", "", body)
    return (m.group(1) if m else None), body


def hook_records(tpath):
    recs = []
    if not tpath:
        return recs
    with open(tpath, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") == "attachment":
                a = r.get("attachment") or {}
                if a.get("hookEvent") or str(a.get("type", "")).startswith("hook"):
                    recs.append(a)
            elif r.get("type") == "system" and "compact" in json.dumps(r)[:400]:
                recs.append({"type": "system-record", "subtype": r.get("subtype"),
                             "content": str(r.get("content"))[:300]})
    return recs


def api_text(tpath):
    """All text the session SENT to the API (the `api-request-blob` records hold the request
    messages verbatim). This is what the model actually received."""
    parts = []
    if not tpath:
        return ""
    with open(tpath, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") != "api-request-blob":
                continue
            c = (r.get("message") or {}).get("content")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                for b in c:
                    if isinstance(b, dict):
                        parts.append(str(b.get("text") or b.get("content") or ""))
    return "\n".join(parts)


def api_verdict(api, start, end):
    """Per hook: did the start / end marker reach the API, and inside a persisted-output block?"""
    i = api.find(start)
    v = {"api_start": i >= 0, "api_end": end in api, "api_in_persisted_block": False}
    if i >= 0:
        o = api.rfind("<persisted-output>", 0, i)
        c = api.rfind("</persisted-output>", 0, i)
        if o >= 0 and o > c:
            close = api.find("</persisted-output>", i)
            block = api[o:close + len("</persisted-output>")] if close >= 0 else api[o:]
            v["api_in_persisted_block"] = True
            v["api_block"] = measure(block)
            size, body = preview_parts(block)
            v["api_header_size"] = size
            v["api_preview_body"] = measure(body) if body is not None else None
        elif end in api:
            v["api_segment"] = measure(api[i:api.find(end, i) + len(end)])
    return v


def measure(s):
    s = s or ""
    return {"codepoints": len(s), "utf16_units": len(s.encode("utf-16-le")) // 2,
            "utf8_bytes": len(s.encode("utf-8"))}


def parse_reply(stdout):
    try:
        out = json.loads(stdout)
    except json.JSONDecodeError:
        return None, None
    res = out.get("result") or ""
    m = re.search(r"\{.*\}", res, re.S)
    reply = None
    if m:
        try:
            reply = json.loads(m.group(0))
        except json.JSONDecodeError:
            reply = None
    return out, reply


def analyse(cell, hooks, tag, session_id, run, extra=None):
    tpath = transcript_path(session_id)
    recs = hook_records(tpath)
    api = api_text(tpath)
    out, reply = parse_reply(run["stdout"])
    emitted = []
    with open(os.path.join(HERE, "logs", "emitted.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            e = json.loads(line)
            if e["tag"] == tag:
                emitted.append(e)
    rows = []
    for ev, label, n, kind in hooks:
        start, end = f"R0-START-{label}-{tag}", f"R0-END-{label}-{tag}"
        mine = [a for a in recs if start in (a.get("stdout") or "")]
        em = [e for e in emitted if e["label"] == label]
        row = {"cell": cell, "event": ev, "label": label, "n_codepoints": n, "kind": kind,
               "tag": tag, "session_id": session_id, "emitted_count": len(em),
               "emitted": em[0] if em else None, "records": len(mine)}
        if mine:
            a = mine[0]
            content = a.get("content") or ""
            row["record_type"] = a.get("type")
            row["stdout_recv"] = measure(a.get("stdout"))
            row["content"] = measure(content)
            row["previewed"] = content.startswith("<persisted-output>")
            row["whole"] = (not row["previewed"]) and start in content and end in content
            if row["previewed"]:
                size, body = preview_parts(content)
                row["preview_header_size"] = size
                row["preview_body"] = measure(body) if body is not None else None
                row["preview_has_start"] = start in content
                row["preview_has_end"] = end in content
        row.update(api_verdict(api, start, end))
        if reply is not None:
            sl = reply.get("start_lines") or []
            el = reply.get("end_lines") or []
            row["model_start"] = any(start in str(x) for x in sl)
            row["model_end"] = any(end in str(x) for x in el)
            row["model_saved_to"] = reply.get("saved_to")
        rows.append(row)
    noise = [{"type": a.get("type"), "hookEvent": a.get("hookEvent"),
              "hookName": a.get("hookName"), "command": (a.get("command") or "")[:120],
              "stdout": measure(a.get("stdout")),
              "content_head": str(a.get("content"))[:160]}
             for a in recs if "R0-START-" not in (a.get("stdout") or "")]
    doc = {"cell": cell, "tag": tag, "session_id": session_id, "transcript": tpath,
           "run": {k: run[k] for k in ("argv", "rc", "secs", "stderr")},
           "result": out, "reply": reply, "rows": rows, "other_hook_records": noise,
           "extra": extra}
    with open(os.path.join(HERE, "runs", f"{cell}.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    with open(os.path.join(HERE, "runs", "results.jsonl"), "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return doc


def summarise(doc):
    print(f"== {doc['cell']} rc={doc['run']['rc']} secs={doc['run']['secs']} "
          f"cost={((doc.get('result') or {}).get('total_cost_usd'))} transcript={bool(doc['transcript'])}")
    if doc["run"]["rc"] != 0:
        print("stderr:", doc["run"]["stderr"][-800:])
        print("result:", json.dumps(doc.get("result"))[:800])
    for r in doc["rows"]:
        print(f"  {r['label']:<16} n={r['n_codepoints']:<6} recs={r['records']} "
              f"emit={r['emitted_count']} "
              f"bytes={(r.get('emitted') or {}).get('utf8_bytes')} "
              f"u16={(r.get('emitted') or {}).get('utf16_units')} "
              f"whole={r.get('whole')} previewed={r.get('previewed')} "
              f"hdr={r.get('preview_header_size')} body={r.get('preview_body')} "
              f"model_start={r.get('model_start')} model_end={r.get('model_end')} "
              f"saved_to={'Y' if r.get('model_saved_to') else 'N'} | API start={r.get('api_start')} "
              f"end={r.get('api_end')} persisted={r.get('api_in_persisted_block')} "
              f"seg={(r.get('api_segment') or {}).get('codepoints')} "
              f"block={(r.get('api_block') or {}).get('codepoints')} "
              f"apibody={r.get('api_preview_body')}")
    for o in doc["other_hook_records"]:
        print("  other:", json.dumps(o)[:260])


def reanalyse(cell):
    """Re-derive a cell's rows from its saved run (no new session)."""
    with open(os.path.join(HERE, "runs", f"{cell}.json"), encoding="utf-8") as fh:
        old = json.load(fh)
    hooks = [(r["event"], r["label"], r["n_codepoints"], r["kind"]) for r in old["rows"]]
    run = dict(old["run"])
    run["stdout"] = json.dumps(old["result"]) if old.get("result") else ""
    doc = analyse(cell, hooks, old["tag"], old["session_id"], run, extra=old.get("extra"))
    summarise(doc)


def main():
    if sys.argv[1] == "--reanalyse":
        for c in sys.argv[2:]:
            reanalyse(c)
        return
    cell = sys.argv[1]
    hooks = []
    for spec in sys.argv[2:]:
        ev, label, n, kind = spec.split(":")
        hooks.append((ev, label, int(n), kind))
    tag = secrets.token_hex(4)
    with open(os.path.join(HERE, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
        json.dump(settings_for(hooks, tag), fh, indent=1)
    sid = str(uuid.uuid4())
    run = run_claude(PROMPT, sid)
    doc = analyse(cell, hooks, tag, sid, run)
    summarise(doc)


if __name__ == "__main__":
    main()
