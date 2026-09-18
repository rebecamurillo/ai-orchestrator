/**
 * `ArtifactModal` (1-6, FR-19, UX-DR9): the artifact viewer/editor modal; the second modal
 * in the product after `CancelModal`. Prop-driven, so its rendered markup is asserted with
 * `renderToStaticMarkup` (`vitest.config.ts` runs in `environment: 'node'`, no DOM-mounting
 * library — `run-detail-island.test.ts`'s own note). Fetch effects and CodeMirror mount do
 * not run in SSR; what is verified here is the structure that `canEditFile` and `isListFile`
 * drive before any content is loaded.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import ArtifactModal from '../../src/components/run/ArtifactModal';
import type { SignalKind } from '../../src/lib/run/detail';

const FOLDER = 'specs/gates';

/** A parked run with no terminal session — the condition for Edit to appear. */
const PARKED_RUN = {
  id: 'r1',
  status: 'needs_you' as const,
  admitted_signals: [] as SignalKind[],
  branch: 'epics/gates',
  budget_usd: '15',
  compare_urls: [] as string[],
  created_at: '2026-09-09T09:00:00Z',
  inputs: {} as Record<string, unknown>,
  manual_estimate_h: null as null,
  plan_ref: 'abc1234',
  project: 'p1',
  repository: 'r1',
  spend_usd: '0',
  template: 'epic',
  terminal_session: false,
  version: 1,
  worktree_path: '/work/acme/widgets/wt/gates',
  worktrees: [] as { branch: string; created_branch: boolean; path: string; pushed: boolean }[],
  accepted_paths: [] as string[],
};

type TestRun = Omit<typeof PARKED_RUN, 'status'> & { status: string };

type ArtifactModalRun = Parameters<typeof ArtifactModal>[0]['run'];

function render(path = `${FOLDER}/SPEC.md`, run: TestRun = PARKED_RUN): string {
  return renderToStaticMarkup(
    createElement(ArtifactModal, {
      runId: 'r1',
      path,
      run: run as unknown as ArtifactModalRun,
      folder: FOLDER,
      onClose: () => {},
    }),
  );
}

describe('ArtifactModal', () => {
  it('is exported as a function component', () => {
    expect(typeof ArtifactModal).toBe('function');
  });

  it('renders the wf-artifact-modal panel testid', () => {
    expect(render()).toContain('data-testid="wf-artifact-modal"');
  });

  it('renders the three tab controls', () => {
    const html = render();
    expect(html).toContain('data-testid="wf-artifact-modal-tab-rendered"');
    expect(html).toContain('data-testid="wf-artifact-modal-tab-source"');
    expect(html).toContain('data-testid="wf-artifact-modal-tab-raw"');
  });

  it('shows the Edit button when run is parked, no terminal session, non-list path', () => {
    expect(render()).toContain('data-testid="wf-artifacts-edit"');
  });

  it('does not show the Edit button when run is not parked', () => {
    const html = render(`${FOLDER}/SPEC.md`, { ...PARKED_RUN, status: 'running' as const });
    expect(html).not.toContain('data-testid="wf-artifacts-edit"');
  });

  it('does not show the Edit button when a terminal session is active', () => {
    const html = render(`${FOLDER}/SPEC.md`, { ...PARKED_RUN, terminal_session: true });
    expect(html).not.toContain('data-testid="wf-artifacts-edit"');
  });

  it('does not show the Edit button for stories.yaml', () => {
    expect(render(`${FOLDER}/stories.yaml`)).not.toContain('data-testid="wf-artifacts-edit"');
  });

  it('does not show the Edit button for epics.yaml', () => {
    expect(render(`${FOLDER}/epics.yaml`)).not.toContain('data-testid="wf-artifacts-edit"');
  });

  it('shows the read-only line for stories.yaml with the plan_ref sha', () => {
    const html = render(`${FOLDER}/stories.yaml`);
    expect(html).toContain('planned at abc1234');
    expect(html).toContain('start a new run to change the list');
  });

  it('shows the read-only line for epics.yaml', () => {
    const html = render(`${FOLDER}/epics.yaml`);
    expect(html).toContain('planned at abc1234');
    expect(html).toContain('start a new run to change the list');
  });

  it('does not show the read-only line for a non-list file', () => {
    expect(render()).not.toContain('start a new run to change the list');
  });

  it('carries role="dialog" and aria-modal on the panel', () => {
    const html = render();
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
  });

  it('renders the download button (row 8 partial — click behavior is tests/e2e)', () => {
    expect(render()).toContain('wf-artifact-modal-download');
  });

  it('never congratulates or apologises (NFR-8)', () => {
    const html = render().toLowerCase();
    expect(html).not.toContain('sorry');
    expect(html).not.toContain('congratulations');
  });
});
