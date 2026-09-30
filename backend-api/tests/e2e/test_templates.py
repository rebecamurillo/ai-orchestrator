"""The Template Version round-trip against the running stack (SPEC CAP-3, FR-6).

The unit suite proves the rules over the fake repository: `save_version`'s next-number and
name checks, `seed_shipped`'s retry-until-no-progress ordering, `calls`/`called_by`. What
only a real Postgres and a real container start-up settle is the claim this story exists
for: that every shipped Template is actually seeded — through the real migration, the real
repository, the real `TEMPLATES_DIR` — before the process answers a request, and that a
saved version's YAML comes back byte for byte.

The shipped Templates are never posted a new version here: this suite may run twice against
the same stack (no `DELETE` exists), and every shipped name must stay exactly
`versions: [1]` however many times it runs. Every write below targets a name of its own,
made unique per run.

Revised 2026-09-30 (Operator decision: the mono-repo `initiative` and `story-run` workflows
are retired to `templates/drafts/`, not seeded): the shipped names are read off the
`templates/` directory instead of being listed, and the `called_by` leg — which read the
shipped `initiative@1 -> epic@1` pin — is asserted over a caller/leaf pair of this suite's
own, so no shipped file is pinned (hard rule 6).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
import pytest

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

TEMPLATES = "/api/v1/templates"

#: `backend-api/tests/e2e/test_templates.py` -> the repository root -> what the image seeds.
SHIPPED_DIR = Path(__file__).resolve().parents[3] / "templates"

#: The version number a save answers with once a name already holds one version.
SECOND_VERSION = 2

LEAF = (
    "name: {name}\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)


#: A caller of this suite's own: one loop, one collapsed call to a leaf pinned at version 1.
CALLER = (
    "name: {name}\n"
    "version: 1\n"
    "inputs:\n"
    "  list_folder: {{ type: path, required: true }}\n"
    "steps:\n"
    "  - id: entries\n"
    '    for_each: "{{{{list_folder}}}}/entries.yaml"\n'
    "    as: entry\n"
    "    steps:\n"
    "      - id: call\n"
    "        uses: template\n"
    "        with:\n"
    "          name: {leaf}\n"
    "          version: 1\n"
)


@pytest.fixture
def leaf_name() -> str:
    """A Template name no earlier run of this suite can have taken."""
    return f"e2e-leaf-{uuid4().hex}"


@pytest.fixture
def caller_name() -> str:
    """A caller name no earlier run of this suite can have taken."""
    return f"e2e-caller-{uuid4().hex}"


def test_every_shipped_template_is_seeded_at_startup(authenticated: httpx.Client) -> None:
    """Every `*.yaml` directly under `templates/` — the names derive from the directory, so
    a shipped file added, renamed or retired to `templates/drafts/` never edits this test."""
    shipped = sorted(path.stem for path in SHIPPED_DIR.glob("*.yaml"))
    assert shipped, SHIPPED_DIR

    response = authenticated.get(TEMPLATES)

    assert response.status_code == HTTP_OK
    by_name = {item["name"]: item for item in response.json()["items"]}
    for name in shipped:
        assert name in by_name, (name, sorted(by_name))
        assert 1 in by_name[name]["versions"], by_name[name]

    assert response.json()["next_cursor"] is None


def test_epic_1_shows_its_call_and_its_inputs(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{TEMPLATES}/epic/1")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["calls"] == [{"name": "story", "version": 1}]
    assert isinstance(body["called_by"], list)
    assert body["pinned_by"] == 0
    # Revised: an exact input count pinned shipped template content, which the
    # exemplar-freeze ruling (2026-09-10) forbids — and it broke the moment S5 added
    # `done_checkpoint` to epic@1 (multi-repo initiative, 2026-09-23). Structural in its
    # place: every declared input carries its full shape, whatever epic@1 currently lists.
    assert body["inputs"], body["inputs"]
    for decl in body["inputs"]:
        assert decl.keys() >= {"name", "type", "required", "default", "values"}, decl
        assert isinstance(decl["name"], str) and decl["name"]
        assert isinstance(decl["type"], str) and decl["type"]
        assert isinstance(decl["required"], bool)
        assert isinstance(decl["values"], list)
    assert body["hash"]
    assert body["created_at"]


def test_a_saved_caller_is_its_leafs_called_by_and_the_leaf_is_its_call(
    authenticated: httpx.Client, leaf_name: str, caller_name: str
) -> None:
    """`calls` is recorded at save time from the text, and `called_by` is its inverse read
    back through the real repository — over a pair of this suite's own, made unique per run."""
    leaf = authenticated.post(
        f"{TEMPLATES}/{leaf_name}/versions", json={"yaml": LEAF.format(name=leaf_name)}
    )
    assert leaf.status_code == HTTP_CREATED, leaf.text
    caller_text = CALLER.format(name=caller_name, leaf=leaf_name)
    caller = authenticated.post(f"{TEMPLATES}/{caller_name}/versions", json={"yaml": caller_text})
    assert caller.status_code == HTTP_CREATED, caller.text

    caller_body = authenticated.get(f"{TEMPLATES}/{caller_name}/1").json()
    leaf_body = authenticated.get(f"{TEMPLATES}/{leaf_name}/1").json()

    assert caller_body["calls"] == [{"name": leaf_name, "version": 1}]
    assert caller_body["called_by"] == []
    assert leaf_body["calls"] == []
    assert leaf_body["called_by"] == [{"name": caller_name, "version": 1}]
    # `pinned_by` counts Runs that pin the version (AD-15), not callers: none was started.
    assert leaf_body["pinned_by"] == 0


