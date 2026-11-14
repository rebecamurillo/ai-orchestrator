import { describe, expect, it } from 'vitest';

import {
  CHART_TITLES,
  NO_MODEL_GATEWAY,
  modelRows,
  roleOrder,
  roleRows,
  runCharts,
  scopeRows,
  seriesKey,
  timeRows,
  tokenRows,
  tokensTitle,
} from '../../src/lib/charts/run-charts';
import { entry, value } from './metrics-fixtures';

const at = (metric_id: string, scope_type: string, scope_key: string, over = {}) =>
  value({ metric_id, scope_type, scope_key, value_num: '2', ...over });

const STORY0 = 'epics[0].stories[0]';
const STORY1 = 'epics[0].stories[1]';
const RETRO = 'epics[0].retro';
const STEPS = [`${STORY0}.build`, `${STORY1}.build`, RETRO];

const entries = Object.fromEntries(
  [
    'cost.gateway',
    'cost.harness',
    'cost.retries',
    'tokens.output',
    'tokens.cache_read',
    'tokens.cache_write',
    'tokens.input',
    'time.machine',
    'time.parked',
  ].map((id) => [id, entry(id)]),
);

describe('scopeRows', () => {
  const items = [
    at('cost.gateway', 'story', STORY1, { value_num: '3' }),
    at('cost.harness', 'story', STORY1),
    at('cost.gateway', 'story', STORY0),
    at('cost.harness', 'story', STORY0),
    at('cost.retries', 'story', STORY0, { source: 'gateway', value_num: '1' }),
    at('cost.retries', 'story', STORY0, { source: 'harness', value_num: '0.5' }),
    at('cost.gateway', 'step', `${STORY0}.build`),
    at('cost.gateway', 'step', RETRO),
    at('cost.harness', 'step', RETRO, {
      value_num: null,
      missing: 'n/a — shell step, no model called',
    }),
    at('cost.gateway', 'attempt', `${STORY0}.build#1`, { attempt_n: 1 }),
  ];

  it('lists stories and the steps outside a story in tree order', () => {
    const rows = scopeRows(items, STEPS);
    expect(rows.map((r) => r.label)).toEqual(['epic 1 · story 1', 'epic 1 · story 2', RETRO]);
    expect(rows.map((r) => r.id)).toEqual([`story:${STORY0}`, `story:${STORY1}`, `step:${RETRO}`]);
  });

  it('reads the table values, shares by exact source, and keeps a shell word', () => {
    const [first, , retro] = scopeRows(items, STEPS);
    expect(first.gateway?.value_num).toBe('2');
    expect(first.gatewayShare?.value_num).toBe('1');
    expect(first.harnessShare?.value_num).toBe('0.5');
    expect(retro.gateway?.value_num).toBe('2');
    expect(retro.harness?.missing).toBe('n/a — shell step, no model called');
    expect(retro.gatewayShare).toBeNull();
  });

  it('has a null figure where the scope has no value', () => {
    const rows = scopeRows([at('cost.gateway', 'story', STORY0)], STEPS);
    expect(rows[0].harness).toBeNull();
  });
});

