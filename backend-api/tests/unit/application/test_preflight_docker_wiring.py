"""`run_preflight` carries the `docker` line, last, and it never blocks a start.

`PreflightPorts.verify_docker` is `Settings.verify_docker` (`api/providers.py`); the line
itself is `application/preflight/docker.py`'s and is tested there. What is held here is the
wiring: the setting reaches the line, the line lands after FR-8's twelve, and a `warn` leaves
`start_allowed` as it was.
"""

from __future__ import annotations

import pytest

from orchestrator.application.preflight.model import CHECK_DOCKER, PreflightRequest
from orchestrator.application.use_cases.preflight import PreflightPorts, run_preflight
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_preflight_use_case import ports
from tests.unit.fakes.git import FakeGit


def repo_init_request() -> PreflightRequest:
    return PreflightRequest(
        template_name="repo-init",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
    )


def remote(files: dict[tuple[str, str], str], *, verify_docker: bool) -> PreflightPorts:
    """`repo_init_git()`'s remote, holding `files` at the base branch's commit."""
    git = FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files=files, listings={})
    return ports(git=git, verify_docker=verify_docker)


@pytest.mark.parametrize(("verify_docker", "status"), [(False, "warn"), (True, "ok")])
def test_a_compose_file_at_the_base_commit_gets_the_line_last(
    verify_docker: bool, status: str
) -> None:
    result = run_preflight(
        remote(
            {(fixtures.BASE_SHA, "compose.yaml"): "services: {}\n"}, verify_docker=verify_docker
        ),
        repo_init_request(),
    )

    assert result.lines[-1].check == CHECK_DOCKER
    assert result.lines[-1].status == status
    assert result.start_allowed is True


def test_a_repository_with_no_sign_gets_no_line() -> None:
    result = run_preflight(
        remote({}, verify_docker=False),
        repo_init_request(),
    )

    assert CHECK_DOCKER not in [line.check for line in result.lines]
    assert result.start_allowed is True


def test_the_ports_default_is_off() -> None:
    """Every construction that predates the setting means an instance without the sidecar."""
    assert ports(git=fixtures.repo_init_git()).verify_docker is False
