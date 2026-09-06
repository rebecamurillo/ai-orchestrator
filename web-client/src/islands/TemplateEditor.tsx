/**
 * The Template YAML editor (3.5): CodeMirror 6 (`src/lib/editor/yamlEditor.ts`), Validate,
 * and Save-as-v{n+1}. The one island the story adds — `client:load`, five props, no `fetch`
 * of its own (`src/api/client.ts` only, AD-1).
 *
 * State lives in two places on purpose. `textRef` (a ref, not `useState`) holds the current
 * document text: CodeMirror already renders every keystroke inside its own DOM, so mirroring
 * it into React state would re-render the whole island on every character typed for no
 * visible benefit. `result` (a real `useState`) holds the last Validate/Save outcome, because
 * the readout and the error list *do* need to re-render when it changes.
 *
 * Validate runs on the *Validate* click and 800 ms after the last keystroke (Binding rules);
 * both paths call the same `validate()`, reading `textRef.current` at call time so a debounce
 * firing after a further edit still validates the latest text.
 *
 * `requestSeqRef` is one counter shared by `validate()` and `save()`: each call captures the
 * value it incremented to, and only applies its own outcome if that value is still current
 * when the network call settles. This is what a manual Validate click racing the 800 ms
 * debounce (or a stray Validate racing a Save) cannot do without it — an older response
 * landing after a newer one would otherwise overwrite the screen with a stale result (Review
 * Triage Log, story 3.5, finding 3).
 *
 * 3.6 adds one line to `validate()`: the outcome is also published to
 * `src/stores/template-validation.ts`, which is how the diagram column — a second island, in
 * a second grid cell, with no React state in common — learns that this text validated and
 * can ask for its graph. What is published is text and validity, never a graph: this island
 * validates, and the column that draws the picture is the one that fetches it.
 */
import { useEffect, useRef, useState } from 'react';
import { EditorView } from '@codemirror/view';

import type { components } from '../api/schema';
import { api } from '../api/client';
import { buildYamlExtensions, rewriteVersionLine } from '../lib/editor/yamlEditor';
import { publishValidation } from '../stores/template-validation';
import '../styles/template-editor.css';

type ProblemError = components['schemas']['ProblemError'];
type ProblemDetail = components['schemas']['ProblemDetail'];
type InputDecl = components['schemas']['InputDeclOut'];

export interface ValidateResult {
  errors: ProblemError[];
  unvalidated: string[];
  /** ISO 8601 UTC. Server time for `errorsInitial` — the page validates the stored YAML
   * before render — client time for every Validate or Save afterwards. */
  validatedAt: string;
}

interface Props {
  name: string;
  version: number;
  yaml: string;
  /** Accepted for prop-shape parity with the brief's `{name, version, yaml, inputs,
   * errorsInitial}` list; the island itself never reads it — `InputsTable.astro` renders the
   * same data independently, from the page's own fetch. Not an oversight. */
  inputs: InputDecl[];
  errorsInitial: ValidateResult;
}

const DEBOUNCE_MS = 800;
const GENERIC_FAILURE_REASON = 'the request failed';

export function readoutTime(iso: string): string {
  return iso.slice(11, 19);
}

/** `line {n} · {reason}` for a gated error, `{reason}` alone when the backend named no line;
 * `unvalidated · {path}` for each ungated step. Order matches the story's AC2: errors first,
 * then the ungated paths — both feed the same `templates-error-<n>` sequence. */
export function errorRows(result: Pick<ValidateResult, 'errors' | 'unvalidated'>): string[] {
  const named = result.errors.map((error) =>
    error.line != null ? `line ${error.line} · ${error.reason}` : error.reason,
  );
  return [...named, ...result.unvalidated.map((path) => `unvalidated · ${path}`)];
}

/**
 * A Save (or Validate) failure's `errors[]`, defaulting to one row synthesized from the
 * Problem's own `detail`/`title` when the backend sent no `errors[]` at all — a 404 "no
 * Template has that name" being the case that motivated this: `error.errors ?? []` used to
 * become `[]`, `hasErrors` read `false`, and the readout showed `valid ·` right after a Save
 * that had in fact failed (Review Triage Log, story 3.5, finding 1). `reason` is the one
 * field `ProblemError` always requires, so this can never come back empty.
 */
export function errorsFromProblem(problem: ProblemDetail): ProblemError[] {
  if (problem.errors && problem.errors.length > 0) return problem.errors;
  return [{ reason: problem.detail ?? problem.title }];
}

function genericFailureResult(): ValidateResult {
  return {
    errors: [{ reason: GENERIC_FAILURE_REASON }],
    unvalidated: [],
    validatedAt: new Date().toISOString(),
  };
}

