"""`slack_mentions_bot` and `slack_strip_mentions`: the bot named as `<@BOTID>` (story 3-2).

Slack stores a mention as the user's id in angle brackets, sometimes with a `|label`. The id is
matched exactly, and code and quotes are masked first, as for Mattermost, so a quoted or
pasted mention never counts. Slack escapes a typed `>` as `&gt;`, so both quote forms count.
"""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.chat.mentions import slack_mentions_bot, slack_strip_mentions

BOT = "U0BOT"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<@U0BOT> fix it", True),
        ("thanks <@U0BOT>", True),
        ("<@U0BOT|orchestrator> go", True),
        ("<@U0BOTX> no", False),
        ("<@u0bot> case matters", False),
        ("<@U0BO> shorter", False),
        ("@U0BOT without brackets", False),
        ("@orchestrator by name", False),
        ("`<@U0BOT>` in code", False),
        ("```\n<@U0BOT>\n```", False),
        ("&gt; <@U0BOT> quoted", False),
        ("> <@U0BOT> quoted", False),
        ("&gt; quoted\n<@U0BOT> then asked", True),
        ("&lt;@U0BOT&gt; escaped text", False),
        ("", False),
    ],
)
def test_slack_mentions_bot(text: str, expected: bool) -> None:
    assert slack_mentions_bot(text, BOT) is expected


@pytest.mark.parametrize(
    ("text", "body"),
    [
        ("<@U0BOT> fix it", " fix it"),
        ("<@U0BOT|bot> fix <@U0BOT> it", " fix  it"),
        ("<@U7> and <@U0BOT> please", "<@U7> and  please"),
        ("`<@U0BOT>` <@U0BOT> go", "`<@U0BOT>`  go"),
        ("&gt; <@U0BOT>\n<@U0BOT> yes", "&gt; <@U0BOT>\n yes"),
        ("no mention", "no mention"),
    ],
)
def test_slack_strip_mentions_removes_exactly_the_counted_mentions(text: str, body: str) -> None:
    assert slack_strip_mentions(text, BOT) == body


def test_an_id_with_regex_characters_is_matched_literally() -> None:
    assert slack_mentions_bot("<@U.+> hi", "U.+") is True
    assert slack_mentions_bot("<@UXX> hi", "U.+") is False
