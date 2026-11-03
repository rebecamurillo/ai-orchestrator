"""`Workspace.read_lenient` beside a strict `read` (story 2-5 review, 2026-11-02).

Only the senior session's reply is read leniently: it is shown and never written back. Every
other reader keeps strict decoding, so a file that is read and rewritten (an answer archive,
a story file, a marker) is never altered on the way through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.workspace import Workspace
from orchestrator.infrastructure.workspace import FsWorkspace
from tests.unit.fakes.workspace import FakeWorkspace

UNDECODABLE = b"ok \xff\xfe done"


def test_a_strict_read_still_raises_on_undecodable_bytes(tmp_path: Path) -> None:
    (tmp_path / "story.md").write_bytes(UNDECODABLE)

    with pytest.raises(UnicodeDecodeError):
        FsWorkspace(str(tmp_path)).read("story.md")


def test_a_lenient_read_replaces_undecodable_bytes(tmp_path: Path) -> None:
    (tmp_path / "reply.md").write_bytes(UNDECODABLE)

    assert FsWorkspace(str(tmp_path)).read_lenient("reply.md") == "ok �� done"


def test_a_lenient_read_of_nothing_is_none(tmp_path: Path) -> None:
    assert FsWorkspace(str(tmp_path)).read_lenient("missing.md") is None


def test_both_implementations_satisfy_the_port(tmp_path: Path) -> None:
    fake = FakeWorkspace(files={"reply.md": "text"})

    assert isinstance(FsWorkspace(str(tmp_path)), Workspace)
    assert isinstance(fake, Workspace)
    assert fake.read_lenient("reply.md") == "text"