export default function TemplateEditor({ name, version, yaml, errorsInitial }: Props) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const textRef = useRef(yaml);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const requestSeqRef = useRef(0);
  const [result, setResult] = useState<ValidateResult>(errorsInitial);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);

  async function validate(): Promise<void> {
    const seq = ++requestSeqRef.current;
    // captured before the request so that what is published is the text that was validated,
    // not whatever has been typed by the time the response lands
    const validated = textRef.current;
    setValidating(true);
    try {
      const { data, error } = await api.POST('/templates/{name}/validate', {
        params: { path: { name } },
        body: { yaml: validated },
      });
      if (seq !== requestSeqRef.current) return; // superseded by a newer Validate or Save
      if (error || !data) {
        // the readout keeps its prior value (3.5), but the diagram must not: this text was
        // never validated, so the picture beside it is the last valid one and says so
        publishValidation({ yaml: validated, ok: false });
        return;
      }
      setResult({
        errors: data.errors,
        unvalidated: data.unvalidated,
        validatedAt: new Date().toISOString(),
      });
      // the hand-off to the diagram column: `unvalidated` paths are not errors (NFR-2), so
      // a file with an ungated step is still text a graph can be drawn from
      publishValidation({ yaml: validated, ok: data.errors.length === 0 });
    } catch {
      if (seq === requestSeqRef.current) {
        setResult(genericFailureResult());
        publishValidation({ yaml: validated, ok: false });
      }
    } finally {
      if (seq === requestSeqRef.current) setValidating(false);
    }
  }

  async function save(): Promise<void> {
    const seq = ++requestSeqRef.current;
    // a debounced Validate still queued from an earlier keystroke must never fire after Save
    // has already set its own outcome (Review Triage Log, story 3.5, finding 9)
    clearTimeout(timerRef.current);
    setSaving(true);
    try {
      const rewritten = rewriteVersionLine(textRef.current, version + 1);
      const { data, error } = await api.POST('/templates/{name}/versions', {
        params: { path: { name } },
        body: { yaml: rewritten },
      });
      if (seq !== requestSeqRef.current) return; // superseded by a newer Validate or Save
      if (error) {
        setResult({
          errors: errorsFromProblem(error),
          unvalidated: [],
          validatedAt: new Date().toISOString(),
        });
        return;
      }
      if (!data) {
        setResult(genericFailureResult());
        return;
      }
      window.location.assign(`/templates/${encodeURIComponent(name)}/${data.version}`);
    } catch {
      if (seq === requestSeqRef.current) setResult(genericFailureResult());
    } finally {
      if (seq === requestSeqRef.current) setSaving(false);
    }
  }

  useEffect(() => {
    if (!mountRef.current) return undefined;

    const view = new EditorView({
      doc: yaml,
      parent: mountRef.current,
      extensions: buildYamlExtensions({
        onChange: (value) => {
          textRef.current = value;
          clearTimeout(timerRef.current);
          timerRef.current = setTimeout(() => void validate(), DEBOUNCE_MS);
        },
      }),
    });

    return () => {
      clearTimeout(timerRef.current);
      view.destroy();
    };
    // mounts exactly once: the island is recreated wholesale by a full page navigation
    // whenever `name`/`version`/`yaml` change, so there is never a live prop change to react to
  }, []);

  const rows = errorRows(result);
  const hasErrors = result.errors.length > 0;
  const readoutText = hasErrors
    ? `${result.errors.length} errors`
    : `valid · ${readoutTime(result.validatedAt)}`;
  const busy = saving || validating;

  return (
    <div className="template-editor">
      {/* the brief's own ASSUMPTION: the editor shows the stored YAML unchanged (never
          rewritten in place — see `save()` above) while this line states what Save will
          actually post, verbatim (NFR-8) */}
      <p className="template-editor-banner">editing as v{version + 1}</p>

      <div className="template-editor-toolbar">
        <span
          className="template-editor-readout"
          data-testid="templates-readout"
          data-signal={hasErrors ? 'failed' : undefined}
        >
          {readoutText}
        </span>
        <div className="template-editor-actions">
          <button
            type="button"
            className="template-editor-button"
            data-testid="templates-validate"
            disabled={busy}
            onClick={() => void validate()}
          >
            Validate
          </button>
          <button
            type="button"
            className="template-editor-button"
            data-variant="primary"
            data-testid="templates-save"
            disabled={busy}
            onClick={() => void save()}
          >
            Save as v{version + 1}
          </button>
        </div>
      </div>

      <div className="template-editor-mount" data-testid="templates-editor" ref={mountRef} />

      <div className="template-editor-errors" data-testid="templates-errors">
        {rows.map((text, index) => (
          <p
            key={index}
            className="template-editor-error-row"
            data-testid={`templates-error-${index}`}
          >
            {text}
          </p>
        ))}
      </div>
    </div>
  );
}
