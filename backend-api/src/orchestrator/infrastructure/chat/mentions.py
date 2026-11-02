"""Whether a message names the bot, and the message without those names. Pure.

`@username`, case-insensitive, not followed by a username character, nor by a `.` and then
one: `@bot.` ending a sentence names `bot`, `@bot.ops` names someone else.
"""

from __future__ import annotations

import re


def _mention(username: str) -> re.Pattern[str]:
    return re.compile(rf"@{re.escape(username)}(?![a-z0-9_-])(?!\.[a-z0-9_-])", re.IGNORECASE)


def mentions_bot(text: str, username: str) -> bool:
    return _mention(username).search(text) is not None


def strip_mentions(text: str, username: str) -> str:
    return _mention(username).sub("", text)
