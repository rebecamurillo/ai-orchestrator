/** Story 10.3: the pure helpers of `src/lib/initiatives/new.ts`. */
import { describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import {
  NO_PACKAGE_LINE,
  canCreate,
  createLabel,
  firstAgent,
  firstWorkflow,
  folderLine,
  hubHint,
  liveLine,
  messageHint,
  openHolder,
  packageLine,
  sequenceBands,
  slugOf,
  slugTakenParts,
} from '../../src/lib/initiatives/new';

type Pkg = components['schemas']['PackageOut'];
type Project = components['schemas']['ProjectRead'];
type Entry = components['schemas']['SequenceEntryOut'];
type Row = components['schemas']['InitiativeRowOut'];

const step = (
  id: string,
  kind: 'conversation' | 'automatic',
  persona: string | null,
  writes: string[] = [],
) => ({
  file: null,
  id,
  kind,
  persona,
  skill: null,
  writes,
});

export const entries = (): Entry[] => [
  {
    shown_as: 'workflow',
    steps: [
      step('brief', 'conversation', 'analyst', ['PRD.md', 'SPEC.md']),
      step('ux', 'conversation', 'ux', ['DESIGN.md']),
      step('check', 'automatic', 'reviewer'),
    ],
    template: 'initiative-hub',
    type: 'interactive',
    version: 2,
    workflow: 'spec',
  },
  {
    shown_as: 'step',
    steps: [step('merge-step', 'automatic', 'merger')],
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

export const pkg = (sequence: Entry[] = entries()): Pkg =>
  ({
    installed_at: '2026-11-20T10:11:12Z',
    name: 'orchestrator-package',
    repository: { default_branch: 'main', id: 'r', initiative_folder: 'initiatives', slug: 'hub' },
    sequence,
  }) as unknown as Pkg;

const project = (over: Partial<Project> = {}): Project =>
  ({
    default_autonomy: 'auto',
    default_budget_usd: '60',
    default_model: 'claude-opus-5-5',
    ...over,
  }) as Project;

describe('slugOf', () => {
  it('mirrors the backend slugify', () => {
    expect(slugOf('')).toBe('project');
    expect(slugOf('  --  ')).toBe('project');
    expect(slugOf('Familio Dessin v2')).toBe('familio-dessin-v2');
    const fifty = 'abcdefghij'.repeat(5);
    expect(slugOf(fifty)).toBe(fifty.slice(0, 40));
    expect(slugOf(`${'a'.repeat(39)} ${'b'.repeat(10)}`)).toBe('a'.repeat(39));
    expect(slugOf('Été 2026!')).toBe('t-2026');
  });
});

describe('lines and hints', () => {
  it('formats the live line, hub hint, package and folder lines', () => {
    expect(liveLine('x-y', 'initiatives')).toBe(
      'slug x-y · folder initiatives/x-y · spec branch spec/x-y',
    );
    expect(hubHint(pkg())).toBe('hub repository hub · base main');
    expect(packageLine(pkg())).toBe(
      'package orchestrator-package · installed 2026-11-20 · 2 workflows',
    );
    expect(folderLine(pkg())).toBe('initiative folder initiatives (repository setting)');
  });

  it('names the first workflow and its first agent', () => {
    expect(firstWorkflow(pkg())).toBe('spec');
    expect(createLabel(pkg())).toBe('Create and start spec');
    expect(createLabel(null)).toBe('Create and start');
    expect(firstAgent(pkg())).toBe('analyst');
    const noPersona = entries();
    noPersona[0].steps[0].persona = null;
    expect(firstAgent(pkg(noPersona))).toBe('brief');
    expect(firstAgent(pkg([]))).toBe('');
    expect(firstWorkflow(pkg([]))).toBe('');
    expect(messageHint('analyst')).toBe(
      'Sent to the analyst agent as turn 1. The conversation is saved; leave and come back to it from the initiative page.',
    );
    expect(NO_PACKAGE_LINE).toBe(
      "no package installed · install one in the project's Package section",
    );
  });
});

describe('sequenceBands', () => {
  it('numbers steps, the merge row and the auto band', () => {
    const bands = sequenceBands(pkg(), project());
    expect(bands).toHaveLength(2);
    expect(bands[0]).toMatchObject({
      n: 1,
      workflow: 'spec',
      templateRef: 'initiative-hub@2',
      typeWord: 'INTERACTIVE',
      defaultsLine: null,
    });
    expect(bands[0].rows).toEqual([
      { n: '1.1', name: 'brief', kind: 'conversation · writes PRD.md, SPEC.md', agent: 'analyst' },
      { n: '1.2', name: 'ux', kind: 'conversation · writes DESIGN.md', agent: 'ux' },
      { n: '1.3', name: 'check', kind: 'automatic', agent: 'reviewer' },
      { n: '1.4', name: 'merge', kind: 'automatic', agent: 'merger' },
    ]);
    expect(bands[1]).toMatchObject({
      n: 2,
      workflow: 'build',
      templateRef: 'staged-initiative-hub@4',
      typeWord: 'AUTO',
      rows: [],
      defaultsLine:
        'starts by itself when spec is done · project defaults: autonomy auto, claude-opus-5-5, budget $60.00',
    });
  });

  it('handles a null version, a null budget, null defaults, and a first auto band', () => {
    const e = entries();
    e[0].version = null;
    e[0].steps[0].persona = null;
    e[1].steps = [];
    const bands = sequenceBands(pkg(e), project({ default_budget_usd: null }));
    expect(bands[0].templateRef).toBe('initiative-hub');
    expect(bands[0].rows[0].agent).toBe('');
    expect(bands[0].rows[3].agent).toBe('');
    expect(bands[1].defaultsLine).toContain('no default budget — the build will stop and ask');
    const bare = sequenceBands(pkg(e), null);
    expect(bare[1].defaultsLine).toBe(
      'starts by itself when spec is done · no default budget — the build will stop and ask',
    );
    const noDefaults = sequenceBands(
      pkg(e),
      project({ default_autonomy: null, default_model: null }),
    );
    expect(noDefaults[1].defaultsLine).toContain('autonomy —, —, budget $60.00');
    const first = sequenceBands(pkg([e[2]]), project());
    expect(first[0].defaultsLine).toBe(
      'project defaults: autonomy auto, claude-opus-5-5, budget $60.00',
    );
  });
});

const item = (id: string, slug: string, status: Row['status'], stepName = 'ux'): Row =>
  ({ id, slug, status, step: stepName }) as Row;

describe('holder', () => {
  it('skips cancelled items and returns null without an open one', () => {
    const items = [
      item('a', 'x', 'cancelled'),
      item('b', 'x', 'running'),
      item('c', 'y', 'running'),
    ];
    expect(openHolder(items, 'x')?.id).toBe('b');
    expect(openHolder([item('a', 'x', 'cancelled')], 'x')).toBeNull();
    expect(openHolder([], 'x')).toBeNull();
  });

  it('words the slug-taken line', () => {
    expect(slugTakenParts(item('b', 'x', 'running'))).toEqual({
      lead: 'slug x is used by an open initiative: ',
      linkText: 'x',
      href: '/initiatives/b',
      tail: " (ux, running). A cancelled initiative's slug is free.",
    });
    expect(slugTakenParts(item('b', 'x', 'waiting for her')).tail).toContain('(ux, needs you)');
  });
});

describe('canCreate', () => {
  const base = { name: 'n', message: 'm', hasPackage: true, refused: false, submitting: false };
  it('is a truth table', () => {
    expect(canCreate(base)).toBe(true);
    expect(canCreate({ ...base, name: '  ' })).toBe(false);
    expect(canCreate({ ...base, message: ' \n' })).toBe(false);
    expect(canCreate({ ...base, hasPackage: false })).toBe(false);
    expect(canCreate({ ...base, refused: true })).toBe(false);
    expect(canCreate({ ...base, submitting: true })).toBe(false);
  });
});