def test_reading_an_unknown_template_is_a_404(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{TEMPLATES}/does-not-exist/1")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_saved_version_round_trips_byte_for_byte(
    authenticated: httpx.Client, leaf_name: str
) -> None:
    text = LEAF.format(name=leaf_name)

    created = authenticated.post(f"{TEMPLATES}/{leaf_name}/versions", json={"yaml": text})
    assert created.status_code == HTTP_CREATED, created.text
    assert created.json()["version"] == 1

    read_back = authenticated.get(f"{TEMPLATES}/{leaf_name}/1")
    assert read_back.status_code == HTTP_OK
    assert read_back.json()["yaml"] == text

    listed = authenticated.get(TEMPLATES)
    by_name = {item["name"]: item for item in listed.json()["items"]}
    assert by_name[leaf_name]["versions"] == [1]


def test_a_second_version_never_changes_the_first(
    authenticated: httpx.Client, leaf_name: str
) -> None:
    first_text = LEAF.format(name=leaf_name)
    authenticated.post(f"{TEMPLATES}/{leaf_name}/versions", json={"yaml": first_text})
    second_text = first_text.replace("version: 1", "version: 2")

    created = authenticated.post(f"{TEMPLATES}/{leaf_name}/versions", json={"yaml": second_text})

    assert created.status_code == HTTP_CREATED, created.text
    assert created.json()["version"] == SECOND_VERSION

    still_original = authenticated.get(f"{TEMPLATES}/{leaf_name}/1")
    assert still_original.json()["yaml"] == first_text

    versions = authenticated.get(f"{TEMPLATES}/{leaf_name}/versions")
    assert versions.json()["items"] == [1, SECOND_VERSION]


def test_the_wrong_next_version_number_is_a_422(
    authenticated: httpx.Client, leaf_name: str
) -> None:
    wrong = LEAF.format(name=leaf_name).replace("version: 1", "version: 5")

    response = authenticated.post(f"{TEMPLATES}/{leaf_name}/versions", json={"yaml": wrong})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert "version must be 1" in response.json()["detail"]


def test_a_name_that_does_not_match_the_yaml_is_a_422(authenticated: httpx.Client) -> None:
    response = authenticated.post(
        f"{TEMPLATES}/not-the-right-name/versions",
        json={"yaml": LEAF.format(name="something-else")},
    )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert "name must be not-the-right-name" in response.json()["detail"]


def _by_line_and_reason(errors: list[dict[str, object]]) -> list[tuple[object, object]]:
    return sorted((entry["line"], entry["reason"]) for entry in errors)


def test_invalid_yaml_is_200_from_validate_and_422_from_versions_with_the_same_errors(
    authenticated: httpx.Client, leaf_name: str
) -> None:
    invalid = "not: [valid\n"

    validated = authenticated.post(f"{TEMPLATES}/{leaf_name}/validate", json={"yaml": invalid})
    assert validated.status_code == HTTP_OK
    assert validated.json()["errors"]

    saved = authenticated.post(f"{TEMPLATES}/{leaf_name}/versions", json={"yaml": invalid})
    assert saved.status_code == HTTP_UNPROCESSABLE
    # the same problem, by line and reason — `/validate`'s 200 body and the 422's `errors[]`
    # differ only in whether a null field is omitted (`Problem` omits, this response doesn't)
    assert _by_line_and_reason(saved.json()["errors"]) == _by_line_and_reason(
        validated.json()["errors"]
    )

    missing = authenticated.get(f"{TEMPLATES}/{leaf_name}/1")
    assert missing.status_code == HTTP_NOT_FOUND


def test_validating_the_latest_stored_version_without_a_body(
    authenticated: httpx.Client, leaf_name: str
) -> None:
    text = LEAF.format(name=leaf_name)
    authenticated.post(f"{TEMPLATES}/{leaf_name}/versions", json={"yaml": text})

    response = authenticated.get(f"{TEMPLATES}/{leaf_name}/validate")

    assert response.status_code == HTTP_OK
    assert response.json() == {"errors": [], "unvalidated": []}
