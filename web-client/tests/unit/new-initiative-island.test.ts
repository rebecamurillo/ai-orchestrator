// @vitest-environment jsdom
/** Story 10.3: the NewInitiative island against a mocked `src/api/client.ts`. */
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET, POST } = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, POST } }));

import NewInitiative from '../../src/islands/NewInitiative';

const st = (id: string, persona: string) => ({
  file: null,
  id,
  kind: 'conversation',
  persona,
  skill: null,
  writes: ['A.md'],
});
const pkgFor = (marker: string) => ({
  installed_at: '2026-11-20T10:00:00Z',
  name: `pkg-${marker}`,
  repository: { default_branch: 'main', id: 'r', initiative_folder: 'initiatives', slug: 'hub' },
  sequence: [
    {
      shown_as: 'workflow',
      steps: [st('a', 'analyst')],
      template: 't',
      type: 'interactive',
      version: 1,
      workflow: 'spec',
    },
  ],
});
const projectRead = { default_autonomy: 'auto', default_budget_usd: '60', default_model: 'm' };
const projects = [
  { id: 'A', name: 'Alpha' },
  { id: 'B', name: 'Beta' },
];
const problem = (status: number, title: string, detail: string) => ({
  data: undefined,
  error: { status, title, detail },
  response: { status },
});
const item = (id: string, status: string) => ({
  id,
  slug: 'familio-dessin-v2',
  status,
  step: 'ux',
});

