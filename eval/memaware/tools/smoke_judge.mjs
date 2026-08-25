#!/usr/bin/env node
/**
 * One-call smoke test for the judge path. Run this BEFORE a 900-question run.
 *
 * Checks the two things that silently zero out a whole run:
 *   1. the provider is reachable with the key you exported, and
 *   2. `maxTokens: 20` — run.mjs's hard-coded judge budget — still leaves room
 *      for a parseable "YES | CORRECT". A model that spends the budget before
 *      emitting text parses as NO and scores every answer 0.
 *
 * Usage:  MEMAWARE_JUDGE=claude-sonnet-5 node tools/smoke_judge.mjs
 */

import { chatComplete, MODELS } from "../upstream/lib/llm.mjs";

const CASES = [
  { label: "should judge YES",
    response: "Since your commute runs 45 minutes each way, set the alarm for 7:00 AM." },
  { label: "should judge NO",
    response: "Set your alarm early enough to get ready and travel comfortably." },
];

const PROMPT = (response) => `An AI assistant was asked to perform a task. A related past decision exists in the assistant's memory that should have been surfaced proactively.

Task request: I'm planning my morning routine so I can arrive at the office by 8:30 AM. What time should I set my alarm?
Past context that should have been recalled: The user's daily commute takes 45 minutes each way.
Why these are related: The alarm time cannot be computed without the commute duration.

Assistant's response:
${response}

Did the assistant demonstrate awareness of the related past context? This means the assistant either explicitly referenced the past decision, used information from it, or acknowledged its relevance. Simply arriving at the same answer by coincidence does NOT count.

Also classify the response type:
- CORRECT: explicitly referenced the right past context
- ABSTAINED: responded without any reference to past context
- HALLUCINATED: referenced past context that is wrong or doesn't exist
- PARTIAL: referenced related but different past context

Answer format: YES/NO | TYPE
Example: YES | CORRECT or NO | ABSTAINED`;

console.log(`  ~ judge model: ${MODELS.JUDGE}`);
let bad = 0;
for (const c of CASES) {
  try {
    const raw = await chatComplete(MODELS.JUDGE, "You are an evaluation judge.",
      PROMPT(c.response), { maxTokens: 20 });
    const parts = raw.trim().split("|").map((s) => s.trim());
    const verdict = parts[0]?.toLowerCase().startsWith("yes") ? "YES" : "NO";
    const type = parts[1] || "(none)";
    const parsed = /^(yes|no)\b/i.test(raw.trim());
    if (!parsed) bad++;
    console.log(`  ${parsed ? "+" : "!"} ${c.label}: raw=${JSON.stringify(raw)} -> ${verdict} | ${type}`);
  } catch (err) {
    bad++;
    console.log(`  ! ${c.label}: ${err.message.slice(0, 160)}`);
  }
}
console.log(bad === 0
  ? "  + judge path OK — 20-token budget is sufficient"
  : `  ! ${bad}/${CASES.length} unusable — DO NOT launch a full run`);
process.exit(bad === 0 ? 0 : 1);
