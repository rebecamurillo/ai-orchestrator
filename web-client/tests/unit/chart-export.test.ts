// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';

import {
  exportFileName,
  exportSvg,
  flagLine,
  slug,
  sourceLine,
  svgDataUrl,
  today,
  unitWords,
  wrapText,
  type ExportMeta,
} from '../../src/lib/charts/export';
import { markFor } from '../../src/lib/charts/layout';
import {
  runCharts,
  seriesKey,
  NO_MODEL_GATEWAY,
  type RunChart,
} from '../../src/lib/charts/run-charts';
import tokens from '../../src/styles/tokens.css?raw';
import { entry, value } from './metrics-fixtures';
import { seedCatalogue } from './run-metrics-fixtures';
import { $catalogue } from '../../src/stores/catalogue';

const token = (name: string): string =>
  (new RegExp(`${name}:\\s*([^;]+);`).exec(tokens) as RegExpExecArray)[1].trim();

const at = (metric_id: string, scope_type: string, scope_key: string, over = {}) =>
  value({ metric_id, scope_type, scope_key, value_num: '2', ...over });

const extras = () =>
  ['tokens.cache_write', 'time.machine', 'time.parked', 'cost.retries'].map((id) =>
    entry(id, { label: `label of ${id}` }),
  );

let entries: ReturnType<typeof entriesOf>;
const entriesOf = () => $catalogue.get().entries;

const roleItems = () =>
  ['implement', 'senior', 'review'].flatMap((role, i) => [
    at('cost.gateway', 'role', role, { value_num: String(5 - i), role }),
    at('cost.harness', 'role', role, {
      role,
      ...(i === 1 ? { value_num: null, missing: 'not recorded' } : { value_num: String(4 - i) }),
    }),
    at('cost.gateway', 'attempt', `s.build#${i + 1}`, { role, attempt_n: i + 1 }),
  ]);

const chartOf = (items: ReturnType<typeof roleItems>, title: string): RunChart => {
  const found = runCharts(entries, items, ['s.build'], 'headline').find((c) => c.title === title);
  return found as RunChart;
};

const meta = (over: Partial<ExportMeta> = {}): ExportMeta => ({
  entries,
  project: 'familio',
  runLabel: 'snake round 2 · story session',
  runId: '0190aaaa-0000-7000-8000-000000000001',
  version: 2,
  subscription: false,
  date: '2026-11-19',
  ...over,
});

const parse = (svg: string): Document => new DOMParser().parseFromString(svg, 'image/svg+xml');
const texts = (doc: Document): Element[] => [...doc.querySelectorAll('text')];
const words = (doc: Document): string[] => texts(doc).map((t) => t.textContent ?? '');

beforeEach(() => {
  seedCatalogue(extras());
  entries = entriesOf();
});

describe('exportSvg content (AC1)', () => {
  it('prints title, context, key, rows, mark labels, the missing word and the source line', () => {
    const chart = chartOf(roleItems(), 'cost by role');
    const m = meta();
    const doc = parse(exportSvg(chart, m));
    const root = doc.documentElement;
    expect(root.getAttribute('width')).toBe('820');
    expect(root.getAttribute('viewBox')).toMatch(/^0 0 820 /);
    const all = words(doc);
    expect(all[0]).toBe('cost by role');
    expect(texts(doc)[0].getAttribute('font-size')).toBe('18');
    expect(all[1]).toBe(`${m.runLabel} · ${m.runId} · US dollars`);
    const key = seriesKey(entries, chart, false).split(' · ');
    for (const label of key) expect(all).toContain(label);
    for (const role of ['implement', 'senior', 'review']) expect(all.join('|')).toContain(role);
    if (chart.kind !== 'pair') throw new Error('pair expected');
    for (const row of chart.rows) {
      for (const v of [row.gateway, row.harness]) {
        if (v === null || v.value_num === null) continue;
        expect(all).toContain(markFor(v, 5).label);
      }
    }
    expect(all).toContain('not recorded');
    const last = texts(doc).at(-1) as Element;
    expect(last.textContent).toBe(
      'source: ai-orchestrator · project familio · result v2 · exported 2026-11-19',
    );
    expect(last.getAttribute('font-size')).toBe('12');
    for (const t of texts(doc).slice(0, -1).slice(1)) {
      expect(Number(t.getAttribute('font-size'))).toBeGreaterThanOrEqual(14);
    }
  });

  it('draws no mark for a missing value', () => {
    const chart = chartOf(roleItems(), 'cost by role');
    const doc = parse(exportSvg(chart, meta()));
    // 3 gateway + 2 harness marks (the harness value of `senior` is a word)
    expect(doc.querySelectorAll('rect[data-mark]').length).toBe(5);
  });

  it('prints subscription, live and note variants and the axis note', () => {
    const chart = chartOf(roleItems(), 'cost by role');
    const sub = words(parse(exportSvg(chart, meta({ subscription: true })))).at(-1);
    expect(sub).toBe(
      'source: ai-orchestrator · project familio · result v2 · list-price equivalent · exported 2026-11-19',
    );
    const live = words(
      parse(exportSvg(chart, meta({ version: null, notes: ['Run running · values so far'] }))),
    );
    expect(live.at(-1)).toContain('values so far · exported');
    expect(live.at(-2)).toBe('Run running · values so far');
    expect(
      words(parse(exportSvg(chart, meta({ axisFromZero: false, runLabel: 'run' }))))[1],
    ).toMatch(/ · US dollars · axis does not start at zero$/);
    expect(words(parse(exportSvg(chart, meta())))[1]).not.toContain('axis does not start');
  });

  it('escapes interpolated text', () => {
    const items = [at('cost.gateway', 'role', 'a<&>"b', { role: 'a<&>"b' })];
    const chart = chartOf(
      [
        ...items,
        at('cost.harness', 'role', 'a<&>"b', { role: 'a<&>"b' }),
        ...roleItems().slice(2, 3),
      ],
      'cost by role',
    );
    const svg = exportSvg(chart, meta({ project: 'p<&>' }));
    expect(svg).toContain('a&lt;&amp;&gt;&quot;b');
    expect(parse(svg).querySelector('parsererror')).toBeNull();
    expect(words(parse(svg)).at(-1)).toContain('project p<&>');
  });
});

