---
name: ch-test-gen
description: Generate tests following Docker-only execution, mock governance, and the project's test tiers
argument-hint: [--file FILE] [--type unit|integration|e2e|contract|scenario] [--tier backend|ui-unit|ui-browser|e2e]
allowed-tools: [Task, Read, Write, Edit, Bash, Glob, Grep]
model: inherit
enabled: true
---

# Test Generator

Generate tests following the project's testing architecture, mock governance, and Docker-only
execution rules. Customize the tiers below to match your stack.

## Test Tiers

### Tier: Backend (pytest in Docker)

**Execution:** ALL backend tests run in the Docker dev container — never on the host.

```bash
.venv-eval/bin/python -m pytest <path> -v 2>&1 | tee workflow/review-output/pytest.log
```

**Rules:**
- System-dependent tests MUST run — never `--ignore` them. If imports fail, the container env is
  broken; recreate `.venv-eval` (see .claude/PROJECT_PROFILE.md §commands) rather than skipping tests.
- Tests go in `tests/` mirroring `src/refmatrix/` structure.
- Use `conftest.py` fixtures for shared setup.

**Markers:**
- `@pytest.mark.scenario` — workflow / integration tests
- `@pytest.mark.contract` — API response-shape validation
- No custom markers without updating `pyproject.toml`.

### Tier: UI Unit (jsdom) — *if the project has a frontend*

**File pattern:** `*.test.tsx` / `*.test.ts`
**Run:** `cd ui && npx vitest run --project unit`
- Standard component tests with jsdom. Mock browser APIs as needed.

### Tier: UI Browser Mode (real Chromium) — *if applicable*

**File pattern:** `*.browser.test.tsx`
**Run:** `cd ui && npx vitest run --project browser`
- Required for components that need real DOM measurement, Canvas, or layout. No jsdom mocks.

### Tier: E2E (full-stack) — *if applicable*

**File pattern:** `ui/e2e/*.spec.ts`
**Run:** `cd ui && npm run test:e2e`
- Runs against the full app. Authenticate via the real auth flow (dev-mode fallback) — no mock auth.
- Required for new user workflows.

## Mock Governance

Every mock in test code must be classified in `workflow/test_mock_registry.md`:

| Classification | Meaning | Lifetime |
|----------------|---------|----------|
| `external` | External library, platform API, third-party service | Permanent |
| `internal-active` | Internal subsystem with an existing implementation | **Must graduate** to real impl |
| `internal-pending` | Internal subsystem not yet built | Temporary until built |

**When generating tests:**
1. Check `workflow/test_mock_registry.md` — is the dependency already registered?
2. Mocking an external dep → register as `external`.
3. Mocking an internal subsystem → if a real impl exists in `src/refmatrix/`, use it (or flag
   for graduation); otherwise register as `internal-pending` with a graduation target.
4. New auth-protected endpoints → MUST include a real-auth test (no dependency overrides).
5. New UI-facing API responses → MUST include a contract test (`@pytest.mark.contract`).

## Execution

1. Read the target file(s) to understand the code.
2. Check existing tests — don't duplicate coverage.
3. Check `workflow/test_mock_registry.md` for existing classifications.
4. Generate tests following the tier rules above.
5. Register any new mocks.
6. Verify tests pass (tee backend output to `workflow/review-output/`).

## Output

- Write test files to the correct location for their tier.
- Update `workflow/test_mock_registry.md` if new mocks were introduced.
- Report test count and pass/fail status; flag any mock-governance violations found.
