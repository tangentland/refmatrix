#!/usr/bin/env python3
"""where.py <session_id> <token>...: for each transcript file of the session (main + subagents),
count records containing each token, by record type / attachment type / role. Prints counts only."""
import glob, json, os, sys, collections
sid, toks = sys.argv[1], sys.argv[2:]
home = os.path.expanduser("~/.claude/projects")
files = glob.glob(f"{home}/*/{sid}.jsonl") + glob.glob(f"{home}/*/{sid}/subagents/*.jsonl")
res = {}
for f in files:
    kind = "subagent" if "/subagents/" in f else "main"
    for line in open(f):
        for t in toks:
            if t in line:
                try: r = json.loads(line)
                except Exception: r = {}
                att = r.get("attachment", {}) if isinstance(r.get("attachment"), dict) else {}
                key = f"{kind}:{r.get('type')}:{att.get('type','-')}:{(r.get('message') or {}).get('role','-')}"
                res.setdefault(t, collections.Counter())[key] += 1
print(json.dumps({t: dict(c) for t, c in res.items()}, indent=1, sort_keys=True) if res else "{}")
print("files:", len(files))
