#!/bin/bash
# L155 mutation proof for the widened AC-0.8 node, on the green-315 working-tree snapshot.
cd /Volumes/littlebig/refmatrix-315-verify || exit 2
SNAP=/private/tmp/claude-501/telemetry.green-snapshot.py
NODE='tests/test_injection_capture.py::test_prompt_text_appears_only_inside_block_text'
run() {  # $1 = log name
  PYTHONPATH=$PWD/src .venv-eval/bin/python -B -m pytest "$NODE" -q -p no:cacheprovider \
    > "workflow/review-output/31.5/$1.log" 2>&1
  echo "$1 rc=$?"; grep -E '^E  |passed|failed' "workflow/review-output/31.5/$1.log" | head -4
}
mutate() {  # $1 = python replace old, $2 = new
  .venv-eval/bin/python - "$1" "$2" <<'PY'
import sys; from pathlib import Path
p = Path("src/refmatrix/telemetry.py"); t = p.read_text()
assert t.count(sys.argv[1]) == 1, "mutation anchor not unique"
p.write_text(t.replace(sys.argv[1], sys.argv[2]))
PY
  find src -name __pycache__ -type d -prune -exec rm -r {} +
}
restore() { cp "$SNAP" src/refmatrix/telemetry.py; find src -name __pycache__ -type d -prune -exec rm -r {} +; }
# MA: the prompt written into a record field outside block text (keeps the key set)
mutate '"channel": channel, "invocation": invocation, "session": session,' \
       '"channel": channel, "invocation": invocation, "session": prompt or session,'
run l155-mut-a-prompt-in-field; restore
# MB: a second candidate-bag anchor carrying the prompt appended to a stored content block
mutate '"blocks": [{"i": i, **b} for i, b in enumerate(blocks)],' \
       '"blocks": [{"i": i, **b, **({"text": b["text"] + "\n=== context for `" + prompt + "` ===\n"} if b.get("kind") == "content" and b.get("state") != "delivered" and b.get("text") and prompt else {})} for i, b in enumerate(blocks)],'
run l155-mut-b-second-anchor; restore
cmp -s "$SNAP" src/refmatrix/telemetry.py && echo "restored clean"
run l155-green-wip-after
