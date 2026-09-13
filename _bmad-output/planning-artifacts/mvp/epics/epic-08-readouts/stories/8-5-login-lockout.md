---
title: 'Login lockout'
type: 'feature'
created: '2026-09-11'
status: 'done'
baseline_revision: '45630153fe9fd810f2cf2c13869fb3015b4bf255'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      "1 attempts left" is grammatically wrong when n=1; should be "1 attempt left"
    evidence: |-
      The spec prescribes the exact format string `token rejected — {n} attempts left` with no
      singular form, so the message "token rejected — 1 attempts left" is spec-compliant but
      grammatically incorrect. Fixing it requires amending the intent-contract.
    severity: low
  - summary: >-
      `workers: 1` makes the pre-existing `fullyParallel: true` a misleading no-op
    evidence: |-
      With one Playwright worker all tests are sequentially scheduled regardless of fullyParallel.
      The setting was pre-existing (workers was 2 before this story); reducing workers to 1 made
      it inoperative. Removing fullyParallel would be a cleanup-only change.
    severity: low
  - summary: >-
      `data-lockout` attribute on the form element is not queried by any test
    evidence: |-
      The spec's Code Map planned to use it for e2e assertions; the actual e2e tests instead rely
      on `data-testid="login-locked"` and the `disabled` property. The attribute is harmless but
      dead markup.
    severity: low
  - summary: >-
      `locked_until` returns `entries[MAX-1]` without sorting; non-monotonic clock gives wrong expiry
    evidence: |-
      `windowEntries` preserves insertion order. If `record_failure` were called with a
      non-monotonic `now`, the 5th stored entry would not be the most-recent failure and the
      computed expiry would be wrong. Production uses `Date.now()` (monotonic); unit tests use
      explicit increasing timestamps. Theoretical risk only.
    severity: low
  - summary: >-
      `clearIpCounter` in beforeEach does not assert the login succeeded
    evidence: |-
      If the IP were locked when clearIpCounter runs, the correct-token submit receives FORBIDDEN
      and does not call clear(ip); the function returns without having reset the counter, and the
      next test starts from a dirty state with no warning. The current test order (locking test is
      last) prevents this, but it is fragile if more tests are added after the locking test.
    severity: low
  - summary: >-
      A successful login from any source clears the shared '0.0.0.0' fallback bucket
    evidence: |-
      When context.clientAddress is undefined (e.g. reverse proxy that strips X-Forwarded-For),
      all clients share the '0.0.0.0' key. A single successful login from any one of them calls
      clear('0.0.0.0') and resets the lockout counter for every other client in that bucket,
      including potentially locked ones. The fallback is spec-prescribed; documenting this
      limitation would help operators who deploy behind a proxy.
    severity: medium
  - summary: >-
      In-memory counters are not shared across process instances; multi-instance deployments allow up to 5 wrong tokens per instance
    evidence: |-
      The module is intentionally in-process only (spec constraint). Each process independently
      counts failures; an attacker targeting a multi-instance cluster could make up to
      5 × N attempts before any instance locks the IP. The module comment documents the
      per-process constraint but not its security implication for clustered deployments.
    severity: low
  - summary: >-
      The `other` Playwright project has no dependency on `login-lockout`; parallelism risk if workers > 1 in the future
    evidence: |-
      With workers: 1 all projects run sequentially and there is no contamination. If workers
      is ever raised, the `other` project could run concurrently with `login-lockout` and
      accumulate failures on the shared 127.0.0.1 counter. Adding
      `dependencies: ['login-lockout']` to the `other` project would make the ordering
      explicit.
    severity: low
  - summary: >-
      No e2e test submits a correct token while the IP is locked
    evidence: |-
      Matrix row "Correct token while locked" is not exercised as a standalone e2e scenario.
      The action's early-exit on non-null locked_until prevents reaching the token comparison,
      so a correct token receives the same FORBIDDEN response. Testing this directly requires
      reaching the locked state and then bypassing the disabled UI, which the clearIpCounter
      mechanism cannot support (it is called before the lock, and calling it after locks the IP
      indefinitely). The Design Notes document this structural limitation.
    severity: low
  - summary: >-
      Button.astro href-variant ignores the disabled prop; link buttons remain fully clickable when disabled
    evidence: |-
      The disabled prop is applied to the <button> branch only. An <a> link rendered by Button
      when href is provided is not given aria-disabled or pointer-events:none when disabled is
      true. Current usage in the login page passes no href, so this does not affect story 8-5;
      it is a pre-existing gap exposed by the new prop.
    severity: low
  - summary: >-
      Adding further wrong-token tests to login.spec.ts could push the shared IP counter past the 5-failure lockout threshold
    evidence: |-
      login.spec.ts currently makes 2 wrong-token submissions before a correct-token test resets
      the counter, well under the 5-failure threshold. No structural guard prevents a future
      contributor from adding additional wrong-token scenarios that push the counter to 5,
      causing login.spec.ts's own rejection-message assertions to observe the locked state and
      fail unexpectedly.
    severity: low
