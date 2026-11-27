"""Run defaults, the initiative folder and the package install against the running stack
(initiative orchestrator-initiative-steps, epic 6, SPEC CAP-1..CAP-4).

The unit suite proves each rule over the shared fakes. What only the running stack settles:
the five run defaults and the folder survive a real Postgres round trip and the full-replace
`PUT`s; `POST /runs` and pre-flight bind `initiative_folder` through the real adapters and
store the bound value on the Run; install reads `package.yaml` from a real bare origin
through the real `Git` adapter, stores the qualified template versions and the record in one
unit of work, and a refusal leaves both untouched; the MCP endpoint reaches all five
operations.

Every package and template name is fresh, every origin a new bare repository this module
writes; no test reads a shipped template or the hub's `package/` (hard rule 6). The happy
path holds no shipped entry for that reason: a shipped reference is covered by the unit
suite, and here only as the refusal of a name no shipped template can carry.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import (
    DOCKER_TIMEOUT_SECONDS,
    FIXTURE_DIRECTORY,
    REPO_ROOT,
    UNKNOWN_ID,
    manifest_stating,
)
from tests.e2e.test_mcp_setup_path import Mcp
from tests.e2e.test_run_creation import (
    BRANCH,
    PROJECTS,
    REPOSITORIES,
    RUNS,
    TEMPLATES,
    clone_check,
    create_repository,
)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
TIMEOUT_SECONDS = 30.0

PATH = "pkg"

DEFAULTS = {
    "default_budget_usd": "25.00",
    "default_harness": "claude",
    "default_model": "claude-opus-5-5",
    "default_autonomy": "auto",
    "default_senior_model": "claude-opus-5-5",
}
UNSET = dict.fromkeys(DEFAULTS)
#: A budget is rendered as the money string every payload uses, so it is read as a decimal.
DEFAULTS_READ = {**DEFAULTS, "default_budget_usd": Decimal(DEFAULTS["default_budget_usd"])}

SPEC = """name: spec
version: 1
description: e2e epic 6 spec workflow
type: interactive
steps:
@ROWS@  - id: gate
    uses: agent
    role: spec-gate
    with: { skill: spec-gate }
    prompts:
      dispatch: "Run {skill}."
      rendered: "Rendered at {path}."
    expect:
      files: ["docs/gate.md"]
      success: [@SUCCESS@]
      blocked: [blocked]
    gate: liveness
"""

CONVERSATION = """  - id: @STEP@
    uses: conversation
    role: plan
    gate: human
    with: { step: @STEP@, skill: bmad-@STEP@, persona: personas/analyst.md }
    expect:
      files: ["docs/@STEP@.md"]
      success: [done]
    writes: ["docs/@STEP@.md"]
    prompts:
      open: "Open @STEP@."
      close: "Close @STEP@ as {attempt_id}."
"""

MERGE = """name: @NAME@
version: 1
description: e2e epic 6 merge workflow
type: interactive
steps:
  - id: merge
    uses: git.merge
    gate: deterministic
"""

SEQUENCE = (
    "  - { workflow: spec, template: templates/spec.yaml }\n"
    "  - { workflow: merge, template: templates/merge.yaml }\n"
)

LEAF_WITH_FOLDER = (
    "name: {name}\nversion: 1\ndescription: e2e epic 6 folder binding\n"
    "inputs:\n"
    "  project:           {{ type: project,    required: true }}\n"
    "  repository:        {{ type: repository, required: true }}\n"
    "  base_branch:       {{ type: string,     required: true }}\n"
    "  initiative_folder: {{ type: string,     required: false }}\n"
    "steps:\n"
    "  - id: touch\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)

#: `$1` directory, `$2` name, `$3` manifest; then pairs of repository path and content.
MAKE_PACKAGE_ORIGIN = """
set -e
dir="$1"; name="$2"; manifest="$3"; shift 3
mkdir -p "$dir"
rm -rf "$dir/$name.git" "$dir/$name.seed"
git init --quiet --bare --initial-branch=main "$dir/$name.git"
git init --quiet --initial-branch=main "$dir/$name.seed"
cd "$dir/$name.seed"
git config user.email e2e@example.invalid
git config user.name e2e
echo "$name" > README.md
mkdir -p _bmad/_config
printf '%s' "$manifest" > _bmad/_config/manifest.yaml
while [ "$#" -ge 2 ]; do
  mkdir -p "$(dirname "$1")"
  printf '%s' "$2" > "$1"
  shift 2
