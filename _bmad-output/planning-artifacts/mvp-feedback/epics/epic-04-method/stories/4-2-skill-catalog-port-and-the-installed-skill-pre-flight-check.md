---
title: SkillCatalog port and the installed-skill pre-flight check
type: feature
created: '2026-09-17'
status: done
baseline_revision: 01de2a00ecd2ad609cd765efcdc9617460a12e1b
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** A `skill:` step that names a non-existent skill fails silently at dispatch time; pre-flight has no check that would catch the typo before a Run starts.

**Approach:** Add a `SkillCatalog` domain port (read-only view of `skills-manifest.json`), its `FsSkillCatalog` infrastructure adapter (reads `{agent_home}/.claude/skills-manifest.json`), one shared fake, and an installed-skill pre-flight check that fails early — naming the absent skill — whenever the plan contains a `skill:` agent step whose name is not in the catalog.

## Boundaries & Constraints

**Always:**
- AD-2: `domain/` and `application/` stay pure — no `os`, `json`, or filesystem calls; the infrastructure adapter is the only I/O path.
- AD-16: `SkillCatalog` is a domain port; `validate.py` does not change.
- `agent_home` is already in `Settings`; no new setting is added.
- The installed-skill check appears in `_lines()` immediately after `harness_line`, uses the same `skip`/`fail`/`ok` idiom, and never raises.
- The shared fake lives in `tests/unit/fakes/skill_catalog.py` and is the only double for `SkillCatalog` used across all unit tests.
- `FsSkillCatalog` reads `{"skills": [...]}` from the manifest path; returns `None` (catalog unavailable → `skip`) if the file is missing or unparseable.

**Block If:** Any ambiguity about whether the check should skip or fail when the manifest file is absent cannot be resolved from the story description alone.

