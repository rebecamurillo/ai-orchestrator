/**
 * The Run page's metric glance: the gateway / harness figure pair, retries, waiting on you and
 * the version line. Strings come from `lib/run/metrics-glance.ts`, labels and reasons from the
 * catalogue; a missing value prints its word, never `0` (EXPERIENCE §4, §6).
 */
import { useStore } from '@nanostores/react';

import type { components } from '../../api/schema';
import type { RunDetailOut } from '../../lib/run/detail';
import { NOT_AVAILABLE_WORD } from '../../lib/metrics/format';
import {
  figuresDiffer,
  isEnded,
  NO_VERSION,
  retriesCount,
  RUNNING_WORD,
  runValue,
  targetFor,
  versionLine,
} from '../../lib/run/metrics-glance';
import { $catalogue, entryOf, methodOf } from '../../stores/catalogue';
import type { RunMetricsState } from '../../stores/run-metrics';
import FigurePair from '../metrics/FigurePair';
import HintControl from '../metrics/HintControl';
import MissingWord from '../metrics/MissingWord';
import ValueCell from '../metrics/ValueCell';
import FiguresDifferCard from './FiguresDifferCard';

type MetricValueOut = components['schemas']['MetricValueOut'];

interface Props {
  detail: RunDetailOut;
  glance: RunMetricsState;
  subscription: boolean;
}

function latestOf(glance: RunMetricsState): number | null {
  return glance.metrics?.latest ?? null;
}

function context(detail: RunDetailOut, glance: RunMetricsState, subscription: boolean) {
  return {
    runLabel: detail.run.label ?? detail.run.branch,
    versions: glance.versions,
    selected: glance.selected,
    latest: latestOf(glance),
    projectName: detail.header.meta.project,
    items: glance.metrics?.items ?? [],
    subscription,
  };
}

/** The figures-differ card, or nothing when the figures agree or either is missing. */
export function FiguresGap({ glance }: { glance: RunMetricsState }) {
  useStore($catalogue);
  const items = glance.metrics?.items ?? [];
  const differ = figuresDiffer(runValue(items, 'cost.gateway'), runValue(items, 'cost.harness'));
  if (!differ) return null;
  const entry = entryOf('cost.figure_gap');
  const gap = runValue(items, 'cost.figure_gap');
  const method = entry
    ? gap
      ? methodOf(entry, gap.method_id)
      : (entry.methods.at(-1) ?? null)
    : null;
  return (
    <FiguresDifferCard line={differ.line} gate={differ.gate} reason={method?.description ?? null} />
  );
}

export default function CostGlance({ detail, glance, subscription }: Props) {
  const metrics = glance.metrics;
  if (!metrics) return null;
  const ctx = context(detail, glance, subscription);
  const ended = isEnded(detail.run.status);
  if (ended && !metrics.values_so_far && metrics.latest === null) {
    return <p className="wf-glance-none">{NO_VERSION}</p>;
  }

  const cell = (value: MetricValueOut | null) =>
    value ? (
      <ValueCell target={targetFor(value, ctx)} />
    ) : (
      <MissingWord word={NOT_AVAILABLE_WORD} />
    );
  const { items } = metrics;
  const gateway = runValue(items, 'cost.gateway');
  const harness = runValue(items, 'cost.harness');
  const count = retriesCount(items);
  const shown = glance.selected ?? metrics.latest;
  const line = shown === null ? null : versionLine(glance.versions, shown);

  return (
    <div className="wf-glance" data-testid="wf-glance">
      {line ? <p className="wf-version-line">{line}</p> : null}
      <FigurePair
        gateway={gateway ? targetFor(gateway, ctx) : null}
        harness={harness ? targetFor(harness, ctx) : null}
        subscription={subscription}
        gatewayMetricId="cost.gateway"
        harnessMetricId="cost.harness"
      />
      {metrics.values_so_far ? (
        <div className="wf-glance-running-row">
          <span className="wf-glance-running">{RUNNING_WORD}</span>
          <span className="wf-glance-running">{RUNNING_WORD}</span>
        </div>
      ) : null}
      <p className="wf-glance-row">
        retries {count === null ? <MissingWord word={NOT_AVAILABLE_WORD} /> : <span>{count}</span>}
        {' · of which '}
        {cell(runValue(items, 'cost.retries', 'gateway'))} gateway{' · '}
        {cell(runValue(items, 'cost.retries', 'harness'))} harness{' · '}
        {cell(runValue(items, 'time.retries'))}
        <HintControl metricId="process.retries" />
      </p>
      <p className="wf-glance-row">
        waiting on you {cell(runValue(items, 'time.parked'))}
        <HintControl metricId="time.parked" />
      </p>
    </div>
  );
}