describe('ink, marks and flags (AC2)', () => {
  it('uses token values, literal pattern colours and no var()', () => {
    const items = [
      ...roleItems(),
      at('cost.gateway', 'role', 'part', { role: 'part', partial_n: 1, partial_m: 2 }),
      at('cost.harness', 'role', 'part', { role: 'part', value_num: '0' }),
    ];
    const svg = exportSvg(chartOf(items, 'cost by role'), meta());
    expect(svg).not.toContain('var(');
    const doc = parse(svg);
    const ink = token('--color-chart-ink');
    for (const t of texts(doc)) expect(t.getAttribute('fill')).toBe(ink);
    for (const l of doc.querySelectorAll('line[data-grid]')) {
      expect(l.getAttribute('stroke')).toBe(ink);
      expect(l.getAttribute('stroke-opacity')).toBe('0.35');
    }
    expect(doc.querySelectorAll('line[data-grid]').length).toBeGreaterThan(1);
    const marks = [...doc.querySelectorAll('rect[data-mark]')];
    expect(marks.some((r) => r.getAttribute('fill') === token('--color-chart-data-1'))).toBe(true);
    expect(marks.some((r) => r.getAttribute('fill') === token('--color-chart-data-2'))).toBe(true);
    const partial = marks.filter((r) => r.getAttribute('fill') === 'none');
    expect(partial).toHaveLength(1);
    expect(words(doc)).toContain('$2.00 · partial · 1 of 2 attempts');
    const zero = marks.find((r) => r.getAttribute('width') === '2');
    expect(zero).toBeTruthy();
    expect(words(doc)).toContain('0');
    expect(doc.querySelectorAll('defs pattern').length).toBeGreaterThanOrEqual(2);
    for (const p of doc.querySelectorAll('defs pattern')) {
      expect(p.getAttribute('patternTransform') ?? '').toMatch(/^(rotate\(45\))?$/);
    }
    expect(svg).toContain(token('--color-chart-data-2'));
  });

  it('prints the no-model-gateway word in each gateway slot of cost by model', () => {
    const items = [at('cost.harness', 'model', 'sonnet', { value_num: '7' })];
    const doc = parse(exportSvg(chartOf(items, 'cost by model'), meta()));
    expect(words(doc).filter((w) => w === NO_MODEL_GATEWAY)).toHaveLength(1);
  });

  it('draws a hatched share at the end of a bar', () => {
    const items = [
      at('cost.gateway', 'story', 'epics[0].stories[0]', { value_num: '10' }),
      at('cost.harness', 'story', 'epics[0].stories[0]', { value_num: '12' }),
      at('cost.retries', 'story', 'epics[0].stories[0]', { source: 'gateway', value_num: '3' }),
    ];
    const chart = runCharts(entries, items, ['epics[0].stories[0].build'], 'headline')[0];
    const doc = parse(exportSvg(chart, meta()));
    expect(doc.querySelector('rect[fill^="url(#hatch"]')).not.toBeNull();
    expect(words(doc)).toContain('label of cost.retries');
  });

  it('flags metrics read with different methods, only then', () => {
    const same = roleItems().map((v) => ({ ...v, method_id: `${v.metric_id}@2` }));
    const one = chartOf(same, 'cost by role');
    expect(flagLine(one)).toBeNull();
    expect(words(parse(exportSvg(one, meta()))).some((w) => w.startsWith('≠'))).toBe(false);
    const other = at('cost.gateway', 'role', 'x', { role: 'x', method_id: 'cost.gateway@1' });
    const mixed = chartOf([...same, other], 'cost by role');
    expect(flagLine(mixed)).toBe('≠ methods differ: cost.gateway@1 · cost.gateway@2');
    expect(words(parse(exportSvg(mixed, meta())))).toContain(
      '≠ methods differ: cost.gateway@1 · cost.gateway@2',
    );
  });

  it('exports the time chart on duration ticks with a hatched park row', () => {
    const items = [
      at('time.machine', 'run', 'r', {
        unit: 'seconds',
        value_num: '5400',
        method_id: 'time.machine@1',
      }),
      at('time.parked', 'run', 'r', {
        unit: 'seconds',
        value_num: '1800',
        method_id: 'time.machine@1',
      }),
    ];
    const chart = chartOf(items, 'where the time went');
    const doc = parse(exportSvg(chart, meta()));
    const all = words(doc);
    expect(all[1]).toContain('hours and minutes');
    expect(all).toContain('1h 30m');
    expect(doc.querySelector('rect[data-mark][fill^="url(#hatch"]')).not.toBeNull();
  });

  it('exports a token chart', () => {
    const items = [
      at('tokens.output', 'role', 'implement', {
        unit: 'tokens',
        value_num: '1000',
        role: 'implement',
      }),
    ];
    entries = { ...entries, 'tokens.output': entry('tokens.output', { unit: 'tokens' }) };
    const doc = parse(exportSvg(chartOf(items, 'tokens by role · label of tokens.output'), meta()));
    expect(words(doc)[1]).toMatch(/· tokens$/);
  });
});

