import { describe, expect, it } from 'vitest';

import { isStaticSpec } from '../../src/lib/charts/compare-static-charts';
import { drawn } from '../../src/lib/charts/compare-png';
import { TOTAL_CHARTS, totalCharts } from '../../src/lib/charts/compare-charts';
import { A, B, entries as unitEntries, mcell, metricOf, payloadOf } from './compare-chart-fixtures';
import { entry } from './metrics-fixtures';

const entries = {
  ...unitEntries(),
  ...Object.fromEntries(
    [
      'code.duplication_added',
      'code.suppressions_added',
      'code.skip_focus_markers_added',
      'code.test_lines',
      'code.type_escapes_added',
    ].map((id) => [id, entry(id, { group: 'code', unit: 'count', level: 'A' })]),
  ),
  'code.type_escapes_added': entry('code.type_escapes_added', {
    group: 'code',
    unit: 'count',
    level: 'H',
  }),
};

const c = (
  run: string,
  source: string | null,
  value: string | null,
  missing: string | null = null,
) =>
  mcell({
    scope_key: 'run',
    source,
    value_num: value,
    missing,
    method_id: 'm@1',
    scope_type: 'run',
  });

const dup = (over = {}) =>
  metricOf(
    'code.duplication_added',
    {
      [A]: [c(A, 'production', '7'), c(A, 'per_100', '0.95')],
      [B]: [c(B, 'production', '9'), c(B, 'per_100', null, 'raw only')],
    },
    over,
  );

