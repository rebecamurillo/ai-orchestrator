---
status: done
date: 2026-09-09
---

# Continue and Reject at checkpoints

Story 6-2 (SPEC CAP-2, FR-19, NFR-8, UX-DR10, UX-DR18; binds AD-9, AD-13).

## Anchor conflict, authorised by the operator

Investigation before implementation found that `test_agent_answer_dispatch.py::
test_a_spec_checkpoint_answer_quotes_spec_rejected_and_does_not_halt_again` (landed by 6-1)
asserted the opposite of this story's own AC: a Reject's redispatch prompt could never carry
`" Halt after planning."`, while the brief requires exactly that suffix after the Answer
clause (so a rejected, re-planned spec pauses again instead of running straight through to
implementation). The work halted and the conflict was reported in full (file, test, both
assertions, why no additive alternative existed). The operator ruled: 6-1 had guessed wrong
about behaviour this story's own brief governs, and authorised the minimal edit — rename the
test, extend its `.endswith(...)`, drop the `not in prompt` assertion, correct the docstring
— with strictly-exceeding coverage in a new file in the same commit. That ruling also set a
standing rule for the rest of Epic 6: a story may correct an earlier story's frozen test when
the earlier story reached into this story's own governed behaviour and got it wrong, under
the same minimal-edit-plus-new-coverage discipline.

## What landed

