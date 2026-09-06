/**
 * CodeMirror 6 wiring for the Template YAML editor (3.5): line numbers, the instrument-dark
 * palette (keys in `text-secondary`, `uses:`/`run:` values in `accent`), and the "cursor
 * inside a step" highlight (`surface-raised`). `rewriteVersionLine`, `findStepRange`,
 * `keyRanges` and `accentRanges` are pure text functions with no DOM dependency, unit-tested
 * directly; `buildYamlExtensions` wires them into the `Extension[]` `TemplateEditor.tsx`
 * mounts. Whether a decoration actually paints a pixel is a real browser's job
 * (`tests/e2e/templates.spec.ts`) — this file's own test proves the pure functions and that
 * the extension list is well-formed, nothing about rendered CSS.
 *
 * No YAML parsing happens here (`web-client/AGENTS.md`): every helper below is a line-and-
 * column scan of the text CodeMirror already holds, never a semantic document built from it.
 * Validation stays exactly one place — `POST /templates/{name}/validate`, called by the
 * island, never by this module.
 */
import { EditorState, RangeSetBuilder, StateField, type Extension } from '@codemirror/state';
import { Decoration, EditorView, lineNumbers, type DecorationSet } from '@codemirror/view';
import { yaml } from '@codemirror/lang-yaml';

export interface Range {
  from: number;
  to: number;
}

/** Only the anchored, column-0 `version:` line — never a nested key a step's `with:` block
 * happens to declare under the same name (Save rewrite, story Design Notes). */
const VERSION_LINE = /^version:\s*\d+.*$/m;

export function rewriteVersionLine(yamlText: string, nextVersion: number): string {
  return yamlText.replace(VERSION_LINE, `version: ${nextVersion}`);
}

function leadingSpaces(line: string): number {
  let count = 0;
  while (count < line.length && line[count] === ' ') count++;
  return count;
}

/** A step's own first line, as every shipped Template writes it: `- id: <name>`, at whatever
 * indentation its `steps:` (or a `for_each` block's nested `steps:`) sits at. */
const STEP_START = /^(\s*)-\s+id:\s*\S/;

/**
 * The half-open `[from, to)` character range of the step whose mapping contains `pos` — from
 * its `- id:` line through the last line before indentation returns to that line's own level
 * or shallower. `null` when `pos` sits outside every step (e.g. inside `inputs:`).
 *
 * Nesting resolves to the innermost step: scanning upward from the cursor's line for the
 * nearest `- id:` line, regardless of indentation, finds a nested nested-loop step before it
 * finds the outer one that contains it.
 */
export function findStepRange(text: string, pos: number): Range | null {
  const lines = text.split('\n');
  const starts: number[] = [];
  let offset = 0;
  for (const line of lines) {
    starts.push(offset);
    offset += line.length + 1;
  }

  let cursorLine = 0;
  for (let i = 0; i < starts.length; i++) {
    if (starts[i]! <= pos) cursorLine = i;
    else break;
  }

  let stepLine = -1;
  let indent = 0;
  for (let i = cursorLine; i >= 0; i--) {
    const match = STEP_START.exec(lines[i]!);
    if (match) {
      stepLine = i;
      indent = match[1]!.length;
      break;
    }
  }
  if (stepLine === -1) return null;

  let endLine = lines.length - 1;
  for (let i = stepLine + 1; i < lines.length; i++) {
    const line = lines[i]!;
    if (line.trim().length === 0) continue;
    if (leadingSpaces(line) <= indent) {
      endLine = i - 1;
      break;
    }
  }
  while (endLine > stepLine && lines[endLine]!.trim().length === 0) endLine--;

  const from = starts[stepLine]!;
  const to = endLine + 1 < starts.length ? starts[endLine + 1]! - 1 : text.length;
  return { from, to };
}

/** Any `key:` (or `- key:`) line's key span — the part the "keys in text-secondary" rule
 * colours. Deliberately loose (`[A-Za-z0-9_.]+`) rather than a YAML grammar: the templates
 * this product ships never quote a key, and a decoration that misses an exotic key costs
 * nothing beyond that one key staying the default colour. */
const KEY_LINE = /^(\s*)(-\s+)?([A-Za-z0-9_.]+):/;

export function keyRanges(text: string): Range[] {
  const ranges: Range[] = [];
  const lines = text.split('\n');
  let offset = 0;
  for (const line of lines) {
    const match = KEY_LINE.exec(line);
    if (match) {
      const start = match[1]!.length + (match[2]?.length ?? 0);
      const end = start + match[3]!.length;
      ranges.push({ from: offset + start, to: offset + end });
    }
    offset += line.length + 1;
  }
  return ranges;
}

/** `uses:` and `run:` are the two keys whose *value* names a callee or a shell command — the
 * one thing on the screen coloured for identity rather than for signal (`--color-accent`). */
const ACCENT_KEY = /^(\s*)(uses|run):[ \t]*(\S.*?)[ \t]*$/;

