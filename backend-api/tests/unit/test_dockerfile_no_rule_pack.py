"""The image installs the Opengrep engine and fetches no rule pack (epic 6 story 2, AC9).

Each repository declares its own rules (`sast.rules`); a rule pack in the image would ship
third-party rules the instance can no longer be installed for clients with (decision C5).
"""

from __future__ import annotations

import pytest

from tests.unit.test_dockerfiles import code, dockerfile, instructions

FORBIDDEN = (
    "semgrep-rules",
    "--config p/",
    "--config r/",
    "--config auto",
    "registry.semgrep.dev",
    "semgrep.dev/c/",
)


def test_the_image_installs_opengrep_from_one_run() -> None:
    runs = [
        run for run in instructions(code(dockerfile("backend-api")), "RUN") if "opengrep" in run
    ]
    assert len(runs) == 1
    assert "/usr/local/bin/opengrep" in runs[0]


@pytest.mark.parametrize("fragment", FORBIDDEN)
def test_no_line_of_the_image_fetches_a_rule_pack(fragment: str) -> None:
    assert fragment not in code(dockerfile("backend-api"))


def test_no_rule_file_is_downloaded() -> None:
    downloads = [
        run for run in instructions(code(dockerfile("backend-api")), "RUN") if "curl" in run
    ]
    assert not [run for run in downloads if ".yaml" in run or ".yml" in run]
