---
id: IMP-003
title: Answer a blocked Story in the same harness session, or restart — the operator chooses
status: accepted
accepted: 2026-09-15 — sprint-change-proposal-2026-09-14 approved by the operator
raised: 2026-09-13
raised-by: operator, answering a blocked story mid-run and watching the agent re-enter plan mode
area: backend-api
prd-deltas: FR-18 (the archive-and-replan becomes one of two operator-selectable modes)
spine-deltas: AD-13 possibly (a fourth re-dispatch form: an operator resume); AD-8, AD-9, AD-10 unchanged
effort: S–M
---

# IMP-003 — Answer a blocked Story in the same session, or restart

## Problem

When a Story blocks, the operator has exactly one way to resume it: the Answer, and the
Answer always destroys the agent's context. FR-18 archives the Story file to
`stories/.answers/{id}-attempt-{n}.md` and dispatches a **new** harness session, which
re-plans the Story from scratch with the operator's paragraph in front of it. That is the
right shape when the agent went wrong and a fresh start is cheaper than a correction. It is
the wrong shape when the agent is one small step from done — the motivating case was a Story
whose implementation was complete and verified, blocked only because its session could not
run `git commit`: the Answer threw away a session that needed one sentence ("your work is
committed; finalize") and paid for a full re-plan instead.

The machinery to continue a session already exists and is deliberately withheld from the
operator: `Harness.resume` is wired, capability-flagged, and used — but only by a Template's
own bounded `retry` rule. The operator's only same-session path is FR-21's terminal takeover,
which means a shell in the container. The missing piece is a choice on the Answer itself:
**reply in the same session** (continue with full context, no re-plan) or **restart** (the
current archive-and-replan). Which one is right depends on why the Story blocked, and only
the operator knows that.

## Evidence

- The Answer's only effect on the step machine is `blocked → queued`
  (`application/use_cases/signal_effects.py:145` `_answer`); everything that makes it a
  restart happens at the next dispatch.
- The restart is the archive, by design: "moving it leaves the glob empty, so the next
  dispatch is a first dispatch and the agent plans again"
  (`application/steps/agent_answer.py:11`, `archive_with_answer` at `:113`). The signal
  payload carries only the operator's text (`TEXT_KEY = "text"`, `agent_answer.py:82`) — no
  key exists on which a different behaviour could be selected.
- Session resume is already a first-class dispatch: `steps/agent.py:325` `_planned` builds a
  `_Dispatch` with `resume_id` when `retry.resume_session and harness.capabilities.resume`
  and the previous attempt recorded a `session_id` (`agent.py:334`). The claude adapter's
  `resume` says it outright: "Continue the session this row already opened — `retry`'s path
  only (AD-10)" (`infrastructure/harness/claude/adapter.py:247`).
- Capabilities are uneven, so the option must be conditional: claude `resume=True`
  (`claude/adapter.py:186`), codex `resume=True` (`codex/adapter.py:143`), opencode
  `resume=False` (`opencode/adapter.py:147`), fake `resume=True` (`fake/adapter.py:100`).
- Work is preserved either way: `_wip_commit` commits whatever the interrupted attempt left
  before any dispatch (`agent.py:214`), so the choice is about *context*, not about losing
  files.
- The manual escape hatch exists and proves the semantics are sound: FR-21's
  `resume_command` hands the operator `claude --resume {session_id}`
  (`claude/adapter.py:276`) — this improvement is that path, one click instead of a shell.

## Options

**A. A `mode` key on the existing `answer` payload** — `mode: "restart" | "session"`,
default `"restart"`. The step machine is untouched: `blocked → queued` via the existing
`answer` event either way; the difference lives where the retry/resume difference already
lives, in `_planned`. In session mode the dispatch skips `archive_with_answer` (the Story
file stays where it is), builds a reply prompt from the operator's text alone (a resumed
session already holds the condition it reported), and passes `resume_id`. Costs: one signal
kind now has two behaviours, and validation must refuse `mode: "session"` when the parked
row cannot resume (harness without the capability, or a previous attempt that recorded no
`session_id`) — a 422 `problem+json` naming the reason, because degrading silently to a
restart would be the exact surprise this note exists to remove.

