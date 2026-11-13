"""Lock-file and manifest parsing (epic 5 story 3, AC1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.analysis.lockfiles import (
    LOCK_ECOSYSTEM,
    MANIFEST_ECOSYSTEM,
    parse_lock,
    parse_manifest,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis" / "tier1b"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_the_ecosystem_tables_name_the_supported_files() -> None:
    assert LOCK_ECOSYSTEM == {
        "package-lock.json": "npm",
        "pnpm-lock.yaml": "npm",
        "uv.lock": "pypi",
        "poetry.lock": "pypi",
    }
    assert MANIFEST_ECOSYSTEM == {"package.json": "npm", "pyproject.toml": "pypi"}


def test_pnpm_lock_v9_lists_scoped_names_without_the_peer_suffix() -> None:
    parsed = parse_lock("pnpm-lock.yaml", fixture("pnpm-lock.head.yaml"))
    assert parsed.problem is None
    assert parsed.packages == {
        "@scope/pkg": frozenset({"1.0.0"}),
        "left-pad": frozenset({"1.3.0"}),
        "react": frozenset({"18.2.0"}),
        "zod": frozenset({"3.23.8"}),
    }


def test_pnpm_lock_v6_and_v5_key_shapes() -> None:
    v6 = (
        "lockfileVersion: '6.0'\npackages:\n  /zod@3.22.4:\n    x: 1\n"
        "  /@s/p@1.0.0(react@18.2.0):\n    x: 1\n"
    )
    v5 = (
        "lockfileVersion: 5.4\npackages:\n  /zod/3.22.4:\n    x: 1\n"
        "  /@s/p/1.0.0_react@18.2.0:\n    x: 1\n"
    )
    assert parse_lock("pnpm-lock.yaml", v6).packages == {
        "zod": frozenset({"3.22.4"}),
        "@s/p": frozenset({"1.0.0"}),
    }
    assert parse_lock("pnpm-lock.yaml", v5).packages == {
        "zod": frozenset({"3.22.4"}),
        "@s/p": frozenset({"1.0.0"}),
    }


def test_package_lock_v3_reads_node_modules_keys_and_skips_the_root() -> None:
    parsed = parse_lock("package-lock.json", fixture("package-lock.base.json"))
    assert parsed.packages == {
        "zod": frozenset({"3.22.4"}),
        "old-dep": frozenset({"2.0.0"}),
        "@scope/nested": frozenset({"1.1.0"}),
    }


def test_package_lock_v1_reads_dependencies_recursively() -> None:
    text = (
        '{"lockfileVersion": 1, "dependencies": {"a": {"version": "1.0.0", '
        '"dependencies": {"b": {"version": "2.0.0"}}}, "c": {}, "d": 5}}'
    )
    assert parse_lock("package-lock.json", text).packages == {
        "a": frozenset({"1.0.0"}),
        "b": frozenset({"2.0.0"}),
    }


def test_package_lock_collects_every_version_of_a_name() -> None:
    text = (
        '{"packages": {"node_modules/x": {"version": "1.0.0"}, '
        '"node_modules/y/node_modules/x": {"version": "2.0.0"}, "node_modules/z": {}}}'
    )
    assert parse_lock("package-lock.json", text).packages == {"x": frozenset({"1.0.0", "2.0.0"})}


def test_uv_lock_skips_editable_and_virtual_and_normalises_names() -> None:
    base = parse_lock("uv.lock", fixture("uv.base.lock")).packages
    head = parse_lock("uv.lock", fixture("uv.head.lock")).packages
    assert base == {"requests": frozenset({"2.31.0"}), "old-lib": frozenset({"1.0.0"})}
    assert head == {"requests": frozenset({"2.32.3"}), "new-lib": frozenset({"0.4.0"})}


def test_poetry_lock_normalises_names() -> None:
    parsed = parse_lock("poetry.lock", fixture("poetry.head.lock"))
    assert parsed.packages == {
        "click": frozenset({"8.1.8"}),
        "typing-extensions": frozenset({"4.12.2"}),
    }


@pytest.mark.parametrize("name", list(LOCK_ECOSYSTEM))
def test_no_text_is_no_packages_and_no_problem(name: str) -> None:
    parsed = parse_lock(name, None)
    assert parsed.packages == {}
    assert parsed.problem is None


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("package-lock.json", "{not json"),
        ("package-lock.json", "[1]"),
        ("pnpm-lock.yaml", "a: [unclosed"),
        ("pnpm-lock.yaml", "- a"),
        ("uv.lock", "= not toml"),
        ("poetry.lock", "package = 3"),
    ],
)
def test_an_unparseable_lock_file_is_no_packages_and_a_problem(name: str, text: str) -> None:
    parsed = parse_lock(name, text)
    assert parsed.packages == {}
    assert parsed.problem is not None
    assert name in parsed.problem


def test_a_pnpm_tarball_key_keeps_its_url_out_of_the_package_name() -> None:
    text = (
        "lockfileVersion: '9.0'\npackages:\n"
        "  foo@https://user:TOKEN@npm.corp/foo.tgz:\n    x: 1\n"
        "  '@s/p@git+https://TOKEN@host/p.git':\n    x: 1\n"
    )
    assert parse_lock("pnpm-lock.yaml", text).packages == {
        "foo": frozenset({"https://user:TOKEN@npm.corp/foo.tgz"}),
        "@s/p": frozenset({"git+https://TOKEN@host/p.git"}),
    }


def test_a_pep508_direct_reference_ends_the_name_at_the_at_sign() -> None:
    text = '[project]\ndependencies = ["pkg@git+https://TOKEN@github.com/x", "b @ file:///x"]\n'
    assert set(parse_manifest("pyproject.toml", text).packages) == {"pkg", "b"}


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("package-lock.json", '{"packages": [1, 2]}'),
        ("pnpm-lock.yaml", "packages: 3"),
        ("pnpm-lock.yaml", "packages: [a, b]"),
    ],
)
def test_a_lock_file_of_the_wrong_shape_is_a_problem_not_a_crash(name: str, text: str) -> None:
    parsed = parse_lock(name, text)
    assert parsed.packages == {}
    assert parsed.problem == f"{name}: not parseable"


def test_a_v1_package_lock_with_non_table_dependencies_holds_what_it_can() -> None:
    text = '{"dependencies": {"a": {"version": "1.0.0", "dependencies": [1]}}}'
    assert parse_lock("package-lock.json", text).packages == {"a": frozenset({"1.0.0"})}
    assert parse_lock("package-lock.json", '{"dependencies": "x"}').packages == {}


def test_an_unknown_lock_name_is_no_packages() -> None:
    parsed = parse_lock("Gemfile.lock", "anything")
    assert parsed.packages == {}
    assert parsed.problem is None


def test_package_json_reads_every_dependency_table() -> None:
    parsed = parse_manifest("package.json", fixture("package.head.json"))
    assert parsed.packages == {
        "zod": frozenset({"^3.23.0"}),
        "left-pad": frozenset({"^1.3.0"}),
        "fsevents": frozenset({"^2.3.3"}),
    }
    base = parse_manifest("package.json", fixture("package.base.json"))
    assert base.packages == {"zod": frozenset({"^3.22.0"}), "vitest": frozenset({"^1.0.0"})}


def test_package_json_peer_dependencies_count() -> None:
    parsed = parse_manifest("package.json", '{"peerDependencies": {"react": ">=18"}}')
    assert parsed.packages == {"react": frozenset({">=18"})}


def test_pyproject_reads_dependencies_and_optional_dependencies() -> None:
    text = (
        '[project]\nname = "x"\ndependencies = ["Requests>=2.0", "click[extra] ~=8.0; '
        'python_version>\'3.8\'", "pkg (>=1)"]\n'
        '[project.optional-dependencies]\ndev = ["pytest!=7.0", "Typing_Extensions"]\n'
    )
    assert parse_manifest("pyproject.toml", text).packages == {
        "requests": frozenset({">=2.0"}),
        "click": frozenset({"[extra] ~=8.0; python_version>'3.8'"}),
        "pkg": frozenset({"(>=1)"}),
        "pytest": frozenset({"!=7.0"}),
        "typing-extensions": frozenset({""}),
    }


@pytest.mark.parametrize(
    ("name", "text"),
    [("package.json", "{nope"), ("package.json", "[]"), ("pyproject.toml", "= x")],
)
def test_an_unparseable_manifest_is_no_packages_and_a_problem(name: str, text: str) -> None:
    parsed = parse_manifest(name, text)
    assert parsed.packages == {}
    assert parsed.problem is not None


def test_no_manifest_text_and_an_unknown_manifest() -> None:
    assert parse_manifest("package.json", None).packages == {}
    assert parse_manifest("pyproject.toml", None).problem is None
    assert parse_manifest("pom.xml", "<x/>").packages == {}


def test_a_pyproject_without_a_project_table_and_junk_entries() -> None:
    assert parse_manifest("pyproject.toml", "[tool.x]\na = 1\n").packages == {}
    assert parse_manifest("pyproject.toml", "project = 3\n").packages == {}
    odd = '[project]\ndependencies = [3, ""]\n[project.optional-dependencies]\ndev = "no"\n'
    assert parse_manifest("pyproject.toml", odd).packages == {}


NESTED_V1 = '{"dependencies": ' + '{"a": {"dependencies": ' * 3000 + "{}" + "}}" * 3000 + "}"
DEEP = "[" * 100_000 + "]" * 100_000


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("package-lock.json", NESTED_V1),
        ("package-lock.json", DEEP),
        ("pnpm-lock.yaml", DEEP),
        ("package.json", DEEP),
    ],
    ids=["v1-recursion", "json", "yaml", "manifest"],
)
def test_a_file_nested_past_the_recursion_limit_is_a_problem_not_a_crash(
    name: str, text: str
) -> None:
    parse = parse_manifest if name == "package.json" else parse_lock
    parsed = parse(name, text)
    assert parsed.packages == {}
    assert parsed.problem == f"{name}: not parseable"
