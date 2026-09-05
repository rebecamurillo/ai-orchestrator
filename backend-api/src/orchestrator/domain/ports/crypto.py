"""The `Crypto` port.

A Project's agent environment variables are secrets the Operator typed, and they are stored
encrypted at rest (AD-5). Which cipher does it, and where the key comes from, is an
infrastructure question: `domain/` and `application/` hold no key and import no crypto
library — they take this port, encrypt on the way in, and decrypt only when a Run is about
to hand the value to a harness process.

The adapter is `infrastructure/crypto/fernet.py`; the fake every unit test injects is
`tests/unit/fakes/crypto.py` (AD-18).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Crypto(Protocol):
    """Reversible encryption of a single value, keyed by the instance."""

    def encrypt(self, plaintext: str) -> str:
        """Return a token this instance can decrypt, and nothing else can read."""
        ...

    def decrypt(self, token: str) -> str:
        """Return the plaintext of a token this instance issued.

        A token that was tampered with, or issued under another key, is refused rather
        than decoded into whatever the bytes happen to say.
        """
        ...
