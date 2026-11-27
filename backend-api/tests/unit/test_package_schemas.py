"""`api/schemas/packages.py`: the request refuses unknown keys, the gate serialises `pass`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.packages import GateOut, PackageIn
from orchestrator.domain.entities.project_package import GateWords
from orchestrator.domain.ids import new_id


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        PackageIn.model_validate(
            {"repository_id": str(new_id()), "path": "p", "ref": "main", "extra": 1}
        )


def test_an_empty_ref_is_refused_and_an_empty_path_is_left_to_the_use_case() -> None:
    body = {"repository_id": str(new_id()), "path": "", "ref": "main"}
    assert PackageIn.model_validate(body).path == ""
    with pytest.raises(ValidationError):
        PackageIn.model_validate({**body, "ref": ""})


def test_the_gate_serialises_the_key_pass() -> None:
    gate = GateOut.of(GateWords(pass_words=("a",), fail_words=("b",), owners_key="owners"))

    assert gate.model_dump(by_alias=True) == {"pass": ["a"], "fail": ["b"], "owners_key": "owners"}