describe('roleOrder, roleRows, tokenRows', () => {
  const items = [
    at('cost.gateway', 'role', 'review', { value_num: '9' }),
    at('cost.gateway', 'role', 'implement', { value_num: '5' }),
    at('cost.gateway', 'role', 'senior', { value_num: '1' }),
    at('cost.gateway', 'role', 'unseen', { value_num: '0.5' }),
    at('cost.harness', 'role', 'implement'),
    at('tokens.output', 'role', 'implement', { unit: 'tokens' }),
    at('tokens.output', 'role', 'review', { value_num: null, missing: 'not recorded' }),
    at('cost.gateway', 'attempt', `${STORY0}.build#1`, { role: 'implement', attempt_n: 1 }),
    at('cost.gateway', 'attempt', `${STORY0}.build#2`, { role: 'senior', attempt_n: 2 }),
    at('cost.gateway', 'attempt', `${STORY1}.build#1`, { role: 'review', attempt_n: 1 }),
    at('cost.gateway', 'attempt', `${STORY1}.build#1`, { role: null, attempt_n: 1 }),
  ];

  it('follows plan order from the attempts, unseen roles after', () => {
    expect(roleOrder(items, STEPS)).toEqual(['implement', 'senior', 'review', 'unseen']);
  });

  it('ranks an attempt of a step the plan does not list after the planned ones', () => {
    const extra = [
      at('cost.gateway', 'role', 'a', { value_num: '2' }),
      at('cost.gateway', 'role', 'b', { value_num: '1' }),
      at('cost.gateway', 'attempt', 'ghost#1', { role: 'a', attempt_n: 1 }),
      at('cost.gateway', 'attempt', `${STORY0}.build#1`, { role: 'b', attempt_n: 1 }),
    ];
    expect(roleOrder(extra, STEPS)).toEqual(['b', 'a']);
  });

  it('breaks a tie on the same step by attempt number', () => {
    const tie = [
      at('cost.gateway', 'role', 'a', { value_num: '2' }),
      at('cost.gateway', 'role', 'b', { value_num: '1' }),
      at('cost.gateway', 'attempt', `${STORY0}.build#2`, { role: 'a', attempt_n: 2 }),
      at('cost.gateway', 'attempt', `${STORY0}.build#1`, { role: 'b', attempt_n: 1 }),
    ];
    expect(roleOrder(tie, STEPS)).toEqual(['b', 'a']);
  });

  it('builds pair rows and token rows for the same roles', () => {
    const pairs = roleRows(items, STEPS);
    expect(pairs.map((r) => r.label)).toEqual(['implement', 'senior', 'review', 'unseen']);
    expect(pairs[0].harness?.value_num).toBe('2');
    expect(pairs[1].harness).toBeNull();
    const tokens = tokenRows(items, STEPS, 'tokens.output');
    expect(tokens.map((r) => r.label)).toEqual(['implement', 'senior', 'review', 'unseen']);
    expect(tokens[0].value?.value_num).toBe('2');
    expect(tokens[1].value).toBeNull();
    expect(tokens[2].value?.missing).toBe('not recorded');
  });
});

describe('modelRows', () => {
  it('uses the gateway value of a model row when one exists', () => {
    const items = [
      at('cost.gateway', 'model', 'sonnet'),
      at('cost.harness', 'model', 'sonnet', { value_num: '4' }),
    ];
    const [row] = modelRows(items);
    expect(row.gateway?.value_num).toBe('2');
    expect(row.gatewayWord).toBeUndefined();
    expect(row.harness?.value_num).toBe('4');
  });

  it('says the split is not stored when no model row carries a gateway value', () => {
    const rows = modelRows([at('cost.harness', 'model', 'sonnet'), at('cost.gateway', 'run', '')]);
    expect(rows).toHaveLength(1);
    expect(rows[0].gateway).toBeNull();
    expect(rows[0].gatewayWord).toBe(NO_MODEL_GATEWAY);
    expect(NO_MODEL_GATEWAY).toBe('not available (per-model gateway split not stored)');
  });
});

describe('timeRows', () => {
  it('takes machine and parked time at run scope, hatching the parked one', () => {
    const rows = timeRows(
      [
        at('time.machine', 'run', 'r', { unit: 'seconds', value_num: '60' }),
        at('time.parked', 'run', 'r', { unit: 'seconds', value_num: '30' }),
        at('time.machine', 'step', 's', { unit: 'seconds' }),
      ],
      entries,
    );
    expect(rows.map((r) => [r.label, r.texture])).toEqual([
      ['label of time.machine', undefined],
      ['label of time.parked', 'hatch'],
    ]);
  });

  it('drops an absent value and keeps a missing word', () => {
    const rows = timeRows(
      [at('time.parked', 'run', 'r', { value_num: null, missing: 'not recorded' })],
      entries,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].value?.missing).toBe('not recorded');
  });

  it('falls back to the metric id for an uncatalogued label', () => {
    expect(timeRows([at('time.machine', 'run', 'r')], {})[0].label).toBe('time.machine');
  });
});

