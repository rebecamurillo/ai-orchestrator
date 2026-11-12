"""The guide lint gate (AD-32), driven against scratch trees so it is shown to fire.

Structure only: no test here asserts the prose of a real guide page (hard rule 6).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from check_guide import main

from tests.unit.conftest import REPO_ROOT

HOST_LINE = "Local agent on the host or the user only."
RUN_LINE = "run: python3 scripts/check_guide.py --write"


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def page(title: str = "T", kind: str = "page", audience: str = "any", extra: str = "") -> str:
    return f"---\ntitle: {title}\nkind: {kind}\naudience: {audience}\n{extra}---\n"


@pytest.fixture
def guide(tmp_path: Path) -> Path:
    root = tmp_path / "guide"
    write(root, "a.md", page() + "\nBody of a.\n")
    write(root, "b/two.md", page(kind="procedure") + "\nBody of two.\n")
    return root


@pytest.fixture
def readme(tmp_path: Path) -> Path:
    return write(tmp_path, "README.md", "# Readme\n\nNo blocks.\n")


def run(guide: Path, readme: Path, *flags: str) -> int:
    return main(["--guide", str(guide), "--readme", str(readme), *flags])


def block(section: str, body: str) -> str:
    return f"<!-- guide:{section} -->\n\n{body}\n\n<!-- /guide -->\n"


def test_valid_tree_passes(guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(guide, readme) == 0
    assert capsys.readouterr().out.strip()


def test_uppercase_id_fails(guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(guide, "Upper.md", page())
    assert run(guide, readme) == 1
    assert "Upper.md" in capsys.readouterr().out


def test_bad_segment_fails(guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(guide, "a_b.md", page())
    assert run(guide, readme) == 1
    assert "a_b.md" in capsys.readouterr().out


def test_errors_directory_fails(
    guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(guide, "errors/x.md", page())
    assert run(guide, readme) == 1
    assert "errors" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text",
    [
        "\n" + page() + "body\n",  # front matter not on line 1
        "---\ntitle: T\nkind: page\naudience: any\nbody\n",  # unclosed
        "---\ntitle: T\nkind: page\naudience: any\nnot a pair\n---\n",
        page(extra="colour: red\n"),  # unknown key
        "---\nkind: page\naudience: any\n---\n",  # missing title
        "---\ntitle: T\naudience: any\n---\n",  # missing kind
        "---\ntitle: T\nkind: page\n---\n",  # missing audience
        page(title=""),  # empty title
        page(kind="essay"),
        page(audience="everyone"),
        page(extra="readme: Bad_Id\n"),
        page(extra="release: 1.0.0\n"),
    ],
)
def test_front_matter_defects_fail(
    guide: Path, readme: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    write(guide, "broken.md", text)
    assert run(guide, readme) == 1
    assert "broken.md" in capsys.readouterr().out


def test_release_key_is_named(
    guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(guide, "broken.md", page(extra="release: 1.0.0\n"))
    run(guide, readme)
    assert "release" in capsys.readouterr().out


def test_host_page_needs_the_line(
    guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = write(guide, "host.md", page(audience="host") + "\nBody.\n")
    assert run(guide, readme) == 1
    assert "host.md" in capsys.readouterr().out
    host.write_text(page(audience="host") + f"\n{HOST_LINE}\n\nBody.\n")
    assert run(guide, readme) == 0


def test_duplicate_readme_id_fails(
    guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(guide, "c.md", page(extra="readme: sec\n") + "\nC\n")
    write(guide, "d.md", page(extra="readme: sec\n") + "\nD\n")
    readme.write_text(block("sec", "C"))
    assert run(guide, readme) == 1
    assert "sec" in capsys.readouterr().out


def test_opener_naming_no_page_fails(
    guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    readme.write_text(block("ghost", "x"))
    assert run(guide, readme) == 1
    assert "ghost" in capsys.readouterr().out


@pytest.mark.parametrize("flags", [(), ("--write",)])
def test_unclosed_opener_fails_and_writes_nothing(
    guide: Path, readme: Path, flags: tuple[str, ...]
) -> None:
    write(guide, "c.md", page(extra="readme: sec\n") + "\nC\n")
    original = "<!-- guide:sec -->\n\nstale\n"
    readme.write_text(original)
    assert run(guide, readme, *flags) == 1
    assert readme.read_text() == original


@pytest.mark.parametrize("flags", [(), ("--write",)])
def test_marker_in_page_body_fails_and_writes_nothing(
    guide: Path, readme: Path, flags: tuple[str, ...]
) -> None:
    write(guide, "c.md", page(extra="readme: sec\n") + "\n<!-- /guide -->\n")
    original = block("sec", "stale")
    readme.write_text(original)
    assert run(guide, readme, *flags) == 1
    assert readme.read_text() == original


@pytest.mark.parametrize("flags", [(), ("--write",)])
def test_page_with_readme_and_no_block_fails(
    guide: Path, readme: Path, flags: tuple[str, ...]
) -> None:
    write(guide, "c.md", page(extra="readme: sec\n") + "\nC\n")
    original = readme.read_text()
    assert run(guide, readme, *flags) == 1
    assert readme.read_text() == original


def test_stale_block_fails_then_write_fixes_it(
    guide: Path, readme: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(guide, "c.md", page(extra="readme: sec\n") + "\n\nBody of c.\n\n\n")
    readme.write_text("top\n\n" + block("sec", "stale") + "\nbottom\n")
    assert run(guide, readme) == 1
    assert RUN_LINE in capsys.readouterr().out
    assert run(guide, readme, "--write") == 0
    assert readme.read_text() == "top\n\n" + block("sec", "Body of c.") + "\nbottom\n"
    assert run(guide, readme) == 0


def test_write_leaves_current_blocks_alone(guide: Path, readme: Path) -> None:
    write(guide, "c.md", page(extra="readme: sec\n") + "\nBody of c.\n")
    readme.write_text(block("sec", "Body of c."))
    before = readme.stat().st_mtime_ns
    assert run(guide, readme, "--write") == 0
    assert readme.stat().st_mtime_ns == before


def test_two_blocks_for_one_id_fail(guide: Path, readme: Path) -> None:
    write(guide, "c.md", page(extra="readme: sec\n") + "\nBody of c.\n")
    readme.write_text(block("sec", "Body of c.") + block("sec", "Body of c."))
    assert run(guide, readme) == 1


def test_missing_guide_directory_fails(tmp_path: Path, readme: Path) -> None:
    assert run(tmp_path / "nope", readme) == 1


def test_real_guide_and_readme_pass() -> None:
    assert main([]) == 0
    assert (REPO_ROOT / "guide").is_dir()
