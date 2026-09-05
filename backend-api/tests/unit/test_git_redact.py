"""The one function every path out of the git adapter goes through (AD-5, hard rule 5).

git puts a URL in almost every message it writes, and a credential that ever reached a URL
would reach a stored `clone_check.output`, a log line and a response body with it. The
adapter never puts the token in a URL — but "never" is a claim about code that will keep
changing, and this function is what makes it a property of the output instead.

The empty case matters as much as the replacing one: an instance with no `GITHUB_TOKEN`
would otherwise have every character of every message replaced by `***`.
"""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.git.redact import REDACTION, redact

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"


def test_the_token_is_replaced_where_it_appears() -> None:
    assert redact(f"fatal: {TOKEN} refused", TOKEN) == f"fatal: {REDACTION} refused"


def test_every_occurrence_is_replaced_and_not_only_the_first() -> None:
    assert redact(f"{TOKEN} {TOKEN}", TOKEN) == f"{REDACTION} {REDACTION}"


def test_the_token_is_replaced_inside_a_url() -> None:
    """The shape a credential-in-URL leak actually takes."""
    said = f"remote: https://x-access-token:{TOKEN}@github.com/org/repo.git"

    assert TOKEN not in redact(said, TOKEN)
    assert REDACTION in redact(said, TOKEN)


def test_text_that_does_not_hold_the_token_is_untouched() -> None:
    said = "fatal: repository 'https://github.com/org/repo.git' not found"

    assert redact(said, TOKEN) == said


@pytest.mark.parametrize("text", ["", "fatal: nope", "***"])
def test_an_empty_token_replaces_nothing(text: str) -> None:
    """`"".replace("", "***")` inserts the marker between every character."""
    assert redact(text, "") == text


def test_the_marker_says_nothing_about_the_value_it_replaced() -> None:
    """A marker carrying a length or a prefix would be a hint at the secret."""
    assert REDACTION == "***"
