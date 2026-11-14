// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it } from 'vitest';

import FigurePair from '../../src/components/metrics/FigurePair';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { entry, target, value } from './metrics-fixtures';

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: { 'cost.gateway': entry('cost.gateway'), 'cost.harness': entry('cost.harness') },
  });
});

afterEach(() => {
  cleanup();
  resetCatalogue();
});

const props = {
  gatewayMetricId: 'cost.gateway',
  harnessMetricId: 'cost.harness',
};

it('shows GATEWAY then HARNESS, each with a hint control, and list-price equivalent once', () => {
  const { container } = render(
    createElement(FigurePair, {
      ...props,
      subscription: true,
      gateway: target({ value: value({ metric_id: 'cost.gateway' }) }),
      harness: target({ value: value({ metric_id: 'cost.harness' }) }),
    }),
  );
  const heads = Array.from(container.querySelectorAll('.metric-figure-head'));
  expect(heads.map((h) => h.textContent!.replace('i', '').trim())).toEqual(['GATEWAY', 'HARNESS']);
  expect(heads.every((h) => h.querySelector('button.metric-hint-control'))).toBe(true);
  expect(container.textContent!.match(/list-price equivalent/g)).toHaveLength(1);
  expect(container.querySelectorAll('.metric-value-cell')).toHaveLength(2);
});

it('reads not available for a source with no value, and omits the note off subscription', () => {
  const { container } = render(
    createElement(FigurePair, { ...props, subscription: false, gateway: null, harness: null }),
  );
  expect(container.querySelectorAll('.metric-missing')).toHaveLength(2);
  expect(container.textContent).toContain('not available');
  expect(container.textContent).not.toContain('list-price equivalent');
});
