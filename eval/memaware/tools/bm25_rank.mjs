#!/usr/bin/env node
/**
 * Rank the corpus for every question with MemAware's OWN BM25 implementation.
 *
 * Layer-A (no-LLM) baseline. Deliberately imports upstream/lib/bm25.mjs rather
 * than reimplementing it in Python: the point of the comparison is rmx's graph
 * against *their* lexical baseline, so any scoring difference has to come from
 * the retrieval model and not from a second-hand BM25.
 *
 * Usage:
 *   node tools/bm25_rank.mjs --questions <path> --k 20 > results/rank-bm25.json
 */

import { readFileSync, existsSync, writeFileSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
const HERE = dirname(fileURLToPath(import.meta.url));
// Benchmark DATA lives off-repo (see paths.py) — default the volume, allow an
// override, fall back to ./data so a fresh checkout still runs.
const DATA = process.env.MEMAWARE_DATA
  || (existsSync("/Volumes/littlebig") ? "/Volumes/littlebig/memaware"
                                       : join(HERE, "..", "data"));
const { buildIndex, search } = await import(join(DATA, "upstream", "lib", "bm25.mjs"));

const args = process.argv.slice(2);
const getArg = (n, d = null) => {
  const i = args.indexOf(`--${n}`);
  return i !== -1 && i + 1 < args.length ? args[i + 1] : d;
};

const QUESTIONS = getArg("questions", join(DATA, "upstream", "data", "questions.json"));
const K = parseInt(getArg("k", "20"));
const OUT = getArg("out", null);

// --granularity day reproduces upstream's own chunking: one document per
// DAILY file (up to 858KB, ~14 sessions concatenated). Ranked days are then
// expanded to the session ids they contain, so the scorer can ask whether the
// answer session was inside anything retrieved. Note the asymmetry — one day
// at k=1 carries ~14 sessions — and read hit@k accordingly. The point of the
// mode is to separate "BM25 is weak here" from "BM25 was handed 700KB blobs".
const GRAN = getArg("granularity", "session");
const mapFile = GRAN === "day" ? "_mapping_daily.json" : "_mapping.json";
const mapping = JSON.parse(readFileSync(join(DATA, "corpus", mapFile), "utf8"));
const docs = [];
for (const relPath of Object.keys(mapping)) {
  const full = relPath.startsWith("/") ? relPath : join(DATA, relPath);
  if (!existsSync(full)) continue;
  docs.push({ id: relPath, text: readFileSync(full, "utf8") });
}
if (docs.length === 0) throw new Error("no corpus docs — run prepare.py first");
process.stderr.write(`  ~ indexing ${docs.length} session docs\n`);

const idx = buildIndex(docs);
const questions = JSON.parse(readFileSync(QUESTIONS, "utf8"));

const out = {};
for (const q of questions) {
  const hits = search(idx, q.question, K);
  out[q.question_id] = GRAN === "day"
    // expand each retrieved day into its member sessions, rank order preserved
    ? hits.flatMap((r) => mapping[r.id] || [])
    // session id is the file stem; the metric layer compares ids, not paths
    : hits.map((r) => basename(r.id, ".md"));
}

const outPath = OUT || join(DATA, "results",
  GRAN === "day" ? "rank-bm25-daily.json" : "rank-bm25.json");
writeFileSync(outPath, JSON.stringify(out, null, 1) + "\n");
process.stderr.write(`  + ${Object.keys(out).length} rankings -> ${outPath}\n`);
