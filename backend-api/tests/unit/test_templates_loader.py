"""`infrastructure/templates_loader.py` — the one reader of `TEMPLATES_DIR` (AD-2).

`application/` performs no file I/O; this module is where a shipped Template's text
actually comes off disk, as the `(name, yaml_text)` pairs `seed_shipped` takes.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.infrastructure.templates_loader import load_shipped_templates


def test_every_yaml_file_is_read_as_its_stem_and_its_text(tmp_path: Path) -> None:
    (tmp_path / "epic.yaml").write_text("name: epic\nversion: 1\nsteps: []\n")
    (tmp_path / "story.yaml").write_text("name: story\nversion: 1\nsteps: []\n")

    files = load_shipped_templates(tmp_path)

    assert dict(files) == {
        "epic": "name: epic\nversion: 1\nsteps: []\n",
        "story": "name: story\nversion: 1\nsteps: []\n",
    }


def test_files_are_sorted_by_name(tmp_path: Path) -> None:
    (tmp_path / "story.yaml").write_text("b\n")
    (tmp_path / "epic.yaml").write_text("a\n")

    files = load_shipped_templates(tmp_path)

    assert [name for name, _ in files] == ["epic", "story"]


def test_a_non_yaml_file_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "epic.yaml").write_text("name: epic\nversion: 1\nsteps: []\n")
    (tmp_path / "README.md").write_text("not a template\n")

    files = load_shipped_templates(tmp_path)

    assert [name for name, _ in files] == ["epic"]


def test_an_empty_directory_yields_nothing(tmp_path: Path) -> None:
    assert load_shipped_templates(tmp_path) == []
