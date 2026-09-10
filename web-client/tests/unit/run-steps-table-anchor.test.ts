/**
 * The Steps table's `#step-{seq}` anchor (7.5). `run-steps-table.test.ts` covers the table
 * as 4.15 wrote it and is frozen; what it cannot cover is behaviour that did not exist when
 * it was written, so the row id, the anchored promotion, and the promotion's neutrality live
 * here — the same split `component-props.test.ts` documents for its own two additions.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StepsTable from '../../src/components/run/StepsTable';
import type { RunDetailOut, StepRowOut } from '../../src/lib/run/detail';

function step(overrides: Partial<StepRowOut> = {}): StepRowOut {
  return {
    seq: 7,
    path: 'epics[0].stories[3].build',
    label: 'build',
    kind: 'agent',
    gate: 'deterministic',
    status: 'done',
    token: 'DON',
    reason: null,
    attempts: 1,
    latest: null,
    cost_usd: '0',
    ...overrides,
  } as StepRowOut;
}

function detail(steps: StepRowOut[]): RunDetailOut {
  // the minimum `currentStepPath` reads: a Run status, no alert, no gate record
  return {
    steps,
    run: { status: 'running' },
    alert: null,
    gate_record: [],
  } as unknown as RunDetailOut;
}

function render(steps: StepRowOut[], anchoredSeq: number | null): string {
  return renderToStaticMarkup(createElement(StepsTable, { detail: detail(steps), anchoredSeq }));
}

describe('the Steps table anchor', () => {
  it('gives every row the id a history link targets', () => {
    expect(render([step()], null)).toContain('id="step-7"');
  });

  it('promotes the row the detail was opened at, and only that one', () => {
    const html = render([step(), step({ seq: 8, path: 'epics[0].stories[4].build' })], 7);

    expect(html).toMatch(/id="step-7"[^>]*data-anchored="true"/);
    expect(html).toMatch(/id="step-8"[^>]*data-anchored="false"/);
  });

  it('promotes nothing when the page was opened without a fragment', () => {
    expect(render([step()], null)).not.toContain('data-anchored="true"');
  });

  it('adds no second signal colour to the promoted row', () => {
    const html = render([step()], 7);

    const signalled = [...html.matchAll(/data-signal="([^"]*)"/g)].map((match) => match[1]);
    expect(signalled).toEqual(['neutral']);
  });
});
