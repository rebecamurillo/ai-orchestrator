/** Story 10.3: `NewInitiativeForm` markup — hints, refusals, actions. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import NewInitiativeForm, {
  type FormState,
} from '../../src/components/initiatives/NewInitiativeForm';
import type { components } from '../../src/api/schema';
import type { PackageOut } from '../../src/lib/initiatives/new';

type Row = components['schemas']['InitiativeRowOut'];

const pkg = {
  installed_at: '2026-11-20T10:00:00Z',
  name: 'orch',
  repository: { default_branch: 'main', id: 'r', initiative_folder: 'initiatives', slug: 'hub' },
  sequence: [
    {
      shown_as: 'workflow',
      steps: [
        { file: null, id: 'a', kind: 'conversation', persona: 'analyst', skill: null, writes: [] },
      ],
      template: 't',
      type: 'interactive',
      version: 1,
      workflow: 'spec',
    },
  ],
} as unknown as PackageOut;

const projects = [
  { id: 'p1', name: 'Alpha' },
  { id: 'p2', name: 'Beta' },
];

const base: FormState = {
  projectId: 'p2',
  name: '',
  message: '',
  refusal: null,
  otherProblem: null,
  submitting: false,
};

const html = (state: Partial<FormState> = {}, p: PackageOut | null = pkg) =>
  renderToStaticMarkup(
    createElement(NewInitiativeForm, {
      state: { ...base, ...state },
      projects,
      pkg: p,
      onChange: () => undefined,
      onCreate: () => undefined,
    }),
  );

describe('NewInitiativeForm', () => {
  it('renders the fields, hints, label and static lines', () => {
    const out = html();
    expect(out).toContain('data-testid="newini-project"');
    expect(out).toContain('data-testid="newini-name"');
    expect(out).toContain('data-testid="newini-message"');
    expect(out).toContain('hub repository hub · base main');
    expect(out).toContain('Sent to the analyst agent as turn 1.');
    expect(out).toContain('Create and start spec');
    expect(out).toContain('href="/initiatives"');
    expect(out).toContain('One workflow runs at a time; the next starts when this one is done.');
    expect(out).not.toContain('slug ');
  });

  it('selects the chosen project', () => {
    expect(html()).toMatch(/<option value="p2" selected/);
  });

  it('shows the live line for a non-blank name', () => {
    expect(html({ name: 'Familio Dessin v2' })).toContain(
      'slug familio-dessin-v2 · folder initiatives/familio-dessin-v2 · spec branch spec/familio-dessin-v2',
    );
  });

  it('disables create until name and message are filled', () => {
    expect(html()).toMatch(/data-testid="newini-create"[^>]*disabled/);
    expect(html({ name: 'n', message: 'm' })).not.toMatch(
      /data-testid="newini-create"[^>]*disabled/,
    );
    expect(html({ name: 'n', message: ' ' })).toMatch(/data-testid="newini-create"[^>]*disabled/);
  });

  it('without a package reads the bare label, disabled', () => {
    const out = html({ name: 'n', message: 'm' }, null);
    expect(out).toContain('Create and start<');
    expect(out).toMatch(/data-testid="newini-create"[^>]*disabled/);
    expect(out).not.toContain('Sent to the');
  });

  it('renders the holder refusal under the name, amber, create disabled', () => {
    const holder = { id: 'abc', slug: 'x', status: 'running', step: 'ux' } as Row;
    const out = html({ name: 'x', message: 'm', refusal: { holder } });
    expect(out).toContain('data-testid="newini-slug-taken"');
    expect(out).toContain('data-signal="needs-you"');
    expect(out).toContain('href="/initiatives/abc"');
    expect(out).toContain('slug x is used by an open initiative: ');
    expect(out).toMatch(/data-testid="newini-create"[^>]*disabled/);
  });

  it('renders a problem refusal under the name, amber', () => {
    const out = html({
      name: 'x',
      message: 'm',
      refusal: { title: 'Conflict', detail: 'slug x waits for its branch cleanup' },
    });
    expect(out).toContain('Conflict');
    expect(out).toContain('slug x waits for its branch cleanup');
    expect(out).toContain('data-signal="needs-you"');
    expect(out).not.toContain('newini-slug-taken');
    expect(out).toMatch(/data-testid="newini-create"[^>]*disabled/);
  });

  it('renders the other problem under the actions with create enabled', () => {
    const out = html({
      name: 'x',
      message: 'm',
      otherProblem: { title: 'Unprocessable', detail: 'name too long' },
    });
    expect(out).toContain('Unprocessable');
    expect(out).toContain('name too long');
    expect(out).not.toMatch(/data-testid="newini-create"[^>]*disabled/);
    expect(out.indexOf('Unprocessable')).toBeGreaterThan(out.indexOf('newini-create'));
  });

  it('renders a problem with no detail by its title alone', () => {
    const out = html({ otherProblem: { title: 'Boom', detail: null } });
    expect(out).toContain('Boom');
  });
});
