"""The four exemplar Templates (CAP-2, SPEC epic-03-templates 3.2): validate, compose, gate.

`repo-init`, `story`, `epic` and `initiative` are DSL v1 in the flesh: the brief's binding
rules superseding `template-dsl-draft.md` §3 (`uses: <kind>` instead of `run: git.worktree`,
`gate` on every executable step). The files are the frozen copies under
`fixtures/exemplars/` — a snapshot of the shipped Templates taken when the suite was
decoupled from `templates/*.yaml`, so the shipped files evolve freely without breaking the
DSL coverage here (the shipped files themselves are covered by `test_shipped_smoke.py`).
Each file's text is run through `validate()` against a fake repository holding the other
three, pinned the way saving `epic@1` and `initiative@1` would pin their callees (AD-15).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.templates.model import ForEach, ParsedTemplate, Step
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: The frozen exemplar Templates — never the shipped `templates/*.yaml`.
TEMPLATES_DIR = Path(__file__).resolve().parent / "fixtures" / "exemplars"

NAMES = ("repo-init", "story", "epic", "initiative")

#: `story@1` build.timeout_min, per the brief's AC (a liveness step, longer than the default).
EXPECTED_BUILD_TIMEOUT_MIN = 90


def _read(name: str) -> str:
    return (TEMPLATES_DIR / f"{name}.yaml").read_text()


TEXTS: dict[str, str] = {name: _read(name) for name in NAMES}


@pytest.fixture
def templates() -> FakeTemplateVersionRepository:
    """All four shipped versions, `calls` pinned exactly as saving each one would record."""
    return FakeTemplateVersionRepository(
        [
            TemplateVersion(name="repo-init", version=1, yaml=TEXTS["repo-init"], hash="sha"),
            TemplateVersion(name="story", version=1, yaml=TEXTS["story"], hash="sha"),
            TemplateVersion(
                name="epic",
                version=1,
                yaml=TEXTS["epic"],
                hash="sha",
                calls=(TemplateRef(name="story", version=1),),
            ),
            TemplateVersion(
                name="initiative",
                version=1,
                yaml=TEXTS["initiative"],
                hash="sha",
                calls=(TemplateRef(name="epic", version=1),),
            ),
        ]
    )


def _entries(template: ParsedTemplate) -> dict[str, Step | ForEach]:
    """Every top-level step or `for_each`, by id."""
    return {entry.id: entry for entry in template.steps}


def _inner(loop: Step | ForEach, step_id: str) -> Step:
    """One step nested inside a `for_each`, by id."""
    assert isinstance(loop, ForEach)
    found = {child.id: child for child in loop.steps}[step_id]
    return found


# --- AC1: every file validates clean, with nothing gateless ------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_every_shipped_template_validates_with_no_errors(
    templates: FakeTemplateVersionRepository, name: str
) -> None:
    result = validate(TEXTS[name], templates=templates)

    assert result.errors == ()
    assert result.template is not None


@pytest.mark.parametrize("name", NAMES)
def test_every_shipped_template_leaves_nothing_unvalidated(
    templates: FakeTemplateVersionRepository, name: str
) -> None:
    result = validate(TEXTS[name], templates=templates)

    assert result.unvalidated == ()


# --- loaded through the YAML loader: name and version --------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_version_is_the_integer_one_and_name_equals_the_file_stem(
    templates: FakeTemplateVersionRepository, name: str
) -> None:
    result = validate(TEXTS[name], templates=templates)

    assert result.template is not None
    assert result.template.version == 1
    assert result.template.name == name


# --- AC2: initiative -> epic -> story at depth 3, item bindings on both calls ---------------


def test_initiative_calls_epic_binding_the_loop_item_to_an_item_input(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["initiative"], templates=templates)

    assert result.template is not None
    loop = result.template.steps[0]
    call = _inner(loop, "epic")

    assert call.call is not None
    assert call.call.name == "epic"
    assert call.call.version == 1
    assert dict(call.call.inputs)["epic"] == "{{epic}}"


def test_epic_calls_story_binding_the_loop_item_to_an_item_input(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["epic"], templates=templates)

    assert result.template is not None
    loop = _entries(result.template)["stories"]
    call = _inner(loop, "story")

    assert call.call is not None
    assert call.call.name == "story"
    assert call.call.version == 1
    assert dict(call.call.inputs)["story"] == "{{story}}"


def test_the_call_chain_is_three_deep_and_would_reject_a_fourth_level(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`initiative -> epic -> story` is depth 3 and passes; confirms the fixture is pinned
    the way the real seeding would pin it, not merely absent from the fake."""
    deeper = FakeTemplateVersionRepository(
        [
            *templates.versions.values(),
            TemplateVersion(
                name="leaf", version=1, yaml="name: leaf\nversion: 1\nsteps: []\n", hash="sha"
            ),
        ]
    )
    # story@1 itself calls nothing further, so depth stays at 3 regardless of `leaf`.
    result = validate(TEXTS["initiative"], templates=deeper)

    assert result.errors == ()


