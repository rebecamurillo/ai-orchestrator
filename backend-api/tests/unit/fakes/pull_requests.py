"""In-memory `PullRequests` — the one fake for that port (AD-18). Reuse it; do not write another."""

from __future__ import annotations

from collections.abc import Iterable


class FakePullRequests:
    """Answers from a dict keyed `(owner, repo, head)`; an unknown key is `False`."""

    def __init__(
        self,
        answers: dict[tuple[str, str, str], bool] | None = None,
        unreadable: Iterable[tuple[str, str, str]] = (),
    ) -> None:
        self.answers = dict(answers or {})
        self.unreadable = set(unreadable)
        self.calls: list[tuple[str, str, str]] = []

    def merged(self, owner: str, repo: str, head: str) -> bool | None:
        key = (owner, repo, head)
        self.calls.append(key)
        if key in self.unreadable:
            return None
        return self.answers.get(key, False)
