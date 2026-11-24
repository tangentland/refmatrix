"""THE byte budget of every rmx producer that writes into a Claude Code hook's stdout.

Why (task 25.1 R1, bug-164, 2026-11-11): the per-prompt recall hook printed 15-31 kB of JSON on
refmatrix and 22-59 kB on cliquedb, and Claude Code delivers a hook's output whole only up to a
cap; past it the model gets a ~2 kB preview. So the hook cliquedb most wanted working arrived as a
preview on 95% of prompts, and scan-prompt (its sibling on the same event, `--max-tokens` being a
TOKEN count) overflowed on its own. There was no budget anywhere -- each producer had its own
notion of "short".

R0 measured the cap (`workflow/measurements/hook-output-cap-probe.md`, 2026-11-11, Claude Code
2.1.322): **10,000 UTF-16 code units of whitespace-trimmed stdout, per hook COMMAND** (outcome A
on UserPromptSubmit and on SessionStart; PreCompact cuts at the same cap instead of previewing).
The unit this module budgets is therefore the generated hook command (25.1 d9), at
`0.95 x cap` = 9,500 B each (raised from 0.9 by the user, 2026-11-15: "make sure the 9.5k
constraint is added with it", with the scan-prompt order fix), and producers that share ONE command share its budget
(`HOOK_COMMAND_CHANNELS`: scan-prompt and curator status run in `scan_cmd`).

The budget unit is UTF-8 BYTES of the rendered payload (19.1 R1): for any text the UTF-8 byte
count is >= its UTF-16 unit count, so a payload within N bytes is within N units of the harness
cap too. Counting characters would under-count every `—` / `→` by 2 bytes (the AC-2 fixture is
dense in them on purpose).

Everything here is pure: no I/O beyond reading `RMX_HOOK_BUDGET_BYTES`, no telemetry, no store.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Sequence

# R0 (d748196): Claude Code's per-hook delivery cap, in UTF-16 code units.
HOOK_CAP_UNITS = 10_000
# Outcome (A): each generated hook command's budget is 0.95 x cap (the user, 2026-11-15; was
# 0.9). UTF-8 bytes >= UTF-16 units, so 9,500 B stays 500 units under the harness cap.
HOOK_COMMAND_BUDGET_BYTES = int(0.95 * HOOK_CAP_UNITS)

# Per producer (21.1's channel names, plus R11's `recall_state`). The R1 provisional set was
# kept after R0: under outcome (A) every value is at or under the per-command budget (9,500 B since 2026-11-15)
# (`#outcome-r1-fit`), and the per-prompt 4,000 is d3's POINTER list -- 12 hook lines at
# 250-370 B fill it and no 2 kB body fits, so bodies stay a `session_start` feature.
CHANNEL_BUDGET_BYTES: "dict[str, int]" = {
    "prompt_recall": 4_000,
    # scan_cmd = scan-prompt `;` curator status: ONE command, ONE 9,500 B budget split here
    # (2026-11-15: was 4,500 + 500 = 5,000, leaving half the command's room unused while the
    # cap dropped the symbol bundles on nearly every prompt).
    "scan_prompt": 9_000,
    "curator_status": 500,
    # `rmx focus hook --event input` writes nothing to stdout today; its share is a cap, so a
    # later print cannot grow unbounded beside the other three UserPromptSubmit commands.
    "focus_input": 256,
    "session_start": 9_000,
    "focus_context": 1_500,
    # task-compaction-as-handoff R3b (L202 fold, 2026-11-24): `rmx handoff remind`, ONE line
    # naming `<store>/handoffs/<session>.txt` while a handoff is unread. 512 B holds the line
    # with a UUID session under a deep store path (the line is ~200 B plus the path).
    # (`precompact`, 9,000 B, is retired: R2 removed the generated PreCompact recall, and
    # bsd-cah r1 #m-4 found the channel kept alive only by a hand-written test argv.)
    "handoff_remind": 512,
    # R11 (rev 6): `rmx recall-state --max-bytes N` on SessionStart compact|clear, own command.
    "recall_state": 9_000,
}

# Which channels write into ONE generated hook command (hooks._claude_hook_block). A command's
# budget is the SUM of its channels' budgets, and must be <= HOOK_COMMAND_BUDGET_BYTES.
HOOK_COMMAND_CHANNELS: "dict[str, tuple[str, ...]]" = {
    "scan_cmd": ("scan_prompt", "curator_status"),
    "sess_cmd": ("curator_status",),
    "focus_input_cmd": ("focus_input",),
    "prompt_recall_cmd": ("prompt_recall",),
    "session_start_cmd": ("session_start",),
    "focus_context_cmd": ("focus_context",),
    "handoff_remind_cmd": ("handoff_remind",),
    "recall_state_cmd": ("recall_state",),
}

# The rmx producers on each event, with the share each would get under a PER-EVENT cap
# (spec R1 requires the constant; R0 (B) is the only formula that would consume it:
# EVENT_BUDGET[event] split across the event's producers). R0 found outcome (A) on both events,
# so no budget is computed from it today. What IS read, at import (`_check_tables`, bsd-251 m-4,
# 2026-11-14): every share is a known channel's own cap (never more), and every budgeted channel
# but PreCompact's sits on an R0 event, so a new channel cannot be added without a place here.
EVENT_SPLIT: "dict[str, dict[str, int]]" = {
    "UserPromptSubmit": {c: CHANNEL_BUDGET_BYTES[c]
                         for c in ("scan_prompt", "curator_status", "focus_input",
                                   "prompt_recall", "handoff_remind")},
    "SessionStart": {c: CHANNEL_BUDGET_BYTES[c]
                     for c in ("curator_status", "session_start", "focus_context",
                               "recall_state")},
}

# Bytes the user's NON-rmx hooks add per event, rounded up to 512 B (R0 #reserve-rounded):
# UserPromptSubmit = the caveman mode tracker, 121 B observed, 242 B worst case (two copies);
# SessionStart = caveman-activate standalone 1,215 B + its plugin copy 2,024 B = 3,239 B. Per
# event, never one number for both (AC-14: one reserve overflows SessionStart by caveman's
# bytes under a per-event cap).
NON_RMX_RESERVE_BYTES: "dict[str, int]" = {
    "UserPromptSubmit": 512,
    "SessionStart": 3_584,
}

# Header + 6 hook lines: below this a recall payload is not worth printing (outcome C's floor).
# Read at import (`_check_tables`): no recall channel's table budget may sit under it.
MIN_USEFUL_RECALL_BYTES = 2_000

ENV_VAR = "RMX_HOOK_BUDGET_BYTES"


def _check_tables() -> None:
    """Fail at import if the table contradicts itself: a channel no command carries, a command
    over R0's per-command budget, a reserve not on the 512 B grid, an event share above its
    channel's cap or a budgeted channel on no event, a recall channel under the useful floor.
    Cheap, and it turns an edit that breaks the contract into an import error rather than a
    truncated hook."""
    for cmd, chans in HOOK_COMMAND_CHANNELS.items():
        unknown = [c for c in chans if c not in CHANNEL_BUDGET_BYTES]
        if unknown:
            raise ValueError(f"hook_budget: command {cmd!r} names unknown channel(s) {unknown}")
        total = sum(CHANNEL_BUDGET_BYTES[c] for c in chans)
        if total > HOOK_COMMAND_BUDGET_BYTES:
            raise ValueError(f"hook_budget: command {cmd!r} budget {total} B exceeds the "
                             f"per-command {HOOK_COMMAND_BUDGET_BYTES} B (0.95 x R0's cap)")
    carried = {c for chans in HOOK_COMMAND_CHANNELS.values() for c in chans}
    missing = sorted(set(CHANNEL_BUDGET_BYTES) - carried)
    if missing:
        raise ValueError(f"hook_budget: channel(s) {missing} belong to no hook command")
    for ev, v in NON_RMX_RESERVE_BYTES.items():
        if v % 512:
            raise ValueError(f"hook_budget: NON_RMX_RESERVE_BYTES[{ev!r}] = {v} is not a "
                             f"multiple of 512")
    # R0 (B): an event's split is over ITS producers, each share a hard cap the producer
    # enforces on itself -- so a share is a known channel and never above that channel's cap.
    if set(EVENT_SPLIT) != set(NON_RMX_RESERVE_BYTES):
        raise ValueError(f"hook_budget: EVENT_SPLIT events {sorted(EVENT_SPLIT)} != "
                         f"NON_RMX_RESERVE_BYTES events {sorted(NON_RMX_RESERVE_BYTES)}")
    for ev, split in EVENT_SPLIT.items():
        for c, share in split.items():
            if c not in CHANNEL_BUDGET_BYTES:
                raise ValueError(f"hook_budget: EVENT_SPLIT[{ev!r}] names unknown channel {c!r}")
            if share > CHANNEL_BUDGET_BYTES[c]:
                raise ValueError(f"hook_budget: EVENT_SPLIT[{ev!r}][{c!r}] = {share} B exceeds "
                                 f"the channel's own cap {CHANNEL_BUDGET_BYTES[c]} B")
    placed = {c for split in EVENT_SPLIT.values() for c in split} | set(_NON_R0_EVENT_CHANNELS)
    unplaced = sorted(set(CHANNEL_BUDGET_BYTES) - placed)
    if unplaced:
        raise ValueError(f"hook_budget: channel(s) {unplaced} sit on no EVENT_SPLIT event")
    # R0 (C)'s floor: a recall payload under MIN_USEFUL_RECALL_BYTES is not worth printing.
    for c in _RECALL_CHANNELS:
        if CHANNEL_BUDGET_BYTES[c] < MIN_USEFUL_RECALL_BYTES:
            raise ValueError(f"hook_budget: recall channel {c!r} budget "
                             f"{CHANNEL_BUDGET_BYTES[c]} B is under MIN_USEFUL_RECALL_BYTES "
                             f"{MIN_USEFUL_RECALL_BYTES} B")


# Channels on no R0 outcome event: none since the PreCompact recall channel was retired
# (task-compaction-as-handoff, L202 #m-4). The recall channels are the `memory recall --pack`
# producers.
_NON_R0_EVENT_CHANNELS: "tuple[str, ...]" = ()
_RECALL_CHANNELS = ("prompt_recall", "session_start")


_check_tables()


def env_override() -> "int | None":
    """`RMX_HOOK_BUDGET_BYTES` as an int, None when unset or empty. A set, non-integer (or
    non-positive) value RAISES `ValueError` naming the variable (R1: never a silent fallback
    to the table)."""
    raw = os.environ.get(ENV_VAR)
    if raw is None or raw.strip() == "":
        return None
    try:
        n = int(raw.strip())
    except ValueError:
        raise ValueError(f"{ENV_VAR}={raw!r} is not an integer byte count") from None
    if n <= 0:
        raise ValueError(f"{ENV_VAR}={raw!r} must be a positive byte count")
    return n


def budget(channel: str) -> int:
    """The byte budget of `channel`: `RMX_HOOK_BUDGET_BYTES` when set (it overrides EVERY
    channel), else the table. An unknown channel raises `ValueError` (a caller bug)."""
    if channel not in CHANNEL_BUDGET_BYTES:
        raise ValueError(f"hook_budget: unknown channel {channel!r}; known: "
                         f"{', '.join(sorted(CHANNEL_BUDGET_BYTES))}")
    env = env_override()
    return env if env is not None else CHANNEL_BUDGET_BYTES[channel]


def resolve(channel: str, max_bytes: "int | None") -> int:
    """An explicit `--max-bytes` / verb `max_bytes` wins; else `budget(channel)`. A
    non-positive explicit value raises `ValueError`."""
    if max_bytes is None:
        return budget(channel)
    n = int(max_bytes)
    if n <= 0:
        raise ValueError(f"max_bytes must be a positive byte count, got {max_bytes!r}")
    return n


def nbytes(text: str) -> int:
    """UTF-8 byte length -- THE unit."""
    return len(text.encode("utf-8"))


def clip_utf8(text: str, max_bytes: int) -> str:
    """`text` cut to at most `max_bytes` UTF-8 bytes on a character boundary. Used only for a
    trailer or an error line that cannot fit whole: a payload is never over N, never empty."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max(0, max_bytes)].decode("utf-8", "ignore")