let packageAnswer: (id: string) => unknown;
let listAnswer: () => unknown;

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  packageAnswer = (id) => ({ data: pkgFor(id), response: { status: 200 } });
  listAnswer = () => ({ data: { items: [] }, response: { status: 200 } });
  GET.mockImplementation((path: string, opts: { params: { path?: { project_id: string } } }) => {
    if (path === '/projects/{project_id}/package')
      return packageAnswer(opts.params.path!.project_id);
    if (path === '/projects/{project_id}') return { data: projectRead, response: { status: 200 } };
    return listAnswer();
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const mount = (initialProjectId: string | null = 'A') =>
  render(createElement(NewInitiative, { projects, initialProjectId }));
const type = (testId: string, value: string) =>
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
const ready = async () => screen.findByText('package pkg-A', { exact: false });
const fill = async () => {
  await ready();
  type('newini-name', 'Familio Dessin v2');
  type('newini-message', 'hello');
};
const create = () => screen.getByTestId('newini-create') as HTMLButtonElement;

describe('NewInitiative', () => {
  it('selects the initial project and reads its package (AC9)', async () => {
    mount('B');
    await screen.findByText('package pkg-B', { exact: false });
    expect((screen.getByTestId('newini-project') as HTMLSelectElement).value).toBe('B');
    expect(GET).toHaveBeenCalledWith('/projects/{project_id}/package', {
      params: { path: { project_id: 'B' } },
    });
  });

  it('falls back to the first project when none is named', async () => {
    mount(null);
    await screen.findByText('package pkg-A', { exact: false });
  });

  it('renders nothing selectable with no projects', () => {
    render(createElement(NewInitiative, { projects: [], initialProjectId: null }));
    expect(GET).not.toHaveBeenCalled();
    expect(create().disabled).toBe(true);
  });

  it('posts exactly project_id, name, first_message and navigates (AC8)', async () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', { value: { assign }, configurable: true });
    POST.mockResolvedValue({ data: { id: 'new-id' }, response: { status: 201 } });
    mount();
    await fill();
    expect(create().textContent).toBe('Create and start spec');
    fireEvent.click(create());
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/initiatives/new-id'));
    expect(POST).toHaveBeenCalledWith('/initiatives', {
      body: { project_id: 'A', name: 'Familio Dessin v2', first_message: 'hello' },
    });
  });

  it('disables create without a package (AC7) and reads the no-package line', async () => {
    packageAnswer = () => ({ data: undefined, error: { status: 404 }, response: { status: 404 } });
    mount();
    await screen.findByText("no package installed · install one in the project's Package section");
    type('newini-name', 'n');
    type('newini-message', 'm');
    expect(create().disabled).toBe(true);
  });

  it('reads the failed-fetch readout when the package read fails otherwise, and retries', async () => {
    packageAnswer = () => ({ data: undefined, error: { status: 500 }, response: { status: 500 } });
    mount();
    await screen.findByTestId('fetch-failed');
    expect(create().disabled).toBe(true);
    packageAnswer = (id) => ({ data: pkgFor(id), response: { status: 200 } });
    fireEvent.click(screen.getByTestId('fetch-retry'));
    await ready();
  });

  it('reads the failed-fetch readout when the package fetch rejects', async () => {
    packageAnswer = () => Promise.reject(new Error('down'));
    mount();
    await screen.findByTestId('fetch-failed');
  });

  it('renders bands with the no-budget line when the project read fails', async () => {
    GET.mockImplementation((path: string, opts: { params: { path?: { project_id: string } } }) => {
      if (path === '/projects/{project_id}/package')
        return packageAnswer(opts.params.path!.project_id);
      return { data: undefined, error: { status: 500 }, response: { status: 500 } };
    });
    mount();
    await ready();
    expect(screen.getByTestId('newini-sequence')).toBeTruthy();
  });

  it('refetches on project change and ignores a late answer for the previous project (AC7)', async () => {
    let resolveA: (v: unknown) => void = () => undefined;
    packageAnswer = (id) =>
      id === 'A'
        ? new Promise((r) => {
            resolveA = r;
          })
        : { data: pkgFor(id), response: { status: 200 } };
    mount();
    fireEvent.change(screen.getByTestId('newini-project'), { target: { value: 'B' } });
    await screen.findByText('package pkg-B', { exact: false });
    await act(async () => {
      resolveA({ data: pkgFor('A'), response: { status: 200 } });
    });
    expect(screen.queryByText('package pkg-A', { exact: false })).toBeNull();
    expect(screen.getByText('package pkg-B', { exact: false })).toBeTruthy();
    const calls = GET.mock.calls.filter((c) => c[0] === '/projects/{project_id}');
    expect(calls.map((c) => c[1].params.path.project_id)).toEqual(['A', 'B']);
  });

  it('renders the holder on a 409 and clears it when the name changes (AC2)', async () => {
    POST.mockResolvedValue(problem(409, 'Conflict', 'slug taken'));
    listAnswer = () => ({
      data: { items: [item('old', 'cancelled'), item('live', 'running')] },
      response: { status: 200 },
    });
    mount();
    await fill();
    fireEvent.click(create());
    const taken = await screen.findByTestId('newini-slug-taken');
    expect(taken.textContent).toBe(
      "slug familio-dessin-v2 is used by an open initiative: familio-dessin-v2 (ux, running). A cancelled initiative's slug is free.",
    );
    expect(taken.getAttribute('data-signal')).toBe('needs-you');
    expect(taken.querySelector('a')!.getAttribute('href')).toBe('/initiatives/live');
    expect(create().disabled).toBe(true);
    expect(GET).toHaveBeenCalledWith('/initiatives', {
      params: { query: { project_id: 'A', filter: 'all' } },
    });
    type('newini-name', 'Familio Dessin v3');
    expect(screen.queryByTestId('newini-slug-taken')).toBeNull();
    expect(create().disabled).toBe(false);
  });

  it('renders the problem under the name when no open item holds the slug (AC3)', async () => {
    POST.mockResolvedValue(
      problem(409, 'Conflict', 'slug familio-dessin-v2 waits for its branch cleanup: x'),
    );
    listAnswer = () => ({ data: { items: [item('old', 'cancelled')] }, response: { status: 200 } });
    mount();
    await fill();
    fireEvent.click(create());
    await screen.findByText('Conflict');
    expect(screen.getByText(/waits for its branch cleanup/)).toBeTruthy();
    expect(screen.queryByTestId('newini-slug-taken')).toBeNull();
    expect(create().disabled).toBe(true);
    type('newini-name', 'other');
    expect(create().disabled).toBe(false);
  });

  it('falls back to the problem when the list read fails or rejects', async () => {
    POST.mockResolvedValue(problem(409, 'Conflict', 'branch exists'));
    listAnswer = () => ({ data: undefined, error: { status: 500 }, response: { status: 500 } });
    mount();
    await fill();
    fireEvent.click(create());
    await screen.findByText('branch exists');
    type('newini-name', 'x');
    listAnswer = () => {
      throw new Error('down');
    };
    fireEvent.click(create());
    await screen.findByText('branch exists');
  });

  it('renders another problem under the actions and keeps create enabled (AC4)', async () => {
    POST.mockResolvedValue(problem(422, 'Unprocessable', 'name too long'));
    mount();
    await fill();
    fireEvent.click(create());
    await screen.findByText('Unprocessable');
    expect(screen.getByText('name too long')).toBeTruthy();
    expect(create().disabled).toBe(false);
  });

  it('renders the failed-fetch readout when the post rejects (AC4)', async () => {
    POST.mockRejectedValue(new Error('down'));
    mount();
    await fill();
    fireEvent.click(create());
    await screen.findByTestId('fetch-failed');
    expect(create().disabled).toBe(false);
  });
});
