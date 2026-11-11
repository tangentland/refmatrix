"""Regenerate the plan-25 task 25.1 frozen fixture (synthetic text only).

Run once, commit the output; the tests read the COMMITTED files, never this script
(`tests/task25_1_support.py` copies them into a sandbox memdir). Deterministic: the same
run writes the same bytes, so `git diff` after a re-run is the fixture's change log.

    python3 tests/fixtures/plan25/make_fixture.py

Sizes follow the 21.1 byte counts quoted in the task spec (#why): cliquedb's per-prompt
recall bodies measured 2.0-8.7 KB, so the 30 bodies step linearly from 2,000 to 8,700 B.
Every hook line and body carries >= 4 of `—` / `→` (AC-2, AC-10 multibyte pre-checks).
No real prompt, query log or memory text is used (feedback_no_raw_prompts_in_public_repo).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEM = HERE / "memory"
GLOBAL = HERE / "global"

N_MEM = 30
BODY_MIN, BODY_MAX = 2000, 8700
TYPES = ("project", "feedback", "reference")

QUESTION = "how does the quasar ledger reconcile flux batches across zorbulate shards"
ACK = "yes next"
SYMBOL = "zorbulate_shard_merge"

_TOPICS = ("flux batch", "shard merge", "ledger close", "reconcile pass", "quasar audit",
           "batch fence", "zorbulate split", "settlement window", "drift check", "replay")


def mem_name(i: int) -> str:
    return f"fx_mem_{i:02d}"


def title_of(i: int) -> str:
    return f"Quasar ledger note {i:02d} — {_TOPICS[i % len(_TOPICS)]} → shard {i}"


def hook_of(i: int) -> str:
    # The CURATED hook: never the file's first sentence, so a pack that prints it proves the
    # index lookup ran (AC-9). Two `—` and two `→`: with the line's own two `—` separators the
    # hook line carries >= 4 multibyte characters.
    return (f"HOOK-{mem_name(i)} — curated: reconcile {_TOPICS[i % len(_TOPICS)]} "
            f"→ ledger → shard {i} — owner note")


def body_of(i: int, size: int) -> str:
    name = mem_name(i)
    topic = _TOPICS[i % len(_TOPICS)]
    head = (f"# {title_of(i)} {{#root}}\n\n"
            f"First sentence of {name} — the quasar ledger reconciles {topic} "
            f"→ zorbulate shard {i} → close.\n\n"
            f"BODYMARK {name} — this paragraph marks the body; a pack that prints it "
            f"printed the whole body → not a hook line → not a pointer.\n\n")
    para = (f"- {name}: flux batches across zorbulate shards — {topic} — reconcile "
            f"→ settle → audit; the quasar ledger keeps every batch fenced — step "
            f"{{n}}.\n")
    out = head
    n = 0
    while len(out.encode("utf-8")) < size:
        out += para.format(n=n)
        n += 1
    out += f"\nEND {name} — →\n"
    return out


def frontmatter(mid: str, title: str, mtype: str, extra: str = "") -> str:
    return (f"---\ngmd: \"0.1\"\nid: {mid}\ntitle: \"{title}\"\n"
            f"tags: [{mtype.split('/')[0]}, plan25-fixture]\nmetadata:\n"
            f"  node_type: memory\n  type: {mtype}\n{extra}"
            f"  created: 2026-11-01\n  updated: 2026-11-01\n---\n\n")


def main() -> None:
    MEM.mkdir(parents=True, exist_ok=True)
    (MEM / "savestates").mkdir(exist_ok=True)
    GLOBAL.mkdir(parents=True, exist_ok=True)
    index = []
    for i in range(N_MEM):
        size = BODY_MIN + round(i * (BODY_MAX - BODY_MIN) / (N_MEM - 1))
        mtype = TYPES[i % len(TYPES)]
        (MEM / f"{mem_name(i)}.md").write_text(
            frontmatter(mem_name(i), title_of(i), mtype) + body_of(i, size), encoding="utf-8")
        index.append(f"- [{title_of(i)}]({mem_name(i)}.md) — {hook_of(i)}")
    # AC-11: a project row and a global row with ONE name.
    (MEM / "fx_dup_x.md").write_text(
        frontmatter("fx_dup_x", "Duplicate name — project copy → AC-11", "project")
        + "# Duplicate name — project copy → AC-11 {#root}\n\n"
          "PROJECT-COPY fx_dup_x — the project's row of a name the global store also "
          "holds → quasar ledger → shard.\n", encoding="utf-8")
    index.append("- [Duplicate name — project copy → AC-11](fx_dup_x.md) — "
                 "HOOK-fx_dup_x — curated: the project copy → not the global one → —")
    # AC-5: a hand-authored save-state mis-typed `project` (4 of cliquedb's files carry it),
    # placed where 26.3 puts save-states, and the body that best matches the question.
    ss_body = ("# Save-state fx01 {#root}\n\n"
               "SAVESTATE-fx01 — handoff → next → reconcile.\n\n"
               + "".join(f"{QUESTION} — handoff note {n} → next step.\n" for n in range(60)))
    (MEM / "savestates" / "savestate_fx01.md").write_text(
        frontmatter("savestate_fx01", "Save-state fx01 — handoff → next", "project")
        + ss_body, encoding="utf-8")
    (MEM / "MEMORY.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    # 10 global memories (lexical global leg: the content holds the question verbatim, the
    # global store's `memory_search` being a substring match), plus AC-11's duplicate.
    rows = []
    for g in range(10):
        rows.append({"name": f"gx_mem_{g}", "mtype": "feedback",
                     "content": f"GLOBAL-COPY gx_mem_{g} — cross-project rule {g} → "
                                f"{QUESTION} → always fence the batch — owner {g}.\n"
                                + "global detail line — → — →\n" * 30})
    rows.append({"name": "fx_dup_x", "mtype": "feedback",
                 "content": f"GLOBAL-COPY fx_dup_x — the global row → {QUESTION} — →\n"})
    (GLOBAL / "memories.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False)
                                          + "\n", encoding="utf-8")
    (HERE / "prompts.json").write_text(json.dumps(
        {"question": QUESTION, "ack": ACK, "symbol": SYMBOL}, indent=1) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
