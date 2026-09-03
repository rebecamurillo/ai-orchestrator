---
story: "5-11"
epic: 5
title: Claude readiness passes end to end
requirements: [FR-14, FR-26, FR-27, FR-33, PRD §8 items 1–5, AR-27]
binds: [AD-10, AD-11]
---

# Story 5.11 — Claude readiness passes end to end

As the Operator,
I want the `claude` harness to reach `enabled` on the real host Gateway and Langfuse, with every open day-1 question answered by that run and recorded,
So that the first real epic is dispatched to a harness that has already proven the whole chain once.

## Scope

**In:** running `POST /harnesses/claude/readiness` on the compose stack against the host LiteLLM and Langfuse; resolving PRD §8 items 1–5 from what the run shows; recording the verified invocation, allowlist, cap-exit field, header behaviour, and key setup in `_bmad-output/planning-artifacts/mvp/addendum.md` §B and `host/README.md`; fixing what the run reveals in 5.1–5.8 (small, tested changes).
**Out:** codex and local (Epic 7).

## Binding rules (inlined)

- **Preconditions.** `.env` filled with real `LITELLM_BASE_URL`, `LITELLM_API_KEY` (a key generated with `key_type: llm_api`), `LITELLM_SPEND_KEY` (master or `proxy_admin_viewer`), `LANGFUSE_*`; `make up` green. If the host services are unreachable, HALT `blocked` with `blocking condition: host services unreachable: {which}`.
- **Item 1 — allowlist.** The readiness Run must reach `done` under `--permission-mode dontAsk` with `CLAUDE_ALLOWED_TOOLS`; a `blocked · no subagents` or a permission stall means the allowlist lacks `Task` or a Bash pattern; adjust `.env.example`'s default and record the final list.
- **Item 2 — trace continuity.** `attempt_observed` must find Claude Code spans under the attempt span (`TRACEPARENT` honoured); if not, record the observed behaviour and the fallback used.
- **Item 3 — skill discovery from the worktree.** The image's `~/.claude/skills/bmad-build-auto` must resolve the worktree (with its `_bmad/`) as project root; if it does not, implement the fallback: `git.worktree` copies the stubs into the worktree's git-ignored `.claude/skills/` (a small addition to 4.8 behind a setting `SKILL_STUBS_INTO_WORKTREE`).
- **Item 4 — spend and session headers coexist.** `/spend/logs/v2?end_user=&session_id=` must return the attempt's rows while Langfuse shows `session_id == run_id`; if `x-litellm-session-id` collides, switch `_query` (5.3) to the `request_tags` filter and record it.
- **Item 5 — two keys.** Confirm the harness key cannot read `/spend/logs/v2` (403) and the spend key can; record the host commands in `host/README.md`.
- **Cap-exit field.** Observe a run with `--max-budget-usd 0.01` on the fixture to learn the JSON field that marks the cap stop; set the constant in 5.7 and record it.
- **Record.** `addendum.md` §B gains a dated "Claude — verified" block: exact argv, allowlist, cap field, trace parenting result, header result, key types; `host/README.md` gains the key-generation commands.

## Acceptance criteria

**Given** the stack against the host services
**When** the readiness Run for `claude` completes
**Then** `GET /harnesses` shows `claude · enabled`, `last_readiness_at` set, and every evaluation line `ok`; the Board card reads `DON · readiness`; the Run detail's trace link opens a Langfuse trace with the attempt's Claude Code spans under the Run session; the attempt's cost is non-provisional.

**Given** the cap probe Run with `--max-budget-usd 0.01`
**When** it stops
**Then** the Run parks `budget` (not `misconfigured`), and the field that marked it is recorded in the addendum and used by 5.7.

**Given** `addendum.md` §B and `host/README.md`
**When** read
**Then** they contain the verified Claude block and the key commands, dated.

**Given** any fix made to 5.1–5.8
**When** `make lint test` runs
**Then** it is covered by a unit test and green.

## Implementation notes

- Drive the run through the API (`POST /harnesses/claude/readiness`, poll `GET /runs/{id}`); keep a transcript of the checks in the story file's Auto Run Result.
- If the allowlist needs repository-specific Bash patterns beyond `.env.example`'s default, document the rule "a target repository's patterns extend `CLAUDE_ALLOWED_TOOLS`" as a deferred per-Project setting in the addendum (do not build it).

## Verification

```bash
make up && curl -s -X POST -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" localhost:8000/api/v1/harnesses/claude/readiness
```

## Sources for detail only

PRD §8 (open questions 1–5), FR-33. Spine "Open at handoff" 1, 3, 5, 6; AD-10, AD-11. `addendum.md` §B, §H. `host/README.md`.
