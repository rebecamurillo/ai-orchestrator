"""`application/use_cases/templates.py` (SPEC CAP-3, FR-6): every read, write and seed rule.

`TemplatePorts` is built from the shared fakes (AD-18): `FakeTemplateVersionRepository`,
`FakeUnitOfWork`, `FakeClock`. Nothing here reaches a database — the SQLAlchemy adapter's
own shape is proved in `tests/unit/test_template_repository_adapter.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.application.use_cases.templates import (
    SeedResult,
    ShippedTemplateInvalid,
    TemplatePorts,
    TemplateValidationFailed,
    get_version,
    latest_version,
    list_templates,
    list_versions,
    save_version,
    seed_shipped,
    validate_latest,
    validate_text,
)
from orchestrator.domain.entities.template import (
    TemplateCaller,
    TemplateCallRef,
    TemplateRef,
    TemplateVersion,
)
from orchestrator.domain.errors import Invalid, NotFound
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"

#: Calls `leaf@1` directly at the root — one `uses: template` step, no `for_each`.
ROOT_CALLER = (
    "name: root-caller\n"
    "version: 1\n"
    "steps:\n"
    "  - id: leaf\n"
    "    uses: template\n"
    "    with:\n"
    "      name: leaf\n"
    "      version: 1\n"
    "      inputs: {}\n"
)

#: Calls `leaf@1` from inside a `for_each` — proves `_calls_of` walks one level in.
LOOP_CALLER = (
    "name: loop-caller\n"
    "version: 1\n"
    "inputs:\n"
    "  spec_folder:\n"
    "    type: path\n"
    "    required: true\n"
    "steps:\n"
    "  - id: items\n"
    '    for_each: "{{spec_folder}}/items.yaml"\n'
    "    as: item\n"
    "    steps:\n"
    "      - id: leaf\n"
    "        uses: template\n"
    "        with:\n"
    "          name: leaf\n"
    "          version: 1\n"
    "          inputs: {}\n"
)

WITH_INPUT = (
    "name: has-input\n"
    "version: 1\n"
    "inputs:\n"
    "  spec_folder:\n"
    "    type: path\n"
    "    required: true\n"
    "steps:\n"
    "  - id: sync\n"
    "    uses: git.sync\n"
    "    gate: deterministic\n"
)

INVALID_YAML = "not: [valid\n"


def a_stored(name: str = "leaf", number: int = 1, **overrides: object) -> TemplateVersion:
    fields: dict[str, object] = {
        "name": name,
        "version": number,
        "yaml": LEAF,
        "hash": "leaf-sha",
        "created_at": AT,
    }
    fields.update(overrides)
    return TemplateVersion(**fields)  # type: ignore[arg-type]


def ports(templates: FakeTemplateVersionRepository | None = None) -> TemplatePorts:
    uow = FakeUnitOfWork()
    uow.__enter__()
    return TemplatePorts(
        uow=uow, templates=templates or FakeTemplateVersionRepository(), clock=FakeClock(AT)
    )


# --- list_templates --------------------------------------------------------------------


def test_list_templates_delegates_to_the_repository() -> None:
    templates = FakeTemplateVersionRepository([a_stored()])

    assert list_templates(ports(templates)) == templates.list()


def test_list_templates_is_empty_when_nothing_is_stored() -> None:
    assert list_templates(ports()) == []


# --- list_versions -----------------------------------------------------------------------


def test_list_versions_is_ascending() -> None:
    templates = FakeTemplateVersionRepository([a_stored(number=1), a_stored(number=2)])

    assert list_versions(ports(templates), "leaf") == [1, 2]


def test_list_versions_of_an_unknown_name_is_not_found() -> None:
    with pytest.raises(NotFound, match="leaf"):
        list_versions(ports(), "leaf")


# --- get_version -------------------------------------------------------------------------


def test_get_version_of_an_unknown_pair_is_not_found() -> None:
    with pytest.raises(NotFound):
        get_version(ports(), "leaf", 1)


def test_get_version_returns_the_stored_text_and_derived_inputs() -> None:
    templates = FakeTemplateVersionRepository([a_stored(yaml=WITH_INPUT, name="has-input")])

    detail = get_version(ports(templates), "has-input", 1)

    assert detail.template.yaml == WITH_INPUT
    assert [decl.name for decl in detail.inputs] == ["spec_folder"]


def test_get_version_reports_who_calls_it() -> None:
    templates = FakeTemplateVersionRepository(
        [
            a_stored(),
            a_stored(
                name="root-caller",
                yaml=ROOT_CALLER,
                calls=(TemplateRef(name="leaf", version=1),),
            ),
        ]
    )

    detail = get_version(ports(templates), "leaf", 1)

    # revised to `TemplateCaller` by the Operator decision 2026-10-02, editable workflows: a
    # `uses: template` call may omit `version`; it resolves to the callee's latest at validate
    # and plan time; no cascade.
    assert detail.called_by == (TemplateCaller(name="root-caller", version=1, pinned=True),)


# --- validate_text / validate_latest -------------------------------------------------------


def test_validate_text_reports_errors_for_broken_yaml() -> None:
    result = validate_text(ports(), INVALID_YAML)

    assert result.errors
    assert result.template is None


def test_validate_text_reports_no_errors_for_valid_yaml() -> None:
    result = validate_text(ports(), LEAF)

    assert result.errors == ()
    assert result.template is not None


def test_validate_latest_of_an_unknown_name_is_not_found() -> None:
    with pytest.raises(NotFound):
        validate_latest(ports(), "leaf")


def test_validate_latest_validates_the_highest_stored_version() -> None:
    templates = FakeTemplateVersionRepository([a_stored(number=1), a_stored(number=2)])

    result = validate_latest(ports(templates), "leaf")

    assert result.errors == ()
    assert result.template is not None
    assert result.template.version == 1  # LEAF's own text always says version 1


# --- save_version ------------------------------------------------------------------------


def test_save_version_stores_the_first_version_of_a_new_name() -> None:
    saved = save_version(ports(), "leaf", LEAF)

    assert saved.version == 1
    assert saved.name == "leaf"
    assert saved.hash
    assert saved.created_at == AT
    assert saved.id is not None


def test_save_version_commits_the_unit_of_work() -> None:
    uow = FakeUnitOfWork()
    uow.__enter__()
    fresh = TemplatePorts(uow=uow, templates=FakeTemplateVersionRepository(), clock=FakeClock(AT))
    save_version(fresh, "leaf", LEAF)

    assert uow.committed is True


def test_save_version_computes_the_next_number_from_what_is_already_stored() -> None:
    templates = FakeTemplateVersionRepository([a_stored(number=1)])
    next_version = 2
    next_text = LEAF.replace("version: 1", f"version: {next_version}")

    saved = save_version(ports(templates), "leaf", next_text)

    assert saved.version == next_version
    assert templates.list_versions("leaf") == [1, next_version]


def test_save_version_refuses_a_yaml_name_that_does_not_match_the_path() -> None:
    templates = FakeTemplateVersionRepository([a_stored()])
    # ROOT_CALLER's own `name:` is "root-caller"; posting it under "leaf" is the mismatch
    with pytest.raises(Invalid, match="name must be leaf"):
        save_version(ports(templates), "leaf", ROOT_CALLER)
    # LEAF's own `name:` is "leaf"; posting it under "root-caller" is the mismatch
    with pytest.raises(Invalid, match="name must be root-caller"):
        save_version(ports(templates), "root-caller", LEAF)


def test_save_version_refuses_a_version_number_that_is_not_the_next_one() -> None:
    templates = FakeTemplateVersionRepository([a_stored(number=1)])
    wrong_number = LEAF.replace("version: 1", "version: 5")

    with pytest.raises(Invalid, match="version must be 2"):
        save_version(ports(templates), "leaf", wrong_number)


def test_save_version_raises_the_validators_own_errors_and_writes_nothing() -> None:
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    fresh = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))

    with pytest.raises(TemplateValidationFailed) as raised:
        save_version(fresh, "leaf", INVALID_YAML)

    assert raised.value.errors
    assert templates.list() == []
    assert uow.committed is False


def test_save_version_pins_a_root_level_call_into_calls() -> None:
    templates = FakeTemplateVersionRepository([a_stored()])

    saved = save_version(ports(templates), "root-caller", ROOT_CALLER)

    assert saved.calls == (TemplateRef(name="leaf", version=1),)


def test_save_version_pins_a_call_nested_in_a_for_each() -> None:
    templates = FakeTemplateVersionRepository([a_stored()])

    saved = save_version(ports(templates), "loop-caller", LOOP_CALLER)

    assert saved.calls == (TemplateRef(name="leaf", version=1),)


def test_save_version_pins_no_calls_for_a_leaf() -> None:
    saved = save_version(ports(), "leaf", LEAF)

    assert saved.calls == ()


def test_save_version_records_the_parsed_description() -> None:
    described = WITH_INPUT.replace(
        "name: has-input\nversion: 1\n", "name: has-input\nversion: 1\ndescription: a thing\n"
    )
    templates = FakeTemplateVersionRepository()

    save_version(ports(templates), "has-input", described)

    assert templates.descriptions["has-input"] == "a thing"


# --- seed_shipped ------------------------------------------------------------------------


def test_seed_shipped_inserts_every_file_as_version_one() -> None:
    other = LEAF.replace("name: leaf", "name: other")

    results = seed_shipped(ports(), [("leaf", LEAF), ("other", other)])

    assert {result.name: result.inserted_as for result in results} == {
        "leaf": 1,
        "other": 1,
    }


def test_seed_shipped_commits_the_unit_of_work() -> None:
    uow = FakeUnitOfWork()
    uow.__enter__()
    fresh = TemplatePorts(uow=uow, templates=FakeTemplateVersionRepository(), clock=FakeClock(AT))

    seed_shipped(fresh, [("leaf", LEAF)])

    assert uow.committed is True


def test_seed_shipped_a_second_time_inserts_nothing() -> None:
    templates = FakeTemplateVersionRepository()
    seed_shipped(ports(templates), [("leaf", LEAF)])

    results = seed_shipped(ports(templates), [("leaf", LEAF)])

    assert results == [SeedResult(name="leaf", inserted_as=None)]
    assert templates.list_versions("leaf") == [1]


def test_seed_shipped_reseeds_a_file_whose_hash_changed() -> None:
    templates = FakeTemplateVersionRepository()
    seed_shipped(ports(templates), [("leaf", LEAF)])
    edited = LEAF + "\n# an operator edit\n"

    results = seed_shipped(ports(templates), [("leaf", edited)])

    assert results == [SeedResult(name="leaf", inserted_as=2)]
    assert templates.list_versions("leaf") == [1, 2]
    # the first version is untouched
    assert templates.get("leaf", 1).yaml == LEAF


def test_seed_shipped_tolerates_a_callee_listed_after_its_caller() -> None:
    """`caller.yaml` sorts before `leaf.yaml` alphabetically; seeding must not care."""
    results = seed_shipped(ports(), [("root-caller", ROOT_CALLER), ("leaf", LEAF)])

    by_name = {result.name: result.inserted_as for result in results}
    assert by_name == {"root-caller": 1, "leaf": 1}


def test_seed_shipped_raises_on_a_genuinely_invalid_file() -> None:
    with pytest.raises(ShippedTemplateInvalid) as raised:
        seed_shipped(ports(), [("broken", INVALID_YAML)])

    (failure,) = raised.value.failures
    assert failure[0] == "broken"
    assert failure[1]
    assert "broken" in str(raised.value)


def test_seed_shipped_does_not_let_one_bad_file_block_the_good_ones() -> None:
    templates = FakeTemplateVersionRepository()

    with pytest.raises(ShippedTemplateInvalid):
        seed_shipped(ports(templates), [("leaf", LEAF), ("broken", INVALID_YAML)])

    # the good file still landed before the bad one stopped the whole start-up
    assert templates.list_versions("leaf") == [1]


def test_seed_shipped_reports_every_still_failing_file_not_only_the_first() -> None:
    """Two files stuck for different reasons in the same stalled round: both are named."""
    unresolvable_callee = (
        "name: needs-ghost\nversion: 1\nsteps:\n"
        "  - id: ghost\n    uses: template\n    with:\n"
        "      name: never-shipped\n      version: 1\n      inputs: {}\n"
    )

    with pytest.raises(ShippedTemplateInvalid) as raised:
        seed_shipped(ports(), [("broken", INVALID_YAML), ("needs-ghost", unresolvable_callee)])

    names = {name for name, _ in raised.value.failures}
    assert names == {"broken", "needs-ghost"}
    assert "broken" in str(raised.value)
    assert "needs-ghost" in str(raised.value)


# ── `latest_version`: dispatching by name (AD-7, AD-15) ───────────────────────────────────
# Operator decision 2026-09-30: no template name hardcoded in product code. The two
# dispatchers that are configured with a Template *name* (`repositories.init_repository`,
# `harness_readiness.start`) resolve the version here instead of pinning one.

#: The highest of the three versions the store below holds — out of order on purpose.
HIGHEST_STORED = 3


def test_latest_version_is_the_highest_stored_number() -> None:
    templates = FakeTemplateVersionRepository(
        [
            TemplateVersion(name="leaf", version=1, yaml=LEAF, hash="h1"),
            TemplateVersion(name="leaf", version=3, yaml=LEAF, hash="h3"),
            TemplateVersion(name="leaf", version=2, yaml=LEAF, hash="h2"),
        ]
    )

    assert latest_version(templates, "leaf") == HIGHEST_STORED


def test_latest_version_of_a_name_nothing_stores_is_not_found() -> None:
    with pytest.raises(NotFound, match="no template named 'leaf'"):
        latest_version(FakeTemplateVersionRepository(), "leaf")


# --- unpinned calls --------------------------------------------------------------------------
# Operator decision 2026-10-02, editable workflows: a `uses: template` call may omit `version`; it
# resolves to the callee's latest at validate and plan time; no cascade.

#: `leaf` with one optional input, and the same at version 2 with that input renamed.
LEAF_WITH_FOLDER = (
    "name: leaf\nversion: {n}\ninputs:\n  folder:\n    type: path\nsteps:\n"
    "  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)
LEAF_RENAMED = LEAF_WITH_FOLDER.replace("  folder:", "  spec:")

#: Calls `leaf` with no `version:` — follows whatever is latest — binding `folder`.
UNPINNED_CALLER = ROOT_CALLER.replace(
    "      version: 1\n      inputs: {}\n", "      inputs:\n        folder: docs\n"
)


def test_save_version_records_an_unpinned_call_with_no_version() -> None:
    templates = FakeTemplateVersionRepository([a_stored()])

    saved = save_version(
        ports(templates), "root-caller", UNPINNED_CALLER.replace("        folder: docs\n", "")
    )

    assert saved.calls == (TemplateCallRef(name="leaf", version=None),)
    assert saved.calls[0].version is None


def test_get_version_tells_a_pinned_caller_from_one_that_follows() -> None:
    templates = FakeTemplateVersionRepository(
        [
            a_stored(),
            a_stored(name="pinned", yaml=ROOT_CALLER, calls=(TemplateRef(name="leaf", version=1),)),
            a_stored(
                name="follows",
                yaml=UNPINNED_CALLER,
                calls=(TemplateCallRef(name="leaf", version=None),),
            ),
        ]
    )

    detail = get_version(ports(templates), "leaf", 1)

    assert detail.called_by == (
        TemplateCaller(name="follows", version=1, pinned=False),
        TemplateCaller(name="pinned", version=1, pinned=True),
    )


def _stored_leaf_and_unpinned_caller() -> FakeTemplateVersionRepository:
    return FakeTemplateVersionRepository(
        [
            a_stored(yaml=LEAF_WITH_FOLDER.format(n=1)),
            a_stored(
                name="root-caller",
                yaml=UNPINNED_CALLER,
                calls=(TemplateCallRef(name="leaf", version=None),),
            ),
        ]
    )


def test_save_version_refuses_a_callee_that_would_strand_an_unpinned_caller() -> None:
    """`root-caller` binds `folder` with no pin; leaf@2 renames it, so the save is refused
    naming the caller — the Operator fixes the caller first, or pins it."""
    templates = _stored_leaf_and_unpinned_caller()
    fresh = ports(templates)

    with pytest.raises(TemplateValidationFailed) as raised:
        save_version(fresh, "leaf", LEAF_RENAMED.format(n=2))

    assert [(e.template, e.version) for e in raised.value.errors] == [("root-caller", 1)]
    assert templates.list_versions("leaf") == [1]
    assert fresh.uow.committed is False  # type: ignore[attr-defined]


def test_save_version_accepts_a_callee_its_unpinned_callers_still_bind_to() -> None:
    templates = _stored_leaf_and_unpinned_caller()
    described = LEAF_WITH_FOLDER.format(n=2).replace("steps:", "description: wider\nsteps:")

    saved = save_version(ports(templates), "leaf", described)

    assert saved.version == 2  # noqa: PLR2004 — the next number after the stored leaf@1
    assert templates.list_versions("leaf") == [1, 2]


def test_save_version_does_not_consult_a_pinned_caller() -> None:
    templates = FakeTemplateVersionRepository(
        [
            a_stored(yaml=LEAF_WITH_FOLDER.format(n=1)),
            a_stored(
                name="root-caller", yaml=ROOT_CALLER, calls=(TemplateRef(name="leaf", version=1),)
            ),
        ]
    )

    saved = save_version(ports(templates), "leaf", LEAF_RENAMED.format(n=2))

    assert saved.version == 2  # noqa: PLR2004


def test_seed_shipped_lands_an_unpinned_caller_after_the_callee_it_follows() -> None:
    """Listed first, the caller fails `callee not found` in round one and lands in round two."""
    results = seed_shipped(
        ports(),
        [("root-caller", UNPINNED_CALLER.replace("        folder: docs\n", "")), ("leaf", LEAF)],
    )

    assert [(r.name, r.inserted_as) for r in results] == [("leaf", 1), ("root-caller", 1)]
