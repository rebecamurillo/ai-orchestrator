"""`is_valid_glob` — the pure rule a stored `test_globs` entry must satisfy.

Reused by a later story's protected-path check; asserted here on its own. The schema
layer's `errors[]` wiring (which index a bad glob names) is asserted in
`tests/unit/test_repository_schemas.py`.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.rules.globs import GLOB_REASON, is_valid_glob


@pytest.mark.parametrize(
    "glob",
    ["tests/**", "**/*.test.*", "**/*.spec.*", "e2e/**", "a/b/*.py", "README.md"],
)
def test_an_ordinary_glob_is_valid(glob: str) -> None:
    assert is_valid_glob(glob)


@pytest.mark.parametrize("glob", ["/abs/**", "/", "/tests/**"])
def test_a_leading_slash_is_refused(glob: str) -> None:
    assert not is_valid_glob(glob)


@pytest.mark.parametrize("glob", ["../x", "a/../b", "..", "tests/../secrets/**", "a/b/.."])
def test_a_parent_segment_is_refused(glob: str) -> None:
    assert not is_valid_glob(glob)


def test_an_empty_glob_is_refused() -> None:
    assert not is_valid_glob("")


def test_the_reason_is_stated_once_so_every_layer_says_the_same_thing() -> None:
    assert GLOB_REASON == "no leading `/`, no `..` segment"
