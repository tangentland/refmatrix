# P7: does a USER-level rule's paths: match a file outside the project (a memory dir)?
# Three spellings of the glob, each its own nonce; control = a user rule matching a file INSIDE the
# project. The user-level rule files live in the slot HOME's ~/.claude/rules and are removed afterwards.
run_probe() {
  newproj P7; MEM="$WORKROOT/p7mem.$$/memory"; mkdir -p "$MEM"; echo n > "$MEM/note.md"
  A=$(nonce P7ABS); B=$(nonce P7STAR); T=$(nonce P7TILDE); K=$(nonce P7INSIDE); export PROBE_TOKENS="$A,$B,$T,$K"
  RD="$HOME/.claude/rules"; mkdir -p "$RD"; TAG=p7probe-$$
  REL=${MEM#$HOME/}
  printf -- '---\npaths:\n  - "%s/**"\n---\nUser rule %s\n' "$MEM" "$A" > "$RD/$TAG-abs.md"
  printf -- '---\npaths:\n  - "**/memory/*.md"\n---\nUser rule %s\n' "$B" > "$RD/$TAG-star.md"
  printf -- '---\npaths:\n  - "~/%s/**"\n---\nUser rule %s\n' "$REL" "$T" > "$RD/$TAG-tilde.md"
  printf -- '---\npaths:\n  - "p7inside/**"\n---\nUser rule %s\n' "$K" > "$RD/$TAG-inside.md"
  mkdir -p "$P/p7inside"; echo i > "$P/p7inside/f.txt"
  echo '{"hooks":[{"event":"InstructionsLoaded","label":"loaded"}]}' > "$P/spec.json"; settings "$P/spec.json"
  ask "Read the file $MEM/note.md, then read p7inside/f.txt. Then report every token starting P7ABS, P7STAR, P7TILDE or P7INSIDE visible anywhere in your context, each on its own line, or NONE." --add-dir "$MEM/.."
  echo "outside file, absolute glob : $(seen "$A")"; echo "outside file, **/memory/*.md : $(seen "$B")"
  echo "outside file, ~/ glob       : $(seen "$T")"; echo "control (inside project)    : $(seen "$K")"
  ask "Same task but WITHOUT --add-dir: Read $MEM/note.md then report tokens starting P7ABS, P7STAR, P7TILDE visible in context, or NONE."
  echo "[no --add-dir] abs: $(seen "$A") star: $(seen "$B") tilde: $(seen "$T")"
  rm -f "$RD/$TAG"-*.md; rmdir "$RD" 2>/dev/null; rm -rf "$WORKROOT/p7mem.$$"
}
