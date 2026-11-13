/**
 * The METRICS tab: view and metric-set toggles, the version selector, then the by-scope tree,
 * the by-role and by-model tables and the metric list. Every string this tab authors lives in
 * `lib/run/metrics-tab.ts`; labels, hints and missing words come from the catalogue and API.
 */
import { useStore } from '@nanostores/react';

import FailedFetch from '../FailedFetch';
import type { RunDetailOut } from '../../lib/run/detail';
import { versionLine, type TargetContext } from '../../lib/run/metrics-glance';
import {
  LIVE_LINE,
  NO_ATTEMPTS,
  NO_VERSION_LINE,
  SET_LABELS,
  VIEW_LABELS,
  type MetricsSet,
  type MetricsView,
} from '../../lib/run/metrics-tab';
import { isEnded } from '../../lib/run/metrics-glance';
import { $metricsTab, setSet, setView } from '../../stores/metrics-tab';
import type { RunMetricsState } from '../../stores/run-metrics';
import VersionSelector from '../metrics/VersionSelector';
import MetricsFlatTable from './MetricsFlatTable';
import MetricsList from './MetricsList';
import MetricsScopeTable from './MetricsScopeTable';

interface Props {
  detail: RunDetailOut;
  glance: RunMetricsState;
  onSelectVersion: (n: number) => void;
  onRetryMetrics: () => void;
}

export function metricsContext(
  detail: RunDetailOut,
  glance: RunMetricsState,
  subscription: boolean,
): TargetContext {
  return {
    runLabel: detail.run.label ?? detail.run.branch,
    versions: glance.versions,
    selected: glance.selected,
    latest: glance.metrics?.latest ?? null,
    projectName: detail.header.meta.project,
    items: glance.metrics?.items ?? [],
    subscription,
  };
}

function Toggle<T extends string>({
  label,
  options,
  current,
  onPick,
  disabled,
}: {
  label: string;
  options: Record<T, string>;
  current: T;
  onPick: (next: T) => void;
  disabled?: T;
}) {
  return (
    <div className="wf-metrics-toggle" role="group" aria-label={label}>
      {(Object.keys(options) as T[]).map((key) => (
        <button
          key={key}
          type="button"
          className="wf-metrics-toggle-btn"
          aria-pressed={current === key}
          disabled={disabled === key}
          onClick={() => onPick(key)}
        >
          {options[key]}
        </button>
      ))}
    </div>
  );
}

export default function MetricsTab({ detail, glance, onSelectVersion, onRetryMetrics }: Props) {
  const { set } = useStore($metricsTab);
  const metrics = glance.metrics;
  const queued = detail.run.status === 'queued';
  const noVersion =
    metrics !== null &&
    isEnded(detail.run.status) &&
    !metrics.values_so_far &&
    metrics.latest === null;
  const shown = metrics === null ? null : (glance.selected ?? metrics.latest);
  const line = shown === null ? null : versionLine(glance.versions, shown);
  const ctx = metricsContext(detail, glance, false);
  const items = metrics?.items ?? [];
  const stepOrder = [...detail.steps].sort((a, b) => a.seq - b.seq).map((s) => s.path);

  return (
    <div className="wf-metrics" data-testid="wf-metrics">
      <div className="wf-metrics-head" data-testid="wf-metrics-head">
        <Toggle<MetricsView>
          label="view"
          options={VIEW_LABELS}
          current="table"
          onPick={setView}
          disabled="chart"
        />
        <Toggle<MetricsSet> label="metric set" options={SET_LABELS} current={set} onPick={setSet} />
        {!queued && !noVersion && shown !== null && glance.versions.length > 0 ? (
          <VersionSelector versions={glance.versions} selected={shown} onSelect={onSelectVersion} />
        ) : null}
        {line ? <p className="wf-version-line">{line}</p> : null}
      </div>
      {glance.status === 'failed' && glance.failed ? (
        <FailedFetch
          method="GET"
          path={glance.failed.path}
          status={glance.failed.status}
          onRetry={onRetryMetrics}
        />
      ) : null}
      {queued ? <p className="wf-metrics-note">{NO_ATTEMPTS}</p> : null}
      {!queued && noVersion ? <p className="wf-metrics-note">{NO_VERSION_LINE}</p> : null}
      {!queued && metrics !== null && !noVersion ? (
        <>
          {metrics.values_so_far ? <p className="wf-metrics-note">{LIVE_LINE}</p> : null}
          <h3 className="wf-metrics-section">BY SCOPE</h3>
          <MetricsScopeTable items={items} stepOrder={stepOrder} ctx={ctx} />
          <MetricsFlatTable scopeType="role" items={items} ctx={ctx} />
          <MetricsFlatTable scopeType="model" items={items} ctx={ctx} />
          <MetricsList items={items} set={set} ctx={ctx} />
        </>
      ) : null}
    </div>
  );
}
