/**
 * `ArtifactsTree` with changed-marks (story 8-3): the chip renders for a changed file, is
 * absent for an unchanged file, and is absent for a directory even when `changed=true` (the
 * Python side never marks directories, but the component's own guard is also asserted here).
 *
 * Uses `renderToStaticMarkup` + `createElement` — the same pattern `run-artifacts.test.ts`
 * uses for the same component — because `vitest.config.ts` runs in `environment: 'node'`
 * with no DOM-mounting library. The `.tsx` extension is the spec name; JSX is not required
 * to use `createElement`, but having the extension keeps the test file in step with the
 * component's own file type.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import ArtifactsTree from '../../src/components/run/ArtifactsTree';
import type { RunFileEntryChangedOut } from '../../src/lib/run/artifacts';

const FOLDER = 'specs/gates';
const FILE_PATH = `${FOLDER}/SPEC.md`;
const DIR_PATH = `${FOLDER}/stories`;

function entry(overrides: Partial<RunFileEntryChangedOut> = {}): RunFileEntryChangedOut {
  return {
    path: FILE_PATH,
    kind: 'file',
    size: 10,
    mtime: 1_000_000,
    changed: false,
    ...overrides,
  };
}

function render(entries: RunFileEntryChangedOut[]): string {
  return renderToStaticMarkup(
    createElement(ArtifactsTree, {
      entries,
      root: FOLDER,
      selectedPath: null,
      onSelect: () => {},
    }),
  );
}

describe('ArtifactsTree changed marks (story 8-3)', () => {
  it('renders the accent chip when a file entry has changed=true', () => {
    const markup = render([entry({ changed: true })]);

    expect(markup).toContain('wf-artifacts-chip');
  });

  it('sets data-changed="true" on the file button when changed=true', () => {
    const markup = render([entry({ changed: true })]);

    expect(markup).toContain('data-changed="true"');
  });

  it('does not render the chip when a file entry has changed=false', () => {
    const markup = render([entry({ changed: false })]);

    expect(markup).not.toContain('wf-artifacts-chip');
  });

  it('does not set data-changed on the file button when changed=false', () => {
    const markup = render([entry({ changed: false })]);

    expect(markup).not.toContain('data-changed');
  });

  it('does not render the chip for a directory entry even if changed=true', () => {
    // The Python side never marks directories, but the component's own conditional
    // (`entry.kind === 'dir'` branch never renders a button with the chip) is the
    // additional guard this test asserts.
    const dirEntry: RunFileEntryChangedOut = {
      path: DIR_PATH,
      kind: 'dir',
      size: 0,
      mtime: 1_000_000,
      changed: true,
    };
    const markup = render([dirEntry]);

    expect(markup).not.toContain('wf-artifacts-chip');
  });

  it('does not set data-changed on a directory row', () => {
    const dirEntry: RunFileEntryChangedOut = {
      path: DIR_PATH,
      kind: 'dir',
      size: 0,
      mtime: 1_000_000,
      changed: true,
    };
    const markup = render([dirEntry]);

    expect(markup).not.toContain('data-changed');
  });

  it('renders the chip only on the changed file, not the unchanged one', () => {
    const entries: RunFileEntryChangedOut[] = [
      entry({ path: `${FOLDER}/changed.md`, changed: true }),
      entry({ path: `${FOLDER}/unchanged.md`, changed: false }),
    ];
    const markup = render(entries);

    // Only one chip in the whole tree
    const chipCount = (markup.match(/wf-artifacts-chip/g) ?? []).length;
    expect(chipCount).toBe(1);
  });
});
