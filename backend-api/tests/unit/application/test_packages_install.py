"""`install_package` over the shared fakes and fixture packages (story 3 of epic 6, AC1-AC7)."""

from __future__ import annotations

import pytest

from orchestrator.application.packages.declaration import PackageInvalid
from orchestrator.application.use_cases import packages as use_cases
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from tests.unit.application.package_fixtures import (
    PATH,
    SHA,
    merge_text,
    package_text,
    spec_text,
)
from tests.unit.application.package_world import WORK, World, files

TWO = 2


def install(world: World, **overrides: object):  # type: ignore[no-untyped-def]
    arguments = {"repository_id": world.hub.id, "path": PATH, "ref": "main", **overrides}
    return use_cases.install_package(world.ports, world.project.id, **arguments)  # type: ignore[arg-type]


def refused(world: World, **overrides: object) -> list[tuple[str, str]]:
    with pytest.raises(PackageInvalid) as raised:
        install(world, **overrides)
    assert world.stored() == []
    assert world.packages.packages == {}
    assert "commit" not in world.uow.calls
    return [(p.file, p.reason) for p in raised.value.problems]


def test_a_valid_package_installs() -> None:
    world = World()

    record = install(world)

    assert (record.sha, record.name, record.path, record.ref) == (SHA, "acme", PATH, "main")
    assert world.packages.get(world.project.id) == record
    assert world.stored() == [("acme.merge", 1), ("acme.spec", 1)]
    for key in world.stored():
        stored = world.templates.versions[key]
        assert (stored.source, stored.package_sha) == ("package", SHA)
    assert world.uow.calls.count("commit") == 1


def test_the_declaration_reads_each_entry() -> None:
    sequence = install(World()).declaration.sequence

    spec, merge, build = sequence
    assert (spec.workflow, spec.template, spec.version) == ("spec", "acme.spec", 1)
    assert (spec.type, spec.shown_as) == ("interactive", "workflow")
    assert [(s.id, s.kind) for s in spec.steps] == [
        ("intake", "conversation"),
        ("product", "conversation"),
        ("gate", "automatic"),
    ]
    assert (merge.shown_as, merge.steps, merge.type) == ("step", (), "interactive")
    assert (build.template, build.version, build.type, build.shown_as) == (
        "shipped-build",
        None,
        "auto",
        "workflow",
    )


def test_the_gate_and_status_map_are_as_declared() -> None:
    declaration = install(World()).declaration

    assert declaration.gate.pass_words == ("pass",)
    assert declaration.gate.fail_words == ("fail",)
    assert declaration.gate.owners_key == "owners"
    assert declaration.status_map == {"final": "done", "blocked": "waiting for her"}


def test_a_second_install_at_the_same_sha_stores_no_version_and_replaces_the_record() -> None:
    world = World()
    first = install(world)

    second = install(world)

    assert world.stored() == [("acme.merge", 1), ("acme.spec", 1)]
    assert second.id == first.id
    assert len(world.packages.packages) == 1
    assert second.declaration == first.declaration


def test_a_new_sha_stores_the_next_version() -> None:
    world = World()
    install(world)
    newer = "b" * 40
    world.git.refs = {"main": newer}
    world.git.files = {(newer, path): text for (_, path), text in world.git.files.items()}  # type: ignore[union-attr]

    record = install(world)

    assert record.sha == newer
    assert record.declaration.sequence[0].version == TWO


def test_the_base_clone_is_made_only_when_missing_and_fetched_at_the_ref() -> None:
    world = World()
    install(world)

    assert [name for name, _ in world.git.calls if name in ("clone_base", "fetch_base")] == [
        "clone_base",
        "fetch_base",
    ]
    dest = WORK / "familio" / "hub" / "base"
    assert ("fetch_base", (dest, "main")) in world.git.calls
    reads = [args for name, args in world.git.calls if name == "read_file"]
    assert reads and all(args[1] == SHA for args in reads)

    existing = World()
    existing.git = type(existing.git)(refs={"main": SHA}, files=files(), base_exists=[True])
    install(existing)
    assert "clone_base" not in [name for name, _ in existing.git.calls]


def test_a_malformed_package_stores_nothing() -> None:
    assert refused(World(files(package="name: [\n"))) == [("pkg/package.yaml", "invalid yaml")]


def test_a_missing_package_file() -> None:
    world = World({})
    assert refused(world) == [("pkg/package.yaml", "file not found")]


def test_a_missing_template_file() -> None:
    content = files()
    del content[(SHA, "pkg/templates/merge.yaml")]
    assert ("pkg/templates/merge.yaml", "file not found") in refused(World(content))


def test_a_template_that_fails_judging() -> None:
    found = refused(World(files(**{"templates/merge.yaml": "name: merge\nversion: 1\nsteps: x\n"})))
    assert found and found[0][0] == "pkg/templates/merge.yaml"
    assert found[0][1].startswith("line ")


def test_a_template_whose_name_differs_from_its_stem() -> None:
    found = refused(World(files(**{"templates/merge.yaml": merge_text("other")})))
    assert found == [("pkg/templates/merge.yaml", "name must be merge")]


def test_two_templates_with_the_same_stem() -> None:
    sequence = (
        "  - { workflow: a, template: a/spec.yaml }\n  - { workflow: b, template: b/spec.yaml }\n"
    )
    content = files(
        package=package_text(sequence=sequence),
        **{"a/spec.yaml": spec_text(), "b/spec.yaml": spec_text()},
    )
    found = refused(World(content))
    assert (
        "pkg/b/spec.yaml",
        "two templates have the stem spec: a/spec.yaml, b/spec.yaml",
    ) in found


