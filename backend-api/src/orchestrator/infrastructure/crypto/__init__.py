"""Encryption at rest, behind one package (AD-2).

`domain/` and `application/` take the `Crypto` port; `cryptography` is imported here and
nowhere else, and `main.py` is the only module that names this adapter.
"""

from __future__ import annotations

from orchestrator.infrastructure.crypto.fernet import FernetCrypto

__all__ = ["FernetCrypto"]
