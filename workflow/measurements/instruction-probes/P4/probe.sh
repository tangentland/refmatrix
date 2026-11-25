# P4: can a hook entry be limited by tool_input content before a process starts? Experiment: the
# `if` field (permission-rule syntax) on a PreToolUse command hook. Unfiltered twin = control that
# the logger runs at all; the filtered entry must record ONLY the matching call.
run_probe() {
  newproj P4; C=$(nonce P4CTL); export PROBE_TOKENS="$C"
  cat > "$P/spec.json" <<J
{"hooks":[
 {"event":"PreToolUse","matcher":"Bash","label":"unfiltered"},
 {"event":"PreToolUse","matcher":"Bash","label":"if-filtered","if":"Bash(echo p4hit*)"},
 {"event":"PreToolUse","matcher":"Bash","label":"control-deny","if":"Bash(echo p4deny*)","out":"{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$C\"}}"}]}
J
  settings "$P/spec.json"
  ask "Run these three shell commands, separately and in this order: echo p4miss ; echo p4hit ; echo p4deny. Then list any token starting P4CTL you saw." --allowedTools "Bash(echo p4*)"
  echo "control (if-filtered deny fired and model repeated nonce): $(seen "$C")"
  python3 - "$PROBE_EV" <<'PY'
import json,sys,collections
c=collections.Counter(json.loads(l)["label"] for l in open(sys.argv[1])); print("calls per hook entry:",dict(c))
PY
}