def test_an_unknown_shipped_name() -> None:
    sequence = (
        "  - { workflow: spec, template: templates/spec.yaml }\n"
        "  - { workflow: x, template: nope }\n"
    )
    found = refused(World(files(package=package_text(sequence=sequence))))
    assert found == [("pkg/package.yaml", "nope is not a shipped template")]


def test_a_shipped_template_that_no_longer_validates() -> None:
    world = World()
    world.templates.versions[("shipped-build", 1)] = world.templates.versions[
        ("shipped-build", 1)
    ].model_copy(update={"yaml": "steps: ["})
    assert refused(world) == [("pkg/package.yaml", "shipped-build does not validate")]


def test_no_spec_gate_row() -> None:
    found = refused(World(files(**{"templates/spec.yaml": spec_text(gate=False)})))
    assert found == [("pkg/package.yaml", "no spec-gate row in the package's templates")]


def test_a_spec_gate_row_missing_a_gate_word() -> None:
    found = refused(World(files(**{"templates/spec.yaml": spec_text(gate_success="pass")})))
    assert found == [
        (
            "pkg/templates/spec.yaml",
            "spec-gate row gate does not list gate word fail in expect.success",
        )
    ]


def test_a_package_yaml_rule_refusal() -> None:
    found = refused(World(files(package=package_text(status_map="{ final: finished }"))))
    assert found == [
        (
            "pkg/package.yaml",
            "status_map final: finished is not one of done, running, waiting for her, failed",
        )
    ]


def test_every_problem_of_the_templates_is_named_at_once() -> None:
    content = files(
        **{
            "templates/merge.yaml": merge_text("other"),
            "templates/spec.yaml": spec_text(gate=False),
        }
    )
    assert len(refused(World(content))) == 1  # the gate check waits for every template to be read
    del content[(SHA, "pkg/templates/spec.yaml")]
    assert len(refused(World(content))) == TWO


def test_a_ref_the_remote_lacks_is_a_conflict_naming_it() -> None:
    world = World()
    with pytest.raises(Conflict, match="ref gone"):
        install(world, ref="gone")
    assert world.stored() == []


def test_a_repository_of_another_project_is_not_found() -> None:
    world = World()
    _, other = world.another_project("Other")
    with pytest.raises(NotFound):
        install(world, repository_id=other.id)
    with pytest.raises(NotFound):
        install(world, repository_id=new_id())
    with pytest.raises(NotFound):
        use_cases.install_package(
            world.ports, new_id(), repository_id=world.hub.id, path=PATH, ref="main"
        )


@pytest.mark.parametrize("path", ["", "/abs", "a/../b", "a/"])
def test_an_invalid_path_is_refused_before_any_git_call(path: str) -> None:
    world = World()
    with pytest.raises(Invalid, match="path: must be one or more"):
        install(world, path=path)
    assert world.git.calls == []


def test_the_same_package_installs_on_a_second_project() -> None:
    world = World()
    install(world)
    other, hub = world.another_project("Orchestrator")

    use_cases.install_package(world.ports, other.id, repository_id=hub.id, path=PATH, ref="main")

    assert len(world.packages.packages) == TWO
    assert world.stored() == [("acme.merge", 1), ("acme.spec", 1)]


def test_another_package_of_the_same_name_is_refused_naming_the_project() -> None:
    world = World()
    install(world)
    other, hub = world.another_project("Orchestrator", url="https://github.com/org/else.git")
    before = world.stored()

    with pytest.raises(Conflict, match="project familio"):
        use_cases.install_package(
            world.ports, other.id, repository_id=hub.id, path=PATH, ref="main"
        )

    assert world.stored() == before
    assert other.id not in world.packages.packages


def test_the_same_url_with_another_path_clashes_too() -> None:
    world = World()
    install(world)
    other, hub = world.another_project("Orchestrator")
    moved = {(SHA, f"x/{path.split('/', 1)[1]}"): text for (_, path), text in files().items()}
    world.git.files = {**(world.git.files or {}), **moved}

    with pytest.raises(Conflict):
        use_cases.install_package(world.ports, other.id, repository_id=hub.id, path="x", ref="main")


def test_a_clash_with_a_deleted_project_names_its_id() -> None:
    world = World()
    record = install(world)
    other, hub = world.another_project("Orchestrator", url="https://github.com/org/else.git")
    del world.projects.projects[world.project.id]
    del world.repositories.repositories[record.repository_id]

    with pytest.raises(Conflict, match=str(world.project.id)):
        use_cases.install_package(
            world.ports, other.id, repository_id=hub.id, path=PATH, ref="main"
        )


def test_a_git_failure_propagates() -> None:
    world = World()
    world.git = type(world.git)(
        refs={"main": SHA},
        files=files(),
        fetch_base=[GitError(command="fetch", exit_code=1, output="x")],
    )
    with pytest.raises(Exception, match="fetch"):
        install(world)
    assert world.stored() == []


def test_the_same_sha_from_another_folder_stores_its_own_text() -> None:
    world = World()
    install(world)
    other = {
        (SHA, f"other/{path.removeprefix(PATH + '/')}"): text
        for (_, path), text in world.git.files.items()  # type: ignore[union-attr]
    }
    other[(SHA, "other/templates/spec.yaml")] = spec_text() + "# another folder\n"
    world.git.files = {**world.git.files, **other}  # type: ignore[dict-item]

    moved = install(world, path="other")
    again = install(world, path="other")
    back = install(world)

    assert moved.declaration.sequence[0].version == TWO
    assert world.templates.versions[("acme.spec", TWO)].yaml.endswith("# another folder\n")
    assert again.declaration.sequence[0].version == TWO
    assert back.declaration.sequence[0].version == 1
    assert world.stored() == [("acme.merge", 1), ("acme.spec", 1), ("acme.spec", TWO)]
