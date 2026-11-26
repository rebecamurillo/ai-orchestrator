// @vitest-environment jsdom
/** Story 10.1: the Initiatives island against a mocked `src/api/client.ts`. */
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { components } from '../../src/api/schema';

type ListOut = components['schemas']['InitiativeListOut'];
type Row = components['schemas']['InitiativeRowOut'];

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import Initiatives from '../../src/islands/Initiatives';
import { stopPolling } from '../../src/stores/poll';

const row = (slug: string, status: Row['status'], workflow = 'spec'): Row => ({
  attention: null,
  id: slug,
  line: `line ${slug}`,
  name: slug,
  position: 0,
  progress: 'p',
  project_id: 'p',
  project_name: 'Proj',
  reason: '',
  repo_tag: [],
  repository_id: 'r',
  slug,
  status,
  step: 's',
  updated_at: new Date().toISOString(),
  workflow,
  workflow_count: 3,
  workflows: [{ workflow, type: 'auto', state: 'ongoing' }],
});

const list = (items: Row[], counts: Partial<ListOut['counts']> = {}): ListOut => ({
  columns: [
    { workflow: 'spec', type: 'interactive' },
    { workflow: 'build', type: 'auto' },
    { workflow: 'deploy', type: 'auto' },
  ],
  counts: { ongoing: items.length, need_you: 0, cancelled: 0, oldest_wait_at: null, ...counts },
  items,
  next_cursor: null,
});
const ok = (data: ListOut) => ({ data, response: { status: 200 } });
const mount = (filter: 'ongoing' | 'needs_you' | 'all' = 'ongoing') =>
  render(createElement(Initiatives, { initialProjectId: null, initialFilter: filter }));

beforeEach(() => {
  GET.mockReset();
  window.history.replaceState(null, '', '/initiatives');
});
afterEach(() => {
  stopPolling();
  cleanup();
  document.body.innerHTML = '';
});

