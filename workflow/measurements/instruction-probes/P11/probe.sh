# P11: does an agent's skills: preload deliver a project skill's body to a spawned agent?
# Control: a second agent WITHOUT skills: must NOT see the nonce (so a yes is the preload, not leakage).
run_probe() {
  newproj P11; S=$(nonce P11SKILL); export PROBE_TOKENS="$S"
  mkdir -p "$P/.claude/skills/p11skill" "$P/.claude/agents"
  printf -- '---\nname: p11skill\ndescription: probe skill p11\n---\nSkill body nonce %s\n' "$S" > "$P/.claude/skills/p11skill/SKILL.md"
  printf -- '---\nname: p11with\ndescription: probe agent p11 with preload\ntools: Read\nskills:\n  - p11skill\n---\nYou are p11with. Do what the task says, briefly.\n' > "$P/.claude/agents/p11with.md"
  printf -- '---\nname: p11without\ndescription: probe agent p11 without preload\ntools: Read\n---\nYou are p11without. Do what the task says, briefly.\n' > "$P/.claude/agents/p11without.md"
  echo '{"hooks":[{"event":"SubagentStart","label":"substart"}]}' > "$P/spec.json"; settings "$P/spec.json"
  Q="List every token starting P11SKILL visible anywhere in your context WITHOUT calling any tool, or NONE. Reply with just that."
  PROBE_FORM=fg-with ask "Use the Agent tool once: subagent_type p11with, prompt: '$Q' Give me its reply verbatim."
  echo "[fg, skills: preload] nonce seen by agent: $(seen "$S")"; where "$S" | head -12
  PROBE_FORM=fg-without ask "Use the Agent tool once: subagent_type p11without, prompt: '$Q' Give me its reply verbatim."
  echo "[fg, no skills:  CONTROL] nonce seen by agent: $(seen "$S")   (must be no)"
  PROBE_FORM=bg-with ask "Use the Agent tool once with run_in_background true: subagent_type p11with, prompt: '$Q' Wait for completion and give me its reply."
  echo "[bg, skills: preload] nonce seen: $(seen "$S")"
  PROBE_FORM=fork ask "Fork yourself once (forked subagent; reply FORK-UNAVAILABLE if unavailable) asking it: '$Q' (a fork has no skills: list; this is the fork form of the control). Give me its reply."
  echo "[fork] nonce seen: $(seen "$S")"
}
