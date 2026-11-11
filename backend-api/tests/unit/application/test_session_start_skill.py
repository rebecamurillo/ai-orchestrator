"""`session_start` refuses 422 when the `senior-session` skill is not installed (story 2-5,
Decided 1): the opening line names the skill, so a session must not open where a harness
would have to improvise one. A process wired with no catalog at all checks nothing, as
pre-flight and the `agent` kind do."""

from __future__ import annotations

from dataclasses import replace

import pytest

from orchestrator.application.use_cases.session_checks import NO_SKILL
from orchestrator.application.use_cases.signals import (
    SignalEffectPorts,
    handle_signal,
    session_ports,
)
from orchestrator.domain.errors import Invalid
from orchestrator.domain.values import Signal
from tests.unit.application.session_fixtures import MODEL, SessionWorld, a_session_world, probing
from tests.unit.fakes.skill_catalog import FakeSkillCatalog

START = {"scope": "story", "harness": "claude", "model": MODEL}


def with_catalog(session: SessionWorld, catalog: FakeSkillCatalog | None) -> SignalEffectPorts:
    ports = session.ports
    assert ports.signal.preflight is not None
    preflight = replace(ports.signal.preflight, skill_catalog=catalog)
    return replace(ports, signal=replace(ports.signal, preflight=preflight))


def start(session: SessionWorld, catalog: FakeSkillCatalog | None) -> object:
    ports = with_catalog(session, catalog)
    return handle_signal(ports, session.world.run.id, Signal(kind="session_start", payload=START))


@pytest.mark.parametrize("skills", [None, frozenset(), frozenset({"senior-consult"})])
def test_a_missing_or_unreadable_skill_refuses_the_start(skills: frozenset[str] | None) -> None:
    """Revised by story 1 (orchestrator-deploy-folder epic 1), 2026-11-11: the refusal names
    the harness the session starts on."""
    session = a_session_world()
    before = (session.world.stored_run(), len(session.world.records()))

    with pytest.raises(Invalid) as raised:
        start(session, FakeSkillCatalog({"claude": skills}))

    assert str(raised.value) == NO_SKILL.format(harness="claude")
    assert str(raised.value) == "skill senior-session is not installed on claude"
    assert (session.world.stored_run(), len(session.world.records())) == before


def test_an_installed_skill_lets_the_session_open() -> None:
    session = a_session_world()

    start(session, FakeSkillCatalog({"claude": frozenset({"senior-session"})}))

    assert session.world.stored_run().senior_session is True


def test_the_session_ports_carry_the_catalog_the_preflight_reads() -> None:
    session = a_session_world()
    catalog = FakeSkillCatalog({"claude": frozenset({"senior-session"})})

    assert session_ports(with_catalog(session, catalog)).skill_catalog is catalog


def test_a_skill_installed_for_another_harness_refuses_the_start() -> None:
    """Story 1 (orchestrator-deploy-folder epic 1), 2026-11-11: the catalog is asked by harness."""
    session = a_session_world(harnesses={"codex": probing(name="codex")})
    catalog = FakeSkillCatalog({"claude": frozenset({"senior-session"}), "codex": frozenset()})
    ports = with_catalog(session, catalog)
    payload = {**START, "harness": "codex"}

    with pytest.raises(Invalid) as raised:
        handle_signal(ports, session.world.run.id, Signal(kind="session_start", payload=payload))

    assert str(raised.value) == "skill senior-session is not installed on codex"
