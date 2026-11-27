/** Story 10.3: `PackageSequence` renders the package lines and the workflow sequence. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import PackageSequence from '../../src/components/initiatives/PackageSequence';
import type { components } from '../../src/api/schema';
import type { PackageOut } from '../../src/lib/initiatives/new';

type Entry = components['schemas']['SequenceEntryOut'];
type Project = components['schemas']['ProjectRead'];

const st = (
  id: string,
  kind: 'conversation' | 'automatic',
  persona: string,
  writes: string[] = [],
) => ({ file: null, id, kind, persona, skill: null, writes });

const sequence: Entry[] = [
  {
    shown_as: 'workflow',
    steps: [
      st('a', 'conversation', 'p1', ['A.md']),
      st('b', 'conversation', 'p2', ['B.md', 'C.md']),
      st('c', 'conversation', 'p3', ['D.md']),
      st('d', 'conversation', 'p4', ['E.md']),
      st('e', 'automatic', 'p5'),
      st('f', 'conversation', 'p6', ['F.md']),
    ],
    template: 'initiative-hub',
    type: 'interactive',
    version: 3,
    workflow: 'spec',
  },
  {
    shown_as: 'step',
    steps: [st('m', 'automatic', 'merger')],
    template: 'initiative-hub-merge',
    type: 'auto',
    version: 1,
    workflow: 'merge',
  },
  {
    shown_as: 'workflow',
    steps: [],
    template: 'staged-initiative-hub',
    type: 'auto',
    version: 4,
    workflow: 'build',
  },
];

const pkg = {
  installed_at: '2026-11-20T10:00:00Z',
  name: 'orch',
  repository: { default_branch: 'main', id: 'r', initiative_folder: 'initiatives', slug: 'hub' },
  sequence,
} as unknown as PackageOut;

const project = (budget: string | null) =>
  ({
    default_autonomy: 'auto',
    default_budget_usd: budget,
    default_model: 'claude-opus-5-5',
  }) as Project;

const html = (budget: string | null) =>
  renderToStaticMarkup(createElement(PackageSequence, { pkg, project: project(budget) }));

describe('PackageSequence', () => {
  it('renders the package lines and the section head', () => {
    const out = html('60');
    expect(out).toContain('PACKAGE');
    expect(out).toContain('package orch · installed 2026-11-20 · 2 workflows');
    expect(out).toContain('initiative folder initiatives (repository setting)');
    expect(out).toContain('WORKFLOWS · WHAT WILL RUN, ONE AFTER ANOTHER');
  });

  it('renders two bands, seven step rows and the auto defaults line', () => {
    const out = html('60');
    expect(out).toContain('data-testid="newini-sequence"');
    expect(out.match(/data-band="workflow"/g)).toHaveLength(2);
    expect(out).toContain('initiative-hub@3');
    expect(out).toContain('INTERACTIVE');
    expect(out).toContain('staged-initiative-hub@4');
    expect(out).toContain('AUTO');
    for (const n of ['1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7']) expect(out).toContain(n);
    expect(out).toContain('conversation · writes B.md, C.md');
    expect(out).toContain('p5');
    expect(out).toContain('merge');
    expect(out).toContain(
      'starts by itself when spec is done · project defaults: autonomy auto, claude-opus-5-5, budget $60.00',
    );
  });

  it('reads the no-budget line when the project has none', () => {
    expect(html(null)).toContain('no default budget — the build will stop and ask');
  });
});
