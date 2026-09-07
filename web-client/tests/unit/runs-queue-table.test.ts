/**
 * `QueueTable.tsx` (4.16, UX-DR14): every column, the em dash for a Run already holding its
 * slot, the fixed reason printed verbatim, the parked hint, and no colour anywhere in the
 * table (`renderToStaticMarkup`, stateless — `StepsTable.test.ts`'s own precedent).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import QueueTable from '../../src/components/runs/QueueTable';
import { REASON_WAITING_ANSWER, type QueueItemOut, type QueueRun } from '../../src/lib/runs/queue';

function run(overrides: Partial<QueueRun> = {}): QueueRun {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    status: 'queued',
    template: 'initiative',
    version: 1,
    project: '22222222-2222-2222-2222-222222222222',
    repository: '33333333-3333-3333-3333-333333333333',
    branch: 'epics/1',
    budget_usd: '15.00',
    spend_usd: '0',
    plan_ref: null,
    created_at: '2026-09-07T09:00:00Z',
    admitted_signals: [],
    ...overrides,
  };
}

function row(overrides: Partial<QueueItemOut> = {}): QueueItemOut {
  return {
    position: 1,
    run: run(),
    next_step_label: 'plan',
    reason: 'repository lock held by initiative v1 · feat/other',
    waiting_since: '2026-09-07T09:00:00Z',
    waiting_seconds: 90,
    ...overrides,
  };
}

describe('QueueTable', () => {
  it('renders every column, in the fixed order, with an em dash for the running row', () => {
    const html = renderToStaticMarkup(
      createElement(QueueTable, {
        items: [row({ position: null, reason: 'running', run: run({ id: 'r1' }) })],
      }),
    );

    expect(html).toContain('data-testid="runs-queue-row-r1"');
    expect(html).toMatch(/<td>—<\/td>/);
    expect(html).toContain('22222222-2222-2222-2222-222222222222');
    expect(html).toContain('initiative v1 · epics/1');
    expect(html).toContain('href="/workflows/r1"');
    expect(html).toContain('plan');
    expect(html).toContain('running');
  });

  it('prints the position for a queued row, and the reason verbatim, unreworded', () => {
    const html = renderToStaticMarkup(
      createElement(QueueTable, {
        items: [
          row({
            position: 2,
            reason: 'global concurrency, held by initiative v1 · epics/1, epic v3 · epics/2',
            run: run({ id: 'r2' }),
          }),
        ],
      }),
    );

    expect(html).toContain('<td>2</td>');
    expect(html).toContain(
      'global concurrency, held by initiative v1 · epics/1, epic v3 · epics/2',
    );
  });

  it('adds the parked hint only under the waiting-for-your-answer reason', () => {
    const parked = renderToStaticMarkup(
      createElement(QueueTable, {
        items: [row({ position: null, reason: REASON_WAITING_ANSWER, run: run({ id: 'r3' }) })],
      }),
    );
    const notParked = renderToStaticMarkup(
      createElement(QueueTable, {
        items: [row({ reason: 'running', run: run({ id: 'r4' }) })],
      }),
    );

    expect(parked).toContain('not queued until then');
    expect(notParked).not.toContain('not queued until then');
  });

  it('reads an em dash for a Run with no next-step label yet', () => {
    const html = renderToStaticMarkup(
      createElement(QueueTable, { items: [row({ next_step_label: '' })] }),
    );

    // one em dash for `pos` (position: 1 here, so not that one) plus one for `next step`
    expect(html.match(/<td>—<\/td>/g)?.length).toBe(1);
  });

  it('carries no colour anywhere — the signal rule keeps this table token-free', () => {
    const html = renderToStaticMarkup(
      createElement(QueueTable, {
        items: [row({ reason: 'running' }), row({ position: null, reason: REASON_WAITING_ANSWER })],
      }),
    );

    expect(html).not.toContain('data-signal');
    expect(html).not.toContain('style=');
  });
});
