"""The guide build (AD-32): source tree + VERSION in, stamped pages, `errors/` and an index out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.api.routers import version
from orchestrator.application.findings import REGISTRY
from orchestrator.tools import build_guide


def page(title: str, kind: str = "page", extra: str = "") -> str:
    return f"---\ntitle: {title}\nkind: {kind}\naudience: any\n{extra}---\n\nBody of {title}.\n"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    (root / "b").mkdir(parents=True)
    (root / "a.md").write_text(page("A"))
    (root / "b" / "two.md").write_text(page("Two", "procedure", "readme: two\n"))
    return root


@pytest.fixture
def version_file(tmp_path: Path) -> Path:
    path = tmp_path / "VERSION"
    path.write_text("1.2.3\n")
    return path


def build(source: Path, out: Path, version_file: Path | None = None) -> int:
    args = ["--source", str(source), "--out", str(out)]
    if version_file is not None:
        args += ["--version-file", str(version_file)]
    return build_guide.main(args)


def test_pages_are_stamped_with_release_last(
    source: Path, version_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    assert build(source, out, version_file) == 0
    assert (out / "a.md").read_text() == page("A", extra="release: 1.2.3\n")
    assert (out / "b" / "two.md").read_text() == page(
        "Two", "procedure", "readme: two\nrelease: 1.2.3\n"
    )


def test_one_error_page_per_registry_code(source: Path, version_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert build(source, out, version_file) == 0
    files = sorted(p.stem for p in (out / "errors").glob("*.md"))
    assert files == sorted(REGISTRY)
    for code, entry in REGISTRY.items():
        header = f"---\ntitle: {code}\nkind: page\naudience: any\nrelease: 1.2.3\n---\n"
        text = (out / "errors" / f"{code}.md").read_text()
        assert text.startswith(f"{header}# {entry.message}\n\n{entry.explanation}")


def test_index_lists_sources_then_errors_sorted(
    source: Path, version_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    assert build(source, out, version_file) == 0
    text = (out / "guide-index.json").read_text()
    assert text.endswith("}\n")
    index = json.loads(text)
    assert index["release"] == "1.2.3"
    assert index["pages"][:2] == [
        {"id": "a", "title": "A", "kind": "page", "audience": "any"},
        {"id": "b/two", "title": "Two", "kind": "procedure", "audience": "any"},
    ]
    assert [p["id"] for p in index["pages"][2:]] == [f"errors/{c}" for c in sorted(REGISTRY)]
    assert index["pages"][2]["title"] == sorted(REGISTRY)[0]


def test_stale_file_in_out_is_removed(source: Path, version_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.md").write_text("old")
    assert build(source, out, version_file) == 0
    assert not (out / "old.md").exists()


def test_bad_id_names_file_and_leaves_out_alone(
    source: Path, version_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.md").write_text("keep")
    (source / "Bad.md").write_text(page("Bad"))
    assert build(source, out, version_file) == 1
    assert "Bad.md" in capsys.readouterr().err
    assert (out / "keep.md").exists()


@pytest.mark.parametrize(
    "text",
    [
        "no front matter\n",
        "---\ntitle: T\naudience: any\n---\n",
        "---\ntitle: T\nkind: page\naudience: any\n",
    ],
)
def test_unindexable_page_fails(
    source: Path,
    version_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
) -> None:
    (source / "broken.md").write_text(text)
    assert build(source, tmp_path / "out", version_file) == 1
    assert "broken.md" in capsys.readouterr().err


def test_out_equal_to_source_is_refused(source: Path, version_file: Path) -> None:
    assert build(source, source, version_file) == 1
    assert (source / "a.md").exists() and (source / "b" / "two.md").exists()


def test_out_parent_of_source_is_refused(source: Path, version_file: Path) -> None:
    assert build(source, source.parent, version_file) == 1
    assert (source / "a.md").exists() and (source / "b" / "two.md").exists()


def test_out_inside_source_is_refused(source: Path, version_file: Path) -> None:
    assert build(source, source / "build", version_file) == 1
    assert not (source / "build").exists()
    assert (source / "a.md").exists() and (source / "b" / "two.md").exists()


def test_out_filesystem_root_is_refused(source: Path, version_file: Path, tmp_path: Path) -> None:
    assert build(source, Path(tmp_path.anchor), version_file) == 1
    assert (source / "a.md").exists()


def test_default_version_file_is_the_version_route_file(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert build(source, out) == 0
    release = json.loads((out / "guide-index.json").read_text())["release"]
    assert release == version.VERSION_FILE.read_text().strip()
