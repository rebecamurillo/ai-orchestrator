"""`epics.yaml` as a dispatcher reads it (multi-repo initiative S6, 2026-09-23).

The operator-facing contract, which this module is the executable copy of: an entry carries
`id, title, repo, branch, spec_folder, depends_on, done_checkpoint?, checkpoint?,
baseline_sha?`, and `done_checkpoint: true` alone means `block_merge`.

Every fixture here is the test's own text, never a shipped `templates/*.yaml` or a real
project's file (hard rule 6).
"""

from __future__ import annotations

from orchestrator.application.initiatives.epics import (
    BLOCK_MERGE,
    GO_LIVE,
    Epic,
    parse_epics,
    topological_order,
    wavefront,
)

ONE = """
- id: a
  title: The A epic
  repo: web
  branch: develop
  spec_folder: specs/a
"""


def entry(name: str, *, extra: str = "") -> str:
    return (
        f"- id: {name}\n"
        f"  title: The {name} epic\n"
        f"  repo: {name}-repo\n"
        f"  branch: develop-{name}\n"
        f"  spec_folder: specs/{name}\n" + extra
    )


def texts(*entries: str) -> str:
    return "\n".join(entries)


def reasons(text: str | None) -> list[str]:
    return [line.text for line in parse_epics(text).lines if line.status == "fail"]


# ── what a good file parses to ────────────────────────────────────────────────


def test_one_entry_carries_every_declared_field() -> None:
    parsed = parse_epics(ONE)

    assert not parsed.failed
    assert parsed.epics == (
        Epic(
            id="a",
            title="The A epic",
            repo="web",
            branch="develop",
            spec_folder="specs/a",
        ),
    )


def test_depends_on_is_read_as_a_tuple_of_ids() -> None:
    text = texts(entry("a"), entry("b", extra="  depends_on: [a]\n"))

    assert parse_epics(text).epics[1].depends_on == ("a",)


def test_a_scalar_depends_on_is_read_as_the_one_id_it_names() -> None:
    """Reading `depends_on: a` as "no dependencies" would silently put the epic in wave 0."""
    text = texts(entry("a"), entry("b", extra="  depends_on: a\n"))

    assert parse_epics(text).epics[1].depends_on == ("a",)


def test_a_depends_on_that_is_neither_a_list_nor_a_string_is_still_one_id() -> None:
    text = texts(entry("1"), entry("b", extra="  depends_on: 1\n"))

    assert parse_epics(text).epics[1].depends_on == ("1",)


def test_a_baseline_sha_is_carried_and_an_absent_one_is_none() -> None:
    text = texts(entry("a", extra="  baseline_sha: deadbeef\n"), entry("b"))
    epics = parse_epics(text).epics

    assert (epics[0].baseline_sha, epics[1].baseline_sha) == ("deadbeef", None)


# ── the checkpoint contract ───────────────────────────────────────────────────


def test_done_checkpoint_true_on_its_own_means_block_merge() -> None:
    parsed = parse_epics(entry("a", extra="  done_checkpoint: true\n"))

    assert parsed.epics[0].checkpoint == BLOCK_MERGE
    assert parsed.epics[0].blocks_merge is True


def test_done_checkpoint_false_declares_no_stop_at_all() -> None:
    parsed = parse_epics(entry("a", extra="  done_checkpoint: false\n"))

    assert parsed.epics[0].checkpoint is None


def test_an_explicit_go_live_checkpoint_is_carried_as_it_stands() -> None:
    parsed = parse_epics(entry("a", extra="  checkpoint: go_live\n"))

    assert parsed.epics[0].checkpoint == GO_LIVE
    assert parsed.epics[0].goes_live is True
    assert parsed.epics[0].blocks_merge is False


def test_an_explicit_checkpoint_wins_over_the_shorthand() -> None:
    """The shorthand is defined as what `done_checkpoint: true` means *on its own*."""
    text = entry("a", extra="  done_checkpoint: true\n  checkpoint: go_live\n")

    assert parse_epics(text).epics[0].checkpoint == GO_LIVE


def test_a_checkpoint_token_the_contract_does_not_have_is_refused() -> None:
    assert reasons(entry("a", extra="  checkpoint: ship_it\n")) == [
        "epic a: checkpoint must be block_merge | go_live"
    ]


# ── everything that can be wrong with the file ────────────────────────────────


