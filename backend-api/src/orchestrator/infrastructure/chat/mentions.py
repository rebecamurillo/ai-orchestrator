"""Whether a message names the bot, and the message without those names. Pure.

`@username`, ASCII case-insensitive, not preceded by a word character, `@`, `.` or `-`, not
followed by a username character, nor by a `.` and then one: `@bot.` ending a sentence names
`bot`, `@bot.ops` and `ops@bot` do not. Fenced code, inline code and `>` quote lines are
masked first, so a quoted or pasted mention never counts. An unclosed fence masks to the
end, failing closed. `re.ASCII` stops Unicode case folds (the long s, the Kelvin sign) matching.
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?(?:^[ \t]*\1[ \t]*$|\Z)", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"(`+).+?\1", re.DOTALL)
_QUOTE = re.compile(r"^[ \t]*>.*$", re.MULTILINE)


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group())


def _plain(text: str) -> str:
    """`text` with code and quotes blanked, keeping every offset and line break."""
    for pattern in (_FENCE, _INLINE_CODE, _QUOTE):
        text = pattern.sub(_blank, text)
    return text


def _mentions(text: str, username: str) -> list[re.Match[str]]:
    pattern = re.compile(
        rf"(?<![\w@.-])@{re.escape(username)}(?![a-z0-9_-])(?!\.[a-z0-9_-])",
        re.IGNORECASE | re.ASCII,
    )
    return list(pattern.finditer(_plain(text)))


def mentions_bot(text: str, username: str) -> bool:
    return bool(_mentions(text, username))


def strip_mentions(text: str, username: str) -> str:
    kept, start = [], 0
    for match in _mentions(text, username):
        kept.append(text[start : match.start()])
        start = match.end()
    kept.append(text[start:])
    return "".join(kept)
