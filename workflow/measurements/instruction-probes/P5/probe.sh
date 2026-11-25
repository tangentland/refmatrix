# P5: do PreCompact / SessionStart(compact) fire inside a subagent, with agent_id?
# Method: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE lowers the auto-compact threshold; the subagent reads files
# until ITS context compacts; the main session reads nothing large. A main-session compaction is told
# apart by the absence of agent_id. Control: the SubagentStart record (agent_id present) in the same run.
run_probe() {
  newproj P5; export PROBE_TOKENS=""; BOUND=${PROBE_BOUND:-1800}
  mkdir -p "$P/.claude/agents" "$P/big"
  printf -- '---\nname: p5agent\ndescription: probe agent p5 that reads large files\ntools: Read\n---\nYou are p5agent. Read every file you are told to, fully, one by one, then answer briefly.\n' > "$P/.claude/agents/p5agent.md"
  python3 - "$P/big" <<'PY'
import random,sys
random.seed(5)
w=["alpha","bravo","delta","echo","fox","golf","hotel","india","juliet","kilo","lima","mike","nov","oscar","papa","quebec"]
for i in range(8):
    open(f"{sys.argv[1]}/f{i}.txt","w").write("\n".join(" ".join(random.choice(w)+str(random.randint(0,999)) for _ in range(10)) for _ in range(1500)))
PY
  python3 - "$P" <<'PY'
import json,sys
ev="SessionStart PreCompact PostCompact SubagentStart SubagentStop".split()
json.dump({"hooks":[{"event":e,"label":e} for e in ev]},open(sys.argv[1]+"/spec.json","w"))
PY
  settings "$P/spec.json"
  CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=${PCT:-20} PROBE_FORM=sub ask "Use the Agent tool once: subagent_type p5agent, prompt: 'Read big/f0.txt, big/f1.txt, big/f2.txt, big/f3.txt, big/f4.txt, big/f5.txt, big/f6.txt, big/f7.txt each in full using the Read tool (paging with offset/limit as needed), one after another, then reply DONE with the number of files read.' Give me its reply."
  echo "[session] $SID  subagent transcript files: $(ls ~/.claude/projects/*/$SID/subagents 2>/dev/null | wc -l)"
  echo "compact-boundary records in subagent transcripts: $(grep -l 'compact_boundary' ~/.claude/projects/*/$SID/subagents/*.jsonl 2>/dev/null | wc -l); in main: $(grep -c 'compact_boundary' ~/.claude/projects/*/$SID.jsonl 2>/dev/null)"
}
