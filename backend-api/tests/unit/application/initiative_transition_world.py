"""A three-entry initiative on the shared fakes, for the transitions of epic 8 story 3.

The sequence is spec (`interactive`, `workflow`, steps `intake product ux tech` and the gate),
merge (`interactive`, `step`, no steps) and build (`auto`, `step`). Every template is this
module's own fixture (hard rule 6), never a shipped `templates/*.yaml`.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from orchestrator.application.use_cases.initiative_advance import AdvancePorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.initiative import FrozenSequence, FrozenWorkflow, Initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.entities.project_package import GateWords, StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import ProbeResult
from tests.unit.application.initiative_world import InitiativeWorld
from tests.unit.application.templates.test_conversation_kind import document
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.remote_branches import FakeRemoteGit
from tests.unit.fakes.runs import FakeAttemptRepository, FakeStepRunRepository

SLUG = "snake-v3"
STEPS = ("intake", "product", "ux", "tech")
SPEC = ("fx.spec", 1)
MERGE = ("fx.merge", 1)
BUILD = ("fx.build", 2)
PLAIN_BUILD = ("fx.build-plain", 1)
SPEC_BUDGET = Decimal("12.00")
PROJECT_BUDGET = Decimal("40")
MAIN_SHA = "a" * 40
FEAT_SHA = "b" * 40
GATE_ROLE = "spec-gate"

HEAD_INPUTS = """inputs:
  project: { type: project, required: true }
  repository: { type: repository, required: true }
  base_branch: { type: string, required: true }
"""

MERGE_YAML = (
    "name: fx-merge\nversion: 1\ntype: interactive\n"
    + HEAD_INPUTS
    + """  slug: { type: string }
  branch: { type: string }
  initiative_folder: { type: path }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
"""
)

BUILD_INPUTS = (
    HEAD_INPUTS
    + """  branch: { type: string }
  initiative_folder: { type: path, required: true }
  harness: { type: string }
  model: { type: string }
  plan_model: { type: string }
  review_model: { type: string }
  senior_model: { type: string }
"""
)
BUILD_STEPS = """steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
  - id: epics
    for_each: "{{initiative_folder}}/epics.yaml"
    as: epic
    steps:
      - id: work
        uses: agent
        gate: liveness
        with: { harness: "{{harness}}", prompt: "do {{epic.id}}" }
"""
BUILD_YAML = (
    "name: fx-build\nversion: 2\n" + BUILD_INPUTS + "  autonomy: { type: string }\n" + BUILD_STEPS
)
PLAIN_BUILD_YAML = (
    "name: fx-build-plain\nversion: 1\n"
    + BUILD_INPUTS.replace("  senior_model: { type: string }\n", "")
    + BUILD_STEPS
)
EPICS = "- id: e1\n  title: One\n  branch: b\n  spec_folder: epic-1\n"


def spec_yaml() -> str:
    text = document(names=STEPS).replace("name: talking", "name: fx-spec")
    inputs = (
        HEAD_INPUTS
        + """  slug: { type: string }
  branch: { type: string }
  first_turn: { type: string }
  round_steps: { type: string }
  initiative_folder: { type: path }
