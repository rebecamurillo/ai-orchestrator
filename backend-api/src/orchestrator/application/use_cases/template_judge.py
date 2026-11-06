"""`judge_text` — the one place a Template's text meets `validate()` with a repository (AD-26).

`validate()` reads stored callees through the repository, and PyYAML plus the checkers can
still raise on text no rule covers yet. Those two failures must not read alike: a fault in
the text is a refusal (`invalid template`, at line 1), a fault of the repository — a database
error, a `Conflict` — is the caller's to see. `_Guarded` wraps every `TemplateVersionRepository`
method so anything the repository raises arrives as `PortRaised`, which `judge_text` unwraps.
"""

from __future__ import annotations

import structlog

from orchestrator.application.templates.model import (
    INVALID_TEMPLATE,
    ValidationResult,
)
from orchestrator.application.templates.table import problem
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateCaller, TemplateSummary, TemplateVersion
from orchestrator.domain.ports.templates import TemplateVersionRepository

log = structlog.get_logger(__name__)


class PortRaised(Exception):
    """A repository call made during `validate()` raised; carries the original to re-raise."""

    def __init__(self, error: Exception) -> None:
        super().__init__(str(error))
        self.error = error


class _Guarded:
    """A `TemplateVersionRepository` that re-raises anything its inner one raises as
    `PortRaised`, so `judge_text` can tell a port fault from a fault in the text."""

    def __init__(self, inner: TemplateVersionRepository) -> None:
        self._inner = inner

    def get(self, name: str, version: int) -> TemplateVersion | None:
        try:
            return self._inner.get(name, version)
        except Exception as error:
            raise PortRaised(error) from error

    def add_version(self, version: TemplateVersion, *, description: str | None) -> None:
        try:
            self._inner.add_version(version, description=description)
        except Exception as error:
            raise PortRaised(error) from error

    def list_versions(self, name: str) -> list[int]:
        try:
            return self._inner.list_versions(name)
        except Exception as error:
            raise PortRaised(error) from error

    def callers_of(self, name: str, version: int) -> list[TemplateCaller]:
        try:
            return self._inner.callers_of(name, version)
        except Exception as error:
            raise PortRaised(error) from error

    def pinned_by(self, name: str, version: int) -> int:
        try:
            return self._inner.pinned_by(name, version)
        except Exception as error:
            raise PortRaised(error) from error

    def names_with_source(self, source: str) -> frozenset[str]:
        try:
            return self._inner.names_with_source(source)
        except Exception as error:
            raise PortRaised(error) from error

    # Last: see the note in `domain/ports/templates.py` on a method named `list`.
    def list(self) -> list[TemplateSummary]:
        try:
            return self._inner.list()
        except Exception as error:
            raise PortRaised(error) from error


def judge_text(
    yaml_text: str, templates: TemplateVersionRepository, root_version: int | None = None
) -> ValidationResult:
    """`validate()` over one text, where a fault in the text is a result and a fault of the
    repository is an error.

    `root_version` is the stored number of a text that is already stored; `None` for a text
    that is not. Any exception `validate()` raises that did not come from the repository is
    one `invalid template` at line 1; the class name is logged, never put in the reason.
    """
    try:
        return validate(yaml_text, templates=_Guarded(templates), root_version=root_version)
    except PortRaised as raised:
        raise raised.error from None
    except Exception as error:
        log.warning("template text could not be judged", error=type(error).__name__)
        return ValidationResult(errors=(problem(1, INVALID_TEMPLATE),))
