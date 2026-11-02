"""`mentions_bot` and `strip_mentions`: one match for "this text names the bot" (story 3-1)."""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.chat.mentions import mentions_bot, strip_mentions


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("thanks @Bot.", True),
        ("@bot.ops", False),
        ("@botty", False),
        ("@bot", True),
        ("@BOT fix it", True),
        ("(@bot)", True),
        ("@bot, then", True),
        ("@bot\nnext line", True),
        ("@bot-ops", False),
        ("@bot_ops", False),
        ("@bot9", False),
        ("@bot.Ops", False),
        ("@bot..", True),
        ("bot without the at", False),
        ("", False),
    ],
)
def test_mentions_bot(text: str, expected: bool) -> None:
    assert mentions_bot(text, "bot") is expected


def test_a_username_with_a_dot_is_matched_literally() -> None:
    assert mentions_bot("@bot.ops please", "bot.ops") is True
    assert mentions_bot("@botxops please", "bot.ops") is False


def test_strip_mentions_removes_every_match_and_nothing_else() -> None:
    assert strip_mentions("@bot fix @botty and @Bot.", "bot") == " fix @botty and ."


def test_strip_mentions_leaves_text_without_a_match_unchanged() -> None:
    text = "  @bot.ops and @botty\r\n  "

    assert strip_mentions(text, "bot") == text
