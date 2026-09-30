"""`infrastructure/kit.py` — the one reader of `KIT_DIR` (AD-2, agent-delivery-kit plan §1)."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from orchestrator.infrastructure.kit import archive, install_script, kit_version


def _kit(root: Path) -> Path:
    (root / "install.sh").write_text("#!/usr/bin/env bash\necho kit\n")
    (root / "manifest.json").write_text(json.dumps({"kit_version": "1.2.3", "skills": ["a"]}))
    (root / "skills" / "a").mkdir(parents=True)
    (root / "skills" / "a" / "SKILL.md").write_text("# a\n")
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text("{}")
    return root


def test_the_installer_text_is_read_verbatim(tmp_path: Path) -> None:
    assert install_script(_kit(tmp_path)) == "#!/usr/bin/env bash\necho kit\n"


def test_an_absent_kit_answers_none_everywhere(tmp_path: Path) -> None:
    assert install_script(tmp_path) is None
    assert archive(tmp_path) is None
    assert kit_version(tmp_path) is None


def test_the_version_comes_from_the_manifest(tmp_path: Path) -> None:
    assert kit_version(_kit(tmp_path)) == "1.2.3"


def test_a_manifest_without_a_usable_version_answers_none(tmp_path: Path) -> None:
    _kit(tmp_path)
    for body in ('{"kit_version": ""}', '{"kit_version": 3}', "[]", "not json"):
        (tmp_path / "manifest.json").write_text(body)
        assert kit_version(tmp_path) is None, body


def test_the_archive_holds_every_file_relative_to_the_kit_root_in_name_order(
    tmp_path: Path,
) -> None:
    data = archive(_kit(tmp_path))

    assert data is not None
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        names = tar.getnames()
        skill = tar.extractfile("skills/a/SKILL.md")
        assert skill is not None and skill.read() == b"# a\n"
    assert names == sorted(names)
    assert set(names) == {
        ".claude-plugin/plugin.json",
        "install.sh",
        "manifest.json",
        "skills/a/SKILL.md",
    }
