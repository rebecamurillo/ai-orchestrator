/**
 * The standalone PNG export of a Run page chart: the same `RunChart` model the screen draws,
 * re-drawn as one 820 px wide SVG that carries its own font, then rasterised at 2×. Every
 * printed figure is `markFor`'s text of a value the chart row holds (RM-7).
 */
import fontSubset from '../../assets/fonts/JetBrainsMono-subset.woff2?inline';
import tokensCss from '../../styles/tokens.css?raw';
import type { components } from '../../api/schema';
import {
  EXPORT_BAR,
  EXPORT_FONT,
  EXPORT_FOOTER,
  EXPORT_GUTTER,
  EXPORT_LABEL_CHARS,
  EXPORT_PAD,
  EXPORT_PAIR_BAR,
  EXPORT_PAIR_GAP,
  EXPORT_SCALE,
  EXPORT_TITLE,
  EXPORT_VALUE_SPACE,
  EXPORT_WIDTH,
  GRID_OPACITY,
  HATCH,
  layoutRows,
  markFor,
  niceTicks,
  scale,
  secondsTicks,
  tickLabel,
  wrapLabel,
  type Mark,
} from './layout';
import { type ChartRow, type PairRow, type RunChart } from './run-charts';

type MetricValueOut = components['schemas']['MetricValueOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export type Background = 'transparent' | 'light' | 'dark';

export interface ExportMeta {
  entries: Record<string, CatalogueEntryOut>;
  project: string;
  runLabel: string;
  runId: string;
  version: number | null;
  subscription: boolean;
  date: string;
  notes?: string[];
  axisFromZero?: boolean;
}

export function tokenValue(css: string, name: string): string {
  const found = new RegExp(`${name}:\\s*([^;]+);`).exec(css);
  return found === null ? '' : found[1].trim();
}

const INK = tokenValue(tokensCss, '--color-chart-ink');
const DATA = [
  tokenValue(tokensCss, '--color-chart-data-1'),
  tokenValue(tokensCss, '--color-chart-data-2'),
];
const DARK_GROUND = tokenValue(tokensCss, '--color-bg');
// No token holds white and `tokens.test.ts` pins the token set.
const LIGHT_GROUND = '#ffffff';
const FAMILY = "'JetBrains Mono Export', monospace";
const PLOT = EXPORT_WIDTH - 2 * EXPORT_PAD - EXPORT_GUTTER - EXPORT_VALUE_SPACE;
const ORIGIN = EXPORT_PAD + EXPORT_GUTTER;
const LINE = 18;

export function unitWords(unit: string): string {
  if (unit === 'USD') return 'US dollars';
  if (unit === 'seconds') return 'hours and minutes';
  return unit;
}

export function sourceLine(meta: ExportMeta): string {
  const result = meta.version === null ? 'values so far' : `result v${meta.version}`;
  const plan = meta.subscription ? ' · list-price equivalent' : '';
  return `source: ai-orchestrator · project ${meta.project} · ${result}${plan} · exported ${meta.date}`;
}

function chartValues(chart: RunChart): MetricValueOut[] {
  const found: (MetricValueOut | null | undefined)[] =
    chart.kind === 'pair'
      ? chart.rows.flatMap((r) => [r.gateway, r.harness, r.gatewayShare, r.harnessShare])
      : chart.rows.map((r) => r.value);
  return found.filter((v): v is MetricValueOut => v != null && v.value_num !== null);
}

export function flagLine(chart: RunChart): string | null {
  const byMetric = new Map<string, Set<string>>();
  for (const v of chartValues(chart)) {
    const set = byMetric.get(v.metric_id) ?? new Set<string>();
    set.add(v.method_id);
    byMetric.set(v.metric_id, set);
  }
  const differing = [...byMetric.values()].filter((s) => s.size > 1);
  if (differing.length === 0) return null;
  const ids = [...new Set(differing.flatMap((s) => [...s]))].sort();
  return `≠ methods differ: ${ids.join(' · ')}`;
}

export function wrapText(text: string, fontSize: number, width: number): string[] {
  const limit = Math.floor(width / (fontSize * 0.6));
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(' ')) {
    if (line !== '' && `${line} ${word}`.length > limit) {
      lines.push(line);
      line = word;
    } else {
      line = line === '' ? word : `${line} ${word}`;
    }
  }
  lines.push(line);
  return lines;
}

