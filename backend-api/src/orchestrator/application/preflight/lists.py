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

from orchestrator.application.preflight.checks import Context, list_error_target
from orchestrator.application.preflight.model import (
    CHECK_EPICS_YAML,
    CHECK_EXISTING_STORY_FILES,
    CHECK_SPEC_MD,
    CHECK_STORIES_YAML,
    Line,
)
from orchestrator.application.templates.lines import load_sequence, load_with_lines
from orchestrator.application.templates.lists import stories_directory

EPICS_FILENAME = "epics.yaml"
STORIES_FILENAME = "stories.yaml"
SPEC_FILENAME = "SPEC.md"
STATUS_KEY = "status"
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
    """Every `epics.yaml` entry the plan read (`()` unless this is an initiative Run)."""
    entries: list[Entry] = []
    for path in _list_paths(ctx, EPICS_FILENAME):
        entries.extend(_entries(ctx, path))
    return tuple(entries)


def epics_yaml_line(ctx: Context) -> Line | None:
    """Line 4: initiative only. `None` means "does not apply", not "skip"."""
    if not ctx.is_initiative:
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
    """Every spec folder the plan touches: each epic's, or the request's own single one."""
    if ctx.is_initiative:
        return (
            tuple(_joined(epics_entries(ctx), "spec_folder").split(", "))
            if epics_entries(ctx)
            else ()
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
