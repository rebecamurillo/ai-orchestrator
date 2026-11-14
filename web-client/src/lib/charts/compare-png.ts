/**
 * The standalone PNG of a comparison chart: the `CompareChart` model the screen draws, as one
 * 820 px SVG on `exportSvg`'s layout. It takes no follow state, so a followed Run never reaches
 * a file (RM-7: every printed figure is a payload value through `formatValue`).
 */
import type { components } from '../../api/schema';
import { NO_CELL } from '../metrics/compare';
import { formatValue } from '../metrics/format';
import type { CompareChart, CompareMark } from './compare-charts';
import { keyEntries } from './compare-runs';
import {
  DATA,
  INK,
  browserEnv,
  esc,
  exportFileName,
  fixed,
  markEls,
  textEl,
  wrapSvg,
  wrapText,
  writePng,
  type Background,
  type PngEnv,
} from './export';
import {
  EXPORT_BAR,
  EXPORT_FONT,
  EXPORT_FOOTER,
  EXPORT_GUTTER,
  EXPORT_LABEL_CHARS,
  EXPORT_PAD,
  EXPORT_PAIR_BAR,
  EXPORT_PAIR_GAP,
  EXPORT_TITLE,
  EXPORT_VALUE_SPACE,
  EXPORT_WIDTH,
  GRID_OPACITY,
  layoutRows,
  markFor,
  niceTicks,
  scale,
  secondsTicks,
  tickLabel,
  wrapLabel,
  type Mark,
  type Ticks,
} from './layout';
import { rangeTicks } from './compare-charts';

type CompareRunHeaderOut = components['schemas']['CompareRunHeaderOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export interface CompareExportMeta {
  entries: Record<string, CatalogueEntryOut>;
  project: string;
  headers: CompareRunHeaderOut[];
  date: string;
}

const PLOT = EXPORT_WIDTH - 2 * EXPORT_PAD - EXPORT_GUTTER - EXPORT_VALUE_SPACE;
const ORIGIN = EXPORT_PAD + EXPORT_GUTTER;
const LINE = 18;
const DOT = 5;

export function compareSourceLine(meta: CompareExportMeta): string {
  const versions = meta.headers
    .map((h) => (h.selected_version === null ? 'values so far' : `v${h.selected_version}`))
    .join(', ');
  const plan = meta.headers.some((h) => h.subscription === true) ? ' · list-price equivalent' : '';
  return `source: ai-orchestrator · project ${meta.project} · result ${versions} per Run${plan} · exported ${meta.date}`;
}

export const markWord = (mark: CompareMark): string | null => {
  if (mark.word !== undefined) return mark.word;
  return mark.value === null || mark.value.value_num === null
    ? null
    : formatValue(mark.value.value_num, mark.value.unit);
};

/** The geometry of a bar mark on a zero-based axis; null when the mark is empty. */
export function drawn(mark: CompareMark, maxTick: number, plot: number): Mark | null {
  if (mark.word !== undefined) return { kind: 'missing', width: 0, label: '', word: mark.word };
  if (mark.value === null) return null;
  const raw = markFor(mark.value, maxTick, plot);
  const found =
    mark.rate !== undefined && raw.kind === 'bar'
      ? { ...raw, label: `${raw.label} · ${mark.rate}` }
      : raw;
  if (mark.outline && found.kind !== 'missing')
    return { ...found, kind: 'partial', label: `${found.label} · partial` };
  return mark.dotted !== undefined && found.kind === 'bar'
    ? { ...found, label: `${found.label} · ${mark.dotted}` }
    : found;
}

/** The two figures of a dot row as printed: a missing one keeps its word beside the other. */
export const dotWords = (g: CompareMark, h: CompareMark | undefined): string =>
  [g, h ?? { value: null }].map((m) => markWord(m) ?? NO_CELL).join(' · ');

export function chartNumbers(chart: CompareChart): number[] {
  return chart.groups.flatMap((g) =>
    g.rows.flatMap((r) =>
      r.marks.flatMap((m) =>
        m?.value == null || m.value.value_num === null ? [] : [Number(m.value.value_num)],
      ),
    ),
  );
}

export function chartTicks(chart: CompareChart): Ticks & { origin: number } {
  const nums = chartNumbers(chart);
  if (!chart.axisFromZero && nums.length > 0)
    return rangeTicks(Math.min(...nums), Math.max(...nums));
  const top = Math.max(0, ...nums);
  const ticks = chart.unit === 'seconds' ? secondsTicks(top) : niceTicks(top);
  return { ...ticks, origin: 0 };
}

