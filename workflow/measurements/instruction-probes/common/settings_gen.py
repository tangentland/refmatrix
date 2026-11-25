#!/usr/bin/env python3
"""settings_gen.py <project> <spec.json>: write <project>/.claude/settings.json.
spec: {"hooks":[{"event":..,"matcher":..,"label":..,"out":..|null,"out_if_token":[tok,json]|null,"if":..|null}], "extra":{}}
Each hook runs python3 <project>/.claude/hooks/log_hook.py <label> ..., env PROBE_EV / PROBE_TOKENS from the shell env."""
import json, shlex, sys, pathlib
proj = pathlib.Path(sys.argv[1]); spec = json.load(open(sys.argv[2]))
hk = {}
for h in spec["hooks"]:
    cmd = f"python3 {shlex.quote(str(proj/'.claude/hooks/log_hook.py'))} {shlex.quote(h['label'])}"
    if h.get("out"): cmd += f" --out {shlex.quote(h['out'])}"
    if h.get("out_if_token"): cmd += " --out-if-token " + " ".join(shlex.quote(x) for x in h["out_if_token"])
    ent = {"type": "command", "command": cmd}
    if h.get("if"): ent["if"] = h["if"]
    g = {"hooks": [ent]}
    if h.get("matcher") is not None: g["matcher"] = h["matcher"]
    hk.setdefault(h["event"], []).append(g)
s = {"hooks": hk}; s.update(spec.get("extra", {}))
(proj/".claude").mkdir(parents=True, exist_ok=True)
(proj/".claude/settings.json").write_text(json.dumps(s, indent=1))
