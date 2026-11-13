"""The languages a change is written in, for a repository's detail line.

A detail-line attribute, not a metric: it is stored in the summary and never rated.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath

from orchestrator.application.analysis.classify import FileClass
from orchestrator.domain.ports.git_analysis import NumstatEntry

EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".astro": "Astro",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".css": "CSS",
    ".scss": "SCSS",
    ".html": "HTML",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".swift": "Swift",
    ".sh": "Shell",
    ".sql": "SQL",
}


def languages_of(
    numstat: Sequence[NumstatEntry], class_of: Callable[[str], FileClass]
) -> tuple[str, ...]:
    """By summed added lines, largest first, then by name; artefacts and unknown suffixes out."""
    added: Counter[str] = Counter()
    for entry in numstat:
        if entry.binary or entry.added <= 0 or class_of(entry.path) == "generated_or_artefact":
            continue
        language = EXTENSIONS.get(PurePosixPath(entry.path).suffix.lower())
        if language is not None:
            added[language] += entry.added
    return tuple(sorted(added, key=lambda name: (-added[name], name)))
