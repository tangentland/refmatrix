# P6: skill `paths:`: does a matching file touch load the skill BODY, or only change the listing?
# Control: a path rule with the same paths: delivers its own nonce on the same touch (verified mechanism).
run_probe() {
  newproj P6; R=$(nonce P6RULE); S=$(nonce P6SKILL); export PROBE_TOKENS="$R,$S"
  mkdir -p "$P/.claude/rules" "$P/.claude/skills/p6skill" "$P/.claude/agents" "$P/p6dir"
  printf -- '---\npaths:\n  - "p6dir/**"\n---\nRule nonce %s\n' "$R" > "$P/.claude/rules/p6rule.md"
  printf -- '---\nname: p6skill\ndescription: probe skill p6 for files under p6dir\npaths:\n  - "p6dir/**"\n---\nSkill body nonce %s\n' "$S" > "$P/.claude/skills/p6skill/SKILL.md"
  printf -- '---\nname: p6agent\ndescription: probe agent p6\ntools: Read\n---\nYou are p6agent. Do what the task says, briefly.\n' > "$P/.claude/agents/p6agent.md"
  echo m > "$P/p6dir/main.txt"; echo s > "$P/p6dir/sub.txt"
  cat > "$P/spec.json" <<J
{"hooks":[{"event":"InstructionsLoaded","label":"loaded"},{"event":"SubagentStart","label":"substart"}]}
J
  settings "$P/spec.json"
  PROBE_FORM=main ask "Read p6dir/main.txt. Do NOT call the Skill tool. Then report every token starting P6RULE or P6SKILL you can see anywhere in your context (reminders, rules, skill text), separately, or NONE."
  M=$SID; echo "[main] rule nonce (control) repeated: $(seen "$R")   skill body nonce repeated: $(seen "$S")"; where "$R" "$S"
  PROBE_FORM=sub ask "Use the Agent tool once, subagent_type p6agent, prompt: 'Read p6dir/sub.txt. Do NOT call the Skill tool. Report every token starting P6RULE or P6SKILL visible anywhere in your context, or NONE.' Give me its report verbatim."
  echo "[subagent] rule nonce (control) repeated: $(seen "$R")   skill body nonce repeated: $(seen "$S")"; where "$R" "$S"
}
