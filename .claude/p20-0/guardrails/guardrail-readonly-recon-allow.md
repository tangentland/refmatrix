---
gmd: "0.1"
id: guardrail-readonly-recon-allow
title: "Guardrail — read-only recon is allowed, never blocked (allow)"
tags: [guardrail, allow, recon, carve-out]
metadata:
  node_type: memory
  type: guardrail
  originSessionId: 00000000-0000-0000-0000-000000000000
  created: 2026-07-06
  updated: 2026-07-06
---

# Read-only recon is allowed — never block it {#root}

Carve-out (false-block prevention): read-only reconnaissance never mutates state and must always be
permitted. This compiles to `allow`.

Guardrail (compiler-read structured block):

```yaml
guardrail:
  tier: allow
  rule: "Read-only recon is always allowed and must never be blocked: grep or rg, rmx context/query/grep, ls, git status, and cat or reading file heads never mutate state and are pure recon."
  scope:
    role: any
  match_kind: prose
  message: "Allowed: read-only recon (grep/rg, rmx, ls, git status, cat/reading heads). These never mutate state."
```

**Why:** read-only recon is exactly the encouraged behavior — orienting before acting. Blocking it
would train the model to route around the guardrail. The blocking tiers are about destructive or
off-machine actions; pure reads are explicitly carved out so they are never a false block.

**How to apply:** treat `grep`/`rg`, `rmx context/query/grep`, `ls`, `git status`, and `cat` or
reading file heads as always-allowed recon; do not nudge or block them.
