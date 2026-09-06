"""The one parser and validator of Template DSL v1 (AD-15).

`validate.py` is the only module anything outside this package imports: it holds the single
public entry point `validate(yaml_text, *, templates)`. The siblings are its private parts —
`lines.py` loads YAML while recording line numbers, `model.py` holds the parsed tree and
the result vocabulary, and `keys.py`, `expressions.py` and `calls.py` are the three checkers
it runs. They are separate modules because the key table alone exceeds the 400-line limit
`backend-api/AGENTS.md` puts on a module, not because there is more than one parser.

Nothing here performs I/O. A callee is reached through `TemplateVersionRepository`; `yaml`
is the only third-party import in the package, and it lives in `lines.py` alone (AD-2).
"""
