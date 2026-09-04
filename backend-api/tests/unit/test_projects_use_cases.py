"""Every rule the Project use cases hold, over the fakes and never over a database (AD-18).

The rows of the story's I/O matrix that are use-case rules are here: encryption on the way
in, masking on the way out, slug derivation and collision, the name conflict, the unknown
id, and the keep/replace/delete semantics of `PUT`. The rows about payload *shape* —
a malformed or reserved variable name, a duplicate inside one payload — are asserted in
`tests/unit/test_project_schemas.py`, because that is the layer that turns them into an
`errors[]` entry with a path.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from orchestrator.application.use_cases.projects import (
    NO_STORED_VALUE_REASON,
    EnvVarInput,
    ProjectDraft,
    ProjectPorts,
    create_project,
    decrypt_env_vars,
    get_project,
    list_projects,
    update_project,
)
from orchestrator.domain.entities.project import MASK_PREFIX, ProjectView
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository


class Ports:
    """The four fakes, kept beside the `ProjectPorts` a use case receives."""

    def __init__(self) -> None:
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock()
        self.uow.__enter__()

    @property
    def ports(self) -> ProjectPorts:
        return ProjectPorts(
            uow=self.uow, projects=self.projects, crypto=self.crypto, clock=self.clock
        )


@pytest.fixture
def ports() -> Ports:
    return Ports()


def a_draft(name: str = "My Website", **overrides: object) -> ProjectDraft:
    fields: dict[str, object] = {
        "name": name,
        "log_prompt_content": None,
        "context_text": "",
        "context_paths": (),
        "env_vars": (),
    }
    fields.update(overrides)
    return ProjectDraft(**fields)  # type: ignore[arg-type]


def create(
    ports: Ports, draft: ProjectDraft | None = None, *, default: bool = False
) -> ProjectView:
    """`create_project` with the instance default named, the way the router calls it."""
    return create_project(ports.ports, draft or a_draft(), log_prompt_content_default=default)


TWO_VARS = (
    EnvVarInput(name="API_URL", value="https://x"),
    EnvVarInput(name="TOKEN_A", value="abcdefgh"),
)


# ── create ───────────────────────────────────────────────────────────────────


def test_creating_stores_the_values_as_ciphertext_and_returns_them_masked(ports: Ports) -> None:
    view = create(ports, a_draft(env_vars=TWO_VARS))

    stored = ports.projects.get(view.id)
    assert stored is not None
    assert [variable.name for variable in stored.env_vars_enc] == ["API_URL", "TOKEN_A"]
    assert [variable.value_enc for variable in stored.env_vars_enc] != ["https://x", "abcdefgh"]
    assert [(v.name, v.masked) for v in view.env_vars] == [
        ("API_URL", f"{MASK_PREFIX}://x"),
        ("TOKEN_A", f"{MASK_PREFIX}efgh"),
    ]


def test_creating_encrypts_every_value_exactly_once(ports: Ports) -> None:
    create(ports, a_draft(env_vars=TWO_VARS))

    assert ports.crypto.encrypted == ["https://x", "abcdefgh"]


def test_no_plaintext_value_survives_into_the_view(ports: Ports) -> None:
    view = create(ports, a_draft(env_vars=TWO_VARS))

    assert "abcdefgh" not in view.model_dump_json()
    assert "https://x" not in view.model_dump_json()


def test_creating_records_both_timestamps_from_the_clock(ports: Ports) -> None:
    view = create(ports, a_draft())

    assert view.created_at == ports.clock.now()
    assert view.updated_at == ports.clock.now()


def test_creating_commits(ports: Ports) -> None:
    create(ports, a_draft())

    assert ports.uow.committed is True


def test_creating_keeps_the_context_the_operator_typed(ports: Ports) -> None:
    view = create(
        ports, a_draft(context_text="read this", context_paths=("docs/a.md", "README.md"))
    )

    assert view.context_text == "read this"
    assert view.context_paths == ("docs/a.md", "README.md")


@pytest.mark.parametrize("default", [False, True])
def test_a_create_that_states_no_switch_takes_the_instance_default(
    ports: Ports, default: bool
) -> None:
    """FR-2: `LOG_PROMPT_CONTENT_DEFAULT` applies when the payload omitted the field."""
    view = create_project(ports.ports, a_draft(), log_prompt_content_default=default)

    stored = ports.projects.get(view.id)
    assert stored is not None
    assert stored.log_prompt_content is default
    assert view.log_prompt_content is default


@pytest.mark.parametrize("chosen", [False, True])
def test_a_create_that_states_a_switch_keeps_it_over_the_instance_default(
    ports: Ports, chosen: bool
) -> None:
    view = create_project(
        ports.ports,
        a_draft(log_prompt_content=chosen),
        log_prompt_content_default=not chosen,
    )

    assert view.log_prompt_content is chosen


@pytest.mark.parametrize("stored_switch", [False, True])
def test_an_update_that_states_no_switch_keeps_the_stored_one(
    ports: Ports, stored_switch: bool
) -> None:
    """A `PUT` that leaves the field out is not a request to reset the Operator's choice."""
    created = create_project(
        ports.ports,
        a_draft(log_prompt_content=stored_switch),
        log_prompt_content_default=not stored_switch,
    )

    updated = update_project(ports.ports, created.id, a_draft(context_text="changed"))

    assert updated.log_prompt_content is stored_switch
    stored = ports.projects.get(created.id)
    assert stored is not None
    assert stored.log_prompt_content is stored_switch


