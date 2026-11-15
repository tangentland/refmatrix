#!/bin/bash
# L155 + L156 proof against green-315's committed tip c3e04d3 (verify clone, detached).
V=/Volumes/littlebig/refmatrix-315-verify
R=/Volumes/littlebig/refmatrix-315
cd "$V" || exit 2
[ "$(git rev-parse --short=7 HEAD)" = "c3e04d3" ] || { echo "not at c3e04d3"; exit 2; }
OUT=/Volumes/littlebig/refmatrix-315/workflow/review-output/31.5
COMP='tests/test_composite.py::test_intra_cluster_emits_real_verb_not_cooccurs tests/test_composite.py::test_intra_edges_zero_drops_grounded_block tests/test_composite.py::test_ltm_expansion_ranks_sparse_first_and_dedups'
AC08='tests/test_injection_capture.py::test_prompt_text_appears_only_inside_block_text'
run() {  # $1 log, rest = nodes
  local log=$1; shift
  PYTHONPATH=$V/src .venv-eval/bin/python -B -m pytest "$@" -q -p no:cacheprovider > "$OUT/$log.log" 2>&1
  echo "== $log rc=$?"; grep -E '^E   [A-Za-z]|passed|failed' "$OUT/$log.log" | head -4
}
clean_pyc() { find src tests -name __pycache__ -type d -prune -exec rm -r {} +; }
mutate() {
  .venv-eval/bin/python - "$1" "$2" <<'PY'
import sys; from pathlib import Path
p = Path("src/refmatrix/telemetry.py"); t = p.read_text()
assert t.count(sys.argv[1]) == 1, "mutation anchor not unique"
p.write_text(t.replace(sys.argv[1], sys.argv[2]))
PY
  clean_pyc
}
restore() { git checkout -q -- src/refmatrix/telemetry.py; clean_pyc; git diff --quiet -- src && echo "src restored clean"; }
# L156: green's own test_composite (bare object()) fails; with the double it passes; whole file too
run l156-green-original-test-composite $COMP
cp "$R/tests/test_composite.py" tests/test_composite.py; clean_pyc
run l156-green-double-3-nodes $COMP
run l156-green-double-test-composite-file tests/test_composite.py
# L155: the widened AC-0.8 node on green's tip, then MA and MB
cp "$R/tests/test_injection_capture.py" tests/test_injection_capture.py; clean_pyc
run l155-green-c3e04d3 $AC08
mutate '"channel": channel, "invocation": invocation, "session": session,' \
       '"channel": channel, "invocation": invocation, "session": prompt or session,'
run l155-c3e04d3-mut-a-prompt-in-field $AC08; restore
mutate '"blocks": [{"i": i, **b} for i, b in enumerate(blocks)],' \
       '"blocks": [{"i": i, **b, **({"text": b["text"] + "\n=== context for `" + prompt + "` ===\n"} if b.get("kind") == "content" and b.get("state") != "delivered" and b.get("text") and prompt else {})} for i, b in enumerate(blocks)],'
run l155-c3e04d3-mut-b-second-anchor $AC08; restore
run l155-green-c3e04d3-after $AC08
git checkout -q -- tests; echo "tests restored to c3e04d3"
