"""Epic orchestrator-client-kit/epic-01 (template folder) against the running stack.

The unit suite proves every rule over the fakes. What only the real stack settles: the
reload operation is mounted behind the one credential and answers either the D3 report or an
RFC 9457 409; `in_folder` and an input's `description` survive the real repository and the
generated contract; a depth-2 file with `bind:` saves, validates and graphs through the real
store; the AD-15 amendment's rejections reach the client as data.

The e2e stack leaves `OPERATOR_TEMPLATES_DIR` blank (folder off), but an Operator may point
`make e2e-api` at a stack with the folder on: the reload test accepts either answer and checks
the shape of whichever arrives — it never skips. Every name saved here is unique per run.
"""

from __future__ import annotations

import httpx

from tests.e2e.helpers.templates import unique

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_UNAUTHORIZED = 401
HTTP_CONFLICT = 409

TEMPLATES = "/api/v1/templates"
RELOAD = f"{TEMPLATES}/reload"
PROBLEM_MEDIA_TYPE = "application/problem+json"

FOLDER_OFF = "template folder not configured"
FOLDER_MISSING = "template folder not found: "

DESCRIBED = (
    "name: {name}\n"
    "version: 1\n"
    "inputs:\n"
    '  spec_folder: {{ type: path, required: true, description: "The epic folder." }}\n'
    "  harness: {{ type: string, required: false, default: claude }}\n"
    "steps:\n"
    "  - id: sync\n"
    "    uses: git.sync\n"
    "    gate: deterministic\n"
)

DEPTH_2 = (
    "name: {name}\n"
    "version: 1\n"
    "inputs:\n"
    "  initiative_folder: {{ type: path, required: true }}\n"
    "steps:\n"
    "  - id: epics\n"
    '    for_each: "{{{{initiative_folder}}}}/epics.yaml"\n'
    "    as: epic\n"
    '    bind: {{ spec_folder: "{{{{initiative_folder}}}}/{{{{epic.spec_folder}}}}" }}\n'
    "    steps:\n"
    "      - id: stories\n"
    '        for_each: "{{{{spec_folder}}}}/stories.yaml"\n'
    "        as: story\n"
    "        steps:\n"
    "          - id: build\n"
    "            uses: agent\n"
    "            with:\n"
    "              harness: claude\n"
    "              skill: bmad-build-auto\n"
    "            prompts:\n"
    '              dispatch: "Run the skill {{skill}}: spec folder {{spec_folder}}, story id '
    '{{story_id}}."\n'
    '              rendered: "The workflow for skill {{skill}} is rendered at {{path}}; read '
    'and follow it."\n'
    "            gate: liveness\n"
)

LEAF_LOOP = (
    '  - id: {loop_id}\n    for_each: "{{{{{folder}}}}}/x.yaml"\n    as: {alias}\n'
    "    steps:\n      - id: sync\n        uses: git.sync\n        gate: deterministic\n"
)


def _reasons(response: httpx.Response) -> list[str]:
    assert response.status_code == HTTP_OK, response.text
    return [str(error["reason"]) for error in response.json()["errors"]]


def test_reload_without_the_bearer_is_a_401(client: httpx.Client) -> None:
    response = client.post(RELOAD)

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_reload_answers_the_report_or_a_folder_409(authenticated: httpx.Client) -> None:
    response = authenticated.post(RELOAD)

    if response.status_code == HTTP_CONFLICT:
        assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
        detail = response.json()["detail"]
        assert detail == FOLDER_OFF or detail.startswith(FOLDER_MISSING), detail
        return
    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body.keys() >= {"folder", "stored", "unchanged", "refused", "not_in_folder"}
    assert body["folder"]
    # A second reload with nothing edited in between stores nothing (D3).
    again = authenticated.post(RELOAD)
    assert again.status_code == HTTP_OK, again.text
    assert again.json()["stored"] == []


def test_reload_never_creates_a_version_of_a_saved_name_absent_from_the_folder(
    authenticated: httpx.Client,
) -> None:
    """Nothing is ever deleted and a saved name with no file stays exactly as saved."""
    name = unique("e2e-folder-saved")
    saved = authenticated.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": DESCRIBED.format(name=name)}
    )
    assert saved.status_code == HTTP_CREATED, saved.text

    authenticated.post(RELOAD)

    versions = authenticated.get(f"{TEMPLATES}/{name}/versions")
    assert versions.status_code == HTTP_OK
    assert versions.json()["items"] == [1]


