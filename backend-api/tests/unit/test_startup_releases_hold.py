"""`launch_engine` deletes every hold row, committed, before the engine launches (AD-30)."""

from __future__ import annotations

from typing import Any

from orchestrator.infrastructure.dbos.startup import launch_engine, serving


class Session:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def execute(self, statement: Any) -> None:
        self.events.append(f"execute: {statement}")

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


class Engine:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def launch(self) -> None:
        self.events.append("launch")


def test_the_holds_are_deleted_and_committed_before_the_engine_launches() -> None:
    events: list[str] = []

    with serving(Engine(events), lambda: Session(events)):  # type: ignore[arg-type]
        launch_engine()

    assert events == ["execute: DELETE FROM instance_hold", "commit", "close", "launch"]


def test_a_process_with_no_session_factory_deletes_nothing_and_still_launches() -> None:
    events: list[str] = []

    with serving(Engine(events)):  # type: ignore[arg-type]
        launch_engine()

    assert events == ["launch"]
