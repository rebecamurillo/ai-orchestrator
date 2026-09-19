"""What the `fake` harness is told to do: the scenario file, and which one is next (AR-14).

A scenario is the whole behaviour of one dispatch, written as YAML in the *target*
repository rather than in this one — `{worktree}/.fake-harness/{story_id}/attempt-{k}.yaml`,
falling back to `default.yaml` for a story that scripts every attempt the same way. Keeping
it in the fixture repository is what makes the loop testable end to end: a test changes what
"the agent" does by committing a file, not by patching a double into a running stack.

```yaml
story_file: { slug: notify, content: "---\\nstatus: blocked\\n---\\n..." }
files: [{ path: src/notify.py, content: "..." }]
delete: [GATE_OK]
commit: true
exit_code: 0
sleep_seconds: 0
echo_prompt: true
usage: { tokens_in: 120, tokens_out: 340, cost_usd: "0.02" }
```

**`delete:` is the one effect `files:` cannot express** (6.8). A scenario that has to make a
repository's own quality gate *fail* has to remove the file the gate reads: writing it with
different contents is a different scenario, and every gate command is free to decide what
"present" means. Paths are relative to the worktree and are dropped, not refused, when they
are absolute or carry a `..` part — a scenario is test input inside a Run's worktree, and a
delete that could reach outside it is a mistake this harness declines to carry out rather
than a traceback in a durable step.

**Nothing here raises.** A missing file, YAML that does not load, a document that is not a
mapping, a key of the wrong type: every one of them is the field's default, because a
scenario is test *input* and a malformed one must fail the assertion the test actually makes
— "the Run parked `blocked`" — rather than a traceback inside a durable step. The empty
scenario writes nothing and exits 0, which routes exactly as a real agent that wrote no
Story file would.

**The attempt counter lives outside the worktree, and it has to.** `k` is "how many times
this story has been dispatched in this worktree", and the obvious place to keep it — a file
under `.fake-harness/` — would be committed by the next attempt's WIP commit
(`application/steps/agent.py::_wip_commit`), would dirty the whole-tree commit guard, and
would show up in the protected-path check's uncommitted set. It is kept under `WORK_DIR`
instead, keyed by a digest of the worktree path, so it survives a backend restart (which a
process-local counter would not) and touches nothing a Run reads.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath

import yaml

from orchestrator.domain.ports.harness import HarnessUsage

#: The fixed sentence `application/steps/agent.py::DISPATCH` writes, read back for the two
#: facts a scenario is keyed by. Matched rather than imported: `application/` is a layer this
#: one may import, but the coupling worth having is to the *text the harness receives*, which
#: is what a real adapter would have to parse too. `test_fake_harness_scenarios.py` asserts
#: this pattern against `DISPATCH` itself, so a change to the sentence fails there.
DISPATCH_PATTERN = re.compile(r"spec folder (?P<spec_folder>.+?), story id (?P<story_id>.+?)\.")

#: Where the scenarios live, relative to the worktree the dispatch runs in.
SCENARIO_DIRECTORY = ".fake-harness/{story_id}"
ATTEMPT_FILE = "attempt-{k}.yaml"
DEFAULT_FILE = "default.yaml"

#: Where the per-story dispatch counter lives, under `WORK_DIR` and never in the worktree.
COUNTER_DIRECTORY = "fake-harness"
#: Counter filename for a dispatch whose prompt names no story id (see `counter_path`).
NO_STORY = "-no-story-"
#: Enough of a digest to separate two worktrees, short enough to read in a directory listing.
DIGEST_LENGTH = 16

ENCODING = "utf-8"


@dataclass(frozen=True)
class FileSpec:
    """One file the scenario writes, at a path relative to the worktree root."""

    path: str
    content: str = ""


@dataclass(frozen=True)
class StoryFileSpec:
    """The Story file this dispatch leaves at `{spec_folder}/stories/{story_id}-{slug}.md`."""

    slug: str
    content: str = ""


@dataclass(frozen=True)
class Dispatch:
    """The two facts the prompt carries, or empty strings when it carries neither."""

    spec_folder: str = ""
    story_id: str = ""


@dataclass(frozen=True)
class Scenario:
    """One dispatch's whole scripted behaviour. Every field has a do-nothing default."""

    story_file: StoryFileSpec | None = None
    files: tuple[FileSpec, ...] = field(default_factory=tuple)
    #: Worktree-relative paths removed before anything is written (6.8) — how a scenario
    #: makes the repository's own quality gate fail.
    delete: tuple[str, ...] = field(default_factory=tuple)
    #: `git add -A && git commit` as `fake <fake@local>` after the files are written.
    commit: bool = False
    exit_code: int = 0
    #: How long the process runs — what a timeout scenario turns up past `timeout_min`.
    sleep_seconds: float = 0.0
    #: Append the prompt to the Story file, so a test can assert what the agent was asked.
    echo_prompt: bool = False
    usage: HarnessUsage | None = None


