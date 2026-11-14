/**
 * The METRICS tab's view, metric set and expanded rows. They live here, not in component state,
 * so a poll re-render never collapses a row (EXPERIENCE §7); nothing is persisted.
 */
import { atom } from 'nanostores';

import type { MetricsSet, MetricsView } from '../lib/run/metrics-tab';

export interface MetricsTabState {
  runId: string;
  view: MetricsView;
  set: MetricsSet;
  expanded: string[];
}

export const $metricsTab = atom<MetricsTabState>({
  runId: '',
  view: 'table',
  set: 'headline',
  expanded: [],
});

export function initMetricsTab(runId: string, init: { view: MetricsView; set: MetricsSet }): void {
  const held = $metricsTab.get();
  $metricsTab.set({ ...init, runId, expanded: held.runId === runId ? held.expanded : [] });
}

export function setView(view: MetricsView): void {
  $metricsTab.set({ ...$metricsTab.get(), view });
}

export function setSet(set: MetricsSet): void {
  $metricsTab.set({ ...$metricsTab.get(), set });
}

export function toggleRow(id: string): void {
  const state = $metricsTab.get();
  const expanded = state.expanded.includes(id)
    ? state.expanded.filter((e) => e !== id)
    : [...state.expanded, id];
  $metricsTab.set({ ...state, expanded });
}

export function isExpanded(state: MetricsTabState, id: string): boolean {
  return state.expanded.includes(id);
}
