#!/usr/bin/env python3
"""Check the guide source and keep the README's shared sections generated from it (AD-32).

`make lint` runs this on the system interpreter, not under `uv`: `test_makefile.py` pins the
number of `uv` invocations in the `lint` recipe, so this stays inside the standard library
and inside syntax Python 3.9 accepts (no `match`, no runtime `X | Y`).

Checks, each failure printed as `<file>: <rule>`:

- a page id (its path under `guide/` without `.md`) is lowercase `[a-z0-9-]` segments;
- `errors/` is generated at build and never exists in the source;
- front matter opens on line 1, holds `key: value` lines only, with `title`, `kind` and
  `audience` and optionally `readme`; `release` is stamped at build and never written;
- a page with `audience: host` holds the line `Local agent on the host or the user only.`;
- a page's `readme: <id>` names one block `<!-- guide:<id> -->` … `<!-- /guide -->` in the
  README, whose content is the page body, one blank line either side. A differing block
  fails; `--write` rewrites it. Structural defects fail in both modes and write nothing.

Usage: `python3 scripts/check_guide.py [--guide PATH] [--readme PATH] [--write]`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GUIDE = REPO_ROOT / "guide"
DEFAULT_README = REPO_ROOT / "deploy" / "README.md"

ID_PATTERN = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+)*$")
README_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
KEYS = {"title", "kind", "audience", "readme"}
REQUIRED = ("title", "kind", "audience")
KINDS = {"page", "procedure"}
AUDIENCES = {"any", "host"}
HOST_LINE = "Local agent on the host or the user only."
OPENER = re.compile(r"<!-- guide:([^\s>]*) -->")
CLOSER = "<!-- /guide -->"
RUN_HINT = "run: python3 scripts/check_guide.py --write"


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_page(text: str) -> tuple[dict[str, str] | None, str, str]:
    """`(front matter, body, error)`; the front matter is None when the error is set."""
    lines = text.split("\n")
    if lines[0] != "---":
        return None, "", "front matter must open on line 1 with `---`"
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None, "", "front matter is not closed with `---`"
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(": ")
        if not sep and line.endswith(":"):
            key, sep, value = line[:-1], ":", ""
        if not sep or not key or " " in key:
            return None, "", "front matter line is not `key: value`: " + line
        meta[key] = value.strip()
    return meta, "\n".join(lines[end + 1 :]), ""


def _front_matter_errors(meta: dict[str, str]) -> list[str]:
    errors = []
    if "release" in meta:
        errors.append("`release` is stamped at build and must not be written")
    for key in sorted(set(meta) - KEYS - {"release"}):
        errors.append(f"unknown front matter key `{key}`")
    for key in REQUIRED:
        if key not in meta:
            errors.append(f"front matter lacks `{key}`")
    if "title" in meta and not meta["title"]:
        errors.append("`title` is empty")
    if "kind" in meta and meta["kind"] not in KINDS:
        errors.append("`kind` must be one of page, procedure")
    if "audience" in meta and meta["audience"] not in AUDIENCES:
        errors.append("`audience` must be one of any, host")
    if "readme" in meta and not README_ID_PATTERN.match(meta["readme"]):
        errors.append("`readme` must match [a-z0-9-]+")
    return errors


def _canonical_block(body: str) -> str:
    return "\n\n" + body.strip("\n") + "\n\n"


def check_pages(guide: Path) -> tuple[list[str], dict[str, str]]:
    """Failures, and the page body per `readme:` id."""
    failures: list[str] = []
    bodies: dict[str, str] = {}
    owners: dict[str, str] = {}
    if not guide.is_dir():
        return [f"{_display(guide)}: guide directory does not exist"], bodies
    if (guide / "errors").exists():
        failures.append(
            "{}: `errors/` is generated at build and must not exist".format(
                _display(guide / "errors")
            )
        )
    for path in sorted(guide.rglob("*.md")):
        shown = _display(path)
        page_id = path.relative_to(guide).with_suffix("").as_posix()
        if not ID_PATTERN.match(page_id):
            failures.append(f"{shown}: page id `{page_id}` must be lowercase [a-z0-9-] segments")
        meta, body, error = parse_page(path.read_text())
        if meta is None:
            failures.append(f"{shown}: {error}")
            continue
        failures.extend(f"{shown}: {e}" for e in _front_matter_errors(meta))
        if meta.get("audience") == "host" and HOST_LINE not in body.split("\n"):
            failures.append(f"{shown}: audience host page lacks the line `{HOST_LINE}`")
        if any(
            line.startswith("<!-- guide:") or line.strip() == CLOSER for line in body.split("\n")
        ):
            failures.append(f"{shown}: page body holds a guide marker line")
        section = meta.get("readme", "")
        if section and README_ID_PATTERN.match(section):
            if section in owners:
                failures.append(f"{shown}: readme id `{section}` is also used by {owners[section]}")
            owners[section] = shown
            bodies[section] = body
    return failures, bodies


def _find_blocks(text: str, shown: str) -> tuple[list[tuple[str, int, int]], list[str]]:
    """Every closed block as `(section, content start, content end)`, and the unclosed ones."""
    blocks: list[tuple[str, int, int]] = []
    failures: list[str] = []
    for opener in OPENER.finditer(text):
        close = text.find(CLOSER, opener.end())
        following = OPENER.search(text, opener.end())
        if close == -1 or (following is not None and following.start() < close):
            failures.append(f"{shown}: block `{opener.group(1)}` is not closed")
        else:
            blocks.append((opener.group(1), opener.end(), close))
    return blocks, failures


def check_readme(readme: Path, bodies: dict[str, str], write: bool) -> tuple[list[str], str | None]:
    """Failures, and the rewritten README text when `--write` found blocks to fix."""
    shown = _display(readme)
    if not readme.is_file():
        return ([f"{shown}: README does not exist"] if bodies else []), None
    text = readme.read_text()
    blocks, failures = _find_blocks(text, shown)
    sections = [section for section, _, _ in blocks]
    for section in sorted(set(sections)):
        if section not in bodies:
            failures.append(f"{shown}: block `{section}` names no page with that `readme:`")
        elif sections.count(section) > 1:
            failures.append(f"{shown}: more than one block for `{section}`")
    failures.extend(
        f"{shown}: no block for `readme: {section}`"
        for section in sorted(set(bodies) - set(sections))
    )
    if failures:
        return failures, None
    stale = [b for b in blocks if text[b[1] : b[2]] != _canonical_block(bodies[b[0]])]
    if not stale:
        return [], None
    if not write:
        return [f"{shown}: block `{b[0]}` differs from its page" for b in stale] + [RUN_HINT], None
    out, cursor = [], 0
    for section, start, end in stale:
        out.append(text[cursor:start] + _canonical_block(bodies[section]))
        cursor = end
    return [], "".join(out) + text[cursor:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the guide source and the README blocks (AD-32)."
    )
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--write", action="store_true", help="rewrite README blocks that differ")
    args = parser.parse_args(argv)

    failures, bodies = check_pages(args.guide)
    if not failures:
        readme_failures, rewritten = check_readme(args.readme, bodies, args.write)
        failures.extend(readme_failures)
        if not failures and rewritten is not None:
            args.readme.write_text(rewritten)
    if failures:
        sys.stdout.write("\n".join(failures) + "\n")
        return 1
    count = sum(1 for _ in args.guide.rglob("*.md"))
    sys.stdout.write(f"guide: {count} pages ok\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
