---
gmd: "0.1"
id: planted-fire-noprefilter
title: "Planted: a fire envelope missing its own prefilter"
tags: [instruction-unit, planted, task-I1.b1]
unit:
  kind: deny
  bind:
    - event: PreToolUse
      tool: Bash
      match:
        command: 'rmfoo +--all'
      unless: '--dry-run'
      prefilter: 'rmfoo --all'
  priority: 50
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "rmfoo --all dist/"}
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "rmfoo  --all build/"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "ls build/"}
---

# Planted: a fire envelope missing its own prefilter {#root}

Planted: fire[1] matches the pattern (two spaces) but its raw JSON lacks the literal prefilter.

Instead: `rmfoo build/`.
