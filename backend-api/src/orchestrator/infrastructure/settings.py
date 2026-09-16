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

from pydantic import BeforeValidator, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from orchestrator.domain.entities.harness import HARNESS_NAMES

LogLevel = Literal["debug", "info", "warning", "error", "critical"]

#: How `infrastructure/gateway/litellm_spend.py` finds one attempt's rows in the Gateway's
#: spend log (AD-11). `session` is 5.3's verified query — `x-litellm-session-id` lands in the
#: log's `session_id` column and the route filters on it. `attempt_tag` is 5.3's own
#: documented fallback for a request path that does not keep that header: the rows are asked
#: for by `end_user` alone and narrowed to the ones whose `request_tags` carry
#: `attempt:{id}`, since `/spend/logs/v2` has no tag filter of its own (`research/spend.md`).
SpendMatch = Literal["session", "attempt_tag"]

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


def _split_pairs(value: object) -> object:
    """Read `name=value,name=value` as a mapping, leaving mappings alone.

    `_split_csv`'s shape for a setting that binds something *per* name. Every failure is
    raised here rather than tolerated, because each of them is a name that would silently
    bind nothing: a pair with no `=`, no name, or no value.
    """
    if not isinstance(value, str):
        return value
    pairs: dict[str, str] = {}
    for item in value.split(","):
        if not item.strip():
            continue
        name, separator, bound = item.partition("=")
        if not separator or not name.strip() or not bound.strip():
            raise ValueError(f"{item.strip()!r} is not a `name=value` pair")
        pairs[name.strip()] = bound.strip()
    return pairs


CommaSeparatedPairs = Annotated[
    dict[str, str],
    NoDecode,
    BeforeValidator(_split_pairs),
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
    #: `harness_readiness.start`'s own `model`, one per harness (SPEC CAP-8, AD-10):
    #: `claude=…,codex=…,local=…`, each naming a `model_name` the Gateway's `model_list`
    #: serves. One value per harness because a single one cannot be right — `codex` cannot
    #: run an Anthropic model, and `local` is pointed at the host's own model server.
    #:
    #: Bound rather than left empty because an unbound `{{model}}` resolves to the empty
    #: string and the harness falls back to its own built-in default, which the Gateway
    #: serves no route for. `_covers_every_harness` below is why a half-filled line refuses
    #: at start-up instead of at the dispatch that would have bound nothing.
    readiness_models: CommaSeparatedPairs

    # ── Git (AD-5) — never handed to a harness process ───────────────────────
    github_token: SecretStr

    # ── Gateway (AD-5, AD-11) ────────────────────────────────────────────────
    litellm_base_url: str
    litellm_api_key: SecretStr
    litellm_spend_key: SecretStr
    local_models: CommaSeparated
    #: Which query attributes an attempt's spend (AD-11) — see `SpendMatch`.
    #:
    #: Defaulted, like `orch_test_mode` and for the same reason: an operator's existing
    #: `.env`, and the `.env.e2e` `scripts/generate-env.sh` writes once and never rewrites,
    #: must keep starting unchanged. The default is the mode 5.3 verified live, so an
    #: environment that never sets it behaves exactly as it did before this field existed.
    #: The AD-20 contract is unaffected: the field has its line in `.env.example` and
    #: `scripts/check_env_contract.py` still checks both directions.
    #:
    #: `attempt_tag` is switched on only once the Operator has *observed* a request path
    #: dropping `x-litellm-session-id` while keeping `x-litellm-tags` — story 7.2's runbook
    #: is where that measurement is made. Switching automatically on an empty result would
    #: be a silent retry (hard rule 7) and would hide the finding.
    litellm_spend_match: SpendMatch = "session"

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

    # ── derived flags (not fields — no line in .env.example, not in model_fields) ──

    @property
    def gateway_enabled(self) -> bool:
        """True when LITELLM_BASE_URL is a non-blank, non-whitespace-only string."""
        return bool(self.litellm_base_url.strip())

    @property
    def tracing_enabled(self) -> bool:
        """True when LANGFUSE_BASE_URL is a non-blank, non-whitespace-only string."""
        return bool(self.langfuse_base_url.strip())

    # ── cross-field validation ────────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_service_config(self) -> Settings:
        """Refuse a non-blank base URL paired with a blank key.

        A half-configured service looks configured to the Operator but fails at first use —
        refused here, at bind time, rather than silently at the first request that needs it.
        Blank the base URL to disable the service entirely; that is the intended off switch.
        """
        errors: list[str] = []

        if self.litellm_base_url.strip() and not self.litellm_api_key.get_secret_value().strip():
            errors.append(
                "litellm_api_key is blank but litellm_base_url is non-blank — "
                "blank litellm_base_url to disable the gateway, or provide litellm_api_key"
            )

        if self.langfuse_base_url.strip():
            for field_name, raw_value in [
                ("langfuse_public_key", self.langfuse_public_key),
                ("langfuse_secret_key", self.langfuse_secret_key.get_secret_value()),
                ("langfuse_project_id", self.langfuse_project_id),
            ]:
                if not str(raw_value).strip():
                    errors.append(
                        f"{field_name} is blank but langfuse_base_url is non-blank — "
                        f"blank langfuse_base_url to disable tracing, or provide {field_name}"
                    )

        if errors:
            raise ValueError("; ".join(errors))

        return self

    @field_validator("readiness_models")
    @classmethod
    def _covers_every_harness(cls, value: dict[str, str]) -> dict[str, str]:
        """Exactly the three harnesses the image installs, no more and no fewer.

        Missing: that harness's readiness Run would bind no model, which is the failure the
        setting exists to remove — refused here, at start-up, rather than at the dispatch,
        because a partly-filled line looks configured. Extra: a name that is not a harness
        is a typo (`opencode` for `local`), and ignoring it would leave the harness it was
        meant for unbound while the line looks complete.
        """
        missing = [name for name in HARNESS_NAMES if name not in value]
        unknown = sorted(name for name in value if name not in HARNESS_NAMES)
        if missing or unknown:
            raise ValueError(
                f"missing {missing or 'nothing'}, unknown {unknown or 'nothing'} — "
                "one `name=model` pair for each harness the image installs, and no other"
            )
        return value

    @field_validator("work_dir", "agent_home")
    @classmethod
    def _must_be_absolute(cls, value: Path) -> Path:
        """These name container volumes; a relative path would resolve against the cwd."""
        if not value.is_absolute():
            raise ValueError(f"must be an absolute path, got {value!r}")
        return value
