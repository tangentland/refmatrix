---
gmd: "0.1"
id: sample-skill
title: "Sample skill: shipping a release"
tags: [instruction-unit, sample, task-I1.b1]
name: sample-skill
description: "Ship a release: the checklist sample-gate delivers before `shipit --prod`."
unit:
  kind: skill
  bind:
    - event: PreToolUse
      tool: Edit
      match:
        file_path: '/deploy/[^/]+[.]ya?ml$'
      prefilter: 'deploy/'
  priority: 10
  census: [R906]
  fixtures:
    fire:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/deploy/prod.yaml", old_string: "a", new_string: "b"}
    pass:
      - envelope:
          hook_event_name: PreToolUse
          session_id: fixture-session
          tool_name: Edit
          tool_input: {file_path: "/w/app/src/deploy.py", old_string: "a", new_string: "b"}
---

# Sample skill {#root}

SAMPLE-SKILL-TEXT: how a release is shipped.

## Checklist {#checklist}

1. SKILL-CHECKLIST-SENTINEL: run `shipit --dry-run` and read its plan.
2. Tag the release commit.

## Background {#background}

SKILL-BACKGROUND-SENTINEL: not part of the checklist.
