---
story: "6-1"
epic: 6
title: Answer a blocked story, with a scripted test harness
requirements: [FR-18, NFR-8, UX-DR10 (blocked body), UX-DR17, AR-14 (fake harness)]
binds: [AD-9, AD-10, AD-13]
---

# Story 6.1 — Answer a blocked story, with a scripted test harness

As the Operator,
I want to answer a blocked story from the Run detail and see the Run resume within seconds, with the mechanism stated in words above the button,
So that the intent gap an agent found costs me one paragraph, not a session (UJ-3).

## Scope

**In:** the `answer` effect in the agent executor's prepare phase, the prompt suffix, the gate record text, the Answer box and *Resume with answer* in `RunDetail`, the `fake` harness adapter enabled in test mode with its `harness` row, unit and e2e tests.
**Out:** Reject at a spec checkpoint (6.2, same signal, different park), the diagram.

## Binding rules (inlined)

- **Signal.** `POST /runs/{id}/signals {kind: answer, payload: {text}}`; `signal_run` (4.5) validates `park_kind ∈ {blocked, checkpoint}` on an agent row, records `answer` with `text`, moves the row to `queued`, resumes the engine.
- **Effect in the resumed attempt (AD-13, `_prepare_writes` of 5.4):** when `resume_signal.kind == answer`: the story file `stories/{id}-*.md` (exactly one; if none, proceed as a first dispatch and log `no file to archive`) is moved with `Workspace.move` to `stories/.answers/{id}-attempt-{n}.md` where `n` is the previous attempt's number; the text `\n\n## Human Answer\n\n{ISO time} · operator\n\n{answer}\n` is appended to the archived file; both paths go into the prepare commit `orchestrator: prepare story {id} attempt {n+1}`. No `stories/{id}-*.md` remains, so the dispatch is a first dispatch (build-auto plans fresh).
- **Prompt suffix (`compose_prompt`).** ` Answer from the operator to the blocking condition "{condition}": {answer}` where `condition` is the `Blocking condition:` line of the archived file (or `spec rejected` at a spec checkpoint). Same harness, new session.
- **Timing (FR-18).** The Run leaves `needs_you` as soon as `signal_run` commits (before the executor runs); the UI's next poll (≤ 5 s) shows `RUN`.
- **Answer box (UX-DR10, UX-DR17).** Under the question block: textarea (test-id `wf-answer`), the hint line verbatim: `Blocked story file archived to stories/.answers/{id}-attempt-{n}.md with your answer; story {id} re-planned with the answer as context. If the gap is in SPEC.md, edit SPEC.md on the branch instead.`; primary *Resume with answer* (`wf-signal-answer`), disabled while the textarea is empty; posts the signal, then re-fetches; a 409 prints the detail beside the button. Also offered: *Skip story*, *Skip epic* (when admitted), *Cancel run*.
- **Fake harness (test mode).** `infrastructure/harness/fake/adapter.py`, registered as `fake` only when `ORCH_TEST_MODE=1`, with a `harness` row `enabled: true` seeded in that mode. Behaviour of `run(cwd, prompt, …)`: it parses `spec_folder` and `story_id` from the prompt (the fixed sentence of 5.4), reads the scenario file `{cwd}/.fake-harness/{story_id}/attempt-{k}.yaml` for the k-th call for that story in this worktree (falling back to `default.yaml`), and applies it: `story_file: {slug, content}` → writes `stories/{id}-{slug}.md`; `files: [{path, content}]` → writes them; `commit: true` → `git add -A && git commit -m "story {id}: fake"` as user `fake <fake@local>`; `exit_code`; `sleep_seconds`; `usage: {tokens_in, tokens_out, cost_usd}`; `echo_prompt: true` → appends the prompt to the story file (so tests assert the Answer suffix). `resume` behaves like `run` with the next scenario. `session_id` pre-assigned; `native_tracing: false`. It never reads the model, never leaves the worktree.
- **Fixture.** `fixtures/gates-repo/` (committed) with `specs/gates/SPEC.md`, `stories.yaml` (stories `1`, `2` with `spec_checkpoint: true`, `3` with `done_checkpoint: true`), `check.sh` as the quality gate reading a `GATE_OK` file, and `.fake-harness/` scenarios per story used by the e2e tests of this epic; a helper materialises it as a local origin like the readiness fixture.

## Acceptance criteria

**Given** a Run parked `blocked` on story `4-1` after attempt 1, whose file's blocking condition is `intent gap`
**When** `answer {text: "Post to the project's channel only"}` is signalled and the executor resumes on the fakes
**Then** the file is at `stories/.answers/4-1-attempt-1.md` ending with `## Human Answer`, the time, and the text; the prepare commit contains the move; no `stories/4-1-*.md` exists at dispatch; the harness prompt ends with ` Answer from the operator to the blocking condition "intent gap": Post to the project's channel only`; the gate record has `answer` with the text.

**Given** the Answer box
**When** rendered on a `blocked` detail
**Then** the hint reads the verbatim line with the right file name, the button is disabled until text is typed, and clicking posts the signal.

**Given** the fake harness in test mode
**When** dispatched with a scenario `story_file: {status: blocked, blocking condition intent gap}` then, after an Answer, `story_file: {status: done}, commit: true, echo_prompt: true`
**Then** the first attempt parks `blocked`, the second reaches `done`, and the archived file and the new story file (with the echoed Answer suffix) exist on the branch (e2e on the compose stack with `ORCH_TEST_MODE=1`).

**Given** `answer` posted on a Run parked `timeout`
**When** validated
**Then** 409.

## Implementation notes

- Executor: extend `_prepare_writes` (5.4) with `_archive_with_answer`; `compose_prompt` gains the `answer` branch (already specified in 5.4; implement here if left as a stub).
- Fake adapter under `infrastructure/harness/fake/`; scenario schema unit-tested; `ORCH_TEST_MODE` in settings and `.env.example` (documented as test-only, default unset).
- `fixtures/gates-repo/` and `tests/e2e/helpers/gates_fixture.py`.

## Verification

```bash
make lint && make test && ORCH_TEST_MODE=1 make up && make e2e-api
```

## Sources for detail only

PRD FR-18 (verbatim), UJ-3. Spine AD-13 (`answer` row), AD-9 (archive in the resumed executor). `addendum.md` §D Answer. `EXPERIENCE-v1.md` §2.2 stop table (`blocked`), §Voice.
