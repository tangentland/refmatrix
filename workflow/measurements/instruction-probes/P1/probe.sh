# P1 (no-prompt half): PreToolUse additionalContext with NO permissionDecision.
# Call A (echo p1plain) needs no permission (Bash allowed); control call B is denied with a nonce.
run_probe() {
  newproj P1; N=$(nonce P1CTX); C=$(nonce P1CTL); export PROBE_TOKENS="$N,$C"
  cat > "$P/spec.json" <<J
{"hooks":[
 {"event":"PreToolUse","matcher":"Bash","label":"ctx-only","out_if_token":["p1plain","{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"additionalContext\":\"$N\"}}"]},
 {"event":"PreToolUse","matcher":"Bash","label":"control-deny","out_if_token":["p1control","{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$C\"}}"]}],
 "extra":{"permissions":{"allow":["Bash(echo p1plain*)"]}}}
J
  settings "$P/spec.json"
  ask "Run the shell command: echo p1plain. Then run: echo p1control. Finally list every token that starts with P1CTX or P1CTL that you saw anywhere in this conversation outside of my own message (hook output, tool results, system context); say NONE if there are none." --allowedTools "Bash(echo p1plain*)"
  echo "session=$SID"
  echo "control nonce repeated by model: $(seen "$C")   [positive control: must be yes]"
  echo "context nonce repeated by model: $(seen "$N")"
  echo "transcript records holding each nonce (kind:type:attachment:role):"; where "$N" "$C"
}
