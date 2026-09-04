"""The one `/api/v1` operation, read as a router rather than through the application.

`test_bearer_auth.py` drives `/api/v1/ping` over ASGI to prove the credential dependency
fires; what is left unasserted there is the router itself — the path it declares, the method
it answers, and the payload model the exported contract is derived from (AD-3). A router
that silently changed its response model would keep every bearer test green and change the
generated TypeScript.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from orchestrator.api.routers.ping import Pong, ping, router


def _routes() -> list[APIRoute]:
    return [route for route in router.routes if isinstance(route, APIRoute)]


def test_the_router_declares_one_operation() -> None:
    assert [(route.path, sorted(route.methods)) for route in _routes()] == [("/ping", ["GET"])]


def test_the_operation_carries_a_summary_and_a_response_model() -> None:
    """Both land in `contracts/openapi.json`, which the web-client types are generated from."""
    route = _routes()[0]

    assert route.response_model is Pong
    assert route.summary


def test_the_handler_answers_pong() -> None:
    assert ping() == Pong(pong=True)


def test_the_payload_has_one_boolean_field() -> None:
    assert Pong.model_json_schema()["properties"] == {"pong": {"title": "Pong", "type": "boolean"}}
