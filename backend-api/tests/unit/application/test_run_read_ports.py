"""`run_read_ports.py`: the read ports the Run routes share, moved out of `create_run.py`."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases import create_run, run_read_ports
from orchestrator.application.use_cases.run_read_ports import RunReadPorts, get_run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.test_dependency_resolution import a_run
from tests.unit.fakes.runs import FakeRunRepository


def test_get_run_returns_a_stored_run() -> None:
    run = a_run()

    assert get_run(RunReadPorts(runs=FakeRunRepository([run])), run.id) == run


def test_get_run_raises_not_found_for_a_missing_id() -> None:
    with pytest.raises(NotFound):
        get_run(RunReadPorts(runs=FakeRunRepository()), new_id())


def test_create_run_re_exports_the_moved_names() -> None:
    assert create_run.RunReadPorts is run_read_ports.RunReadPorts
    assert create_run.get_run is run_read_ports.get_run
