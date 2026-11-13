// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import RunCharts from '../../src/components/charts/RunCharts';
import MetricsTab from '../../src/components/run/MetricsTab';
import * as exporter from '../../src/lib/charts/export';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { initMetricsTab, setView } from '../../src/stores/metrics-tab';
import { metricsContext } from '../../src/components/run/MetricsTab';
import { entry, value } from './metrics-fixtures';
import { detailOf, glanceOf, seedCatalogue } from './run-metrics-fixtures';

vi.mock('../../src/lib/charts/export', async (original) => ({
  ...(await original<typeof import('../../src/lib/charts/export')>()),
  writePng: vi.fn(async () => undefined),
}));

const at = (metric_id: string, scope_type: string, scope_key: string, over = {}) =>
  value({ metric_id, scope_type, scope_key, value_num: '2', ...over });

const items = () => [
  ...['implement', 'senior'].flatMap((role) => [
    at('cost.gateway', 'role', role, { role }),
    at('cost.harness', 'role', role, { role }),
    at('tokens.output', 'role', role, { unit: 'tokens', role }),
  ]),
  at('time.machine', 'run', 'r', { unit: 'seconds', value_num: '5400' }),
];

const meta = {
  project: 'Fam Project',
  runLabel: 'my run',
  runId: '1',
  version: 2,
  subscription: false,
};

const mount = (over: Partial<Parameters<typeof RunCharts>[0]> = {}) => {
  const ctx = metricsContext(detailOf('done'), glanceOf(), false);
  const props = {
    entries: $catalogue.get().entries,
    items: items(),
    stepOrder: [],
    set: 'headline' as const,
    ctx,
    exportMeta: meta,
    ...over,
  };
  const out = render(createElement(RunCharts, props));
  return {
    ...out,
    again: (p: Partial<typeof props>) => out.rerender(createElement(RunCharts, { ...props, ...p })),
  };
};

const pressed = (group: string, name: string) =>
  within(screen.getByRole('group', { name: group }))
    .getByRole('button', { name })
    .getAttribute('aria-pressed');

beforeEach(() => {
  seedCatalogue(
    ['tokens.cache_write', 'time.machine', 'time.parked', 'cost.retries'].map((id) => entry(id)),
  );
  vi.mocked(exporter.writePng).mockClear();
});
afterEach(() => {
  cleanup();
  resetCatalogue();
  setView('table');
});

describe('PNG controls (story 6 AC8)', () => {
  it('shows both switches with their defaults', () => {
    mount();
    expect(pressed('PNG background', 'TRANSPARENT')).toBe('true');
    expect(pressed('PNG background', 'LIGHT')).toBe('false');
    expect(pressed('PNG background', 'DARK')).toBe('false');
    expect(pressed('preview PNG ink on', 'SCREEN')).toBe('true');
    expect(pressed('preview PNG ink on', 'DARK PAGE')).toBe('false');
    expect(pressed('preview PNG ink on', 'LIGHT PAGE')).toBe('false');
  });

  it('gives each chart one PNG button outside its figure', () => {
    mount();
    const figures = screen.getAllByRole('figure');
    const pngs = screen
      .getAllByRole('button', { name: /^PNG / })
      .filter((b) => b.textContent === 'PNG');
    expect(pngs).toHaveLength(figures.length);
    for (const figure of figures) {
      const title = figure.getAttribute('aria-label') as string;
      const button = screen.getByRole('button', { name: `PNG ${title}` });
      expect(figure.contains(button)).toBe(false);
    }
  });

  it('writes the chosen background and the file name on click', async () => {
    mount();
    fireEvent.click(
      within(screen.getByRole('group', { name: 'PNG background' })).getByRole('button', {
        name: 'DARK',
      }),
    );
    expect(pressed('PNG background', 'DARK')).toBe('true');
    expect(pressed('PNG background', 'TRANSPARENT')).toBe('false');
    fireEvent.click(screen.getByRole('button', { name: 'PNG cost by role' }));
    const [svg, name] = vi.mocked(exporter.writePng).mock.calls[0];
    expect(svg).toContain('fill="#0b0d0e"');
    expect(name).toBe(`fam-project-my-run-cost-by-role-${exporter.today()}.png`);
    expect(svg).toContain('cost by role');
  });

  it('replaces the figures with the export drawing on a page ground and back', () => {
    mount();
    const figures = screen.getAllByRole('figure').length;
    fireEvent.click(screen.getByRole('button', { name: 'DARK PAGE' }));
    expect(screen.queryAllByRole('figure')).toHaveLength(0);
    const imgs = screen.getAllByRole('img');
    expect(imgs).toHaveLength(figures);
    expect(imgs.map((i) => i.getAttribute('alt'))).toContain('cost by role');
    expect(imgs[0].getAttribute('src')).toMatch(/^data:image\/svg\+xml/);
    expect(decodeURIComponent(imgs[0].getAttribute('src') as string)).toContain('#0b0d0e');
    fireEvent.click(screen.getByRole('button', { name: 'LIGHT PAGE' }));
    expect(
      decodeURIComponent(screen.getAllByRole('img')[0].getAttribute('src') as string),
    ).toContain('#ffffff');
    expect(screen.getAllByRole('button', { name: /^PNG / }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'SCREEN' }));
    expect(screen.getAllByRole('figure')).toHaveLength(figures);
    expect(screen.queryAllByRole('img')).toHaveLength(0);
  });

  it('keeps both choices across a poll re-render', () => {
    const { again } = mount();
    fireEvent.click(screen.getByRole('button', { name: 'LIGHT' }));
    fireEvent.click(screen.getByRole('button', { name: 'DARK PAGE' }));
    again({ items: items() });
    expect(pressed('PNG background', 'LIGHT')).toBe('true');
    expect(pressed('preview PNG ink on', 'DARK PAGE')).toBe('true');
  });

  it('shows the reason beside the switches when the write is rejected', async () => {
    vi.mocked(exporter.writePng).mockRejectedValueOnce(new Error('decode failed'));
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'PNG cost by role' }));
    await waitFor(() => expect(screen.getByText('PNG not written · decode failed')).toBeTruthy());
  });

  it('renders no controls without exportMeta', () => {
    mount({ exportMeta: undefined });
    expect(screen.queryByRole('group', { name: 'PNG background' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^PNG / })).toBeNull();
  });
});

describe('MetricsTab passes the Run to the export', () => {
  it('names the file from the project and the Run label', () => {
    initMetricsTab('1', { view: 'chart', set: 'headline' });
    render(
      createElement(MetricsTab, {
        detail: detailOf('done'),
        glance: glanceOf({
          metrics: { items: items(), latest: 1, run_id: '1', values_so_far: true, version: 1 },
        }),
        onSelectVersion: vi.fn(),
        onRetryMetrics: vi.fn(),
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'PNG cost by role' }));
    const [svg, name] = vi.mocked(exporter.writePng).mock.calls[0];
    expect(name).toMatch(/^familio-.*-cost-by-role-\d{4}-\d{2}-\d{2}\.png$/);
    expect(svg).toContain('project familio · result v1');
    expect(svg).toContain('Run running');
  });
});
