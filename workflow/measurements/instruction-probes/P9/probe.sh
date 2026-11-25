# P9: SubagentStart envelope (is the task prompt there?) and does additionalContext reach the agent?
# Control: the same SubagentStart hook's nonce is what the agent must repeat (if it does, delivery works;
# the control for "envelope has no prompt" is the PreToolUse envelope of the Agent call, which does).
run_probe() {
  newproj P9; N=$(nonce P9CTX); T=$(nonce P9TASK); export PROBE_TOKENS="$N,$T"
  mkdir -p "$P/.claude/agents"
  printf -- '---\nname: p9agent\ndescription: probe agent p9\ntools: Read\n---\nYou are p9agent. Do what the task says, briefly.\n' > "$P/.claude/agents/p9agent.md"
  cat > "$P/spec.json" <<J
{"hooks":[
 {"event":"SubagentStart","label":"substart","out":"{\"hookSpecificOutput\":{\"hookEventName\":\"SubagentStart\",\"additionalContext\":\"$N\"}}"},
 {"event":"PreToolUse","matcher":"Agent","label":"agent-call-control"},
 {"event":"PreToolUse","matcher":"Task","label":"task-call-control"}]}
J
  settings "$P/spec.json"
  PROBE_FORM=fg ask "Use the Agent tool once: subagent_type p9agent, prompt: 'Task token $T. List every token starting P9CTX visible anywhere in your context, or NONE. Reply with just that.' Give me its reply verbatim."
  echo "[fg] nonce reached subagent (model relayed): $(seen "$N")"; where "$N" | head -20
  PROBE_FORM=bg ask "Use the Agent tool once with run_in_background true: subagent_type p9agent, prompt: 'Task token $T. List every token starting P9CTX visible in your context, or NONE.' Wait for completion and give me its reply."
  echo "[bg] nonce relayed: $(seen "$N")"
  PROBE_FORM=fork ask "Fork yourself once (forked subagent; if unavailable reply FORK-UNAVAILABLE). Fork task token $T: list every token starting P9CTX visible in the fork's context, or NONE. Give me its reply."
  echo "[fork] nonce relayed: $(seen "$N")"
}
