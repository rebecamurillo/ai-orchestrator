"""The only reader of the environment (AD-20).

Every field here has a line in the repository's `.env.example`, and `make lint` runs
`scripts/check_env_contract.py` to prove it in both directions. Adding a setting means
adding it to both places in the same change.

Configuration comes from the process environment only — no config file, no `.env`
auto-loading — so a container and a shell see exactly the same contract.

Anything that carries a credential is a `SecretStr`, including `DATABASE_URL`: the
committed contract embeds `POSTGRES_PASSWORD` in it, and a plain `str` would put that
password into every `repr()` and every log line binding these settings (hard rule 5).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LogLevel = Literal["debug", "info", "warning", "error", "critical"]

MIN_TCP_PORT = 1
MAX_TCP_PORT = 65535


def _split_csv(value: object) -> object:
    """Read a comma-separated environment value as a list, leaving lists alone."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CommaSeparated = Annotated[
    list[str],
    NoDecode,
    BeforeValidator(_split_csv),
    Field(min_length=1),
]


class Settings(BaseSettings):
    """Typed view of the environment contract for backend-api."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # ── Access (AD-4, AD-5) ──────────────────────────────────────────────────
    orchestrator_token: SecretStr
    orchestrator_secret_key: SecretStr

    # ── Database (AD-6) ──────────────────────────────────────────────────────
    database_url: SecretStr
    dbos_application_version: Annotated[int, Field(ge=1)]
    max_active_runs: Annotated[int, Field(ge=1)]
    #: The single `recv` the walker parks in lasts this long (AD-13). A setting rather
    #: than a constant so an e2e scenario can shorten the 30 days it defaults to.
    human_wait_seconds: Annotated[int, Field(ge=1)]
    #: How long a terminal Run's worktrees and logs are kept before `worktree_gc` sweeps
    #: them (SPEC CAP-11, FR-9).
    worktree_retention_days: Annotated[int, Field(ge=1)]
    #: The scheduled jobs' own crons (SPEC CAP-11, FR-4, FR-9, FR-21); `engine.schedule`
    #: reads these, never a constant, so an e2e scenario can run any of them sooner.
    #: `terminal_poll_cron` is a six-field cron because its period is seconds, not minutes
    #: (`*/30 * * * * *`), which is the form the DBOS scheduler takes.
    clone_check_cron: str
    worktree_gc_cron: str
    terminal_poll_cron: str
    #: `harness_readiness.start`'s own `budget_usd` (SPEC CAP-8) — the fixture's one story
    #: is small, so a low ceiling still leaves room for a retry or two.
    readiness_budget_usd: Annotated[Decimal, Field(gt=0)]

    # ── Git (AD-5) — never handed to a harness process ───────────────────────
    github_token: SecretStr

    # ── Gateway (AD-5, AD-11) ────────────────────────────────────────────────
    litellm_base_url: str
    litellm_api_key: SecretStr
    litellm_spend_key: SecretStr
    local_models: CommaSeparated

    # ── Tracing (AD-11) ──────────────────────────────────────────────────────
    langfuse_base_url: str
    langfuse_public_key: str
    langfuse_secret_key: SecretStr
    langfuse_environment: str
    #: `LangfuseTracer.trace_url` formats the UI link from this alone, so it never has to
    #: make the SDK's own blocking `get_trace_url()` project lookup (5.2's own spike).
    langfuse_project_id: str

    # ── Pinned tool versions carried by the image (AD-16) ────────────────────
    bmad_version: str
    claude_code_version: str
    codex_version: str
    opencode_version: str
    langfuse_opencode_plugin_version: str

    # ── Harness environment ──────────────────────────────────────────────────
    claude_allowed_tools: CommaSeparated
    #: How this instance's Claude Code authenticates to the Gateway (AD-5).
    #:
    #: `false` — the default and the shipped contract — is API-key mode: the Gateway's
    #: virtual key goes to the harness as `ANTHROPIC_AUTH_TOKEN`, and LiteLLM calls the
    #: provider with the key the host holds.
    #:
    #: `true` is subscription mode: Claude Code is logged in against the operator's own
    #: Claude subscription, so `Authorization` carries that OAuth token, the virtual key
    #: moves to `x-litellm-api-key`, and `ANTHROPIC_AUTH_TOKEN` must be absent or it would
    #: override the login. It needs `forward_client_headers_to_llm_api: true` on the
    #: Gateway, which is host-side and documented in `host/README.md`.
    claude_subscription_auth: bool
    work_dir: Path
    agent_home: Path

    # ── Templates (AD-15) ────────────────────────────────────────────────────
    #: `../templates` in development, `/app/templates` in the image; never validated
    #: absolute like `work_dir`/`agent_home` because the development value is relative.
    templates_dir: Path

    # ── This process ─────────────────────────────────────────────────────────
    log_prompt_content_default: bool
    log_level: LogLevel
    #: Test mode (SPEC CAP-1): the scripted `fake` harness is registered and its `harness`
    #: row seeded `enabled` only while this is on. Off is the shipped contract, and off is
    #: what every unit test sees — `tests/unit/conftest.py` builds its environment from
    #: `.env.example`, so the registry a test reads is the production one.
    #:
    #: The one field here with a default, and deliberately: it is test-only, and an
    #: environment that predates it — an operator's `.env`, the `.env.e2e`
    #: `scripts/generate-env.sh` writes once and never rewrites — must keep working
    #: unchanged rather than refusing to start over a variable that only turns a fake on.
    #: The AD-20 contract is unaffected: the field still has its line in `.env.example`, and
    #: `scripts/check_env_contract.py` still checks both directions.
    orch_test_mode: bool = False
    backend_api_port: Annotated[int, Field(ge=MIN_TCP_PORT, le=MAX_TCP_PORT)]

    @field_validator("work_dir", "agent_home")
    @classmethod
    def _must_be_absolute(cls, value: Path) -> Path:
        """These name container volumes; a relative path would resolve against the cwd."""
        if not value.is_absolute():
            raise ValueError(f"must be an absolute path, got {value!r}")
        return value