def dispatch_of(prompt: str) -> Dispatch:
    """The spec folder and story id the dispatch sentence names, or empty strings."""
    found = DISPATCH_PATTERN.search(prompt)
    if found is None:
        return Dispatch()
    return Dispatch(spec_folder=found["spec_folder"], story_id=found["story_id"])


def scenario_path(cwd: Path, story_id: str, k: int) -> Path:
    """The k-th scenario for this story, or the story's `default.yaml` when it has none."""
    directory = cwd / SCENARIO_DIRECTORY.format(story_id=story_id)
    numbered = directory / ATTEMPT_FILE.format(k=k)
    return numbered if numbered.is_file() else directory / DEFAULT_FILE


def load(path: Path) -> Scenario:
    """The scenario at `path`, or the empty one for anything that cannot be read as one."""
    try:
        text = path.read_text(encoding=ENCODING)
    except OSError:
        return Scenario()
    return parse(text)


def parse(text: str) -> Scenario:
    """A scenario document as this harness reads it. Never raises; see the module docstring."""
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return Scenario()
    if not isinstance(loaded, dict):
        return Scenario()
    return Scenario(
        story_file=_story_file(loaded.get("story_file")),
        files=_files(loaded.get("files")),
        delete=_deletes(loaded.get("delete")),
        commit=loaded.get("commit") is True,
        exit_code=_int(loaded.get("exit_code"), 0),
        sleep_seconds=_float(loaded.get("sleep_seconds"), 0.0),
        echo_prompt=loaded.get("echo_prompt") is True,
        usage=_usage(loaded.get("usage")),
    )


def next_attempt(work_dir: Path, cwd: Path, story_id: str) -> int:
    """Which dispatch of this story in this worktree this is, counting from 1.

    Reads the count, writes it back incremented, and answers the new value — so two
    dispatches of one story never read the same scenario file. A counter that cannot be
    written (a read-only `WORK_DIR`) still answers, and answers `1`: a scenario set that
    scripts every attempt through `default.yaml` keeps working, which is the common case.
    """
    counter = counter_path(work_dir, cwd, story_id)
    current = 0
    try:
        current = int(counter.read_text(encoding=ENCODING).strip())
    except OSError, ValueError:
        current = 0
    following = current + 1
    try:
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text(str(following), encoding=ENCODING)
    except OSError:
        return following
    return following


def counter_path(work_dir: Path, cwd: Path, story_id: str) -> Path:
    """`{WORK_DIR}/fake-harness/{digest of the worktree}/{story_id}` — never in the worktree.

    An empty story id (a dispatch whose prompt names no story — `epic@1`'s spec-gate,
    gen-e2e and retro rows) files under `{NO_STORY}` rather than under the bare digest:
    `digest / ""` IS the digest directory, and writing the counter there would replace the
    directory every per-story counter lives in.
    """
    digest = hashlib.sha256(str(cwd).encode(ENCODING)).hexdigest()[:DIGEST_LENGTH]
    return work_dir / COUNTER_DIRECTORY / digest / (story_id or NO_STORY)


def _story_file(value: object) -> StoryFileSpec | None:
    if not isinstance(value, dict):
        return None
    slug = value.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        return None
    return StoryFileSpec(slug=slug.strip(), content=_text(value.get("content")))


def _files(value: object) -> tuple[FileSpec, ...]:
    if not isinstance(value, list):
        return ()
    kept = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str) and path.strip():
            kept.append(FileSpec(path=path.strip(), content=_text(entry.get("content"))))
    return tuple(kept)


def _deletes(value: object) -> tuple[str, ...]:
    """The `delete:` list, keeping only worktree-relative paths (6.8).

    Same shape as `_files`, and the same silence: a document that is not a list, an entry
    that is not a string, a blank one, and one that escapes the worktree are all dropped.
    """
    if not isinstance(value, list):
        return ()
    kept = [
        entry.strip()
        for entry in value
        if isinstance(entry, str) and entry.strip() and not _escapes(entry.strip())
    ]
    return tuple(kept)


def _escapes(path: str) -> bool:
    """Whether `path` could reach outside the worktree it is resolved against.

    `application/use_cases/run_files.py::_escapes` restated: that one guards an Operator's
    own path over HTTP, this one guards a scenario file's, and neither may import the other
    (AD-2 — `infrastructure/` does not reach into `application/` for a helper).
    """
    pure = PurePosixPath(path)
    return pure.is_absolute() or ".." in pure.parts


def _usage(value: object) -> HarnessUsage | None:
    """The figures the harness reports, or `None` — never zeroes read back as measured."""
    if not isinstance(value, dict):
        return None
    try:
        cost = Decimal(str(value.get("cost_usd", "0")))
    except InvalidOperation:
        return None
    return HarnessUsage(
        tokens_in=_int(value.get("tokens_in"), 0),
        tokens_out=_int(value.get("tokens_out"), 0),
        cost_usd=cost,
    )


def _int(value: object, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _float(value: object, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    return float(value) if isinstance(value, int | float) else fallback


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