describe('static charts', () => {
  it('has the six specs, type escapes in HEADLINE and the rest in ALL', () => {
    const ids = TOTAL_CHARTS.filter((s) => s.ids[0].startsWith('code.')).map((s) => s.title);
    expect(ids).toHaveLength(6);
    const payload = payloadOf([
      dup(),
      metricOf('code.type_escapes_added', {
        [A]: [c(A, 'test', '2'), c(A, 'test:per_100', '1.5')],
        [B]: [c(B, 'test', '1')],
      }),
    ]);
    const head = totalCharts(payload, entries, 'headline').map((x) => x.title);
    expect(head).toEqual(['type escapes in tests · per 100 test lines']);
    const all = totalCharts(payload, entries, 'all').map((x) => x.title);
    expect(all).toContain('duplicated lines added');
  });

  it('tells a static spec from the others', () => {
    expect(isStaticSpec({ ids: ['code.test_lines'] })).toBe(true);
    expect(isStaticSpec({ ids: ['cost.gateway'] })).toBe(false);
  });

  it('draws the raw value with the stored rate as the label, or raw only', () => {
    const [chart] = totalCharts(payloadOf([dup()]), entries, 'all');
    const [a, b] = chart.groups[0].rows;
    expect(drawn(a.marks[0], 10, 100)?.label).toBe('7 · 0.95 per 100');
    expect(drawn(b.marks[0], 10, 100)?.label).toBe('9 · raw only');
    expect(chart.flag).toBeNull();
  });

  it('picks the source of the spec for test lines', () => {
    const payload = payloadOf([
      metricOf('code.test_lines', {
        [A]: [
          c(A, 'test_unit:added', '4'),
          c(A, 'test_unit:added:per_100', '2'),
          c(A, 'test_e2e:added', '9'),
        ],
        [B]: [c(B, 'test_unit:added', null, 'not run — x')],
      }),
    ]);
    payload.diff_size[B] = '+1 −1 · 1 files';
    const charts = totalCharts(payload, entries, 'all');
    expect(charts.map((x) => x.title)).toEqual([
      'test lines added · unit',
      'test lines added · e2e',
    ]);
    expect(drawn(charts[0].groups[0].rows[0].marks[0], 10, 100)?.label).toBe('4 · 2.00 per 100');
    expect(charts[0].groups[0].rows[1].marks[0].word).toBe('not run — x');
    expect(charts[1].groups[0].rows[0].marks[0].value?.value_num).toBe('9');
    expect(charts[1].groups[0].rows[0].marks[0].rate).toBeUndefined();
    expect(charts[1].groups[0].rows[1].marks[0].word).toBe('—');
  });

  it('dots a Run measured with another tool version and flags the chart', () => {
    const payload = payloadOf([
      dup({
        tool_versions_differ: true,
        toolsets: {
          [A]: [{ tool: 'jscpd', version: '4.0.5' }],
          [B]: [{ tool: 'jscpd', version: '4.1.0' }],
        },
      }),
    ]);
    const [chart] = totalCharts(payload, entries, 'all');
    expect(chart.flag).toBe('≠ tool versions differ: jscpd 4.0.5 (Run 1) vs 4.1.0 (Run 2)');
    const [a, b] = chart.groups[0].rows;
    expect(a.marks[0].dotted).toBeUndefined();
    expect(b.marks[0].dotted).toBe('jscpd 4.1.0');
    expect(drawn(b.marks[0], 10, 100)?.label).toBe('9 · raw only · jscpd 4.1.0');
  });

  it('keeps a Run on the first toolset undotted when the lines match', () => {
    const payload = payloadOf([
      dup({
        tool_versions_differ: true,
        toolsets: {
          [A]: [{ tool: 'jscpd', version: '1' }],
          [B]: [
            { tool: 'jscpd', version: '1' },
            { tool: 'lizard', version: '2' },
          ],
        },
      }),
    ]);
    const [chart] = totalCharts(payload, entries, 'all');
    expect(chart.groups[0].rows[1].marks[0].dotted).toBeUndefined();
  });

  it('falls back to the methods flag when the tool versions match', () => {
    const payload = payloadOf([
      dup({
        methods_differ: true,
        methods: { [A]: ['code.duplication_added@1'], [B]: ['code.duplication_added@2'] },
      }),
    ]);
    const [chart] = totalCharts(payload, entries, 'all');
    expect(chart.flag).toBe(
      '≠ methods differ: code.duplication_added@1 · code.duplication_added@2',
    );
    expect(chart.groups[0].rows[1].marks[0].dotted).toBe('code.duplication_added@2');
  });

  it('lets the tool flag win over the methods flag', () => {
    const payload = payloadOf([
      dup({
        methods_differ: true,
        methods: { [A]: ['m@1'], [B]: ['m@2'] },
        tool_versions_differ: true,
        toolsets: {
          [A]: [{ tool: 'jscpd', version: '1' }],
          [B]: [{ tool: 'jscpd', version: '2' }],
        },
      }),
    ]);
    const [chart] = totalCharts(payload, entries, 'all');
    expect(chart.flag).toBe('≠ tool versions differ: jscpd 1 (Run 1) vs 2 (Run 2)');
    expect(chart.groups[0].rows[1].marks[0].dotted).toBe('jscpd 2');
  });

  it('prints not run, with no bar, for a Run without an analysis', () => {
    const payload = payloadOf([
      metricOf('code.duplication_added', {
        [A]: [c(A, 'production', '7')],
        [B]: [],
      }),
    ]);
    payload.diff_size[B] = 'not run';
    const [chart] = totalCharts(payload, entries, 'all');
    expect(chart.groups[0].rows[1].marks[0].word).toBe('not run');
    expect(drawn(chart.groups[0].rows[1].marks[0], 10, 100)?.kind).toBe('missing');
    expect(chart.groups[0].rows[0].marks[0].rate).toBeUndefined();
  });

  it('prints a stored missing word of the raw cell', () => {
    const payload = payloadOf([
      metricOf('code.duplication_added', {
        [A]: [c(A, 'production', null, 'not run — tool')],
        [B]: [c(B, 'production', '1')],
      }),
    ]);
    const [chart] = totalCharts(payload, entries, 'all');
    expect(chart.groups[0].rows[0].marks[0].word).toBe('not run — tool');
  });
});
