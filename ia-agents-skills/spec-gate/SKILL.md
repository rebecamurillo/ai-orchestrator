---
name: spec-gate
description: Review the spec folder before the story loop — identify open questions and formatting problems in SPEC.md and stories.yaml; fix formatting defects in place and write a result file for routing.
args:
  folder: "Absolute path to the spec folder containing SPEC.md and stories.yaml"
---

# Spec Gate

## Purpose

Review the spec folder at `{folder}` before the story loop begins. Identify open questions and formatting problems across `SPEC.md` and `stories.yaml`. Fix any formatting problems in place, then write `{folder}/spec-gate-result.md` so the orchestrator can route accordingly.

This skill is invoked automatically by the `epic` template's `spec-gate` step. It always writes `spec-gate-result.md` — that file's frontmatter `status` field drives routing:

- `status: done` — story loop may start
- `status: blocked` — run parks at `needs_you`; the operator resolves the listed questions and signals Continue

## On Activation

Parse `folder` from the skill args: `folder=<absolute-path>`. If `folder` is absent or empty, write `{folder}/spec-gate-result.md` (if path is known) with `status: blocked`, `blocking_condition: "missing folder arg"`, body `## Auto Run Result\nStatus: blocked\nError: skill invoked without folder arg`, and exit. If the path is not known, terminate with an error message naming the missing arg.

## Operation

### 1. Load source files

Read both files:

- `{folder}/SPEC.md`
- `{folder}/stories.yaml`

If either file is missing, treat its absence as a formatting problem (record it in the problems list) and continue with whatever is present. Do not abort.

### 2. Identify open questions

Scan each loaded file for:

- **TBD / placeholder markers** — literal `TBD`, `TODO`, `FIXME`, `???`, `<placeholder>`, `[PLACEHOLDER]`, or equivalent markers in any field value or prose paragraph.
- **Unresolved ambiguities** — `open_questions:` list entries, `assumptions:` entries whose resolution is still pending, prose that explicitly states a decision has not been made.
- **Contradictions** — a capability or constraint in `SPEC.md` that is directly contradicted by a story's `description` or `scope` in `stories.yaml` (e.g. SPEC says feature X is out of scope, a story implements it).
- **Multiple incompatible implementations** — a story description that admits two or more incompatible approaches without specifying which applies, creating genuine ambiguity an implementing agent cannot resolve from the spec alone.

Record each open question as a single line prefixed with the originating file path (relative to `{folder}`). Group them by source file.

An **open question is blocking** — it requires operator input to resolve. Do not attempt to answer open questions; record them as-is.

### 3. Identify formatting problems

Scan each loaded file for:

- **YAML parse errors** — `stories.yaml` that fails to parse as valid YAML.
- **Missing required frontmatter fields** — `stories.yaml` entries lacking `id`, `title`, or `description`; `SPEC.md` frontmatter lacking `title` or `capabilities`.
- **Broken markdown** — unclosed code fences (triple backtick without matching close), broken tables (row missing pipes, header/separator mismatch).
- **Placeholder text not filled in** — frontmatter values that are literal strings like `"<your title here>"`, `"TODO"`, or identical to the field name (e.g. `title: title`).

Record each formatting problem as a single line identifying the file and the defect. Formatting problems are fixable — do not report them as open questions.

### 4. Branch on findings

#### Branch A — Open questions present (possibly with formatting problems too)

Do not attempt to fix formatting problems when open questions are present; the operator will revisit the spec anyway. Write `{folder}/spec-gate-result.md` immediately:

```
---
status: blocked
blocking_condition: "open questions"
---

# Spec Gate Result

## Auto Run Result

Status: blocked

### SPEC.md

<one line per open question found in SPEC.md, or "(none)" if none>

### stories.yaml

<one line per open question found in stories.yaml, or "(none)" if none>
```

Exit after writing the result file. Do not commit anything.

#### Branch B — Formatting problems only (no open questions)

Fix each defect in the affected file. Fixes must be minimal and mechanical — correct the syntax without changing the content's meaning:

- Close unclosed code fences.
- Add missing YAML keys with a `# TODO: fill in` comment value so the file is valid but the gap is visible.
- Replace broken table rows with syntactically valid rows preserving existing cell content.
- Correct malformed frontmatter that prevents parsing.

After all fixes are applied, stage and commit with the exact message:

```
git commit --message "spec: gate fixes (orchestrator)"
```

Then write `{folder}/spec-gate-result.md`:

```
---
status: done
---

# Spec Gate Result

## Auto Run Result

Status: done
Outcome: formatting fixes applied

### Fixes

<one line per fix: file — what was fixed>
```

#### Branch C — Clean (no open questions, no formatting problems)

Write `{folder}/spec-gate-result.md`:

```
---
status: done
---

# Spec Gate Result

## Auto Run Result

Status: done
Outcome: clean
```

## Output

The skill's only required output is `{folder}/spec-gate-result.md`. The orchestrator's `agent_tail` reads `expect.files` — this file must exist when the skill exits. Never exit without writing it.

The result file is always at `{folder}/spec-gate-result.md` regardless of branch.
