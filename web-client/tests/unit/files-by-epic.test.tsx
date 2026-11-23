// @vitest-environment jsdom
/**
 * `FilesByEpic` (epic 2 story 1, EXPERIENCE § 6.1): rows from `GET /runs/{id}/files-by-epic`,
 * the changed-path diff, the modal, the diagram's Files focus and the poll re-read.
 */
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));
vi.mock('../../src/components/run/ArtifactModal', () => ({
  default: (p: { path: string; onClose: () => void }) =>
    createElement('div', { 'data-testid': 'modal' }, [
      p.path,
      createElement('button', { key: 'c', onClick: p.onClose, 'data-testid': 'modal-close' }),
    ]),
}));

import ArtifactsPanel from '../../src/components/run/ArtifactsPanel';
import FilesByEpic from '../../src/components/run/FilesByEpic';
import { EpicCard, StoryCard } from '../../src/components/run/diagram/nodes';
import { buildHierarchy } from '../../src/lib/diagram/run-tree';
import { $filesFocus } from '../../src/stores/files-focus';
import { $poll } from '../../src/stores/poll';
import { twoEpicFiles } from '../fixtures/files-by-epic';
import { twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';

const RUN = { id: 'r1' } as never;
const DIFF = '--- a/x\n+++ b/x\n-old\n+new\n same';

function route(files: unknown = twoEpicFiles(), diff: unknown = { data: { diff: DIFF } }) {
  GET.mockImplementation(async (url: string) => {
    if (url.endsWith('/diff')) return diff;
    return files;
  });
}
const okFiles = (data = twoEpicFiles()) => ({ data, response: { status: 200 } });

const scrollIntoView = vi.fn();

beforeEach(() => {
  Element.prototype.scrollIntoView = scrollIntoView;
  route(okFiles());
});
afterEach(() => {
  cleanup();
  GET.mockReset();
  scrollIntoView.mockReset();
  $filesFocus.set(null);
});

async function mount() {
  render(createElement(FilesByEpic, { runId: 'r1', run: RUN, folder: 'f' }));
  await screen.findByText('epic 1 · models');
}

describe('FilesByEpic', () => {
  it('lists the epic files in order under the epic row', async () => {
    await mount();
    const names = screen
      .getAllByRole('button')
      .map((b) => b.textContent)
      .slice(0, 3);
    expect(names).toEqual(['SPEC.md', 'stories.yaml', 'spec-gate-result.md']);
    expect(screen.getByText('specs/epic-1-models/')).toBeTruthy();
    expect(document.getElementById('files-epic-0')).not.toBeNull();
  });

  it('shows a story row, its file and its changed count; no file yet for story 3', async () => {
    await mount();
    expect(document.getElementById('files-story-0-1')?.textContent).toBe('story 1 · model list');
    expect(screen.getByText('stories/1-model-list.md')).toBeTruthy();
    expect(screen.getByText('changed: 2 files')).toBeTruthy();
    expect(screen.getByText('no file yet')).toBeTruthy();
    expect(screen.getAllByText('no file yet')).toHaveLength(1);
  });

  it('lists the changed paths, then shows the clicked path’s diff with classed lines', async () => {
    await mount();
    expect(screen.queryByText('src/models.py')).toBeNull();
    fireEvent.click(screen.getByText('changed: 2 files'));
    expect(screen.getByText('tests/test_models.py')).toBeTruthy();
    fireEvent.click(screen.getByText('src/models.py'));
    const pre = await waitFor(() => {
      const el = document.querySelector('pre.wf-files-diff');
      expect(el).not.toBeNull();
      return el!;
    });
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/files-by-epic/diff', {
      params: { path: { run_id: 'r1' }, query: { epic: 0, story: '1', path: 'src/models.py' } },
    });
    expect(pre.querySelector('.wf-files-diff-add')?.textContent).toBe('+new\n');
    expect(pre.querySelector('.wf-files-diff-del')?.textContent).toBe('-old\n');
    fireEvent.click(screen.getByText('src/models.py'));
    expect(document.querySelector('pre.wf-files-diff')).toBeNull();
  });

  it('says it could not read the diff when the diff request fails', async () => {
    route(okFiles(), { error: { status: 500 }, response: { status: 500 } });
    await mount();
    fireEvent.click(screen.getByText('changed: 2 files'));
    fireEvent.click(screen.getByText('src/models.py'));
    expect(await screen.findByText('could not read the diff of src/models.py')).toBeTruthy();
  });

  it('opens the modal on a file’s full path and closes it', async () => {
    await mount();
    fireEvent.click(
      screen.getByTestId('artifacts-file-specs/epic-1-models/stories/1-model-list.md'),
    );
    expect(screen.getByTestId('modal').textContent).toContain(
      'specs/epic-1-models/stories/1-model-list.md',
    );
    fireEvent.click(screen.getByTestId('modal-close'));
    expect(screen.queryByTestId('modal')).toBeNull();
  });

  it('keeps the open modal across a poll tick', async () => {
    await mount();
    fireEvent.click(screen.getByTestId('artifacts-file-specs/epic-1-models/SPEC.md'));
    const before = GET.mock.calls.length;
    act(() => $poll.set($poll.get() + 1));
    await waitFor(() => expect(GET.mock.calls.length).toBeGreaterThan(before));
    expect(screen.getByTestId('modal').textContent).toContain('specs/epic-1-models/SPEC.md');
  });

  it('highlights and scrolls to the focused story, then epic; nothing when null', async () => {
    await mount();
    expect(document.querySelector('.wf-files-focus')).toBeNull();
    act(() => $filesFocus.set('epics[0].stories[1]'));
    const rows = document.querySelectorAll('.wf-files-focus');
    expect(rows).toHaveLength(1);
    expect(rows[0]!.id).toBe('files-story-0-2');
    expect(scrollIntoView).toHaveBeenCalled();
    act(() => $filesFocus.set('epics[1]'));
    expect(document.querySelector('.wf-files-focus')!.id).toBe('files-epic-1');
    act(() => $filesFocus.set(null));
    expect(document.querySelector('.wf-files-focus')).toBeNull();
  });

  it('shows the read failure line with no rows, and re-fetches on a poll tick', async () => {
    route({ error: { status: 500 }, response: { status: 500 } });
    render(createElement(FilesByEpic, { runId: 'r1', run: RUN, folder: 'f' }));
    expect(await screen.findByText('could not read /runs/r1/files-by-epic')).toBeTruthy();
    expect(document.querySelector('.wf-files-group')).toBeNull();
    const before = GET.mock.calls.length;
    act(() => $poll.set($poll.get() + 1));
    await waitFor(() => expect(GET.mock.calls.length).toBeGreaterThan(before));
  });

  it('drops a stale response that lands after a newer one', async () => {
    let first!: (v: unknown) => void;
    GET.mockReset();
    GET.mockImplementationOnce(() => new Promise((r) => (first = r)));
    GET.mockImplementationOnce(async () => okFiles());
    render(createElement(FilesByEpic, { runId: 'r1', run: RUN, folder: 'f' }));
    act(() => $poll.set($poll.get() + 1));
    await screen.findByText('epic 1 · models');
    await act(async () => first({ error: { status: 500 }, response: { status: 500 } }));
    expect(screen.queryByTestId('wf-artifacts-error')).toBeNull();
  });
});

