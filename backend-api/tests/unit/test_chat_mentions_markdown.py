"""Mentions that do not name the bot: code, quotes, words, Unicode folds.

Story 3-1 review, 2026-11-02.
"""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.chat.mentions import mentions_bot, strip_mentions


@pytest.mark.parametrize(
    "text",
    [
        "```\n@orchestrator fix it\n```",
        "~~~\n@orchestrator\n~~~",
        "```\n@orchestrator never closed",
        "run `@orchestrator fix` to ask",
        "``@orchestrator``",
        "> @orchestrator fix it",
        "  > quoted @orchestrator",
        "ops@orchestrator",
        "ops.@orchestrator",
        "x-@orchestrator",
        "@@orchestrator",
        "@orche\u017ftrator",
        "@orchestrator2",
    ],
)
def test_a_mention_outside_plain_text_does_not_count(text: str) -> None:
    assert mentions_bot(text, "orchestrator") is False


def test_the_kelvin_sign_does_not_fold_to_k() -> None:
    assert mentions_bot("@\u212abot", "kbot") is False
    assert mentions_bot("@Kbot", "kbot") is True


@pytest.mark.parametrize(
    "text",
    [
        "> earlier advice\n@orchestrator fix it",
        "```\ncode\n```\n@orchestrator fix it",
        "`code` then @orchestrator",
        "(@orchestrator)",
        "hi\n@orchestrator",
    ],
)
def test_a_plain_text_mention_beside_code_or_quotes_counts(text: str) -> None:
    assert mentions_bot(text, "orchestrator") is True


def test_strip_mentions_keeps_code_and_quotes_unchanged() -> None:
    text = "> @bot said\n`@bot` @bot fix\n```\n@bot\n```"

    assert strip_mentions(text, "bot") == "> @bot said\n`@bot`  fix\n```\n@bot\n```"


def test_strip_mentions_keeps_a_mention_after_a_word() -> None:
    assert strip_mentions("ops@bot and @bot", "bot") == "ops@bot and "
