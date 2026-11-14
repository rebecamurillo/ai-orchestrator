// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import FindingsList from '../../src/components/metrics/FindingsList';
import OriginDrawer from '../../src/components/metrics/OriginDrawer';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $originTarget, closeOrigin, openOrigin } from '../../src/stores/metric-ui';
import { entry, target, value } from './metrics-fixtures';

const source = { runId: 'r1', analysisId: 'an-1', tool: 'gitleaks', repository: '.' };
const sarif = {
  runs: [
    {
      results: [
        {
          ruleId: 'aws-key',
          locations: [
            { physicalLocation: { artifactLocation: { uri: 'a.py' }, region: { startLine: 4 } } },
          ],
        },
      ],
    },
  ],
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

async function open(findings?: (typeof source)[]) {
  render(createElement(OriginDrawer));
  await act(async () => {
    openOrigin(target({ value: value(), findings }));
  });
}

describe('the drawer findings', () => {
  it('lists each finding and offers the SARIF download', async () => {
    GET.mockResolvedValue({ data: sarif });
    await open([source]);
    expect(await screen.findByText('aws-key · a.py:4')).toBeTruthy();
    const link = screen.getByRole('link', { name: 'SARIF · gitleaks · .' });
    expect(link.getAttribute('href')).toBe('/api/runs/r1/analysis/an-1/sarif/gitleaks');
    expect(link.hasAttribute('download')).toBe(true);
    expect(GET).toHaveBeenCalledWith(
      '/runs/{run_id}/analysis/{analysis_id}/sarif/{tool}',
      expect.objectContaining({ parseAs: 'json' }),
    );
  });
  it('says so when the report is empty', async () => {
    GET.mockResolvedValue({ data: { runs: [] } });
    await open([source]);
    expect(await screen.findByText('no findings in this report')).toBeTruthy();
  });
  it('names the failed request', async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 404 } });
    await open([source]);
    expect(
      await screen.findByText('GET /api/runs/r1/analysis/an-1/sarif/gitleaks · 404'),
    ).toBeTruthy();
  });
  it('names a network failure', async () => {
    GET.mockRejectedValue(new Error('down'));
    await open([source]);
    expect(
      await screen.findByText('GET /api/runs/r1/analysis/an-1/sarif/gitleaks · network error'),
    ).toBeTruthy();
  });
  it('renders alone as a list with its link', async () => {
    GET.mockResolvedValue({ data: sarif });
    render(createElement(FindingsList, { source }));
    expect(await screen.findByText('aws-key · a.py:4')).toBeTruthy();
  });
  it('shows no findings section without findings', async () => {
    await open([]);
    expect(screen.queryByLabelText('findings')).toBeNull();
    expect($originTarget.get()).not.toBeNull();
  });
});
