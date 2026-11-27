"""The port for asking GitHub whether a branch's pull request was merged."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PullRequests(Protocol):
    def merged(self, owner: str, repo: str, head: str) -> bool | None:
        """`True` when a pull request from `head` was merged in `owner/repo`, `False` when
        none was, `None` when GitHub could not be read."""
        ...
