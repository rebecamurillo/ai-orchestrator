"""The pure rules of `package.yaml` and a package template's steps (story 3 of epic 6)."""

from __future__ import annotations

import pytest

from orchestrator.application.packages import declaration as d
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.project_package import StepDecl
from tests.unit.application.package_fixtures import package_text, spec_text
from tests.unit.fakes.templates import FakeTemplateVersionRepository

FILE = "pkg/package.yaml"
TWO = 2


def parse(text: str) -> d.ParsedPackage:
    return d.parse_package(text, FILE)


def reasons(text: str) -> list[str]:
    with pytest.raises(d.PackageInvalid) as raised:
        parse(text)
    assert {p.file for p in raised.value.problems} == {FILE}
    return [p.reason for p in raised.value.problems]


def parsed_template(text: str):  # type: ignore[no-untyped-def]
    result = validate(text, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None, result.errors
    return result.template


def test_a_valid_package_parses() -> None:
    package = parse(package_text())

    assert package.name == "acme"
    assert [(e.workflow, e.is_file) for e in package.entries] == [
        ("spec", True),
        ("merge", True),
        ("build", False),
    ]
    assert package.pass_words == ("pass",)
    assert package.fail_words == ("fail",)
    assert package.owners_key == "owners"
    assert package.status_map == {"final": "done", "blocked": "waiting for her"}


@pytest.mark.parametrize("text", ["a: [", "- 1\n- 2\n", "just text"])
def test_bad_yaml_or_a_non_mapping(text: str) -> None:
    assert reasons(text)[0].startswith("invalid yaml")


def test_unknown_and_missing_keys() -> None:
    assert reasons("extra: 1\nname: a\n") == [
        "unknown key extra",
        "missing key sequence",
        "missing key gate",
        "missing key status_map",
    ]


def test_a_bad_name() -> None:
    assert reasons(package_text(name="Bad_Name")) == ["name: must match ^[a-z][a-z0-9-]*$"]


@pytest.mark.parametrize("sequence", ["  []", "  not-a-list"])
def test_an_empty_or_malformed_sequence(sequence: str) -> None:
    text = package_text(sequence=sequence)
    assert reasons(text) == ["sequence: must be a non-empty list"]


def test_sequence_entry_rules() -> None:
    sequence = (
        "  - { workflow: spec, template: a.yaml }\n"
        "  - { workflow: spec, template: ../b.yaml }\n"
        "  - { workflow: Bad, template: '', extra: 1 }\n"
        "  - 5\n"
    )
    found = reasons(package_text(sequence=sequence))
    assert "workflow spec appears twice" in found
    assert "sequence[1]: template ../b.yaml is not a path inside the package" in found
    assert "sequence[2]: unknown key extra" in found
    assert "sequence[2]: workflow must match ^[a-z][a-z0-9-]*$" in found
    assert "sequence[2]: template must be a non-empty string" in found
    assert "sequence[3]: must be a mapping" in found


def test_gate_rules() -> None:
    assert reasons(package_text(gate="5")) == [
        "gate: must be a mapping of pass, fail and owners_key"
    ]
    found = reasons(package_text(gate="{ pass: [], fail: [''], extra: 1, owners_key: Bad }"))
    assert "gate: unknown key extra" in found
    assert "gate.pass: must be a non-empty list of non-empty strings" in found
    assert "gate.fail: must be a non-empty list of non-empty strings" in found
    assert "gate.owners_key: must match ^[a-z_][a-z0-9_]*$" in found
    assert "gate: missing key owners_key" not in found
    assert "gate: missing key pass" not in found


def test_gate_missing_keys_and_shared_word() -> None:
    assert reasons(package_text(gate="{ pass: [a] }")) == [
        "gate: missing key fail",
        "gate: missing key owners_key",
        "gate.fail: must be a non-empty list of non-empty strings",
    ]
    both = reasons(package_text(gate="{ pass: [x], fail: [x], owners_key: o }"))
    assert both == ["word x is in both gate.pass and gate.fail"]


def test_status_map_rules() -> None:
    assert reasons(package_text(status_map="{}")) == ["status_map: must be a non-empty mapping"]
    found = reasons(package_text(status_map="{ final: finished, '': done }"))
    assert (
        "status_map final: finished is not one of done, running, waiting for her, failed" in found
    )
    assert "status_map : key must be a word" in found


def test_stems_and_duplicates() -> None:
    assert d.stem_of("a/b/spec.yaml") == "spec"
    assert d.stem_of("spec.yaml") == "spec"
    package = parse(
        package_text(
            sequence=(
                "  - { workflow: a, template: a/spec.yaml }\n"
                "  - { workflow: b, template: b/spec.yaml }\n"
                "  - { workflow: c, template: shipped }\n"
                "  - { workflow: e, template: e/other.yaml }\n"
            )
        )
    )
    assert d.duplicate_stems(package.entries, "pkg") == [
        d.PackageProblem(
            "pkg/b/spec.yaml", "two templates have the stem spec: a/spec.yaml, b/spec.yaml"
        )
    ]


def test_entry_steps_in_row_order() -> None:
    steps = d.entry_steps(parsed_template(spec_text()))

    assert steps == (
        StepDecl(
            id="intake",
            kind="conversation",
            skill="bmad-intake",
            persona="Mary",
            file="docs/intake.md",
            writes=("docs/intake.md",),
        ),
        StepDecl(
            id="product",
            kind="conversation",
            skill="bmad-product",
            persona="Mary",
            file="docs/product.md",
            writes=("docs/product.md",),
        ),
        StepDecl(
            id="gate", kind="automatic", skill=None, persona=None, file="docs/gate.md", writes=()
        ),
    )


def test_a_template_with_neither_has_no_steps() -> None:
    text = "name: m\nversion: 1\nsteps:\n  - id: a\n    uses: git.merge\n    gate: deterministic\n"
    assert d.entry_steps(parsed_template(text)) == ()


def test_a_gate_row_without_files_has_no_file() -> None:
    text = spec_text(gate=False) + (
        "  - id: g\n    uses: git.merge\n    role: spec-gate\n    gate: deterministic\n"
    )
    steps = d.entry_steps(parsed_template(text))
    assert steps[-1].file is None


def test_gate_problems() -> None:
    pkg = parse(package_text())
    ok = parsed_template(spec_text())
    plain = parsed_template(spec_text(gate=False))
    assert d.gate_problems([("pkg/a.yaml", ok)], pkg, "pkg") == []
    assert [p.reason for p in d.gate_problems([("pkg/a.yaml", plain)], pkg, "pkg")] == [
        "no spec-gate row in the package's templates"
    ]
    twice = d.gate_problems([("pkg/a.yaml", ok), ("pkg/b.yaml", ok)], pkg, "pkg")
    assert twice[0].reason.startswith("more than one spec-gate row: ")
    short = parsed_template(spec_text(gate_success="pass"))
    assert d.gate_problems([("pkg/a.yaml", short)], pkg, "pkg") == [
        d.PackageProblem(
            "pkg/a.yaml", "spec-gate row gate does not list gate word fail in expect.success"
        )
    ]
    bare = spec_text(gate=False) + (
        "  - id: g\n    uses: git.merge\n    role: spec-gate\n    gate: deterministic\n"
    )
    assert len(d.gate_problems([("pkg/a.yaml", parsed_template(bare))], pkg, "pkg")) == TWO


def test_shown_as() -> None:
    conversation = (
        StepDecl(id="a", kind="conversation", skill=None, persona=None, file=None, writes=()),
    )
    assert d.shown_as(0, "interactive", ()) == "workflow"
    assert d.shown_as(1, "interactive", ()) == "step"
    assert d.shown_as(1, "interactive", conversation) == "workflow"
    assert d.shown_as(1, "auto", ()) == "workflow"


def test_a_workflow_that_is_not_text_is_refused_not_raised() -> None:
    text = (
        package_text()
        .replace("workflow: spec", "workflow: [spec]")
        .replace("workflow: merge", "workflow: [spec]")
    )

    assert "sequence[0]: workflow must match ^[a-z][a-z0-9-]*$" in reasons(text)
