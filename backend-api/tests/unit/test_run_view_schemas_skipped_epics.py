"""`SummaryOut.skipped_epics` (6.5): `.of()` projects the field `test_run_view_schemas.py`
(4.12, predates this story) does not yet construct — that file's own `Summary(...)` call is
left unedited (hard rule 1), which is exactly why `Summary.skipped_epics` needs a default.
"""

from __future__ import annotations

from orchestrator.api.schemas.run_views import SummaryOut
from orchestrator.application.use_cases.run_view_types import Summary


def test_skipped_epics_is_projected_when_present() -> None:
    summary = Summary(progress=None, links=[], skipped=[], skipped_epics=[1, 2])

    out = SummaryOut.of(summary)

    assert out.skipped_epics == [1, 2]


def test_skipped_epics_defaults_to_empty_off_the_dataclasss_own_default() -> None:
    """A caller built before this story (`test_run_view_schemas.py`'s own `Summary(...)`)
    supplies no `skipped_epics` at all; the dataclass default carries it through."""
    summary = Summary(progress=None, links=["https://example.invalid"], skipped=["4-2"])

    out = SummaryOut.of(summary)

    assert out.skipped_epics == []
