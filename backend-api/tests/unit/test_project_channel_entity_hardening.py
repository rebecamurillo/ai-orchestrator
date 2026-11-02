"""`is_valid_base_url` hardening (story 3-4 review, 2026-11-02).

A malformed host answers `False` instead of raising. Userinfo, a query and a fragment are
refused, because a base URL names a host and an optional path, and nothing else.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.entities.project_channel import is_valid_base_url


@pytest.mark.parametrize("url", ["http://[::1", "http://[zz]/"])
def test_a_malformed_host_is_not_a_base_url_rather_than_an_error(url: str) -> None:
    assert is_valid_base_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@chat.example.com",
        "https://user@chat.example.com",
        "https://chat.example.com/?team=a",
        "https://chat.example.com/?",
        "https://chat.example.com/#top",
        "https://chat.example.com#",
    ],
)
def test_userinfo_a_query_or_a_fragment_is_refused(url: str) -> None:
    assert is_valid_base_url(url) is False


def test_a_bracketed_ipv6_host_is_still_a_base_url() -> None:
    assert is_valid_base_url("http://[::1]:8065/mm")
