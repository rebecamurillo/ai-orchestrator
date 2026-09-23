"""`preflight_initiative`: every refusal, before anything is written (multi-repo S6).

The pure half of AD-12's dispatch. It reads the hub's `epics.yaml`, checks the graph,
resolves each `repo` to a Repository of the Project, refuses an integration branch that is a
repository's default branch, proves each `spec_folder` exists in its own repository, and
pre-flights every would-be epic Run — then states how wide wave 0 is against the instance's
cap. Nothing here may write, and the last test in this module is what says so.
"""

from __future__ import annotations

from orchestrator.application.initiatives.plan import (
    CHECK_BRANCH,
    CHECK_REPOS,
    CHECK_SPEC,
    CHECK_TEMPLATE,
    CHECK_WAVEFRONT,
    latest_version,
)
from orchestrator.application.initiatives.validate import validate_initiative
from orchestrator.application.use_cases.dispatch_initiative import preflight_initiative
from tests.unit.application.initiatives import fixtures as fx

#: The second stored version of the fixture epic Template — what `latest` must answer.
NEWEST_EPIC_VERSION = 2


def lines_of(harness: fx.Harness, **overrides: object) -> list[tuple[str, str, str]]:
    result = preflight_initiative(harness.preflight, fx.request(**overrides))
    return [(line.status, line.check, line.text) for line in result.all_lines]


def failures(harness: fx.Harness, **overrides: object) -> list[str]:
    result = preflight_initiative(harness.preflight, fx.request(**overrides))
    return [line.text for line in result.failing]


# ── the happy path ────────────────────────────────────────────────────────────


def test_a_whole_initiative_pre_flights_with_nothing_refusing_it() -> None:
    harness = fx.Harness()

    result = preflight_initiative(harness.preflight, fx.request())

    assert result.failing == ()
    assert result.start_allowed is True
    assert result.slug == fx.SLUG


def test_the_order_is_the_topological_one_the_dispatch_would_create_in() -> None:
    harness = fx.Harness()

    assert preflight_initiative(harness.preflight, fx.request()).order == ("web-1", "api-1")


def test_each_epic_reports_where_it_lands_and_what_it_waits_for() -> None:
    harness = fx.Harness()

    epics = preflight_initiative(harness.preflight, fx.request()).epics

    assert [(e.epic_id, e.branch, e.working_branch, e.depends_on, e.checkpoint) for e in epics] == [
        ("web-1", fx.WEB_BRANCH, f"{fx.WEB_BRANCH}-web-1", (), "go_live"),
        ("api-1", fx.API_BRANCH, f"{fx.API_BRANCH}-api-1", ("web-1",), "block_merge"),
    ]


def test_the_repo_table_names_one_row_per_repository_the_initiative_touches() -> None:
    harness = fx.Harness()

    repos = preflight_initiative(harness.preflight, fx.request()).repos

    assert [(row.slug, row.branch, row.default_branch, row.remote_holds) for row in repos] == [
        ("web", fx.WEB_BRANCH, fx.MAIN, False),
        ("api", fx.API_BRANCH, fx.MAIN, False),
    ]


def test_a_repository_whose_integration_branch_the_origin_holds_says_so() -> None:
    harness = fx.Harness(refs={fx.MAIN: fx.MAIN_SHA, fx.WEB_BRANCH: fx.MAIN_SHA})

    repos = preflight_initiative(harness.preflight, fx.request()).repos

    assert [(row.slug, row.remote_holds) for row in repos] == [("web", True), ("api", False)]


def test_every_per_run_line_is_named_after_the_epic_it_belongs_to() -> None:
    """A dozen `branch` lines all reading as one Run's is the failure this prevents."""
    harness = fx.Harness()

    checks = {check for _status, check, _text in lines_of(harness)}

    assert "initiative epic web-1: branch" in checks
    assert "initiative epic api-1: branch" in checks