---

<intent-contract>

## Intent

**Problem:** The login form has no rate-limiting; an attacker can guess `ORCHESTRATOR_TOKEN` at will.

**Approach:** Add a pure in-memory lockout module (`src/lib/lockout.ts`) with an injectable clock; integrate it into the login Action so wrong tokens decrement a per-IP counter (shown in the rejection line) and the fifth failure within 15 minutes locks the IP for 15 minutes with the input and button disabled.

## Boundaries & Constraints

**Always:**
- Counter lives in `src/lib/lockout.ts` only; `record_failure(ip, now)`, `remaining(ip, now)`, `locked_until(ip, now)`, `clear(ip)` accept a plain `number` timestamp so unit tests can inject a fake clock.
- Rolling 15-minute window (`WINDOW_MS = 900_000`); at 5 failures the IP is locked until the 5th failure timestamp + `WINDOW_MS`; a success calls `clear(ip)`.
- Lockout check runs before token inspection; a locked IP never reaches the token comparison.
- Rejection copy: `token rejected — {n} attempts left` (n = `5 − failures`, in red). Locked copy: `too many attempts — try again in {m} min` (red, disabled input and submit button). Exact strings, no other wording.
- `data-testid="login-rejected"` remains on an inner `<span>` containing ONLY the text `token rejected`; the attempts fragment ` — {n} attempts left` is a sibling `<span>` on the same visual line. This preserves the pre-existing `toHaveText('token rejected')` assertions in `login.spec.ts` (lines 95 and 116), which must not be modified (AGENTS.md).
- `context.clientAddress ?? '0.0.0.0'` for the IP key; `Date.now()` passed as `now` to all lockout calls in the action.
- `Button.astro` gains `disabled?: boolean` (no other prop changes).
- Locked state: Action throws `FORBIDDEN`; wrong-token state throws `UNAUTHORIZED`; `login.astro` detects `result?.error?.code === 'FORBIDDEN'` to branch between the two visual modes.

**Block If:**
- `context.clientAddress` is not typed on `ActionAPIContext` in the installed Astro version (confirm before implementing — the subagent confirmed it is available).

**Never:**
- Per-IP lockout persisted to the database or disk; this is in-process memory only.
- Modify or delete any existing test file.
- Change the `WINDOW_MS` or `MAX` constants to a shorter value to help tests; unit tests inject a fake clock instead.
- Add a reset endpoint or test-only bypass; unit tests use the injectable clock.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|-----------------|----------------|
| 4th wrong token | 4 failures in window | `token rejected — 1 attempts left` in red; input enabled | — |
| 5th wrong token | 5th failure pushes count to MAX | `too many attempts — try again in 15 min`; input + button disabled | — |
| Correct token while locked | Locked IP, correct token submitted | Same locked message, no cookie, no redirect | — |
| Window elapsed, correct token | `locked_until` returns null (5 failures expired) | Login succeeds, counter cleared | — |
| Correct token after 2 failures | 2 failures then success | Login succeeds; next wrong token shows `token rejected — 4 attempts left` | — |
| IP unknown / first failure | Fresh state or cleared | `token rejected — 4 attempts left` | — |
| `clientAddress` absent | `context.clientAddress` is undefined | Uses fallback `'0.0.0.0'`; lockout still applies to that bucket | — |

</intent-contract>

## Code Map

