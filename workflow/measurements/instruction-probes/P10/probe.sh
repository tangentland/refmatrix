# P10: a throwaway local plugin (--plugin-dir) with one agent + one skill. How are they named, and may a
# PROJECT agent's skills: name the plugin's skill (namespaced p10plug:p10skill, or bare p10skill)?
run_probe() {
  newproj P10; S=$(nonce P10SKILL); export PROBE_TOKENS="$S"
  PL="$P/plugin-src"; mkdir -p "$PL/.claude-plugin" "$PL/agents" "$PL/skills/p10skill" "$P/.claude/agents"
  printf '{"name":"p10plug","version":"0.0.1","description":"probe plugin p10"}\n' > "$PL/.claude-plugin/plugin.json"
  printf -- '---\nname: p10agent\ndescription: probe plugin agent p10\ntools: Read\n---\nYou are p10agent. Do what the task says, briefly.\n' > "$PL/agents/p10agent.md"
  printf -- '---\nname: p10skill\ndescription: probe plugin skill p10\n---\nPlugin skill body nonce %s\n' "$S" > "$PL/skills/p10skill/SKILL.md"
  printf -- '---\nname: p10nsagent\ndescription: project agent preloading the NAMESPACED plugin skill\ntools: Read\nskills:\n  - p10plug:p10skill\n---\nYou are p10nsagent. Do what the task says, briefly.\n' > "$P/.claude/agents/p10nsagent.md"
  printf -- '---\nname: p10bareagent\ndescription: project agent preloading the BARE plugin skill name\ntools: Read\nskills:\n  - p10skill\n---\nYou are p10bareagent. Do what the task says, briefly.\n' > "$P/.claude/agents/p10bareagent.md"
  cat > "$P/spec.json" <<J
{"hooks":[{"event":"SubagentStart","label":"substart"},{"event":"PreToolUse","matcher":"Skill","label":"skill-call"},{"event":"PreToolUse","matcher":"Agent","label":"agent-call"}]}
J
  settings "$P/spec.json"
  Q="List every token starting P10SKILL visible anywhere in your context WITHOUT calling any tool, or NONE. Reply with just that."
  PROBE_FORM=ns-agent ask "Use the Agent tool once: subagent_type p10plug:p10agent (if that name is rejected try p10agent), prompt: 'Reply READY.' Tell me which exact subagent_type name was accepted." --plugin-dir "$PL"
  echo "[plugin agent] reply: $(head -c 300 "$P/res.txt" | tr '\n' ' ')"
  PROBE_FORM=ns-skill ask "Call the Skill tool with skill p10plug:p10skill (if rejected try p10skill). Tell me which exact name was accepted and repeat any token starting P10SKILL." --plugin-dir "$PL"
  echo "[plugin skill via Skill tool] nonce: $(seen "$S")  reply: $(head -c 300 "$P/res.txt" | tr '\n' ' ')"
  PROBE_FORM=preload-ns ask "Use the Agent tool once: subagent_type p10nsagent, prompt: '$Q' Give me its reply verbatim." --plugin-dir "$PL"
  echo "[project agent skills: p10plug:p10skill] nonce seen by agent: $(seen "$S")"
  PROBE_FORM=preload-bare ask "Use the Agent tool once: subagent_type p10bareagent, prompt: '$Q' Give me its reply verbatim." --plugin-dir "$PL"
  echo "[project agent skills: p10skill (bare)] nonce seen by agent: $(seen "$S")"
}
