#!/usr/bin/env python3
"""R0 probe hook: print a payload of EXACTLY N code points, with unique first/last-line markers.

Usage (as a Claude Code hook command):
    python3 payload.py <label> <n_codepoints> <kind> <tag>

kind:
    ascii  filler is a-z (1 byte, 1 UTF-16 unit per char)
    cjk    filler is U+4E2D (3 UTF-8 bytes, 1 UTF-16 unit per char)
    emoji  filler is U+1F600 (4 UTF-8 bytes, 2 UTF-16 units per char)

First line:  R0-START-<label>-<tag>
Last line:   R0-END-<label>-<tag>      (no trailing newline, so N is exact)
Optional 5th arg: a count of "\n" appended AFTER the end marker (tests whether the harness
measures raw stdout or trimmed stdout); those newlines are counted in the emitted log.

Every emission is logged to logs/emitted.jsonl next to this script (ground truth for the
analysis: code points, UTF-16 units, UTF-8 bytes, sha256), with the hook event name and the
session id read from the hook's stdin JSON.
"""
import hashlib
import json
import os
import sys
import time

FILL = {"ascii": None, "cjk": "中", "emoji": "\U0001F600"}
LINE = 80  # code points per filler line including its newline


def build(label: str, n: int, kind: str, tag: str) -> str:
    start = f"R0-START-{label}-{tag}\n"
    end = f"\nR0-END-{label}-{tag}"
    room = n - len(start) - len(end)
    if room < 0:
        raise SystemExit(f"payload.py: n={n} smaller than the markers ({len(start) + len(end)})")
    out = []
    i = 0
    while room > 0:
        width = min(LINE - 1, room)
        if kind == "ascii":
            body = "".join(chr(ord("a") + (i + k) % 26) for k in range(width))
        else:
            body = FILL[kind] * width
        out.append(body)
        room -= width
        if room > 0:
            out.append("\n")
            room -= 1
        i += 1
    text = start + "".join(out) + end
    assert len(text) == n, (len(text), n)
    return text


def main() -> None:
    as_json = "--json" in sys.argv  # wrap as hookSpecificOutput.additionalContext JSON
    if as_json:
        sys.argv.remove("--json")
    label, n, kind, tag = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    trailing_nl = int(sys.argv[5]) if len(sys.argv) > 5 else 0  # extra "\n" after the end marker
    if kind not in FILL:
        raise SystemExit(f"payload.py: unknown kind {kind!r}")
    raw = sys.stdin.read()
    try:
        ev = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"payload.py: hook stdin is not JSON: {exc}")
    text = build(label, n, kind, tag) + "\n" * trailing_nl
    data = text.encode("utf-8")
    if as_json:
        wire = json.dumps({"hookSpecificOutput": {"hookEventName": ev.get("hook_event_name"),
                                                  "additionalContext": text}}).encode("utf-8")
    else:
        wire = data
    rec = {
        "ts": time.time(),
        "label": label,
        "tag": tag,
        "kind": kind,
        "json": as_json,
        "trailing_nl": trailing_nl,
        "event": ev.get("hook_event_name"),
        "source": ev.get("source") or ev.get("trigger"),
        "session_id": ev.get("session_id"),
        "codepoints": len(text),
        "utf16_units": len(text.encode("utf-16-le")) // 2,
        "utf8_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "emitted.jsonl")
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    sys.stdout.buffer.write(wire)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
