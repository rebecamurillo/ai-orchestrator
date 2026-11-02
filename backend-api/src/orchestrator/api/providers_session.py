"""Ports for `GET /runs/{id}/session` and its messages (AD-23): the signal endpoint's own,
narrowed.

A sibling of `api/providers.py`, which is near its line cap; built on `signal_effect_ports`
so the read and the two session signals go through the same writers, `Git` and registry.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from orchestrator.api.providers import signal_effect_ports
from orchestrator.application.use_cases.session_checks import SessionPorts
from orchestrator.application.use_cases.session_turn import MessagePorts
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.application.use_cases.signals import session_ports as narrowed


def session_ports(
    ports: Annotated[SignalEffectPorts, Depends(signal_effect_ports)],
) -> SessionPorts:
    return narrowed(ports)


def message_ports(
    ports: Annotated[SignalEffectPorts, Depends(signal_effect_ports)],
) -> MessagePorts:
    return MessagePorts(writers=ports.signal.writers, engine=ports.signal.engine)
