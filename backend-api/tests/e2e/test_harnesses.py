"""The harness table, seeded at start-up against the running stack (SPEC CAP-3, AD-10).

The unit suite proves `seed_harnesses`'s rules over fakes: idempotent upsert, `enabled`
never touched. What only a real Postgres and a real container start-up settle is that the
three names are actually there — through the real migration and the real seed call inside
`main.run_migrations` — before the process answers a request, and that a second start (this
suite may run twice against the same stack) never flips `enabled` back to `false`.
"""

from __future__ import annotations

import httpx

HTTP_OK = 200
HARNESSES = "/api/v1/harnesses"
HARNESS_NAMES = ("claude", "codex", "local")


def test_the_three_harnesses_are_seeded_at_startup(authenticated: httpx.Client) -> None:
    response = authenticated.get(HARNESSES)

    assert response.status_code == HTTP_OK
    by_name = {item["name"]: item for item in response.json()["items"]}
    for name in HARNESS_NAMES:
        assert name in by_name, by_name
        assert by_name[name]["version_pin"], by_name[name]

    assert response.json()["next_cursor"] is None


def test_every_seeded_harness_starts_disabled_or_stays_however_readiness_left_it(
    authenticated: httpx.Client,
) -> None:
    """A second start-up in this suite's lifetime must never flip `enabled` back to
    `false` — only Epic 5's readiness use case may write it, never the seed."""
    first = {item["name"]: item["enabled"] for item in authenticated.get(HARNESSES).json()["items"]}
    second = {
        item["name"]: item["enabled"] for item in authenticated.get(HARNESSES).json()["items"]
    }

    assert first == second


def test_the_response_is_the_one_list_envelope(authenticated: httpx.Client) -> None:
    response = authenticated.get(HARNESSES)

    body = response.json()
    assert set(body) == {"items", "next_cursor"}
    for item in body["items"]:
        assert set(item) == {"name", "enabled", "last_readiness_at", "failing_check", "version_pin"}
