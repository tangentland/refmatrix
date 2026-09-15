---
gmd: "0.1"
id: guardrail-externalize-off-machine
title: "Guardrail — never externalize project content off-machine (hard_deny)"
tags: [guardrail, hard-deny, confidentiality]
metadata:
  node_type: memory
  type: guardrail
  originSessionId: 00000000-0000-0000-0000-000000000000
  created: 2026-07-06
  updated: 2026-07-06
---

# Never externalize project content off-machine {#root}

Lane-agnostic confidentiality danger: publishing or sending project code, design, or schema to any
external host leaks confidential content. This is `hard_deny` for every actor.

Guardrail (compiler-read structured block):

```yaml
guardrail:
  tier: hard_deny
  rule: "Never externalize project content off-machine: do not publish or send project code, design, or schema to the Artifact tool or any web service. Local files and the on-machine rmx store only."
  scope:
    role: any
  match_kind: prose
  message: "Blocked: externalizing project content off-machine. Keep artifacts local (file://) and use the on-machine rmx store; the Artifact tool publishes to claude.ai."
```

**Why:** project content is confidential; the Artifact tool deploys to claude.ai (external) and web
services are off-machine. A dispatched implementer must also not externalize content — the danger is
actor-agnostic.

**How to apply:** build diagrams and pages as local files under the project; never use the Artifact
tool or a web service to move project code, design, or schema off the machine without explicit user
permission.
