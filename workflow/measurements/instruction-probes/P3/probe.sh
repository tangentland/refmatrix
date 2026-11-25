# P3: InstructionsLoaded in main session and subagent: CLAUDE.md, a path rule, a skill.
# Forms: foreground subagent, background subagent, forked agent, teammate (each tried; see summary).
run_probe() {
  newproj P3; C=$(nonce P3CTL); R=$(nonce P3RULE); S=$(nonce P3SKILL); export PROBE_TOKENS="$C,$R,$S"
  mkdir -p "$P/.claude/rules" "$P/.claude/skills/p3skill" "$P/.claude/agents" "$P/p3dir"
  printf 'p3 project memory\n' > "$P/CLAUDE.md"
  printf -- '---\npaths:\n  - "p3dir/**"\n---\nRule nonce %s\n' "$R" > "$P/.claude/rules/p3rule.md"
  printf -- '---\nname: p3skill\ndescription: probe skill p3, invoke when asked\n---\nSkill body nonce %s\n' "$S" > "$P/.claude/skills/p3skill/SKILL.md"
  printf -- '---\nname: p3agent\ndescription: probe agent p3\ntools: Read, Skill, Bash\n---\nYou are p3agent. Do what the task says, briefly.\n' > "$P/.claude/agents/p3agent.md"
  echo a > "$P/p3dir/a.txt"; echo b > "$P/p3dir/b.txt"; echo c > "$P/p3dir/c.txt"; echo d > "$P/p3dir/d.txt"
  cat > "$P/spec.json" <<J
{"hooks":[
 {"event":"InstructionsLoaded","label":"loaded"},
 {"event":"SubagentStart","label":"substart"},
 {"event":"PreToolUse","matcher":"Bash","label":"control-deny","out_if_token":["p3control","{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$C\"}}"]}]}
J
  settings "$P/spec.json"
  PROBE_FORM=main ask "In the main session (no subagent) do, in order: Read p3dir/a.txt; call the Skill tool with skill p3skill; run Bash 'echo p3control'. Then report any token starting P3RULE, P3SKILL or P3CTL you saw." 
  echo "[main] control(deny nonce) repeated: $(seen "$C")"
  PROBE_FORM=fg ask "Use the Agent tool once with subagent_type p3agent and prompt: 'Read p3dir/b.txt, then call the Skill tool with skill p3skill. Report any token starting P3RULE or P3SKILL you saw.' Wait for it and give me its report verbatim."
  echo "[fg subagent] rule nonce seen by model: $(seen "$R")  skill nonce: $(seen "$S")"; SID_FG=$SID
  PROBE_FORM=bg ask "Use the Agent tool once with subagent_type p3agent and run_in_background true, prompt: 'Read p3dir/c.txt, then call the Skill tool with skill p3skill. Report tokens starting P3RULE or P3SKILL you saw.' Wait for its completion notification and give me its report."
  echo "[bg subagent] rule nonce: $(seen "$R")"
  PROBE_FORM=fork ask "Fork yourself once (a forked subagent that inherits this conversation, subagent_type fork if offered; if forking is unavailable say FORK-UNAVAILABLE) to: Read p3dir/d.txt then report tokens starting P3RULE you saw. Give me its report." 
  echo "[fork] result head: $(head -c 200 "$P/res.txt" | tr '\n' ' ')"
  SID=$SID_FG; echo "fg-session transcript records per nonce:"; where "$R" "$S"
}