@dataclass(frozen=True)
class Fitted:
    """`fit_blocks`' answer: the text, how many blocks were kept (a PREFIX of the input) and
    dropped, and the text's UTF-8 byte length."""
    text: str
    kept: int
    dropped: int
    payload_bytes: int


def fit_blocks(blocks: "Sequence[str]", max_bytes: int, *,
               trailer: "Callable[[int], str]") -> Fitted:
    """Fit `blocks` (in the given order) into `max_bytes` UTF-8 bytes, WHOLE blocks only.

    - Everything fits: the blocks joined, no trailer.
    - Otherwise: the longest PREFIX of blocks that leaves room for the one-line trailer
      `trailer(dropped)`, then that line. A block is never cut and a later block never jumps an
      earlier one that did not fit (render order is the producer's ranking).
    - Not even the trailer fits: the trailer alone, clipped on a character boundary -- the
      payload is never over N and never empty.

    The trailer goes on its own line: a newline is inserted before it when the kept text does
    not end with one. Blocks carry their own separators. Pure."""
    if max_bytes <= 0:
        raise ValueError(f"fit_blocks: max_bytes must be positive, got {max_bytes!r}")
    sizes = [nbytes(b) for b in blocks]
    if sum(sizes) <= max_bytes:
        text = "".join(blocks)
        return Fitted(text, len(blocks), 0, nbytes(text))
    used = 0
    kept = 0
    n = len(blocks)
    for i, sz in enumerate(sizes):
        sep = 0 if blocks[i].endswith("\n") else 1
        line = nbytes(trailer(n - (i + 1)))
        if used + sz + sep + line > max_bytes:
            break
        used += sz
        kept = i + 1
    head = "".join(blocks[:kept])
    tail = trailer(n - kept)
    if head and not head.endswith("\n"):
        head += "\n"
    text = head + tail
    if nbytes(text) > max_bytes:
        # Only reachable with kept == 0: the trailer alone is over N.
        text = clip_utf8(tail, max_bytes)
        kept = 0
    return Fitted(text, kept, n - kept, nbytes(text))
