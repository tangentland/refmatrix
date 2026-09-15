#!/usr/bin/env python3
"""p20-0 SessionStart compiler — guardrail memories -> native auto-mode arrays.

Reads the committed `guardrail`-type rmx memories (the memory plane, the source
of truth) and merges their prose rules into
`.claude/settings.local.json -> autoMode.{hard_deny,soft_deny,allow,environment}`
at the tier each memory declares. Native Claude Code auto-mode then enforces them
at the action seam. No bespoke classifier: the enforcement engine is the
platform's own auto-mode.

SELF-HARDENING LOOP: add a new guardrail memory to `.claude/p20-0/guardrails/`
and re-run this compiler; the new rule is enforced with zero new code.

DETERMINISTIC LOADER: enumerates guardrails via
`rmx memory list --type guardrail` (NOT `rmx memory recall` — recall is
semantic/session-dependent; list is deterministic), then `rmx memory get <name>`
for each full body, and parses the fenced `guardrail:` block's `tier` + `rule`.
Before listing it runs the memory bridge (`rmx ingest-gmd --as-memory`) on the
committed guardrail dir so the store reflects the on-disk source of truth
(idempotent upsert), making a lone `compile_guardrails.py` run fully
self-contained. The seed step is REQUIRED: if it fails the compile fails, loudly
— an edited guardrail that never reaches the store is a silent policy hole
(bsd-plan5-r2 #b-2-r2: the old alias call died behind `|| true`).

TIER -> ARRAY:
  hard_deny -> autoMode.hard_deny        (lane-agnostic BLOCK, any actor)
  soft_deny -> autoMode.soft_deny        (unused by the seed set)
  allow     -> autoMode.allow            (read-only recon carve-out)
  advise    -> autoMode.environment      (nudge only; never a blocking tier)

IDEMPOTENT: every compiled rule carries the MARKER suffix. Each run strips prior
MARKER-tagged entries from the managed arrays and re-adds the current set, so
re-running never duplicates and never drops the `"$defaults"` sentinel (which is
always kept first).

EFFICACY IS A KNOWN LIMITATION: whether the installed CLI enforces autoMode rules
at runtime is unverified here (see .claude/p20-0/README.md). This compiler is
validated STRUCTURALLY by .claude/p20-0/validate.py (reads the compiled JSON,
spawns nothing). Rules are inert unless the session runs in `auto` permission-mode.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SETTINGS = os.path.join(REPO, ".claude", "settings.local.json")
GUARDRAIL_DIR = os.path.join(HERE, "guardrails")

MARKER = "[auto:p20-0]"

# guardrail tier -> target autoMode array name.
TIER_ARRAY = {
    "hard_deny": "hard_deny",
    "soft_deny": "soft_deny",
    "allow": "allow",
    "advise": "environment",
}
# arrays that must always exist and carry "$defaults" so every canonical array
# composes with the platform defaults.
MATERIALIZE_ARRAYS = ["hard_deny", "soft_deny", "allow", "environment"]
DEFAULTS = "$defaults"

TIER_RE = re.compile(r"^\s*tier:\s*(\S+)\s*$")
RULE_RE = re.compile(r"^\s*rule:\s*(.+?)\s*$")


def _rmx(args: list[str], *, required: bool = False) -> str:
    """Run an rmx subcommand with a wide COLUMNS so table names never truncate.
    `required=True`: a non-zero exit aborts the compile (memory path)."""
    env = dict(os.environ, COLUMNS="400", RMX_INVOCATION_SOURCE="hook")
    proc = subprocess.run(
        ["rmx", *args], capture_output=True, text=True, env=env, check=False,
    )
    if proc.returncode != 0:
        msg = (f"compile_guardrails: `rmx {' '.join(args)}` exited "
               f"{proc.returncode}: {proc.stderr.strip()}\n")
        sys.stderr.write(msg)
        if required:
            raise SystemExit(f"compile_guardrails: guardrail seed step FAILED — "
                             f"the store may not reflect .claude/p20-0/guardrails/; "
                             f"nothing compiled")
    return proc.stdout


def sync_source() -> None:
    """Upsert the committed guardrail .md files into rmx through the memory
    bridge (idempotent, content-hash gated). Required — see `_rmx`."""
    if os.path.isdir(GUARDRAIL_DIR):
        _rmx(["ingest-gmd", "--as-memory", GUARDRAIL_DIR], required=True)


def list_guardrail_names() -> list[str]:
    """Deterministic loader: names of every `guardrail`-type memory."""
    out = _rmx(["memory", "list", "--type", "guardrail", "-n", "200"])
    names: list[str] = []
    for line in out.splitlines():
        if "│" not in line:  # only rich data rows use the │ box char
            continue
        parts = line.split("│")
        # parts: ['', ' id ', ' name ', ' mtype ', ' content ', ' tags ', '']
        if len(parts) < 4:
            continue
        rid = parts[1].strip()
        name = parts[2].strip()
        if rid.isdigit() and name:  # skip wrapped continuation rows (blank id)
            names.append(name)
    return names


def parse_guardrail_block(body: str) -> tuple[str | None, str | None]:
    """Extract the first `tier:` and `rule:` from a memory body's guardrail block."""
    tier = rule = None
    for line in body.splitlines():
        if tier is None:
            m = TIER_RE.match(line)
            if m:
                tier = m.group(1).strip().strip("\"'")
                continue
        if rule is None:
            m = RULE_RE.match(line)
            if m:
                rule = m.group(1).strip().strip("\"'")
    return tier, rule


