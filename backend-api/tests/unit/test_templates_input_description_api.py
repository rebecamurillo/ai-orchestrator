"""An input's `description` through `/api/v1/templates` and `InputDeclOut` (story 3, 2026-11-06)."""

from __future__ import annotations

import pytest

from orchestrator.api.schemas.templates import InputDeclOut
from orchestrator.application.templates.model import InputDecl
from tests.unit.test_templates_router import TEMPLATES, Harness

HTTP_OK = 200
HTTP_CREATED = 201

WITH_INPUTS = (
    "name: leaf\nversion: 1\n"
    "inputs:\n"
    "  spec_folder:\n    type: path\n    required: true\n    description: Folder holding SPEC.md\n"
    "  note:\n    type: string\n"
    "steps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


async def test_a_saved_description_is_read_back(api: Harness) -> None:
    async with api.client() as client:
        saved = await client.post(f"{TEMPLATES}/leaf/versions", json={"yaml": WITH_INPUTS})
        read = await client.get(f"{TEMPLATES}/leaf/1")

    assert saved.status_code == HTTP_CREATED, saved.text
    assert read.status_code == HTTP_OK
    inputs = read.json()["inputs"]
    assert inputs[0]["description"] == "Folder holding SPEC.md"
    assert "description" in inputs[1]
    assert inputs[1]["description"] is None


def test_input_decl_out_maps_the_description() -> None:
    decl = InputDecl(line=1, name="a", type="string", description="x")

    assert InputDeclOut.of(decl).description == "x"
    assert InputDeclOut.of(InputDecl(line=1, name="a", type="string")).description is None
