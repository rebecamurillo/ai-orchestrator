"""Languages of a change as a detail-line attribute (epic 5 story 5, AC1)."""

from __future__ import annotations

from orchestrator.application.analysis.classify import FileClass
from orchestrator.application.analysis.languages import EXTENSIONS, languages_of
from orchestrator.domain.ports.git_analysis import NumstatEntry


def _class(path: str) -> FileClass:
    return "generated_or_artefact" if path.startswith("dist/") else "production"


def test_languages_are_ordered_by_added_lines_then_name() -> None:
    entries = (
        NumstatEntry("a.py", 5, 0, False),
        NumstatEntry("b.ts", 9, 0, False),
        NumstatEntry("c.tsx", 1, 0, False),
        NumstatEntry("d.go", 6, 0, False),
    )

    assert languages_of(entries, _class) == ("TypeScript", "Go", "Python")


def test_ties_break_by_name() -> None:
    entries = (NumstatEntry("a.py", 3, 0, False), NumstatEntry("b.go", 3, 0, False))

    assert languages_of(entries, _class) == ("Go", "Python")


def test_artefact_binary_removed_only_and_unknown_suffix_are_ignored() -> None:
    entries = (
        NumstatEntry("dist/a.js", 50, 0, False),
        NumstatEntry("img.PNG", 0, 0, True),
        NumstatEntry("b.py", 0, 4, False),
        NumstatEntry("notes.xyz", 8, 0, False),
        NumstatEntry("Makefile", 8, 0, False),
        NumstatEntry("UP.PY", 2, 0, False),
    )

    assert languages_of(entries, _class) == ("Python",)


def test_empty_input_holds_no_language() -> None:
    assert languages_of((), _class) == ()
    assert EXTENSIONS[".mts"] == "TypeScript"
