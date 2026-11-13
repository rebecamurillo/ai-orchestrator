// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MetricsTab from '../../src/components/run/MetricsTab';
import OriginDrawer from '../../src/components/metrics/OriginDrawer';
import { resetCatalogue } from '../../src/stores/catalogue';
import { initMetricsTab } from '../../src/stores/metrics-tab';
import { $openHint, $originTarget, closeHint, closeOrigin } from '../../src/stores/metric-ui';
import { value, version } from './metrics-fixtures';
import { detailOf, glanceOf, seedCatalogue } from './run-metrics-fixtures';

const v = (metric_id: string, over = {}) => value({ metric_id, value_num: '2', ...over });
const items = () => [
  v('cost.gateway'),
  v('cost.gateway', { scope_type: 'epic', scope_key: 'epics[0]' }),
  v('cost.gateway', {
    scope_type: 'story',
    scope_key: 'epics[0].stories[0]',
    scope_label: '1-1',
  }),
  v('tokens.input', { value_num: null, missing: 'not recorded', unit: 'tokens' }),
];

function mount(props: Partial<Parameters<typeof MetricsTab>[0]> = {}, status = 'done') {
  const base: Parameters<typeof MetricsTab>[0] = {
    detail: detailOf(status),
    glance: glanceOf({
      metrics: { items: items(), latest: 1, run_id: '1', values_so_far: false, version: 1 },
    }),
    onSelectVersion: vi.fn(),
    onRetryMetrics: vi.fn(),
  };
  const ui = (p: typeof base) =>
    createElement('div', null, createElement(MetricsTab, p), createElement(OriginDrawer));
  const out = render(ui({ ...base, ...props }));
  return {
    ...out,
    again: (p: Partial<typeof base>) => out.rerender(ui({ ...base, ...props, ...p })),
  };
}

beforeEach(() => {
  seedCatalogue();
  initMetricsTab(String(Math.random()), { view: 'table', set: 'headline' });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
  closeHint();
  closeOrigin();
});

describe('MetricsTab', () => {
  it('shows heads, a collapsed epic and the missing word', () => {
    mount();
    expect(screen.getByText('scope')).toBeTruthy();
    expect(screen.getAllByText('label of cost.gateway').length).toBeGreaterThan(0);
    const caret = screen.getByRole('button', { name: 'expand epic 1' });
    expect(caret.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText(/story 1-1/)).toBeNull();
    expect(screen.getAllByText('not recorded').length).toBeGreaterThan(0);
    fireEvent.click(caret);
    expect(caret.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText(/epic 1 · story 1-1/)).toBeTruthy();
  });

  it('keeps drawer, hint, expanded row and selection across a poll', () => {
    const { again } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'expand epic 1' }));
    fireEvent.click(screen.getAllByRole('button', { name: /^my run label of cost\.gateway/ })[0]);
    const opened = $originTarget.get()?.value;
    expect(opened).toBeTruthy();
    fireEvent.click(
      screen.getAllByRole('button', { name: 'how label of tokens.input is calculated' })[0],
    );
    const hint = $openHint.get();
    expect(hint).not.toBeNull();
    again({
      glance: glanceOf({
        selected: 1,
        metrics: { items: items(), latest: 1, run_id: '1', values_so_far: false, version: 1 },
      }),
    });
    expect($originTarget.get()?.value.scope_key).toBe(opened?.scope_key);
    expect($openHint.get()).toBe(hint);
    expect(
      screen.getByRole('button', { name: 'expand epic 1' }).getAttribute('aria-expanded'),
    ).toBe('true');
    expect(screen.getByRole('button', { name: 'v1 latest' }).getAttribute('aria-pressed')).toBe(
      'true',
    );
  });

  it('switches the metric set and keeps CHART disabled', () => {
    mount();
    expect(screen.getByRole('button', { name: 'CHART' }).hasAttribute('disabled')).toBe(true);
    expect(screen.queryByText('TOKENS')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'ALL METRICS' }));
    expect(screen.getByText('ALL METRICS').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'TABLE' }));
  });

  it('prints the version line and passes a selection on', () => {
    const onSelectVersion = vi.fn();
    mount({
      onSelectVersion,
      glance: glanceOf({
        versions: [version(1), version(2)],
        selected: 1,
        metrics: { items: items(), latest: 2, run_id: '1', values_so_far: false, version: 1 },
      }),
    });
    expect(screen.getByText('showing v1 of 2 · latest is v2')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'v2 latest' }));
    expect(onSelectVersion).toHaveBeenCalledWith(2);
  });

  it('states a live Run', () => {
    mount(
      {
        glance: glanceOf({
          metrics: {
            items: items(),
            latest: null,
            run_id: '1',
            values_so_far: true,
            version: null,
          },
        }),
      },
      'running',
    );
    expect(
      screen.getByText('Run running · values so far, stored as each attempt ends'),
    ).toBeTruthy();
  });

  it('states an ended Run with no version, without a selector or tables', () => {
    mount({
      glance: glanceOf({
        versions: [],
        metrics: { items: [], latest: null, run_id: '1', values_so_far: false, version: null },
      }),
    });
    expect(screen.getByText(/^no result version · CALCULATE METRICS creates v1/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^v1/ })).toBeNull();
    expect(screen.queryByTestId('wf-metrics-scope')).toBeNull();
  });

  it('states a queued Run without a table', () => {
    mount({}, 'queued');
    expect(screen.getByText('no attempts yet')).toBeTruthy();
    expect(screen.queryByTestId('wf-metrics-scope')).toBeNull();
  });

  it('shows the failed request inside the panel and retries it', () => {
    const onRetryMetrics = vi.fn();
    mount({
      onRetryMetrics,
      glance: glanceOf({
        status: 'failed',
        failed: { path: '/api/runs/1/metrics', status: 500 },
        metrics: null,
      }),
    });
    expect(screen.getByTestId('fetch-failed').textContent).toContain('/api/runs/1/metrics');
    fireEvent.click(screen.getByTestId('fetch-retry'));
    expect(onRetryMetrics).toHaveBeenCalled();
    expect(screen.queryByTestId('wf-metrics-scope')).toBeNull();
  });
});
