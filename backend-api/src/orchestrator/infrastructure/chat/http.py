"""The transport rules every chat adapter shares (AD-25, AD-5).

The token goes only to the configured host, as `Authorization: Bearer`, and redirects are
never followed, so a 3xx comes back as a status and the bearer cannot reach another host. A
request that cannot be built is reported by exception class only, because those messages
quote the header, and a transport error is redacted in the token's raw and escaped forms.
Nothing is retried (hard rule 7) and nothing is logged. The shared client keeps no cookies,
so one bot's session cookie can never ride along with another bot's requests.
"""

from __future__ import annotations

from collections.abc import Mapping
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

from orchestrator.domain.ports.chat import ChatError
from orchestrator.infrastructure.redact import redact

TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TOKEN_REFUSED = "the token must be non-empty printable ASCII with no whitespace"

Params = Mapping[str, str | int]


class TooLarge(Exception):
    """An answer longer than `MAX_RESPONSE_BYTES`."""


def new_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The client every channel uses unless given one: bounded, no redirects, no cookies."""
    return httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        cookies=CookieJar(DefaultCookiePolicy(allowed_domains=[])),
        transport=transport,
    )


def sendable(token: str) -> bool:
    return bool(token) and token.isascii() and token.isprintable() and " " not in token


def redact_token(detail: str, token: str) -> str:
    for form in {token, repr(token)[1:-1], repr(token.encode())[2:-1]}:
        detail = redact(detail, form)
    return detail


def read_capped(response: httpx.Response) -> bytes:
    chunks, size = [], 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise TooLarge
        chunks.append(chunk)
    return b"".join(chunks)


def exchange(  # noqa: PLR0913 — one request's parts, each passed through to httpx
    client: httpx.Client,
    method: str,
    url: str,
    token: str,
    label: str,
    *,
    params: Params | None = None,
    json: Any = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, httpx.Headers, bytes]:
    """One request: its status, headers and capped body, or a `ChatError` for the transport."""
    try:
        with client.stream(
            method,
            url,
            params=params,
            json=json,
            headers={**(headers or {}), "Authorization": f"Bearer {token}"},
            follow_redirects=False,
        ) as response:
            return response.status_code, response.headers, read_capped(response)
    except httpx.HTTPError as error:
        raise ChatError(redact_token(f"{type(error).__name__}: {error}", token)) from None
    except (httpx.InvalidURL, ValueError, UnicodeError) as error:
        name = type(error).__name__
        raise ChatError(f"{name}: the request to {label} could not be built") from None
    except TooLarge:
        raise ChatError(f"{label} answered more than {MAX_RESPONSE_BYTES} bytes") from None