def test_a_missing_file_is_a_refusal_and_not_an_exception() -> None:
    assert reasons(None) == ["epics.yaml not found"]


def test_text_that_is_not_a_sequence_is_refused() -> None:
    assert reasons("initiative: q4\n") == ["epics.yaml is not a list of entries"]


def test_text_that_does_not_parse_at_all_is_refused() -> None:
    assert reasons("- id: [unclosed\n") == ["epics.yaml is not a list of entries"]


def test_a_sequence_of_scalars_is_refused() -> None:
    assert reasons("- a\n- b\n") == ["epics.yaml is not a list of entries"]


def test_an_empty_list_is_refused() -> None:
    assert reasons("[]\n") == ["epics.yaml holds no entries"]


def test_every_missing_field_is_named_once() -> None:
    assert reasons("- id: a\n  title: The A epic\n") == [
        "epic a: missing repo",
        "epic a: missing branch",
        "epic a: missing spec_folder",
    ]


def test_an_entry_with_no_id_is_named_by_where_it_sits() -> None:
    assert reasons("- title: nameless\n")[0].startswith("epic entry 0: missing")


def test_a_duplicate_id_is_refused_at_its_second_appearance() -> None:
    assert reasons(texts(entry("a"), entry("a"))) == ["epic a: duplicate id"]


def test_a_dependency_on_an_epic_the_file_does_not_hold_is_refused() -> None:
    text = texts(entry("a", extra="  depends_on: [nope]\n"))

    assert reasons(text) == ["epic a: depends_on names no epic: nope"]


def test_a_cycle_names_every_entry_it_swallowed() -> None:
    text = texts(
        entry("a", extra="  depends_on: [b]\n"),
        entry("b", extra="  depends_on: [a]\n"),
    )

    assert reasons(text) == ["epics depend on each other in a cycle: a, b"]


def test_two_epics_on_one_repository_may_not_name_two_branches() -> None:
    both = (
        "- id: a\n  title: A\n  repo: web\n  branch: develop\n  spec_folder: specs/a\n"
        "- id: b\n  title: B\n  repo: web\n  branch: other\n  spec_folder: specs/b\n"
    )

    assert reasons(both) == ["repo web: two integration branches declared: develop, other"]


def test_two_epics_on_one_repository_sharing_one_branch_are_fine() -> None:
    both = (
        "- id: a\n  title: A\n  repo: web\n  branch: develop\n  spec_folder: specs/a\n"
        "- id: b\n  title: B\n  repo: web\n  branch: develop\n  spec_folder: specs/b\n"
    )

    assert reasons(both) == []


def test_a_refused_file_carries_no_order_at_all() -> None:
    assert parse_epics(texts(entry("a"), entry("a"))).order == ()


# ── the order the Runs are created in ─────────────────────────────────────────


def test_the_order_is_topological_and_file_order_breaks_every_tie() -> None:
    text = texts(
        entry("a", extra="  depends_on: [c]\n"),
        entry("b"),
        entry("c"),
    )

    assert parse_epics(text).order == ("b", "c", "a")


def test_the_order_is_the_same_for_two_reads_of_one_file() -> None:
    """Determinism is what makes "created in topological order" (AD-12) checkable."""
    text = texts(entry("a"), entry("b"), entry("c"))

    assert parse_epics(text).order == parse_epics(text).order == ("a", "b", "c")


def test_a_cycle_leaves_the_walk_short_of_the_whole_list() -> None:
    cyclic = (
        Epic(id="a", title="A", repo="r", branch="b", spec_folder="s", depends_on=("b",)),
        Epic(id="b", title="B", repo="r", branch="b", spec_folder="s", depends_on=("a",)),
    )

    assert topological_order(cyclic) == ()


def test_a_dependency_on_an_unknown_id_does_not_stall_the_walk() -> None:
    """`check_graph` refuses it; the walk must still terminate rather than loop."""
    dangling = (Epic(id="a", title="A", repo="r", branch="b", spec_folder="s", depends_on=("x",)),)

    assert topological_order(dangling) == ("a",)


# ── the wavefront ─────────────────────────────────────────────────────────────


def test_the_wavefront_is_every_entry_with_no_dependency() -> None:
    text = texts(entry("a"), entry("b"), entry("c", extra="  depends_on: [a]\n"))

    assert wavefront(parse_epics(text).epics) == ("a", "b")
