import { beforeEach, describe, expect, it } from 'vitest';

import {
  $metricsTab,
  initMetricsTab,
  isExpanded,
  setSet,
  setView,
  toggleRow,
} from '../../src/stores/metrics-tab';

beforeEach(() => initMetricsTab('', { view: 'table', set: 'headline' }));

describe('metrics tab store', () => {
  it('initialises view and set', () => {
    initMetricsTab('r1', { view: 'chart', set: 'all' });
    expect($metricsTab.get()).toEqual({ runId: 'r1', view: 'chart', set: 'all', expanded: [] });
  });

  it('keeps expanded rows for the same run and resets them for another', () => {
    initMetricsTab('r1', { view: 'table', set: 'headline' });
    toggleRow('epic:epics[0]');
    initMetricsTab('r1', { view: 'table', set: 'all' });
    expect(isExpanded($metricsTab.get(), 'epic:epics[0]')).toBe(true);
    initMetricsTab('r2', { view: 'table', set: 'all' });
    expect($metricsTab.get().expanded).toEqual([]);
  });

  it('toggles a row open and closed', () => {
    toggleRow('a');
    expect(isExpanded($metricsTab.get(), 'a')).toBe(true);
    toggleRow('a');
    expect(isExpanded($metricsTab.get(), 'a')).toBe(false);
  });

  it('sets view and set', () => {
    setView('chart');
    setSet('all');
    expect($metricsTab.get()).toMatchObject({ view: 'chart', set: 'all' });
  });
});
