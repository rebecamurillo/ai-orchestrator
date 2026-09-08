"""The Project: the context every agent reads and the environment every Run exports.

Four rules live here because four layers restate them, and a copy of any of them would be
the copy that drifts:

- **A variable name** matches `^[A-Z][A-Z0-9_]*$`. The name reaches a harness process as a
  shell environment variable, and anything else is either unexportable or a different
  variable than the Operator typed.
- **A reserved name is refused.** `GITHUB_TOKEN`, the Gateway keys and everything under
  `LANGFUSE_` / `ORCHESTRATOR_` are instance settings read once by `infrastructure/
  settings.py` (AD-5). A Project variable of the same name would either shadow the
  instance's own value or hand a harness a credential it must never see.
- **A value is never returned.** `mask` is the only rendering of a stored value there is,
  and it shows at most the last four characters — enough for the Operator to recognise
  which secret is in the slot, not enough to reconstruct it.
- **A slug is derived once.** It names the Project's directory under `/work` (AD-14), so it
  is lowercase, short, and stable: renaming a Project never moves its clones.

The values themselves are Fernet ciphertext by the time they reach this module. `domain/`
holds no key and performs no encryption — that is the `Crypto` port, and its adapter.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

#: The shell-exportable name of a Project variable.
ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

#: Said back to the Operator when a name does not match, so the message names the rule.
ENV_NAME_REASON = "a variable name matches ^[A-Z][A-Z0-9_]*$"

#: Instance settings (AD-5). A Project may not redefine any of them.
RESERVED_ENV_NAMES = frozenset(
    {
        "GITHUB_TOKEN",
        "LITELLM_API_KEY",
        "LITELLM_SPEND_KEY",
    }
)

#: Whole families of instance settings, refused by prefix rather than one name at a time.
RESERVED_ENV_PREFIXES = ("LANGFUSE_", "ORCHESTRATOR_")

#: The exact wording the API returns for a reserved name.
RESERVED_ENV_REASON = "instance setting, not a project variable"

#: What a masked value starts with, and how much of the real value follows it.
MASK_PREFIX = "••••"
MASK_TAIL = 4

#: The one Project seeded at start-up (SPEC CAP-8): the fixture readiness runs work in.
#: `Project.builtin` is `True` exactly when a Project's `slug` equals this — never a stored
#: column of its own, since `slug` already is one and is already unique per instance.
READINESS_PROJECT_SLUG = "readiness"

#: A slug names a directory; keep it short enough to nest under `/work` comfortably.
SLUG_MAX_LENGTH = 40
SLUG_SEPARATOR = "-"
#: What a name with no slug characters at all becomes.
SLUG_FALLBACK = "project"

_NOT_SLUG = re.compile(r"[^a-z0-9]+")


def is_valid_env_name(name: str) -> bool:
    """True when `name` is a shell-exportable variable name."""
    return ENV_NAME_PATTERN.match(name) is not None


def is_reserved_env_name(name: str) -> bool:
    """True when `name` belongs to the instance, not to a Project (AD-5)."""
    return name in RESERVED_ENV_NAMES or name.startswith(RESERVED_ENV_PREFIXES)


def mask(value: str) -> str:
    """The only rendering of a stored value: four dots, then at most its last four bytes.

    A value shorter than the tail is shown as the dots alone — padding it with part of
    itself would leak the whole secret for exactly the values that can least afford it.
    """
    if len(value) < MASK_TAIL:
        return MASK_PREFIX
    return MASK_PREFIX + value[-MASK_TAIL:]


def slugify(name: str) -> str:
    """`"My Website 2!"` -> `my-website-2`: lowercase, `[a-z0-9-]`, never empty.

    Truncation happens before the trailing separator is stripped, so a name cut mid-word
    never leaves a dangling `-`.
    """
    collapsed = _NOT_SLUG.sub(SLUG_SEPARATOR, name.lower()).strip(SLUG_SEPARATOR)
    trimmed = collapsed[:SLUG_MAX_LENGTH].strip(SLUG_SEPARATOR)
    return trimmed or SLUG_FALLBACK


def numbered_slug(base: str, number: int) -> str:
    """`(my-website, 2)` -> `my-website-2`, still within the length limit.

    The base is shortened to make room for the suffix rather than the suffix being dropped:
    a slug that lost its number would collide with the one it was meant to differ from.
    """
    suffix = f"{SLUG_SEPARATOR}{number}"
    head = base[: SLUG_MAX_LENGTH - len(suffix)].strip(SLUG_SEPARATOR) or SLUG_FALLBACK
    return f"{head}{suffix}"


class EncryptedEnvVar(BaseModel):
    """One agent environment variable: the name in clear, the value as a Fernet token."""

    model_config = ConfigDict(frozen=True)

    name: str
    value_enc: str


class MaskedEnvVar(BaseModel):
    """One agent environment variable as every reader outside this process sees it."""

    model_config = ConfigDict(frozen=True)

    name: str
    masked: str


class ProjectView(BaseModel):
    """A Project as an endpoint may return it: no value, encrypted or otherwise."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str
    name: str
    context_text: str
    context_paths: tuple[str, ...]
    env_vars: tuple[MaskedEnvVar, ...]
    log_prompt_content: bool
    #: Whether this is the seeded `readiness` Project (SPEC CAP-8): never editable or
    #: deletable through the API. `False` for every Project an Operator creates. Derived
    #: from `slug`, not a stored column (`Project.builtin`'s own docstring says why).
    #: Defaulted `False`, the same reason `Project.builtin` is: every `ProjectView(...)`
    #: construction predating this story — every frozen schema test among them — keeps
    #: reading unchanged.
    builtin: bool = False
    created_at: datetime
    updated_at: datetime


class Project(BaseModel):
    """A Project as it is stored: context, encrypted variables, and the logging switch."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str
    name: str
    context_text: str
    context_paths: tuple[str, ...]
    env_vars_enc: tuple[EncryptedEnvVar, ...]
    log_prompt_content: bool
    #: `True` for exactly the Project whose `slug` is `READINESS_PROJECT_SLUG` (SPEC CAP-8).
    #: Not a stored field on the row this entity is read from — the repository computes it
    #: from `slug` every time (`infrastructure/db/repositories/projects.py::to_entity`'s own
    #: docstring says why: a second, redundant column would only ever agree with `slug` or
    #: be a bug). The default here is what every existing `Project(...)` construction site
    #: — every unit test among them — keeps reading as `False` unchanged.
    builtin: bool = False
    created_at: datetime
    updated_at: datetime

    def view(self, plaintexts: Mapping[str, str]) -> ProjectView:
        """The read model, given each variable's plaintext — which only `Crypto` can supply.

        Masking is over the plaintext, not the ciphertext: the four characters the Operator
        recognises are the ones they typed. The plaintexts are read here and kept nowhere;
        the returned view holds masks and no value at all.
        """
        return ProjectView(
            id=self.id,
            slug=self.slug,
            name=self.name,
            context_text=self.context_text,
            context_paths=self.context_paths,
            env_vars=tuple(
                MaskedEnvVar(name=variable.name, masked=mask(plaintexts[variable.name]))
                for variable in self.env_vars_enc
            ),
            log_prompt_content=self.log_prompt_content,
            builtin=self.builtin,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
