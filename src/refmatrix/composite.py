"""Topic composite — a GMD subgraph fusing the STM focus graph with long-term
graph neighborhoods, for injection into the per-prompt context.

The STM focus graph already aggregates every prompt+result (their extracted
refs) into a scored, decayed co-occurrence graph; `stm.topic_composites` splits
it into the dominant topic threads. This module expands each thread's strongest
nodes into their long-term linkage neighborhood via `build_context` and renders
ONE GMD subgraph — "what I'm working on now" (STM) fused with "what it connects
to" (LTM).

The rendered output is hard-capped by its OWN token budget
(`max_tokens` / env `RMX_STM_COMPOSITE_TOKENS`), independent of the
prompt-symbol context budget, so the two never rob each other.
"""
from __future__ import annotations

import os
from pathlib import Path

from .context import build_context, estimate_tokens
from .stm import Stm, is_junk_ref, latest_session, topic_composites

# Shape-based junk gate (canonical in stm). Kept as a module name for the
# render loop + tests. English-word channel noise (e.g. "notification") is an
# UPSTREAM ingest problem, fixed by gating the input hook + `focus rebuild`.
_is_junk = is_junk_ref

# Own budget, independent of scan-prompt's --max-tokens.
COMPOSITE_TOKENS = int(os.environ.get("RMX_STM_COMPOSITE_TOKENS", "1200"))
# Ceiling for the autoscaled budget — a long session earns a richer composite,
# but never an unbounded one.
COMPOSITE_TOKENS_MAX = int(os.environ.get("RMX_STM_COMPOSITE_TOKENS_MAX", "3000"))
# Tokens of extra budget per STM turn (input prompt) when autoscaling.
COMPOSITE_TOKENS_PER_TURN = int(
    os.environ.get("RMX_STM_COMPOSITE_TOKENS_PER_TURN", "15"))
COMPOSITE_K = int(os.environ.get("RMX_STM_COMPOSITE_K", "3"))
# Inject cadence: render the composite only every Nth STM turn. 1 = every turn
# (default). Higher N throttles the per-prompt injection — the focus graph still
# updates every turn, but the composite block is only emitted on turns where
# `turn % every == 0` (turn 0 always renders).
COMPOSITE_EVERY = int(os.environ.get("RMX_STM_COMPOSITE_EVERY", "1"))


def _scaled_budget(base: int, turn: int, *, autoscale: bool,
                   ceiling: int, per_turn: int) -> int:
    """Effective composite budget. `base` is the floor; when `autoscale`, it
    grows linearly with session depth (`turn` = number of input prompts) up to
    `ceiling`. A longer session builds a denser focus graph, so its composite is
    allowed more room — bounded so it can't crowd the whole context window."""
    if not autoscale:
        return base
    return max(base, min(ceiling, base + max(0, turn) * per_turn))


def build_topic_composite(
    s,
    root,
    *,
    k: int = COMPOSITE_K,
    top: int = 40,
    expand: bool = True,
    per_node_entities: int = 4,
    expand_nodes_per_topic: int = 3,
    max_expansions: int = 6,
    max_tokens: int = COMPOSITE_TOKENS,
    autoscale: bool = True,
    max_tokens_ceiling: int = COMPOSITE_TOKENS_MAX,
    tokens_per_turn: int = COMPOSITE_TOKENS_PER_TURN,
    every: int = COMPOSITE_EVERY,
    session: str | None = None,
) -> str:
    """GMD subgraph of the session's current topics, or "" when there is no STM
    or no multi-node topic.

    Budget: `max_tokens` is the floor. When `autoscale` (default), the effective
    cap grows with session depth (STM turn count) up to `max_tokens_ceiling`, so
    a deep session's denser focus gets a proportionally richer composite. This
    budget is separate from the prompt-symbol context budget.

    Cadence: `every` throttles injection to one turn in N (default 1 = every
    turn). On skipped turns this returns "" — the focus graph still updates, only
    the emitted block is suppressed.

    `s` is the long-term Store (for LTM expansion); `root` is the project's
    `.refmatrix` dir (STM lives at `<root>/stm`, keyed like `focus hook`).
    `session` defaults to the most-recently-written ring (`latest_session`),
    which the UserPromptSubmit `focus hook` writes on the same turn."""
    root = Path(root)
    session = session or latest_session(root)
    if session is None:
        return ""
    graph = Stm(root, session=session).focus_graph(top=top)
    topics = topic_composites(graph, k=k)
    if not topics:
        return ""
    turn = graph.get("turn", 0)
    # Cadence gate: throttle per-prompt injection to every Nth turn.
    if every > 1 and turn % every != 0:
        return ""
    budget = _scaled_budget(
        max_tokens, turn, autoscale=autoscale,
        ceiling=max_tokens_ceiling, per_turn=tokens_per_turn)
    return _render_gmd(
        s, topics,
        expand=expand, per_node_entities=per_node_entities,
        expand_nodes_per_topic=expand_nodes_per_topic,
        max_expansions=max_expansions, max_tokens=budget,
        turn=turn,
    )


def _render_gmd(
    s, topics, *, expand, per_node_entities, expand_nodes_per_topic,
    max_expansions, max_tokens, turn,
) -> str:
    lines: list[str] = [
        "# STM topic composite — current focus (GMD subgraph)",
        "```gmd",
        "---",
        'gmd: "0.1"',
        "id: stm-topic-composite",
        'title: "STM topic composite"',
        "tags: [stm, composite, focus]",
        f"metadata: {{turn: {turn}}}",
        "---",
        "# Current focus {#root}",
    ]

    def _budget_ok() -> bool:
        return estimate_tokens("\n".join(lines)) < max_tokens

    expansions = 0
    topic_no = 0
    for t in topics:
        if not _budget_ok():
            break
        members = [m for m in t["members"] if not _is_junk(m)]
        if len(members) < 2:
            continue  # collapsed to noise after the junk gate
        topic_no += 1
        head = members[0]
        lines.append("")
        lines.append(f"## Topic {topic_no}: {head} {{#topic-{topic_no}}}")
        lines.append("Members: " + ", ".join(members))
        # STM co-occurrence edges (typed rel between focus members).
        for e in t["edges"]:
            if not _budget_ok():
                break
            if _is_junk(e.get("source", "")) or _is_junk(e.get("target", "")):
                continue
            lines.append(
                f"rel: co-occurs -> [[{e['target']}]] "
                f"{{from: {e['source']}, w: {e.get('weight', 0)}}}")
        # LTM expansion: strongest clean nodes → their linkage neighborhood.
        if expand:
            clean_nodes = [nd for nd in t["nodes"] if not _is_junk(nd["name"])]
            for nd in clean_nodes[:expand_nodes_per_topic]:
                if expansions >= max_expansions or not _budget_ok():
                    break
                b = build_context(
                    s, nd["name"],
                    max_entities=per_node_entities, max_tokens=300)
                if b.anchor is None or not b.groups:
                    continue
                expansions += 1
                for linkage, entries in b.groups.items():
                    for ent in entries[:per_node_entities]:
                        if not _budget_ok():
                            break
                        tgt = getattr(ent.entity, "name", None)
                        if not tgt or tgt == nd["name"]:
                            continue
                        lines.append(
                            f"rel: {linkage} -> [[{tgt}]] "
                            f"{{anchor: {nd['name']}, ltm: 1}}")
    lines.append("```")
    return "\n".join(lines)
