#!/usr/bin/env python3
"""p20-0 structural validation harness — memory-driven action classifier.

WHAT THIS IS
------------
The deterministic pass/fail ORACLE for the p20-0 guardrail compiler. It validates
that guardrail memories have been compiled into the native Claude Code auto-mode
block
(`.claude/settings.local.json -> autoMode.{hard_deny,soft_deny,allow,environment}`)
at the correct tiers, with the `"$defaults"` sentinel preserved.

This file does NOT build or run the compiler; it only reads the compiled result.

VERDICT MECHANISM: STRUCTURAL
-----------------------------
The named CLI surface is `claude auto-mode config` + `claude auto-mode critique`.
On the installed CLI those do NOT work as a config-inspection surface:
`config`/`critique` are swallowed as prompt tokens, and piping input to
`claude auto-mode` SPAWNS A LIVE AGENTIC SESSION WITH TOOLS. That is unsafe to use
as a validation mechanism.

So this harness uses the STRUCTURAL fallback: assert the compiled `autoMode` arrays
contain the expected rule prose at the expected tier, that `"$defaults"` is
preserved, that no case's rule leaks into a forbidden (blocking) tier, and that no
duplicate rules exist (idempotency). It is hermetic (reads one JSON file) and
spawns no session.

If a future CLI exposes a real per-payload classify surface, add a `--live` mode
that classifies each corpus `command` and asserts `expected_decision` (already in
the corpus).

CONTRACT IMPOSED ON THE SEED PROSE (so the oracle bites without being brittle)
------------------------------------------------------------------------------
Each golden case's `reason_contains` is a list of substrings that must ALL appear
(case-insensitive) inside a SINGLE compiled rule string in the expected tier array.
The seed `guardrail` memories' prose must therefore contain these concept tokens:
  hard_deny  externalize -> "off-machine"
  hard_deny  revert      -> "uncommitted"
  allow      recon       -> "read-only" + "recon"

TIER -> ARRAY MAP
-----------------
  hard_deny -> autoMode.hard_deny
  soft_deny -> autoMode.soft_deny        (unused by the seed set; if present must keep $defaults)
  allow     -> autoMode.allow
  advise    -> autoMode.environment  (preferred)  OR  autoMode.advise  (accepted alt)

USAGE
-----
  python3 .claude/p20-0/validate.py                 # validate repo settings.local.json
  python3 .claude/p20-0/validate.py --settings PATH # validate a candidate compiled file
Exit 0 = GREEN (all checks pass); exit 1 = RED (>=1 check fails).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_SETTINGS = os.path.join(REPO, ".claude", "settings.local.json")
CORPUS = os.path.join(HERE, "golden_cases.jsonl")

DEFAULTS_SENTINEL = "$defaults"

# tier -> list of acceptable array names (first is preferred)
TIER_ARRAYS = {
    "hard_deny": ["hard_deny"],
    "soft_deny": ["soft_deny"],
    "allow": ["allow"],
    "advise": ["environment", "advise"],
}
# arrays the corpus actively populates or the compiler always materializes
# (must exist + carry $defaults for GREEN)
REQUIRED_ARRAYS = ["hard_deny", "allow", "environment"]
CANONICAL_ARRAYS = ["hard_deny", "soft_deny", "allow", "environment", "advise"]

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RST = "\033[0m"


def _c(txt: str, color: str) -> str:
    if not sys.stdout.isatty():
        return txt
    return f"{color}{txt}{RST}"


def load_corpus(path: str):
    cases = []
    meta = None
    with open(path, "r", encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "_meta" in obj:
                meta = obj
                continue
            if "id" not in obj:
                raise ValueError(f"{path}:{ln}: corpus row missing 'id'")
            cases.append(obj)
    return meta, cases


def load_automode(path: str):
    if not os.path.exists(path):
        return None, f"settings file not found: {path}"
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("autoMode"), None


def _array(automode, name):
    """Return the array named `name` as a list, or None if absent."""
    if not isinstance(automode, dict):
        return None
    val = automode.get(name)
    return val if isinstance(val, list) else None


def _rule_matches(rule, tokens):
    if not isinstance(rule, str):
        return False
    low = rule.lower()
    return all(t.lower() in low for t in tokens)


def _tier_hit(automode, tier, tokens):
    """True if some rule in any acceptable array for `tier` contains all tokens."""
    for arr_name in TIER_ARRAYS[tier]:
        arr = _array(automode, arr_name) or []
        if any(_rule_matches(r, tokens) for r in arr):
            return True, arr_name
    return False, None


class Report:
    def __init__(self):
        self.rows = []  # (ok, name, detail)

    def add(self, ok, name, detail=""):
        self.rows.append((bool(ok), name, detail))

    @property
    def ok(self):
        return all(ok for ok, _, _ in self.rows)

    def print(self):
        fails = [r for r in self.rows if not r[0]]
        for ok, name, detail in self.rows:
            tag = _c("PASS", GREEN) if ok else _c("FAIL", RED)
            line = f"  [{tag}] {name}"
            if detail:
                line += _c(f"  — {detail}", DIM)
            print(line)
        print()
        n = len(self.rows)
        npass = n - len(fails)
        if fails:
            print(_c(f"VERDICT: RED  ({npass}/{n} checks pass, {len(fails)} FAIL)", RED))
        else:
            print(_c(f"VERDICT: GREEN  ({npass}/{n} checks pass)", GREEN))


def main():
    ap = argparse.ArgumentParser(description="p20-0 structural validation harness")
    ap.add_argument("--settings", default=DEFAULT_SETTINGS,
                    help="path to the compiled settings.local.json (default: repo)")
    ap.add_argument("--corpus", default=CORPUS)
    args = ap.parse_args()

    _meta, cases = load_corpus(args.corpus)
    automode, err = load_automode(args.settings)

    print(_c("p20-0 action-classifier — structural validation", ""))
    print(_c("  verdict mechanism : STRUCTURAL", DIM))
    print(_c(f"  compiled surface  : {args.settings}#autoMode", DIM))
    print(_c(f"  corpus            : {args.corpus} ({len(cases)} cases)", DIM))
    print()

    rep = Report()

    # ---- Global checks -----------------------------------------------------
    # G1: autoMode present & is an object.
    g1 = isinstance(automode, dict)
    rep.add(g1, "G1 autoMode block present",
            "" if g1 else (err or "autoMode key missing from settings.local.json"))

    # G2: $defaults preserved in every required array; required arrays exist.
    for name in REQUIRED_ARRAYS:
        arr = _array(automode, name)
        if arr is None:
            rep.add(False, f"G2 array '{name}' exists", "array missing")
        else:
            rep.add(DEFAULTS_SENTINEL in arr, f"G2 '$defaults' preserved in '{name}'",
                    "" if DEFAULTS_SENTINEL in arr else f"'{DEFAULTS_SENTINEL}' not in {name}")
    # soft_deny is unused by the seed set, but if present must keep $defaults.
    sd = _array(automode, "soft_deny")
    if sd is not None:
        rep.add(DEFAULTS_SENTINEL in sd, "G2 '$defaults' preserved in 'soft_deny' (if present)")

    # G3: well-formedness (critique surrogate) — arrays are lists of non-empty strings.
    wf_ok = True
    wf_detail = ""
    if isinstance(automode, dict):
        for name in CANONICAL_ARRAYS:
            arr = _array(automode, name)
            if arr is None:
                continue
            for r in arr:
                if not isinstance(r, str) or not r.strip():
                    wf_ok = False
                    wf_detail = f"non-string/empty entry in '{name}'"
    else:
        wf_ok = False
        wf_detail = "no autoMode object"
    rep.add(wf_ok, "G3 rules well-formed (critique surrogate)", wf_detail)

    # G4: idempotency — no duplicate rule strings within any array.
    idem_ok = True
    idem_detail = ""
    if isinstance(automode, dict):
        for name in CANONICAL_ARRAYS:
            arr = _array(automode, name)
            if arr is None:
                continue
            strs = [r for r in arr if isinstance(r, str)]
            if len(strs) != len(set(strs)):
                idem_ok = False
                idem_detail = f"duplicate rule(s) in '{name}'"
    else:
        idem_ok = False
        idem_detail = "no autoMode object"
    rep.add(idem_ok, "G4 idempotent (no duplicate rules)", idem_detail)

    # ---- Per-case checks ---------------------------------------------------
    print(_c("  Per-case tier assertions:", ""))
    for case in cases:
        cid = case["id"]
        tier = case["expected_tier"]
        tokens = case.get("reason_contains", [])
        hit, arr_name = _tier_hit(automode, tier, tokens)
        if hit:
            detail = f"tier={tier} in '{arr_name}' matched {tokens}"
        else:
            detail = f"expected tier={tier} rule matching {tokens} NOT FOUND"
        # not_in_tiers: the same rule must NOT appear in a forbidden (blocking) tier.
        leaked = None
        for ftier in case.get("not_in_tiers", []):
            fhit, farr = _tier_hit(automode, ftier, tokens)
            if fhit:
                leaked = farr
        if leaked:
            hit = False
            detail = f"rule {tokens} LEAKED into forbidden tier '{leaked}'"
        rep.add(hit, f"case {cid}", detail)

    print()
    rep.print()
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
