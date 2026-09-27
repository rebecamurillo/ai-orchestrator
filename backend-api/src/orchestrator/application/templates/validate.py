"""`validate()` — the one function that reads Template DSL v1 (AD-15).

`POST /templates/{name}/validate`, `plan_run` and `application/graph.py` call this and
nothing else parses Template YAML. There is no second parser, in Python or in TypeScript:
what the editor shows and what a Run is planned from are the same judgement.

Four things hold whatever the input is:

- **It never raises.** Text that is not YAML at all is one `invalid yaml` record.
- **Every problem in the file is found in one pass.** The three checkers each read the
  whole tree and each skips what it cannot read, so a file with several mistakes reports
  several mistakes rather than the first one.
- **Errors come back sorted by line.** The sort is stable, so within one line the order is
  the order the checkers found them in — the same output for the same input, every time.
- **`template` is `None` whenever `errors` is non-empty.** There is no partially valid
  Template; `unvalidated` is reported either way, because a step with no declared gate is
  a fact about the file and not a consequence of the rest of it (NFR-2).
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps import AGENT_KIND, KIND_META, TEMPLATE_CALL_KIND
from orchestrator.application.templates.calls import check_calls
from orchestrator.application.templates.expressions import check_expressions
from orchestrator.application.templates.keys import check_keys
from orchestrator.application.templates.lines import (
    AS_KEY,
    FOR_EACH_KEY,
    LinedMap,
    as_map,
    as_seq,
    child_steps,
    is_for_each,
    key_line,
    load_with_lines,
)
from orchestrator.application.templates.model import (
    INVALID_YAML,
    AgentExtras,
    ForEach,
    InputDecl,
    ParsedTemplate,
    Step,
    TemplateCall,
    ValidationError,
    ValidationResult,
)
from orchestrator.application.templates.table import (
    RUN_KEY,
    RUN_SUGAR_KIND,
    WITH_KEY,
    WRITES_KEY,
    is_count,
    problem,
)
from orchestrator.domain.ports.templates import TemplateVersionRepository

#: The `with` key a bare `run: <command>` desugars into.
COMMAND_KEY = "command"

#: `resume_session` defaults on: a harness that can resume a session should resume it.
RESUME_DEFAULT = True


def validate(yaml_text: str, *, templates: TemplateVersionRepository) -> ValidationResult:
    """Read one Template file: the parsed tree, or every problem in it, by line and reason."""
    loaded = load_with_lines(yaml_text)
    if loaded.root is None:
        return ValidationResult(errors=(problem(loaded.line, INVALID_YAML),))
    root = loaded.root
    found, unvalidated = check_keys(root)
    found += check_expressions(root)
    found += check_calls(root, templates)
    unique = _deduplicated(found)
    unique.sort(key=lambda record: record.line)
    errors = tuple(_stamped(record, root) for record in unique)
    if errors:
        return ValidationResult(errors=errors, unvalidated=tuple(unvalidated))
    return ValidationResult(template=parse(root), unvalidated=tuple(unvalidated))


def _deduplicated(found: list[ValidationError]) -> list[ValidationError]:
    """One record per `(line, reason)`, in the order they were first found.

    Two checkers can reach the same offence by different routes — a callee pinned twice by
    the same caller is one mistake — and the matrix promises one error per row. The cost is
    that two genuinely separate offences sharing a line and a reason are reported once;
    the line is the unit the Operator acts on, so that is the right side to err on.
    """
    seen: set[tuple[int, str]] = set()
    unique: list[ValidationError] = []
    for record in found:
        key = (record.line, record.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _stamped(record: ValidationError, root: LinedMap) -> ValidationError:
    """Each record says which Template it is about, as far as the file managed to say."""
    name, version = root.get("name"), root.get("version")
    return record.model_copy(
        update={
            "template": name if isinstance(name, str) else None,
            "version": version if is_count(version) else None,
        }
    )


# --- building the tree ---------------------------------------------------------------------


def parse(root: LinedMap) -> ParsedTemplate:
    """The frozen tree of a file that has already passed every checker."""
    inputs = as_map(root.get("inputs")) or LinedMap()
    return ParsedTemplate(
        line=root.line,
        name=root["name"],
        version=root["version"],
        description=_text(root.get("description")),
        inputs=tuple(_input(inputs, name) for name in inputs),
        steps=tuple(_entry(node) for node in child_steps(root)),
    )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _plain(value: Any) -> Any:
    """The same value with the line bookkeeping dropped: a tree, not a loader's output."""
    mapping = as_map(value)
    if mapping is not None:
        return {key: _plain(sub) for key, sub in mapping.items()}
    sequence = as_seq(value)
    if sequence is not None:
        return [_plain(item) for item in sequence]
    return value


