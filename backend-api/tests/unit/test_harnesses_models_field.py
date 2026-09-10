"""`GET /harnesses` states which models this instance offers per harness (FR-27, story 7.3).

The Operator ruled in session on 2026-09-10 that `HarnessOut` may gain `models` and that the
two closed-set equalities pinning its field set — `tests/unit/test_harnesses_router.py::
test_harness_out_of_renders_every_field` and `tests/e2e/test_harnesses.py::
test_the_response_is_the_one_list_envelope` — may gain that one name. Both stay exact and both
went from seven names to eight, the same edit the Epic 5 CAP-8 ruling made to the same two
files. This module is the coverage that strictly exceeds those two lines: they say the key
exists, and everything below says what is in it, where it comes from, and what it is for.

**What it is for.** `local` dispatches to models the host itself serves, whose aliases are this
instance's own choice (`LOCAL_MODELS`, PRD §8 items 7-8). A free-text model field for that
harness invites a name the Gateway serves no route for — a Run that pre-flights clean, starts,
and fails at the first model call. The New workflow turns the field into a select over exactly
these values, so the offer and the routing table cannot disagree.

**Why it is composed and not stored.** Every field on the `harness` row is something a readiness
run observed. Which models the Gateway currently routes is not: it changes with an `.env` edit
and a restart, with no migration and no readiness run in between, so a stored copy would go
stale exactly when it mattered (`infrastructure/harness/models.py`).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import harness_models, harness_ports
from orchestrator.api.schemas.harnesses import HarnessOut
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.domain.entities.harness import HARNESS_NAMES, Harness
from orchestrator.infrastructure.harness.models import HARNESS_MODEL_SETTINGS, model_table
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.harnesses import FakeHarnessRepository

HTTP_OK = 200
HARNESSES = "/api/v1/harnesses"
#: `.env.example` ships `LOCAL_MODELS=local-coder,local-general` (AD-20).
SHIPPED_MODELS = ["local-coder", "local-general"]


class Api:
    """One application over the real providers' shape, with a fake repository."""

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.harnesses = FakeHarnessRepository(
            [Harness(name=name, version_pin="x") for name in HARNESS_NAMES]
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[harness_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> HarnessPorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return HarnessPorts(uow=self.uow, harnesses=self.harnesses)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def items_of(api: Api) -> dict[str, dict[str, object]]:
    async with api.client() as client:
        response = await client.get(HARNESSES)
    assert response.status_code == HTTP_OK
    return {item["name"]: item for item in response.json()["items"]}


# ── the table the field is composed from ─────────────────────────────────────


def test_only_the_local_harness_has_a_models_setting() -> None:
    """`claude` and `codex` take a model name their provider publishes; `local`'s aliases are
    this instance's own. A name absent here answers the empty list, which is a statement."""
    assert set(HARNESS_MODEL_SETTINGS) == {"local"}


def test_every_name_in_the_table_is_a_harness_the_domain_declares() -> None:
    assert set(HARNESS_MODEL_SETTINGS) <= set(HARNESS_NAMES)


def test_the_table_reads_the_shipped_contracts_own_value(env: dict[str, str]) -> None:
    assert model_table(Settings())["local"] == tuple(SHIPPED_MODELS)


def test_the_table_follows_the_environment_rather_than_a_stored_row(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Operator's `.env` edit reaches the offer at the next restart, with no migration —
    which is the whole argument for composing this per request."""
    monkeypatch.setenv("LOCAL_MODELS", "qwen-coder,deepseek-v3")

    assert model_table(Settings())["local"] == ("qwen-coder", "deepseek-v3")


def test_the_table_is_immutable_so_one_response_cannot_edit_the_next(
    env: dict[str, str],
) -> None:
    assert isinstance(model_table(Settings())["local"], tuple)


# ── the schema ───────────────────────────────────────────────────────────────


def test_the_field_defaults_to_empty_so_existing_callers_keep_compiling() -> None:
    """Defaulted on the `last_readiness_run_id`/`lines` precedent: the generated client type
    marks it optional, so `web-client`'s frozen fixtures need no edit (AD-3)."""
    out = HarnessOut.of(Harness(name="codex", version_pin="0.152.1"))

    assert out.models == []


def test_the_field_is_rendered_always_even_when_it_is_empty() -> None:
    """Which is what makes the two closed-set equalities see it for every harness, not only
    for the one that has models."""
    dumped = HarnessOut.of(Harness(name="codex", version_pin="0.152.1")).model_dump()

    assert "models" in dumped


def test_the_field_carries_the_models_it_is_given_in_their_own_order() -> None:
    out = HarnessOut.of(Harness(name="local", version_pin="1.18.26"), SHIPPED_MODELS)

    assert out.models == SHIPPED_MODELS


def test_the_field_is_a_copy_rather_than_the_callers_own_sequence() -> None:
    """The table it comes from is shared across requests; a response model holding a
    reference into it would let one request's serialization touch the next one's."""
    given = list(SHIPPED_MODELS)

    out = HarnessOut.of(Harness(name="local", version_pin="1.18.26"), given)
    given.append("smuggled")

    assert out.models == SHIPPED_MODELS


# ── the route ────────────────────────────────────────────────────────────────


async def test_the_local_row_lists_the_configured_aliases(api: Api) -> None:
    items = await items_of(api)

    assert items["local"]["models"] == SHIPPED_MODELS


async def test_every_other_harness_lists_no_models(api: Api) -> None:
    """The brief's own wording: "empty for others"."""
    items = await items_of(api)

    assert items["claude"]["models"] == []
    assert items["codex"]["models"] == []


async def test_the_route_composes_the_models_from_this_instances_settings(
    env: dict[str, str],
) -> None:
    """Overriding the one dependency proves the router reads it rather than the row."""
    api = Api(env)
    api.app.dependency_overrides[harness_models] = lambda: {"local": ("only-this-one",)}

    items = await items_of(api)

    assert items["local"]["models"] == ["only-this-one"]


async def test_the_rows_own_fields_are_untouched_by_the_join(api: Api) -> None:
    """The models are added beside the stored row, never in place of anything on it."""
    items = await items_of(api)

    assert items["local"]["enabled"] is False
    assert items["local"]["version_pin"] == "x"
    assert items["local"]["lines"] == []
