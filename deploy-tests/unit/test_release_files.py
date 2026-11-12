"""The release's files agree with each other (story 5, epic 2, SPEC CAP-5, AD-28).

`VERSION` and the compose image tags, `deploy/release.env` and the harness scripts'
defaults, and the shape of the `setup` service whose mounts draw the secrets boundary.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

import pytest
import yaml

from tests.unit.conftest import REPO_ROOT, parse_env_example

VERSION = (REPO_ROOT / "VERSION").read_text().strip()
COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
RELEASE_ENV = REPO_ROOT / "deploy" / "release.env"
HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
HARNESSES = ("claude", "codex", "opencode")

PIN_NAMES = {
    "BMAD_VERSION",
    "DBOS_APPLICATION_VERSION",
    "CLAUDE_CODE_VERSION",
    "CODEX_VERSION",
    "OPENCODE_VERSION",
    "LANGFUSE_OPENCODE_PLUGIN_VERSION",
}


def _compose() -> dict[str, Any]:
    loaded = yaml.safe_load(COMPOSE.read_text())
    assert isinstance(loaded, dict)
    return loaded


def _setup() -> dict[str, Any]:
    return _compose()["services"]["setup"]


def _default(script: str, name: str) -> str:
    text = (HARNESS_DIR / f"{script}.sh").read_text()
    match = re.search(rf': "\$\{{{name}:=([^}}]*)\}}"', text)
    assert match, f"{script}.sh declares no default for {name}"
    return match.group(1)


def _asset_dirs() -> list[str]:
    entries: list[str] = []
    for harness in HARNESSES:
        out = subprocess.run(  # fixed argv, no shell
            ["bash", str(HARNESS_DIR / f"{harness}.sh"), "asset-dirs"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        entries.extend(line for line in out.splitlines() if line)
    return entries


def _volumes() -> list[dict[str, Any]]:
    """Every setup volume in long form; the short form `src:dst[:ro]` is normalised."""
    volumes: list[dict[str, Any]] = []
    for entry in _setup()["volumes"]:
        if isinstance(entry, dict):
            volumes.append(entry)
            continue
        parts = entry.split(":")
        volumes.append({"source": parts[0], "target": parts[1], "read_only": parts[2:] == ["ro"]})
    return volumes


# ── VERSION and the image tags ───────────────────────────────────────────────


@pytest.mark.parametrize("name", ["backend-api", "web-client"])
def test_the_compose_image_tag_equals_version(name: str) -> None:
    image = _compose()["services"][name]["image"]

    assert image == f"ghcr.io/rebecamurillo/ai-orchestrator/{name}:{VERSION}"


def test_the_setup_service_uses_the_backend_image() -> None:
    assert _setup()["image"] == _compose()["services"]["backend-api"]["image"]


# ── release.env and the scripts' defaults ────────────────────────────────────


def test_release_env_holds_exactly_the_six_pins() -> None:
    assert set(parse_env_example(RELEASE_ENV)) == PIN_NAMES


@pytest.mark.parametrize(
    ("name", "script"),
    [
        ("BMAD_VERSION", "_common"),
        ("CLAUDE_CODE_VERSION", "claude"),
        ("CODEX_VERSION", "codex"),
        ("OPENCODE_VERSION", "opencode"),
        ("LANGFUSE_OPENCODE_PLUGIN_VERSION", "opencode"),
    ],
)
def test_a_pin_equals_its_script_default(name: str, script: str) -> None:
    assert parse_env_example(RELEASE_ENV)[name] == _default(script, name)


def test_the_backend_reads_release_env_then_dotenv() -> None:
    env_file = _compose()["services"]["backend-api"]["env_file"]

    assert [entry["path"] for entry in env_file] == ["release.env", ".env"]
    assert all(entry["required"] is True for entry in env_file)


# ── the setup service ────────────────────────────────────────────────────────


def test_the_setup_service_has_the_declared_shape() -> None:
    setup = _setup()

    assert "env_file" not in setup
    assert set(setup["environment"]) == {"BMAD_VERSION", "ORCH_SETUP_TRIGGER", "ORCH_RELEASE"}
    assert setup["profiles"] == ["setup"]
    assert setup["entrypoint"] == ["/app/scripts/setup/run.sh"]
    assert setup["restart"] == "no"


def test_the_setup_service_mounts_only_the_listed_paths() -> None:
    expected = {f"/home/agent/{entry}" for entry in _asset_dirs()} | {
        "/home/agent/.orchestrator",
        "/client-setup",
        "/bmad",
        "/logs",
    }

    assert {volume["target"] for volume in _volumes()} == expected


def test_every_agent_home_mount_is_a_subpath_of_the_volume() -> None:
    mounts = [volume for volume in _volumes() if volume["source"] == "agent-home"]

    assert len(mounts) == len(_asset_dirs()) + 1
    for volume in mounts:
        assert volume["target"] == f"/home/agent/{volume['volume']['subpath']}"


@pytest.mark.parametrize("target", ["/client-setup", "/bmad"])
def test_the_client_mounts_are_read_only(target: str) -> None:
    (volume,) = [v for v in _volumes() if v["target"] == target]

    assert volume["read_only"] is True


@pytest.mark.parametrize("forbidden", [".claude/settings.json", ".codex/config.toml", ".env"])
def test_the_setup_service_mounts_no_harness_config_and_no_dotenv(forbidden: str) -> None:
    for volume in _volumes():
        assert forbidden not in volume["target"]
        assert forbidden not in str(volume["source"])


def test_the_setup_service_mounts_no_work_volume() -> None:
    for volume in _volumes():
        assert volume["source"] != "work"
        assert not volume["target"].startswith("/work")


def test_the_setup_service_is_on_its_own_network_only() -> None:
    assert _setup()["networks"] == ["setup"]
    assert "setup" in _compose()["networks"]