const hasDots = (chart: CompareChart): boolean =>
  chart.groups.some((g) => g.rows.some((r) => r.marks[0]?.dotted !== undefined));
const hasShare = (chart: CompareChart): boolean =>
  chart.groups.some((g) => g.rows.some((r) => r.marks[0]?.share != null));

function seriesKey(
  chart: CompareChart,
  meta: CompareExportMeta,
): { label: string; fill: string }[] {
  const label = (id: string): string => meta.entries[id]?.label ?? id;
  const [a, b] = chart.metricIds;
  const out = [{ label: label(a), fill: DATA[0] }];
  if (chart.kind === 'dot') out.push({ label: label(b), fill: 'none' });
  else if (b !== undefined)
    out.push({ label: label(b), fill: chart.second ? 'url(#hatch-2)' : DATA[1] });
  if (hasShare(chart)) out.push({ label: label('process.retries'), fill: 'url(#hatch-1)' });
  if (hasDots(chart)) out.push({ label: 'other method', fill: 'url(#dots-1)' });
  return out;
}

function barEls(
  mark: Mark,
  y: number,
  height: number,
  series: 0 | 1,
  m: CompareMark,
  share: number,
): string {
  if (mark.kind === 'bar' && m.dotted !== undefined) {
    const body = `<rect data-mark="1" x="${ORIGIN}" y="${fixed(y)}" width="${fixed(mark.width)}" height="${height}" fill="url(#dots-1)" stroke="${DATA[series]}" stroke-width="1"/>`;
    return (
      body +
      textEl(fixed(ORIGIN + mark.width + 6), y + height / 2 + 5, EXPORT_FONT, esc(mark.label))
    );
  }
  return markEls(mark, y, height, series, { share, hatched: false });
}

