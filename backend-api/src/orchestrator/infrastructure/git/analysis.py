"""The `Git` port's analysis half: fetch into a scratch clone and read diffs (story 5.1).

A mixin over `SubprocessGit`'s `_run` / `_attempt`, so every command inherits the AD-5
credential path and redaction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, cast

from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry

END_OF_OPTIONS = "--"
NUL = "\0"
RAW_PATHS = ("-c", "core.quotePath=false")
KINDS = frozenset("AMDRCT")
TWO_PATH = "RC"
BINARY_COUNT = "-"


class _Runner(Protocol):
    def _run(self, *arguments: str) -> str: ...

    def _attempt(self, *arguments: str) -> str | None: ...


def _numstat(raw: str) -> tuple[NumstatEntry, ...]:
    """`--numstat -z`: `added\\tremoved\\tpath\\0`, or `added\\tremoved\\t\\0old\\0new\\0`."""
    fields = raw.split(NUL)
    entries: list[NumstatEntry] = []
    index = 0
    while index < len(fields) and fields[index]:
        added, removed, path = fields[index].split("\t", 2)
        index += 1
        if path == "":
            path = fields[index + 1]
            index += 2
        binary = added == BINARY_COUNT
        entries.append(
            NumstatEntry(
                path=path,
                added=0 if binary else int(added),
                removed=0 if binary else int(removed),
                binary=binary,
            )
        )
    return tuple(entries)


def _name_status(raw: str) -> tuple[NameStatus, ...]:
    """`--name-status -z`: `R100\\0old\\0new\\0` or `M\\0path\\0`."""
    fields = raw.split(NUL)
    entries: list[NameStatus] = []
    index = 0
    while index < len(fields) and fields[index]:
        letter = fields[index][0]
        kind = cast("Literal['A', 'M', 'D', 'R', 'C', 'T']", letter if letter in KINDS else "M")
        if letter in TWO_PATH:
            entries.append(
                NameStatus(status=kind, path=fields[index + 2], old_path=fields[index + 1])
            )
            index += 3
        else:
            entries.append(NameStatus(status=kind, path=fields[index + 1], old_path=None))
            index += 2
    return tuple(entries)


class AnalysisCommands:
    """The six analysis operations of the `Git` port."""

    def fetch(self: _Runner, remote_url: str, refs: tuple[str, ...], into: Path) -> None:
        if not (into / ".git").exists():
            into.mkdir(parents=True, exist_ok=True)
            self._run("init", "--quiet", str(into))
        self._run("-C", str(into), "fetch", "--no-tags", END_OF_OPTIONS, remote_url, *refs)

    def merge_base(self: _Runner, dest: Path, a: str, b: str) -> str | None:
        answer = self._attempt("-C", str(dest), "merge-base", END_OF_OPTIONS, a, b)
        sha = (answer or "").strip()
        return sha or None

    def diff_numstat(self: _Runner, dest: Path, base: str, head: str) -> tuple[NumstatEntry, ...]:
        raw = self._attempt(
            "-C", str(dest), *RAW_PATHS, "diff", "--numstat", "-z", "-M", base, head, END_OF_OPTIONS
        )
        return _numstat(raw) if raw else ()

    def diff_name_status(self: _Runner, dest: Path, base: str, head: str) -> tuple[NameStatus, ...]:
        raw = self._attempt(
            "-C",
            str(dest),
            *RAW_PATHS,
            "diff",
            "--name-status",
            "-z",
            "-M",
            base,
            head,
            END_OF_OPTIONS,
        )
        return _name_status(raw) if raw else ()

    def diff_text(self: _Runner, dest: Path, base: str, head: str, paths: tuple[str, ...]) -> str:
        raw = self._attempt(
            "-C",
            str(dest),
            *RAW_PATHS,
            "diff",
            "--unified=0",
            "-M",
            base,
            head,
            END_OF_OPTIONS,
            *paths,
        )
        return raw or ""

    def commits_between(self: _Runner, dest: Path, base: str, head: str) -> tuple[str, ...]:
        raw = self._attempt("-C", str(dest), "rev-list", f"{base}..{head}", END_OF_OPTIONS)
        return tuple((raw or "").split())