def test_an_input_description_round_trips_and_is_null_when_absent(
    authenticated: httpx.Client,
) -> None:
    name = unique("e2e-described")

    saved = authenticated.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": DESCRIBED.format(name=name)}
    )
    assert saved.status_code == HTTP_CREATED, saved.text

    read = authenticated.get(f"{TEMPLATES}/{name}/1")
    assert read.status_code == HTTP_OK
    by_name = {decl["name"]: decl for decl in read.json()["inputs"]}
    assert by_name["spec_folder"]["description"] == "The epic folder."
    assert by_name["harness"]["description"] is None


def test_a_non_string_description_is_an_invalid_value(authenticated: httpx.Client) -> None:
    name = unique("e2e-described-bad")
    text = DESCRIBED.format(name=name).replace('"The epic folder."', "[1, 2]")

    response = authenticated.post(f"{TEMPLATES}/{name}/validate", json={"yaml": text})

    assert "invalid value" in _reasons(response)


def test_a_fresh_name_is_not_in_the_folder_on_save_read_and_list(
    authenticated: httpx.Client,
) -> None:
    name = unique("e2e-in-folder")

    saved = authenticated.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": DESCRIBED.format(name=name)}
    )
    assert saved.status_code == HTTP_CREATED, saved.text
    assert saved.json()["in_folder"] is False

    assert authenticated.get(f"{TEMPLATES}/{name}/1").json()["in_folder"] is False

    listed = authenticated.get(TEMPLATES)
    assert listed.status_code == HTTP_OK
    by_name = {item["name"]: item for item in listed.json()["items"]}
    assert by_name[name]["in_folder"] is False


def test_a_depth_2_file_with_bind_saves_validates_and_graphs_nested_groups(
    authenticated: httpx.Client,
) -> None:
    name = unique("e2e-depth-2")
    text = DEPTH_2.format(name=name)

    saved = authenticated.post(f"{TEMPLATES}/{name}/versions", json={"yaml": text})
    assert saved.status_code == HTTP_CREATED, saved.text

    validated = authenticated.get(f"{TEMPLATES}/{name}/validate")
    assert validated.status_code == HTTP_OK
    assert validated.json()["errors"] == []

    graph = authenticated.get(f"{TEMPLATES}/{name}/1/graph")
    assert graph.status_code == HTTP_OK, graph.text
    body = graph.json()
    assert [node["id"] for node in body["nodes"]] == ["epics.stories.build"]
    groups = {group["id"]: group for group in body["groups"]}
    assert set(groups) == {"epics", "epics.stories"}
    # The outer loop's group lists every node inside it, the inner loop's included.
    assert "epics.stories.build" in groups["epics"]["members"]
    assert groups["epics.stories"]["members"] == ["epics.stories.build"]


def test_a_third_loop_level_is_nested_for_each(authenticated: httpx.Client) -> None:
    name = unique("e2e-depth-3")
    text = (
        f"name: {name}\nversion: 1\ninputs:\n  f: {{ type: path, required: true }}\nsteps:\n"
        '  - id: a\n    for_each: "{{f}}/a.yaml"\n    as: x\n    steps:\n'
        '      - id: b\n        for_each: "{{f}}/b.yaml"\n        as: y\n        steps:\n'
        '          - id: c\n            for_each: "{{f}}/c.yaml"\n            as: z\n'
        "            steps:\n              - id: sync\n                uses: git.sync\n"
        "                gate: deterministic\n"
    )

    response = authenticated.post(f"{TEMPLATES}/{name}/validate", json={"yaml": text})

    assert "nested for_each" in _reasons(response)


def test_two_loops_in_one_steps_list_is_second_for_each(authenticated: httpx.Client) -> None:
    name = unique("e2e-two-loops")
    text = (
        f"name: {name}\nversion: 1\ninputs:\n  f: {{ type: path, required: true }}\nsteps:\n"
        + LEAF_LOOP.format(loop_id="one", folder="f", alias="x")
        + LEAF_LOOP.format(loop_id="two", folder="f", alias="y")
    )

    response = authenticated.post(f"{TEMPLATES}/{name}/validate", json={"yaml": text})

    assert "second for_each" in _reasons(response)


def test_a_bind_name_equal_to_an_input_is_loop_name_already_bound(
    authenticated: httpx.Client,
) -> None:
    name = unique("e2e-bind-clash")
    text = DEPTH_2.format(name=name).replace("bind: { spec_folder:", "bind: { initiative_folder:")

    response = authenticated.post(f"{TEMPLATES}/{name}/validate", json={"yaml": text})

    assert "loop name already bound" in _reasons(response)