- `web-client/src/lib/lockout.ts` — NEW; module-level `Map<string, number[]>` (failure timestamps per IP); `WINDOW_MS=900_000`, `MAX=5`; `windowEntries(ip,now)` filters to `t > now-WINDOW_MS`; `record_failure` appends `now`; `remaining` = `MAX - windowEntries.length`; `locked_until` = `entries[MAX-1] + WINDOW_MS` when `entries.length >= MAX`, else `null`; `clear` deletes the key
- `web-client/src/actions/login.ts:17-37` — current handler; add imports from `../lib/lockout`; at top of handler: `const ip = context.clientAddress ?? '0.0.0.0'; const now = Date.now()`; before token check: call `locked_until(ip, now)` → throw `FORBIDDEN` with `too many attempts — try again in ${m} min`; on wrong token: `record_failure(ip,now)`, compute `r = remaining(ip,now)`; if `r === 0` throw `FORBIDDEN` else throw `UNAUTHORIZED` with `token rejected — ${r} attempts left`; on success: `clear(ip)` before `context.cookies.set`
- `web-client/src/pages/login.astro:23-33` — frontmatter: add `const locked = result?.error?.code === 'FORBIDDEN'`; change `const rejected = Boolean(result?.error)` to `const rejected = Boolean(result?.error) && !locked`; add `const attemptsText = (result?.error?.message ?? '').replace(/^token rejected/, '')` (gives ` — N attempts left` or empty)
- `web-client/src/pages/login.astro:50` — form element: add `data-lockout={locked}` attribute (used by e2e assertions only); input at line 52: add `disabled={locked}`
- `web-client/src/pages/login.astro:61` — `<Button>` call: add `disabled={locked}`
- `web-client/src/pages/login.astro:64-74` — rejection paragraph: replace with three-branch conditional: `locked` → `<p class="rejected" data-testid="login-locked">{message}</p>`; `rejected` → `<p class="rejected"><span data-testid="login-rejected">token rejected</span><span data-testid="login-attempts">{attemptsText}</span></p>`; else → existing hint paragraph unchanged
- `web-client/src/components/Button.astro:15-23` — add `disabled?: boolean` to Props interface; destructure it; add `disabled={disabled}` to the `<button>` element at line 32; add `.button:disabled { opacity: 0.4; cursor: default; pointer-events: none; }` to the scoped style
- `web-client/tests/e2e/login.spec.ts` — DO NOT MODIFY; `toHaveText('token rejected')` at lines 95 and 116 targets the `<span data-testid="login-rejected">` which contains only `token rejected` — preserved by the two-span approach
- `web-client/tests/unit/lockout.test.ts` — NEW; Vitest unit tests for all four brief ACs using injected `now` values; test `remaining`, `locked_until`, `clear`, rolling-window expiry
- `web-client/tests/e2e/login-lockout.spec.ts` — NEW; `test.use({ storageState: NO_SESSION })`; `test.describe.serial` to prevent within-file parallelism; `beforeEach` uses a separate browser context to submit the correct token and clear the IP counter before each scenario; scenarios: (a) 4 wrong tokens → check `login-rejected` text and sibling attempts text; (b) 5th wrong token → check `login-locked` text, input `disabled`, button `disabled`; (c) correct token after 2 failures → success redirect; next wrong token shows `4 attempts left`; AC 3 (window elapsed, fake clock) is covered by unit tests only — server clock is not controllable from the browser in e2e

## Tasks & Acceptance

**Execution:**

1. `web-client/tests/unit/lockout.test.ts` — NEW (TDD: write first, all tests fail until task 2); cover: initial state (remaining=5, locked_until=null); 4 failures (remaining=1, locked_until=null); 5th failure (remaining=0, locked_until=T5+WINDOW_MS); failures expire after WINDOW_MS (remaining=5 again); clear resets counter; rolling window: failure outside window not counted
2. `web-client/src/lib/lockout.ts` — NEW; export `record_failure(ip, now)`, `remaining(ip, now)`, `locked_until(ip, now)`, `clear(ip)`; no external imports; use module-level `Map<string, number[]>`; makes task 1 tests pass
3. `web-client/src/components/Button.astro` — add `disabled?: boolean` to Props; pass to `<button disabled={disabled}>`; add `.button:disabled { opacity: 0.4; cursor: default; pointer-events: none; }` scoped style rule
4. `web-client/src/actions/login.ts` — import lockout functions; add `const ip = context.clientAddress ?? '0.0.0.0'; const now = Date.now()` at top of handler; locked check before token compare (throw FORBIDDEN); count-decrement on wrong token (throw UNAUTHORIZED with count, or FORBIDDEN when remaining hits 0); clear on success before cookie
5. `web-client/src/pages/login.astro` — update frontmatter: add `const locked = result?.error?.code === 'FORBIDDEN'`; change `rejected` to exclude locked; add `const message = result?.error?.message ?? ''` and `const attemptsText = message.replace(/^token rejected/, '')`; add `disabled={locked}` to `<input>` and `<Button>`; replace rejection paragraph with: locked → `<p class="rejected" data-testid="login-locked">{message}</p>`; rejected → `<p class="rejected"><span data-testid="login-rejected">token rejected</span><span data-testid="login-attempts">{attemptsText}</span></p>`; else → existing hint unchanged
6. `web-client/tests/e2e/login-lockout.spec.ts` — NEW; `test.use({ storageState: NO_SESSION })`; `test.describe.serial`; `beforeEach` uses a separate browser context to submit the correct token (clears IP counter); covers ACs 1, 2, 4

