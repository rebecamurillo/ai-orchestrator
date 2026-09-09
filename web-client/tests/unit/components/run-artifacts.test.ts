/**
 * The ARTIFACTS column's own components (6.3, FR-19, FR-23, UX-DR9): `ArtifactsTree`,
 * `FileViewer` and `FileEditor` are prop-driven, so their rendered markup is asserted
 * outright with `renderToStaticMarkup` (`vitest.config.ts` runs in `environment: 'node'`,
 * no DOM-mounting library — `run-detail-island.test.ts`'s own note). `ArtifactsPanel.tsx`
 * mounts real fetch effects the way `RunDetail.tsx` itself does, so that island's own test
 * is narrower: it proves the module resolves and exports the component `RunDetail.tsx`
 * mounts, satisfying `check-test-pairs.mjs` (AD-18) with a real import. The rest of its own
 * wiring — the tree load, selecting a file, Save, the tree's own mtime refresh — is
 * `tests/e2e/run-detail-artifacts.spec.ts`'s job, in a real browser.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import ArtifactsPanel from '../../../src/components/run/ArtifactsPanel';
import ArtifactsTree from '../../../src/components/run/ArtifactsTree';
import FileEditor from '../../../src/components/run/FileEditor';
import FileViewer from '../../../src/components/run/FileViewer';
import type { RunFileEntryOut } from '../../../src/lib/run/artifacts';

const FOLDER = 'specs/gates';

const ENTRIES: RunFileEntryOut[] = [
  { path: `${FOLDER}/SPEC.md`, kind: 'file', size: 12, mtime: 0 },
  { path: `${FOLDER}/stories`, kind: 'dir', size: 0, mtime: 0 },
  { path: `${FOLDER}/stories/2-x.md`, kind: 'file', size: 8, mtime: 0 },
];

describe('ArtifactsTree', () => {
  function render(selectedPath: string | null = null): string {
    return renderToStaticMarkup(
      createElement(ArtifactsTree, {
        entries: ENTRIES,
        root: FOLDER,
        selectedPath,
        onSelect: () => {},
      }),
    );
  }

  it('carries the artifacts-tree testid on the root', () => {
    expect(render()).toContain('data-testid="artifacts-tree"');
  });

  it('carries an artifacts-file-<path> testid per row, file and directory alike', () => {
    const markup = render();
    for (const entry of ENTRIES) {
      expect(markup).toContain(`data-testid="artifacts-file-${entry.path}"`);
    }
  });

  it('indents a deeper row further than its own ancestor directory', () => {
    const markup = render();
    expect(markup).toContain('data-depth="0"');
    expect(markup).toContain('data-depth="1"');
  });

  it('marks the selected file row current', () => {
    const markup = render(`${FOLDER}/SPEC.md`);
    const tag = /<button[^>]*data-testid="artifacts-file-specs\/gates\/SPEC\.md"[^>]*>/.exec(
      markup,
    )?.[0];
    expect(tag).toContain('aria-current="true"');
  });

  it('does not mark an unselected file row current', () => {
    const markup = render(null);
    const tag = /<button[^>]*data-testid="artifacts-file-specs\/gates\/SPEC\.md"[^>]*>/.exec(
      markup,
    )?.[0];
    expect(tag).toContain('aria-current="false"');
  });

  it('a directory row is not a button — nothing to click through to', () => {
    const markup = render();
    const dirIndex = markup.indexOf(`data-testid="artifacts-file-${FOLDER}/stories"`);
    const nearby = markup.slice(Math.max(0, dirIndex - 80), dirIndex);
    expect(nearby).not.toContain('<button');
  });
});

describe('FileViewer', () => {
  function render(overrides: Partial<Parameters<typeof FileViewer>[0]> = {}): string {
    return renderToStaticMarkup(
      createElement(FileViewer, {
        path: `${FOLDER}/SPEC.md`,
        content: '# Gates spec\n\nsome text\n',
        readOnlyLine: null,
        canEdit: true,
        editing: false,
        onEditToggle: () => {},
        ...overrides,
      }),
    );
  }

  it('renders Markdown content through the block renderer for a .md path', () => {
    expect(render()).toContain('<h1>Gates spec</h1>');
  });

  it('prints a non-Markdown path as plain text', () => {
    const markup = render({ path: `${FOLDER}/stories.yaml`, content: 'stories: []\n' });
    expect(markup).toContain('<pre>stories: []');
  });

  it('shows the Edit control when it can edit and is not already editing', () => {
    expect(render()).toContain('data-testid="wf-artifacts-edit"');
  });

  it('shows the read-only line instead of the Edit control for a list file', () => {
    const markup = render({
      canEdit: false,
      readOnlyLine: 'planned at abc1234 — start a new run to change the list',
    });
    expect(markup).toContain('data-testid="artifacts-readonly"');
    expect(markup).toContain('planned at abc1234 — start a new run to change the list');
    expect(markup).not.toContain('data-testid="wf-artifacts-edit"');
  });

  it('shows neither control while already editing', () => {
    const markup = render({ editing: true });
    expect(markup).not.toContain('data-testid="wf-artifacts-edit"');
    expect(markup).not.toContain('data-testid="artifacts-readonly"');
  });
});

describe('FileEditor', () => {
  function render(overrides: Partial<Parameters<typeof FileEditor>[0]> = {}): string {
    return renderToStaticMarkup(
      createElement(FileEditor, {
        path: `${FOLDER}/SPEC.md`,
        initialContent: '# Gates spec\n',
        branch: 'epics/gates',
        saving: false,
        error: null,
        onSave: () => {},
        onCancel: () => {},
        ...overrides,
      }),
    );
  }

  it('carries the wf-editor, wf-editor-save and wf-editor-hint testids', () => {
    const markup = render();
    expect(markup).toContain('data-testid="wf-editor"');
    expect(markup).toContain('data-testid="wf-editor-save"');
    expect(markup).toContain('data-testid="wf-editor-hint"');
  });

  it('the hint names the exact commit message and the branch', () => {
    expect(render()).toContain(
      'saved as commit &quot;spec: operator edit (orchestrator)&quot; on epics/gates',
    );
  });

  it('the textarea opens holding the file’s own current text', () => {
    expect(render()).toContain('# Gates spec');
  });

  it('the Save control disables while a save is in flight', () => {
    const markup = render({ saving: true });
    const save = markup.slice(markup.indexOf('data-testid="wf-editor-save"') - 40);
    expect(save.slice(0, 120)).toContain('disabled=""');
  });

  it('shows the error text when a save was refused', () => {
    const markup = render({
      error: { type: 'about:blank', title: 'conflict', status: 409, detail: 'planned at abc' },
    });
    expect(markup).toContain('planned at abc');
  });
});

describe('the ArtifactsPanel island fragment', () => {
  it('is exported as the function component RunDetail.tsx mounts', () => {
    expect(typeof ArtifactsPanel).toBe('function');
  });

  it('renders the ARTIFACTS heading before its own fetch effect has run', () => {
    const markup = renderToStaticMarkup(
      createElement(ArtifactsPanel, {
        runId: 'r1',
        run: {
          id: 'r1',
          status: 'needs_you',
          admitted_signals: [],
          branch: 'epics/gates',
          budget_usd: '15',
          compare_urls: [],
          created_at: '2026-09-09T09:00:00Z',
          inputs: {},
          manual_estimate_h: null,
          plan_ref: 'abc1234',
          project: 'p1',
          repository: 'r1',
          spend_usd: '0',
          template: 'epic',
          terminal_session: false,
          version: 1,
          worktree_path: '/work/acme/widgets/wt/gates',
          worktrees: [],
          accepted_paths: [],
        },
        folder: FOLDER,
      }),
    );

    expect(markup).toContain('data-testid="wf-artifacts"');
    expect(markup).toContain('ARTIFACTS');
  });
});