const esc = (text: string): string =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const ESCAPED_FAMILY = esc(FAMILY);

function textEl(
  x: number | string,
  y: number | string,
  size: number,
  body: string,
  anchor?: string,
): string {
  const end = anchor ? ` text-anchor="${anchor}"` : '';
  return `<text x="${x}" y="${y}" font-family="${ESCAPED_FAMILY}" font-size="${size}" fill="${INK}"${end}>${body}</text>`;
}

const fixed = (n: number): string => String(Number(n.toFixed(2)));

interface Series {
  label: string;
  fill: string;
}

function seriesOf(chart: RunChart, meta: ExportMeta, hasShare: boolean): Series[] {
  const label = (id: string): string => meta.entries[id]?.label ?? id;
  if (chart.kind === 'bar') return [{ label: label(chart.metricIds[0]), fill: DATA[0] }];
  if (chart.kind === 'time') {
    const base = [{ label: label('time.machine'), fill: DATA[0] }];
    return meta.entries['time.parked']
      ? [...base, { label: label('time.parked'), fill: 'url(#hatch-2)' }]
      : base;
  }
  const base = [
    { label: label('cost.gateway'), fill: DATA[0] },
    { label: label('cost.harness'), fill: DATA[1] },
  ];
  return hasShare && meta.entries['cost.retries']
    ? [...base, { label: label('cost.retries'), fill: 'url(#hatch-1)' }]
    : base;
}

function patterns(): string {
  const period = HATCH.line * 2;
  const hatch = DATA.map(
    (colour, i) =>
      `<pattern id="hatch-${i + 1}" patternUnits="userSpaceOnUse" width="${period}" height="${period}" patternTransform="rotate(${HATCH.angle})"><line x1="0" y1="0" x2="0" y2="${period}" stroke="${colour}" stroke-width="${HATCH.line}"/></pattern>`,
  ).join('');
  const dots = `<pattern id="dots-1" patternUnits="userSpaceOnUse" width="5" height="5"><circle cx="2.5" cy="2.5" r="1" fill="${DATA[0]}"/></pattern>`;
  return `${hatch}${dots}`;
}

function markEls(
  mark: Mark,
  y: number,
  height: number,
  series: 0 | 1,
  opts: { share?: number; hatched?: boolean },
): string {
  const mid = y + height / 2 + 5;
  if (mark.kind === 'missing') return textEl(ORIGIN + 4, mid, EXPORT_FONT, esc(mark.word));
  const colour = DATA[series];
  const base = (w: number, x: number, extra: string): string =>
    `<rect data-mark="1" x="${fixed(x)}" y="${fixed(y)}" width="${fixed(w)}" height="${height}" ${extra}/>`;
  let body: string;
  if (mark.kind === 'partial') {
    body = base(mark.width, ORIGIN, `fill="none" stroke="${colour}" stroke-width="1"`);
  } else if (opts.hatched) {
    body = base(
      mark.width,
      ORIGIN,
      `fill="url(#hatch-${series + 1})" stroke="${colour}" stroke-width="1"`,
    );
  } else {
    const share = opts.share ?? 0;
    const solid = share > 0 ? Math.max(0, mark.width - share) : mark.width;
    body = base(solid, ORIGIN, `fill="${colour}"`);
    if (share > 0) body += base(share, ORIGIN + solid, `fill="url(#hatch-${series + 1})"`);
  }
  return body + textEl(fixed(ORIGIN + mark.width + 6), mid, EXPORT_FONT, esc(mark.label));
}

