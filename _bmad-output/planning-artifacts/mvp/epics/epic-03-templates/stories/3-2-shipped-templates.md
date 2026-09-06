---
title: 'Shipped Templates repo-init, story, epic, initiative'
type: 'feature'
created: '2026-09-05'
status: 'done'
baseline_revision: '649f5bf437c9ddc1c39322beafb38fc18c7e901c'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-03-templates/briefs/3-2-shipped-templates.md'
---

<intent-contract>

## Intent

**Problem:** `application/templates/validate.py` (story 3.1) exists but nothing in the repository is a Template yet. The dev loop and repository bootstrap need to ship as real DSL v1 files so the planner of Epic 4 has something to expand and the Operator has something to read (SPEC CAP-2, FR-9..FR-11, FR-30).

**Approach:** Author `templates/{repo-init,story,epic,initiative}.yaml` at the repository root, converted from `template-dsl-draft.md` §3 to DSL v1 spelling (`uses:` instead of `run: git.worktree`, a `gate` on every executable step, slug step ids). Add `Settings.TEMPLATES_DIR` (AD-20) and its `.env.example` line so the backend has a configured path to read them from once 3.3 seeds them; wire nothing else up (seeding and the versions API are 3.3).

## Boundaries & Constraints

**Always:**
- Every step declares `gate`; ids are slugs (`^[a-z][a-z0-9-]*$` -- `commit-guard`, never `commit_guard`).
- `story@1` is a callee only: no `git.worktree`/checkout step.
- `epic@1` has no separate install step: `install_command` runs inside `git.worktree` (spine "Shipped kinds").
- `repo-init@1`'s branch literal is `chore/bmad-init` on `checkout`, `push` and `link`.
- A new setting is added to `Settings` and to `.env.example` in the same change (AD-20).

**Never:**
- Never parse Template YAML anywhere but `application/templates/validate.py` (AD-15) -- this story only supplies input files and reads them through it in tests.
- Never restate the step-kind registry: kinds, gates and `with` keys come from `application/steps.KIND_META` (AD-9); the four files are checked against it, not against a second list.
- Never touch `stories.yaml`, `epics.yaml`, `SPEC.md`, any `AGENTS.md`, or any other pre-existing test file. The one anchor exception exercised by this story is narrow and explicit: `backend-api/tests/unit/test_settings.py`'s `BACKEND_VARIABLES` and `backend-api/tests/unit/test_env_contract.py`'s two literal-count assertions, both re-expressed as values derived from `.env.example`/`Settings` rather than hand-maintained, per operator authorisation -- with new tests added in the same commit whose coverage strictly exceeds what the literals covered.

## I/O & Edge-Case Matrix

| Input | Expected output |
| --- | --- |
| `templates/story.yaml`, `epic.yaml`, `initiative.yaml`, `repo-init.yaml`, each validated with a fake `TemplateVersionRepository` holding the other three | `errors == ()`, `unvalidated == ()` |
| Each file loaded through `validate()` | `template.version == 1`, `template.name` equals the file stem |
| `initiative@1`'s `epic` call | binds `epic: "{{epic}}"` (the `for_each as: epic` item) to the callee's `item`-typed `epic` input |
| `epic@1`'s `story` call | binds `story: "{{story}}"` (the `for_each as: story` item) to the callee's `item`-typed `story` input |
| `story@1` parsed | no `git.worktree` step; `verify` step has `redispatch == "build"`, `redispatch_max == 1`; `build.agent.expect_files` has exactly one entry; `build.timeout_min == 90` |
| `epic@1` parsed | exactly one `for_each`, `pause_after_item_when == "story.done_checkpoint"`; no `bmad.install` step; `baseline.on_fail == "fail"` |
| `repo-init@1` parsed | exactly one `bmad.install` step; `checkout`/`push`/`link` all carry `branch == "chore/bmad-init"` |
| `Settings.TEMPLATES_DIR` absent from `.env.example`, or vice versa | `scripts/check_env_contract.py` fails (`make lint`) -- verified by the existing, now-derived `test_env_contract.py` suite |

## Code Map

Read-only anchors that decide whether this lands (do not edit any of them, beyond the one exercised exception above):