@pytest.mark.parametrize("chosen", [False, True])
def test_an_update_that_states_a_switch_writes_it(ports: Ports, chosen: bool) -> None:
    created = create_project(
        ports.ports, a_draft(log_prompt_content=not chosen), log_prompt_content_default=not chosen
    )

    updated = update_project(ports.ports, created.id, a_draft(log_prompt_content=chosen))

    assert updated.log_prompt_content is chosen


def test_a_second_project_with_a_stored_name_is_a_conflict(ports: Ports) -> None:
    create(ports, a_draft("My Website"))

    with pytest.raises(Conflict, match="already exists"):
        create(ports, a_draft("My Website"))


def test_a_create_that_conflicts_never_commits_the_second_write(ports: Ports) -> None:
    create(ports, a_draft("My Website"))
    ports.uow.committed = False

    with pytest.raises(Conflict):
        create(ports, a_draft("My Website"))

    assert ports.uow.committed is False
    assert len(ports.projects.list()) == 1


def test_creating_with_a_keep_that_has_nothing_to_keep_is_invalid(ports: Ports) -> None:
    """A brand-new Project stores nothing, so every entry has to carry its value."""
    with pytest.raises(Invalid, match=NO_STORED_VALUE_REASON):
        create(ports, a_draft(env_vars=(EnvVarInput(name="A"),)))


# ── the slug ─────────────────────────────────────────────────────────────────


def test_the_slug_is_derived_from_the_name(ports: Ports) -> None:
    assert create(ports, a_draft("My Website 2!")).slug == "my-website-2"


def test_a_colliding_slug_is_numbered_from_two(ports: Ports) -> None:
    first = create(ports, a_draft("My Website"))
    second = create(ports, a_draft("my  website"))
    third = create(ports, a_draft("MY-WEBSITE"))

    assert (first.slug, second.slug, third.slug) == (
        "my-website",
        "my-website-2",
        "my-website-3",
    )


def test_a_name_with_no_slug_characters_still_gets_a_directory_name(ports: Ports) -> None:
    assert create(ports, a_draft("!!!")).slug == "project"


# ── read ─────────────────────────────────────────────────────────────────────


def test_getting_returns_the_masked_project(ports: Ports) -> None:
    created = create(ports, a_draft(env_vars=TWO_VARS))

    assert get_project(ports.ports, created.id) == created


def test_getting_an_unknown_id_is_a_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound, match="no project with id"):
        get_project(ports.ports, new_id())


def test_the_list_comes_back_ordered_by_name_and_masked(ports: Ports) -> None:
    create(ports, a_draft("Charlie"))
    create(ports, a_draft("Alpha", env_vars=TWO_VARS))
    create(ports, a_draft("Bravo"))

    listed = list_projects(ports.ports)

    assert [view.name for view in listed] == ["Alpha", "Bravo", "Charlie"]
    assert listed[0].env_vars[1].masked == f"{MASK_PREFIX}efgh"


def test_the_empty_list_is_a_list(ports: Ports) -> None:
    assert list_projects(ports.ports) == []


# ── update ───────────────────────────────────────────────────────────────────


def test_an_update_keeps_replaces_and_deletes_in_one_payload(ports: Ports) -> None:
    created = create(
        ports,
        a_draft(
            env_vars=(
                EnvVarInput(name="A", value="value-a"),
                EnvVarInput(name="B", value="value-b"),
            )
        ),
    )
    before = ports.projects.get(created.id)
    assert before is not None
    stored_a = before.env_vars_enc[0].value_enc
    ports.clock.advance(60)

    updated = update_project(
        ports.ports,
        created.id,
        a_draft(env_vars=(EnvVarInput(name="A"), EnvVarInput(name="C", value="x"))),
    )

    after = ports.projects.get(created.id)
    assert after is not None
    assert [variable.name for variable in after.env_vars_enc] == ["A", "C"]
    assert after.env_vars_enc[0].value_enc == stored_a
    assert ports.crypto.decrypt(after.env_vars_enc[1].value_enc) == "x"
    assert updated.updated_at > created.updated_at
    assert updated.created_at == created.created_at


def test_a_kept_variable_is_neither_re_encrypted_nor_decrypted_to_be_kept(
    ports: Ports,
) -> None:
    created = create(ports, a_draft(env_vars=(EnvVarInput(name="A", value="a"),)))
    ports.crypto.encrypted.clear()
    ports.crypto.decrypted.clear()

    update_project(ports.ports, created.id, a_draft(env_vars=(EnvVarInput(name="A"),)))

    assert ports.crypto.encrypted == []
    # the one decryption is the mask of the returned view, not the keep
    assert len(ports.crypto.decrypted) == 1


