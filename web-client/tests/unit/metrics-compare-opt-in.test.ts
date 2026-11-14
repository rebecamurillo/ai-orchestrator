// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import CompareGrid from '../../src/components/metrics/CompareGrid';
import { $catalogue } from '../../src/stores/catalogue';
import { $originTarget } from '../../src/stores/metric-ui';
import { entry } from './metrics-fixtures';
import { A, B, cell, comparePayload, metric } from './metrics-compare-fixtures';
import { FIRST, LINT, SECURITY, firstEntry, tierEntries } from './static-tier-fixtures';

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: Object.fromEntries(
      [entry('cost.gateway'), ...tierEntries(), firstEntry()].map((e) => [e.id, e]),
    ),
  });
});
afterEach(() => {
  cleanup();
  $originTarget.set(null);
});

const c = (id: string, source: string | null, num: string | null, over = {}) =>
  cell({ scope_key: 'run', unit: 'count', method_id: `${id}@1`, source, value_num: num, ...over });

function payload() {
  const p = comparePayload([A, B]);
  p.metrics = [
    metric('cost.gateway', [A, B]),
    metric(LINT, [A, B], {
      cells: { [A]: [c(LINT, null, '3')], [B]: [c(LINT, null, '4')] },
      tool_versions_differ: true,
      toolsets: {
        [A]: [{ tool: 'opengrep rules', version: 'aaaaaaaa' }],
        [B]: [{ tool: 'opengrep rules', version: 'bbbbbbbb' }],
      },
    }),
    metric(SECURITY, [A, B], {
      cells: { [A]: [c(SECURITY, 'high', '3'), c(SECURITY, 'fixed', '1')], [B]: [] },
    }),
    metric(FIRST, [A, B], { cells: { [A]: [c(FIRST, 'test_first', '4')], [B]: [] } }),
  ];
  p.diff_size = { [A]: '+1 −1 · 1 files', [B]: 'not run' };
  return p;
}

const mount = () =>
  render(
    createElement(CompareGrid, {
      payload: payload(),
      set: 'all',
      onRemove: () => {},
      onVersion: () => {},
    }),
  );

describe('Tier 2 and test-first in the comparison', () => {
  it('flags a rule pack difference by the opengrep rules tool', () => {
    mount();
    expect(screen.getByTestId(`compare-row-${LINT}`).textContent).toContain(
      '≠ tool versions differ: opengrep rules aaaaaaaa (Run 1) vs bbbbbbbb (Run 2)',
    );
  });

  it('never flags the test-first row nor offers a recalculation for it', () => {
    mount();
    const row = screen.getByTestId(`compare-row-${FIRST}`);
    expect(row.textContent).not.toContain('tool versions differ');
    const empty = screen.getByTestId(`compare-cell-${FIRST}-${B}`);
    expect(empty.textContent).toBe('—');
    expect(screen.getByTestId(`compare-cell-${LINT}-${B}`).textContent).not.toContain('not run');
  });

  it('keeps the recalculation offer for another code row of a not-run Run', () => {
    mount();
    expect(screen.getByTestId(`compare-cell-${SECURITY}-${B}`).textContent).toContain(
      'recalculate',
    );
  });

  it('writes severity words in a cell', () => {
    mount();
    const text = screen.getByTestId(`compare-cell-${SECURITY}-${A}`).textContent!;
    expect(text).toContain('3 possible high');
    expect(text).toContain('fixed 1');
  });
});
