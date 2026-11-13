"""The blind switch (ARCHITECTURE §6.4): what a payload or file never carries while blind.

Never stored; applied once, on the server, over the values of a comparison or an export.
Harness, status, stories done and Run ids are not hidden.
"""

from __future__ import annotations

from orchestrator.domain.entities.metric_results import StoredMetricValue

HIDDEN = "hidden · blind"
MODEL_SCOPE = "model"


def blind_label(n: int) -> str:
    """The label of the n-th selected Run (1-based)."""
    return f"R{n}"


def blind_value(value: StoredMetricValue) -> StoredMetricValue:
    """The value with every model name and the template name replaced by `HIDDEN`."""
    origin = value.origin.model_copy(update={"template_name": HIDDEN})
    if origin.origin_model is not None:
        origin = origin.model_copy(update={"origin_model": HIDDEN})
    update: dict[str, object] = {"origin": origin}
    if value.model is not None:
        update["model"] = HIDDEN
    if value.scope_type == MODEL_SCOPE:
        update["scope_key"] = HIDDEN
        update["scope_label"] = HIDDEN
    return value.model_copy(update=update)
