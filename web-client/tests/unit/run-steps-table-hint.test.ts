import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it } from 'vitest';

import StepsTable from '../../src/components/run/StepsTable';
import { resetCatalogue } from '../../src/stores/catalogue';
import { detailOf, seedCatalogue } from './run-metrics-fixtures';

const steps = [
  {
    seq: 1,
    path: 'build',
    kind: 'agent',
    gate: 'deterministic',
    status: 'done',
    token: 'DON',
    cost_usd: '0.50',
    started_at: null,
    ended_at: null,
    harness: 'claude',
  },
];
const render = () =>
  renderToStaticMarkup(
    createElement(StepsTable, {
      detail: { ...detailOf(), steps } as never,
      anchoredSeq: null,
      runId: 'r1',
    }),
  );

beforeEach(() => resetCatalogue());

describe('StepsTable cost head hint', () => {
  it('has the spend.recorded control on the cost head only when catalogued', () => {
    expect(render()).not.toContain('metric-hint-control');
    seedCatalogue();
    const out = render();
    expect(out.match(/metric-hint-control/g)).toHaveLength(1);
    expect(out).toMatch(/cost<span[^>]*><button[^>]*how label of spend\.recorded is calculated/);
    expect(out).toContain('$0.50');
  });
});