**Never:**
- Do not change `validate.py`.
- Do not add a new `Settings` field — use `settings.agent_home`.
- Do not pin shipped template content in tests.
- Do not make the domain or application layer import `json`, `os`, or `pathlib.Path` for I/O.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Catalog unavailable | `skills-manifest.json` missing | `skip` line: "catalog unavailable" | No error |
| No skill steps in plan | Plan has no `skill:` agent steps | No installed-skill line in output | — |
| All skills installed | Plan has `skill: foo`; manifest contains `foo` | `ok` line: "ok" | No error |
| One skill absent | Plan has `skill: bar`; manifest lacks `bar` | `fail` line: "not installed: bar" | `fix` sentence suggests image rebuild |
| Multiple absent | Plan has `skill: x` and `skill: y`; manifest lacks both | Two `fail` lines, one per missing name | Both names reported |
| Plan not built | `ctx.plan is None` | Empty list (no installed-skill lines) | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/skill_catalog.py` — NEW port; `SkillCatalog` `@runtime_checkable Protocol` with `installed_skills() -> frozenset[str] | None`; `None` = manifest unavailable
- `backend-api/src/orchestrator/infrastructure/skill_catalog.py` — NEW `FsSkillCatalog(manifest_path: Path)`; `installed_skills()` reads `{"skills": [...]}` JSON; returns `None` on `FileNotFoundError` or parse error; returns `frozenset[str]` on success
- `backend-api/src/orchestrator/application/preflight/model.py:37` — ADD `CHECK_INSTALLED_SKILL = "installed skill"` after `CHECK_HARNESS` on line 36
- `backend-api/src/orchestrator/application/preflight/checks.py:70-84` — `Context` dataclass; ADD `skill_catalog: SkillCatalog` field; import `SkillCatalog` from `domain/ports/skill_catalog`; import `CHECK_INSTALLED_SKILL` from model
- `backend-api/src/orchestrator/application/preflight/checks.py:232-258` — `harness_line` and `_has_agent_step`; the new `installed_skill_lines` function mirrors this area; walks `ctx.plan.rows` for `AGENT_KIND` rows with `with_resolved.get("skill")`; calls `ctx.skill_catalog.installed_skills()`; returns `list[Line]`
- `backend-api/src/orchestrator/application/use_cases/preflight.py:43-57` — `PreflightPorts`; ADD `skill_catalog: SkillCatalog` field; import `SkillCatalog`
- `backend-api/src/orchestrator/application/use_cases/preflight.py:92-104` — `Context` construction; ADD `skill_catalog=ports.skill_catalog`
- `backend-api/src/orchestrator/application/use_cases/preflight.py:137-153` — `_lines()`; ADD `lines += checks.installed_skill_lines(ctx)` immediately after `checks.harness_line(ctx)` call on line 148
- `backend-api/src/orchestrator/api/providers.py:138-152` — `_preflight_ports`; ADD `skill_catalog=FsSkillCatalog(settings.agent_home / ".claude" / "skills-manifest.json")` to `PreflightPorts(...)` construction; import `FsSkillCatalog`
- `backend-api/tests/unit/fakes/skill_catalog.py` — NEW `FakeSkillCatalog`; `__init__(self, skills: frozenset[str] | None = frozenset())`; `installed_skills()` returns `self._skills`; `None` simulates unavailable catalog
- `backend-api/tests/unit/test_preflight_installed_skill.py` — NEW; tests for the installed-skill check using `FakeSkillCatalog` and minimal `Context` stubs

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/ports/skill_catalog.py` -- CREATE -- `SkillCatalog` Protocol: `installed_skills(self) -> frozenset[str] | None`; decorated `@runtime_checkable`; `None` means catalog unavailable
- `backend-api/src/orchestrator/infrastructure/skill_catalog.py` -- CREATE -- `FsSkillCatalog` class: `__init__(self, manifest_path: Path)`; `installed_skills()` opens and parses `{"skills": [...]}` JSON; returns `frozenset(data["skills"])` on success; returns `None` on `FileNotFoundError`, `KeyError`, `json.JSONDecodeError`, or any parse failure
- `backend-api/src/orchestrator/application/preflight/model.py` -- ADD constant -- `CHECK_INSTALLED_SKILL = "installed skill"` inserted after `CHECK_HARNESS` on line 36; export from module unchanged (no `__all__`)
- `backend-api/src/orchestrator/application/preflight/checks.py` -- EXTEND -- add `skill_catalog: SkillCatalog` to `Context` dataclass; add import for `SkillCatalog` from `orchestrator.domain.ports.skill_catalog`; add import for `CHECK_INSTALLED_SKILL` from model; add `installed_skill_lines(ctx: Context) -> list[Line]` function after `harness_line`
- `backend-api/src/orchestrator/application/use_cases/preflight.py` -- EXTEND -- add `skill_catalog: SkillCatalog` to `PreflightPorts` dataclass; add import for `SkillCatalog`; pass `skill_catalog=ports.skill_catalog` into `Context`; add `lines += checks.installed_skill_lines(ctx)` in `_lines()` after the `harness_line` call
- `backend-api/src/orchestrator/api/providers.py` -- EXTEND -- import `FsSkillCatalog` from `orchestrator.infrastructure.skill_catalog`; add `skill_catalog=FsSkillCatalog(settings.agent_home / ".claude" / "skills-manifest.json")` to `PreflightPorts(...)` in `_preflight_ports`
- `backend-api/tests/unit/fakes/skill_catalog.py` -- CREATE -- `FakeSkillCatalog(skills: frozenset[str] | None = frozenset())`: stores `_skills`; `installed_skills()` returns `self._skills`
- `backend-api/tests/unit/test_preflight_installed_skill.py` -- CREATE -- unit tests covering every I/O matrix row: (a) catalog unavailable → `skip`; (b) no skill steps → empty list; (c) skill present → `ok`; (d) one skill absent → one `fail` line naming the skill; (e) two skills absent → two `fail` lines; (f) plan is `None` → empty list

**Acceptance Criteria:**
- Given a plan containing an `agent` step with `skill: bmad-missing`, when `installed_skill_lines` is called with a `FakeSkillCatalog(frozenset({"bmad-build-auto"}))`, then exactly one `fail` Line is returned whose `text` contains `"bmad-missing"`
- Given `FakeSkillCatalog(None)` (catalog unavailable), when `installed_skill_lines` is called with a plan that has a skill step, then exactly one `skip` Line is returned
- Given a plan with no `skill:` agent steps, when `installed_skill_lines` is called, then an empty list is returned regardless of catalog state
- Given `make lint`, then ruff, mypy, and import-linter all pass (in particular: `domain/ports/skill_catalog.py` contains no I/O imports; `application/preflight/checks.py` imports `SkillCatalog` only from `domain/ports/`)
- Given `make test`, then domain and application coverage stays at 100% branch

## Design Notes

`installed_skill_lines` returns `list[Line]` (like `branch_lines`) rather than a single `Line` so that a plan with multiple distinct missing skills emits one `fail` line per name, giving the operator the full list in one pre-flight pass. The `ok` case emits a single `ok` line; the `skip` and "no skill steps" cases emit one and zero lines respectively.

