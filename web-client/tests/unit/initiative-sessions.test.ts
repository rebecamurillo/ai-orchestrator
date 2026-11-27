/** Story 11.3 AC7: `SessionsAndRuns` lists every entry the API sends, in its order. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import SessionsAndRuns from '../../src/components/initiative/SessionsAndRuns';

type Entries = Parameters<typeof SessionsAndRuns>[0]['sessions'];

const SESSIONS = [
  {
    workflow: 'spec',
    step: 'tech',
    kind: 'session',
    id: '0193a1b2-0000-7000-8000-0000000011ab',
    round: 1,
    state: 'closed',
  },
  {
    workflow: 'spec',
    step: 'tech',
    kind: 'session',
    id: '0193c3d4-0000-7000-8000-000000007f21',
    round: 2,
    state: 'open',
  },
  {
    workflow: 'build',
    step: null,
    kind: 'run',
    id: '0193e5f6-0000-7000-8000-000000008c02',
    round: 1,
    state: 'running',
  },
] as Entries;

const html = (sessions: Entries) =>
  renderToStaticMarkup(createElement(SessionsAndRuns, { sessions }));

describe('SessionsAndRuns', () => {
  it('renders the head and three rows in order', () => {
    const out = html(SESSIONS);
    expect(out).toContain('data-testid="ini-links"');
    expect(out).toContain('SESSIONS AND RUNS');
    expect(out.match(/data-testid="ini-link"/g)).toHaveLength(3);
    const a = out.indexOf('tech · session 0193…11ab · closed');
    const b = out.indexOf('tech · session 0193…7f21 · open');
    const c = out.indexOf('run 0193…8c02 · running');
    expect(a).toBeGreaterThan(0);
    expect(b).toBeGreaterThan(a);
    expect(c).toBeGreaterThan(b);
    expect(out).toContain('>spec<');
    expect(out).toContain('>build<');
  });

  it('links a Run row to its workflow page and no session row', () => {
    const out = html(SESSIONS);
    expect(out).toContain('href="/workflows/0193e5f6-0000-7000-8000-000000008c02"');
    expect(out.match(/<a /g)).toHaveLength(1);
  });

  it('renders the head with no row for an empty list', () => {
    const out = html([]);
    expect(out).toContain('SESSIONS AND RUNS');
    expect(out).not.toContain('ini-link"');
  });
});
