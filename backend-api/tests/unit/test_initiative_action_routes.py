"""The three initiative action paths are published behind the bearer (story 5, epic 7, AC10)."""

from __future__ import annotations

from fastapi import FastAPI

from orchestrator.api.initiative_routes import install_initiative_routes

CANCEL = "/api/v1/initiatives/{initiative_id}/cancel"
START_NEXT = "/api/v1/initiatives/{initiative_id}/start-next"


def paths() -> dict[str, dict[str, dict[str, object]]]:
    app = FastAPI()
    install_initiative_routes(app)
    return app.openapi()["paths"]


def test_the_actions_are_post_only_and_create_joins_the_list() -> None:
    published = paths()

    assert set(published[CANCEL]) == {"post"}
    assert set(published[START_NEXT]) == {"post"}
    assert "post" in published["/api/v1/initiatives"]


def test_each_post_declares_401_and_its_refusals() -> None:
    published = paths()
    expected = {
        ("/api/v1/initiatives", "201"): {"401", "404", "409", "422"},
        (CANCEL, "200"): {"401", "404", "409"},
        (START_NEXT, "200"): {"401", "404", "409", "422"},
    }

    for (path, success), codes in expected.items():
        responses = published[path]["post"]["responses"]  # type: ignore[index]
        assert success in responses
        assert codes <= set(responses)
