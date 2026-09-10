"""`LiteLLMSpend`: the real `Gateway` adapter over LiteLLM's `GET /spend/logs/v2` (AD-11).

Verified live against LiteLLM `v1.99.1`'s own source (`litellm/proxy/spend_tracking/
spend_management_endpoints.py`, `ui_view_spend_logs`, shared by `/spend/logs/v2`;
`research/spend.md`, this story's Code Map):

- **`start_date`/`end_date` are required**, not optional as an earlier brief's example call
  implied — omitted, the route raises 400. This adapter supplies a fixed, wide window
  (`START_DATE`..`END_DATE`) rather than a real one: a query already scoped exactly to one
  `(end_user, session_id)` pair needs no narrower window, and a fixed window needs no
  `Clock` port.
- **`session_id` is `LIKE %value%`** (partial match), not equality; `end_user` is exact
  equality. A UUIDv7 attempt id colliding as a substring of another attempt id's is not a
  realistic risk — noted, not defended against, since the route offers no exact filter.
- **Response envelope:** `{"data": [...], "total", "page", "page_size", "total_pages",
  "total_is_capped"}`. Each row carries (among others) `spend` (float), `prompt_tokens`,
  `completion_tokens`, `model`.

**The bearer is `LITELLM_SPEND_KEY`, never `LITELLM_API_KEY`** (AD-5, AD-11): the harness
never receives this key, and this adapter — the only reader of it — is the only place it is
read outside `infrastructure/settings.py`.

**Never raises to `spend_for_attempt`'s caller** (this story's own Boundaries). Empty rows,
an HTTP error, a bad body — every one of them is logged and answered as a provisional zero,
the same shape `tests/unit/fakes/gateway.py::PROVISIONAL_ZERO` gives an unscripted pair, so
a caller never has to tell "the Gateway has nothing yet" from "the Gateway is unreachable".

**Two ways to find an attempt's rows** (`Settings.litellm_spend_match`, 7.2). `session` is
everything above and is the default. `attempt_tag` is the fallback 5.3 left as a swap-in, for
a request path that does not carry `x-litellm-session-id` into the log's `session_id` column
— Codex reaches the Gateway over the `responses` wire API through `env_http_headers`, and
whether that path keeps the header is what 7.2's runbook has the Operator measure. In that
mode the rows are asked for by `end_user` alone, because `/spend/logs/v2` offers no tag filter
(`research/spend.md`), and narrowed here to the ones whose `request_tags` carry
`attempt:{attempt_id}` — one of the five positions `infrastructure/harness/env.py::tag_list`
writes into `x-litellm-tags`. The mode is a setting and never an automatic second query: an
automatic one would be a silent retry (hard rule 7) and would hide the very finding the
runbook exists to record.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import httpx
import structlog

from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from orchestrator.infrastructure.harness.env import attempt_tag
from orchestrator.infrastructure.settings import Settings

log = structlog.get_logger(__name__)

#: The one route this adapter calls.
SPEND_LOGS_PATH = "/spend/logs/v2"

#: A fixed, wide window — see the module docstring on why no `Clock` is needed for it.
START_DATE = "2020-01-01"
END_DATE = "2099-12-31"

#: The two values of `Settings.litellm_spend_match`, named here because this is the module
#: that acts on them (`infrastructure/settings.py::SpendMatch` declares the type).
MATCH_SESSION = "session"
MATCH_ATTEMPT_TAG = "attempt_tag"

#: Logged whenever `spend_for_attempt` answers a provisional zero (empty rows, an HTTP
#: error, or a body the adapter could not read) — never raised.
SPEND_QUERY_DEGRADED = "litellm spend query answered provisional zero"

#: What a provisional answer looks like — one place, so every degraded path returns the
#: same shape `tests/unit/fakes/gateway.py::PROVISIONAL_ZERO` also gives.
_PROVISIONAL_ZERO = AttemptSpend(
    usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=True
)


class LiteLLMSpend:
    """`Gateway`, built once per process or once per request — cheap either way: the only
    state is the injected `httpx.Client` and a `Settings` reference."""

    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self._settings = settings
        self._http = http

    def spend_for_attempt(self, run_id: UUID, attempt_id: UUID) -> AttemptSpend:
        try:
            rows = self._rows(run_id, attempt_id)
        except Exception:
            log.exception(
                SPEND_QUERY_DEGRADED, run_id=str(run_id), attempt_id=str(attempt_id), reason="error"
            )
            return _PROVISIONAL_ZERO
        if not rows:
            log.info(
                SPEND_QUERY_DEGRADED, run_id=str(run_id), attempt_id=str(attempt_id), reason="empty"
            )
            return _PROVISIONAL_ZERO
        return _aggregate(rows)

    def _rows(self, run_id: UUID, attempt_id: UUID) -> list[dict[str, Any]]:
        """Every row across every page — `/spend/logs/v2` pages, and this reads them all —
        narrowed to the ones that actually match, per `_matches`'s own docstring."""
        by_tag = self._settings.litellm_spend_match == MATCH_ATTEMPT_TAG
        rows: list[dict[str, Any]] = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            body = self._page(run_id, attempt_id, page, by_tag=by_tag)
            rows.extend(body.get("data") or [])
            total_pages = int(body.get("total_pages") or 1)
            page += 1
        return [row for row in rows if _matches(row, run_id, attempt_id, by_tag=by_tag)]

    def _page(self, run_id: UUID, attempt_id: UUID, page: int, *, by_tag: bool) -> dict[str, Any]:
        """One page of the Run's rows. In `attempt_tag` mode the query names no session: the
        route has no tag filter, so the narrowing to this attempt happens in `_matches`."""
        params: dict[str, Any] = {
            "end_user": str(run_id),
            "start_date": START_DATE,
            "end_date": END_DATE,
            "page": page,
        }
        if not by_tag:
            params["session_id"] = str(attempt_id)
        response = self._http.get(
            SPEND_LOGS_PATH,
            params=params,
            headers={
                "Authorization": f"Bearer {self._settings.litellm_spend_key.get_secret_value()}"
            },
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError(f"/spend/logs/v2 answered a non-object body: {type(body).__name__}")
        return body


def _matches(row: Mapping[str, Any], run_id: UUID, attempt_id: UUID, *, by_tag: bool) -> bool:
    """`session_id` on `/spend/logs/v2` is a `LIKE %value%` partial match, not equality
    (verified live against LiteLLM `v1.99.1`'s own source — the module docstring says so);
    `end_user` is exact already, but is checked here too for symmetry. A row whose
    `session_id` merely contains `attempt_id` as a substring, rather than equalling it, is
    dropped client-side before it ever reaches a money or budget-park figure.

    In `attempt_tag` mode the attempt is identified by the tag instead, and the check is
    equality against one whole tag rather than a substring for exactly the same reason: two
    attempts of the same Run come back in one query there, and `attempt:{id}` being a prefix
    of `attempt:{id}-2` would put one attempt's money on the other."""
    end_user_matches = str(row.get("end_user")) == str(run_id)
    if by_tag:
        return end_user_matches and attempt_tag(str(attempt_id)) in _tags(row.get("request_tags"))
    return end_user_matches and str(row.get("session_id")) == str(attempt_id)


def _tags(value: Any) -> list[str]:
    """A row's `request_tags`, as the list of whole tags it is. `x-litellm-tags` is sent
    comma-joined and stored as a JSON array; whether a given proxy version hands back the
    array or the string it received is its own business, so both read the same way here.
    Anything else — absent, a number, an object — is no tags at all, never a partial match."""
    if isinstance(value, list):
        return [tag for tag in value if isinstance(tag, str)]
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []


@dataclass
class _Bucket:
    """One model's running total, while `_aggregate` walks the rows. Mutable and local —
    never returned, never compared — so the accumulation itself needs no `Decimal | int`
    union and no suppression to satisfy `mypy --strict`."""

    usd: Decimal = field(default_factory=lambda: Decimal("0"))
    tokens_in: int = 0
    tokens_out: int = 0


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> AttemptSpend:
    """Sum every row, and sum again per model — one pass, since every row names exactly
    one model."""
    per_model: dict[str, _Bucket] = {}
    total_usd = Decimal("0")
    total_in = 0
    total_out = 0
    for row in rows:
        model = str(row.get("model") or "")
        usd = _decimal(row.get("spend"))
        tokens_in = _int(row.get("prompt_tokens"))
        tokens_out = _int(row.get("completion_tokens"))
        total_usd += usd
        total_in += tokens_in
        total_out += tokens_out
        bucket = per_model.setdefault(model, _Bucket())
        bucket.usd += usd
        bucket.tokens_in += tokens_in
        bucket.tokens_out += tokens_out
    by_model = tuple(
        ModelSpend(
            model=name, usd=bucket.usd, tokens_in=bucket.tokens_in, tokens_out=bucket.tokens_out
        )
        for name, bucket in per_model.items()
    )
    return AttemptSpend(
        usd=total_usd,
        tokens_in=total_in,
        tokens_out=total_out,
        by_model=by_model,
        calls=len(rows),
        provisional=False,
    )


def _decimal(value: Any) -> Decimal:
    """A row's `spend` as a `Decimal`, off its `repr` — never the float itself, which would
    carry its own binary rounding into a money figure. Anything unusable is `0`."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(repr(value)) if isinstance(value, float) else Decimal(str(value))
    except InvalidOperation, ValueError:
        return Decimal("0")


def _int(value: Any) -> int:
    """A row's token count as an `int`. Anything unusable is `0`."""
    try:
        return int(value)
    except TypeError, ValueError:
        return 0