**B. A new signal kind `reply`** — explicit in the API, and the gate record reads cleanly.
Costs: a new `RunEvent`/`StepEvent` through `domain/statuses.py`'s transition tables, whose
existing tests are frozen anchors; a wider OpenAPI delta; and a second signal whose effect
differs from `answer` only at dispatch time, which is a distinction the step machine itself
never sees — the wrong layer to spend an event on.

**C. Do nothing; document FR-21** — the terminal takeover already gives same-session access.
Costs: it is a shell in the container, not an Answer box; it requires the operator to know
the worktree path and drive the harness by hand; and opencode has no resume at all, so the
"documented" path is harness-dependent in a way a doc cannot fix.

## Recommendation

**Option A.** The two-writers rule (AD-8) and the step machine stay untouched — the operator
transition is still one `signal_run` write, and "what kind of dispatch follows a park" is
already decided in `_planned`, which is where the retry/resume fork lives today; a reply is
the same fork with an operator's reason instead of a Template's. Option B spends a domain
event on a distinction only the dispatcher sees and walks into frozen transition-table
tests. Option C is the status quo with better docs, and the motivating case shows the status
quo picking wrong.

Two behaviours worth pinning in the spec that follows:

- **Refuse, never degrade.** A `mode: "session"` answer against a row that cannot resume is
  refused at signal time with the reason (`harness opencode records no resumable session`),
  and the UI only offers the choice when it is real — a new field on the parked row's view
  (e.g. `reply_available`), derived from the harness capability and the previous attempt's
  recorded `session_id`, delivered through the generated contract (AD-3).
- **The WIP commit stands in both modes.** A replied-to session finds its dirty tree
  committed as `wip: story {id} attempt {n} (interrupted)` — that is durability (AD-9), not
  a bug, and in the motivating case it is the fix itself. The reply prompt should state it
  as a fact so the resumed agent does not re-diagnose a "dirty" tree that is now clean.

## Scope of change

- `application/rules/signals.py` (+ table): read and validate `mode`; the resumability check
  at signal time, with `problem+json` refusal.
- `application/steps/agent_answer.py`: a `replying(ctx)` predicate beside `answering(ctx)`;
  `archive_with_answer` returns `()` in session mode.
- `application/steps/agent.py`: `_planned` gains the reply branch (`resume_id` from the
  previous attempt, prompt from the operator's text via a named constant); `compose_prompt`
  untouched — a resumed session never sees the dispatch sentence, same as a resumed retry.
- `application/use_cases/run_views*` / `open_run`: `reply_available` on the parked row.
- `contracts/openapi.json` via `make openapi`; `web-client` types via `pnpm gen:api` (AD-3).
- `web-client` blocked panel: one textarea, two actions, copy that states the mechanism
  (NFR-8): reply continues the recorded session; restart archives the Story file and
  dispatches fresh with the answer in front.
- New unit tests over the shared fakes (the fake harness already declares `resume=True`);
  one e2e scenario: block, reply in session, assert the harness received `resume` with the
  prior `session_id` and that no `.answers/` archive was written.

## Open questions

- **Spec-checkpoint rejects.** The same `answer` event fires on a rejected plan
  (`checkpoint → queued`). A session-mode reply there would let the planning agent revise
  its plan with its own context — likely valuable, but it interacts with
  `halts_after_planning` (`agent_answer.py:157`), which must still halt the revised plan.
  In scope, or a follow-up?
- **Do any frozen tests pin "an Answer always archives"?** If a test asserts the archive as
  the Answer's universal effect, revising it is the Operator's revision (root AGENTS.md,
  anchor exception four) — this note is that product decision, dated; the spec should name
  the tests it touches before any build starts.
- **Budget on a replied session.** The adapter's resume path drops `--max-budget-usd` (the
  cap belongs to a dispatch); the post-attempt spend guard in `agent_tail` still runs. Is
  that guard alone acceptable for an operator-initiated resume, or does the reply need its
  own cap?
- **Session liveness.** A recorded `session_id` whose state has since been lost (volume
  pruned) fails at `resume` time, not at signal time; the attempt errors and the row parks
  `error` with the harness's output (no silent retry, hard rule 7). Is that late failure
  acceptable, or should signal-time validation probe the session store?
