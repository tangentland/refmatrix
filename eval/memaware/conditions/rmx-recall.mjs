/**
 * Condition: rmx dense memory recall — `rmx memory recall`.
 *
 * The reactive counterpart to rmx-scan: dense ANN (bge-small) over the memory
 * partition, k sessions, injected verbatim. Included as a control — it isolates
 * how much of any rmx result comes from the graph walk rather than from having
 * embedded the corpus at session granularity at all. If rmx-scan and
 * rmx-recall score the same, the graph is contributing nothing here and the
 * win (or loss) is entirely chunking plus embeddings.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chatComplete, MODELS } from "../lib/llm.mjs";

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
// run.sh always exports MEMAWARE_RMX_ROOT; the fallback only matters if a
// condition is invoked directly. Conditions are COPIED into the upstream
// clone, so HERE is inside it — never resolve the store relative to HERE.
const STORE = process.env.MEMAWARE_RMX_ROOT
  || join(process.env.MEMAWARE_DATA || "/Volumes/littlebig/memaware", ".refmatrix");
const RMX = process.env.MEMAWARE_RMX || "rmx";
const K = process.env.MEMAWARE_RMX_K || "5";

export const name = "rmx-recall";
export const description = "rmx memory recall (dense ANN over session memories)";

const SYSTEM = `You are a helpful AI assistant with access to past conversation memory. Relevant past sessions were retrieved and are shown below. Use them where they bear on the request; ignore them where they do not.`;

export async function evaluate(question, context) {
  let injected = "(no memory surfaced)";
  try {
    const { stdout } = await execFileAsync(
      RMX,
      ["memory", "recall", question.question, "--gmd", "-k", K],
      {
        env: { ...process.env, REFMATRIX_ROOT: STORE, RMX_PARTITION: "memaware",
               RMX_INVOCATION_SOURCE: "eval" },
        maxBuffer: 32 * 1024 * 1024,
      },
    );
    if (stdout.trim()) injected = stdout.trim();
  } catch (err) {
    process.stderr.write(`  ! memory recall failed: ${err.message}\n`);
  }

  const prompt = `Memory:\n${injected}\n\nUser request: ${question.question}`;
  const response = await chatComplete(MODELS.ANSWER, SYSTEM, prompt, { maxTokens: 2048 });
  return { response };
}