function numbers(chart: RunChart): number[] {
  const all =
    chart.kind === 'pair'
      ? chart.rows.flatMap((r) => [r.gateway, r.harness])
      : chart.rows.map((r) => r.value);
  return all.flatMap((v) => (v == null || v.value_num === null ? [] : [Number(v.value_num)]));
}

function rowsSvg(chart: RunChart, top: number): { svg: string; bottom: number } {
  const ticks =
    chart.kind === 'time'
      ? secondsTicks(Math.max(0, ...numbers(chart)))
      : niceTicks(Math.max(0, ...numbers(chart)));
  const maxTick = ticks.ticks[ticks.ticks.length - 1];
  const pair = chart.kind === 'pair';
  const span = 2 * EXPORT_PAIR_BAR + EXPORT_PAIR_GAP;
  const labels = chart.rows.map((r) => wrapLabel(r.label, undefined, EXPORT_LABEL_CHARS));
  const heights = labels.map((l) => Math.max((pair ? span : EXPORT_BAR) + 14, l.length * LINE + 8));
  const { tops, total } = layoutRows(heights);
  let out = '';
  for (const t of ticks.ticks) {
    const x = fixed(ORIGIN + scale(t, maxTick, PLOT));
    out += `<line data-grid="1" x1="${x}" x2="${x}" y1="${top}" y2="${top + total}" stroke="${INK}" stroke-opacity="${GRID_OPACITY}" stroke-width="1"/>`;
    out += textEl(
      x,
      top + total + 18,
      EXPORT_FONT,
      esc(tickLabel(t, ticks.step, chart.unit)),
      'middle',
    );
  }
  const share = (v: MetricValueOut | null | undefined): number =>
    v == null || v.value_num === null ? 0 : scale(Number(v.value_num), maxTick, PLOT);
  chart.rows.forEach((row, i) => {
    const y = top + tops[i];
    const mid = y + heights[i] / 2;
    const first = mid - ((labels[i].length - 1) * LINE) / 2 + 5;
    const tspans = labels[i]
      .map(
        (line, n) => `<tspan x="${ORIGIN - 8}" y="${fixed(first + n * LINE)}">${esc(line)}</tspan>`,
      )
      .join('');
    out += textEl(ORIGIN - 8, fixed(first), EXPORT_FONT, tspans, 'end');
    if (chart.kind === 'pair') {
      const r = row as PairRow;
      const y0 = y + (heights[i] - span) / 2;
      if (r.gatewayWord !== undefined) {
        out += textEl(ORIGIN + 4, fixed(y0 + EXPORT_PAIR_BAR), EXPORT_FONT, esc(r.gatewayWord));
      } else if (r.gateway) {
        out += markEls(markFor(r.gateway, maxTick, PLOT), y0, EXPORT_PAIR_BAR, 0, {
          share: share(r.gatewayShare),
        });
      }
      if (r.harness) {
        out += markEls(
          markFor(r.harness, maxTick, PLOT),
          y0 + EXPORT_PAIR_BAR + EXPORT_PAIR_GAP,
          EXPORT_PAIR_BAR,
          1,
          { share: share(r.harnessShare) },
        );
      }
    } else {
      const r = row as ChartRow;
      if (r.value !== null) {
        const hatched = r.texture === 'hatch';
        out += markEls(
          markFor(r.value, maxTick, PLOT),
          y + (heights[i] - EXPORT_BAR) / 2,
          EXPORT_BAR,
          hatched ? 1 : 0,
          {
            hatched,
          },
        );
      }
    }
  });
  return { svg: out, bottom: top + total + 26 };
}

