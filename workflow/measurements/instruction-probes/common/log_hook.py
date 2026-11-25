#!/usr/bin/env python3
"""Probe hook: append one evidence record per hook call. AC-3: key paths, types, lengths,
sha256[:12] only; a raw value is written ONLY for (a) a whitelisted enum key, (b) a synthetic
probe name (^p\\d+... / probe...), (c) a nonce/token the probe declared in PROBE_TOKENS.
usage: log_hook.py <label> [--out JSON] [--out-if-token TOKEN JSON]
env: PROBE_EV (evidence file), PROBE_TOKENS (comma list)"""
import hashlib, json, os, re, sys
ENUM = {"hook_event_name", "tool_name", "load_reason", "memory_type", "source", "agent_type",
        "permission_mode", "trigger", "reason", "matcher", "type", "subagent_type"}
SYN = re.compile(r"^(p\d+|probe)[\w:.\-]*$", re.I)
def walk(v, path, out, toks, depth=0):
    if isinstance(v, dict):
        for k, x in v.items():
            walk(x, f"{path}.{k}" if path else k, out, toks, depth + 1)
    elif isinstance(v, list):
        out.append({"path": path, "type": "list", "len": len(v)})
        for i, x in enumerate(v[:5]):
            walk(x, f"{path}[]", out, toks, depth + 1)
    else:
        s = v if isinstance(v, str) else json.dumps(v)
        e = {"path": path, "type": type(v).__name__, "len": len(s),
             "sha": hashlib.sha256(s.encode()).hexdigest()[:12]}
        leaf = path.rsplit(".", 1)[-1]
        hit = [t for t in toks if t and t in s]
        if hit: e["tokens"] = hit
        if isinstance(v, str) and (leaf in ENUM or SYN.match(s)) and len(s) <= 60: e["val"] = s
        out.append(e)
def main():
    label = sys.argv[1]
    raw = sys.stdin.read()
    toks = os.environ.get("PROBE_TOKENS", "").split(",")
    try: env = json.loads(raw)
    except Exception: env = None
    rec = {"label": label, "form": os.environ.get("PROBE_FORM", ""), "bytes": len(raw), "parse": env is not None}
    if isinstance(env, dict):
        leaves = []; walk(env, "", leaves, toks)
        rec["event"] = env.get("hook_event_name")
        rec["has_agent_id"] = "agent_id" in env
        rec["keys"] = leaves
    with open(os.environ["PROBE_EV"], "a") as f: f.write(json.dumps(rec) + "\n")
    a = sys.argv[2:]
    if a[:1] == ["--out"]: print(a[1])
    elif a[:1] == ["--out-if-token"] and a[1] in raw: print(a[2])
main()