**Acceptance Criteria:**
- Given four wrong tokens in a minute, when the fourth response renders, then `[data-testid="login-rejected"]` text is `token rejected` and `[data-testid="login-attempts"]` text is ` — 1 attempts left`; input and button are enabled
- Given a fifth wrong token, when submitted, then `[data-testid="login-locked"]` text is `too many attempts — try again in 15 min`; `[data-testid="login-token"]` has `disabled`; `[data-testid="login-submit"]` has `disabled`; a correct token submitted while locked is refused with the same line
- Given the window elapsed (unit test, fake clock), when `locked_until(ip, now + WINDOW_MS + 1)` is called, then it returns `null` and `remaining` returns 5
- Given a correct token after two failures, when submitted, then redirect to `/`; the next wrong token from the same IP shows ` — 4 attempts left`

## Spec Change Log

## Review Triage Log

### 2026-09-12 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 0
- defer: 11: (high 0, medium 1, low 10)
- reject: 4: (high 0, medium 0, low 4)
- addressed_findings:
  - none

## Design Notes

**Two-span display for `login-rejected`:** The pre-existing `login.spec.ts` asserts `toHaveText('token rejected')` on `[data-testid="login-rejected"]`. Playwright's `toHaveText` is an exact-content match; placing the count in a sibling `<span>` (no testid) keeps the inner span's text content as `token rejected` exactly, satisfying the existing test while displaying `token rejected — N attempts left` as one visual line. The outer `<p class="rejected">` propagates the red colour to both inline spans.

**AC 3 is unit-only:** The lockout module's injectable `now` parameter lets unit tests fake clock advancement without any server-side clock API. Playwright's `page.clock` only controls the browser clock; the server's `Date.now()` cannot be controlled from the browser side, so AC 3 (window expiry) is covered exclusively by `lockout.test.ts`.

**`test.describe.serial` + `beforeEach` counter clear:** The in-memory counter is shared across all connections from 127.0.0.1 in the test server. A `beforeEach` hook logs in successfully via a separate browser context (which calls `clear(ip)`) before each lockout scenario, giving the tests a known-zero counter state. Additionally, `playwright.config.ts` is changed from `workers: 2` to `workers: 1` so login.spec.ts and login-lockout.spec.ts run serially and cannot contaminate each other's counter via parallel submissions. This also avoids the stub-backend saturation issue that originally motivated capping workers.

## Verification

**Commands:**
- `make lint` — expected: zero eslint/tsc errors
- `make test` — expected: all unit tests pass including new `lockout.test.ts`
- `make e2e-ui` — expected: `login-lockout.spec.ts` passes; `login.spec.ts` unaffected

## Auto Run Result

Status: done

**Summary:** Added per-IP in-memory login lockout to the web-client. Five wrong tokens within a 15-minute rolling window lock the IP for 15 minutes. The rejection line counts down remaining attempts; the locked state disables the input and submit button.

**Files changed:**
- `web-client/src/lib/lockout.ts` — NEW; pure in-memory lockout module with injectable clock (`record_failure`, `remaining`, `locked_until`, `clear`)
- `web-client/tests/unit/lockout.test.ts` — NEW; 6 Vitest unit tests covering all boundary conditions with fake clock injection
- `web-client/src/actions/login.ts` — added lockout check before token inspection; failure counting; FORBIDDEN on lockout; clear on success
- `web-client/src/components/Button.astro` — added `disabled?: boolean` prop; disabled button style rule
- `web-client/src/pages/login.astro` — three-branch rejection display (locked / rejected-with-count / hint); disabled input and button when locked
- `web-client/tests/e2e/login-lockout.spec.ts` — NEW; 3 serial e2e scenarios covering ACs 1, 2, 4
- `web-client/playwright.config.ts` — reduced `workers` from 2 to 1; added `projects` block to enforce `login` → `login-lockout` ordering

**Review findings:** 0 intent_gap, 0 bad_spec, 0 patch, 11 defer (1 medium, 10 low), 4 reject. No patches applied.

**Follow-up review recommendation:** false (patched: 0 high, 0 medium, 0 low; score = 0 < 5)

**Verification performed:**
- `make lint` — 0 errors (eslint, tsc, astro check, prettier, import-linter all clean)
- `make test` — 6041 backend tests passed, 1339 frontend unit tests passed (108 test files); includes all 6 new `lockout.test.ts` scenarios
- `pnpm exec playwright test login.spec.ts login-lockout.spec.ts` — 17/17 passed; pre-existing `login.spec.ts` assertions at lines 95 and 116 unaffected

**Residual risks:**
- In-memory lockout resets on server restart; an attacker who knows restart timing gets a fresh 5-attempt window
- Multi-instance deployments track counters independently (documented in deferred list)
- The `'0.0.0.0'` fallback bucket is shared across all clients when `clientAddress` is unavailable (documented in deferred list)
