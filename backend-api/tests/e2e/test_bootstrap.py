"""The bootstrap contract and the kit's retirement against the running stack (initiative
orchestrator-instance-guide, epic 3: SPEC CAP-1, CAP-2, CAP-3; member AD-33; C1).

The unit suite proves the version answer over a test client and the installer over a `curl`
stub. What only the running image settles: the C1 answer the image serves over REST and over
MCP; the three guide addresses in that answer resolve on this instance; the kit the image
ships holds the bootstrap and no retired skill or `bin/`; and the served installer, piped into
bash as the connect page documents, fetches that kit from this instance, writes a bootstrap
free of the instance's release and of the token, and probes this instance's version.

The installer runs in `tmp_path`, with `HOME`, `CODEX_HOME` and `XDG_CONFIG_HOME` there too,
so it never touches the runner's own harness configuration. No assertion reads page prose or
pins which pages ship (member hard rule 6).
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import httpx
import pytest

from tests.e2e.test_agent_connection import INDEX_LINK, Mcp

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401

VERSION = "/api/v1/version"
INSTALL = "/api/v1/kit/install.sh"
ARCHIVE = "/api/v1/kit/archive"
LLMS = "/llms.txt"

#: C1, frozen from the release that ships it (AD-33).
CONTRACT = 1
GUIDE = {"index": "/llms.txt", "page_url": "/guide/{id}.md", "resource": "guide://{id}"}

TOKEN_VAR = "ORCHESTRATOR_TOKEN"
INSTALL_TIMEOUT_SECONDS = 60.0


@pytest.fixture
def mcp(authenticated: httpx.Client) -> Mcp:
    return Mcp(authenticated)


@pytest.fixture(scope="module")
def answer(stack: str, bearer: dict[str, str]) -> dict[str, object]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=10.0) as client:
        response = client.get(VERSION)
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, object] = response.json()
    return body


def _members(data: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        return [m.name.removeprefix("./") for m in archive.getmembers() if m.isfile()]


# --- CAP-1: the C1 version answer ---------------------------------------------------------


def test_version_is_behind_the_bearer(client: httpx.Client) -> None:
    assert client.get(VERSION).status_code == HTTP_UNAUTHORIZED


def test_version_answers_the_frozen_contract(answer: dict[str, object]) -> None:
    """C1: `app_version`, `bootstrap_contract` 1, the three guide addresses; `kit_version` null."""
    assert isinstance(answer["app_version"], str)
    assert answer["app_version"]
    assert answer["bootstrap_contract"] == CONTRACT
    assert answer["guide"] == GUIDE
    assert "kit_version" in answer
    assert answer["kit_version"] is None


def test_the_version_tool_answers_what_the_route_answers(
    mcp: Mcp, answer: dict[str, object]
) -> None:
    assert mcp.call("version") == answer


def test_the_version_tool_says_to_report_a_contract_difference_and_continue(mcp: Mcp) -> None:
    (tool,) = [t for t in mcp.rpc("tools/list")["tools"] if t["name"] == "version"]
    description = tool["description"]
    assert "refusal-bootstrap-contract" in description
    assert "continue" in description
    assert not re.search(r"stop\b[^.]*\b(mismatch|disagree)", description)


def test_read_guide_takes_one_optional_id(mcp: Mcp) -> None:
    """C1: `read_guide(id?)`."""
    (tool,) = [t for t in mcp.rpc("tools/list")["tools"] if t["name"] == "read_guide"]
    schema = tool["inputSchema"]
    assert set(schema["properties"]) == {"id"}
    assert "id" not in schema.get("required", [])


def test_the_guide_addresses_in_the_answer_resolve_on_this_instance(
    answer: dict[str, object], client: httpx.Client, mcp: Mcp
) -> None:
    """What the bootstrap tells an agent to follow is what this instance serves."""
    guide = answer["guide"]
    assert isinstance(guide, dict)
    index = client.get(guide["index"])
    assert index.status_code == HTTP_OK, index.text
    ids = [m["id"] for line in index.text.splitlines() if (m := INDEX_LINK.match(line))]
    assert ids, "the index lists no page"
    page_id = ids[0]
    page = client.get(guide["page_url"].format(id=page_id))
    assert page.status_code == HTTP_OK, page.text
    contents = mcp.rpc("resources/read", {"uri": guide["resource"].format(id=page_id)})["contents"]
    assert contents[0]["text"] == page.text


def test_the_contract_difference_page_is_served(client: httpx.Client) -> None:
    response = client.get("/guide/errors/refusal-bootstrap-contract.md")
    assert response.status_code == HTTP_OK, response.text


# --- CAP-3: the kit the image ships -------------------------------------------------------


def test_the_kit_routes_are_behind_the_bearer(client: httpx.Client) -> None:
    assert client.get(INSTALL).status_code == HTTP_UNAUTHORIZED
    assert client.get(ARCHIVE).status_code == HTTP_UNAUTHORIZED


def test_the_served_kit_holds_the_bootstrap_and_no_retired_file(
    authenticated: httpx.Client,
) -> None:
    """AC-4: no `skills/`, no `bin/`; the template, the installer and the three MCP templates."""
    response = authenticated.get(ARCHIVE)
    assert response.status_code == HTTP_OK, response.text
    members = _members(response.content)
    assert not [m for m in members if m.startswith(("skills/", "bin/"))], members
    assert {
        "bootstrap/SKILL.md.tmpl",
        "install.sh",
        "mcp/claude.json",
        "mcp/codex.toml",
        "mcp/opencode.json",
    } <= set(members)


def test_the_served_installer_is_the_one_in_the_archive(authenticated: httpx.Client) -> None:
    script = authenticated.get(INSTALL)
    assert script.status_code == HTTP_OK, script.text
    with tarfile.open(fileobj=io.BytesIO(authenticated.get(ARCHIVE).content), mode="r:gz") as tar:
        names = {m.name.removeprefix("./"): m for m in tar.getmembers()}
        packed = tar.extractfile(names["install.sh"])
        assert packed is not None
        assert packed.read().decode() == script.text


# --- CAP-2: the documented piped call, against this instance ------------------------------


def _require_tools() -> None:
    missing = [tool for tool in ("bash", "curl", "tar", "python3") if shutil.which(tool) is None]
    if missing:
        pytest.fail(f"the piped installer needs {', '.join(missing)} on the e2e runner's PATH")


def test_the_piped_installer_bootstraps_a_project_from_this_instance(
    authenticated: httpx.Client, stack: str, token: str, tmp_path: Path, answer: dict[str, object]
) -> None:
    """AC-1 and AC-3 over the wire: kit fetched, MCP configured, no token and no release."""
    _require_tools()
    script = authenticated.get(INSTALL)
    assert script.status_code == HTTP_OK, script.text

    project = tmp_path / "project"
    home, codex_home, xdg = tmp_path / "home", tmp_path / "codex", tmp_path / "xdg"
    for d in (project, home, codex_home, xdg):
        d.mkdir()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "CODEX_HOME": str(codex_home),
        "XDG_CONFIG_HOME": str(xdg),
        TOKEN_VAR: token,
    }
    done = subprocess.run(
        [
            "bash",
            "-s",
            "--",
            "--harness",
            "all",
            "--base-url",
            f"{stack}/",
            "--project",
            str(project),
        ],
        input=script.text,
        env=env,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=INSTALL_TIMEOUT_SECONDS,
        check=False,
    )
    output = done.stdout + done.stderr
    assert done.returncode == 0, output.replace(token, "<token>")
    assert token not in output
    assert f"{stack}{ARCHIVE}" in output
    assert f"bootstrap_contract {CONTRACT}" in output

    mcp_url = f"{stack}/mcp"
    claude = json.loads((project / ".mcp.json").read_text())["mcpServers"]["orchestrator"]
    assert claude["url"] == mcp_url
    assert claude["headers"]["Authorization"] == f"Bearer ${{{TOKEN_VAR}}}"
    codex = tomllib.loads((codex_home / "config.toml").read_text())["mcp_servers"]["orchestrator"]
    assert codex == {"url": mcp_url, "bearer_token_env_var": TOKEN_VAR}
    opencode = json.loads((project / "opencode.json").read_text())["mcp"]["orchestrator"]
    assert opencode["url"] == mcp_url
    assert opencode["headers"]["Authorization"] == f"Bearer {{env:{TOKEN_VAR}}}"

    marker = json.loads((project / ".orchestrator" / "bootstrap.json").read_text())
    assert marker["bootstrap_contract"] == CONTRACT
    assert marker["base_url"] == stack

    for rel in (".claude/skills/orchestrator", ".agents/skills/orchestrator"):
        assert sorted(p.name for p in (project / rel).iterdir()) == ["SKILL.md"]

    release = answer["app_version"]
    assert isinstance(release, str)
    written = [p for d in (project, home, codex_home, xdg) for p in d.rglob("*") if p.is_file()]
    assert written
    for path in written:
        text = path.read_text()
        assert token not in text, path
        assert release not in text, path
        assert "@@" not in text, path