`FsSkillCatalog` reads from `agent_home/.claude/skills-manifest.json` (the claude harness path). Both harness manifests carry identical skill names (they're both generated from the same `ia-agents-skills/` source), so one path is sufficient for the check.

`None` return from `installed_skills()` means "manifest file not found" — e.g. in a dev environment where the image hasn't been built yet. The pre-flight check treats this as `skip`, not `fail`, matching the convention that a missing prerequisite silently skips its dependent line.

## Verification

**Commands:**
- `make lint` -- expected: ruff format+lint, mypy, import-linter all green; no AD-2 violations in domain or application
- `make test` -- expected: new `test_preflight_installed_skill.py` green; domain + application 100% branch coverage maintained

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 2, low 1)
- defer: 0
- reject: 11
- addressed_findings:
  - `[medium]` `[patch]` `FsSkillCatalog` caught only `FileNotFoundError`; `PermissionError`/`IsADirectoryError` (other `OSError` subclasses) propagate instead of returning `None` — changed to `OSError`
  - `[medium]` `[patch]` No use-case-level test verified that a `fail` line from `installed_skill_lines` flows into `start_allowed=False`; removing the `_lines()` wiring call would not break any test — added `test_preflight_installed_skill_wiring.py`
  - `[low]` `[patch]` `data["skills"]` not validated as a list; a string value produces a frozenset of characters, silently matching no skill names — added `isinstance(skills, list)` guard returning `None` on wrong type

## Auto Run Result

Status: done

**Summary:** Added `SkillCatalog` domain port (`domain/ports/skill_catalog.py`), `FsSkillCatalog` infrastructure adapter (reads `{agent_home}/.claude/skills-manifest.json`), shared `FakeSkillCatalog` fake, `CHECK_INSTALLED_SKILL` constant, and `installed_skill_lines` pre-flight check function wired into `_lines()` after `harness_line`. The check scans the plan's agent steps for `skill:` values, consults the catalog, and emits one `fail` line per absent skill name (or `skip` when the catalog is unavailable).

**Files changed:**
- `backend-api/src/orchestrator/domain/ports/skill_catalog.py` — new; `SkillCatalog` `@runtime_checkable` Protocol with `installed_skills() -> frozenset[str] | None`
- `backend-api/src/orchestrator/infrastructure/skill_catalog.py` — new; `FsSkillCatalog` adapter; reads manifest, validates `skills` is a list, catches `OSError`/`KeyError`/`JSONDecodeError`/`TypeError` → returns `None`
- `backend-api/src/orchestrator/application/preflight/model.py` — added `CHECK_INSTALLED_SKILL = "installed skill"` constant
- `backend-api/src/orchestrator/application/preflight/checks.py` — added `skill_catalog: SkillCatalog | None = None` to `Context`; added `installed_skill_lines` function
- `backend-api/src/orchestrator/application/use_cases/preflight.py` — added `skill_catalog: SkillCatalog | None = None` to `PreflightPorts`; wired into `Context` construction and `_lines()`
- `backend-api/src/orchestrator/api/providers.py` — added `FsSkillCatalog` import and `skill_catalog=FsSkillCatalog(...)` to `_preflight_ports`
- `backend-api/tests/unit/fakes/skill_catalog.py` — new; `FakeSkillCatalog` shared fake with runtime Protocol assertion
- `backend-api/tests/unit/test_preflight_installed_skill.py` — new; 13 tests covering all I/O matrix rows plus `FsSkillCatalog` adapter
- `backend-api/tests/unit/application/test_preflight_installed_skill_wiring.py` — new; 1 test verifying `installed_skill_lines` fail output makes `start_allowed` False

**Review findings breakdown:** 3 patches applied (0 high, 2 medium, 1 low); 0 deferred; 11 rejected.

**Follow-up review recommended:** true — score 3×2 + 1×1 = 7 (≥ 5 threshold), driven by 2 medium patches (OSError coverage gap and missing wiring test).

**Verification performed:**
- `make lint`: PASS — ruff format+lint, mypy, import-linter, env-contract, test-pairs, gen:api, tsc, eslint, prettier all green
- `make test`: PASS — 6329 backend tests passed (23 skipped); domain+application at 100% branch coverage (0 missed branches)

**Residual risks:**
- `skill_catalog=None` default on `PreflightPorts` and `Context` means existing test factories that omit the field silently exercise the `skip` path, not the `fail` path; new test in `test_preflight_installed_skill_wiring.py` closes the gap for the wiring, but end-to-end e2e coverage (calling `POST /runs/preflight` with a real plan and an absent skill) remains future work
