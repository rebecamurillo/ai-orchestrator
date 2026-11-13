"""The backend image pins the four analysis tools (epic 5 story 3, AD-14, RM-5).

Textual checks on `backend-api/Dockerfile`; nothing here builds the image or runs a tool. It
lives with the deployment tests and is written, not run, in the story's Run (member AD-31).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_dockerfiles import build_args, code, dockerfile, instructions

FIXTURES = REPO_ROOT / "backend-api" / "tests" / "unit" / "fixtures" / "analysis"
VERSION_ARGS = (
    "GITLEAKS_VERSION",
    "OSV_SCANNER_VERSION",
    "LIZARD_VERSION",
    "JSCPD_VERSION",
)
CHECKSUM_ARGS = (
    "GITLEAKS_SHA256_AMD64",
    "GITLEAKS_SHA256_ARM64",
    "OSV_SCANNER_SHA256_AMD64",
    "OSV_SCANNER_SHA256_ARM64",
)
#: Each recorded tool's `--version` output, committed beside its other fixtures.
VERSION_FIXTURES = {
    "GITLEAKS_VERSION": FIXTURES / "gitleaks-version.txt",
    "JSCPD_VERSION": FIXTURES / "tier1b" / "jscpd-version.txt",
    "LIZARD_VERSION": FIXTURES / "tier1b" / "lizard-version.txt",
}
#: The downloaded binaries: the gitleaks archive and the osv-scanner executable.
DOWNLOADS = 2


def args() -> dict[str, str]:
    return build_args(dockerfile("backend-api"))


def install_run() -> str:
    runs = [
        run for run in instructions(code(dockerfile("backend-api")), "RUN") if "gitleaks" in run
    ]
    assert len(runs) == 1, runs
    return runs[0]


@pytest.mark.parametrize("name", VERSION_ARGS)
def test_each_tool_version_is_a_literal(name: str) -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", args().get(name, ""))


@pytest.mark.parametrize("name", CHECKSUM_ARGS)
def test_each_download_has_a_literal_sha256_per_architecture(name: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", args().get(name, ""))


@pytest.mark.parametrize("name", CHECKSUM_ARGS)
def test_every_checksum_is_used_in_the_install_run(name: str) -> None:
    assert f"${{{name}}}" in install_run()


def test_every_download_is_checked_with_sha256sum() -> None:
    assert install_run().count("sha256sum -c -") == DOWNLOADS


def test_the_install_run_names_each_pinned_version() -> None:
    run = install_run()
    assert "gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/" in run
    assert "google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/" in run
    assert '"lizard==${LIZARD_VERSION}"' in run
    assert '"jscpd@${JSCPD_VERSION}"' in run


def test_the_install_run_installs_as_root_onto_the_agents_path_before_the_user_exists() -> None:
    text = dockerfile("backend-api")
    assert text.index("gitleaks_${GITLEAKS_VERSION}") < text.index("useradd")
    assert "/usr/local/bin" in install_run()


@pytest.mark.parametrize(("name", "path"), sorted(VERSION_FIXTURES.items()))
def test_each_pinned_version_equals_the_recorded_fixtures(name: str, path: object) -> None:
    recorded = re.search(r"\d+\.\d+\.\d+", path.read_text())  # type: ignore[attr-defined]
    assert recorded is not None
    assert args()[name] == recorded.group(0)


def test_the_osv_scanner_pin_equals_the_version_its_synthetic_report_imitates() -> None:
    sarif = json.loads((FIXTURES / "tier1b" / "synthetic-osv.sarif").read_text())
    assert args()["OSV_SCANNER_VERSION"] == sarif["runs"][0]["tool"]["driver"]["version"]
