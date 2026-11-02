"""A token the current key cannot open is the port's `DecryptionError` (story 3-4 review).

The Fernet adapter still raises an `InvalidToken` too, so every existing caller of `decrypt`
behaves as it did. The shared fake raises the same port error.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from orchestrator.domain.ports.crypto import DecryptionError
from orchestrator.infrastructure.crypto import FernetCrypto
from tests.unit.fakes.crypto import FakeCrypto


def test_a_token_under_a_rotated_key_is_a_decryption_error() -> None:
    token = FernetCrypto(Fernet.generate_key().decode()).encrypt("secret")
    rotated = FernetCrypto(Fernet.generate_key().decode())

    with pytest.raises(DecryptionError) as caught:
        rotated.decrypt(token)

    assert isinstance(caught.value, InvalidToken)
    assert "secret" not in str(caught.value)


def test_a_malformed_token_is_a_decryption_error() -> None:
    with pytest.raises(DecryptionError):
        FernetCrypto(Fernet.generate_key().decode()).decrypt("not-a-token")


def test_the_fake_refuses_a_foreign_token_with_the_same_error() -> None:
    with pytest.raises(DecryptionError, match="never issued"):
        FakeCrypto().decrypt("fake-enc:9:Zm9v")


def test_the_port_error_stays_a_value_error() -> None:
    assert issubclass(DecryptionError, ValueError)
