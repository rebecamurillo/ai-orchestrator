// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import MetricHint from '../../src/islands/MetricHint';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { closeHint } from '../../src/stores/metric-ui';
import { entry } from './metrics-fixtures';

afterEach(() => {
  cleanup();
  closeHint();
  resetCatalogue();
  GET.mockReset();
});

describe('MetricHint', () => {
  it('loads the catalogue and opens the spend.month_recorded hint on click', async () => {
    GET.mockResolvedValue({
      data: {
        items: [entry('spend.month_recorded', { label: 'recorded spend this month' })],
        next_cursor: null,
      },
    });
    render(createElement(MetricHint, { metricId: 'spend.month_recorded' }));
    const button = await screen.findByRole('button', {
      name: 'how recorded spend this month is calculated',
    });
    expect($catalogue.get().status).toBe('ready');
    fireEvent.click(button);
    expect(screen.getByText('how spend.month_recorded v2')).toBeTruthy();
  });
});
