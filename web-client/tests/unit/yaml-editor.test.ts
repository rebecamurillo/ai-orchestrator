/**
 * `src/lib/editor/yamlEditor.ts` (3.5): the pure text helpers behind the CodeMirror setup,
 * plus a smoke test of the wiring itself. `EditorState.create` needs no DOM (only
 * `EditorView` mounting does), which is what lets the two `StateField`s be exercised here at
 * all — whether a decoration actually paints is `tests/e2e/templates.spec.ts`'s job, in a
 * real browser.
 */
import { describe, expect, it } from 'vitest';

import {
  accentRanges,
  buildYamlExtensions,
  createYamlEditorState,
  findStepRange,
  keyRanges,
  rewriteVersionLine,
  yamlKeyField,
  yamlStepHighlightField,
} from '../../src/lib/editor/yamlEditor';

const SAMPLE = [
  'name: demo',
  'version: 1',
  'description: two steps',
  'inputs:',
  '  project: { type: project, required: true }',
  'steps:',
  '  - id: checkout',
  '    uses: git.worktree',
  '    with: { base: "{{base_branch}}", branch: "{{branch}}" }',
  '    gate: deterministic',
  '',
  '  - id: build',
  '    run: "{{repository.quality_gate_command}}"',
  '    on_fail: fail',
  '    gate: deterministic',
].join('\n');

const NESTED = [
  'steps:',
  '  - id: stories',
  '    for_each: "{{spec_folder}}/stories.yaml"',
  '    steps:',
  '      - id: story',
  '        uses: template',
  '        with:',
  '          name: story',
  '          version: 1',
].join('\n');

function lineOffset(text: string, lineIndex: number): number {
  return text
    .split('\n')
    .slice(0, lineIndex)
    .reduce((total, line) => total + line.length + 1, 0);
}

describe('rewriteVersionLine', () => {
  it('replaces the anchored top-level version line', () => {
    expect(rewriteVersionLine(SAMPLE, 2)).toContain('\nversion: 2\n');
    expect(rewriteVersionLine(SAMPLE, 2)).not.toContain('version: 1');
  });

  it('never touches a nested version key inside a step', () => {
    const rewritten = rewriteVersionLine(NESTED, 2);

    // the outer text has no top-level `version:` line to rewrite, so the nested one under
    // `with:` (a step calling another Template at a pinned version) must survive untouched
    expect(rewritten).toBe(NESTED);
    expect(rewritten).toContain('          version: 1');
  });
});

describe('findStepRange', () => {
  it('returns the enclosing step, from its `- id:` line to the line before the next one', () => {
    const posInsideUses = lineOffset(SAMPLE, 7) + 6; // inside "uses: git.worktree"
    const range = findStepRange(SAMPLE, posInsideUses)!;

    const text = SAMPLE.slice(range.from, range.to);
    expect(text).toContain('- id: checkout');
    expect(text).toContain('gate: deterministic');
    expect(text).not.toContain('- id: build');
  });

  it('finds the second step when the cursor sits inside it', () => {
    const posInsideRun = lineOffset(SAMPLE, 12) + 6; // inside the `run:` line
    const range = findStepRange(SAMPLE, posInsideRun)!;

    const text = SAMPLE.slice(range.from, range.to);
    expect(text).toContain('- id: build');
    expect(text).not.toContain('- id: checkout');
  });

  it('returns null outside every step', () => {
    const posInInputs = lineOffset(SAMPLE, 4) + 2;

    expect(findStepRange(SAMPLE, posInInputs)).toBeNull();
  });

  it('resolves to the innermost step of a nested for_each', () => {
    const posInsideNestedUses = lineOffset(NESTED, 5) + 8; // inside the nested "uses: template"
    const range = findStepRange(NESTED, posInsideNestedUses)!;

    const text = NESTED.slice(range.from, range.to);
    expect(text).toContain('- id: story');
    expect(text).not.toContain('- id: stories');
  });
});

describe('keyRanges', () => {
  it('spans exactly the key text of a mapping line, dash prefix excluded', () => {
    const ranges = keyRanges(SAMPLE);
    const usesLineStart = lineOffset(SAMPLE, 7);
    const match = ranges.find(
      (range) => range.from >= usesLineStart && range.from < usesLineStart + 20,
    );

    expect(match).toBeDefined();
    expect(SAMPLE.slice(match!.from, match!.to)).toBe('uses');
  });

  it('finds the id key on a step start line, after the dash', () => {
    const ranges = keyRanges(SAMPLE);
    const stepLineStart = lineOffset(SAMPLE, 6);
    const match = ranges.find(
      (range) => range.from >= stepLineStart && range.from < stepLineStart + 20,
    );

    expect(SAMPLE.slice(match!.from, match!.to)).toBe('id');
  });
});

describe('accentRanges', () => {
  it('covers the uses: value only, not the key or surrounding whitespace', () => {
    const ranges = accentRanges(SAMPLE);
    const usesRange = ranges[0]!;

    expect(SAMPLE.slice(usesRange.from, usesRange.to)).toBe('git.worktree');
  });

  it('covers the run: value including its quotes', () => {
    const ranges = accentRanges(SAMPLE);
    const runRange = ranges.find((range) => SAMPLE.slice(range.from, range.to).startsWith('"'))!;

    expect(SAMPLE.slice(runRange.from, runRange.to)).toBe('"{{repository.quality_gate_command}}"');
  });

  it('ignores lines with neither key', () => {
    const ranges = accentRanges('gate: deterministic\non_fail: fail');

    expect(ranges).toEqual([]);
  });
});

describe('buildYamlExtensions and the state it wires', () => {
  it('builds a non-empty extension list', () => {
    const extensions = buildYamlExtensions({ onChange: () => {} });

    expect(Array.isArray(extensions)).toBe(true);
    expect(extensions.length).toBeGreaterThan(0);
  });

  it('creates an EditorState with no DOM, decorating keys, accents, and the active step', () => {
    const state = createYamlEditorState(SAMPLE, () => {});

    expect(state.doc.toString()).toBe(SAMPLE);
    expect(state.field(yamlKeyField).size).toBeGreaterThan(0);
    // no selection was set, so the cursor sits at 0 — outside every step
    expect(state.field(yamlStepHighlightField).size).toBe(0);
  });

  it('recomputes the step highlight when the selection moves inside a step, and the key\n      decorations when the document changes', () => {
    const state = createYamlEditorState(SAMPLE, () => {});
    const posInsideUses = lineOffset(SAMPLE, 7) + 6;

    const withSelection = state.update({ selection: { anchor: posInsideUses } }).state;
    expect(withSelection.field(yamlStepHighlightField).size).toBeGreaterThan(0);

    const withEdit = withSelection.update({ changes: { from: 0, to: 0, insert: 'x: y\n' } }).state;
    expect(withEdit.field(yamlKeyField).size).toBeGreaterThan(0);
  });
});
