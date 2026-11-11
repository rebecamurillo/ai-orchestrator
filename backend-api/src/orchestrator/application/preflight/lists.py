"""The pre-flight checks that need a second look at a list file: `epics.yaml` (line 4),
`stories.yaml` (line 5), `SPEC.md` (line 7) and existing story files (line 10) — FR-8.

Each is read again directly through `Git.read_file` / `Git.list_files`, at the commit
`plan_run` already recorded for it (`Plan.plan_refs`), rather than through
`application/templates/lists.py`: that module's `read_list` takes the walker's own `Frame`,
which pre-flight has no reason to construct. By the time any of these run, `plan_run` has
already succeeded, so the entries are already known-valid — this module only renders them.
"""

from __future__ import annotations

from collections.abc import Mapping

from orchestrator.application.dto import DEFAULT_HARNESS
from orchestrator.application.preflight.checks import Context, list_error_target, run_label
from orchestrator.application.preflight.model import (
    CHECK_CONCURRENT_REPO,
    CHECK_EPICS_YAML,
    CHECK_EXISTING_STORY_FILES,
    CHECK_INSTALLED_SKILL,
    CHECK_SPEC_MD,
    CHECK_STORIES_YAML,
    CHECK_TEST_GLOBS,
    Line,
)
from orchestrator.application.steps import AGENT_KIND
from orchestrator.application.templates.lines import load_sequence, load_with_lines
from orchestrator.application.templates.lists import stories_directory
from orchestrator.application.templates.plan_model import ON_FAIL_KEY, REDISPATCH_TARGET_SEQ
from orchestrator.application.templates.table import CONSULT_KEY
from orchestrator.domain.entities.run import Run
from orchestrator.domain.values import PlannedRow

EPICS_FILENAME = "epics.yaml"
STORIES_FILENAME = "stories.yaml"
SPEC_FILENAME = "SPEC.md"
STATUS_KEY = "status"
#: The Run input a Template binds its epic list's own folder under (same key as
#: `walk_frame.py`); a plan that does not name one leaves the list's entries bare.
INITIATIVE_FOLDER_KEY = "initiative_folder"
FRONTMATTER_FENCE = "---"
STORY_SUFFIX = ".md"
PATH_SEPARATOR = "/"

Entry = Mapping[str, object]


def _list_paths(ctx: Context, filename: str) -> tuple[str, ...]:
    """Every path in the plan's own `plan_refs` whose basename is `filename`."""
    if ctx.plan is None:
        return ()
    return tuple(
        path for path in ctx.plan.plan_refs if path.rpartition(PATH_SEPARATOR)[2] == filename
    )


def _entries(ctx: Context, path: str) -> tuple[Entry, ...]:
    """One list file's entries, re-read at the commit `plan_run` recorded for it."""
    if ctx.plan is None:
        return ()
    ref = ctx.plan.plan_refs.get(path)
    if ref is None:
        return ()
    text = ctx.git.read_file(ctx.base_dir, ref, path)
    if text is None:
        return ()
    sequence = load_sequence(text)
    if sequence is None:
        return ()
    return tuple(entry for entry in sequence if isinstance(entry, Mapping))


def epics_entries(ctx: Context) -> tuple[Entry, ...]:
    """Every `epics.yaml` entry the plan read (`()` unless the plan reads one at all)."""
    entries: list[Entry] = []
    for path in _list_paths(ctx, EPICS_FILENAME):
        entries.extend(_entries(ctx, path))
    return tuple(entries)


