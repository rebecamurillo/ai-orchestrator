"""`step_drawer`'s `files_read` over the shared fakes (story 6, AC4-AC6)."""

from __future__ import annotations

from datetime import timedelta

from orchestrator.application.use_cases.run_step_drawer import (
    FilesRead,
    StepDrawerPorts,
    step_drawer,
)
from orchestrator.domain.entities.facts import AttemptFacts, EventFact, FactSet
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.log_facts import LogFacts, LogFactsCapabilities
from tests.unit.application.test_run_step_drawer import NOW, a_row, a_run, an_attempt
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.git_history import FakeGitHistory
from tests.unit.fakes.log_facts import ScriptedLogFacts
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOT_RECORDED = FilesRead("not_recorded", ())


def _extractor(name: str = "claude", version: int = 2, *, reads: bool = True) -> ScriptedLogFacts:
    found = ScriptedLogFacts(name=name, version=version)
    found.capabilities = LogFactsCapabilities(False, False, False, False, files_read=reads)
    return found


def _read(path: str | None, kind: str = "read") -> EventFact:
    return EventFact(at=NOW, conversation="main", kind=kind, path=path)  # type: ignore[arg-type]


class Rig:
    def __init__(self, extractors: dict[str, LogFacts], kind: str = "agent") -> None:
        self.run = a_run()
        self.row: StepRun = a_row(self.run, kind=kind)
        self.attempt = an_attempt(self.row)
        self.facts = FakeFactSetRepository()
        self.ports = StepDrawerPorts(
            runs=FakeRunRepository([self.run]),
            steps=FakeStepRunRepository([self.row]),
            attempts=FakeAttemptRepository([self.attempt]),
            logs=FakeLogReader(),
            history=FakeGitHistory(),
            facts=self.facts,
            extractors=extractors,
        )

    def store(
        self,
        events: tuple[EventFact, ...] = (),
        *,
        extractor: str = "claude",
        version: int = 2,
        status: str = "ok",
        later: int = 0,
    ) -> None:
        fact_set = FactSet(
            id=new_id(),
            attempt_id=self.attempt.id,
            run_id=self.run.id,
            extractor=extractor,
            extractor_version=version,
            read_at=NOW + timedelta(seconds=later),
            status=status,  # type: ignore[arg-type]
        )
        self.facts.add(fact_set, AttemptFacts(events=events))

    def files_read(self) -> FilesRead:
        return step_drawer(self.ports, self.run.id, 1, 0).files_read


def test_a_current_set_lists_sorted_distinct_read_paths() -> None:
    rig = Rig({"claude": _extractor()})
    rig.store((_read("b.py"), _read("a.py"), _read("a.py"), _read("c.py", "write"), _read(None)))

    assert rig.files_read() == FilesRead("listed", ("a.py", "b.py"))


def test_a_partial_set_counts() -> None:
    rig = Rig({"claude": _extractor()})
    rig.store((_read("a.py"),), status="partial")

    assert rig.files_read() == FilesRead("listed", ("a.py",))


def test_a_current_set_without_reads_is_none() -> None:
    rig = Rig({"claude": _extractor()})
    rig.store((_read("x.py", "write"),))

    assert rig.files_read() == FilesRead("none", ())


def test_sets_that_do_not_qualify_are_not_recorded() -> None:
    rig = Rig(
        {"claude": _extractor(), "codex": _extractor("codex", 1, reads=False)},
    )
    rig.store((_read("a.py"),), version=1)
    rig.store((_read("a.py"),), extractor="codex", version=1)
    rig.store((_read("a.py"),), status="failed")
    rig.store((_read("a.py"),), extractor="gone")

    assert rig.files_read() == NOT_RECORDED


def test_an_attempt_without_fact_sets_is_not_recorded() -> None:
    assert Rig({"claude": _extractor()}).files_read() == NOT_RECORDED


def test_the_latest_qualifying_set_decides() -> None:
    rig = Rig({"claude": _extractor(), "other": _extractor("other", 1)})
    rig.store((_read("old.py"),), later=1)
    rig.store((_read("new.py"),), extractor="other", version=1, later=5)

    assert rig.files_read() == FilesRead("listed", ("new.py",))


def test_a_non_agent_row_is_not_recorded() -> None:
    rig = Rig({"claude": _extractor()}, kind="git.commit")
    rig.store((_read("a.py"),))

    assert rig.files_read() == NOT_RECORDED


def test_a_row_without_an_attempt_is_none() -> None:
    rig = Rig({"claude": _extractor()})
    rig.ports.attempts.attempts.clear()  # type: ignore[attr-defined]

    assert rig.files_read() == FilesRead("none", ())
