"""`refuse_if_in_folder` on the save route (epic 2 story 2, 2026-11-12, AD-34)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.test_templates_in_folder import BODY, SMOKE, TEMPLATES, Harness

HTTP_CREATED = 201
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
SAVE = f"{TEMPLATES}/{SMOKE}/versions"


def held(env: dict[str, str]) -> Harness:
    return Harness(env, FakeTemplateFolders(folder=ready(file(SMOKE, "x"), path="/folder")))


async def post(api: Harness, body: dict[str, Any], name: str = SMOKE) -> Any:
    async with api.client() as client:
        return await client.post(f"{TEMPLATES}/{name}/versions", json=body)


def v2(name: str = SMOKE) -> str:
    return BODY.format(n=name, v=2)


async def test_a_flagged_save_of_a_folder_held_name_is_refused_and_stores_nothing(
    env: dict[str, str],
) -> None:
    api = held(env)

    response = await post(api, {"yaml": v2(), "refuse_if_in_folder": True})

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "refusal-template-in-folder"
    assert body["guide"] == "errors/refusal-template-in-folder"
    assert body["title"] == "template held in the operator folder"
    for part in (f"{SMOKE}.yaml", "/folder", "reload_templates"):
        assert part in body["detail"]
    assert api.templates.list_versions(SMOKE) == [1]


async def test_the_unflagged_save_is_the_web_editors_and_succeeds(env: dict[str, str]) -> None:
    api = held(env)

    response = await post(api, {"yaml": v2()})

    assert response.status_code == HTTP_CREATED
    assert response.json()["in_folder"] is True
    assert api.templates.list_versions(SMOKE) == [1, 2]


async def test_a_flagged_save_of_a_name_the_folder_does_not_hold_succeeds(
    env: dict[str, str],
) -> None:
    api = held(env)

    response = await post(api, {"yaml": v2("plain"), "refuse_if_in_folder": True}, "plain")

    assert response.status_code == HTTP_CREATED
    assert response.json()["in_folder"] is False


def test_the_contract_declares_the_409_and_the_flag(env: dict[str, str]) -> None:
    document = held(env).app.openapi()

    operation = document["paths"][f"{TEMPLATES}/{{name}}/versions"]["post"]
    assert "409" in operation["responses"]
    assert "application/problem+json" in operation["responses"]["409"]["content"]
    schema = document["components"]["schemas"]["SaveVersionIn"]
    flag = schema["properties"]["refuse_if_in_folder"]
    assert flag["type"] == "boolean"
    assert flag["default"] is False
    assert "refuse_if_in_folder" not in schema["required"]


@pytest.mark.parametrize("flag", [True, False])
async def test_a_flagged_or_unflagged_invalid_body_on_a_free_name_is_still_a_422(
    env: dict[str, str], flag: bool
) -> None:
    api = held(env)

    response = await post(api, {"yaml": "name: plain\n", "refuse_if_in_folder": flag}, "plain")

    assert response.status_code == HTTP_UNPROCESSABLE
