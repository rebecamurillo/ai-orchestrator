"""Declared literal input defaults, applied when a Run or a caller leaves the input empty."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.application.templates.expressions import OPEN
from orchestrator.application.templates.model import ParsedTemplate


def with_defaults(template: ParsedTemplate, scope: Mapping[str, Any]) -> dict[str, Any]:
    """The scope, plus each declared literal default whose input is absent or `""`.

    An expression default (`{{model}}`) is validated but never applied here: binding it
    would substitute the braces themselves as the value.
    """
    bound = dict(scope)
    for decl in template.inputs:
        default = decl.default
        if default is None or (isinstance(default, str) and OPEN in default):
            continue
        if bound.get(decl.name, "") == "":
            bound[decl.name] = default
    return bound
