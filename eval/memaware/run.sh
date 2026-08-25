#!/usr/bin/env bash
# Drive MemAware's upstream harness against the local corpus + rmx conditions.
#
# The upstream clone is gitignored, so our conditions live in eval/memaware/
# and are symlinked into it at run time; nothing here mutates the clone's
# tracked files.
#
# Two things upstream gets wrong on any machine that is not the author's, both
# fixed here rather than in the clone:
#   * _mapping.json ships absolute /Users/kevin/... paths, and run.mjs passes
#     absolute paths straight to existsSync — so the index silently comes back
#     empty. prepare.py writes a local mapping; MEMAWARE_MEMORY points at it.
#   * The published baselines were judged by gpt-5.1, but lib/llm.mjs defaults
#     MODELS.JUDGE to gpt-4o-mini. Numbers produced without setting
#     MEMAWARE_JUDGE are NOT comparable to the README's table.
#
# It also installs a vendored lib/llm.mjs that adds Anthropic as a third
# provider, so `claude-*` can serve as judge and/or answer model.
#
# Usage:
#   ./run.sh rmx-scan                       # stratified subset (default)
#   MEMAWARE_QUESTIONS=upstream/data/questions.json ./run.sh all
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Benchmark DATA lives off-repo. See paths.py for why (the watcher ate the
# corpus once already); MEMAWARE_DATA overrides.
if [ -z "${MEMAWARE_DATA:-}" ]; then
  if [ -d /Volumes/littlebig ]; then MEMAWARE_DATA=/Volumes/littlebig/memaware
  else MEMAWARE_DATA="$HERE/data"; fi
fi
export MEMAWARE_DATA
UP="$MEMAWARE_DATA/upstream"
CONDITION="${1:-rmx-scan}"

[ -d "$UP" ] || { echo "  ! $UP missing — python3 prepare.py --clone" >&2; exit 1; }
[ -d "$MEMAWARE_DATA/corpus" ] || { echo "  ! corpus missing — python3 prepare.py" >&2; exit 1; }
[ -d "$UP/node_modules" ] || (cd "$UP" && npm install)
[ -d "$UP/node_modules/@anthropic-ai/sdk" ] || (cd "$UP" && npm install @anthropic-ai/sdk)

# COPY, never symlink. Node resolves bare imports ("openai", "@anthropic-ai/sdk")
# from a module's REAL path, so a symlink back into eval/memaware/ would look
# for node_modules here instead of in the clone, and every condition would die
# on "Cannot find package 'openai'".
for f in "$HERE"/conditions/*.mjs; do
  cp -f "$f" "$UP/conditions/$(basename "$f")"
done

# Install the Anthropic-capable llm.mjs, keeping the original beside it. The
# judge is constructed inside run.mjs, which imports ./lib/llm.mjs directly —
# there is no seam to add a provider through from a condition.
if [ ! -f "$UP/lib/llm.upstream.mjs" ]; then
  cp "$UP/lib/llm.mjs" "$UP/lib/llm.upstream.mjs"
fi
EXPECT="$(cat "$HERE/lib/.upstream-llm-sha")"
ACTUAL="$(shasum -a 256 "$UP/lib/llm.upstream.mjs" | cut -c1-16)"
if [ "$EXPECT" != "$ACTUAL" ]; then
  echo "  ! upstream lib/llm.mjs drifted (expected $EXPECT, got $ACTUAL)" >&2
  echo "  ! re-vendor eval/memaware/lib/llm.mjs before trusting a comparison" >&2
fi
cp -f "$HERE/lib/llm.mjs" "$UP/lib/llm.mjs"

export MEMAWARE_MEMORY="${MEMAWARE_MEMORY:-$MEMAWARE_DATA/corpus}"
export MEMAWARE_QUESTIONS="${MEMAWARE_QUESTIONS:-$MEMAWARE_DATA/subsets/stratified-30.json}"
export MEMAWARE_RESULTS="${MEMAWARE_RESULTS:-$MEMAWARE_DATA/results}"
export MEMAWARE_RMX_ROOT="${MEMAWARE_RMX_ROOT:-$MEMAWARE_DATA/.refmatrix}"
# Answer model: upstream defaults to Kimi K2.5 on Fireworks. Without a
# FIREWORKS_API_KEY, override to an OpenAI model — and re-run the no-memory and
# bm25-search baselines with the SAME model, or the comparison is meaningless.
# Answer + judge models. Any id starting with `claude-` routes to the Anthropic
# Messages API via the vendored llm.mjs; `accounts/fireworks/*` to Fireworks;
# anything else to OpenAI. Upstream's published numbers used Kimi K2.5 as the
# answer model and gpt-5.1 as judge — swapping EITHER makes this run
# incomparable to the README table until the no-memory and bm25-search
# baselines are re-run under the same pair.
export MEMAWARE_MODEL="${MEMAWARE_MODEL:-accounts/fireworks/models/kimi-k2p5}"
export MEMAWARE_JUDGE="${MEMAWARE_JUDGE:-gpt-5.1}"

mkdir -p "$MEMAWARE_RESULTS"
echo "  ~ questions : $MEMAWARE_QUESTIONS"
echo "  ~ corpus    : $MEMAWARE_MEMORY"
echo "  ~ store     : $MEMAWARE_RMX_ROOT"
echo "  ~ answer    : $MEMAWARE_MODEL"
echo "  ~ judge     : $MEMAWARE_JUDGE"

cd "$UP"
node run.mjs --condition "$CONDITION" "${@:2}"
