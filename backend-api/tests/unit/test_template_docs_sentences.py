"""The documentation says the same few things in the same words (story 8, 2026-11-06, D7, D14).

This pins documentation, not template content (hard rule 6 does not apply): the owner and an
agent customising a workflow are told that the folder's file wins, and the README states the
rules the reload answer relies on. Line wrapping is ignored. The kit skills' two pairs read the
guide pages instead (epic 3 story 3, 2026-11-12, AD-33).
"""

from __future__ import annotations

import pytest

from tests.unit.conftest import REPO_ROOT

PRECEDENCE = (
    "When the folder holds a file named after a template, edit the file: a version saved on the "
    "instance is superseded by the file's content as the next version at the next reload or "
    "start-up, and stays listed."
)
VERSION_REQUIRED = (
    "`version:` is required by the parser; for a folder file its value is ignored. The instance "
    "assigns the next number and the reload answer reports it in `stored[].version`. Leave the "
    "line as it is (`version: 1` is fine)."
)
VERSION_HASH = "Changing only the `version:` line changes the file's hash and stores a new version."
VERSION_WEB = "A web UI save still has to say the next number."
SPEC_FOLDER = "the one name agent steps read implicitly"
SKIP_SIGNAL = (
    "A loop named neither `epics` nor `stories` gets no skip signal of its own; an outer loop "
    "must be called `epics` for *Skip epic* to stop at its boundary."
)
REMOVED = (
    "A name is listed in `not_in_folder` only when the folder once stored a version of it; a "
    "file that never stored one (its content always equalled the latest version, or it was "
    "always refused) is not listed after removal."
)
SHIPPED_OVERRIDE = (
    "A shipped name listed in `not_in_folder` with `overrides_shipped: true` keeps running your "
    "last folder version. To go back to the shipped text, copy the image's "
    "`/app/templates/agent-smoke.yaml` (for that name) into the folder, or save it in the web UI. "
    "A copy in the folder then wins over every later shipped version of that name (the folder "
    "pass compares a file with the latest version only), so after an upgrade remove the copy or "
    "refresh it from the new image; a web save does not have that effect."
)

README = "templates/README.md"

PAIRS = [
    (README, PRECEDENCE),
    ("deploy/README.md", PRECEDENCE),
    ("guide/workflows/customize.md", PRECEDENCE),
    ("guide/host/template-folder.md", PRECEDENCE),
    (README, VERSION_REQUIRED),
    (README, VERSION_HASH),
    (README, VERSION_WEB),
    (README, SPEC_FOLDER),
    (README, SKIP_SIGNAL),
    (README, REMOVED),
    (README, SHIPPED_OVERRIDE),
]


@pytest.mark.parametrize(("path", "sentence"), PAIRS, ids=[f"{p}:{s[:30]}" for p, s in PAIRS])
def test_the_file_carries_the_sentence(path: str, sentence: str) -> None:
    assert sentence in " ".join((REPO_ROOT / path).read_text().split())