export function accentRanges(text: string): Range[] {
  const ranges: Range[] = [];
  const lines = text.split('\n');
  let offset = 0;
  for (const line of lines) {
    const match = ACCENT_KEY.exec(line);
    if (match) {
      const keyStart = match[1]!.length;
      const colonIndex = line.indexOf(':', keyStart);
      let valueStart = colonIndex + 1;
      while (line[valueStart] === ' ' || line[valueStart] === '\t') valueStart++;
      let valueEnd = line.length;
      while (valueEnd > valueStart && (line[valueEnd - 1] === ' ' || line[valueEnd - 1] === '\t')) {
        valueEnd--;
      }
      if (valueEnd > valueStart) ranges.push({ from: offset + valueStart, to: offset + valueEnd });
    }
    offset += line.length + 1;
  }
  return ranges;
}

const KEY_MARK = Decoration.mark({ class: 'cm-yaml-key' });
const ACCENT_MARK = Decoration.mark({ class: 'cm-yaml-accent' });
const STEP_LINE = Decoration.line({ class: 'cm-yaml-step-active' });

function buildMarkDecorations(text: string): DecorationSet {
  const marks = [
    ...keyRanges(text).map((range) => ({ ...range, deco: KEY_MARK })),
    ...accentRanges(text).map((range) => ({ ...range, deco: ACCENT_MARK })),
  ].sort((a, b) => a.from - b.from || a.to - b.to);

  const builder = new RangeSetBuilder<Decoration>();
  for (const { from, to, deco } of marks) {
    if (to > from) builder.add(from, to, deco);
  }
  return builder.finish();
}

function buildStepDecorations(text: string, pos: number): DecorationSet {
  const range = findStepRange(text, pos);
  if (!range) return Decoration.none;

  const builder = new RangeSetBuilder<Decoration>();
  const lines = text.split('\n');
  let offset = 0;
  for (const line of lines) {
    if (offset > range.to) break;
    if (offset >= range.from) builder.add(offset, offset, STEP_LINE);
    offset += line.length + 1;
  }
  return builder.finish();
}

/** Recomputed only on a document change — key and accent spans depend on the text alone.
 * Exported (not just used internally) so the unit test can inspect it without a DOM, and so
 * a later story can read the same field rather than re-deriving it. */
export const yamlKeyField = StateField.define<DecorationSet>({
  create: (state) => buildMarkDecorations(state.doc.toString()),
  update: (value, tr) => (tr.docChanged ? buildMarkDecorations(tr.state.doc.toString()) : value),
  provide: (field) => EditorView.decorations.from(field),
});

/** Recomputed on a document change or a cursor move — "the step under the cursor" depends on
 * both. Exported for the same reason as `yamlKeyField` above. */
export const yamlStepHighlightField = StateField.define<DecorationSet>({
  create: (state) => buildStepDecorations(state.doc.toString(), state.selection.main.head),
  update: (value, tr) => {
    if (tr.docChanged || !tr.startState.selection.eq(tr.state.selection)) {
      return buildStepDecorations(tr.state.doc.toString(), tr.state.selection.main.head);
    }
    return value;
  },
  provide: (field) => EditorView.decorations.from(field),
});

/** The instrument-dark palette (DESIGN.md): the editor's own ground and gutter, plus the
 * three decoration classes the two `StateField`s above apply. Every colour is a CSS custom
 * property, resolved by the browser exactly as `src/styles/*.css` resolves one, so this
 * module carries no literal hex despite not being a stylesheet `stylesheets.test.ts` scans. */
const theme = EditorView.theme({
  '&': {
    color: 'var(--color-text)',
    backgroundColor: 'var(--color-surface)',
    fontFamily: 'var(--font-mono)',
    fontSize: 'var(--type-command)',
  },
  '.cm-content': { caretColor: 'var(--color-accent)' },
  '.cm-scroller': { fontFamily: 'var(--font-mono)' },
  '.cm-gutters': {
    backgroundColor: 'var(--color-surface-rail)',
    color: 'var(--color-text-tertiary)',
    border: 'none',
  },
  '.cm-yaml-key': { color: 'var(--color-text-secondary)' },
  '.cm-yaml-accent': { color: 'var(--color-accent)' },
  '.cm-yaml-step-active': { backgroundColor: 'var(--color-surface-raised)' },
});

export interface YamlEditorOptions {
  /** Called on every document change, with the editor's full current text. */
  onChange: (value: string) => void;
}

/** No soft wrap (story Binding rules): the editor states the file's own line breaks, and a
 * wrapped line would make "line {n}" in the error list point at the wrong row on screen. */
export function buildYamlExtensions({ onChange }: YamlEditorOptions): Extension[] {
  return [
    lineNumbers(),
    yaml(),
    yamlKeyField,
    yamlStepHighlightField,
    theme,
    EditorView.updateListener.of((update) => {
      if (update.docChanged) onChange(update.state.doc.toString());
    }),
  ];
}

/** Exported for the unit test only: building an `EditorState` (no DOM) is how the two
 * `StateField`s above are exercised without mounting a real `EditorView`. */
export function createYamlEditorState(
  doc: string,
  onChange: YamlEditorOptions['onChange'],
): EditorState {
  return EditorState.create({ doc, extensions: buildYamlExtensions({ onChange }) });
}
