/**
 * Pure chart geometry and wording. A mark's text is the table cell's text (`formatValue`,
 * `stateWords`); nothing here sums, subtracts or divides metric values — only geometry.
 */
import type { components } from '../../api/schema';
import { formatValue } from '../metrics/format';

type MetricValueOut = components['schemas']['MetricValueOut'];

export const CHART_WIDTH = 640;
export const GUTTER = 230;
export const VALUE_SPACE = 150;
export const BAR = 12;
export const PAIR_BAR = 8;
export const PAIR_GAP = 2;
export const ZERO_TICK = 2;
export const FONT = 12;
export const HATCH = { angle: 45, line: 2.4 } as const;
export const GRID_OPACITY = 0.35;
const PLOT = CHART_WIDTH - GUTTER - VALUE_SPACE;
const LINE = 14;

export interface Ticks {
  step: number;
  ticks: number[];
}

export function decimals(step: number): number {
  let d = 0;
  while (d < 10 && Math.abs(Math.round(step * 10 ** d) - step * 10 ** d) > 1e-9) d += 1;
  return d;
}

export function niceTicks(max: number): Ticks {
  if (max <= 0) return { step: 1, ticks: [0, 1] };
  const raw = max / 3;
  const base = 10 ** Math.floor(Math.log10(raw) + 1e-9);
  const step = [1, 2, 2.5, 5, 10]
    .map((m) => Number((m * base).toPrecision(12)))
    .find((s) => s >= raw * (1 - 1e-9)) as number;
  const count = Math.ceil(max / step - 1e-9);
  const places = decimals(step);
  const ticks = Array.from({ length: count + 1 }, (_, i) => Number((i * step).toFixed(places)));
  return { step, ticks };
}

/** `formatValue` prints whole minutes, so a minute step must be whole: below 1 → 1, 2.5 → 5. */
export function secondsTicks(max: number): Ticks {
  const minutes = max / 60;
  const nice = niceTicks(minutes);
  if (Number.isInteger(nice.step)) {
    return { step: nice.step * 60, ticks: nice.ticks.map((t) => t * 60) };
  }
  const step = nice.step < 1 ? 1 : 5;
  const count = Math.max(1, Math.ceil(minutes / step - 1e-9));
  return { step: step * 60, ticks: Array.from({ length: count + 1 }, (_, i) => i * step * 60) };
}

export function tickLabel(value: number, step: number, unit: string): string {
  if (unit === 'seconds') return formatValue(String(value), 'seconds');
  const places = decimals(step);
  const text = new Intl.NumberFormat('en-US', { maximumFractionDigits: places }).format(value);
  return unit === 'USD' ? `$${text}` : text;
}

export function scale(value: number, maxTick: number): number {
  return maxTick <= 0 ? 0 : (value / maxTick) * PLOT;
}

export function wrapLabel(text: string, shortId?: string, max = 28): string[] {
  const lines: string[] = [];
  if (text.length <= max) {
    lines.push(text);
  } else {
    const head = text.slice(0, max + 1);
    const dot = head.lastIndexOf(' · ');
    const cut = dot > 0 ? dot : head.lastIndexOf(' ');
    const at = cut > 0 ? cut : max;
    lines.push(text.slice(0, at).trimEnd());
    const rest = text.slice(at).replace(/^( · | )/, '');
    lines.push(rest.length > max ? `${rest.slice(0, max - 1)}…` : rest);
  }
  if (shortId) lines.push(shortId);
  return lines;
}

export interface Mark {
  kind: 'bar' | 'zero' | 'partial' | 'missing';
  width: number;
  label: string;
  word: string;
}

export function markFor(value: MetricValueOut, maxTick: number): Mark {
  if (value.value_num === null) {
    return { kind: 'missing', width: 0, label: '', word: value.missing ?? '' };
  }
  const n = Number(value.value_num);
  if (n === 0) return { kind: 'zero', width: ZERO_TICK, label: '0', word: '' };
  const partial = value.partial_n !== null && value.partial_m !== null;
  let label = formatValue(value.value_num, value.unit);
  if (partial) label += ` · partial · ${value.partial_n} of ${value.partial_m} attempts`;
  if (value.carried_from !== null) label += ` from v${value.carried_from}`;
  return { kind: partial ? 'partial' : 'bar', width: scale(n, maxTick), label, word: '' };
}

export type Texture = 'solid' | 'hatch' | 'dots';

export function textureFor(opts: { share: boolean; otherMethod: boolean }): Texture {
  if (opts.otherMethod) return 'dots';
  return opts.share ? 'hatch' : 'solid';
}

export function rowHeight(kind: 'single' | 'pair', lines: number): number {
  const marks = kind === 'pair' ? 2 * PAIR_BAR + PAIR_GAP + 14 : BAR + 14;
  return Math.max(marks, lines * LINE + 8);
}

export function layoutRows(heights: readonly number[]): { tops: number[]; total: number } {
  const tops: number[] = [];
  let total = 0;
  for (const h of heights) {
    tops.push(total);
    total += h;
  }
  return { tops, total };
}
