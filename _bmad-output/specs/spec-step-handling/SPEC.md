---
id: SPEC-step-handling
title: "Step handling: skip, resume, cancel"
capabilities: [CAP-1, CAP-2, CAP-3, CAP-4, CAP-5, CAP-6]
companions: [current-behaviour.md]
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Step handling: skip, resume, cancel

## Why

A pain, on the operator's own hands. Five controls the Run detail owes the operator are missing or wrong, and each one costs a whole story or a whole Run to work around. A step in `error` offers *Skip story* and *Skip epic* but no way to skip that one step. Retry re-dispatches a fresh session by default, throwing away everything the agent had already established, and carries no instruction from the operator on either path. A Run that is running offers no Cancel at all — the control exists, but only on a stop. The local (OpenCode) harness declares it cannot resume a session, on a premise its own CLI contradicts at the very version this repository pins. And the step-run detail page renders its attempt history as run-on text. `current-behaviour.md` names, per item, the code that is wrong today.

## Capabilities

- **CAP-1**
  - **intent:** The operator can skip the single step a Run is parked on, and the Run continues at the next row.
  - **success:** A Run parked on a step in `error` offers a *Skip step* action beside *Skip story* and *Skip epic*; taking it marks exactly that row `skipped`, writes a `gate_record` with `actor: operator`, returns the Run to `running`, and the walker executes the next row. The rows of the enclosing story are untouched.

- **CAP-2**
  - **intent:** The operator can send an instruction of their own with a Retry, on either path — into the session the agent was already in, or into the fresh dispatch when the session is gone.
  - **success:** The Retry control accepts free text on both paths. Retrying with text on a resumable stop delivers exactly that text as the resumed session's message — not the template's `retry.prompt`, not an empty message — and the attempt records the same `session_id` as the previous one. Retrying with text on the restart path delivers it as the retry prompt in front of the composed dispatch.

- **CAP-3**
  - **intent:** Retry resumes the existing session wherever one can be resumed, without the operator having to ask for it; where it cannot, the operator learns why before they act.
  - **success:** On a stop whose latest attempt recorded a `session_id` under a resumable harness, Retry resumes by default and the fresh-session path is reachable only by the operator choosing it. On a stop that cannot resume, the control states both facts: the reason resume is unavailable — no session was recorded, or this harness has no resume — and that restart is the only path left. It never silently restarts.

- **CAP-4**
  - **intent:** The `local` harness continues a recorded OpenCode session, so every shipped harness resumes.
  - **success:** `LocalHarness.capabilities.resume` is `True`; `resume()` invokes `opencode run --session {session_id}` with the recorded id and returns a `HarnessResult` carrying that same id; `resume_command()` returns the line an operator can paste to take the session over; and a `local` Run's stop offers the resume path that `reply_available` gates. A session id the store no longer holds fails as a reported failure, never as a silent fresh session.

- **CAP-5**
  - **intent:** The operator can cancel a Run from its page while it is running, not only once it has parked.
  - **success:** A Run in `running` or `queued` renders a Cancel control; confirming it posts `cancel`, and the Run reaches `cancelled` with AD-13's effects applied — live process groups killed, worktrees removed, an unpushed branch the Run created deleted.

- **CAP-6**
  - **intent:** The step-run detail page presents one step's attempt history as a table the operator can read across.
  - **success:** `/workflows/{run_id}/steps/{path}` renders the attempts as aligned columns with a header row — at minimum attempt number, status token, harness, model, duration, cost and exit code — one row per attempt, newest first, the selected row still selecting. Nothing on that page renders as unaligned run-on text.

## Constraints

- **Skip is admitted on every park kind.** All twelve, `budget`, `plan_stale`, `push_rejected` and `merge_conflict` included — the four where `skip_story` is refused today. The operator decides whether a row is worth skipping; the table does not decide for them.
- **AD-13 is an enumerated contract, and a new `SignalKind` amends it.** `SignalKind`, `RUN_TRANSITIONS`, `rules/signals_table.py::VALID` and the spine's own AD-13 table each enumerate the kinds; CAP-1 adds one to all four. The spine amendment is ratified and dated in the same change, as `merge_conflict` was on 2026-09-23 — it is not written silently into code.
- **AD-8 stands.** Skip, retry and cancel are `signal_run` writes. No executor, router, or island writes or derives a status.
- **The step machine already admits the skip, and gains no new edge.** `STEP_TRANSITIONS` holds `(planned|queued|blocked|checkpoint|error, skip) -> skipped`. CAP-1 drives those edges; it adds no `(running, skip)`.
- **Resume names the session explicitly.** `opencode run --session {id}` only. Never `--continue`, which guesses the last session of a directory other attempts share, and never `--fork`, which opens a new session id and so breaks the attempt's spend and trace attribution (AD-11).
- **No harness version moves for this work.** The pinned `OPENCODE_VERSION=1.18.26` already carries `--session`; a version bump would be an unrelated change riding along.
- **AD-10 stands.** The OpenCode invocation is written once, in `infrastructure/harness/opencode/adapter.py`. No application module learns a flag.
- **AD-2 stands.** The skip rule and the retry-mode default are `application/` rules; `domain/` and `application/` import no adapter.
- **100 % branch coverage on `domain` and `application`.** The new signal kind, its table row and each of its refusals are covered, or `make test` is red.
- **Do not rebuild or restart the operator's running instance.** Agents are running on it as of 2026-09-24 (hard rule 9).
- **Copy states the mechanism.** A control that cannot resume names the reason and the remaining path; nothing congratulates (PRD NFR-8).

## Non-goals

- Skipping a step that is `running`. No `(running, skip)` transition, no kill path, no partial-worktree cleanup. A live step parks or is cancelled first.
- Changing what `skip_story` or `skip_epic` do, or which parks admit them.
- Skipping a step the Run has not reached yet.
- Restyling the Run detail's STEPS tab (`table.wf-steps`), which is a real table with real rules and is not what is broken.
- Any new terminal-takeover path beyond the `resume_command` FR-21 already ships.
- An editor for the dispatch prompt. CAP-2 adds an instruction to a retry; it does not make the composed prompt editable.
- Bumping any pinned harness version.

## Success signal

An operator sitting in front of a Run stuck on one bad step fixes it from that page: they skip the step and the Run moves on, or they type what the agent got wrong and Retry drops that sentence into the session the agent was already holding — and when that session is gone, the control says so and takes the same sentence into a fresh dispatch instead. When the Run is going nowhere, Cancel is on the page rather than behind a stop. Nothing in the five needs a restart, a database edit, or a story abandoned to get past one row.

## Assumptions

- "An agent blocked for any reason" is read as every operator stop, not only `park_kind == "blocked"`. Retry's park kinds exclude `blocked` today, where *Answer* is the signal that carries text; CAP-2 and CAP-3 are about the operator's instruction reaching the agent, whichever control carries it.
- The step-run detail page's `with_resolved` block (a `<dl class="wf-kv">` grid) is not part of the complaint; CAP-6 is the attempt history.
