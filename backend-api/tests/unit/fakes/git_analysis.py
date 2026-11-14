"""The analysis half of the one `FakeGit` (AD-18), split out only for the 400-line cap."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry


@dataclass
class AnalysisScript:
    """What the analysis methods answer; every mapping is optional."""

    fetch: dict[str, BaseException] = field(default_factory=dict)
    merge_bases: dict[tuple[str, str], str | None] = field(default_factory=dict)
    numstat: dict[tuple[str, str], tuple[NumstatEntry, ...]] = field(default_factory=dict)
    name_status: dict[tuple[str, str], tuple[NameStatus, ...]] = field(default_factory=dict)
    diff_text: dict[tuple[str, str], str] = field(default_factory=dict)
    commits: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)


class FakeAnalysisGit:
    """Mixin of `FakeGit`: six methods answered from `self.analysis`."""

    analysis: AnalysisScript

    def _record(self, method: str, arguments: tuple[Any, ...]) -> None: ...

    def fetch(self, remote_url: str, refs: tuple[str, ...], into: Path) -> None:
        self._record("fetch", (remote_url, refs, into))
        for ref in refs:
            if ref in self.analysis.fetch:
                raise self.analysis.fetch[ref]

    def merge_base(self, dest: Path, a: str, b: str) -> str | None:
        self._record("merge_base", (dest, a, b))
        script = self.analysis.merge_bases
        return script.get((a, b), script.get((b, a)))

    def diff_numstat(self, dest: Path, base: str, head: str) -> tuple[NumstatEntry, ...]:
        self._record("diff_numstat", (dest, base, head))
        return self.analysis.numstat.get((base, head), ())

    def diff_name_status(self, dest: Path, base: str, head: str) -> tuple[NameStatus, ...]:
        self._record("diff_name_status", (dest, base, head))
        return self.analysis.name_status.get((base, head), ())

    def diff_text(self, dest: Path, base: str, head: str, paths: tuple[str, ...]) -> str:
        self._record("diff_text", (dest, base, head, paths))
        return self.analysis.diff_text.get((base, head), "")

    def commits_between(self, dest: Path, base: str, head: str) -> tuple[str, ...]:
        self._record("commits_between", (dest, base, head))
        return self.analysis.commits.get((base, head), ())
