/** Story 10.2: InitiativesTable, byLastChange and workflowCellText. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import InitiativesTable from '../../src/components/initiatives/InitiativesTable';
import {
  byLastChange,
  workflowCellText,
  type InitiativeRow,
} from '../../src/lib/initiatives/format';

const NOW = Date.parse('2026-11-26T12:00:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();

const row = (slug: string, over: Partial<InitiativeRow> = {}): InitiativeRow => ({
  attention: null,
  id: `id-${slug}`,
  line: `line ${slug}`,
  name: `name-${slug}`,
  position: 1,
  progress: 'p',
  project_id: 'p',
  project_name: 'ProjectZed',
  reason: '',
  repo_tag: ['repo-a'],
  repository_id: 'r',
  slug,
  status: 'running',
  step: 's',
  updated_at: ago(60),
  workflow: 'spec',
  workflow_count: 2,
  workflows: [{ workflow: 'spec', type: 'auto', state: 'ongoing' }],
  ...over,
});

const render = (rows: InitiativeRow[], showProject: boolean) =>
  renderToStaticMarkup(createElement(InitiativesTable, { rows, showProject }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe('InitiativesTable (story 10.2)', () => {
  it('AC1: rows sorted by last change, smallest age first', () => {
    const html = render(
      [
        row('old', { updated_at: ago(26 * 3600) }),
        row('new', { updated_at: ago(180) }),
        row('mid', { updated_at: ago(18 * 60) }),
      ],
      true,
    );
    const at = (s: string) => html.indexOf(`initiatives-row-${s}`);
    expect(at('new')).toBeGreaterThan(-1);
    expect(at('new')).toBeLessThan(at('mid'));
    expect(at('mid')).toBeLessThan(at('old'));
    expect(html).toContain('3m');
    expect(html).toContain('18m');
    expect(html).toContain('1d 02h');
  });

  it('AC2: project column only with showProject', () => {
    const without = render([row('a')], false);
    expect(without).not.toContain('Project');
    expect(without).not.toContain('ProjectZed');
    const withP = render([row('a')], true);
    const heads = Array.from(withP.matchAll(/<th>([^<]*)<\/th>/g)).map((m) => m[1]);
    expect(heads).toEqual([
      'Status',
      'Project',
      'Repository',
      'Initiative',
      'Workflow',
      'Current step',
      'Last change',
    ]);
    expect(withP).toContain('ProjectZed');
    expect(withP).toContain('data-testid="initiatives-list"');
  });

  it('AC3: needs-you signals only on a waiting row', () => {
    const html = render(
      [row('w', { status: 'waiting for her', updated_at: ago(49 * 3600) })],
      true,
    );
    expect(html).toContain('BLK');
    expect(html).toContain('<td data-signal="needs-you">line w</td>');
    expect(html).toMatch(/<td class="ini-table-age" data-signal="needs-you">2d 01h<\/td>/);
    const running = render([row('r', { status: 'running', updated_at: ago(49 * 3600) })], true);
    expect(running).not.toContain('needs-you');
  });

  it('AC4: workflow, repository, line and link cells', () => {
    const html = render(
      [row('x', { repo_tag: ['my-agents-brain', 'hub'], line: 'as sent' })],
      true,
    );
    expect(html).toContain('spec · 1 of 2');
    expect(html).toContain('my-agents-brain, hub');
    expect(html).toContain('as sent');
    expect(html).toContain('<a href="/initiatives/id-x">name-x</a>');
  });
});

describe('format helpers (story 10.2)', () => {
  it('byLastChange sorts newest first without mutating', () => {
    const input = [row('a', { updated_at: ago(500) }), row('b', { updated_at: ago(5) })];
    const out = byLastChange(input);
    expect(out.map((r) => r.slug)).toEqual(['b', 'a']);
    expect(input.map((r) => r.slug)).toEqual(['a', 'b']);
  });
  it('workflowCellText joins workflow and position', () => {
    expect(workflowCellText(row('a', { workflow: 'build', position: 2, workflow_count: 3 }))).toBe(
      'build · 2 of 3',
    );
  });
});
