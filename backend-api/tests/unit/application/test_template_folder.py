"""`seed_folder` (SPEC CAP-4, AD-26, D13): the folder pass on the shared fakes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.application.templates.model import CALL_CYCLE
from orchestrator.application.use_cases.template_folder import (
    FolderEntry,
    NotInFolder,
    seed_folder,
)
from orchestrator.application.use_cases.templates import TemplatePorts, text_hash
from orchestrator.domain.entities.template import TemplateCallRef, TemplateVersion
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.template_folders import OperatorFolder
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
STEP = "steps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
THIRD = 3


def plain(name: str, note: str = "a") -> str:
    return f"name: {name}\nversion: 1\ndescription: {note}\n{STEP}"


def lib(name: str = "lib", *, extra: bool = False, renamed: bool = False) -> str:
    first = "spec" if renamed else "folder"
    more = "  extra:\n    type: path\n" if extra else ""
    return f"name: {name}\nversion: 1\ninputs:\n  {first}:\n    type: path\n{more}{STEP}"


def app(name: str = "app", callee: str = "lib", *, extra: bool = False) -> str:
    more = "        extra: more\n" if extra else ""
    return (
        f"name: {name}\nversion: 1\nsteps:\n  - id: c\n    uses: template\n    with:\n"
        f"      name: {callee}\n      inputs:\n        folder: docs\n{more}"
    )


def stored(
    name: str, number: int, text: str, source: str | None = "saved", **over: object
) -> TemplateVersion:
    fields: dict[str, object] = {
        "name": name,
        "version": number,
        "yaml": text,
        "hash": text_hash(text),
        "created_at": AT,
        "source": source,
    }
    fields.update(over)
    return TemplateVersion(**fields)  # type: ignore[arg-type]


def ports(templates: FakeTemplateVersionRepository, folders: FakeTemplateFolders) -> TemplatePorts:
    uow = FakeUnitOfWork()
    uow.__enter__()
    return TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT), folders=folders)


def run(
    templates: FakeTemplateVersionRepository,
    *files: object,
    shipped: set[str] | None = None,
) -> tuple[object, FakeTemplateFolders]:
    folders = FakeTemplateFolders(shipped=shipped or set(), folder=ready(*files))  # type: ignore[arg-type]
    return seed_folder(ports(templates, folders), folders.folder), folders


def test_a_file_equal_to_an_older_version_is_stored_anew_then_unchanged() -> None:
    """AC1: only the latest version's hash counts."""
    v1, v2 = plain("wf", "one"), plain("wf", "two")
    templates = FakeTemplateVersionRepository([stored("wf", 1, v1), stored("wf", 2, v2)])

    first, _ = run(templates, file("wf", v1))
    second, _ = run(templates, file("wf", v1))

    assert first.stored == (FolderEntry("wf", THIRD, "wf.yaml", False),)  # type: ignore[attr-defined]
    version = templates.get("wf", THIRD)
    assert version is not None
    assert (version.yaml, version.source) == (v1, "folder")
    assert second.stored == ()  # type: ignore[attr-defined]
    assert [e.name for e in second.unchanged] == ["wf"]  # type: ignore[attr-defined]
    assert second.unchanged[0].version == THIRD  # type: ignore[attr-defined]


def test_the_version_line_of_the_text_never_picks_the_stored_number() -> None:
    """AC2."""
    templates = FakeTemplateVersionRepository(
        [stored("wf", 1, plain("wf", "one")), stored("wf", 2, plain("wf", "two"))]
    )

    outcome, _ = run(templates, file("wf", plain("wf", "x").replace("version: 1", "version: 7")))

    assert [e.version for e in outcome.stored] == [THIRD]  # type: ignore[attr-defined]


