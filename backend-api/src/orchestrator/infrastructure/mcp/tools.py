"""The tools `/mcp` publishes: one REST operation each, and the rule that governs it.

Every docstring here is read by the agent that calls the tool — the SDK publishes it as the
tool's description — so each one states the same rule the guide states for that
endpoint. The guide, read through `read_guide`, is the floor: an operator whose harness speaks no
MCP reads exactly these rules in prose, and nothing here is a second source of truth for
*how* the API behaves (`infrastructure/mcp/client.py` says why).

Thin by construction: a tool parses nothing, decides nothing and writes no status (AD-8).

Five builders rather than one, in the order a session uses them — what this instance holds,
what sets a target up, what checks and saves a workflow, what starts and steers a Run, what
watches one. The split is also what keeps each function under the complexity limit
`backend-api/AGENTS.md` sets, since a nested definition counts.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

from orchestrator.infrastructure.mcp.client import InProcessApi
from orchestrator.infrastructure.mcp.facade import ToolFailure

#: What `build_tools` hands the server: named async callables, their signatures the schema.
type Tool = Callable[..., Awaitable[Any]]


#: The operationId (as `app.openapi()` names it) of every operation a tool calls. A tool whose
#: call is not here fails `tests/unit/test_mcp_allow_list.py`; nothing under `/instance`, `/kit`,
#: `/readiness` or `/probe` may ever be added (AD-34).
ALLOWED_OPERATION_IDS: frozenset[str] = frozenset(
    {
        "read_version_api_v1_version_get",
        "list_templates_api_v1_templates_get",
        "get_version_api_v1_templates__name___version__get",
        "list_projects_api_v1_projects_get",
        "read_queue_api_v1_queue_get",
        "create_project_api_v1_projects_post",
        "update_project_api_v1_projects__project_id__put",
        "add_repository_api_v1_projects__project_id__repositories_post",
        "run_clone_check_api_v1_repositories__repository_id__clone_check_post",
        "init_api_v1_repositories__repository_id__init_post",
        "validate_text_api_v1_templates__name__validate_post",
        "save_version_api_v1_templates__name__versions_post",
        "reload_folder_api_v1_templates_reload_post",
        "validate_spec_folder_api_v1_spec_folders_validate_post",
        "preflight_api_v1_runs_preflight_post",
        "create_api_v1_runs_post",
        "post_signal_api_v1_runs__run_id__signals_post",
        "get_api_v1_runs__run_id__get",
        "detail_api_v1_runs__run_id__detail_get",
        "events_api_v1_runs__run_id__events_get",
        "list_models_api_v1_harnesses__name__models_get",
        "read_index_llms_txt_get",
        "read_page_guide__page_id__md_get",
    }
)

#: A guide page id (C2): lowercase segments joined by `/`. Nothing else may become a path.
PAGE_ID = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+)*$")


def prompt_name(page_id: str) -> str:
    """The MCP prompt a procedure page is published as: its id with `/` written `.`."""
    return page_id.replace("/", ".")


_UUID = re.compile(r"^[0-9a-fA-F-]{36}$")
_HARNESS = re.compile(r"^[a-z0-9-]+$")


_SEGMENT_BREAKERS = ("/", "\\", "%", "?", "#", "..")
_SEGMENT_MAX = 200
_CONTROL = frozenset(map(chr, [*range(0x20), 0x7F]))


def _path_segment(value: str, name: str = "path argument") -> str:
    """The one gate for a value that goes into a URL path: exactly one segment, or refused.

    httpx resolves `..` and moves anything after `?` into the query, so an unchecked value
    can reach an operation outside `ALLOWED_OPERATION_IDS` (epic 2 retro R1, AD-34).
    """
    if (
        value in ("", ".")
        or len(value) > _SEGMENT_MAX
        or any(breaker in value for breaker in _SEGMENT_BREAKERS)
        or any(char in _CONTROL for char in value)
    ):
        raise ToolFailure(f"{name} must be one path segment: not empty or ., no .. / \\ % ? #")
    return quote(value, safe="")


def _path_id(name: str, value: str) -> str:
    """An id that goes into a path: UUID-shaped or refused, so it cannot add a segment."""
    if not _UUID.fullmatch(value):
        raise ToolFailure(f"{name} must be a UUID")
    return _path_segment(value, name)


def build_tools(api: InProcessApi) -> list[Tool]:
    """The whole tool set, bound to one in-process API client."""
    return [
        *_instance_tools(api),
        *_guide_tools(api),
        *_setup_tools(api),
        *_workflow_tools(api),
        *_dispatch_tools(api),
        *_watch_tools(api),
    ]


def _instance_tools(api: InProcessApi) -> list[Tool]:
    """What this instance is and what it holds."""

    async def version() -> Any:
        """What this instance is: its release, its bootstrap contract, where its guide is, and its
        BMAD and harness pins.

        Call this first, then `read_guide` with no id. When `bootstrap_contract` is above the
        one your bootstrap states, tell the user (code `refusal-bootstrap-contract`, page
        `errors/refusal-bootstrap-contract`) and continue; never stop on a release difference.
        """
        return await api.get("/version")

    async def list_templates() -> Any:
        """Every workflow Template this instance holds, with its versions.

        Templates are exemplars that evolve: read the list, never a remembered name or version.
        """
        return await api.get("/templates")

    async def get_template(name: str, version: int) -> Any:
        """One Template version — its declared inputs, defaults and steps.

        What a Run may be given is what the Template declares here; an input it does not
        declare is not passed.
        """
        number = _path_segment(str(int(version)), "version")
        return await api.get(f"/templates/{_path_segment(name, 'name')}/{number}")

    async def list_projects() -> Any:
        """Every Project and the Repositories under it — where a Run's targeting comes from."""
        return await api.get("/projects")

    async def list_queue() -> Any:
        """What is running, what is waiting, and why each waiting Run is waiting."""
        return await api.get("/queue")

    async def list_models(harness: str) -> Any:
        """The models a harness can use, and where the list comes from.

        The answer names its `source`: `litellm` (the instance's LiteLLM key may use exactly
        these), `configured` (`LOCAL_MODELS`, for the local harness) or `none` (nothing can be
        listed here). With `source: none`, ask the user for the model name; never invent one.
        A `code` carries a `guide` page.
        """
        if not _HARNESS.fullmatch(harness):
            raise ToolFailure("harness must match ^[a-z0-9-]+$")
        return await api.get(f"/harnesses/{_path_segment(harness, 'harness')}/models")

    return [version, list_templates, get_template, list_projects, list_queue, list_models]


