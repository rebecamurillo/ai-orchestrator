"""`backend-api/Dockerfile`: BMAD is a package in `/opt/bmad`, not a harness-home folder (CAP-2)."""

from __future__ import annotations

import re

from tests.unit.conftest import REPO_ROOT

DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"
HARNESS_INSTALL = "scripts/harness/claude.sh install"


def _code() -> str:
    text = DOCKERFILE.read_text().replace("\\\n", " ")
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def _lines_with(needle: str) -> list[str]:
    return [line for line in _code().splitlines() if needle in line]


def test_the_package_prefix_is_created_and_owned_by_agent_in_the_existing_lines() -> None:
    mkdir = [line for line in _lines_with("mkdir -p") if "/opt/harness-image" in line]
    chown = [line for line in _lines_with("chown -R agent:agent") if "/opt/harness-image" in line]

    assert mkdir
    assert chown
    assert "/opt/bmad" in mkdir[0]
    assert "/opt/bmad" in chown[0]


def test_one_run_installs_the_package_after_the_last_user_agent_and_before_the_harnesses() -> None:
    code = _code()
    install = [m.start() for m in re.finditer(r"install_bmad_package", code)]
    last_user = max(m.start() for m in re.finditer(r"^USER agent", code, re.MULTILINE))
    harness = code.index(HARNESS_INSTALL)

    assert len(install) == 1
    assert last_user < install[0] < harness
    assert "_common.sh" in code[code.rfind("RUN", 0, install[0]) : install[0]]


def test_opt_bmad_is_never_a_mount_and_the_dockerfile_carries_no_bmad_version() -> None:
    code = _code()

    assert not re.search(r"^VOLUME\b.*", code, re.MULTILINE)
    for line in _lines_with("/opt/bmad"):
        assert "VOLUME" not in line
        assert "mount" not in line.lower()
    assert "BMAD_VERSION" not in code
