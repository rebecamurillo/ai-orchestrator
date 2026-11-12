"""The README's role table names every path of the deploy folder with its role
(epic 3 story 5, SPEC CAP-5; AD-31: a deployment test, never run by a Run)."""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from tests.unit.conftest import REPO_ROOT

DEPLOY = REPO_ROOT / "deploy"
README = DEPLOY / "README.md"
GENERATOR = REPO_ROOT / "scripts" / "product_manifest.py"
ADMIN_SKILL = DEPLOY / "kit" / "skills" / "orchestrator-admin"
ROLE_HEADING = "## Which file is whose"
MIGRATION_HEADING = "## Migrating an existing folder"
PLATFORM_HEADING = "## Getting an LLM platform"
MIN_CELLS = 2
FORBIDDEN = (
    "--with-platform",
    "--no-platform",
    "platform-up",
    "start --with-platform",
    "llm-platform/sync-env.sh",
)


def _manifest_paths(tmp_path: Path) -> dict[str, str]:
    root = tmp_path / "app"
    shutil.copytree(DEPLOY, root / "deploy")
    shipped = root / "deploy" / "templates" / "shipped"
    shipped.mkdir(parents=True)
    for template in (REPO_ROOT / "templates").glob("*.yaml"):
        shutil.copy2(template, shipped / template.name)
    (root / "VERSION").write_text("1.2.3\n")
    result = subprocess.run(
        [sys.executable, "-I", str(GENERATOR), str(root / "deploy"), str(root / "VERSION")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return {e["path"]: e["role"] for e in json.loads(result.stdout)["files"]}


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = re.search(r"^## ", text[start + len(heading) :], re.M)
    return text[start : start + len(heading) + nxt.start()] if nxt else text[start:]


def _rows() -> list[tuple[list[str], str]]:
    rows = []
    for line in _section(README.read_text(), ROLE_HEADING).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) < MIN_CELLS or set(cells[0]) <= {"-", " "}:
            continue
        paths = re.findall(r"`([^`]+)`", cells[0])
        rows.append((paths or [cells[0]], cells[1]))
    return rows


def _covers(pattern: str, path: str) -> bool:
    if pattern == path or (pattern.endswith("/") and path.startswith(pattern)):
        return True
    if "*" not in pattern:
        return False
    left, right = pattern.split("/"), path.split("/")
    return len(left) == len(right) and all(
        fnmatch.fnmatch(r, p) for p, r in zip(left, right, strict=True)
    )


def _roles_covering(path: str) -> set[str]:
    return {role for paths, role in _rows() for p in paths if _covers(p, path)}


def test_every_manifest_path_is_in_the_table_with_the_manifests_role(tmp_path: Path) -> None:
    for path, role in _manifest_paths(tmp_path).items():
        assert _roles_covering(path) == {role}, path


def test_the_manifest_itself_and_the_client_paths_have_their_rows() -> None:
    assert _roles_covering("product-files.json") == {"product"}
    for client in ("setup/example.sh", "templates/mine.yaml", ".env"):
        assert _roles_covering(client) == {"client"}, client
    for written in ("backups/", "logs/", "diagnostics/", ".upgrade/"):
        assert _roles_covering(written) != set(), written


def test_a_row_says_anything_else_you_add_is_yours() -> None:
    assert any("anything else you add" in paths[0] and role == "client" for paths, role in _rows())


def test_a_wildcard_row_never_covers_a_deeper_path() -> None:
    assert not _covers("templates/*.yaml", "templates/shipped/x.yaml")
    assert _covers("templates/shipped/*.yaml", "templates/shipped/x.yaml")


def test_the_migration_section_names_each_step_in_order() -> None:
    text = _section(README.read_text(), MIGRATION_HEADING)
    steps = [
        "new, empty folder",
        "`.env`, `templates/*.yaml` and `backups/`",
        "`IMAGE_TAG`",
        "`LANGFUSE_OPENCODE_PLUGIN_VERSION`",
        "`COMPOSE_PROJECT_NAME`",
        "old folder's name",
        "Stop the old stack, from the old folder",
        "Start from the new folder",
        "`llm-platform/` folder in the old folder stays where it is",
        "Never run an older `install.sh upgrade` across this release",
    ]
    positions = [text.index(step) for step in steps]
    assert positions == sorted(positions)
    for pin in (
        "BMAD_VERSION",
        "DBOS_APPLICATION_VERSION",
        "CLAUDE_CODE_VERSION",
        "CODEX_VERSION",
        "OPENCODE_VERSION",
    ):
        assert pin in text


def test_no_document_names_a_platform_command() -> None:
    files = [README, *ADMIN_SKILL.rglob("*.md")]
    for file in files:
        text = file.read_text()
        for word in FORBIDDEN:
            assert word not in text, f"{file.name}: {word}"


def test_the_platform_section_points_at_the_starter_and_disclaims_it() -> None:
    text = _section(README.read_text(), PLATFORM_HEADING)

    assert "https://github.com/rebecamurillo/ai-orchestrator" in text
    assert "deploy/llm-platform/" in text
    assert "v<VERSION>" in text
    assert "neither ships nor manages" in text
