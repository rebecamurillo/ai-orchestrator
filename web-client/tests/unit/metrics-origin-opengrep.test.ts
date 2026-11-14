// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import OpengrepFindings from '../../src/components/metrics/OpengrepFindings';
import OriginDrawer from '../../src/components/metrics/OriginDrawer';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { closeOrigin, openOrigin } from '../../src/stores/metric-ui';
import { entry, target, value } from './metrics-fixtures';
import { FINDING } from './static-tier-fixtures';

const source = {
  runId: 'r1',
  analysisId: 'an-app',
  tool: 'opengrep',
  repository: 'repos/app',
  kind: 'security' as const,
};

beforeEach(() => {
  GET.mockReset();
  $catalogue.set({ status: 'ready', entries: { 'cost.total': entry('cost.total') } });
});
afterEach(() => {
  cleanup();
  closeOrigin();
  resetCatalogue();
});

const answer = (items: unknown[]) =>
  GET.mockResolvedValue({ data: { analysis_id: 'an-app', items } });

async function open() {
  render(createElement(OriginDrawer));
  await act(async () => {
    openOrigin(target({ value: value(), findings: [source] }));
  });
}

describe('the opengrep findings in the drawer', () => {
  it('lists three new security findings with CWE and the SARIF link', async () => {
    answer([FINDING, FINDING, FINDING]);
    await open();
    expect(await screen.findAllByText('r.xss · a.py:4 · high · CWE-79')).toHaveLength(3);
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/analysis/{analysis_id}/findings', {
      params: { path: { run_id: 'r1', analysis_id: 'an-app' } },
    });
    const link = screen.getByRole('link', { name: 'SARIF · opengrep · repos/app' });
    expect(link.getAttribute('href')).toBe('/api/runs/r1/analysis/an-app/sarif/opengrep');
    expect(link.hasAttribute('download')).toBe(true);
  });

  it('leaves out unchanged, absent and the other kind', async () => {
    answer([
      FINDING,
      { ...FINDING, state: 'unchanged' },
      { ...FINDING, state: 'absent' },
      { ...FINDING, kind: 'bug', rule: 'r.bug' },
    ]);
    render(createElement(OpengrepFindings, { source }));
    expect(await screen.findAllByText(/r\.xss/)).toHaveLength(1);
    expect(screen.queryByText(/r\.bug/)).toBeNull();
  });

  it('says so when there is no new finding', async () => {
    answer([]);
    render(createElement(OpengrepFindings, { source }));
    expect(await screen.findByText('no new findings in this report')).toBeTruthy();
  });

  it('names a failed read and a network failure', async () => {
    GET.mockResolvedValueOnce({ data: undefined, response: { status: 404 } });
    const { unmount } = render(createElement(OpengrepFindings, { source }));
    expect(await screen.findByText('GET /runs/r1/analysis/an-app/findings · 404')).toBeTruthy();
    unmount();
    GET.mockRejectedValueOnce(new Error('down'));
    render(createElement(OpengrepFindings, { source }));
    expect(
      await screen.findByText('GET /runs/r1/analysis/an-app/findings · network error'),
    ).toBeTruthy();
  });
});