describe('Initiatives island', () => {
  it('AC3: one column per response column, then DONE', async () => {
    GET.mockResolvedValue(ok(list([row('a', 'waiting for her', 'spec')])));
    mount();
    await screen.findByTestId('initiatives-board');
    const ids = Array.from(document.querySelectorAll('[data-testid^="initiatives-col-"]')).map(
      (e) => e.getAttribute('data-testid'),
    );
    expect(ids).toEqual([
      'initiatives-col-spec',
      'initiatives-col-build',
      'initiatives-col-deploy',
      'initiatives-col-done',
    ]);
    expect(screen.getByTestId('initiatives-col-deploy').textContent).toContain('—');
    expect(screen.getByTestId('initiatives-col-done').textContent).toContain('DONE · LAST 30 DAYS');
    expect(screen.getByTestId('initiatives-col-spec').textContent).toContain('INTERACTIVE');
    expect(screen.getByTestId('initiatives-card-a')).toBeTruthy();
  });

  it('AC6: cancelled items are hidden until show', async () => {
    GET.mockResolvedValue(
      ok(list([row('x', 'cancelled'), row('y', 'cancelled'), row('d', 'done')], { cancelled: 2 })),
    );
    mount('all');
    const done = await screen.findByTestId('initiatives-col-done');
    expect(done.textContent).toContain('2 cancelled, hidden · show');
    expect(screen.queryByTestId('initiatives-card-x')).toBeNull();
    expect(screen.getByTestId('initiatives-card-d')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /cancelled, hidden/ }));
    expect(screen.getByTestId('initiatives-card-x')).toBeTruthy();
    expect(screen.getByTestId('initiatives-card-y')).toBeTruthy();
  });

  it('AC7: a segment refetches with its filter and writes the query', async () => {
    GET.mockResolvedValue(ok(list([row('a', 'running')])));
    mount();
    await screen.findByTestId('initiatives-board');
    fireEvent.click(screen.getByRole('button', { name: 'NEEDS YOU' }));
    await waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
    expect(GET.mock.calls[1][1].params.query.filter).toBe('needs_you');
    expect(window.location.search).toBe('?filter=needs_you');
    expect(screen.getByRole('button', { name: 'NEEDS YOU' }).getAttribute('aria-current')).toBe(
      'true',
    );
  });

  it('passes project_id when given', async () => {
    GET.mockResolvedValue(ok(list([row('a', 'running')])));
    render(createElement(Initiatives, { initialProjectId: 'pid', initialFilter: 'all' }));
    await screen.findByTestId('initiatives-board');
    expect(GET.mock.calls[0][1].params.query).toEqual({ filter: 'all', project_id: 'pid' });
  });

  it('AC8: empty state', async () => {
    GET.mockResolvedValue(ok(list([])));
    mount();
    const empty = await screen.findByTestId('initiatives-empty');
    expect(empty.textContent).toContain('NO INITIATIVES');
    expect(empty.textContent).toContain(
      'An initiative starts from a project: a name and a first message.',
    );
    expect(empty.querySelector('a')!.getAttribute('href')).toBe('/initiatives/new');
  });

  it('AC9: readout with and without need-you', async () => {
    const wait = new Date(Date.now() - 2 * 3600_000 - 5000).toISOString();
    GET.mockResolvedValueOnce(
      ok(list([row('a', 'waiting for her')], { ongoing: 3, need_you: 1, oldest_wait_at: wait })),
    );
    mount();
    const readout = await screen.findByTestId('initiatives-readout');
    expect(readout.textContent).toBe('3 ongoing · 1 need you · oldest wait 2h 00m');
    cleanup();
    GET.mockResolvedValueOnce(ok(list([row('a', 'running')], { ongoing: 3 })));
    mount();
    expect((await screen.findByTestId('initiatives-readout')).textContent).toBe('3 ongoing');
  });

  it('AC9: an error response renders FailedFetch', async () => {
    GET.mockResolvedValue({ error: {}, response: { status: 500 } });
    mount();
    await waitFor(() => expect(document.body.textContent).toContain('/api/initiatives?filter='));
  });

  it('AC9: a rejected fetch renders FailedFetch', async () => {
    GET.mockRejectedValue(new Error('down'));
    mount();
    await waitFor(() => expect(document.body.textContent).toContain('/api/initiatives?filter='));
  });

  it('patches the rail count and need-you line, then removes the line', async () => {
    document.body.innerHTML =
      '<ul><li><a data-testid="nav-initiatives" data-astro-cid-x="">Initiatives</a></li></ul>';
    GET.mockResolvedValueOnce(
      ok(list([row('a', 'waiting for her')], { ongoing: 4, need_you: 1 })),
    ).mockResolvedValueOnce(ok(list([row('a', 'running')], { ongoing: 4, need_you: 0 })));
    const host = document.createElement('div');
    document.body.appendChild(host);
    render(createElement(Initiatives, { initialProjectId: null, initialFilter: 'ongoing' }), {
      container: host,
    });
    await waitFor(() =>
      expect(document.querySelector('[data-testid="nav-initiatives"] .count')?.textContent).toBe(
        '4',
      ),
    );
    const badge = document.querySelector('[data-testid="nav-initiatives-needs-you"]')!;
    expect(badge.textContent).toBe('1 need you');
    expect(badge.getAttribute('data-astro-cid-x')).toBe('');
    expect(badge.getAttribute('style')).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'ALL' }));
    });
    await waitFor(() =>
      expect(document.querySelector('[data-testid="nav-initiatives-needs-you"]')).toBeNull(),
    );
  });
});

describe('Initiatives island — view segment (story 10.2, 2026-11-22)', () => {
  it('AC5: board by default, LIST switches without refetch, BOARD clears view', async () => {
    GET.mockResolvedValue(ok(list([row('a', 'running')])));
    window.history.replaceState(null, '', '/initiatives?filter=all');
    mount();
    await screen.findByTestId('initiatives-board');
    const seg = screen.getByTestId('initiatives-view');
    const btn = (label: string) =>
      Array.from(seg.querySelectorAll('button')).find((b) => b.textContent === label)!;
    expect(btn('BOARD').getAttribute('aria-current')).toBe('true');
    const calls = GET.mock.calls.length;
    fireEvent.click(btn('LIST'));
    const table = await screen.findByTestId('initiatives-list');
    expect(table.textContent).toContain('Project');
    expect(window.location.search).toContain('view=list');
    expect(window.location.search).toContain('filter=all');
    expect(GET.mock.calls.length).toBe(calls);
    fireEvent.click(btn('BOARD'));
    await screen.findByTestId('initiatives-board');
    expect(window.location.search).not.toContain('view');
  });

  it('AC5: initialView list renders the table on mount', async () => {
    GET.mockResolvedValue(ok(list([row('a', 'running')])));
    render(
      createElement(Initiatives, {
        initialProjectId: null,
        initialFilter: 'ongoing',
        initialView: 'list',
      }),
    );
    await screen.findByTestId('initiatives-list');
    expect(screen.queryByTestId('initiatives-board')).toBeNull();
  });
});