def epics_yaml_line(ctx: Context) -> Line | None:
    """Line 4: plans that read an epics list only. `None` means "does not apply", not
    "skip" — `Context.reads_epics_list` is the fact, not a Template's name (Operator
    decision 2026-09-30: no template name hardcoded in product code)."""
    if not ctx.reads_epics_list:
        return None
    if list_error_target(ctx) == CHECK_EPICS_YAML:
        assert ctx.plan_error is not None  # `list_error_target` only names this when set
        return Line(CHECK_EPICS_YAML, "fail", str(ctx.plan_error))
    entries = epics_entries(ctx)
    if not entries:
        return None
    branches = _joined(entries, "branch")
    folders = _joined(entries, "spec_folder")
    text = f"{len(entries)} epics · branches {branches} · spec folders {folders}"
    return Line(CHECK_EPICS_YAML, "ok", text)


def _joined(entries: tuple[Entry, ...], field: str) -> str:
    values = sorted({str(entry[field]) for entry in entries if entry.get(field)})
    return ", ".join(values)


def stories_yaml_lines(ctx: Context) -> tuple[list[Line], dict[str, tuple[str, ...]]]:
    """Line 5, one per `stories.yaml` the plan read; and each file's ids, for line 10."""
    if list_error_target(ctx) == CHECK_STORIES_YAML:
        assert ctx.plan_error is not None
        return [Line(CHECK_STORIES_YAML, "fail", str(ctx.plan_error))], {}
    lines: list[Line] = []
    ids_by_path: dict[str, tuple[str, ...]] = {}
    for path in _list_paths(ctx, STORIES_FILENAME):
        entries = _entries(ctx, path)
        ids_by_path[path] = tuple(str(entry["id"]) for entry in entries if entry.get("id"))
        lines.append(Line(CHECK_STORIES_YAML, "ok", f"{path} · {len(entries)} stories"))
    return lines, ids_by_path


def spec_folders(ctx: Context) -> tuple[str, ...]:
    """Every spec folder the plan touches: each epic's, or the request's own single one.

    An epic's `spec_folder` is relative to the Initiative folder (PRD §3), the same
    composition a Template looping over an epics list declares — so each entry is prefixed
    with the request's `initiative_folder` when one is typed; without it the bare entries
    stand.
    """
    if ctx.reads_epics_list:
        entries = epics_entries(ctx)
        if not entries:
            return ()
        prefix = ctx.req.inputs.get(INITIATIVE_FOLDER_KEY)
        head = f"{prefix}{PATH_SEPARATOR}" if isinstance(prefix, str) and prefix else ""
        return tuple(
            f"{head}{folder}" for folder in _joined(entries, "spec_folder").split(", ") if folder
        )
    folder = ctx.req.inputs.get("spec_folder")
    return (folder,) if isinstance(folder, str) and folder else ()


def spec_md_lines(ctx: Context) -> list[Line]:
    """Line 7: one per spec folder the plan touches — `found` or `fail · missing`."""
    if ctx.plan is None:
        return []
    lines: list[Line] = []
    for folder in spec_folders(ctx):
        path = f"{folder}{PATH_SEPARATOR}{SPEC_FILENAME}"
        text = ctx.git.read_file(ctx.base_dir, ctx.plan.plan_ref, path)
        if text is not None:
            lines.append(Line(CHECK_SPEC_MD, "ok", f"{folder}: found"))
        else:
            lines.append(Line(CHECK_SPEC_MD, "fail", f"{folder}: missing"))
    return lines


def existing_story_files_line(ctx: Context, ids_by_path: dict[str, tuple[str, ...]]) -> Line:
    """Line 10: every Story file already on the branch, and its `status`, or `ok · none`."""
    if ctx.plan is None:
        return Line(CHECK_EXISTING_STORY_FILES, "skip", "plan not built")
    found: list[str] = []
    for path, ids in ids_by_path.items():
        found.extend(_existing_for(ctx, path, ids))
    if not found:
        return Line(CHECK_EXISTING_STORY_FILES, "ok", "none")
    return Line(CHECK_EXISTING_STORY_FILES, "warn", "; ".join(found))


