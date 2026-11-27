"""`install_initiative_routes` mounts the package router behind the bearer (story 3 of epic 6)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from fastapi import FastAPI

from orchestrator.api.initiative_routes import install_initiative_routes
from orchestrator.api.protected_routes import install_metrics_routes

PATH = "/api/v1/projects/{project_id}/package"


def test_the_package_path_is_published_behind_the_bearer() -> None:
    app = FastAPI()

    install_initiative_routes(app)

    operations = app.openapi()["paths"][PATH]
    assert set(operations) == {"put", "get", "delete"}
    for operation in operations.values():
        assert "401" in operation["responses"]


def test_the_metrics_installer_calls_it_last() -> None:
    app = FastAPI()

    install_metrics_routes(app)

    assert PATH in app.openapi()["paths"]
    paths = list(app.openapi()["paths"])
    assert (
        paths.index(PATH) > paths.index("/api/v1/runs/{run_id}/files/by-epic")
        if ("/api/v1/runs/{run_id}/files/by-epic" in paths)
        else True
    )


@pytest.mark.parametrize("first", ["initiative_routes", "protected_routes"])
def test_either_module_imports_first(first: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import orchestrator.api.{first}"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
