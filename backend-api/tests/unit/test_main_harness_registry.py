"""The harness registry the composition root builds (AD-2, AD-10).

`build_harnesses` is the one place an adapter class is named. The executor 5.4 lands looks
its harness up by `with_resolved.harness`, which is a string from a Template, so the
registry's keys are what decide whether `harness: claude` in a Template resolves to
anything at all — and the key has to be the same string the `harness` table is seeded with,
or a Run could pass pre-flight and then find no adapter.

`main.py` already imports the stored `Harness` *entity*; the port shares its name, so the
alias the registry's annotation uses is asserted here too — a rename that silently pointed
the registry at the entity would type-check nowhere, since mypy is strict only over
`domain/` and `application/`.
"""

from __future__ import annotations

from orchestrator.domain.ports.harness import Harness as HarnessPort
from orchestrator.infrastructure.harness import ClaudeHarness
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import HARNESS_VERSION_SETTINGS, build_harnesses
from tests.unit.fakes.process import FakeProcessRunner


def test_the_registry_holds_the_one_adapter_this_epic_lands(env: dict[str, str]) -> None:
    harnesses = build_harnesses(Settings(), FakeProcessRunner())

    assert list(harnesses) == ["claude"]
    assert isinstance(harnesses["claude"], ClaudeHarness)


def test_every_registered_adapter_satisfies_the_port(env: dict[str, str]) -> None:
    harnesses = build_harnesses(Settings(), FakeProcessRunner())

    for name, harness in harnesses.items():
        assert isinstance(harness, HarnessPort), name
        assert harness.name == name


def test_every_registered_name_is_a_name_the_harness_table_is_seeded_with(
    env: dict[str, str],
) -> None:
    """A registry key with no seeded row would be a harness pre-flight can never enable."""
    assert set(build_harnesses(Settings(), FakeProcessRunner())) <= set(HARNESS_VERSION_SETTINGS)


def test_the_registry_builds_one_adapter_per_call_on_the_runner_it_is_given(
    env: dict[str, str],
) -> None:
    """The walker's own `ProcessRunner` is what the adapters must start processes through
    (AD-14), so the registry takes one rather than building its own."""
    runner = FakeProcessRunner()

    harness = build_harnesses(Settings(), runner)["claude"]

    assert isinstance(harness, ClaudeHarness)
    assert harness.runner is runner
