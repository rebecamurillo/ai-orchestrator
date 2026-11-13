/** The Run page CHART view: the same rows the tables read, drawn (EXPERIENCE §5.12). */
import type { components } from '../../api/schema';
import { runCharts, seriesKey, type PairRow } from '../../lib/charts/run-charts';
import type { TargetContext } from '../../lib/run/metrics-glance';
import type { MetricsSet } from '../../lib/run/metrics-tab';
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
}

export default function RunCharts({ entries, items, stepOrder, set, ctx }: Props) {
  const label = (id: string): string => entries[id]?.label ?? id;
  return (
    <div className="chart-view" data-testid="wf-metrics-charts">
      {runCharts(entries, items, stepOrder, set).map((chart) => {
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
      })}
    </div>
  );
}
