"""The root's identity in the call-cycle check is its stored number or the next one, never its
`version:` line (AD-15 amendment; retro F1 of orchestrator-client-kit, 2026-11-06)."""

from __future__ import annotations

from orchestrator.application.templates.calls import check_calls
from orchestrator.application.templates.model import CALL_CYCLE, CALLEE_NOT_FOUND
from orchestrator.domain.entities.template import TemplateCallRef, TemplateRef
from tests.unit.application.templates import parsed, reasons
from tests.unit.application.templates.conftest import TRIVIAL, version
from tests.unit.fakes.templates import FakeTemplateVersionRepository

STEP = "steps:\n  - id: c\n    uses: template\n    with:\n      name: b\n"


def text(version_line: int, *, pinned: int | None) -> str:
    pin = "" if pinned is None else f"      version: {pinned}\n"
    return f"name: a\nversion: {version_line}\n{STEP}{pin}"


def store() -> FakeTemplateVersionRepository:
    """`a@1`, `a@2`, and `b@1` pinned to `a@1`: the tree `a@3 -> b@1 -> a@1` has no cycle."""
    return FakeTemplateVersionRepository(
        [
            version("a", 1, TRIVIAL),
            version("a", 2, TRIVIAL),
            version("b", 1, TRIVIAL, TemplateRef(name="a", version=1)),
        ]
    )


def test_a_text_with_an_old_version_line_is_checked_as_the_next_version() -> None:
    """The F1 case: `version: 1` in the text once made `b@1 -> a@1` look like a cycle."""
    templates = store()

    assert reasons(check_calls(parsed(text(1, pinned=1)), templates)) == []
    assert reasons(check_calls(parsed(text(3, pinned=1)), templates)) == []


def test_an_unpinned_call_back_to_the_root_name_resolves_to_the_text_being_stored() -> None:
    """Once `a@3` is stored, `b@1 -> a` (unpinned) means `a@3`: a cycle, whatever the line."""
    templates = FakeTemplateVersionRepository(
        [
            version("a", 1, TRIVIAL),
            version("a", 2, TRIVIAL),
            version("b", 1, TRIVIAL, TemplateCallRef(name="a", version=None)),
        ]
    )

    assert reasons(check_calls(parsed(text(1, pinned=1)), templates)) == [CALL_CYCLE]


def test_a_stored_text_is_checked_as_its_own_number() -> None:
    """`a@1` re-validated as `a@1`: `b@1 -> a@1` returns to it; as a new text it does not."""
    templates = store()

    stored = check_calls(parsed(text(1, pinned=1)), templates, root_version=1)
    fresh = check_calls(parsed(text(1, pinned=1)), templates)

    assert reasons(stored) == [CALL_CYCLE]
    assert reasons(fresh) == []


def test_a_root_with_nothing_stored_is_version_one() -> None:
    """A first version calling itself pinned to 1 is a cycle; unpinned, with no store, too."""
    templates = FakeTemplateVersionRepository()
    own = "name: a\nversion: 1\nsteps:\n  - id: c\n    uses: template\n    with:\n      name: a\n"

    assert reasons(check_calls(parsed(own + "      version: 1\n"), templates)) == [CALL_CYCLE]
    assert reasons(check_calls(parsed(own), templates)) == [CALL_CYCLE]
    assert reasons(check_calls(parsed(own + "      version: 2\n"), templates)) == [CALLEE_NOT_FOUND]


def test_a_root_with_no_name_resolves_unpinned_calls_from_the_store_alone() -> None:
    templates = store()
    nameless = "version: 1\nsteps:\n  - id: c\n    uses: template\n    with:\n      name: a\n"

    assert reasons(check_calls(parsed(nameless), templates)) == []