export function exportSvg(
  chart: RunChart,
  meta: ExportMeta,
  background: Background = 'transparent',
): string {
  const inner = EXPORT_WIDTH - 2 * EXPORT_PAD;
  let y = EXPORT_PAD + EXPORT_TITLE;
  let body = '';
  const lines = (text: string, size: number, lead: number): void => {
    for (const line of wrapText(text, size, inner)) {
      body += textEl(EXPORT_PAD, y, size, esc(line));
      y += lead;
    }
  };
  body += textEl(EXPORT_PAD, y, EXPORT_TITLE, esc(chart.title));
  y += 24;
  const axis = meta.axisFromZero === false ? ' · axis does not start at zero' : '';
  lines(`${meta.runLabel} · ${meta.runId} · ${unitWords(chart.unit)}${axis}`, EXPORT_FONT, LINE);
  const shared = chart.kind === 'pair' && chart.rows.some((r) => r.gatewayShare || r.harnessShare);
  const key = seriesOf(chart, meta, shared);
  let x = EXPORT_PAD;
  y += 4;
  for (const s of key) {
    const width = 16 + s.label.length * EXPORT_FONT * 0.6 + 20;
    if (x + width > EXPORT_WIDTH - EXPORT_PAD && x > EXPORT_PAD) {
      x = EXPORT_PAD;
      y += LINE + 4;
    }
    body += `<rect data-key="1" x="${fixed(x)}" y="${y - 10}" width="10" height="10" fill="${s.fill}" stroke="${s.fill.startsWith('url') ? DATA[s.fill.endsWith('2)') ? 1 : 0] : 'none'}" stroke-width="1"/>`;
    body += textEl(fixed(x + 16), y, EXPORT_FONT, esc(s.label));
    x += width;
  }
  y += LINE + 4;
  const flag = flagLine(chart);
  if (flag !== null) {
    lines(flag, EXPORT_FONT, LINE);
  }
  y += 6;
  const rows = rowsSvg(chart, y);
  body += rows.svg;
  y = rows.bottom + 8;
  for (const note of meta.notes ?? []) lines(note, EXPORT_FONT, LINE);
  y += 4;
  lines(sourceLine(meta), EXPORT_FOOTER, LINE);
  const height = Math.ceil(y + EXPORT_PAD - LINE + 4);
  const ground =
    background === 'transparent'
      ? ''
      : `<rect x="0" y="0" width="${EXPORT_WIDTH}" height="${height}" fill="${background === 'light' ? LIGHT_GROUND : DARK_GROUND}"/>`;
  const style = `<style>@font-face { font-family: 'JetBrains Mono Export'; src: url(${fontSubset}) format('woff2'); }</style>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${EXPORT_WIDTH}" height="${height}" viewBox="0 0 ${EXPORT_WIDTH} ${height}"><defs>${style}${patterns()}</defs>${ground}${body}</svg>`;
}

export const svgDataUrl = (svg: string): string =>
  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

export function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[ ·]/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

export function exportFileName(
  project: string,
  runLabel: string,
  title: string,
  date: string,
): string {
  return `${slug(project)}-${slug(runLabel)}-${slug(title)}-${date}.png`;
}

export const today = (now: Date = new Date()): string => now.toISOString().slice(0, 10);

export interface PngEnv {
  loadImage(src: string): Promise<{ width: number; height: number; image: CanvasImageSource }>;
  createCanvas(): HTMLCanvasElement;
  save(blob: Blob, fileName: string): void;
}

export const browserEnv: PngEnv = {
  async loadImage(src) {
    const image = new Image();
    image.src = src;
    await image.decode();
    return { width: image.naturalWidth, height: image.naturalHeight, image };
  },
  createCanvas: () => document.createElement('canvas'),
  save(blob, fileName) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};

export async function writePng(
  svg: string,
  fileName: string,
  env: PngEnv = browserEnv,
): Promise<void> {
  let loaded: Awaited<ReturnType<PngEnv['loadImage']>>;
  try {
    loaded = await env.loadImage(svgDataUrl(svg));
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : String(error), { cause: error });
  }
  const canvas = env.createCanvas();
  canvas.width = loaded.width * EXPORT_SCALE;
  canvas.height = loaded.height * EXPORT_SCALE;
  const context = canvas.getContext('2d');
  if (context === null) throw new Error('canvas has no 2d context');
  context.scale(EXPORT_SCALE, EXPORT_SCALE);
  context.drawImage(loaded.image, 0, 0);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (blob === null) throw new Error('canvas produced no PNG');
  env.save(blob, fileName);
}
