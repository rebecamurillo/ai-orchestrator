"""`main()` wires one `ChatChannels` and closes it at shutdown (story 3-4).

`ChatChannels` owns one pooled HTTP client (story 3-1), so the composition root that builds it
must close it once uvicorn returns, and also when uvicorn raises.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator import main as main_module
from orchestrator.api.providers_channel import CHAT
from orchestrator.infrastructure.chat import ChatChannels
from orchestrator.infrastructure.settings import Settings


class RecordingChannels(ChatChannels):
    instances: list[RecordingChannels] = []  # noqa: RUF012 — a per-test record, reset below

    def __init__(self) -> None:
        super().__init__()
        self.closed = 0
        RecordingChannels.instances.append(self)

    def close(self) -> None:
        self.closed += 1
        super().close()


@pytest.fixture
def channels(monkeypatch: pytest.MonkeyPatch) -> type[RecordingChannels]:
    RecordingChannels.instances = []
    monkeypatch.setattr(main_module, "ChatChannels", RecordingChannels)
    monkeypatch.setattr(main_module, "run_migrations", lambda settings: "head")
    return RecordingChannels


def test_the_served_application_holds_the_factory_and_main_closes_it(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, channels: type[RecordingChannels]
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        (built,) = channels.instances
        captured["chat"] = getattr(app.state, CHAT)
        captured["closed_while_serving"] = built.closed

    monkeypatch.setattr(main_module.uvicorn, "run", fake_run)

    main_module.main()

    (built,) = channels.instances
    assert captured == {"chat": built, "closed_while_serving": 0}
    assert built.closed == 1


def test_the_factory_is_closed_when_serving_raises(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, channels: type[RecordingChannels]
) -> None:
    def exploding_run(app: Any, **kwargs: Any) -> None:
        raise RuntimeError("address already in use")

    monkeypatch.setattr(main_module.uvicorn, "run", exploding_run)

    with pytest.raises(RuntimeError, match="address already in use"):
        main_module.main()

    (built,) = channels.instances
    assert built.closed == 1


def test_an_application_built_without_one_holds_none(env: dict[str, str]) -> None:
    app = main_module.create_app(Settings())

    assert getattr(app.state, CHAT) is None
    assert CHAT == "chat"
