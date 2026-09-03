"""The error vocabulary use cases raise.

`domain/` imports no web framework (AD-2), so nothing here knows an HTTP status code.
A use case raises one of these; `api/errors.py` is the single place that turns a kind into
a status and a problem document. Adding a kind therefore means adding it to that one
mapping, not scattering `raise HTTPException` through the rules.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base for every error a use case raises deliberately.

    An unexpected exception is a bug and stays a 500; a `DomainError` is a described
    outcome the API is expected to report.
    """


class NotFound(DomainError):
    """The entity named by the request does not exist."""


class Conflict(DomainError):
    """The request is well formed but not valid for the entity's current state."""


class Invalid(DomainError):
    """The request's content breaks a rule the schema alone cannot express."""
