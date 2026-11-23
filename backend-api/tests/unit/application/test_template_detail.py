"""`template_detail.py`: the read model of one stored version (story 1 of epic 3, 2026-11-23)."""

from __future__ import annotations

from orchestrator.application.use_cases import templates
from orchestrator.application.use_cases.template_detail import TemplateVersionDetail
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.fakes.clock import FakeClock


def test_defaults_and_reexport() -> None:
    stored = TemplateVersion(name="a", version=1, yaml="", hash="h", created_at=FakeClock().now())
    detail = TemplateVersionDetail(template=stored, called_by=(), inputs=())
    assert detail.type == "auto"
    assert detail.pinned_by == 0
    assert templates.TemplateVersionDetail is TemplateVersionDetail