done
git add --all
git commit --quiet --message seed
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
"""


def spec_text(success: str = "pass, fail", steps: tuple[str, ...] = ("intake", "product")) -> str:
    rows = "".join(CONVERSATION.replace("@STEP@", step) for step in steps)
    return SPEC.replace("@ROWS@", rows).replace("@SUCCESS@", success)


def package_text(name: str, /, **overrides: str) -> str:
    parts = {
        "name": name,
        "sequence": SEQUENCE,
        "gate": "{ pass: [pass], fail: [fail], owners_key: owners }",
        "status_map": "{ final: done, blocked: waiting for her }",
        "extra": "",
    }
    parts.update(overrides)
    return (
        f"name: {parts['name']}\nsequence:\n{parts['sequence']}"
        f"gate: {parts['gate']}\nstatus_map: {parts['status_map']}\n{parts['extra']}"
    )


def package_files(name: str, /, folder: str = PATH, **overrides: str) -> dict[str, str]:
    """A valid package under `folder`; an override keyed by a relative path replaces a file,
    one keyed by a `package.yaml` part replaces that part, and an empty text drops a file."""
    parts = {key: overrides.pop(key) for key in list(overrides) if "/" not in key}
    files = {
        "package.yaml": package_text(name, **parts),
        "templates/spec.yaml": spec_text(),
        "templates/merge.yaml": MERGE.replace("@NAME@", "merge"),
        **overrides,
    }
    return {f"{folder}/{path}": text for path, text in files.items() if text}


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


def package_origin(settings: Settings, files: dict[str, str]) -> str:
    """A fresh bare origin holding `files` on `main`; its `file://` URL.

    The container is tried first, as `test_conversation_stop.talking_origin` does: the
    backend must be able to read what the test wrote.
    """
    directory = settings.work_dir / FIXTURE_DIRECTORY
    name = f"pkg-{uuid4()}"
    pairs = [item for pair in files.items() for item in pair]
    arguments = [str(directory), name, manifest_stating(settings.bmad_version), *pairs]
    refusals: list[str] = []
    for prefix in (("docker", "compose", "exec", "-T", "backend-api"), ()):
        command = [*prefix, "sh", "-c", MAKE_PACKAGE_ORIGIN, "sh", *arguments]
        try:
            done = subprocess.run(  # fixed argv, no shell
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=DOCKER_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            refusals.append(str(error))
            continue
        if done.returncode == 0:
            return f"file://{directory}/{name}.git"
        refusals.append((done.stderr or done.stdout).strip())
    pytest.fail("no route to create the package fixture: " + " | ".join(refusals))


def defaults_of(payload: dict[str, Any]) -> dict[str, Any]:
    read = {key: payload[key] for key in DEFAULTS}
    if read["default_budget_usd"] is not None:
        read["default_budget_usd"] = Decimal(read["default_budget_usd"])
    return read


def new_project(api: httpx.Client) -> dict[str, Any]:
    response = api.post(PROJECTS, json={"name": f"e2e package {uuid4()}"})
    assert response.status_code == HTTP_CREATED, response.text
    return dict(response.json())


def read_project(api: httpx.Client, project_id: str) -> dict[str, Any]:
    response = api.get(f"{PROJECTS}/{project_id}")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def unique_package() -> str:
    return f"e2e-pkg-{uuid4().hex[:12]}"


def hub_with(api: httpx.Client, settings: Settings, files: dict[str, str]) -> tuple[str, str]:
    """A new project and its hub repository holding `files`: `(project_id, repository_id)`."""
    project_id = str(new_project(api)["id"])
    return project_id, create_repository(api, project_id, package_origin(settings, files))


def install(
    api: httpx.Client, project_id: str, repository_id: str, *, path: str = PATH, ref: str = BRANCH
) -> httpx.Response:
    return api.put(
        f"{PROJECTS}/{project_id}/package",
        json={"repository_id": repository_id, "path": path, "ref": ref},
    )


def versions_of(api: httpx.Client, name: str) -> list[int]:
    response = api.get(f"{TEMPLATES}/{name}/versions")
    if response.status_code == HTTP_NOT_FOUND:
        return []
    assert response.status_code == HTTP_OK, response.text
    return [int(item) for item in response.json()["items"]]


def errors_of(response: httpx.Response) -> list[tuple[str, str]]:
    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    return [(item["path"], item["reason"]) for item in response.json()["errors"]]


# ── CAP-1: run defaults ─────────────────────────────────────────────────────────────────


def test_a_new_project_reads_every_run_default_null(api: httpx.Client) -> None:
    created = new_project(api)

    assert {key: created.get(key) for key in DEFAULTS} == UNSET
    assert {key: read_project(api, created["id"]).get(key) for key in DEFAULTS} == UNSET


def test_run_defaults_are_stored_returned_and_survive_the_full_replace_put(
    api: httpx.Client,
) -> None:
    project = new_project(api)

    response = api.put(f"{PROJECTS}/{project['id']}/run-defaults", json=DEFAULTS)

    assert response.status_code == HTTP_OK, response.text
    assert defaults_of(response.json()) == DEFAULTS_READ
    assert defaults_of(read_project(api, project["id"])) == DEFAULTS_READ

    replaced = api.put(
        f"{PROJECTS}/{project['id']}",
        json={
            "name": f"{project['name']} renamed",
            "context_text": project["context_text"],
            "context_paths": project["context_paths"],
            "env_vars": [],
        },
    )
    assert replaced.status_code == HTTP_OK, replaced.text
    assert defaults_of(read_project(api, project["id"])) == DEFAULTS_READ

    cleared = api.put(f"{PROJECTS}/{project['id']}/run-defaults", json=UNSET)
    assert cleared.status_code == HTTP_OK, cleared.text
    assert {key: read_project(api, project["id"])[key] for key in DEFAULTS} == UNSET


@pytest.mark.parametrize("budget", ["0", "-1"])
def test_a_budget_of_zero_or_below_is_refused_naming_the_field(
    api: httpx.Client, budget: str
) -> None:
    project = new_project(api)

    response = api.put(
        f"{PROJECTS}/{project['id']}/run-defaults", json={**DEFAULTS, "default_budget_usd": budget}
    )

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    assert "default_budget_usd" in response.text
    assert read_project(api, project["id"])["default_budget_usd"] is None


def test_an_unknown_key_or_an_omitted_key_is_refused(api: httpx.Client) -> None:
    project = new_project(api)
    url = f"{PROJECTS}/{project['id']}/run-defaults"

    assert api.put(url, json={**DEFAULTS, "default_colour": "red"}).status_code == (
        HTTP_UNPROCESSABLE
    )
    omitted = {key: value for key, value in DEFAULTS.items() if key != "default_model"}
    assert api.put(url, json=omitted).status_code == HTTP_UNPROCESSABLE


def test_run_defaults_of_an_unknown_project_are_a_404(api: httpx.Client) -> None:
    response = api.put(f"{PROJECTS}/{UNKNOWN_ID}/run-defaults", json=DEFAULTS)

    assert response.status_code == HTTP_NOT_FOUND, response.text


# ── CAP-2: the initiative folder ────────────────────────────────────────────────────────


@pytest.fixture
def repository(api: httpx.Client, settings: Settings) -> dict[str, str]:
    """A new project and a clone-checked repository: `{project_id, repository_id}`."""
    project_id = str(new_project(api)["id"])
    repository_id = create_repository(api, project_id, package_origin(settings, {}))
    clone_check(api, repository_id)
    return {"project_id": project_id, "repository_id": repository_id}


def test_a_new_repository_reads_the_default_folder_and_the_put_stores_another(
    api: httpx.Client, repository: dict[str, str]
) -> None:
    url = f"{REPOSITORIES}/{repository['repository_id']}"
    assert api.get(url).json()["initiative_folder"] == "initiatives"

    response = api.put(f"{url}/initiative-folder", json={"initiative_folder": "specs/initiatives"})

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["initiative_folder"] == "specs/initiatives"
    assert api.get(url).json()["initiative_folder"] == "specs/initiatives"


@pytest.mark.parametrize("folder", ["", "/abs", "a/../b", "a/", "a//b"])
def test_an_invalid_folder_is_refused_and_nothing_changes(
    api: httpx.Client, repository: dict[str, str], folder: str
) -> None:
    url = f"{REPOSITORIES}/{repository['repository_id']}"

    response = api.put(f"{url}/initiative-folder", json={"initiative_folder": folder})

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    assert api.get(url).json()["initiative_folder"] == "initiatives"


def test_the_folder_of_an_unknown_repository_is_a_404(api: httpx.Client) -> None:
    response = api.put(
        f"{REPOSITORIES}/{UNKNOWN_ID}/initiative-folder", json={"initiative_folder": "x"}
    )

    assert response.status_code == HTTP_NOT_FOUND, response.text


@pytest.fixture
def folder_template(api: httpx.Client) -> str:
    name = f"e2e-folder-{uuid4().hex}"
    response = api.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": LEAF_WITH_FOLDER.format(name=name)}
    )
    assert response.status_code == HTTP_CREATED, response.text
    return name


def run_body(template: str, repository: dict[str, str], inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_name": template,
        "template_version": 1,
        "project_id": repository["project_id"],
        "repository_id": repository["repository_id"],
        "base_branch": BRANCH,
        "budget_usd": "5",
        "inputs": inputs,
    }


@pytest.fixture
def started(api: httpx.Client) -> Iterator[list[str]]:
    run_ids: list[str] = []
    yield run_ids
    for run_id in run_ids:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}})


def created_inputs(api: httpx.Client, body: dict[str, Any], started: list[str]) -> dict[str, Any]:
    response = api.post(RUNS, json=body)
    assert response.status_code == HTTP_CREATED, response.text
    run_id = str(response.json()["run"]["id"])
    started.append(run_id)
    detail = api.get(f"{RUNS}/{run_id}/detail")
    assert detail.status_code == HTTP_OK, detail.text
    return dict(detail.json()["run"]["inputs"])


@pytest.mark.parametrize(
    "binding",
    [({}, "initiatives"), ({"initiative_folder": "initiatives/snake"}, "initiatives/snake")],
)
def test_an_omitted_folder_is_bound_and_one_under_it_is_kept_on_the_stored_run(
    api: httpx.Client,
    repository: dict[str, str],
    folder_template: str,
    started: list[str],
    binding: tuple[dict[str, Any], str],
) -> None:
    given, stored = binding
    inputs = created_inputs(api, run_body(folder_template, repository, given), started)

    assert inputs["initiative_folder"] == stored


@pytest.mark.parametrize("value", ["docs/initiative", "initiatives/../x", "initiatives//a", 3])
def test_a_value_outside_the_folder_is_refused_by_create_and_preflight_storing_no_run(
    api: httpx.Client, repository: dict[str, str], folder_template: str, value: object
) -> None:
    body = run_body(folder_template, repository, {"initiative_folder": value})
    reason = (
        f"initiative_folder {value} is not under the repository's initiative folder initiatives"
    )

    created = api.post(RUNS, json=body)

    assert created.status_code == HTTP_UNPROCESSABLE, created.text
    assert reason in created.json()["detail"]
    listed = api.get(RUNS, params={"project_id": repository["project_id"]})
    assert listed.status_code == HTTP_OK, listed.text
    assert listed.json()["items"] == []

    preflight = api.post(f"{RUNS}/preflight", json=body)
    assert preflight.status_code == HTTP_OK, preflight.text
    assert preflight.json()["plan_error"]["reason"] == reason
    assert preflight.json()["start_allowed"] is False


def test_the_bound_folder_follows_the_repository_folder(
    api: httpx.Client, repository: dict[str, str], folder_template: str, started: list[str]
) -> None:
    url = f"{REPOSITORIES}/{repository['repository_id']}/initiative-folder"
    assert api.put(url, json={"initiative_folder": "specs/work"}).status_code == HTTP_OK

    inputs = created_inputs(api, run_body(folder_template, repository, {}), started)

    assert inputs["initiative_folder"] == "specs/work"
    refused = api.post(
        RUNS, json=run_body(folder_template, repository, {"initiative_folder": "initiatives"})
    )
    assert refused.status_code == HTTP_UNPROCESSABLE, refused.text


def test_a_template_with_no_folder_input_is_not_bound(
    api: httpx.Client, repository: dict[str, str], started: list[str]
) -> None:
    name = f"e2e-nofolder-{uuid4().hex}"
    text = LEAF_WITH_FOLDER.format(name=name).replace(
        "  initiative_folder: { type: string,     required: false }\n", ""
    )
    assert "initiative_folder" not in text
    saved = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": text})
    assert saved.status_code == HTTP_CREATED, saved.text

    inputs = created_inputs(api, run_body(name, repository, {}), started)

    assert "initiative_folder" not in inputs


# ── CAP-3: the package install ──────────────────────────────────────────────────────────


def test_a_valid_package_installs_reads_back_and_stores_qualified_versions(
    api: httpx.Client, settings: Settings
) -> None:
    name = unique_package()
    project_id, repository_id = hub_with(api, settings, package_files(name))

    response = install(api, project_id, repository_id)

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert (body["name"], body["path"], body["ref"]) == (name, PATH, BRANCH)
    assert len(body["sha"]) == 40  # noqa: PLR2004 — a full commit sha
    assert body["repository"]["id"] == repository_id
    assert body["repository"]["initiative_folder"] == "initiatives"
    assert body["gate"] == {"pass": ["pass"], "fail": ["fail"], "owners_key": "owners"}
    assert body["status_map"] == {"final": "done", "blocked": "waiting for her"}

    spec, merge = body["sequence"]
    assert (spec["workflow"], spec["template"], spec["version"]) == ("spec", f"{name}.spec", 1)
    assert (spec["type"], spec["shown_as"]) == ("interactive", "workflow")
    assert [(s["id"], s["kind"]) for s in spec["steps"]] == [
        ("intake", "conversation"),
        ("product", "conversation"),
        ("gate", "automatic"),
    ]
    intake = spec["steps"][0]
    assert intake == {
        "id": "intake",
        "kind": "conversation",
        "skill": "bmad-intake",
        "persona": "personas/analyst.md",
        "file": "docs/intake.md",
        "writes": ["docs/intake.md"],
    }
    assert spec["steps"][2] == {
        "id": "gate",
        "kind": "automatic",
        "skill": None,
        "persona": None,
        "file": "docs/gate.md",
        "writes": [],
    }
    assert (merge["template"], merge["shown_as"], merge["steps"]) == (f"{name}.merge", "step", [])

    read = api.get(f"{PROJECTS}/{project_id}/package")
    assert read.status_code == HTTP_OK, read.text
    assert read.json() == body

    stored = api.get(f"{TEMPLATES}/{name}.spec/1")
    assert stored.status_code == HTTP_OK, stored.text
    assert stored.json()["type"] == "interactive"
    assert stored.json()["yaml"] == spec_text()


def test_a_second_install_at_the_same_sha_stores_no_new_version(
    api: httpx.Client, settings: Settings
) -> None:
    name = unique_package()
    project_id, repository_id = hub_with(api, settings, package_files(name))
    first = install(api, project_id, repository_id)
    assert first.status_code == HTTP_OK, first.text

    second = install(api, project_id, repository_id)

    assert second.status_code == HTTP_OK, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["sequence"] == first.json()["sequence"]
    assert versions_of(api, f"{name}.spec") == [1]
    assert versions_of(api, f"{name}.merge") == [1]


REFUSALS: list[tuple[str, dict[str, str], str, str]] = [
    ("unknown key", {"extra": "owner: her\n"}, "package.yaml", "unknown key owner"),
    ("bad name", {"name": "Bad_Name"}, "package.yaml", "name: must match"),
    (
        "empty sequence",
        {"sequence": "  []\n"},
        "package.yaml",
        "sequence: must be a non-empty list",
    ),
    (
        "duplicate workflow",
        {"sequence": SEQUENCE.replace("workflow: merge", "workflow: spec")},
        "package.yaml",
        "workflow spec appears twice",
    ),
    (
        "dotdot path",
        {"sequence": SEQUENCE.replace("templates/merge.yaml", "../merge.yaml")},
        "package.yaml",
        "template ../merge.yaml is not a path inside the package",
    ),
    ("missing template file", {"templates/merge.yaml": ""}, "templates/merge.yaml", "not found"),
    (
        "template fails judging",
        {"templates/merge.yaml": "name: merge\nversion: 1\nsteps: x\n"},
        "templates/merge.yaml",
        "line ",
    ),
    (
        "name differs from stem",
        {"templates/merge.yaml": MERGE.replace("@NAME@", "other")},
        "templates/merge.yaml",
        "name must be merge",
    ),
    (
        "unknown shipped name",
        {"sequence": SEQUENCE + "  - { workflow: build, template: e2e-no-such-shipped }\n"},
        "package.yaml",
        "e2e-no-such-shipped is not a shipped template",
    ),
    (
        "word in pass and fail",
        {"gate": "{ pass: [pass], fail: [pass], owners_key: owners }"},
        "package.yaml",
        "word pass is in both gate.pass and gate.fail",
    ),
    (
        "no spec-gate row",
        {"templates/spec.yaml": spec_text().split("  - id: gate")[0]},
        "package.yaml",
        "no spec-gate row",
    ),
    (
        "gate word missing from expect.success",
        {"templates/spec.yaml": spec_text(success="pass")},
        "templates/spec.yaml",
        "spec-gate row gate does not list gate word fail in expect.success",
    ),
    (
        "bad status word",
        {"status_map": "{ final: finished }"},
        "package.yaml",
        "status_map final: finished is not one of",
    ),
]


@pytest.mark.parametrize("refusal", REFUSALS, ids=[case for case, *_ in REFUSALS])
def test_a_malformed_package_is_refused_naming_the_file_and_stores_nothing(
    api: httpx.Client, settings: Settings, refusal: tuple[str, dict[str, str], str, str]
) -> None:
    case, overrides, file, reason = refusal
    name = unique_package()
    project_id, repository_id = hub_with(api, settings, package_files(name, **overrides))

    response = install(api, project_id, repository_id)

    found = errors_of(response)
    assert any(path == f"{PATH}/{file}" and reason in why for path, why in found), (
        f"{case}: {found}"
    )
    assert api.get(f"{PROJECTS}/{project_id}/package").status_code == HTTP_NOT_FOUND
    assert versions_of(api, f"{name}.spec") == []
    assert versions_of(api, f"{name}.merge") == []


def test_two_templates_with_one_stem_are_refused(api: httpx.Client, settings: Settings) -> None:
    name = unique_package()
    sequence = (
        "  - { workflow: a, template: a/spec.yaml }\n  - { workflow: b, template: b/spec.yaml }\n"
    )
    files = package_files(
        name,
        sequence=sequence,
        **{"a/spec.yaml": spec_text(), "b/spec.yaml": spec_text()},
    )
    project_id, repository_id = hub_with(api, settings, files)

    found = errors_of(install(api, project_id, repository_id))

    assert (
        f"{PATH}/b/spec.yaml",
        "two templates have the stem spec: a/spec.yaml, b/spec.yaml",
    ) in found
    assert versions_of(api, f"{name}.spec") == []


def test_a_missing_package_file_and_a_bad_path_are_refused(
    api: httpx.Client, settings: Settings
) -> None:
    project_id, repository_id = hub_with(api, settings, package_files(unique_package()))

    assert errors_of(install(api, project_id, repository_id, path="elsewhere")) == [
        ("elsewhere/package.yaml", "file not found")
    ]
    bad_path = install(api, project_id, repository_id, path="../pkg")
    assert bad_path.status_code == HTTP_UNPROCESSABLE, bad_path.text


def test_a_ref_the_remote_lacks_is_a_409_naming_it(api: httpx.Client, settings: Settings) -> None:
    project_id, repository_id = hub_with(api, settings, package_files(unique_package()))

    response = install(api, project_id, repository_id, ref="no-such-branch")

    assert response.status_code == HTTP_CONFLICT, response.text
    assert "no-such-branch" in response.json()["detail"]


def test_a_repository_of_another_project_is_a_404(api: httpx.Client, settings: Settings) -> None:
    _, repository_id = hub_with(api, settings, package_files(unique_package()))
    other = str(new_project(api)["id"])

    response = install(api, other, repository_id)

    assert response.status_code == HTTP_NOT_FOUND, response.text
    assert api.get(f"{PROJECTS}/{other}/package").status_code == HTTP_NOT_FOUND


def test_one_package_installs_on_two_projects_and_another_of_its_name_is_refused(
    api: httpx.Client, settings: Settings
) -> None:
    name = unique_package()
    url = package_origin(settings, package_files(name))
    first = new_project(api)
    second = new_project(api)
    for project in (first, second):
        repository_id = create_repository(api, project["id"], url)
        response = install(api, project["id"], repository_id)
        assert response.status_code == HTTP_OK, response.text

    impostor, impostor_repository = hub_with(api, settings, package_files(name))
    refused = install(api, impostor, impostor_repository)

    assert refused.status_code == HTTP_CONFLICT, refused.text
    detail = refused.json()["detail"]
    assert first["slug"] in detail or second["slug"] in detail, detail
    assert api.get(f"{PROJECTS}/{impostor}/package").status_code == HTTP_NOT_FOUND


def test_delete_removes_the_record_and_keeps_every_template_version(
    api: httpx.Client, settings: Settings
) -> None:
    name = unique_package()
    project_id, repository_id = hub_with(api, settings, package_files(name))
    assert install(api, project_id, repository_id).status_code == HTTP_OK

    removed = api.delete(f"{PROJECTS}/{project_id}/package")

    assert removed.status_code == HTTP_NO_CONTENT, removed.text
    assert api.get(f"{PROJECTS}/{project_id}/package").status_code == HTTP_NOT_FOUND
    assert api.delete(f"{PROJECTS}/{project_id}/package").status_code == HTTP_NOT_FOUND
    assert versions_of(api, f"{name}.spec") == [1]
    assert versions_of(api, f"{name}.merge") == [1]


def test_the_package_operations_need_the_bearer(client: httpx.Client) -> None:
    url = f"{PROJECTS}/{UNKNOWN_ID}/package"
    for method in ("GET", "PUT", "DELETE"):
        assert client.request(method, url).status_code == httpx.codes.UNAUTHORIZED, method
    assert (
        client.put(f"{PROJECTS}/{UNKNOWN_ID}/run-defaults", json=DEFAULTS).status_code
        == httpx.codes.UNAUTHORIZED
    )
    assert (
        client.put(
            f"{REPOSITORIES}/{UNKNOWN_ID}/initiative-folder", json={"initiative_folder": "x"}
        ).status_code
        == httpx.codes.UNAUTHORIZED
    )


# ── CAP-4: the five MCP tools ───────────────────────────────────────────────────────────


def test_the_five_operations_are_reached_through_mcp_tools(
    api: httpx.Client, settings: Settings
) -> None:
    name = unique_package()
    project_id, repository_id = hub_with(api, settings, package_files(name))
    mcp = Mcp(api)

    listed = mcp._post("tools/list", {})["result"]["tools"]
    names = {tool["name"] for tool in listed}
    tools = {
        "set_run_defaults",
        "set_initiative_folder",
        "install_package",
        "read_package",
        "remove_package",
    }
    assert tools <= names

    project = mcp.call("set_run_defaults", project_id=project_id, body=DEFAULTS)
    assert defaults_of(project) == DEFAULTS_READ
    folder = mcp.call(
        "set_initiative_folder",
        repository_id=repository_id,
        body={"initiative_folder": "specs/initiatives"},
    )
    assert folder["initiative_folder"] == "specs/initiatives"

    installed = mcp.call(
        "install_package",
        project_id=project_id,
        body={"repository_id": repository_id, "path": PATH, "ref": BRANCH},
    )
    assert installed["name"] == name
    assert installed["repository"]["initiative_folder"] == "specs/initiatives"
    assert mcp.call("read_package", project_id=project_id) == installed

    mcp._post("tools/call", {"name": "remove_package", "arguments": {"project_id": project_id}})
    assert api.get(f"{PROJECTS}/{project_id}/package").status_code == HTTP_NOT_FOUND
