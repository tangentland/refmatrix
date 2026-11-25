# Pteam: the TEAMMATE form for P3, P9 and P11 (experimental agent teams). One attempt, bound 10 min.
# Records which hooks fire for a teammate, with which fields (agent_id? team fields?), and whether the
# path rule (P3), the SubagentStart nonce (P9) and an agent's skills: preload (P11) reach it.
run_probe() {
  newproj Pteam; R=$(nonce PTRULE); N=$(nonce PTCTX); S=$(nonce PTSKILL); export PROBE_TOKENS="$R,$N,$S"
  mkdir -p "$P/.claude/rules" "$P/.claude/skills/ptskill" "$P/.claude/agents" "$P/ptdir"
  printf -- '---\npaths:\n  - "ptdir/**"\n---\nRule nonce %s\n' "$R" > "$P/.claude/rules/ptrule.md"
  printf -- '---\nname: ptskill\ndescription: probe skill pt\n---\nSkill body nonce %s\n' "$S" > "$P/.claude/skills/ptskill/SKILL.md"
  printf -- '---\nname: ptagent\ndescription: probe agent pt\ntools: Read\nskills:\n  - ptskill\n---\nYou are ptagent. Do what the task says, briefly.\n' > "$P/.claude/agents/ptagent.md"
  echo t > "$P/ptdir/t.txt"
  python3 - "$P" "$N" <<'PY'
import json,sys
ev="SessionStart SubagentStart SubagentStop InstructionsLoaded PreToolUse TeammateIdle TaskCreated TaskCompleted".split()
hk=[{"event":e,"label":e} for e in ev]
for h in hk:
    if h["event"]=="SubagentStart": h["out"]=json.dumps({"hookSpecificOutput":{"hookEventName":"SubagentStart","additionalContext":sys.argv[2]}})
json.dump({"hooks":hk},open(sys.argv[1]+"/spec.json","w"))
PY
  settings "$P/spec.json"
  CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 PROBE_FORM=team ask "Create an agent team with exactly one teammate that uses the ptagent definition. Its task: Read ptdir/t.txt, then report every token starting PTRULE, PTCTX or PTSKILL visible anywhere in its context without calling other tools, or NONE. Wait for the teammate, relay its report, then clean up the team. If agent teams are unavailable reply TEAMS-UNAVAILABLE."
  echo "[teammate] reply head: $(head -c 400 "$P/res.txt" | tr '\n' ' ')"
  echo "path rule nonce: $(seen "$R")  SubagentStart nonce: $(seen "$N")  skills: preload nonce: $(seen "$S")"
}
