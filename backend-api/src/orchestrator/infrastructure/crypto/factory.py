"""The deferred `Crypto` builder the composition root wires (`main.py` re-exports it)."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache

from orchestrator.domain.ports.crypto import Crypto
from orchestrator.infrastructure.crypto.fernet import FernetCrypto
from orchestrator.infrastructure.settings import Settings

#: How a request reaches the instance key.
CryptoFactory = Callable[[], Crypto]


def crypto_factory(settings: Settings) -> CryptoFactory:
    """A `Crypto` that is built on first use, and then once.

    Constructing it here would refuse the `.env.example` placeholder at start-up, which is
    the value `main()` is called with in two unit tests. The adapter still validates its
    key strictly; the refusal simply moves from import time to the first request that needs
    a Project port — any of the four, read or write — where it becomes a 500.
    """

    @cache
    def build() -> Crypto:
        return FernetCrypto(settings.orchestrator_secret_key.get_secret_value())

    return build
