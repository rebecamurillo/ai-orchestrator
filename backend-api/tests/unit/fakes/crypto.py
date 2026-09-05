"""In-memory `Crypto` — the one fake for that port (AD-18). Reuse it; do not write another.

Three properties are copied from the Fernet adapter, because a use case tested against a
weaker double would pass here and fail in production:

- **The token is not the plaintext.** An identity fake would let "the value was stored
  encrypted" pass for code that stored it in clear.
- **Two encryptions of one value differ.** Fernet embeds a timestamp and a random IV, so a
  test that compared ciphertexts to decide "unchanged" would be asserting something the
  real adapter never guarantees.
- **A token it never issued is refused.** Fernet rejects a tampered or foreign token; a
  fake that decoded anything would hide a use case decrypting the wrong value.
"""

from __future__ import annotations

import base64

PREFIX = "fake-enc"


class FakeCrypto:
    """A reversible, non-deterministic, non-identity encoder that records what it was asked."""

    def __init__(self) -> None:
        self.encrypted: list[str] = []
        self.decrypted: list[str] = []
        self._issued: dict[str, str] = {}
        self._issue_count = 0

    def encrypt(self, plaintext: str) -> str:
        self._issue_count += 1
        body = base64.urlsafe_b64encode(plaintext.encode()).decode()
        token = f"{PREFIX}:{self._issue_count}:{body}"
        self._issued[token] = plaintext
        self.encrypted.append(plaintext)
        return token

    def decrypt(self, token: str) -> str:
        if token not in self._issued:
            raise ValueError(f"{PREFIX}: this instance never issued that token")
        self.decrypted.append(token)
        return self._issued[token]
