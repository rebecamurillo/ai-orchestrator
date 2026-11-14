/** TIER 3 · FROM WORKFLOW STEPS: the test-first line and each step-produced metric, run scope. */
import { Fragment } from 'react';

import type { components } from '../../api/schema';
import {
  NA_WORD,
  TEST_FIRST,
  TIER_3,
  sourceWord,
  testFirstLine,
  tierThree,
  type StaticCell,
} from '../../lib/metrics/static-signals';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import HintControl from '../metrics/HintControl';
import MissingWord from '../metrics/MissingWord';
import ValueCell from '../metrics/ValueCell';

type MetricValueOut = components['schemas']['MetricValueOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

interface Props {
  items: readonly MetricValueOut[];
  stepEntries: readonly CatalogueEntryOut[];
  set: 'headline' | 'all';
  ctx: TargetContext;
}

const stored = (items: readonly MetricValueOut[], source: string): string | null =>
  items.find(
    (v) =>
      v.metric_id === TEST_FIRST &&
      v.scope_type === 'run' &&
      v.scope_key === 'run' &&
      v.source === source,
  )?.value_num ?? null;

function Cells({ cells, ctx }: { cells: StaticCell[]; ctx: TargetContext }) {
  return (
    <>
      {cells.map((cell, at) => (
        <Fragment key={at}>
          {at > 0 && ' · '}
          <span className="static-cell">
            <span className="metric-label">{sourceWord(cell.source)} </span>
            <ValueCell target={targetFor(cell as MetricValueOut, ctx)} />
          </span>
        </Fragment>
      ))}
    </>
  );
}

export default function StaticTierThree({ items, stepEntries, set, ctx }: Props) {
  const { testFirst, steps } = tierThree(items, stepEntries, set);
  const nothing = testFirst === null && steps.every((s) => s.cells.length === 0);
  return (
    <>
      <tr className="tier">
        <th colSpan={3} scope="colgroup">
          {TIER_3}
        </th>
      </tr>
      {nothing && (
        <tr>
          <td colSpan={3}>
            <MissingWord word={NA_WORD} />
          </td>
        </tr>
      )}
      {!nothing && testFirst !== null && (
        <tr data-testid={`static-row-run-${TEST_FIRST}`}>
          <td>
            <HintControl metricId={TEST_FIRST} />{' '}
            {testFirstLine(stored(items, 'readable'), stored(items, 'stories'))}
          </td>
          <td colSpan={2}>
            <Cells cells={testFirst} ctx={ctx} />
          </td>
        </tr>
      )}
      {!nothing &&
        steps.map((step) => (
          <tr key={step.metricId} data-testid={`static-row-run-${step.metricId}`}>
            <td>
              <HintControl metricId={step.metricId} showLabel />
            </td>
            <td colSpan={2}>
              {step.cells.length === 0 ? '—' : <Cells cells={step.cells} ctx={ctx} />}
            </td>
          </tr>
        ))}
    </>
  );
}