describe('runCharts and seriesKey', () => {
  const items = [
    at('cost.gateway', 'story', STORY0),
    at('cost.harness', 'story', STORY0),
    at('cost.retries', 'story', STORY0, { source: 'gateway' }),
    at('cost.gateway', 'role', 'implement'),
    at('cost.harness', 'role', 'implement'),
    at('tokens.output', 'role', 'implement'),
    at('tokens.cache_read', 'role', 'implement'),
    at('tokens.cache_write', 'role', 'implement'),
    at('tokens.input', 'role', 'implement'),
    at('cost.harness', 'model', 'm'),
    at('time.machine', 'run', 'r', { unit: 'seconds' }),
  ];
  const label = (id: string) => `label of ${id}`;

  it('lists the headline panels in order', () => {
    const charts = runCharts(entries, items, STEPS, 'headline');
    expect(charts.map((c) => c.title)).toEqual([
      CHART_TITLES.scope,
      CHART_TITLES.role,
      tokensTitle(label('tokens.output')),
      tokensTitle(label('tokens.cache_read')),
      CHART_TITLES.model,
      CHART_TITLES.time,
    ]);
    expect(charts.map((c) => c.kind)).toEqual(['pair', 'pair', 'bar', 'bar', 'pair', 'time']);
    expect(tokensTitle('x')).toBe('tokens by role · x');
  });

  it('adds the two other token classes after the headline ones', () => {
    const charts = runCharts(entries, items, STEPS, 'all');
    expect(charts.map((c) => c.title).slice(2, 6)).toEqual([
      tokensTitle(label('tokens.output')),
      tokensTitle(label('tokens.cache_read')),
      tokensTitle(label('tokens.cache_write')),
      tokensTitle(label('tokens.input')),
    ]);
  });

  it('drops a panel without a catalogue entry or without rows', () => {
    const slim = { ...entries };
    delete slim['tokens.output'];
    delete slim['time.machine'];
    const charts = runCharts(slim, items, STEPS, 'headline');
    expect(charts.map((c) => c.title)).not.toContain(tokensTitle(label('tokens.output')));
    expect(charts.map((c) => c.kind)).not.toContain('time');
    const none = runCharts(entries, [], STEPS, 'all');
    expect(none).toEqual([]);
    const noGateway = { ...entries };
    delete noGateway['cost.gateway'];
    expect(runCharts(noGateway, items, STEPS, 'headline').map((c) => c.kind)).toEqual([
      'bar',
      'bar',
      'time',
    ]);
  });

  it('builds the series key from catalogue labels', () => {
    const [scope, , , , , time] = runCharts(entries, items, STEPS, 'headline');
    expect(seriesKey(entries, scope, true)).toBe(
      'label of cost.gateway · label of cost.harness · hatched = label of cost.retries',
    );
    expect(seriesKey(entries, scope, false)).toBe('label of cost.gateway · label of cost.harness');
    expect(seriesKey(entries, time, false)).toBe(
      'label of time.machine · hatched = label of time.parked',
    );
    const [, , output] = runCharts(entries, items, STEPS, 'headline');
    expect(seriesKey(entries, output, false)).toBe('label of tokens.output');
  });

  it('omits an uncatalogued hatch word from the key', () => {
    const [scope, , , , , time] = runCharts(entries, items, STEPS, 'headline');
    const slim = { ...entries };
    delete slim['cost.retries'];
    delete slim['time.parked'];
    expect(seriesKey(slim, scope, true)).toBe('label of cost.gateway · label of cost.harness');
    expect(seriesKey(slim, time, false)).toBe('label of time.machine');
  });
});
