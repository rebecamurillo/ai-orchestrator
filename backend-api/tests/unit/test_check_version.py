"""`scripts/check_version.py` — every manifest names the version in `VERSION` (plan §3).

`plugin.json` said `0.1.0` against a `1.0.0-beta` `VERSION` on 2026-09-30: that is the
drift this gate exists to refuse. The scratch trees prove it fires; the last test proves the
repository itself passes it, which is what `make lint` asserts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from check_version import (
    KIT_MANIFEST,
    PACKAGE_JSON,
    PLUGIN_JSON,
    PYPROJECT,
    compare,
    main,
    release_version,
)

from tests.unit.conftest import REPO_ROOT


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Every manifest at one version, in the shape each real file has."""
    _write(tmp_path, "VERSION", "2.0.0-rc.1\n")
    _write(
        tmp_path,
        PYPROJECT,
        '[build-system]\nrequires = ["x"]\n\n[project]\nname = "orchestrator"\n'
        'version = "2.0.0-rc.1"\n\n[tool.other]\nversion = "9.9.9"\n',
    )
    _write(tmp_path, PACKAGE_JSON, json.dumps({"name": "web-client", "version": "2.0.0-rc.1"}))
    _write(tmp_path, PLUGIN_JSON, json.dumps({"name": "orchestrator", "version": "2.0.0-rc.1"}))
    _write(tmp_path, KIT_MANIFEST, json.dumps({"kit_version": "2.0.0-rc.1", "skills": []}))
    return tmp_path


def test_a_tree_at_one_version_passes(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(tree)]) == 0
    assert capsys.readouterr().out == (
        f"version: 2.0.0-rc.1 in VERSION, {PYPROJECT}, {PACKAGE_JSON}, {PLUGIN_JSON}, "
        f"{KIT_MANIFEST}\n"
    )


@pytest.mark.parametrize("relative", [PYPROJECT, PACKAGE_JSON, PLUGIN_JSON, KIT_MANIFEST])
def test_one_drifted_manifest_fails_and_is_named(
    tree: Path, relative: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tree / relative
    path.write_text(path.read_text().replace("2.0.0-rc.1", "0.1.0"))

    assert main(["--root", str(tree)]) == 1
    err = capsys.readouterr().err
    assert relative in err
    assert "'0.1.0'" in err
    assert "2.0.0-rc.1" in err


def test_a_missing_manifest_or_field_is_drift_too(tree: Path) -> None:
    (tree / KIT_MANIFEST).write_text(json.dumps({"skills": []}))
    (tree / PLUGIN_JSON).unlink()

    drift = compare(tree)

    assert [line.split(":")[0] for line in drift] == [PLUGIN_JSON, KIT_MANIFEST]
    assert all("None" in line for line in drift)


def test_only_the_project_table_is_read_from_pyproject(tree: Path) -> None:
    """`[tool.other]` above carries `9.9.9`; a naive regex would read that one."""
    assert compare(tree) == []


@pytest.mark.parametrize("text", ["v1.0.0\n", "1.0\n", "latest\n"])
def test_a_version_file_that_is_not_a_release_number_refuses(tree: Path, text: str) -> None:
    (tree / "VERSION").write_text(text)

    with pytest.raises(SystemExit):
        release_version(tree)


def test_this_repository_passes_the_gate() -> None:
    assert compare(REPO_ROOT) == [], compare(REPO_ROOT)
