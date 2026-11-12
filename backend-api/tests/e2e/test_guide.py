"""The served guide against the running stack (initiative orchestrator-instance-guide, epic 1:
SPEC CAP-1, CAP-3, CAP-4, CAP-6; member AD-1 amended, AD-15 amended, AD-32, AD-35).

The unit suite proves the routes over guides it builds in `tmp_path`. What only the running
stack settles is that the image really built the guide (the Dockerfile's `build_guide` step)
into the directory the routes read, that the routes answer with no bearer while `/api/v1/*`
still refuses, and that a finding the real validator emits names a page the real build wrote.

No assertion reads a page's prose or pins which pages ship (member hard rule 6): every check is
structure — the index layout, media types, front matter, the host line, codes and page ids.
"""

from __future__ import annotations

import re
from uuid import uuid4

import httpx
import jsonschema
import pytest
import yaml

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404

LLMS = "/llms.txt"
VERSION = "/api/v1/version"
TEMPLATES = "/api/v1/templates"
PROJECTS = "/api/v1/projects"

UNAVAILABLE = "refusal-guide-unavailable"
UNKNOWN_KEY = "template-unknown-key"
HOST_LINE = "Local agent on the host or the user only."
INDEX_LINK = re.compile(r"^- \[[^\]]+\]\(/guide/(?P<id>[a-z0-9-]+(?:/[a-z0-9-]+)*)\.md\)$")

