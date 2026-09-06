"""`infrastructure/dbos/config.py`: the environment, narrowed to what the engine needs.

Four values and one mapping, and each of them is a rule that would otherwise be invisible:
the pinned application version (AD-6), the application's own database as the engine's system
database (Operations), the admin server off, and the queue and topic names the adapter and
the walker have to agree on.
"""

from __future__ import annotations

from orchestrator.infrastructure.dbos.config import (
    APP_NAME,
    HUMAN_TOPIC,
    QUEUE_NAME,
    STEP_ID,
    WORKFLOW_ID,
    dbos_config,
    engine_config,
)
from orchestrator.infrastructure.settings import Settings

EXPECTED_CONCURRENCY = 2


def test_the_engine_reads_its_three_values_from_the_typed_settings(env: dict[str, str]) -> None:
    config = engine_config(Settings())

    assert config.application_version == "1"
    assert config.max_active_runs == EXPECTED_CONCURRENCY
    assert config.database_url.startswith("postgresql+psycopg://")


def test_the_human_wait_is_not_carried_here(env: dict[str, str]) -> None:
    """It reaches the walker through `startup.walker_deps`; two carriers read as two wirings."""
    assert not hasattr(engine_config(Settings()), "human_wait_seconds")


def test_the_version_is_the_pinned_setting_and_not_a_hash_of_the_source(
    env: dict[str, str],
) -> None:
    """A version that moved with the source would make running Runs unrecoverable (AD-6)."""
    assert dbos_config(engine_config(Settings()))["application_version"] == "1"


def test_the_engine_shares_the_applications_database(env: dict[str, str]) -> None:
    settings = Settings()

    config = dbos_config(engine_config(settings))

    assert config["system_database_url"] == settings.database_url.get_secret_value()


def test_the_application_is_named_so_two_of_them_can_share_one_database(
    env: dict[str, str],
) -> None:
    assert dbos_config(engine_config(Settings()))["name"] == APP_NAME


def test_the_admin_server_is_off(env: dict[str, str]) -> None:
    """It binds a second port that answers no product route."""
    assert dbos_config(engine_config(Settings()))["run_admin_server"] is False


def test_the_configuration_declares_nothing_else(env: dict[str, str]) -> None:
    assert set(dbos_config(engine_config(Settings()))) == {
        "name",
        "system_database_url",
        "application_version",
        "run_admin_server",
    }


def test_the_names_the_adapter_and_the_walker_share() -> None:
    assert QUEUE_NAME == "runs"
    assert HUMAN_TOPIC.format(run_id="r-1") == "human:r-1"
    assert (WORKFLOW_ID, STEP_ID) == ("workflow_id", "step_id")