- `backend-api/tests/unit/test_settings.py`, `backend-api/tests/unit/test_env_contract.py` -- the exercised exception; every other pre-existing test file is untouched.
- `backend-api/src/orchestrator/application/templates/validate.py` (+ siblings `keys.py`, `table.py`, `inputs.py`, `agent.py`, `expressions.py`, `calls.py`, `model.py`, `lines.py`) -- the authority on what parses; read in full before authoring the YAML (slugs, `with_keys` per kind, the `run:` sugar, the expression grammar's bare-field rule for `pause_when`/`escalate_when`).
- `backend-api/src/orchestrator/application/steps/__init__.py` `KIND_META` -- the accepted kinds, gates, timeouts and `with` keys; nothing here is restated.
- `backend-api/tests/unit/fakes/templates.py` `FakeTemplateVersionRepository` -- the one fake; not duplicated.
- `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` variable table (~line 428) -- extended, not restructured, with `TEMPLATES_DIR`.

Patterns to copy:

- `backend-api/tests/unit/application/templates/fixtures/full-valid.yaml`, `initiative-chain.yaml`, `callee-story.yaml` -- the YAML style 3.1's own suite already validates against.
- `backend-api/tests/unit/application/templates/__init__.py` `fixture()` -- not reused directly (this story reads `templates/` at the repo root, not the fixtures folder) but the same "read the file, don't restate it" idea.

## Tasks & Acceptance

1. `templates/story.yaml`, `templates/epic.yaml`, `templates/initiative.yaml`, `templates/repo-init.yaml` -- DSL v1, converted from the draft per the brief's inlined binding rules.
2. `backend-api/tests/unit/application/templates/test_shipped_templates.py` -- reads the four files relative to the repository root, validates each against a fake repository holding the other three (callees' `calls` pinned as saving them would), and asserts every row of the I/O matrix above.
3. `backend-api/src/orchestrator/infrastructure/settings.py` -- `templates_dir: Path` (no absolute-path validator: the development value is relative).
4. `.env.example` -- `TEMPLATES_DIR=/app/templates`.
5. `backend-api/tests/unit/test_settings.py` -- `BACKEND_VARIABLES` derived from `env_example_variables() - COMPOSE_ONLY_VARIABLES` instead of a hand-maintained literal; three new tests proving the derivation moves with the contract file and that the top-level assertion still fails in both drift directions.
6. `backend-api/tests/unit/test_env_contract.py` -- the `"25"`/`"31"` substring checks replaced by a derived-substring test plus a new test that parses the success line's exact three numbers and checks them against fresh calls to `settings_variables()`, `env_example_variables()` and `COMPOSE_ONLY_VARIABLES`, plus a test proving the contract-side count shrinks when the file does.
7. `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` -- `TEMPLATES_DIR` added to the backend-api volumes row.

**Acceptance Criteria** (the brief's, verified by task 2's suite):

- Given the four files, when each is validated with a fake repository containing the other three, then every result has no errors and an empty `unvalidated` list.
- Given `initiative@1`, when its calls are resolved, then the call chain is `initiative -> epic -> story` at depth 3, and every callee input is bound with a matching type.
- Given `story@1`, when parsed, then it has no `git.worktree` step, `verify.on_fail` is `{redispatch: build, max: 1}`, `build.expect.files` has one glob, and `build.timeout_min` is 90.
- Given `epic@1`, when parsed, then it has exactly one `for_each` with `pause_after_item_when: story.done_checkpoint`, no `install` step, and `baseline.on_fail` is `fail`.
- Given `repo-init@1`, when parsed, then its branch literal is `chore/bmad-init` on `checkout`, `push`, and `link`, and it contains one `bmad.install` step.
- Given the four files, when loaded through the YAML loader, then each `version` is the integer `1` and each `name` equals the file stem.

## Spec Change Log

- 2026-09-05 -- Operator-authorised, narrow revision of two frozen anchor test files (`test_settings.py`, `test_env_contract.py`) to add `Settings.TEMPLATES_DIR` without a permanent hand-maintained duplicate list; see Design Notes.

## Design Notes

**Why this needed an anchor exception, and why the fix is a derivation, not a suppression.** Adding any `Settings` field breaks `test_settings.py::test_every_backend_variable_is_a_typed_field` (a hardcoded 25-name set) and `test_env_contract.py::test_the_success_line_reports_both_sides` (hardcoded `"25"`/`"31"` substrings) -- both hand-maintained shadows of the same fact `.env.example` already states once. The fix makes each of them read that one source instead of a second copy: `BACKEND_VARIABLES = env_example_variables() - COMPOSE_ONLY_VARIABLES` (never `Settings.model_fields`, which would make the check `fields == fields` and check nothing), and the two literals replaced with live calls to `settings_variables()` / `env_example_variables()` / `COMPOSE_ONLY_VARIABLES`. Three new tests in `test_settings.py` and two in `test_env_contract.py` prove the derivation actually reads the file (a trimmed copy of `.env.example` shrinks the derived set by exactly the trimmed variable) and that the top-level assertions still fail in both directions of drift (an extra `Settings` field, or a contract variable the field set no longer covers) -- strictly more than the single static equality/substring checks covered before. The next story that adds a setting will not need this operator conversation again.

**`TEMPLATES_DIR` is not validated absolute.** Unlike `work_dir`/`agent_home`, the brief's own default differs by environment (`../templates` in development, `/app/templates` in the image), so the `_must_be_absolute` validator is deliberately not applied to it.

**Step ids are slugs, not the draft's variable names.** `commit_guard` (draft) -> `commit-guard`; matches the architecture spine's own FR-9..FR-11 mapping row, which already spells it hyphenated.

**`uses: template` steps carry no `gate`.** They are not rows (AD-15/keys.py design notes); declaring one would not be an error but is absent here to match the draft skeletons and keep the `unvalidated` list legitimately empty rather than accidentally so.

## Verification

**Commands:**
- `cd backend-api && uv run pytest tests/unit -q` -- whole unit suite green, including the new shipped-templates suite and the revised settings/env-contract suites.
- `make lint` -- ruff, mypy strict, import-linter, the test-pair gate and the env-contract check all pass.
- `make test` -- unit suite green and the 100% branch-coverage report over `domain/` + `application/` passes.

## Auto Run Result

Status: done
