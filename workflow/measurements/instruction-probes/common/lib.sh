# shared helpers, sourced by run.sh. Requires: claude, python3, git.
IP_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CC_VERSION=$(claude --version | awk '{print $1}')
WORKROOT=${PROBE_WORKROOT:-$HOME/agents/probes-b0/work}
BOUND=${PROBE_BOUND:-600}   # seconds per session (P5: 1800)
nonce() { printf '%s-%s' "$1" "$(LC_ALL=C tr -dc 'A-F0-9' </dev/urandom | head -c 8)"; }
newproj() { # newproj <name> -> sets P (fresh dir), PROBE_EV
  mkdir -p "$WORKROOT"; P=$(mktemp -d "$WORKROOT/$1.XXXXXX"); P=$(cd "$P" && pwd -P)
  git -C "$P" init -q; mkdir -p "$P/.claude/hooks"
  cp "$IP_DIR/common/log_hook.py" "$P/.claude/hooks/"; export PROBE_EV="$P/evidence.jsonl"; : > "$PROBE_EV"
}
settings() { python3 "$IP_DIR/common/settings_gen.py" "$P" "$1"; } # settings <spec.json>
ask() { # ask <prompt> [claude args...]: headless session in $P; sets SID, RES (result text file)
  local prompt=$1; shift
  ( cd "$P" && timeout "$BOUND" claude -p "$prompt" --setting-sources user,project \
      --output-format json --permission-mode "${PROBE_PERM:-acceptEdits}" "$@" ) > "$P/res.$$.json" 2> "$P/err.$$.txt"
  RC=$?
  SID=$(python3 -c "import json,sys;print(json.load(open('$P/res.$$.json')).get('session_id',''))" 2>/dev/null)
  python3 -c "import json;print(json.load(open('$P/res.$$.json')).get('result',''))" > "$P/res.txt" 2>/dev/null
  [ $RC -eq 0 ] || echo "ask: claude exit $RC (124 = past the ${BOUND}s bound)" >&2
}
seen() { grep -q -- "$1" "$P/res.txt" && echo yes || echo no; } # model repeated token?
where() { python3 "$IP_DIR/common/where.py" "$SID" "$@"; }       # transcript record kinds holding a token
summ() { # summarize evidence: per label+event: calls, agent_id present, key paths, tokens hit
  python3 - "$PROBE_EV" <<'PY'
import json,sys,collections
n=collections.Counter(); ag=collections.Counter(); keys={}; tok=collections.defaultdict(set); vals=collections.defaultdict(set)
for l in open(sys.argv[1]):
    r=json.loads(l); k=(r["label"]+(":"+r["form"] if r.get("form") else ""),r.get("event"))
    n[k]+=1; ag[k]+=bool(r.get("has_agent_id"))
    for e in r.get("keys",[]):
        keys.setdefault(k,set()).add(e["path"])
        for t in e.get("tokens",[]): tok[k].add(f'{e["path"]}~{t}')
        if "val" in e and e["path"].rsplit(".",1)[-1] in ("hook_event_name","tool_name","load_reason","memory_type","agent_type","source","trigger","subagent_type") or ("val" in e and e["path"] in ("tool_input.skill","tool_input.command","tool_input.name","tool_input.subagent_type")):
            vals[k].add(f'{e["path"]}={e["val"]}')
for k in sorted(n,key=str):
    print(f"[{k[0]} / {k[1]}] calls={n[k]} with_agent_id={ag[k]}")
    print("   keys:", ",".join(sorted(keys.get(k,[]))))
    if vals[k]: print("   vals:", "; ".join(sorted(vals[k])))
    if tok[k]: print("   token-in:", "; ".join(sorted(tok[k])))
if not n: print("(no hook records)")
PY
}
