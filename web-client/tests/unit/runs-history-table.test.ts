/**
 * `HistoryTable.tsx` (7.5, UX-DR14): the ten columns in their fixed order, one row per
 * attempt with its own test-id, the row link, the em dashes a non-agent row reads as, and
 * the signal rule — the status token is the only coloured cell in a row (NFR-6).
 *
 * `renderToStaticMarkup`, stateless — `QueueTable.test.ts`'s own precedent.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HistoryTable from '../../src/components/runs/HistoryTable';
import type { HistoryRowOut } from '../../src/lib/runs/history';

const RUN_ID = '11111111-1111-1111-1111-111111111111';
const ATTEMPT_ID = '22222222-2222-2222-2222-222222222222';

function row(overrides: Partial<HistoryRowOut> = {}): HistoryRowOut {
  return {
    attempt_id: ATTEMPT_ID,
    run_id: RUN_ID,
    seq: 7,
    started_at: '2026-09-09T08:04:05Z',
    ended_at: '2026-09-09T08:06:35Z',
    seconds: 150,
    project_name: 'acme',
    run_label: 'story v3 · feat/epic-7',
    path: 'epics[0].stories[3].build',
    kind: 'agent',
    harness: 'codex',
    model: 'gpt-5-codex',
    session_id: 'sess-1',
    status: 'done',
    token: 'DON',
    tokens_in: 100,
    tokens_out: 20,
    cost_usd: '0.250000',
    cost_provisional: false,
    trace_url: 'https://langfuse.test/t/1',
    log_tail_url: `/api/v1/runs/${RUN_ID}/detail`,
    ...overrides,
  };
}

function render(rows: HistoryRowOut[]): string {
  return renderToStaticMarkup(createElement(HistoryTable, { rows }));
}

describe('HistoryTable', () => {
  it('renders the ten column heads in UX-DR14’s order', () => {
    const heads = [...render([row()]).matchAll(/<th scope="col">([^<]*)<\/th>/g)].map(
      (match) => match[1],
    );

    expect(heads).toEqual([
      'time',
      'project',
      'workflow',
      'path',
      'kind',
      'harness',
      'status',
      'time',
      'cost',
      'trace',
    ]);
  });

  it('gives every row its own test-id, keyed by the attempt', () => {
    expect(render([row()])).toContain(`data-testid="runs-history-row-${ATTEMPT_ID}"`);
  });

  it('prints the path, never the label (UX-DR16), and links it to the Run detail at that row', () => {
    const html = render([row()]);

    expect(html).toContain('epics[0].stories[3].build');
    expect(html).toContain(`href="/workflows/${RUN_ID}#step-7"`);
  });

  it('reads every cell of an agent attempt', () => {
    const html = render([row()]);

    expect(html).toContain('08:04:05');
    expect(html).toContain('acme');
    expect(html).toContain('story v3 · feat/epic-7');
    expect(html).toContain('agent');
    expect(html).toContain('codex · gpt-5-codex');
    expect(html).toContain('150s');
    expect(html).toContain('$0.250000');
    expect(html).toContain('href="https://langfuse.test/t/1"');
  });

  it('reads em dashes on a non-agent attempt with no trace', () => {
    const html = render([
      row({ kind: 'git.commit', harness: null, model: null, cost_usd: null, trace_url: null }),
    ]);

    expect(html).toContain('git.commit');
    expect((html.match(/—/g) ?? []).length).toBe(3);
  });

  it('promotes the executing rows above the rest', () => {
    const html = render([
      row({ attempt_id: 'a' }),
      row({ attempt_id: 'b', status: 'running', token: 'RUN', seconds: null, ended_at: null }),
    ]);

    expect(html.indexOf('runs-history-row-b')).toBeLessThan(html.indexOf('runs-history-row-a'));
    expect(html).toContain('data-current="true"');
  });

  it('colours the status token and nothing else in the row', () => {
    const html = render([row({ token: 'ERR', status: 'error' })]);

    const signalled = [...html.matchAll(/data-signal="([^"]*)"/g)].map((match) => match[1]);
    expect(signalled).toEqual(['failed']);
    expect(html).toContain('class="runs-history-token"');
  });

  it('keeps a skipped attempt a plain word rather than a signal', () => {
    const html = render([row({ token: 'SKP', status: 'skipped' })]);

    expect(html).toContain('data-signal="neutral"');
    expect(html).toContain('SKP');
  });
});
