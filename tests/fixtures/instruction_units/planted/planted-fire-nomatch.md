---
gmd: "0.1"
id: planted-fire-nomatch
title: "Planted: a fire envelope its pattern does not match"
tags: [instruction-unit, planted, task-I1.b1]
unit:
  kind: deny
  bind:
    - event: PreToolUse
      tool: Bash
      match:
        command: '^rmfoo +--all'
      unless: '--dry-run'
      prefilter: 'rmfoo'
  priority: 50
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "rmfoo --all build/"}
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "echo rmfoo --all"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Bash
          tool_input: {command: "ls build/"}
---

# Planted: a fire envelope its pattern does not match {#root}

Planted: fire[1] holds the prefilter but the anchored pattern does not match it.

Instead: `rmfoo build/`.
