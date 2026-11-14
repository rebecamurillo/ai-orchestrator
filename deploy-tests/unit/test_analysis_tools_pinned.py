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


OPENGREP_ARGS = ("OPENGREP_VERSION", "OPENGREP_SHA256_AMD64", "OPENGREP_SHA256_ARM64")
RULE_PACK_FRAGMENTS = (
    "semgrep-rules",
    "--config p/",
    "--config r/",
    "--config auto",
    "registry.semgrep.dev",
    "semgrep.dev/c/",
)


def opengrep_run() -> str:
    runs = [
        run
        for run in instructions(code(dockerfile("backend-api")), "RUN")
        if "/usr/local/bin/opengrep" in run
    ]
    assert len(runs) == 1, runs
    return runs[0]


def test_the_opengrep_version_is_a_literal() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", args().get("OPENGREP_VERSION", ""))


@pytest.mark.parametrize("name", OPENGREP_ARGS[1:])
def test_opengrep_has_a_literal_sha256_per_architecture_used_in_its_run(name: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", args().get(name, ""))
    assert f"${{{name}}}" in opengrep_run()


def test_the_opengrep_download_is_checked_once_with_sha256sum() -> None:
    assert opengrep_run().count("sha256sum -c -") == 1


def test_the_opengrep_run_names_the_release_and_the_pinned_version() -> None:
    assert "opengrep/opengrep/releases/download/v${OPENGREP_VERSION}/" in opengrep_run()


def test_opengrep_is_installed_before_the_user_exists() -> None:
    text = code(dockerfile("backend-api"))
    assert text.index("/usr/local/bin/opengrep") < text.index("useradd")


def test_the_opengrep_pin_equals_the_recorded_fixture() -> None:
    recorded = re.search(
        r"\d+\.\d+\.\d+", (FIXTURES / "tier2" / "opengrep" / "opengrep-version.txt").read_text()
    )
    assert recorded is not None
    assert args()["OPENGREP_VERSION"] == recorded.group(0)


@pytest.mark.parametrize("fragment", RULE_PACK_FRAGMENTS)
def test_no_rule_pack_is_fetched_anywhere_in_the_dockerfile(fragment: str) -> None:
    assert fragment not in code(dockerfile("backend-api"))
