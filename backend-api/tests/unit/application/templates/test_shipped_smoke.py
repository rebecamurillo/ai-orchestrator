"""The shipped `templates/*.yaml`, checked as invariants — never as content.

The shipped Templates are operator-evolving artifacts: steps are added, renamed and
re-parameterised without a code change, and `seed_shipped` inserts each edited file as the
next version at start-up. So nothing here names a step, counts a row or pins a parameter —
that coverage runs against the frozen copies under `fixtures/exemplars/`
(`plan_fixtures.py`, `test_shipped_templates.py`, `test_graph_shipped.py`,
`test_plan_shipped.py`), which no template edit can break.

What must hold for *any* text the shipped directory carries, and is asserted here:
every file seeds through the same `seed_shipped` start-up runs (so it validates, its
callees resolve, and the call chain stays within depth); the two Template names a
default-configured instance dispatches on its own — `Settings.init_template` for
`repositories.py`'s init Run and `Settings.readiness_template` for `harness_readiness.py`'s
readiness Run — resolve among the shipped files; every stored version builds a graph whose
edges and groups name its own nodes, with no indexed id and nothing `unvalidated`; and the
tree of every root resolves.

The product itself pins no Template name (Operator decision 2026-09-30: the orchestrator
hardcodes no template name and no template step id); the two defaults are configuration,
and this module checks only that the configuration as shipped points at something shipped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.application.graph import Graph, build_template_graph
from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.plan_run import resolve_tree
from orchestrator.application.use_cases.templates import TemplatePorts, seed_shipped
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.templates_loader import load_shipped_templates
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: `tests/unit/application/templates/test_shipped_smoke.py` -> the repository root.
SHIPPED_DIR = Path(__file__).resolve().parents[5] / "templates"

AT = datetime(2026, 9, 10, tzinfo=UTC)

#: The DB version a changed file lands as once a name already has a stored version 1.
NEXT_VERSION = 2


def seeded() -> FakeTemplateVersionRepository:
    """Every shipped file, through the exact seeding `main.py` runs at start-up."""
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))
    seed_shipped(ports, load_shipped_templates(SHIPPED_DIR))
    return templates


@pytest.fixture(scope="module")
def templates() -> FakeTemplateVersionRepository:
    return seeded()


def stored_names(templates: FakeTemplateVersionRepository) -> list[str]:
    return [summary.name for summary in templates.list()]


def graphs(templates: FakeTemplateVersionRepository) -> list[tuple[str, Graph]]:
    built = []
    for (name, version), stored in templates.versions.items():
        result = validate(stored.yaml, templates=templates)
        assert result.template is not None, (name, result.errors)
        built.append((f"{name}@{version}", build_template_graph(result.template)))
    return built


def test_every_shipped_file_seeds_clean(templates: FakeTemplateVersionRepository) -> None:
    """`seed_shipped` raises `ShippedTemplateInvalid` on any file that does not validate,
    so the fixture having been built is the assertion; the names confirm none was dropped."""
    assert stored_names(templates) == [path.stem for path in sorted(SHIPPED_DIR.glob("*.yaml"))]


@pytest.mark.parametrize("setting", ["init_template", "readiness_template"])
def test_the_settings_defaults_resolve_among_the_shipped_files(
    templates: FakeTemplateVersionRepository, setting: str
) -> None:
    """Replaces `test_the_names_the_product_starts_by_hand_still_ship` (Operator decision
    2026-09-30: no template name is hardcoded). The invariant it protected — a
    default-configured instance can dispatch its init and readiness Runs — now lives in the
    two Settings defaults, read off the model's field defaults so no environment is needed.
    """
    default = Settings.model_fields[setting].default

    assert isinstance(default, str) and default
    assert default in stored_names(templates), (setting, default)


def test_every_stored_version_validates_with_nothing_unvalidated(
    templates: FakeTemplateVersionRepository,
) -> None:
    for (name, _version), stored in templates.versions.items():
        result = validate(stored.yaml, templates=templates)

        assert result.errors == (), name
        assert result.unvalidated == (), name


def test_every_shipped_graph_is_self_contained(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Edges and groups name nodes of their own graph — a rename that misses a reference
    fails here whatever the new names are."""
    for label, graph in graphs(templates):
        ids = {node.id for node in graph.nodes}

        assert graph.nodes, label
        for edge in graph.edges:
            assert {edge.from_id, edge.to_id} <= ids, (label, edge)
        for group in graph.groups:
            assert set(group.members) <= ids, (label, group)


def test_no_shipped_id_carries_an_index_and_nothing_reads_unvalidated(
    templates: FakeTemplateVersionRepository,
) -> None:
    for label, graph in graphs(templates):
        for found in [*(node.id for node in graph.nodes), *(group.id for group in graph.groups)]:
            assert "[" not in found and "]" not in found, (label, found)
            assert not any(segment.isdigit() for segment in found.split(".")), (label, found)
        assert all(node.gate != "unvalidated" for node in graph.nodes), label


