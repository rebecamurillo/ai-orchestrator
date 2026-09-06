"""Loading Template YAML while remembering where every node was, and reading it back.

An error the Operator cannot find is not much better than no error, so this module is the
one place `yaml` is imported (AD-2 permits the parser; nothing else in `application/` needs
it) and every mapping and sequence it produces carries the 1-based line it began on.

`LinedMap` additionally carries `key_lines`, the line of each key's own scalar node. That
is what makes the reporting rule possible:

- an offence about a key or its scalar value is reported at `key_lines[key]`;
- an offence about a nested mapping or sequence is reported at that child's `line`.

Without `key_lines`, `version: "1"` on line 2 would be reported at the line the enclosing
document opened on, which is not where the Operator has to look.

Keys are recorded by their raw scalar text. Every key of DSL v1 is a string, so the raw
text and the constructed key are the same; a non-string key has already been refused by the
loader before this module records anything, because a key that is not hashable is not a key.

The readers below (`as_map`, `as_seq`, `child_steps`, `iter_steps`) all answer "nothing"
rather than raising when the tree is not the shape asked for. That is what lets a checker
skip a subtree it cannot read and still report every problem it can name in the same pass.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import yaml

#: Where a problem with no position of its own is reported.
FIRST_LINE = 1

#: The three key names the readers here need. The rest of the table lives in `keys.py`.
STEPS_KEY = "steps"
FOR_EACH_KEY = "for_each"
AS_KEY = "as"


class LinedMap(dict[Any, Any]):
    """A YAML mapping that remembers its own line and the line of each of its keys."""

    def __init__(self, source: Any = ()) -> None:
        super().__init__(source)
        #: 1-based line the mapping began on.
        self.line: int = FIRST_LINE
        #: 1-based line of each key's own scalar node.
        self.key_lines: dict[str, int] = {}


class LinedSeq(list[Any]):
    """A YAML sequence that remembers its own line."""

    def __init__(self, source: Any = ()) -> None:
        super().__init__(source)
        #: 1-based line the sequence began on.
        self.line: int = FIRST_LINE


class LineLoader(yaml.SafeLoader):
    """`yaml.SafeLoader`, except that every mapping and sequence records its position.

    Both overrides construct deeply. The base loader builds collections lazily so that
    recursive aliases can be resolved, and a half-built child would reach the constructor
    below with no position on it; DSL v1 has no recursive alias to lose by it.
    """

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> LinedMap:
        mapping = LinedMap(super().construct_mapping(node, deep=True))
        mapping.line = node.start_mark.line + 1
        mapping.key_lines = {key.value: key.start_mark.line + 1 for key, _ in node.value}
        return mapping

    def construct_sequence(self, node: yaml.SequenceNode, deep: bool = False) -> LinedSeq:
        sequence = LinedSeq(super().construct_sequence(node, deep=True))
        sequence.line = node.start_mark.line + 1
        return sequence


def _lined_map(loader: LineLoader, node: yaml.MappingNode) -> LinedMap:
    return loader.construct_mapping(node, deep=True)


def _lined_seq(loader: LineLoader, node: yaml.SequenceNode) -> LinedSeq:
    return loader.construct_sequence(node, deep=True)


# The default map and sequence constructors are generators that yield an empty container
# first and fill it afterwards, which would discard the subclass the overrides return.
LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _lined_map)
LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, _lined_seq)


@dataclass(frozen=True)
class LoadedYaml:
    """The document, or the line an `invalid yaml` error belongs on when there is none."""

    root: LinedMap | None
    line: int


def _error_line(error: yaml.YAMLError) -> int:
    """The line the loader stopped at, or the first line when it names no position.

    A `ReaderError` — an unacceptable character in the text — carries no mark at all, so
    the fallback is reached by real input and not only in theory.
    """
    mark = getattr(error, "problem_mark", None)
    if mark is None:
        return FIRST_LINE
    return int(mark.line) + 1


def load_with_lines(text: str) -> LoadedYaml:
    """Load one YAML document, or report the line it could not be loaded at.

    Never raises: a text that does not parse, an empty text, and a root that is not a
    mapping are all "no document", which the caller reports as `invalid yaml`.
    """
    try:
        # `LineLoader` subclasses `SafeLoader`: no arbitrary object is ever constructed.
        document = yaml.load(text, Loader=LineLoader)
    except yaml.YAMLError as error:
        return LoadedYaml(None, _error_line(error))
    if isinstance(document, LinedMap):
        return LoadedYaml(document, document.line)
    return LoadedYaml(None, FIRST_LINE)


# --- reading the tree back ---------------------------------------------------------------


def as_map(value: object) -> LinedMap | None:
    """`value` when it is a mapping, else `None`."""
    return value if isinstance(value, LinedMap) else None


def as_seq(value: object) -> LinedSeq | None:
    """`value` when it is a sequence, else `None`."""
    return value if isinstance(value, LinedSeq) else None


def line_of(node: object, default: int) -> int:
    """The line a mapping or sequence began on, or `default` for anything else."""
    return int(getattr(node, "line", default))


def key_line(mapping: LinedMap, key: str, default: int) -> int:
    """The line `key` was written on, or `default` when the mapping does not hold it."""
    return mapping.key_lines.get(key, default)


def is_for_each(node: LinedMap) -> bool:
    """True when this entry of a `steps:` list is the loop construct, not a step."""
    return FOR_EACH_KEY in node


def child_steps(node: LinedMap) -> list[LinedMap]:
    """The step mappings under this node's `steps:`, skipping every entry that is not one."""
    found: list[LinedMap] = []
    entries = as_seq(node.get(STEPS_KEY))
    if entries is None:
        return found
    for entry in entries:
        child = as_map(entry)
        if child is not None:
            found.append(child)
    return found


def iter_steps(root: LinedMap) -> Iterator[tuple[LinedMap, str | None]]:
    """Every step mapping in the file, paired with the item name in scope where it has one.

    A `for_each` construct is yielded like any other entry — the caller decides what its
    keys mean — and its own `steps` follow it, carrying its `as` name.
    """
    for node in child_steps(root):
        yield node, None
        if is_for_each(node):
            declared = node.get(AS_KEY)
            item = declared if isinstance(declared, str) else None
            for nested in child_steps(node):
                yield nested, item
