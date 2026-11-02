"""Story 3-4 review fixes (2026-11-02) over HTTP: none of them is a 5xx."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.unit.test_project_channel_router import Harness, a_body

HTTP_OK = 200
HTTP_UNPROCESSABLE = 422


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


async def test_a_token_the_current_key_cannot_open_is_a_200_not_ok(api: Harness) -> None:
    async with api.client() as client:
        await client.put(api.url(), json=a_body())
        stored = api.channels.get(api.project.id)
        assert stored is not None
        api.channels.put(replace(stored, token_enc="fake-enc:99:rotated"))
        response = await client.post(api.url(suffix="/test"))

    assert response.status_code == HTTP_OK
    assert response.json() == {
        "ok": False,
        "detail": "the stored token cannot be decrypted with the current key; save the token again",
    }


async def test_a_keep_across_a_host_change_is_a_422_naming_the_token(api: Harness) -> None:
    body = a_body(base_url="https://elsewhere.example")
    del body["token"]

    async with api.client() as client:
        await client.put(api.url(), json=a_body())
        response = await client.put(api.url(), json=body)

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "token: enter the token again when the host changes"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://[::1",
        "http://[zz]/",
        "https://u:p@chat.example.com",
        "https://h/?a=1",
        "https://h/#x",
    ],
)
async def test_a_bad_base_url_is_a_422_at_its_field(api: Harness, base_url: str) -> None:
    async with api.client() as client:
        response = await client.put(api.url(), json=a_body(base_url=base_url))

    assert response.status_code == HTTP_UNPROCESSABLE
    assert [error["path"] for error in response.json()["errors"]] == ["body.base_url"]
    assert api.channels.channels == {}
