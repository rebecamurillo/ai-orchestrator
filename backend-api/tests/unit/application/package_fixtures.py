"""Fixture packages the package tests own: never `templates/*.yaml` (hard rule 6)."""

from __future__ import annotations

from tests.unit.application.templates.test_conversation_kind import document

SHA = "a" * 40
PATH = "pkg"

SPEC_GATE_ROW = """  - id: {id}
    uses: agent
    role: spec-gate
    with: {{ skill: spec-gate }}
    prompts:
      dispatch: "Run {{skill}}."
      rendered: "Rendered at {{path}}."
    expect:
      files: ["docs/{id}.md"]
      success: [{success}]
      blocked: [blocked]
    gate: liveness
"""

MERGE = """name: merge
version: 1
type: interactive
steps:
  - id: merge
    uses: git.merge
    gate: deterministic
"""


def spec_text(name: str = "spec", gate_success: str = "pass, fail", gate: bool = True) -> str:
    text = document(names=("intake", "product")).replace("name: talking", f"name: {name}")
    if gate:
        text += SPEC_GATE_ROW.format(id="gate", success=gate_success)
    return text


def merge_text(name: str = "merge") -> str:
    return MERGE.replace("name: merge", f"name: {name}")


def package_text(**overrides: str) -> str:
    parts = {
        "name": "acme",
        "sequence": (
            "  - { workflow: spec, template: templates/spec.yaml }\n"
            "  - { workflow: merge, template: templates/merge.yaml }\n"
            "  - { workflow: build, template: shipped-build }\n"
        ),
        "gate": "{ pass: [pass], fail: [fail], owners_key: owners }",
        "status_map": "{ final: done, blocked: waiting for her }",
    }
    parts.update(overrides)
    lines = [f"name: {parts['name']}", "sequence:", parts["sequence"].rstrip("\n")]
    lines += [f"gate: {parts['gate']}", f"status_map: {parts['status_map']}"]
    return "\n".join(lines) + "\n"


def build_text(name: str = "shipped-build") -> str:
    return merge_text(name).replace("type: interactive\n", "")
