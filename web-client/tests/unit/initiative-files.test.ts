// @vitest-environment jsdom
/** Story 11.3 AC1–AC5: `FilesByStep` renders the API's files, states and flags verbatim. */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET, PUT } = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, PUT } }));

import FilesByStep from '../../src/components/initiative/FilesByStep';
import { detail, step, workflow, type Detail } from './initiative-fixtures';

const DESIGN = 'initiatives/familio-dessin-v2/DESIGN.md';

function build(
  over: Record<string, unknown> = {},
  buildOver: Record<string, unknown> = {},
): Detail {
  return detail({
    workflows: [
      workflow('spec', 1, {
        steps: [
          step('ux', {
            files_state: 'open',
            files: [
              {
                path: DESIGN,
                draft: true,
                changed: true,
                run_id: 'r1',
                time: '2026-11-22T21:30:00Z',
              },
            ],
          }),
          step('tech', { files_state: 'to come', files: [] }),
        ],
      }),
      workflow('build', 2, {
        type: 'auto',
        run_id: 'run-b',
        files: [{ path: 'specs/epic-1/stories/1-1-model-list.md', run_id: 'run-b' }],
        ...buildOver,
      }),
    ],
    ...over,
  } as Partial<Detail>);
}

const mount = (d: Detail, selection = { position: 1, stepId: 'ux' as string | null }) =>
  render(createElement(FilesByStep, { detail: d, selection }));

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
  GET.mockResolvedValue({ data: { path: DESIGN, content: '# Design\n', size: 9, mtime: 0 } });
});
afterEach(cleanup);

describe('FilesByStep', () => {
  it('AC1: head, workflow heading, group head, draft row and changed chip', () => {
    mount(build());
    const root = screen.getByTestId('ini-files');
    expect(root.textContent).toContain('FILES BY WORKFLOW AND STEP');
    expect(root.textContent).toContain('initiatives/familio-dessin-v2/');
    expect(root.textContent).toContain('1 · SPEC');
    const group = screen.getByTestId('ini-files-1-ux');
    expect(group.textContent).toContain('UX');
    expect(group.textContent).toContain('open');
    const row = within(group).getByTestId('ini-file');
    expect(row.textContent).toContain('DESIGN.md');
    expect(row.textContent).toContain('21:30 · draft');
    expect(within(row).getByTestId('ini-file-changed')).toBeTruthy();
  });

  it('AC1: a file neither draft nor changed has no draft word and no chip', () => {
    const d = build();
    d.workflows[0].steps[0].files = [
      { path: DESIGN, draft: false, changed: false, run_id: 'r1', time: '2026-11-22T21:30:00Z' },
    ];
    mount(d);
    const row = within(screen.getByTestId('ini-files-1-ux')).getByTestId('ini-file');
    expect(row.textContent).not.toContain('draft');
    expect(within(row).queryByTestId('ini-file-changed')).toBeNull();
  });

  it('AC2: an empty group reads no file yet; state words pass through verbatim', () => {
    mount(build());
    const tech = screen.getByTestId('ini-files-1-tech');
    expect(tech.textContent).toContain('TECH');
    expect(tech.textContent).toContain('to come');
    expect(tech.textContent).toContain('no file yet');
    cleanup();
    for (const word of ['done', 'skipped, forced', 'failed']) {
      const d = build();
      d.workflows[0].steps[1] = step('tech', { files_state: word, files: undefined } as never);
      mount(d);
      const g = screen.getByTestId('ini-files-1-tech');
      expect(g.textContent).toContain(word);
      expect(g.textContent).toContain('no file yet');
      cleanup();
    }
  });

  it('AC3: the auto workflow lists its files and links to the workflow page', () => {
    mount(build());
    const root = screen.getByTestId('ini-files');
    expect(root.textContent).toContain('2 · BUILD');
    expect(root.textContent).toContain('specs/epic-1/stories/1-1-model-list.md');
    const link = screen.getByText('all files per epic and story → workflow page');
    expect(link.getAttribute('href')).toBe('/workflows/run-b');
  });

  it('AC3: no Run reads not started, no link, no row', () => {
    mount(build({}, { run_id: null, files: [] }));
    expect(screen.getByTestId('ini-files').textContent).toContain('not started');
    expect(screen.queryByText('all files per epic and story → workflow page')).toBeNull();
    expect(screen.getAllByTestId('ini-file')).toHaveLength(1);
  });

  it('AC4: only the selected step group is marked', () => {
    mount(build());
    expect(screen.getByTestId('ini-files-1-ux').getAttribute('data-selected')).toBe('true');
    expect(screen.getByTestId('ini-files-1-tech').getAttribute('data-selected')).toBeNull();
    cleanup();
    mount(build(), { position: 2, stepId: null });
    expect(screen.getByTestId('ini-files-1-ux').getAttribute('data-selected')).toBeNull();
    expect(screen.getByTestId('ini-files-1-tech').getAttribute('data-selected')).toBeNull();
  });

  it('AC5: a click opens the modal read-only on the file’s own Run; close removes it', async () => {
    mount(build());
    fireEvent.click(within(screen.getByTestId('ini-files-1-ux')).getByTestId('ini-file'));
    await waitFor(() => expect(screen.getByTestId('wf-artifact-modal')).toBeTruthy());
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/files', {
      params: { path: { run_id: 'r1' }, query: { path: DESIGN } },
    });
    await waitFor(() =>
      expect(screen.getByTestId('wf-file-viewer').textContent).toContain('Design'),
    );
    expect(screen.queryByTestId('wf-artifacts-edit')).toBeNull();
    expect(PUT).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(/close/i));
    expect(screen.queryByTestId('wf-artifact-modal')).toBeNull();
  });

  it('AC5: a file without a Run id is text, not a button', () => {
    const d = build();
    d.workflows[0].steps[0].files = [
      { path: DESIGN, draft: false, changed: false, run_id: null, time: null },
    ];
    mount(d);
    const ux = screen.getByTestId('ini-files-1-ux');
    expect(within(ux).queryByTestId('ini-file')).toBeNull();
    expect(ux.textContent).toContain('DESIGN.md');
    expect(within(ux).queryByRole('button')).toBeNull();
  });
});
