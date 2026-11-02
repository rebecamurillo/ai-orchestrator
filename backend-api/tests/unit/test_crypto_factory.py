"""`infrastructure/crypto/factory.py` — the deferred `Crypto` builder `main.py` wires.

It moved out of `main.py` unchanged (story 3-4, to keep the composition root under the cap),
so the name `orchestrator.main.crypto_factory` must still resolve to it.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from orchestrator import main
from orchestrator.infrastructure.crypto import FernetCrypto
from orchestrator.infrastructure.crypto.factory import crypto_factory
from orchestrator.infrastructure.settings import Settings


def test_main_still_exports_the_same_factory() -> None:
    assert main.crypto_factory is crypto_factory


def test_the_placeholder_key_is_refused_only_on_first_use(env: dict[str, str]) -> None:
    build = crypto_factory(Settings())

    with pytest.raises(ValueError, match="ORCHESTRATOR_SECRET_KEY"):
        build()


def test_a_real_key_builds_the_fernet_adapter_once(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", Fernet.generate_key().decode())

    build = crypto_factory(Settings())

    assert isinstance(build(), FernetCrypto)
    assert build() is build()
