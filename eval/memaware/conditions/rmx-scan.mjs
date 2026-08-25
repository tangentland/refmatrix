/**
 * Condition: rmx proactive injection — `rmx scan-prompt`.
 *
 * This is the surface refmatrix actually ships. In normal use a Claude Code
 * UserPromptSubmit hook pipes the prompt to `rmx scan-prompt` and the block it
 * prints is prepended to the turn. No search decision, no extra model call,
 * no tool round-trip: the concept graph is walked (personalized PageRank
 * seeded on the prompt's matched concepts) and whatever it reaches is
 * injected whether or not the user asked for it.
 *
 * That is precisely what MemAware set out to measure, which is why this
 * condition — unlike bm25-search — is not a RAG pipeline wearing a different
 * retriever. The one LLM call it makes is the answer call.
 *
 * The token figure the harness records for this condition therefore counts
 * only the injected block plus the answer. The graph walk's own cost is real
 * but is CPU on a local store, not tokens; retrieval_eval.py measures that
 * side separately and for free.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chatComplete, MODELS } from "../lib/llm.mjs";

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));

// conditions/ is symlinked into upstream/, so resolve the store off the env
// the runner exports rather than off import.meta.url.
// run.sh always exports MEMAWARE_RMX_ROOT; the fallback only matters if a
// condition is invoked directly. Conditions are COPIED into the upstream
// clone, so HERE is inside it — never resolve the store relative to HERE.
const STORE = process.env.MEMAWARE_RMX_ROOT
  || join(process.env.MEMAWARE_DATA || "/Volumes/littlebig/memaware", ".refmatrix");
const RMX = process.env.MEMAWARE_RMX || "rmx";
const MAX_TOKENS = process.env.MEMAWARE_RMX_MAX_TOKENS || "1500";

export const name = "rmx-scan";
export const description = "rmx scan-prompt proactive injection (no search step)";

const SYSTEM = `You are a helpful AI assistant. Context from your memory of past conversations with this user has been prepended to the request. It was surfaced automatically — the user did not ask for it, and some of it may be irrelevant. Where it IS relevant, use it and say what you are drawing on. Where it is not, ignore it and answer normally.`;

export async function evaluate(question, context) {
  let injected = "(no memory surfaced)";
  try {
    const { stdout } = await execFileAsync(
      RMX,
      ["scan-prompt", question.question, "--max-tokens", MAX_TOKENS, "--no-composite"],
      {
        env: { ...process.env, REFMATRIX_ROOT: STORE, RMX_PARTITION: "memaware",
               RMX_INVOCATION_SOURCE: "eval" },
        maxBuffer: 32 * 1024 * 1024,
      },
    );
    if (stdout.trim()) injected = stdout.trim();
  } catch (err) {
    // Fail loud in the log, soft in the run: an empty injection is a
    // legitimate 0 for this condition, but a silently swallowed crash would
    // masquerade as one.
    process.stderr.write(`  ! scan-prompt failed: ${err.message}\n`);
  }

  const prompt = `${injected}\n\nUser request: ${question.question}`;
  const response = await chatComplete(MODELS.ANSWER, SYSTEM, prompt, { maxTokens: 2048 });
  return { response };
}
