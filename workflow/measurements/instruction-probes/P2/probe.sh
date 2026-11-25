# P2 — INTERACTIVE, for the lead. A PreToolUse hook returning permissionDecision "ask" in default and in
# auto mode. Builds the project and prints the steps; nothing is run.
run_probe() {
  newproj P2; C=$(nonce P2CTL); export PROBE_TOKENS="$C"; MODE="interactive (lead)"
  cat > "$P/spec.json" <<J
{"hooks":[
 {"event":"PreToolUse","matcher":"Bash","label":"ask","out_if_token":["p2ask","{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"p2 probe ask\"}}"]},
 {"event":"PreToolUse","matcher":"Bash","label":"control-deny","out_if_token":["p2control","{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$C\"}}"]}],
 "extra":{"permissions":{"allow":["Bash(echo p2ask*)","Bash(echo p2plain*)"]}}}
J
  settings "$P/spec.json"
  cat <<T
STEPS (lead; interactive, as the slot user). The allow rule makes "echo p2ask" prompt-free WITHOUT the hook,
so a prompt can only come from the hook's ask:
  cd $P && export PROBE_EV=$PROBE_EV PROBE_TOKENS=$C
  A. claude --setting-sources user,project --permission-mode default
     1. Run: echo p2plain  -> NO prompt expected (control: the allow rule works).
     2. Run: echo p2ask    -> prompt expected (hook ask). Record: prompt? (yes/no)
     3. Run: echo p2control -> denied; model repeats $C (control for the hook wiring).
  B. claude --setting-sources user,project --permission-mode auto     (the auto-mode classifier on)
     repeat 1-3. Record for step 2: prompt appeared? or ran silently? or denied?
  Verdict: prompt in both => the ask kind is built and R006 is ask; no prompt in auto mode => R006 is a gate.
T
}