def load_rules() -> list[tuple[str, str, str]]:
    """Return [(mem_name, tier, rule_text), ...] for every guardrail memory."""
    rules: list[tuple[str, str, str]] = []
    for name in list_guardrail_names():
        body = _rmx(["memory", "get", name])
        tier, rule = parse_guardrail_block(body)
        if not tier or not rule:
            sys.stderr.write(
                f"compile_guardrails: skipping '{name}' — missing tier/rule "
                f"(tier={tier!r} rule={rule!r})\n"
            )
            continue
        if tier not in TIER_ARRAY:
            sys.stderr.write(
                f"compile_guardrails: skipping '{name}' — unknown tier {tier!r}\n"
            )
            continue
        rules.append((name, tier, rule))
    return rules


def compile_into(automode: dict, rules: list[tuple[str, str, str]]) -> dict:
    """Merge compiled rules into the autoMode arrays, idempotently."""
    # arrays we will (re)build this run: the always-materialized set + any array a
    # rule targets.
    managed = set(MATERIALIZE_ARRAYS)
    by_array: dict[str, list[str]] = {}
    for _name, tier, rule in rules:
        arr = TIER_ARRAY[tier]
        managed.add(arr)
        by_array.setdefault(arr, []).append(f"{rule} {MARKER}")

    for arr in sorted(managed):
        existing = automode.get(arr)
        existing = existing if isinstance(existing, list) else []
        # keep user/native entries; drop this compiler's prior output (MARKER).
        preserved = [
            x for x in existing
            if not (isinstance(x, str) and MARKER in x) and x != DEFAULTS
        ]
        result = [DEFAULTS, *preserved]
        for compiled in by_array.get(arr, []):
            if compiled not in result:
                result.append(compiled)
        automode[arr] = result
    return automode


def main() -> int:
    sync_source()
    rules = load_rules()
    if not rules:
        sys.stderr.write(
            "compile_guardrails: no guardrail memories found — nothing compiled. "
            "(Did `rmx ingest-gmd --as-memory .claude/p20-0/guardrails` land rows? "
            "Is the guardrail dir populated?)\n"
        )

    if os.path.exists(SETTINGS):
        with open(SETTINGS, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = {}

    automode = data.get("autoMode")
    if not isinstance(automode, dict):
        automode = {}
    data["autoMode"] = compile_into(automode, rules)

    with open(SETTINGS, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")

    counts = {
        arr: len([x for x in data["autoMode"].get(arr, []) if MARKER in x])
        for arr in sorted(set(TIER_ARRAY.values()))
        if arr in data["autoMode"]
    }
    print(
        f"compile_guardrails: compiled {len(rules)} guardrail rule(s) into "
        f"{SETTINGS} -> autoMode {counts}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