describe('ArtifactsPanel', () => {
  it('keeps wf-artifacts and the heading, and never requests the old tree', async () => {
    render(createElement(ArtifactsPanel, { runId: 'r1', run: RUN, folder: 'f' }));
    expect(screen.getByTestId('wf-artifacts').textContent).toContain('FILES · BY EPIC AND STORY');
    await screen.findByText('epic 1 · models');
    expect(GET.mock.calls.map((c) => c[0])).not.toContain('/runs/{run_id}/files');
  });
});

describe('the diagram Files button', () => {
  const built = buildHierarchy(twoEpicGraph(), twoEpicSteps(), new Set(['epics[0]']));
  const find = (id: string) => built.nodes.find((n) => n.id === id)!;

  it('focuses the story, and its row carries the highlight', async () => {
    render(
      createElement(StoryCard, { node: find('epics[0].stories[1]'), onToggle: () => undefined }),
    );
    fireEvent.click(screen.getByTestId('wf-diagram-files-epics.0.stories.1'));
    expect($filesFocus.get()).toBe('epics[0].stories[1]');
    cleanup();
    await mount();
    expect(document.querySelector('.wf-files-focus')!.id).toBe('files-story-0-2');
  });

  it('focuses the epic', () => {
    render(createElement(EpicCard, { node: find('epics[0]'), onToggle: () => undefined }));
    fireEvent.click(screen.getByTestId('wf-diagram-files-epics.0'));
    expect($filesFocus.get()).toBe('epics[0]');
  });
});