def _existing_for(ctx: Context, list_path: str, ids: tuple[str, ...]) -> list[str]:
    assert ctx.plan is not None
    ref = ctx.plan.plan_refs.get(list_path, ctx.plan.plan_ref)
    directory = stories_directory(list_path)
    listing = ctx.git.list_files(ctx.base_dir, ref, directory)
    found: list[str] = []
    for story_id in ids:
        for match in _story_matches(listing, directory, story_id):
            text = ctx.git.read_file(ctx.base_dir, ref, match)
            status = _story_status(text) if text is not None else None
            found.append(f"{match} · {status or 'unknown'}")
    return found


def _story_matches(listing: tuple[str, ...], directory: str, story_id: str) -> list[str]:
    opening = f"{directory}{PATH_SEPARATOR}{story_id}-"
    return [
        path
        for path in listing
        if path.startswith(opening)
        and path.endswith(STORY_SUFFIX)
        and PATH_SEPARATOR not in path[len(opening) :]
    ]


def _story_status(text: str) -> str | None:
    """The `status:` frontmatter field of a story file, or `None` when it has none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_FENCE:
            loaded = load_with_lines("\n".join(lines[1:index]))
            value = loaded.root.get(STATUS_KEY) if loaded.root is not None else None
            return str(value) if value is not None else None
    return None


def skill_fix(skill: str, bmad_choice: str | None) -> str:
    """The command that restores a missing skill: the BMAD installer for a `bmad-` skill the
    operator removed, the setup otherwise."""
    if skill.startswith("bmad-") and bmad_choice == "removed":
        return "./install.sh bmad install"
    return "./install.sh setup"


def installed_skill_lines(ctx: Context) -> list[Line]:
    """One `fail` line per missing (skill, harness) pair and per harness whose catalog cannot
    be read, a single `ok` line when every pair is present.

    Each skill is checked on the harness of the row that names it: the Run's for an agent
    row, the consult's own `harness` when the consult declares one.  Returns an empty list
    when the plan is `None` or names no skill.  Lives here rather than in `checks.py` on
    line count alone (the 400-line module limit).  A planned `consult` block's skill is a
    named skill too (AD-22).

    An unreadable catalog is a `fail` naming every skill it could not verify: a harness
    handed a skill name it cannot resolve does not fail, it improvises.  A `Context` with
    no catalog port at all `skip`s — only a unit test's context is ever that.
    """
    if ctx.plan is None:
        return []
    run_harness = ctx.req.harness or DEFAULT_HARNESS
    by_seq = {row.seq: _row_harness(row, run_harness) for row in ctx.plan.rows}
    pairs: list[tuple[str, str]] = []
    for plan_row in ctx.plan.rows:
        for pair in _row_skills(plan_row, by_seq):
            if pair not in pairs:
                pairs.append(pair)
    if not pairs:
        return []
    if ctx.skill_catalog is None:
        return [Line(CHECK_INSTALLED_SKILL, "skip", "no catalog configured")]
    installed: dict[str, frozenset[str] | None] = {}
    for _, harness in pairs:
        if harness not in installed:
            installed[harness] = ctx.skill_catalog.installed_skills(harness)
    lines = _unreadable_lines(pairs, installed) + [
        Line(
            CHECK_INSTALLED_SKILL,
            "fail",
            f"not installed: {skill} on {harness}",
            fix=skill_fix(skill, ctx.bmad_choice),
        )
        for skill, harness in pairs
        if (names := installed[harness]) is not None and skill not in names
    ]
    return lines or [Line(CHECK_INSTALLED_SKILL, "ok", "ok")]


def _unreadable_lines(
    pairs: list[tuple[str, str]], installed: Mapping[str, frozenset[str] | None]
) -> list[Line]:
    """One `fail` per harness whose catalog could not be read, in first-seen order."""
    return [
        Line(
            CHECK_INSTALLED_SKILL,
            "fail",
            "catalog unavailable on "
            f"{harness}: cannot verify {', '.join(s for s, h in pairs if h == harness)}",
            fix="./install.sh setup",
        )
        for harness, names in installed.items()
        if names is None
    ]


def _row_harness(plan_row: PlannedRow, run_harness: str) -> str:
    return str(plan_row.with_resolved.get("harness") or "").strip() or run_harness


def _row_skills(plan_row: PlannedRow, by_seq: Mapping[int, str]) -> list[tuple[str, str]]:
    """The (skill, harness) pairs one planned row dispatches: an `agent` row's own skill and
    its consult's, and the consult a `run` row's `on_fail` redispatch declares for
    `verify_failed` (story 1-6).  A consult runs on its own `harness`, else on the harness
    of the row it runs in — for the `on_fail` consult that is the redispatch target, not the
    `run` row (`steps/agent_consult.py::_consult` reads the dispatched row's)."""
    resolved = plan_row.with_resolved
    row_harness = by_seq[plan_row.seq]
    found: list[tuple[object, str]] = []
    if plan_row.kind == AGENT_KIND:
        found.append((resolved.get("skill"), row_harness))
        found.extend(_consult_skill(resolved.get(CONSULT_KEY), row_harness))
    route = resolved.get(ON_FAIL_KEY)
    if isinstance(route, Mapping):
        target = by_seq.get(int(route.get(REDISPATCH_TARGET_SEQ) or 0), row_harness)
        found.extend(_consult_skill(route.get(CONSULT_KEY), target))
    return [(skill, harness) for skill, harness in found if isinstance(skill, str) and skill]


def _consult_skill(block: object, fallback: str) -> list[tuple[object, str]]:
    if not isinstance(block, Mapping):
        return []
    return [(block.get("skill"), str(block.get("harness") or "").strip() or fallback)]


def _new_partition_branch(ctx: Context) -> str | None:
    """The declared branch the new Run would partition by, or `None` when unknown.

    Mirrors `create_run._partition_branch`: `plan.branches` maps declared → created, so
    its first key is the declared name.  When the plan is absent (form still incomplete),
    falls back to `req.base_branch` so the check can still skip same-branch holders.
    """
    if ctx.plan is not None and ctx.plan.branches:
        return next(iter(ctx.plan.branches))
    return ctx.req.base_branch


def _concurrent_run_text(run: Run) -> str:
    """`run_label(run)` plus `· {folder}` when the holder named a spec or initiative folder."""
    label = run_label(run)
    folder = run.inputs.get("spec_folder") or run.inputs.get("initiative_folder")
    if folder:
        return f"{label} · {folder}"
    return label


def concurrent_repo_lines(ctx: Context) -> list[Line]:
    """One `warn` line per non-terminal Run on the same Repository with a *different*
    non-`None` `partition_branch` (story 5-2).

    Same-branch holders are excluded: `branch_lines` already emits a `fail` for them, and
    showing both a `fail` and a `warn` for the same branch is redundant.  Holders with
    `partition_branch=None` (pre-story-5-1 runs) are excluded because they carry no branch
    information and cannot cause the kind of merge conflict this check warns about.
    """
    if ctx.repository is None:
        return []
    new_branch = _new_partition_branch(ctx)
    lines: list[Line] = []
    for run in ctx.runs.list_by_repository_non_terminal(ctx.repository.id):
        if run.partition_branch is None:
            continue
        if new_branch is not None and run.partition_branch == new_branch:
            continue
        lines.append(Line(CHECK_CONCURRENT_REPO, "warn", _concurrent_run_text(run)))
    return lines


#: AD-17 freezes the tests `repository.test_globs` matches; with none, nothing is protected.
NO_TEST_GLOBS = "no test_globs: no existing test is frozen"


def test_globs_line(ctx: Context) -> Line | None:
    """A `warn` when the chosen repository freezes no test, else nothing; never a refusal."""
    if ctx.repository is None or ctx.repository.test_globs:
        return None
    return Line(check=CHECK_TEST_GLOBS, status="warn", text=NO_TEST_GLOBS)