# ── the wavefront line ────────────────────────────────────────────────────────


def test_the_wavefront_line_states_the_width_and_the_cap() -> None:
    harness = fx.Harness(max_active_runs=2)

    result = preflight_initiative(harness.preflight, fx.request())

    assert [(line.status, line.text) for line in result.lines if line.check == CHECK_WAVEFRONT] == [
        ("ok", "initiative wavefront is 1 parallel runs; MAX_ACTIVE_RUNS is 2")
    ]


def test_a_wavefront_wider_than_the_cap_warns_but_does_not_refuse() -> None:
    wide = "\n".join(
        f"- id: e{n}\n  title: E{n}\n  repo: web\n  branch: {fx.WEB_BRANCH}\n"
        f"  spec_folder: {fx.WEB_SPEC}\n"
        for n in range(3)
    )
    harness = fx.Harness(epics=wide, specs=(fx.WEB_SPEC,), max_active_runs=2)

    result = preflight_initiative(harness.preflight, fx.request())
    wavefront = [line for line in result.lines if line.check == CHECK_WAVEFRONT]

    assert [(line.status, line.text) for line in wavefront] == [
        ("warn", "initiative wavefront is 3 parallel runs; MAX_ACTIVE_RUNS is 2")
    ]
    assert result.failing == ()


# ── every refusal ─────────────────────────────────────────────────────────────


def test_a_hub_that_does_not_hold_the_file_refuses() -> None:
    harness = fx.Harness(epics=None)

    assert failures(harness) == ["epics.yaml not found"]


def test_a_broken_graph_refuses_before_a_repository_is_even_resolved() -> None:
    cyclic = (
        "- id: a\n  title: A\n  repo: web\n  branch: develop-web\n  spec_folder: specs/a\n"
        "  depends_on: [b]\n"
        "- id: b\n  title: B\n  repo: web\n  branch: develop-web\n  spec_folder: specs/b\n"
        "  depends_on: [a]\n"
    )
    harness = fx.Harness(epics=cyclic)

    result = preflight_initiative(harness.preflight, fx.request())

    assert [line.text for line in result.failing] == ["epics depend on each other in a cycle: a, b"]
    assert result.epics == ()
    assert result.repos == ()


def test_a_repo_that_names_no_repository_of_this_project_is_refused_by_entry() -> None:
    orphan = (
        "- id: a\n  title: A\n  repo: nowhere\n  branch: develop-web\n"
        f"  spec_folder: {fx.WEB_SPEC}\n"
    )
    harness = fx.Harness(epics=orphan)

    assert failures(harness) == [
        "epic a: repo 'nowhere' is not a repository of this project",
    ]
    assert [check for _s, check, _t in lines_of(harness) if check == CHECK_REPOS]


def test_a_repo_named_by_a_clone_url_resolves_through_the_slug_rule() -> None:
    """`epics.yaml` may say `web`, `web.git` or the whole URL and mean the same row."""
    by_url = (
        "- id: a\n  title: A\n  repo: https://github.com/org/web.git\n"
        f"  branch: {fx.WEB_BRANCH}\n  spec_folder: {fx.WEB_SPEC}\n"
    )
    harness = fx.Harness(epics=by_url, specs=(fx.WEB_SPEC,))

    result = preflight_initiative(harness.preflight, fx.request())

    assert result.failing == ()
    assert result.epics[0].repository_slug == "web"


def test_an_integration_branch_equal_to_the_default_branch_is_refused() -> None:
    """`git.push` refuses it at run time (AD-14), so the merge Run could never land."""
    on_main = (
        f"- id: a\n  title: A\n  repo: web\n  branch: {fx.MAIN}\n  spec_folder: {fx.WEB_SPEC}\n"
    )
    harness = fx.Harness(epics=on_main, specs=(fx.WEB_SPEC,))

    assert "repo web: integration branch 'main' is the default branch" in failures(harness)
    assert [check for _s, check, _t in lines_of(harness) if check == CHECK_BRANCH]


