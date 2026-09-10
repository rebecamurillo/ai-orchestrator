"""Which models an instance offers per harness (FR-27, SPEC CAP-3, story 7.3).

A sibling of `registry.py`'s `alias_table` and the same kind of thing: the one place a
harness-specific name is joined to the `Settings` field that carries it. `seed.py`'s
`HARNESS_VERSION_SETTINGS` does it for the version pin, this does it for the model list, and
neither is a dictionary any layer above `infrastructure/` has to know the shape of.

**Why this is config and not a stored column.** `Harness` is a row, and every field on it is
something a readiness run *observed* — `enabled`, `last_readiness_at`, `failing_check`, the
lines. Which models the Gateway is currently configured to serve is none of those: it changes
when an Operator edits `.env` and restarts, with no migration and no readiness run in between,
and a stored copy would go stale exactly when it mattered. So `GET /harnesses` composes it per
request from `Settings`, which is what makes the New workflow's select always offer what the
Gateway will actually route.

**Why only `local` has an entry.** `LOCAL_MODELS` exists because the host serves those models
itself and their aliases are an instance's own choice (PRD §8 items 7-8). `claude` and `codex`
are pointed at model names the provider publishes, and the brief's own wording — "`models`
lists the `LOCAL_MODELS` aliases, empty for others" — is what a harness with no entry answers.
An empty list is a statement, not a gap: it means "this harness takes a free-text model name",
which is exactly what the New workflow's text field is for.
"""

from __future__ import annotations

from orchestrator.infrastructure.settings import Settings

#: Harness name -> the `Settings` field naming the models this instance offers for it. Keyed
#: the way `build_harnesses` and the `harness` table are, so a name here that is not a harness
#: would simply never be asked for.
HARNESS_MODEL_SETTINGS: dict[str, str] = {"local": "local_models"}


def model_table(settings: Settings) -> dict[str, tuple[str, ...]]:
    """The models this instance offers, per harness name — `{}` entries omitted, never faked.

    Tuples rather than lists: this is read by a response model and by nothing that may edit
    it, and a shared mutable default is a bug waiting for the one caller that appends.
    """
    return {name: tuple(getattr(settings, field)) for name, field in HARNESS_MODEL_SETTINGS.items()}