def _guide_tools(api: InProcessApi) -> list[Tool]:
    """The guide, for a harness that speaks tools only."""

    async def read_guide(id: str | None = None) -> Any:
        """Read the guide: call with no id for the index, then with a page id from it.

        Pages under `host/` are for the host agent only. An `errors/{code}` page explains the
        `code` of a problem document.
        """
        if id is None:
            return await api.get_open("/llms.txt")
        if not PAGE_ID.fullmatch(id):
            raise ToolFailure(f"not a page id: {id!r}")
        page = "/".join(_path_segment(part, "id") for part in id.split("/"))
        return await api.get_open(f"/guide/{page}.md")

    return [read_guide]


def _setup_tools(api: InProcessApi) -> list[Tool]:
    """What sets a target up: a Project, its Repository, the clone check, BMAD, variables."""

    async def create_project(body: dict[str, Any]) -> Any:
        """Create a Project: `{name, context_text, context_paths, env_vars}`.

        Every variable carries a value and is secret: it leaves the API as `{name, masked}`.
        Look with `list_projects` before creating — Projects are reused across Runs.
        """
        return await api.post("/projects", body)

    async def update_project(project_id: str, body: dict[str, Any]) -> Any:
        """Replace a Project. PUT replaces the whole Project, not the fields sent.

        Read it with `list_projects` first and send every field and every variable: an omitted
        `context_text` or `context_paths` is reset, an omitted variable is dropped (only an
        omitted `log_prompt_content` keeps its stored value). Every project variable is secret
        and leaves the API as `{name, masked}`. A variable sent without `value` keeps its
        stored value; a value can be replaced, never read back.
        """
        return await api.put(f"/projects/{_path_id('project_id', project_id)}", body)

    async def add_repository(project_id: str, body: dict[str, Any]) -> Any:
        """Add a Repository to a Project.

        The orchestrator clones with its own instance token, so the URL must be reachable by
        it. `test_globs` is exactly the list sent: empty freezes no file for the agent.
        """
        return await api.post(f"/projects/{_path_id('project_id', project_id)}/repositories", body)

    async def check_clone(repository_id: str) -> Any:
        """Prove a Repository's URL and token resolve, and create its base clone.

        Run it after `add_repository`. Do not proceed past a failing check: its lines and
        hint say what to fix.
        """
        rid = _path_id("repository_id", repository_id)
        return await api.post(f"/repositories/{rid}/clone-check")

    async def init_repository(repository_id: str, body: dict[str, Any] | None = None) -> Any:
        """Start a `repo-init` Run that sets a Repository up with BMAD, as a pull request.

        Only when the Repository has never been BMAD-initialised, on its default branch. The
        optional body is `{harness}`. Monitor the Run like any other: until it ends, pre-flight
        on the same Repository warns about it and `create_run` needs `conflict_consent`.
        """
        rid = _path_id("repository_id", repository_id)
        return await api.post(f"/repositories/{rid}/init", body)

    return [create_project, update_project, add_repository, check_clone, init_repository]


