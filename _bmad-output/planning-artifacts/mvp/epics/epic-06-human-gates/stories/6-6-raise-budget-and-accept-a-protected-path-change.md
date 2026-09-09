---
title: 'Raise budget and Accept a protected-path change'
type: 'feature'
created: '2026-09-09'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
deferred: []
baseline_revision: 'b44152ec8774eefc6ca21fd57740fc674769176e'
---

<intent-contract>

## Intent

**Problem:** Two of AD-13's actions still have no reach. `budget_raise` is refused
`budget_raise not available yet` by `handle_signal`'s scope gate, and its stop has no body
at all — the `budget` park's `admitted_signals` are `("budget_raise", "cancel")`, and
`detail.ts::stopSignals` filters `budget_raise` out (it is not one of `EFFECTIVE_KINDS`), so
an over-budget Run offers the Operator nothing but *Cancel run*. `continue` on a
`protected_path` park is refused the same way, even though 5.6 already built the executor's
whole Accept branch (`agent_tail.re_check`) and `run.accepted_paths` already reaches the
protected-path rule and the trajectory — the branch has no caller because no signal can
reach it.

**Approach:** Widen `use_cases/signals.py::_in_scope` for both (`budget_raise`
unconditionally; `protected_path` joins `CONTINUE_PARK_KINDS`), correct the two writer gaps
the brief names that 4.5 left (`_budget_raise` queues nothing, so a retry-path `error` row
resumes into a stall; the gate record says "budget raised by the operator" rather than
naming the new figure), add the hit-list 409 the Accept needs, publish `alert.payload` and a
`?diff=1` mode on `GET /runs/{id}/files`, and give the two stops the bodies UX-DR10
specifies.

## Boundaries & Constraints

**Always:**
- AD-13 stays the authority on validity. `VALID["budget_raise"]`/`VALID["continue"]` already
  carry the right park kinds and `extra` predicates (4.5) — the only change to
  `rules/signals.py::VALID` is the two record *sentences* the brief pins, which no existing
  test asserts (`test_signal_rules.py` covers `record_text` for `answer` and `retry` only).
- AD-8's two writers stay the two writers. The Run's status still moves in
  `signal_run::_apply`; `_budget_raise` only widens what it hands back.
- `agent_tail.py`'s `tail` order is frozen (`"5.6" < "route(" < "5.7"`, FR-31) and is not
  touched. `re_check` already exists, already excludes `run.accepted_paths`, and already
  runs no dispatch — this story only gives it a caller by admitting the signal.
- The `diff` mode is a **mode on the existing `GET`**, not a third operation:
  `test_run_files_router.py::test_the_router_declares_exactly_the_two_operations` stays true.
- Module cap 400: `agent_tail.py` is at exactly 400 and must not grow (it does not need to);
  `api/schemas/run_views.py` is at 382 and `StopBody.tsx` at 270 — check both after edits and
  split along a real seam if either is pushed over.
- New coverage goes in new test files; `tests/unit/fakes/` is the sole additive exception
  (`FakeGit.diff`).

