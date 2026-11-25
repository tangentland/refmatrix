# P1b (P1's prompting half) — INTERACTIVE, for the lead. Builds the project and prints the steps; nothing is run.
run_probe() {
  newproj P1b; N=$(nonce P1BCTX); C=$(nonce P1BCTL); export PROBE_TOKENS="$N,$C"; MODE="interactive (lead)"
  cat > "$P/spec.json" <<J
{"hooks":[
 {"event":"PreToolUse","matcher":"Bash","label":"ctx-only","out_if_token":["p1bprompt","{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"additionalContext\":\"$N\"}}"]},
 {"event":"PreToolUse","matcher":"Bash","label":"control-deny","out_if_token":["p1bcontrol","{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$C\"}}"]}]}
J
  settings "$P/spec.json"
  cat <<T
STEPS (lead; Claude Code in tmux/screen as the slot user; no allow rules, default permission mode):
  cd $P && export PROBE_EV=$PROBE_EV PROBE_TOKENS=$N,$C
  claude --setting-sources user,project --permission-mode default
  1. type: Run the shell command: echo p1bprompt     -> a PERMISSION PROMPT must appear (the hook gave no decision).
     Record: prompt appeared? (yes = flow unchanged). Approve it once.
  2. type: Run: echo p1bcontrol                      -> must be denied with no prompt (control).
  3. type: List every token starting P1BCTX or P1BCTL you saw in this conversation outside my messages.
     Record: N=$N repeated? (yes + prompt unchanged => context mode is built); C=$C repeated? (control: yes)
  4. repeat step 1 but DENY at the prompt; was the nonce still delivered?
  Then: python3 $IP_DIR/common/where.py <session_id> $N $C   and   summ over $PROBE_EV (run.sh prints it).
T
}