def test_a_keep_naming_a_variable_that_is_not_stored_is_invalid(ports: Ports) -> None:
    created = create(ports, a_draft(env_vars=(EnvVarInput(name="A", value="a"),)))

    with pytest.raises(Invalid, match=NO_STORED_VALUE_REASON):
        update_project(ports.ports, created.id, a_draft(env_vars=(EnvVarInput(name="Z"),)))


def test_a_refused_update_leaves_the_stored_project_alone(ports: Ports) -> None:
    created = create(ports, a_draft(env_vars=(EnvVarInput(name="A", value="a"),)))
    before = ports.projects.get(created.id)
    ports.uow.committed = False

    with pytest.raises(Invalid):
        update_project(ports.ports, created.id, a_draft(env_vars=(EnvVarInput(name="Z"),)))

    assert ports.projects.get(created.id) == before
    assert ports.uow.committed is False


def test_an_update_never_changes_the_slug(ports: Ports) -> None:
    """The slug names the Project's clone directory; a rename must not move it (AD-14)."""
    created = create(ports, a_draft("My Website"))

    updated = update_project(ports.ports, created.id, a_draft("Something Else Entirely"))

    assert updated.slug == "my-website"
    assert updated.name == "Something Else Entirely"


def test_renaming_to_another_projects_name_is_a_conflict(ports: Ports) -> None:
    create(ports, a_draft("Taken"))
    mine = create(ports, a_draft("Mine"))

    with pytest.raises(Conflict, match="already exists"):
        update_project(ports.ports, mine.id, a_draft("Taken"))


def test_renaming_a_project_to_its_own_name_is_allowed(ports: Ports) -> None:
    mine = create(ports, a_draft("Mine"))

    updated = update_project(ports.ports, mine.id, a_draft("Mine", context_text="changed"))

    assert updated.name == "Mine"
    assert updated.context_text == "changed"


def test_updating_an_unknown_id_is_a_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound, match="no project with id"):
        update_project(ports.ports, new_id(), a_draft())


def test_an_update_commits(ports: Ports) -> None:
    created = create(ports, a_draft())
    ports.uow.committed = False

    update_project(ports.ports, created.id, a_draft(context_text="changed"))

    assert ports.uow.committed is True


def test_an_update_can_empty_the_variable_set(ports: Ports) -> None:
    created = create(ports, a_draft(env_vars=TWO_VARS))

    updated = update_project(ports.ports, created.id, a_draft())

    assert updated.env_vars == ()


# ── decrypt_env_vars — the one function that returns plaintext ───────────────


def test_decrypt_env_vars_returns_the_values_a_run_will_export(ports: Ports) -> None:
    created = create(ports, a_draft(env_vars=TWO_VARS))

    assert decrypt_env_vars(ports.ports, created.id) == {
        "API_URL": "https://x",
        "TOKEN_A": "abcdefgh",
    }


def test_decrypt_env_vars_of_a_project_without_variables_is_empty(ports: Ports) -> None:
    created = create(ports, a_draft())

    assert decrypt_env_vars(ports.ports, created.id) == {}


def test_decrypt_env_vars_of_an_unknown_id_is_a_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound, match="no project with id"):
        decrypt_env_vars(ports.ports, new_id())


API = Path(__file__).resolve().parents[2] / "src" / "orchestrator" / "api"

#: The one function here that returns plaintext. Nothing under `api/` may name it.
PLAINTEXT_FUNCTION = "decrypt_env_vars"


def _names_used(source: str) -> set[str]:
    """Every way a module can name something: an import alias, an attribute, a bare name.

    Collecting `ImportFrom` aliases alone would miss the form the router actually uses —
    `from ... use_cases import projects as use_cases` and then `use_cases.decrypt_env_vars(
    ...)`, where the alias is `projects` and the function is only ever an attribute.
    """
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def test_no_route_reaches_decrypt_env_vars() -> None:
    """It exists for the Run machinery of Epic 4; a router that reached it would leak."""
    for module in API.rglob("*.py"):
        assert PLAINTEXT_FUNCTION not in _names_used(module.read_text()), module.name


def test_the_guard_sees_the_call_form_the_router_actually_uses() -> None:
    """A guard that cannot fail is not a guard. This is the leak it has to catch."""
    leak = (
        "from orchestrator.application.use_cases import projects as use_cases\n"
        "\n\n"
        "def get_project(ports, project_id):\n"
        "    return use_cases.decrypt_env_vars(ports, project_id)\n"
    )

    assert PLAINTEXT_FUNCTION in _names_used(leak)


def test_the_guard_also_sees_a_direct_import() -> None:
    leak = "from orchestrator.application.use_cases.projects import decrypt_env_vars\n"

    assert PLAINTEXT_FUNCTION in _names_used(leak)
