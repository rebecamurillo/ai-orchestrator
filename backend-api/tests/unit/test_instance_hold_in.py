"""`POST /instance/hold`'s body refuses a reason no text column can hold.

Schemathesis found it in CI on 2026-11-13: `"reason": "\\u0000"` reached psycopg and answered 500.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.instance import HoldIn


@pytest.mark.parametrize("reason", ["\x00", "up\x00grade", "\ud800"])
def test_a_reason_no_text_column_can_hold_is_a_validation_error(reason: str) -> None:
    with pytest.raises(ValidationError, match="reason"):
        HoldIn(ttl_seconds=60, reason=reason)


def test_a_plain_reason_is_kept() -> None:
    assert HoldIn(ttl_seconds=60, reason="upgrade").reason == "upgrade"