**Block If:** — **triggered, and resolved by an operator ruling; see `## Auto Run Result

Status: done

**Summary.** Both of AD-13's last non-terminal actions reach their effects.
`handle_signal`'s scope gate admits `budget_raise` and `continue` on a `protected_path`
park; the raised budget now actually resumes the plan (a real bug — see below); the Accept
is refused unless its file list is exactly the hit list AD-17 recorded; `alert.payload`
publishes that hit list; `GET /runs/{id}/files` grew a `diff=1` mode scoped to those same
hits; and the two stops that had no body at all now have one each.

**The bug the brief's first `[ASSUMPTION]` uncovered.** `signal_effects.py::_budget_raise`
wrote `run.budget_usd`, let `signal_run` move the Run to `running`, and queued **nothing**.
`walk.py::next_row` finds work three ways, and a budget park on an `error` row — FR-17's
retry path — matched none of them: `next_row` answered `None`, `close_run` read it as a
stall, and the Run parked `internal`, a stop admitting only `cancel`. A park on a `done` row
happened to work through `_start_the_plan`'s "every row is planned/done/skipped" branch, so
the half that was broken was invisible. `resume_from(ports, park_row)` — the call every
other resuming effect already makes — is both cases in one line.
`test_budget_raise_resume.py` pins the `error` path against `next_row` itself, not only
against the repository, because "the row is queued" and "the walk finds it" are the two
halves that came apart.

**Files changed** (backend): `application/rules/signals.py` (`Rule.text_from`/
`Rule.extra_refusal` and their two builders — `budget raised to $60.00` off the *validated*
figure, `accepted: a, b` for an Accept while a checkpoint `continue` keeps its phrase; the
`new budget must exceed spend $41.20` refusal), `application/rules/protected_paths.py`
(`hits_payload`/`park_record_payload`/`hit_paths` — the hit list as stored state, written by
both call sites and read by both readers), `application/use_cases/signal_effects.py`
(`_budget_raise` resumes), `application/use_cases/signals.py` (the scope gate, and the
Accept's own hit-list 409), `application/steps/git_commit.py` (its `protected_path` park
records a hit list, which it never did — without it the brief's "`files` must equal the hit
list" was unsatisfiable for a commit-guard park), `application/steps/agent_tail.py`
(`HITS_KEY` re-bound from the rule; still exactly 400 lines, marker order untouched),
`run_view_types.py`/`run_views_alert.py`/`run_views.py`/`api/schemas/run_views.py`
(`Alert.payload`), `domain/ports/git.py` + `infrastructure/git/worktrees.py` +
`tests/unit/fakes/git.py` (`Git.diff`), `application/use_cases/run_files.py` +
`api/schemas/run_files.py` + `api/routers/run_files.py` + `api/providers.py` (the `diff`
mode). Nine new test files; three pending-gate assertions removed under the ruling.

**Files changed** (frontend): `lib/run/budget.ts` and `lib/run/accept.ts` (new),
`components/run/BudgetRaiseBox.tsx` and `components/run/AcceptBox.tsx` (new),
`components/run/StopBody.tsx` (both bodies; the plain `Continue` button steps aside on the
`protected_path` stop only), `islands/RunDetail.tsx` (two more payload-carrying callbacks
through 6.1's own `sendSignal`), `lib/run/artifacts.ts` (`isFile` beside `isTree` — the
files response is a three-member union now, so "not the tree" stopped being a narrowing),
`components/run/ArtifactsPanel.tsx`, `styles/run-detail.css`. Six new test files.
`contracts/openapi.json`/`schema.d.ts` regenerated with `AlertOut.payload`,
`RunFileDiffOut` and the `diff` query parameter.

**Anchor removals, all three authorised by the operator's ruling.**

| File | Removed | Replaced by |
| --- | --- | --- |
| `tests/unit/application/test_handle_signal.py` | `test_continue_on_protected_path_is_refused_not_available_yet` (a standalone pending-gate test, story 4-9) | `tests/unit/application/test_accept_protected_path_signal.py` (10 tests) |
| `tests/unit/application/test_handle_signal.py` | the `budget_raise` parametrize row, its `ids` entry, and the `COMMIT_GUARD` constant left unused | `test_budget_raise_signal.py` (6), `test_budget_raise_resume.py` (6) |
| `tests/unit/application/test_answer_signal_scope.py` | the `budget_raise` row — its last — and with it the now-vacuous `test_the_kinds_this_story_did_not_land_still_answer_not_available_yet` | the same two files |

Nothing else in either file changed. `test_signals_router.py`'s scope-gate illustration was
not touched: its vehicle is `terminal_start`, which this story does not land.

**Decisions the brief left open.**

- **`[ASSUMPTION]` 1 — a retry-path `error` under budget resumes as a retry.** Implemented
  through `resume_from`, whose own rule ("the parked row is the first candidate") re-queues
  an `error` row and steps over a `done` one, so AD-13's two separately-stated cases are one
  line. See the bug note above.
- **`[ASSUMPTION]` 2 — the field pre-filled with `spend + 10` rounded.** `Math.ceil`, to two
  decimals. A floor would land at or below the spend for a spend under a dollar, so the
  screen would sometimes pre-fill a figure the server is about to refuse; a ceiling always
  clears. `run-budget-lib.test.ts` asserts that property over a range of spends rather than
  only the example.
- **The `diff` mode's scope** (implicit in the brief). Not `_within_spec_folder`: every
  anchor AD-17 protects — `AGENTS.md` anywhere, every frozen test file — is outside the spec
  folder by construction, so that gate would 403 exactly the paths the mode exists to show.
  Scoped instead to the hit list *this Run's own park recorded*, which is tighter than the
  spec folder and is state the Run wrote itself. `_escapes` is reused unchanged.
- **The Accept is all-or-nothing, not a set of checkboxes.** The server refuses any list
  that is not exactly the hits, so a partial accept would leave a flagged file unaccepted and
  park the resumed check on it again. The per-file control an Operator needs is the diff
  link, which is a read.
- **The mismatch is compared as sets**, not as ordered lists: the Operator is answering "yes
  to these files", and the order the list arrived in says nothing about that.

**Gates — all run from a clean tree, all green**

| Gate | Result |
| --- | --- |
| `make lint` | pass — ruff, ruff format, mypy (domain/application strict), import-linter (4 contracts kept), env contract, test pairs (189 backend / 89 web), `gen:api --check` (no drift), eslint, prettier, `tsc --noEmit`, astro check (0 errors) |
| `make test` | pass — 5304 backend passed, 1 skipped; `domain/` + `application/` **100 %** branch coverage; web-client 1198 passed in 92 files |
| `make openapi` | pass — `contracts/openapi.json` and `schema.d.ts` regenerated with `AlertOut.payload`, `RunFileDiffOut` and the `diff` query parameter; re-running produced no further change |
| `make e2e` | pass — 183 passed, 11 deselected, 38 subtests, on the disposable `aio-e2e` stack with `ORCH_TEST_MODE=1`, including the new `test_budget_raise.py`; stack torn down |
| `make e2e-ui` | pass — 148 passed, including the new `run-detail-accept.spec.ts` |

The two Epic-5 PNGs under `_bmad-output/implementation-artifacts/epic-5-screens/` are
regenerated by story 5.10's own anchor spec; the new bytes are committed.

## Notes for the next story (6-7, terminal resume)

- **`_in_scope` now refuses exactly three kinds**, all yours: `terminal_start`,
  `terminal_release`, `terminal_resume`. Landing the last of them empties
  `use_cases/signals.py::_refuse_out_of_scope`'s second branch entirely.
- **`test_signals_router.py::test_a_kind_outside_this_epics_scope_is_a_409_not_available_yet`
  uses `terminal_start`** and cannot be retargeted after 6.6: no out-of-scope kind will be
  left that is not one of yours. The operator has already ruled that the story landing the
  last kind may retire that test together with the then-dead `_refuse_out_of_scope` branch,
  provided coverage proves the endpoint's real behaviour.
- **The two registries are terminal-only now.** `test_handle_signal.py` holds three rows
  (`terminal_start`, `terminal_release`, `terminal_resume`) with `_terminal_release_world`
  and `_terminal_resume_world` beside them; `test_answer_signal_scope.py` holds no registry
  at all any more.
- **`rules/signals.py` is at 397 of 400.** It has three lines of headroom, and 6.7 touches
  it. Split along the seam its own docstring already names — the table (`Rule`, the
  predicates, the text builders, `VALID`) against the questions asked of it (`validate`,
  `admitted_signals`, `run_admitted_signals`, `record_text`, `row_at`, `raised_budget`,
  `accepted_files`) — re-exporting every public name, rather than trimming comments.
- **`Rule.text_from` is there if a terminal record needs a built sentence**, and
  `Rule.extra_refusal` if `_in_terminal_session`/`_no_terminal_session` should say why they
  refused rather than falling back to `INVALID`. Neither is used by a terminal kind today.
- **`Alert.payload` is generic**, not protected-path specific: it is whatever the parking
  gate record kept, so a terminal stop that wants to carry details to the screen has a place
  for them without a new field.
- **Still deferred to Epic 7, untouched:** a resumed dispatch records no `pgid`, and
  `Harness.resume` takes neither `model` nor `budget_usd_remaining`. Neither blocked this
  story — the Accept resumes the tail with no dispatch at all.
