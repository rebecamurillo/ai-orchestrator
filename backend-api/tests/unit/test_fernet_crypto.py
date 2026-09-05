"""The Fernet adapter: what it guarantees, and what it refuses (AD-5).

`.env.example` carries `ORCHESTRATOR_SECRET_KEY=change-me-fernet-key`, which is *not* a
Fernet key — deliberately, so that an instance nobody configured cannot encrypt anything.
Every test here therefore builds its own key with `Fernet.generate_key()` rather than
reading the contract placeholder, and one of them asserts that the placeholder is refused.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from orchestrator.domain.ports.crypto import Crypto
from orchestrator.infrastructure.crypto import FernetCrypto
from orchestrator.infrastructure.crypto.fernet import KEY_COMMAND


@pytest.fixture
def crypto() -> FernetCrypto:
    return FernetCrypto(Fernet.generate_key().decode())


def test_the_adapter_satisfies_the_port(crypto: FernetCrypto) -> None:
    port: Crypto = crypto

    assert isinstance(port, Crypto)


@pytest.mark.parametrize(
    "value", ["abcdefgh", "", "https://example.com/x?y=1", "ünïcødé 🔐", "a" * 5000]
)
def test_a_value_survives_the_round_trip(crypto: FernetCrypto, value: str) -> None:
    assert crypto.decrypt(crypto.encrypt(value)) == value


def test_the_token_is_not_the_value(crypto: FernetCrypto) -> None:
    assert crypto.encrypt("abcdefgh") != "abcdefgh"
    assert "abcdefgh" not in crypto.encrypt("abcdefgh")


def test_the_token_is_the_form_the_column_stores(crypto: FernetCrypto) -> None:
    """A `text` column holds it; Fernet tokens are url-safe base64 and start with `gAAAAA`."""
    token = crypto.encrypt("abcdefgh")

    assert isinstance(token, str)
    assert token.startswith("gAAAAA")


def test_two_encryptions_of_one_value_differ(crypto: FernetCrypto) -> None:
    """The IV is random. Comparing ciphertexts to decide "unchanged" would be wrong."""
    assert crypto.encrypt("same") != crypto.encrypt("same")


def test_a_tampered_token_is_refused_rather_than_decoded(crypto: FernetCrypto) -> None:
    token = crypto.encrypt("abcdefgh")
    flipped = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]

    with pytest.raises(InvalidToken):
        crypto.decrypt(flipped)


def test_a_token_from_another_instance_is_refused() -> None:
    """Two instances, two keys: one may not read the other's Project variables."""
    theirs = FernetCrypto(Fernet.generate_key().decode())
    mine = FernetCrypto(Fernet.generate_key().decode())

    with pytest.raises(InvalidToken):
        mine.decrypt(theirs.encrypt("abcdefgh"))


def test_something_that_is_not_a_token_at_all_is_refused(crypto: FernetCrypto) -> None:
    with pytest.raises(InvalidToken):
        crypto.decrypt("not-a-token")


@pytest.mark.parametrize(
    "key",
    ["change-me-fernet-key", "", "short", "!" * 44, Fernet.generate_key().decode()[:-1]],
    ids=["contract-placeholder", "empty", "short", "not-base64", "truncated"],
)
def test_a_key_that_is_not_a_fernet_key_is_refused_at_construction(key: str) -> None:
    with pytest.raises(ValueError, match="ORCHESTRATOR_SECRET_KEY") as refusal:
        FernetCrypto(key)

    assert KEY_COMMAND in str(refusal.value)


def test_the_refusal_says_the_key_is_the_key_and_not_a_passphrase() -> None:
    """Deriving one would accept any string and shrink the keyspace without saying so."""
    with pytest.raises(ValueError, match="never a passphrase") as refusal:
        FernetCrypto("change-me-fernet-key")

    assert "Fernet.generate_key" in str(refusal.value)


def test_the_refusal_never_echoes_the_key() -> None:
    secret = "a-secret-someone-typed-into-dot-env"

    with pytest.raises(ValueError) as refusal:
        FernetCrypto(secret)

    assert secret not in str(refusal.value)


def test_the_key_is_used_as_given_and_never_derived() -> None:
    """A byte-identical key must read what the other instance wrote; a derived one might not."""
    key = Fernet.generate_key().decode()
    token = FernetCrypto(key).encrypt("abcdefgh")

    assert FernetCrypto(key).decrypt(token) == "abcdefgh"
    assert Fernet(key.encode()).decrypt(token.encode()).decode() == "abcdefgh"
