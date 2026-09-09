"""What UJ-3's own scenarios need from `fixtures/gates-repo/` (6.8, SPEC CAP-8).

`tests/unit/test_gates_fixture.py` pins what every Epic 6 suite depends on and is untouched.
This module pins the four facts only scenario C depends on, for the same reason that one
exists: these files are *input* to a gate that takes minutes and needs Docker, so a typo here
would otherwise surface as an unexplained timeout in `make e2e` instead of as a failed unit
test naming the file.

The chain being pinned, in order: a quality gate whose file lives inside the spec folder
(so the Operator's repair can be a real `PUT /runs/{id}/files`), story 3's first dispatch
deleting exactly that file (so `verify` fails), and story 3's redispatch leaving something
uncommitted (so the post-skip commit guard really commits under the rewritten message).
"""

from __future__ import annotations

import yaml

from orchestrator.infrastructure.harness.fake import scenario as scenarios
from tests.unit.conftest import REPO_ROOT

FIXTURE = REPO_ROOT / "fixtures" / "gates-repo"
SPEC_FOLDER = "specs/gates"

#: The gate file scenario C deletes and the Operator puts back, and the script reading it.
SPEC_GATE_FILE = f"{SPEC_FOLDER}/GATE_OK"
SPEC_GATE_SCRIPT = "check-spec.sh"

STORY_3 = FIXTURE / ".fake-harness" / "3"


def test_the_spec_scoped_quality_gate_passes_on_an_untouched_clone() -> None:
    """`epic@1`'s `baseline` row runs it before the first story, with `on_fail: fail` — so
    the committed value has to pass, exactly as the root `GATE_OK` does for `check.sh`."""
    assert (FIXTURE / SPEC_GATE_FILE).read_text().strip() == "1"
    assert SPEC_GATE_FILE in (FIXTURE / SPEC_GATE_SCRIPT).read_text()


def test_the_spec_scoped_gate_file_is_inside_the_folder_a_put_may_write() -> None:
    """`run_files.py::_within_spec_folder` is the whole reason this second gate exists: the
    root `GATE_OK` is outside every Run's scope folder and could never be repaired."""
    assert SPEC_GATE_FILE.startswith(f"{SPEC_FOLDER}/")
    assert (FIXTURE / SPEC_FOLDER / "stories.yaml").is_file()


def test_the_gate_file_is_not_a_list_file_the_plan_pinned() -> None:
    """A `PUT` is refused 409 for a path in `run.plan_refs` — the two list files. The gate
    file must not be one of them, or the Operator's repair could never land."""
    lists = {f"{SPEC_FOLDER}/stories.yaml", f"{SPEC_FOLDER}/epics.yaml"}

    assert SPEC_GATE_FILE not in lists


def test_story_threes_first_dispatch_deletes_the_spec_scoped_gate_file() -> None:
    """Scenario C's first failure. The root `GATE_OK` is untouched, which is what keeps
    every `sh check.sh` suite walking story 3 to a green `verify`."""
    first = scenarios.load(STORY_3 / "default.yaml")

    assert first.delete == (SPEC_GATE_FILE,)
    assert first.commit is True
    assert "GATE_OK" not in [spec.path for spec in first.files]


def test_story_threes_redispatch_leaves_the_commit_guard_something_to_commit() -> None:
    """`commit:` absent on purpose: `signal_effects.py::SKIP_MESSAGE` is only observable on
    the branch if the skipped frame's commit guard actually has changes to commit."""
    second = scenarios.load(STORY_3 / "attempt-2.yaml")

    assert second.commit is False
    assert second.story_file is not None
    assert "status: done" in second.story_file.content
    assert [spec.path for spec in second.files] == ["SHIP_NOTES.md"]


def test_story_three_still_carries_the_done_checkpoint_the_skip_takes_with_it() -> None:
    """The frame's own checkpoint row is what `_skip_frame` marks `skipped by operator`,
    and it exists only because `stories.yaml` says `done_checkpoint: true` for story 3."""
    stories = yaml.safe_load((FIXTURE / SPEC_FOLDER / "stories.yaml").read_text())

    assert stories[2]["id"] == "3"
    assert stories[2]["done_checkpoint"] is True
