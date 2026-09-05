"""The DSL v1 suite (AD-15), and the one reader of its fixture files.

Every rejection the story's matrix names has a fixture under `fixtures/`, named by the
reason it must produce, so a test reads as "this file, that reason, that line" and the file
itself is the example a reader checks the rule against.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.templates.lines import LinedMap, load_with_lines

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    """The text of one fixture file, by name without the `.yaml` suffix."""
    return (FIXTURES / f"{name}.yaml").read_text()


def parsed(text: str) -> LinedMap:
    """The lined root mapping of `text` — the input every checker takes."""
    loaded = load_with_lines(text)
    assert loaded.root is not None, text
    return loaded.root


def reasons(errors: object) -> list[str]:
    """Just the reasons, in order, for a test that is about which rules fired."""
    return [record.reason for record in errors]  # type: ignore[attr-defined]