LEAF = (
    "name: {name}\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)


def _sections(text: str) -> dict[str, list[str]]:
    """`## Title` → the page ids its link lines name."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:], [])
        elif current is not None and line:
            match = INDEX_LINK.match(line)
            assert match, f"not an index link: {line!r}"
            current.append(match["id"])
    return sections


def _front_matter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    assert lines[0] == "---", "a page opens on its front matter"
    end = lines.index("---", 1)
    return dict(line.split(": ", 1) for line in lines[1:end])


def _assert_refusal(response: httpx.Response) -> None:
    assert response.status_code == HTTP_NOT_FOUND, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == UNAVAILABLE
    assert body["guide"] == f"errors/{UNAVAILABLE}"


@pytest.fixture(scope="module")
def index(stack: str) -> str:
    with httpx.Client(base_url=stack, timeout=10.0) as client:
        response = client.get(LLMS)
    assert response.status_code == HTTP_OK, response.text
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    return response.text


def test_the_index_answers_without_the_bearer_in_the_llmstxt_layout(index: str) -> None:
    lines = index.splitlines()
    assert lines[0] == "# ai-orchestrator guide"
    assert lines[1] == ""
    assert re.fullmatch(
        r"> The guide for release \S+\. Every page is at /guide/\{id\}\.md\.", lines[2]
    )
    sections = _sections(index)
    assert list(sections) == [s for s in ("Guide", "Host", "Errors") if s in sections]
    assert all(page.startswith("errors/") for page in sections.get("Errors", []))
    assert not any(page.startswith("errors/") for page in sections.get("Guide", []))


def test_every_listed_page_is_served_open_and_stamped_with_the_instance_release(
    client: httpx.Client, authenticated: httpx.Client, index: str
) -> None:
    """AC-8: the page's `release` is the instance's `app_version`."""
    version = authenticated.get(VERSION)
    assert version.status_code == HTTP_OK, version.text
    release = version.json()["app_version"]
    assert f"> The guide for release {release}." in index

    sections = _sections(index)
    for section, ids in sections.items():
        for page_id in ids:
            response = client.get(f"/guide/{page_id}.md")
            assert response.status_code == HTTP_OK, f"{page_id}: {response.text}"
            assert response.headers["content-type"] == "text/markdown; charset=utf-8"
            meta = _front_matter(response.text)
            assert meta["release"] == release, page_id
            assert meta["title"], page_id
            assert meta["kind"] in {"page", "procedure"}, page_id
            assert (meta["audience"] == "host") == (section == "Host"), page_id
            if meta["audience"] == "host":
                assert HOST_LINE in response.text.splitlines(), page_id


def test_the_open_routes_set_no_cookie_and_no_cors_header(client: httpx.Client, index: str) -> None:
    first = _sections(index)["Guide"][0]
    for path in (LLMS, f"/guide/{first}.md", "/schemas/workflow.json", "/guide/nope.md"):
        response = client.get(path, headers={"Origin": "https://elsewhere.example"})
        assert "set-cookie" not in response.headers, path
        assert not any(h.lower().startswith("access-control-") for h in response.headers), path


def test_the_instance_data_still_needs_the_bearer(client: httpx.Client) -> None:
    assert client.get(PROJECTS).status_code == HTTP_UNAUTHORIZED
    assert client.get(TEMPLATES).status_code == HTTP_UNAUTHORIZED


def test_an_unknown_page_or_schema_and_a_path_escape_answer_the_refusal(
    client: httpx.Client,
) -> None:
    missing = f"no-such-page-{uuid4().hex}"
    _assert_refusal(client.get(f"/guide/{missing}.md"))
    _assert_refusal(client.get(f"/schemas/{missing}.json"))
    _assert_refusal(client.get("/schemas/Workflow.json"))
    escape = client.get("/guide/%2e%2e/VERSION.md")
    assert escape.status_code == HTTP_NOT_FOUND, escape.text


def test_the_refusal_names_a_page_the_instance_serves(client: httpx.Client) -> None:
    page = client.get(f"/guide/errors/{UNAVAILABLE}.md")

    assert page.status_code == HTTP_OK, page.text
    assert _front_matter(page.text)["title"] == UNAVAILABLE


@pytest.mark.parametrize("name", ["workflow", "spec-folder"])
def test_each_format_description_is_a_served_draft_2020_12_schema(
    client: httpx.Client, name: str
) -> None:
    response = client.get(f"/schemas/{name}.json")

    assert response.status_code == HTTP_OK, response.text
    assert response.headers["content-type"].startswith("application/schema+json")
    schema = response.json()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == f"/schemas/{name}.json"
    jsonschema.Draft202012Validator.check_schema(schema)


def test_the_served_workflow_schema_and_the_validator_agree_on_an_unknown_key(
    client: httpx.Client, authenticated: httpx.Client
) -> None:
    """AC-12, HTTP half: one fixture, two checks, same verdict — and the finding resolves."""
    schema = client.get("/schemas/workflow.json").json()
    name = f"e2e-guide-{uuid4().hex}"
    good = LEAF.format(name=name)
    bad = good + "colour: blue\n"

    jsonschema.validate(yaml.safe_load(good), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(yaml.safe_load(bad), schema)

    accepted = authenticated.post(f"{TEMPLATES}/{name}/validate", json={"yaml": good})
    assert accepted.status_code == HTTP_OK, accepted.text
    assert accepted.json()["errors"] == []

    refused = authenticated.post(f"{TEMPLATES}/{name}/validate", json={"yaml": bad})
    assert refused.status_code == HTTP_OK, refused.text
    findings = [e for e in refused.json()["errors"] if e.get("code") == UNKNOWN_KEY]
    assert findings, refused.text
    finding = findings[0]
    assert finding["guide"] == f"errors/{UNKNOWN_KEY}"
    assert isinstance(finding["line"], int)

    page = client.get(f"/guide/{finding['guide']}.md")
    assert page.status_code == HTTP_OK, page.text
    assert _front_matter(page.text)["title"] == UNKNOWN_KEY


def test_the_spec_folder_schema_refuses_an_entry_without_its_required_fields(
    client: httpx.Client,
) -> None:
    schema = client.get("/schemas/spec-folder.json").json()
    for kind in ("epics", "stories"):
        definition = {**schema["$defs"][kind], "$defs": schema["$defs"]}
        assert definition["type"] == "array"
        required = definition["items"]["required"]
        assert "id" in required
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([{"unrelated": 1}], definition)
        jsonschema.validate([{field: "1" for field in required}], definition)