def test_a_file_calling_a_template_pinned_to_an_older_version_of_itself_is_stored() -> None:
    """Retro F1 (AD-15 amendment): the file's `version:` line is not the root's identity, so
    `a.yaml` saying `version: 1` and calling `b@1 -> a@1` is stored as `a@3`, the real tree
    `a@3 -> b@1 -> a@1` having no cycle. The same file is refused when `b@1` follows `a`
    unpinned, because once stored `a@3` is what `a` means."""
    caller = (
        "name: a\nversion: 1\nsteps:\n  - id: c\n    uses: template\n    with:\n      name: b\n"
    )
    pinned_b = stored("b", 1, plain("b"), calls=(TemplateCallRef(name="a", version=1),))
    unpinned_b = stored("b", 1, plain("b"), calls=(TemplateCallRef(name="a", version=None),))
    older = [stored("a", 1, plain("a", "one")), stored("a", 2, plain("a", "two"))]

    fine, _ = run(FakeTemplateVersionRepository([*older, pinned_b]), file("a", caller))
    cycle, _ = run(FakeTemplateVersionRepository([*older, unpinned_b]), file("a", caller))

    assert [e.version for e in fine.stored] == [THIRD]  # type: ignore[attr-defined]
    assert fine.refused == ()  # type: ignore[attr-defined]
    assert cycle.stored == ()  # type: ignore[attr-defined]
    refused = cycle.refused[0].errors  # type: ignore[attr-defined]
    assert [e.reason for e in refused] == [CALL_CYCLE]


def test_a_bad_file_is_refused_with_its_reason_and_the_good_one_is_stored() -> None:
    """AC3: validator reason, `file unreadable`, and the stem/name mismatch at `name:`."""
    templates = FakeTemplateVersionRepository()

    outcome, _ = run(
        templates,
        file("good", plain("good")),
        file("invalid", "name: invalid\nversion: 1\nsteps: []\n"),
        file("unreadable", "", read_error="denied"),
        file("x", "version: 1\nname: y\n" + STEP),
    )

    assert [e.name for e in outcome.stored] == ["good"]  # type: ignore[attr-defined]
    reasons = {r.file: [(e.line, e.reason, e.template) for e in r.errors] for r in outcome.refused}  # type: ignore[attr-defined]
    assert reasons["unreadable.yaml"] == [(1, "file unreadable", "unreadable")]
    assert reasons["x.yaml"] == [(2, "file name differs from template name", "x")]
    assert reasons["invalid.yaml"][0][1] == "empty steps"


@pytest.mark.parametrize(("lib_name", "app_name"), [("a-lib", "b-app"), ("b-lib", "a-app")])
def test_a_caller_and_its_new_callee_load_in_either_name_order(
    lib_name: str, app_name: str
) -> None:
    """AC4: the unpinned stored caller of `lib` stays satisfied, and a retry round lets the
    new caller land after the callee that adds the input it binds."""
    templates = FakeTemplateVersionRepository(
        [
            stored(lib_name, 1, lib(lib_name)),
            stored(
                app_name,
                1,
                app(app_name, lib_name),
                calls=(TemplateCallRef(name=lib_name, version=None),),
            ),
        ]
    )

    outcome, _ = run(
        templates,
        file(lib_name, lib(lib_name, extra=True)),
        file(app_name, app(app_name, lib_name, extra=True)),
    )

    assert sorted(e.name for e in outcome.stored) == sorted([lib_name, app_name])  # type: ignore[attr-defined]
    assert outcome.refused == ()  # type: ignore[attr-defined]


def test_a_callee_change_that_strands_a_stored_caller_stays_refused() -> None:
    """AC5: refused in every round, with the last round's caller-check errors naming `app@1`."""
    templates = FakeTemplateVersionRepository(
        [
            stored("lib", 1, lib()),
            stored("app", 1, app(), calls=(TemplateCallRef(name="lib", version=None),)),
        ]
    )

    outcome, _ = run(templates, file("lib", lib(renamed=True)), file("other", plain("other")))

    assert [e.name for e in outcome.stored] == ["other"]  # type: ignore[attr-defined]
    (refusal,) = outcome.refused  # type: ignore[attr-defined]
    assert refusal.file == "lib.yaml"
    assert [(e.template, e.version) for e in refusal.errors] == [("app", 1)]
    assert templates.list_versions("lib") == [1]


