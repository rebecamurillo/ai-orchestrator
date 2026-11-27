"""The three initiative read paths are published behind the bearer (story 4, epic 7)."""

from __future__ import annotations

from fastapi import FastAPI

from orchestrator.api.initiative_routes import install_initiative_routes

PATHS = (
    "/api/v1/initiatives",
    "/api/v1/projects/{project_id}/initiatives",
    "/api/v1/initiatives/{initiative_id}",
)


def test_each_read_path_is_published_with_a_401() -> None:
    app = FastAPI()

    install_initiative_routes(app)

    paths = app.openapi()["paths"]
    for path in PATHS:
        # story 5 of epic 7, 2026-11-22: `POST /initiatives` joins the list path
        assert set(paths[path]) == ({"get", "post"} if path == PATHS[0] else {"get"})
        assert "401" in paths[path]["get"]["responses"]
        assert "404" in paths[path]["get"]["responses"]
