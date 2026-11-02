"""Whether a message names the bot, and the message without those names. Pure.

`@username`, ASCII case-insensitive, not preceded by a word character, `@`, `.` or `-`, not
followed by a username character, nor by a `.` and then one: `@bot.` ending a sentence names
`bot`, `@bot.ops` and `ops@bot` do not. Fenced code, inline code and `>` quote lines are
masked first, so a quoted or pasted mention never counts. An unclosed fence masks to the
end, failing closed. `re.ASCII` stops Unicode case folds (the long s, the Kelvin sign) matching.

Slack (`slack_*`) names a user as `<@ID>` or `<@ID|label>`, matched exactly and case-sensitively,
after the same masking. Slack stores a typed `>` as `&gt;`, so a line opening with either is
a quote, and a line opening with `>>>` (`&gt;&gt;&gt;`) quotes everything after it.
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?(?:^[ \t]*\1[ \t]*$|\Z)", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"(`+).+?\1", re.DOTALL)
_QUOTE = re.compile(r"^[ \t]*>.*$", re.MULTILINE)
_SLACK_QUOTE = re.compile(r"^[ \t]*(?:(?:>>>|&gt;&gt;&gt;)[\s\S]*\Z|(?:>|&gt;).*$)", re.MULTILINE)


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group())


def _plain(text: str, quote: re.Pattern[str] = _QUOTE) -> str:
    """`text` with code and quotes blanked, keeping every offset and line break."""
    for pattern in (_FENCE, _INLINE_CODE, quote):
        text = pattern.sub(_blank, text)
    return text


def _without(text: str, matches: list[re.Match[str]]) -> str:
    kept, start = [], 0
    for match in matches:
        kept.append(text[start : match.start()])
        start = match.end()
    kept.append(text[start:])
    return "".join(kept)


def _slack_mentions(text: str, user_id: str) -> list[re.Match[str]]:
    pattern = re.compile(rf"<@{re.escape(user_id)}(?:\|[^<>]*)?>")
    return list(pattern.finditer(_plain(text, _SLACK_QUOTE)))


def slack_mentions_bot(text: str, user_id: str) -> bool:
    return bool(_slack_mentions(text, user_id))


def slack_strip_mentions(text: str, user_id: str) -> str:
    return _without(text, _slack_mentions(text, user_id))


def _mentions(text: str, username: str) -> list[re.Match[str]]:
    pattern = re.compile(
        rf"(?<![\w@.-])@{re.escape(username)}(?![a-z0-9_-])(?!\.[a-z0-9_-])",
        re.IGNORECASE | re.ASCII,
    )
    return list(pattern.finditer(_plain(text)))


def mentions_bot(text: str, username: str) -> bool:
    return bool(_mentions(text, username))


def strip_mentions(text: str, username: str) -> str:
    return _without(text, _mentions(text, username))
