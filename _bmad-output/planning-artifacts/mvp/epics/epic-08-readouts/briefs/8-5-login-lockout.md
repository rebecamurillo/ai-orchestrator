---
story: "8-5"
epic: 8
title: Login lockout
requirements: [FR-1 (lockout), NFR-8, UX-DR6]
binds: [AD-4]
---

# Story 8.5 — Login lockout

As the Operator,
I want repeated wrong tokens to be counted and, after five in fifteen minutes, refused for fifteen minutes,
So that the one secret of the instance cannot be guessed at leisure.

## Scope

**In:** the attempts counter in the web-client login Action, the rejection line with the remaining count, the refusal window, the disabled input, tests.
**Out:** per-IP tracking beyond the process memory `[ASSUMPTION: an in-memory counter keyed by client IP in the single Astro process is enough for one operator]`.

## Binding rules (inlined)

- **Counter.** In `src/lib/lockout.ts` (pure, injectable clock): `record_failure(ip, now)`, `remaining(ip, now)`, `locked_until(ip, now)`; failures within a rolling 15-minute window count; at 5 the ip is locked until the fifth failure + 15 minutes; a success clears the ip.
- **Lines (UX-DR6).** Wrong token: `token rejected — {n} attempts left` (n = 5 − failures, in red); locked: `too many attempts — try again in {m} min` with the input and button disabled and the form refusing submissions server-side (the Action returns the same line without checking the token).
- **Copy:** exactly those lines; no apology.

## Acceptance criteria

**Given** four wrong tokens in a minute
**When** the fourth response renders
**Then** the line reads `token rejected — 1 attempts left`.

**Given** a fifth wrong token
**When** submitted
**Then** the line reads `too many attempts — try again in 15 min`, the input is disabled, and a correct token submitted within the window is refused with the same line.

**Given** the window elapsed (fake clock)
**When** the correct token is submitted
**Then** login succeeds and the counter is cleared.

**Given** a correct token after two failures
**When** submitted
**Then** login succeeds and the next failure reads `4 attempts left`.

## Implementation notes

- `src/lib/lockout.ts` unit-tested with a fake clock; the Action reads `context.clientAddress`.
- Playwright `tests/e2e/login-lockout.spec.ts`.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

PRD FR-1 (lockout assumption: 5 failures / 15 minutes), §9. `EXPERIENCE-v1.md` §1 Login. Spine Deferred (FR-1 lockout: web-client middleware counter).
