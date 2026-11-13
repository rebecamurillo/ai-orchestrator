/** The Run page CHART view: the same rows the tables read, drawn (EXPERIENCE §5.12). */
import { useState } from 'react';

import type { components } from '../../api/schema';
import { runCharts, seriesKey, type PairRow, type RunChart } from '../../lib/charts/run-charts';
import {
  exportFileName,
  exportSvg,
  svgDataUrl,
  today,
  writePng,
  type Background,
  type ExportMeta,
} from '../../lib/charts/export';
import type { TargetContext } from '../../lib/run/metrics-glance';
import type { MetricsSet } from '../../lib/run/metrics-tab';
import { BACKGROUNDS, PREVIEWS, Switch, type Preview } from './ChartSwitch';
import BarChart from './BarChart';
import PairedBarChart from './PairedBarChart';
import TimeStrip from './TimeStrip';

type MetricValueOut = components['schemas']['MetricValueOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

interface Props {
  entries: Record<string, CatalogueEntryOut>;
  items: readonly MetricValueOut[];
  stepOrder: readonly string[];
  set: MetricsSet;
  ctx: TargetContext;
  exportMeta?: Omit<ExportMeta, 'entries' | 'date'>;
}

export default function RunCharts({ entries, items, stepOrder, set, ctx, exportMeta }: Props) {
  const [background, setBackground] = useState<Background>('transparent');
  const [preview, setPreview] = useState<Preview>('screen');
  const [failure, setFailure] = useState<string | null>(null);
  const charts = runCharts(entries, items, stepOrder, set);
  if (exportMeta === undefined) {
    return (
      <div className="chart-view" data-testid="wf-metrics-charts">
        {charts.map((chart) => screenChart(chart, entries, ctx))}
      </div>
    );
  }
  const meta: ExportMeta = { ...exportMeta, entries, date: today() };
  const download = (chart: RunChart): void => {
    setFailure(null);
    const file = exportFileName(meta.project, meta.runLabel, chart.title, meta.date);
    writePng(exportSvg(chart, meta, background), file).catch((error: unknown) =>
      setFailure(error instanceof Error ? error.message : String(error)),
    );
  };
  return (
    <div className="chart-view" data-testid="wf-metrics-charts">
      <div className="chart-export-bar">
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
        {failure !== null ? (
          <p className="chart-export-error">PNG not written · {failure}</p>
        ) : null}
      </div>
      {charts.map((chart) => (
        <div className="chart-slot" key={chart.title}>
          <button
            type="button"
            className="chart-png"
            aria-label={`PNG ${chart.title}`}
            onClick={() => download(chart)}
          >
            PNG
          </button>
          {preview === 'screen' ? (
            screenChart(chart, entries, ctx)
          ) : (
            <img
              className="chart-preview"
              alt={chart.title}
              src={svgDataUrl(exportSvg(chart, meta, preview))}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function screenChart(
  chart: RunChart,
  entries: Record<string, CatalogueEntryOut>,
  ctx: TargetContext,
) {
  const label = (id: string): string => entries[id]?.label ?? id;
  if (chart.kind === 'pair') {
    const shared = chart.rows.some((r: PairRow) => r.gatewayShare || r.harnessShare);
    return (
      <PairedBarChart
        key={chart.title}
        title={chart.title}
        keyText={seriesKey(entries, chart, shared)}
        rows={chart.rows}
        unit={chart.unit}
        ctx={ctx}
        labels={{ gateway: label('cost.gateway'), harness: label('cost.harness') }}
      />
    );
  }
  if (chart.kind === 'time') {
    return (
      <TimeStrip
        key={chart.title}
        title={chart.title}
        keyText={seriesKey(entries, chart, false)}
        rows={chart.rows}
        ctx={ctx}
      />
    );
  }
  return (
    <BarChart
      key={chart.title}
      title={chart.title}
      keyText={seriesKey(entries, chart, false)}
      rows={chart.rows}
      unit={chart.unit}
      ctx={ctx}
      seriesLabel={label(chart.metricIds[0])}
    />
  );
}
