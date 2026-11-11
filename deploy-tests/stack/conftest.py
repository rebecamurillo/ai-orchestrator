import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import guard


@pytest.fixture(scope="session", autouse=True)
def deploy_stack(tmp_path_factory):
    project = f"aio-deploy-{uuid.uuid4().hex[:8]}"
    folder = tmp_path_factory.mktemp("stack")
    guard.check_project(project)
    guard.check_folder(folder)
    yield project, folder
