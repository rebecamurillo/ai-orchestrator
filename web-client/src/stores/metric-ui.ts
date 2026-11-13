/**
 * Open hint and open origin drawer live here, not in component state, so a poll re-render
 * never closes either (EXPERIENCE §7).
 */
import { atom } from 'nanostores';

import type { components } from '../api/schema';

type MetricValueOut = components['schemas']['MetricValueOut'];
type ResultVersionOut = components['schemas']['ResultVersionOut'];

export interface OriginTarget {
  value: MetricValueOut;
  runLabel: string;
  version: ResultVersionOut | null;
  latest: number | null;
  projectName?: string;
  spans?: { models?: number; repositories?: number; harnesses?: number };
  aggregate?: { n: number; noun: string };
  subscription?: boolean;
  onBreakdown?: () => void;
}

export const $openHint = atom<string | null>(null);
export const $originTarget = atom<OriginTarget | null>(null);

export function openHint(key: string): void {
  $openHint.set(key);
}

export function closeHint(): void {
  $openHint.set(null);
}

export function openOrigin(target: OriginTarget): void {
  $originTarget.set(target);
}

export function closeOrigin(): void {
  $originTarget.set(null);
}