"""
    )
    return text.replace("steps:\n", inputs + "steps:\n", 1)


def entry(
    ref: tuple[str, int], *, type_: str, shown: str, steps: tuple[StepDecl, ...] = ()
) -> FrozenWorkflow:
    return FrozenWorkflow(
        workflow=ref[0].split(".")[-1],
        template=ref[0],
        version=ref[1],
        type=type_,  # type: ignore[arg-type]
        shown_as=shown,  # type: ignore[arg-type]
        steps=steps,
    )


def spec_steps() -> tuple[StepDecl, ...]:
    talks = tuple(
        StepDecl(id=name, kind="conversation", skill="s", persona=None, file=None, writes=())
        for name in STEPS
    )
    gate = StepDecl(id="gate", kind="automatic", skill=None, persona=None, file=None, writes=())
    return (*talks, gate)


def sequence(build: tuple[str, int] = BUILD) -> FrozenSequence:
    return FrozenSequence(
        package="acme",
        sha="c" * 40,
        workflows=(
            entry(SPEC, type_="interactive", shown="workflow", steps=spec_steps()),
            entry(MERGE, type_="interactive", shown="step"),
            entry(build, type_="auto", shown="step"),
        ),
        gate=GateWords(pass_words=("pass",), fail_words=("fail",), owners_key="owners"),
        status_map={"done": "done"},
    )


class TransitionWorld(InitiativeWorld):
    """`InitiativeWorld` with the fixture templates, a stored initiative and the advance ports."""

    def __init__(
        self,
        *,
        build: tuple[str, int] = BUILD,
        probes: bool = True,
        scripts: dict[str, list[Any]] | None = None,
    ) -> None:
        super().__init__(
            git=FakeRemoteGit(refs={"main": MAIN_SHA}, files={}, listings={}, **(scripts or {}))
        )
        for (name, version), text in (
            (SPEC, spec_yaml()),
            (MERGE, MERGE_YAML),
            (BUILD, BUILD_YAML),
            (PLAIN_BUILD, PLAIN_BUILD_YAML),
        ):
            self.templates.add(
                TemplateVersion(
                    name=name, version=version, yaml=text, hash=f"{name}{version}", source="package"
                )
            )
        self.step_rows = FakeStepRunRepository()
        self.attempt_rows = FakeAttemptRepository()
        self.remote: FakeRemoteGit = self.git  # type: ignore[assignment]
        if probes:
            self.registry(
                FakeHarness(
                    probe_results=[
                        ProbeResult(ok=True, failing_reason=None, version="t", models=[])
                    ]
                    * 20
                )
            )
        self.initiative_row: Initiative = self.seed(
            self.initiative(slug=SLUG, sequence=sequence(build))
        )
        self.put_epics(MAIN_SHA)

    def registry(self, harness: FakeHarness | None) -> None:
        preflight = self.create_ports.preflight
        registry = {} if harness is None else {"claude": harness}
        self.create_ports = replace(
            self.create_ports, preflight=replace(preflight, harness_registry=registry)
        )

    def defaults(self, **changes: Any) -> None:
        self.project = self.project.model_copy(update=changes)
        self.projects.projects[self.project.id] = self.project

    def advance_ports(self) -> AdvancePorts:
        return AdvancePorts(
            initiatives=self.initiatives,
            advances=self.advances,
            runs=self.runs,
            create_run=self.create_ports,
            uow=self.uow,
            clock=self.harness.clock,
            steps=self.step_rows,
            attempts=self.attempt_rows,
            branches=self.remote,
        )

    def ended_run(
        self, position: int, *, status: str = "done", round_: int = 1, **fields: Any
    ) -> Run:
        run = build_run(
            status,  # type: ignore[arg-type]
            initiative_id=self.initiative_row.id,
            initiative_round=round_,
            initiative_position=position,
            project_id=self.project.id,
            repository_id=self.hub.id,
            budget_usd=SPEC_BUDGET,
            **{"inputs": {"harness": "claude", "model": "opus"}, **fields},
        )
        self.runs.add(run)
        return run

    def advance_of(self, run: Run) -> InitiativeAdvance:
        advance = InitiativeAdvance(
            id=new_id(),
            initiative_id=self.initiative_row.id,
            from_run_id=run.id,
            round=run.initiative_round or 1,
            position=run.initiative_position or 0,
        )
        self.advances.add(advance)
        return advance

    def spec_run(
        self,
        word: str | None = "pass",
        *,
        owners: Any = None,
        text: str = "- a defect",
        talks: bool = True,
    ) -> tuple[Run, InitiativeAdvance]:
        """A done spec Run holding four conversation rows and a gate row with a verdict."""
        run = self.ended_run(0)
        rows = [
            StepRun(
                id=new_id(),
                run_id=run.id,
                seq=seq,
                path=f"steps[{seq}]",
                label=name,
                kind="conversation",
                gate="human",
                status="done",
                with_resolved={
                    "step": name,
                    "writes": [f"initiatives/{SLUG}/epics.yaml"] if name == "tech" else [],
                },
            )
            for seq, name in enumerate(STEPS, start=1)
            if talks
        ]
        gate = StepRun(
            id=new_id(),
            run_id=run.id,
            seq=len(STEPS) + 1,
            path="gate",
            label="gate",
            kind="shell",
            gate="deterministic",
            status="done",
            role=GATE_ROLE,
            with_resolved={},
        )
        self.step_rows.add_many([*rows, gate])
        if word is not None:
            fields = {} if owners is None else {"owners": owners}
            self.attempt_rows.add(
                Attempt(
                    id=new_id(),
                    run_id=run.id,
                    step_run_id=gate.id,
                    n=1,
                    status="done",
                    verdict_word=word,
                    verdict_fields=fields,
                    verdict_text=text,
                )
            )
        return run, self.advance_of(run)

    def another_initiative(self, slug: str) -> None:
        """Make the next `spec_run`, `ended_run` and `advance_of` belong to a second initiative."""
        self.initiative_row = self.seed(self.initiative(slug=slug, sequence=sequence()))
        self.put_epics(MAIN_SHA)

    def put_epics(self, sha: str) -> None:
        folder = f"initiatives/{self.initiative_row.slug}"
        self.remote.files[(sha, f"{folder}/epics.yaml")] = EPICS
        self.remote.files[(sha, f"{folder}/epic-1/SPEC.md")] = "# spec\n"

    def spec_branch(self, *, epics: bool) -> None:
        """`spec/{slug}` on the remote, with or without the initiative's `epics.yaml`."""
        assert self.remote.refs is not None
        self.remote.refs[f"spec/{self.initiative_row.slug}"] = "d" * 40
        if epics:
            self.put_epics("d" * 40)