**1 — the halt decision, corrected.** `agent_answer.halts_after_planning(with_resolved,
resume_signal)` (`backend-api/src/orchestrator/application/steps/agent_answer.py`) is the
one place `compose_prompt` asks: a first dispatch or re-plan at a spec checkpoint
(`resume_signal is None`), and once more on a Reject there (`resume_signal.event ==
ANSWER_EVENT`) — never on `continue`, which is the plan already approved. `agent.py`'s own
`compose_prompt` shrank to one call (net zero line growth, at 397/400) and its Answer-then-
Halt ordering was corrected to match the brief's AC exactly (`Answer from the operator ...
Halt after planning.`, concatenated, no extra separator). The authorised edit landed in
`test_agent_answer_dispatch.py` (renamed, corrected); strictly-exceeding coverage landed in
two new files: `test_agent_reject_halts_again.py` (the full composed prompt for Reject, and
the two contrast cases — a `blocked` Answer never halts, `continue` never halts) and
`test_agent_continue_dispatch.py` (the whole executor dispatch: new session, no archive, no
halt suffix, for `continue` at a spec checkpoint).

**2 — `Alert.row_kind` and `Alert.checkpoint_story`, and the `run_views.py` split.**
`application/use_cases/run_view_types.py` gained both fields (`str | None = None`, backward
compatible) plus a new `CheckpointStory` dataclass (`story_id`, `title`, `attempts`,
`cost_usd`, `verify`). `run_views.py` sat at exactly 400/400 lines before this story, so
`_run_token`/`_attribution`/`_alert` moved to a new `application/use_cases/
run_views_alert.py` (the same seam 6-1 used for `agent.py` → `agent_answer.py`), which also
computes `checkpoint_story` for a done checkpoint: `title` is read back out of the
commit-guard row's own `with_resolved["message"]` (`"story {id}: {title} (orchestrator)"` —
the one place a Story's title reaches stored state), `attempts` off the frame's `build` row,
`cost_usd` summed across the whole frame, `verify` off the frame's `verify` row status. No
test imported the moved private helpers directly, so the split touched no assertion.
`api/schemas/run_views.py` gained `AlertOut.row_kind`/`checkpoint_story` and a new
`CheckpointStoryOut`, both `_drop_default`-guarded so a pre-story response keeps compiling.

**3 — `GET /runs/{id}/files`, net new.** `application/use_cases/run_files.py::
read_run_file` reads a literal path or resolves a single-segment glob (the brief's own
`{spec_folder}/stories/{id}-*.md`) server-side, taking the newest match on ambiguity (AD-13's
own de-ambiguation precedent). Three refusals, checked in an order that keeps `path=../x` a
422 even though it would also fail the narrower spec-folder scope check: an escaping path
(`..`, absolute) is `Invalid`; a well-formed path outside the Run's own `spec_folder`/
`initiative_folder` is a new `Forbidden` domain error (`domain/errors.py`, mapped to 403 in
`api/errors.py`'s `DOMAIN_STATUS`); a path inside scope that names nothing is `NotFound`. The
brief's own implementation note places the endpoint in `api/routers/runs.py`, but that
router carries `test_runs_router.py::test_the_router_declares_exactly_the_two_operations`,
frozen to `GET`/`POST /runs/preflight` — the honest alternative, precedented twice already by
`run_detail.py` and `signals.py`, is the new sibling `api/routers/run_files.py`, mounted
after `signals.router` in `main.py`. `api/providers.py::run_files_ports` wires `FsWorkspace`
itself (the class, a factory) the same way `StepPorts.workspace` already does, since the
route cannot root a Workspace before it has read the Run's own `worktree_path`.

**4 — the checkpoint bodies.** `web-client/src/lib/run/checkpoint.ts` (new): `isSpecCheckpoint`/
`isDoneCheckpoint` off `alert.row_kind` (missing entirely — a response predating this story —
resolves to neither, so the old generic `checkpoint` banner stays exactly as it was),
`offersReject`, `checkpointSignals` (the `continue`/`skip_story`/`skip_epic` button set a
checkpoint stop offers — `stopSignals`'s three `EFFECTIVE_KINDS` never included the two
skips, so this is a new sibling filter, not a widening of the frozen one), `plannedFilePath`/
`plannedEyebrow`, `checkpointSummaryLine` (verbatim: `story {id} · {title} · {attempts}
attempts · ${cost} · verify {done|skipped}`). `RejectBox.tsx` (new) mirrors `AnswerBox.tsx`
with the one difference the brief asks for: a "Reject with a reason" toggle collapses the
textarea by default. `StoryFileBlock.tsx` (new) renders the planned file inline, read-only —
`QuestionBlock.tsx`'s own block renderer duplicated (small, local, no `dangerouslySetInnerHTML`
anywhere). `StopBody.tsx` gained both bodies, gated on `alert.row_kind`, additive around the
existing generic `checkpoint` paragraph so the frozen `run-stop-body.test.ts` case is
untouched. `RunDetail.tsx` gained one more `useEffect` fetching the planned file via
`GET /runs/{id}/files` when the stop is a spec checkpoint; Reject reuses the exact same
`onAnswer` callback 6.1 already threads through, since the wire signal is identical.

**5 — the gates fixture's own gap.** `fixtures/gates-repo/.fake-harness/2/attempt-1.yaml`
is new: story 2's only prior scenario (`default.yaml`) wrote `status: done` on every
dispatch, which `rules/routing.py::route` never turns into a `checkpoint` park (that needs
`status: ready-for-dev` and `spec_checkpoint` both) — so the spec checkpoint this story needs
to prove end to end was, before this file, unreachable by any e2e test. `attempt-1.yaml`
plans and halts (`status: ready-for-dev`, no `files`, no `commit`, mirroring story 1's own
`attempt-1.yaml`); `default.yaml` is unchanged and now correctly represents only the
Continue's second dispatch. Additive; `test_gates_fixture.py`'s frozen assertions (including
the one keying scenarios by story id, which two files per story now satisfies identically
since both carry the same `slug: plan`) all still pass.

**6 — the e2e proof.** `tests/e2e/test_checkpoint_signals.py` (new): a Run walked past
story 1's own block (Answer) to story 2's spec checkpoint, Continue re-dispatching without
archiving (attempt 2, same story file, `commit-guard` reaches `done`) and without a halt,
the gate record holding exactly one `continue` for it; on to story 3's done checkpoint
(`alert.row_kind == "checkpoint"`, `checkpoint_story` summarising story 3 exactly), admitting
`continue` but not `answer`; a final Continue resuming the Run through `push`/`link` to
`done` — `pr.link` correctly records no compare URL for the fixture's own `file://` origin
(`no compare link for this host`, `application/steps/pr_link.py`'s own documented rule), so
the assertion there is that the Run finished clean, not that a GitHub-only link appeared.

## Anchor edit (operator-authorised, strictly-exceeding coverage in the same commit)

| File | Lines | Was | Is | New coverage |
| --- | --- | --- | --- | --- |
| `backend-api/tests/unit/application/steps/test_agent_answer_dispatch.py` | 127-135 | `test_..._does_not_halt_again`; `.endswith(...clause)`; `"Halt after planning." not in prompt` | `test_..._and_halts_again`; `.endswith(...clause + " Halt after planning.")`; second assertion dropped | `test_agent_reject_halts_again.py` (3 tests), `test_agent_continue_dispatch.py` (3 tests) |

Nothing else in that file changed.

## Splits (no comment deleted to buy space)

- `application/use_cases/run_views.py` 400 → 137 of 400: `_run_token`/`_attribution`/
  `_alert`'s bodies moved to the new `application/use_cases/run_views_alert.py` (48 lines),
  which also gained `checkpoint_story`'s computation. `_run_token`/`_alert` stay callable
  under those names in `run_views.py` (`_run_token = run_token`; `_alert` now a thin
  positional-to-keyword adapter), so every existing call site kept working unchanged.

## Decisions the brief left open

- **The done-checkpoint compare link**: the brief's binding rule lists "the compare link if
  the epic is already pushed" among the done-checkpoint body's contents. `CostBlock.tsx`
  already renders `run.compare_urls` unconditionally on every Run detail screen regardless of
  stop kind (5.10), so this is already always visible beside the done-checkpoint body rather
  than duplicated inside it — no new code, and nothing in `StopBody.tsx` repeats it.
- **The done-checkpoint's `title`/`attempts`/`verify`**: none of these three facts was
  previously derivable from the wire — see item 2 above (title parsed from the commit-guard's
  own commit message; attempts and verify read off the frame's own rows). Scoped to
  `Alert.checkpoint_story` (computed only for a done checkpoint) rather than widening
  `StoryCellOut` (used by every story cell on every screen), since the summary line is a
  checkpoint-stop-specific fact, not a general per-story one.
- **A glob with more than one match** (`GET /runs/{id}/files?path=...-*.md`): answers the
  newest by `Workspace.mtime`, the same de-ambiguation AD-13 already uses elsewhere, rather
  than a new `misconfigured`-style refusal — this is a read, not a routing decision.

## Gates — all run from a clean tree, all green

| Gate | Result |
| --- | --- |
| `make lint` | pass — ruff, mypy (domain/application strict), import-linter (4 contracts kept), env contract, test pairs (188 backend modules / 78 web modules), `gen:api --check` (no drift), eslint, prettier, `tsc --noEmit`, astro check (0 errors) |
| `make test` | pass — 5150 backend passed, 1 skipped; `domain/`+`application/` **100 %** branch coverage; web-client 1045 passed in 77 files |
| `make openapi` | pass — `contracts/openapi.json` and `schema.d.ts` regenerated with `RunFileOut`, `CheckpointStoryOut`, `AlertOut.row_kind`/`checkpoint_story`, `/runs/{run_id}/files`; `gen:api --check` clean afterward |
| `make e2e` | pass — 162 passed, 11 deselected, 37 subtests, on the disposable `aio-e2e` stack, `ORCH_TEST_MODE=1` |
| `make e2e-ui` | pass — 124 passed |

## Notes for the next story (6-3, inline spec editing)

- **`GET /runs/{id}/files` is the endpoint to extend.** It already lives in its own router
  (`api/routers/run_files.py`) for the same reason 6-3's own `PUT` will have to: `runs.py`'s
  frozen route count leaves no room on that resource either. The use case
  (`application/use_cases/run_files.py::read_run_file`) already does the three-way refusal
  (422 escape / 403 out-of-scope / 404 missing) a `PUT` will need too — the scope check
  (`_within_spec_folder`) and the escape check (`_escapes`) are both free functions, reusable
  as they are.
- **The glob-resolution convention.** A `*`-bearing `path` resolves server-side to the
  newest match (`Workspace.mtime`); a tree endpoint (6-3's own `GET .../files` widened to a
  tree) has `Workspace.tree(prefix)` already on the port, unused by this story.
- **`RejectBox`/`AnswerBox`/`StoryFileBlock`** are all read-only or single-field; 6-3's own
  editor is a materially different component (multi-line, syntax-aware, a real Save action)
  and should not try to extend any of these three.
- **Still deferred to Epic 7, untouched by this story either:** a resumed dispatch records
  no `pgid`, and `Harness.resume` takes neither `model` nor `budget_usd_remaining`.
