"""`PUT /api/v1/repositories/{id}/initiative-folder` (story 2 of epic 6, AC1-AC4)."""

from __future__ import annotations

from uuid import UUID

import pytest

from tests.unit.test_repositories_router import (
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNPROCESSABLE,
    PROBLEM_MEDIA_TYPE,
    REPOSITORIES,
    UNKNOWN_ID,
    Harness,
    a_payload,
    add,
    api,  # noqa: F401  (the fixture)
)


async def stored(api: Harness) -> str:  # noqa: F811
    created = await add(api, api.project())
    return str(created.json()["id"])


async def read(api: Harness, repository_id: str) -> dict[str, object]:  # noqa: F811
    async with api.client() as client:
        return (await client.get(f"{REPOSITORIES}/{repository_id}")).json()  # type: ignore[no-any-return]


async def put(api: Harness, repository_id: str, body: object) -> object:  # noqa: F811
    async with api.client() as client:
        return await client.put(f"{REPOSITORIES}/{repository_id}/initiative-folder", json=body)


async def test_a_new_repository_reads_initiatives(api: Harness) -> None:  # noqa: F811
    repository_id = await stored(api)

    assert (await read(api, repository_id))["initiative_folder"] == "initiatives"


async def test_the_folder_is_set_and_read_back(api: Harness) -> None:  # noqa: F811
    repository_id = await stored(api)

    response = await put(api, repository_id, {"initiative_folder": "specs/initiatives"})

    assert response.status_code == HTTP_OK  # type: ignore[attr-defined]
    assert response.json()["initiative_folder"] == "specs/initiatives"  # type: ignore[attr-defined]
    assert (await read(api, repository_id))["initiative_folder"] == "specs/initiatives"


@pytest.mark.parametrize("folder", ["", "/abs", "a/../b", "a/./b", "a/", "a//b"])
async def test_an_invalid_folder_is_a_422_and_stores_nothing(api: Harness, folder: str) -> None:  # noqa: F811
    repository_id = await stored(api)

    response = await put(api, repository_id, {"initiative_folder": folder})

    assert response.status_code == HTTP_UNPROCESSABLE  # type: ignore[attr-defined]
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)  # type: ignore[attr-defined]
    assert "initiative_folder" in response.json()["detail"]  # type: ignore[attr-defined]
    assert (await read(api, repository_id))["initiative_folder"] == "initiatives"


@pytest.mark.parametrize("body", [{}, {"initiative_folder": "a", "extra": 1}])
async def test_a_missing_or_unknown_key_is_a_422(api: Harness, body: dict[str, object]) -> None:  # noqa: F811
    repository_id = await stored(api)

    assert (await put(api, repository_id, body)).status_code == HTTP_UNPROCESSABLE  # type: ignore[attr-defined]


async def test_an_unknown_repository_is_a_404(api: Harness) -> None:  # noqa: F811
    response = await put(api, UNKNOWN_ID, {"initiative_folder": "specs"})

    assert response.status_code == HTTP_NOT_FOUND  # type: ignore[attr-defined]


async def test_the_full_replace_put_keeps_the_folder(api: Harness) -> None:  # noqa: F811
    repository_id = await stored(api)
    await put(api, repository_id, {"initiative_folder": "specs"})

    async with api.client() as client:
        response = await client.put(f"{REPOSITORIES}/{repository_id}", json=a_payload())

    assert response.status_code == HTTP_OK
    assert response.json()["initiative_folder"] == "specs"
    assert (await read(api, repository_id))["initiative_folder"] == "specs"


async def test_the_operation_id_is_the_one_the_tool_allow_list_names(api: Harness) -> None:  # noqa: F811
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    operation = document["paths"][f"{REPOSITORIES}/{{repository_id}}/initiative-folder"]["put"]
    assert operation["operationId"] == (
        "set_initiative_folder_api_v1_repositories__repository_id__initiative_folder_put"
    )
    assert set(operation["responses"]) - {"200", "401"} == {"404", "422"}
    assert UUID(UNKNOWN_ID)
