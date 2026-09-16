/**
 * `HistoryTable.tsx` off-mode behavior (story 9-6): `trace_url: null` on an otherwise-normal
 * agent row (harness and cost_usd non-null) — isolates the trace-null case from the
 * multi-null-field `git.commit` scenario already covered by the frozen
 * `runs-history-table.test.ts` (ANCHOR READ-ONLY).
 *
 * Kept in its own file so the off-mode coverage is explicitly attributed to this story and
 * survives any future refactor of the general table tests.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HistoryTable from '../../src/components/runs/HistoryTable';
import { EMPTY_CELL, type HistoryRowOut } from '../../src/lib/runs/history';

const RUN_ID = '33333333-3333-3333-3333-333333333333';
const ATTEMPT_ID = '44444444-4444-4444-4444-444444444444';

function row(overrides: Partial<HistoryRowOut> = {}): HistoryRowOut {
  return {
    attempt_id: ATTEMPT_ID,
    run_id: RUN_ID,
    seq: 3,
    started_at: '2026-09-14T10:00:00Z',
    ended_at: '2026-09-14T10:05:00Z',
    seconds: 300,
    project_name: 'acme',
    run_label: 'story v1 · feat/epic-09',
    path: 'epics[0].stories[0].build',
    kind: 'agent',
    harness: 'claude',
    model: 'claude-sonnet-4-6',
    session_id: 'sess-off-mode',
    status: 'done',
    token: 'DON',
    tokens_in: 500,
    tokens_out: 150,
    cost_usd: '0.420000',
    cost_provisional: true,
    trace_url: null,
    log_tail_url: `/api/v1/runs/${RUN_ID}/detail`,
    ...overrides,
  };
}

function render(rows: HistoryRowOut[]): string {
  return renderToStaticMarkup(createElement(HistoryTable, { rows }));
}

describe('HistoryTable · off-mode · null trace_url on agent row (Langfuse disabled)', () => {
  it('renders the em dash in the trace cell when trace_url is null', () => {
    const html = render([row()]);

    expect(html).toContain(EMPTY_CELL);
  });

  it('renders no noreferrer anchor in the trace cell when trace_url is null', () => {
    const html = render([row()]);

    expect(html).not.toContain('rel="noreferrer noopener"');
  });
});
