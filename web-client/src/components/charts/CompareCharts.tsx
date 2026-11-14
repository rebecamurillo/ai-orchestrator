/** The comparison CHART view (EXPERIENCE §5.12): charts from the payload the page already holds. */
import { useState } from 'react';

import type { components } from '../../api/schema';
import { chartsFor, type CompareChart } from '../../lib/charts/compare-charts';
import { compareSvg, pngAll, type CompareExportMeta } from '../../lib/charts/compare-png';
import { FOLLOWING, NOT_SPLIT_LINE } from '../../lib/charts/compare-runs';
import { exportFileName, today, writePng, type Background } from '../../lib/charts/export';
import type { CompareState } from '../../lib/metrics/compare';
import CompareChartPanel from './CompareChartPanel';
import { BACKGROUNDS, PREVIEWS, Switch, type Preview } from './ChartSwitch';
import './charts.css';

type CompareOut = components['schemas']['CompareOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

interface Props {
  payload: CompareOut;
  entries: Record<string, CatalogueEntryOut>;
  set: CompareState['set'];
  stepOrder: readonly string[];
}

type Breakdown = 'total' | 'role' | 'model';
type Roles = 'declared' | 'family';

const BREAKDOWNS: [Breakdown, string][] = [
  ['total', 'TOTAL'],
  ['role', 'ROLE'],
  ['model', 'MODEL'],
];
const ROLES: [Roles, string][] = [
  ['declared', 'AS DECLARED'],
  ['family', 'ROLE FAMILY (proposal)'],
];

function Segments<T extends string>(props: {
  label: string;
  prefix: string;
  options: [T, string][];
  current: T;
  onPick: (next: T) => void;
}) {
  return (
    <div className="compare-segments" role="group" aria-label={props.label}>
      {props.options.map(([key, text]) => (
        <button
          key={key}
          type="button"
          className="metric-version-segment"
          aria-pressed={key === props.current}
          data-testid={`${props.prefix}-${key}`}
          onClick={() => props.onPick(key)}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

export default function CompareCharts({ payload, entries, set, stepOrder }: Props) {
  const [breakdown, setBreakdown] = useState<Breakdown>('total');
  const [roles, setRoles] = useState<Roles>('declared');
  const [followed, setFollowed] = useState<string | null>(null);
  const [background, setBackground] = useState<Background>('transparent');
  const [preview, setPreview] = useState<Preview>('screen');
  const [failure, setFailure] = useState<string | null>(null);
  const charts = chartsFor(payload, entries, { breakdown, roles, set, stepOrder });
  const meta: CompareExportMeta = {
    entries,
    project: payload.project_name,
    headers: payload.runs,
    date: today(),
  };
  const fail = (error: unknown): void =>
    setFailure(error instanceof Error ? error.message : String(error));
  const download = (chart: CompareChart): void => {
    setFailure(null);
    const file = exportFileName(meta.project, 'compare', chart.title, meta.date);
    writePng(compareSvg(chart, meta, background), file).catch(fail);
  };
  const followedLabel = payload.runs.find((h) => h.run_id === followed)?.label;
  return (
    <div className="chart-view" data-testid="compare-charts">
      <div className="compare-chart-controls">
        <span className="compare-chart-label">BREAK DOWN BY:</span>
        <Segments
          label="break down by"
          prefix="compare-breakdown"
          options={BREAKDOWNS}
          current={breakdown}
          onPick={setBreakdown}
        />
        {breakdown === 'role' ? (
          <>
            <span className="compare-chart-label">ROLES:</span>
            <Segments
              label="roles"
              prefix="compare-roles"
              options={ROLES}
              current={roles}
              onPick={setRoles}
            />
          </>
        ) : null}
        <button
          type="button"
          className="chart-png-all"
          data-testid="compare-png-all"
          onClick={() => {
            setFailure(null);
            pngAll(charts, meta, background).catch(fail);
          }}
        >
          PNG · all charts
        </button>
        <Switch
          label="PNG background"
          options={BACKGROUNDS}
          current={background}
          onPick={setBackground}
        />
        <Switch
          label="preview PNG ink on"
          options={PREVIEWS}
          current={preview}
          onPick={setPreview}
        />
      </div>
      <p role="status" className="compare-chart-line" data-testid="compare-following">
        {followedLabel === undefined ? '' : FOLLOWING(followedLabel)}
      </p>
      {failure !== null ? (
        <p className="chart-export-error" data-testid="compare-png-failed">
          PNG not written · {failure}
        </p>
      ) : null}
      {charts.map((chart) => (
        <CompareChartPanel
          key={chart.title}
          chart={chart}
          headers={payload.runs}
          followed={followed}
          onFollow={(id) => setFollowed(followed === id ? null : id)}
          onPng={download}
          preview={preview}
          meta={meta}
        />
      ))}
      {breakdown !== 'total' ? (
        <p className="compare-chart-line" data-testid="compare-not-split">
          {NOT_SPLIT_LINE}
        </p>
      ) : null}
    </div>
  );
}
