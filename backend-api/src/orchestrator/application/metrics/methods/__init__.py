"""The method registry: `metric_id@n` → the function that computes that method.

No method is registered yet; a test ties every key held here to a catalogued `metric_id@n`.
"""

from __future__ import annotations

import re
from collections.abc import Callable

Method = Callable[..., object]

REGISTRY: dict[str, Method] = {}

METHOD_KEY = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*@[1-9][0-9]*$")


def register(method_id: str) -> Callable[[Method], Method]:
    """Decorator: file the function under `metric_id@n`, refusing a bad or repeated key."""
    if not METHOD_KEY.match(method_id):
        raise ValueError(f"malformed method id {method_id!r}: expected metric_id@n")
    if method_id in REGISTRY:
        raise ValueError(f"method {method_id} is already registered")

    def decorate(method: Method) -> Method:
        REGISTRY[method_id] = method
        return method

    return decorate
