# P8: which event/field carries a Skill call and a slash command? A hook on every event; the tokens
# are the synthetic names p8skill / p8cmd (recorded by path). Control: SessionStart + PreToolUse record.
run_probe() {
  newproj P8; export PROBE_TOKENS="p8skill,p8cmd,P8ARG"
  mkdir -p "$P/.claude/skills/p8skill" "$P/.claude/commands"
  printf -- '---\nname: p8skill\ndescription: probe skill p8\n---\nSkill body, reply DONE.\n' > "$P/.claude/skills/p8skill/SKILL.md"
  printf -- '---\ndescription: probe command p8cmd\n---\nCommand body, reply DONE. Arg: $ARGUMENTS\n' > "$P/.claude/commands/p8cmd.md"
  python3 - "$P" <<'PY'
import json,sys
ev="SessionStart UserPromptSubmit UserPromptExpansion PreToolUse PostToolUse PostToolUseFailure PermissionRequest PermissionDenied Notification SubagentStart SubagentStop Stop StopFailure PreCompact PostCompact InstructionsLoaded SessionEnd CwdChanged FileChanged".split()
json.dump({"hooks":[{"event":e,"label":e} for e in ev]},open(sys.argv[1]+"/spec.json","w"))
PY
  settings "$P/spec.json"
  PROBE_FORM=skilltool ask "Call the Skill tool with skill p8skill now, then say DONE."
  echo "[skill tool] session $SID"
  PROBE_FORM=slashcmd ask "/p8cmd P8ARG"
  PROBE_FORM=slashskill ask "/p8skill P8ARG"
}
