"""`GET /api/v1/metrics/catalogue` against the real stack (epic run-facts story 1, SPEC CAP-1).

The validator and the router are settled without a stack by
`tests/unit/application/test_metrics_catalogue.py` and
`tests/unit/test_metrics_catalogue_router.py`.
What only a built image can settle is that the YAML files ship as package data, that start-up
validated them (a backend that answers at all got past the check), and that the route is mounted
behind the bearer. Every assertion is structural: the catalogue's entries evolve, so no id
list, count or label is pinned here beyond the relations the story itself declares.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
CATALOGUE = "/api/v1/metrics/catalogue"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
LEVELS = frozenset({"H", "A"})
SCOPES = frozenset(
    {
        "run",
        "epic",
        "story",
        "step",
        "attempt",
        "role",
        "model",
        "repository",
        "project",
        "park",
        "gate",
        "tool",
        "conversation",
    }
)
ENTRY_FIELDS = frozenset(
    {
        "id",
        "label",
        "group",
        "level",
        "scopes",
        "unit",
        "source",
        "component_of",
        "additive",
        "missing_words",
        "limits",
        "fingerprint_group",
        "methods",
    }
)

#: Relations the story declares outright (story 1 scope), not content picked from the files.
DECLARED_COMPONENTS = {
    "tokens.thinking": "tokens.output",
    "tokens.cache_write_5m": "tokens.cache_write",
    "tokens.cache_write_1h": "tokens.cache_write",
}


def _items(authenticated: httpx.Client) -> list[dict[str, Any]]:
    response = authenticated.get(CATALOGUE)
    assert response.status_code == HTTP_OK, response.text
    items = response.json()["items"]
    assert isinstance(items, list)
    return items


def test_the_catalogue_refuses_a_request_without_the_bearer(client: httpx.Client) -> None:
    response = client.get(CATALOGUE)

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith("application/problem+json")


def test_the_shipped_catalogue_is_served_in_the_list_envelope(
    authenticated: httpx.Client,
) -> None:
    response = authenticated.get(CATALOGUE)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert "items" in body
    assert body["items"], "the shipped catalogue reached the image empty"


def test_every_entry_carries_exactly_the_catalogue_fields(authenticated: httpx.Client) -> None:
    for entry in _items(authenticated):
        assert set(entry) == ENTRY_FIELDS, entry.get("id")


def test_every_entry_is_well_formed(authenticated: httpx.Client) -> None:
    for entry in _items(authenticated):
        entry_id = entry["id"]
        assert isinstance(entry_id, str) and ID_PATTERN.match(entry_id), entry_id
        assert entry["level"] in LEVELS, entry_id
        assert entry["scopes"] and set(entry["scopes"]) <= SCOPES, entry_id
        assert entry["additive"] in (True, False, "within_scope_type"), entry_id
        assert isinstance(entry["fingerprint_group"], bool), entry_id
        assert isinstance(entry["missing_words"], list), entry_id


def test_ids_are_unique(authenticated: httpx.Client) -> None:
    ids = [entry["id"] for entry in _items(authenticated)]

    assert len(ids) == len(set(ids))


def test_every_component_of_names_a_catalogued_id(authenticated: httpx.Client) -> None:
    items = _items(authenticated)
    ids = {entry["id"] for entry in items}

    for entry in items:
        parent = entry["component_of"]
        assert parent is None or parent in ids, (entry["id"], parent)


def test_the_declared_token_components_are_served(authenticated: httpx.Client) -> None:
    by_id = {entry["id"]: entry for entry in _items(authenticated)}

    for child, parent in DECLARED_COMPONENTS.items():
        assert by_id[child]["component_of"] == parent


def test_every_entry_has_described_methods_numbered_from_one(
    authenticated: httpx.Client,
) -> None:
    for entry in _items(authenticated):
        methods = entry["methods"]
        assert isinstance(methods, list) and methods, entry["id"]
        numbers = [method["n"] for method in methods]
        assert numbers[0] >= 1 and numbers == sorted(set(numbers)), entry["id"]
        for method in methods:
            assert method["description"].strip(), (entry["id"], method["n"])
            assert isinstance(method["parameters"], dict), (entry["id"], method["n"])
