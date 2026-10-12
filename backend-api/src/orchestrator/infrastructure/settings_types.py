"""Shipped defaults and the comma-separated readers `settings.py` declares its fields with.

Split out of `settings.py` to keep that module under the 400-line limit; `Settings` is still
the only reader of the environment.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import NoDecode

#: Shipped defaults for the three list- and mapping-shaped settings, spelled here rather
#: than inline so the field declarations stay one line each. Each equals its `.env.example`
#: value, which `test_settings_defaults.py` proves rather than trusts.
READINESS_MODELS_DEFAULT = {
    "claude": "claude-sonnet-4-6",
    "codex": "gpt-5.4",
    "local": "local-coder",
}
LOCAL_MODELS_DEFAULT = ["local-coder", "local-general"]
#: `Bash` whole, not a list of command families (Operator decision D-1, 2026-10-12): the
#: container is the sandbox, and an instance that lists families parks `blocked` on the first
#: package manager or test runner it forgot — a park no answer can clear. `git push` stays
#: denied by the adapter's own disallow list, which this value cannot widen.
CLAUDE_ALLOWED_TOOLS_DEFAULT = [
    "Task",
    "Bash",
    "Edit",
    "Read",
    "Write",
    "Glob",
    "Grep",
    "Skill",
    "ToolSearch",
]


def split_csv(value: object) -> object:
    """Read a comma-separated environment value as a list, leaving lists alone."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CommaSeparated = Annotated[
    list[str],
    NoDecode,
    BeforeValidator(split_csv),
    Field(min_length=1),
]


def split_pairs(value: object) -> object:
    """Read `name=value,name=value` as a mapping, leaving mappings alone.

    `split_csv`'s shape for a setting that binds something *per* name. Every failure is
    raised here rather than tolerated, because each of them is a name that would silently
    bind nothing: a pair with no `=`, no name, or no value.
    """
    if not isinstance(value, str):
        return value
    pairs: dict[str, str] = {}
    for item in value.split(","):
        if not item.strip():
            continue
        name, separator, bound = item.partition("=")
        if not separator or not name.strip() or not bound.strip():
            raise ValueError(f"{item.strip()!r} is not a `name=value` pair")
        pairs[name.strip()] = bound.strip()
    return pairs


CommaSeparatedPairs = Annotated[
    dict[str, str],
    NoDecode,
    BeforeValidator(split_pairs),
    Field(min_length=1),
]
