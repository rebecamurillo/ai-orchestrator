---
title: 'Claude readiness: fast auth pre-check'
type: 'bugfix'
created: '2026-09-23'
status: 'done'
route: 'one-shot'
---

## Intent

**Problem:** In subscription mode (`CLAUDE_SUBSCRIPTION_AUTH=true`), `claude -p` authenticates
through `claude login`'s own OAuth session, but the existing readiness Probe only tested the
Gateway's own key — so a missing or expired login was invisible to the Probe and was only
discovered deep into a dispatched `epic@1` readiness Run, slowly. The Operator watched "re-run
readiness" hang for minutes before it finally failed.

**Approach:** Extend `scripts/harness/claude.sh`'s existing `probe()` with a fast, no-spend
`claude auth status` check, gated on `CLAUDE_SUBSCRIPTION_AUTH`, timeout-bounded so a stalled
CLI can never slow it down. `POST /harnesses/claude/readiness` already re-checks the Probe
before dispatching (`use_cases/harness_readiness.start` → `create_run`'s live-probe gate), so a
broken login now refuses in well under a second instead of after a multi-minute Run. The full
`epic@1` diagnostic is unchanged for the case where the pre-check passes.

## Suggested Review Order

**Fast auth pre-check**

- Entry point: the new login check, gated on subscription mode, timeout-bounded via `python3` rather than the `timeout` binary.
  [`claude.sh:106`](../../scripts/harness/claude.sh#L106)

- `probe()` turns each of the check's exit codes into its own `failing_reason` instead of collapsing every cause into "not logged in".
  [`claude.sh:133`](../../scripts/harness/claude.sh#L133)

- `doctor()` (the manual `make doctor` diagnostic) gained the same check, so it can no longer report healthy while `probe()` refuses.
  [`claude.sh:126`](../../scripts/harness/claude.sh#L126)

**Operator-facing documentation**

- Names the new fast-fail behavior and the recovery step where an Operator troubleshooting subscription mode would actually look.
  [`README.md:245`](../../host/README.md#L245)

**Test coverage**

- Real bash execution against a fake `claude` executable — logged-in, logged-out, malformed output, and a stalled `auth status` call, each asserting the specific `failing_reason` and, for the stall case, a wall-clock bound.
  [`test_harness_claude_subscription_login_probe.py:91`](../../backend-api/tests/unit/test_harness_claude_subscription_login_probe.py#L91)

**Deferred**

- Two Blind Hunter findings recorded for later rather than patched now (a combined login+live-gateway test needs a fake HTTP server; the `.env` boolean comparison has no shared parsing helper).
  [`deferred-work.md`](deferred-work.md)
