"""`PullRequests` over the GitHub REST API."""

from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)

API_URL = "https://api.github.com/repos/{owner}/{repo}/pulls"
TIMEOUT_SECONDS = 10.0


class GitHubPullRequests:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        self._transport = transport

    def merged(self, owner: str, repo: str, head: str) -> bool | None:
        status: int | None = None
        try:
            with httpx.Client(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
                response = client.get(
                    API_URL.format(owner=owner, repo=repo),
                    params={"state": "closed", "head": f"{owner}:{head}", "per_page": 100},
                    headers=self._headers,
                )
            status = response.status_code
            if status == httpx.codes.OK:
                items = response.json()
                if isinstance(items, list) and all(isinstance(i, dict) for i in items):
                    return any(item.get("merged_at") is not None for item in items)
        except httpx.HTTPError, ValueError:
            pass
        log.warning(
            "pull_request_check_unreadable", owner=owner, repo=repo, head=head, status=status
        )
        return None
