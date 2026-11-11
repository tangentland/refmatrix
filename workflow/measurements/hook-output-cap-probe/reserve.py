#!/usr/bin/env python3
"""Read-only: the bytes the user's NON-rmx global hooks add per event.

Executes NOTHING from ~/.claude/hooks (caveman-activate.js writes ~/.claude/.caveman-active).
It replicates the two scripts' output strings from their source, reads the state they read
(flag file, caveman config, settings.json statusLine, the plugin's SKILL.md), and cross-checks
against what the lead's interactive transcript recorded those hooks emitting.

Producers (from ~/.claude/settings.json hooks + enabledPlugins, read 2026-11-11):
  UserPromptSubmit: caveman-mode-tracker.js twice — the standalone settings.json entry AND the
                    enabled caveman@caveman plugin's copy (byte-identical script).
  SessionStart:     caveman-activate.js twice (standalone -> fallback ruleset; plugin -> its
                    skills/caveman/SKILL.md filtered), plus the tldr daemon start (stdout to
                    /dev/null, 0 B).
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
PLUGIN = f"{HOME}/.claude/plugins/cache/caveman/caveman/ef6050c5e184"
LEAD_T = (f"{HOME}/.claude/projects/-Users-tholley-claude-tools-refmatrix/"
          "7efc36ce-3694-46b6-b30c-31160ae25396.jsonl")


def m(s):
    return f"{len(s):,} chars / {len(s.encode('utf-16-le')) // 2:,} UTF-16 / {len(s.encode()):,} B"


def mode():
    env = os.environ.get("CAVEMAN_DEFAULT_MODE")
    if env:
        return env.lower()
    cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config", "caveman",
                       "config.json")
    if os.path.exists(cfg):
        return json.load(open(cfg)).get("defaultMode", "full").lower()
    return "full"


def fallback(label, status_nudge):
    out = ("CAVEMAN MODE ACTIVE — level: " + label + "\n\n"
           "Respond terse like smart caveman. All technical substance stay. Only fluff die.\n\n"
           "## Persistence\n\n"
           "ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift. Still active if "
           "unsure. Off only: \"stop caveman\" / \"normal mode\".\n\n"
           "Current level: **" + label + "**. Switch: `/caveman lite|full|ultra`.\n\n"
           "## Rules\n\n"
           "Drop: articles (a/an/the), filler (just/really/basically/actually/simply), "
           "pleasantries (sure/certainly/of course/happy to), hedging. "
           "Fragments OK. Short synonyms (big not extensive, fix not \"implement a solution "
           "for\"). Technical terms exact. Code blocks unchanged. Errors quoted exact.\n\n"
           "Pattern: `[thing] [action] [reason]. [next step].`\n\n"
           "Not: \"Sure! I'd be happy to help you with that. The issue you're experiencing is "
           "likely caused by...\"\n"
           "Yes: \"Bug in auth middleware. Token expiry check use `<` not `<=`. Fix:\"\n\n"
           "## Auto-Clarity\n\n"
           "Drop caveman for: security warnings, irreversible action confirmations, multi-step "
           "sequences where fragment order risks misread, user asks to clarify or repeats "
           "question. Resume caveman after clear part done.\n\n"
           "## Boundaries\n\n"
           "Code/commits/PRs: write normal. \"stop caveman\" or \"normal mode\": revert. Level "
           "persist until changed or session end.")
    if status_nudge:
        out += "\n\n[STATUSLINE SETUP NEEDED ... nudge, not emitted: statusLine is set]"
    return out


def plugin_skill(label):
    body = re.sub(r"^---[\s\S]*?---\s*", "", open(f"{PLUGIN}/skills/caveman/SKILL.md").read(),
                  count=1)
    acc = []
    for line in body.split("\n"):
        t = re.match(r"^\|\s*\*\*(\S+?)\*\*\s*\|", line)
        if t:
            if t.group(1) == label:
                acc.append(line)
            continue
        e = re.match(r"^- (\S+?):\s", line)
        if e:
            if e.group(1) == label:
                acc.append(line)
            continue
        acc.append(line)
    return "CAVEMAN MODE ACTIVE — level: " + label + "\n\n" + "\n".join(acc)


def main():
    md = mode()
    label = "wenyan-full" if md == "wenyan" else md
    flag = open(f"{HOME}/.claude/.caveman-active").read().strip() \
        if os.path.exists(f"{HOME}/.claude/.caveman-active") else None
    settings = json.load(open(f"{HOME}/.claude/settings.json"))
    has_status = bool(settings.get("statusLine"))
    print(f"caveman default mode={md!r} flag file={flag!r} statusLine set={has_status} "
          f"standalone SKILL.md present={os.path.exists(HOME + '/.claude/skills/caveman/SKILL.md')} "
          f"plugin SKILL.md present={os.path.exists(PLUGIN + '/skills/caveman/SKILL.md')}")
    ac = ("CAVEMAN MODE ACTIVE (" + (flag or md) + "). "
          "Drop articles/filler/pleasantries/hedging. Fragments OK. "
          "Code/commits/security: write normal.")
    wire = json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                              "additionalContext": ac}}, separators=(",", ":"))
    print("UPS tracker (each copy): wire JSON", m(wire), "| additionalContext", m(ac))
    fb = fallback(label, not has_status)
    ps = plugin_skill(label)
    print("SS standalone activate (fallback ruleset):", m(fb))
    print("SS plugin activate (SKILL.md filtered):   ", m(ps))
    print("SS sum of both:", f"{len(fb) + len(ps):,} chars / {len((fb + ps).encode()):,} B")
    if os.path.exists(LEAD_T):
        ss = []
        ups = []
        for line in open(LEAD_T, encoding="utf-8"):
            r = json.loads(line)
            a = r.get("attachment") or {}
            if a.get("hookEvent") == "SessionStart" and "CAVEMAN" in (a.get("stdout") or ""):
                ss.append(a["stdout"])
            if a.get("type") == "hook_additional_context" and a.get("hookEvent") == \
                    "UserPromptSubmit":
                ups.append(a["content"])
        print(f"lead transcript: SessionStart caveman records={len(ss)} sizes="
              f"{[(len(s), len(s.encode())) for s in ss]} replica match="
              f"{sorted(s.strip() for s in ss) == sorted([fb.strip(), ps.strip()])}")
        shapes = {json.dumps(c): 0 for c in ups}
        for c in ups:
            shapes[json.dumps(c)] += 1
        print(f"lead transcript: UPS additionalContext records={len(ups)} distinct={len(shapes)}"
              f" entries-per-record={[len(c) for c in ups][:3]}... first={ups[0] if ups else None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
