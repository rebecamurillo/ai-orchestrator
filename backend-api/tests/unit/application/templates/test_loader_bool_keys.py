"""A plain bool-looking key loads as its text, and nothing else changes (story 1-4 review,
2026-11-02). The loader is shared with Story-file frontmatter and list files, so an
explicitly tagged key and every value — an alias of such a key included — keep YAML's
own reading."""

from __future__ import annotations

from orchestrator.application.templates.lines import load_with_lines


def loaded(text: str) -> dict[object, object]:
    result = load_with_lines(text)
    assert result.root is not None, text
    return dict(result.root)


def test_an_explicitly_tagged_key_stays_a_bool() -> None:
    assert loaded("!!bool on: 1\nyes: 2\n") == {True: 1, "yes": 2}


def test_an_alias_of_a_bool_looking_key_used_as_a_value_stays_a_bool() -> None:
    assert loaded("? &x on\n: 1\nb: *x\n") == {"on": 1, "b": True}


def test_an_anchored_plain_key_is_still_text() -> None:
    assert loaded("&k off: 1\n") == {"off": 1}


def test_an_unhashable_key_is_still_no_document() -> None:
    assert load_with_lines("? [a, b]\n: 1\n").root is None


def test_a_merge_key_still_merges() -> None:
    assert loaded("base: &b {x: 1}\nchild:\n  <<: *b\n  on: 2\n")["child"] == {"x": 1, "on": 2}


def test_quoted_and_plain_values_are_untouched() -> None:
    assert loaded("a: on\nb: 'on'\nc: no\n") == {"a": True, "b": "on", "c": False}
