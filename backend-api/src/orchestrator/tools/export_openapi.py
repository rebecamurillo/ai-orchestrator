"""Export `contracts/openapi.json`, the one source web-client generates its types from (AD-3).

`make openapi` runs this and then `pnpm gen:api`. Two constraints shape the module:

**It must run on a fresh clone.** No `.env`, no Postgres, no network — the document depends
on the Pydantic schemas and the routes, on nothing else. `Settings.model_construct()` builds
the settings object without validating it and without reading the environment, so the
exporter carries no copy of the configuration contract: AD-20 keeps the number of places
that know the settings to two, the module and `.env.example`, and a table of dummy values
here would be a third. `create_app` only stores the object on `app.state` for request-time
dependencies to read, so nothing dereferences a field. If a later story makes `create_app`
read one, this fails with `AttributeError` instead of exporting a wrong document.

**Its output must be byte-stable.** `schema.d.ts` is committed and `make lint` fails on
drift, so an export whose key order varied between runs would report drift every time and
mean nothing. Keys are sorted and the file ends in exactly one newline.

`--output` exists because `… > contracts/openapi.json` truncates the committed contract
before the exporter runs: a failed build would leave an empty file behind. With `--output`
the document is written beside the destination and moved onto it only once it is complete.
Stdout stays the default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app


def build_document() -> dict[str, Any]:
    """The OpenAPI document of an application that has performed no I/O.

    `lifespan` is left at `None`, so the application built here never runs the migration
    step — this process talks to no database at any point.
    """
    return create_app(Settings.model_construct()).openapi()


def render(document: dict[str, Any]) -> str:
    """The document as the committed file holds it: sorted, indented, newline-terminated."""
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _replace(text: str, destination: Path) -> None:
    """Write `text` to `destination` atomically, leaving nothing behind on failure.

    The temporary file is created in the destination's own directory so that the final
    move is a rename within one filesystem, which is what makes it atomic.
    """
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the OpenAPI contract (AD-3).")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write the document to this file atomically; the default is stdout",
    )
    args = parser.parse_args(argv)

    text = render(build_document())
    if args.output is None:
        sys.stdout.write(text)
    else:
        _replace(text, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