export function compareSvg(
  chart: CompareChart,
  meta: CompareExportMeta,
  background: Background = 'transparent',
): string {
  const inner = EXPORT_WIDTH - 2 * EXPORT_PAD;
  let y = EXPORT_PAD + EXPORT_TITLE;
  let body = textEl(EXPORT_PAD, y, EXPORT_TITLE, esc(chart.title));
  y += 24;
  const lines = (text: string, size: number): void => {
    for (const line of wrapText(text, size, inner)) {
      body += textEl(EXPORT_PAD, y, size, esc(line));
      y += LINE;
    }
  };
  for (const line of chart.context) lines(line, EXPORT_FONT);
  if (chart.groups[0]?.name != null)
    for (const line of keyEntries(meta.headers)) lines(line, EXPORT_FONT);
  y += 4;
  let x = EXPORT_PAD;
  for (const s of seriesKey(chart, meta)) {
    const width = 16 + s.label.length * EXPORT_FONT * 0.6 + 20;
    if (x + width > EXPORT_WIDTH - EXPORT_PAD && x > EXPORT_PAD) {
      x = EXPORT_PAD;
      y += LINE + 4;
    }
    const open = s.fill === 'none' || s.fill.startsWith('url');
    const stroke = open ? (s.fill.endsWith('2)') || s.fill === 'none' ? DATA[1] : DATA[0]) : 'none';
    body += `<rect data-key="1" x="${fixed(x)}" y="${y - 10}" width="10" height="10" fill="${s.fill}" stroke="${stroke}" stroke-width="1"/>`;
    body += textEl(fixed(x + 16), y, EXPORT_FONT, esc(s.label));
    x += width;
  }
  y += LINE + 4;
  if (chart.flag !== null) lines(chart.flag, EXPORT_FONT);
  y += 6;

  const ticks = chartTicks(chart);
  const maxTick = ticks.ticks[ticks.ticks.length - 1];
  const span = maxTick - ticks.origin;
  const pair = chart.kind === 'pair';
  const pairSpan = 2 * EXPORT_PAIR_BAR + EXPORT_PAIR_GAP;
  const items: {
    head?: string;
    row?: CompareChart['groups'][number]['rows'][number];
    h: number;
    labels: string[];
  }[] = [];
  for (const g of chart.groups) {
    if (g.name !== null) items.push({ head: g.name, h: LINE + 6, labels: [] });
    for (const row of g.rows) {
      const labels = row.name.flatMap((n) => wrapLabel(n, undefined, EXPORT_LABEL_CHARS));
      items.push({
        row,
        labels,
        h: Math.max((pair ? pairSpan : EXPORT_BAR) + 14, labels.length * LINE + 8),
      });
    }
  }
  const { tops, total } = layoutRows(items.map((i) => i.h));
  const px = (t: number): number => ORIGIN + scale(t - ticks.origin, span, PLOT);
  for (const t of ticks.ticks) {
    body += `<line data-grid="1" x1="${fixed(px(t))}" x2="${fixed(px(t))}" y1="${y}" y2="${y + total}" stroke="${INK}" stroke-opacity="${GRID_OPACITY}" stroke-width="1"/>`;
    body += textEl(
      fixed(px(t)),
      y + total + 18,
      EXPORT_FONT,
      esc(tickLabel(t, ticks.step, chart.unit)),
      'middle',
    );
  }
  items.forEach((item, i) => {
    const top = y + tops[i];
    if (item.head !== undefined) {
      body += textEl(EXPORT_PAD, fixed(top + LINE), EXPORT_FONT, esc(item.head));
      return;
    }
    const row = item.row!;
    const mid = top + item.h / 2;
    const first = mid - ((item.labels.length - 1) * LINE) / 2 + 5;
    const tspans = item.labels
      .map(
        (line, n) => `<tspan x="${ORIGIN - 8}" y="${fixed(first + n * LINE)}">${esc(line)}</tspan>`,
      )
      .join('');
    body += textEl(ORIGIN - 8, fixed(first), EXPORT_FONT, tspans, 'end');
    const [m0, m1] = row.marks;
    if (chart.kind === 'dot') {
      const g = m0.value?.value_num == null ? null : Number(m0.value.value_num);
      const h = m1?.value?.value_num == null ? null : Number(m1.value.value_num);
      if (g === null || h === null) {
        body += textEl(ORIGIN + 4, fixed(mid + 5), EXPORT_FONT, esc(dotWords(m0, m1)));
        return;
      }
      const xg = fixed(px(g));
      const xh = fixed(px(h));
      body += `<line data-mark="1" x1="${xg}" x2="${xh}" y1="${fixed(mid)}" y2="${fixed(mid)}" stroke="${INK}" stroke-width="1"/>`;
      body += `<circle data-mark="1" data-series="gateway" cx="${xg}" cy="${fixed(mid)}" r="${DOT}" fill="${DATA[0]}"/>`;
      body += `<circle data-mark="1" data-series="harness" cx="${xh}" cy="${fixed(mid)}" r="${DOT}" fill="none" stroke="${DATA[1]}" stroke-width="1"/>`;
      const label = `${markWord(m0)} · ${markWord(m1!)}`;
      body += textEl(
        fixed(Math.max(px(g), px(h)) + DOT + 6),
        fixed(mid + 5),
        EXPORT_FONT,
        esc(label),
      );
      return;
    }
    const marks = pair ? [m0, m1!] : [m0];
    marks.forEach((m, k) => {
      const y0 = pair
        ? top + (item.h - pairSpan) / 2 + k * (EXPORT_PAIR_BAR + EXPORT_PAIR_GAP)
        : top + (item.h - EXPORT_BAR) / 2;
      const found = drawn(m, maxTick, PLOT);
      if (found === null) return;
      const share =
        m.share?.value_num == null ? 0 : scale(Number(m.share.value_num), maxTick, PLOT);
      const hatched = pair && k === 1 && chart.second === 'hatch';
      body += hatched
        ? markEls(found, y0, EXPORT_PAIR_BAR, 1, { hatched })
        : barEls(found, y0, pair ? EXPORT_PAIR_BAR : EXPORT_BAR, k === 1 ? 1 : 0, m, share);
    });
  });
  y += total + 26 + 8;
  y += 4;
  lines(compareSourceLine(meta), EXPORT_FOOTER);
  const height = Math.ceil(y + EXPORT_PAD - LINE + 4);
  return wrapSvg(body, height, background);
}

export async function pngAll(
  charts: CompareChart[],
  meta: CompareExportMeta,
  background: Background,
  env: PngEnv = browserEnv,
): Promise<void> {
  for (const chart of charts) {
    await writePng(
      compareSvg(chart, meta, background),
      exportFileName(meta.project, 'compare', chart.title, meta.date),
      env,
    );
  }
}