# --- AC3: story@1 ----------------------------------------------------------------------------


def test_story_has_no_checkout_step(templates: FakeTemplateVersionRepository) -> None:
    result = validate(TEXTS["story"], templates=templates)

    assert result.template is not None
    steps = _entries(result.template)
    assert "checkout" not in steps
    assert all(step.uses != "git.worktree" for step in steps.values() if isinstance(step, Step))


def test_story_verify_redispatches_to_build_once(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["story"], templates=templates)

    assert result.template is not None
    verify = _entries(result.template)["verify"]
    assert isinstance(verify, Step)
    assert verify.on_fail is None
    assert verify.redispatch == "build"
    assert verify.redispatch_max == 1


def test_story_build_expects_one_glob_and_times_out_at_ninety_minutes(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["story"], templates=templates)

    assert result.template is not None
    build = _entries(result.template)["build"]
    assert isinstance(build, Step)
    assert build.timeout_min == EXPECTED_BUILD_TIMEOUT_MIN
    assert build.agent is not None
    assert len(build.agent.expect_files) == 1


# --- AC4: epic@1 -------------------------------------------------------------------------


def test_epic_has_exactly_one_for_each_paused_after_the_done_checkpoint(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["epic"], templates=templates)

    assert result.template is not None
    loops = [entry for entry in result.template.steps if isinstance(entry, ForEach)]
    assert len(loops) == 1
    assert loops[0].pause_after_item_when == "story.done_checkpoint"


def test_epic_has_no_install_step(templates: FakeTemplateVersionRepository) -> None:
    result = validate(TEXTS["epic"], templates=templates)

    assert result.template is not None
    steps = _entries(result.template)
    assert "install" not in steps
    assert all(step.uses != "bmad.install" for step in steps.values() if isinstance(step, Step))


def test_epic_baseline_fails_the_run_outright(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["epic"], templates=templates)

    assert result.template is not None
    baseline = _entries(result.template)["baseline"]
    assert isinstance(baseline, Step)
    assert baseline.on_fail == "fail"


# --- AC5: repo-init@1 ----------------------------------------------------------------------


def test_repo_init_branch_literal_is_chore_bmad_init_on_every_git_step(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["repo-init"], templates=templates)

    assert result.template is not None
    steps = _entries(result.template)
    for step_id in ("checkout", "push", "link"):
        step = steps[step_id]
        assert isinstance(step, Step)
        assert dict(step.params)["branch"] == "chore/bmad-init"


def test_repo_init_has_exactly_one_bmad_install_step(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate(TEXTS["repo-init"], templates=templates)

    assert result.template is not None
    install_steps = [
        step
        for step in result.template.steps
        if isinstance(step, Step) and step.uses == "bmad.install"
    ]
    assert len(install_steps) == 1