def test_a_file_named_like_a_shipped_template_overrides_it() -> None:
    """AC6."""
    templates = FakeTemplateVersionRepository([stored("agent-smoke", 1, plain("agent-smoke"))])

    outcome, _ = run(
        templates, file("agent-smoke", plain("agent-smoke", "mine")), shipped={"agent-smoke"}
    )

    assert outcome.stored == (FolderEntry("agent-smoke", 2, "agent-smoke.yaml", True),)  # type: ignore[attr-defined]


def test_a_removed_file_is_reported_and_nothing_is_deleted() -> None:
    """AC7, including K1: an unchanged file leaves no `folder` row, so it is never listed."""
    templates = FakeTemplateVersionRepository([stored("same", 1, plain("same"))])
    run(templates, file("wf", plain("wf")), file("same", plain("same")))
    run(templates, file("agent-smoke", plain("agent-smoke")), shipped={"agent-smoke"})
    before = dict(templates.versions)

    gone, _ = run(templates, shipped={"agent-smoke"})

    assert gone.not_in_folder == (  # type: ignore[attr-defined]
        NotInFolder("agent-smoke", True),
        NotInFolder("wf", False),
    )
    assert templates.versions == before


def test_a_file_present_but_unreadable_is_not_reported_as_gone() -> None:
    templates = FakeTemplateVersionRepository()
    run(templates, file("wf", plain("wf")))

    outcome, _ = run(templates, file("wf", "", read_error="denied"))

    assert outcome.not_in_folder == ()  # type: ignore[attr-defined]


class _CountingTemplates(FakeTemplateVersionRepository):
    def __init__(self) -> None:
        super().__init__()
        self.source_reads = 0

    def names_with_source(self, source: str) -> frozenset[str]:
        self.source_reads += 1
        return super().names_with_source(source)


@pytest.mark.parametrize("state", ["off", "missing"])
def test_an_off_or_missing_folder_is_an_empty_outcome(state: str) -> None:
    """AC8: and the repository is not asked anything."""
    templates = _CountingTemplates()
    folders = FakeTemplateFolders(folder=OperatorFolder(path="/x", state=state))  # type: ignore[arg-type]

    outcome = seed_folder(ports(templates, folders), folders.folder)

    assert (outcome.stored, outcome.unchanged, outcome.refused, outcome.not_in_folder) == ((),) * 4
    assert templates.source_reads == 0


def test_without_a_folders_port_the_pass_is_off() -> None:
    templates = FakeTemplateVersionRepository()
    folders = FakeTemplateFolders(folder=ready(file("wf", plain("wf"))))
    bare = TemplatePorts(uow=FakeUnitOfWork(), templates=templates, clock=FakeClock(AT))

    assert seed_folder(bare, folders.folder) == seed_folder(bare, OperatorFolder("", "off"))
    assert templates.list_versions("wf") == []


def test_a_concurrent_save_conflict_passes_through_and_commits_nothing() -> None:
    class Racing(FakeTemplateVersionRepository):
        def add_version(self, version: TemplateVersion, *, description: str | None) -> None:
            raise Conflict(f"template version {version.name}@{version.version} taken")

    folders = FakeTemplateFolders(folder=ready(file("wf", plain("wf"))))
    fresh = ports(Racing(), folders)

    with pytest.raises(Conflict, match=r"wf@1"):
        seed_folder(fresh, folders.folder)

    assert fresh.uow.committed is False  # type: ignore[attr-defined]


@pytest.mark.parametrize("method", ["names_with_source", "get", "list_versions"])
def test_a_port_error_is_raised_never_a_refusal(method: str) -> None:
    class Failing(FakeTemplateVersionRepository):
        pass

    def boom(self: object, *args: object, **kwargs: object) -> object:
        raise RuntimeError("database down")

    setattr(Failing, method, boom)
    templates = Failing([stored("lib", 1, lib())])
    folders = FakeTemplateFolders(folder=ready(file("app", app()), file("wf", plain("wf"))))

    with pytest.raises(RuntimeError, match="database down"):
        seed_folder(ports(templates, folders), folders.folder)
