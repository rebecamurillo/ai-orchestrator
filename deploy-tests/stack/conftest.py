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


import harness  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "stack: builds and installs a throwaway deployment stack")


@pytest.fixture(scope="session")
def stack_work(tmp_path_factory):
    return tmp_path_factory.mktemp("deploy-stack")


@pytest.fixture(scope="session")
def runner(stack_work):
    return harness.Runner(stack_work)


@pytest.fixture(scope="session")
def _tags_removed(runner):
    yield
    harness.remove_release_tags(
        runner,
        harness._release(harness.VERSION_1, None, ()),
        harness._release(harness.VERSION_2, None, ()),
    )


@pytest.fixture(scope="session")
def release_n(runner, stack_work, _tags_removed):
    repo_root = Path(__file__).resolve().parents[2]
    yield harness.build_release_n(runner, repo_root, stack_work / "build")


@pytest.fixture(scope="session")
def release_n1(runner, stack_work, release_n):
    yield harness.build_release_n1(runner, release_n, stack_work / "build")


@pytest.fixture
def installed_stack(runner, stack_work, _tags_removed):
    made = []

    def make(release, env=None):
        folder = stack_work / f"stack-{len(made)}-{release.version}"
        stack = harness.install_stack(runner, release, folder, env)
        made.append(stack)
        return stack

    yield make
    failed = []
    for stack in reversed(made):
        done = stack.teardown()
        if done.returncode != 0:
            failed.append(f"{stack.project}: {done.stderr.decode(errors='replace')[-2000:]}")
    assert not failed, "teardown failed: " + "; ".join(failed)
