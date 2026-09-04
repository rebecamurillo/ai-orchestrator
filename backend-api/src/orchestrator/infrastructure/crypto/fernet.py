"""The `Crypto` adapter: Fernet under `ORCHESTRATOR_SECRET_KEY` (AD-5).

`ORCHESTRATOR_SECRET_KEY` **is** the Fernet key — it is not derived, padded, hashed or
truncated into one. A deriving adapter would accept any string the Operator typed and
silently produce a keyspace far smaller than Fernet's; refusing the key instead means a
misconfigured instance is told what to do, once, at the first write.

Fernet is AES-128-CBC with an HMAC-SHA256 tag over `version ‖ timestamp ‖ IV ‖ ciphertext`.
Two properties matter to the rest of this system: the same value encrypted twice produces
different tokens, because the IV is random — so a test that compared ciphertexts to decide
"the value did not change" would be asserting something untrue; and a token that was
altered by one byte, or issued under another key, is refused rather than decoded, so a
Project's variables cannot be swapped in the database without the swap being noticed.

Nothing in this module logs, and no message it raises contains a key or a value.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

#: The one command that produces a valid value, quoted into the message that asks for one.
KEY_COMMAND = (
    'python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"'
)

#: What the Operator is told when the configured key is not a Fernet key.
KEY_REASON = (
    "ORCHESTRATOR_SECRET_KEY is not a Fernet key: it must be 32 url-safe base64-encoded "
    f"bytes, and it is the key itself, never a passphrase it is derived from. Generate one "
    f"with: {KEY_COMMAND}"
)

#: The encoding a token and a plaintext travel in. Fernet works on bytes; this API is `str`.
ENCODING = "utf-8"


class FernetCrypto:
    """Reversible encryption of one value under the instance key."""

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode(ENCODING))
        except (ValueError, TypeError) as error:
            # the message never repeats the key, so a failed start-up logs no secret
            raise ValueError(KEY_REASON) from error

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode(ENCODING)).decode(ENCODING)

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode(ENCODING)).decode(ENCODING)
