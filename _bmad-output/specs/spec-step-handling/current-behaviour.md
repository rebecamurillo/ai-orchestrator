# Current behaviour

What each capability is up against, read at `feat/multi-repo-initiative` on 2026-09-24. Line numbers are of that read; the named symbol is the contract, not the number.

## CAP-1 — skip one step

| Fact | Where |
| --- | --- |
| The step machine already admits the skip from every parked status: `(planned\|queued\|blocked\|checkpoint\|error, skip) -> skipped`. | `domain/statuses.py::STEP_TRANSITIONS` |
| `SignalKind` holds `skip_story` and `skip_epic`, no per-row skip. `RUN_TRANSITIONS` has a `needs_you` row for each. | `domain/statuses.py` |
| `VALID["skip_story"]` requires a story frame (`_has_story_frame`); `VALID["skip_epic"]` an epic frame. Both skip a whole frame. | `application/rules/signals_table.py` |
| What a stop offers is `admitted_signals(park_kind, row_kind)` filtered by `_skippable`, which drops a skip whose frame the park path does not have. | `application/rules/signals.py` |
| On `error`-class stops the UI appends *Skip story* and *Skip epic* as confirms (`offersSkipStory` / `offersSkipEpic`). | `components/run/StopBody.tsx` |
| `skip_story`'s park kinds exclude `budget`, `plan_stale`, `push_rejected`, `merge_conflict`; `skip_epic`'s exclude `budget`, `plan_stale`, `merge_conflict`. **Skip step excludes none** — the spec's first constraint. | `application/rules/signals_table.py` |

## CAP-2, CAP-3 — retry with an instruction, resuming by default

| Fact | Where |
| --- | --- |
| A `retry` or `answer` signal may carry `payload.mode ∈ {restart, session}`. **An absent mode defaults to `restart`.** | `use_cases/signal_run.py::_check_mode` |
| `mode: session` is refused unless the latest attempt has a `session_id` and the harness is resumable — the two facts that also define `reply_available`. | `use_cases/signal_run.py::_check_mode`, `use_cases/run_views.py::_reply_available` |
| In session mode the message sent is the *answer's* text for an Answer, else the **template's** `retry.prompt`, else `""`. An operator Retry on a row whose template declares no `retry` resumes with an empty message. | `application/steps/agent.py::_session_message` |
| Dispatch selection: `mode == "session"` resumes; otherwise a template `retry` with `resume_session` resumes; otherwise a fresh session with the retry prompt prepended. | `application/steps/agent.py::_planned` |
| `RetryBox` defaults its radio to `restart`, and renders at all only when `reply_available` is true. Otherwise a plain *Retry* button posts `retry` with no mode — a fresh session. | `components/run/RetryBox.tsx`, `components/run/StopBody.tsx` (`hasRetryBox`) |
| Retry's park kinds: `timeout`, `push_rejected`, `misconfigured`, `internal`, `verify_failed`, `protected_path`, `merge_conflict`. **`blocked` is not among them** — there, *Answer* is the text-carrying signal. | `application/rules/signals_table.py::VALID["retry"]` |

## CAP-4 — the local harness resumes

| Fact | Where |
| --- | --- |
| `LocalHarness.capabilities = HarnessCapabilities(preassign_session=False, resume=False, native_tracing=False)`, and `resume()` refuses with `RESUME_UNSUPPORTED`. `resume_command` returns `None`, so the Run detail hides the terminal block for `local`. | `infrastructure/harness/opencode/adapter.py` |
| The stated ground — "`research/tracing.md` §OpenCode and the brief agree: `opencode run` opens a session, and this system does not continue one" — is what changes. | same module's docstring |
| The CLI does support it. `opencode run` flags at <https://opencode.ai/docs/cli/>: `--session, -s` "Session ID to continue"; `--continue, -c` "Continue the last session"; `--fork` "Fork the session when continuing". | vendor docs, read 2026-09-24 |
| **The pinned version already has it — no bump.** `packages/opencode/src/cli/cmd/run.ts` at tag `v1.18.26`, which is `OPENCODE_VERSION` in `.env.example`, declares `session` ("session id to continue"), `continue` and `fork`. Latest at time of reading is 1.18.32. | `sst/opencode` at `v1.18.26`, verified 2026-09-25 |
| A `--session` id the store no longer holds prints `Session not found` and exits 1 — a reportable failure, not a silent fresh session. This is what lets hard rule 7 hold on the resume path. | `run.ts` `session()` resolver, `v1.18.26` |
| `--fork` is refused without `--continue` or `--session`, and when given mints a **new** session id (`sdk.session.fork`) — which is precisely why the spec forbids it. | `run.ts` `v1.18.26` |
| The other two harnesses already resume: `claude --resume {id}` and `codex exec resume {id}`, both `capabilities.resume = True`. | `harness/claude/adapter.py`, `harness/codex/adapter.py` |
| Because `local` is not resumable, `reply_available` is false for every `local` Run — so CAP-4 is also what puts the mode selector of CAP-2/CAP-3 on those stops. | `use_cases/run_views.py::_reply_available` |

## CAP-5 — cancel a running Run

| Fact | Where |
| --- | --- |
| The server already admits it: a non-terminal, unparked Run's admitted signals are `("cancel",)` — and `("start", "cancel")` for a saved one. | `application/rules/signals.py::run_admitted_signals` |
| `RUN_TRANSITIONS` holds `(queued, cancel)`, `(running, cancel)` and `(needs_you, cancel)`. | `domain/statuses.py` |
| The effects are built: kill every recorded pgid, remove each worktree, delete a branch the Run created and never pushed — all idempotent. | `use_cases/signal_effects.py::_apply_cancel` |
| `CancelModal` exists and `RunDetail` wires it to `sendSignal('cancel')`. | `islands/RunDetail.tsx` |
| **But the only control that opens it lives in `StopBody`, which returns `null` when `stopKind(detail, token)` is `null`** — i.e. whenever the Run is not parked. That one early return is the whole gap. | `components/run/StopBody.tsx` |

## CAP-6 — the step-run detail page

| Fact | Where |
| --- | --- |
| The page is `/workflows/[id]/steps/[...path].astro`, rendering the `StepDetail` island client-side. | `pages/workflows/[id]/steps/[...path].astro` |
| Attempts render as a `<ul class="wf-step-detail-attempt-list">` of buttons — `display: flex; flex-wrap: wrap` — each label a `·`-joined string of number, token, harness and seconds. That is the run-on text. | `islands/StepDetail.tsx`, `styles/step-detail.css` |
| `styles/step-detail.css` is 252 lines and declares **no table rule at all**. | `styles/step-detail.css` |
| For contrast, the Run detail's STEPS tab is a real `<table class="wf-steps">` with `th`/`td` rules in `run-detail.css`, imported by `islands/RunDetail.tsx`. It is out of scope. | `components/run/StepsTable.tsx`, `styles/run-detail.css` |
| `base.css` gives bare `table` `width: 100%; border-collapse: collapse` — a new table gets that much for free and needs its own padding, header and border rules. | `styles/base.css` |
