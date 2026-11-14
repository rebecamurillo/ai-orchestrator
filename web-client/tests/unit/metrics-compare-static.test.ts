// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import CompareStaticRows from '../../src/components/metrics/CompareStaticRows';
import CompareGrid from '../../src/components/metrics/CompareGrid';
import { $catalogue } from '../../src/stores/catalogue';
import { $originTarget } from '../../src/stores/metric-ui';
import { entry } from './metrics-fixtures';
import { A, B, cell, comparePayload, metric } from './metrics-compare-fixtures';
import { DUP, SUPP } from './static-fixtures';

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: {
      'cost.gateway': entry('cost.gateway'),
      [DUP]: entry(DUP, { group: 'code', unit: 'count' }),
      [SUPP]: entry(SUPP, { group: 'code', unit: 'count' }),
    },
  });
});
afterEach(() => {
  cleanup();
  $originTarget.set(null);
});

const codeCell = (run: string, source: string | null, over = {}) =>
  cell({
    scope_key: 'run',
    unit: 'count',
    method_id: `${DUP}@1`,
    source,
    ...over,
    value_num: over && 'value_num' in over ? (over as { value_num: string | null }).value_num : '7',
  });

function payload(differ: boolean, analysedB = true) {
  const p = comparePayload([A, B]);
  p.metrics = [
    metric('cost.gateway', [A, B]),
    metric(DUP, [A, B], {
      cells: {
        [A]: [codeCell(A, 'production'), codeCell(A, 'per_100', { value_num: '0.95' })],
        [B]: analysedB
          ? [
              codeCell(B, 'production', { value_num: '9' }),
              codeCell(B, 'per_100', { value_num: null, missing: 'raw only' }),
              codeCell(B, 'small_change', { value_num: null, missing: 'small change' }),
            ]
          : [],
      },
      tool_versions_differ: differ,
      toolsets: differ
        ? {
            [A]: [{ tool: 'jscpd', version: '4.0.5' }],
            [B]: [{ tool: 'jscpd', version: '4.1.0' }],
          }
        : {},
    }),
  ];
  p.diff_size = { [A]: '+40 −2 · 3 files', [B]: analysedB ? '+1 −1 · 1 files' : 'not run' };
  return p;
}

const mount = (p = payload(true), set: 'headline' | 'all' = 'all') =>
  render(createElement(CompareGrid, { payload: p, set, onRemove: () => {}, onVersion: () => {} }));

describe('comparison static rows', () => {
  it('renders alone as rows of a table', () => {
    const p = payload(true);
    render(
      createElement(
        'table',
        null,
        createElement(
          'tbody',
          null,
          createElement(CompareStaticRows, {
            payload: p,
            entries: $catalogue.get().entries,
            set: 'all',
          }),
        ),
      ),
    );
    expect(screen.getByTestId(`compare-row-${DUP}`)).toBeTruthy();
  });
  it('flags the differing tool versions and prints each Run’s own', () => {
    mount();
    const row = screen.getByTestId(`compare-row-${DUP}`);
    expect(row.textContent).toContain(
      '≠ tool versions differ: jscpd 4.0.5 (Run 1) vs 4.1.0 (Run 2)',
    );
    expect(screen.getByTestId(`compare-cell-${DUP}-${A}`).textContent).toContain('jscpd 4.0.5');
    expect(screen.getByTestId(`compare-cell-${DUP}-${B}`).textContent).toContain('jscpd 4.1.0');
    expect(screen.getByTestId(`compare-cell-${DUP}-${B}`).textContent).toContain('raw only');
    expect(screen.getByTestId(`compare-cell-${DUP}-${B}`).textContent).toContain('small change');
    expect(screen.getByTestId(`compare-cell-${DUP}-${A}`).textContent).toContain(' · ');
  });
  it('prints no flag when the toolsets agree', () => {
    mount(payload(false));
    expect(screen.getByTestId(`compare-row-${DUP}`).textContent).not.toContain(
      'tool versions differ',
    );
  });
  it('reads not run with a recalculate link for a Run with no analysis', () => {
    mount(payload(false, false));
    const cellB = screen.getByTestId(`compare-cell-${DUP}-${B}`);
    expect(cellB.textContent).toContain('not run');
    expect(within(cellB).getByRole('link', { name: 'recalculate' }).getAttribute('href')).toBe(
      `/workflows/${B}?tab=metrics&recalculate=1`,
    );
  });
  it('prints a dash for a missing cell of an analysed Run', () => {
    const p = payload(false, false);
    p.diff_size[B] = '+1 −1 · 1 files';
    mount(p);
    expect(screen.getByTestId(`compare-cell-${DUP}-${B}`).textContent).toBe('—');
  });
  it('labels several raw sources and keeps the headline filter', () => {
    const p = payload(false);
    p.metrics[1].cells[A] = [codeCell(A, 'production'), codeCell(A, 'test', { value_num: '2' })];
    mount(p);
    expect(screen.getByTestId(`compare-cell-${DUP}-${A}`).textContent).toContain(' / ');
    cleanup();
    mount(p, 'headline');
    expect(screen.queryByTestId(`compare-row-${SUPP}`)).toBeNull();
  });
});
