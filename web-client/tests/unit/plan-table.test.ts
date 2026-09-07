/**
 * `PlanTable.tsx` (4.13) holds no state and runs no effect, so — like `Diagram.tsx` (3.6) —
 * it renders outright in `environment: 'node'` with `renderToStaticMarkup`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import PlanTable from '../../src/components/PlanTable';
import type { components } from '../../src/api/schema';

type PlannedRowOut = components['schemas']['PlannedRowOut'];

function row(overrides: Partial<PlannedRowOut> = {}): PlannedRowOut {
  return {
    seq: 1,
    path: 'plan',
    label: 'plan',
    kind: 'plan.check',
    gate: 'deterministic',
    status: 'planned',
    reason: null,
    with_resolved: {},
    frame: null,
    story_id: null,
    ...overrides,
  };
}

describe('PlanTable', () => {
  it('renders the plan row first, path · kind · gate', () => {
    const markup = renderToStaticMarkup(
      createElement(PlanTable, { rows: [row()], planError: null }),
    );

    expect(markup).toContain('data-testid="newwf-plan"');
    expect(markup).toContain('data-testid="newwf-plan-row-1"');
    expect(markup).toContain('plan');
    expect(markup).toContain('plan.check');
    expect(markup).toContain('deterministic');
  });

  it('replaces the gate cell with skipped · {reason}, never green, for a skipped row', () => {
    const markup = renderToStaticMarkup(
      createElement(PlanTable, {
        rows: [
          row({
            seq: 2,
            path: 'story-1',
            kind: 'agent',
            status: 'skipped',
            reason: 'already done',
          }),
        ],
        planError: null,
      }),
    );

    expect(markup).toContain('skipped · already done');
    expect(markup).not.toContain('>deterministic<');
  });

  it('renders one red plan-error line instead of a table when the plan could not be built', () => {
    const markup = renderToStaticMarkup(
      createElement(PlanTable, {
        rows: null,
        planError: {
          reason: 'unknown input',
          template: 'epic',
          version: 1,
          line: 4,
          item: 'branch',
        },
      }),
    );

    expect(markup).toContain('data-testid="newwf-plan"');
    expect(markup).toContain('data-signal="failed"');
    expect(markup).toContain('plan error · epic@1 · line 4 · unknown input');
    expect(markup).not.toContain('<table');
  });
});