def test_the_tree_of_every_shipped_root_resolves(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Every call a shipped file makes reaches a stored version, from every root."""
    for name in stored_names(templates):
        latest = max(templates.list_versions(name))
        tree = resolve_tree(templates, TemplateRef(name=name, version=latest))

        assert tree.root.name == name


# --- a shipped file whose content moved (S5, multi-repo initiative, 2026-09-23) -------------


def test_every_pinned_call_of_every_shipped_version_is_found_by_the_resolver(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Revised 2026-09-30 (Operator decision: the mono-repo `initiative` and `story-run`
    workflows are retired to `templates/drafts/`, so `initiative` is no longer a seeded
    name). This replaces `test_initiatives_pinned_epic_call_resolves_against_the_freshly_
    seeded_files`, which read `initiative@1` and checked its one `epic@1` call. The
    invariant it protected — after a callee's content edit lands as a new version, a caller
    pinned to the old number still finds exactly the version it pinned via
    `ResolvedTree.callee()` — now holds for every call every shipped file records, in the
    fresh-seed shape every environment this system runs in today has."""
    pinned = [
        (name, version, ref)
        for (name, version), stored in templates.versions.items()
        for ref in stored.calls
    ]
    assert pinned, "no shipped file calls another — the check would be vacuous"

    for name, version, ref in pinned:
        tree = resolve_tree(templates, TemplateRef(name=name, version=version))

        assert tree.callee(ref.name, ref.version) is not None, (name, version, ref)


def test_a_shipped_files_content_change_lands_as_a_new_version_and_old_callers_still_resolve() -> (
    None
):
    """The seeding loader handles a file whose version moved: a name that already has a
    stored version gets its changed content seeded as the *next* version, never overwriting
    the old one (AD-15) — and a caller pinned to the old number still resolves it.
    `prior_epic` stands in for "whatever epic.yaml held before this story" — a synthetic,
    differently-hashed file, never the real shipped text (hard rule 6): the point under test
    is the seeding/resolution mechanism, not any shipped template's content.

    Revised 2026-09-30 (Operator decision: mono-repo `initiative` retired to
    `templates/drafts/`): the caller pinned to `epic@1` used to be the shipped
    `initiative.yaml`; it is now `PRIOR_CALLER`, a stored stand-in of this test's own, so the
    check pins no shipped file at all."""
    prior_epic = TemplateVersion(name="epic", version=1, yaml=PRIOR_EPIC, hash="prior-epic-sha")
    prior_caller = TemplateVersion(
        name="prior-caller",
        version=1,
        yaml=PRIOR_CALLER,
        hash="prior-caller-sha",
        calls=(TemplateRef(name="epic", version=1),),
    )
    templates = FakeTemplateVersionRepository([prior_epic, prior_caller])
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))

    results = seed_shipped(ports, load_shipped_templates(SHIPPED_DIR))

    epic_result = next(result for result in results if result.name == "epic")
    assert epic_result.inserted_as == NEXT_VERSION
    assert templates.list_versions("epic") == [1, NEXT_VERSION]
    assert templates.get("epic", 1) is prior_epic

    tree = resolve_tree(templates, TemplateRef(name="prior-caller", version=1))
    callee = tree.callee("epic", 1)

    assert callee is not None
    # `prior_epic`'s one step id (`sync`) is what tells the old, frozen content apart from
    # the current `templates/epic.yaml` (whose steps are `checkout`, `setup`, …).
    assert [entry.id for entry in callee.steps] == ["sync"]


#: A minimal, self-consistent stand-in for "epic content before S5" — never the real
#: shipped text (hard rule 6). Its only job is to occupy `epic@1` with a hash that differs
#: from the current `templates/epic.yaml`.
PRIOR_EPIC = (
    "name: epic\n"
    "version: 1\n"
    "inputs:\n"
    # `PRIOR_CALLER`'s call binds this exact key set — a stand-in occupying `epic@1` must
    # accept it or resolving the caller refuses with a callee input mismatch, which is a
    # fact about the caller/callee contract, not about what the real `epic.yaml` says.
    "  project:     { type: project,    required: true }\n"
    "  repository:  { type: repository, required: true }\n"
    "  base_branch: { type: string,     required: true }\n"
    "  branch:      { type: string,     required: true }\n"
    "  spec_folder: { type: path,       required: true }\n"
    "  epic:        { type: item,       required: false }\n"
    "  harness:     { type: enum, values: [claude, codex, local], default: claude }\n"
    "  model:       { type: string,     required: false }\n"
    "steps:\n"
    "  - id: sync\n"
    "    uses: git.sync\n"
    "    gate: deterministic\n"
)

#: A minimal caller pinned to `epic@1`, stored before seeding — the stand-in for "a Template
#: whose pinned callee's file has since changed" (until 2026-09-30 the shipped mono-repo
#: `initiative.yaml` played this part). Its bindings match `PRIOR_EPIC`'s declared inputs.
PRIOR_CALLER = (
    "name: prior-caller\n"
    "version: 1\n"
    "inputs:\n"
    "  project:      { type: project,    required: true }\n"
    "  repository:   { type: repository, required: true }\n"
    "  base_branch:  { type: string,     required: true }\n"
    "  epics_folder: { type: path,       required: true }\n"
    "  harness:      { type: enum, values: [claude, codex, local], default: claude }\n"
    "  model:        { type: string,     required: false }\n"
    "steps:\n"
    "  - id: epics\n"
    '    for_each: "{{epics_folder}}/epics.yaml"\n'
    "    as: epic\n"
    "    steps:\n"
    "      - id: epic\n"
    "        uses: template\n"
    "        with:\n"
    "          name: epic\n"
    "          version: 1\n"
    "          inputs:\n"
    '            project: "{{project}}"\n'
    '            repository: "{{repository}}"\n'
    '            base_branch: "{{base_branch}}"\n'
    '            branch: "{{epic.branch}}"\n'
    '            spec_folder: "{{epics_folder}}/{{epic.spec_folder}}"\n'
    '            epic: "{{epic}}"\n'
    '            harness: "{{harness}}"\n'
    '            model: "{{model}}"\n'
)
