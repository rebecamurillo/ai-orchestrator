"""Build `guide/` into the pages the instance serves (AD-32).

Run by the image build (`--out /app/guide-build`) and by `make guide`. Source pages are copied
with `release: <VERSION>` stamped as the last front-matter key, one `errors/{code}.md` page is
generated per finding code, and `guide-index.json` lists every page. Files only, no network.

Every check runs before `--out` is touched: `--out` is deleted and recreated, so one that is or
contains the source would destroy the guide it builds from, and one inside it would be read back
as source pages by the next build.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from orchestrator.api.routers.version import VERSION_FILE
from orchestrator.application.findings import REGISTRY

ID_PATTERN = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+)*$")
REQUIRED = ("title", "kind", "audience")


class _Refused(Exception):
    pass


def _parse(path: Path, text: str) -> tuple[list[str], str, dict[str, str]]:
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        raise _Refused(f"{path}: front matter must open on line 1 and close with `---`")
    end = lines.index("---", 1)
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    missing = [key for key in REQUIRED if not meta.get(key)]
    if missing:
        raise _Refused(f"{path}: front matter lacks {', '.join(missing)}")
    return lines[1:end], "\n".join(lines[end + 1 :]), meta


def _load(source: Path) -> list[tuple[str, list[str], str, dict[str, str]]]:
    pages = []
    for path in sorted(source.rglob("*.md")):
        page_id = path.relative_to(source).with_suffix("").as_posix()
        if not ID_PATTERN.match(page_id):
            raise _Refused(f"{path}: page id `{page_id}` must be lowercase [a-z0-9-] segments")
        front, body, meta = _parse(path, path.read_text())
        pages.append((page_id, front, body, meta))
    return sorted(pages, key=lambda page: page[0])


def _write(path: Path, front: list[str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + "\n".join(front) + "\n---\n" + body)


def build(source: Path, out: Path, version_file: Path) -> None:
    if source.is_relative_to(out) or out.is_relative_to(source) or out == Path(out.anchor):
        raise _Refused(f"--out {out} is, contains, lies inside or is the root of --source {source}")
    pages = _load(source)
    release = version_file.read_text().strip()

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    index = []
    for page_id, front, body, meta in pages:
        _write(out / f"{page_id}.md", [*front, f"release: {release}"], body)
        index.append({"id": page_id, **{key: meta[key] for key in REQUIRED}})
    for code in sorted(REGISTRY):
        entry = REGISTRY[code]
        front = [f"title: {code}", "kind: page", "audience: any", f"release: {release}"]
        _write(out / "errors" / f"{code}.md", front, f"# {entry.message}\n\n{entry.explanation}\n")
        index.append({"id": f"errors/{code}", "title": code, "kind": "page", "audience": "any"})
    document = {"release": release, "pages": index}
    (out / "guide-index.json").write_text(json.dumps(document, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the guide (AD-32).")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, default=VERSION_FILE)
    args = parser.parse_args(argv)
    try:
        build(args.source.resolve(), args.out.resolve(), args.version_file)
    except _Refused as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