def _input(inputs: LinedMap, name: str) -> InputDecl:
    decl = inputs[name]
    return InputDecl(
        line=key_line(inputs, name, inputs.line),
        name=name,
        type=decl["type"],
        required=decl.get("required") is True,
        default=decl.get("default"),
        values=tuple(as_seq(decl.get("values")) or ()),
    )


def _entry(node: LinedMap) -> Step | ForEach:
    if is_for_each(node):
        return ForEach(
            line=node.line,
            id=node["id"],
            source=node[FOR_EACH_KEY],
            as_name=node[AS_KEY],
            steps=tuple(_step(child) for child in child_steps(node)),
            pause_before_item_when=_text(node.get("pause_before_item_when")),
            pause_after_item_when=_text(node.get("pause_after_item_when")),
            only=_text(node.get("only")),
        )
    return _step(node)


def _step(node: LinedMap) -> Step:
    kind = RUN_SUGAR_KIND if RUN_KEY in node else str(node["uses"])
    params = as_map(node.get(WITH_KEY)) or LinedMap()
    action, redispatch, limit = _on_fail(node)
    return Step(
        line=node.line,
        id=node["id"],
        uses=kind,
        meta=KIND_META[kind],
        params=_params(node, params, kind),
        gate=node.get("gate"),
        timeout_min=node.get("timeout_min"),
        stall_min=node.get("stall_min"),
        on_fail=action,
        redispatch=redispatch,
        redispatch_max=limit,
        agent=_agent(node) if kind == AGENT_KIND else None,
        call=_call(params) if kind == TEMPLATE_CALL_KIND else None,
    )


def _params(node: LinedMap, params: LinedMap, kind: str) -> tuple[tuple[str, Any], ...]:
    """The `with` map as pairs. A call's `with` is its `call`, so it holds no params."""
    if RUN_KEY in node:
        return ((COMMAND_KEY, _plain(node[RUN_KEY])),)
    if kind == TEMPLATE_CALL_KIND:
        return ()
    return tuple((str(key), _plain(value)) for key, value in params.items())


def _on_fail(node: LinedMap) -> tuple[Any, str | None, int | None]:
    value = node.get("on_fail")
    if isinstance(value, str):
        return value, None, None
    redispatch = as_map(value)
    if redispatch is None:
        return None, None, None
    return None, redispatch["redispatch"], redispatch["max"]


def _agent(node: LinedMap) -> AgentExtras:
    expect = as_map(node.get("expect")) or LinedMap()
    retry = as_map(node.get("retry")) or LinedMap()
    prompts = as_map(node.get("prompts")) or LinedMap()
    return AgentExtras(
        line=node.line,
        expect_files=tuple(as_seq(expect.get("files")) or ()),
        expect_status_in=tuple(as_seq(expect.get("status_in")) or ()),
        retry_max=retry.get("max"),
        retry_prompt=retry.get("prompt"),
        retry_resume_session=retry.get("resume_session", RESUME_DEFAULT),
        escalate_when=_text(node.get("escalate_when")),
        pause_when=_text(node.get("pause_when")),
        writes=tuple(as_seq(node.get(WRITES_KEY)) or ()),
        prompt_dispatch=_text(prompts.get("dispatch")),
        prompt_rendered=_text(prompts.get("rendered")),
        prompt_answer=_text(prompts.get("answer")),
        prompt_halt=_text(prompts.get("halt")),
    )


def _call(params: LinedMap) -> TemplateCall:
    bindings = as_map(params.get("inputs")) or LinedMap()
    return TemplateCall(
        line=params.line,
        name=params["name"],
        version=params["version"],
        inputs=tuple((str(key), value) for key, value in bindings.items()),
    )
