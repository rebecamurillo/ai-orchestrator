"""`gate_verdict.verdict_of` and `routed_with_verdict` (epic 8 story 2, AD-37)."""

from __future__ import annotations

from orchestrator.application.steps import gate_verdict
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.values import GateVerdict, StepResult
from tests.unit.application.steps.agent_fixtures import an_agent_row

PATH = "spec/gate.md"
FAIL = "---\nstatus: fail\nowners: [ux, tech]\n---\n\n- defect one\n- defect two\n"


def a_gate(role: str = "spec-gate") -> StepRun:
    return an_agent_row().model_copy(update={"role": role})


def test_a_fail_verdict_carries_word_owners_and_body() -> None:
    verdict = gate_verdict.verdict_of(a_gate(), PATH, FAIL)

    assert verdict is not None
    assert verdict.word == "fail"
    assert verdict.fields == {"status": "fail", "owners": ["ux", "tech"]}
    assert verdict.text == "\n- defect one\n- defect two"


def test_a_pass_verdict_carries_its_word() -> None:
    verdict = gate_verdict.verdict_of(a_gate(), PATH, "---\nstatus: pass\n---\nok\n")

    assert verdict is not None and verdict.word == "pass"


def test_another_role_has_no_verdict() -> None:
    assert gate_verdict.verdict_of(a_gate("implement"), PATH, FAIL) is None


def test_an_unparseable_file_has_no_verdict() -> None:
    assert gate_verdict.verdict_of(a_gate(), PATH, "no frontmatter") is None


def test_the_text_is_cut_at_the_cap() -> None:
    text = "---\nstatus: pass\n---\n" + "x" * (gate_verdict.VERDICT_TEXT_MAX + 10)

    verdict = gate_verdict.verdict_of(a_gate(), PATH, text)

    assert verdict is not None
    assert verdict.text == "x" * gate_verdict.VERDICT_TEXT_MAX


def test_the_fields_are_json_safe() -> None:
    text = (
        "---\nstatus: pass\nwhen: 2026-11-25\nnested: {a: [1, 2.5, true, null]}\n"
        "1: numeric key\n---\nbody\n"
    )

    verdict = gate_verdict.verdict_of(a_gate(), PATH, text)

    assert verdict is not None
    assert verdict.fields["when"] == "2026-11-25"
    assert verdict.fields["nested"] == {"a": [1, 2.5, True, None]}
    assert verdict.fields["1"] == "numeric key"
    assert type(verdict.fields["nested"]) is dict


def test_a_done_result_gets_the_verdict() -> None:
    routed = StepResult(status="done", gate="liveness")

    result = gate_verdict.routed_with_verdict(routed, a_gate(), PATH, lambda _p: FAIL)

    assert result.verdict == GateVerdict(
        word="fail",
        fields={"status": "fail", "owners": ["ux", "tech"]},
        text="\n- defect one\n- defect two",
    )
    assert result.status == "done"


def test_a_result_that_is_not_done_is_untouched() -> None:
    routed = StepResult(status="blocked", gate="liveness")

    assert gate_verdict.routed_with_verdict(routed, a_gate(), PATH, lambda _p: FAIL) is routed


def test_no_path_leaves_the_result_untouched() -> None:
    routed = StepResult(status="done", gate="liveness")

    assert gate_verdict.routed_with_verdict(routed, a_gate(), None, lambda _p: FAIL) is routed


def test_an_unreadable_file_leaves_the_result_untouched() -> None:
    routed = StepResult(status="done", gate="liveness")

    assert gate_verdict.routed_with_verdict(routed, a_gate(), PATH, lambda _p: None) is routed


def test_another_role_leaves_the_result_untouched() -> None:
    routed = StepResult(status="done", gate="liveness")

    assert (
        gate_verdict.routed_with_verdict(routed, a_gate("implement"), PATH, lambda _p: FAIL)
        is routed
    )


def test_nul_and_non_finite_floats_never_reach_storage() -> None:
    text = '---\nstatus: pass\nnote: "a\\0b"\nbad: .nan\nbig: -.inf\n---\nx\x00y\n'

    verdict = gate_verdict.verdict_of(a_gate(), PATH, text)

    assert verdict is not None
    assert verdict.fields["note"] == "ab"
    assert verdict.fields["bad"] == "nan"
    assert verdict.fields["big"] == "-inf"
    assert verdict.text == "xy"


def test_an_alias_bomb_keeps_only_the_word() -> None:
    levels = ["l0: &l0 [" + ", ".join(["x"] * 10) + "]"]
    for n in range(1, 8):
        levels.append(f"l{n}: &l{n} [" + ", ".join([f"*l{n - 1}"] * 10) + "]")
    text = "---\nstatus: fail\n" + "\n".join(levels) + "\n---\nbody\n"

    verdict = gate_verdict.verdict_of(a_gate(), PATH, text)

    assert verdict is not None
    assert verdict.fields == {"status": "fail"}
    assert verdict.word == "fail"


def test_an_oversized_string_keeps_only_the_word() -> None:
    text = "---\nstatus: pass\nnote: " + "y" * gate_verdict.VERDICT_FIELDS_MAX + "\n---\n"

    verdict = gate_verdict.verdict_of(a_gate(), PATH, text)

    assert verdict is not None and verdict.fields == {"status": "pass"}


def test_another_role_is_never_read() -> None:
    routed = StepResult(status="done", gate="liveness")
    reads: list[str] = []

    def read(path: str) -> str | None:
        reads.append(path)
        return FAIL

    assert gate_verdict.routed_with_verdict(routed, a_gate("implement"), PATH, read) is routed
    assert reads == []