describe('background (AC3), font (AC4), no follow (AC6)', () => {
  const chart = () => chartOf(roleItems(), 'cost by role');
  it('draws no background when transparent, one rectangle otherwise', () => {
    const none = parse(exportSvg(chart(), meta()));
    expect(none.querySelectorAll('rect:not([data-mark]):not([data-key])')).toHaveLength(0);
    for (const [bg, fill] of [
      ['light', '#ffffff'],
      ['dark', token('--color-bg')],
    ] as const) {
      const doc = parse(exportSvg(chart(), meta(), bg));
      const full = [...doc.querySelectorAll('rect')].filter(
        (r) => r.getAttribute('width') === '820',
      );
      expect(full).toHaveLength(1);
      expect(full[0].getAttribute('fill')).toBe(fill);
      expect(doc.documentElement.querySelector('rect')).toBe(full[0]);
    }
  });

  it('embeds the font subset and uses it on every text', () => {
    const svg = exportSvg(chart(), meta());
    expect(svg.match(/@font-face/g)).toHaveLength(1);
    expect(svg).toContain('src: url(data:font/woff2;base64,d09GMg');
    for (const t of texts(parse(svg))) {
      expect(t.getAttribute('font-family')).toBe("'JetBrains Mono Export', monospace");
    }
  });

  it('carries no accent, underline or outline', () => {
    const svg = exportSvg(chart(), meta());
    expect(svg).not.toContain(token('--color-accent'));
    expect(svg).not.toMatch(/underline|outline/);
    expect(Object.keys(meta())).not.toContain('follow');
  });
});

describe('words and names (AC7)', () => {
  it('names the file from the slugged parts', () => {
    expect(
      exportFileName('familio', 'snake round 2 · story session', 'cost by role', '2026-11-19'),
    ).toBe('familio-snake-round-2-story-session-cost-by-role-2026-11-19.png');
    expect(slug('familio familio-snake-v2 bench-v1-staged 2026-11-10 10:23')).toBe(
      'familio-familio-snake-v2-bench-v1-staged-2026-11-10-1023',
    );
    expect(slug(' -A  ·  B- ')).toBe('a-b');
  });

  it('words units, the source line, wrapping, the date and the data URL', () => {
    expect(unitWords('USD')).toBe('US dollars');
    expect(unitWords('seconds')).toBe('hours and minutes');
    expect(unitWords('tokens')).toBe('tokens');
    expect(unitWords('other')).toBe('other');
    expect(sourceLine(meta({ version: null }))).toContain('values so far · exported');
    expect(wrapText('aaa bbb ccc', 10, 60)).toEqual(['aaa bbb', 'ccc']);
    expect(wrapText('supercalifragilistic x', 10, 30)).toEqual(['supercalifragilistic', 'x']);
    expect(wrapText('', 10, 30)).toEqual(['']);
    expect(today(new Date('2026-11-19T23:59:00Z'))).toBe('2026-11-19');
    expect(today()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(svgDataUrl('<svg a="1"/>')).toBe(
      'data:image/svg+xml;charset=utf-8,%3Csvg%20a%3D%221%22%2F%3E',
    );
  });
});
