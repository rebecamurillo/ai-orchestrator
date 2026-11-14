import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it } from 'vitest';

import AttemptsTable, { type AttemptDetail } from '../../src/components/run/AttemptsTable';
import { metricsContext } from '../../src/components/run/MetricsTab';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { value } from './metrics-fixtures';
import { detailOf, glanceOf, seedCatalogue } from './run-metrics-fixtures';

function attempt(n: number, cost: string | null): AttemptDetail {
  return {
    id: `a${n}`,
    n,
    status: 'done',
    token: 'DON',
    started_at: null,
    ended_at: null,
    seconds: 3,
    harness: 'claude',
    model: 'm',
    session_id: null,
    exit_code: 0,
    cost_usd: cost,
    cost_provisional: false,
    tokens_in: null,
    tokens_out: null,
    dispatch_prompt: null,
    retry_prompt: null,
    result: null,
    command: null,
  };
}

const ctx = metricsContext(detailOf(), glanceOf(), false);
const noop = () => undefined;
const render = (values?: ReturnType<typeof value>[], withCtx = true) =>
  renderToStaticMarkup(
    createElement(AttemptsTable, {
      attempts: [attempt(1, '0.42'), attempt(2, null)],
      selectedN: 1,
      onSelect: noop,
      onDrawer: noop,
      values,
      ctx: withCtx ? ctx : undefined,
    }),
  );

beforeEach(() => resetCatalogue());

describe('AttemptsTable figures', () => {
  it('adds six catalogued heads after cost and the values on the right row', () => {
    seedCatalogue();
    const out = render([
      value({
        metric_id: 'tokens.input',
        scope_type: 'attempt',
        scope_key: 'a.build#2',
        attempt_n: 2,
        value_num: '1234',
        unit: 'tokens',
      }),
    ]);
    const heads = [...out.matchAll(/<th scope="col">/g)];
    expect(heads).toHaveLength(14);
    expect(out).toContain('label of tokens.cache_write');
    expect(out).toContain(
      'how recorded spend is calculated'.replace('recorded spend', 'label of spend.recorded'),
    );
    expect(out).toContain('$0.42');
    const rows = out.split('<tr').slice(2);
    expect(rows[0]).not.toContain('metric-value-cell');
    expect(rows[1]).toContain('metric-value-cell');
  });

  it('keeps the eight base columns without a catalogue', () => {
    expect(render([], true).match(/<th /g)).toHaveLength(8);
    expect(render(undefined, false).match(/<th /g)).toHaveLength(8);
    expect($catalogue.get().status).toBe('idle');
  });
});
