---
story: "5-8"
epic: 5
title: Harness readiness
requirements: [FR-33, FR-8 (harness line), FR-14 (readiness gate), AR-15]
binds: [AD-10, AD-11, AD-16]
---

# Story 5.8 — Harness readiness

As the Operator,
I want a harness offered to me only after it has actually run one story to `done` on a fixture repository with its trace and its spend attributable,
So that "enabled" means proven, and a broken adapter or a changed version can never quietly eat a real Run.

## Scope

**In:** the built-in Project `readiness` and its fixture Repository, `scripts/readiness_fixture.sh` + `fixtures/readiness-repo/`, `application/use_cases/harness_readiness.py` (`start`, `evaluate`, `sync_pins`), `POST /api/v1/harnesses/{name}/readiness`, `GET /harnesses` completed, the walker finish hook calling `evaluate`, the readiness lines on New workflow, tests.
**Out:** running it for real against the host (5.11).

## Binding rules (inlined)

- **Fixture (AD-10, Structural Seed).** `fixtures/readiness-repo/` in the orchestrator repository holds a minimal project: `README.md`, `check.sh` (the quality gate: exits 0 when `HELLO.md` exists and contains `hello`, else 1), `specs/readiness/SPEC.md` (a kernel with one capability: "a file HELLO.md containing the word hello exists"), `specs/readiness/stories.yaml` with one story `id: "1"`, title `Create HELLO.md`, description pointing at the capability, no checkpoints. `scripts/readiness_fixture.sh` (run at container start, idempotent): creates a bare origin at `$WORK_DIR/readiness/origin.git` and, from the fixture files, a `main` branch with `_bmad/` installed at `BMAD_VERSION` (`npx bmad-method@… install --yes --modules bmm --tools claude-code,codex,opencode --directory …`) and the two gitignore lines, pushed to the origin.
- **Built-in Project.** Seeded at startup: Project `readiness` (slug `readiness`, `builtin: true`, cannot be edited or deleted — the API returns 409 on `PUT`, the UI hides *Edit*) with one Repository `readiness-repo` (`url: file://$WORK_DIR/readiness/origin.git`, `default_branch: main`, `quality_gate_command: sh check.sh`, default `test_globs`), clone check run at seeding. Add `project.builtin` (migration).
- **`start(name)`** → `create_run` with `epic@1`, `project: readiness`, `repository: readiness-repo`, `base_branch: main`, `branch: readiness/{name}/{YYYY-MM-DD}` (`-2`, `-3` suffix when a non-terminal Run holds it), `spec_folder: specs/readiness`, `harness: name`, `budget_usd: settings.READINESS_BUDGET_USD` (default 5), `skip_harness_check=True`; 409 when a non-terminal readiness Run for that harness exists. The push goes to the local origin only (never to GitHub).
- **`evaluate(run_id)`**, called by the walker's finish hook for every Run of Project `readiness` (any terminal status): lines, each `{check, ok, text}` in order — `story file done` (the story frame's build row `done` and the story file at `end_sha` reads `status: done`); `session id recorded` (attempt `session_id` non-empty); `trace observed` (`Tracer.attempt_observed(run_id, attempt_id)`); `spend attributable` (the attempt's `cost_provisional == false` and `calls > 0`); `verify exit 0` (the frame's verify row `done`, not skipped); `run done` (Run status `done`). All ok → `harness.enabled = true`, `failing_check = None`; else `enabled = false`, `failing_check = "{check}: {text}"` of the first failing line; always `last_readiness_at = now`, `last_readiness_run_id = run_id`. Written only here.
- **`sync_pins()`** at container start: for each harness, if `version_pin != settings pin` → `enabled = false`, `failing_check = "version pin changed: {old} → {new}"`, `version_pin = new`. A readiness Run in flight is unaffected; parked Runs keep their harness (AD-10: `enabled` is read only by `create_run` and pre-flight).
- **Endpoints.** `POST /harnesses/{name}/readiness` → 201 `{run}`; `GET /harnesses` → items now with `last_readiness_run_id` and `lines` of the last evaluation.
- **New workflow (UX-DR8).** The harness line reads `{name} · enabled | disabled: {failing_check or "no readiness run"} · last readiness {time} · re-run readiness`; *re-run readiness* posts to the endpoint and links to the created Run's card. Readiness Runs are ordinary Runs on the Board with `kind_label: readiness`.

## Acceptance criteria

**Given** startup on an empty database
**When** seeding runs
**Then** Project `readiness` exists with `builtin: true` and its Repository's clone check is `ok` with `bmad_version == BMAD_VERSION`; `PUT /projects/{readiness id}` returns 409.

**Given** `POST /harnesses/claude/readiness`
**When** called
**Then** an `epic@1` Run is created on branch `readiness/claude/{date}` with the fixture spec folder, `skip_harness_check` bypassed the disabled line, and the Board shows it with `readiness` in place of progress.

**Given** a finished readiness Run whose attempt has a session id, a non-provisional spend with calls, an observed trace, a `done` story file, and a `done` verify row
**When** `evaluate` runs on the fakes
**Then** `claude` is `enabled` with `failing_check None` and `last_readiness_at` set; **and** with `attempt_observed` false, `enabled` is false and `failing_check` is `trace observed: no spans for attempt …`; each other line is tested failing alone.

**Given** `CLAUDE_CODE_VERSION` changed since the last start
**When** `sync_pins` runs
**Then** `claude` is disabled with `version pin changed: 2.1.258 → 2.1.260`.

**Given** the New workflow harness list after a failed evaluation
**When** rendered
**Then** the line reads `claude · disabled: trace observed: … · last readiness {time} · re-run readiness`.

## Implementation notes

- `fixtures/readiness-repo/` is committed; the script copies it, never edits it in place.
- Finish hook: extend `use_cases/run_finished.on_finished` (4.10) with the readiness branch.
- Settings: `READINESS_BUDGET_USD` + `.env.example`.

## Verification

```bash
make lint && make test && make openapi && make up && make e2e-api
```

## Sources for detail only

PRD FR-33 (lines), FR-8. Spine AD-10 (readiness paragraph), AD-16 (fixture with `_bmad/`), Structural Seed (`scripts/readiness_fixture.sh`, `fixtures/readiness-repo/`). `EXPERIENCE-v1.md` §2.1 (harness list).
