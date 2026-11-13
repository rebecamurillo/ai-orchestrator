/** Run identity in the comparison charts, built from the payload's headers only (RM-7). */
import type { components } from '../../api/schema';
import { wrapLabel } from './layout';

type CompareRunHeaderOut = components['schemas']['CompareRunHeaderOut'];

export const FOLLOWING = (label: string): string => `following: ${label} · click again to stop`;
export const NOT_SPLIT_LINE =
  'not split by role: machine time, waiting on you, your interventions, budget, every static signal on the change';
export const NO_SUCH_STEP = 'no such step in this template';
export const SCROLL_RUNS = 15;

export interface RunName {
  runId: string;
  position: string;
  label: string;
  shortId: string;
  lines: string[];
}

const words = (label: string): string[] => label.split(/\s+/).filter((w) => w !== '');

export function sharedWords(labels: string[]): string[] {
  if (labels.length < 2) return [];
  const rest = labels.slice(1).map((l) => new Set(words(l)));
  return words(labels[0]).filter((w) => rest.every((set) => set.has(w)));
}

export function runNames(headers: CompareRunHeaderOut[]): RunName[] {
  const shared = new Set(sharedWords(headers.map((h) => h.label)));
  return headers.map((h, i) => {
    const own = words(h.label)
      .filter((w) => !shared.has(w))
      .join(' ');
    return {
      runId: h.run_id,
      position: `R${i + 1}`,
      label: h.label,
      shortId: h.short_id,
      lines: wrapLabel(own === '' ? h.label : own, h.short_id),
    };
  });
}

export function keyEntries(headers: CompareRunHeaderOut[]): string[] {
  return headers.map((h, i) => {
    const position = `R${i + 1}`;
    return h.label === position
      ? `${position} · ${h.short_id}`
      : `${position} · ${h.label} · ${h.short_id}`;
  });
}