def _workflow_tools(api: InProcessApi) -> list[Tool]:
    """What checks a workflow, saves it, and reloads the operator's template folder."""

    async def validate_template(name: str, yaml: str) -> Any:
        """Check workflow YAML without storing it; every problem is a finding in `errors`.

        Each finding carries `line`, `code` and `guide`: read the page `errors/{code}`. The
        `name:` key must equal `name`.
        """
        return await api.post(f"/templates/{_path_segment(name, 'name')}/validate", {"yaml": yaml})

    async def save_template(name: str, yaml: str) -> Any:
        """Save workflow YAML as the next version of `name`; `version:` is `max + 1`.

        Invalid YAML answers 422 with findings (`code`, `guide`: read `errors/{code}`). A
        workflow held in the operator's template folder is refused with 409
        `refusal-template-in-folder`: the file is edited on the host, then call
        `reload_templates`. A saved version never changes.
        """
        body = {"yaml": yaml, "refuse_if_in_folder": True}
        return await api.post(f"/templates/{_path_segment(name, 'name')}/versions", body)

    async def reload_templates() -> Any:
        """Re-read the operator's template folder and store each changed, valid file.

        Answers `stored`, `unchanged`, `refused` (with findings) and `not_in_folder`.
        """
        return await api.post("/templates/reload")

    async def validate_spec_folder(files: dict[str, str]) -> Any:
        """Check a spec folder before it is pushed.

        Send every file of the folder, keyed by its path relative to the initiative folder
        (`epics.yaml`, `<spec_folder>/stories.yaml`, `<spec_folder>/SPEC.md`,
        `<spec_folder>/stories/*.md`). The answer equals what the launch check reports after
        the push. Each finding carries `code` and `guide`: read page `errors/{code}`.
        """
        return await api.post("/spec-folders/validate", {"files": files})

    return [validate_template, save_template, reload_templates, validate_spec_folder]


def _dispatch_tools(api: InProcessApi) -> list[Tool]:
    """What starts a Run and what steers a parked one."""

    async def preflight_run(body: dict[str, Any]) -> Any:
        """Pre-flight a Run: every check that would refuse it, before anything is created.

        Always before `create_run`, and read every line: a `fail` line is a refusal to fix, not
        a warning to pass. `create_run` re-runs these checks and answers 409 on a `fail`.
        """
        return await api.post("/runs/preflight", body)

    async def create_run(body: dict[str, Any]) -> Any:
        """Create and enqueue a Run from a Template version.

        `budget_usd` is one human decision per Run: carry the number the operator gave, never
        invent, round or raise it. Pre-flight first.
        """
        return await api.post("/runs", body)

    async def send_signal(
        run_id: str, kind: str, payload: dict[str, Any] | None = None, stop: int | None = None
    ) -> Any:
        """Send one Signal to a parked Run.

        `kind` must be one of that Run's own `admitted_signals` — never a kind chosen from
        memory; anything else is refused with 409. A budget and a checkpoint are the operator's
        decisions and are never resolved on their behalf.

        On `answer`, `retry` and `continue`, set `stop` to the `park_seq` you read with the
        question: a Run that has moved to another stop refuses it with 409.
        """
        body: dict[str, Any] = {"kind": kind, "payload": payload or {}}
        if stop is not None:
            body["stop"] = stop
        return await api.post(f"/runs/{_path_segment(run_id, 'run_id')}/signals", body)

    return [preflight_run, create_run, send_signal]


def _watch_tools(api: InProcessApi) -> list[Tool]:
    """What a watcher reads, and how it waits."""

    async def get_run(run_id: str) -> Any:
        """One Run's state: status, spend, and the Signals it admits right now."""
        return await api.get(f"/runs/{_path_segment(run_id, 'run_id')}")

    async def get_run_detail(run_id: str) -> Any:
        """Everything the Run screen shows: every step, the park, its attempts and its cost.

        This is what to read once a Run parks — the park payload is here, not in the events
        endpoint.
        """
        return await api.get(f"/runs/{_path_segment(run_id, 'run_id')}/detail")

    async def wait_run_events(run_id: str, wait: int = 30, since: str | None = None) -> Any:
        """Wait up to `wait` seconds (0..30) for this Run to move, instead of polling.

        Answers as soon as `status` or `updated_at` changes, and `changed: false` when the wait
        ran out. Pass the `updated_at` of the previous answer as `since`, or a change made
        between two calls is missed. Then read `get_run_detail` to learn what happened.
        """
        rid = _path_segment(run_id, "run_id")
        return await api.get(f"/runs/{rid}/events", {"wait": wait, "since": since})

    return [get_run, get_run_detail, wait_run_events]