def test_the_default_branch_refusal_is_reported_once_per_repository() -> None:
    twice = (
        f"- id: a\n  title: A\n  repo: web\n  branch: {fx.MAIN}\n"
        f"  spec_folder: {fx.WEB_SPEC}\n"
        f"- id: b\n  title: B\n  repo: web\n  branch: {fx.MAIN}\n"
        f"  spec_folder: {fx.WEB_SPEC}\n"
    )
    harness = fx.Harness(epics=twice, specs=(fx.WEB_SPEC,))

    assert failures(harness) == [
        "repo web: integration branch 'main' is the default branch",
    ]


def test_a_spec_folder_that_is_not_in_the_member_repository_is_refused() -> None:
    harness = fx.Harness(specs=(fx.WEB_SPEC,))

    # the epic's own `SPEC.md` line refuses too: this check is the *folder*, before the
    # Run's pre-flight looks inside it, and both belong to the same epic
    assert failures(harness) == [
        f"epic api-1: spec folder '{fx.API_SPEC}' is not in api at {fx.MAIN}",
        f"{fx.API_SPEC}: missing",
    ]
    assert [check for _s, check, _t in lines_of(harness) if check == CHECK_SPEC]


def test_a_template_the_instance_never_stored_is_refused_by_name() -> None:
    harness = fx.Harness()

    assert failures(harness, merge_template="not-stored") == [
        "template 'not-stored' is not stored",
    ]
    assert [check for _s, check, _t in lines_of(harness) if check == CHECK_TEMPLATE] == []


def test_an_unstored_template_refuses_before_any_epic_is_pre_flighted() -> None:
    harness = fx.Harness()

    result = preflight_initiative(harness.preflight, fx.request(epic_template="not-stored"))

    assert result.epics == ()
    assert [line.check for line in result.failing] == [CHECK_TEMPLATE]


# ── resolving the template version ────────────────────────────────────────────


def test_the_latest_stored_version_is_what_a_dispatch_would_use() -> None:
    """Never a hardcoded number (AD-7/AD-15): a newer stored version is the one that runs."""
    harness = fx.Harness(epic_versions=(1, 2))

    assert latest_version(harness.templates, fx.EPIC_TEMPLATE) == NEWEST_EPIC_VERSION


def test_a_name_nothing_is_stored_under_has_no_latest_version() -> None:
    harness = fx.Harness()

    assert latest_version(harness.templates, "never-saved") is None


# ── the one property the whole module rests on ────────────────────────────────


def test_pre_flighting_writes_nothing_at_all() -> None:
    harness = fx.Harness()

    preflight_initiative(harness.preflight, fx.request())

    assert harness.runs.runs == {}
    assert harness.engine.calls == []
    assert harness.git.called("push_branch") == []
    assert harness.uow.calls == []


# ── the one pass both entry points share ──────────────────────────────────────


def test_the_validation_pass_carries_what_only_the_write_half_needs() -> None:
    """`preflight_initiative` is a projection of `validate_initiative`, not a second pass:
    a dispatch that re-derived any of this could disagree with what was pre-flighted."""
    harness = fx.Harness()

    validated = validate_initiative(harness.preflight, fx.request())

    assert validated.preflight == preflight_initiative(harness.preflight, fx.request())
    assert [member.epic.id for member in validated.members] == ["web-1", "api-1"]
    assert [epic.id for epic in validated.epics] == ["web-1", "api-1"]
    assert validated.versions == {
        fx.EPIC_TEMPLATE: 1,
        fx.MERGE_TEMPLATE: 1,
        fx.GOLIVE_TEMPLATE: 1,
    }
    assert validated.hub is not None and validated.hub.id == fx.HUB_ID
    assert validated.project is not None and validated.project.id == fx.PROJECT_ID
